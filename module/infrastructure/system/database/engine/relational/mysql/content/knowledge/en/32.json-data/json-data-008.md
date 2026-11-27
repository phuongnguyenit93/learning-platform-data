# JSON_CONTAINS, JSON_OVERLAPS, and Component Querying

MySQL provides JSON functions to inspect structure and locate components inside JSON documents. Two commonly used functions are JSON_CONTAINS() and JSON_OVERLAPS(). Both answer questions about the relationship between two JSON values, but their semantics differ: JSON_CONTAINS() checks whether a document contains an entire candidate structure; JSON_OVERLAPS() checks whether two documents share at least one common element or key-value pair.

When you need to read deep inside JSON data, you can combine JSON_EXTRACT(), the -> and ->> operators, JSON paths, and JSON_TABLE(). These tools allow you to extract a field, traverse arrays, or transform JSON elements into rows and columns for SQL JOINs, filtering, grouping, and aggregation.

Within the **DATABASE_MYSQL** module, JSON fits data with flexible structure that still requires controlled querying. This lesson guides you through distinguishing containment from overlap, querying nested objects/arrays, turning elements into relational rows, and choosing appropriate indexes for real workloads.

## 1. Preparing JSON Data

MySQL has a native JSON data type. When executing INSERT or UPDATE on a JSON column, the server validates that the content is valid JSON and stores it in an internal format optimized for component access.

Example products table:

```sql
CREATE TABLE products (
    product_id BIGINT UNSIGNED NOT NULL,
    product_name VARCHAR(150) NOT NULL,
    attributes JSON NOT NULL,
    PRIMARY KEY (product_id)
) ENGINE = InnoDB;
```

Insert data containing objects, scalars, and arrays:

```sql
INSERT INTO products (
    product_id,
    product_name,
    attributes
)
VALUES
(
    1,
    'Travel Bottle',
    JSON_OBJECT(
        'brand', 'Northwind',
        'category', 'outdoor',
        'capacity_ml', 750,
        'features', JSON_ARRAY('insulated', 'leakproof'),
        'tags', JSON_ARRAY('travel', 'sale'),
        'dimensions', JSON_OBJECT(
            'height_cm', 25,
            'diameter_cm', 7
        )
    )
),
(
    2,
    'Desk Lamp',
    JSON_OBJECT(
        'brand', 'Contoso',
        'category', 'home',
        'features', JSON_ARRAY('dimmable', 'led'),
        'tags', JSON_ARRAY('office', 'new')
    )
);
```

Inspect the contents:

```sql
SELECT product_id, attributes
FROM products;
```

A JSON object contains key/value pairs; a JSON array contains ordered elements; scalars are strings, numbers, booleans, or JSON null. Nested structures can combine all three kinds.

## 2. JSON_CONTAINS(): Checking Whether One Structure Is Contained in Another

Syntax:

```sql
JSON_CONTAINS(target, candidate[, path])
```

The function returns:

- 1 if `candidate` is contained in `target` according to containment rules.
- 0 if `candidate` is not contained.
- SQL NULL if any argument is SQL NULL.
- An error if the JSON input or path is invalid.

You can pass `path` to restrict the check to a portion of the document. If `path` is omitted, MySQL checks the entire `target`.

### 2.1. Containment Rules for Objects

For two objects, `candidate` is contained in `target` if every key/value pair of `candidate` exists in `target`, with corresponding values considered equal according to JSON comparison rules.

Example:

```sql
SELECT JSON_CONTAINS(
    '{"brand":"Northwind","category":"outdoor","capacity_ml":750}',
    '{"brand":"Northwind"}'
) AS is_contained;
```

The result is 1 because `target` has the pair `brand = Northwind`.

If `candidate` requires an additional pair not present in `target`:

```sql
SELECT JSON_CONTAINS(
    '{"brand":"Northwind","category":"outdoor"}',
    '{"brand":"Northwind","color":"blue"}'
) AS is_contained;
```

The result is 0 because `target` does not have `color = blue`.

A `candidate` object can be a subset of a larger object. It does not need to contain all keys of `target`.

### 2.2. Containment Rules for Arrays

When `candidate` is an array, every element of `candidate` must be found in the `target` array according to containment rules. A candidate array therefore expresses a complete set of required conditions.

```sql
SELECT JSON_CONTAINS(
    '["travel","sale","featured"]',
    '["travel","sale"]'
) AS contains_all;
```

The result is 1 because both `travel` and `sale` are in `target`.

If one element does not exist:

```sql
SELECT JSON_CONTAINS(
    '["travel","sale"]',
    '["travel","clearance"]'
) AS contains_all;
```

The result is 0.

If `candidate` is a scalar and `target` is an array, the function checks whether that scalar is an element of `target`:

```sql
SELECT JSON_CONTAINS(
    '["travel","sale"]',
    '"sale"'
) AS has_sale;
```

The result is 1.

Note that a candidate string must be a valid JSON string. The SQL literal `'"sale"'` contains the JSON string `"sale"`; the SQL literal `'sale'` is not a valid JSON document.

### 2.3. Containment Rules for Arrays of Objects

A common case is finding an object inside an array:

```sql
SELECT JSON_CONTAINS(
    '[
        {"sku":"A-100","qty":2,"warehouse":"HCM"},
        {"sku":"B-200","qty":1,"warehouse":"HN"}
    ]',
    '{"sku":"A-100","qty":2}'
) AS item_found;
```

The result is 1 because one object element contains both `sku = A-100` and `qty = 2`. `candidate` does not need to list `warehouse`.

You can apply this directly to a path in a JSON column:

```sql
SELECT product_id, product_name
FROM products
WHERE JSON_CONTAINS(
    attributes,
    JSON_ARRAY('insulated', 'leakproof'),
    '$.features'
);
```

The query selects products that have both features. Because `features` is an array, JSON_CONTAINS requires every candidate element to be contained.

### 2.4. Finding an Object Inside a Table's JSON Array

Suppose orders contain an item list:

```sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL,
    payload JSON NOT NULL,
    PRIMARY KEY (order_id)
) ENGINE = InnoDB;

INSERT INTO orders (order_id, payload)
VALUES
(
    1001,
    JSON_OBJECT(
        'customer_id', 501,
        'items', JSON_ARRAY(
            JSON_OBJECT('sku', 'A-100', 'qty', 2),
            JSON_OBJECT('sku', 'B-200', 'qty', 1)
        )
    )
);
```

Find orders containing item SKU A-100:

```sql
SELECT order_id
FROM orders
WHERE JSON_CONTAINS(
    payload,
    JSON_OBJECT('sku', 'A-100'),
    '$.items'
);
```

Path `$.items` points to the array. The candidate object is matched against the elements of the array; having a single element satisfy the candidate object is sufficient under array containment rules.

To require an item with both SKU and quantity:

```sql
SELECT order_id
FROM orders
WHERE JSON_CONTAINS(
    payload,
    JSON_OBJECT('sku', 'A-100', 'qty', 2),
    '$.items'
);
```

## 3. JSON_OVERLAPS(): Checking for Common Elements

Syntax:

```sql
JSON_OVERLAPS(json_doc1, json_doc2)
```

JSON_OVERLAPS() returns 1 if two JSON documents share at least one common component under comparison rules; returns 0 if none; returns SQL NULL if any argument is SQL NULL.

Unlike JSON_CONTAINS(), it does not require one document to contain the entire other document. Just a single common element or key/value pair suffices.

### 3.1. Two Arrays Sharing at Least One Element

```sql
SELECT JSON_OVERLAPS(
    '["travel","sale","featured"]',
    '["new","sale"]'
) AS has_overlap;
```

The result is 1 because `sale` appears in both arrays.

If there are no common elements:

```sql
SELECT JSON_OVERLAPS(
    '["travel","sale"]',
    '["office","new"]'
) AS has_overlap;
```

The result is 0.

Use JSON_OVERLAPS() when the business condition is "has any tag from the requested list", rather than "must have every tag".

### 3.2. Two Objects Sharing a Key/Value Pair

For objects, two documents overlap if they share at least one identical key and corresponding value.

```sql
SELECT JSON_OVERLAPS(
    '{"brand":"Northwind","category":"outdoor"}',
    '{"category":"outdoor","color":"blue"}'
) AS has_overlap;
```

The result is 1 because both have the pair `category = outdoor`.

Having the same key with different values is not enough:

```sql
SELECT JSON_OVERLAPS(
    '{"status":"PAID"}',
    '{"status":"PENDING"}'
) AS has_overlap;
```

The result is 0. The key/value pairs are not the same.

### 3.3. Scalar and Array

If one argument is a scalar and the other is an array, the function checks whether the scalar is an element of the array:

```sql
SELECT JSON_OVERLAPS(
    '"sale"',
    '["new","sale","featured"]'
) AS has_overlap;
```

The result is 1.

Two scalars overlap when they are equal under JSON comparison rules:

```sql
SELECT JSON_OVERLAPS('42', '42') AS same_value;
```

The result is 1.

### 3.4. Comparison Does Not Recurse Automatically into Nested Structures

JSON_OVERLAPS() compares values at the top level of the two passed documents. It does not automatically recurse through all nested objects or arrays to find a scalar anywhere inside. When comparing a nested part, extract the exact path first:

```sql
SELECT JSON_OVERLAPS(
    payload->'$.tags',
    JSON_ARRAY('sale', 'featured')
)
FROM orders;
```

If `tags` resides inside each item of an `items` array, use JSON_TABLE to expand items and tags into rows rather than assuming JSON_OVERLAPS will search across all nesting levels.

### 3.5. Using with a JSON Column Containing Tags

If a product has multiple tags and a query needs to match any tag in a requested set:

```sql
SELECT product_id, product_name
FROM products
WHERE JSON_OVERLAPS(
    attributes->'$.tags',
    JSON_ARRAY('sale', 'featured')
);
```

A product is selected if `tags` contains at least one of `sale` or `featured`.

If business logic requires all tags to be present, use JSON_CONTAINS:

```sql
SELECT product_id, product_name
FROM products
WHERE JSON_CONTAINS(
    attributes->'$.tags',
    JSON_ARRAY('sale', 'featured')
);
```

This is the key difference between the two functions:

| Need | Suitable Function |
|---|---|
| Has all elements in the requested list | JSON_CONTAINS |
| Has at least one element in the requested list | JSON_OVERLAPS |
| Object contains all candidate key/value pairs | JSON_CONTAINS |
| Two objects share at least one key/value pair | JSON_OVERLAPS |

JSON_OVERLAPS() was added in MySQL 8.0.17. If the system runs an older version, check the version before using this function or write an equivalent condition for the data structure.

## 4. JSON Type Comparison and NULL Handling

JSON functions compare values according to JSON types. Do not rely on implicit coercion between string, number, and boolean.

For example, the string `"42"` differs from the number `42`:

```sql
SELECT
    JSON_CONTAINS('["42"]', '42') AS string_array_contains_number,
    JSON_CONTAINS('[42]', '"42"') AS number_array_contains_string;
```

Both expressions return 0. Use candidates with types matching the stored data.

For numeric scalars, MySQL allows comparing INTEGER and DECIMAL values under JSON containment rules; do not generalize that into assuming all types are coerced into one another.

### 4.1. SQL NULL Differs from JSON null

Three cases must be distinguished:

1. SQL NULL: no SQL value exists.
2. JSON null: a valid JSON value inside the document.
3. Missing path: JSON_EXTRACT typically returns SQL NULL because the path is not found.

Example:

```sql
SELECT
    JSON_EXTRACT('{"a":null}', '$.a') AS explicit_json_null,
    JSON_EXTRACT('{"b":1}', '$.a') AS missing_path,
    JSON_TYPE(JSON_EXTRACT('{"a":null}', '$.a')) AS json_type;
```

For an existing path containing JSON null, the result is a JSON null value. For a missing path, JSON_EXTRACT returns SQL NULL. JSON_TYPE of a JSON null value returns the string `NULL`.

You can check path existence using JSON_CONTAINS_PATH:

```sql
SELECT
    JSON_CONTAINS_PATH(
        '{"a":null}',
        'one',
        '$.a'
    ) AS path_exists,
    JSON_CONTAINS_PATH(
        '{"a":null}',
        'one',
        '$.missing'
    ) AS missing_path_exists;
```

JSON_CONTAINS() and JSON_OVERLAPS() return SQL NULL if any SQL argument is NULL. Therefore, when a JSON column allows NULL or a path expression can return SQL NULL, define explicitly how it is handled in WHERE, IF, or CASE.

### 4.2. Checking Data Types Before Comparing

You can use JSON_TYPE() to inspect a component's type:

```sql
SELECT
    JSON_TYPE(attributes->'$.capacity_ml') AS capacity_type,
    JSON_TYPE(attributes->'$.features') AS features_type,
    JSON_TYPE(attributes->'$.brand') AS brand_type
FROM products
WHERE product_id = 1;
```

Common types include OBJECT, ARRAY, STRING, INTEGER, DOUBLE, DECIMAL, BOOLEAN, and NULL. The result depends on the actual JSON value and version.

When applications supply candidates, standardize schemas and data types. For instance, product codes should always be strings if stored as strings; quantities should always be numbers. Do not send `"2"` sometimes and `2` other times if logic depends on exact matching.

## 5. JSON Paths for Accessing Components

A JSON path specifies the location to read in a document. Common forms:

| Path | Meaning |
|---|---|
| $ | Entire document |
| $.brand | Key `brand` in the root object |
| $.dimensions.height_cm | Nested key |
| $.features[0] | First element of the array |
| $.items[*].sku | `sku` field of every element in `items` |
| $[1] | Second element of a root array |

Array indices start at 0.

Example retrieving capacity:

```sql
SELECT
    JSON_EXTRACT(attributes, '$.capacity_ml') AS capacity
FROM products;
```

Retrieve the first element of `features`:

```sql
SELECT
    JSON_EXTRACT(attributes, '$.features[0]') AS first_feature
FROM products;
```

Retrieve all SKUs in the array:

```sql
SELECT
    JSON_EXTRACT(payload, '$.items[*].sku') AS item_skus
FROM orders;
```

JSON_EXTRACT with a wildcard can return a JSON array containing the matching results.

### 5.1. The -> and ->> Operators

The `->` operator is shorthand for JSON_EXTRACT:

```sql
SELECT attributes->'$.brand' AS brand_json
FROM products;
```

The result is still a JSON value. When you need an SQL string with JSON quotes stripped, use `->>`:

```sql
SELECT attributes->>'$.brand' AS brand_text
FROM products;
```

`->>` is equivalent to using JSON_UNQUOTE(JSON_EXTRACT(...)).

```sql
SELECT
    JSON_UNQUOTE(
        JSON_EXTRACT(attributes, '$.brand')
    ) AS brand_text
FROM products;
```

Use `->>` when comparing against VARCHAR, displaying strings, or JOINing with text columns. For numeric values, CAST to an appropriate SQL type if performing arithmetic or numeric comparisons:

```sql
SELECT product_id
FROM products
WHERE CAST(
    attributes->>'$.capacity_ml' AS UNSIGNED
) >= 500;
```

If numeric queries run frequently, consider a typed generated column and index instead of repeated CASTs on every row.

### 5.2. JSON_CONTAINS with Paths and Wildcard Restrictions

You can check containment at a specific path:

```sql
SELECT JSON_CONTAINS(
    attributes,
    '"outdoor"',
    '$.category'
)
FROM products;
```

The path argument of JSON_CONTAINS() does not allow wildcards `*` or `**`. If you need to check elements inside an array, point to the array such as `$.features` or `$.items`, and let containment rules evaluate its elements.

For queries extracting multiple elements, JSON_EXTRACT supports appropriate wildcard paths:

```sql
SELECT JSON_EXTRACT(
    payload,
    '$.items[*].sku'
)
FROM orders;
```

Do not confuse JSON_EXTRACT's wildcard capability with JSON_CONTAINS's path argument.

## 6. Querying Nested Fields and Combining Conditions

You can combine JSON_EXTRACT, JSON_CONTAINS, and JSON_OVERLAPS in WHERE:

```sql
SELECT
    product_id,
    product_name,
    attributes->>'$.brand' AS brand
FROM products
WHERE attributes->>'$.category' = 'outdoor'
  AND JSON_OVERLAPS(
      attributes->'$.features',
      JSON_ARRAY('insulated', 'waterproof')
  );
```

The query filters `category` as `outdoor` and requires at least one feature in the requested list.

If all features are required:

```sql
SELECT product_id, product_name
FROM products
WHERE attributes->>'$.category' = 'outdoor'
  AND JSON_CONTAINS(
      attributes->'$.features',
      JSON_ARRAY('insulated', 'leakproof')
  );
```

If both `category` and a specific nested object structure are required:

```sql
SELECT product_id
FROM products
WHERE JSON_CONTAINS(
    attributes,
    JSON_OBJECT(
        'category', 'outdoor',
        'dimensions', JSON_OBJECT('height_cm', 25)
    )
);
```

The candidate object must be contained according to the nested structure. A nested object cannot be substituted by a scalar with similar display text.

## 7. Turning JSON Arrays into Rows with JSON_TABLE

JSON_EXTRACT works well for retrieving values. When you need JOIN, GROUP BY, filtering multiple attributes per element, or aggregation, JSON_TABLE() is usually easier to use.

JSON_TABLE() turns elements selected by a JSON path into a virtual relational table in the SELECT statement. This function has existed since MySQL 8.0.4.

Example order payload:

```sql
SELECT
    o.order_id,
    jt.item_no,
    jt.sku,
    jt.qty
FROM orders AS o
JOIN JSON_TABLE(
    o.payload,
    '$.items[*]'
    COLUMNS (
        item_no FOR ORDINALITY,
        sku VARCHAR(64) PATH '$.sku',
        qty INT PATH '$.qty'
    )
) AS jt ON TRUE;
```

Explanation:

- `o.payload`: input JSON document.
- `$.items[*]`: each element in the `items` array produces a row.
- `FOR ORDINALITY`: generates a sequence number starting from 1.
- `PATH '$.sku'`: extracts `sku` from the element object.
- `PATH '$.qty'`: extracts `qty` and converts it to SQL INT.
- `AS jt`: alias for referencing columns produced by JSON_TABLE.

The result has one row per item. Columns such as `jt.sku` can be used in WHERE, JOIN, and GROUP BY like columns of a regular table.

### 7.1. Controlling Missing or Unconvertible Data

JSON_TABLE supports ON EMPTY and ON ERROR per column:

```sql
SELECT
    o.order_id,
    jt.sku,
    jt.qty
FROM orders AS o
JOIN JSON_TABLE(
    o.payload,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(64) PATH '$.sku'
            ERROR ON EMPTY
            ERROR ON ERROR,
        qty INT PATH '$.qty'
            DEFAULT '1' ON EMPTY
            NULL ON ERROR
    )
) AS jt ON TRUE;
```

- `ERROR ON EMPTY`: raises an error when the column path finds nothing.
- `DEFAULT '1' ON EMPTY`: uses a default value if the path does not exist.
- `NULL ON ERROR`: returns SQL NULL when conversion or extraction triggers an ON ERROR condition.

The standard declaration order is ON EMPTY before ON ERROR. Choose policies based on the data contract: required fields should error or be explicitly validated; optional fields may take defaults or NULL.

Do not use DEFAULT to silently mask bad data. If a `qty` value has an invalid format, decide whether that is a data error or safely ignorable.

### 7.2. Filtering and Aggregating JSON Elements

Once converted into rows, individual items can be filtered:

```sql
SELECT
    o.order_id,
    jt.sku,
    jt.qty
FROM orders AS o
JOIN JSON_TABLE(
    o.payload,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(64) PATH '$.sku',
        qty INT PATH '$.qty'
    )
) AS jt ON TRUE
WHERE jt.qty >= 2;
```

Aggregate quantities by SKU:

```sql
SELECT
    jt.sku,
    SUM(jt.qty) AS total_qty
FROM orders AS o
JOIN JSON_TABLE(
    o.payload,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(64) PATH '$.sku',
        qty INT PATH '$.qty'
    )
) AS jt ON TRUE
GROUP BY jt.sku
ORDER BY total_qty DESC;
```

JSON_TABLE helps convert semi-structured layouts into relational form to leverage familiar SQL tools. However, every execution still reads and parses the relevant documents; if component querying is a hot workload, consider normalizing into a child table or adding suitable indexes.

### 7.3. NESTED PATH for Nested Arrays

An element may contain a child array. Use NESTED PATH to generate columns from nested structures:

```sql
SELECT
    o.order_id,
    jt.sku,
    jt.discount_code
FROM orders AS o
JOIN JSON_TABLE(
    o.payload,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(64) PATH '$.sku',
        NESTED PATH '$.discounts[*]'
        COLUMNS (
            discount_code VARCHAR(32) PATH '$'
        )
    )
) AS jt ON TRUE;
```

Each discount in each item can produce a row. When the nested path finds no matches, JSON_TABLE can still emit the parent row with nested columns set to SQL NULL under NESTED PATH semantics. If multiple nested arrays exist, evaluate row multiplication and potential result blowup.

## 8. Choosing the Right Function to Inspect Data

Several functions are commonly used alongside JSON_CONTAINS and JSON_OVERLAPS:

| Function | Purpose |
|---|---|
| JSON_CONTAINS | Checks whether candidate is contained in target |
| JSON_OVERLAPS | Checks whether two documents share any common components |
| JSON_CONTAINS_PATH | Checks whether one or all JSON paths exist |
| JSON_EXTRACT | Extracts values by JSON path |
| JSON_LENGTH | Counts array/object elements or length at a path |
| JSON_KEYS | Returns the list of keys in an object |
| JSON_SEARCH | Finds paths containing strings matching a pattern |
| JSON_TABLE | Transforms JSON data into relational rows/columns |
| JSON_TYPE | Identifies the JSON type of a value |

Example checking path existence:

```sql
SELECT product_id
FROM products
WHERE JSON_CONTAINS_PATH(
    attributes,
    'all',
    '$.brand',
    '$.features'
);
```

`one` means at least one path exists; `all` means all listed paths exist. This function only checks existence, not whether the underlying values satisfy conditions.

Count features:

```sql
SELECT
    product_id,
    JSON_LENGTH(attributes, '$.features') AS feature_count
FROM products;
```

List object keys:

```sql
SELECT JSON_KEYS(attributes)
FROM products;
```

If you need pattern matching on strings, JSON_SEARCH() can return paths of string values matching a pattern. It is not a general finder for all JSON value types and does not replace JSON_CONTAINS().

## 9. Indexes for JSON Queries

A JSON column cannot be used as an ordinary B-tree index to search arbitrary paths. If a workload frequently filters by a scalar path, you can create a generated column and index that column.

### 9.1. Generated Columns for Scalar Paths

Example where `category` is queried frequently:

```sql
ALTER TABLE products
    ADD COLUMN category VARCHAR(50)
        GENERATED ALWAYS AS (
            JSON_UNQUOTE(
                JSON_EXTRACT(attributes, '$.category')
            )
        ) STORED,
    ADD INDEX idx_products_category (category);
```

Then query:

```sql
SELECT product_id, product_name
FROM products
WHERE category = 'outdoor';
```

A generated column has an explicit SQL type and can be indexed like a normal column. Choose length, charset, collation, and numeric type matching the data; if the path can be missing or mistyped, define NULL/default/conversion semantics clearly.

### 9.2. Multi-Valued Indexes for JSON Arrays

Since MySQL 8.0.17, InnoDB supports multi-valued indexes (MVI) to index multiple scalar elements within a JSON array. MVI is useful for array membership queries, including eligible predicates using JSON_CONTAINS(), JSON_OVERLAPS(), and MEMBER OF().

Example indexing the `tags` array:

```sql
CREATE INDEX idx_products_tags
ON products (
    (
        CAST(
            attributes->'$.tags'
            AS CHAR(32) ARRAY
        )
    )
);
```

Overlap query:

```sql
SELECT product_id, product_name
FROM products
WHERE JSON_OVERLAPS(
    attributes->'$.tags',
    JSON_ARRAY('sale', 'featured')
);
```

If the predicate's expression and data type match the MVI, the optimizer can use the index to find rows containing matching elements. Having an index does not guarantee the optimizer always picks it; confirm with EXPLAIN on representative data.

MVI has important limitations:

- Supported only on InnoDB.
- Each index can have only one multi-valued key part.
- MVI does not replace ordinary B-tree indexes for all query types.
- Does not provide element sort ordering like a standard B-tree key.
- Must choose a CAST type matching the JSON element type and data length.
- Predicates must be compatible with the index expression so the optimizer can leverage it.

If an array holds complex objects or requires JOINing multiple attributes per element, a relational child table is usually easier to index and constrain than an MVI.

### 9.3. When Should a JSON Array Be Normalized into a Child Table?

A JSON array fits when elements are usually read with the document, structure changes flexibly, and strong relational constraints are unnecessary.

Consider a child table when:

- Frequent JOINs per element are needed.
- Foreign keys or UNIQUE constraints on elements are needed.
- Independent updates/deletes per element are needed.
- Aggregations, pagination, or sorting over individual elements are needed.
- Arrays are large or component querying is the primary workload.

Example relational table:

```sql
CREATE TABLE product_tags (
    product_id BIGINT UNSIGNED NOT NULL,
    tag VARCHAR(32) NOT NULL,
    PRIMARY KEY (product_id, tag),
    KEY idx_product_tags_tag (tag),
    CONSTRAINT fk_product_tags_product
        FOREIGN KEY (product_id)
        REFERENCES products (product_id)
) ENGINE = InnoDB;
```

Find products having tag `sale` or `featured`:

```sql
SELECT DISTINCT product_id
FROM product_tags
WHERE tag IN ('sale', 'featured');
```

A child table cleanly supports indexes, constraints, and JOINs. In return, the application must maintain consistency between parent data and child rows within transactions.

## 10. Optimizing JSON Queries

Some guidelines:

1. Extract only needed paths; avoid fetching the entire document unnecessarily.
2. Use JSON_CONTAINS when all candidates must be present; use JSON_OVERLAPS when only one common element is needed.
3. Use JSON_TABLE when multiple elements must become rows for JOINs or aggregations.
4. For frequently queried scalar paths, consider a generated column and index.
5. For scalar arrays, consider MVI if version and predicates match.
6. For complex relationships, consider a child table instead of keeping everything in JSON.
7. Use EXPLAIN to verify index selection.
8. Measure on data whose size and distribution resemble production.

Example inspecting the execution plan:

```sql
EXPLAIN FORMAT = JSON
SELECT product_id
FROM products
WHERE JSON_OVERLAPS(
    attributes->'$.tags',
    JSON_ARRAY('sale', 'featured')
);
```

Inspect access path, chosen key, estimated rows, and filters. If MVI is not used, verify the index expression, CAST type, element types, and server version.

Do not create an MVI or generated column for every path. Every index increases storage size and INSERT/UPDATE cost; when a JSON document changes, corresponding indexes must also be maintained.

## 11. Safety When Building JSON Candidates from Applications

Never build JSON strings from user data via manual string concatenation. Use parameter binding and JSON functions to avoid escaping bugs and preserve types.

Example using JSON_ARRAY:

```sql
SELECT product_id
FROM products
WHERE JSON_OVERLAPS(
    attributes->'$.tags',
    JSON_ARRAY(?, ?)
);
```

Example using JSON_OBJECT:

```sql
SELECT order_id
FROM orders
WHERE JSON_CONTAINS(
    payload,
    JSON_OBJECT('sku', ?, 'qty', ?),
    '$.items'
);
```

If the application passes a complete JSON document, bind it as a parameter and CAST to JSON if needed:

```sql
SELECT product_id
FROM products
WHERE JSON_CONTAINS(
    attributes,
    CAST(? AS JSON),
    '$.features'
);
```

Never concatenate user values directly into JSON paths or dynamic SQL. If a path must vary by feature, use an allowlist of permitted paths and validate input. An invalid path can cause query errors; an overly broad path can also make queries consume more resources than expected.

## 12. Comprehensive Example: Finding Orders by SKU and Quantity

Requirement: find orders containing item SKU A-100 with quantity at least 2, then list every item of those orders.

Using JSON_CONTAINS to filter documents:

```sql
SELECT order_id
FROM orders
WHERE JSON_CONTAINS(
    payload,
    JSON_OBJECT('sku', 'A-100', 'qty', 2),
    '$.items'
);
```

Note: the candidate object here checks `qty` equal to exactly 2. If `qty >= 2` is required, JSON_CONTAINS cannot express range comparisons. Use JSON_TABLE to convert `qty` into a numeric column:

```sql
SELECT DISTINCT o.order_id
FROM orders AS o
JOIN JSON_TABLE(
    o.payload,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(64) PATH '$.sku',
        qty INT PATH '$.qty'
    )
) AS jt ON TRUE
WHERE jt.sku = 'A-100'
  AND jt.qty >= 2;
```

To inspect all items of matching orders, you can use a CTE:

```sql
WITH matching_orders AS (
    SELECT DISTINCT o.order_id
    FROM orders AS o
    JOIN JSON_TABLE(
        o.payload,
        '$.items[*]'
        COLUMNS (
            sku VARCHAR(64) PATH '$.sku',
            qty INT PATH '$.qty'
        )
    ) AS x ON TRUE
    WHERE x.sku = 'A-100'
      AND x.qty >= 2
)
SELECT
    o.order_id,
    jt.sku,
    jt.qty
FROM matching_orders AS m
JOIN orders AS o
    ON o.order_id = m.order_id
JOIN JSON_TABLE(
    o.payload,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(64) PATH '$.sku',
        qty INT PATH '$.qty'
    )
) AS jt ON TRUE
ORDER BY o.order_id, jt.sku;
```

This example illustrates the boundary between the two tool groups:

- JSON_CONTAINS fits checking whether a structure contains a candidate.
- JSON_TABLE fits comparing individual fields with SQL conditions such as `>=`, `BETWEEN`, `JOIN`, or `GROUP BY`.

## 13. Common Mistakes

| Mistake | Consequence | How to Handle |
|---|---|---|
| Using JSON_CONTAINS when any single element suffices | Condition is too strict because every candidate array element must be present | Use JSON_OVERLAPS |
| Using JSON_OVERLAPS when all elements are required | Returns rows sharing only one element | Use JSON_CONTAINS |
| Confusing JSON string with SQL string | Candidate is not valid JSON or has mismatched type | Use JSON_ARRAY/JSON_OBJECT or proper JSON literals |
| Comparing string `"42"` with number `42` | Fails to match due to differing JSON types | Normalize data types |
| Using JSON_CONTAINS path with wildcards | Invalid path | Point to a concrete array or use JSON_EXTRACT/JSON_TABLE |
| Using JSON_EXTRACT and comparing objects as text | Comparison breaks easily due to formatting/types | Use JSON_CONTAINS/JSON_OVERLAPS or JSON_TYPE |
| Treating JSON null as SQL NULL | Misses JSON null values or missing paths | Distinguish via JSON_TYPE and JSON_CONTAINS_PATH |
| Using JSON_CONTAINS to check `qty >= n` | Containment checks structure/values, not ranges | Use JSON_TABLE or a generated scalar column |
| Using JSON_TABLE on very large arrays in every query | High CPU cost and potential row blowup | Normalize into a child table or index per workload |
| Assuming a JSON column auto-indexes all paths | Queries still scan many documents | Generated column or MVI |
| Creating MVI yet optimizer skips it | Predicate does not match expression/type or another plan is cheaper | Check version, CAST, and EXPLAIN |
| Building JSON from input via string concatenation | Escaping bugs and injection risk | Parameter binding and JSON_OBJECT/JSON_ARRAY |

## 14. Checklist for Choosing JSON Tools

Before writing queries:

- Determine whether data is an object, array, or scalar.
- Determine whether the condition requires all elements or any element.
- Determine the path and candidate data type.
- Distinguish SQL NULL, JSON null, and non-existent paths.
- If range comparisons or per-element aggregation are needed, use JSON_TABLE.
- If only path existence is needed, use JSON_CONTAINS_PATH.
- If reading scalars, use JSON_EXTRACT or `->>`; choose the right SQL type.
- If using JSON_OVERLAPS, verify MySQL 8.0.17 or later.
- If using JSON_TABLE, verify MySQL 8.0.4 or later.

Before deploying:

- Verify JSON documents are valid and data schemas are consistent.
- Bind parameters instead of concatenating JSON strings.
- Consider generated columns for hot scalar-path queries.
- Consider MVI for scalar arrays if predicates are supported.
- Consider child tables when constraints/JOINs/per-element updates are required.
- Read EXPLAIN and benchmark on representative data.
- Measure write overhead, index footprint, and query latency.
- Have a migration plan when JSON structure evolves.

## 15. Key Takeaways

- JSON_CONTAINS(target, candidate[, path]) checks whether `candidate` is contained inside `target`.
- For objects, `candidate` must match all its key/value pairs; for arrays, every `candidate` element must be contained.
- JSON_OVERLAPS(doc1, doc2) only requires at least one shared element or key/value pair.
- Use JSON_CONTAINS when matching all; use JSON_OVERLAPS when matching any.
- JSON_OVERLAPS has been available since MySQL 8.0.17.
- JSON comparisons respect types; strings and numbers are not the same value.
- SQL NULL, JSON null, and missing paths are distinct cases.
- JSON paths start with `$`, and array indices start at 0.
- JSON_EXTRACT/`->` returns JSON; `->>` returns unquoted values for use as SQL strings.
- JSON_CONTAINS paths do not support wildcards; JSON_EXTRACT and JSON_TABLE fit reading multiple elements better.
- JSON_TABLE turns JSON arrays/objects into rows and columns for JOINs, filtering, grouping, and aggregation.
- JSON_CONTAINS cannot express range conditions like `qty >= 2`; use JSON_TABLE or relational columns.
- Generated columns fit indexing scalar paths; MVI can index scalar elements inside JSON arrays on InnoDB.
- If foreign keys, unique constraints, or independent per-element updates are needed, consider a child-table model.
- Use parameter binding and JSON_ARRAY/JSON_OBJECT to build candidates safely.

Choose JSON functions matching the exact business question: containment to verify required complete structure, overlap to test intersection, JSON paths to locate components, and JSON_TABLE to bring elements into relational form. Then verify performance with execution plans and choose indexes or data models suited to real query frequency.

## References

- MySQL 8.0 Reference Manual — JSON Search Functions: https://dev.mysql.com/doc/refman/8.0/en/json-search-functions.html
- MySQL 8.0 Reference Manual — JSON Utility Functions: https://dev.mysql.com/doc/refman/8.0/en/json-utility-functions.html
- MySQL 8.0 Reference Manual — JSON Table Functions: https://dev.mysql.com/doc/refman/8.0/en/json-table-functions.html
- MySQL 8.0 Reference Manual — JSON Path Syntax: https://dev.mysql.com/doc/refman/8.0/en/json-path-syntax.html
- MySQL 8.0 Reference Manual — Multi-Valued Indexes: https://dev.mysql.com/doc/refman/8.0/en/create-index.html#create-index-multi-valued
- MySQL 8.0 Reference Manual — Secondary Indexes and Generated Columns: https://dev.mysql.com/doc/refman/8.0/en/create-table-secondary-indexes.html
