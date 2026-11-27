# JSON and Spatial Data Types

A MySQL application typically holds well-structured relational data such as customer IDs, order statuses, and monetary amounts. However, certain attributes vary per record type, or data describing map locations is awkward to represent cleanly with ordinary scalar columns. MySQL provides the `JSON` type for storing structured documents and spatial types such as `POINT`, `LINESTRING`, and `POLYGON` for storing geometry.

These two type groups solve different problems. JSON fits semi-structured attributes that need path-based reads and updates; spatial types fit coordinates, geographic regions, and geometric operations. Picking the right type, governing structure, and indexing properly enables efficient queries while preserving data consistency.

## 1. When Should You Use JSON and Spatial Types?

### 1.1. JSON for Semi-Structured Data

Suppose an e-commerce system carries many product categories. Phones have `screen_size`, `ram_gb`, `storage_gb`; shirts have `size`, `material`, `color`; appliances have `capacity_liter` and `power_watt`. You could create dozens of nullable columns in one shared table, or split every product type into separate tables. Another option is keeping variable attributes in a `JSON` column:

```json
{
  "screen_size": 6.7,
  "ram_gb": 12,
  "storage_gb": 256,
  "colors": ["black", "blue"]
}
```

JSON represents nested objects, arrays, strings, numbers, booleans, and nulls. MySQL can query individual elements, update a specific path, and expand array elements into rows using `JSON_TABLE`.

JSON should not replace all relational columns. Attributes with stable types and rules that are frequently filtered, joined, sorted, constrained, or referenced across tables should remain regular relational columns. A common pattern keeps core columns like `product_id`, `category_id`, `price`, and `created_at` as scalars while storing flexible attributes in JSON.

### 1.2. Spatial Types for Coordinates and Geometry

A delivery application may need to store store locations, drop-off points, routes, or service zones. Storing longitude and latitude in two `DECIMAL` columns suffices for simple display, but does not directly provide geometric operations or spatial indexing.

MySQL's spatial types store geometries such as points, lines, and polygons. Spatial functions calculate distances and test whether a point lies inside a region or whether two shapes intersect. Spatial indexes locate candidate objects within a region without scanning the entire table.

## 2. The JSON Type in MySQL

### 2.1. JSON Is a Native Data Type

MySQL introduced a native `JSON` type in MySQL 5.7.8. When writing to a `JSON` column, the server validates that the input is a valid JSON document and stores it in an internal binary format optimized for element access. It is not merely a `VARCHAR` column holding a JSON string. JSON functions and indexing features have expanded across releases, so verify your server version before using newer features.

Example creating an events table:

```sql
CREATE TABLE events (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    event_type VARCHAR(40) NOT NULL,
    payload JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_event_type_created (event_type, created_at)
) ENGINE=InnoDB;
```

Inserting a JSON document:

```sql
INSERT INTO events (event_type, payload)
VALUES (
    'order.created',
    '{"order_id": 9001, "customer": {"id": 120}, "items": [{"sku": "KB-01", "quantity": 2}], "source": "web"}'
);
```

If the string is not valid JSON, MySQL rejects it instead of storing a malformed document in a `JSON` column. On ordinary text columns, if you want to guarantee JSON validity, validate it explicitly or add an appropriate constraint such as `CHECK (JSON_VALID(column))` on versions supporting `CHECK`.

MySQL normalizes JSON documents on storage. Do not rely on key order inside a JSON object to represent business ordering; a JSON object is a collection of key/value pairs. For duplicate keys within the same object, normalization keeps the last value according to MySQL rules. If element order matters, use an array.

### 2.2. JSON Value Types

JSON supports basic value types:

| Type | Example |
|---|---|
| Object | `{"name": "An", "active": true}` |
| Array | `["red", "blue"]` |
| String | `"MySQL"` |
| Number | `12`, `3.14` |
| Boolean | `true`, `false` |
| JSON null | `null` |

Distinguish SQL `NULL` from JSON `null`. SQL `NULL` means the column has no value in SQL semantics; JSON `null` is a value inside a JSON document. A `JSON` column can hold the JSON document `null` without the column itself being SQL `NULL`.

### 2.3. Validating JSON and Inspecting Element Types

```sql
SELECT
    JSON_VALID('{"name":"An","age":28}') AS valid_document,
    JSON_TYPE(JSON_EXTRACT('{"age":28}', '$.age')) AS age_type,
    JSON_TYPE(JSON_EXTRACT('{"active":true}', '$.active')) AS active_type;
```

Commonly used functions:

| Function | Purpose |
|---|---|
| `JSON_VALID(doc)` | Checks whether a string/document is valid JSON |
| `JSON_TYPE(value)` | Returns the JSON value type such as `OBJECT`, `ARRAY`, `INTEGER`, `STRING`, `BOOLEAN`, `NULL` |
| `JSON_OBJECT(k, v, ...)` | Constructs a JSON object |
| `JSON_ARRAY(v, ...)` | Constructs a JSON array |
| `JSON_LENGTH(doc[, path])` | Counts object or array elements at path |
| `JSON_KEYS(doc[, path])` | Returns keys of an object |
| `JSON_DEPTH(doc)` | Maximum nesting depth of the document |
| `JSON_PRETTY(doc)` | Formats the document for human readability |

## 3. Extracting Values Using JSON Paths

A JSON path specifies the location of an element in a document. `$` is the root; `.key` navigates to an object property; `[index]` accesses an array element starting at 0.

Example document:

```json
{
  "order_id": 9001,
  "customer": {"id": 120, "name": "An"},
  "items": [
    {"sku": "KB-01", "quantity": 2},
    {"sku": "MS-02", "quantity": 1}
  ]
}
```

Corresponding paths:

| JSON path | Selected Value |
|---|---|
| `$.order_id` | `9001` |
| `$.customer.id` | `120` |
| `$.items[0].sku` | `"KB-01"` |
| `$.items[1].quantity` | `1` |

### 3.1. JSON_EXTRACT and Shorthand Operators

```sql
SELECT
    JSON_EXTRACT(payload, '$.order_id') AS order_id_json,
    payload->'$.customer.id' AS customer_id_json,
    payload->>'$.customer.name' AS customer_name_text,
    payload->>'$.items[0].sku' AS first_sku
FROM events
WHERE id = 1;
```

`JSON_EXTRACT(doc, path)` returns a JSON value. The `->` operator is shorthand for `JSON_EXTRACT`. The `->>` operator is equivalent to extracting the value and unquoting it with `JSON_UNQUOTE`, which is convenient when you need a SQL string for display or comparison.

When comparing numbers, pay attention to data types. `JSON_EXTRACT` returns a JSON number, whereas `->>` returns an unquoted string. Use `CAST` to convert to an explicit numeric type when performing numeric calculations or comparisons:

```sql
SELECT id
FROM events
WHERE CAST(payload->>'$.customer.id' AS UNSIGNED) = 120;
```

This query may have to read and convert many documents if no suitable index exists. The JSON indexing section shows how to expose frequently queried values via generated columns.

### 3.2. Distinguishing Missing Paths from JSON null

If a path does not exist, `JSON_EXTRACT` returns SQL `NULL`. If the path exists and contains JSON `null`, it returns a JSON null value. You can check path existence with `JSON_CONTAINS_PATH`:

```sql
SELECT
    JSON_CONTAINS_PATH('{"nickname": null}', 'one', '$.nickname') AS has_nickname,
    JSON_CONTAINS_PATH('{"nickname": null}', 'one', '$.missing') AS has_missing,
    JSON_TYPE(JSON_EXTRACT('{"nickname": null}', '$.nickname')) AS nickname_type;
```

This distinction matters for profile update APIs. A missing property may mean the user omitted the field; JSON `null` may mean the user wants to clear the value; SQL `NULL` may mean no payload was provided at all.

### 3.3. Querying Arrays

Functions such as `JSON_LENGTH`, `JSON_CONTAINS`, `JSON_SEARCH`, and `JSON_OVERLAPS` help inspect array/object contents. Example checking whether a tag exists in a `tags` array:

```sql
SELECT id
FROM products
WHERE JSON_CONTAINS(attributes, JSON_QUOTE('sale'), '$.tags');
```

`JSON_QUOTE` turns a SQL string into a valid JSON string literal. Starting in MySQL 8.0.17, `JSON_OVERLAPS` tests whether two documents share any elements, useful for comparing tag sets:

```sql
SELECT id
FROM products
WHERE JSON_OVERLAPS(attributes->'$.tags', JSON_ARRAY('sale', 'clearance'));
```

Verify your server version before using newer functions. If the application frequently filters arrays over large datasets, consider multi-valued indexes or normalizing the array into a child table.

## 4. Constructing and Updating JSON

### 4.1. Constructing Documents in SQL

Instead of concatenating JSON strings manually in application code, use JSON constructors to avoid quoting and escaping bugs:

```sql
SELECT JSON_OBJECT(
    'order_id', 9001,
    'status', 'PAID',
    'items', JSON_ARRAY(
        JSON_OBJECT('sku', 'KB-01', 'quantity', 2),
        JSON_OBJECT('sku', 'MS-02', 'quantity', 1)
    )
);
```

### 4.2. Modifying Part of a Document

Common JSON update functions:

| Function | Behavior |
|---|---|
| `JSON_SET(doc, path, value, ...)` | Inserts or updates the value at path |
| `JSON_INSERT(doc, path, value, ...)` | Inserts only if the path does not exist |
| `JSON_REPLACE(doc, path, value, ...)` | Replaces only if the path already exists |
| `JSON_REMOVE(doc, path, ...)` | Removes the element at path |
| `JSON_ARRAY_APPEND(doc, path, value, ...)` | Appends an element to the end of an array |
| `JSON_ARRAY_INSERT(doc, path, value, ...)` | Inserts an element at the specified array position |
| `JSON_MERGE_PATCH(doc, patch)` | Applies JSON Merge Patch rules to objects |

Example updating status and attempt count:

```sql
UPDATE events
SET payload = JSON_SET(
    payload,
    '$.status', 'processed',
    '$.attempts', 2
)
WHERE id = 1;
```

Appending a tag:

```sql
UPDATE products
SET attributes = JSON_ARRAY_APPEND(attributes, '$.tags', 'featured')
WHERE id = 42;
```

Removing an attribute:

```sql
UPDATE events
SET payload = JSON_REMOVE(payload, '$.temporary_token')
WHERE id = 1;
```

These functions produce a new JSON document according to each function's rules. When updating large documents, measure payload size, write frequency, and lock contention; do not assume modifying one path always writes only a few physical bytes.

### 4.3. Merge Patch and Null Values

`JSON_MERGE_PATCH` follows JSON Merge Patch semantics: a property in the patch with a JSON `null` value deletes that property from the target object. This differs from `JSON_SET`, which writes JSON `null` at the path. Choose the function matching your API's update semantics.

## 5. Transforming JSON into Relational Rows with JSON_TABLE

JSON is convenient for storing payloads, yet reports often need each array element as a row for joining, grouping, and aggregating. `JSON_TABLE` (MySQL 8.0.4 and later) converts a JSON document into a relational table inside a query.

Example extracting line items from an event payload:

```sql
SELECT
    e.id AS event_id,
    e.payload->>'$.order_id' AS order_id,
    item.sku,
    item.quantity
FROM events AS e
JOIN JSON_TABLE(
    e.payload,
    '$.items[*]' COLUMNS (
        sku VARCHAR(40) PATH '$.sku',
        quantity INT PATH '$.quantity'
    )
) AS item ON TRUE
WHERE e.event_type = 'order.created';
```

Each element of `items` generates one row in the output. You can specify `NULL ON EMPTY`, `ERROR ON EMPTY`, `NULL ON ERROR`, or `ERROR ON ERROR` in `JSON_TABLE` column definitions to control missing paths or unconvertible values. Choose explicit behavior rather than letting malformed data be interpreted silently.

`JSON_TABLE` is useful for reporting, imports, and data transformation. If the application regularly joins individual array elements with other tables, consider storing those elements in a relational child table for explicit foreign keys, indexes, and constraints.

## 6. Indexing JSON Data

MySQL does not build a standard B-tree index over every key inside a `JSON` column automatically. If queries frequently filter on an attribute, expose that value in an indexable structure.

### 6.1. Generated Columns Combined with Indexes

Suppose an application regularly filters products by `category` inside JSON:

```sql
CREATE TABLE products (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    name VARCHAR(160) NOT NULL,
    attributes JSON NOT NULL,
    category_code VARCHAR(40)
        GENERATED ALWAYS AS (
            JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.category'))
        ) STORED,
    PRIMARY KEY (id),
    KEY idx_category_code (category_code)
) ENGINE=InnoDB;
```

Queries can filter on the generated column:

```sql
SELECT id, name
FROM products
WHERE category_code = 'phone';
```

Generated columns can be `VIRTUAL` or `STORED`; indexing is supported on both in MySQL-supported scenarios. Choose based on computation cost, storage footprint, and query patterns. Use `EXPLAIN` to confirm the optimizer actually picks the index.

### 6.2. Functional Indexes

MySQL 8.0.13 and later supports functional key parts. You can create an index directly on an expression instead of declaring a visible generated column:

```sql
CREATE INDEX idx_priority
ON tasks ((CAST(payload->>'$.priority' AS UNSIGNED)));
```

Query predicates must match the indexed expression for the optimizer to recognize it. For complex expressions, a named generated column is often easier to read, inspect in metadata, and reference consistently in application code.

### 6.3. Multi-Valued Indexes for JSON Arrays

MySQL 8.0.17 and later supports multi-valued indexes, allowing one row to contribute multiple index entries from a JSON array. Example:

```sql
CREATE INDEX idx_product_tags
ON products ((CAST(attributes->'$.tags' AS CHAR(32) ARRAY)));
```

This index type helps certain array membership checks. It has constraints on supported types, expressions, and operators, and does not fully replace a child table with one row per tag. If you need joins, foreign keys, per-tag metadata, or complex queries, a relational model is usually easier to manage.

### 6.4. When Should You Normalize Instead of Keeping JSON?

Extract attributes into relational columns or tables when:

- The attribute has a stable type and is a mandatory business field.
- `NOT NULL`, `UNIQUE`, `CHECK`, or foreign keys are needed to protect integrity.
- The attribute is frequently used in joins, grouping, sorting, or filtering.
- Array elements need their own identifiers, independent updates, or foreign key references from other tables.
- Attribute-level access control or detailed change history is required.

JSON is meant for flexible extensibility, not for bypassing schema design. Maintain a clear boundary between core relational data and extensible attributes.

## 7. MySQL Spatial Data Types

### 7.1. Geometry Hierarchy

MySQL provides the base `GEOMETRY` type and its subtypes:

| Type | Description | Example Usage |
|---|---|---|
| `POINT` | A single point | Store, device, or customer location |
| `LINESTRING` | A sequence of connected points forming a path | Road route, travel path |
| `POLYGON` | A region bounded by closed rings | Delivery zone, district boundary |
| `MULTIPOINT` | A collection of points | Sensor locations or pickup points |
| `MULTILINESTRING` | A collection of line strings | Multiple road segments |
| `MULTIPOLYGON` | A collection of polygons | Multi-part disconnected service area |
| `GEOMETRYCOLLECTION` | A collection of heterogeneous geometries | Mixed geometric dataset |

These types represent geometry without inherent business semantics. For instance, a `POINT` could be a store or a driver location; the application gives it meaning through table, column, and attribute design.

### 7.2. Spatial Reference System (SRS) and SRID

An SRID (Spatial Reference System Identifier) identifies a geometry's spatial reference system. An SRS defines the coordinate system, axis order, units, and parameters needed to interpret coordinates.

Key points:

- SRID `0` is the default abstract Cartesian coordinate system, untied to any geographic coordinate system.
- SRID `4326` is commonly used for WGS 84, standard in GPS and GeoJSON data.
- Never arbitrarily compare or compute geometries from different SRSs.
- The same coordinate numbers mean different locations if the SRID or axis order differs.

Starting in MySQL 8.0, the server includes geographic SRS definitions in the data dictionary. You can inspect available SRSs via `INFORMATION_SCHEMA.ST_SPATIAL_REFERENCE_SYSTEMS` on supported versions.

### 7.3. Coordinate Axis Order

A common mistake is swapping longitude and latitude. Many mapping APIs pass coordinates as longitude, latitude; some SRS definitions such as EPSG:4326 define axis order as latitude, longitude. By default, MySQL follows the axis order declared by the SRS.

When input data is explicitly known to be longitude before latitude, specify the `axis-order=long-lat` option in geometry constructors. The `axis-order` option for spatial functions is supported starting in MySQL 8.0.12:

```sql
SET @store_point = ST_GeomFromText(
    'POINT(106.7009 10.7769)',
    4326,
    'axis-order=long-lat'
);
```

This example illustrates a location near central Ho Chi Minh City, with longitude `106.7009` and latitude `10.7769`. Always confirm the input format of your data source and apply the same convention consistently on read and write. Reversing axis order can yield a syntactically valid geometry plotted in the wrong part of the world.

## 8. Storing and Reading Spatial Data

### 8.1. Creating a Location Table

In MySQL 8.0, you can restrict a column to geometries of SRID 4326 using the `SRID` attribute:

```sql
CREATE TABLE stores (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    name VARCHAR(120) NOT NULL,
    location POINT NOT NULL SRID 4326,
    PRIMARY KEY (id),
    SPATIAL INDEX idx_location (location)
) ENGINE=InnoDB;
```

`POINT NOT NULL SRID 4326` enforces non-null points using that exact SRID. InnoDB spatial indexes use an R-tree structure for spatial data. Having an SRID-restricted, `NOT NULL` column is essential for the optimizer to utilize spatial indexes under MySQL rules.

### 8.2. Inserting Points

```sql
INSERT INTO stores (name, location)
VALUES (
    'Downtown Store',
    ST_GeomFromText(
        'POINT(106.7009 10.7769)',
        4326,
        'axis-order=long-lat'
    )
);
```

Reading coordinates as WKT (Well-Known Text):

```sql
SELECT
    id,
    name,
    ST_AsText(location) AS location_wkt,
    ST_SRID(location) AS srid,
    ST_GeometryType(location) AS geometry_type
FROM stores;
```

`ST_AsText` converts a geometry to a WKT string; `ST_SRID` returns the SRID; `ST_GeometryType` returns the geometry type. When exchanging data with mapping apps, you can also use `ST_AsGeoJSON` and `ST_GeomFromGeoJSON` on supported versions. Keep SRID and axis order consistent between MySQL and the application.

### 8.3. Assigning an SRID Is Not Coordinate Transformation

`ST_SRID(geometry, srid)` only sets the SRID metadata on a geometry; it does not transform coordinate numbers into a new reference system. If coordinates are in another projection, changing only the SRID label causes misinterpretation.

In MySQL 8.0.13 and later, `ST_Transform` performs actual coordinate transformation between compatible SRSs:

```sql
SELECT ST_Transform(location, 3857)
FROM stores;
```

Check version, source/target SRS, and units before transforming. Not every SRID pair has complete parameters or supported transformations.

## 9. Spatial Functions and Operations

### 9.1. Inspecting Geometries

Commonly used functions:

| Function | Meaning |
|---|---|
| `ST_GeomFromText(wkt, srid)` | Constructs a geometry from WKT |
| `ST_AsText(g)` | Converts a geometry to WKT |
| `ST_GeomFromGeoJSON(doc)` | Constructs a geometry from GeoJSON on supported versions |
| `ST_AsGeoJSON(g)` | Converts a geometry to GeoJSON on supported versions |
| `ST_SRID(g)` | Reads the SRID of a geometry |
| `ST_GeometryType(g)` | Reads the geometry type |
| `ST_IsValid(g)` | Checks whether a geometry is geometrically valid |
| `ST_Envelope(g)` | Returns the minimum bounding rectangle |

A syntactically valid geometry may still violate geographic or business rules. For instance, a polygon might self-intersect or have an invalid ring; verify validity and domain rules before computing with it.

### 9.2. Relationships Between Geometries

Common exact spatial predicate functions:

- `ST_Contains(a, b)`: geometry `a` geometrically contains geometry `b`.
- `ST_Within(a, b)`: geometry `a` lies within geometry `b`.
- `ST_Intersects(a, b)`: the two geometries intersect.
- `ST_Disjoint(a, b)`: the two geometries do not intersect.
- `ST_Touches(a, b)`: the two geometries touch at boundaries without intersecting interiors.
- `ST_Equals(a, b)`: the two geometries represent the same point set.
- `ST_Distance(a, b)`: computes distance per the SRS and function rules.

Example checking whether stores lie within a delivery zone:

```sql
SET @delivery_zone = ST_GeomFromText(
    'POLYGON((106.60 10.70, 106.82 10.70, 106.82 10.86, 106.60 10.86, 106.60 10.70))',
    4326,
    'axis-order=long-lat'
);

SELECT id, name
FROM stores
WHERE ST_Contains(@delivery_zone, location);
```

This uses a simple rectangle; real service zones typically need polygons following exact geographic boundaries. Both geometries must have compatible SRSs and matching axis order.

### 9.3. Distance and Units

Distances must be interpreted according to the chosen reference system and function. Never take raw differences on latitude/longitude coordinates and assume the unit is meters or kilometers.

`ST_Distance_Sphere(g1, g2)` computes spherical Earth distance and returns meters. This is an approximation suitable for many proximity searches. For high-precision requirements or wide geographic regions, choose calculations matching the geographic SRS, ellipsoid, and MySQL version; verify output units in function documentation.

Example comparing approximate distances from an origin point:

```sql
SET @origin = ST_GeomFromText(
    'POINT(106.7009 10.7769)',
    4326,
    'axis-order=long-lat'
);

SELECT
    id,
    name,
    ST_Distance_Sphere(location, @origin) AS distance_meters
FROM stores
ORDER BY distance_meters
LIMIT 10;
```

This query sorts by distance, which may require computing distance across many rows. On large tables, filter candidates first using a bounding box and spatial index before computing exact or approximate distances on candidates.

## 10. Spatial Indexes and Optimizing Spatial Queries

### 10.1. How Does a Spatial Index Work?

MySQL spatial indexes use an R-tree to organize minimum bounding rectangles (MBRs) of geometries. An MBR is the smallest axis-aligned rectangle enclosing a geometry. The index quickly finds objects whose bounding boxes overlap the search area.

MBR filtering is only a candidate filter. Two shapes whose MBRs overlap do not necessarily intersect geometrically. For queries requiring exact geometric relationships, apply exact predicates like `ST_Contains` or `ST_Intersects` alongside appropriate index filtering.

### 10.2. Creating a Spatial Index

```sql
ALTER TABLE stores
ADD SPATIAL INDEX idx_location (location);
```

Before creating the index, verify that the geometry column is `NOT NULL`, has an appropriate SRID restriction, and uses a storage engine supporting spatial indexes. InnoDB supports spatial indexes via R-trees. On columns without an SRID restriction, the optimizer may not use the spatial index as expected; check exact conditions for your MySQL version.

### 10.3. Filtering by Bounding Rectangle

Example finding points within a candidate rectangular region:

```sql
SET @search_box = ST_GeomFromText(
    'POLYGON((106.60 10.70, 106.82 10.70, 106.82 10.86, 106.60 10.86, 106.60 10.70))',
    4326,
    'axis-order=long-lat'
);

SELECT id, name
FROM stores
WHERE MBRContains(@search_box, location);
```

`MBRContains` evaluates the enclosing bounding rectangle. If the search region is a complex polygon, results can include points inside the bounding rectangle yet outside the true polygon. When exactness is required, combine with an exact geometric predicate:

```sql
SELECT id, name
FROM stores
WHERE MBRContains(@search_box, location)
  AND ST_Contains(@delivery_zone, location);
```

In this example, `@delivery_zone` is the business polygon created with the proper SRID and axis order. The MBR predicate narrows candidates; `ST_Contains` verifies the exact geometric relationship.

### 10.4. Verifying the Execution Plan

```sql
EXPLAIN
SELECT id, name
FROM stores
WHERE MBRContains(@search_box, location);
```

Check `key`, `type`, estimated rows, and filter conditions. The optimizer may skip a spatial index if the table is tiny, predicates do not qualify, or statistics/configuration make another plan cheaper. Do not assume an index is broken merely because one query does not use it; check DDL, SRID, nullability, data distribution, and `EXPLAIN`.

## 11. Combining JSON with Spatial Data

A delivery application may receive JSON device events containing status and coordinates:

```json
{
  "device_id": "DRV-100",
  "status": "moving",
  "position": {"longitude": 106.7009, "latitude": 10.7769},
  "speed_kmh": 28.5,
  "recorded_at": "2026-11-19T09:30:00Z"
}
```

If you need to retain raw payloads for auditing or compatibility across device firmware versions, store the JSON. If you need to search for drivers within a region, convert coordinates into a `POINT` with an explicit SRID and add a spatial index:

```sql
CREATE TABLE driver_positions (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    device_id VARCHAR(40) NOT NULL,
    payload JSON NOT NULL,
    location POINT NOT NULL SRID 4326,
    recorded_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    KEY idx_device_time (device_id, recorded_at),
    SPATIAL INDEX idx_driver_location (location)
) ENGINE=InnoDB;
```

Upon receiving a payload, the application or pipeline writes both JSON and geometry:

```sql
INSERT INTO driver_positions (device_id, payload, location, recorded_at)
VALUES (
    'DRV-100',
    '{"status":"moving","speed_kmh":28.5}',
    ST_GeomFromText('POINT(106.7009 10.7769)', 4326, 'axis-order=long-lat'),
    '2026-11-19 09:30:00'
);
```

In production systems, convert timestamps explicitly per time zone conventions, validate latitude/longitude bounds, validate payloads, and prevent drift between JSON and scalar columns. If a field is queried frequently, extract it into a dedicated column rather than keeping it solely inside JSON.

## 12. Common Mistakes

- **Storing JSON in `TEXT` and treating it like native JSON:** `JSON` columns enforce validation and use optimized internal storage; text columns require manual checks.
- **Putting every attribute in JSON:** core data needing keys, joins, and constraints belongs in relational columns/tables.
- **Comparing JSON numbers casually against strings:** use explicit types and `CAST` when needed.
- **Failing to distinguish SQL `NULL`, JSON `null`, and missing paths:** all three carry distinct meanings.
- **Assuming JSON automatically indexes every key:** use generated columns, functional indexes, or multi-valued indexes as appropriate.
- **Assuming `VIRTUAL` columns are free:** expressions still evaluate on read, and indexes still carry overhead.
- **Swapping longitude and latitude:** always confirm axis order and SRID of your data source.
- **Changing SRID without transforming coordinates:** `ST_SRID` does not reproject coordinates.
- **Treating MBR predicates as exact geometric relationships:** follow up with appropriate `ST_...` predicates to verify results.
- **Assuming distance outputs are always meters:** verify SRS and function units; `ST_Distance_Sphere` returns meters.
- **Creating spatial indexes on ineligible columns:** verify `NOT NULL`, SRID restriction, engine, and execution plans.

## 13. Pre-Design Checklist

- Is the data a stable relational attribute, a flexible JSON document, or spatial geometry?
- If using JSON, which fields are frequently filtered/joined and should be promoted to relational columns?
- How does the application distinguish SQL `NULL`, JSON `null`, and missing properties?
- Are `JSON_TABLE`, generated columns, functional indexes, or multi-valued indexes needed?
- Does the target MySQL version support the planned functions and index types?
- For spatial data, what are the SRID, SRS, units, and axis order?
- Are input coordinates longitude-latitude or latitude-longitude?
- Is the geometry column `NOT NULL` with an SRID restriction suitable for a spatial index?
- Do queries need bounding-box filtering or exact geometric predicates?
- Have you tested `EXPLAIN`, sample data, and malformed coordinate/JSON edge cases?

## Conclusion

The `JSON` type stores semi-structured data and supports path queries; generated columns, functional indexes, multi-valued indexes, and `JSON_TABLE` bridge JSON documents with relational queries. Spatial types such as `POINT`, `LINESTRING`, and `POLYGON` represent coordinates and geometry; SRIDs define reference systems, spatial functions perform geometric calculations, and R-tree indexes accelerate region filtering. Keep stable business attributes in relational columns, govern JSON structure, enforce explicit SRID/axis-order conventions, and inspect execution plans before deploying at scale.
