#!/usr/bin/env python3
"""Build cadastre-zones.geojson (buildings) and cadastre-roads.geojson (road network)."""
import json
import math
from typing import Optional
from shapely.geometry import LineString, Point, Polygon, mapping, shape
from shapely.ops import unary_union

SITE = "/Users/mac/Desktop/Земля Серпухов /site"

# Parcel corners for bilinear map (SVG top=north, left=west)
NW = (37.39750607534424, 55.03073380116581)
NE = (37.4047769220826, 55.03203331314409)
SE = (37.40755558603009, 55.029485178499556)
SW = (37.39900900799723, 55.028313620040365)
W, H = 612.0, 332.0


def bilinear(u: float, v: float) -> tuple[float, float]:
    lon = NW[0] * (1 - u) * (1 - v) + NE[0] * u * (1 - v) + SW[0] * (1 - u) * v + SE[0] * u * v
    lat = NW[1] * (1 - u) * (1 - v) + NE[1] * u * (1 - v) + SW[1] * (1 - u) * v + SE[1] * u * v
    return lon, lat


def svg_uv(sx: float, sy: float) -> tuple[float, float]:
    return (sx - 54) / W, (sy - 46) / H


def area_ha(poly: Polygon) -> float:
    c = poly.centroid
    m_lon = 111320 * math.cos(math.radians(c.y))
    pm = Polygon([((x - c.x) * m_lon, (y - c.y) * 111320) for x, y in poly.exterior.coords])
    return pm.area / 10000


def to_metric(poly: Polygon) -> Polygon:
    c = poly.centroid
    m_lon = 111320 * math.cos(math.radians(c.y))
    return Polygon([((x - c.x) * m_lon, (y - c.y) * 111320) for x, y in poly.exterior.coords])


def from_metric(pm: Polygon, ref: Polygon) -> Polygon:
    c = ref.centroid
    m_lon = 111320 * math.cos(math.radians(c.y))
    return Polygon([(c.x + x / m_lon, c.y + y / 111320) for x, y in pm.exterior.coords])


def buffer_line_uv(points_uv: list, width_m: float, parcel: Polygon) -> Optional[Polygon]:
    ring = [bilinear(u, v) for u, v in points_uv]
    line = LineString(ring)
    ref = parcel
    c = ref.centroid
    m_lon = 111320 * math.cos(math.radians(c.y))

    def to_m(lon, lat):
        return ((lon - c.x) * m_lon, (lat - c.y) * 111320)

    def to_ll(x, y):
        return (c.x + x / m_lon, c.y + y / 111320)

    lm = LineString([to_m(*p) for p in ring])
    buf = lm.buffer(width_m / 2, cap_style=2, join_style=2)
    clipped = buf.intersection(to_metric(parcel))
    if clipped.is_empty:
        return None
    if clipped.geom_type == "MultiPolygon":
        clipped = max(clipped.geoms, key=lambda g: g.area)
    elif clipped.geom_type != "Polygon":
        polys = [g for g in clipped.geoms if g.geom_type == "Polygon"]
        if not polys:
            return None
        clipped = max(polys, key=lambda g: g.area)
    return Polygon([to_ll(x, y) for x, y in clipped.exterior.coords])


def rect_zone(sx, sy, sw, sh, props, parcel):
    u0, v0 = svg_uv(sx, sy)
    u1, v1 = svg_uv(sx + sw, sy + sh)
    ring = [
        bilinear(u0, v0),
        bilinear(u1, v0),
        bilinear(u1, v1),
        bilinear(u0, v1),
        bilinear(u0, v0),
    ]
    poly = Polygon(ring)
    clipped = poly.intersection(parcel)
    if clipped.is_empty:
        return None
    if clipped.geom_type == "MultiPolygon":
        clipped = max(clipped.geoms, key=lambda g: g.area)
    elif clipped.geom_type != "Polygon":
        polys = [g for g in clipped.geoms if g.geom_type == "Polygon"]
        if not polys:
            return None
        clipped = max(polys, key=lambda g: g.area)
    ha = round(area_ha(clipped), 2)
    props = {**props, "ha_calc": ha, "ha": ha}
    return {
        "type": "Feature",
        "properties": props,
        "geometry": {"type": "Polygon", "coordinates": [list(clipped.exterior.coords)]},
    }


def feature_polygon(poly: Polygon, props: dict) -> dict:
    ha = round(area_ha(poly), 2)
    props = {**props, "ha_calc": ha, "ha": ha}
    return {
        "type": "Feature",
        "properties": props,
        "geometry": {"type": "Polygon", "coordinates": [list(poly.exterior.coords)]},
    }


def feature_line(coords, props):
    return {
        "type": "Feature",
        "properties": props,
        "geometry": {"type": "LineString", "coordinates": coords},
    }


def main():
    with open(f"{SITE}/cadastre.geojson") as f:
        cad = json.load(f)
    feat4 = next(ft for ft in cad["features"] if ft["properties"]["plot"] == "4")
    parcel = Polygon(feat4["geometry"]["coordinates"][0], feat4["geometry"]["coordinates"][1:])

    # Building zones (no roads strip — roads are separate layer)
    zones_def = [
        (54, 46, 396, 104, {"zone": "wh1", "name": "Склад B+, фаза 1", "color": "#34d399"}),
        (456, 46, 100, 104, {"zone": "wh3", "name": "Склад B+, фаза 3", "color": "#34d399"}),
        (562, 46, 104, 104, {"zone": "edge", "name": "Edge-ЦОД 1 МВт", "color": "#4d9fff"}),
        (54, 158, 248, 96, {"zone": "wh2", "name": "Склад B+, фаза 2", "color": "#34d399"}),
        (308, 158, 358, 96, {"zone": "park", "name": "Инд. парк", "color": "#a78bfa"}),
        (54, 262, 98, 72, {"zone": "log", "name": "Лог. двор", "color": "#fbbf24"}),
        (158, 262, 68, 72, {"zone": "buf", "name": "Буфер", "color": "#22c55e"}),
        (232, 262, 88, 72, {"zone": "mine", "name": "Майнинг", "color": "#f87171"}),
        (326, 262, 68, 72, {"zone": "prod", "name": "Производство 1440 м²", "color": "#fbbf24"}),
        (400, 262, 108, 72, {"zone": "admin", "name": "Админ · КПП", "color": "#64748b"}),
        (514, 262, 152, 72, {"zone": "eng", "name": "КТП · газ · ВРК", "color": "#64748b"}),
    ]
    zone_features = [f for z in zones_def if (f := rect_zone(*z, parcel))]

    # --- Internal road network (UV layout) ---
    road_specs = [
        # South belt: parking + turnaround
        ([(0.02, 0.86), (0.98, 0.86), (0.98, 0.99), (0.02, 0.99), (0.02, 0.86)], 14, "roads_belt", "Южная площадка · парковка"),
        # Main spine from KPP north
        ([(0.54, 0.84), (0.54, 0.12)], 12, "roads_spine", "Главный проезд"),
        # East-west distributor (between warehouse rows)
        ([(0.06, 0.50), (0.94, 0.50)], 10, "roads_ew", "Поперечный проезд"),
        # West spur to logistics yard
        ([(0.10, 0.84), (0.10, 0.58)], 9, "roads_w", "Проезд к лог. двору"),
        # East spur to KTP / Edge
        ([(0.90, 0.84), (0.90, 0.58)], 9, "roads_e", "Проезд к КТП"),
        # Short north stubs to warehouses
        ([(0.30, 0.50), (0.30, 0.18)], 8, "roads_n1", "Проезд к складу ф.1"),
        ([(0.70, 0.50), (0.70, 0.18)], 8, "roads_n2", "Проезд к инд. парку"),
    ]

    road_polys = []
    road_features = []
    for pts, width, zid, name in road_specs:
        poly = buffer_line_uv(pts, width, parcel)
        if poly and not poly.is_empty:
            road_polys.append(poly)
            road_features.append(
                feature_polygon(poly, {"zone": zid, "name": name, "color": "#8fa3be", "kind": "internal"})
            )

    internal_union = unary_union(road_polys) if road_polys else None
    if internal_union and not internal_union.is_empty:
        total_ha = round(area_ha(internal_union), 2)
        road_features.append(
            {
                "type": "Feature",
                "properties": {
                    "zone": "roads",
                    "name": "Внутренние дороги · парковка",
                    "color": "#8fa3be",
                    "kind": "internal_total",
                    "ha_calc": total_ha,
                    "ha": total_ha,
                },
                "geometry": mapping(internal_union),
            }
        )

    # --- External access (OSM: 46Н-11289 tertiary ~120 m, field track NW) ---
    gate = bilinear(0.54, 0.90)  # KPP / main gate
    # Real geometry from OSM way/25564120 (46Н-11289)
    public_road = [
        (37.393511, 55.027075),
        (37.394902, 55.027223),
        (37.399304, 55.027542),
        (37.400652, 55.027813),
        (37.402684, 55.027977),
        (37.404600, 55.028452),
        (37.406572, 55.028895),
        (37.407489, 55.029029),
        (37.408195, 55.029115),
        (37.409812, 55.029276),
        (37.412818, 55.029611),
    ]
    pr_line = LineString(public_road)
    c = parcel.centroid
    m_lon = 111320 * math.cos(math.radians(c.y))

    def to_m(lon, lat):
        return ((lon - c.x) * m_lon, (lat - c.y) * 111320)

    def to_ll(x, y):
        return (c.x + x / m_lon, c.y + y / 111320)

    pr_m = LineString([to_m(*p) for p in public_road])
    gate_m = Point(to_m(*gate))
    join_m = pr_m.interpolate(pr_m.project(gate_m))
    join = to_ll(join_m.x, join_m.y)

    access_coords = [join, gate]
    road_features.append(
        feature_line(
            access_coords,
            {
                "zone": "access",
                "name": "Подъезд от 46Н-11289",
                "color": "#fbbf24",
                "kind": "access",
            },
        )
    )
    road_features.append(
        feature_line(
            public_road,
            {
                "zone": "public",
                "name": "46Н-11289 (региональная дорога)",
                "color": "#e2e8f0",
                "kind": "public",
            },
        )
    )

    # Subtract roads from building zones for cleaner map (optional clip)
    if internal_union and not internal_union.is_empty:
        for zf in zone_features:
            g = shape(zf["geometry"])
            cut = g.difference(internal_union)
            if cut.is_empty:
                continue
            if cut.geom_type == "MultiPolygon":
                cut = max(cut.geoms, key=lambda x: x.area)
            if cut.geom_type == "Polygon":
                ha = round(area_ha(cut), 2)
                zf["geometry"] = mapping(cut)
                zf["properties"]["ha_calc"] = ha
                zf["properties"]["ha"] = ha

    with open(f"{SITE}/cadastre-zones.geojson", "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": zone_features}, f, ensure_ascii=False, indent=2)

    with open(f"{SITE}/cadastre-roads.geojson", "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": road_features}, f, ensure_ascii=False, indent=2)

    print(f"zones: {len(zone_features)}")
    print(f"roads: {len(road_features)} features")
    if internal_union:
        print(f"internal roads: {area_ha(internal_union):.2f} ha")


if __name__ == "__main__":
    main()
