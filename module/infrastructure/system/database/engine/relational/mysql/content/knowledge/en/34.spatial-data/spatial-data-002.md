# Cartesian/Geographic Spatial Reference Systems and SRID

Spatial data is only meaningful when its coordinate system is clearly defined. Two `POINT` values with the exact same pair of numbers can represent completely different locations if one is longitude/latitude and the other is meters on a projected plane. MySQL associates a Spatial Reference System (SRS) with each geometry via a Spatial Reference System Identifier (SRID). The SRID tells MySQL how to interpret coordinate axes, units, and the geometric model of the data.

The two SRS categories to distinguish are Cartesian and geographic. Cartesian systems describe coordinates on a flat plane; geographic systems describe locations on the Earth's surface using a geographic coordinate system. SRID 0 is MySQL's default Cartesian system when a geometry is not assigned a specific SRS. EPSG:4326 is commonly used for WGS 84 latitude/longitude; EPSG:3857 is the Web Mercator projection frequently encountered in web mapping. These systems cannot be swapped merely by changing the SRID label.

In the `DATABASE_MYSQL` module, you must choose an SRS suited to your data source and calculations, specify axis order explicitly, store geometries with a consistent SRID, and distinguish SRID assignment from coordinate transformation. A wrong SRID can cause spatial queries to return incorrect results even when the SQL executes without error.

The DDL and query examples in this lesson target MySQL 8.0.13 or later for SRID restrictions, explicit axis order, and `ST_Transform()`. On older versions, verify actual feature support before using the corresponding syntax.

## Objectives

After this lesson, you will be able to:

- Explain SRS, SRID, EPSG codes, and the role of coordinate metadata.
- Distinguish Cartesian SRSs from geographic SRSs.
- Understand SRID 0 and the risks of using it for real geographic data.
- Select the appropriate SRID for longitude/latitude, map data, and local measurements.
- Query MySQL-supported SRSs in `INFORMATION_SCHEMA`.
- Construct geometries with an explicit SRID using WKT.
- Inspect SRID, geometry type, axis order, and coordinate ranges.
- Distinguish `ST_SRID()` for metadata assignment from `ST_Transform()` for coordinate system transformation.
- Design geometry columns with SRID restrictions and spatial indexes.
- Understand the limitations of MBR predicates and how to combine approximate filters with exact checks.
- Build a workflow to ingest, normalize, validate, and transform spatial data.

## 1. What Is a Spatial Reference System?

A Spatial Reference System (SRS) is the mathematical definition and metadata describing how coordinates are interpreted. Depending on the system, the definition may describe:

- Coordinate system type: Cartesian (planar) or geographic (Earth-based).
- Coordinate axes and axis order.
- Measurement units, such as degrees or meters.
- Datum, ellipsoid, and map projection if applicable.
- Parameters needed to transform into other coordinate systems.

An SRID is the identifier of an SRS in MySQL. A geometry carrying an SRID indicates which SRS its coordinates must be interpreted under. The SRID is not decorative metadata and does not automatically modify existing coordinates.

For example, the pair `(106.7, 10.8)` can be interpreted as longitude 106.7 degrees and latitude 10.8 degrees in a geographic SRS. If instead it is tagged with a projected SRS whose units are meters, MySQL will interpret those numbers according to that projection's definition. Assigning the wrong SRID corrupts the meaning of the data.

## 2. Cartesian vs. Geographic SRS

### 2.1. Cartesian: Planar Geometry

A Cartesian SRS describes positions using flat planar axes, typically X and Y. Geometric operations follow planar geometry:

- Coordinates use the linear units of the SRS, such as meters or feet if the system defines those units.
- Distance is planar distance in the coordinate system.
- Area is planar area in squared linear units.
- Earth curvature is not automatically accounted for.

MySQL's SRID 0 is the default Cartesian SRS and is not bound to a specific geographic unit. It suits floor plans, indoor layouts, CAD/engineering drawings, or local coordinate systems where the application defines the units. You should not use SRID 0 for real longitude/latitude coordinates and expect calculations to understand distances on Earth.

A projected SRS such as EPSG:3857 also uses planar coordinates, typically expressed in meters. However, meters in a map projection do not mean every distance or area is accurate on the ground. Web Mercator introduces distortion that grows with latitude; it is primarily useful for web map display.

### 2.2. Geographic: Coordinates on Earth

A geographic SRS represents locations by longitude/latitude or geographic axes defined by the SRS. Coordinates are typically angular, such as degrees:

- Longitude describes east/west position.
- Latitude describes north/south position.
- Latitude values must lie within the system's valid geographic range; for WGS 84, this is typically -90 to +90 degrees.
- WGS 84 longitude typically lies within -180 to +180 degrees.

Geographic operations must account for the ellipsoid model and Earth curvature. For MySQL-supported geographic SRSs, functions such as `ST_Distance()` return distance in meters and `ST_Area()` returns area in square meters. This is an important difference from geometries in SRID 0, where units are simply arbitrary coordinate units defined by application convention.

### 2.3. Comparison Table

| Criterion | Cartesian SRS | Geographic SRS |
|---|---|---|
| Model | Flat plane | Earth's surface |
| Typical coordinates | X/Y | Longitude/latitude or defined geographic axes |
| Coordinate unit | Linear unit of the SRS | Angular unit, usually degrees |
| Distance | Linear unit of the SRS; SRID 0 has no geographic unit | Meters for supported geographic SRSs |
| Area | Squared linear units | Square meters for supported geographic SRSs |
| Best suited for | Floor plans, drawings, projected planar systems | Global geographic locations |
| Main risk | Treating degree data as planar coordinates | Mixing up axis order, datum, or coordinate ranges |

There is no single best SRS for every scenario. Choose the system based on your goal: storing global locations, computing geographic distances, making local measurements, or rendering maps.

## 3. SRID 0, EPSG, and Common Identifiers

### 3.1. SRID 0

If you construct a geometry without specifying an SRID, MySQL typically assigns SRID 0. This is the default Cartesian SRS. Two geometries sharing SRID 0 can participate in Cartesian operations, but MySQL cannot infer whether they represent longitude/latitude, meters, or feet.

Example:

~~~sql
SET @local_point = ST_GeomFromText('POINT(12.5 8.25)');

SELECT
    ST_SRID(@local_point) AS srid,
    ST_AsText(@local_point) AS wkt;
~~~

The geometry above carries SRID 0 because no SRID was supplied. The two numbers `12.5` and `8.25` only carry meaning according to the application's convention.

### 3.2. EPSG Codes

EPSG is a registry of coordinate definitions and spatial reference parameters. MySQL ships with an SRS catalog in which many SRIDs correspond to familiar EPSG codes. Do not assume every SRID in every system is an EPSG code; inspect the organization and organization coordinate-system ID in MySQL's catalog.

Common systems:

| SRID | Common Name | Kind | Common Use Case |
|---:|---|---|---|
| 0 | MySQL default Cartesian | Cartesian | Planar/local data without a geographic SRS |
| 4326 | WGS 84 | Geographic 2D | Global longitude/latitude |
| 3857 | WGS 84 / Pseudo-Mercator | Projected Cartesian | Web map rendering |

EPSG:4326 is not a planar coordinate system. EPSG:3857 is a projected planar system derived from geographic data. Never write longitude/latitude values directly into an SRID 3857 column without transforming the coordinates first.

### 3.3. Querying MySQL's SRS Catalog

MySQL provides `INFORMATION_SCHEMA.ST_SPATIAL_REFERENCE_SYSTEMS` to inspect installed coordinate systems:

~~~sql
SELECT
    SRS_ID,
    SRS_NAME,
    ORGANIZATION,
    ORGANIZATION_COORDSYS_ID,
    DEFINITION
FROM INFORMATION_SCHEMA.ST_SPATIAL_REFERENCE_SYSTEMS
WHERE SRS_ID IN (4326, 3857);
~~~

The columns show the ID in MySQL, system name, defining organization, organization ID, and SRS definition. You can inspect `DEFINITION` to verify the system type, units, and coordinate axes. You do not need to copy the entire definition into the application just for lookup purposes; manage the chosen SRID as part of your data contract.

SRID 0 is MySQL's special default system; do not rely on it appearing in the catalog in the same way as EPSG SRSs.

## 4. Axis Order: Longitude/Latitude or Latitude/Longitude?

This is a frequent source of bugs. Many mapping APIs pass coordinates in longitude, latitude (X/Y) order. However, the official EPSG:4326 definition specifies axes in latitude, longitude order. By default, MySQL interprets geographic axes according to the SRS definition unless you specify an axis-order option.

For example, when passing data in the common longitude-first order, state it explicitly:

~~~sql
SET @hcm_point = ST_GeomFromText(
    'POINT(106.7000 10.8000)',
    4326,
    'axis-order=long-lat'
);

SELECT
    ST_SRID(@hcm_point) AS srid,
    ST_AsText(@hcm_point, 'axis-order=long-lat') AS longitude_latitude;
~~~

In this example, `106.7000` is longitude and `10.8000` is latitude. The `axis-order` option clarifies the order of values in WKT. If omitted, MySQL uses the default axis order defined by the SRS.

Available `axis-order` options when reading/writing WKT or other supported formats:

- `axis-order=srid-defined`: use the axis order in the SRS definition.
- `axis-order=lat-long`: interpret latitude first, longitude second.
- `axis-order=long-lat`: interpret longitude first, latitude second.

Use a single convention consistently across ingestion, APIs, migrations, and queries. Never swap two numbers to "fix" a wrong result without first checking the axis definition.

### 4.1. Validating Coordinate Ranges

In WGS 84, longitude and latitude must fall within valid bounds. For instance, a latitude of 106.7 degrees is invalid; this typically happens when longitude/latitude are passed in the opposite order from what the parser expects.

When constructing geographic geometries, MySQL can reject coordinates outside the SRS bounds. Do not treat range errors as a cue to arbitrarily swap axes; confirm the data source and convention first.

## 5. How Geometries Carry SRIDs

MySQL supports these core geometry types:

- `POINT`: a single location.
- `LINESTRING`: a path of ordered points.
- `POLYGON`: an area enclosed by linear rings.
- `MULTIPOINT`, `MULTILINESTRING`, `MULTIPOLYGON`: collections of geometries of the same type.
- `GEOMETRYCOLLECTION`: a collection of geometries that may differ in type.

The SRID is attached to each geometry value. Two geometries used in a spatial operation should share the same SRID and compatible coordinate system. If one geometry is 4326 and the other is 3857, their numbers do not carry the same meaning. MySQL raises an SRID mismatch error rather than transforming automatically.

### 5.1. Creating Geometries from WKT

Well-Known Text (WKT) is a text format describing geometries. You can pass the SRID when constructing a value:

~~~sql
SET @point = ST_GeomFromText(
    'POINT(106.7000 10.8000)',
    4326,
    'axis-order=long-lat'
);

SET @line = ST_GeomFromText(
    'LINESTRING(106.70 10.80, 106.71 10.81)',
    4326,
    'axis-order=long-lat'
);

SELECT
    ST_SRID(@point) AS point_srid,
    ST_GeometryType(@point) AS geometry_type,
    ST_AsText(@point, 'axis-order=long-lat') AS point_wkt;
~~~

Other WKT constructors such as `ST_PointFromText()` also accept an SRID according to supported syntax. For geographic SRSs, pass the `axis-order` option whenever the coordinate source uses the longitude/latitude convention.

### 5.2. POLYGON Rings Must Be Closed

A WKT polygon must have a closed exterior ring, meaning the last point matches the first point. Rectangle example:

~~~sql
SET @district = ST_GeomFromText(
    'POLYGON((
        106.60 10.70,
        106.80 10.70,
        106.80 10.90,
        106.60 10.90,
        106.60 10.70
    ))',
    4326,
    'axis-order=long-lat'
);

SELECT ST_SRID(@district), ST_GeometryType(@district);
~~~

Vertices are written in longitude/latitude order thanks to the specified option. A self-intersecting polygon or one with invalid rings can raise errors or yield unexpected results in geometric operations; validate geometry validity on ingest.

### 5.3. Inspecting Geometries

~~~sql
SELECT
    ST_SRID(@district) AS srid,
    ST_GeometryType(@district) AS geometry_type,
    ST_IsValid(@district) AS is_valid,
    ST_AsText(@district, 'axis-order=long-lat') AS wkt;
~~~

`ST_IsValid()` checks geometric validity against the OGC rules supported by MySQL. Validity checks do not prove that a geometry belongs to the right place or tenant; those are separate business rules.

## 6. Assigning SRID vs. Transforming Coordinates

These two operations must never be confused.

### 6.1. ST_SRID() Reads or Assigns the SRID Label

With one argument, `ST_SRID(geometry)` returns the current SRID. With a second argument, `ST_SRID(geometry, srid)` assigns a new SRID to the geometry without recalculating its coordinates.

~~~sql
-- SRID 0: raw numbers without geographic axes; we stored them in the
-- latitude, longitude order defined by target SRS 4326.
SET @point_without_srs = ST_GeomFromText('POINT(10.8 106.7)');

SELECT ST_SRID(@point_without_srs) AS original_srid;

SET @point_tagged = ST_SRID(@point_without_srs, 4326);

SELECT
    ST_SRID(@point_tagged) AS assigned_srid,
    ST_AsText(@point_tagged, 'axis-order=long-lat') AS longitude_latitude;
~~~

The snippet above is only appropriate if the numbers were already stored in the target SRS's axis order (latitude first, longitude second for EPSG:4326) and simply lacked metadata. When exported with `long-lat`, the output shows `106.7` and `10.8`. It does not convert an arbitrary Cartesian point into a WGS 84 location.

If the original data was actually in meters in a projected system, assigning 4326 makes MySQL misinterpret meters as degrees. The numbers remain unchanged while their meaning changes, leading to wrong locations or out-of-range errors.

### 6.2. ST_Transform() Transforms Coordinates

`ST_Transform(geometry, target_srid)` transforms coordinates from the current SRS to the target SRS when MySQL supports the corresponding transformation. The function updates both the coordinates and the resulting SRID.

~~~sql
SET @hcm_wgs84 = ST_GeomFromText(
    'POINT(106.7000 10.8000)',
    4326,
    'axis-order=long-lat'
);

SET @hcm_web_mercator = ST_Transform(@hcm_wgs84, 3857);

SELECT
    ST_SRID(@hcm_wgs84) AS source_srid,
    ST_AsText(@hcm_wgs84, 'axis-order=long-lat') AS source_coordinates,
    ST_SRID(@hcm_web_mercator) AS target_srid,
    ST_AsText(@hcm_web_mercator) AS projected_coordinates;
~~~

The first output keeps longitude/latitude in degrees. The second output contains projected coordinates in EPSG:3857. Never multiply or divide coordinates manually to approximate a projection; use supported SRS transformations.

### 6.3. When ST_Transform() Fails

A transformation can fail if:

- The source geometry lacks a valid SRS or carries SRID 0.
- The target SRID does not exist in the SRS catalog.
- MySQL lacks the parameters or transformation path between the two SRSs.
- The geometry contains coordinates outside the valid domain of the source or target SRS.
- The data's axis order or datum does not match what was declared.

Do not work around failures by merely reassigning the SRID on the geometry. Inspect the source SRS, target SRS, axes, units, and coordinate bounds before retrying.

### 6.4. Summary Comparison Table

| Function | Effect | Do Coordinates Change? | When to Use |
|---|---|---:|---|
| `ST_SRID(g)` | Read SRID | No | Inspecting metadata |
| `ST_SRID(g, srid)` | Assign a new SRID | No | Coordinates are already in that system but missing/wrong metadata |
| `ST_Transform(g, srid)` | Change SRS and coordinates | Yes | Actually converting coordinate systems |

## 7. Declaring an SRID Restriction on a Geometry Column

A geometry column without an SRID restriction can hold geometries from different SRSs. That complicates querying, indexing, and data consistency.

MySQL 8.0.13+ supports specifying an SRID restriction directly in the column definition. Every geometry written to that column must then carry the declared SRID.

~~~sql
CREATE TABLE delivery_point (
    point_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    point_name VARCHAR(120) NOT NULL,
    position POINT NOT NULL SRID 4326,
    PRIMARY KEY (point_id)
) ENGINE=InnoDB;
~~~

The `position` column accepts only `POINT` values with SRID 4326. If the application sends a geometry with SRID 0 or 3857, MySQL rejects it rather than silently mixing coordinate systems.

### 7.1. Inserting Data with the Correct SRID

~~~sql
INSERT INTO delivery_point (point_name, position)
VALUES (
    'Ben Thanh',
    ST_GeomFromText(
        'POINT(106.6983 10.7725)',
        4326,
        'axis-order=long-lat'
    )
);
~~~

### 7.2. Verifying Data After Insert

~~~sql
SELECT
    point_id,
    point_name,
    ST_SRID(position) AS srid,
    ST_AsText(position, 'axis-order=long-lat') AS longitude_latitude
FROM delivery_point;
~~~

The result must show SRID 4326. Verify metadata at both the database and application layers to catch mapping mistakes early.

## 8. Spatial Indexes and SRID

MySQL InnoDB supports R-tree-based spatial indexes. A spatial index stores the Minimum Bounding Rectangle (MBR) of each geometry to locate spatial candidates by region.

In MySQL 8.0, the optimizer uses a spatial index on a geometry column when the column is restricted to a specific SRID; a geometry column in a spatial index must also be `NOT NULL`. Declare the SRID restriction and `NOT NULL` up front, then confirm the execution plan with `EXPLAIN` on your deployed MySQL version.

~~~sql
ALTER TABLE delivery_point
    ADD SPATIAL INDEX sx_delivery_position (position);

SHOW CREATE TABLE delivery_point;
~~~

A spatial index is no substitute for choosing the right SRS. A fast index built on mislabeled SRID data still returns results from the wrong coordinate system.

### 8.1. What Is an MBR?

The MBR is the smallest axis-aligned rectangle enclosing a geometry. For a `POINT`, the MBR degenerates to the point itself. For a complex `POLYGON`, the MBR can include substantial area outside the actual polygon.

MBR functions such as `MBRContains()`, `MBRWithin()`, `MBRIntersects()`, and `MBROverlaps()` operate on bounding rectangles. They are suited for candidate filtering and can utilize spatial indexes.

Exact geometric predicates such as `ST_Contains()` or `ST_Intersects()` evaluate the actual shape. With complex geometries, an MBR filter can produce false positives; an exact check is required when business logic demands true boundaries.

### 8.2. Region Queries: MBR Filter Followed by Exact Check

~~~sql
SET @search_area = ST_GeomFromText(
    'POLYGON((
        106.60 10.70,
        106.80 10.70,
        106.80 10.90,
        106.60 10.90,
        106.60 10.70
    ))',
    4326,
    'axis-order=long-lat'
);

SELECT point_id, point_name
FROM delivery_point
WHERE MBRContains(@search_area, position)
  AND ST_Contains(@search_area, position);
~~~

`MBRContains()` performs the bounding-rectangle filter; `ST_Contains()` verifies exact geometry containment. In this example the region is rectangular so its MBR matches the shape; with complex polygons, the exact check eliminates candidates inside the MBR that fall outside the polygon.

### 8.3. Confirming Optimizer Index Usage

~~~sql
EXPLAIN
SELECT point_id, point_name
FROM delivery_point
WHERE MBRContains(@search_area, position);
~~~

Inspect the access type, `key`, and estimated `rows`. If the optimizer does not use the spatial index, check:

- Is the geometry column `NOT NULL`?
- Does the column have an SRID restriction?
- Is the predicate a supported MBR predicate?
- Do both geometries share the same SRID?
- Is the table large enough for the optimizer to prefer the index?
- Are table statistics and the MySQL version appropriate?

Do not assume an index is broken simply because a tiny table chooses a table scan. Test with representative data and inspect `EXPLAIN` after updating statistics if needed.

## 9. Distance and Area Depend on the SRS

You cannot interpret a distance result without knowing the SRS and units.

### 9.1. Distance with a Geographic SRS

For two WGS 84 points, `ST_Distance()` returns distance in meters:

~~~sql
SET @p1 = ST_GeomFromText(
    'POINT(106.7000 10.8000)',
    4326,
    'axis-order=long-lat'
);

SET @p2 = ST_GeomFromText(
    'POINT(106.7100 10.8100)',
    4326,
    'axis-order=long-lat'
);

SELECT ST_Distance(@p1, @p2) AS distance_metres;
~~~

This is a geographic measurement under the SRS, not a Euclidean calculation on raw longitude/latitude differences. The length of one degree of longitude varies with latitude, so you cannot use a fixed factor to convert degrees to meters everywhere.

### 9.2. Distance with a Cartesian SRS

With SRID 0 or a Cartesian SRS, `ST_Distance()` returns distance in the coordinate system's units. For `(0,0)` and `(3,4)`, the planar distance is 5 units. If no physical unit was established, the result is simply 5 coordinate units, not 5 meters.

### 9.3. Area and Projections

For supported geographic SRSs, `ST_Area()` returns area in square meters; for Cartesian SRSs, it returns area in squared linear units of the system. A projected SRS may be convenient for measuring small regions, yet still introduces distortion depending on location and projection.

For cadastral reporting, urban planning, or legal surveying, select a dedicated projection suited to the region and accuracy requirements. Do not use Web Mercator merely because the application displays map tiles in Web Mercator.

## 10. Spatial Data Ingestion Pipeline

A reliable pipeline makes the SRS explicit at every boundary:

1. Identify the data source's SRS and datum rather than guessing from filenames or number pairs.
2. Determine the source axis order: longitude/latitude or latitude/longitude.
3. Validate coordinate ranges, geometry types, dimensions, and geometric validity.
4. Parse WKT/WKB with the proper source SRID and explicit `axis-order`.
5. If storing in a different SRS, use `ST_Transform()` and verify the resulting SRID.
6. Write to a geometry column with the appropriate SRID restriction.
7. Add spatial indexes for region queries when warranted by the workload.
8. Spot-check samples using WKT, SRID, and visual map inspection.
9. Record provenance: source, original SRID, target SRID, timestamp, and pipeline version.

Do not accept a geometry merely because it parses cleanly. The parser only checks format and basic rules; it does not know whether the point lies in the intended city or business region.

## 11. Schema Changes and SRID Migration

When an existing system stores SRID 0 data and needs to migrate to 4326, first determine what the legacy coordinates actually represent. If they were already longitude/latitude lacking SRID metadata, you can assign the proper metadata after verification. If they were projected coordinates, you must know the exact source SRS before transforming.

Safe migration workflow:

1. Pause or gate writers so no data continues arriving under the old convention during conversion.
2. Back up and sample existing geometries.
3. Confirm the source SRS, axes, and units from the producing system.
4. Partition data into groups with verified provenance; quarantine unknown records.
5. Generate new geometries via `ST_Transform()` when a coordinate system change is needed.
6. Verify coordinate bounds, validity, SRID, and sample locations.
7. Create a new column with the SRID restriction and backfill in batches.
8. Create the spatial index and verify plans with `EXPLAIN`.
9. Switch application reads/writes to the new column while monitoring discrepancies and latency.
10. Drop the old column only after the rollback window has safely passed.

Never bulk-run `ST_SRID(old_geom, 4326)` just to satisfy a column's SRID 4326 constraint. If the coordinates are not already WGS 84, that is relabeling, not transforming.

## 12. Common Pitfalls

| Symptom | Likely Cause | How to Handle |
|---|---|---|
| Points appear in the wrong country or ocean | Swapped latitude/longitude or wrong SRID assigned | Check source, `axis-order`, and SRS definition |
| Coordinates `106.7/10.8` rejected as out of range | Parser expects latitude/longitude order | Pass explicit `axis-order` if source is longitude/latitude |
| Distance returns tiny or huge values | Degrees treated as planar units or meters treated as degrees | Identify source SRS and use `ST_Transform` if needed |
| Spatial operation fails with SRID mismatch | Two geometries belong to different SRSs | Transform one side to a common SRID before comparing |
| `ST_Transform()` fails | Unsupported source/target SRID or transformation | Query SRS catalog and check definition/bounds |
| Spatial index not used | Column lacks SRID restriction, is nullable, or unsupported predicate | Inspect DDL, predicate, and `EXPLAIN` |
| MBR query returns extra points outside polygon | MBR is only the bounding rectangle | Combine with an exact predicate such as `ST_Contains()` |
| Legacy data has SRID 0 | Application constructed geometries without specifying SRID | Determine true SRS of coordinates before migrating |
| Some polygons rejected | Malformed WKT, unclosed ring, or invalid geometry | Validate WKT and `ST_IsValid()` |

## 13. Design Checklist

Before shipping a spatial column to production, verify:

- The SRS was selected based on an authoritative data source.
- Geographic vs. Cartesian fits the calculations required.
- The SRID and organization coordinate-system ID were verified in the catalog.
- Axis order is documented in the API contract.
- Distance/area units are clearly documented.
- The geometry column has an SRID restriction and `NOT NULL` where appropriate.
- Spatial indexes are created and confirmed via `EXPLAIN` on representative queries.
- MBR prefiltering is paired with exact predicates when needed.
- The pipeline validates geometry validity and coordinate bounds.
- Migrations distinguish SRID relabeling from coordinate transformation.
- Sample records are available for visual map verification.
- A rollback plan exists when changing SRIDs or projections.

## 14. Hands-On Practice

Run these in a lab schema on MySQL 8.0.13+:

1. Create a `POINT` without passing an SRID; inspect it with `ST_SRID()` and explain why it is SRID 0.
2. Query EPSG:4326 and EPSG:3857 in `INFORMATION_SCHEMA.ST_SPATIAL_REFERENCE_SYSTEMS`.
3. Create a WGS 84 `POINT` using `axis-order=long-lat` and read it back via `ST_AsText()` with the same axis order.
4. Create a point using default axis order; compare it with the `axis-order=long-lat` result.
5. Test a coordinate pair with swapped axes; observe the out-of-range error or wrong location.
6. Create a `LINESTRING` and `POLYGON` in SRID 4326; verify geometry type and validity.
7. Use `ST_SRID(g, 4326)` to tag a geometry whose coordinates are known to be WGS 84; explain why the coordinates do not change.
8. Use `ST_Transform()` to convert a 4326 point to 3857; compare SRID and coordinates before and after.
9. Test `ST_Distance()` between two 4326 points and interpret the result in meters.
10. Create a table with `POINT NOT NULL SRID 4326`; try inserting an SRID 0 geometry to observe the constraint.
11. Add a `SPATIAL INDEX` on the `POINT` column and verify DDL with `SHOW CREATE TABLE`.
12. Write an `MBRContains()` query for a rectangular region; read `EXPLAIN` and check spatial index usage.
13. Combine `ST_Contains()` as an exact filter after the MBR prefilter.
14. Create a complex polygon with a wide MBR; demonstrate why MBR filtering produces false positives.
15. Draft a migration plan for legacy SRID 0 data, distinguishing missing metadata from cases requiring true coordinate transformation.

## 15. Key Takeaways

- An SRS defines the coordinate system; an SRID identifies the SRS attached to a geometry.
- MySQL's SRID 0 is the default Cartesian system and does not inherently represent longitude/latitude.
- Cartesian uses planar geometry; geographic accounts for Earth's surface and uses appropriate geographic units.
- EPSG:4326 is geographic WGS 84; EPSG:3857 is projected Web Mercator.
- EPSG:4326 axes are defined as latitude/longitude; if your source sends longitude/latitude, pass `axis-order=long-lat` explicitly.
- `ST_SRID(g, srid)` only assigns the SRID label; it does not transform coordinates.
- `ST_Transform(g, srid)` transforms coordinates to the target SRS when the transformation is supported.
- Never compare geometries with different SRIDs as if they were in the same coordinate system.
- SRID restrictions prevent mixing coordinate systems inside a single column.
- InnoDB spatial indexes rely on R-tree/MBR; geometry columns need `NOT NULL` and an SRID restriction for optimizer usage as required in MySQL 8.0.
- MBR predicates filter by bounding rectangle; use exact geometric predicates when business rules require true shapes.
- Distances and areas must be interpreted according to SRS type and units.
- Choose a projection suited to your measurement goals; do not assume Web Mercator is accurate for measurements.
- Before migrating, verify the source SRS and separate metadata relabeling from coordinate transformation.
