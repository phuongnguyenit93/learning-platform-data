# Axis Order, Longitude/Latitude, and Handling SRID 4326

When storing geographic coordinates in MySQL, the two numbers of a point can end up swapped even though both are valid numbers. A frequent cause is that applications commonly write longitude before latitude, whereas the EPSG:4326 reference system defines axes in latitude-then-longitude order. By default, MySQL follows the axis order defined in the Spatial Reference System (SRS) when parsing or writing WKT.

To work accurately, distinguish three concepts:

- **SRID/CRS** specifies which coordinate reference system the coordinates belong to—for example, SRID 4326 is WGS 84.
- **Axis order** specifies which axis each component in a coordinate pair represents—for example, latitude then longitude, or longitude then latitude.
- **Coordinate transformation** recalculates coordinate values to convert from one reference system to another.

Setting an SRID does not swap longitude/latitude and does not transform coordinates. This lesson walks through reading the EPSG:4326 definition, specifying axis order explicitly with WKT, verifying coordinates using geographic functions, and avoiding confusion when exchanging data between MySQL and mapping applications.

## 1. SRID and Spatial Reference System

An SRID is the identifier of a Spatial Reference System. An SRS describes how coordinates are interpreted: coordinate system type, axes, measurement units, datum, and related parameters.

A number pair such as `(105.8, 21.0)` is not enough to identify a location. You must know:

- Whether those two values are longitude/latitude or planar X/Y coordinates.
- Which reference system they were measured in.
- Whether the units are degrees, meters, or another unit.
- Which axis order applies when reading and writing the data.

### 1.1. SRID 0 and SRID 4326

MySQL uses SRID 0 for the default Cartesian coordinate system, unbound to any specific geographic reference system. Values are typically interpreted as planar coordinates in units defined by application convention.

SRID 4326 corresponds to the WGS 84 geographic reference system, widely used for GPS data and global mapping. Coordinates are angles in degrees. Under the EPSG:4326 axis definition, the axis order is:

1. Latitude, North/South direction.
2. Longitude, East/West direction.

Key point: many APIs, mapping libraries, and exchange formats instead use longitude before latitude. Both conventions describe the same location, but the order of the two values is reversed.

### 1.2. SRID Is Not Axis Order

SRID 4326 defines the reference system and its axis definition. The `axis-order` option controls how certain MySQL functions interpret or serialize WKT coordinates. That option does not change the geometry's SRID.

For example, the following two expressions can describe the same location:

~~~sql
-- Order matching EPSG:4326 axis definition: latitude, longitude
ST_GeomFromText('POINT(21.0278 105.8342)', 4326)

-- Order commonly used in applications: longitude, latitude
ST_GeomFromText(
    'POINT(105.8342 21.0278)',
    4326,
    'axis-order=long-lat'
)
~~~

In this example, both forms represent a point near Hanoi. The second form explicitly declares that the incoming WKT string puts longitude before latitude.

## 2. Why Is EPSG:4326 Easy to Mix Up?

A geographic coordinate is typically written in one of two orders:

| Convention | First Component | Second Component | Example Point Near Hanoi |
|---|---|---|---|
| EPSG:4326 per SRS axis order | Latitude | Longitude | `(21.0278, 105.8342)` |
| Longitude/latitude common in APIs and GeoJSON | Longitude | Latitude | `(105.8342, 21.0278)` |

If an application sends longitude before latitude while MySQL parses in SRS axis order, the first value is treated as latitude. When longitude exceeds 90 degrees, that value falls outside the valid latitude range and raises an error. In some regions, both numbers fall within the valid range of both axes, so the data is silently accepted at the wrong location.

### 2.1. Axis-Swap Example

Suppose an application sends:

~~~text
longitude = 105.8342
latitude  = 21.0278
~~~

This is longitude/latitude order. If passed verbatim into WKT with SRID 4326 without specifying axis order:

~~~sql
SELECT ST_GeomFromText('POINT(105.8342 21.0278)', 4326);
~~~

By default, MySQL parses in the SRS axis order. `105.8342` is treated as latitude and exceeds the valid latitude bounds. The correct approach when input is longitude/latitude is:

~~~sql
SELECT ST_GeomFromText(
    'POINT(105.8342 21.0278)',
    4326,
    'axis-order=long-lat'
);
~~~

### 2.2. Why You Cannot Rely on Looking at Two Numbers Alone

A point like `(10.5, 20.5)` falls inside valid numeric bounds under either interpretation:

- Latitude `10.5`, longitude `20.5`.
- Longitude `10.5`, latitude `20.5`.

Both interpretations yield two different locations that are each numerically valid. Therefore, geometry validity checks alone cannot catch every swapped-axis bug. Maintain an explicit data contract and verify against a known reference point.

## 3. MySQL's axis-order Option

MySQL's WKT read/write functions accept the `axis-order` option to control coordinate ordering. Common values:

| Value | Meaning |
|---|---|
| `srid-defined` | Use the axis order defined in the SRS; this is the default |
| `long-lat` | Interpret or export longitude before latitude |
| `lat-long` | Interpret or export latitude before longitude |

For EPSG:4326, `srid-defined` corresponds to latitude/longitude.

### 3.1. Reading WKT in Longitude/Latitude Order

~~~sql
SET @hanoi = ST_GeomFromText(
    'POINT(105.8342 21.0278)',
    4326,
    'axis-order=long-lat'
);
~~~

The third parameter to `ST_GeomFromText()` specifies the order of the two values in the input WKT string.

### 3.2. Reading WKT in SRS-Defined Axis Order

~~~sql
SET @hanoi_srs_order = ST_GeomFromText(
    'POINT(21.0278 105.8342)',
    4326,
    'axis-order=srid-defined'
);
~~~

For EPSG:4326, this string places latitude before longitude. You can omit the third argument if you want the default `srid-defined` behavior.

### 3.3. Reading WKT Explicitly in Latitude/Longitude Order

~~~sql
SET @hanoi_lat_lon = ST_GeomFromText(
    'POINT(21.0278 105.8342)',
    4326,
    'axis-order=lat-long'
);
~~~

This example matches the axis order defined for EPSG:4326. Specifying the option explicitly is helpful when code should document the data contract right at the conversion boundary.

### 3.4. Exporting WKT in the Desired Order

`ST_AsText()` accepts the `axis-order` option to format the output:

~~~sql
SELECT
    ST_AsText(@hanoi) AS srs_defined_order,
    ST_AsText(@hanoi, 'axis-order=long-lat') AS longitude_first,
    ST_AsText(@hanoi, 'axis-order=lat-long') AS latitude_first;
~~~

When exported as `srid-defined`, EPSG:4326 outputs latitude before longitude. When exported as `long-lat`, longitude appears before latitude. This lets you produce WKT matching the contract expected by downstream consumers.

### 3.5. Stay Consistent Between Reads and Writes

If the application sends longitude/latitude, pass `long-lat` when parsing WKT. If the application consumes WKT, pass the expected order explicitly when exporting. Never rely on an implicit default on one side while assuming the other side uses the same convention.

## 4. Inspecting Coordinates with Geographic Functions

For a `POINT` with a geographic SRID, MySQL provides functions to read longitude and latitude directly. Use them to inspect coordinate semantics instead of guessing with `ST_X()` or `ST_Y()`.

~~~sql
SELECT
    ST_SRID(@hanoi) AS srid,
    ST_Longitude(@hanoi) AS longitude,
    ST_Latitude(@hanoi) AS latitude,
    ST_AsText(@hanoi, 'axis-order=long-lat') AS wkt_long_lat;
~~~

Expected output:

| Expression | Approximate Value |
|---|---:|
| `srid` | `4326` |
| `longitude` | `105.8342` |
| `latitude` | `21.0278` |
| `wkt_long_lat` | `POINT(105.8342 21.0278)` |

### 4.1. Longitude and Latitude Have Distinct Domains

For SRID 4326:

- Longitude ranges from `-180` to `180` degrees.
- Latitude ranges from `-90` to `90` degrees.

Negative values indicate West for longitude or South for latitude. Positive values indicate East or North.

Domain checks catch some swapped-axis errors, though not all. Small number pairs can satisfy both ranges; in those cases, verify against known reference points.

### 4.2. Using ST_Longitude() and ST_Latitude()

~~~sql
SELECT
    ST_Longitude(@hanoi),
    ST_Latitude(@hanoi);
~~~

These two functions directly reflect the geographic meaning of the coordinates. They require a `POINT` input with an appropriate geographic SRS. Do not call them on Cartesian geometries or non-`POINT` geometries.

### 4.3. Be Careful with ST_X() and ST_Y()

`ST_X()` and `ST_Y()` return a point's X and Y coordinate components. In geographic reference systems whose axis order differs from conventional X/Y, do not assume X is always longitude and Y is always latitude.

When your goal is to retrieve longitude/latitude of a geographic point, prefer `ST_Longitude()` and `ST_Latitude()`. When working with planar coordinates, use X/Y as defined by the Cartesian system.

## 5. Assigning SRID vs. Transforming Coordinate Systems

One of the gravest mistakes in spatial data handling is treating SRID assignment as a coordinate transformation. These two operations have completely different meanings.

### 5.1. ST_SRID() Only Assigns or Reads the SRS Identifier

`ST_SRID(geometry)` returns the geometry's SRID. The two-argument form `ST_SRID(geometry, srid)` assigns a new SRID to the geometry.

Assigning an SRID tells MySQL that existing values should be interpreted under the new reference system. It does not recalculate or change coordinate units.

For example, a geometry currently carrying SRID 0 whose values were actually recorded in EPSG:4326 latitude/longitude order can be tagged with SRID 4326:

~~~sql
SET @point_without_srs = ST_GeomFromText('POINT(21.0278 105.8342)');
SET @point_tagged = ST_SRID(@point_without_srs, 4326);

SELECT
    ST_SRID(@point_tagged) AS srid,
    ST_Longitude(@point_tagged) AS longitude,
    ST_Latitude(@point_tagged) AS latitude;
~~~

This example is only valid if the initial numbers genuinely represent latitude `21.0278` and longitude `105.8342` in EPSG:4326. If the source data used another coordinate system, merely assigning SRID 4326 causes MySQL to misinterpret the location.

### 5.2. ST_Transform() Transforms Coordinates

`ST_Transform(geometry, target_srid)` converts coordinates from the source SRS to the target SRS when MySQL has the required definition and transformation. Unlike `ST_SRID()`, this function recalculates the coordinate values.

Example converting a WGS 84 point to Web Mercator:

~~~sql
SET @hanoi_4326 = ST_GeomFromText(
    'POINT(105.8342 21.0278)',
    4326,
    'axis-order=long-lat'
);

SET @hanoi_3857 = ST_Transform(@hanoi_4326, 3857);

SELECT
    ST_SRID(@hanoi_4326) AS source_srid,
    ST_AsText(@hanoi_4326, 'axis-order=long-lat') AS source_wkt,
    ST_SRID(@hanoi_3857) AS target_srid,
    ST_AsText(@hanoi_3857) AS target_wkt;
~~~

EPSG:3857 is the Web Mercator projected coordinate system, typically expressing positions in meters on a plane. The transformed coordinate values will differ markedly from the degree-based longitude/latitude pair.

### 5.3. Choosing the Right Operation

| Situation | Operation |
|---|---|
| Geometry already holds valid EPSG:4326 coordinates but its SRID is 0 | Assign SRID 4326 after verifying the source |
| Geometry has SRID 4326 and needs WKT exported as longitude/latitude | `ST_AsText()` with `axis-order=long-lat` |
| Input data is WKT in longitude/latitude order | `ST_GeomFromText()` with `axis-order=long-lat` |
| Geometry is in EPSG:3857 and needs WGS 84 coordinates | `ST_Transform(..., 4326)` |
| Changing only the SRID to make numbers look like another CRS | Do not do this; identify the source CRS and transform |

You cannot reliably transform a geometry without knowing its true source coordinate system. Before calling `ST_Transform()`, confirm that the current SRID accurately reflects the underlying data.

### 5.4. Units Do Not Change When Assigning an SRID

EPSG:4326 coordinates are angular degrees. EPSG:3857 coordinates are planar meters. Assigning SRID 3857 to numbers representing degrees does not turn them into meters. Only a proper coordinate transformation produces values in the target system.

## 6. Storing SRID 4326 Points in a Table

Starting in MySQL 8.0.13, you can restrict the SRID directly on a geometry column. An SRID-restricted column guarantees that all stored values belong to the same SRS.

~~~sql
CREATE TABLE places (
    place_id BIGINT UNSIGNED NOT NULL,
    name VARCHAR(200) NOT NULL,
    location POINT NOT NULL SRID 4326,
    PRIMARY KEY (place_id),
    SPATIAL INDEX spx_places_location (location)
) ENGINE = InnoDB;
~~~

The `NOT NULL` and SRID restriction requirements matter for spatial index usage in InnoDB. An unrestricted geometry column can contain data from multiple coordinate systems; in that case spatial comparisons become inconsistent and the spatial index cannot be used as expected.

### 6.1. Inserting Coordinates from a Longitude/Latitude Application

~~~sql
INSERT INTO places (place_id, name, location)
VALUES (
    1001,
    'Hanoi reference point',
    ST_GeomFromText(
        'POINT(105.8342 21.0278)',
        4326,
        'axis-order=long-lat'
    )
);
~~~

Because the input puts longitude before latitude, the statement specifies `long-lat`. In application code, bind the WKT string as a prepared statement parameter rather than interpolating user input into SQL.

### 6.2. Reading Coordinates with Geographic Semantics

~~~sql
SELECT
    place_id,
    name,
    ST_SRID(location) AS srid,
    ST_Longitude(location) AS longitude,
    ST_Latitude(location) AS latitude,
    ST_AsText(location, 'axis-order=long-lat') AS wkt_long_lat
FROM places;
~~~

The output returns the SRID, longitude, latitude, and WKT matching the application contract. You never need to parse WKT strings manually to extract longitude and latitude.

### 6.3. Updating a Location

~~~sql
UPDATE places
SET location = ST_GeomFromText(
    'POINT(106.7009 10.7769)',
    4326,
    'axis-order=long-lat'
)
WHERE place_id = 1001;
~~~

This example updates the location to a point near Ho Chi Minh City. The input still uses longitude before latitude. The `WHERE` clause targets the primary key to update the exact row.

### 6.4. Verifying SRID and Geometry Type

~~~sql
SELECT
    place_id,
    ST_GeometryType(location) AS geometry_type,
    ST_SRID(location) AS srid,
    ST_IsValid(location) AS is_valid
FROM places;
~~~

Expected results are `POINT`, SRID `4326`, and a valid geometry. `ST_IsValid()` checks geometric validity; it does not prove that data was entered with the right axis order or true geographic location.

## 7. Viewing SRS Definitions in MySQL

MySQL stores supported Spatial Reference Systems in the data dictionary. You can query SRS definitions via `INFORMATION_SCHEMA.ST_SPATIAL_REFERENCE_SYSTEMS`:

~~~sql
SELECT
    SRS_ID,
    SRS_NAME,
    ORGANIZATION,
    ORGANIZATION_COORDSYS_ID,
    DEFINITION
FROM INFORMATION_SCHEMA.ST_SPATIAL_REFERENCE_SYSTEMS
WHERE SRS_ID IN (0, 4326, 3857);
~~~

Key columns:

- `SRS_ID`: the SRID used by MySQL.
- `SRS_NAME`: name of the reference system.
- `ORGANIZATION`: defining organization, usually `EPSG` for corresponding SRIDs.
- `ORGANIZATION_COORDSYS_ID`: coordinate system identifier within that organization.
- `DEFINITION`: SRS definition, including axis and coordinate system details.

### 7.1. Verifying SRIDs of Stored Data

~~~sql
SELECT
    ST_SRID(location) AS srid,
    COUNT(*) AS row_count
FROM places
GROUP BY ST_SRID(location);
~~~

On a column restricted to SRID 4326, only that SRID should appear. On unrestricted geometry columns, this query detects mixed coordinate systems.

### 7.2. Do Not Infer Axis Order Solely from the SRID Name

The name EPSG:4326 often leads developers to assume longitude/latitude immediately. Read the SRS definition or specify `axis-order` explicitly at integration boundaries. A CRS name does not force all exchange formats to share the same coordinate order.

## 8. Integrating with GeoJSON and Mapping APIs

WKT and GeoJSON follow different coordinate rules. Under the standard RFC 7946 GeoJSON convention, a 2D geographic position orders longitude before latitude:

~~~json
{
  "type": "Point",
  "coordinates": [105.8342, 21.0278]
}
~~~

For EPSG:4326, the axis order defined in the SRS is latitude/longitude. When exchanging data, never assume GeoJSON uses the same order as MySQL's default WKT.

### 8.1. Reading GeoJSON

MySQL provides `ST_GeomFromGeoJSON()` to convert GeoJSON into a geometry. Example:

~~~sql
SET @geojson = ST_GeomFromGeoJSON(
    '{"type":"Point","coordinates":[105.8342,21.0278]}',
    1,
    4326
);

SELECT
    ST_SRID(@geojson) AS srid,
    ST_Longitude(@geojson) AS longitude,
    ST_Latitude(@geojson) AS latitude,
    ST_AsGeoJSON(@geojson) AS geojson_output;
~~~

GeoJSON positions are written longitude before latitude. Follow the GeoJSON specification when exchanging data; never take a raw `coordinates` array and paste it into WKT without accounting for `axis-order`.

### 8.2. Exporting GeoJSON for Frontends

~~~sql
SELECT
    place_id,
    name,
    ST_AsGeoJSON(location) AS geometry_json
FROM places;
~~~

Mapping frontends typically expect coordinates in longitude/latitude order. When exporting GeoJSON, use the dedicated `ST_AsGeoJSON()` function rather than assembling JSON manually from `ST_X()`, `ST_Y()`, or WKT strings.

### 8.3. Integration Boundary Conventions

A clear data contract specifies:

- The API accepts two named fields: `longitude` and `latitude`.
- GeoJSON array ordering is `[longitude, latitude]`.
- The SRID stored in the database is `4326`.
- Input WKT uses `axis-order=long-lat` if the application sends longitude before latitude.
- When returning WKT to the application, choose `axis-order` explicitly.
- When returning GeoJSON, use `ST_AsGeoJSON()`.
- Never pass bare coordinate numbers without an SRID or CRS specification in internal data flows.

Explicit field names are usually safer than an undocumented two-element array. If an API requires arrays, the API documentation must state the coordinate order.

## 9. Validating Data Before and After Writes

Incorrect coordinates can be stored without causing SQL errors, especially when both values lie inside valid bounds. Combine structural checks, range checks, and location cross-checks.

### 9.1. Application-Layer Checks

Before writing:

1. Confirm both longitude and latitude are present.
2. Parse them as numeric types, rejecting empty strings or non-finite values.
3. Verify longitude is between `-180` and `180`.
4. Verify latitude is between `-90` and `90`.
5. Confirm whether the coordinate source uses WGS 84 / EPSG:4326 or another CRS.
6. Build WKT/geometries with explicit axis order.

Range checks do not replace CRS verification. A pair of numbers within both valid bounds can still place a point in the wrong location if the axes are swapped.

### 9.2. Database-Layer Checks

For a `location` column restricted to SRID 4326:

~~~sql
SELECT
    place_id,
    ST_SRID(location) AS srid,
    ST_Longitude(location) AS longitude,
    ST_Latitude(location) AS latitude,
    ST_IsValid(location) AS geometry_valid
FROM places
WHERE ST_SRID(location) <> 4326
   OR ST_Longitude(location) NOT BETWEEN -180 AND 180
   OR ST_Latitude(location) NOT BETWEEN -90 AND 90
   OR ST_IsValid(location) = 0;
~~~

When the column is declared with `SRID 4326`, the SRID check is mainly helpful when auditing legacy tables or external imports. If a column allows multiple SRIDs, group and process each CRS separately before comparing or transforming.

### 9.3. ST_IsValid() Does Not Catch Every Domain Error

A `POINT` can be geometrically valid yet land in the wrong country or city due to swapped axes, wrong SRID, or bad source data. OGC validity does not verify business semantics of a location.

For critical datasets, validate using known control points:

- A point with verified longitude/latitude.
- A point near longitude or latitude boundaries if the system handles edge regions.
- A point with negative values on one or both axes.
- One sample point from each external integration source.

Cross-check `ST_Longitude()`, `ST_Latitude()`, and plot on a test map.

### 9.4. Detecting Axis-Swapped Data in Legacy Tables

There is no universal query that detects every swapped-axis point with certainty. You can screen suspicious rows based on the geographic bounding box your application serves.

For example, if data should only lie within Vietnam, you can run a preliminary filter on expected longitude and latitude bounds:

~~~sql
SELECT
    place_id,
    ST_Longitude(location) AS longitude,
    ST_Latitude(location) AS latitude
FROM places
WHERE ST_Longitude(location) NOT BETWEEN 102 AND 110
   OR ST_Latitude(location) NOT BETWEEN 8 AND 24;
~~~

This is merely a bounding-region quality filter for expected data, not a universal validity rule for all applications. Adjust the bounds to your domain coverage and review outliers before modifying records.

## 10. SRID and Distance Measurements

Axis order and SRID affect how MySQL interprets geometries in spatial operations. Two geometries need compatible reference systems for meaningful comparisons.

### 10.1. Measurement Units Depend on the SRS

In Cartesian systems, distance is computed in the coordinate system's units. In supported geographic SRSs, `ST_Distance()` returns distance in meters. Never treat every distance result as meters if a geometry has SRID 0 or uses a planar coordinate system with different units.

Example:

~~~sql
SELECT ST_Distance(
    ST_GeomFromText(
        'POINT(105.8342 21.0278)',
        4326,
        'axis-order=long-lat'
    ),
    ST_GeomFromText(
        'POINT(105.85 21.03)',
        4326,
        'axis-order=long-lat'
    )
) AS distance_meters;
~~~

For two points both in SRID 4326, MySQL treats them as geographic coordinates and `ST_Distance()` returns meters on versions supporting geographic distance calculations.

### 10.2. Do Not Manually Swap Axes Before Every Operation

Once a geometry has been constructed with the right SRID and axis order, spatial operations operate on that geometry as-is. Never swap values again simply because a function name mentions X or Y.

To inspect input coordinates, use `ST_Longitude()` and `ST_Latitude()`. To change CRS, use `ST_Transform()`. To format WKT, use `ST_AsText()` with the desired `axis-order`.

### 10.3. Avoid Comparing Geometries with Different SRIDs

Do not mix SRID 4326 and SRID 3857 geometries in the same distance or spatial relationship operation without transforming them to a common reference system. Before calling `ST_Distance()`, `ST_Contains()`, or `ST_Intersects()`, verify both SRIDs and coordinate semantics.

## 11. MySQL Version Differences to Note

Geographic SRS support expanded significantly in MySQL 8.0. If your application targets multiple versions, establish the minimum required version before relying on axis-order syntax and functions.

| Capability | MySQL Version Milestone |
|---|---|
| Geographic SRS support and SRID-aware operations beyond SRID 0 | MySQL 8.0 |
| `axis-order` option in relevant WKT/WKB functions | MySQL 8.0.12 |
| `ST_Longitude()` and `ST_Latitude()` | MySQL 8.0.12 |
| SRID-restricted geometry columns and `ST_Transform()` | MySQL 8.0.13 |
| `ST_Distance()` support for geographic SRSs | MySQL 8.0.18 |

These milestones indicate feature availability; always check the Reference Manual for your exact deployed version, especially when using custom SRSs or specific CRS transformations.

### 11.1. Do Not Assume Older Servers Understand axis-order

If your application supports MySQL versions earlier than 8.0.12, do not assume the `axis-order` option in WKT/WKB functions will work. Build a version-compatible conversion layer or upgrade the server before using that syntax.

### 11.2. Checking Deployment Capabilities

~~~sql
SELECT VERSION() AS mysql_version;

SELECT
    SRS_ID,
    SRS_NAME
FROM INFORMATION_SCHEMA.ST_SPATIAL_REFERENCE_SYSTEMS
WHERE SRS_ID IN (4326, 3857);
~~~

Check both the server version and the required SRS entries. Even when a version supports a function, the source data or specific reference system might still lack a supported transformation path.

## 12. Common Pitfalls and How to Handle Them

### 12.1. Passing Longitude Before Latitude Without Specifying axis-order

**Symptom:** the statement reports out-of-range coordinates or points appear at the wrong location.

**Cause:** MySQL uses the axis order defined in EPSG:4326, whereas application input is longitude/latitude.

**Solution:** pass `axis-order=long-lat` to the WKT parser or normalize input under an explicit contract.

### 12.2. Exporting WKT and Seeing the Application Flip Coordinates

**Symptom:** points are stored accurately, but when read back, the application places markers elsewhere.

**Cause:** `ST_AsText()` defaults to SRS axis order, which may differ from the order expected by the API.

**Solution:** call `ST_AsText()` with `axis-order=long-lat` if the API expects longitude before latitude, or return `longitude` and `latitude` as two separate fields.

### 12.3. Using ST_SRID() Instead of ST_Transform()

**Symptom:** coordinate numbers stay identical even though the SRID changed; measurements or map positions are wrong.

**Cause:** `ST_SRID()` only assigns the reference system identifier. It does not transform coordinates or units.

**Solution:** identify the true source SRS and call `ST_Transform()` to the target SRID. Assign an SRID directly only when you are certain the existing coordinates are already expressed in that SRS.

### 12.4. Confusing SRID 4326 with a Meter-Based Coordinate System

**Symptom:** the application treats longitude/latitude values as planar X/Y in meters or computes distance by subtracting raw coordinates.

**Cause:** EPSG:4326 uses angular degrees, not meters.

**Solution:** use spatial operations supporting geographic SRSs, or transform to an appropriate projected system when planar coordinates are needed. Never multiply degrees by a fixed constant to approximate meters everywhere.

### 12.5. Using ST_X()/ST_Y() to Populate Longitude/Latitude APIs

**Symptom:** two API fields named `longitude` and `latitude` contain swapped values due to the SRS axis definition.

**Cause:** X/Y are generic coordinate component names; do not assume they always mean longitude/latitude across all SRSs.

**Solution:** use `ST_Longitude()` and `ST_Latitude()` for geographic `POINT` values.

### 12.6. Valid Geometry in the Wrong Location

**Symptom:** `ST_IsValid()` returns `1`, yet the marker lands in the wrong region.

**Cause:** `ST_IsValid()` checks geometric validity, not coordinate contracts, CRS accuracy, or business location.

**Solution:** verify SRID, axis order, expected geographic bounds, and cross-check against known reference points.

### 12.7. Writing a Geometry to a Column Restricted to a Different SRID

**Symptom:** `INSERT` or `UPDATE` fails with an SRID mismatch error.

**Cause:** the column is declared to accept only one SRID (e.g., 4326), while the input geometry carries SRID 0 or 3857.

**Solution:** verify the source SRS. If the coordinates are genuinely EPSG:4326, assign the right SRID; if they belong to another CRS, apply the appropriate transformation. Never change the SRID solely to bypass a write error.

### 12.8. Unsupported Transformation

**Symptom:** `ST_Transform()` raises an error or cannot perform the conversion.

**Cause:** missing source/target SRS, SRID 0 lacking a geographic definition, or transformation unsupported by MySQL in that environment.

**Solution:** confirm both SRSs exist in the data dictionary, determine the true source SRID, and check transformation support in your MySQL version.

### 12.9. Mixing GeoJSON and WKT Without Normalization

**Symptom:** the same point differs between API GeoJSON input and WKT imports.

**Cause:** GeoJSON typically uses longitude/latitude, whereas MySQL's default WKT for EPSG:4326 follows SRS axis order.

**Solution:** use `ST_GeomFromGeoJSON()` for GeoJSON and pass `axis-order` explicitly when reading or writing WKT.

## 13. Standard Workflow for Geographic Data

A consistent pipeline prevents axis errors from the start:

1. **Identify the source:** know whether data comes from GPS, GeoJSON, WKT, a GIS system, or a projected system.
2. **Identify the CRS:** confirm the true SRID of source coordinates rather than guessing from number magnitudes.
3. **Determine axis order:** document whether the source sends longitude/latitude or SRS axis order.
4. **Validate bounds:** verify longitude and latitude fall within valid bounds for EPSG:4326.
5. **Convert on input:** use the proper parser and explicit `axis-order`.
6. **Enforce SRID in schema:** if the entire column uses one CRS, declare an SRID restriction and pick the right geometry subtype.
7. **Read back to verify:** check `ST_SRID()`, `ST_Longitude()`, `ST_Latitude()`, and exported WKT per the contract.
8. **Ground-truth check:** verify several control points on a map.
9. **Transform when needed:** use `ST_Transform()` when converting to another CRS for analysis or rendering.
10. **Monitor data quality:** detect mixed SRIDs, out-of-region coordinates, and drift across integration sources.

### 13.1. Read/Write Pipeline Example

~~~sql
-- 1. Construct geometry from application data sending longitude/latitude.
SET @incoming = ST_GeomFromText(
    'POINT(105.8342 21.0278)',
    4326,
    'axis-order=long-lat'
);

-- 2. Verify semantics before writing.
SELECT
    ST_SRID(@incoming) AS srid,
    ST_Longitude(@incoming) AS longitude,
    ST_Latitude(@incoming) AS latitude;

-- 3. Write geometry into a column restricted to SRID 4326.
INSERT INTO places (place_id, name, location)
VALUES (2001, 'Control point', @incoming);

-- 4. Read using the longitude/latitude contract.
SELECT
    ST_Longitude(location) AS longitude,
    ST_Latitude(location) AS latitude,
    ST_AsText(location, 'axis-order=long-lat') AS wkt
FROM places
WHERE place_id = 2001;
~~~

This pipeline highlights the conversion boundary between application data and MySQL geometries. In production application code, use prepared statements to bind WKT and other parameters.

## 14. Hands-On Practice

### 14.1. Distinguishing Axis Orders

Create two geometry variables representing the same point near Hanoi:

- Latitude/longitude WKT with `axis-order=lat-long`.
- Longitude/latitude WKT with `axis-order=long-lat`.

Compare `ST_SRID()`, `ST_Longitude()`, `ST_Latitude()`, and `ST_AsText()` under both output orders.

### 14.2. Finding Axis-Swap Errors

Try passing `POINT(105.8342 21.0278)` into SRID 4326 without specifying `axis-order`. Observe the server error or interpretation. Then add `long-lat` and compare.

### 14.3. Assigning SRID vs. Transforming SRID

Create an SRID 0 geometry whose coordinates are known to be EPSG:4326. Assign SRID 4326 with `ST_SRID()` and read longitude/latitude. Next, transform it to SRID 3857 with `ST_Transform()`. Explain why the two operations produce different results.

### 14.4. Storing Points with an SRID Restriction

Create a `places` table with a `POINT NOT NULL SRID 4326` column and a `SPATIAL INDEX`. Insert a point using `ST_GeomFromText()` with `long-lat`. Attempt to insert SRID 0 and SRID 3857 geometries to observe SRID mismatch errors.

### 14.5. Parsing GeoJSON

Use `ST_GeomFromGeoJSON()` to parse a `Point` with `[longitude, latitude]` coordinates. Inspect `ST_Longitude()` and `ST_Latitude()`, then export back with `ST_AsGeoJSON()`.

### 14.6. Region-Based Data Quality Check

Write a query finding points outside the expected coordinate bounds of a business region. Explain why this is only a domain quality check, not CRS confirmation.

### 14.7. Inspecting SRS Definitions

Query `INFORMATION_SCHEMA.ST_SPATIAL_REFERENCE_SYSTEMS` to inspect SRS 4326 and 3857. Determine units and axis order from the definition instead of guessing from the name.

### 14.8. Designing an API Contract

Write a brief specification for an API accepting `longitude` and `latitude`, storing `POINT SRID 4326`, and returning GeoJSON. Document array order, SRID, valid value ranges, and missing-data handling.

## 15. Pre-Release Checklist

- [ ] Confirmed the true CRS/SRID of the data source.
- [ ] Confirmed source and target axis order.
- [ ] Did not confuse EPSG:4326 with the longitude/latitude convention of APIs.
- [ ] Passed explicit `axis-order=long-lat` or `lat-long` when reading WKT where needed.
- [ ] Used `ST_AsText()` with the appropriate `axis-order` when exporting WKT.
- [ ] Used `ST_Longitude()` and `ST_Latitude()` to read geographic coordinates.
- [ ] Did not assume `ST_X()` is always longitude and `ST_Y()` is always latitude.
- [ ] Validated longitude in `-180..180` and latitude in `-90..90` for SRID 4326.
- [ ] Distinguished `ST_SRID()` from `ST_Transform()`.
- [ ] Did not assign a new SRID to fake a CRS transformation.
- [ ] Geometry column has an SRID restriction matching stored data.
- [ ] Spatial index is created on a column meeting InnoDB's requirements.
- [ ] Verified SRID, geometry type, and validity after writing.
- [ ] Cross-checked control points on a map or reference source.
- [ ] Established GeoJSON longitude/latitude rules.
- [ ] Verified MySQL version and required function availability.
- [ ] Verified measurement units of spatial calculations.
- [ ] Tested boundary values, negative coordinates, and every integration source.

## Conclusion

EPSG:4326 is the WGS 84 reference system whose SRS-defined axis order is latitude followed by longitude. Many applications and GeoJSON instead send longitude before latitude. In MySQL, use `axis-order` to parse or export WKT according to your contract; use `ST_Longitude()` and `ST_Latitude()` to read geographic values; use `ST_SRID()` to inspect/assign SRIDs and `ST_Transform()` to perform true coordinate transformations.

SRID, axis order, and coordinate transformation are three separate concerns. A geometrically valid shape can still hold coordinates that are wrong for the business domain. Verify the source CRS, normalize order at integration boundaries, enforce SRID restrictions in the schema when appropriate, and verify against known reference points before shipping spatial data to production.
