# PostGIS and the Boundary Between Built-In Geometric Types and Spatial Data

## 1. Why Does PostgreSQL Have Built-In Geometric Types Yet Still Need PostGIS?

PostgreSQL includes built-in geometric types such as `point`, `line`, `lseg`, `box`, `path`, `polygon`, and `circle`. They represent shapes on a two-dimensional coordinate plane and come with basic operators. For applications storing relative positions, regions on a diagram, or simple shapes in an internal coordinate system, these types can be sufficient.

Real-world geographic data usually requires much more than storing an X/Y number pair. Applications must know which reference system the coordinates belong to, whether units are degrees or meters, how distances on Earth are calculated, whether two regions intersect, whether a point lies inside a polygon, how to query millions of objects efficiently, and how to transform between coordinate systems.

**PostGIS** is a spatial extension that adds specialized data types, functions, operators, spatial reference systems, and indexing mechanisms to PostgreSQL. It extends PostgreSQL into a spatial database while continuing to use familiar mechanisms such as transactions, constraints, WAL, backups, SQL, roles, and replication.

The core distinction:

- PostgreSQL built-in geometric types represent shapes on a plane without built-in geographic reference systems or measurement units.
- PostGIS `geometry` represents spatial objects that can carry an SRID and use rich geometric operations.
- PostGIS `geography` supports geodetic calculations on the Earth's surface for supported object types and functions.

```text
PostgreSQL built-in geometric types
   |
   +-- point / line / lseg / box
   +-- path / polygon / circle
   |
   +-- Planar coordinates
   +-- No built-in SRID metadata
   +-- Basic geometric operators
   |
   v
Good for simple local geometry

PostGIS extension
   |
   +-- geometry + SRID
   +-- geography + geodetic calculations
   +-- spatial functions and predicates
   +-- spatial indexes and reference systems
   |
   v
Good for GIS and earth-referenced spatial data
```

This lesson helps define the appropriate boundary between the two groups, avoid treating degree coordinates as meters, avoid assigning the wrong SRID, and choose the right data type and index for each problem.

### Learning Objectives

After this lesson, you will be able to:

1. List and explain PostgreSQL's built-in geometric types.
2. Understand the limitations of a coordinate plane without an SRID.
3. Distinguish built-in geometry, PostGIS `geometry`, and PostGIS `geography`.
4. Explain SRID, CRS, EPSG, and coordinate units.
5. Distinguish `ST_SetSRID` and `ST_Transform`.
6. Choose `geometry` or `geography` based on the problem.
7. Create geometry columns with type/SRID constraints.
8. Use common spatial predicates and measurement functions.
9. Create and use GiST spatial indexes.
10. Understand bounding-box filtering and exact spatial predicates.
11. Check geometry validity, dimensionality, and coordinate order.
12. Install, verify, and upgrade the PostGIS extension.
13. Design schemas, migrations, and backups for spatial data.
14. Safely migrate from built-in `point` to PostGIS `geometry`.
15. Choose the right tool for internal diagrams, GIS, geofencing, proximity, and spatial joins.

---

## 2. PostgreSQL Built-In Geometric Types

PostgreSQL provides geometric types on a coordinate plane:

| Type | Description | Example use |
|---|---|---|
| `point` | A point (x, y) | Node on a diagram |
| `line` | Infinite straight line | Mathematical line relationship |
| `lseg` | Line segment with two endpoints | Edge of a diagram |
| `box` | Rectangle defined by two opposite corners | Rectangular region |
| `path` | Ordered sequence of points, open or closed | Path on a diagram |
| `polygon` | Closed polygon | Region on a plane |
| `circle` | Circle with center and radius | Internal radius region |

### 2.1. point

`point` stores two floating-point coordinates:

```sql
SELECT point '(1, 2)' AS position;
```

This point only means X = 1, Y = 2 in an application-defined coordinate system. PostgreSQL does not know whether it represents longitude/latitude, meters, pixels, or arbitrary units.

### 2.2. line

`line` represents an infinite line, typically defined by the equation:

\[
A x + B y + C = 0
\]

It is not a road segment with start/end points and does not inherently represent a geographic route.

### 2.3. lseg

`lseg` is a finite line segment with two endpoints:

```sql
SELECT lseg '[(0, 0), (4, 3)]' AS segment;
```

Use it when you need to represent an edge or span connecting two points on a plane.

### 2.4. box

`box` is an axis-aligned rectangle defined by two opposite corners:

```sql
SELECT box '((0, 0), (10, 5))' AS area;
```

It is not an arbitrary polygon; the rectangle's sides are always parallel to the X/Y axes.

### 2.5. path

`path` represents an ordered sequence of points. Square brackets denote an open path, whereas parentheses denote a closed path:

```sql
SELECT
    path '[(0, 0), (2, 3), (5, 1)]' AS open_path,
    path '((0, 0), (2, 3), (5, 1))' AS closed_path;
```

A path is a sequence of points on a plane; it has no concept of real-world roads, one-way streets, or network routing.

### 2.6. polygon

`polygon` represents a closed polygonal region:

```sql
SELECT polygon '((0, 0), (5, 0), (4, 4), (0, 3))' AS region;
```

PostgreSQL can perform several operations on `polygon`, but it does not provide a full GIS model like PostGIS's SRIDs, geometry validity rules, and spatial transformations.

### 2.7. circle

`circle` represents a circle by center and radius:

```sql
SELECT circle '<(2, 3), 5>' AS coverage;
```

It is useful for simple planar geometry. The radius is in the plane's coordinate units, not automatically meters on Earth.

## 3. Built-In Types Use a Planar Coordinate System

Built-in geometric types carry no metadata about:
- Coordinate Reference System (CRS).
- SRID/EPSG identifier.
- Units of measurement.
- Datum/ellipsoid.
- Longitude/latitude axes.
- Transformations between CRSs.

For example, two points `point '(106.7, 10.8)'` and `point '(106.8, 10.8)'` are simply two positions 0.1 X-units apart. PostgreSQL cannot infer whether that separation is degrees of longitude or an arbitrary unit.

### 3.1. All Measurements Depend on Application Units

If X/Y are meters in an internal diagram, planar measurements carry meaning in meters. If X/Y are longitude/latitude in degrees, Euclidean distance is not ground distance in meters.

### 3.2. No Built-In Awareness of Earth Curvature

A straight line between two longitude/latitude pairs is not automatically a geodesic. Computing distance with the Pythagorean theorem on degrees can introduce substantial error.

### 3.3. No SRID to Prevent Mixing Coordinates

An application can accidentally compare points from two different reference systems. The database has no metadata to detect that incompatibility.

### 3.4. When Are Built-In Types Still Appropriate?

Use them for internal diagrams, game boards, layouts, relative geometry, small application-defined coordinate spaces, or simple planar operations that do not require a GIS ecosystem.

## 4. Built-In Geometric Operators

PostgreSQL provides geometric operators such as:
- Checking whether two shapes are equal.
- Checking overlap.
- Checking whether one shape contains or is contained within another.
- Checking relative position left/right/above/below.
- Computing certain intersections, unions, or distances depending on shape type.

Example checking whether a point lies inside a box:

```sql
SELECT point '(3, 2)' <@ box '((0, 0), (10, 5))'
    AS inside_box;
```

### 4.1. Operators Depend on Shape Type

Not every operator applies to every pair of geometric types. Consult the operator tables in the PostgreSQL documentation before use.

### 4.2. Overlap Is Not General Intersects

For built-in types, operator semantics are defined for specific shape types. Do not interpret an operator as equivalent to a PostGIS OGC predicate solely because its name looks similar without reading the semantics.

### 4.3. Index Support for Some Operators

Built-in geometric types can use GiST indexes for certain spatial queries. This helps find candidates by geometric characteristics, but it does not add CRS awareness or geodesic calculations.

### 4.4. Built-In Operators Are Not a Full GIS API

They do not provide the full set of functions such as `ST_Transform`, `ST_Buffer`, `ST_Intersects`, `ST_Within`, `ST_DWithin`, or PostGIS's geometry validity model.

## 5. What Is PostGIS?

PostGIS is an extension that adds spatial data storage, indexing, and querying capabilities to PostgreSQL.

Core components can include:
- `geometry`: geometric data in planar coordinates, optionally tagged with an SRID.
- `geography`: geodetic data on the Earth's surface for supported types and functions.
- `raster`: raster data via the PostGIS Raster component when installed.
- Spatial predicates and measurement functions.
- Spatial reference metadata.
- GiST/SP-GiST and appropriate operator classes.
- 2D/3D features, linear referencing, clustering, and many GIS utilities.

### 5.1. PostGIS Is an Extension, Not a Separate Database Server

PostGIS runs inside PostgreSQL. The database still uses SQL, transactions, WAL, backups, roles, replication, and PostgreSQL administration.

### 5.2. Installed at the Database Level

The extension requires compatible packages/libraries on the host/container and is enabled per database using `CREATE EXTENSION`.

### 5.3. PostGIS Has an OGC Ecosystem

PostGIS supports widely used spatial standards and formats such as WKT, EWKT, WKB, EWKB, GeoJSON, and geometry types following the OGC Simple Features model within supported scope.

### 5.4. PostGIS Does Not Automatically Fix Bad Data

The extension provides tools for validation and conversion. Applications remain responsible for ensuring CRS accuracy, coordinate order, validity, and data semantics.

## 6. Installing and Enabling PostGIS

First, install the PostGIS package compatible with your PostgreSQL major version and operating system. On managed services, verify that the extension is supported by the provider.

Once the package is present, connect to the target database and run:

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
```

Verify:

```sql
SELECT PostGIS_Full_Version();
```

### 6.1. Extensions Are Enabled Per Database

Running `CREATE EXTENSION` in database A does not automatically enable PostGIS in database B. Each database maintains its own extension state.

### 6.2. Package and SQL Extension Are Two Layers

Installing the OS package provides shared libraries, control files, and update files. `CREATE EXTENSION` creates the SQL objects inside the database.

### 6.3. Check Extension Inventory

```sql
SELECT
    extname,
    extversion,
    extnamespace::regnamespace AS extension_schema
FROM pg_extension
WHERE extname LIKE 'postgis%';
```

### 6.4. Privileges to Install Extensions

Creating an extension requires appropriate privileges and an installed package. In managed environments, users may require provider-specific roles or permissions.

## 7. PostGIS geometry

`geometry` is the primary spatial type for planar coordinate data. `geometry` can represent:
- Point.
- LineString.
- Polygon.
- MultiPoint.
- MultiLineString.
- MultiPolygon.
- GeometryCollection.
- Certain curve/surface types and extended dimensions as supported by PostGIS.

Example:

```sql
SELECT
    ST_GeomFromText('POINT(10 20)') AS p,
    ST_GeomFromText('LINESTRING(0 0, 2 3, 5 1)') AS route,
    ST_GeomFromText(
        'POLYGON((0 0, 5 0, 5 4, 0 4, 0 0))'
    ) AS region;
```

### 7.1. Geometry Is Planar

`geometry` measurements use planar coordinates and the units of the CRS. With SRID 4326, coordinates are in degrees; `ST_Distance` on SRID 4326 `geometry` returns distance in degrees, not meters.

### 7.2. Geometry Has an SRID

A `geometry` can carry a Spatial Reference Identifier to identify its CRS. The SRID tells both the database and users which reference system the coordinates belong to.

### 7.3. Geometry Supports Dimensionality

It can store XY, XYZ, XYM, or XYZM depending on the type and function. Z and M are additional ordinates; not all functions use them in calculations.

### 7.4. Geometry Usually Fits a Projected CRS

When data belongs to a specific region and you need distances or areas in planar units, choose an appropriate projected CRS for that area.

## 8. PostGIS geography

`geography` represents objects on the Earth's surface under a geodetic model. It suits longitude/latitude data when you want Earth-surface measurements without manually picking a projected CRS.

Example:

```sql
SELECT
    ST_Distance(
        'POINT(106.7009 10.7769)'::geography,
        'POINT(106.7100 10.7769)'::geography
    ) AS distance_meters;
```

### 8.1. Distance Usually Returns Meters

`geography` measurements such as `ST_Distance` return results in meters; by default they use the spheroid in corresponding supported functions.

### 8.2. Geography Has Narrower Type/Function Coverage Than Geometry

Not every `geometry` type or spatial function has a `geography` overload. Check function signatures and documentation.

### 8.3. Geography Can Be More CPU-Intensive

Geodetic calculations are more complex than planar calculations. For large workloads within a small region, `geometry` in a suitable projected CRS can be faster and more flexible.

### 8.4. Geography Does Not Replace CRS Knowledge

`geography` still requires the proper SRID and correct coordinate order. Assigning the wrong SRID or swapping longitude/latitude will produce wrong results.

## 9. How Do geometry and geography Differ?

| Criterion | geometry | geography |
|---|---|---|
| Model | Coordinate plane | Earth's surface |
| SRID | Yes | Yes |
| Distance units | CRS units | Typically meters |
| Area | Squared CRS units | Square meters for corresponding functions |
| Performance | Usually faster | Usually more computationally expensive |
| Projected CRS | Very suitable | Not the primary target |
| Geographic CRS | Can be stored, but measured in degrees | Well suited for geodetic operations |
| Function coverage | Broader | Narrower |
| Use case | Planar/projected GIS, local/regional analysis | Global or lat/lon geodetic distance/area |

### 9.1. Do Not Choose geography Just Because You Have Latitude/Longitude

If the workload is primarily within one city/region and requires many overlay/buffer/union operations, projected `geometry` may be more appropriate.

### 9.2. Do Not Use geometry 4326 to Compute Meters

`ST_Distance` between two SRID 4326 `geometry` values returns degrees. Transform to a suitable projected CRS or cast to `geography` when appropriate for the problem.

### 9.3. Geography Does Not Support Every Geometry Operation

If you need a function without a `geography` overload, you can transform/cast in an appropriate workflow, provided you understand the change in semantics and units.

### 9.4. Choose Based on Workload and Accuracy

Consider region, distances, areas, analysis type, performance, and tolerance. Document the decision in the schema and documentation.

## 10. CRS, SRID, and EPSG

A CRS (Coordinate Reference System) describes how coordinates map to real-world locations, including datum, projection, axes, and units.

An SRID is the reference system identifier in PostGIS. Many SRIDs correspond to EPSG codes, though not every SRID is an EPSG code.

### 10.1. EPSG:4326

EPSG:4326 is the common geographic CRS based on WGS 84. In PostGIS X/Y convention, X is longitude and Y is latitude.

### 10.2. EPSG:3857

EPSG:3857 is Web Mercator, commonly used for web map tiles. Its coordinate units are meters, but distortion increases sharply at high latitudes; do not use it for accurate global area/distance measurements.

### 10.3. Regional Projected CRSs

A projected CRS suited to the study region can provide meter units and lower distortion for local distances and areas. Choose the correct zone/datum for the data.

### 10.4. SRID 0

A `geometry` without a defined reference system usually has SRID 0. You cannot infer units or transform accurately without knowing the source CRS.

## 11. ST_SetSRID and ST_Transform

These two functions are frequently confused.

**ST_SetSRID** changes the SRID metadata without altering coordinate values.

**ST_Transform** converts coordinates from a source CRS to a target CRS based on coordinate reference system definitions and PROJ support.

```sql
-- Coordinates are already WGS 84 longitude/latitude.
SELECT ST_SetSRID(
    ST_MakePoint(106.7009, 10.7769),
    4326
);

-- Transform coordinates from SRID 4326 to SRID 3857.
SELECT ST_Transform(
    ST_SetSRID(
        ST_MakePoint(106.7009, 10.7769),
        4326
    ),
    3857
);
```

### 11.1. ST_SetSRID Is Not a Coordinate Conversion

If coordinates are in UTM and you assign SRID 4326, the numeric values do not magically become longitude/latitude. Incorrect metadata corrupts all subsequent calculations.

### 11.2. ST_Transform Requires Knowing the Source CRS

If a `geometry` has SRID 0 or the wrong SRID, `ST_Transform` cannot guess what the coordinates mean. Verify the source before transforming.

### 11.3. Transforming a CRS Is More Than Changing Units

A transform can alter X/Y values, projections, and datum transformations. Some transformations require appropriate grid files or PROJ resources.

### 11.4. Verify Results

Use `ST_SRID`, `ST_AsText`, and bounding-box coordinates to confirm that the transformed geometry lies in the expected region.

## 12. Coordinate Order: Longitude and Latitude

In PostGIS, `geometry` follows the X/Y convention:
- X is typically longitude for geographic CRSs.
- Y is typically latitude.

For example, a point with longitude 106.7 and latitude 10.8:

```sql
SELECT ST_SetSRID(
    ST_MakePoint(106.7, 10.8),
    4326
);
```

### 12.1. Do Not Swap Latitude and Longitude

`ST_MakePoint(latitude, longitude)` can place coordinates in the wrong region. Always verify the API/GeoJSON/client contract.

### 12.2. Axis Order in External Standards

Some CRS definitions and standards specify an axis order different from the X/Y convention commonly used in PostGIS. When integrating external tools, verify the axis order required by the specific protocol.

### 12.3. Range Checks

For longitude/latitude, verify that longitude and latitude lie within valid ranges for the CRS. Range checks do not prove a point lies in the intended country or region.

### 12.4. GeoJSON

RFC 7946 GeoJSON uses WGS 84 longitude/latitude coordinate order. When exporting/importing, verify CRS and axis order per the standard.

## 13. WKT, EWKT, WKB, and GeoJSON

PostGIS supports common representations:

| Format | Characteristics | When to use |
|---|---|---|
| WKT | Text describing geometry | Debugging, interchange |
| EWKT | Extended WKT with SRID | Debugging/interchange with PostGIS |
| WKB | Binary geometry | Efficient binary transport |
| EWKB | Binary extended with PostGIS metadata | Preserving SRID/dimensions per format |
| GeoJSON | JSON geometry | Web APIs and map clients |

### 13.1. ST_AsText

```sql
SELECT ST_AsText(geom)
FROM places;
```

Standard WKT does not carry an SRID. Do not treat WKT alone as proof of CRS.

### 13.2. ST_AsEWKT

```sql
SELECT ST_AsEWKT(geom)
FROM places;
```

EWKT can display the SRID in PostGIS's text representation.

### 13.3. ST_AsBinary

WKB is well suited for exchanging binary geometry, though standard WKB does not necessarily contain an SRID. Use EWKB when PostGIS metadata is needed per contract.

### 13.4. ST_AsGeoJSON

```sql
SELECT ST_AsGeoJSON(geom)
FROM places;
```

When exporting GeoJSON, convert geometry to the CRS/axis order specified by RFC 7946—typically WGS 84 longitude/latitude.

## 14. Creating Geometry Tables with Fixed Type and SRID

A schema for location points:

```sql
CREATE TABLE public.places (
    place_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL,
    location geometry(Point, 4326) NOT NULL
);
```

The `geometry(Point, 4326)` type constrains the geometry subtype to `Point` and the SRID to `4326`.

### 14.1. Typmod

PostGIS typmod can enforce subtype, SRID, and dimensionality—for example `Point`, `PointZ`, or `Polygon` as needed.

### 14.2. Generic Geometry

`geometry(Geometry, 4326)` permits multiple subtypes while still requiring SRID 4326. Use it when a column intentionally holds multiple shape types.

### 14.3. Geography Typmod

```sql
CREATE TABLE public.delivery_zones (
    zone_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL,
    boundary geography(MultiPolygon, 4326) NOT NULL
);
```

Choose `MultiPolygon` if the domain may include multiple component polygons.

### 14.4. Constraints and Application Contract

Typmod protects type/SRID at the column level, but it does not verify that coordinates make business sense for a location. Input validation is still necessary.

## 15. Inserting and Constructing Geometry

Use `ST_MakePoint` and assign an SRID:

```sql
INSERT INTO public.places (name, location)
VALUES (
    'Office',
    ST_SetSRID(
        ST_MakePoint(106.7009, 10.7769),
        4326
    )
);
```

Or parse WKT:

```sql
INSERT INTO public.places (name, location)
VALUES (
    'Warehouse',
    ST_GeomFromText('POINT(106.7100 10.7800)', 4326)
);
```

### 15.1. ST_MakePoint

Constructs a point from X/Y (with overloads for higher dimensions). The function is unaware of CRS, so assign the proper SRID.

### 15.2. ST_GeomFromText

Parses WKT and accepts an SRID depending on the overload. Verify input format and SRID.

### 15.3. Geometry Collections

`ST_GeomFromText` can construct various geometry types. Column typmod will reject incompatible types.

### 15.4. Input Validation

Validate coordinate range, SRID, emptiness, geometry type, and business region before committing.

## 16. Important Spatial Predicates

PostGIS provides predicates such as:
- `ST_Intersects`: two geometries share any portion of space.
- `ST_Contains`: A contains B per topology semantics.
- `ST_Within`: A is within B.
- `ST_Covers`: A covers B, with boundary semantics differing from Contains.
- `ST_Touches`: touches at boundaries without interior overlap.
- `ST_Crosses`: crosses per geometry-type definitions.
- `ST_Disjoint`: no shared points.
- `ST_Equals`: spatially equal per topology semantics.

### 16.1. ST_Intersects

Returns `true` if two geometries have at least one point in common. Useful for spatial joins and impact zones.

### 16.2. ST_Contains and ST_Within

These two functions have reversed argument order. Points lying exactly on the boundary have different semantics from interior points; understand them before implementing geofencing.

### 16.3. ST_Covers

Often appropriate when the boundary itself is considered part of the region. Choose according to business rules—for example, whether a point on the border counts as inside.

### 16.4. ST_Touches and ST_Crosses

Use when distinguishing boundary contact from interior crossing. Test edge and corner cases.

### 16.5. ST_Equals Is Not Byte Equality

Two geometries can represent the same space with different vertex ordering or representation. Choose the predicate matching what you need to test.

## 17. Spatial Measurement Functions

Common measurement functions:

| Function | Meaning |
|---|---|
| `ST_Distance` | Distance between two geometries/geographies |
| `ST_DWithin` | Checks whether within a distance threshold |
| `ST_Length` | Length of a linear geometry |
| `ST_Perimeter` | Perimeter of a polygon |
| `ST_Area` | Area of a polygon/surface |
| `ST_Centroid` | Geometric centroid |
| `ST_PointOnSurface` | Point guaranteed to lie on the geometry surface |
| `ST_ClosestPoint` | Closest point on a geometry |
| `ST_Azimuth` | Azimuth angle between two points |

### 17.1. Units Depend on Type and SRID

For `geometry`, distance/length/area use CRS units. For `geography`, corresponding geodetic functions usually return meters/square meters.

### 17.2. ST_Distance

Use to retrieve distance under the type/CRS semantics. If you only need to filter within a radius, `ST_DWithin` is usually better because it can leverage a spatial index.

### 17.3. ST_Length

For `geometry` in a meter-based projected CRS, the result can be in meters. For SRID 4326 `geometry`, the result is in coordinate degrees, not meters.

### 17.4. ST_Area

The area of an SRID 4326 `geometry` is not in square meters. Use a suitable projected CRS or `geography` for geodetic area.

### 17.5. Centroids Do Not Always Lie Inside Polygons

For concave or complex polygons, the centroid may fall outside. If you need a point guaranteed to lie on the surface, look at `ST_PointOnSurface`.

## 18. Buffers and Geometric Transformations

`ST_Buffer` creates a region within a specified distance of an input geometry in the corresponding units.

```sql
SELECT ST_Buffer(
    ST_Transform(location, 32648),
    500
)
FROM public.places;
```

This example assumes SRID 32648 suits the region and input data has SRID 4326; choose the actual CRS for your region.

### 18.1. Buffer on geometry

The buffer distance uses CRS units. A buffer of `500` on SRID 4326 `geometry` means 500 degrees, not 500 meters.

### 18.2. Buffer on geography

PostGIS provides a `geography` overload for buffering by geodetic distance, though the implementation may internally transform to a suitable planar CRS. For wide regions or complex shapes, inspect results and limits.

### 18.3. ST_Intersection

Computes the intersection of two geometries. Input validity and CRS compatibility must be checked.

### 18.4. ST_Union

Merges geometries. Unioning many large polygons can be CPU- and memory-intensive; use a batch/aggregate strategy and benchmark the workload.

### 18.5. ST_Difference

Extracts the portion of geometry A not contained in B. Useful for overlays, though output type and emptiness must be checked.

## 19. Checking Geometry Validity

A geometry may parse cleanly yet still be topologically invalid—for example, a self-intersecting polygon or malformed ring.

```sql
SELECT
    id,
    ST_IsValid(geom) AS is_valid,
    ST_IsValidReason(geom) AS reason
FROM spatial_features;
```

### 19.1. ST_IsValid

Checks validity according to the rules applicable to the geometry. Different geometry types have different rules.

### 19.2. ST_IsValidReason

Returns the reason a geometry is invalid, useful for data cleaning.

### 19.3. ST_MakeValid

Can repair an invalid geometry, though the output type/structure may change—for example into a `MultiPolygon` or `GeometryCollection`. Do not assume output always keeps the input type.

### 19.4. ST_IsEmpty

An empty geometry is different from `NULL`. An empty geometry is a geometry value containing no points; handle it explicitly in business logic.

### 19.5. Validity Does Not Prove Business Correctness

A valid polygon can still be in the wrong country, have the wrong SRID, or have swapped coordinates.

## 20. Spatial Indexes

Spatial queries over millions of geometries require indexing. PostGIS commonly uses a GiST index:

```sql
CREATE INDEX places_location_gix
ON public.places
USING GIST (location);
```

The index accelerates candidate filtering using bounding boxes, after which the exact predicate checks the geometric relationship.

### 20.1. GiST

Generalized Search Tree is PostgreSQL's extensible indexing framework. PostGIS provides operator classes for spatial types.

### 20.2. Bounding Box

The index typically uses bounding-box approximations to locate candidates. Candidates must then be verified exactly by the spatial predicate.

### 20.3. Indexes Do Not Store Every Topological Answer

Overlapping bounding boxes do not mean two polygons truly intersect. Exact predicates remain necessary.

### 20.4. Selectivity

If a query returns most of the table, the planner may choose a sequential scan because an index is no faster. Having an index does not guarantee every query uses it.

### 20.5. SP-GiST and BRIN

PostGIS may offer additional operator classes/index strategies depending on version and data characteristics. Choose after benchmarking; GiST is the common starting point.

## 21. Bounding-Box Filters vs. Exact Predicates

The `&&` operator checks whether bounding boxes overlap. It is not an exact intersection test of the full shapes.

Example:

```sql
SELECT id
FROM spatial_features
WHERE geom && ST_MakeEnvelope(
    106.60, 10.70,
    106.80, 10.90,
    4326
);
```

This is a bounding-box filter.

To obtain exact intersections:

```sql
SELECT id
FROM spatial_features
WHERE ST_Intersects(
    geom,
    ST_MakeEnvelope(
        106.60, 10.70,
        106.80, 10.90,
        4326
    )
);
```

### 21.1. Index-Aware Predicates

Many PostGIS predicates such as `ST_Intersects` and `ST_DWithin` automatically include a bounding-box condition so the planner can use an index.

### 21.2. && Is a Candidate Filter

If you use `&&` alone, results can contain false positives where bounding boxes overlap even though the actual shapes do not intersect.

### 21.3. EXPLAIN Confirms Index Usage

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id
FROM spatial_features
WHERE ST_Intersects(geom, :query_geom);
```

Look for an appropriate `Index Scan` or `Bitmap Index Scan` and compare against actual rows/loops.

### 21.4. Transform on the Right Side

If a column is indexed in SRID 4326, usually transform the query geometry to 4326 rather than wrapping the column in `ST_Transform` on every row. If the workload consistently queries in another CRS, consider a functional index.

## 22. KNN Spatial Search

PostGIS supports nearest-neighbor search with distance ordering operators such as `<->` on compatible indexes/operator classes.

Example finding points nearest to a query point:

```sql
SELECT
    place_id,
    name,
    location <-> ST_SetSRID(
        ST_MakePoint(106.7009, 10.7769),
        4326
    ) AS planar_distance
FROM public.places
ORDER BY location <-> ST_SetSRID(
    ST_MakePoint(106.7009, 10.7769),
    4326
)
LIMIT 10;
```

### 22.1. KNN Relies on Operator Semantics

Distance ordering for `geometry` is planar per the CRS. For `geography`, KNN semantics/accuracy may differ from spheroid distance depending on operator/version.

### 22.2. KNN Does Not Fix Units Automatically

SRID 4326 `geometry` orders by distance in the coordinate plane, not geodetic meters.

### 22.3. Exact Re-Ranking

One pattern uses KNN/index lookup to fetch a candidate set, then recomputes exact distance using `geography`/spheroid if required by the business logic.

### 22.4. EXPLAIN

Verify that the planner uses index ordering rather than sorting the entire table. Check candidate counts and exact results.

## 23. ST_DWithin for Radius Search

A common pattern for finding locations within a radius:

```sql
SELECT
    place_id,
    name
FROM public.places
WHERE ST_DWithin(
    location::geography,
    ST_SetSRID(
        ST_MakePoint(106.7009, 10.7769),
        4326
    )::geography,
    1000
);
```

Here the distance is 1,000 meters under `geography` semantics.

### 23.1. DWithin Fits Threshold Filtering

It is usually more efficient than computing `ST_Distance` for every row and filtering with `WHERE distance < threshold`.

### 23.2. Indexing on geography

If the workload frequently queries `geography`, consider a `geography` column or an appropriate index on the cast expression. The index must match the expression in the query.

### 23.3. Do Not Cast Arbitrarily Per Row

Casting `geometry` to `geography` in a query may require an expression index for good performance. Measure with `EXPLAIN` and consider storing `geography` directly if that matches the domain model.

### 23.4. Boundary Semantics

`DWithin` tests for distance less than or equal to the threshold per function semantics. Test threshold edge cases and tolerance.

## 24. Spatial Joins

A spatial join matches records based on geometric relationships rather than equality keys alone.

Example finding points inside zones:

```sql
SELECT
    p.place_id,
    p.name,
    z.zone_id,
    z.name AS zone_name
FROM public.places AS p
JOIN public.zones AS z
  ON ST_Within(p.location, z.boundary);
```

### 24.1. Choose Predicates per Business Rules

`ST_Within` is not always equivalent to `ST_CoveredBy` on boundaries. If a point lying right on the border must count as inside the zone, evaluate `ST_Covers`/`ST_CoveredBy`.

### 24.2. Index Both Sides

Indexes on both point and polygon columns can help the planner. Inspect the plan and table sizes.

### 24.3. Spatial Join Cardinality

A point may match multiple polygons if zones overlap. If business rules require a single zone, define a priority rule or data constraint.

### 24.4. Precompute When Needed

If point-to-zone relationships change rarely yet are queried heavily, materializing the mapping can reduce spatial join cost; keep it updated whenever geometries change.

## 25. Built-In point and PostGIS geometry(Point) Are Not the Same

Both types can represent a coordinate pair, but their metadata and function ecosystems differ.

| Criterion | PostgreSQL point | PostGIS geometry(Point) |
|---|---|---|
| Value | X/Y | Spatial point |
| SRID | No | Optional/supported |
| CRS | Application-managed | SRID metadata attached |
| Functions | Built-in geometric functions/operators | Rich spatial functions |
| Geometry model | Basic planar point | OGC-style geometry model |
| Spatial joins | Limited | Rich predicates |
| Coordinate transform | No built-in GIS transform | `ST_Transform` |
| Geography | No | Separate `geography` type |
| Spatial indexing | Built-in geometric index support | PostGIS operator classes |
| Interchange | Simple coordinates | WKT/WKB/GeoJSON and many formats |

### 25.1. Do Not Substitute Just Because Names Look Similar

A `point` column does not inherently carry `geometry(Point, 4326)` semantics. Data must be converted and its CRS verified.

### 25.2. Conversions Must Be Explicit

If `point` X/Y values have been verified as WGS 84 longitude/latitude:

```sql
SELECT ST_SetSRID(
    ST_MakePoint(
        (legacy_point)[0],
        (legacy_point)[1]
    ),
    4326
)
FROM legacy_locations;
```

Coordinate access syntax and casting must be verified against your PostgreSQL version/type context; the goal is to transfer X/Y via `ST_MakePoint` and then attach a verified SRID.

### 25.3. Do Not Guess SRID from Numeric Values

Coordinates `106.7, 10.8` look like longitude/latitude, but that does not prove the CRS. Check the data source and contract.

### 25.4. Preserve Source Data During Migration

In large migrations, add the new column, backfill, validate, switch the application, and drop the old column only in a later phase.

## 26. When to Use Built-In Geometric Types?

Built-in types are appropriate when:
- The application only needs simple planar geometry.
- Coordinates are in well-defined internal units.
- No SRID/CRS transformations are needed.
- No geographic Earth-surface distances are needed.
- You only need simple points, boxes, paths, or circles.
- Data does not require GIS interchange or rich spatial analytics.
- You want to avoid an extension dependency for a small problem.

### 26.1. UI Diagrams

A node at pixel `(x, y)` or a rectangle on a canvas can use `point`/`box` if the application manages units and bounds itself.

### 26.2. Game Boards

Piece positions on a grid can use `point` or integer coordinate pairs; PostGIS is unnecessary just because data is two-dimensional.

### 26.3. Internal Geometry

An application simulating a local plane can use built-in types if CRS/Earth semantics are unneeded.

### 26.4. Growth Constraints

If the roadmap includes geofencing, map layers, spatial joins, or importing GIS data, adopting PostGIS early can avoid a later migration.

## 27. When to Use PostGIS?

PostGIS is appropriate when:
- Storing addresses/locations with an explicit CRS.
- Searching for locations within a radius.
- Determining whether a point lies inside a polygon or administrative boundary.
- Computing area, length, or buffers.
- Performing spatial joins across multiple data layers.
- Importing/exporting GeoJSON, WKT, WKB, or GIS formats.
- Storing road segments, routes, parcels, or zones.
- Requiring reprojection/coordinate transformations.
- Needing spatial indexing at scale.
- Performing geographic and topological analysis.

### 27.1. Store Locator

Find stores near a user's location, filter by radius, and sort by distance.

### 27.2. Geofencing

Check whether a device's position lies inside a delivery or service boundary.

### 27.3. Land Parcels

Store land parcel polygons and check overlaps, adjacency, and area.

### 27.4. Logistics

Analyze service areas, distances, pickup/delivery points, and spatial relationships. Road-network routing may additionally require pgRouting or a routing service; PostGIS itself is not a routing engine.

## 28. Boundary Between a Spatial Database and Routing/Topology Systems

PostGIS provides spatial data types, predicates, measurements, and many GIS functions. However, certain problems require additional extensions or specialized systems.

### 28.1. Road Routing

Finding shortest paths on a road graph usually requires pgRouting or a dedicated routing engine. `ST_Distance` between two points is not actual travel time or route length.

### 28.2. Network Topology

Some topology-management problems can use the PostGIS Topology extension. Ordinary polygon/line geometries do not automatically enforce dataset-wide topology.

### 28.3. Raster Analysis

Raster workflows require the PostGIS Raster component and appropriate tooling. Do not confuse vector geometries with raster grids.

### 28.4. Geocoding

Converting text addresses to coordinates usually requires a geocoding dataset/service. PostGIS stores and queries the results, but it does not natively bundle every address in the world.

## 29. SRID Constraints and Schema Design

Design columns to match the domain:

```sql
CREATE TABLE public.delivery_points (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL,
    location geometry(Point, 4326) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
```

### 29.1. One Column Should Have One CRS Contract

Keeping the SRID consistent clarifies query, index, and application behavior. Avoid mixing 4326 and 3857 in the same column without a clear reason.

### 29.2. Type Constraints

Use `Point`, `MultiPolygon`, or a specific subtype instead of generic `geometry` when the schema expects one shape kind.

### 29.3. Dimensionality

Choose XY/XYZ/XYM/XYZM according to data meaning. Do not add Z just because a client sends altitude unless the application defines a vertical CRS and units.

### 29.4. Null vs. Empty

Specify whether `location` may be `NULL`. An empty geometry is not equivalent to `NULL`; handle both explicitly.

### 29.5. Business Constraints

You can add `CHECK` constraints to restrict coordinate ranges or validity, but evaluate performance and semantics before applying them to large tables.

## 30. Geometry Validity and Data Quality Pipelines

A spatial ingestion pipeline should:
1. Validate WKT/WKB/GeoJSON format.
2. Validate coordinate order and source CRS.
3. Transform to the storage CRS.
4. Validate type/dimension.
5. Check `NULL`/empty.
6. Check validity.
7. Check bounds/domain region.
8. Record rejection reasons.
9. Insert into the main table after validation.

### 30.1. ST_IsValidReason

Helps diagnose invalid polygons, such as ring self-intersections.

### 30.2. ST_MakeValid Is Not a Business Decision

Repairing a geometry can produce multiple components or alter its shape. Inspect the output against business rules.

### 30.3. Precision

Coordinates use floating-point numbers. Do not compare coordinates with exact equality when the domain requires tolerance; use `ST_DWithin` or appropriate precision normalization.

### 30.4. Outlier Detection

Coordinates outside the expected region may indicate swapped lat/lon, wrong CRS, or input corruption. Use bounds checks and monitoring.

## 31. Geometry and Z/M Dimensionality

PostGIS can store:
- XY: two dimensions.
- XYZ: adds a Z coordinate.
- XYM: adds a measure M.
- XYZM: both Z and M.

### 31.1. Z Is Not Automatically Accurate Altitude

Z is simply a third ordinate. Define the vertical datum, units, and elevation source if geographic meaning is required.

### 31.2. M Is Measure

M can represent chainage, route measure, or an application-defined linear quantity.

### 31.3. Not All Functions Use Z/M

Many traditional predicates/measurements are 2D or have specific behavior. Consult 3D counterparts such as `ST_3DDistance` when needed.

### 31.4. Typmod Dimensionality

A `geometry(PointZ, 4326)` column can enforce dimensionality. Verify inputs and function outputs accordingly.

## 32. Geography vs. Geometry for Distance Search

If you need points within 2 km:
- Geography: use longitude/latitude and distance in meters.
- Geometry: transform data/query to an appropriate projected CRS and use meters per that CRS.

### 32.1. Geography Example

```sql
SELECT id
FROM delivery_points
WHERE ST_DWithin(
    location::geography,
    :origin_geography,
    2000
);
```

### 32.2. Projected Geometry Example

```sql
SELECT id
FROM delivery_points_projected
WHERE ST_DWithin(
    location,
    :origin_projected,
    2000
);
```

### 32.3. Choose a Region-Appropriate CRS

Projected CRSs introduce distortion. Select the projection for the region and use case rather than picking an SRID merely because its unit name is meter.

### 32.4. Global Queries

If queries span multiple regions or countries, `geography` can be more convenient for geodetic distances, though performance and function coverage must be checked.

## 33. Geography vs. Geometry for Area

Area can be computed in two ways:

```sql
-- Geometry: result units are CRS units squared.
SELECT ST_Area(ST_Transform(boundary, 32648))
FROM zones;

-- Geography: result is square meters for the supported calculation.
SELECT ST_Area(boundary::geography)
FROM zones;
```

### 33.1. Projected Geometry

Well suited for area analysis within a single region using an appropriately chosen projection.

### 33.2. Geographic Geometry

`ST_Area` on SRID 4326 `geometry` returns square degrees, not physical area. Never display it as m².

### 33.3. Geography

Computes geodetic area using the default spheroid in the corresponding `geography` function.

### 33.4. Output Units

Name columns/aliases with explicit units such as `area_m2` and `length_m` to avoid downstream misunderstanding.

## 34. ST_Transform and Index Strategy

Suppose a table has an index on SRID 4326 `geometry`; queries should transform the query geometry to the column's SRID:

```sql
SELECT id
FROM spatial_features
WHERE ST_Intersects(
    geom_4326,
    ST_Transform(:query_geom_3857, 4326)
);
```

### 34.1. Avoid Transforming Every Row Unnecessarily

`ST_Transform(geom_4326, 3857)` in a predicate can prevent use of a plain index on `geom_4326`.

### 34.2. Functional Index

If queries consistently use the same expression, you can create a functional index:

```sql
CREATE INDEX spatial_features_3857_gix
ON spatial_features
USING GIST (ST_Transform(geom_4326, 3857));
```

### 34.3. Query Expression Must Match

The planner must recognize that the expression matches the functional index. Verify with `EXPLAIN`.

### 34.4. Cost of Storing Multiple Representations

Storing an extra projected column increases storage and requires synchronization whenever the source geometry changes. Only do this if justified by the workload.

## 35. Partitioning and Spatial Data

Partitioning can help when spatial data is partitioned by time, tenant, or business region.

### 35.1. Time Partitioning

Timestamped location events can be time-partitioned for retention/archival and query pruning.

### 35.2. Spatial Partitioning

Splitting by tile/grid/geohash or region can narrow data scope, provided the partition key aligns with query patterns.

### 35.3. Spatial Index per Partition

Each partition needs appropriate indexes; monitor index coverage and partition pruning.

### 35.4. Partition Boundaries

A geometry may cross multiple tiles/regions. Choose a controlled rule for storing a single copy, duplicating with identity tracking, or splitting geometries.

## 36. Performance and Query Planning

Spatial query performance depends on:
- Spatial indexes.
- Geometry complexity/vertex count.
- CRS and function choice.
- Query selectivity.
- Spatial data distribution.
- Table statistics.
- Join order.
- Reprojection cost.
- Validity/precision.
- Number of candidate geometries.

### 36.1. EXPLAIN ANALYZE

Inspect index scans, rows removed by filter, recheck conditions, loops, and buffer reads.

### 36.2. Geometry Complexity

A few massive geometries can dominate latency. You can simplify within an acceptable tolerance for display while preserving original geometries for legal/authoritative use.

### 36.3. Subdivision

`ST_Subdivide` can split large geometries into smaller parts for faster spatial indexing/filtering in certain workloads. Manage identity and aggregation so business results stay accurate.

### 36.4. Statistics

Run `ANALYZE` after bulk loads/updates and monitor planner estimates. Spatial data distributions can be highly skewed.

### 36.5. Avoid Unnecessary Transforms

Transform the query geometry once instead of transforming every row, or use a functional index when warranted.

## 37. Importing and Exporting Spatial Data

PostGIS commonly integrates with tools such as `ogr2ogr`/GDAL, `shp2pgsql`, and GIS clients.

Common formats:
- GeoJSON.
- Shapefile.
- GeoPackage.
- WKT/WKB.
- GeoParquet via suitable tooling.
- Raster formats via PostGIS Raster/GDAL.

### 37.1. Check CRS on Import

Does the source file include CRS metadata? If not, never guess the SRID solely from coordinate values.

### 37.2. Reproject Before or During Import

Select the target CRS and verify the transform pipeline. Check PROJ grids if datum transformations require them.

### 37.3. Field/Type Mapping

Check field names, string encoding, numeric precision, geometry types, and null handling.

### 37.4. Validate After Import

Compare row counts, extent, SRID, geometry types, validity, nulls, and sample visual output.

## 38. Migrating from Built-In point to PostGIS geometry

Suppose a legacy table exists:

```sql
CREATE TABLE legacy_locations (
    id bigint PRIMARY KEY,
    position point NOT NULL
);
```

Once the application confirms X/Y are WGS 84 longitude/latitude, expand the schema:

```sql
ALTER TABLE legacy_locations
ADD COLUMN location geometry(Point, 4326);
```

Backfill:

```sql
UPDATE legacy_locations
SET location = ST_SetSRID(
    ST_MakePoint(
        (position)[0],
        (position)[1]
    ),
    4326
)
WHERE location IS NULL;
```

### 38.1. Verify Source Before Assigning SRID

If legacy `point` values use local units or a projected CRS, do not assign 4326. Determine the source CRS and transform properly.

### 38.2. Batch Backfills for Large Tables

Do not run a single full-table `UPDATE` in production on a large table. Batch by primary key, commit, and monitor WAL/replication lag.

### 38.3. Validate

Check row counts, `NULL` counts, coordinate bounds, sample points, and expected geography. Reconcile against the source system.

### 38.4. Dual-Write and Cutover

Deploy application code writing both columns or transition in phases. Only drop the legacy `point` column in a later migration after all consumers use `geometry`.

### 38.5. Indexing and Rollback

Build the GiST index, test queries, and retain the legacy column during the rollback window. With `CREATE INDEX CONCURRENTLY`, the migration runner must support non-transactional execution.

## 39. Migrations and Extension Lifecycle

The PostGIS version must be compatible with the PostgreSQL major version, OS packages, PROJ/GDAL dependencies, and related extensions.

### 39.1. Check Version

```sql
SELECT PostGIS_Full_Version();
```

### 39.2. Upgrade SQL Extension

When the target package provides an update path:

```sql
ALTER EXTENSION postgis UPDATE;
```

Check available versions and PostGIS release notes before running. Companion PostGIS extensions may need separate updates.

### 39.3. Major PostgreSQL Upgrades

Target-compatible PostGIS binaries are needed on the new cluster. For `pg_upgrade`, extension libraries must satisfy the target major version's requirements.

### 39.4. Managed Services

Providers may support a specific set of extensions/versions. Verify availability before selecting a target PostgreSQL major version.

### 39.5. Backup/Restore

Restoring a database containing PostGIS requires compatible extension files on the target host/service and proper restoration of SQL extension objects.

## 40. Security and Access Control

Spatial data can reveal home addresses, customers, employees, assets, or delivery routes.

### 40.1. Least Privilege

Application roles only need privileges on appropriate schemas/tables/functions. Never grant superuser just to call spatial functions.

### 40.2. Sensitive Coordinates

Apply row-level security, tenant filters, and data minimization as needed. Do not place sensitive coordinates in logs or metrics labels.

### 40.3. Query Text and GeoJSON Logs

GeoJSON and coordinates can contain personal locations. Redact or restrict retention when logging requests.

### 40.4. Extension Trust

Install PostGIS from trusted package sources, apply security updates, and monitor extension versions.

## 41. Monitoring Spatial Workloads

Monitor:
- Query p50/p95/p99.
- Calls/s and slow spatial queries.
- GiST index scans/hit behavior.
- Rows removed by spatial filter.
- Buffer reads and temp I/O.
- Geometry complexity/vertex counts.
- Invalid geometry counts.
- Import/backfill throughput.
- Index build duration.
- Table/index growth.
- Replication lag/WAL rate.
- Extension version and upgrade status.

### 41.1. Do Not Just Check That an Index Exists

An index may go unused due to query expression, selectivity, statistics, or operator mismatch.

### 41.2. Geometry Complexity

A handful of huge geometries can dominate latency. Track vertex count distributions and query outliers.

### 41.3. Invalid Input

Count rejected/invalid geometries and classify reasons. Never silently drop invalid data.

### 41.4. Upgrade Monitoring

After extension or server upgrades, watch function errors, plan changes, index behavior, and query latency.

## 42. Troubleshooting: Distance Returns Wrong Results

Symptom: two nearby points produce an unexpectedly huge or tiny `ST_Distance` result.

Check:
1. Is the type `geometry` or `geography`?
2. Are both SRIDs identical and correct?
3. Is SRID 4326 `geometry` being measured in degrees?
4. Are longitude and latitude swapped?
5. Was `ST_SetSRID` used instead of `ST_Transform`?
6. Does the source CRS have the right metadata?
7. Is the `geography` cast appropriate?
8. Does the projection have acceptable distortion for the region?
9. Do query outputs have explicit aliases/units?

### 42.1. Geometry 4326

Distances are returned in coordinate degrees. Switch to `geography` or transform to an appropriate projected CRS.

### 42.2. SRID Mismatch

Never attach a fake SRID just to make a query run. Verify the source and transform properly.

### 42.3. Coordinate Order

Check a few points with known locations. Swapping X/Y can place geometries in the wrong part of the world.

### 42.4. Test a Known Distance

Use a pair of coordinates with a known reference distance to verify units and CRS.

## 43. Troubleshooting: Spatial Query Does Not Use Index

Symptom: `EXPLAIN` shows a sequential scan on a large table.

Check:
1. Does the GiST index exist and is it valid?
2. Does the query use an index-supported spatial predicate/operator?
3. Is the column wrapped in a different function or `CAST` expression?
4. Is there an SRID mismatch?
5. Does the query return most of the table?
6. Are statistics up to date?
7. Are planner estimates reasonable?
8. Is a functional index needed?
9. What are geometry complexity and table size?
10. What does `EXPLAIN (ANALYZE, BUFFERS)` show?

### 43.1. Index-Aware Predicates

Prefer `ST_Intersects`/`ST_DWithin` or PostGIS-documented patterns when appropriate.

### 43.2. Transform Query Side

Transform the query geometry to the indexed column's SRID when possible.

### 43.3. Functional Index

If queries always transform the column, create a matching functional index after evaluating storage/maintenance costs.

### 43.4. Sequential Scan Can Be Correct

If a query fetches most of the table or the table is small, a sequential scan can be cheaper than an index scan.

## 44. Common Misconceptions

1. **PostgreSQL has `point`, so PostGIS is unnecessary.** Only true for simple planar geometry problems.
2. **Built-in `point` understands longitude/latitude.** False; it only stores X/Y.
3. **Setting an SRID converts coordinates.** False; `ST_SetSRID` only changes metadata.
4. **`ST_Transform` only changes a label.** False; it transforms coordinates across CRSs.
5. **`geometry` 4326 measures distance in meters.** False; units are degrees.
6. **`geography` supports all PostGIS functions.** False; function coverage and type support are narrower.
7. **EPSG:3857 is always accurate for area.** False; distortion can be substantial.
8. **`&&` is exact intersection.** False; it checks bounding-box overlap.
9. **Having a GiST index means every spatial query uses it.** False; predicates, expressions, selectivity, and plans decide.
10. **`ST_Centroid` always lies inside the polygon.** False for concave or complex polygons.
11. **`ST_MakeValid` always returns the same geometry type.** False; output can change type or become a collection.
12. **Z is automatically altitude in meters.** False; a vertical CRS/units contract is required.
13. **PostGIS is a separate database server.** False; it is a PostgreSQL extension.
14. **`CREATE EXTENSION` in one database applies to all databases.** False; extension state is per database.
15. **PostGIS automatically geocodes street addresses.** False; a geocoding dataset/service is needed.
16. **`ST_Distance` followed by `WHERE < radius` always leverages indexes well.** Usually `ST_DWithin` should be used to filter candidates.
17. **Transforming a column in `WHERE` does not affect indexing.** It can prevent a standard index from being used without a functional index.
18. **A valid polygon is guaranteed to be in the right location.** False; SRID, coordinates, and business extent can still be wrong.
19. **Logical migration automatically syncs all spatial metadata.** False; schemas, extensions, and objects require explicit migration.
20. **A spatial index replaces validation.** False; validity, CRS, and domain checks are still needed.

## 45. Practice Exercises with Answers

### Exercise 1. What are PostgreSQL's built-in geometric types?

**Answer:** `point`, `line`, `lseg`, `box`, `path`, `polygon`, and `circle`.

### Exercise 2. What information does `point` store?

**Answer:** Two X/Y coordinates on an application-defined plane.

### Exercise 3. Does built-in `point` have an SRID?

**Answer:** No. It carries no CRS metadata.

### Exercise 4. How does `line` differ from `lseg`?

**Answer:** `line` is an infinite straight line; `lseg` is a line segment with two endpoints.

### Exercise 5. What shape does `box` represent?

**Answer:** An axis-aligned rectangle defined by two opposite corners.

### Exercise 6. How are open and closed `path` values represented?

**Answer:** An open path uses square brackets; a closed path uses parentheses in its input representation.

### Exercise 7. Is a `circle` radius automatically in meters?

**Answer:** No. The radius uses the units of the application's coordinate plane.

### Exercise 8. What is PostGIS?

**Answer:** An extension adding spatial types, functions, operators, indexes, and CRS support to PostgreSQL.

### Exercise 9. Is PostGIS a separate database server?

**Answer:** No. It runs inside the PostgreSQL database.

### Exercise 10. Where does `CREATE EXTENSION postgis` take effect?

**Answer:** In the database where the command is run; each database must be enabled separately.

### Exercise 11. How does `geometry` differ from `geography`?

**Answer:** `geometry` uses a planar coordinate model; `geography` supports geodetic calculations on the Earth's surface.

### Exercise 12. What distance units does SRID 4326 `geometry` use?

**Answer:** Angular coordinate units, typically degrees, not meters.

### Exercise 13. What units does `geography` `ST_Distance` normally return?

**Answer:** Meters for the corresponding `geography` overload.

### Exercise 14. What does EPSG:4326 typically describe?

**Answer:** The WGS 84 geographic CRS with longitude/latitude coordinates.

### Exercise 15. In PostGIS X/Y for 4326, what is the standard order?

**Answer:** X = longitude, Y = latitude.

### Exercise 16. Where is EPSG:3857 commonly used?

**Answer:** Web map tiles/Web Mercator; not an accurate choice for all global measurements.

### Exercise 17. What role does SRID play?

**Answer:** Identifies the coordinate reference system of a `geometry` or `geography`.

### Exercise 18. Does `ST_SetSRID` change coordinates?

**Answer:** No. It changes only SRID metadata.

### Exercise 19. What does `ST_Transform` do?

**Answer:** Converts coordinates from a source CRS to a target CRS.

### Exercise 20. Why must you never guess an SRID?

**Answer:** Wrong metadata causes distance, area, overlay, and transform operations to return incorrect results.

### Exercise 21. Does `ST_MakePoint(106.7, 10.8)` automatically have SRID 4326?

**Answer:** No. You must attach the proper SRID with `ST_SetSRID` or an appropriate constructor.

### Exercise 22. Does WKT always contain an SRID?

**Answer:** No. Standard WKT does not include an SRID; EWKT can include PostGIS metadata.

### Exercise 23. What coordinate order does RFC 7946 GeoJSON use?

**Answer:** Longitude first, latitude second in WGS 84 coordinate order.

### Exercise 24. What does `geometry(Point, 4326)` enforce?

**Answer:** The `Point` geometry subtype and SRID 4326, along with dimensionality per the typmod.

### Exercise 25. When is `geography(Point, 4326)` appropriate?

**Answer:** Storing geographic points to use `geography` operations such as distance in meters.

### Exercise 26. What question does `ST_Intersects` answer?

**Answer:** Whether two geometries share at least one point in common.

### Exercise 27. How are `ST_Contains` and `ST_Within` related?

**Answer:** They have reversed argument order, with boundary semantics that must be understood clearly.

### Exercise 28. When a point on a boundary still counts as inside the region, which functions should you check?

**Answer:** `ST_Covers` or `ST_CoveredBy`, depending on argument direction.

### Exercise 29. What advantage does `ST_DWithin` have over filtering with `ST_Distance`?

**Answer:** It tests within a threshold and can leverage a spatial index.

### Exercise 30. What does `ST_Area` on SRID 4326 `geometry` return?

**Answer:** Area in squared CRS units, typically square degrees, not m².

### Exercise 31. Does `ST_Centroid` always lie inside a polygon?

**Answer:** No. `ST_PointOnSurface` is better when you need a point guaranteed to be on the surface.

### Exercise 32. What is `ST_IsValid` used for?

**Answer:** Checking the topological validity of a geometry.

### Exercise 33. Can `ST_MakeValid` change a geometry's type?

**Answer:** Yes. Output may become a MultiGeometry or GeometryCollection.

### Exercise 34. What is a GiST spatial index used for?

**Answer:** Quickly finding candidate geometries via a spatial index strategy, typically based on bounding boxes.

### Exercise 35. Is `&&` an exact intersection check?

**Answer:** No. It checks bounding-box overlap.

### Exercise 36. Can `ST_Intersects` use a spatial index?

**Answer:** Yes, PostGIS has index-aware behavior for this predicate when the query and planner allow it.

### Exercise 37. Why is an index not used in every query?

**Answer:** Predicate/operator, expression, selectivity, statistics, and planner cost determine index usage.

### Exercise 38. What does the KNN operator `<->` help with?

**Answer:** Supports nearest-neighbor ordering on compatible operator classes/indexes.

### Exercise 39. Does KNN on SRID 4326 `geometry` compute distance in meters?

**Answer:** No. `geometry` distance remains in planar coordinate units.

### Exercise 40. When is built-in `point` appropriate?

**Answer:** Diagrams/canvases/game boards or local planar coordinates not requiring CRS or GIS functions.

### Exercise 41. When is PostGIS appropriate?

**Answer:** Geofencing, radius search, GIS layers, spatial joins, coordinate transformations, and spatial analytics.

### Exercise 42. Does PostGIS geocode addresses on its own?

**Answer:** No. A geocoding service/dataset is required; PostGIS stores and queries coordinates.

### Exercise 43. Does PostGIS compute the fastest road route on its own?

**Answer:** No. Routing usually requires pgRouting or a specialized routing engine.

### Exercise 44. Why create a functional index for `ST_Transform` when needed?

**Answer:** A query transforming a column in its expression may not use a standard index on the base column; a functional index can support that expression.

### Exercise 45. Why validate geometry type and SRID during ingestion?

**Answer:** To prevent wrong-CRS or wrong-type data from corrupting spatial calculations and joins.

### Exercise 46. What pattern should a migration from `point` to `geometry` follow?

**Answer:** Add column, backfill with CRS verification, validate, dual-write/cutover, and drop the legacy column later.

### Exercise 47. Why must the PostGIS package match the PostgreSQL major version?

**Answer:** Extension shared libraries and package dependencies must be build- and runtime-compatible with the server major version/platform.

### Exercise 48. Can `CREATE INDEX CONCURRENTLY` run inside a normal transaction block?

**Answer:** No. The migration runner must support non-transactional execution.

### Exercise 49. What should be checked after importing spatial data?

**Answer:** Row counts, SRID, geometry type, bounds, validity, `NULL`s, and sample outputs.

### Exercise 50. What should determine the choice between built-in types and PostGIS?

**Answer:** Whether you need CRS support, Earth distances/areas, spatial predicates, transformations, GIS formats, indexing, and spatial workload scalability.

## 46. Spatial Data Design Checklist

| Question | What to determine |
|---|---|
| Domain | Is this a flat diagram or locations on Earth? |
| Type | Built-in `point`/`box`, `geometry`, or `geography`? |
| CRS | What are the source and target SRIDs? |
| Units | Degrees, meters, or local units? |
| Axis | Are X/Y in the right longitude/latitude order? |
| Dimension | XY, XYZ, XYM, or XYZM? |
| Type constraint | Point, LineString, Polygon, MultiPolygon? |
| Validity | Are `ST_IsValid` and domain bounds checked? |
| Boundary | Are boundary points considered inside or outside? |
| Measurements | Do distance/area need planar or geodetic calculations? |
| Index | Is GiST/SP-GiST/functional indexing appropriate? |
| Query | Do `ST_DWithin`/`ST_Intersects` use the index? |
| Performance | Geometry complexity/selectivity/`EXPLAIN`? |
| Migration | Are backfill/dual-write/cutover safe? |
| Operations | Extension packages/versions/backup/restore? |
| Security | Are coordinates sensitive? |
| Integration | GeoJSON axis order/CRS contract? |
| Validation | Are there known-point/reference-distance tests? |

## 47. Official PostgreSQL and PostGIS Documentation

- [PostgreSQL Geometric Types](https://www.postgresql.org/docs/current/datatype-geometric.html) — `point`, `line`, `lseg`, `box`, `path`, `polygon`, and `circle`.
- [PostgreSQL Geometric Functions and Operators](https://www.postgresql.org/docs/current/functions-geometry.html) — built-in geometric operators/functions.
- [PostgreSQL Index Types](https://www.postgresql.org/docs/current/indexes-types.html) — GiST and index methods.
- [PostGIS Documentation](https://postgis.net/documentation/) — guide to installing and using PostGIS.
- [PostGIS Geometry](https://postgis.net/docs/geometry.html) — `geometry` type.
- [PostGIS Geography](https://postgis.net/docs/geography.html) — `geography` type.
- [PostGIS ST_SetSRID](https://postgis.net/docs/ST_SetSRID.html) — attaching SRID metadata.
- [PostGIS ST_Transform](https://postgis.net/docs/ST_Transform.html) — transforming coordinates between CRSs.
- [PostGIS Spatial Relationships](https://postgis.net/docs/reference.html#Spatial_Relationships) — predicates such as `ST_Intersects`/`ST_Contains`.
- [PostGIS Measurement Functions](https://postgis.net/docs/reference.html#Measurement_Functions) — distance, area, length, and measurements.
- [PostGIS Spatial Indexing](https://postgis.net/workshops/postgis-intro/indexing.html) — GiST, bounding boxes, and query patterns.
- [PostGIS FAQ](https://postgis.net/documentation/faq/) — common deployment questions.

Function overloads, operator classes, CRS definitions, and extension packaging change across PostgreSQL/PostGIS/PROJ versions. Check documentation for your exact version, `PostGIS_Full_Version()`, and actual execution plans before deploying to production.

## 48. Summary: Data Types Must Reflect the Coordinate System and Problem

```text
Do we need Earth-referenced spatial data?
             |
       +-----+-----+
       |           |
      No          Yes
       |           |
       v           v
Built-in planar  Do we need geodetic
geometric types  calculations?
                   |
              +----+----+
              |         |
             Yes        No / local region
              |         |
              v         v
          geography   geometry + suitable CRS
              |         |
              +----+----+
                   |
                   v
      SRID + type + validity + units
                   |
                   v
          Spatial predicates/indexes
                   |
                   v
       Validate results and performance
```

Key principles to remember:

1. **PostgreSQL built-in geometric types are planar geometry.** They fit points, lines, boxes, paths, polygons, and circles in an application-defined coordinate system.
2. **Built-in `point` has no awareness of CRS or units.** An X/Y pair is not automatically longitude/latitude.
3. **PostGIS adds a fuller spatial model.** `geometry`, `geography`, SRID, functions, predicates, and spatial indexes support GIS workloads.
4. **Geometry uses planar coordinate units.** With SRID 4326 `geometry`, distance/length/area are not automatically in meters/square meters.
5. **Geography supports geodetic measurements.** It is convenient for Earth-surface distances/areas, though function coverage and performance differ from `geometry`.
6. **`ST_SetSRID` attaches metadata; `ST_Transform` converts coordinates.** Never use them interchangeably.
7. **Spatial indexes typically filter candidates using bounding boxes.** Exact predicates are still needed to confirm geometric relationships.
8. **`ST_DWithin` usually suits radius search.** Use `EXPLAIN` to confirm index usage and units.
9. **Validity does not mean business-valid data.** Check CRS, coordinate order, bounds, and business semantics.
10. **PostGIS is a per-database extension.** It requires compatible packages, `CREATE EXTENSION`, and a backup/restore and upgrade plan.
11. **Migrations must preserve coordinate meaning.** Verify the source CRS before converting built-in `point` to `geometry`.
12. **Choose by problem, not by data type name.** Flat diagrams may only need built-in types; real GIS usually requires PostGIS.

**One sentence to remember:** *PostgreSQL's built-in geometric types describe shapes on a plane; PostGIS adds coordinate reference systems, Earth models, measurements, and indexes for working with real-world spatial data.*
