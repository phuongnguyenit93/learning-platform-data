# Creating Geometries from WKT/WKB and Inspecting Geometric Structure

MySQL provides spatial data types such as `POINT`, `LINESTRING`, `POLYGON`, and `MULTI*` types. To bring data from applications or GIS files into these columns, two common exchange formats are WKT (Well-Known Text) and WKB (Well-Known Binary). WKT represents geometries as human-readable text; WKB represents the same structure as compact binary data suited for transmission and exchange storage.

In the `DATABASE_MYSQL` module, this lesson covers creating geometries with `ST_GeomFromText` and `ST_GeomFromWKB`, exporting data with `ST_AsText` and `ST_AsWKB`, attaching the right SRID, and understanding coordinate axis order. After creating geometries, you will inspect geometry type, component counts, bounding envelopes, point counts, and validity using MySQL spatial functions.

## 1. Geometry, WKT, and WKB

A geometry is a spatial object with structure and a coordinate reference system. WKT and WKB are two representations of that object:

| Format | Characteristics | Common Usage |
|---|---|---|
| WKT | Text containing geometry type name and coordinates | Debugging, logging, manual input, human-readable exchange |
| WKB | Binary byte stream encoding geometric structure | Binary transfer between application and database, GIS exchange |
| Geometry in MySQL | Spatial value stored in a spatial-typed column | Spatial querying and analysis inside the database |

WKT and WKB are not column types you declare instead of `POINT` or `POLYGON`. They are input/output formats; columns in MySQL are still declared using a specific geometry type or the generic `GEOMETRY` type.

Example of the same point:

~~~text
POINT(10 20)
~~~

WKT can be read directly as a point with two coordinates. WKB contains the type code, byte order, and coordinate values in binary; you should not build WKB manually by concatenating raw bytes without knowing the encoding specification.

## 2. Common Geometry Types

MySQL supports basic geometry types and collection types:

| Type | Meaning | WKT Example |
|---|---|---|
| `POINT` | A single location | `POINT(10 20)` |
| `LINESTRING` | A sequence of points connected as a path | `LINESTRING(0 0, 5 5, 10 5)` |
| `POLYGON` | A region with an outer ring and optional holes | `POLYGON((0 0, 10 0, 10 10, 0 10, 0 0))` |
| `MULTIPOINT` | Multiple points | `MULTIPOINT((1 1), (2 2))` |
| `MULTILINESTRING` | Multiple paths | `MULTILINESTRING((0 0, 1 1), (2 2, 3 3))` |
| `MULTIPOLYGON` | Multiple polygon regions | `MULTIPOLYGON(((0 0, 4 0, 4 4, 0 4, 0 0)))` |
| `GEOMETRYCOLLECTION` | Collection of geometries, possibly mixed types | `GEOMETRYCOLLECTION(POINT(1 1), LINESTRING(0 0, 2 2))` |

`POINT` has dimension 0, `LINESTRING` has dimension 1, and `POLYGON` has dimension 2. `MULTI*` types group multiple objects of the same type; `GEOMETRYCOLLECTION` can hold different types.

## 3. WKT Structure

WKT typically begins with the geometry type name, followed by a coordinate list or component list. A two-dimensional coordinate has two numbers in the axis order defined by the reference system.

`POINT` example:

~~~text
POINT(106.70098 10.77689)
~~~

`LINESTRING` example:

~~~text
LINESTRING(106.7000 10.7760, 106.7010 10.7770, 106.7020 10.7780)
~~~

`POLYGON` example:

~~~text
POLYGON((0 0, 10 0, 10 10, 0 10, 0 0))
~~~

A polygon has an exterior ring; if it has holes, add interior rings:

~~~text
POLYGON(
    (0 0, 10 0, 10 10, 0 10, 0 0),
    (2 2, 2 4, 4 4, 4 2, 2 2)
)
~~~

Each polygon ring must be closed: the last coordinate must match the first. A ring usually requires at least four coordinate positions because the starting point is repeated at the end. The first ring is the exterior ring; subsequent rings are interior rings (holes).

WKT uses commas to separate points or components. Never place a comma between the two coordinates of the same point. Malformed WKT strings are rejected by the constructor during parsing.

## 4. Creating Geometries with ST_GeomFromText

`ST_GeomFromText` converts a WKT string into a geometry:

~~~sql
ST_GeomFromText(wkt [, srid [, options]])
~~~

Parameters:

- `wkt`: valid WKT text.
- `srid`: Spatial Reference System Identifier; if omitted, the geometry typically receives SRID 0.
- `options`: parsing options, such as `axis-order` for reference systems whose axis order differs from the source data.

Create a Cartesian point:

~~~sql
SET @point = ST_GeomFromText('POINT(10 20)');

SELECT
    ST_GeometryType(@point) AS geometry_type,
    ST_SRID(@point) AS srid,
    ST_AsText(@point) AS wkt;
~~~

Omitting the SRID causes the geometry to use SRID 0. SRID 0 typically denotes an unspecified Cartesian system; do not use SRID 0 for geographic longitude/latitude if you need geographic calculations.

You can create `LINESTRING` and `POLYGON` similarly:

~~~sql
SET @route = ST_GeomFromText(
    'LINESTRING(0 0, 5 5, 10 5)',
    0
);

SET @area = ST_GeomFromText(
    'POLYGON((0 0, 10 0, 10 10, 0 10, 0 0))',
    0
);

SELECT ST_AsText(@route), ST_AsText(@area);
~~~

The examples above use Cartesian coordinates to focus on structure. For geographic data, select the SRID and axis order that match your data source.

## 5. SRID Identifies the Coordinate Reference System

The SRID indicates which reference system the coordinates belong to. Two geometries with identical numbers but different SRIDs can represent different locations because the reference systems and units differ.

Key notes:

- SRID 0 is typically used for Cartesian data without a specific geographic reference system.
- SRID 4326 represents the WGS 84 geographic system, commonly used for GPS data.
- Other projected planar systems may use meters or units defined by the SRS.

Do not guess an SRID solely from coordinate numbers. You must know the coordinate system, units, and axis order of the data source.

Inspect the SRID:

~~~sql
SELECT
    ST_SRID(@point) AS point_srid,
    ST_SRID(@route) AS route_srid;
~~~

When storing into an SRID-restricted column, the input geometry must carry the matching SRID. Never assign a new SRID solely to bypass schema validation: changing the SRID label does not convert coordinates to the new reference system. When a coordinate system conversion is required, use an appropriate coordinate transformation such as `ST_Transform` when supported by the SRS and server version.

## 6. Coordinate Axis Order and SRID 4326

A common mistake is swapping longitude/latitude order. Under the EPSG:4326 axis definition, the order is latitude followed by longitude. Many map APIs and GeoJSON payloads instead send longitude followed by latitude.

By default, MySQL interprets coordinates in the axis order defined by the SRS. For WKT data coming from a longitude-latitude source, you can specify the `axis-order` option:

The `axis-order` option in GIS functions is supported starting in MySQL 8.0.3. On older versions, do not assume options can be passed as shown below; normalize coordinate order at the application layer and check documentation for your exact running version.

~~~sql
-- Following SRID 4326 axis order: latitude, longitude.
SET @point_lat_lon = ST_GeomFromText(
    'POINT(10.77689 106.70098)',
    4326
);

-- Source supplies longitude first, latitude second.
SET @point_lon_lat = ST_GeomFromText(
    'POINT(106.70098 10.77689)',
    4326,
    'axis-order=long-lat'
);
~~~

When exporting WKT for an application expecting longitude-latitude:

~~~sql
SELECT ST_AsText(
    @point_lon_lat,
    'axis-order=long-lat'
) AS point_wkt;
~~~

The `axis-order` option controls how coordinate order is interpreted; it does not change the reference system or perform a projection. Standardize on one convention across the application, GIS files, and database. Verify a few known points before bulk-loading data.

## 7. Storing Geometries in a Table

Example table storing geographic points:

~~~sql
CREATE TABLE places (
    place_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    place_name VARCHAR(150) NOT NULL,
    location POINT NOT NULL SRID 4326,
    PRIMARY KEY (place_id)
) ENGINE=InnoDB;
~~~

The `SRID 4326` attribute restricts geometries in the column to that reference system. SRID-restricted spatial column syntax is supported starting in MySQL 8.0.13. On older versions, check support and syntax before applying; do not assume every version enforces the same level of restriction.

Insert a point using WKT:

~~~sql
INSERT INTO places (place_name, location)
VALUES (
    'Office',
    ST_GeomFromText(
        'POINT(106.70098 10.77689)',
        4326,
        'axis-order=long-lat'
    )
);
~~~

Read it back:

~~~sql
SELECT
    place_id,
    place_name,
    ST_SRID(location) AS srid,
    ST_AsText(location, 'axis-order=long-lat') AS location_wkt
FROM places;
~~~

If the column is declared with `SRID 4326` but the input carries SRID 0 or another SRID, the write fails the constraint. Always construct geometries with the right SRID in the constructor.

## 8. Creating Geometries from WKB with ST_GeomFromWKB

WKB is binary data, not a WKT string. Use `ST_GeomFromWKB` to parse it:

~~~sql
ST_GeomFromWKB(wkb [, srid [, options]])
~~~

Example generating WKB from an existing geometry and reading it back:

~~~sql
SET @original_geometry = ST_GeomFromText(
    'LINESTRING(0 0, 5 5, 10 5)',
    0
);

SET @wkb_value = ST_AsWKB(@original_geometry);

SET @geometry_from_wkb = ST_GeomFromWKB(
    @wkb_value,
    ST_SRID(@original_geometry)
);

SELECT ST_AsText(@geometry_from_wkb) AS round_trip_wkt;
~~~

`ST_AsWKB` returns binary WKB. `@wkb_value` holds the binary byte string passed back into `ST_GeomFromWKB`.

Standard WKB does not carry an SRID like MySQL's internal geometry metadata. Therefore, when exchanging WKB, the application must pass the SRID separately or include the SRID in protocol metadata. Never assume `ST_AsWKB` embeds the SRID inside the payload.

## 9. Displaying WKB as Hexadecimal

WKB can contain non-printable bytes. To inspect it in logs or documentation, use `HEX`:

~~~sql
SELECT HEX(ST_AsWKB(@original_geometry)) AS wkb_hex;
~~~

If you have a valid WKB hex string and want to convert it back to binary before parsing:

~~~sql
SET @wkb_hex = HEX(ST_AsWKB(@original_geometry));
SET @wkb_binary = UNHEX(@wkb_hex);

SELECT ST_AsText(
    ST_GeomFromWKB(@wkb_binary, 0)
) AS geometry_text;
~~~

`HEX` is only a byte representation for human viewing or text-only transport. When calling `ST_GeomFromWKB`, you must pass actual binary data; never pass raw hex characters without converting via `UNHEX`.

In applications, prefer prepared statements with binary parameter binding to avoid unnecessary text conversions. Validate encoding and payload size when receiving data from clients.

## 10. Exporting Geometries with ST_AsText and ST_AsWKB

Two export functions:

~~~sql
ST_AsText(geometry [, options])
ST_AsWKB(geometry [, options])
~~~

`ST_AsText` converts a geometry to human-readable WKT. `ST_AsWKB` converts it to binary WKB. For geographic SRIDs with a specific axis order, you can pass `axis-order` on WKT/WKB export to match the exchange protocol.

Example:

~~~sql
SELECT
    ST_AsText(location, 'axis-order=long-lat') AS wkt_value,
    HEX(ST_AsWKB(location, 'axis-order=long-lat')) AS wkb_hex
FROM places;
~~~

WKT output is convenient for debugging. WKB output is suited for applications consuming binary data. Using `HEX` in an API increases payload size over raw binary because each byte expands into two hexadecimal characters.

## 11. WKT/WKB Round-Trip

A round-trip exports a geometry to an exchange format and reconstructs the geometry from that format. WKT example:

~~~sql
SET @source_geometry = ST_GeomFromText(
    'POLYGON((0 0, 10 0, 10 10, 0 10, 0 0))',
    0
);

SET @source_wkt = ST_AsText(@source_geometry);

SET @copy_from_wkt = ST_GeomFromText(
    @source_wkt,
    ST_SRID(@source_geometry)
);

SELECT
    ST_AsText(@source_geometry) AS source_wkt,
    ST_AsText(@copy_from_wkt) AS copied_wkt,
    ST_IsValid(@copy_from_wkt) AS copied_is_valid;
~~~

WKB round-trip:

~~~sql
SET @source_wkb = ST_AsWKB(@source_geometry);
SET @copy_from_wkb = ST_GeomFromWKB(
    @source_wkb,
    ST_SRID(@source_geometry)
);

SELECT
    ST_AsText(@copy_from_wkb) AS copied_wkt,
    ST_SRID(@copy_from_wkb) AS copied_srid;
~~~

When comparing results, verify geometry type, SRID, coordinates, and validity. Never use raw WKT string equality as the sole criterion for geometric equivalence because number formatting or representation order may differ.

## 12. Inspecting Geometry Type and SRID

Core functions:

~~~sql
SELECT
    ST_GeometryType(location) AS geometry_type,
    ST_SRID(location) AS srid,
    ST_Dimension(location) AS dimension
FROM places;
~~~

- `ST_GeometryType` returns the geometry type such as `POINT`, `LINESTRING`, or `POLYGON`.
- `ST_SRID` returns the reference system identifier.
- `ST_Dimension` returns the spatial dimension of the geometry.

Check the geometry type before calling type-specific functions. For example, `ST_ExteriorRing` and `ST_NumInteriorRings` apply to `POLYGON`; `ST_NumPoints` applies to `LINESTRING`. Calling a function on the wrong geometry type may return `NULL` or raise an error depending on the function and version.

## 13. Inspecting Point Counts, Components, and Polygon Rings

For `LINESTRING`:

~~~sql
SET @route = ST_GeomFromText(
    'LINESTRING(0 0, 5 5, 10 5)',
    0
);

SELECT ST_NumPoints(@route) AS point_count;
~~~

For `POLYGON`:

~~~sql
SET @area = ST_GeomFromText(
    'POLYGON((0 0, 10 0, 10 10, 0 10, 0 0),
             (2 2, 2 4, 4 4, 4 2, 2 2))',
    0
);

SELECT
    ST_NumInteriorRings(@area) AS hole_count,
    ST_AsText(ST_ExteriorRing(@area)) AS outer_ring;
~~~

For `GEOMETRYCOLLECTION`:

~~~sql
SET @collection = ST_GeomFromText(
    'GEOMETRYCOLLECTION(POINT(1 1), LINESTRING(0 0, 2 2))',
    0
);

SELECT
    ST_GeometryType(@collection) AS collection_type,
    ST_NumGeometries(@collection) AS component_count,
    ST_GeometryType(ST_GeometryN(@collection, 1)) AS first_component_type;
~~~

`ST_NumGeometries` counts components in a collection or multi-geometry; `ST_GeometryN` retrieves a component by 1-based index. Structural inspection functions help detect records missing components or having the wrong type relative to application requirements.

## 14. Inspecting Envelopes and Coordinate Bounds

An envelope is the smallest axis-aligned bounding rectangle enclosing the geometry:

~~~sql
SELECT
    ST_AsText(ST_Envelope(@route)) AS route_envelope
;
~~~

An envelope is useful for quickly inspecting coordinate ranges or debugging shifted coordinates. However, an envelope does not describe the exact shape of a line or region; two distinct polygons can share the same envelope.

For any geometry, you can export its envelope to check min/max coordinates in WKT. Never substitute envelope checks for topological validity checks or exact intersection tests.

## 15. Checking Validity with ST_IsValid

Syntactically valid WKT does not guarantee a topologically valid geometry. For example, a polygon with a self-intersecting ring can be represented in syntactically valid WKT yet be invalid under geometric rules.

`ST_IsValid` checks validity:

~~~sql
SELECT ST_IsValid(@area) AS is_valid;
~~~

Typical return values:

- `1`: valid geometry.
- `0`: invalid geometry.
- `SQL NULL`: input is `SQL NULL`.

Example of a bow-tie polygon with a self-intersecting ring:

~~~sql
SET @bow_tie = ST_GeomFromText(
    'POLYGON((0 0, 2 2, 0 2, 2 0, 0 0))',
    0
);

SELECT ST_IsValid(@bow_tie) AS is_valid;
~~~

This illustrates a topologically invalid polygon structure. Verify the exact behavior on your target MySQL version before relying on it in automated tests, as GIS function behavior can vary across versions and SRS types.

`ST_IsValid` is a check, not an automatic repair function. When a geometry is invalid, apply domain rules to repair or reject the data at ingestion time.

## 16. Core Validity Rules by Geometry Type

Key structural requirements:

### POINT

- Has a single coordinate position.
- Coordinates must fit within the SRS domain when using a geographic SRS.

### LINESTRING

- Has at least two points.
- Points are connected in list order.
- A self-intersecting line should not be confused with an invalid polygon; simplicity (`simple`) and validity (`valid`) are distinct checks.

### POLYGON

- Exterior ring must be closed.
- Each ring must have enough coordinate positions to form a boundary.
- Interior rings must lie inside the region bounded by the exterior ring.
- Rings must not intersect each other in ways that violate topology rules.
- A self-intersecting ring like a bow-tie is an invalid polygon.

### MULTIPOLYGON

- Each component must be a valid polygon.
- Component regions must obey MultiPolygon topology rules; polygon interiors must not overlap in ways that invalidate the object.

### GEOMETRYCOLLECTION

- Each component must be a valid geometry.
- Components may have different geometry types.
- When stored in an SRID-restricted column, component geometries must match the column's SRID.

These rules are foundational; run `ST_IsValid` on actual data rather than relying solely on successful WKT parsing.

## 17. Distinguishing Syntax Errors, SRID Errors, and Topology Errors

Three distinct error categories are often conflated:

| Error Category | Examples | Where Detected |
|---|---|---|
| Invalid WKT/WKB | Missing parentheses, malformed byte layout, missing coordinates | `ST_GeomFromText` / `ST_GeomFromWKB` constructors |
| SRID or coordinate mismatch with SRS | Column requires 4326 while geometry carries another SRID; coordinates outside SRS bounds | Constructors, column assignment, or spatial operations |
| Invalid topology | Self-intersecting polygon, interior ring outside exterior ring | `ST_IsValid` and topology checks |

Do not treat all errors the same way by arbitrarily changing the SRID or patching the WKT string. Determine whether the error stems from format, coordinate system, or geometric structure.

## 18. Safe WKT/WKB Ingestion Workflow

An ingestion pipeline can follow these steps:

1. Identify whether the incoming format is WKT or WKB.
2. Confirm the source reference system and SRID.
3. Determine the axis order; check whether the source sends latitude-longitude or longitude-latitude.
4. Parse with `ST_GeomFromText` or `ST_GeomFromWKB` using the proper SRID and options.
5. Check `ST_GeometryType` and `ST_SRID`.
6. Check structure with `ST_NumPoints`, `ST_NumGeometries`, or other type-appropriate functions.
7. Validate with `ST_IsValid`.
8. Reject invalid rows or route them to a staging area for review; never silently rewrite SRIDs.
9. Write valid geometries into a column with the appropriate type and SRID constraint.
10. Persist source metadata such as ingestion timestamp, reference system, and pipeline version if auditability is needed.

For high-volume datasets, load into a staging table first, summarize errors by category, and then promote valid records to the production table. This prevents one bad batch from halting the entire pipeline.

## 19. Prepared Statements and WKB Data from Applications

Applications should never concatenate user-supplied WKT/WKB strings directly into SQL. Use prepared statements to bind parameters:

~~~sql
INSERT INTO places (place_name, location)
VALUES (
    ?,
    ST_GeomFromWKB(?, 4326)
);
~~~

The first parameter is the place name; the second must be bound as binary WKB. If the source payload uses an axis order different from the SRID default, pass the appropriate `options` argument or normalize coordinates before sending.

With WKT:

~~~sql
INSERT INTO places (place_name, location)
VALUES (
    ?,
    ST_GeomFromText(?, 4326, 'axis-order=long-lat')
);
~~~

Prepared statements separate data from SQL syntax and prevent escaping bugs. They do not replace SRID checks, payload size limits, or geometry validity checks.

## 20. Post-Load Verification Queries

Suppose the `places` table is populated:

~~~sql
SELECT
    place_id,
    place_name,
    ST_GeometryType(location) AS geometry_type,
    ST_SRID(location) AS srid,
    ST_IsValid(location) AS is_valid,
    ST_AsText(location, 'axis-order=long-lat') AS location_wkt
FROM places;
~~~

If `location` is declared as `POINT SRID 4326`, you can run summary checks:

~~~sql
SELECT
    COUNT(*) AS total_rows,
    SUM(ST_IsValid(location) = 1) AS valid_rows,
    SUM(ST_IsValid(location) = 0) AS invalid_rows,
    SUM(ST_SRID(location) <> 4326) AS wrong_srid_rows
FROM places;
~~~

If the column already has an SRID restriction, `wrong_srid_rows` should be `0` because mismatched SRIDs are rejected on write. This audit query remains helpful when inspecting legacy tables without restrictions or data imported via another path.

## 21. Common Errors When Creating and Inspecting Geometries

| Symptom | Likely Cause | How to Handle |
|---|---|---|
| Constructor reports invalid WKT | Wrong type name, mismatched parentheses, or comma placement | Check WKT syntax and each coordinate ring |
| Geometry appears at the wrong map location | Swapped latitude/longitude | Check `axis-order` and pass the appropriate option |
| Spatial column insert fails with SRID error | Input SRID does not match column constraint | Construct geometry with the source's true SRID |
| WKB parsing fails | Hex string passed instead of binary, or truncated payload | Use `UNHEX` for hex text or bind full-length binary |
| WKT parses cleanly but `ST_IsValid` returns 0 | Invalid topology | Repair geometry per business rules or reject it |
| Polygon is invalid | Unclosed ring, self-intersection, or misplaced hole | Inspect exterior and interior rings |
| `ST_NumPoints` returns `NULL` or errors | Function called on wrong geometry type | Check `ST_GeometryType` first |
| WKB export lacks expected SRID | Standard WKB does not carry MySQL SRID metadata | Pass SRID separately on parse and in the protocol |
| Assigning a new SRID leaves location wrong | Changing metadata does not transform coordinates | Use an appropriate coordinate system transformation |
| WKT round-trip differs from original string | Different number formatting or representation order | Compare structure, SRID, and coordinates per domain rules |

## 22. Hands-On Exercises

1. Create a `POINT` from WKT and inspect `ST_GeometryType`, `ST_SRID`, and `ST_AsText`.
2. Create a `LINESTRING` from WKT and count its points with `ST_NumPoints`.
3. Create a `POLYGON` with one hole; inspect `ST_NumInteriorRings` and `ST_ExteriorRing`.
4. Create a `GEOMETRYCOLLECTION` containing a `POINT` and `LINESTRING`; count components with `ST_NumGeometries`.
5. Export a geometry to WKB, display it in `HEX`, and parse it back with `ST_GeomFromWKB`.
6. Perform WKT and WKB round-trips; compare geometry type, SRID, and `ST_IsValid` results.
7. Create a `POINT` with SRID 4326 using default `axis-order` and with `axis-order=long-lat`; verify the location against known coordinates.
8. Create a table with a `POINT SRID 4326` column; try inserting an SRID 0 geometry and observe the error.
9. Create a bow-tie polygon; check `ST_IsValid` and explain why successful WKT parsing does not guarantee valid topology.
10. Create a WKT polygon with an unclosed exterior ring; observe the parse error and distinguish it from topology errors.
11. Write a query counting valid, invalid, and wrong-SRID geometries in a staging table.
12. Design a prepared statement accepting binary WKB from an application and specify how SRID and axis order are passed.

You have completed this lesson when you can create geometries from WKT and WKB, explain the role of SRID and axis order, export data back to both exchange formats, and inspect type, components, bounding envelope, and validity before writing to production tables. Successful parsing only confirms the format is readable; inspecting structure and coordinate systems is what makes spatial data trustworthy.
