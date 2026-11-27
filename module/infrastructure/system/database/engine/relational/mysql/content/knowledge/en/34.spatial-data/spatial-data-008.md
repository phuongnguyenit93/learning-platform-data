# Coordinate System Transformations, Validity Checks, and Version Limitations

Spatial data describes the location, shape, and geometric relationships of objects such as delivery points, routes, service zones, or administrative boundaries. In MySQL, these values are stored using geometry types such as `POINT`, `LINESTRING`, `POLYGON`, and `MULTI`/`GEOMETRYCOLLECTION` types.

A geometry value is more than raw coordinates. It is also bound to a Spatial Reference System (SRS), identified by an SRID. If two geometries use different coordinate systems, distance measurements or intersection checks may produce wrong results or be rejected by MySQL. Changing an SRID label is also not the same as transforming coordinates; you must clearly distinguish `ST_SRID()` from `ST_Transform()`.

Beyond coordinate systems, data must also be structurally valid. A `POLYGON` may contain valid numeric coordinates yet violate topology—for instance, a self-intersecting ring. MySQL provides validation functions such as `ST_IsValid()`, though checking validity does not automatically repair the geometry. Data ingestion pipelines must verify SRID, axis order, coordinate bounds, topology, and server version feature limits.

This lesson falls within `DATABASE_MYSQL`: understanding SRS/SRID, transforming coordinate systems, distinguishing SRID assignment from transformations, validating geometries, designing SRID-restricted columns and spatial indexes, and building safe migration workflows across MySQL versions.

## 1. Geometry, SRS, and SRID

A geometry represents a shape using coordinates. An SRS defines how those coordinates are interpreted on Earth or on a flat plane. An SRID (Spatial Reference System Identifier) identifies that SRS.

Examples:

- EPSG:4326 is WGS 84, a geographic coordinate system commonly used for longitude/latitude.
- EPSG:3857 is WGS 84 / Pseudo-Mercator, a planar coordinate system frequently seen in web maps.
- UTM systems have distinct SRIDs by zone and datum; they are generally better suited for local measurements within their target zone.

A geometry can contain identical numbers with completely different meanings depending on the SRID. `POINT(106.7 10.8)` can represent longitude/latitude under a geographic system and appropriate axis order; the same pair in a planar system can denote a position `106.7` units along X and `10.8` units along Y from the origin.

### 1.1. SRID 0

When no SRID is specified, many geometry constructors create a geometry with SRID 0. SRID 0 denotes the default Cartesian coordinate system unbound to any specific geographic reference system.

Example:

~~~sql
SET @g0 = ST_GeomFromText('POINT(106.7 10.8)');

SELECT ST_SRID(@g0) AS srid;
~~~

The resulting SRID is `0`. Do not assume these numbers are longitude/latitude or use them to compute geographic distances.

### 1.2. SRID Is Not a Unit of Measure

An SRID identifies the reference system and defines axis units and semantics per the SRS definition. Depending on the system:
- Geographic coordinates usually express angles, typically in degrees.
- Projected coordinates usually express distances, typically in meters.
- Some local coordinate systems use different units or datums.

Never compare measurements directly across two different SRSs. Transform to a common SRS before performing measurements or geometric relation checks.

## 2. Inspecting the SRS Catalog in MySQL

MySQL exposes SRS metadata in `INFORMATION_SCHEMA`.

~~~sql
SELECT
    SRS_ID,
    SRS_NAME,
    ORGANIZATION,
    ORGANIZATION_COORDSYS_ID,
    DEFINITION,
    DESCRIPTION
FROM information_schema.st_spatial_reference_systems
WHERE SRS_ID IN (0, 4326, 3857);
~~~

Commonly used fields:

| Field | Meaning |
|---|---|
| `SRS_ID` | SRID of the reference system |
| `SRS_NAME` | Reference system name |
| `ORGANIZATION` | Publishing organization, such as EPSG |
| `ORGANIZATION_COORDSYS_ID` | Coordinate system code within that organization |
| `DEFINITION` | SRS definition, typically in WKT format |
| `DESCRIPTION` | Description |

Check whether an SRID exists:

~~~sql
SELECT
    SRS_ID,
    SRS_NAME,
    ORGANIZATION,
    ORGANIZATION_COORDSYS_ID
FROM information_schema.st_spatial_reference_systems
WHERE SRS_ID = 4326;
~~~

If no row is returned, the server lacks that SRS definition in its current catalog. Do not assume every recent EPSG code is available across all MySQL versions.

### 2.1. Reading Axis Order from the SRS Definition

An SRS definition can specify explicit axis ordering. For some geographic systems, the official axis order differs from the longitude/latitude order commonly sent by mapping APIs.

This is a frequent source of bugs: data arrives as longitude-latitude while MySQL parses it as latitude-longitude, or vice versa. Always verify:
- The SRS in use.
- The axis order in the SRS definition.
- The axis order in the source file/API.
- The `axis-order` option when constructing geometries.

## 3. Axis Order: Latitude-Longitude or Longitude-Latitude?

Many formats and mapping libraries use longitude, latitude order. However, EPSG:4326 officially defines axis order as latitude followed by longitude. MySQL follows the SRS axis order in WKT operations unless an option explicitly overrides it.

Therefore, in MySQL distinguish:

- `axis-order=lat-long`: the first number is latitude, the second is longitude.
- `axis-order=long-lat`: the first number is longitude, the second is latitude.
- If omitted, MySQL uses the axis order defined in the SRS.

Example creating a point using longitude-latitude:

~~~sql
SET @hcm = ST_GeomFromText(
    'POINT(106.7009 10.7769)',
    4326,
    'axis-order=long-lat'
);

SELECT ST_SRID(@hcm) AS srid;
~~~

Example parsing WKT using EPSG:4326's default axis order:

~~~sql
SET @hcm_lat_long = ST_GeomFromText(
    'POINT(10.7769 106.7009)',
    4326
);
~~~

Both examples represent the exact same location when axis order is handled properly.

### 3.1. Why Can Swapped Axes Cause Serious Errors?

If longitude `106.7` is interpreted as latitude, the latitude exceeds the valid range `[-90, 90]`. MySQL raises an out-of-range error for geographic SRSs. When both numbers happen to fall within valid bounds, the point is silently stored at a completely wrong location, making the bug much harder to spot.

For instance, a point whose coordinates both lie inside `[-90,90]` can have its axes swapped without triggering any error. Therefore, numeric range checks alone are insufficient; verify locations on a map or against authoritative reference data.

### 3.2. Documenting the Axis Contract When Constructing Geometries from WKT

An ingestion convention should specify:
- Whether the API sends longitude first or latitude first.
- Whether the WKT constructor passes an `axis-order` option.
- Which SRID the column stores.
- How WKT/GeoJSON is exported for application reads.
- A test suite of known reference locations.

Do not infer MySQL's behavior from another library's defaults. Test both writes and reads.

## 4. Assigning an SRID vs. Transforming Coordinates

This is the most critical distinction when working with spatial data.

### 4.1. ST_SRID(): Assigning or Reading an SRID

Read form:

~~~sql
SELECT ST_SRID(@hcm) AS srid;
~~~

Assign SRID form:

~~~sql
SET @raw_point = ST_GeomFromText('POINT(106.7009 10.7769)');

SET @tagged_point = ST_SRID(@raw_point, 4326);
~~~

`ST_SRID(geometry, srid)` returns a geometry with its SRID set to the argument. It does not transform coordinate values.

If the initial geometry was `POINT(106.7009 10.7769)` in SRID 0, assigning SRID 4326 merely labels those numbers as belonging to SRS 4326. That is valid only if the source coordinates were already expressed in that system and in the right axis order.

Never use `ST_SRID` to convert data from UTM to WGS 84. That only changes metadata, not coordinates.

### 4.2. ST_Transform(): Transforming Coordinates Between SRSs

`ST_Transform(geometry, target_srid)` converts coordinates from the current SRS to the target SRS when MySQL has the required definitions and supported transformation.

Example converting a point from WGS 84 to Web Mercator:

~~~sql
SET @point_4326 = ST_GeomFromText(
    'POINT(106.7009 10.7769)',
    4326,
    'axis-order=long-lat'
);

SET @point_3857 = ST_Transform(@point_4326, 3857);

SELECT
    ST_SRID(@point_4326) AS source_srid,
    ST_SRID(@point_3857) AS target_srid,
    ST_AsText(@point_3857) AS projected_point;
~~~

The output coordinates are no longer longitude/latitude degrees; under EPSG:3857, the axes are projected planar coordinates. Never interpret the transformed values as degrees.

### 4.3. Comparison Table

| Operation | SRID | Coordinates | When to Use |
|---|---|---|---|
| `ST_SRID(g)` | Reads current SRID | Unchanged | Inspecting metadata |
| `ST_SRID(g, n)` | Assigns new SRID | Unchanged | Source coordinates already match target system/axis order, only missing/wrong SRID label after verification |
| `ST_Transform(g, n)` | Converts to target SRID | Recalculated | Truly converting data between two reference systems |

If you are unsure which SRS the source data belongs to, halt the migration and verify the source. No function can reliably deduce an SRS from an arbitrary pair of coordinates.

## 5. Transforming Existing Data Safely

Suppose a legacy table stored delivery points as SRID 0 geometries, even though the application actually wrote WGS 84 longitude/latitude coordinates.

Before converting:
1. Verify the actual coordinate system of the source data.
2. Verify the axis order.
3. Sample records and cross-check locations on a map.
4. Check longitude/latitude ranges.
5. Back up and test on staging.
6. Separate data already in the target SRID from data merely mislabeled with the wrong SRID.

If the data is genuinely WGS 84 longitude/latitude tagged with SRID 0, you can assign SRID 4326 after verification:

~~~sql
UPDATE delivery_location
SET position = ST_SRID(position, 4326)
WHERE ST_SRID(position) = 0;
~~~

This statement is appropriate only when stored coordinates already conform to the target SRS convention. It does not transform coordinates.

If the source data belongs to a projected system such as a specific UTM zone, assign the true source SRID first and then transform to the target SRID:

~~~sql
UPDATE delivery_location
SET position = ST_Transform(
    ST_SRID(position, 32648),
    4326
)
WHERE ST_SRID(position) = 0;
~~~

SRID 32648 here is merely an example for UTM zone 48N; use it only if the data truly belongs to that system. Never copy an example SRID into production without verifying datum, zone, and coverage.

### 5.1. Never Update an Entire Large Table Unmeasured

For large tables:
- Estimate the number of rows to convert.
- Process in batches by primary key.
- Monitor undo/redo, binlog volume, replication lag, and lock duration.
- Retain a backup or legacy geometry column for cross-checking during rollout.
- Verify sample points before and after using an independent GIS tool.
- Prepare a rollback or backup restore plan.

A single `UPDATE` transforming millions of geometries generates heavy write volume and can lag replicas. Deploy conversions as controlled data migrations.

## 6. Creating SRID-Restricted Spatial Columns

In MySQL 8.0, you can restrict a geometry column to a single SRID. This guarantees all values in the column share the same reference system.

Example store locations table:

~~~sql
CREATE TABLE store_location (
    store_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    store_name VARCHAR(150) NOT NULL,
    position POINT NOT NULL SRID 4326,
    PRIMARY KEY (store_id),
    SPATIAL INDEX sx_store_position (position)
) ENGINE = InnoDB;
~~~

The `position` column accepts only geometries with SRID 4326. Values with any other SRID are rejected instead of silently mixing coordinate systems inside the same column.

Insert data:

~~~sql
INSERT INTO store_location(store_name, position)
VALUES (
    'Central Store',
    ST_GeomFromText(
        'POINT(106.7009 10.7769)',
        4326,
        'axis-order=long-lat'
    )
);
~~~

Verify:

~~~sql
SELECT
    store_id,
    store_name,
    ST_SRID(position) AS srid,
    ST_AsText(position, 'axis-order=long-lat') AS position_wkt
FROM store_location;
~~~

An SRID-restricted column is ideal when every row in the column must follow one SRS. If an application must accept multiple coordinate systems, transform into a canonical SRS prior to writing or separate into columns/tables with explicit contracts.

### 6.1. Spatial Indexes and SRID Restrictions

InnoDB spatial indexes use R-trees to search by minimum bounding rectangle (MBR). In MySQL, for the optimizer to use a spatial index effectively, the column should be declared SRID-restricted and `NOT NULL`. Verify support requirements on your exact server version before deploying.

Do not treat a spatial index like a standard B-tree:
- R-trees accelerate bounding-box spatial lookups.
- Spatial indexes narrow down candidates.
- Exact geometric checks may still require a follow-up evaluation step.
- A geometry can have a large MBR even when its true shape is narrow or irregular.

## 7. Geographic vs. Projected Systems: Choosing Correctly for Queries

### 7.1. EPSG:4326

EPSG:4326 is widely used to store WGS 84 geographic locations. Coordinates represent angles, not meters. It is standard for global location storage.

However, distance and area calculations must respect geographic SRS semantics. Never subtract raw longitude/latitude coordinates and treat the difference as meters.

### 7.2. EPSG:3857

EPSG:3857 is widely used for web map tiles. It is convenient for rendering Web Mercator maps, yet area and distance distortion grows sharply at higher latitudes.

Do not treat EPSG:3857 as the default choice for accurate measurements. For local area/distance problems, choose an appropriate regional projected CRS or use MySQL's geographic measurement functions.

### 7.3. UTM and Local Projections

UTM divides the Earth into zones. Data confined to a specific region often fits its corresponding UTM zone for meter-based measurements. However, you must pick the exact:
- Zone.
- Hemisphere.
- Datum.
- EPSG/SRID.
- Valid area of use.

Do not apply a single UTM zone to datasets spanning multiple zones or global extents without evaluating distortion.

## 8. SRS Transformations and Potential Errors

`ST_Transform()` can fail when:
- The source SRID lacks an SRS definition.
- The target SRID does not exist.
- MySQL lacks a supported transformation path between the two SRSs.
- The geometry contains coordinates outside the valid domain.
- The geometry is invalid or unsupported by the transformation.
- The server version does not support `ST_Transform`.
- Input axes or units were misinterpreted.

Check SRIDs beforehand:

~~~sql
SELECT
    ST_SRID(position) AS srid,
    COUNT(*) AS row_count
FROM delivery_location
GROUP BY ST_SRID(position);
~~~

If a column contains multiple SRIDs, classify and process each group separately. Never transform the entire table assuming a single source SRID.

### 8.1. Do Not Transform from SRID 0 by Guessing

SRID 0 lacks a geographic definition telling MySQL which system the coordinates belong to. You cannot accurately convert from SRID 0 to 4326 merely by calling `ST_Transform`; you must determine the true source SRS first.

If you verify that the coordinates are genuinely WGS 84 longitude/latitude mistakenly tagged with SRID 0, you may assign label 4326 after verification. If the data belongs to another projection, assign the true source SRID first and then transform.

## 9. Checking Geometry Validity

A geometry may be stored in syntactically valid WKB/WKT yet violate geometric validity rules.

Examples:
- A `POLYGON` with an unclosed ring.
- A self-intersecting polygon ring.
- A hole (interior ring) lying outside the exterior ring.
- Rings or components with invalid topological relationships.
- A geometry collection containing components incompatible with the expected structure.

Distinguish four levels of validity:
- **Syntactic validity**: WKT/WKB data parses cleanly.
- **Coordinate validity**: coordinates lie within the SRS's valid domain.
- **Topological validity**: shape obeys geometric topology rules.
- **Business validity**: shape satisfies domain rules (e.g., delivery zone stays within authorized territory).

A polygon can be OGC-valid yet remain invalid under business rules.

### 9.1. ST_IsValid()

Use `ST_IsValid()` to test geometric validity:

~~~sql
SELECT
    area_id,
    ST_IsValid(service_area) AS is_valid
FROM service_area;
~~~

Results:
- `1`: geometry is valid under MySQL's validation rules.
- `0`: geometry is invalid.
- `NULL`: input is `NULL`.

The check does not repair the geometry. Never interpret `1` as proof that the data satisfies business rules or sits in the right geographic place; still check SRID, coordinate bounds, and containment.

### 9.2. Finding Invalid Geometries

~~~sql
SELECT area_id
FROM service_area
WHERE ST_IsValid(service_area) = 0;
~~~

You can also summarize counts:

~~~sql
SELECT
    COUNT(*) AS total_rows,
    SUM(ST_IsValid(service_area) = 1) AS valid_rows,
    SUM(ST_IsValid(service_area) = 0) AS invalid_rows
FROM service_area;
~~~

If the column is nullable, count `NULL` values separately. Never lump `NULL` into valid or invalid counts in quality reports.

### 9.3. Checking Before Writing

Example application submitting a polygon WKT:

~~~sql
SET @candidate = ST_GeomFromText(
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

SELECT
    ST_SRID(@candidate) AS srid,
    ST_IsValid(@candidate) AS is_valid;
~~~

If the candidate is valid and has the expected SRID, you can `INSERT` it into the SRID-restricted column. In application code, also catch parse/constructor errors because malformed geometries can be rejected before `ST_IsValid` is ever reached.

## 10. Checking Coordinate Bounds and Topology

For EPSG:4326 under the longitude-latitude convention:
- Longitude normally lies in `[-180, 180]`.
- Latitude normally lies in `[-90, 90]`.

However, MySQL may follow SRS axis order. Under latitude-longitude order, the first value's range is `[-90, 90]` and the second's is `[-180, 180]`. Never validate ranges purely by positional index without checking axis order.

### 10.1. Validating Points in Applications

For `POINT`:
- Verify SRID.
- Verify axis order.
- Verify value ranges.
- Cross-check sample locations against GPS/geocoder sources.
- Verify whether the point lies inside the expected service region.

You cannot catch all axis-swap bugs by range checks alone, because a number pair can satisfy valid bounds in both orders.

### 10.2. Validating Polygons

For `POLYGON`:
- Exterior ring must be closed.
- Rings must not self-intersect under validity rules.
- Holes must lie properly inside the exterior boundary.
- Holes must not overlap illegally.
- Polygon must stay within the business geographic scope.
- Geometry must not cross boundaries/antimeridian in ways the system does not handle.

`ST_IsValid` checks topology under geometry rules, but does not know whether a region covers the right district or service zone. Business rules must be checked separately.

## 11. Do Not Confuse ST_IsValid with Geometry Repair

`ST_IsValid()` returns a validation result. It does not automatically:
- Close a polygon ring missing its closing point.
- Fix self-intersections.
- Remove invalid holes.
- Swap coordinate order.
- Change SRID.
- Move a geometry into a valid region.

When data is invalid:
1. Preserve the original record for traceability.
2. Determine whether the error is syntactic, coordinate-based, or topological.
3. Choose an appropriate, controlled geometry repair tool.
4. Store the repaired geometry in staging.
5. Check `ST_IsValid` and visually compare shapes.
6. Verify SRID and location.
7. Replace production data only after sign-off.

You can use dedicated GIS libraries in the ETL or application layer to repair geometries, provided you log the algorithm, version, and shape changes. Never silently alter polygons in ways that could shift legal boundaries or business territories.

## 12. Measurements and Geometric Relations Require a Common SRS

Spatial operations generally require both geometries to have the same SRID. If two geometries differ in SRID, MySQL raises an SRS mismatch error.

Example:

~~~sql
SELECT ST_Distance(point_a, point_b)
FROM route_test;
~~~

Check SRIDs beforehand:

~~~sql
SELECT
    ST_SRID(point_a),
    ST_SRID(point_b)
FROM route_test;
~~~

If SRIDs differ, transform one geometry to a suitable common SRS before computing:

~~~sql
SELECT ST_Distance(
    ST_Transform(point_a, 4326),
    point_b
)
FROM route_test;
~~~

This example is valid only if transforming from `point_a`'s SRID to `4326` is supported and `point_b` is genuinely `4326`.

### 12.1. Distance Units

Measurement units depend on the SRS and function used. Under a Cartesian SRS, `ST_Distance` returns distance in coordinate units. Under a geographic SRS, MySQL applies SRS-aware measurement semantics, typically meters for supported angular geographic systems.

Never take `ST_Distance` on degree coordinates and assume the output is meters. Read the function and SRS documentation carefully, especially when measuring areas or distances over wide regions.

### 12.2. ST_Distance_Sphere

For two geographic points, you can use `ST_Distance_Sphere` to calculate spherical distance in meters:

~~~sql
SELECT ST_Distance_Sphere(
    ST_GeomFromText(
        'POINT(106.7009 10.7769)',
        4326,
        'axis-order=long-lat'
    ),
    ST_GeomFromText(
        'POINT(106.6800 10.8000)',
        4326,
        'axis-order=long-lat'
    )
) AS distance_meters;
~~~

This is an approximate distance on a sphere, not an exact geodetic measurement on an ellipsoid. Use it where spherical approximation is acceptable; when high measurement accuracy is required, select an appropriate method and SRS.

## 13. Spatial Indexes and Region Queries

Spatial indexes in InnoDB use R-trees over each geometry's MBR (minimum bounding rectangle). The MBR is the smallest rectangle enclosing a geometry. It narrows candidates effectively yet can include space outside the true shape.

Example:

~~~sql
CREATE TABLE service_area (
    area_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    area_name VARCHAR(120) NOT NULL,
    boundary POLYGON NOT NULL SRID 4326,
    PRIMARY KEY (area_id),
    SPATIAL INDEX sx_service_area_boundary (boundary)
) ENGINE = InnoDB;
~~~

Create a point to test:

~~~sql
SET @customer_point = ST_GeomFromText(
    'POINT(106.7009 10.7769)',
    4326,
    'axis-order=long-lat'
);
~~~

Find zones whose MBR contains the point:

~~~sql
SELECT area_id, area_name
FROM service_area
WHERE MBRContains(boundary, @customer_point);
~~~

`MBRContains` checks only the bounding rectangle. For concave polygons or polygons with holes, a point can lie inside the MBR yet outside the true polygon.

For exact evaluation, use an exact geometric predicate:

~~~sql
SELECT area_id, area_name
FROM service_area
WHERE ST_Contains(boundary, @customer_point);
~~~

You can combine MBR prefiltering and an exact predicate:

~~~sql
SELECT area_id, area_name
FROM service_area
WHERE MBRContains(boundary, @customer_point)
  AND ST_Contains(boundary, @customer_point);
~~~

The optimizer can leverage the spatial index for supported query patterns. Verify with `EXPLAIN` on your actual version. MBR conditions do not replace exact checks.

### 13.1. Inspecting the Execution Plan

~~~sql
EXPLAIN
SELECT area_id, area_name
FROM service_area
WHERE ST_Contains(boundary, @customer_point);
~~~

Check:
- `possible_keys` and `key`.
- Access `type`.
- Estimated `rows`.
- `Extra`.
- Whether the optimizer uses the spatial index or falls back to a table scan.

If the index is not used:
- Verify the column has an SRID restriction and `NOT NULL`.
- Verify both geometries share the same SRID.
- Check whether the predicate is supported for spatial range scans.
- Verify the table is large enough for the index to be beneficial.
- Update table statistics if needed.
- Try an appropriate MBR predicate paired with an exact predicate for confirmation.

## 14. SRID Restrictions and Schema Migrations

When adding an SRID restriction to an existing table, existing rows must satisfy the constraint. If the table contains mixed SRIDs or `NULL`s, altering the column will fail.

Before running `ALTER`:
~~~sql
SELECT
    ST_SRID(position) AS srid,
    COUNT(*) AS rows_per_srid
FROM store_location_legacy
GROUP BY ST_SRID(position);
~~~

Check for `NULL`:
~~~sql
SELECT COUNT(*) AS null_positions
FROM store_location_legacy
WHERE position IS NULL;
~~~

After auditing the data:
- Normalize all rows to the target SRS.
- Repair or quarantine invalid records per business rules.
- Create a new SRID-restricted column if performing a phased online migration.
- Verify indexes and query plans after migration.

Never force an SRID restriction before understanding legacy data. A table containing mixed SRIDs may hide an upstream design bug that must be resolved first.

## 15. Checking Compatibility Across MySQL Versions

Spatial capabilities have evolved substantially across MySQL releases.

| Feature Group | Version Notes |
|---|---|
| Core geometry types and spatial functions | Present since older MySQL releases; function set and engine support expanded over time |
| InnoDB spatial indexes | Supported since MySQL 5.7 releases; verify engine/column requirements per exact release |
| SRS metadata and geographic SRS-aware behavior | Part of modern MySQL 8.0 capabilities; differs from older Cartesian/SRID 0 behavior |
| SRID-restricted columns | Check exact 8.0 minor version and DDL syntax before deploying |
| `ST_Transform()` | Available starting in MySQL 8.0.13 |
| Spatial index optimization with SRID-restricted columns | Optimizer usage depends on version and column/predicate conditions |
| `CHECK` constraint enforcement | Enforced starting in MySQL 8.0.16; earlier versions differed on enforcement |
| Additional GIS functions and bug fixes | Can vary across 8.0 minor releases and newer branches |

Check the server:

~~~sql
SELECT VERSION();
~~~

Inspect engine and columns:

~~~sql
SHOW CREATE TABLE store_location;
SHOW INDEX FROM store_location;
~~~

Verify SRS availability:

~~~sql
SELECT SRS_ID, SRS_NAME
FROM information_schema.st_spatial_reference_systems
WHERE SRS_ID IN (4326, 3857);
~~~

Do not rely on MySQL 8.4 syntax to assume MySQL 5.7 or a MySQL-compatible service behaves identically. Always consult documentation for the exact deployed version and test migrations on staging.

### 15.1. ST_Transform and Legacy Datasets

If your environment runs a version lacking `ST_Transform`, you cannot substitute `ST_SRID` to achieve the same result. Instead, you can:
- Perform transformations in ETL/application code using a CRS-capable GIS library.
- Stage the transformed data in a staging table.
- Validate SRID, axis order, and validity.
- Import transformed geometries into MySQL.
- Verify sample locations and row counts.

Never write ad-hoc manual transformation formulas for arbitrary coordinate systems. Transformations may involve datum shifts, grid shifts, or projection math that simple scaling cannot replace.

## 16. Pre- and Post-Conversion Quality Control

A spatial migration report should include:

| Check | Before Conversion | After Conversion |
|---|---|---|
| Total row count | Record | Compare |
| `NULL` row count | Record | Per contract |
| SRID distribution | Record | Only target SRID if required |
| Valid geometries | Count `ST_IsValid` | Recount |
| Out-of-range coordinates | Count | Recount |
| Verified sample points | Save baseline | Compare locations |
| Sample polygons | Save baseline | Compare area/bounds |
| Spatial indexes | Old definition | Confirm created |
| `EXPLAIN` | Save plans | Confirm access paths |
| Replication lag | Baseline | Monitor during migration |

For points, compare distances before and after bringing both geometries into a common SRS. For polygons, compare area, envelope, component count, and inspect topology with an appropriate GIS tool.

Never rely solely on WKT text comparison, as identical shapes can serialize with different ring/vertex ordering.

## 17. Common Mistakes

| Mistake or Misconception | Cause | How to Handle |
|---|---|---|
| `ST_SRID(g, 4326)` converts coordinates to WGS 84 | The function only changes the SRID, leaving coordinates untouched | Use `ST_Transform` once the source SRS is known |
| SRID 0 is automatically longitude/latitude | SRID 0 is the default Cartesian system | Verify the source SRS before labeling |
| EPSG:4326 always puts longitude first in MySQL | MySQL follows SRS axis order unless overridden | Pass `axis-order` explicitly |
| Equal coordinate numbers mean the same location | SRID and axis order may differ | Compare after converting to a common SRS |
| `ST_Transform` works for every SRID | Requires supported SRSs and transformation path | Check SRS catalog and server version |
| Degree distances convert to meters via one constant | Longitude scale varies with latitude and geodetic math | Use appropriate measurement functions/SRSs |
| EPSG:3857 works for all measurements | Web Mercator distorts distances and areas | Use a local projected CRS or geographic calculations |
| `ST_IsValid` repairs polygons | It only checks validity | Repair via a controlled GIS pipeline |
| Parseable geometry guarantees valid geometry | Syntax and topology are separate | Run `ST_IsValid` and business validation |
| `MBRContains` is an exact polygon check | MBR is only the bounding rectangle | Pair with an exact predicate like `ST_Contains` |
| Spatial indexes work on every geometry column | SRID restriction, `NOT NULL`, and predicates affect optimizer | Inspect DDL and `EXPLAIN` |
| Mixing SRIDs in one column still allows comparisons | Spatial operations raise SRS mismatch errors | Normalize SRIDs or separate schemas |
| Transforming an entire table carries no operational risk | Can cause write amplification and replication lag | Batch, stage, back up, and monitor |
| MySQL 5.7 supports all 8.0 GIS features | Features vary across versions | Check `VERSION()` and the matching manual |
| Spatial DDL changes can be rolled back in a transaction | DDL causes implicit commits | Plan standalone migrations |

## 18. Safe Spatial Data Handling Workflow

1. Identify the geometry type and business meaning of every column.
2. Determine the true SRS of source data, not just the currently stored SRID.
3. Determine both source axis order and MySQL axis order.
4. Verify the SRID exists in `INFORMATION_SCHEMA.ST_SPATIAL_REFERENCE_SYSTEMS`.
5. Audit the current SRID distribution.
6. Check for `NULL`s, out-of-range coordinates, and `ST_IsValid`.
7. Choose the target SRS suited for storage, display, or measurement.
8. If only the SRID label is missing and coordinates already match, use `ST_SRID` after verification.
9. If the coordinate system genuinely differs, use `ST_Transform` or a GIS ETL step.
10. Never use SRID 0 as a transformation source without knowing its true coordinate system.
11. Create SRID-restricted, `NOT NULL` columns when the model requires a single SRS.
12. Create spatial indexes on qualifying columns.
13. Verify both MBR predicates and exact spatial predicates.
14. Run `EXPLAIN` and benchmark on representative datasets.
15. Migrate via batches/staging while monitoring binlogs, replica lag, and locks.
16. Cross-check sample points/polygons using an independent source.
17. Record MySQL version, SRID, axis order, pipeline details, and migration timestamps.
18. Switch application reads to the new column only after quality checks pass.

## 19. Hands-On Exercises

### Exercise 1: Reading SRID

Create a `POINT` geometry without specifying an SRID. Inspect it with `ST_SRID`. Explain how SRID 0 differs from EPSG:4326.

### Exercise 2: Axis Order

Create a point in Ho Chi Minh City using longitude-latitude WKT with `axis-order=long-lat`. Create an equivalent point using EPSG:4326's default axis order. Compare positions after exporting WKT.

### Exercise 3: Assigning SRID vs. Transforming

Create an SRID 0 geometry with known WGS 84 coordinates. Assign label `4326` with `ST_SRID`. Then transform it to `3857`. Compare coordinates before and after and explain why the two operations differ.

### Exercise 4: SRS Catalog

Query `INFORMATION_SCHEMA.ST_SPATIAL_REFERENCE_SYSTEMS` for `4326` and `3857`. Inspect `ORGANIZATION`, `SRS_NAME`, and `DEFINITION`. Identify each SRS's axis order.

### Exercise 5: SRID-Restricted Column

Create a table with `POINT NOT NULL SRID 4326` and a spatial index. Try inserting an SRID 0 geometry and another SRID. Record the errors.

### Exercise 6: Geometry Validity

Create one valid `POLYGON` and one self-intersecting polygon. Use `ST_IsValid` to check both. Distinguish parse errors from topology errors.

### Exercise 7: Spatial Index

Create a service-zone table with `POLYGON SRID 4326`. Run `MBRContains` and `ST_Contains`. Compare results for a point lying inside the MBR yet outside a concave polygon.

### Exercise 8: SRS Mismatch

Create two geometries with different SRIDs and test `ST_Distance`/`ST_Intersects`. Record the error. Transform one geometry to the common SRS and rerun.

### Exercise 9: Migration Audit

Create a legacy table containing multiple SRIDs or SRID 0. Write queries summarizing SRID distribution and validity. Plan a migration to a standard SRID without overwriting raw source data.

### Exercise 10: Distance Measurement

Compute `ST_Distance` on Cartesian geometries and `ST_Distance_Sphere` on two geographic points. Compare units and spherical approximation error.

### Exercise 11: Version Compatibility

Check `VERSION()` on your lab server. Verify whether `ST_Transform`, SRID-restricted columns, and spatial index optimization are supported. Design a compatible migration using external ETL if targeting older servers.

### Exercise 12: Spatial Quality Report

Produce a report covering total rows, SRID distribution, `NULL`s, invalid geometries, out-of-range coordinates, index definitions, `EXPLAIN`, and sample control points. Propose acceptance criteria for migration sign-off.

## 20. Pre-Deployment Checklist

- [ ] Identified the true SRS of the data rather than inferring solely from stored SRIDs.
- [ ] Distinguished SRID 0 from defined geographic systems.
- [ ] Checked SRS definitions in `INFORMATION_SCHEMA.ST_SPATIAL_REFERENCE_SYSTEMS`.
- [ ] Identified both source axis order and MySQL axis order.
- [ ] Used explicit `axis-order` whenever WKT/API order differs from SRS order.
- [ ] Distinguished `ST_SRID` from `ST_Transform`.
- [ ] Avoided using `ST_SRID` as a substitute for coordinate transformation.
- [ ] Verified coordinate bounds and measurement units.
- [ ] Checked `ST_IsValid` and domain validation rules.
- [ ] Established a controlled repair workflow while preserving originals.
- [ ] Standardized SRIDs before running two-geometry spatial operations.
- [ ] Selected SRSs suited for display vs. measurement.
- [ ] Accounted for EPSG:3857 distortion and avoided defaulting to it for accurate measurements.
- [ ] Declared SRID restrictions and `NOT NULL` where required.
- [ ] Created spatial indexes and verified them via `EXPLAIN`.
- [ ] Distinguished MBR predicates from exact spatial predicates.
- [ ] Checked DDL behavior and version limitations.
- [ ] Tested migrations on staging with backups ready.
- [ ] Monitored write amplification, locks, and replication lag.
- [ ] Cross-checked sample locations/shapes with an independent GIS tool.
- [ ] Documented MySQL version, SRID, axis order, and conversion procedures.

## 21. Conclusion

A geometry is meaningful only when its coordinates, SRID, SRS, and axis order are consistently understood. `ST_SRID()` reads or assigns the SRID label without changing coordinates; `ST_Transform()` performs actual coordinate transformations when MySQL supports both source and target SRSs. Especially with EPSG:4326, specify latitude-longitude vs. longitude-latitude explicitly to prevent swapped axes.

Checking `ST_IsValid()` catches topologically invalid geometries, though it neither repairs data nor replaces business validation. R-tree spatial indexes accelerate MBR candidate lookups; exact predicates such as `ST_Contains` remain necessary for complex shapes. SRID-restricted, `NOT NULL` columns and spatial indexes improve consistency and enable the optimizer to use the index.

Before migrating, profile SRIDs, verify sources, check validity, test transformations on staging, cross-check sample locations, and measure operational impact. GIS capabilities evolve across releases; always verify `VERSION()`, SRS metadata, and documentation for your exact deployed MySQL release.

## Official References

- [MySQL 8.4 Reference Manual – Spatial Data Types](https://dev.mysql.com/doc/refman/8.4/en/spatial-types.html)
- [MySQL 8.4 Reference Manual – Spatial Reference System Support](https://dev.mysql.com/doc/refman/8.4/en/spatial-reference-systems.html)
- [MySQL 8.4 Reference Manual – Spatial Reference System Functions](https://dev.mysql.com/doc/refman/8.4/en/spatial-relation-functions.html)
- [MySQL 8.4 Reference Manual – Geometry Constructors](https://dev.mysql.com/doc/refman/8.4/en/gis-geometry-construction-functions.html)
- [MySQL 8.4 Reference Manual – Geometry Property Functions](https://dev.mysql.com/doc/refman/8.4/en/gis-general-property-functions.html)
- [MySQL 8.4 Reference Manual – Spatial Convenience Functions](https://dev.mysql.com/doc/refman/8.4/en/spatial-convenience-functions.html)
- [MySQL 8.4 Reference Manual – Spatial Relation Functions](https://dev.mysql.com/doc/refman/8.4/en/spatial-relation-functions.html)
- [MySQL 8.4 Reference Manual – Spatial Index Optimization](https://dev.mysql.com/doc/refman/8.4/en/optimizing-spatial-analysis.html)
- [MySQL 8.4 Reference Manual – INFORMATION_SCHEMA ST_SPATIAL_REFERENCE_SYSTEMS](https://dev.mysql.com/doc/refman/8.4/en/information-schema-st-spatial-reference-systems-table.html)
- [MySQL 8.4 Reference Manual – InnoDB Spatial Indexes](https://dev.mysql.com/doc/refman/8.4/en/innodb-spatial-indexes.html)
- [MySQL 8.4 Reference Manual – EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html)
