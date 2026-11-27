# Oracle Spatial: Geometry, Coordinate Systems, and Spatial Queries

Oracle Spatial stores, indexes, and queries location data inside the same Oracle Database alongside business data. A store can store coordinates, a route can store a geometric line, and a district can store a boundary polygon; SQL can then find stores within a district, routes intersecting a restricted zone, or points near an address.

The central data type is `SDO_GEOMETRY`. A geometry describes a point, line, polygon, or collection of geometric elements. However, coordinates only have meaning when you know the **coordinate reference system (CRS)**, units, datum, and interpretation rules. The pair `(106.7, 10.8)` could be longitude/latitude, planar coordinates, or a local coordinate system; if assigned the wrong SRID, distance and location results can be wrong even though the geometry is syntactically valid.

The workflow for building a spatial data layer typically includes:

1. Choosing the geometry model and CRS matching the data source.
2. Creating an `SDO_GEOMETRY` column, loading coordinates, and attaching the SRID.
3. Declaring metadata for the layer in `USER_SDO_GEOM_METADATA`.
4. Validating geometry integrity and coordinate bounds.
5. Creating a spatial index, typically an R-tree with `MDSYS.SPATIAL_INDEX_V2`.
6. Using spatial operators to filter and evaluate spatial relationships.
7. Monitoring tolerances, performance, CRS data, and updates.

This document focuses on three foundations: **geometry**, **coordinate systems**, and **spatial queries** in Oracle Spatial 19c.

## 1. Oracle Spatial and the Spatial Data Model

### 1.1 What Is Spatial Data?

Spatial data describes the location, shape, and relationships of objects in space. Examples:

| Business Object | Commonly Used Geometry | Question Answerable |
|---|---|---|
| ATMs, stores, bus stops | Point | Which point is closest to the customer? |
| Streets, pipelines, bus routes | LineString | Which route intersects a construction zone? |
| Districts, wards, conservation areas | Polygon | Which ward does this address belong to? |
| Multiple disjoint regions of an area | MultiPolygon | Which areas belong to the same province? |
| Terrain or building models | 3D surface/solid | Do objects intersect in 3D space? |

Oracle Spatial supports storing geometries in the object-relational `SDO_GEOMETRY` type, along with operators, procedures, and functions to analyze location and relationships.

### 1.2 Layer, Geometry, and Element

The data model has three levels:

- **Layer:** the set of geometries in a column of a table, such as `STORES.LOCATION`.
- **Geometry:** the geometry of a single object, such as a store's location or a district's boundary.
- **Element:** a component of a geometry, such as a point, a line, or a ring of a polygon.

A layer usually has a primary key to identify each row. Each geometry is stored in a table row inside a column of type `SDO_GEOMETRY`.

### 1.3 Vector and Raster Geometry

Oracle Spatial supports many kinds of spatial data. `SDO_GEOMETRY` primarily describes vector data including points, lines, regions, surfaces, and solids. Raster data, point clouds, topologies, networks, or graphs have specialized models and APIs; do not force every type of spatial data into a polygon or an SDO_GEOMETRY column.

## 2. The SDO_GEOMETRY Data Type

### 2.1 Object Structure

Oracle defines `SDO_GEOMETRY` with five attributes:

~~~sql
CREATE TYPE sdo_geometry AS OBJECT (
    sdo_gtype      NUMBER,
    sdo_srid       NUMBER,
    sdo_point      SDO_POINT_TYPE,
    sdo_elem_info  SDO_ELEM_INFO_ARRAY,
    sdo_ordinates  SDO_ORDINATE_ARRAY
);
~~~

| Attribute | Role |
|---|---|
| `SDO_GTYPE` | Indicates dimensionality, measure dimension position (if any), and geometry type |
| `SDO_SRID` | Coordinate system identifier attached to the geometry; NULL means no CRS attached |
| `SDO_POINT` | Simple point structure with X, Y, Z; used when the geometry is a simple point |
| `SDO_ELEM_INFO` | Describes how to split and interpret elements in the ordinates array |
| `SDO_ORDINATES` | Sequence of vertex coordinate values |

A simple point can use `SDO_POINT` and leave the element/ordinate arrays NULL. For lines, polygons, multi-geometries, or complex geometries, the information typically resides in `SDO_ELEM_INFO` and `SDO_ORDINATES`.

### 2.2 SDO_GTYPE in the DLTT Pattern

`SDO_GTYPE` is a four-digit number structured as:

~~~text
D L T T
| | | |
| | +-- TT: geometry type
| +---- L: measure dimension position (LRS), or 0 if none
+------ D: number of dimensions
~~~

Examples:

| GTYPE | Interpretation |
|---:|---|
| 2001 | 2D Point |
| 2002 | 2D LineString |
| 2003 | 2D Polygon |
| 2004 | 2D GeometryCollection |
| 2005 | 2D MultiPoint |
| 2006 | 2D MultiLine/MultiCurve |
| 2007 | 2D MultiPolygon/MultiSurface |
| 3001 | 3D Point |
| 3002 | 3D LineString |
| 3003 | 3D Polygon |
| 3008 | 3D Solid |
| 3009 | 3D MultiSolid |

The first digit `D` is the number of ordinates per vertex: 2, 3, or 4. For example, `2003` is a 2D polygon; `3001` is a 3D point. The digit `L` indicates the measure position in an LRS geometry, not a regular spatial dimension. Geometries within the same layer must share matching dimensionality consistent with metadata and the spatial index.

### 2.3 2D Point

A simple point can be constructed as follows:

~~~sql
SDO_GEOMETRY(
    2001,
    4326,
    SDO_POINT_TYPE(106.7000, 10.7800, NULL),
    NULL,
    NULL
)
~~~

In the SRID 4326 example, X is longitude and Y is latitude per SDO coordinate conventions for this data. Confirm the axis order of your input source; do not automatically assume every interchange format uses the same order.

### 2.4 LineString

A line consisting of connected vertices:

~~~sql
SDO_GEOMETRY(
    2002,
    4326,
    NULL,
    SDO_ELEM_INFO_ARRAY(1, 2, 1),
    SDO_ORDINATE_ARRAY(
        106.7000, 10.7800,
        106.7050, 10.7850,
        106.7100, 10.7900
    )
)
~~~

The triplet `(1, 2, 1)` means the element starts at the 1st ordinate, ETYPE 2 is a line, and interpretation 1 is a sequence of straight line segments connecting consecutive points.

### 2.5 Polygon

A 2D polygon can be represented by a closed ring:

~~~sql
SDO_GEOMETRY(
    2003,
    4326,
    NULL,
    SDO_ELEM_INFO_ARRAY(1, 1003, 1),
    SDO_ORDINATE_ARRAY(
        106.7000, 10.7800,
        106.7100, 10.7800,
        106.7100, 10.7900,
        106.7000, 10.7900,
        106.7000, 10.7800
    )
)
~~~

A polygon must be closed: the last coordinate of the ring matches the first coordinate. Per Oracle rules, the exterior ring (ETYPE 1003) must be ordered counter-clockwise; interior rings (ETYPE 2003, holes) must be ordered clockwise.

### 2.6 Polygon with Holes

A polygon can have one exterior ring and multiple interior rings. The exterior ring is declared first, followed by interior rings. Structural example:

~~~sql
SDO_ELEM_INFO_ARRAY(
    1, 1003, 1,   -- exterior ring
    11, 2003, 1   -- interior ring (hole)
)
~~~

Offsets point to the starting position of each element in `SDO_ORDINATES`. When constructing a polygon with holes, verify ring ordering, rotation direction, closure, and that interior rings lie properly inside the exterior ring.

### 2.7 Rectangles and Circles

Oracle provides optimized representations for certain simple shapes. For a rectangle defined by two opposite corners, interpretation 3 can use two points:

~~~sql
SDO_GEOMETRY(
    2003,
    NULL,
    NULL,
    SDO_ELEM_INFO_ARRAY(1, 1003, 3),
    SDO_ORDINATE_ARRAY(0, 0, 10, 5)
)
~~~

For a circle, interpretation 4 uses three points to define a circle under Oracle's model:

~~~sql
SDO_GEOMETRY(
    2003,
    NULL,
    NULL,
    SDO_ELEM_INFO_ARRAY(1, 1003, 4),
    SDO_ORDINATE_ARRAY(8, 7, 10, 9, 8, 11)
)
~~~

These examples use Cartesian coordinates without an SRID. For geographic data, choose an appropriate CRS and curve model; do not infer real-world distances or areas from arbitrary planar coordinates.

### 2.8 SDO_ELEM_INFO and SDO_ORDINATES

`SDO_ELEM_INFO` is an array of three-number groups (triplets):

1. `SDO_STARTING_OFFSET`: starting position in `SDO_ORDINATES`.
2. `SDO_ETYPE`: element type.
3. `SDO_INTERPRETATION`: how to interpret the ordinate sequence or compound components.

Offsets start at **1**, not 0. A multi-element geometry has multiple triplets; the next element starts at its declared offset. Common ETYPE values:

| ETYPE | Meaning |
|---:|---|
| 1 | Point or multipoint element depending on interpretation |
| 2 | LineString |
| 1003 | Exterior polygon ring |
| 2003 | Interior polygon ring |
| 1005 / 2005 | Compound polygon exterior/interior ring |
| 1006 / 2006 | Surface element |
| 1007 | Solid element |

With ETYPE 1003/2003, interpretation 1 is typically a ring of straight line segments; interpretation 3 represents a rectangle; interpretation 4 represents a circle. Compound elements have their own triplet rules to describe consecutive subelements.

Do not manually edit `SDO_ELEM_INFO` by guessing offsets. For complex geometries, use constructors, WKT/WKB import, SDO_UTIL, or GIS tools to build valid structures, then validate using `SDO_GEOM.VALIDATE_GEOMETRY_WITH_CONTEXT`.

## 3. Coordinate Systems and SRID

### 3.1 Why Must Coordinates Be Paired with a CRS?

A CRS defines how coordinates are interpreted and how they relate to the real world. A pair of numbers could be longitude/latitude degrees, meters on a projected plane, feet in a local grid, or CAD facility coordinates. If the wrong SRID is attached, Oracle may perform transformations or compute wrong distances without knowing the source data was mislabeled.

A CRS typically specifies:

- Axes and axis order.
- Units of measurement.
- Datum/ellipsoid if geographic.
- Projection if a planar coordinate system.
- The SRID identifier used in Oracle.

### 3.2 Types of Coordinate Systems

| Type | Description | Data Examples |
|---|---|---|
| Geodetic/geographic | Angular longitude, latitude tied to an Earth datum | Longitude/latitude in WGS 84 |
| Projected | Cartesian coordinates on a plane after map projection | UTM Easting/Northing, meters |
| Cartesian/local | Local coordinate system not tied to Earth | Factory floor plans, CAD coordinates |
| 3D CRS | System with a Z axis or height per datum/vertical CRS | 3D spatial coordinates |

### 3.3 Geodetic and Projected Are Not the Same

Geodetic coordinates typically store longitude/latitude in angular units. You cannot treat one degree of longitude as always equaling a fixed distance in meters: the corresponding ground length varies with latitude. Projected coordinates represent locations on a flat plane, typically in meters or feet; planar distances are easier to compute, yet projections introduce distortion depending on region and purpose.

For global datasets, a geodetic CRS fits storing geographic positions. For local distance/area analysis, a projected CRS suited to the study region can be more convenient. Choose a CRS based on accuracy requirements and geographic extent, not simply because values look like longitude/latitude.

### 3.4 SRID in SDO_GEOMETRY

`SDO_SRID` takes values from the SRID column in `SDO_COORD_REF_SYS`. If SRID is NULL, the geometry has no CRS attached. If SRID is non-NULL, the layer's metadata must also declare the same SRID.

Example:

~~~sql
SELECT srid,
       coord_ref_sys_name,
       coord_sys_name,
       datum_name,
       geogcs_datum_name
FROM sdo_coord_ref_sys
WHERE srid IN (4326, 3857);
~~~

SRID 4326 is commonly used for WGS 84 longitude/latitude; SRID 3857 is Web Mercator projected coordinates. Never change a geometry's SRID merely by overwriting the attribute number while its ordinates remain in the old CRS.

### 3.5 Checking CRS in Oracle

~~~sql
SELECT srid,
       coord_ref_sys_name,
       coord_sys_type,
       coord_sys_name,
       datum_name,
       geogcs_datum_name
FROM sdo_coord_ref_sys
WHERE srid = :p_srid;
~~~

Exact columns may vary by release and metadata view. Query `SDO_COORD_REF_SYS`, `SDO_COORD_SYS`, `SDO_DATUMS`, and related views to inspect CRSs and datums. Cross-check against EPSG sources or your data provider's metadata.

### 3.6 Axis Order and Units

In standard SDO geometry, the first two ordinates are interpreted as X then Y. With geographic SRID 4326, point examples typically use X=longitude, Y=latitude. However, some external formats and APIs follow different axis-order rules; check data interchange specifications and convert explicitly on ingestion.

For geodetic data, Oracle distance/area calculations follow specific unit rules and accept units via the `unit` parameter. For projected/local data, units depend on the CRS. Do not compare a value of 100 against 100 meters if the actual CRS uses feet or degrees.

### 3.7 Tolerance

Tolerance represents the spatial precision Oracle uses to decide whether nearby points/lines are considered equal or touching. It is declared per dimension in `SDO_DIM_ARRAY` metadata.

- For geodetic data, tolerance is interpreted in meters.
- For non-geodetic data, tolerance uses the units of the CRS.
- A tolerance that is too large can cause distinct nearby objects to be treated as coinciding/touching or skew distance results.
- A tolerance that is too small relative to data precision can make calculations sensitive to floating-point error and trigger geometry validation errors.

Choose tolerance based on source data accuracy, business requirements, and the smallest meaningful distance. Do not copy a tolerance value from another example without checking units and precision.

### 3.8 Transforming Coordinate Systems

`SDO_CS.TRANSFORM` converts geometry coordinates from the current CRS to a target SRID:

~~~sql
SELECT SDO_CS.TRANSFORM(shape, 3857) AS shape_3857
FROM city_locations;
~~~

Ensure `shape.SDO_SRID` accurately identifies the source CRS before transforming. Transformations require valid CRS definitions and datum transformations in the database. If source data lacks a trustworthy CRS, verify the source CRS first; assigning a target SRID is not a coordinate transformation.

When two input geometries have different SRIDs:

- Spatial operators can temporarily transform the query window (the second geometry parameter) to the geometry column's CRS.
- Functions in `SDO_GEOM` taking two geometries generally require both to share the same CRS.
- If data must be stored in a unified CRS, transform before insert/update and verify the results.

## 4. Creating Tables and Spatial Metadata

### 4.1 Creating a Table with an SDO_GEOMETRY Column

~~~sql
CREATE TABLE city_locations (
    location_id NUMBER PRIMARY KEY,
    location_name VARCHAR2(100) NOT NULL,
    location_type VARCHAR2(30),
    shape SDO_GEOMETRY
);
~~~

Each geometry row is identified by the primary key `LOCATION_ID`. The geometry column may be NULL if business rules permit, yet rows needing spatial queries must hold valid geometries.

### 4.2 Declaring USER_SDO_GEOM_METADATA

Before creating a spatial index, declare dimensional metadata for the table-column pair:

~~~sql
INSERT INTO user_sdo_geom_metadata (
    table_name,
    column_name,
    diminfo,
    srid
)
VALUES (
    'CITY_LOCATIONS',
    'SHAPE',
    SDO_DIM_ARRAY(
        SDO_DIM_ELEMENT('Longitude', -180, 180, 0.05),
        SDO_DIM_ELEMENT('Latitude',   -90,  90, 0.05)
    ),
    4326
);
~~~

`DIMINFO` holds one `SDO_DIM_ELEMENT` per dimension: dimension name, lower bound, upper bound, and tolerance. The example above assumes the layer is 2D WGS 84 longitude/latitude. The tolerance of 0.05 in the example corresponds to 5 cm for geodetic data per Oracle conventions; this is illustrative only and must be chosen per application precision requirements.

Metadata is managed through `USER_SDO_GEOM_METADATA`, `ALL_SDO_GEOM_METADATA`, or `DBA_SDO_GEOM_METADATA` views. Never update internal MDSYS schema tables directly.

### 4.3 Checking Metadata

~~~sql
SELECT table_name,
       column_name,
       diminfo,
       srid
FROM user_sdo_geom_metadata
WHERE table_name = 'CITY_LOCATIONS'
  AND column_name = 'SHAPE';
~~~

Ensure metadata SRID matches geometry `SDO_SRID`. Every geometry in the same spatially indexed column must have the same SRID.

### 4.4 Loading Point Data

~~~sql
INSERT INTO city_locations (
    location_id,
    location_name,
    location_type,
    shape
)
VALUES (
    1,
    'Central Office',
    'OFFICE',
    SDO_GEOMETRY(
        2001,
        4326,
        SDO_POINT_TYPE(106.7000, 10.7800, NULL),
        NULL,
        NULL
    )
);
~~~

Coordinates are illustrative data. When loading real data, verify CRS, axis order, datum, and coordinate ranges. Swapped longitude/latitude coordinates can still fall within valid bounds in some regions, so geometric validation does not replace source quality checks.

## 5. Validating Geometries Before Querying

### 5.1 Validating a Single Geometry

~~~sql
SELECT location_id,
       SDO_GEOM.VALIDATE_GEOMETRY_WITH_CONTEXT(
           shape,
           diminfo
       ) AS validation_result
FROM city_locations c,
     user_sdo_geom_metadata m
WHERE m.table_name = 'CITY_LOCATIONS'
  AND m.column_name = 'SHAPE';
~~~

The function returns `TRUE` if the geometry is valid; otherwise it returns an error code and context identifying the offending coordinate/edge/ring. The call form taking DIMINFO also checks that the geometry lies within the declared bounds.

### 5.2 Validating an Entire Layer

You can use `SDO_GEOM.VALIDATE_LAYER_WITH_CONTEXT` to check all geometries in a layer. The procedure writes invalid rows into a pre-created result table.

~~~sql
CREATE TABLE spatial_validation_errors (
    sdo_rowid ROWID,
    result VARCHAR2(4000)
);

BEGIN
    SDO_GEOM.VALIDATE_LAYER_WITH_CONTEXT(
        'CITY_LOCATIONS',
        'SHAPE',
        'SPATIAL_VALIDATION_ERRORS'
    );
END;
/
~~~

Then read `SPATIAL_VALIDATION_ERRORS` and address each error type. Execution privileges and schema/table names must fit how the package is called in your environment.

### 5.3 Common Causes of Invalid Geometries

- Unclosed polygon.
- Exterior/interior rings with wrong orientation.
- Self-intersecting polygon.
- Two consecutive vertices identical or closer than tolerance.
- ETYPE inconsistent with GTYPE.
- Incorrect offset or interpretation in ELEM_INFO.
- Geometry outside bounds declared in DIMINFO.
- Geometry dimensionality mismatching layer metadata.

Oracle recommends validating geometries before running spatial operations. Some errors can be repaired with `SDO_UTIL.RECTIFY_GEOMETRY`; others require fixing the source data or transforming via a controlled process. Never auto-rectify production data without backing up originals and verifying geometric meaning afterward.

## 6. Spatial Indexes and the Two-Tier Query Model

### 6.1 R-Tree Spatial Indexes

The default spatial index is typically an R-tree. An R-tree organizes geometry bounding rectangles to quickly locate candidates that may interact with a query window.

Create index:

~~~sql
CREATE INDEX city_locations_spx
ON city_locations(shape)
INDEXTYPE IS MDSYS.SPATIAL_INDEX_V2;
~~~

`SPATIAL_INDEX_V2` is Oracle's recommended choice for new spatial indexes in modern releases because it supports system-managed indexes and simplifies administration, especially with partitioning. Check prerequisites, privileges, tablespaces, and version before creating.

### 6.2 Key Prerequisites of Spatial Indexes

- The geometry column must have matching metadata.
- Every geometry in an indexed column must share the same SRID.
- Dimensionality of metadata, geometries, and index must match.
- Geometries should be valid before querying.
- If index creation fails, the index may be left in an invalid state; address the error, drop, and recreate after fixing the cause.

### 6.3 Primary Filter and Secondary Filter

Oracle uses a two-tier query model:

1. **Primary filter:** uses the spatial index and minimum bounding rectangles (MBRs) to find candidates that could interact. This step is fast but can return false positives because an MBR does not always match the true shape.
2. **Secondary filter:** checks exact geometric relationships on candidate geometries, such as whether the actual polygon intersects the query polygon.

`SDO_FILTER` performs only the primary filter. `SDO_RELATE` and other relationship operators can use the spatial index to filter candidates and then evaluate exact geometric relationships per the mask.

### 6.4 Do Not Confuse Bounding Boxes with Actual Geometry

A curve or concave polygon can have a bounding rectangle much larger than the actual shape. Two MBRs can intersect even when the two actual geometries do not intersect. If business logic requires exact relationships, use `SDO_RELATE` or an appropriate operator rather than relying solely on `SDO_FILTER`.

## 7. Spatial Operators and Spatial Queries

Spatial operators are used in the `WHERE` clause and return the string `'TRUE'` or `'FALSE'`. When comparing, use exact uppercase `= 'TRUE'`. Oracle recommends using spatial operators instead of equivalent functions when an operator meets requirements because operators can leverage spatial indexes.

### 7.1 SDO_FILTER: Finding Candidates by MBR

~~~sql
SELECT location_id,
       location_name
FROM city_locations c
WHERE SDO_FILTER(
          c.shape,
          SDO_GEOMETRY(
              2003,
              4326,
              NULL,
              SDO_ELEM_INFO_ARRAY(1, 1003, 3),
              SDO_ORDINATE_ARRAY(106.68, 10.76, 106.73, 10.81)
          )
      ) = 'TRUE';
~~~

`SDO_FILTER` checks only the primary filter (MBR). The result is a candidate set; geometries might not actually intersect. Use it when fast coarse filtering is needed or when the primary filter suffices for business needs. If exact results are required, add a secondary filter.

### 7.2 SDO_RELATE: Checking Topological Relationships

`SDO_RELATE` checks topological relationships between a column geometry and a query geometry. For example, finding areas interacting with a query window:

~~~sql
SELECT location_id,
       location_name
FROM city_locations c
WHERE SDO_RELATE(
          c.shape,
          :query_geometry,
          'mask=ANYINTERACT'
      ) = 'TRUE';
~~~

Common masks:

| Mask | General Meaning |
|---|---|
| ANYINTERACT | The two geometries have any spatial interaction |
| CONTAINS | The first geometry contains the second geometry |
| INSIDE | The first geometry lies inside the second geometry |
| COVEREDBY / COVERS | Topological covering relationships |
| EQUAL | Both geometries are topologically equal |
| TOUCH | Boundaries touch without interiors intersecting per topology definition |
| OVERLAPBDYINTERSECT | Boundaries intersect per corresponding mask |
| OVERLAPBDYDISJOINT | Interiors intersect while boundaries have a disjoint relationship per mask |

Masks are directional: `CONTAINS(A,B)` is not equivalent to `CONTAINS(B,A)`. Check topological definitions for the exact order of `geometry1` and `geometry2`.

### 7.3 SDO_WITHIN_DISTANCE: Searching Within a Radius

Example finding points within 5 km of a query point:

~~~sql
SELECT location_id,
       location_name
FROM city_locations c
WHERE SDO_WITHIN_DISTANCE(
          c.shape,
          :query_point,
          'distance=5 unit=KM'
      ) = 'TRUE';
~~~

The query geometry must have an appropriate CRS. For geodetic data, the default distance unit is meters; you can specify `unit=KM`, `unit=MILE`, or other Oracle-supported units. Since the parameter is a string, decimal points must use a period regardless of NLS locale, e.g. `'distance=2.5 unit=KM'`.

`SDO_WITHIN_DISTANCE` defines distance between two extended geometries (lines/polygons) as the shortest distance between points on the two surfaces; two adjacent polygons have distance 0. The operator requires a spatial index on the geometry column; for geodetic data, the index must be an R-tree.

### 7.4 SDO_NN: Nearest Neighbors

`SDO_NN` finds the geometries nearest to a query geometry. Example retrieving the 5 nearest stores:

~~~sql
SELECT c.location_id,
       c.location_name,
       SDO_NN_DISTANCE(1) AS distance_value
FROM city_locations c
WHERE SDO_NN(
          c.shape,
          :query_point,
          'sdo_num_res=5',
          1
      ) = 'TRUE'
ORDER BY distance_value;
~~~

The final parameter `1` of `SDO_NN` must match the parameter of `SDO_NN_DISTANCE(1)`. For geodetic data, returned distances default to meters; for non-geodetic data, units follow the CRS. `SDO_NN` requires a spatial index on the geometry column.

If additional attribute conditions exist, such as only returning stores of type `PHARMACY`, use `sdo_batch_size` so Oracle finds enough nearest candidates satisfying the condition:

~~~sql
SELECT *
FROM (
    SELECT c.location_id,
           c.location_name,
           SDO_NN_DISTANCE(1) AS distance_value
    FROM city_locations c
    WHERE SDO_NN(
              c.shape,
              :query_point,
              'sdo_batch_size=30',
              1
          ) = 'TRUE'
      AND c.location_type = 'PHARMACY'
    ORDER BY distance_value
)
WHERE ROWNUM <= 5;
~~~

Do not replace `sdo_batch_size` with `sdo_num_res=5` in examples having a store-type filter and assume you will always get the 5 nearest pharmacies. `sdo_num_res` limits the nearest-neighbor geometries before other attribute predicates apply; it may return fewer than 5 or zero rows.

### 7.5 SDO_JOIN: Spatial Join Between Two Layers

A spatial join compares geometries from two tables. Example finding interacting area and road pairs:

~~~sql
SELECT p.area_id,
       r.road_id
FROM service_areas p,
     road_segments r
WHERE SDO_RELATE(
          r.shape,
          p.shape,
          'mask=ANYINTERACT'
      ) = 'TRUE';
~~~

This is a spatial join using a relational operator. For specialized two-layer spatial joins, `SDO_JOIN` is the dedicated operator for joining by topological relationships. Ensure CRS and dimensionality of both layers are compatible.

### 7.6 SDO_POINTINPOLYGON

`SDO_POINTINPOLYGON` fits cases where a table has two X/Y columns and needs to check whether points fall inside polygons. If data is already stored in `SDO_GEOMETRY`, operators such as `SDO_RELATE` or `SDO_CONTAINS` are generally more natural.

### 7.7 Combining SDO_FILTER with SDO_RELATE

In some complex queries, both steps can be written explicitly:

~~~sql
SELECT c.location_id,
       c.location_name
FROM city_locations c
WHERE SDO_FILTER(c.shape, :query_geometry) = 'TRUE'
  AND SDO_RELATE(
          c.shape,
          :query_geometry,
          'mask=ANYINTERACT'
      ) = 'TRUE';
~~~

Normally `SDO_RELATE` already includes the necessary primary/secondary filter logic. Adding a separate `SDO_FILTER` can be redundant; keep it only when justified by execution plan and workload measurements.

### 7.8 Query Windows Taken from a Table

When the query window comes from a table rather than a single bind geometry, Oracle recommends the `/*+ ORDERED */` optimizer hint in cases where processing order must be controlled for the spatial operator. Example:

~~~sql
SELECT /*+ ORDERED */
       q.query_id,
       c.location_id
FROM query_windows q,
     city_locations c
WHERE SDO_RELATE(
          c.shape,
          q.shape,
          'mask=ANYINTERACT'
      ) = 'TRUE';
~~~

Review the operator's usage notes and the specific execution plan. Hints are not a default solution for every query; only use them when join order needs control per Oracle recommendations.

## 8. Spatial Operators vs. SDO_GEOM Functions

Oracle provides two API groups with distinct roles:

| Group | Examples | Spatial Index |
|---|---|---|
| Spatial operators | SDO_FILTER, SDO_RELATE, SDO_NN, SDO_WITHIN_DISTANCE | Can leverage indexes; operator must appear in the WHERE clause |
| PL/SQL functions/procedures | SDO_GEOM.SDO_DISTANCE, SDO_GEOM.SDO_AREA, SDO_GEOM.RELATE, SDO_CS.TRANSFORM | Do not require an index and do not use a spatial index if present |

### 8.1 Computing Polygon Area

~~~sql
SELECT a.area_id,
       SDO_GEOM.SDO_AREA(a.shape, m.diminfo, 'unit=SQ_KM') AS area_sq_km
FROM service_areas a
JOIN user_sdo_geom_metadata m
  ON m.table_name = 'SERVICE_AREAS'
 AND m.column_name = 'SHAPE';
~~~

For geometries with a georeferenced SRID, measurement units can be specified. Verify supported units in `MDSYS.SDO_AREA_UNITS`/Oracle documentation. Never treat planar Cartesian area of longitude/latitude degrees as square kilometers.

### 8.2 Computing Distance Between Two Geometries

~~~sql
SELECT SDO_GEOM.SDO_DISTANCE(
           :geometry_a,
           :geometry_b,
           0.05,
           'unit=KM'
       ) AS distance_km
FROM dual;
~~~

Both geometries passed to `SDO_GEOM` functions must share the same coordinate system. Tolerance must make sense for the CRS and data precision.

### 8.3 Checking Relationships with Functions

~~~sql
SELECT SDO_GEOM.RELATE(
           :geometry_a,
           'ANYINTERACT',
           :geometry_b,
           0.05
       ) AS relation
FROM dual;
~~~

Functions are useful when a scalar relationship result is needed or when evaluating a few specific geometries. When querying a large table and an operator satisfies the requirement, prefer the operator to leverage the spatial index.

## 9. Transforming and Standardizing Coordinate Systems

### 9.1 Transforming a Geometry to Another SRID

Example converting a point from WGS 84 to Web Mercator:

~~~sql
SELECT SDO_CS.TRANSFORM(
           SDO_GEOMETRY(
               2001,
               4326,
               SDO_POINT_TYPE(106.7000, 10.7800, NULL),
               NULL,
               NULL
           ),
           3857
       ) AS projected_geometry
FROM dual;
~~~

SDO_CS.TRANSFORM converts ordinates according to the CRS transformation and returns a geometry with the target SRID. It is completely different from recreating an object and only overwriting SDO_SRID.

### 9.2 Never Assign a New SRID Without Transforming Coordinates

Suppose data is in CRS A, yet only SDO_SRID is changed from A to B. Oracle interprets the old ordinates as coordinates in B; it does not recalculate coordinates. The result can be positions shifted far away, wrong distances, or data falling outside metadata bounds.

Rules:

- When both source CRS and target CRS are known, use SDO_CS.TRANSFORM.
- When source CRS is unknown, confirm with the data provider or survey source before assigning an SRID.
- Do not pick an SRID simply because numbers look like latitude/longitude.
- After transforming, verify geometry, bounds, units, and map rendering.

### 9.3 Standardizing a Layer to One CRS

For reliable spatial indexing and querying, standardize geometries in a column to the same SRID. If sources have multiple CRSs:

1. Identify the source CRS of each batch.
2. Check source geometry and SRID.
3. Transform to the standard target CRS.
4. Store the transformed geometry in the target layer.
5. Update DIMINFO/SRID metadata accordingly.
6. Validate the layer and create the spatial index.

If source data must be preserved, store raw geometries or a pre-transform copy for traceability and reprocessing.

### 9.4 Query Windows with a Different SRID

Spatial operators can automatically transform the query window (second geometry) to the geometry column's CRS when needed. However, do not rely on implicit transforms for every workload without measuring performance and checking the transformation. For repeated queries, pre-normalizing the query geometry usually gives better control.

`SDO_GEOM` functions accepting two geometries generally require both to be in the same coordinate system. If SRIDs differ, transform one geometry before calling the function.

## 10. WKT, WKB, and Data Exchange

### 10.1 Well-Known Text (WKT)

WKT is a text format describing geometries, for example:

~~~text
POINT (106.7 10.78)
LINESTRING (106.7 10.78, 106.71 10.79)
POLYGON ((106.7 10.78, 106.71 10.78, 106.71 10.79, 106.7 10.79, 106.7 10.78))
~~~

You can construct geometries from WKT using the corresponding constructor:

~~~sql
INSERT INTO city_locations (
    location_id,
    location_name,
    shape
)
VALUES (
    2,
    'WKT Imported Point',
    SDO_GEOMETRY('POINT (106.7 10.78)', 4326)
);
~~~

WKT usually does not carry complete CRS metadata consistently across sources. Provide the SRID explicitly and confirm axis order.

### 10.2 Well-Known Binary (WKB)

WKB represents geometry in binary form, typically suited for large data exchanges or GIS APIs. Oracle supports constructors from WKB BLOBs/WKB hex per documentation. On import, ensure byte order, geometry type, dimensionality, and SRID are handled properly.

### 10.3 Exporting Geometry to WKT/WKB

SDO_GEOMETRY has methods such as GET_WKT() and GET_WKB():

~~~sql
SELECT location_id,
       shape.GET_WKT() AS geometry_wkt
FROM city_locations
WHERE location_id = :p_location_id;
~~~

WKT is convenient for reading/debugging, yet can be verbose and suboptimal for every exchange. For vertex-heavy data or when preserving exact binary representation is required, consider WKB.

### 10.4 GeoJSON

Oracle Spatial supports JSON/GeoJSON in suitable workflows. When exchanging GeoJSON, note:

- Coordinates typically use longitude before latitude for 2D geographic data.
- GeoJSON defaults to WGS 84 per modern specifications; do not confuse with projected meter coordinates.
- Verify how your API/database maps GeoJSON to internal SRIDs.
- Validate geometry type, ring closure, coordinate precision, and null/empty geometries.

Never just rename a file extension or field to turn a geometry into valid GeoJSON; follow the format's schema and coordinate rules.

## 11. 3D Geometry and Dimensionality

Oracle Spatial supports 3D geometries such as points, lines, polygons, surfaces, and solids. A 3D vertex has three ordinates X, Y, Z:

~~~sql
SDO_GEOMETRY(
    3001,
    4979,
    SDO_POINT_TYPE(106.7, 10.78, 25),
    NULL,
    NULL
)
~~~

The SRID in the example must be verified against the desired 3D CRS. Never attach a 2D SRID to a 3D geometry simply because the X/Y dimensions look similar.

### 11.1 3D Metadata

A 3D layer needs three SDO_DIM_ELEMENT entries in DIMINFO, ordered X, Y, Z. Z-dimension bounds and units must match the data's CRS/vertical datum.

### 11.2 3D Spatial Indexes

By default, spatial indexes use two dimensions. For data requiring 3D indexing, configure the index dimensionality per guidance:

~~~sql
CREATE INDEX buildings_3d_spx
ON buildings(shape)
INDEXTYPE IS MDSYS.SPATIAL_INDEX_V2
PARAMETERS('sdo_indx_dims=3');
~~~

### 11.3 Not Every Operator Processes Z

Some spatial operators/functions consider only the first two dimensions; some 2D/3D combinations are supported while others are not. Having a Z coordinate does not mean every query automatically becomes a 3D query. Check the dimensionality matrix and 3D-supported operator list for your exact release before deploying.

### 11.4 3D, LRS, and Measures

LRS (Linear Referencing System) uses a dimension as a measure to represent position along a route, such as kilometer markers on a road. A measure dimension is not the same as Z elevation. If a geometry uses LRS, declare the measure position in SDO_GTYPE and use the corresponding SDO_LRS APIs.

## 12. Spatial Query Performance and Optimization

### 12.1 Spatial Indexes Only Help When Queries Use the Right Operators

A query with `WHERE SDO_GEOM.SDO_DISTANCE(...) < ...` may evaluate per row and fail to use a spatial index. When appropriate for the problem, use SDO_WITHIN_DISTANCE or SDO_NN to leverage the index.

### 12.2 Narrow Candidates Early

Combine selective attribute predicates with spatial operators. Example:

~~~sql
SELECT location_id,
       location_name
FROM city_locations c
WHERE c.location_type = 'PHARMACY'
  AND SDO_WITHIN_DISTANCE(
          c.shape,
          :query_point,
          'distance=3 unit=KM'
      ) = 'TRUE';
~~~

Evaluate execution plans and cardinality. The optimizer can choose different predicate evaluation orders; never assume predicates written first always run first.

### 12.3 Using ORDERED When Query Windows Come from a Table

Oracle recommends `/*+ ORDERED */` in certain spatial operator queries when query windows come from a table, especially with multiple query windows. Check operator usage notes and inspect plans before keeping hints.

### 12.4 Optimizing SDO_NN

- Use sdo_num_res when you need exactly N nearest geometries without attribute filters altering the result set.
- Use sdo_batch_size and ROWNUM when you need N nearest results satisfying additional attribute predicates.
- With partitioned spatial indexes, sdo_num_res may return results per partition; cap results globally with ROWNUM in an outer query when appropriate.
- When distances tie, result sets across calls can differ among tied rows.

### 12.5 Spatial Index Statistics and Execution Plans

After creating an index or loading large amounts of data, update optimizer statistics per DBA policy. Check:

~~~sql
EXPLAIN PLAN FOR
SELECT location_id
FROM city_locations
WHERE SDO_WITHIN_DISTANCE(
          shape,
          :query_point,
          'distance=2 unit=KM'
      ) = 'TRUE';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Look for domain index access signs and inspect actual candidate/row counts using SQL Monitor or appropriate runtime plan statistics. Never rely solely on elapsed time of a single run; caching, binds, concurrency, and data distribution all affect timings.

### 12.6 SPATIAL_VECTOR_ACCELERATION

Oracle provides the `SPATIAL_VECTOR_ACCELERATION` parameter to accelerate certain spatial operators. Its default value is FALSE in the 19c documentation. This feature requires verifying usage rights/licensing and testing on your specific workload; never enable it in production solely because you saw the parameter name.

### 12.7 Choosing Tolerance and Geometry Complexity

Geometries with hundreds of thousands of vertices, tiny rings, or noisy data can make spatial queries CPU-intensive. Consider:

- Cleaning duplicate vertices and invalid geometries.
- Simplifying geometries within business-allowed error tolerances.
- Using generalized geometries for small-scale display queries.
- Keeping detailed geometries separately for precise analysis.
- Choosing sensible, consistent tolerances per layer.
- Avoiding repeatedly transforming the same query geometry per row when it can be pre-normalized.

Never simplify legal, cadastral, or high-precision boundaries without assessing impact.

## 13. Spatial Data Ingestion and Management Workflow

### 13.1 Data Ingestion Pipeline

~~~text
GIS Source / CSV / WKT / WKB / GeoJSON
                |
                v
     Identify CRS and axis order
                |
                v
       Parse into SDO_GEOMETRY
                |
                v
     Check SRID / dimensionality
                |
                v
    Validate geometry and bounds
                |
                v
 Transform to standard CRS (if needed)
                |
                v
       Load into staging table
                |
                v
   Record errors and valid counts
                |
                v
     Merge into spatial layer
                |
                v
    Update statistics / index
                |
                v
     Run verification queries
~~~

### 13.2 Staging Before Production Load

Load external data into a staging table first. Record source file/batch ID, source CRS, load timestamp, row count, invalid geometry count, and error reasons. Merge only verified geometries into the production layer.

### 13.3 Updating Geometries

When editing geometries:

- Ensure SRID and dimensionality do not change unexpectedly.
- Validate the new geometry.
- Check impact on the spatial index.
- Log the source and reason for the edit.
- If changing CRS, update metadata accordingly and verify the index.

### 13.4 Partitioning

Spatial Index V2 supports index management across multiple partitioning models. Choose partition keys based on business access patterns (such as tenant, region, or time), not solely on geometry without evaluating spatial queries. When using partitioned indexes, understand nearest-neighbor behavior and global result limiting.

## 14. Common Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| ORA-13203 when creating index | Layer/column metadata not found | Check USER_SDO_GEOM_METADATA and table/column names |
| ORA-13214/metadata mismatch | SRID or dimensionality mismatch | Cross-check SDO_SRID, DIMINFO, and geometry |
| ORA-13349/invalid polygon | Self-intersecting ring or invalid geometry | Validate with context, fix source, or run controlled rectification |
| Queries miss expected locations | Wrong SRID assigned, swapped X/Y, or wrong transform | Verify source CRS, axis order, and bounds |
| Distance/area has unexpected units | Wrong CRS or unit | Check SRID and specify units explicitly |
| SDO_FILTER returns too many rows | MBRs intersect even though actual geometries do not | Use SDO_RELATE for secondary filtering |
| SDO_NN unusable | Missing spatial index or dimensionality mismatch | Check index and query window dimensions |
| Spatial index invalid after creation | Index creation failed mid-way | Read errors, drop invalid index, and recreate after fixing |
| Slow queries despite index | Function bypasses index, bad metadata, or overly complex geometry | Use appropriate operators, inspect plan, and validate data |
| SDO_GEOM function reports CRS mismatch | Two geometries have different SRIDs | Transform one geometry to match the other's CRS |
| Geometry outside bounds | Metadata bounds do not match data or bad input data | Verify CRS and update DIMINFO per valid data |
| 3D results behave like 2D | Operator evaluates only two dimensions | Check 3D support and create a 3D index if appropriate |

## 15. Hands-On Lab: Creating a Layer, Index, and Spatial Queries

This lab uses a local Cartesian coordinate system to illustrate topology and spatial indexes without depending on real geographic data. Coordinates are in arbitrary example units.

### 15.1 Creating Table and Data

~~~sql
CREATE TABLE lab_areas (
    area_id NUMBER PRIMARY KEY,
    area_name VARCHAR2(30),
    shape SDO_GEOMETRY
);

INSERT INTO lab_areas VALUES (
    1,
    'AREA_A',
    SDO_GEOMETRY(
        2003, NULL, NULL,
        SDO_ELEM_INFO_ARRAY(1, 1003, 3),
        SDO_ORDINATE_ARRAY(0, 0, 10, 10)
    )
);

INSERT INTO lab_areas VALUES (
    2,
    'AREA_B',
    SDO_GEOMETRY(
        2003, NULL, NULL,
        SDO_ELEM_INFO_ARRAY(1, 1003, 1),
        SDO_ORDINATE_ARRAY(8, 8, 14, 8, 14, 14, 8, 14, 8, 8)
    )
);

INSERT INTO lab_areas VALUES (
    3,
    'AREA_C',
    SDO_GEOMETRY(
        2003, NULL, NULL,
        SDO_ELEM_INFO_ARRAY(1, 1003, 3),
        SDO_ORDINATE_ARRAY(20, 20, 25, 25)
    )
);

COMMIT;
~~~

### 15.2 Declaring Metadata

~~~sql
INSERT INTO user_sdo_geom_metadata (
    table_name,
    column_name,
    diminfo,
    srid
)
VALUES (
    'LAB_AREAS',
    'SHAPE',
    SDO_DIM_ARRAY(
        SDO_DIM_ELEMENT('X', -100, 100, 0.001),
        SDO_DIM_ELEMENT('Y', -100, 100, 0.001)
    ),
    NULL
);
~~~

### 15.3 Validating Geometries

~~~sql
SELECT a.area_id,
       SDO_GEOM.VALIDATE_GEOMETRY_WITH_CONTEXT(
           a.shape,
           m.diminfo
       ) AS validation_result
FROM lab_areas a,
     user_sdo_geom_metadata m
WHERE m.table_name = 'LAB_AREAS'
  AND m.column_name = 'SHAPE';
~~~

### 15.4 Creating the Spatial Index

~~~sql
CREATE INDEX lab_areas_spx
ON lab_areas(shape)
INDEXTYPE IS MDSYS.SPATIAL_INDEX_V2;
~~~

### 15.5 Finding Polygons Intersecting a Query Window

~~~sql
SELECT area_id,
       area_name
FROM lab_areas a
WHERE SDO_RELATE(
          a.shape,
          SDO_GEOMETRY(
              2003, NULL, NULL,
              SDO_ELEM_INFO_ARRAY(1, 1003, 3),
              SDO_ORDINATE_ARRAY(9, 9, 12, 12)
          ),
          'mask=ANYINTERACT'
      ) = 'TRUE';
~~~

### 15.6 Comparing Primary Filter vs. Exact Relationship

~~~sql
SELECT area_id, area_name
FROM lab_areas a
WHERE SDO_FILTER(
          a.shape,
          SDO_GEOMETRY(
              2003, NULL, NULL,
              SDO_ELEM_INFO_ARRAY(1, 1003, 3),
              SDO_ORDINATE_ARRAY(9, 9, 12, 12)
          )
      ) = 'TRUE';
~~~

Compare the results against SDO_RELATE. The primary filter can return extra candidates because it only compares bounding rectangles.

### 15.7 Cleaning Up the Lab

~~~sql
DROP INDEX lab_areas_spx;
DELETE FROM user_sdo_geom_metadata
WHERE table_name = 'LAB_AREAS'
  AND column_name = 'SHAPE';
DROP TABLE lab_areas PURGE;
~~~

Only run cleanup commands if this is the lab schema you just created and it contains no data that needs to be kept.

## 16. Oracle Spatial Design Checklist

### Geometry and CRS

1. Does the geometry type match the business object?
2. Are SDO_GTYPE, dimensionality, and LRS measure position correct?
3. Are ELEM_INFO offsets, ETYPEs, and interpretations valid?
4. Are polygons closed and rings oriented properly?
5. Does the SRID accurately reflect the source CRS?
6. Have axis order, datum, projection, and units been verified?
7. Does tolerance match precision and units?

### Metadata and Indexes

1. Does USER_SDO_GEOM_METADATA have the exact table/column?
2. Do DIMINFO bounds and tolerance fit the data?
3. Does metadata SRID match geometry SRID?
4. Were geometries validated before indexing?
5. Was the spatial index created on the right geometry column?
6. Does index dimensionality match the 2D/3D workload?

### Queries and Performance

1. Does the problem need a primary filter or exact topology?
2. Which operator fits: FILTER, RELATE, WITHIN_DISTANCE, or NN?
3. Does the query window have a matching CRS/dimensionality?
4. Should coordinates be pre-transformed to avoid repeated conversions?
5. Are distance/area units specified explicitly?
6. If SDO_NN has attribute filters, is batch size set properly?
7. Does the execution plan use the spatial index?
8. Do geometries have excessive vertices or overly large tolerances?

## 17. Summary

Oracle Spatial enables storing and analyzing geometries in Oracle Database using the SDO_GEOMETRY type, CRS/SRID, metadata, and spatial indexes. To achieve accurate and fast results:

- Choose the right geometry type and understand SDO_GTYPE, SDO_ELEM_INFO, and SDO_ORDINATES.
- Attach the right SRID; the CRS is part of coordinate meaning, not an arbitrary label.
- Declare USER_SDO_GEOM_METADATA with proper DIMINFO, bounds, tolerance, and SRID.
- Validate geometries before creating indexes and running spatial operations.
- Use R-tree spatial indexes with SPATIAL_INDEX_V2 on layers requiring efficient querying.
- Use SDO_FILTER for candidate filtering; use SDO_RELATE, SDO_WITHIN_DISTANCE, SDO_NN, and appropriate operators for business logic.
- Distinguish spatial operators that can use indexes from SDO_GEOM functions that do not use spatial indexes.
- Transform coordinates genuinely using SDO_CS.TRANSFORM; never just overwrite the SRID attribute.
- Choose tolerance and units based on CRS and data accuracy.
- For 3D, verify dimensionality support for indexes and each operator.

Proper spatial design starts from source data and coordinate systems, followed by metadata, indexes, and queries. A good spatial index cannot fix data with the wrong CRS; a structurally valid geometry does not guarantee an accurate real-world location. Manage CRS, geometry validity, and query semantics as inseparable parts.

## 18. Oracle Reference Documentation

- Oracle Database 19c Spatial and Graph Developer's Guide, “Spatial Concepts”: https://docs.oracle.com/en/database/oracle/oracle-database/19/spatl/spatial-concepts.html
- Oracle Database 19c Spatial and Graph Developer's Guide, “SDO_GEOMETRY Object Type”: https://docs.oracle.com/en/database/oracle/oracle-database/19/spatl/spatial-datatypes-metadata.html
- Oracle Database 19c Spatial and Graph Developer's Guide, “Coordinate Systems (Spatial Reference Systems)”: https://docs.oracle.com/en/database/oracle/oracle-database/19/spatl/coordinate-systems-concepts.html
- Oracle Database 19c Spatial and Graph Developer's Guide, “Indexing and Querying Spatial Data”: https://docs.oracle.com/en/database/oracle/oracle-database/19/spatl/indexing-querying-spatial-data.html
- Oracle Database 19c Spatial and Graph Developer's Guide, “Spatial Operators”: https://docs.oracle.com/en/database/oracle/oracle-database/19/spatl/spatial-operators-reference.html
- Oracle Database 19c Spatial and Graph Developer's Guide, “SDO_GEOM Package”: https://docs.oracle.com/en/database/oracle/oracle-database/19/spatl/SDO_GEOM-reference.html
- Oracle Database 19c Spatial and Graph Developer's Guide, “SDO_CS Package”: https://docs.oracle.com/en/database/oracle/oracle-database/19/spatl/SDO_CS-reference.html
- Oracle Database 19c Spatial and Graph Developer's Guide, “Loading Spatial Data”: https://docs.oracle.com/en/database/oracle/oracle-database/19/spatl/loading-spatial-data.html
