# Distance, Measurement Units, and Supported Coordinate System Conditions

When calculating the distance between two locations, the result is meaningful only if both geometries use the same coordinate system and the measurement units are properly understood. Two points at `(10, 20)` and `(11, 21)` could represent two positions on an abstract plane, two coordinates on a projected map, or two longitude/latitude pairs on Earth. The same numbers produce completely different calculations and units.

In MySQL, the primary function is `ST_Distance()`. It returns distance in the length unit of the spatial reference system (SRS) or in a specified unit argument. For geographic SRSs, MySQL computes geodetic distance on the ellipsoid. When a spherical model suffices and the data consists of points, you can use `ST_Distance_Sphere()`, which returns results in meters.

Common mistakes stem from:

- Storing longitude/latitude with the default SRID 0.
- Calling `ST_Distance()` on SRID 0 and interpreting the output as meters.
- Mixing geometries with different SRIDs in the same calculation.
- Assigning a new SRID with `ST_SRID()` without transforming coordinates.
- Passing longitude and latitude in the wrong order relative to the SRS axis definition.
- Calling `ST_Distance_Sphere()` on a projected SRS or non-Point/MultiPoint geometries.
- Requesting a unit unsupported by MySQL or attempting unit conversion when the SRS defines no length unit.

This lesson guides you through choosing an SRS, understanding SRIDs, checking units, selecting distance functions, transforming coordinate systems, designing columns and spatial indexes, and validating input conditions before deploying distance calculations in applications.

Examples focus on MySQL 8.4. SRSs, units, and transformation capabilities depend on the definitions installed in the data dictionary and server version; query metadata on the live server rather than guessing from an SRID name.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish Cartesian SRSs, projected SRSs, and geographic SRSs.
- Explain SRID 0 and why it lacks a length unit.
- Understand SRID 4326 (WGS 84), longitude, latitude, and SRS axis order.
- Distinguish `ST_SRID()` from `ST_Transform()`.
- Choose between `ST_Distance()` and `ST_Distance_Sphere()` based on the measurement model.
- Understand the default unit and `unit` argument of `ST_Distance()`.
- Look up valid units in `INFORMATION_SCHEMA.ST_UNITS_OF_MEASURE`.
- Recognize errors when geometries have different SRIDs or undefined SRSs.
- Recognize the geometry type and SRS limitations of `ST_Distance_Sphere()`.
- Validate that longitude/latitude lie within valid bounds.
- Design SRID-restricted spatial columns and spatial indexes.
- Separate bounding-box candidate filtering from exact distance calculations.
- Write nearest-location queries with clear units and predicates.
- Build a coordinate system verification checklist before release.

## 1. Distance Is More Than Subtracting Coordinates

Suppose two points have coordinates:

    POINT(10 20)
    POINT(13 24)

If these are two points on a Cartesian plane, the Euclidean distance is:

    SQRT((13 - 10)^2 + (24 - 20)^2)
    = 5

What unit does the number `5` have? That depends on the SRS:

- If axes are measured in meters, the result is 5 meters.
- If axes are measured in feet, the result is 5 feet.
- Under SRID 0, the axes have no assigned unit; the result is merely 5 abstract coordinate units.
- If the numbers are longitude/latitude, differences in degrees cannot be treated as fixed linear distances on a plane.

In a geographic SRS, distance between two locations must account for the Earth's ellipsoidal shape. One degree of longitude at the equator has a different physical length than one degree of longitude at high latitudes. Neither can a degree of latitude be treated as an arbitrary fixed linear unit.

Therefore, before choosing a distance function, answer three questions:

1. Which SRS are the geometries stored in?
2. What units and axis order do the coordinate axes use?
3. Does the domain require planar distance, geodetic distance on an ellipsoid, or a spherical approximation?

## 2. SRS, SRID, and Three Coordinate Models

A Spatial Reference System (SRS) describes the coordinate system used to locate geometries. An SRID is the numeric identifier attached to a geometry to reference that SRS.

MySQL supports Cartesian, projected, and geographic SRSs. They differ in how coordinates and units are interpreted.

### 2.1. Cartesian SRS

A Cartesian SRS models a flat plane with perpendicular X/Y axes. Distance calculations follow planar geometry.

Example:

    POINT(100 200)
    POINT(103 204)

If the SRS specifies meters, the Euclidean distance is 5 meters. Under another Cartesian system, the result uses that system's length unit.

Cartesian fits:

- Technical drawings and factory floor plans.
- Game coordinates or simulation models.
- Local maps already projected onto an appropriate planar system.
- Planar geometry problems that do not directly model the whole Earth.

### 2.2. Projected SRS

A projected SRS maps the Earth's ellipsoidal surface onto a flat map plane. Coordinates are typically Easting/Northing or X/Y in linear units such as meters or feet.

Common examples:

- EPSG:3857 — WGS 84 / Pseudo-Mercator, widely used in web maps.
- UTM zones — commonly used for regional surveying.
- National or local projections with dedicated units and projection parameters.

The benefit is convenient planar math for regional operations. However, projections introduce distortion. EPSG:3857 is convenient for rendering web maps, yet direct distance measurements diverge significantly away from the equator. Do not pick a projected SRS solely because its units are meters; select a projection suited to the region and required accuracy.

### 2.3. Geographic SRS

A geographic SRS represents locations on an ellipsoid using angular coordinates, typically longitude/latitude or latitude/longitude per the axis definition.

Common examples:

- EPSG:4326 — WGS 84.
- Other geographic SRSs using different datums/ellipsoids.

In a geographic SRS, coordinates typically fall within:

- Longitude: greater than -180 and less than or equal to 180 degrees.
- Latitude: from -90 to 90 degrees.

MySQL enforces longitude/latitude bounds according to the SRS. If values exceed those bounds, geographic geometry functions raise errors.

### 2.4. SRID 0 Is a Unitless Plane

SRID 0 in MySQL is an infinite Cartesian plane unbound to the Earth and without axis units. It is the default SRID when creating a geometry without specifying one.

Example:

    SET @p1 = ST_GeomFromText('POINT(10 20)');
    SELECT ST_SRID(@p1);

The result is `0`.

Never interpret `ST_Distance()` between two SRID 0 geometries as meters or kilometers. The output is only distance within that abstract coordinate system.

## 3. Checking SRSs Supported by MySQL

MySQL stores SRS definitions in the data dictionary and exposes `INFORMATION_SCHEMA.ST_SPATIAL_REFERENCE_SYSTEMS`.

### 3.1. Looking Up WGS 84

    SELECT
        SRS_NAME,
        SRS_ID,
        ORGANIZATION,
        ORGANIZATION_COORDSYS_ID,
        DEFINITION,
        DESCRIPTION
    FROM INFORMATION_SCHEMA.ST_SPATIAL_REFERENCE_SYSTEMS
    WHERE SRS_ID = 4326;

The result shows SRID 4326 is named WGS 84, organization EPSG, along with its WKT SRS definition. In EPSG:4326's definition, the axes are ordered latitude before longitude.

### 3.2. Finding Geographic or Projected SRSs

    SELECT
        SRS_ID,
        SRS_NAME,
        ORGANIZATION,
        DEFINITION
    FROM INFORMATION_SCHEMA.ST_SPATIAL_REFERENCE_SYSTEMS
    ORDER BY SRS_ID;

You can filter by name or organization:

    SELECT
        SRS_ID,
        SRS_NAME,
        ORGANIZATION
    FROM INFORMATION_SCHEMA.ST_SPATIAL_REFERENCE_SYSTEMS
    WHERE SRS_NAME LIKE '%WGS%'
       OR SRS_NAME LIKE '%UTM%';

This view reflects the SRSs present in the server's data dictionary. Do not assume every EPSG code in an external GIS system is installed or transformable in MySQL.

### 3.3. Inspecting Spatial Column Metadata

    SELECT
        TABLE_SCHEMA,
        TABLE_NAME,
        COLUMN_NAME,
        SRS_ID,
        SRS_NAME,
        GEOMETRY_TYPE_NAME
    FROM INFORMATION_SCHEMA.ST_GEOMETRY_COLUMNS
    WHERE TABLE_SCHEMA = DATABASE();

This query reveals which SRID and declared geometry type each column uses.

## 4. Coordinate Axis Order: Longitude/Latitude or Latitude/Longitude?

This is a very common source of bugs when importing GPS or map API data.

Many APIs and GeoJSON payloads represent positions in the order:

    [longitude, latitude]

However, an SRS may define its axes in the order:

    latitude, longitude

By default, MySQL's WKT geometry constructors interpret geographic coordinates using the axis order defined in the SRS. For EPSG:4326, the defined order is latitude before longitude. You can state your choice explicitly with the `options` argument.

### 4.1. Using SRS-Defined Order

Example geographic coordinates with latitude `10.8` and longitude `106.7`:

    SET @hcm = ST_GeomFromText(
        'POINT(10.8 106.7)',
        4326
    );

Because no options are passed, MySQL uses the SRS-defined axis order.

### 4.2. Explicitly Specifying Longitude Before Latitude

If application input always arrives in longitude/latitude order, specify:

    SET @hcm = ST_GeomFromText(
        'POINT(106.7 10.8)',
        4326,
        'axis-order=long-lat'
    );

Supported options:

- `axis-order=srid-defined`: use the axis order specified by the SRS; this is the default.
- `axis-order=lat-long`: parse coordinates as latitude then longitude.
- `axis-order=long-lat`: parse coordinates as longitude then latitude.

Never alter coordinate order simply by swapping two numbers without understanding the SRS. Standardize the data contract across APIs, ETL, WKT/WKB, and storage columns.

### 4.3. Verifying the Geometry After Creation

    SELECT
        ST_AsText(@hcm),
        ST_SRID(@hcm),
        ST_Longitude(@hcm),
        ST_Latitude(@hcm);

For a geographic Point, `ST_Longitude()` and `ST_Latitude()` read both components with their geographic meaning. If the values fall outside the expected region, check `axis-order` before bulk-loading data.

## 5. ST_Distance(): SRS-Aware Distance

Syntax:

    ST_Distance(g1, g2 [, unit])

Returns the distance between two geometries:

- If the SRS is Cartesian, measurement uses the Cartesian SRS's length unit.
- If the SRS is geographic, MySQL computes geodetic distance on the ellipsoid.
- If the `unit` argument is supplied, the result is converted to that length unit.
- If `unit` is omitted, the result uses the SRS's length unit. Currently supported MySQL SRSs express length units in meters.

Both input geometries must share the same SRS. If SRIDs differ, MySQL raises `ER_GIS_DIFFERENT_SRIDS`.

### 5.1. Distance on the SRID 0 Plane

    SET @a = ST_GeomFromText('POINT(1 1)', 0);
    SET @b = ST_GeomFromText('POINT(4 5)', 0);

    SELECT ST_Distance(@a, @b) AS coordinate_distance;

The result is `5`. That is 5 abstract coordinate units, not 5 meters.

### 5.2. Geographic Distance with WGS 84

    SET @p1 = ST_GeomFromText(
        'POINT(106.7 10.8)',
        4326,
        'axis-order=long-lat'
    );

    SET @p2 = ST_GeomFromText(
        'POINT(106.71 10.8)',
        4326,
        'axis-order=long-lat'
    );

    SELECT ST_Distance(@p1, @p2) AS distance_m;

This computes geodetic distance on the WGS 84 ellipsoid. Because the SRS uses meters as its length unit, the default result is in meters.

### 5.3. Requesting Other Units

    SELECT
        ST_Distance(@p1, @p2, 'metre') AS distance_m,
        ST_Distance(@p1, @p2, 'foot') AS distance_ft,
        ST_Distance(@p1, @p2, 'kilometre') AS distance_km;

The unit name must be supported by MySQL. If the unit does not exist, the function raises `ER_UNIT_NOT_FOUND`.

Never guess unit names from display abbreviations like `m`, `km`, or `mi`. Look up exact names in `INFORMATION_SCHEMA.ST_UNITS_OF_MEASURE`.

### 5.4. SRID 0 Cannot Convert Length Units

Example:

    SELECT ST_Distance(@a, @b, 'metre');

For SRID 0 geometries, MySQL does not know how many meters correspond to one coordinate unit. Passing a linear unit raises `ER_GEOMETRY_IN_UNKNOWN_LENGTH_UNIT`.

You cannot fix this error merely by passing `'metre'`. You must construct geometries in an SRS with a defined unit or transform data using a valid coordinate transformation.

## 6. Querying Supported Measurement Units

MySQL provides `INFORMATION_SCHEMA.ST_UNITS_OF_MEASURE` listing units accepted by `ST_Distance()` and other spatial functions taking a `unit` argument.

### 6.1. Viewing All Units

    SELECT
        UNIT_NAME,
        UNIT_TYPE,
        CONVERSION_FACTOR,
        DESCRIPTION
    FROM INFORMATION_SCHEMA.ST_UNITS_OF_MEASURE
    ORDER BY UNIT_TYPE, UNIT_NAME;

Column meanings:

- `UNIT_NAME`: name passed in the `unit` argument.
- `UNIT_TYPE`: unit category, such as `LINEAR`.
- `CONVERSION_FACTOR`: internal conversion factor.
- `DESCRIPTION`: unit description.

### 6.2. Filtering Linear Units

    SELECT
        UNIT_NAME,
        CONVERSION_FACTOR,
        DESCRIPTION
    FROM INFORMATION_SCHEMA.ST_UNITS_OF_MEASURE
    WHERE UNIT_TYPE = 'LINEAR'
    ORDER BY UNIT_NAME;

The list includes units such as `metre`, `kilometre`, `foot`, or `nautical mile`. Use the exact `UNIT_NAME` reported by the server.

### 6.3. Units and SRS

The `unit` argument of `ST_Distance()` is a linear unit, not an angular unit. Never pass `degree` to request geographic distance in degrees.

For geographic SRSs, MySQL computes geodetic distance and returns it in a linear unit. For projected SRSs, the default unit is the projection's linear unit. For SRID 0, there is no linear unit to convert from.

## 7. ST_Distance_Sphere(): Spherical Distance

Syntax:

    ST_Distance_Sphere(g1, g2 [, radius])

Returns the shortest distance between `Point` or `MultiPoint` geometries on a sphere. The result is always in meters. If supplied, `radius` must also be in meters.

### 7.1. With SRID 0

When both geometries are valid `Point` or `MultiPoint` values with SRID 0:

- X is interpreted as longitude.
- Y is interpreted as latitude.
- Angular coordinates are in degrees.
- The default radius is 6,370,986 meters.

Example:

    SET @p1 = ST_GeomFromText('POINT(106.7 10.8)', 0);
    SET @p2 = ST_GeomFromText('POINT(106.71 10.8)', 0);

    SELECT ST_Distance_Sphere(@p1, @p2) AS distance_m;

In this case, SRID 0 does not describe a geographic SRS; the function has a special rule treating Point X/Y as spherical longitude/latitude. Do not apply this special rule to `ST_Distance()`.

### 7.2. With Geographic SRSs

If both geometries are `Point` or `MultiPoint` values in a geographic SRS:

- MySQL uses a default radius equal to the mean radius of the SRS ellipsoid, calculated as `(2a+b)/3`.
- You can pass a custom `radius` in meters.
- The result is spherical distance, not exact geodetic distance on the ellipsoid.

Example:

    SET @p1 = ST_GeomFromText(
        'POINT(106.7 10.8)',
        4326,
        'axis-order=long-lat'
    );

    SET @p2 = ST_GeomFromText(
        'POINT(106.71 10.8)',
        4326,
        'axis-order=long-lat'
    );

    SELECT
        ST_Distance_Sphere(@p1, @p2) AS default_radius_m,
        ST_Distance_Sphere(@p1, @p2, 6371000) AS custom_radius_m;

### 7.3. Geometry Type and SRS Limitations

`ST_Distance_Sphere()` only supports these combinations:

- Point and Point.
- Point and MultiPoint.
- MultiPoint and Point.

It does not support `Polygon`, `LineString`, or `GeometryCollection`. If a geometry uses a projected SRS, MySQL raises `ER_NOT_IMPLEMENTED_FOR_PROJECTED_SRS`.

When you need distance between paths, regions, or composite geometries, use `ST_Distance()` if the SRS and geometry types are supported.

### 7.4. Which Function Should You Choose?

| Need | Suitable Function | Result |
|---|---|---|
| Distance between two geometries on a Cartesian plane | `ST_Distance` | Unit of the SRS |
| Geodetic distance on an ellipsoid | `ST_Distance` with a geographic SRS | SRS length unit or specified `unit` |
| Approximate spherical distance for Point/MultiPoint | `ST_Distance_Sphere` | Meters |
| Distance from Point to Polygon/LineString | `ST_Distance` if geometries are valid and share SRS | SRS length unit |
| Computing on SRID 0 and treating output as meters | No function infers this automatically | Requires an SRS with defined units |

`ST_Distance_Sphere()` can suffice for general proximity searches, but when higher geodetic accuracy is needed, use `ST_Distance()` with a geographic SRS.

## 8. ST_SRID() Does Not Transform Coordinates

These two functions serve distinct purposes:

- `ST_SRID(g, srid)` assigns a new SRID to a geometry while leaving coordinate numbers untouched.
- `ST_Transform(g, target_srid)` transforms coordinates to the target system and returns a geometry with the target SRID.

### 8.1. Example Relabeling an SRID

    SET @g = ST_GeomFromText('POINT(106.7 10.8)', 0);

    SELECT ST_AsText(ST_SRID(@g, 4326));

This assigns SRID 4326 to the existing numbers. It does not recalculate coordinates under WGS 84 and does not verify that the original numbers were genuinely longitude/latitude.

Use `ST_SRID()` only when a geometry already holds valid coordinates for that system but had the wrong or missing SRID metadata. Never use it as a coordinate transformation.

### 8.2. Using ST_Transform()

    SET @web_point = ST_GeomFromText(
        'POINT(11886500 1220000)',
        3857
    );

    SET @wgs84_point = ST_Transform(@web_point, 4326);

    SELECT
        ST_SRID(@wgs84_point),
        ST_AsText(@wgs84_point);

`ST_Transform()` executes a coordinate transformation according to the SRS definitions. If the source or target transformation is unsupported, MySQL may raise errors such as:

- `ER_SRS_NOT_FOUND`.
- `ER_TRANSFORM_SOURCE_SRS_NOT_SUPPORTED`.
- `ER_TRANSFORM_TARGET_SRS_NOT_SUPPORTED`.
- `ER_TRANSFORM_SOURCE_SRS_MISSING_TOWGS84`.
- `ER_TRANSFORM_TARGET_SRS_MISSING_TOWGS84`.

MySQL 8.4 supports EPSG SRSs except certain definitions noted in the manual, and transformations depend on SRS datum/transform parameters. Test on a few control coordinates before transforming an entire table.

### 8.3. Checking SRIDs Before Computing

    SELECT
        ST_SRID(location) AS srid,
        COUNT(*) AS row_count
    FROM places
    GROUP BY ST_SRID(location);

If a column contains multiple SRIDs, do not pass those values directly into a multi-geometry distance calculation. Normalize data to a single SRS or transform each value to the target SRS first.

## 9. SRID Requirements for Multi-Geometry Functions

Spatial functions taking multiple geometries generally require all geometries to share the same SRS. If one geometry has SRID 4326 and the other has SRID 3857, MySQL raises `ER_GIS_DIFFERENT_SRIDS`.

Invalid example:

    SET @a = ST_GeomFromText(
        'POINT(106.7 10.8)',
        4326,
        'axis-order=long-lat'
    );

    SET @b = ST_GeomFromText(
        'POINT(11886500 1220000)',
        3857
    );

    SELECT ST_Distance(@a, @b);

You must transform one geometry into the other's SRS:

    SET @b_4326 = ST_Transform(@b, 4326);

    SELECT ST_Distance(@a, @b_4326);

Never resolve the error by changing one object's SRID via `ST_SRID()` when its coordinates belong to the old system. Doing so forces MySQL to interpret those numbers under the wrong coordinate system.

## 10. Supported Coordinate Systems and Storage Engine Limits

MySQL supports spatial data types across different storage engines, though SRS and spatial index support varies.

| Storage Engine | Spatial Columns | Supported SRIDs per MySQL Docs | SPATIAL Index |
|---|---|---|---|
| InnoDB | Yes | Cartesian and geographic SRSs | Yes |
| MyISAM | Yes | Cartesian SRSs | Yes |
| NDB | Yes | Check engine-specific limits | No |
| ARCHIVE | Yes | Check engine-specific limits | No |

Spatial indexes are supported only on InnoDB and MyISAM. NDB and ARCHIVE support spatial data types but not `SPATIAL` indexes. For new systems requiring geographic coordinates alongside spatial indexes, InnoDB is typically the practical choice. Do not assume an engine supports every SRS and index type merely because a `POINT` column can be created.

### 10.1. Supported Geometry Types

MySQL supports these geometry types:

- `GEOMETRY`
- `POINT`
- `LINESTRING`
- `POLYGON`
- `MULTIPOINT`
- `MULTILINESTRING`
- `MULTIPOLYGON`
- `GEOMETRYCOLLECTION`

Not every distance function accepts every geometry type. `ST_Distance()` supports geographic SRSs across geometry types per function rules; `ST_Distance_Sphere()` accepts only `Point`/`MultiPoint`.

### 10.2. Undefined SRS

If an SRID references an SRS absent from the data dictionary, many spatial functions raise `ER_SRS_NOT_FOUND`. Verify:

    SELECT *
    FROM INFORMATION_SCHEMA.ST_SPATIAL_REFERENCE_SYSTEMS
    WHERE SRS_ID = 999999;

If no rows are returned, the server lacks that SRS definition. Do not use an SRID code merely because it appears in external data.

## 11. SRID-Restricted Spatial Columns and Spatial Indexes

Spatial indexes in MySQL use R-trees. For the optimizer to consider the index, the column must:

- Be declared `NOT NULL`.
- Have a fixed SRID in its column definition.
- Contain only geometries matching that SRID.

Example:

    CREATE TABLE delivery_point (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(150) NOT NULL,
        location POINT NOT NULL SRID 4326,
        SPATIAL INDEX sx_delivery_location (location)
    ) ENGINE=InnoDB;

The `SRID 4326` attribute ensures the column accepts only SRID 4326 geometries. Inserts with any other SRID are rejected by MySQL.

### 11.1. Columns Without an SRID Restriction

A geometry column without an `SRID` attribute can store values from multiple SRSs. However, the optimizer cannot use a spatial index on an unrestricted column. If the table already holds data, audit all values and normalize them to one SRID before adding the restriction.

Check:

    SELECT DISTINCT ST_SRID(location)
    FROM delivery_point;

If multiple SRIDs appear, clean up the data before altering the column definition.

### 11.2. Spatial Index Restrictions

Spatial indexes:

- Apply to a single spatial column only.
- Require the indexed column to be `NOT NULL`.
- Do not support prefix lengths.
- Cannot serve as a `PRIMARY KEY` or `UNIQUE` index.
- Can use the R-tree to filter by minimum bounding rectangle.

A spatial index does not automatically turn every `ST_Distance()` query into an index seek. Typically, you apply a spatial condition that leverages a bounding box or spatial relation, then compute exact distance on the smaller candidate set.

## 12. Finding Nearest Points with Explicit Units

Example places table:

    CREATE TABLE places (
        place_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
        tenant_id BIGINT UNSIGNED NOT NULL,
        place_name VARCHAR(150) NOT NULL,
        status ENUM('ACTIVE', 'INACTIVE') NOT NULL DEFAULT 'ACTIVE',
        location POINT NOT NULL SRID 4326,
        INDEX ix_places_tenant_status (tenant_id, status),
        SPATIAL INDEX sx_places_location (location)
    ) ENGINE=InnoDB;

Insert a point:

    INSERT INTO places(tenant_id, place_name, location)
    VALUES (
        10,
        'Office A',
        ST_GeomFromText(
            'POINT(106.7 10.8)',
            4326,
            'axis-order=long-lat'
        )
    );

Query distance to a target point:

    SET @origin = ST_GeomFromText(
        'POINT(106.69 10.79)',
        4326,
        'axis-order=long-lat'
    );

    SELECT
        place_id,
        place_name,
        ST_Distance(location, @origin, 'metre') AS distance_m
    FROM places
    ORDER BY distance_m, place_id
    LIMIT 10;

This query makes the unit explicit and uses `place_id` as a deterministic tie-breaker. Still, it may evaluate distance across many rows; on large tables, add a candidate filtering step and inspect the execution plan.

### 12.1. Filter Candidates First, Compute Distance Second

A practical query pattern:

1. Filter by tenant, status, or business region using a B-tree index.
2. Use a spatial predicate / bounding rectangle to narrow candidates.
3. Compute `ST_Distance()` on the remaining candidates.
4. Order by distance and unique key.

Example:

    SELECT
        place_id,
        place_name,
        ST_Distance(location, @origin, 'metre') AS distance_m
    FROM places
    WHERE tenant_id = 10
      AND status = 'ACTIVE'
    ORDER BY distance_m, place_id
    LIMIT 20;

When running radius searches with a spatial index, build an MBR or spatial relation predicate, then confirm true distance with `ST_Distance()`. A bounding rectangle only filters candidates; the corners of a rectangle can lie outside the radius circle, so exact distance filtering must follow.

### 12.2. Avoid Per-Row SRID Transformations in WHERE

Avoid transforming every row in a spatial column at query time when data can be normalized ahead of time. For example:

    WHERE ST_Distance(
        ST_Transform(location, 4326),
        @origin
    ) < 1000

A per-row transformation expression prevents the optimizer from using a spatial index on the base column. Normalize storage to one consistent SRS or preprocess data beforehand.

## 13. Input Preconditions and Common Distance Errors

Before calling a distance function, verify:

- Are the geometries valid and well-formed?
- Is the SRID defined?
- Do all geometries share the same SRS?
- Are longitude/latitude within valid ranges?
- Are the geometry types supported by the function?
- Does the unit exist in `ST_UNITS_OF_MEASURE`?
- Does the SRS define a linear length unit?

### 13.1. Checking SRIDs

    SELECT
        id,
        ST_SRID(location) AS srid
    FROM places
    WHERE id <= 20;

### 13.2. Checking Geometry Validity

    SELECT
        id,
        ST_IsValid(location) AS is_valid
    FROM places;

`ST_IsValid()` checks OGC geometric validity. It does not replace checks for SRID, axis order, or domain meaning of coordinates.

### 13.3. Checking Units

    SELECT UNIT_NAME, UNIT_TYPE
    FROM INFORMATION_SCHEMA.ST_UNITS_OF_MEASURE
    WHERE UNIT_NAME IN ('metre', 'foot', 'kilometre');

If a unit does not appear, do not pass it to `ST_Distance()`.

### 13.4. Common Error Conditions

| Condition | Error / Behavior |
|---|---|
| Two geometries have different SRIDs | `ER_GIS_DIFFERENT_SRIDS` |
| SRID missing from data dictionary | `ER_SRS_NOT_FOUND` |
| Unsupported unit | `ER_UNIT_NOT_FOUND` |
| Linear unit passed with SRID 0 | `ER_GEOMETRY_IN_UNKNOWN_LENGTH_UNIT` |
| Longitude/latitude out of range | Longitude/latitude out-of-range error |
| `ST_Distance_Sphere` given a projected SRS | `ER_NOT_IMPLEMENTED_FOR_PROJECTED_SRS` |
| `ST_Distance_Sphere` given an unsupported geometry type | Corresponding `NOT IMPLEMENTED` error |
| Non-positive radius | `ER_NONPOSITIVE_RADIUS` |

## 14. Real-World Scenario: Delivery Within a 5 km Radius

Suppose an application needs to find drivers within 5 km of a pickup point. The table stores WGS 84 coordinates:

    CREATE TABLE driver (
        driver_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
        tenant_id BIGINT UNSIGNED NOT NULL,
        driver_name VARCHAR(120) NOT NULL,
        status ENUM('ONLINE', 'OFFLINE', 'BUSY') NOT NULL,
        location POINT NOT NULL SRID 4326,
        SPATIAL INDEX sx_driver_location (location),
        INDEX ix_driver_tenant_status (tenant_id, status)
    ) ENGINE=InnoDB;

Define the pickup point:

    SET @pickup = ST_GeomFromText(
        'POINT(106.7 10.8)',
        4326,
        'axis-order=long-lat'
    );

Basic query:

    SELECT
        driver_id,
        driver_name,
        ST_Distance(location, @pickup, 'metre') AS distance_m
    FROM driver
    WHERE tenant_id = 10
      AND status = 'ONLINE'
      AND ST_Distance(location, @pickup, 'metre') <= 5000
    ORDER BY distance_m, driver_id
    LIMIT 20;

This query expresses the business rule accurately, yet you should not assume the optimizer uses the spatial index for `ST_Distance(...) <= 5000`. With many drivers, add a candidate filter step that leverages a spatial index or precomputed bounding box, then confirm exact geodetic distance.

Never multiply raw latitude/longitude degree differences by a single constant as an exact replacement for geodetic calculations across all locations. If using an approximate bounding box, compute bounds carefully in latitude/longitude, account for high latitudes and the antimeridian, and confirm results with `ST_Distance()`.

## 15. Choosing a Measurement Model by Business Requirement

| Problem | Suggested SRS | Function / Technique | Notes |
|---|---|---|---|
| Global GPS coordinates | Geographic, usually WGS 84 (4326) | `ST_Distance` | Geodetic on ellipsoid |
| Quick proximity search for nearby points, spherical model acceptable | Geographic or SRID 0 per special rule | `ST_Distance_Sphere` | Point/MultiPoint, meters |
| Regional surveying in a suitable projection | Projected SRS | `ST_Distance` | SRS length unit |
| Factory floor plan | Cartesian SRS with explicit unit | `ST_Distance` | Planar distance |
| Mixed-SRID GIS dataset | Normalize to common SRS | `ST_Transform` then `ST_Distance` | Do not merely relabel with `ST_SRID` |
| Finding objects within an area | SRID-restricted column + `SPATIAL` index | MBR/spatial predicate, then exact distance | Bounding box filters candidates only |

The SRS must reflect how data was collected and how the business measures. Never choose EPSG:4326 for every task just because it is the default GPS SRID; if high-accuracy local measurement is needed, an appropriate projected SRS may be better.

## 16. Hands-On Lab: Comparing SRID 0, Geographic, and Sphere

Run in a test schema.

### Step 1: Create Two Cartesian Points

    SET @c1 = ST_GeomFromText('POINT(1 1)', 0);
    SET @c2 = ST_GeomFromText('POINT(4 5)', 0);

    SELECT
        ST_SRID(@c1) AS srid,
        ST_Distance(@c1, @c2) AS coordinate_distance;

Expect a distance of `5` coordinate units, not meters.

### Step 2: Request Meters with SRID 0

    SELECT ST_Distance(@c1, @c2, 'metre');

Observe the unknown length unit error. Explain why MySQL cannot convert automatically.

### Step 3: Create Two WGS 84 Points

    SET @g1 = ST_GeomFromText(
        'POINT(106.7 10.8)',
        4326,
        'axis-order=long-lat'
    );

    SET @g2 = ST_GeomFromText(
        'POINT(106.71 10.8)',
        4326,
        'axis-order=long-lat'
    );

### Step 4: Compare ST_Distance and ST_Distance_Sphere

    SELECT
        ST_Distance(@g1, @g2) AS ellipsoid_m,
        ST_Distance_Sphere(@g1, @g2) AS sphere_m;

The two results are close but not identical because one measures on an ellipsoid while the other uses a spherical model.

### Step 5: Test Unit Conversion

    SELECT
        ST_Distance(@g1, @g2, 'metre') AS distance_m,
        ST_Distance(@g1, @g2, 'foot') AS distance_ft,
        ST_Distance(@g1, @g2, 'kilometre') AS distance_km;

Check the conversion ratios and query `ST_UNITS_OF_MEASURE` to verify unit names.

### Step 6: Trigger an SRID Mismatch Error

    SET @p3857 = ST_GeomFromText(
        'POINT(11886500 1220000)',
        3857
    );

    SELECT ST_Distance(@g1, @p3857);

Observe the differing-SRID error. Then:

    SET @p4326 = ST_Transform(@p3857, 4326);
    SELECT ST_Distance(@g1, @p4326);

### Step 7: Verify Coordinate Axes

    SELECT
        ST_AsText(@g1),
        ST_Longitude(@g1),
        ST_Latitude(@g1),
        ST_SRID(@g1);

Recreate the same location using `axis-order=srid-defined` and `axis-order=long-lat` with matching inputs; verify both representations produce the exact same location.

## 17. Common Pitfalls

- Assuming every numeric coordinate is in meters.
- Using SRID 0 for longitude/latitude, calling `ST_Distance`, and treating the result as meters.
- Calling `ST_Distance_Sphere` on a projected SRS.
- Calling `ST_Distance_Sphere` on a `Polygon` or `LineString`.
- Passing `degree` as the `unit` argument of `ST_Distance`.
- Inventing unit names without checking `ST_UNITS_OF_MEASURE`.
- Forgetting that input geometries must share the same SRS.
- Treating `ST_SRID` as if it transforms coordinates.
- Calling `ST_Transform` without verifying that source/target SRSs are supported.
- Swapping longitude/latitude inconsistently with the SRS axis order.
- Treating EPSG:3857 as globally accurate for distance measurement.
- Creating a spatial index on a nullable column or one without a fixed SRID.
- Assuming the optimizer always uses a spatial index whenever `ST_Distance` appears in `WHERE`.
- Using bounding-rectangle results as final without an exact distance check.
- Failing to validate out-of-range longitude/latitude values.
- Failing to check for mixed SRIDs before adding an SRID restriction.

## 18. Pre-Deployment Checklist

- Identified the SRS type: Cartesian, projected, or geographic.
- Identified the SRID of all input geometries.
- Confirmed the SRID exists in `INFORMATION_SCHEMA.ST_SPATIAL_REFERENCE_SYSTEMS`.
- Standardized longitude/latitude vs. SRS-defined axis order.
- Verified longitude/latitude lie within valid bounds.
- Selected `ST_Distance` or `ST_Distance_Sphere` based on accuracy requirements.
- Determined output unit and verified the unit name in `ST_UNITS_OF_MEASURE`.
- Avoided linear unit conversion on SRID 0.
- Used `ST_Transform` when converting geometries between SRSs.
- Did not use `ST_SRID` as a substitute for coordinate transformation.
- Verified geometry types supported by the distance function.
- Declared spatial columns `NOT NULL` with a fixed SRID when a `SPATIAL` index is needed.
- Checked execution plans instead of assuming spatial index usage.
- Used bounding boxes as candidate filters and exact distance as confirmation.
- Tested boundary data, long-distance pairs, and high-latitude points.
- Documented SRS, units, and axis-order rules in the API/schema contract.

## 19. References

- MySQL 8.4 Reference Manual — Spatial Reference System Support: https://dev.mysql.com/doc/refman/8.4/en/spatial-reference-systems.html
- MySQL 8.4 Reference Manual — Spatial Data Types: https://dev.mysql.com/doc/refman/8.4/en/spatial-type-overview.html
- MySQL 8.4 Reference Manual — Functions That Create Geometry Values from WKT: https://dev.mysql.com/doc/refman/8.4/en/gis-wkt-functions.html
- MySQL 8.4 Reference Manual — Spatial Relation Functions That Use Object Shapes (ST_Distance): https://dev.mysql.com/doc/refman/8.4/en/spatial-relation-functions-object-shapes.html
- MySQL 8.4 Reference Manual — Spatial Convenience Functions (ST_Distance_Sphere): https://dev.mysql.com/doc/refman/8.4/en/spatial-convenience-functions.html
- MySQL 8.4 Reference Manual — INFORMATION_SCHEMA.ST_UNITS_OF_MEASURE: https://dev.mysql.com/doc/refman/8.4/en/information-schema-st-units-of-measure-table.html
- MySQL 8.4 Reference Manual — Creating Spatial Indexes: https://dev.mysql.com/doc/refman/8.4/en/creating-spatial-indexes.html
- MySQL 8.4 Reference Manual — Spatial Operator Functions (ST_Transform): https://dev.mysql.com/doc/refman/8.4/en/spatial-operator-functions.html

Distance is meaningful only when geometries use the proper SRS and units are interpreted accurately. `ST_Distance()` measures according to the SRS, performs geodetic calculations on geographic SRSs, and supports MySQL-recognized linear units. `ST_Distance_Sphere()` returns meters on a spherical model and accepts only `Point`/`MultiPoint` on supported SRSs. SRID 0 is a unitless plane; `ST_SRID()` only updates metadata, whereas `ST_Transform()` transforms coordinates. Before computing, verify SRID, axis order, geometry type, unit, and transformation support; for performance, use a spatial index to filter candidates and confirm with exact distance calculations.
