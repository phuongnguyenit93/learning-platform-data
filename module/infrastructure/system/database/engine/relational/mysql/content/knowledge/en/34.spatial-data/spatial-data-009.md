# Designing Location Queries with Boundary Data and Error Verification

This lesson belongs to the **Spatial Data** chapter of the **DATABASE_MYSQL** module. The module aims at mastering MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query optimization, authorization, backup, and relational database operational troubleshooting. Location queries often have to answer seemingly simple questions: does a point belong to a service zone, which zone owns a point lying exactly on a boundary line, do two regions touch, or how many meters is a location from a border? Wrong results typically stem from mixing up longitude/latitude order, assigning the wrong SRID, substituting MBRs for true shapes, or comparing coordinates with inappropriate precision.

After this lesson, you will be able to select the right geometry type and SRID, construct points and polygons with intentional coordinate axes, distinguish strict interior containment from boundary-inclusive semantics, use MBRs for candidate filtering followed by exact geometric predicates, detect invalid geometries, measure distances in meters, define domain-meaningful tolerances, and use `EXPLAIN` to confirm spatial index usage.

## 1. Spatial Data Model in MySQL

MySQL supports these primary geometry types:

| Type | Representation | Business Example |
|---|---|---|
| `GEOMETRY` | Generic base type | Single column holding multiple geometry types |
| `POINT` | Single coordinate | Store, device, or customer location |
| `LINESTRING` | Path composed of multiple points | Road route, linear boundary |
| `POLYGON` | Region with an exterior ring and optional holes | Delivery zone, district, exclusion zone |
| `MULTIPOINT` | Multiple points | Monitoring stations |
| `MULTILINESTRING` | Multiple paths | Route network |
| `MULTIPOLYGON` | Multiple polygons | Territory composed of disconnected regions |
| `GEOMETRYCOLLECTION` | Collection of geometries | Mixed dataset |

Spatial data is stored in geometry-typed columns. Do not store longitude and latitude solely in two numeric columns if the domain requires geometric operations, region predicates, distance calculations, or spatial indexes.

Example places table:

~~~sql
CREATE TABLE places (
    place_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    place_name VARCHAR(150) NOT NULL,
    location POINT NOT NULL SRID 4326
) ENGINE=InnoDB;
~~~

The `location` column stores a `POINT` in the SRID 4326 geographic reference system. Declaring the SRID directly in the column definition restricts stored values to that exact reference system.

### Geometry vs. Geography in Coordinate Interpretation

MySQL uses the same geometry type family, while calculation behavior depends on the spatial reference system (SRS):

- Cartesian SRS: X/Y coordinates lie on a flat plane; units depend on the SRS.
- Geographic SRS: coordinates represent locations on Earth; geographic distance is computed using an ellipsoidal or spherical model depending on the function.

SRID 0 is a special Cartesian plane with no defined axis unit. Never take an SRID 0 distance result and call it meters without an explicit unit convention.

SRID 4326 is WGS 84, commonly used with GPS data. Coordinates are expressed as angles, not meters.

## 2. SRID and Longitude/Latitude Axis Order

A common data error is passing latitude and longitude in the wrong order.

In the common mapping application convention:

- X is longitude.
- Y is latitude.

For example, a point in Ho Chi Minh City might have longitude around `106.7` and latitude around `10.78`.

However, MySQL's EPSG:4326 definition specifies a default axis order of latitude first, longitude second. Geometry constructors parsing WKT follow the SRS-defined axis order by default.

Therefore, if WKT is supplied using the familiar longitude/latitude convention, state it explicitly:

~~~sql
SET @p = ST_GeomFromText(
    'POINT(106.7000 10.7800)',
    4326,
    'axis-order=long-lat'
);
~~~

The `axis-order=long-lat` option makes it explicit that WKT coordinates are supplied as longitude followed by latitude.

When using the default SRID-defined order, coordinate order must follow the SRS axis definition:

~~~sql
SET @p = ST_GeomFromText(
    'POINT(10.7800 106.7000)',
    4326
);
~~~

Both expressions describe the same location when axis order is declared properly. Never mix both conventions in the same ingestion pipeline.

### Inspecting Coordinates After Constructing a Geometry

~~~sql
SELECT
    ST_SRID(@p) AS srid,
    ST_Longitude(@p) AS longitude,
    ST_Latitude(@p) AS latitude,
    ST_AsText(@p, 'axis-order=long-lat') AS wkt_long_lat;
~~~

For geographic SRSs, MySQL checks coordinate ranges:

- Longitude lies in `(-180, 180]`.
- Latitude lies in `[-90, 90]`.

If coordinates exceed those bounds, spatial functions raise a longitude/latitude out-of-range error.

Do not check only whether numbers fall inside valid ranges. A swapped coordinate pair can still be numerically valid while pointing to an entirely different place.

### ST_SRID() Does Not Transform Coordinates

These two operations differ:

- `ST_SRID(geom, srid)`: changes the SRID attached to the geometry without transforming coordinate values.
- `ST_Transform(geom, target_srid)`: transforms coordinates from the source SRS to the target SRS.

Never use `ST_SRID()` to patch data when coordinates actually belong to another reference system. Assigning the wrong SRID label silently corrupts downstream calculations without necessarily throwing an immediate error.

## 3. Constructing Regions and Points with WKT

WKT (Well-Known Text) is a textual representation of geometries. Examples:

~~~sql
SET @point = ST_GeomFromText(
    'POINT(106.7000 10.7800)',
    4326,
    'axis-order=long-lat'
);

SET @zone = ST_GeomFromText(
    'POLYGON((
        106.6800 10.7600,
        106.7200 10.7600,
        106.7200 10.8000,
        106.6800 10.8000,
        106.6800 10.7600
    ))',
    4326,
    'axis-order=long-lat'
);
~~~

A polygon has an exterior ring. Its first and last points must match to close the ring.

A polygon may also have interior rings representing holes. Points inside a hole do not belong to the polygon's area.

### Well-Formedness vs. Validity

MySQL distinguishes two concepts:

- Syntactically well-formed: data obeys valid WKT/WKB structure—for example, a polygon has rings, rings are closed, and each ring has at least four coordinates including the repeated closing point.
- Geometrically valid: the shape obeys topological rules—for example, a polygon does not self-intersect, interior rings lie inside the exterior ring, and polygons in a `MultiPolygon` do not overlap.

A polygon can be well-formed yet geometrically invalid. MySQL does not run full geometric validity checks on every write due to computational cost. Invalid geometries can cause spatial computations to return undefined results or raise errors.

Verify:

~~~sql
SELECT
    ST_IsValid(@zone) AS is_valid,
    ST_GeometryType(@zone) AS geometry_type,
    ST_SRID(@zone) AS srid;
~~~

You can use `ST_Validate()` to return the geometry if valid; it returns `NULL` if the geometry is invalid or not well-formed.

~~~sql
SELECT ST_Validate(@zone);
~~~

In boundary ingestion workflows, validate geometries before writing to main tables. Record the data source and polygon version so changes can be reconciled when boundaries evolve.

## 4. Does the Boundary Count as Inside the Region?

This is a business decision that must be settled before writing queries.

Suppose a polygon is a service zone and a point is a delivery address. The point may lie:

1. Strictly inside the region.
2. Exactly on the boundary line.
3. Outside the region.

Geometric predicates have different semantics.

| Predicate | Point Inside | Point on Boundary | Point Outside |
|---|---:|---:|---:|
| `ST_Contains(polygon, point)` | 1 | 0 | 0 |
| `ST_Within(point, polygon)` | 1 | 0 | 0 |
| `ST_Intersects(polygon, point)` | 1 | 1 | 0 |
| `ST_Disjoint(polygon, point)` | 0 | 0 | 1 |
| `ST_Touches(polygon, point)` | 0 | 1 | 0 |

### ST_Contains: Interior Only

~~~sql
SELECT ST_Contains(@zone, @point);
~~~

`ST_Contains` returns `1` when the first geometry contains the second and their interiors intersect under contains rules. For a point lying strictly on a polygon edge, the result is `0`.

Use `ST_Contains` when rules require the point to lie strictly inside the region—for instance, equipment must sit inside a licensed zone while points exactly on the border are handled separately.

### ST_Within: Inverse Relationship

~~~sql
SELECT ST_Within(@point, @zone);
~~~

`ST_Within(point, polygon)` checks the inverse of `ST_Contains(polygon, point)`. Points strictly on the boundary are likewise not considered within.

### ST_Intersects: Includes Boundary Points

~~~sql
SELECT ST_Intersects(@zone, @point);
~~~

`ST_Intersects` returns `1` if two geometries share at least one point. For a point and a polygon, a point inside the zone or directly on the boundary intersects the polygon.

Use this predicate if policy states that the boundary belongs to the zone—for example, a delivery zone includes addresses sitting right on the border street.

### ST_Touches: Detecting Boundary Contact

~~~sql
SELECT ST_Touches(@zone, @point);
~~~

`ST_Touches` returns `1` when two geometries' interiors do not intersect while the boundary of one intersects the boundary or interior of the other. For a point lying strictly on a polygon boundary, this distinguishes boundary contact from being strictly inside.

Never substitute `ST_Touches` for `ST_Intersects` when you need all points inside or on the region.

### Define Policy Before Implementation

Examples:

- Service zones: count boundary points as inside the zone.
- Restricted zones: boundary points also count as inside the restricted zone.
- Administrative partitioning: two adjacent polygons share a boundary line; define a deterministic tie-breaking rule assigning boundary points to a single unit if non-overlapping assignment is required.
- Toll/pricing zones: specify handling for near-boundary points because GPS jitter can cause a device to oscillate between two zones.

No single predicate fits every business rule. Choose semantics explicitly and test with interior, boundary, and exterior points.

## 5. MBR and Exact Shape Are Two Distinct Checks

The MBR (Minimum Bounding Rectangle) is the smallest axis-aligned rectangle enclosing a geometry.

For example, a concave polygon can have a rectangular MBR much larger than its actual area. A point can lie inside the MBR while sitting outside the true polygon.

Function groups:

- `ST_Contains()`, `ST_Intersects()`, `ST_Touches()`: evaluate relationships between true shapes.
- `MBRContains()`, `MBRIntersects()`, `MBRWithin()`, `MBRCovers()`: evaluate relationships between enclosing rectangles.

C-shaped polygon example:

~~~sql
SET @concave = ST_GeomFromText(
    'POLYGON((
        0 0,
        4 0,
        4 1,
        1 1,
        1 3,
        4 3,
        4 4,
        0 4,
        0 0
    ))'
);

SET @point_in_notch = ST_GeomFromText('POINT(3 2)');

SELECT
    MBRIntersects(@concave, @point_in_notch) AS mbr_match,
    ST_Intersects(@concave, @point_in_notch) AS exact_match;
~~~

Point `(3, 2)` lies inside the enclosing rectangle yet in the concave notch outside the polygon. `MBRIntersects` returns `1` while `ST_Intersects` returns `0`.

This is an MBR false positive. It is expected behavior when MBR is used solely as a candidate filter.

### Contains vs. Covers at the MBR Level

For MBRs:

- `MBRContains` requires the second geometry's MBR to lie in the interior of the first MBR; points strictly on the MBR edge are not contained.
- `MBRCovers` includes points lying on the MBR boundary.
- `MBRIntersects` matches whenever two MBRs share any point.

Do not confuse `MBRCovers` with the true polygon covering a point. `MBRCovers` only states that the enclosing rectangle covers it; true shape still requires an `ST_*` predicate for confirmation.

## 6. Two-Step Querying: Filter Candidates, Then Verify Geometry

On tables with many regions, exact checks may otherwise scan many polygons. A spatial index shrinks the candidate set via MBRs.

Boundary-inclusive pattern:

~~~sql
SELECT zone_id, zone_name
FROM service_zones
WHERE MBRIntersects(@point, geom)
  AND ST_Intersects(geom, @point);
~~~

The two conditions serve distinct roles:

1. `MBRIntersects` filters polygons whose bounding rectangles intersect the point's bounding rectangle. This step can leverage the R-tree spatial index when the optimizer picks an index plan.
2. `ST_Intersects` verifies whether the point truly lies inside or touches the polygon shape.

For strict interior-only rules:

~~~sql
SELECT zone_id, zone_name
FROM service_zones
WHERE MBRWithin(@point, geom)
  AND ST_Contains(geom, @point);
~~~

`MBRWithin` is the bounding-rectangle filter. `ST_Contains` is the final check against the true shape.

### Why Not Use MBR Alone?

Using `MBRIntersects` alone returns points sitting inside the concave notch or interior hole of a polygon.

Using `MBRContains` alone does not guarantee a point inside the MBR lies inside the true polygon.

### Why Not Use Exact Predicates Alone?

`ST_Intersects` or `ST_Contains` expresses exact business logic, yet without an indexable prefilter the engine may have to evaluate geometries across many rows.

The spatial index reduces candidates; the exact predicate guarantees correctness.

Never drop the exact predicate just to make a query faster.

## 7. Spatial Indexes and Optimizer Usage Conditions

MySQL builds spatial indexes using R-trees. InnoDB and MyISAM support spatial indexes.

The indexed column must:

- Have a geometry type.
- Be declared `NOT NULL`.
- Specify a fixed SRID in its column definition to become SRID-restricted.
- Each spatial index covers only a single spatial column.

Example:

~~~sql
CREATE TABLE service_zones (
    zone_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    zone_name VARCHAR(150) NOT NULL,
    geom POLYGON NOT NULL SRID 4326,
    SPATIAL INDEX sx_service_zones_geom (geom)
) ENGINE=InnoDB;
~~~

Without an SRID restriction:

~~~sql
CREATE TABLE zones_without_srid (
    zone_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    geom POLYGON NOT NULL,
    SPATIAL INDEX sx_geom (geom)
) ENGINE=InnoDB;
~~~

In MySQL 9.7, the optimizer uses spatial indexes only for SRID-restricted columns. A spatial index on a column lacking an `SRID` attribute may still be maintained on writes, but the optimizer ignores it.

### How MySQL 9.7 Handles Geographic Indexes by SRS

The optimizer inspects the column's SRID to select bounding-box math matching the SRS:

- Cartesian SRID: uses Cartesian bounding boxes.
- Geographic SRID: uses geographic bounding boxes.

Prior to MySQL 9.7, spatial index comparisons used Cartesian calculations; behavior with non-Cartesian geographic SRIDs was undefined. When upgrading from older releases, verify that schemas carry the `SRID` attribute and stored data uses a single uniform SRID.

Check existing SRIDs:

~~~sql
SELECT DISTINCT ST_SRID(geom)
FROM service_zones;
~~~

If multiple SRIDs exist, normalize the data before converting the column to SRID-restricted.

### Inspecting with EXPLAIN

~~~sql
EXPLAIN
SELECT zone_id, zone_name
FROM service_zones
WHERE MBRIntersects(@point, geom)
  AND ST_Intersects(geom, @point);
~~~

Observe:

| Column | What to Check |
|---|---|
| `possible_keys` | Whether the spatial index is considered |
| `key` | Which index was actually chosen |
| `type` | Whether access type uses range/index access |
| `rows` | Estimated rows examined |
| `filtered` | Percentage remaining after filtering |
| `Extra` | Remaining conditions evaluated |

The optimizer is not forced to use an index for every query. Small tables, overly wide MBRs, or low-selectivity predicates can make a table scan cheaper.

MySQL documentation illustrates spatial index usage with `MBRContains()` and `MBRWithin()` in `WHERE`. For other MBR variants, verify the actual plan rather than assuming all predicates optimize identically.

## 8. Creating Valid Geometries Before Writing

A polygon requires a closed exterior ring. Structurally valid example:

~~~sql
SET @valid_polygon = ST_GeomFromText(
    'POLYGON((
        0 0,
        4 0,
        4 4,
        0 4,
        0 0
    ))'
);

SELECT ST_IsValid(@valid_polygon);
~~~

A self-intersecting bow-tie polygon:

~~~sql
SET @invalid_polygon = ST_GeomFromText(
    'POLYGON((
        0 0,
        2 2,
        0 2,
        2 0,
        0 0
    ))'
);

SELECT
    ST_IsValid(@invalid_polygon) AS is_valid,
    ST_Validate(@invalid_polygon) AS validated_geometry;
~~~

This geometry is syntactically well-formed yet topologically invalid.

### Boundary Ingestion Workflow

1. Confirm data source and reference system.
2. Confirm axis order.
3. Verify longitude/latitude lie within valid bounds.
4. Verify SRID.
5. Verify WKT/WKB structure.
6. Run `ST_IsValid()`.
7. If invalid, quarantine the record and fix the source or run a controlled repair step.
8. Write to production tables only after passing data-quality rules.

Never automatically call `ST_Validate()` and overwrite invalid polygons without preserving original data. A geometry repair operation can alter business boundaries.

## 9. Geographic Distance and Measurement Units

With SRID 4326, input coordinates are angular degrees, yet `ST_Distance()` returns geographic distance in meters unless another unit is passed.

Example:

~~~sql
SET @hcm_center = ST_GeomFromText(
    'POINT(106.7000 10.7800)',
    4326,
    'axis-order=long-lat'
);

SET @nearby_point = ST_GeomFromText(
    'POINT(106.7100 10.7800)',
    4326,
    'axis-order=long-lat'
);

SELECT ST_Distance(@hcm_center, @nearby_point) AS distance_m;
~~~

`ST_Distance()` detects the geographic SRS and computes geodetic distance on the ellipsoid. It supports distance calculations across geometry types in geographic SRSs.

You can specify the unit explicitly:

~~~sql
SELECT ST_Distance(
    @hcm_center,
    @nearby_point,
    'metre'
) AS distance_m;
~~~

The unit must exist in `INFORMATION_SCHEMA.ST_UNITS_OF_MEASURE`.

### ST_Distance_Sphere() Computes Spherical Distance

~~~sql
SELECT ST_Distance_Sphere(
    @hcm_center,
    @nearby_point
) AS approximate_distance_m;
~~~

`ST_Distance_Sphere()` returns the shortest distance on a sphere in meters. It supports `Point`/`Point` or `Point`/`MultiPoint`. It is a spherical approximation rather than exact ellipsoidal geodetic distance.

Choosing a function:

| Requirement | Suitable Function |
|---|---|
| Geographic distance on an ellipsoid | `ST_Distance()` |
| Approximate spherical distance between points | `ST_Distance_Sphere()` |
| Distance on a plane with a defined unit | `ST_Distance()` with an appropriate Cartesian SRS |
| Checking whether geometries intersect | `ST_Intersects()` |
| Checking whether a point is inside a polygon | `ST_Contains()` or `ST_Intersects()` per boundary policy |

Do not use SRID 0 for geographic problems unless you have an explicit unit and projection convention.

## 10. Coordinate Error and Tolerance

GPS coordinates, geocoding outputs, or sensor measurements do not always reflect exact absolute positions.

A recorded point:

~~~text
POINT(106.700000 10.780000)
~~~

may simply be a rounded reading from a device. Another reading might be:

~~~text
POINT(106.700004 10.780003)
~~~

The two coordinates are extremely close yet unequal under exact floating-point comparison.

Never use conditions like:

~~~sql
ST_X(location) = 106.700000
~~~

to decide whether two readings represent the same location when measurement error exists.

### Do Not Pick Arbitrary Degree Epsilons

A difference of `0.00001` degrees of longitude does not correspond to the same number of meters at every latitude. Latitude and longitude deltas do not scale identically either.

Never apply a constant like:

~~~sql
ABS(ST_X(location) - 106.7) < 0.00001
~~~

and treat it as a universal one-meter tolerance across all regions.

Express tolerances in meaningful linear units—such as 1 meter or 5 meters—and compute distances using the appropriate SRS function.

### Measuring Distance to a Boundary

For a simple polygon without holes, you can extract the outer boundary with `ST_ExteriorRing()` and measure distance from a point to that ring:

~~~sql
SELECT ST_Distance(
    @point,
    ST_ExteriorRing(@zone),
    'metre'
) AS distance_to_outer_boundary_m;
~~~

If the polygon has interior rings, is a `MultiPolygon`, or has complex geometry, all boundary components must be accounted for; `ST_ExteriorRing()` returns only the exterior ring of a single `Polygon`.

Business rule example—points within 2 meters of the outer boundary are classified as near-boundary:

~~~sql
SELECT
    CASE
        WHEN ST_Intersects(@zone, @point) = 1
            THEN 'INSIDE_OR_ON_BOUNDARY'
        WHEN ST_Distance(
            @point,
            ST_ExteriorRing(@zone),
            'metre'
        ) <= 2
            THEN 'WITHIN_2M_OF_OUTER_BOUNDARY'
        ELSE 'OUTSIDE'
    END AS location_class;
~~~

This example considers only a `Polygon` without holes. Tolerance rules may accept points just outside or just inside a zone as long as distance to the outer ring is within 2 meters. That is a business policy, not a change to `ST_Contains()` semantics.

Never make tolerance an arbitrary magic number. Base it on:

- Positioning device accuracy.
- Boundary dataset accuracy.
- Source and timestamp of measurements.
- Projection or coordinate-transformation error.
- Impact of misclassifying a point.

## 11. Projection and Coordinate Transformation Errors

A geographic SRS uses angular degrees. A projected SRS can use planar meters.

`ST_Transform()` converts coordinates from one SRS to another:

~~~sql
SELECT ST_Transform(@hcm_center, 32648);
~~~

For instance, SRID 32648 is WGS 84 / UTM zone 48N, a projection suited to the longitude band of Ho Chi Minh City. In a local projection, Cartesian distances are in meters and work well for many short-range measurements in that zone.

Do not apply a single projected SRS to locations worldwide. Projections introduce distortion; error grows outside the projection's design zone.

Guidelines:

- Global datasets: use an appropriate geographic SRS and geodetic distance.
- Small regional datasets: consider a projected SRS suited to the region.
- Computing areas, lengths, buffers, or tolerances: check units and SRS type.
- Transforming across multiple SRSs: document the pipeline, dataset version, and expected accuracy.
- Never replace `SRID` via `ST_SRID()` when coordinate transformation is needed; use `ST_Transform()`.

## 12. Querying Service Zones Including Boundary Points

Suppose `service_zones` stores delivery zone polygons.

~~~sql
CREATE TABLE service_zones (
    zone_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    zone_name VARCHAR(150) NOT NULL,
    geom POLYGON NOT NULL SRID 4326,
    SPATIAL INDEX sx_service_zones_geom (geom)
) ENGINE=InnoDB;
~~~

Insert a sample zone:

~~~sql
INSERT INTO service_zones (
    zone_id,
    zone_name,
    geom
)
VALUES (
    1,
    'Central test zone',
    ST_GeomFromText(
        'POLYGON((
            106.6800 10.7600,
            106.7200 10.7600,
            106.7200 10.8000,
            106.6800 10.8000,
            106.6800 10.7600
        ))',
        4326,
        'axis-order=long-lat'
    )
);
~~~

Create an interior point:

~~~sql
SET @point_inside = ST_GeomFromText(
    'POINT(106.7000 10.7800)',
    4326,
    'axis-order=long-lat'
);
~~~

Create a point directly on the western edge:

~~~sql
SET @point_edge = ST_GeomFromText(
    'POINT(106.6800 10.7800)',
    4326,
    'axis-order=long-lat'
);
~~~

Create an exterior point:

~~~sql
SET @point_outside = ST_GeomFromText(
    'POINT(106.7300 10.7800)',
    4326,
    'axis-order=long-lat'
);
~~~

Compare:

~~~sql
SELECT
    ST_Contains(geom, @point_inside) AS inside_contains,
    ST_Intersects(geom, @point_inside) AS inside_intersects,
    ST_Contains(geom, @point_edge) AS edge_contains,
    ST_Intersects(geom, @point_edge) AS edge_intersects,
    ST_Touches(geom, @point_edge) AS edge_touches,
    ST_Intersects(geom, @point_outside) AS outside_intersects
FROM service_zones
WHERE zone_id = 1;
~~~

Expected results:

| Check | Result |
|---|---:|
| Interior point: `ST_Contains` | 1 |
| Interior point: `ST_Intersects` | 1 |
| Boundary point: `ST_Contains` | 0 |
| Boundary point: `ST_Intersects` | 1 |
| Boundary point: `ST_Touches` | 1 |
| Exterior point: `ST_Intersects` | 0 |

If the service zone includes boundaries, query:

~~~sql
SELECT zone_id, zone_name
FROM service_zones
WHERE ST_Intersects(geom, @point_edge);
~~~

If the service zone includes only the strict interior:

~~~sql
SELECT zone_id, zone_name
FROM service_zones
WHERE ST_Contains(geom, @point_edge);
~~~

The second query returns no zone for a point sitting strictly on the edge.

## 13. Optimizing Region Queries with a Spatial Index

For large tables, add an MBR candidate predicate:

~~~sql
EXPLAIN
SELECT zone_id, zone_name
FROM service_zones
WHERE MBRIntersects(@point_edge, geom)
  AND ST_Intersects(geom, @point_edge);
~~~

Then execute the query:

~~~sql
SELECT zone_id, zone_name
FROM service_zones
WHERE MBRIntersects(@point_edge, geom)
  AND ST_Intersects(geom, @point_edge);
~~~

`MBRIntersects` includes touching MBR edges, so points lying on an MBR edge are not dropped during the candidate step. `ST_Intersects` confirms the true shape relationship.

For a strict-interior query:

~~~sql
EXPLAIN
SELECT zone_id, zone_name
FROM service_zones
WHERE MBRWithin(@point_inside, geom)
  AND ST_Contains(geom, @point_inside);
~~~

Points inside the MBR enter the candidate set; `ST_Contains` eliminates points inside the MBR that fall outside the true polygon.

### Reading EXPLAIN

If the optimizer uses the spatial index, `key` shows the spatial index name and `type` reflects the corresponding index access method. If `key` is `NULL` and `type` is `ALL`, the query is scanning the table.

When a table contains only a handful of zones, a table scan can be cheaper. Test on datasets matching production row counts, distributions, and selectivity.

Do not jump straight to `FORCE INDEX`. First verify:

- Has the column declared an SRID?
- Do all rows share the same SRID?
- Are arguments in the MBR predicate ordered properly?
- Is the search rectangle overly broad?
- Are table statistics and cardinality accurate?
- Does the query actually benefit from a spatial index?

## 14. Finding Locations Within a Radius

Task: find points within 5 km of a location:

~~~sql
SET @origin = ST_GeomFromText(
    'POINT(106.7000 10.7800)',
    4326,
    'axis-order=long-lat'
);

SELECT
    place_id,
    place_name,
    ST_Distance(location, @origin, 'metre') AS distance_m
FROM places
WHERE ST_Distance(location, @origin, 'metre') <= 5000
ORDER BY distance_m, place_id
LIMIT 50;
~~~

`ST_Distance()` on a geographic SRS returns geodetic distance on the ellipsoid. The `<= 5000` condition means within 5,000 meters.

However, a distance expression is not a simple B-tree range lookup. For very large datasets, add a bounding-box candidate prefilter first, then compute exact distance.

The candidate bounding box must be constructed according to the proper SRS. For geographic coordinates, the longitude span corresponding to a given meter distance varies with latitude. Never apply a single fixed longitude delta across all latitudes.

If using `ST_Distance_Sphere()`, the output is a spherical approximation and supports only `Point`/`MultiPoint`. Pick the function based on acceptable error tolerance.

## 15. Verifying Edge Cases and Error Margins

A spatial test suite should never test only a single point in the middle of a polygon.

Include at minimum these test cases:

| Test Case | Goal |
|---|---|
| Point deep inside the region | Verify strict containment |
| Point strictly on an edge | Verify boundary semantics |
| Point strictly on a vertex | Verify vertex boundary handling |
| Point just inside the boundary | Assess stability near borders |
| Point just outside the boundary | Assess tolerance behavior |
| Point inside MBR yet outside concave polygon | Catch MBR false positives |
| Point inside a polygon hole | Ensure empty interior holes are excluded |
| Point with a different SRID | Verify mismatch errors |
| Point with out-of-range longitude/latitude | Verify input validation |
| Self-intersecting polygon | Verify geometry validity checks |

### Creating Near-Boundary Points

~~~sql
SET @point_near_inside = ST_GeomFromText(
    'POINT(106.680010 10.7800)',
    4326,
    'axis-order=long-lat'
);

SET @point_near_outside = ST_GeomFromText(
    'POINT(106.679990 10.7800)',
    4326,
    'axis-order=long-lat'
);

SELECT
    ST_Contains(@zone, @point_near_inside) AS near_inside,
    ST_Contains(@zone, @point_near_outside) AS near_outside,
    ST_Distance(
        @point_near_inside,
        ST_ExteriorRing(@zone),
        'metre'
    ) AS inside_distance_to_boundary_m,
    ST_Distance(
        @point_near_outside,
        ST_ExteriorRing(@zone),
        'metre'
    ) AS outside_distance_to_boundary_m;
~~~

In this example `@zone` must be the simple polygon created earlier. The two points differ by a tiny longitude offset, yet one lies inside while the other lies outside.

Do not derive an exact meter distance from a longitude delta via fixed multiplication. Measure using `ST_Distance()` on the geographic SRS.

### Verifying Results at the Application Level

Test the same coordinate set across:

1. MySQL geometry constructors.
2. `ST_AsText()` with the declared `axis-order`.
3. `ST_SRID()`.
4. `ST_IsValid()`.
5. Exact predicates.
6. Distance outputs.
7. API responses or rendered map displays.

If SQL results are correct while map markers appear shifted, inspect GeoJSON/WKB serializers and axis ordering in the application layer.

## 16. Handling SRID and Geometry Data Errors

Common errors:

### Differing SRIDs Between Two Geometries

Multi-geometry functions generally require a common SRS. If one geometry is 4326 and the other is 3857, MySQL raises `ER_GIS_DIFFERENT_SRIDS`.

Verify:

~~~sql
SELECT
    ST_SRID(@point_inside) AS point_srid,
    ST_SRID(@zone) AS zone_srid;
~~~

Run spatial relation checks only after both geometries share the same reference system. When conversion is required, use `ST_Transform()` when both source and target SRSs are supported.

### Out-of-Range Longitude or Latitude

Example constructing a point with latitude `106`:

~~~sql
SELECT ST_GeomFromText(
    'POINT(10 106)',
    4326,
    'axis-order=long-lat'
);
~~~

Here longitude `10` is valid, but latitude `106` is out of bounds. MySQL raises a latitude out-of-range error.

### Not Well-Formed Geometry

An unclosed polygon ring or one with too few points cannot be constructed from WKT. This is a structural error.

### Well-Formed Yet Invalid Geometry

A self-intersecting polygon may parse and store if syntactically valid, yet spatial operations can return undefined results or errors. Use `ST_IsValid()` and `ST_Validate()` in the ingestion pipeline.

### Misassigned SRID

`ST_SRID(geom, 4326)` does not fix coordinates. If a geometry holds meter coordinates yet is tagged with SRID 4326, MySQL interprets those numbers as degrees, triggering range errors or silent wrong answers.

Always know which SRS the source data uses before labeling or transforming.

## 17. Limitations and Caveats When Using Spatial Indexes

| Limitation | Meaning |
|---|---|
| Only one spatial column per spatial index | Cannot create composite `SPATIAL` indexes across multiple geometry columns |
| Column must be `NOT NULL` | Nullable columns are ineligible for `SPATIAL` indexes |
| Requires SRID restriction for optimizer usage | Declare the `SRID` attribute on the column |
| R-tree stores MBRs | Index does not capture complex shapes directly |
| MBRs produce false positives | Requires exact predicates for final filtering |
| Queries depend on SRS | Different SRIDs cannot be compared directly |
| Invalid geometries | Spatial results may be undefined or error out |
| Small datasets | Table scan may be cheaper than index access |
| Overly wide MBRs | Large candidate sets reduce index benefit |
| Boundary updates | Must manage geometry versions and effective timestamps |

A spatial index does not replace accurate boundary data, decide boundary policies, or fix coordinate source errors.

## 18. Hands-On Lab: Service Zones, Boundary Points, and 2-Meter Tolerance

This lab creates a sample zone, test points, and exact/MBR queries to observe the differences.

### Step 1: Create the Database

~~~sql
CREATE DATABASE IF NOT EXISTS mysql_spatial_boundary_lab;
USE mysql_spatial_boundary_lab;
~~~

### Step 2: Create the Zones Table

~~~sql
CREATE TABLE service_zones (
    zone_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    zone_name VARCHAR(150) NOT NULL,
    geom POLYGON NOT NULL SRID 4326,
    SPATIAL INDEX sx_service_zones_geom (geom)
) ENGINE=InnoDB;
~~~

### Step 3: Insert a Test Zone

~~~sql
INSERT INTO service_zones (
    zone_id,
    zone_name,
    geom
)
VALUES (
    1,
    'HCM test rectangle',
    ST_GeomFromText(
        'POLYGON((
            106.6800 10.7600,
            106.7200 10.7600,
            106.7200 10.8000,
            106.6800 10.8000,
            106.6800 10.7600
        ))',
        4326,
        'axis-order=long-lat'
    )
);
~~~

### Step 4: Validate the Polygon

~~~sql
SELECT
    zone_id,
    ST_SRID(geom) AS srid,
    ST_IsValid(geom) AS is_valid,
    ST_AsText(geom, 'axis-order=long-lat') AS polygon_wkt
FROM service_zones;
~~~

Expected result: SRID `4326` and `is_valid = 1`.

### Step 5: Create Interior, Boundary, and Exterior Points

~~~sql
SET @inside = ST_GeomFromText(
    'POINT(106.7000 10.7800)',
    4326,
    'axis-order=long-lat'
);

SET @edge = ST_GeomFromText(
    'POINT(106.6800 10.7800)',
    4326,
    'axis-order=long-lat'
);

SET @outside = ST_GeomFromText(
    'POINT(106.7300 10.7800)',
    4326,
    'axis-order=long-lat'
);
~~~

### Step 6: Compare Boundary Semantics

~~~sql
SELECT
    ST_Contains(geom, @inside) AS inside_contains,
    ST_Intersects(geom, @inside) AS inside_intersects,
    ST_Contains(geom, @edge) AS edge_contains,
    ST_Intersects(geom, @edge) AS edge_intersects,
    ST_Touches(geom, @edge) AS edge_touches,
    ST_Intersects(geom, @outside) AS outside_intersects
FROM service_zones
WHERE zone_id = 1;
~~~

Expected results:

- Interior point: `Contains = 1`, `Intersects = 1`.
- Boundary point: `Contains = 0`, `Intersects = 1`, `Touches = 1`.
- Exterior point: `Intersects = 0`.

### Step 7: Query Zones Including Boundaries

~~~sql
SELECT zone_id, zone_name
FROM service_zones
WHERE MBRIntersects(@edge, geom)
  AND ST_Intersects(geom, @edge);
~~~

The result must include `zone_id = 1`.

### Step 8: Query Zones for Strict Interior Only

~~~sql
SELECT zone_id, zone_name
FROM service_zones
WHERE MBRWithin(@edge, geom)
  AND ST_Contains(geom, @edge);
~~~

No row is returned because the point sits on the edge rather than strictly inside the polygon's interior.

### Step 9: Demonstrate an MBR False Positive

~~~sql
SET @concave = ST_GeomFromText(
    'POLYGON((
        0 0,
        4 0,
        4 1,
        1 1,
        1 3,
        4 3,
        4 4,
        0 4,
        0 0
    ))'
);

SET @notch = ST_GeomFromText('POINT(3 2)');

SELECT
    MBRIntersects(@concave, @notch) AS mbr_intersects,
    ST_Intersects(@concave, @notch) AS exact_intersects;
~~~

Expected result: `MBRIntersects = 1`, `ST_Intersects = 0`. This illustrates why exact predicates must follow MBR candidate filtering.

### Step 10: Measure Distance to the Boundary

~~~sql
SELECT
    ST_Distance(
        @inside,
        ST_ExteriorRing(geom),
        'metre'
    ) AS inside_to_outer_boundary_m,
    ST_Distance(
        @outside,
        ST_ExteriorRing(geom),
        'metre'
    ) AS outside_to_outer_boundary_m
FROM service_zones
WHERE zone_id = 1;
~~~

Results are in meters under the geographic SRS. The exterior point has a positive distance to the outer ring; the interior point also has a positive distance to the outer ring because the calculation measures distance to the boundary line rather than the filled polygon area.

### Step 11: Inspect EXPLAIN

~~~sql
EXPLAIN
SELECT zone_id, zone_name
FROM service_zones
WHERE MBRIntersects(@edge, geom)
  AND ST_Intersects(geom, @edge);
~~~

Because the lab table is tiny, the optimizer may choose a table scan. Inspect `key` and `rows`, then retest on a larger dataset with diverse zone distributions.

### Step 12: Simulate an Invalid Geometry

~~~sql
SET @bowtie = ST_GeomFromText(
    'POLYGON((
        0 0,
        2 2,
        0 2,
        2 0,
        0 0
    ))'
);

SELECT
    ST_IsValid(@bowtie) AS is_valid,
    ST_Validate(@bowtie) AS validated;
~~~

Expected result: `is_valid = 0`; `ST_Validate` returns `NULL`.

### Step 13: Clean Up

~~~sql
DROP DATABASE mysql_spatial_boundary_lab;
~~~

Run `DROP DATABASE` only on the lab database you created.

## 19. Common Errors and Remedies

| Symptom | Cause | How to Handle |
|---|---|---|
| Point lies on boundary yet `ST_Contains` returns `0` | Contains requires interior intersection, excluding boundaries | Use `ST_Intersects` if policy includes boundaries |
| Boundary point missing after `MBRContains` | `MBRContains` also excludes points on the MBR edge | Use `MBRIntersects`/`MBRCovers` as appropriate, then exact-check |
| Points inside MBR yet outside polygon still returned | Using MBR predicate alone | Add `ST_Contains` or `ST_Intersects` |
| Coordinates plot at the wrong location | Swapped longitude/latitude or wrong axis order | Pass `axis-order` explicitly and check `ST_Longitude`/`ST_Latitude` |
| Spatial function reports differing SRIDs | Two geometries use different SRSs | Convert with `ST_Transform` where appropriate |
| Assigned SRID yet results remain wrong | Used `ST_SRID` instead of transforming coordinates | Use `ST_Transform` and verify source SRS |
| Cannot create spatial index | Column is nullable or not SRID-restricted | Declare `NOT NULL` and an explicit `SRID` |
| Optimizer ignores spatial index | Missing SRID declaration or incompatible predicate | Check column definition, MBR predicate, and `EXPLAIN` |
| `EXPLAIN` selects table scan | Small table or unselective candidate predicate | Evaluate on real datasets; do not force indexes when unhelpful |
| Polygon stored successfully yet spatial query errors | Geometry is well-formed but invalid | Check `ST_IsValid` and fix source data |
| Near-boundary points flip between inside and outside | Device inaccuracy or rounded coordinates | Define a tolerance in meters |
| Degree epsilon drifts across latitudes | Degrees do not equal fixed linear distance | Use `ST_Distance` or an appropriate projected SRS |
| SRID 0 distance interpreted as meters | SRID 0 has no axis unit | Use a geographic/projected SRS with explicit units |
| `ST_Distance_Sphere` called with a polygon | Function supports only `Point`/`MultiPoint` | Use `ST_Distance` or a geometry-compatible function |
| Zone has holes yet points inside holes remain candidates | MBR encloses the hole as well | Exact `ST_Intersects`/`ST_Contains` eliminates false positives |
| Newly imported data has mixed SRIDs | Unstandardized source | Audit `ST_SRID` before indexing |
| Boundary changes yet queries still reflect old data | No geometry versioning | Track version, effective date, and source metadata |

## 20. Location Query Design Checklist

- [ ] Selected the right geometry type.
- [ ] Identified the source data's SRID.
- [ ] Standardized longitude/latitude conventions.
- [ ] Passed explicit `axis-order` when constructing geometries from WKT.
- [ ] Verified `ST_SRID`, longitude, and latitude.
- [ ] Validated geometries using `ST_IsValid` or `ST_Validate`.
- [ ] Decided whether boundary points count as inside or outside.
- [ ] Distinguished `ST_Contains` from `ST_Intersects` and `ST_Touches`.
- [ ] Understood that MBR is a bounding rectangle, not the true shape.
- [ ] Used MBR as a candidate filter where beneficial.
- [ ] Confirmed candidates using exact predicates.
- [ ] Made spatially indexed columns `NOT NULL` and SRID-restricted.
- [ ] Verified spatial index usage with `EXPLAIN`.
- [ ] Measured distances in meaningful units.
- [ ] Selected `ST_Distance` or `ST_Distance_Sphere` based on accuracy needs.
- [ ] Defined tolerances in meters or SRS units rather than arbitrary degree epsilons.
- [ ] Tested interior, boundary, exterior, near-boundary, and polygon-hole points.
- [ ] Tested concave polygons to verify handling of MBR false positives.
- [ ] Tested SRID mismatches and out-of-range coordinates.
- [ ] Managed versioning and provenance for boundary datasets.

## 21. Principles to Remember

1. Geometries represent points, paths, regions, and geometry collections.
2. SRID identifies the reference system; never treat all coordinates as sharing one system.
3. SRID 4326 uses geographic coordinates; control axis order explicitly when parsing WKT.
4. `ST_SRID()` only changes the SRID label; `ST_Transform()` actually transforms coordinates.
5. `ST_Contains()` excludes points lying strictly on the boundary.
6. `ST_Intersects()` includes both interior points and boundary points.
7. `ST_Touches()` identifies boundary-only contact.
8. An MBR describes only the enclosing rectangle; it can produce false positives.
9. Use MBR to filter candidates, then an exact `ST_*` predicate to verify shape semantics.
10. Spatial indexes use R-trees; columns must be `NOT NULL` and SRID-restricted for optimizer usage.
11. MySQL 9.7 uses the column's SRS to compute appropriate spatial index bounding boxes.
12. A well-formed geometry is not necessarily a valid geometry.
13. `ST_IsValid()` and `ST_Validate()` assist with topological validation.
14. `ST_Distance()` on a geographic SRS computes geodetic distance on the ellipsoid.
15. `ST_Distance_Sphere()` computes spherical distance and supports only `Point`/`MultiPoint`.
16. Coordinate error must be handled with unit-aware, domain-meaningful tolerances.
17. Test suites must cover interior, boundary, exterior, near-boundary, and concave/hole cases.

## Official References

Syntax and behavior in this lesson are verified against the **MySQL 9.7 Reference Manual**:

1. [Spatial Data Types](https://dev.mysql.com/doc/refman/9.7/en/spatial-type-overview.html): geometry types, `SRID` attribute, and spatial index requirements.
2. [Spatial Reference System Support](https://dev.mysql.com/doc/refman/9.7/en/spatial-reference-systems.html): reference systems, SRIDs, and coordinate axes.
3. [Functions That Create Geometry Values from WKT Values](https://dev.mysql.com/doc/refman/9.7/en/gis-wkt-functions.html): `ST_GeomFromText()`, `axis-order`, and longitude/latitude bounds.
4. [Geometry Well-Formedness and Validity](https://dev.mysql.com/doc/refman/9.7/en/geometry-well-formedness-validity.html): well-formed geometries, validity, `ST_IsValid()`, and `ST_Validate()`.
5. [Spatial Relation Functions That Use Object Shapes](https://dev.mysql.com/doc/refman/9.7/en/spatial-relation-functions-object-shapes.html): `ST_Contains()`, `ST_Intersects()`, `ST_Touches()`, and `ST_Distance()`.
6. [Spatial Relation Functions That Use Minimum Bounding Rectangles](https://dev.mysql.com/doc/refman/9.7/en/spatial-relation-functions-mbr.html): `MBRContains`, `MBRCovers`, `MBRIntersects`, and boundary semantics.
7. [Creating Spatial Indexes](https://dev.mysql.com/doc/refman/9.7/en/creating-spatial-indexes.html): R-trees, `NOT NULL`, SRID, and `SPATIAL INDEX` syntax.
8. [Using Spatial Indexes](https://dev.mysql.com/doc/refman/9.7/en/using-spatial-indexes.html): using MBR predicates and `EXPLAIN` to verify spatial indexes.
9. [SPATIAL Index Optimization](https://dev.mysql.com/doc/refman/9.7/en/spatial-index-optimization.html): how the optimizer handles Cartesian/geographic SRIDs and SRID-restricted requirements.
10. [Spatial Convenience Functions](https://dev.mysql.com/doc/refman/9.7/en/spatial-convenience-functions.html): `ST_Distance_Sphere()`, `ST_IsValid()`, and convenience function limits.
