# SPATIAL Indexes, Bounding Rectangles, and Usage Conditions

MySQL stores spatial data using geometry types such as `POINT`, `LINESTRING`, `POLYGON`, and their corresponding collection types. When searching for points inside a region, overlapping areas, or objects near a zone, scanning the entire table and evaluating geometric predicates row by row can be very expensive. A `SPATIAL` index narrows down the candidate set using an R-tree structure.

A `SPATIAL` index does not index the exact full shape of every geometry. Instead, it indexes each geometry's minimum bounding rectangle (MBR)—the smallest rectangle enclosing the geometry. Consequently, queries typically operate in two steps: use the MBR to quickly locate candidates, then apply `ST_*` functions to check exact geometric relationships when business logic requires it.

In the **DATABASE_MYSQL** module, you must understand index creation requirements, SRIDs, argument order for MBR functions, and the limitations of bounding rectangles. This lesson guides you through designing spatial columns, creating R-tree indexes, writing index-friendly queries, reading `EXPLAIN`, and avoiding confusion between MBR results and true geometric relationships.

## 1. Geometry, SRID, and Spatial Data

MySQL supports an OpenGIS-based geometry type system. Common types:

| Type | Representation | Example Use Case |
|---|---|---|
| `GEOMETRY` | Generic base type | Column accepting multiple geometry types |
| `POINT` | Single coordinate | Store, station, or device location |
| `LINESTRING` | Sequence of connected points | Roads, pipelines |
| `POLYGON` | Closed region | Area boundaries, delivery zones |
| `MULTIPOINT` | Collection of points | Multiple sites |
| `MULTILINESTRING` | Collection of paths | Route network |
| `MULTIPOLYGON` | Collection of regions | Multi-part territory |
| `GEOMETRYCOLLECTION` | Collection of mixed geometry types | Composite datasets |

WKT (Well-Known Text) examples:

```text
POINT(106.7009 10.7769)
LINESTRING(106.68 10.75, 106.70 10.78, 106.73 10.80)
POLYGON((106.65 10.70, 106.80 10.70, 106.80 10.85,
         106.65 10.85, 106.65 10.70))
```

WKT is convenient for constructing, reading, and exchanging geometries. MySQL also supports WKB (Well-Known Binary), GeoJSON, and their conversion functions.

### 1.1. SRID Identifies the Reference System

The SRID (Spatial Reference System Identifier) identifies a geometry's spatial reference system. It indicates whether coordinates belong to a Cartesian or geographic system, how axes are defined, and what units apply.

Examples:

- SRID 0: MySQL's default Cartesian system, unbound to any specific geographic reference system.
- SRID 4326: WGS 84 geographic coordinate system, commonly used for longitude/latitude.
- Other SRIDs may describe projected or local reference systems.

Never treat two geometries with different SRIDs as sharing the same coordinate system just because they contain similar numbers. Spatial operations between geometries with different SRSs typically raise an SRID mismatch error.

Inspect SRIDs:

```sql
SELECT
    ST_SRID(ST_GeomFromText('POINT(10 20)', 0)) AS cartesian_srid,
    ST_SRID(
        ST_GeomFromText(
            'POINT(106.7009 10.7769)',
            4326,
            'axis-order=long-lat'
        )
    ) AS geographic_srid;
```

### 1.2. Axis Order and Longitude/Latitude

Do not assume WKT always puts longitude before latitude. Some SRSs define their axes as latitude/longitude. MySQL supports the `axis-order` option to specify how coordinates are parsed when constructing geometries from WKT.

When application data uses longitude, latitude order, specify it explicitly:

```sql
SET @point = ST_GeomFromText(
    'POINT(106.7009 10.7769)',
    4326,
    'axis-order=long-lat'
);
```

In this example, `x` is longitude and `y` is latitude. Keep axis order consistent across APIs, GeoJSON/WKT files, applications, and MySQL. Swapping the two axes can produce a syntactically valid geometry at the wrong location.

### 1.3. SRID-Restricted Columns

A geometry column can declare an SRID attribute to restrict every stored value to the same reference system. Example:

```sql
CREATE TABLE places (
    place_id BIGINT UNSIGNED NOT NULL,
    place_name VARCHAR(150) NOT NULL,
    location POINT NOT NULL SRID 4326,
    PRIMARY KEY (place_id)
) ENGINE = InnoDB;
```

With `SRID 4326` declared, MySQL requires geometries inserted into `location` to carry that matching SRID. This keeps column data consistent and informs the optimizer which reference system to use when computing bounding boxes.

For InnoDB in MySQL 8.0, an SRID restriction is an essential condition for the optimizer to exploit a `SPATIAL` index. An index on an unrestricted column may still be maintained for compatibility, but the optimizer ignores it.

## 2. Minimum Bounding Rectangle (MBR)

The MBR is the smallest axis-aligned rectangle enclosing a geometry. In a 2D plane, an MBR is defined by:

- `minX`: minimum X coordinate.
- `maxX`: maximum X coordinate.
- `minY`: minimum Y coordinate.
- `maxY`: maximum Y coordinate.

The four corners of the rectangle are formed from these min/max pairs.

Example concave polygon:

```text
POLYGON((
  0 0,
  0 8,
  3 8,
  3 3,
  7 3,
  7 8,
  10 8,
  10 0,
  0 0
))
```

The polygon's MBR is the rectangle from `(0, 0)` to `(10, 8)`. The empty cutout in the middle of the polygon still lies inside its MBR. Thus, a point can lie inside the MBR while sitting outside the true polygon.

### 2.1. MBRs of Different Geometry Types

- `POINT` has an MBR degenerating to the point itself.
- `LINESTRING` has an MBR enclosing all points on the line; for horizontal or vertical lines, the MBR degenerates to a line segment.
- `POLYGON` has an MBR enclosing the entire region and its boundary rings.
- `MULTI*` and `GEOMETRYCOLLECTION` have an MBR enclosing all their components.

An MBR is typically larger than the actual shape. For concave polygons, polygons with holes, or complex curves, the gap between the geometry and its MBR can be substantial.

### 2.2. Why Does MBR Produce False Positives?

Consider a U-shaped polygon. Its MBR is a rectangle spanning the empty notch in the middle. A point inside that notch satisfies `MBRContains` yet fails `ST_Contains`.

Therefore:

- MBR predicates evaluate relationships between bounding rectangles.
- `ST_*` predicates evaluate relationships between actual geometry shapes.
- MBR serves as a fast candidate filter, not a replacement for exact geometric checks.

The typical flow is: geometries are stored in the table, MBRs are indexed in the R-tree, the query locates MBRs that may satisfy the condition, and candidates are verified with `ST_*` when exact relationships are needed.

## 3. SPATIAL Indexes Use R-Trees

MySQL `SPATIAL` indexes use an R-tree structure. Unlike B-trees, which order keys along a single dimension, R-trees group spatial regions by bounding rectangles to locate regions that may overlap or contain a position.

MySQL builds the `SPATIAL` index over each geometry's MBR. On InnoDB and MyISAM, R-trees accelerate common spatial queries such as:

- Finding objects containing a point.
- Finding objects inside a rectangular region.
- Finding objects whose bounding rectangles intersect a region.

The R-tree reduces the number of geometries that must be inspected. After filtering, MySQL or the application may still need to evaluate exact shapes on the remaining candidates.

### 3.1. Comparing B-Tree and R-Tree

| Feature | B-tree | R-tree in SPATIAL Index |
|---|---|---|
| Primary data | Ordered scalar values | Regions / bounding rectangles |
| Best-suited queries | `=`, range, sort, prefix | Region searches and MBR relationships |
| Structure | Ordered keys | Hierarchical bounding rectangles |
| Geometry support | B-tree on geometry has limited utility | Spatial index built specifically for MBRs |
| Region overlap searches | Not its primary purpose | Primary purpose |

A regular B-tree index on a geometry column can occasionally assist exact-value lookups, but it cannot replace an R-tree for spatial range searches.

## 4. Requirements for Creating a SPATIAL Index

MySQL enforces several key rules:

1. `SPATIAL` indexes are supported only on InnoDB and MyISAM tables.
2. The indexed column must be a spatial data type.
3. The geometry column must be declared `NOT NULL`.
4. A single `SPATIAL` index applies to one spatial column only.
5. Do not specify a prefix length for a column in a `SPATIAL` index.
6. For the optimizer to use the index in MySQL 8.0, the column must be SRID-restricted: explicitly declare an SRID and ensure all data shares that SRID.

Example creating a table and index:

```sql
CREATE TABLE places (
    place_id BIGINT UNSIGNED NOT NULL,
    place_name VARCHAR(150) NOT NULL,
    location POINT NOT NULL SRID 4326,
    PRIMARY KEY (place_id),
    SPATIAL INDEX spx_places_location (location)
) ENGINE = InnoDB;
```

You can add the index after table creation:

```sql
ALTER TABLE places
ADD SPATIAL INDEX spx_places_location (location);
```

Or:

```sql
CREATE SPATIAL INDEX spx_places_location
ON places (location);
```

### 4.1. Why Is NOT NULL Mandatory?

MySQL's `SPATIAL` index requires the indexed geometry column to be `NOT NULL`. When a location is unknown or not yet recorded, choose an appropriate data model:

- Omit creating a location row until coordinates exist.
- Use a separate business status column to represent unknown state.
- Store geometries in a companion table populated only when coordinates are available.
- Never use dummy coordinates such as `POINT(0 0)` in place of `NULL`, as they can be mistaken for a real location.

If `NULL` values must be stored in the geometry column, that column cannot carry a `SPATIAL` index. Establish your data policy before designing the schema.

### 4.2. Why Is an SRID Restriction Important?

The optimizer needs to know the column's reference system to compute bounding boxes properly. If a column mixes Cartesian and geographic geometries, identical numbers carry different meanings and bounding-box math cannot be interpreted consistently.

With an SRID attribute on the column:

```sql
location POINT NOT NULL SRID 4326
```

MySQL knows all `location` values belong to SRID 4326. On columns without an SRID declaration, a `SPATIAL` index may still be maintained in certain compatibility scenarios, but the optimizer will not use it for query optimization.

Check stored SRIDs:

```sql
SELECT DISTINCT ST_SRID(location) AS srid
FROM places;
```

If multiple SRIDs appear, normalize or transform the data to a single reference system before redefining the column and recreating the index. Never alter only the SRID metadata if coordinates have not genuinely been transformed.

## 5. Inserting Geometry Data with the Right SRID

You can construct geometries using WKT functions. Example inserting a point into the table:

```sql
INSERT INTO places (
    place_id,
    place_name,
    location
)
VALUES (
    1,
    'Central Store',
    ST_GeomFromText(
        'POINT(106.7009 10.7769)',
        4326,
        'axis-order=long-lat'
    )
);
```

On an SRID 4326 column, the supplied geometry must carry a compatible SRID. Passing an SRID 0 geometry is rejected by MySQL due to the SRID mismatch.

Read data back as WKT:

```sql
SELECT
    place_id,
    place_name,
    ST_AsText(location) AS location_wkt,
    ST_SRID(location) AS location_srid
FROM places;
```

### 5.1. Validating Geometries Before Indexing

Before bulk-loading large datasets:

- Validate WKT/WKB/GeoJSON syntax.
- Validate SRID and axis order.
- Validate that longitude/latitude lie within the SRS bounds.
- Validate that polygons are closed and well-formed.
- Verify all geometries share the same SRID.
- Check for `NULL` data if the column will be indexed.

Use functions such as `ST_IsValid()`, `ST_GeometryType()`, `ST_SRID()`, and `ST_AsText()` to inspect rows.

Example:

```sql
SELECT
    place_id,
    ST_GeometryType(location) AS geometry_type,
    ST_SRID(location) AS srid,
    ST_IsValid(location) AS is_valid
FROM places;
```

`ST_IsValid` checks geometric validity under MySQL's rules. Syntactically valid data is not guaranteed to be topologically valid.

## 6. Bounding Rectangles and MBR Functions

MySQL provides MBR relationship functions to compare the bounding rectangles of two geometries:

| Function | Meaning |
|---|---|
| `MBRContains(g1, g2)` | MBR of `g1` contains MBR of `g2` |
| `MBRWithin(g1, g2)` | MBR of `g1` lies within MBR of `g2` |
| `MBRIntersects(g1, g2)` | Both MBRs intersect |
| `MBROverlaps(g1, g2)` | Both MBRs overlap per relation rules |
| `MBRCovers(g1, g2)` | MBR of `g1` covers MBR of `g2`, including boundaries |
| `MBRCoveredBy(g1, g2)` | MBR of `g1` is covered by MBR of `g2` |
| `MBREquals(g1, g2)` | Both MBRs are equal |
| `MBRTouches(g1, g2)` | Both MBRs touch |
| `MBRDisjoint(g1, g2)` | Both MBRs are disjoint |

MBR functions return `1` or `0` for bounding-rectangle relationships. If any argument is SQL `NULL` or an empty geometry, the result can be `NULL`. Geometries with different SRSs raise errors.

### 6.1. MBRContains and MBRWithin

These two functions express inverse relationships:

```sql
SELECT
    MBRContains(@region, @point) AS region_contains_point,
    MBRWithin(@point, @region) AS point_within_region;
```

Both evaluate to true when the point lies inside the region's MBR.

Argument order matters. When querying a table with an indexed `location` column, a common pattern puts the search-region geometry first and the indexed geometry column second:

```sql
WHERE MBRContains(@search_window, location)
```

This is the pattern documented by MySQL for optimizer spatial index usage.

### 6.2. MBRIntersects for Overlapping Region Queries

To find geometries whose MBRs intersect a search window:

```sql
SELECT place_id
FROM places
WHERE MBRIntersects(@search_window, location);
```

`MBRIntersects` only confirms that two bounding rectangles intersect. For complex geometries, it may return candidates whose true shapes do not intersect. Inspect the execution plan and add an exact predicate if business rules require true geometric relationships.

Do not assume every MBR function is exploited identically by the optimizer. MySQL explicitly documents patterns such as `MBRContains()` and `MBRWithin()` for spatial indexes; always use `EXPLAIN` to confirm your specific predicate and server version.

## 7. Queries That Leverage a SPATIAL Index

Suppose the `places` table has a `SPATIAL` index on `location`.

Create a rectangular search window:

```sql
SET @search_window = ST_GeomFromText(
    'POLYGON((
        106.65 10.70,
        106.80 10.70,
        106.80 10.85,
        106.65 10.85,
        106.65 10.70
    ))',
    4326,
    'axis-order=long-lat'
);
```

Find points inside the bounding rectangle:

```sql
SELECT
    place_id,
    place_name
FROM places
WHERE MBRContains(@search_window, location);
```

With an SRID-restricted `location` column and a valid `SPATIAL` index, the optimizer can use the R-tree to narrow candidates. `MBRContains` evaluates the MBR relationship; since the query window here is a rectangle, its MBR coincides with the search rectangle.

### 7.1. Checking with EXPLAIN

```sql
EXPLAIN
SELECT
    place_id,
    place_name
FROM places
WHERE MBRContains(@search_window, location);
```

Columns to inspect:

- `possible_keys`: whether the spatial index appears among eligible indexes.
- `key`: the index actually chosen by the optimizer.
- `type`: access type, such as `range` when using a spatial index.
- `rows`: estimated rows to examine.
- `Extra`: additional filtering conditions.

Never rely solely on seeing the index in `SHOW INDEX`. Verify `key` in `EXPLAIN` and compare against queries without the index or with altered predicates.

### 7.2. MBR Filter Combined with Exact Geometry Predicates

For concave polygons or polygons with holes, the MBR can cover many points outside the true polygon. In such cases, use MBR as a fast prefilter and `ST_Contains` as the exact check:

```sql
SELECT
    place_id,
    place_name
FROM places
WHERE MBRContains(@search_window, location)
  AND ST_Contains(@search_window, location);
```

In this example:

1. `MBRContains` locates points potentially inside the region.
2. `ST_Contains` verifies whether each point truly lies inside the polygon.
3. False positives falling in empty cutouts of the MBR are eliminated.

`ST_Contains` enforces exact geometric semantics and excludes points sitting strictly on polygon boundaries. If business logic must include boundary points, pick a matching exact predicate such as `ST_Intersects`, and make sure the MBR prefilter does not drop required boundary points.

### 7.3. Finding Regions That May Intersect a Query Region

Suppose a `districts` table stores boundary polygons:

```sql
CREATE TABLE districts (
    district_id BIGINT UNSIGNED NOT NULL,
    district_name VARCHAR(150) NOT NULL,
    boundary POLYGON NOT NULL SRID 4326,
    PRIMARY KEY (district_id),
    SPATIAL INDEX spx_district_boundary (boundary)
) ENGINE = InnoDB;
```

Find boundaries whose MBRs intersect the search window:

```sql
SELECT district_id, district_name
FROM districts
WHERE MBRIntersects(@search_window, boundary);
```

If you need to confirm the polygons genuinely intersect, add `ST_Intersects`:

```sql
SELECT district_id, district_name
FROM districts
WHERE MBRIntersects(@search_window, boundary)
  AND ST_Intersects(boundary, @search_window);
```

Always check `EXPLAIN` to verify whether the specific MBR predicate is leveraged by the optimizer. If the query plan skips the spatial index, review SRID restrictions, argument order, geometry types, region selectivity, and row count.

## 8. Bounding Rectangles in Geographic Coordinate Systems

Under SRID 4326, coordinates are longitude/latitude in degrees. A geographic MBR does not behave like a flat map rectangle in every scenario.

Points to keep in mind:

- Longitude spans approximately `(-180, 180]`.
- Latitude spans `[-90, 90]`.
- The physical length of one degree of longitude shrinks as latitude moves away from the equator.
- Near the poles, bounding-box interpretation requires extra care.
- Search regions crossing the 180-degree meridian (antimeridian) may need to be split into multiple query regions.
- Never use Euclidean math on longitude/latitude as a substitute for geographic distance.

In Cartesian or projected planar systems, MBRs operate in the linear units of that system. In geographic systems, MySQL computes bounding boxes according to the SRS and geographic rules.

### 8.1. Do Not Confuse Bounding Rectangles with Radius Searches

A rectangular search window and a radius search are two different requirements.

- `MBRContains` filters points inside a bounding rectangle.
- `ST_Distance_Sphere` or an appropriate distance function checks distance in meters.
- An R-tree does not automatically turn a radius query into an exact circle search.

A common pattern is computing a bounding box enclosing the target radius circle to narrow candidates, then computing exact distances on those candidates. Bounding-box calculation must account for latitude, longitude, units, and edge cases near the poles or antimeridian.

## 9. Why Might a Spatial Index Not Be Used?

Common causes:

1. The geometry column is not declared `NOT NULL`.
2. The column lacks an `SRID` attribute and is therefore not SRID-restricted.
3. Data has inconsistent SRIDs or the query passes a geometry with a mismatched SRID.
4. The table uses a storage engine that does not support `SPATIAL` indexes.
5. The `WHERE` clause does not use an MBR predicate recognized by the optimizer.
6. Argument order in the MBR predicate is reversed relative to what the optimizer expects.
7. The geometry column is wrapped in an expression that hides the indexable access path.
8. The search window is too broad, making the index unselective so a full scan is cheaper.
9. Small table size or optimizer cost statistics favor another plan.
10. The index was never created or was dropped during a migration.

### 9.1. Inspecting Column Metadata

```sql
SHOW CREATE TABLE places;
```

Confirm the column definition matches:

```sql
location POINT NOT NULL SRID 4326
```

Inspect actual stored SRIDs:

```sql
SELECT DISTINCT ST_SRID(location)
FROM places;
```

Inspect indexes:

```sql
SHOW INDEX FROM places;
```

### 9.2. Inspecting the Execution Plan

```sql
EXPLAIN FORMAT = JSON
SELECT place_id
FROM places
WHERE MBRContains(@search_window, location);
```

Compare against queries without the spatial predicate or with `IGNORE INDEX` in a test environment to understand the impact. Never ship index hints to production without benchmarking and evaluation.

## 10. Maintaining SPATIAL Indexes

A `SPATIAL` index is updated on `INSERT`, `UPDATE`, and `DELETE` of geometries. When the `location` column changes, the R-tree must update the corresponding MBR.

For large datasets:

- Plan for index build duration.
- Monitor CPU, I/O, and disk space during rebuilds.
- Load data in controlled batches when appropriate.
- Validate SRIDs and geometry validity before loading.
- Run `EXPLAIN` after migrations.
- Verify result accuracy with a regression query suite.

Drop the index when workloads no longer need it:

```sql
ALTER TABLE places
DROP INDEX spx_places_location;
```

Or:

```sql
DROP INDEX spx_places_location
ON places;
```

Do not drop a spatial index just because one query failed to use it. Check SRID restrictions, `NOT NULL`, predicates, and selectivity first.

## 11. SPATIAL Indexes Combined with Attribute Filters

Many production queries filter by both standard attributes and location. For example, finding active stores in a region:

```sql
SELECT
    place_id,
    place_name
FROM places
WHERE MBRContains(@search_window, location)
  AND status = 'ACTIVE';
```

The spatial index narrows candidates by region, and `status` filters further by attribute. A `SPATIAL` index cannot be a multi-column composite index like a B-tree; it indexes only one geometry column. If `status` is highly selective, evaluate the execution plan alongside separate B-tree indexes.

Do not assume MySQL will combine multiple indexes in the way you expect. Use `EXPLAIN` to inspect the chosen access path and estimated rows. When an attribute filter is very selective, the optimizer may prefer the attribute index first or choose a different plan depending on data distribution.

## 12. Common Limitations and Misconceptions

| Misconception | Reality | How to Handle |
|---|---|---|
| `SPATIAL` index stores exact polygon shapes | The index is based on MBRs | Use `ST_*` to evaluate true shapes |
| Having a `SPATIAL` index makes every geographic query fast | Only eligible predicates and qualifying columns can use it | Check `EXPLAIN` |
| Only `NOT NULL` is required | MySQL 8.0 optimizer also requires an SRID restriction | Declare the `SRID` attribute |
| Geometries with different SRIDs compare normally | Operations error out on mismatched SRSs | Transform to a common SRS |
| `MBRContains` equals `ST_Contains` | One compares MBRs, the other compares shapes | Use MBR as prefilter and `ST_*` as exact filter |
| MBR false positives are data bugs | They are a normal consequence of bounding rectangles | Filter exact geometry in the next step |
| All storage engines support `SPATIAL` indexes | InnoDB and MyISAM support them; others have limits | Verify the storage engine |
| Multiple geometries can share one `SPATIAL` index | A `SPATIAL` index covers a single spatial column | Create separate indexes if needed |
| Prefix lengths can be used | Prefix lengths are disallowed on `SPATIAL` indexes | Index the full geometry column |
| Longitude is always the first axis | Axis order depends on SRS and options | Pass the appropriate `axis-order` |
| Geographic MBRs are always simple flat rectangles | Geographic SRSs have dedicated bounding-box rules | Account for SRID, antimeridian, and poles |
| Meter distance equals `MBRContains` | MBR checks regions, not radial distance | Use distance functions for the exact step |

## 13. Spatial Query Design Workflow

1. Identify the geometry type: `POINT`, `LINESTRING`, `POLYGON`, or collection.
2. Select an SRS/SRID suited to your data and measurements.
3. Standardize axis order and coordinate units.
4. Declare the geometry column `NOT NULL` if a `SPATIAL` index is required.
5. Declare the `SRID` attribute so the optimizer can use the index.
6. Create a `SPATIAL` index on a single geometry column.
7. Use `MBRContains` or `MBRWithin` for appropriate region/point queries.
8. Add `ST_*` when exact topological verification is required.
9. Read `EXPLAIN` and verify the selected `key`.
10. Benchmark with representative data and realistic search windows.
11. Test edge cases, mismatched SRIDs, and invalid geometries.
12. Monitor write amplification and index maintenance costs.

## 14. Pre-Production Checklist

**Schema and Data:**

- Geometry column uses the right subtype.
- Indexed column is declared `NOT NULL`.
- `SRID` attribute is explicitly declared.
- All geometries share the same SRID.
- Longitude/latitude or `axis-order` convention is standardized.
- Polygons and geometry collections pass validity checks.
- No dummy coordinates are used in place of `NULL`.

**Indexes and Queries:**

- `SPATIAL` index targets a single geometry column.
- No prefix length is specified.
- MBR predicates use the right argument order.
- Exact `ST_*` predicates are included where needed.
- `EXPLAIN` confirms the optimizer can select the spatial index.
- Small windows, large windows, boundary cases, and complex shapes have been tested.
- MBR results were compared against exact geometry results.

**Operations:**

- Index creation/rebuild duration has been estimated.
- CPU, I/O, disk footprint, and write overhead have been measured.
- An SRID transformation procedure exists if data requirements change.
- A regression query suite exists for migrations.
- Latency and candidate row counts are monitored.
- Handling is in place for malformed data and out-of-range geometries.

## 15. Key Takeaways

- MySQL `SPATIAL` indexes use R-trees and index geometry MBRs.
- An MBR is the smallest enclosing rectangle around a geometry, not its exact shape.
- MBR predicates can produce false positives, especially for concave polygons, polygons with holes, or complex shapes.
- InnoDB and MyISAM support `SPATIAL` indexes.
- The indexed column must be a spatial type and `NOT NULL`.
- Each `SPATIAL` index covers one geometry column; prefix lengths are not allowed.
- For the optimizer to leverage a `SPATIAL` index in MySQL 8.0, the column must be SRID-restricted.
- The column's SRID attribute and actual stored data must agree.
- `MBRContains`/`MBRWithin` are key patterns enabling the optimizer to consider a spatial index.
- Use `EXPLAIN` to verify that the index is actually chosen.
- Use `ST_Contains`, `ST_Within`, `ST_Intersects`, and related `ST_*` functions when exact geometric relationships are required.
- Never confuse MBR checks with distance or radius calculations.
- With geographic SRIDs, pay attention to longitude/latitude, axis order, degree units, and antimeridian crossings.
- Spatial indexes increase write cost and storage size, so benchmark both reads and writes.

A `SPATIAL` index narrows down the geometries to examine using an R-tree and bounding rectangles. Proper design aligns SRIDs, enforces `NOT NULL`, uses appropriate MBR predicates, and verifies plans with `EXPLAIN`. When business rules demand exact shape semantics, use MBR as the candidate filter followed by `ST_*` to eliminate false positives.

## References

- MySQL 8.0 Reference Manual — Creating Spatial Indexes: https://dev.mysql.com/doc/refman/8.0/en/creating-spatial-indexes.html
- MySQL 8.0 Reference Manual — SPATIAL Index Optimization: https://dev.mysql.com/doc/refman/8.0/en/spatial-index-optimization.html
- MySQL 8.0 Reference Manual — Using Spatial Indexes: https://dev.mysql.com/doc/refman/8.0/en/using-spatial-indexes.html
- MySQL 8.0 Reference Manual — Optimizing Spatial Analysis: https://dev.mysql.com/doc/refman/8.0/en/optimizing-spatial-analysis.html
- MySQL 8.0 Reference Manual — Spatial Relation Functions Using MBRs: https://dev.mysql.com/doc/refman/8.0/en/spatial-relation-functions-mbr.html
- MySQL 8.0 Reference Manual — Spatial Relation Functions Using Object Shapes: https://dev.mysql.com/doc/refman/8.0/en/spatial-relation-functions-object-shapes.html
- MySQL 8.0 Reference Manual — Creating Spatial Columns: https://dev.mysql.com/doc/refman/8.0/en/creating-spatial-columns.html
