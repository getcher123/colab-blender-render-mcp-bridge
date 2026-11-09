#!/usr/bin/env python3
"""Blender 4.5 LTS / Colab: self-contained Cycles GPU test; A100 is the default.

Run inside Blender, not ordinary Python:
  blender --background --factory-startup --python-exit-code 1 \
    --python render_test.py -- --output-dir /content/blender-a100/output

Outputs: test_scene.blend, test_render.png, render_report.json,
         gpu_samples.csv, blender_gpu_processes.csv.

The test refuses to render without the expected GPU exposed to Cycles, disables
all CPU rendering devices, and refuses to report success without NVIDIA GPU
telemetry during the render. An explicit --expected-gpu L4 permits an integration
test when Colab cannot allocate A100; the report retains requested_user_gpu=A100
and target_a100_met=false, and the render's plaque names the actual expected GPU.
CPU scene preparation and OpenImageDenoise are normal parts of Blender's pipeline
and are not a CPU rendering fallback.
No external meshes, textures, fonts, or Python packages are needed.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time
import traceback

import bpy
from mathutils import Vector


def arguments():
    tail = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="/content/blender-a100/output")
    parser.add_argument("--backend", choices=("CUDA", "OPTIX", "AUTO"), default="CUDA")
    parser.add_argument("--expected-gpu", default="A100",
                        help="Required GPU family for this run; defaults to the user's A100 target")
    parser.add_argument("--samples", type=int, default=96)
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=1000)
    args = parser.parse_args(tail)
    if not (16 <= args.samples <= 512):
        parser.error("--samples must be between 16 and 512")
    if not (256 <= args.width <= 4096 and 256 <= args.height <= 4096):
        parser.error("Both image dimensions must be between 256 and 4096")
    return args


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def command_text(command, timeout=20):
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {command!r}\n{result.stderr}")
    return result.stdout.strip()


def csv_rows(text, names):
    rows = []
    for values in csv.reader(text.splitlines()):
        if len(values) == len(names):
            rows.append({key: value.strip() for key, value in zip(names, values)})
    return rows


def number(value):
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def matches_gpu(name, expected_gpu):
    return bool(re.search(r"(?<![A-Z0-9])" + re.escape(expected_gpu.upper()) + r"(?![A-Z0-9])",
                          name.upper()))


def nvidia_hardware(expected_gpu):
    if not shutil.which("nvidia-smi"):
        raise RuntimeError(f"nvidia-smi is absent. Attach a Colab NVIDIA {expected_gpu} GPU runtime first.")
    fields = ("index", "name", "uuid", "driver_version", "memory.total", "memory.used")
    text = command_text(["nvidia-smi", "--query-gpu=" + ",".join(fields),
                         "--format=csv,noheader,nounits"])
    rows = csv_rows(text, fields)
    if not any(matches_gpu(row["name"], expected_gpu) for row in rows):
        raise RuntimeError(f"This run requires NVIDIA {expected_gpu}, but nvidia-smi found: {rows!r}")
    return rows


def device_record(device):
    return {"name": device.name, "type": device.type, "id": device.id,
            "enabled": bool(device.use)}


def configure_gpu(backend, expected_gpu):
    if "cycles" not in bpy.context.preferences.addons:
        bpy.ops.preferences.addon_enable(module="cycles")
    prefs = bpy.context.preferences.addons["cycles"].preferences
    attempts = []
    candidates = ("CUDA", "OPTIX") if backend == "AUTO" else (backend,)
    for candidate in candidates:
        try:
            prefs.compute_device_type = candidate
            if hasattr(prefs, "refresh_devices"):
                prefs.refresh_devices()
            else:
                prefs.get_devices()
            if hasattr(prefs, "get_devices_for_type"):
                prefs.get_devices_for_type(candidate)
            for device in prefs.devices:
                device.use = False
            selected = [device for device in prefs.devices
                        if device.type == candidate and matches_gpu(device.name, expected_gpu)]
            for device in selected:
                device.use = True
            snapshot = [device_record(device) for device in prefs.devices]
            attempts.append({"backend": candidate, "devices": snapshot})
            if selected:
                bpy.context.scene.render.engine = "CYCLES"
                bpy.context.scene.cycles.device = "GPU"
                return prefs, candidate, attempts
        except Exception as exc:
            attempts.append({"backend": candidate, "error": str(exc)})
    raise RuntimeError(f"Cycles cannot access NVIDIA {expected_gpu}; CPU fallback is not allowed. "
                       + json.dumps(attempts))


class NvidiaMonitor:
    """External processes avoid Python threads accessing Blender during rendering."""

    GPU_FIELDS = ("timestamp", "index", "name", "uuid", "utilization.gpu", "memory.used", "power.draw")
    PROCESS_FIELDS = ("pid", "process_name", "gpu_uuid", "used_memory")

    def __init__(self, directory, expected_gpu):
        self.directory = directory
        self.expected_gpu = expected_gpu
        self.processes = []
        self.handles = []
        self.paths = {"gpu": directory / "gpu_samples.csv",
                      "process": directory / "blender_gpu_processes.csv"}

    def start(self):
        for key, fields, query in (
                ("gpu", self.GPU_FIELDS, "--query-gpu="),
                ("process", self.PROCESS_FIELDS, "--query-compute-apps=")):
            handle = self.paths[key].open("w", encoding="utf-8")
            self.handles.append(handle)
            process = subprocess.Popen(
                ["nvidia-smi", query + ",".join(fields),
                 "--format=csv,noheader,nounits", "--loop-ms=250"],
                stdout=handle, stderr=subprocess.STDOUT, text=True)
            self.processes.append(process)

    def stop(self):
        for process in self.processes:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        for handle in self.handles:
            if not handle.closed:
                handle.close()

    def evidence(self, hardware):
        gpu_rows = csv_rows(self.paths["gpu"].read_text(encoding="utf-8"), self.GPU_FIELDS)
        process_rows = csv_rows(self.paths["process"].read_text(encoding="utf-8"), self.PROCESS_FIELDS)
        own_pids = {str(os.getpid())}
        status_path = Path("/proc/self/status")
        if status_path.exists():
            for line in status_path.read_text().splitlines():
                if line.startswith("NSpid:"):
                    own_pids.update(line.split()[1:])
        expected_uuids = {row["uuid"] for row in hardware if matches_gpu(row["name"], self.expected_gpu)}
        matching = [row for row in process_rows
                    if row["pid"] in own_pids and row["gpu_uuid"] in expected_uuids
                    and (number(row["used_memory"]) or 0) > 0]
        relevant = [row for row in gpu_rows if row["uuid"] in expected_uuids]
        utilization = [number(row["utilization.gpu"]) for row in relevant]
        utilization = [value for value in utilization if value is not None]
        memory = [number(row["used_memory"]) for row in matching]
        memory = [value for value in memory if value is not None]
        return {
            "blender_pid": os.getpid(),
            "namespace_pids": sorted(own_pids),
            "gpu_sample_count": len(relevant),
            "blender_process_sample_count": len(matching),
            "max_expected_gpu_utilization_percent": max(utilization, default=0),
            "max_blender_gpu_memory_mib": max(memory, default=0),
            "matching_blender_gpu_process_observed": bool(matching),
            "positive_expected_gpu_utilization_observed": max(utilization, default=0) > 0,
            "first_matching_process": matching[0] if matching else None,
            "last_matching_process": matching[-1] if matching else None,
            "gpu_csv": str(self.paths["gpu"]),
            "process_csv": str(self.paths["process"]),
        }


def material(name, color, metallic=0, roughness=0.35, transmission=0,
             coat=0, ior=1.46, microtexture=False):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    shader = nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Metallic"].default_value = metallic
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["IOR"].default_value = ior
    shader.inputs["Transmission Weight"].default_value = transmission
    shader.inputs["Coat Weight"].default_value = coat
    shader.inputs["Coat Roughness"].default_value = 0.19
    if microtexture:
        noise = nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 240
        noise.inputs["Detail"].default_value = 2
        bump = nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.12
        bump.inputs["Distance"].default_value = 0.003
        mat.node_tree.links.new(noise.outputs["Fac"], bump.inputs["Height"])
        mat.node_tree.links.new(bump.outputs["Normal"], shader.inputs["Normal"])
    return mat


def finish(obj, name, mat, smooth=True, bevel=0):
    obj.name = name
    obj.data.materials.append(mat)
    if obj.type == "MESH":
        for polygon in obj.data.polygons:
            polygon.use_smooth = smooth and len(polygon.vertices) <= 4
    if bevel:
        modifier = obj.modifiers.new("Machined edge radii", "BEVEL")
        modifier.width = bevel
        modifier.segments = 3
        modifier.limit_method = "ANGLE"
        modifier.harden_normals = True
        normals = obj.modifiers.new("Weighted machining normals", "WEIGHTED_NORMAL")
        normals.keep_sharp = True
        normals.weight = 50
    return obj


def orient(obj, axis):
    obj.rotation_euler = Vector(axis).to_track_quat("Z", "Y").to_euler()
    return obj


def cylinder(name, radius, depth, location, mat, axis=(0, 0, 1), bevel=0.012, vertices=96):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth,
                                       end_fill_type="NGON", location=location)
    obj = finish(bpy.context.object, name, mat, bevel=bevel)
    return orient(obj, axis)


def box(name, location, dimensions, mat, bevel=0.025):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return finish(obj, name, mat, smooth=False, bevel=bevel)


def torus(name, major, minor, location, mat, axis=(0, 0, 1)):
    bpy.ops.mesh.primitive_torus_add(major_segments=128, minor_segments=20,
                                    major_radius=major, minor_radius=minor, location=location)
    return orient(finish(bpy.context.object, name, mat), axis)


def rod(name, start, end, radius, mat, vertices=48):
    start, end = Vector(start), Vector(end)
    return cylinder(name, radius, (end - start).length, (start + end) / 2,
                    mat, axis=end - start, bevel=min(radius / 3, 0.008), vertices=vertices)


def tube_curve(name, points, radius, mat, poly=False):
    data = bpy.data.curves.new(name, "CURVE")
    data.dimensions = "3D"
    data.resolution_u = 24
    data.bevel_depth = radius
    data.bevel_resolution = 5
    data.use_fill_caps = True
    if poly:
        spline = data.splines.new("POLY")
        spline.points.add(len(points) - 1)
        for point, value in zip(spline.points, points):
            point.co = (*value, 1)
    else:
        spline = data.splines.new("BEZIER")
        spline.bezier_points.add(len(points) - 1)
        for point, value in zip(spline.bezier_points, points):
            point.co = value
            point.handle_left_type = "AUTO"
            point.handle_right_type = "AUTO"
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    data.materials.append(mat)
    return obj


def glass_shell(name, x, y, bottom, top, outer_radius, thickness, mat, segments=128):
    # Four concentric loops form a genuinely hollow, closed manifold glass wall.
    vertices = []
    for radius, z in ((outer_radius, bottom), (outer_radius, top),
                      (outer_radius - thickness, bottom), (outer_radius - thickness, top)):
        vertices.extend((x + radius * math.cos(2 * math.pi * index / segments),
                         y + radius * math.sin(2 * math.pi * index / segments), z)
                        for index in range(segments))
    faces = []
    for i in range(segments):
        j = (i + 1) % segments
        faces.extend(((i, j, segments + j, segments + i),
                      (2 * segments + j, 2 * segments + i, 3 * segments + i, 3 * segments + j),
                      (segments + i, segments + j, 3 * segments + j, 3 * segments + i),
                      (j, i, 2 * segments + i, 2 * segments + j)))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    finish(obj, name, mat)
    for index, face in enumerate(mesh.polygons):
        face.use_smooth = index % 4 < 2
    return obj


def text_object(name, body, location, size, mat, rotation=(0, 0, 0)):
    data = bpy.data.curves.new(name, "FONT")
    data.body = body
    data.align_x = "CENTER"
    data.align_y = "CENTER"
    data.size = size
    data.extrude = 0.0008
    data.bevel_depth = 0.0004
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = rotation
    data.materials.append(mat)
    return obj


def area_light(name, location, target, energy, color, size, size_y=None):
    light = bpy.data.lights.new(name, "AREA")
    light.energy = energy
    light.color = color
    light.shape = "RECTANGLE" if size_y else "DISK"
    light.size = size
    if size_y:
        light.size_y = size_y
    obj = bpy.data.objects.new(name, light)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()
    return obj


def build_scene(args):
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.render.engine = "CYCLES"
    scene.cycles.device = "GPU"
    scene.cycles.samples = args.samples
    scene.cycles.seed = 211
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = 0.015
    scene.cycles.adaptive_min_samples = 16
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = "OPENIMAGEDENOISE"
    if hasattr(scene.cycles, "denoising_use_gpu"):
        scene.cycles.denoising_use_gpu = False
    scene.cycles.max_bounces = 12
    scene.cycles.diffuse_bounces = 4
    scene.cycles.glossy_bounces = 6
    scene.cycles.transmission_bounces = 12
    scene.cycles.transparent_max_bounces = 8
    scene.cycles.sample_clamp_indirect = 3.0
    scene.cycles.blur_glossy = 0.5
    scene.cycles.caustics_reflective = False
    scene.cycles.caustics_refractive = False
    if hasattr(scene.cycles, "use_light_tree"):
        scene.cycles.use_light_tree = True
    scene.render.resolution_x = args.width
    scene.render.resolution_y = args.height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.image_settings.compression = 20
    scene.render.film_transparent = False
    scene.render.use_persistent_data = False
    scene.view_settings.view_transform = "AgX"
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    scene.view_settings.exposure = 0.15

    teal = material("Teal / anodized aluminium", (0.015, 0.235, 0.265), 0.7, 0.26, coat=0.28)
    brass = material("Satin brass", (0.63, 0.35, 0.12), 1, 0.24)
    copper = material("Copper heat exchanger", (0.57, 0.20, 0.073), 1, 0.23)
    steel = material("Machined stainless steel", (0.59, 0.67, 0.74), 1, 0.18)
    dark = material("Graphite elastomer", (0.008, 0.014, 0.021), 0.05, 0.43)
    navy = material("Midnight blue enamel", (0.014, 0.029, 0.046), 0.45, 0.28, coat=0.25)
    glass = material("Borosilicate glass / real wall thickness", (0.94, 0.985, 1.0),
                     roughness=0.035, transmission=1, ior=1.46)
    ivory = material("Warm porcelain", (0.65, 0.70, 0.71), roughness=0.41, microtexture=True)
    paper = material("Instrument dial white", (0.88, 0.88, 0.82), roughness=0.65)
    red = material("Burnt orange valve enamel", (0.52, 0.065, 0.022), 0.3, 0.26, coat=0.35)
    floor_mat = material("Studio floor", (0.021, 0.035, 0.055), 0.1, 0.42, microtexture=True)

    bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, -0.18))
    finish(bpy.context.object, "Seamless studio floor", floor_mat, smooth=False)
    cylinder("Circular graphite plinth", 2.95, 0.32, (0, 0, 0), navy, bevel=0.08, vertices=192)
    cylinder("Porcelain top", 2.90, 0.13, (0, 0, 0.215), ivory, bevel=0.035, vertices=192)
    torus("Fine brass perimeter inlay", 2.76, 0.009, (0, 0, 0.282), brass)

    x, y = -0.67, 0.20
    cylinder("Reactor foot", 0.99, 0.14, (x, y, 0.35), navy, bevel=0.04)
    cylinder("Reactor brass base ring", 0.89, 0.10, (x, y, 0.46), brass, bevel=0.018)
    cylinder("Lower teal head", 0.84, 0.28, (x, y, 0.64), teal, bevel=0.045)
    cylinder("Lower glass seal", 0.77, 0.065, (x, y, 0.805), dark, bevel=0.008)
    glass_shell("Transparent pressure chamber", x, y, 0.81, 3.23, 0.745, 0.027, glass)
    cylinder("Upper glass seal", 0.77, 0.065, (x, y, 3.235), dark, bevel=0.008)
    cylinder("Upper teal head", 0.84, 0.25, (x, y, 3.38), teal, bevel=0.04)
    cylinder("Top brass cover", 0.76, 0.085, (x, y, 3.55), brass, bevel=0.025)

    cylinder("Internal stainless core", 0.105, 2.44, (x, y, 2.015), steel, bevel=0.015)
    for index, z in enumerate((0.98, 2.01, 3.04)):
        cylinder(f"Internal support {index + 1}", 0.28, 0.04, (x, y, z), brass, bevel=0.008)
        for angle in (0, 2 * math.pi / 3, 4 * math.pi / 3):
            rod(f"Support spoke {index + 1}", (x, y, z),
                (x + 0.53 * math.cos(angle), y + 0.53 * math.sin(angle), z), 0.015, steel)
    turns, steps = 6, 960
    helix = [(x + 0.48 * math.cos(2 * math.pi * turns * i / steps),
              y + 0.48 * math.sin(2 * math.pi * turns * i / steps),
              0.94 + 2.13 * i / steps) for i in range(steps + 1)]
    tube_curve("Continuous six-turn copper heat exchanger", helix, 0.047, copper, poly=True)
    for angle in (math.pi / 4, 3 * math.pi / 4, 5 * math.pi / 4, 7 * math.pi / 4):
        px, py = x + 0.855 * math.cos(angle), y + 0.855 * math.sin(angle)
        rod("External tension rod", (px, py, 0.55), (px, py, 3.56), 0.028, steel)
        for z in (0.52, 3.57):
            cylinder("Hexagonal tension nut", 0.064, 0.065, (px, py, z), steel,
                     bevel=0.005, vertices=6)
    for index in range(12):
        angle = 2 * math.pi * index / 12
        cylinder("Top flange hex bolt", 0.037, 0.044,
                 (x + 0.665 * math.cos(angle), y + 0.665 * math.sin(angle), 3.615),
                 steel, bevel=0.004, vertices=6)

    # A compact pump makes the pipe connections and material differences readable.
    box("Pump mounting plate", (1.28, -0.05, 0.37), (1.18, 1.08, 0.15), navy, 0.045)
    for px in (0.94, 1.62):
        box("Pump support", (px, 0.02, 0.54), (0.17, 0.65, 0.29), teal, 0.03)
    cylinder("Pump motor housing", 0.43, 0.92, (1.28, 0.07, 0.93), teal, axis=(0, 1, 0), bevel=0.045)
    for index in range(8):
        torus("Motor cooling rib", 0.436, 0.018, (1.28, -0.25 + index * 0.085, 0.93),
              teal, axis=(0, 1, 0))
    cylinder("Pump front flange", 0.49, 0.13, (1.28, -0.455, 0.93), teal, axis=(0, 1, 0), bevel=0.023)
    cylinder("Pump brass face", 0.265, 0.075, (1.28, -0.55, 0.93), brass, axis=(0, 1, 0), bevel=0.02)
    cylinder("Pump stainless hub", 0.11, 0.085, (1.28, -0.60, 0.93), steel, axis=(0, 1, 0), bevel=0.02)
    for index in range(8):
        angle = 2 * math.pi * index / 8
        cylinder("Pump flange bolt", 0.036, 0.045,
                 (1.28 + 0.38 * math.cos(angle), -0.54, 0.93 + 0.38 * math.sin(angle)),
                 steel, axis=(0, 1, 0), bevel=0.004, vertices=6)

    tube_curve("Polished upper outlet pipe",
               [(0.09, 0.20, 3.38), (0.52, 0.20, 3.38), (0.90, 0.20, 3.11),
                (0.95, 0.20, 2.40), (0.95, 0.20, 1.70), (1.18, 0.20, 1.42),
                (1.28, 0.20, 1.30)], 0.069, steel)
    cylinder("Upper outlet union", 0.14, 0.14, (0.20, 0.20, 3.38), brass, axis=(1, 0, 0))
    cylinder("Pump inlet union", 0.14, 0.12, (1.28, 0.20, 1.34), brass)
    tube_curve("Lower return pipe",
               [(0.08, 0.20, 0.64), (0.40, 0.20, 0.64), (0.55, 0.63, 0.67),
                (0.98, 0.70, 0.81), (1.28, 0.64, 0.93)], 0.07, steel)

    # Side valve wheel, with real spokes instead of a flat disc.
    cylinder("Valve body", 0.135, 0.22, (0.95, 0.20, 2.26), brass)
    rod("Valve spindle", (0.95, 0.20, 2.26), (1.29, 0.20, 2.26), 0.035, steel)
    torus("Valve handwheel", 0.23, 0.025, (1.30, 0.20, 2.26), red, axis=(1, 0, 0))
    cylinder("Valve hub", 0.058, 0.06, (1.30, 0.20, 2.26), brass, axis=(1, 0, 0))
    for angle in (0, math.pi / 2, math.pi, 3 * math.pi / 2):
        rod("Valve spoke", (1.30, 0.20, 2.26),
            (1.30, 0.20 + 0.22 * math.cos(angle), 2.26 + 0.22 * math.sin(angle)), 0.014, red)

    # Small mechanical gauge: ring, ticks, pointer, and a separate glass lens.
    gx, gy, gz = x, -0.01, 3.94
    rod("Pressure gauge stem", (x, y, 3.58), (gx, gy, 3.84), 0.042, brass)
    cylinder("Gauge housing", 0.23, 0.10, (gx, gy, gz), steel, axis=(0, -1, 0), bevel=0.02)
    cylinder("Gauge dial", 0.205, 0.012, (gx, gy - 0.058, gz), paper, axis=(0, -1, 0), bevel=0.004)
    torus("Gauge polished bezel", 0.213, 0.016, (gx, gy - 0.066, gz), steel, axis=(0, -1, 0))
    for index in range(11):
        angle = math.radians(-45 + index * 27)
        start = (gx + 0.155 * math.cos(angle), gy - 0.069, gz + 0.155 * math.sin(angle))
        end = (gx + 0.18 * math.cos(angle), gy - 0.069, gz + 0.18 * math.sin(angle))
        rod("Gauge tick", start, end, 0.004, navy, vertices=12)
    rod("Gauge red pointer", (gx, gy - 0.078, gz),
        (gx - 0.095, gy - 0.078, gz + 0.11), 0.007, red, vertices=16)
    cylinder("Gauge needle pivot", 0.021, 0.016, (gx, gy - 0.082, gz), brass, axis=(0, -1, 0), bevel=0.003)
    cylinder("Gauge protective glass", 0.197, 0.009, (gx, gy - 0.092, gz), glass, axis=(0, -1, 0), bevel=0.002)

    box("Render test nameplate", (0, -1.83, 0.313), (2.55, 0.56, 0.045), navy, 0.04)
    text_object("GPU plaque title", f"{args.expected_gpu.upper()}  /  CYCLES", (0, -1.76, 0.339), 0.19, paper)
    text_object("Plaque subtitle", "PHYSICALLY BASED RENDER", (0, -1.96, 0.339), 0.063, brass)

    world = bpy.data.worlds.new("Cool studio ambient")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.16, 0.21, 0.30, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.30
    scene.world = world
    area_light("Warm softbox / key", (-4.5, -4, 7), (0, 0, 1.8), 1450, (1, 0.87, 0.72), 5)
    area_light("Cool softbox / fill", (5, -1.5, 4.5), (0, 0, 1.8), 1050, (0.66, 0.84, 1), 4)
    area_light("White strip / rim", (-1, 3.8, 6), (-0.4, 0.3, 2.0), 1750, (0.84, 0.95, 1), 3.5, 1.2)
    area_light("Front glass reflection", (-2, -5, 3.1), (-0.5, 0.2, 2), 270, (1, 0.98, 0.92), 1.2, 3.5)
    area_light("Warm edge accent", (3.5, 3, 3.5), (0, 0, 2), 650, (1, 0.64, 0.36), 2)

    bpy.ops.object.camera_add(location=(6.8, -10.4, 6.7))
    camera = bpy.context.object
    camera.name = "Studio hero camera"
    target = Vector((0.0, 0.0, 1.83))
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.lens = 53
    camera.data.sensor_width = 36
    camera.data.clip_start = 0.05
    camera.data.clip_end = 250
    focus = bpy.data.objects.new("Camera focus / chamber", None)
    bpy.context.collection.objects.link(focus)
    focus.location = (-0.05, 0.0, 1.8)
    camera.data.dof.use_dof = True
    camera.data.dof.focus_object = focus
    camera.data.dof.aperture_fstop = 9
    scene.camera = camera
    scene["scene_description"] = "Procedural studio engineering material test; conceptual apparatus, not a production drawing."
    scene["requested_user_gpu"] = "A100"
    scene["expected_gpu_this_run"] = args.expected_gpu
    return scene


def save_report(path, report):
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    args = arguments()
    directory = Path(args.output_dir).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    report_path = directory / "render_report.json"
    image_path = directory / "test_render.png"
    blend_path = directory / "test_scene.blend"
    report = {
        "status": "initializing",
        "started_at_utc": utc_now(),
        "blender_version": bpy.app.version_string,
        "blender_binary": bpy.app.binary_path,
        "platform": platform.platform(),
        "requested_user_gpu": "A100",
        "expected_gpu": args.expected_gpu,
        "target_a100_met": False,
        "requested_backend": args.backend,
        "artifacts": {"image": str(image_path), "blend": str(blend_path), "report": str(report_path)},
    }
    save_report(report_path, report)
    monitor = None
    started = time.perf_counter()
    try:
        hardware = nvidia_hardware(args.expected_gpu)
        report["nvidia_hardware_before"] = hardware
        prefs, backend, attempts = configure_gpu(args.backend, args.expected_gpu)
        report["backend"] = backend
        report["device_detection_attempts"] = attempts
        report["actual_gpu_names"] = [device.name for device in prefs.devices if device.use]
        report["target_a100_met"] = bool(report["actual_gpu_names"]) and all(
            matches_gpu(name, "A100") for name in report["actual_gpu_names"])
        print("GPU_SELECTED " + json.dumps({
            "requested_user_gpu": "A100", "expected_gpu": args.expected_gpu,
            "target_a100_met": report["target_a100_met"],
            "devices": [device_record(device) for device in prefs.devices if device.use]}), flush=True)
        scene = build_scene(args)
        report["cycles_devices"] = [device_record(device) for device in prefs.devices]
        report["render_settings"] = {
            "engine": scene.render.engine, "device": scene.cycles.device,
            "width": args.width, "height": args.height, "samples": args.samples,
            "adaptive_threshold": scene.cycles.adaptive_threshold,
            "denoiser": scene.cycles.denoiser,
            "denoising_device": "CPU (postprocessing; path tracing remains GPU-only)",
            "view_transform": scene.view_settings.view_transform,
            "objects": len(scene.objects),
        }
        enabled = [device for device in prefs.devices if device.use]
        assert scene.cycles.device == "GPU", "Scene unexpectedly changed to CPU"
        assert enabled and all(device.type == backend and matches_gpu(device.name, args.expected_gpu)
                               for device in enabled), "An unexpected rendering device was enabled"
        assert not any(device.use for device in prefs.devices if device.type == "CPU"), "CPU device was enabled"
        scene.render.filepath = str(image_path)
        source = bpy.data.texts.new("render_test.py")
        source.from_string(Path(__file__).read_text(encoding="utf-8"))
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), check_existing=False)
        report["status"] = "rendering"
        save_report(report_path, report)
        monitor = NvidiaMonitor(directory, args.expected_gpu)
        monitor.start()
        render_started = time.perf_counter()
        render_started_wall = time.time()
        render_result = bpy.ops.render.render(write_still=True)
        report["render_seconds"] = round(time.perf_counter() - render_started, 3)
        monitor.stop()
        evidence = monitor.evidence(hardware)
        report["gpu_evidence"] = evidence
        report["nvidia_hardware_after"] = nvidia_hardware(args.expected_gpu)
        report["verification"] = {
            "cycles_scene_device_is_gpu": scene.cycles.device == "GPU",
            "only_expected_gpu_cycles_devices_enabled": bool(enabled) and all(
                device.type == backend and matches_gpu(device.name, args.expected_gpu)
                for device in prefs.devices if device.use),
            "cpu_cycles_device_disabled": not any(device.use for device in prefs.devices if device.type == "CPU"),
            "matching_blender_gpu_process_observed": evidence["matching_blender_gpu_process_observed"],
            "positive_expected_gpu_utilization_observed": evidence["positive_expected_gpu_utilization_observed"],
            "render_operator_finished": "FINISHED" in render_result,
            "image_present_and_fresh": image_path.exists() and image_path.stat().st_size > 10000
                and image_path.stat().st_mtime >= render_started_wall - 1,
            "blend_present": blend_path.exists() and blend_path.stat().st_size > 10000,
        }
        if not all(report["verification"].values()):
            raise RuntimeError("The render finished, but strict GPU verification failed. "
                               "Read render_report.json and telemetry CSVs; do not claim GPU success.")
        report["status"] = ("success_verified_a100" if report["target_a100_met"]
                            else "success_verified_gpu_user_a100_target_unmet")
        report["completed_at_utc"] = utc_now()
        report["total_seconds"] = round(time.perf_counter() - started, 3)
        report["artifact_bytes"] = {"image": image_path.stat().st_size, "blend": blend_path.stat().st_size}
        save_report(report_path, report)
        print("GPU_RENDER_SUCCESS " + json.dumps({
            "status": report["status"], "requested_user_gpu": "A100",
            "actual_gpu_names": report["actual_gpu_names"], "target_a100_met": report["target_a100_met"],
            "backend": backend, "render_seconds": report["render_seconds"],
            "resolution": [args.width, args.height], "samples": args.samples,
            "image": str(image_path), "blend": str(blend_path), "report": str(report_path),
            "gpu_utilization_peak_percent": evidence["max_expected_gpu_utilization_percent"],
            "blender_gpu_memory_peak_mib": evidence["max_blender_gpu_memory_mib"],
        }), flush=True)
    except Exception as exc:
        if monitor:
            monitor.stop()
        report["status"] = "failed"
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()
        report["completed_at_utc"] = utc_now()
        report["total_seconds"] = round(time.perf_counter() - started, 3)
        save_report(report_path, report)
        print("GPU_RENDER_FAILED " + json.dumps({"error": str(exc), "report": str(report_path)}), flush=True)
        raise


if __name__ == "__main__":
    main()
