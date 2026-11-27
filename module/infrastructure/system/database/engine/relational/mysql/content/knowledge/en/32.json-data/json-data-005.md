# JSON_TABLE to Transform Documents into Tabular Data

JSON is often used to store flexible attributes or a list of elements attached to a main record. However, many analytical and business queries need to work with each element as a relational row: filtering by product code, summing quantities, joining with a catalog table, or grouping by attributes.

MySQL provides the `JSON_TABLE()` table function to project a JSON document into SQL rows and columns. This function reads a JSON path as the row source, then maps values from each element into columns with SQL data types.

For example, an order may store a list of line items in a JSON column. `JSON_TABLE()` can turn each element of the `items` array into a row to compute totals or join with a products table.

This article focuses on using `JSON_TABLE()` in `FROM`, defining columns with `PATH`, `FOR ORDINALITY`, and `EXISTS PATH`, handling missing values with `ON EMPTY`, handling errors with `ON ERROR`, expanding nested arrays with `NESTED PATH`, and managing the impact of expanding JSON into multiple rows.

## 1. What Problem Does JSON_TABLE() Solve?

Suppose the `orders` table stores order metadata and a JSON document describing line items:

~~~json
{
  "customerId": 501,
  "items": [
    {"sku": "KB-01", "qty": 2, "unitPrice": 350000},
    {"sku": "MS-02", "qty": 1, "unitPrice": 180000}
  ]
}
~~~

Using only `JSON_EXTRACT()`, the result is typically still a JSON value. To extract the first array element, the second element, or an individual property, the SQL query must manually manage paths and data types.

`JSON_TABLE()` produces a relational row set:

| sku | qty | unit_price |
|---|---:|---:|
| KB-01 | 2 | 350000.00 |
| MS-02 | 1 | 180000.00 |

Once transformed into SQL rows and columns, the data can participate in familiar operations:

- `WHERE` to filter individual elements.
- `JOIN` to match codes inside JSON with relational tables.
- `SUM()`, `AVG()`, `COUNT()` to aggregate.
- `GROUP BY` to compute statistics by attribute.
- `ORDER BY` to sort elements.
- Window functions to analyze each expanded row.

`JSON_TABLE()` is a table function: it provides a tabular data source inside a query, without creating a new physical table or modifying the source JSON document.

### 1.1. Comparing JSON_TABLE() with Other JSON Functions

| Tool | Primary Output | When to Use |
|---|---|---|
| JSON_EXTRACT() | A JSON value | Retrieving a property or JSON branch |
| JSON_UNQUOTE() | An SQL string from a JSON string value | Stripping JSON quotes when a string is needed |
| JSON_VALUE() | An SQL scalar value by path | Retrieving a single value with an SQL type |
| JSON_CONTAINS() | TRUE/FALSE or 1/0 | Checking whether a document contains a value |
| JSON_TABLE() | Multiple rows with SQL columns | Expanding arrays or JSON structures into tabular data |

`JSON_TABLE()` is especially useful when processing each element in an array. If you only need a single scalar value, `JSON_VALUE()` or `JSON_EXTRACT()` can be more concise.

### 1.2. MySQL Version

`JSON_TABLE()` has been available since MySQL 8.0.4. Several behaviors related to errors and JSON `null` values changed across 8.0 releases:

- From MySQL 8.0.20, writing `ON ERROR` before `ON EMPTY` is deprecated; always write `ON EMPTY` before `ON ERROR`.
- From MySQL 8.0.21, JSON `null` values are mapped to SQL `NULL` in `JSON_TABLE()` columns; earlier versions treated this case as an error.
- `EXPLAIN ANALYZE` has been available since MySQL 8.0.18; it can be used to measure actual row counts and timing when querying `JSON_TABLE()`.

When an application supports multiple MySQL versions, check the actual server version and test JSON `null`, missing values, and mismatched data types on the target version.

## 2. Preparing the Table and JSON Documents

Examples throughout use an orders table:

~~~sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL,
    document JSON NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_customer_created (customer_id, created_at)
) ENGINE = InnoDB;
~~~

Insert sample data:

~~~sql
INSERT INTO orders (order_id, customer_id, created_at, document)
VALUES
(
    1001,
    501,
    '2026-02-10 09:30:00',
    JSON_OBJECT(
        'customerId', 501,
        'items', JSON_ARRAY(
            JSON_OBJECT(
                'sku', 'KB-01',
                'qty', 2,
                'unitPrice', 350000
            ),
            JSON_OBJECT(
                'sku', 'MS-02',
                'qty', 1,
                'unitPrice', 180000
            )
        )
    )
),
(
    1002,
    502,
    '2026-02-11 14:15:00',
    JSON_OBJECT(
        'customerId', 502,
        'items', JSON_ARRAY(
            JSON_OBJECT(
                'sku', 'HD-03',
                'qty', 3,
                'unitPrice', 90000
            )
        )
    )
);
~~~

The `document` column has type `JSON`, so MySQL validates document syntax on write. Each row in `orders` remains one order; the `items` array holds the line items belonging to that order.

## 3. JSON_TABLE() Syntax

`JSON_TABLE()` typically appears in the `FROM` clause:

~~~sql
JSON_TABLE(
    json_expression,
    row_path
    COLUMNS (
        column_definition [, column_definition] ...
    )
) AS table_alias
~~~

Where:

- `json_expression` is an expression producing the JSON document to read.
- `row_path` is the path identifying the nodes that will form rows.
- `COLUMNS` describes the SQL columns extracted from each node.
- `table_alias` is the mandatory alias used to reference columns produced by `JSON_TABLE()`.

Important column definition forms:

~~~sql
column_name FOR ORDINALITY

column_name data_type PATH json_path
    [on_empty]
    [on_error]

column_name data_type EXISTS PATH json_path

NESTED [PATH] json_path COLUMNS (
    nested_column_definition [, nested_column_definition] ...
)
~~~

Clauses for handling special cases:

~~~sql
{NULL | DEFAULT json_string | ERROR} ON EMPTY
{NULL | DEFAULT json_string | ERROR} ON ERROR
~~~

Not every column needs both clauses. If omitted, MySQL uses the respective default behavior; in systems needing explicit data contracts, declare them explicitly for important fields.

## 4. Expanding a JSON Array into Multiple Rows

The row path commonly points to an array using the `[*]` syntax. Example:

~~~sql
SELECT
    o.order_id,
    jt.sku,
    jt.qty,
    jt.unit_price
FROM orders AS o
CROSS JOIN JSON_TABLE(
    o.document,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(40) PATH '$.sku',
        qty INT PATH '$.qty',
        unit_price DECIMAL(13, 2) PATH '$.unitPrice'
    )
) AS jt
ORDER BY o.order_id, jt.sku;
~~~

Explanation:

- `o.document` is the JSON document of each order.
- `'$.items[*]'` selects each element in the `items` array as a row.
- `'$.sku'` reads the `sku` property of the current element.
- `'$.qty'` reads the quantity.
- `'$.unitPrice'` reads the unit price and converts it to `DECIMAL(13,2)`.
- `jt` is the alias for the table returned by `JSON_TABLE()`.

Result:

| order_id | sku | qty | unit_price |
|---:|---|---:|---:|
| 1001 | KB-01 | 2 | 350000.00 |
| 1001 | MS-02 | 1 | 180000.00 |
| 1002 | HD-03 | 3 | 90000.00 |

One `orders` row can produce multiple `jt` rows. When joined with `CROSS JOIN`, the number of result rows is the total number of elements across the selected `items` arrays from the source orders.

### 4.1. Row Path and Column Path

The two path types serve different roles:

| Path | Role |
|---|---|
| `'$.items[*]'` | Selects the nodes that form rows |
| `'$.sku'` | Retrieves the `sku` property within the current row node |
| `'$.qty'` | Retrieves the `qty` property within the current row node |
| `'$.unitPrice'` | Retrieves the `unitPrice` property within the current row node |

Column paths are evaluated relative to the current node selected by `row_path`. Therefore, if `row_path` is `'$.items[*]'`, the column path only needs `'$.sku'`, without repeating `'$.items[*].sku'`.

### 4.2. Empty Array or Non-Matching Row Path

If `row_path` matches no nodes, `JSON_TABLE()` produces zero rows for that document.

With `CROSS JOIN`, an order producing no JSON rows is excluded from the result:

~~~sql
SELECT o.order_id, jt.sku
FROM orders AS o
CROSS JOIN JSON_TABLE(
    o.document,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(40) PATH '$.sku'
    )
) AS jt;
~~~

This behavior must be considered when a report needs to retain orders without line items. A later section compares `CROSS JOIN`, `LEFT JOIN`, and `NESTED PATH`.

## 5. FOR ORDINALITY: Numbering Elements

`FOR ORDINALITY` creates an ordinal sequence column for rows generated from the row path. Numbering starts at 1.

~~~sql
SELECT
    o.order_id,
    jt.item_no,
    jt.sku,
    jt.qty
FROM orders AS o
CROSS JOIN JSON_TABLE(
    o.document,
    '$.items[*]'
    COLUMNS (
        item_no FOR ORDINALITY,
        sku VARCHAR(40) PATH '$.sku',
        qty INT PATH '$.qty'
    )
) AS jt
ORDER BY o.order_id, jt.item_no;
~~~

Result:

| order_id | item_no | sku | qty |
|---:|---:|---|---:|
| 1001 | 1 | KB-01 | 2 |
| 1001 | 2 | MS-02 | 1 |
| 1002 | 1 | HD-03 | 3 |

Ordinality reflects the element position within each document's array, not a global sequence across the entire query result. Because each order has its own array, `item_no` restarts at 1 for the next order.

### 5.1. Using Ordinality to Preserve Business Order

JSON arrays are ordered. If you need to preserve line-item order from the source document, extract `FOR ORDINALITY` and `ORDER BY` that column:

~~~sql
SELECT
    o.order_id,
    jt.item_no,
    jt.sku
FROM orders AS o
CROSS JOIN JSON_TABLE(
    o.document,
    '$.items[*]'
    COLUMNS (
        item_no FOR ORDINALITY,
        sku VARCHAR(40) PATH '$.sku'
    )
) AS jt
ORDER BY o.order_id, jt.item_no;
~~~

Do not rely on physical row order or the incidental order returned by `JSON_TABLE()` if order matters to the application. SQL guarantees result ordering only when `ORDER BY` is specified.

## 6. EXISTS PATH: Checking Whether a Property Exists

`EXISTS PATH` creates a column indicating whether a path matches a value in the current node. The result is 1 if present and 0 if absent.

~~~sql
SELECT
    o.order_id,
    jt.sku,
    jt.has_note
FROM orders AS o
CROSS JOIN JSON_TABLE(
    o.document,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(40) PATH '$.sku',
        has_note INT EXISTS PATH '$.note'
    )
) AS jt;
~~~

`EXISTS PATH` is useful when you need to distinguish:

- A property absent from the object.
- A property present with a JSON `null` value.
- A property with a concrete value.

For example, if an item has `note: null`, the path `'$.note'` still exists so `has_note` is 1. A `note` column declared with `PATH` receives SQL `NULL`; the `EXISTS PATH` column indicates whether the node is present.

### 6.1. Using EXISTS PATH in Conditions

You can filter elements that have a promotion property:

~~~sql
SELECT
    o.order_id,
    jt.sku,
    jt.discount_code
FROM orders AS o
CROSS JOIN JSON_TABLE(
    o.document,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(40) PATH '$.sku',
        has_discount INT EXISTS PATH '$.discount',
        discount_code VARCHAR(30) PATH '$.discount'
    )
) AS jt
WHERE jt.has_discount = 1;
~~~

`EXISTS PATH` only returns an existence flag; it does not return the property's content. If you need the content, declare an additional `PATH` column such as `discount_code`.

## 7. ON EMPTY: Handling Paths That Find No Value

A JSON element may lack an optional property. For instance, an item has `sku` and `qty` but no `note`. `ON EMPTY` defines the value assigned when the column's path finds no match.

Three options:

| Clause | Behavior |
|---|---|
| NULL ON EMPTY | Assigns SQL NULL |
| DEFAULT json_string ON EMPTY | Assigns a default value written as a JSON string |
| ERROR ON EMPTY | Raises an error |

Example:

~~~sql
SELECT
    o.order_id,
    jt.sku,
    jt.qty,
    jt.note
FROM orders AS o
CROSS JOIN JSON_TABLE(
    o.document,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(40) PATH '$.sku' ERROR ON EMPTY,
        qty INT PATH '$.qty' DEFAULT '1' ON EMPTY,
        note VARCHAR(200) PATH '$.note'
            DEFAULT '"No note"' ON EMPTY
    )
) AS jt;
~~~

In the example:

- Missing `sku` is an error because `sku` is treated as required.
- Missing `qty` uses the number 1.
- Missing `note` uses the string No note.

### 7.1. DEFAULT json_string Is a JSON Value

The argument to `DEFAULT` is written as a string representing JSON. Distinguish a JSON string from a JSON number:

| DEFAULT | Represented JSON Value |
|---|---|
| `DEFAULT '0'` | Number 0 |
| `DEFAULT 'true'` | Boolean true |
| `DEFAULT 'null'` | JSON null |
| `DEFAULT '"unknown"'` | String unknown |
| `DEFAULT '[]'` | Empty array |
| `DEFAULT '{}'` | Empty object |

Thus, to assign the string `unknown`, place JSON double quotes inside the SQL string: `DEFAULT '"unknown"'`. If you write `DEFAULT 'unknown'`, the content is not a valid JSON document.

The default value must still be compatible with the target column's SQL type. After receiving the default JSON value, MySQL converts it to the type declared in `COLUMNS`.

### 7.2. ON EMPTY Does Not Mean a NULL Value

`ON EMPTY` applies only when the path finds no value. It is not a check for whether a found value is JSON `null`.

If the path exists and the JSON value is `null`:

- From MySQL 8.0.21, `JSON_TABLE()` maps JSON `null` to SQL `NULL`.
- The path is still considered found; `ON EMPTY` is not triggered.
- `EXISTS PATH` for that path returns 1.

If you need to distinguish a missing property from a present property with JSON `null`, combine `EXISTS PATH` with a `PATH` column.

## 8. ON ERROR: Handling Errors When Mapping Values

`ON ERROR` defines behavior when `JSON_TABLE()` encounters an error while placing a JSON value into an SQL column. The options mirror `ON EMPTY`:

| Clause | Behavior |
|---|---|
| NULL ON ERROR | Assigns SQL NULL |
| DEFAULT json_string ON ERROR | Assigns a default value |
| ERROR ON ERROR | Raises an error |

A typical case is a path returning a JSON object or array when the target column is declared with a scalar type such as `VARCHAR`, `INT`, or `DECIMAL`.

Example document with heterogeneous structure:

~~~json
{
  "items": [
    {"sku": "KB-01", "qty": 2},
    {"sku": {"code": "MS-02"}, "qty": 1}
  ]
}
~~~

If `sku` is mapped to `VARCHAR`, the second element is an object instead of a scalar. You can specify how to handle it:

~~~sql
SELECT
    jt.sku,
    jt.qty
FROM JSON_TABLE(
    '{
      "items": [
        {"sku": "KB-01", "qty": 2},
        {"sku": {"code": "MS-02"}, "qty": 1}
      ]
    }',
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(40) PATH '$.sku'
            NULL ON EMPTY
            DEFAULT '"INVALID_SKU"' ON ERROR,
        qty INT PATH '$.qty'
            DEFAULT '0' ON EMPTY
            ERROR ON ERROR
    )
) AS jt;
~~~

For the `sku` that is an object, `ON ERROR` assigns the default string `INVALID_SKU`. If `qty` cannot be mapped per the column's error rules, `ERROR ON ERROR` instructs the query to raise an error.

### 8.1. ON ERROR Does Not Replace Data-Type Validation

Do not assume `ON ERROR` catches every conversion issue. A JSON object or array fed into a scalar column is a clear case handled by `ON ERROR` in `JSON_TABLE()`. Other SQL conversion issues such as value truncation or type coercion may emit warnings under MySQL's data conversion rules.

To protect data:

- Declare column types with sufficient value range.
- Use `ERROR ON ERROR` for fields that must strictly conform to structure.
- Check warnings if the application needs to detect unexpected truncation or coercion.
- Test JSON `null`, missing properties, and mistyped values separately.
- Do not treat `DEFAULT ON ERROR` as a way to fix a structurally malformed JSON document.

### 8.2. Write ON EMPTY Before ON ERROR

When declaring both clauses, write them in this order:

~~~sql
value_col VARCHAR(100) PATH '$.value'
    DEFAULT '"missing"' ON EMPTY
    ERROR ON ERROR
~~~

From MySQL 8.0.20, writing `ON ERROR` before `ON EMPTY` is deprecated. Use the order `ON EMPTY` then `ON ERROR` to avoid warnings and keep syntax consistent.

## 9. NESTED PATH: Expanding Nested JSON Arrays

An element inside an array may contain a child array. For example, an item with multiple options or add-ons:

~~~json
{
  "items": [
    {
      "sku": "LAP-01",
      "qty": 1,
      "options": [
        {"code": "RAM-16", "price": 1200000},
        {"code": "SSD-1T", "price": 1800000}
      ]
    },
    {
      "sku": "MOUSE-01",
      "qty": 2,
      "options": []
    }
  ]
}
~~~

`NESTED PATH` expands the elements of the child array:

~~~sql
SELECT
    jt.item_no,
    jt.sku,
    jt.option_no,
    jt.option_code,
    jt.option_price
FROM JSON_TABLE(
    '{
      "items": [
        {
          "sku": "LAP-01",
          "qty": 1,
          "options": [
            {"code": "RAM-16", "price": 1200000},
            {"code": "SSD-1T", "price": 1800000}
          ]
        },
        {
          "sku": "MOUSE-01",
          "qty": 2,
          "options": []
        }
      ]
    }',
    '$.items[*]'
    COLUMNS (
        item_no FOR ORDINALITY,
        sku VARCHAR(40) PATH '$.sku',
        qty INT PATH '$.qty',
        NESTED PATH '$.options[*]'
        COLUMNS (
            option_no FOR ORDINALITY,
            option_code VARCHAR(40) PATH '$.code',
            option_price DECIMAL(13, 2) PATH '$.price'
        )
    )
) AS jt
ORDER BY jt.item_no, jt.option_no;
~~~

Result:

| item_no | sku | option_no | option_code | option_price |
|---:|---|---:|---|---:|
| 1 | LAP-01 | 1 | RAM-16 | 1200000.00 |
| 1 | LAP-01 | 2 | SSD-1T | 1800000.00 |
| 2 | MOUSE-01 | NULL | NULL | NULL |

Item-level columns are repeated for each option row. An item without options still produces one row; columns belonging to `NESTED PATH` receive SQL `NULL`.

### 9.1. Distinguishing Row Path and Nested Path

In the example:

- `'$.items[*]'` is the main row path, generating rows for each item.
- `'$.options[*]'` is the nested path, generating child rows for the current item.
- `sku` and `qty` belong to the item level.
- `option_code` and `option_price` belong to the option level.

`NESTED PATH` preserves the parent row: when the child array path produces no matches, child columns are set to `NULL` and the parent row is still retained.

This differs from a non-matching main row path: if `'$.items[*]'` finds no elements, `JSON_TABLE()` produces no rows for that document.

### 9.2. Multiple Sibling NESTED PATH Clauses

An item can contain multiple independent child arrays, such as `discounts` and `taxes`:

~~~json
{
  "sku": "KB-01",
  "discounts": [
    {"code": "WELCOME", "amount": 20000}
  ],
  "taxes": [
    {"code": "VAT", "rate": 8},
    {"code": "ENV", "rate": 1}
  ]
}
~~~

When declaring multiple `NESTED PATH` clauses at the same level, MySQL processes them sequentially. Rows generated by one nested path have columns from sibling nested paths set to `NULL`; the result is not a Cartesian product between the two arrays.

Example:

~~~sql
SELECT *
FROM JSON_TABLE(
    '{
      "sku": "KB-01",
      "discounts": [
        {"code": "WELCOME", "amount": 20000}
      ],
      "taxes": [
        {"code": "VAT", "rate": 8},
        {"code": "ENV", "rate": 1}
      ]
    }',
    '$'
    COLUMNS (
        sku VARCHAR(40) PATH '$.sku',
        NESTED PATH '$.discounts[*]'
        COLUMNS (
            discount_code VARCHAR(30) PATH '$.code',
            discount_amount DECIMAL(13, 2) PATH '$.amount'
        ),
        NESTED PATH '$.taxes[*]'
        COLUMNS (
            tax_code VARCHAR(30) PATH '$.code',
            tax_rate DECIMAL(5, 2) PATH '$.rate'
        )
    )
) AS jt;
~~~

The `discounts` array generates a row with `discount_code` and `discount_amount`; the corresponding `tax` columns are `NULL`. The `taxes` array generates rows with `tax_code` and `tax_rate`; the corresponding `discount` columns are `NULL`. If business logic requires every discount-tax pair, you must explicitly join or combine the two result sets.

## 10. JSON_TABLE() and Joining with Source Tables

`JSON_TABLE()` often needs to read documents from each row of a relational table. The function can reference columns of a table preceding it in `FROM`. This is the implicit lateral behavior of `JSON_TABLE()`.

Example:

~~~sql
SELECT
    o.order_id,
    o.customer_id,
    jt.sku,
    jt.qty
FROM orders AS o
JOIN JSON_TABLE(
    o.document,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(40) PATH '$.sku',
        qty INT PATH '$.qty'
    )
) AS jt ON TRUE;
~~~

`JSON_TABLE()` is allowed to reference `o.document` because `orders` precedes it in `FROM`. You do not need—and should not add—the `LATERAL` keyword before `JSON_TABLE()`; lateral evaluation is implicit, and writing explicit `LATERAL` before `JSON_TABLE()` causes a syntax error.

### 10.1. Combining with a Catalog Table

Suppose there is a `products` table:

~~~sql
CREATE TABLE products (
    sku VARCHAR(40) NOT NULL,
    product_name VARCHAR(200) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (sku)
) ENGINE = InnoDB;
~~~

You can join each item inside JSON with the catalog:

~~~sql
SELECT
    o.order_id,
    jt.sku,
    p.product_name,
    jt.qty,
    jt.unit_price
FROM orders AS o
CROSS JOIN JSON_TABLE(
    o.document,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(40) PATH '$.sku',
        qty INT PATH '$.qty',
        unit_price DECIMAL(13, 2) PATH '$.unitPrice'
    )
) AS jt
JOIN products AS p
    ON p.sku = jt.sku
WHERE p.active = TRUE
ORDER BY o.order_id, jt.sku;
~~~

Once expanded into rows, `sku` is an SQL column and can serve as the join key with `products`. If a `sku` in JSON does not match `products`, `INNER JOIN` drops that item; use `LEFT JOIN` if you need to retain codes missing from the catalog.

### 10.2. Retaining Orders Without an items Array

If you need to retain orders with an empty `items` array or missing `items` path, use `LEFT JOIN`:

~~~sql
SELECT
    o.order_id,
    jt.item_no,
    jt.sku,
    jt.qty
FROM orders AS o
LEFT JOIN JSON_TABLE(
    o.document,
    '$.items[*]'
    COLUMNS (
        item_no FOR ORDINALITY,
        sku VARCHAR(40) PATH '$.sku',
        qty INT PATH '$.qty'
    )
) AS jt ON TRUE
ORDER BY o.order_id, jt.item_no;
~~~

When `JSON_TABLE()` generates no rows for an order, `LEFT JOIN` still preserves the `orders` row and the `jt` columns receive `NULL`.

Distinguish two cases:

- Main row path does not match: `JSON_TABLE()` produces 0 rows; `LEFT JOIN` is required to keep the parent row.
- Main row path matches an item, but the item's nested path does not match: `NESTED PATH` automatically keeps the item row and sets child columns to `NULL`.

Do not arbitrarily move conditions on `jt` columns into `WHERE` if you want to keep parent rows without items. For example, `WHERE jt.qty > 0` filters out rows where `jt.qty` is `NULL`, making the result behave like an `INNER JOIN`. If the condition belongs to the join, consider placing it in `ON` or handling `NULL` according to business logic.

## 11. Aggregate Queries over JSON_TABLE() Rows

Once an array is expanded into rows, you can aggregate just like with ordinary tables.

### 11.1. Calculating Total Quantity and Value per Order

~~~sql
SELECT
    o.order_id,
    SUM(jt.qty) AS total_quantity,
    SUM(jt.qty * jt.unit_price) AS order_amount
FROM orders AS o
CROSS JOIN JSON_TABLE(
    o.document,
    '$.items[*]'
    COLUMNS (
        qty INT PATH '$.qty',
        unit_price DECIMAL(13, 2) PATH '$.unitPrice'
    )
) AS jt
GROUP BY o.order_id
ORDER BY o.order_id;
~~~

Each input row to `SUM()` is one line item. The expression `qty * unit_price` calculates line value; `GROUP BY order_id` aggregates back into order total.

### 11.2. Statistics by SKU

~~~sql
SELECT
    jt.sku,
    SUM(jt.qty) AS units_sold,
    SUM(jt.qty * jt.unit_price) AS gross_amount
FROM orders AS o
CROSS JOIN JSON_TABLE(
    o.document,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(40) PATH '$.sku',
        qty INT PATH '$.qty',
        unit_price DECIMAL(13, 2) PATH '$.unitPrice'
    )
) AS jt
WHERE o.created_at >= '2026-02-01'
  AND o.created_at <  '2026-03-01'
GROUP BY jt.sku
ORDER BY gross_amount DESC;
~~~

The time condition filters source orders before computing the SKU report. Using a half-open interval from the start of the month to the start of the next month keeps the time predicate clean and avoids missing timestamps on the last day of the month.

### 11.3. Filtering Individual JSON Elements

~~~sql
SELECT
    o.order_id,
    jt.sku,
    jt.qty
FROM orders AS o
CROSS JOIN JSON_TABLE(
    o.document,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(40) PATH '$.sku',
        qty INT PATH '$.qty'
    )
) AS jt
WHERE jt.qty >= 2
  AND jt.sku LIKE 'K%';
~~~

The `jt.qty` and `jt.sku` predicates apply to the mapped rows. If a document contains thousands of elements, expanding the data still incurs cost; filter the source table first when a sufficiently selective order condition exists.

### 11.4. Combining with a CTE

~~~sql
WITH order_items AS (
    SELECT
        o.order_id,
        o.customer_id,
        jt.sku,
        jt.qty,
        jt.unit_price
    FROM orders AS o
    CROSS JOIN JSON_TABLE(
        o.document,
        '$.items[*]'
        COLUMNS (
            sku VARCHAR(40) PATH '$.sku',
            qty INT PATH '$.qty',
            unit_price DECIMAL(13, 2) PATH '$.unitPrice'
        )
    ) AS jt
    WHERE o.created_at >= '2026-02-01'
      AND o.created_at <  '2026-03-01'
)
SELECT
    customer_id,
    SUM(qty * unit_price) AS customer_spend
FROM order_items
GROUP BY customer_id
ORDER BY customer_spend DESC;
~~~

The CTE names the expanded row set to make the aggregate query easier to read. A CTE does not guarantee the data is materialized into a physical table; the optimizer decides execution based on query structure.

## 12. JSON Paths and Data-Type Mapping

The JSON path identifies the node to read. Common forms:

| Path | Meaning |
|---|---|
| `'$'` | Root node of the document |
| `'$.customerId'` | `customerId` property at the root level |
| `'$.items[0]'` | First element of the `items` array |
| `'$.items[*]'` | Every element in the `items` array |
| `'$.items[*].sku'` | `sku` property of `items` elements |
| `'$.profile.address.city'` | `city` property in a nested object |

JSON key names are case-sensitive. `'$.unitPrice'` and `'$.unitprice'` can be two distinct paths.

If a key name contains spaces or special characters, use JSON path quoted key syntax. Never concatenate raw user input into a JSON path; validate or restrict allowed paths.

### 12.1. Choosing SQL Types for Columns

The SQL type declared in `COLUMNS` determines the data type the query receives:

| JSON Data | Common SQL Type |
|---|---|
| Integer identifier | `INT` or `BIGINT` |
| Quantity | `INT` or `BIGINT` |
| Exact price or rate | `DECIMAL(p,s)` |
| Code or name | `VARCHAR(n)` |
| Date | `DATE` |
| Timestamp without timezone | `DATETIME` |
| Numeric/boolean flag | `TINYINT` or `BOOLEAN` |

For monetary data, use `DECIMAL` instead of `FLOAT`/`DOUBLE` to avoid floating-point rounding errors. Choose precision and scale large enough for real-world values.

Example:

~~~sql
SELECT
    jt.sku,
    jt.qty,
    jt.unit_price,
    jt.is_gift
FROM JSON_TABLE(
    '{
      "items": [
        {
          "sku": "BOOK-01",
          "qty": 2,
          "unitPrice": 125000.50,
          "isGift": false
        }
      ]
    }',
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(40) PATH '$.sku',
        qty INT PATH '$.qty',
        unit_price DECIMAL(13, 2) PATH '$.unitPrice',
        is_gift TINYINT PATH '$.isGift'
    )
) AS jt;
~~~

MySQL converts from the JSON value to the declared SQL type. Do not treat successful casting as proof that data is business-valid; negative quantities, zero prices, or invalid code strings still require separate validation rules.

### 12.2. Missing Values, JSON null, and SQL NULL

Three concepts to distinguish:

| State in JSON | Typical Result in PATH Column |
|---|---|
| Missing key or non-matching path | Per `ON EMPTY` |
| Key exists with JSON null | SQL `NULL` since MySQL 8.0.21 |
| Key exists with valid scalar | Value converted to SQL type |

SQL `NULL` does not indicate whether the cause was a missing key or JSON `null`. Use `EXISTS PATH` if the application needs to distinguish key presence.

Example:

~~~sql
SELECT
    jt.has_note,
    jt.note
FROM JSON_TABLE(
    '{
      "items": [
        {"sku": "A-01"},
        {"sku": "A-02", "note": null},
        {"sku": "A-03", "note": "Fragile"}
      ]
    }',
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(20) PATH '$.sku',
        has_note INT EXISTS PATH '$.note',
        note VARCHAR(100) PATH '$.note'
    )
) AS jt;
~~~

The result distinguishes an item missing `note` from an item whose `note` is JSON `null`:

- Item A-01: `has_note = 0`, `note = NULL`.
- Item A-02: `has_note = 1`, `note = NULL`.
- Item A-03: `has_note = 1`, `note = 'Fragile'`.

## 13. JSON_TABLE() Is a Lateral Table Function

`JSON_TABLE()` commonly reads documents from a column of a table appearing before it in `FROM`:

~~~sql
FROM orders AS o
CROSS JOIN JSON_TABLE(o.document, '$.items[*]' COLUMNS (...)) AS jt
~~~

The table function can reference `o.document` without writing `LATERAL`. Reference scope depends on order in `FROM`: a `JSON_TABLE()` expression can use tables preceding it, not tables appearing after it.

This allows expanding JSON separately for each row of the source table. If `JSON_TABLE()` only reads a JSON literal or standalone expression, no preceding source table is needed.

Do not confuse `JSON_TABLE()` with an ordinary derived table. `JSON_TABLE()`'s lateral rule is a property of the table function itself; adding the explicit `LATERAL` keyword before it is invalid.

## 14. Performance and Query Strategy

`JSON_TABLE()` makes SQL readable and lets you query JSON relationally, but expanding arrays can significantly increase intermediate row counts.

For example, 100,000 orders averaging 20 items each can produce roughly 2 million `JSON_TABLE()` rows before aggregation. Consider the number of documents read, array sizes, and the number of extracted columns.

### 14.1. Filter Source Tables Before Expanding JSON

Include selective conditions on the relational table in the same query:

~~~sql
SELECT
    o.order_id,
    jt.sku,
    jt.qty
FROM orders AS o
CROSS JOIN JSON_TABLE(
    o.document,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(40) PATH '$.sku',
        qty INT PATH '$.qty'
    )
) AS jt
WHERE o.customer_id = 501
  AND o.created_at >= '2026-02-01'
  AND o.created_at <  '2026-03-01';
~~~

Indexes on `customer_id` and `created_at` can help locate matching orders before processing JSON documents. Actual execution order is decided by the optimizer; verify with `EXPLAIN` rather than assuming based on whether conditions are written before or after `JOIN`.

### 14.2. Project Only Needed Columns

Do not declare dozens of JSON columns if the query only needs `sku` and `qty`. Each extra column increases extraction and conversion work.

Similarly, avoid expanding large child arrays if a query only needs an existence check. Functions such as `JSON_CONTAINS()`, `JSON_OVERLAPS()`, or `MEMBER OF()` may fit better depending on the structure and condition type.

### 14.3. Use Generated Columns or Indexes for Repeated Scalar Queries

If you frequently filter by a root-level scalar property, consider a generated column and index:

~~~sql
ALTER TABLE orders
ADD COLUMN document_customer_id BIGINT
    GENERATED ALWAYS AS (
        CAST(
            JSON_UNQUOTE(
                JSON_EXTRACT(document, '$.customerId')
            ) AS UNSIGNED
        )
    ) STORED,
ADD INDEX idx_orders_document_customer (document_customer_id);
~~~

Then you can filter using the indexed column:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE document_customer_id = 501;
~~~

This example is only suitable when `customerId` has a valid numeric format and data rules are enforced. Missing keys, JSON `null`, and mistyped values must be handled per the system's data contract.

A generated column speeds up querying a repeatedly used scalar property. It does not turn the entire `items` array into a relational table on its own.

### 14.4. Multi-Valued Indexes Do Not Replace JSON_TABLE()

MySQL supports multi-valued indexes for certain array-element search predicates, such as `MEMBER OF()`, `JSON_CONTAINS()`, and `JSON_OVERLAPS()` under supported conditions.

A multi-valued index serves array membership searches. It does not replace expanding individual elements into SQL columns for `JOIN`, calculations, or returning multiple rows with `JSON_TABLE()`. Check `EXPLAIN` to see whether the index is used for a specific predicate.

### 14.5. Reading Execution Plans

Use `EXPLAIN` to inspect the plan:

~~~sql
EXPLAIN
SELECT
    o.order_id,
    jt.sku,
    jt.qty
FROM orders AS o
CROSS JOIN JSON_TABLE(
    o.document,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(40) PATH '$.sku',
        qty INT PATH '$.qty'
    )
) AS jt
WHERE o.customer_id = 501;
~~~

If the MySQL version supports `EXPLAIN ANALYZE`, you can measure actual row counts and timing:

~~~sql
EXPLAIN ANALYZE
SELECT
    o.order_id,
    jt.sku,
    jt.qty
FROM orders AS o
CROSS JOIN JSON_TABLE(
    o.document,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(40) PATH '$.sku',
        qty INT PATH '$.qty'
    )
) AS jt
WHERE o.customer_id = 501;
~~~

Focus on observing:

- Number of `orders` rows read.
- Whether an index is used to filter the source table.
- Number of rows produced by `JSON_TABLE()`.
- Number of rows discarded by predicates after expanding JSON.
- Subsequent sort, aggregate, and join costs.
- Whether optimizer estimates diverge significantly from actual row counts.

### 14.6. When Should an Array Be Normalized into a Relational Table?

If a JSON array is frequently queried, updated, joined, and constrained like core data, consider storing each element as a row in a child table.

| Characteristic | Storing Array in JSON | Storing in a Child Table |
|---|---|---|
| Flexible schema | Good | Requires column design |
| Reading whole document | Convenient | Requires JOIN or multi-row query |
| Frequent JOIN per element | Incurs JSON expansion cost | More natural |
| Foreign key per element | Not directly | Supported |
| Indexing per element property | More limited | Flexible |
| Updating a single element | Must update JSON document | `UPDATE` a single row |

`JSON_TABLE()` is a useful bridge between JSON documents and relational queries. It does not mean every relational list should be stored long-term in JSON.

## 15. Common Mistakes When Using JSON_TABLE()

### 15.1. Confusing Row Path with Column Path

Once the row path selects each array element, column paths must be written relative to the current element.

~~~sql
JSON_TABLE(
    o.document,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(40) PATH '$.sku'
    )
)
~~~

Do not repeat the entire path from the root in every column path. Define the row path first, then select properties of the current node.

### 15.2. Forgetting the JSON_TABLE() Alias

`JSON_TABLE()` must have a table alias:

~~~sql
SELECT jt.sku
FROM JSON_TABLE(
    '{"items":[{"sku":"KB-01"}]}',
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(40) PATH '$.sku'
    )
) AS jt;
~~~

The alias makes column references explicit and avoids name collisions with columns from other tables.

### 15.3. Using CROSS JOIN While Expecting to Keep Parent Rows

`CROSS JOIN` drops an order if the main row path produces no rows. If a report must retain orders with no items, use `LEFT JOIN JSON_TABLE() ... ON TRUE` or design the query accordingly.

Do not confuse this with `NESTED PATH`: a non-matching nested path still preserves the row produced by the main row path and sets child columns to `NULL`.

### 15.4. Using ON EMPTY to Handle JSON null

`ON EMPTY` applies only when the path is not found. If a property exists with JSON `null`, starting in MySQL 8.0.21 the `PATH` column receives SQL `NULL` without triggering `ON EMPTY`.

If you need to distinguish the two states, use `EXISTS PATH`.

### 15.5. Assuming ON ERROR Catches Every Conversion Error

`ON ERROR` is not a comprehensive validator for JSON data. A JSON object or array that cannot fit into a scalar column is a typical case; other SQL conversion issues may produce warnings or follow type-coercion rules.

Declare the right data types, check warnings when needed, and validate business rules at the appropriate layer.

### 15.6. Forgetting the Order of ON EMPTY and ON ERROR

When both are needed, place `ON EMPTY` before `ON ERROR`:

~~~sql
amount DECIMAL(13, 2) PATH '$.amount'
    DEFAULT '0' ON EMPTY
    ERROR ON ERROR
~~~

Do not use the reverse order, as `ON ERROR` before `ON EMPTY` has been deprecated since MySQL 8.0.20.

### 15.7. Using INNER JOIN When Unmatched Codes Must Be Retained

When joining `JSON_TABLE()` columns with a catalog table:

- `INNER JOIN` keeps only codes present in the catalog table.
- `LEFT JOIN` retains codes lacking a matching catalog record as well.

Choose according to reporting needs. If you need to find missing reference data, `LEFT JOIN` and check whether the right-side table key is `NULL`.

### 15.8. Not Validating JSON Input Data

A MySQL `JSON` column only accepts valid JSON documents. However, `JSON_TABLE()` can also accept string expressions or other expressions producing JSON. If the expression is not a valid JSON document, the query may fail.

For raw payloads before moving them into a JSON column, you can check with `JSON_VALID()`:

~~~sql
SELECT
    raw_payload,
    JSON_VALID(raw_payload) AS is_valid_json
FROM incoming_messages;
~~~

Do not invoke `JSON_TABLE()` on unvalidated payloads if the application lacks proper error handling. Ideally, validate and normalize data at the ingest boundary before entering the query pipeline.

### 15.9. Assuming Result Order Is Automatically Guaranteed

JSON arrays have element order, but SQL result sets have no guaranteed order without `ORDER BY`. Use `FOR ORDINALITY` to extract positions and then `ORDER BY` parent key and ordinality.

## 16. Practical Example: Revenue Report from JSON

Suppose documents contain line items, each having `sku`, `qty`, `unitPrice`, and optionally `discount`. You need to calculate pre-discount revenue per customer.

~~~sql
SELECT
    o.customer_id,
    COUNT(*) AS line_count,
    SUM(jt.qty) AS total_units,
    SUM(jt.qty * jt.unit_price) AS gross_amount
FROM orders AS o
CROSS JOIN JSON_TABLE(
    o.document,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(40) PATH '$.sku' ERROR ON EMPTY,
        qty INT PATH '$.qty'
            DEFAULT '1' ON EMPTY
            ERROR ON ERROR,
        unit_price DECIMAL(13, 2) PATH '$.unitPrice'
            ERROR ON EMPTY
            ERROR ON ERROR,
        has_discount INT EXISTS PATH '$.discount'
    )
) AS jt
WHERE o.created_at >= '2026-02-01'
  AND o.created_at <  '2026-03-01'
  AND jt.qty > 0
GROUP BY o.customer_id
ORDER BY gross_amount DESC;
~~~

Rules in the example:

- Each `items` element produces one row.
- `sku` and `unitPrice` are required; if missing, the query raises an error.
- `qty` defaults to 1 if missing.
- `has_discount` indicates whether the `discount` property exists.
- Only positive quantities are counted.
- Results are grouped by customer.

If data may contain mistyped values, decide explicitly whether you want the query to stop on error or quarantine invalid documents before running the report.

### 16.1. Separating Invalid Data from Valid Data

In an ingest pipeline, include a structural validation step before running analytical queries:

1. Confirm the payload is valid JSON.
2. Check the root node and the type of `items`.
3. Check required properties such as `sku`, `qty`, `unitPrice`.
4. Check value ranges and business rules.
5. Route valid payloads into the main processing pipeline.
6. Record invalid payloads with reasons for reprocessing or investigation.

`JSON_TABLE()` assists with mapping and catching certain incompatible cases when converting values into SQL columns. It does not replace full schema validation or business rules.

## 17. Guide to Choosing Query Constructs

| Need | Approach |
|---|---|
| Single scalar inside a document | `JSON_VALUE()` or `JSON_EXTRACT()` |
| One row per array element | `JSON_TABLE()` with row path `'$.array[*]'` |
| Preserve element position | `FOR ORDINALITY` |
| Check whether a property is present | `EXISTS PATH` |
| Set default when key is missing | `DEFAULT ... ON EMPTY` |
| Raise error when required key is missing | `ERROR ON EMPTY` |
| Handle object/array incompatible with scalar column | `ON ERROR` |
| Expand child array | `NESTED PATH` |
| Retain source row when root array is empty | `LEFT JOIN JSON_TABLE() ... ON TRUE` |
| Aggregate elements | Aggregate over `JSON_TABLE()` columns |
| Filter frequently by scalar at JSON root | Appropriate generated column or functional index |
| Frequent joins and updates per element | Consider normalizing into a child table |

## 18. Practice Exercises

### 18.1. Retrieve Each Item and Its Position in an Order

Write a query returning `order_id`, item position, `sku`, and `qty`. Sort by `order_id` and item position.

Hints:

- Row path: `'$.items[*]'`.
- Use `FOR ORDINALITY`.
- Use `ORDER BY` on order key and ordinality.

### 18.2. Filter Items with Discount

Add an `EXISTS PATH` column for path `'$.discount'`. Return only items that have the `discount` property, even when the property's value is JSON `null`.

### 18.3. Handle Optional Properties

Create a `note VARCHAR(200)` column with a default string when the path does not exist. Test three documents:

- Item without `note`.
- Item with `note` as JSON `null`.
- Item with `note` as a regular string.

Observe the difference between `ON EMPTY` and `EXISTS PATH`.

### 18.4. Expand Nested Arrays

Create a document with `items` and `options`. Use `NESTED PATH` to return one row per option while keeping items without options with `NULL` option columns.

### 18.5. Aggregate by Customer

Use `JSON_TABLE()` to compute total `qty` and total `qty * unitPrice` by `customer_id` over a time range. Use `EXPLAIN` to inspect the `orders` filter condition.

### 18.6. Self-Check Questions

1. How does `JSON_TABLE()` differ from `JSON_EXTRACT()` in result type?
2. What does `row_path` determine?
3. What number does `FOR ORDINALITY` start from?
4. What does `EXISTS PATH` return when a property exists with JSON `null`?
5. How does `ON EMPTY` differ from `ON ERROR`?
6. Why is `DEFAULT '"unknown"'` different from `DEFAULT 'unknown'`?
7. How does `NESTED PATH` behave when the child array is empty?
8. Do multiple sibling `NESTED PATH` clauses produce a Cartesian product?
9. Why can `CROSS JOIN` drop orders without items?
10. When is `LEFT JOIN JSON_TABLE()` needed?
11. Why can `JSON_TABLE()` reference a preceding table without `LATERAL`?
12. When should a JSON array be normalized into a relational table?

## 19. Checklist Before Shipping Queries to Production

- [ ] MySQL version supports `JSON_TABLE()` and matches application behavior expectations.
- [ ] The JSON expression is a valid document.
- [ ] Row path points to the right row-generating nodes.
- [ ] Column paths are written relative to the current node.
- [ ] Each column has an appropriate SQL type and sufficient value range.
- [ ] `FOR ORDINALITY` is used if element position must be preserved.
- [ ] `EXISTS PATH` is used when distinguishing a missing key from a present key with JSON `null`.
- [ ] `ON EMPTY` is chosen according to the contract for optional or required properties.
- [ ] `ON ERROR` is not treated as a mechanism catching every conversion warning.
- [ ] `ON EMPTY` is written before `ON ERROR`.
- [ ] `NESTED PATH` properly preserves parent rows when the child array is empty.
- [ ] Sibling `NESTED PATH` clauses are understood as sequential branches, not a Cartesian product.
- [ ] `CROSS JOIN` vs. `LEFT JOIN` matches requirements for retaining source rows.
- [ ] Predicates on `JSON_TABLE()` columns do not accidentally filter out parent rows that should be kept.
- [ ] Query projects only needed columns.
- [ ] `EXPLAIN` or `EXPLAIN ANALYZE` has been inspected for large datasets.
- [ ] Row count after array expansion has been evaluated.
- [ ] Frequently filtered scalar properties have been evaluated for generated columns/indexes.
- [ ] A relational child table was considered if joins, constraints, or per-element updates are frequent.

## Conclusion

`JSON_TABLE()` transforms nodes in a JSON document into SQL rows and columns for relational querying. The row path determines which rows are generated; `COLUMNS` maps values; `FOR ORDINALITY` preserves position; `EXISTS PATH` checks presence; `ON EMPTY` and `ON ERROR` define how missing or unmappable data is handled; `NESTED PATH` expands child arrays.

When using `JSON_TABLE()`, clearly evaluate cardinality after array expansion, choose `CROSS JOIN` or `LEFT JOIN` based on parent-row retention requirements, and distinguish missing keys from JSON `null`. For large datasets, filter source tables, project only required columns, inspect execution plans, and consider normalizing if individual JSON elements have become frequently queried relational entities.
