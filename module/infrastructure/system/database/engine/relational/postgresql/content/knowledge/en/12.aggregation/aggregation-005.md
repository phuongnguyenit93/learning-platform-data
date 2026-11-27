# string_agg, array_agg, json_agg, and Element Ordering

An aggregate query does not have to return only a single number like `COUNT(*)` or `SUM(amount)`. In PostgreSQL, you can combine multiple rows into **a string**, **a PostgreSQL array**, or **a JSON array** for reporting, APIs, and downstream processing. Three common functions are **`string_agg`**, **`array_agg`**, and **`json_agg`**.

For example, suppose an order has three line items. There are at least three ways to represent those lines:

```text
Source data:
order_id | line_no | product_name
---------+---------+--------------
1001     | 1       | Mouse
1001     | 2       | Keyboard
1001     | 3       | Mouse

string_agg → "Mouse, Keyboard, Mouse"
array_agg  → {"Mouse","Keyboard","Mouse"}
json_agg   → ["Mouse","Keyboard","Mouse"]
```

The three results differ in both **data type** and usage. Strings are convenient for display; PostgreSQL arrays fit SQL and array operations; JSON fits structured data exchange. What they share is that **element ordering is not guaranteed unless explicitly requested**.

This lesson focuses on:

- Distinguishing the signatures, return types, and roles of `string_agg`, `array_agg`, and `json_agg`.
- Using **`ORDER BY` inside the aggregate call**, separately from the query's outer `ORDER BY`.
- Handling **`DISTINCT`**, **`FILTER`**, `NULL`s, empty groups, and `COALESCE` data types.
- Aggregating into JSON objects, nested JSON structures, arrays, and deduplicated strings.
- Avoiding element duplication when joining multiple one-to-many tables; handling large element counts.
- Practical usage in SQL/JDBC and exercises in an order-management context.

> **Scope:** Examples use PostgreSQL and a lab database. `CREATE`/`INSERT` statements should only be run in a test environment where these object names are free. Across PostgreSQL versions, some JSON function variants and extended syntax may vary; the core techniques here use standard aggregates.

## 1. An Aggregate Produces One Value from Multiple Rows

An aggregate normally takes values from **multiple rows in the same group** and produces one result.

```sql
SELECT
    order_id,
    COUNT(*) AS line_count
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

`COUNT(*)` returns the row count. Instead of counting, we can **collect values**:

```sql
SELECT
    order_id,
    string_agg(product_name, ', ' ORDER BY line_no) AS names
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

Concept:

```text
Rows in group order_id = 1001
       │
       ▼
Sort by line_no inside the aggregate
       │
       ▼
"Mouse" → "Keyboard" → "Mouse"
       │
       ▼
Join with ", "
       │
       ▼
One text value: "Mouse, Keyboard, Mouse"
```

`GROUP BY` determines **which rows belong to the same group**. `ORDER BY` inside the aggregate determines **element order during concatenation**. `ORDER BY` at the end of the query determines **the order of aggregated output rows**. These are three distinct responsibilities and cannot substitute for one another.

## 2. Preparing the Test Data

Create a dedicated schema to avoid `search_path` dependencies:

```sql
CREATE SCHEMA IF NOT EXISTS lesson_aggregates;

CREATE TABLE lesson_aggregates.customers (
    customer_id BIGINT PRIMARY KEY,
    customer_name TEXT NOT NULL
);

CREATE TABLE lesson_aggregates.orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES lesson_aggregates.customers(customer_id),
    ordered_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('PENDING', 'PAID', 'CANCELLED'))
);

CREATE TABLE lesson_aggregates.order_items (
    order_id BIGINT NOT NULL
        REFERENCES lesson_aggregates.orders(order_id),
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_name TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    note TEXT,
    PRIMARY KEY (order_id, line_no)
);
```

Insert sample data:

```sql
INSERT INTO lesson_aggregates.customers(customer_id, customer_name)
VALUES
    (1, 'An'),
    (2, 'Bình'),
    (3, 'Chi');

INSERT INTO lesson_aggregates.orders(
    order_id, customer_id, ordered_at, status
)
VALUES
    (1001, 1, TIMESTAMPTZ '2026-11-10 09:00:00+07', 'PAID'),
    (1002, 1, TIMESTAMPTZ '2026-11-11 11:00:00+07', 'PENDING'),
    (1003, 2, TIMESTAMPTZ '2026-11-12 14:00:00+07', 'PAID'),
    (1004, 3, TIMESTAMPTZ '2026-11-13 16:00:00+07', 'PENDING');

INSERT INTO lesson_aggregates.order_items(
    order_id, line_no, product_name, quantity, unit_price, note
)
VALUES
    (1001, 1, 'Mouse',      2, 120000, 'Promotion'),
    (1001, 2, 'Keyboard',   1, 450000, NULL),
    (1001, 3, 'Mouse',      1, 120000, NULL),
    (1002, 1, 'Headphones', 1, 800000, 'Gift'),
    (1003, 1, 'USB-C Cable', 3, 100000, NULL);
```

Dataset characteristics:

- Order **1001** has three items; two items share the name **Mouse**.
- Order **1002** has one item: **Headphones**.
- Order **1003** has one item: **USB-C Cable**.
- Order **1004** has no items yet.
- The `note` column contains both text values and `NULL`s.

These cases help distinguish duplicate values, null elements, empty groups, and aggregation order.

### Specifying Source Order When Inspecting Data

```sql
SELECT
    order_id,
    line_no,
    product_name,
    quantity,
    note
FROM lesson_aggregates.order_items
ORDER BY order_id, line_no;
```

`ORDER BY` here sorts only **the rows being displayed**. It does not establish a permanent ordering rule for the table or for aggregates executed in other queries.

## 3. Comparing the Three Aggregate Functions

| Function | Result Type | Illustrative Output for Order 1001 | Typical Use Case |
|---|---|---|---|
| `string_agg(text, text)` | `text` | `Mouse, Keyboard, Mouse` | Name strings, display labels, short report lists. |
| `array_agg(expression)` | PostgreSQL array of element type | `{"Mouse","Keyboard","Mouse"}` | Preserving typed values in SQL, passing arrays to functions or apps. |
| `json_agg(expression)` | `json` representing an array | `["Mouse","Keyboard","Mouse"]` | APIs, data exchange, nesting objects. |

A side-by-side comparison query:

```sql
SELECT
    order_id,
    string_agg(product_name, ', ' ORDER BY line_no)
        AS products_text,
    array_agg(product_name ORDER BY line_no)
        AS products_array,
    json_agg(product_name ORDER BY line_no)
        AS products_json
FROM lesson_aggregates.order_items
GROUP BY order_id
ORDER BY order_id;
```

For order 1001, the results look visually similar in content, yet they **do not share the same data type**.

```sql
SELECT
    pg_typeof(string_agg(product_name, ', ')) AS text_type,
    pg_typeof(array_agg(product_name)) AS array_type,
    pg_typeof(json_agg(product_name)) AS json_type
FROM lesson_aggregates.order_items
WHERE order_id = 1001;
```

The respective types are **`text`**, **`text[]`**, and **`json`** for the `product_name TEXT` column.

**Choose the type based on downstream consumption**, not just because one looks nicer in `psql`.

## 4. string_agg: Joining Multiple Values into One String

Common syntax:

```sql
string_agg(value_expression, delimiter_expression
           ORDER BY sort_expression)
```

Where:

- `value_expression` is the expression converted to text for concatenation, typically `text`.
- `delimiter_expression` is the character or string separator placed between elements.
- `ORDER BY` **sits inside the aggregate call** to control concatenation order.

Example:

```sql
SELECT
    order_id,
    string_agg(product_name, ' | ' ORDER BY line_no) AS product_list
FROM lesson_aggregates.order_items
GROUP BY order_id
ORDER BY order_id;
```

Result for order 1001:

```text
Mouse | Keyboard | Mouse
```

### Delimiters Are Not Added at the Ends

With three elements A, B, C:

```text
string_agg(value, ', ') = A + ', ' + B + ', ' + C
```

There is no leading or trailing delimiter. The delimiter can be a comma, newline, or any string suited for display:

```sql
SELECT
    string_agg(product_name, E'\n' ORDER BY line_no) AS lines
FROM lesson_aggregates.order_items
WHERE order_id = 1001;
```

`E'\n'` is a string containing a newline character using PostgreSQL escape-string syntax.

### Concatenating Non-TEXT Values

A `numeric` price must be cast to a string representation before concatenating:

```sql
SELECT
    order_id,
    string_agg(unit_price::text, ', ' ORDER BY line_no)
        AS unit_prices
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

Or formatted inside an expression:

```sql
SELECT
    order_id,
    string_agg(
        product_name || ' x ' || quantity::text,
        '; ' ORDER BY line_no
    ) AS product_summary
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

Example for order 1001:

```text
Mouse x 2; Keyboard x 1; Mouse x 1
```

This string works well as **descriptive display text**. However, if an application needs to re-parse quantities and prices programmatically, structured JSON or arrays are far more reliable than splitting strings on `;`.

### string_agg Is Not a Complete CSV Tool

`string_agg(product_name, ',')` simply joins text; it **does not automatically escape** commas, quotes, or newlines inside values. If your goal is standards-compliant CSV export, use a proper CSV mechanism such as `COPY ... WITH (FORMAT csv)` instead of naive field concatenation.

## 5. array_agg: Keeping Elements in a PostgreSQL Array

`array_agg(expression)` builds an **array** from the input values in the group.

```sql
SELECT
    order_id,
    array_agg(product_name ORDER BY line_no) AS product_names
FROM lesson_aggregates.order_items
GROUP BY order_id
ORDER BY order_id;
```

Order 1001 produces a three-element array:

```text
{"Mouse","Keyboard","Mouse"}
```

This is **PostgreSQL array display syntax**, not JSON. In JSON, the equivalent array uses square brackets `[...]` rather than PostgreSQL's curly-brace array notation.

### Elements Retain Their Data Types

```sql
SELECT
    order_id,
    array_agg(quantity ORDER BY line_no) AS quantities,
    pg_typeof(array_agg(quantity)) AS quantity_array_type
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

Because `quantity` is `integer`, the result is **`integer[]`**, not a string that must be parsed back into integers.

You can apply array functions and operators:

```sql
WITH grouped AS (
    SELECT
        order_id,
        array_agg(product_name ORDER BY line_no) AS names
    FROM lesson_aggregates.order_items
    GROUP BY order_id
)
SELECT
    order_id,
    names,
    cardinality(names) AS number_of_elements,
    'Mouse' = ANY(names) AS has_mouse
FROM grouped
ORDER BY order_id;
```

`cardinality` returns the number of elements in the array. `= ANY(array)` checks whether a value matches at least one element under SQL comparison rules; keep three-valued logic in mind when an array contains `NULL`.

### Arrays Can Contain NULL Elements

`array_agg` **does not strip `NULL`s automatically**. Unlike `string_agg`, if you aggregate `note`:

```sql
SELECT
    order_id,
    array_agg(note ORDER BY line_no) AS notes
FROM lesson_aggregates.order_items
GROUP BY order_id
ORDER BY order_id;
```

Order 1001 has one `Promotion` note and two `NULL` notes. The resulting array retains all three positions, so **element positions can align with `line_no`** when sorted properly.

To keep only non-null notes:

```sql
SELECT
    order_id,
    array_agg(note ORDER BY line_no)
        FILTER (WHERE note IS NOT NULL) AS nonnull_notes
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

In this example, a group with no valid notes yields an aggregate result of **`NULL`**, not automatically an empty array. We will handle that later with `COALESCE`.

## 6. json_agg: Collecting Values into a JSON Array

`json_agg(expression)` returns a **`json`** value structured as a **JSON array**.

```sql
SELECT
    order_id,
    json_agg(product_name ORDER BY line_no) AS products_json
FROM lesson_aggregates.order_items
GROUP BY order_id
ORDER BY order_id;
```

Order 1001 renders as:

```json
["Mouse", "Keyboard", "Mouse"]
```

A key strength is that JSON supports **numbers, strings, booleans, null, arrays, and objects** inside one structure. For example, aggregating quantities:

```sql
SELECT
    order_id,
    json_agg(quantity ORDER BY line_no) AS quantities_json
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

Order 1001 evaluates to `[2,1,1]`, where elements are **JSON numbers**, not strings `"2"`, `"1"`.

### json_agg Preserves JSON null

`json_agg(note ORDER BY line_no)` converts SQL `NULL` input values into **JSON null** elements:

```sql
SELECT
    order_id,
    json_agg(note ORDER BY line_no) AS notes_json
FROM lesson_aggregates.order_items
GROUP BY order_id
ORDER BY order_id;
```

Order 1001 produces:

```json
["Promotion", null, null]
```

This is a major difference from `string_agg(note, ', ')`: string concatenation skips `NULL` inputs, whereas `json_agg` **keeps them as JSON null elements**.

### json_agg vs. jsonb_agg

PostgreSQL also provides **`jsonb_agg`**, returning **`jsonb`**:

```sql
SELECT
    order_id,
    json_agg(product_name ORDER BY line_no) AS as_json,
    jsonb_agg(product_name ORDER BY line_no) AS as_jsonb
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

| Characteristic | `json_agg` | `jsonb_agg` |
|---|---|---|
| Return type | `json` | `jsonb` |
| Produces a JSON array | Yes | Yes |
| Preserves sorted array element order | Yes | Yes |
| Guarantees key order inside JSON objects | **Do not rely on it** | **Do not rely on it** |
| JSONB lookup operators/features | Requires casting for JSONB-only operators. | Convenient for JSONB operations in PostgreSQL. |

**Element order in a JSON array is meaningful.** Conversely, **key order inside a JSON object** should never be relied upon as a business contract; in particular, `jsonb` stores and normalizes objects in its own internal format.

## 7. Most Important: ORDER BY Must Be Inside the Aggregate

Relational row sets have no inherent stable order. Aggregates like `string_agg`, `array_agg`, and `json_agg` are **order-sensitive**: changing input order changes the order of elements in the result.

### Unreliable Approach

```sql
SELECT
    order_id,
    string_agg(product_name, ', ') AS product_list
FROM lesson_aggregates.order_items
GROUP BY order_id
ORDER BY order_id;
```

This query sorts only **the output rows by `order_id`**. It never instructs PostgreSQL to concatenate each order's product names by `line_no`.

PostgreSQL may read rows in a different order due to:

- Changes in execution plan or indexes.
- How the planner executes grouping or joins.
- Physical storage order shifts after `UPDATE`/`VACUUM` or data loads.
- Parallel execution or other changes in how aggregate inputs are produced.

Never say "it always works on my machine" and treat that as an ordering guarantee.

### Correct Approach: Put ORDER BY Inside the Call

```sql
SELECT
    order_id,
    string_agg(product_name, ', ' ORDER BY line_no) AS products_text,
    array_agg(product_name ORDER BY line_no) AS products_array,
    json_agg(product_name ORDER BY line_no) AS products_json
FROM lesson_aggregates.order_items
GROUP BY order_id
ORDER BY order_id;
```

Each aggregate explicitly requests its input sorted by `line_no`. The outer `ORDER BY order_id` only determines that order 1001 appears before order 1002.

### Two ORDER BY Locations, Two Meanings

```text
SELECT
  order_id,
  string_agg(product_name, ', ' ORDER BY line_no)
                        │                │
                        │                └── ELEMENT order inside the string
                        └── delimiter
FROM ...
GROUP BY order_id
ORDER BY order_id DESC;
         └── OUTPUT ROW order (orders)
```

**Quick rule of thumb:** Whenever a per-group list must be ordered, put `ORDER BY` **right inside** `string_agg`, `array_agg`, or `json_agg`.

## 8. Can an ORDER BY in a Subquery Replace It?

A misleading pattern:

```sql
SELECT
    order_id,
    array_agg(product_name) AS products
FROM (
    SELECT order_id, product_name
    FROM lesson_aggregates.order_items
    ORDER BY line_no
) AS sorted_items
GROUP BY order_id;
```

The subquery looks "pre-sorted," and in simple tests the output might happen to look right. However, if the outer query adds a `JOIN`, grouping, or other operations, the actual order in which rows reach the aggregate **can change**.

A far more reliable expression of intent:

```sql
SELECT
    order_id,
    array_agg(product_name ORDER BY line_no) AS products
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

When complex sorting logic is required, you can still use a CTE or subquery to **compute the sort key**, and then reference that key in the aggregate's `ORDER BY` at the final stage:

```sql
WITH prepared AS (
    SELECT
        order_id,
        line_no,
        product_name,
        lower(product_name) AS normalized_name
    FROM lesson_aggregates.order_items
)
SELECT
    order_id,
    array_agg(product_name
              ORDER BY normalized_name, line_no) AS sorted_names
FROM prepared
GROUP BY order_id;
```

This distinguishes **pre-computing sort expressions** from **guaranteeing aggregate input order**.

## 9. Stable Ordering Needs a Tie-Breaker for Duplicate Values

Suppose you sort by `unit_price`, and two items share a price of 120,000. If you write only:

```sql
SELECT
    order_id,
    json_agg(product_name ORDER BY unit_price) AS products
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

the two items with **identical `unit_price`** have no defined relative order under this key. If their JSON payloads differ, different runs may return them in an unexpected order.

Add a **tie-breaker**:

```sql
SELECT
    order_id,
    json_agg(
        json_build_object(
            'line_no', line_no,
            'product', product_name,
            'price', unit_price
        )
        ORDER BY unit_price, line_no
    ) AS products
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

Because `(order_id, line_no)` is the sample table's primary key, `line_no` uniquely orders items **within each order group**. That yields deterministic ordering even when prices tie.

### Principles for Choosing Sort Keys

1. The primary key reflects **business order**: timestamp, sequence number, priority, `sort_order`.
2. Add a secondary key that is **unique within the group** when strict determinism is required.
3. For text data, remember collation determines comparison and alphabetical order.
4. Explicitly specify `NULLS FIRST`/`NULLS LAST` if the sort key can be null and null placement matters.
5. Never rely on `ctid` or physical row order as a long-term business sort key.

Example:

```sql
SELECT
    order_id,
    array_agg(
        product_name
        ORDER BY unit_price DESC NULLS LAST, line_no ASC
    ) AS names_expensive_first
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

## 10. Collation Affects String Ordering

When sorting by `product_name`, PostgreSQL applies the active **collation** rules. Upper/lowercase sorting, accents, and language-specific characters depend on collation and server configuration.

```sql
SELECT
    order_id,
    string_agg(product_name, ', ' ORDER BY product_name)
        AS names_by_text_sort
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

If you need deterministic byte/codepoint comparison for a specific expression in PostgreSQL, you can specify the collation explicitly:

```sql
SELECT
    order_id,
    array_agg(
        product_name
        ORDER BY product_name COLLATE "C", line_no
    ) AS names_c_collation
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

**Do not blindly choose `"C"` for every user-facing interface (such as Vietnamese UIs).** For user display order, pick a locale/collation matching language expectations. `"C"` is better suited for consistent technical byte-order sorting, which differs from natural linguistic sorting.

When array/JSON outputs form an integration contract between systems, specify the exact **sort rule and tie-breaker** rather than vaguely saying "sorted by name."

## 11. NULL Handling: Three Functions with Different Behaviors

For `NULL` inputs:

| Group Inputs | `string_agg(note, ', ')` | `array_agg(note)` | `json_agg(note)` |
|---|---|---|---|
| `'A'`, `NULL`, `'B'` | `A, B` | `{"A",NULL,"B"}` | `["A",null,"B"]` |
| `NULL`, `NULL` | `NULL` | Array of 2 SQL NULL elements | `[null,null]` |
| **Zero input rows** | `NULL` | `NULL` | `NULL` |

Key differences:

- `string_agg` **skips `NULL` input values**. If all inputs are null or there are no rows, the result is `NULL`.
- `array_agg` **retains null values as array elements**.
- `json_agg` **retains null values as JSON null elements**.
- **Zero rows** differs from **one row whose aggregated expression evaluates to null**.

Example on order 1001:

```sql
SELECT
    string_agg(note, ' | ' ORDER BY line_no) AS notes_text,
    array_agg(note ORDER BY line_no) AS notes_array,
    json_agg(note ORDER BY line_no) AS notes_json
FROM lesson_aggregates.order_items
WHERE order_id = 1001;
```

Result:

```text
notes_text  = Promotion
notes_array = {"Promotion",NULL,NULL}
notes_json  = ["Promotion",null,null]
```

### One Row Containing NULL

```sql
SELECT
    string_agg(x.note, ', ') AS s,
    array_agg(x.note) AS a,
    json_agg(x.note) AS j
FROM (VALUES (NULL::text)) AS x(note);
```

Result:

```text
s = SQL NULL
a = {NULL}
j = [null]
```

### Zero Rows

```sql
SELECT
    string_agg(note, ', ') AS s,
    array_agg(note) AS a,
    json_agg(note) AS j
FROM lesson_aggregates.order_items
WHERE order_id = -1;
```

An aggregate query **without `GROUP BY`** still returns **one result row**, where all three aggregates evaluate to SQL `NULL` because there are no matching inputs.

This lays the groundwork for understanding itemless groups in a `LEFT JOIN`.

## 12. LEFT JOIN: A NULL-Extended Row Is Not an Empty Group

To list **every order**, including order 1004 which has no items:

```sql
SELECT
    o.order_id,
    COUNT(i.line_no) AS item_count,
    string_agg(i.product_name, ', ' ORDER BY i.line_no)
        AS item_names,
    array_agg(i.product_name ORDER BY i.line_no)
        AS item_array,
    json_agg(i.product_name ORDER BY i.line_no)
        AS item_json
FROM lesson_aggregates.orders AS o
LEFT JOIN lesson_aggregates.order_items AS i
  ON i.order_id = o.order_id
GROUP BY o.order_id
ORDER BY o.order_id;
```

For order **1004**, `LEFT JOIN` creates **one intermediate row** from `o` with all `i.*` columns set to `NULL`:

```text
order_id = 1004, i.line_no = NULL, i.product_name = NULL
```

Consequently:

- `COUNT(i.line_no)` = **0** because `COUNT(expression)` ignores nulls.
- `string_agg(i.product_name, ', ')` = SQL **NULL**.
- `array_agg(i.product_name)` becomes a **single-element NULL array**.
- `json_agg(i.product_name)` becomes **`[null]`**.

This is a classic API bug: an "order with no items" gets serialized as an array containing one `null` element instead of an **empty array**.

### Using FILTER to Exclude Fake Rows from LEFT JOIN

```sql
SELECT
    o.order_id,
    COUNT(i.line_no) AS item_count,
    array_agg(i.product_name ORDER BY i.line_no)
        FILTER (WHERE i.line_no IS NOT NULL) AS item_array,
    json_agg(i.product_name ORDER BY i.line_no)
        FILTER (WHERE i.line_no IS NOT NULL) AS item_json
FROM lesson_aggregates.orders AS o
LEFT JOIN lesson_aggregates.order_items AS i
  ON i.order_id = o.order_id
GROUP BY o.order_id
ORDER BY o.order_id;
```

`FILTER (WHERE i.line_no IS NOT NULL)` excludes the unmatched right-side row because `line_no` **cannot be null on a real item**. For order 1004, the aggregate receives **0 inputs**, so `array_agg`/`json_agg` evaluates to **SQL NULL**.

Next, use `COALESCE` to convert SQL null into a properly typed empty array.

## 13. COALESCE: Choosing the Right Typed Empty Value

Standard aggregates like `array_agg`, `json_agg`, and `string_agg` return `NULL` when given **no inputs**. If an API always expects a list, convert it to an empty value:

```sql
SELECT
    o.order_id,
    COALESCE(
        string_agg(
            i.product_name, ', '
            ORDER BY i.line_no
        ),
        ''
    ) AS item_names,
    COALESCE(
        array_agg(i.product_name ORDER BY i.line_no)
            FILTER (WHERE i.line_no IS NOT NULL),
        ARRAY[]::text[]
    ) AS item_array,
    COALESCE(
        json_agg(i.product_name ORDER BY i.line_no)
            FILTER (WHERE i.line_no IS NOT NULL),
        '[]'::json
    ) AS item_json
FROM lesson_aggregates.orders AS o
LEFT JOIN lesson_aggregates.order_items AS i
  ON i.order_id = o.order_id
GROUP BY o.order_id
ORDER BY o.order_id;
```

For order 1004:

| Column | Value |
|---|---|
| `item_names` | Empty string `''` |
| `item_array` | Empty PostgreSQL array `{}` of type `text[]` |
| `item_json` | Empty JSON array `[]` of type `json` |

### Why Must an Empty Array Be Explicitly Cast?

`ARRAY[]` contains no elements, so PostgreSQL does not always have enough context to infer its element type. Writing **`ARRAY[]::text[]`** ensures type compatibility with `array_agg(product_name)`.

Similarly:

```sql
SELECT
    COALESCE(array_agg(quantity), ARRAY[]::integer[]) AS quantities
FROM lesson_aggregates.order_items
WHERE order_id = -1;
```

With JSONB:

```sql
SELECT
    COALESCE(jsonb_agg(product_name), '[]'::jsonb) AS names
FROM lesson_aggregates.order_items
WHERE order_id = -1;
```

### Empty vs. NULL Is a Business Decision

Do not automatically turn every `NULL` into an empty string or array. Some systems distinguish:

- **`NULL`**: unknown, not fetched, not computed.
- **`[]`/`{}`**: confirmed empty—zero elements exist.

If the API contract requires lists to always be `[]`, `COALESCE` is right. If business logic distinguishes *unknown* from *empty*, keep null and provide explicit status flags when needed.

## 14. FILTER: Selecting a Subset of Rows per Aggregate

Syntax:

```sql
aggregate_function(...) FILTER (WHERE condition)
```

`FILTER` applies **only to that individual aggregate**, rather than removing rows from the whole group like a query-level `WHERE`.

For example, generating two lists within the same grouping pass:

```sql
SELECT
    order_id,
    string_agg(
        product_name, ', '
        ORDER BY line_no
    ) AS all_products,
    string_agg(
        product_name, ', '
        ORDER BY line_no
    ) FILTER (WHERE quantity >= 2) AS products_with_multiple_units
FROM lesson_aggregates.order_items
GROUP BY order_id
ORDER BY order_id;
```

Order 1001:

- `all_products` = `Mouse, Keyboard, Mouse`.
- `products_with_multiple_units` = `Mouse` because only the first line has `quantity >= 2`.

### FILTER vs. WHERE

```sql
-- WHERE removes rows before any aggregate receives input.
SELECT
    order_id,
    COUNT(*) AS item_rows,
    string_agg(product_name, ', ' ORDER BY line_no) AS names
FROM lesson_aggregates.order_items
WHERE quantity >= 2
GROUP BY order_id;
```

This query **no longer sees** quantity-1 rows in either `COUNT(*)` or `string_agg`. Meanwhile, `FILTER` allows **each aggregate** to have its own predicate.

### FILTER for Genuine NULL Values

To omit items with null notes:

```sql
SELECT
    order_id,
    COALESCE(
        json_agg(note ORDER BY line_no)
            FILTER (WHERE note IS NOT NULL),
        '[]'::json
    ) AS notes_json
FROM lesson_aggregates.order_items
GROUP BY order_id
ORDER BY order_id;
```

`note IS NOT NULL` means **exclude items without notes**, which differs from `i.line_no IS NOT NULL` used to exclude **unmatched rows from a LEFT JOIN**.

Choose the condition matching what you actually want to filter: null input values versus existence of a source row.

## 15. DISTINCT: Deduplicating Before Aggregating

Order 1001 has two item rows named `Mouse`. To get a list of **unique product names**:

```sql
SELECT
    order_id,
    string_agg(
        DISTINCT product_name,
        ', ' ORDER BY product_name
    ) AS distinct_names
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

Order 1001 has two unique names: **Keyboard** and **Mouse**, sorted by `product_name`/collation.

With arrays:

```sql
SELECT
    order_id,
    array_agg(
        DISTINCT product_name
        ORDER BY product_name
    ) AS unique_products
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

With JSON:

```sql
SELECT
    order_id,
    json_agg(
        DISTINCT product_name
        ORDER BY product_name
    ) AS unique_products_json
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

### DISTINCT Deduplicates by Expression Value

If two items share the name `Mouse` with different `line_no` and `quantity`, `DISTINCT product_name` collapses them into **one name**. That is desired when showing "distinct products," but **wrong** when describing each line item.

For individual lines, use:

```sql
SELECT
    order_id,
    json_agg(
        json_build_object(
            'line_no', line_no,
            'product', product_name,
            'quantity', quantity
        )
        ORDER BY line_no
    ) AS items
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

**DISTINCT is a choice about element identity**, not a cure-all for queries whose JOINs inflate row counts.

## 16. DISTINCT + ORDER BY: An Important Syntax Constraint

In PostgreSQL, when an aggregate uses **`DISTINCT`**, the expressions in the aggregate's **`ORDER BY`** must match expressions in the aggregate's argument list. You cannot arbitrarily sort DISTINCT outputs by some other column outside the deduplicated expressions.

Valid example:

```sql
SELECT
    order_id,
    string_agg(
        DISTINCT product_name,
        ', ' ORDER BY product_name
    ) AS names
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

**Invalid** example:

```sql
-- Invalid: DISTINCT on product_name but attempting ORDER BY line_no.
SELECT
    order_id,
    string_agg(
        DISTINCT product_name,
        ', ' ORDER BY line_no
    ) AS names
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

It is also ambiguous semantically: `Mouse` appears at both `line_no = 1` and `line_no = 3`, so after deduplication, **which `line_no`** should determine its sort position?

### Solution: Determine the Sort Key for Each Unique Value

Suppose you want **each product name once, ordered by its first appearance in the order**:

```sql
WITH distinct_products AS (
    SELECT
        order_id,
        product_name,
        MIN(line_no) AS first_line_no
    FROM lesson_aggregates.order_items
    GROUP BY order_id, product_name
)
SELECT
    order_id,
    string_agg(
        product_name,
        ', ' ORDER BY first_line_no, product_name
    ) AS names_by_first_appearance
FROM distinct_products
GROUP BY order_id
ORDER BY order_id;
```

Here:

1. The CTE produces **one row per `(order_id, product_name)` pair**.
2. `MIN(line_no)` unambiguously picks the first appearance position.
3. The final aggregate **needs no DISTINCT**, because the input is already deduplicated.
4. `ORDER BY first_line_no, product_name` orders the list according to the business rule.

This pattern is worth remembering: **deduplicate and compute the sort key in an intermediate step**, then run an ordered aggregate at the end.

## 17. Can DISTINCT Combine with FILTER?

Both can be used together:

```sql
SELECT
    order_id,
    array_agg(
        DISTINCT product_name
        ORDER BY product_name
    ) FILTER (WHERE quantity >= 2) AS distinct_bulk_names
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

`FILTER` selects rows with quantity 2 or more for the aggregate; `DISTINCT` removes duplicate names from those selected rows; `ORDER BY` determines the order of the remaining elements.

Do not equate this logical evaluation order with a fixed physical execution plan. PostgreSQL may pick various optimization strategies while preserving SQL semantics.

### DISTINCT with Complex Expressions

For example, deduplicating by normalized name:

```sql
SELECT
    order_id,
    array_agg(
        DISTINCT lower(product_name)
        ORDER BY lower(product_name)
    ) AS normalized_names
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

When you want to return the **original casing** while deduplicating by **normalized name**, it becomes more complex: you must pick a representative value per normalized key. Typically solve this with a CTE using `ROW_NUMBER()` or a deterministic `MIN`/`MAX` rule before aggregating.

## 18. Building JSON Objects from Rows

`json_agg(product_name)` produces only an array of strings. APIs usually need an **array of objects** containing multiple fields per item.

`json_build_object` creates a JSON object from **key/value** pairs:

```sql
SELECT
    order_id,
    json_agg(
        json_build_object(
            'line_no', line_no,
            'product_name', product_name,
            'quantity', quantity,
            'unit_price', unit_price,
            'note', note
        )
        ORDER BY line_no
    ) AS items
FROM lesson_aggregates.order_items
GROUP BY order_id
ORDER BY order_id;
```

Order 1001 produces:

```json
[
  {
    "line_no": 1,
    "product_name": "Mouse",
    "quantity": 2,
    "unit_price": 120000,
    "note": "Promotion"
  },
  {
    "line_no": 2,
    "product_name": "Keyboard",
    "quantity": 1,
    "unit_price": 450000,
    "note": null
  },
  {
    "line_no": 3,
    "product_name": "Mouse",
    "quantity": 1,
    "unit_price": 120000,
    "note": null
  }
]
```

Notes:

- `unit_price` is numeric, so it serializes as a **JSON number** here, not a formatted currency string.
- Null `note` becomes **JSON null**, unless you add logic to strip null keys.
- **Object order in the array** is controlled by `ORDER BY line_no` inside `json_agg`.
- Never rely on **key order** inside an object as a business guarantee.

### JSONB Version

```sql
SELECT
    order_id,
    jsonb_agg(
        jsonb_build_object(
            'line_no', line_no,
            'product', product_name,
            'quantity', quantity
        )
        ORDER BY line_no
    ) AS items
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

The output type is **`jsonb`**. If the application applies further JSONB operators downstream, `jsonb_agg` can be convenient.

## 19. JSON Composite Rows, row_to_json, and API Contract Clarity

PostgreSQL can convert **a row/composite value** directly to JSON:

```sql
SELECT
    order_id,
    json_agg(i ORDER BY i.line_no) AS raw_items
FROM lesson_aggregates.order_items AS i
GROUP BY i.order_id;
```

`i` is the entire composite row of `order_items`, not just a single column. The resulting JSON includes **every column** of the source table.

### Risk of Serializing Whole Rows

If columns like `internal_note` or `supplier_cost` are added to the table later, `json_agg(i)` may unintentionally expose those new fields in client JSON responses.

For APIs with explicit schema contracts, it is safer to pick fields explicitly:

```sql
SELECT
    i.order_id,
    json_agg(
        json_build_object(
            'lineNo', i.line_no,
            'name', i.product_name,
            'quantity', i.quantity
        )
        ORDER BY i.line_no
    ) AS items
FROM lesson_aggregates.order_items AS i
GROUP BY i.order_id;
```

This also lets you map snake_case SQL columns to camelCase JSON keys per API conventions.

### row_to_json on a Pre-Selected Record

When you already have a derived table or record with exact fields:

```sql
SELECT
    row_to_json(x) AS item_json
FROM (
    SELECT line_no, product_name, quantity
    FROM lesson_aggregates.order_items
    WHERE order_id = 1001
) AS x
ORDER BY x.line_no;
```

This query returns **multiple JSON object rows**, one per item. To get **one JSON array**, wrap it with `json_agg` at the right level, putting `ORDER BY` inside the aggregate:

```sql
SELECT json_agg(row_to_json(x) ORDER BY x.line_no) AS items
FROM (
    SELECT line_no, product_name, quantity
    FROM lesson_aggregates.order_items
    WHERE order_id = 1001
) AS x;
```

`row_to_json(x)` turns the fields of record `x` into an object; `json_agg` gathers those objects into one JSON array.

## 20. Nested JSON: One Customer with Many Orders, Each with Many Items

An API sometimes wants a structure like:

```json
{
  "customer_id": 1,
  "customer_name": "An",
  "orders": [
    {
      "order_id": 1001,
      "status": "PAID",
      "items": [
        {"line_no": 1, "name": "Mouse"},
        {"line_no": 2, "name": "Keyboard"},
        {"line_no": 3, "name": "Mouse"}
      ]
    },
    {
      "order_id": 1002,
      "status": "PENDING",
      "items": [
        {"line_no": 1, "name": "Headphones"}
      ]
    }
  ]
}
```

**Recommended approach:** aggregate bottom-up from the **finest grain** to coarser levels, avoiding row multiplication from joining multiple one-to-many relationships into a single aggregate.

### Step 1 — Aggregate Items per Order

```sql
WITH items_per_order AS (
    SELECT
        i.order_id,
        jsonb_agg(
            jsonb_build_object(
                'line_no', i.line_no,
                'name', i.product_name,
                'quantity', i.quantity
            )
            ORDER BY i.line_no
        ) AS items
    FROM lesson_aggregates.order_items AS i
    GROUP BY i.order_id
)
SELECT
    o.order_id,
    COALESCE(p.items, '[]'::jsonb) AS items
FROM lesson_aggregates.orders AS o
LEFT JOIN items_per_order AS p
  ON p.order_id = o.order_id
ORDER BY o.order_id;
```

By `LEFT JOIN`ing onto the **pre-aggregated table**, order 1004 cleanly receives `[]` rather than `[null]` from a direct one-to-many join.

### Step 2 — Build JSON per Order

```sql
WITH items_per_order AS (
    SELECT
        i.order_id,
        jsonb_agg(
            jsonb_build_object(
                'line_no', i.line_no,
                'name', i.product_name,
                'quantity', i.quantity
            )
            ORDER BY i.line_no
        ) AS items
    FROM lesson_aggregates.order_items AS i
    GROUP BY i.order_id
),
orders_with_items AS (
    SELECT
        o.order_id,
        o.customer_id,
        o.status,
        o.ordered_at,
        jsonb_build_object(
            'order_id', o.order_id,
            'status', o.status,
            'items', COALESCE(ip.items, '[]'::jsonb)
        ) AS order_document
    FROM lesson_aggregates.orders AS o
    LEFT JOIN items_per_order AS ip
      ON ip.order_id = o.order_id
)
SELECT
    customer_id,
    jsonb_agg(
        order_document
        ORDER BY ordered_at, order_id
    ) AS orders
FROM orders_with_items
GROUP BY customer_id
ORDER BY customer_id;
```

Each `order_document` already holds an ordered `items` array. The outer aggregate builds the **orders array**, sorted by timestamp and ID.

### Step 3 — Keep Customers Without Orders

To include **every customer**, even those without orders:

```sql
WITH items_per_order AS (
    SELECT
        i.order_id,
        jsonb_agg(
            jsonb_build_object(
                'line_no', i.line_no,
                'name', i.product_name,
                'quantity', i.quantity
            )
            ORDER BY i.line_no
        ) AS items
    FROM lesson_aggregates.order_items AS i
    GROUP BY i.order_id
),
orders_with_items AS (
    SELECT
        o.order_id,
        o.customer_id,
        o.ordered_at,
        jsonb_build_object(
            'order_id', o.order_id,
            'status', o.status,
            'items', COALESCE(ip.items, '[]'::jsonb)
        ) AS order_document
    FROM lesson_aggregates.orders AS o
    LEFT JOIN items_per_order AS ip
      ON ip.order_id = o.order_id
)
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(
        jsonb_agg(
            o.order_document
            ORDER BY o.ordered_at, o.order_id
        ) FILTER (WHERE o.order_id IS NOT NULL),
        '[]'::jsonb
    ) AS orders
FROM lesson_aggregates.customers AS c
LEFT JOIN orders_with_items AS o
  ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

In the sample data, every customer has at least one order, yet the SQL is written to **remain valid when customers without orders are added**.

### Why Not Write json_agg(json_agg(...))?

PostgreSQL does not permit **directly nesting one aggregate inside another at the same SELECT level**. Separating levels via **CTEs or subqueries** makes the two grouping grains explicit:

```text
order_items
    │ jsonb_agg by order_id
    ▼
items_per_order
    │ JOIN to orders
    ▼
orders_with_items
    │ jsonb_agg by customer_id
    ▼
orders_per_customer
```

This also prevents duplicate-element bugs when data involves multiple one-to-many relationships.

## 21. Joining Multiple One-to-Many Sources Can Duplicate Elements

Suppose the system adds an `order_comments` table, and one order has **two comments** and **three items**. Joining both tables directly:

```text
orders (1 row)
    ├── items (3 rows)
    └── comments (2 rows)
                  │
                  ▼
JOIN both sides → can produce 3 × 2 = 6 rows
```

Running `json_agg(i.product_name)` afterward will include each item **twice**, even though `order_items` stored it only once.

### Do Not Treat DISTINCT as a General Solution

If two items have different `line_no`s yet share the name `Mouse`, `json_agg(DISTINCT product_name)` leaves only one `Mouse`. It "fixes" the duplicated count by **deleting valid lines**.

A better pattern:

1. Identify the row grain of each source.
2. Aggregate `order_items` by `order_id` in its own CTE/subquery.
3. Aggregate `order_comments` by `order_id` in another CTE/subquery.
4. Join **each source (now at most one row per order)** to `orders`.

Ordering still requires an explicit `ORDER BY` inside each CTE's aggregate.

### General SQL Pattern

```sql
WITH items AS (
    SELECT
        order_id,
        jsonb_agg(
            jsonb_build_object(
                'line_no', line_no,
                'name', product_name
            )
            ORDER BY line_no
        ) AS item_list
    FROM lesson_aggregates.order_items
    GROUP BY order_id
)
SELECT
    o.order_id,
    COALESCE(i.item_list, '[]'::jsonb) AS item_list
FROM lesson_aggregates.orders AS o
LEFT JOIN items AS i USING (order_id);
```

Thinking **"aggregate first, join later"** is especially helpful when assembling JSON responses with multiple independent collections.

## 22. json_agg, JSON Arrays, and JSON Objects Differ

Two API needs:

1. A list that may contain duplicate keys/values and must preserve order → **JSON array**.
2. Looking up values by key name without relying on key order → **JSON object**.

`json_agg` produces an **array**, not a map/object:

```sql
SELECT json_agg(
    json_build_object('line', line_no, 'product', product_name)
    ORDER BY line_no
)
FROM lesson_aggregates.order_items
WHERE order_id = 1001;
```

If you want an object mapping keys to values, PostgreSQL offers `json_object_agg` or `jsonb_object_agg` in supported versions. Be careful, however:

- JSON objects **do not guarantee element order** the way JSON arrays do.
- Duplicate-key handling can vary across functions, variants, and versions.
- If business data has multiple items with the same `product_name`, using product name as the key **loses the one-to-many multiplicity** or causes key collisions.

Example building an object when the **key is clearly unique**:

```sql
SELECT
    order_id,
    jsonb_object_agg(line_no::text, product_name) AS product_by_line
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

For order 1001, the object has keys `"1"`, `"2"`, `"3"`. **Do not infer item sequence from displayed key order.** To preserve sequence, use `jsonb_agg` with `ORDER BY line_no`.

## 23. Unnesting Aggregated Results Back to Elements

Aggregation produces one value per group, yet an application or query may need to **expand** it back into rows.

### PostgreSQL Arrays and unnest

```sql
WITH grouped AS (
    SELECT
        order_id,
        array_agg(product_name ORDER BY line_no) AS names
    FROM lesson_aggregates.order_items
    WHERE order_id = 1001
    GROUP BY order_id
)
SELECT
    g.order_id,
    x.ordinality,
    x.name
FROM grouped AS g
CROSS JOIN LATERAL unnest(g.names)
    WITH ORDINALITY AS x(name, ordinality)
ORDER BY g.order_id, x.ordinality;
```

`WITH ORDINALITY` generates element positions during unnesting. `ORDER BY ordinality` ensures the expanded rows reflect the stored order.

### JSON Arrays and jsonb_array_elements

```sql
WITH grouped AS (
    SELECT
        order_id,
        jsonb_agg(
            jsonb_build_object(
                'line_no', line_no,
                'product', product_name
            )
            ORDER BY line_no
        ) AS items
    FROM lesson_aggregates.order_items
    WHERE order_id = 1001
    GROUP BY order_id
)
SELECT
    g.order_id,
    x.ordinality,
    x.item ->> 'product' AS product_name
FROM grouped AS g
CROSS JOIN LATERAL jsonb_array_elements(g.items)
    WITH ORDINALITY AS x(item, ordinality)
ORDER BY x.ordinality;
```

`->>` extracts a JSON field as text. If you need arithmetic on numeric attributes, cast deliberately and validate inputs.

### Concatenated Strings Do Not Preserve Structure

With `string_agg`, if a `product_name` contains `,` or `;`, splitting the string back into the original list can break. Whenever **round-trip fidelity** is needed, prefer arrays or JSON over formatted strings.

## 24. Single-Level or Multi-Level Grouping?

`GROUP BY` decides **which entity one output row represents**:

| Goal | Grouping Level |
|---|---|
| One string of product names per order | `GROUP BY order_id` |
| One array of all product names bought by a customer | Join orders with items, then `GROUP BY customer_id` |
| One JSON array of orders per customer | Build an object per order, then `GROUP BY customer_id` |
| A customer → orders → items hierarchy | Multi-level aggregation via CTEs/subqueries |
| One JSON array of all products in the database | Aggregate without `GROUP BY` |

Example: all product names appearing across each customer's orders:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(
        array_agg(
            i.product_name
            ORDER BY o.ordered_at, o.order_id, i.line_no
        ) FILTER (WHERE i.line_no IS NOT NULL),
        ARRAY[]::text[]
    ) AS all_purchased_product_names
FROM lesson_aggregates.customers AS c
LEFT JOIN lesson_aggregates.orders AS o
  ON o.customer_id = c.customer_id
LEFT JOIN lesson_aggregates.order_items AS i
  ON i.order_id = o.order_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Array order is **order timestamp → order ID → line number**. If two orders share the same timestamp, `o.order_id` breaks the tie. If a customer has no orders or items, the result is an empty array thanks to `FILTER` and `COALESCE`.

### When You Need Unique Names per Customer

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(
        array_agg(
            DISTINCT i.product_name
            ORDER BY i.product_name
        ) FILTER (WHERE i.product_name IS NOT NULL),
        ARRAY[]::text[]
    ) AS distinct_product_names
FROM lesson_aggregates.customers AS c
LEFT JOIN lesson_aggregates.orders AS o
  ON o.customer_id = c.customer_id
LEFT JOIN lesson_aggregates.order_items AS i
  ON i.order_id = o.order_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

In this query, names are **deduplicated and sorted alphabetically**, not by purchase time. The two requirements—**"by purchase sequence"** vs. **"unique product catalog"**—are different data contracts.

## 25. Conditional Aggregation by Order Status

Suppose you want two lists per customer: paid orders and pending orders.

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(
        array_agg(
            o.order_id ORDER BY o.ordered_at, o.order_id
        ) FILTER (WHERE o.status = 'PAID'),
        ARRAY[]::bigint[]
    ) AS paid_order_ids,
    COALESCE(
        array_agg(
            o.order_id ORDER BY o.ordered_at, o.order_id
        ) FILTER (WHERE o.status = 'PENDING'),
        ARRAY[]::bigint[]
    ) AS pending_order_ids
FROM lesson_aggregates.customers AS c
LEFT JOIN lesson_aggregates.orders AS o
  ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Here:

- One `LEFT JOIN` feeds **two aggregates with two different conditions**.
- `FILTER` by status picks inputs for each array.
- `ORDER BY` inside each aggregate orders IDs chronologically.
- `COALESCE` returns an empty `bigint[]` when a customer has no orders in that status.

If you put `WHERE o.status = 'PAID'` at the query level, `PENDING` orders would be dropped before the second aggregate runs. Thus **`FILTER` is the right tool** when building multiple conditional lists in one pass.

## 26. HAVING and Post-Aggregation Filtering

`WHERE` filters inputs before grouping; `HAVING` filters **already aggregated groups**.

For example, fetching orders with at least two line items, including their JSON array:

```sql
SELECT
    order_id,
    COUNT(*) AS item_count,
    json_agg(
        json_build_object(
            'line_no', line_no,
            'product', product_name
        )
        ORDER BY line_no
    ) AS items
FROM lesson_aggregates.order_items
GROUP BY order_id
HAVING COUNT(*) >= 2;
```

On the sample data, only order **1001** has two or more lines.

### Do Not Use SELECT Aliases in HAVING Like in ORDER BY

Within the same query block, write:

```sql
HAVING COUNT(*) >= 2
```

instead of relying on the `item_count` alias from `SELECT`. If you want to filter by the alias explicitly, wrap the aggregation in a CTE and filter in the outer query:

```sql
WITH per_order AS (
    SELECT
        order_id,
        COUNT(*) AS item_count,
        array_agg(product_name ORDER BY line_no) AS names
    FROM lesson_aggregates.order_items
    GROUP BY order_id
)
SELECT *
FROM per_order
WHERE item_count >= 2
ORDER BY order_id;
```

## 27. Should You Build Strings Using array_agg + array_to_string?

PostgreSQL provides `array_to_string` to convert an array into a string:

```sql
SELECT
    order_id,
    array_to_string(
        array_agg(product_name ORDER BY line_no),
        ', '
    ) AS product_list
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

For non-null names, the result matches `string_agg(product_name, ', ' ORDER BY line_no)`.

However, if inputs contain `NULL`, `array_to_string` handles nulls via its optional replacement argument, whereas `array_agg` keeps nulls inside the array. Do not assume **every `array_agg` + `array_to_string` combination behaves identically to `string_agg`**.

If you only need a display string, `string_agg` is shorter. If you need the array for SQL manipulation before formatting it into text, `array_agg` is helpful.

## 28. ORDER BY When Aggregating Formatted Values

Another mistake is **sorting by the formatted string** instead of the underlying data type.

For example, quantities 2, 10, 100:

```sql
WITH values_to_aggregate(n) AS (
    VALUES (2), (10), (100)
)
SELECT
    string_agg(n::text, ', ' ORDER BY n::text) AS text_order,
    string_agg(n::text, ', ' ORDER BY n) AS numeric_order
FROM values_to_aggregate;
```

`text_order` prints **10, 100, 2** under standard text collation, whereas `numeric_order` prints **2, 10, 100**.

**Rule:** The expression passed into the aggregate can be formatted text for display; **the sort key should stay in its native type**—number, timestamp, or priority integer—when true value order is desired.

Likewise, never sort timestamps by a formatted `'DD/MM/YYYY'` string when chronological order is intended; use `ORDER BY timestamp_column`.

## 29. Limiting Elements Before Aggregating

Suppose a customer has millions of events. Running:

```sql
SELECT json_agg(event_payload ORDER BY event_time)
FROM big_events
WHERE customer_id = 1;
```

can create a massive JSON array, consuming heavy memory, sort time, and network bandwidth. This is an **illustrative pattern**; `big_events` is not created in this lesson.

If an API needs only the **10 most recent events**, restrict the **qualifying input rows before aggregating**.

Example on the sample orders table using a `LIMIT` subquery:

```sql
SELECT COALESCE(
    json_agg(
        json_build_object(
            'order_id', recent.order_id,
            'ordered_at', recent.ordered_at
        )
        ORDER BY recent.ordered_at DESC, recent.order_id DESC
    ),
    '[]'::json
) AS ten_latest_orders
FROM (
    SELECT
        o.order_id,
        o.ordered_at
    FROM lesson_aggregates.orders AS o
    ORDER BY o.ordered_at DESC, o.order_id DESC
    LIMIT 10
) AS recent;
```

Here:

1. The subquery picks the **10 newest orders** with a deterministic tie-breaker.
2. The aggregate builds an array from **at most those 10 rows**.
3. `ORDER BY` still sits inside `json_agg` to lock in element order.

Never place `LIMIT 10` at the end of an aggregate query expecting it to truncate a JSON array to 10 elements: an outer `LIMIT` limits **output rows**, not elements inside an aggregated value.

### Limiting to Top N Elements per Group

When you need the **3 newest orders per customer**, use a window function to rank first:

```sql
WITH ranked AS (
    SELECT
        o.customer_id,
        o.order_id,
        o.ordered_at,
        row_number() OVER (
            PARTITION BY o.customer_id
            ORDER BY o.ordered_at DESC, o.order_id DESC
        ) AS rn
    FROM lesson_aggregates.orders AS o
)
SELECT
    customer_id,
    json_agg(
        json_build_object(
            'order_id', order_id,
            'ordered_at', ordered_at
        )
        ORDER BY ordered_at DESC, order_id DESC
    ) AS latest_orders
FROM ranked
WHERE rn <= 3
GROUP BY customer_id
ORDER BY customer_id;
```

`row_number()` determines **which rows are selected** in each group; `json_agg`'s `ORDER BY` determines **the order of those selected rows** inside the array. The two steps serve distinct purposes.

## 30. Performance and Aggregate Result Size

Building full lists in the database is not always better than letting the application stream individual rows.

### Costs to Consider

- **Per-group sorting:** `ORDER BY` inside an aggregate may require additional sort work.
- **Memory:** a huge group can build a giant string, array, or JSON value; never assume an aggregate streams elements incrementally to the client.
- **Network transfer:** oversized JSON arrays inflate response size and parsing overhead.
- **JOIN row multiplication:** if a join inflates input rows before aggregation, both compute cost and output size grow.
- **Indexes:** can help filter or feed inputs by `order_id`/`line_no`, but do not guarantee the planner skips sorting inside the aggregate.
- **Value size limits:** PostgreSQL data types have size limits, and queries may exhaust memory well before hitting theoretical type limits.

### Measure Before Optimizing

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    order_id,
    jsonb_agg(
        jsonb_build_object(
            'name', product_name,
            'quantity', quantity
        )
        ORDER BY line_no
    ) AS items
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

`EXPLAIN ANALYZE` **executes the query**, so here we use a read-only `SELECT` on the lab table. On real workloads, check timings, sorts, I/O, row counts, and the ratio between input rows and post-aggregation rows.

### Indexes Tied to Query Shape

In the sample table, the primary key `(order_id, line_no)` creates a two-column B-tree index, helpful for queries filtering `order_id` and processing in `line_no` order.

That does not mean `ORDER BY line_no` inside an aggregate is always free via the index; the planner chooses based on statistics, scan types, and preceding operations.

For large datasets, ask:

1. Do we need every element or only top N?
2. Do we really need multi-key sorting?
3. Can we aggregate **after filtering** or **before joining another one-to-many table**?
4. Would paginated rows be better than a huge JSON array?
5. What is the maximum group size, not just the average?

## 31. Nested Aggregates and Element Order Across Levels

When building multi-level JSON arrays, **each collection level needs its own ordering rule**.

For example:

```text
Customer An
  └── orders: by ordered_at ASC, order_id ASC
        └── items: by line_no ASC
```

If you sort items by `line_no` yet forget to sort orders, you might get:

```json
{
  "orders": [
    {"order_id": 1002, "items": [{"line_no": 1}]},
    {"order_id": 1001, "items": [{"line_no": 1}, {"line_no": 2}, {"line_no": 3}]}
  ]
}
```

putting 1002 before 1001, even though **each `items` array is properly sorted**.

Every `jsonb_agg` call needs its own `ORDER BY`:

```sql
-- Item level:
jsonb_agg(item_object ORDER BY line_no)

-- Order level:
jsonb_agg(order_object ORDER BY ordered_at, order_id)
```

These two snippets illustrate **aggregate expressions in their respective query levels**, not a standalone SQL script with pre-existing `item_object`/`order_object` tables.

## 32. SQL Results and Data Types in JDBC

Java applications typically read aggregate results through `ResultSet`. For `string_agg`, read text:

```java
String sql = """
    SELECT
        order_id,
        string_agg(product_name, ', ' ORDER BY line_no)
            AS product_names
    FROM lesson_aggregates.order_items
    GROUP BY order_id
    ORDER BY order_id
    """;

try (PreparedStatement ps = connection.prepareStatement(sql);
     ResultSet rs = ps.executeQuery()) {
    while (rs.next()) {
        long orderId = rs.getLong("order_id");
        String productNames = rs.getString("product_names");
        // Use productNames for display.
    }
}
```

This assumes `connection` is an open JDBC `Connection` inside a method handling `SQLException`. It is an illustrative Java snippet; add proper imports and lifecycle management in real code.

### Reading PostgreSQL Arrays

`array_agg(product_name)` returns PostgreSQL `text[]`, which can be read via JDBC `java.sql.Array`:

```java
String sql = """
    SELECT
        COALESCE(
            array_agg(product_name ORDER BY line_no),
            ARRAY[]::text[]
        ) AS product_names
    FROM lesson_aggregates.order_items
    WHERE order_id = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 1001L);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            java.sql.Array jdbcArray = rs.getArray("product_names");
            if (jdbcArray != null) {
                try {
                    Object raw = jdbcArray.getArray();
                    // With pgJDBC and text[], this typically returns String[].
                    String[] names = (String[]) raw;
                    // Use names in array order.
                } finally {
                    jdbcArray.free();
                }
            }
        }
    }
}
```

Casting to `String[]` illustrates what pgJDBC typically returns for `text[]`. In multi-driver code or with other element types, inspect the runtime type and driver documentation rather than assuming every SQL array casts to `String[]`.

### Reading JSON

For `json_agg`/`jsonb_agg`, pgJDBC can return text or driver-specific objects depending on the API/getter used. A straightforward pattern is:

```java
String sql = """
    SELECT COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'name', product_name,
                'quantity', quantity
            )
            ORDER BY line_no
        ),
        '[]'::jsonb
    ) AS items_json
    FROM lesson_aggregates.order_items
    WHERE order_id = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 1001L);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            String jsonText = rs.getString("items_json");
            // Use a reliable JSON parser (Jackson, etc.)
            // rather than splitting manually on commas or brackets.
        }
    }
}
```

### Distinguishing SQL NULL from Empty Strings

`ResultSet.getString(...)` can return Java `null` when the SQL value is `NULL`. If the SQL uses `COALESCE(..., '')`, the result is an empty Java string rather than null. DTO and API contracts should distinguish those two states cleanly.

### Element Order Is a Data Contract

If a client relies on index 0 being the "first item," the SQL must specify a **deterministic sort key**, not trust index scan order. This matters especially when aggregate results are cached or served across replicas.

## 33. Security and JSON Contracts

`json_agg` makes building API responses convenient, but fields must be chosen explicitly:

```sql
SELECT
    order_id,
    json_agg(
        json_build_object(
            'line_no', line_no,
            'product_name', product_name,
            'quantity', quantity
        )
        ORDER BY line_no
    ) AS public_items
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

Never blindly use `json_agg(i)` to dump all table columns into a public API—tables may contain internal costs, PII, or newly added sensitive columns.

Key principles:

- **Explicitly select keys and values** rather than serializing entire rows.
- **Never expose secrets or sensitive columns** in JSON just because they live on the same row.
- Bound element counts and response sizes.
- Filter by user permissions **before aggregating**, rather than aggregating across all tenants and filtering in application code.
- When joining multiple one-to-many sources, aggregate at the proper entity grain to avoid mixing unrelated data.
- For public JSON interfaces, maintain versioning/contracts and validate number/string/null types.

## 34. Common Mistakes and Misconceptions

**"ORDER BY at the end of SELECT controls the order inside string_agg."** No. That sorts output rows; put `ORDER BY` inside the aggregate call.

**"Because the table has PRIMARY KEY(order_id, line_no), array_agg will automatically follow line_no."** There is no such guarantee unless the aggregate specifies an ordering clause.

**"SELECT * FROM (SELECT ... ORDER BY ...) guarantees outer aggregates keep that order."** Unreliable when the outer query adds processing, especially JOINs or grouping.

**"ORDER BY unit_price alone is always deterministic."** Not when items tie on price; add a unique tie-breaker within the group.

**"DISTINCT keeps the item at the lowest position."** No. `DISTINCT` only removes duplicate values; to keep the first appearance, define the rule with a CTE, window function, or `MIN`.

**"string_agg, array_agg, and json_agg handle NULL the same way."** No. `string_agg` skips null inputs, while `array_agg` and `json_agg` keep nulls as elements.

**"With no inputs, array_agg automatically returns {}."** No. On an empty group, aggregates normally return SQL `NULL` unless wrapped in `COALESCE`.

**"On a LEFT JOIN for an order without items, json_agg always returns []." ** No. The unmatched right-side row can produce `[null]`; use `FILTER` and `COALESCE`.

**"COALESCE(array_agg(...), ARRAY[]) always infers the type."** Do not rely on implicit inference; cast empty arrays explicitly like `ARRAY[]::text[]`.

**"json_agg returns text."** No. It returns `json`; `jsonb_agg` returns `jsonb`, even if a client reads its text representation.

**"jsonb does not preserve array order."** False. JSON arrays preserve element order; what you should not rely on is key order inside JSON objects.

**"DISTINCT with ORDER BY any column is always valid."** No. PostgreSQL restricts `ORDER BY` expressions inside `DISTINCT` aggregates; pre-process in a CTE when sorting by another column.

**"Adding DISTINCT fixes all JOIN-duplicated elements."** No. It can also erase valid rows that happen to share the same value.

**"Whenever you need nested JSON, just write json_agg(json_agg(...))."** No. Multi-level aggregation generally requires CTEs or subqueries to produce grouped sources.

**"Serializing a whole record with json_agg is always API-safe."** No. It can leak newly added or internal columns; select fields explicitly.

**"LIMIT 10 at the end of the query caps the JSON array to 10 elements."** No. It caps output rows, not elements inside an aggregated value.

**"string_agg is a standard CSV exporter."** No. Values may contain delimiters; proper CSV output requires escaping.

**"NULL and an empty list are the exact same state."** No. Decide based on your data contract.

## 35. Workflow for Building Ordered Aggregates in Real Systems

When designing a query returning a list of elements per entity, follow these steps:

1. **Choose the entity for one output row**: order, customer, category, or other group.
2. **Choose the input source**: items table, view, CTE, or joined set.
3. **Check whether JOINs duplicate rows** before aggregating.
4. **Choose the output representation**: text string, typed array, or JSON array/object.
5. **Decide whether to keep or deduplicate duplicates**; if deduplicating, define the element identity key.
6. **Decide how to handle NULLs** and outer-join placeholder rows.
7. **Define the business sort order** and a deterministic tie-breaker.
8. **Place `ORDER BY` inside the aggregate function**, not only at the end of the query.
9. **Use `FILTER`** for per-aggregate conditions when needed.
10. **Use typed `COALESCE`** if the contract requires empty strings or empty arrays.
11. **Limit elements before aggregating** if the response is paginated or top-N.
12. **Measure performance and group sizes**, especially on large datasets.

Diagram:

```text
Data source
      │
      ▼
Filter entity/tenant and access permissions
      │
      ▼
Control JOINs, avoid row multiplication
      │
      ▼
Deduplicate / select top-N if business requires
      │
      ▼
GROUP BY entity
      │
      ▼
string_agg / array_agg / json_agg
        └── ORDER BY business key + tie-breaker
      │
      ▼
FILTER + COALESCE per output contract
      │
      ▼
One row per entity, ordered list
```

This diagram is a mental model. In actual SQL, `FILTER` lives inside the aggregate expression rather than being a separate post-aggregation step, and the optimizer is free to pick different execution plans.

## 36. Practice Exercises

### Exercise 1 — Comparing the Three Functions

For order 1001, write three expressions using `string_agg`, `array_agg`, and `json_agg` on `product_name`, all ordered by `line_no`. Explain their differences in return type and application usage.

### Exercise 2 — Placing ORDER BY Correctly

Why does:

```sql
SELECT order_id, string_agg(product_name, ', ')
FROM lesson_aggregates.order_items
GROUP BY order_id
ORDER BY order_id;
```

**fail to guarantee** product names are concatenated in `line_no` order? Rewrite the query correctly and explain the two roles of `ORDER BY`.

### Exercise 3 — Sorting with a Tie-Breaker

Write a `json_agg` query returning each order's items sorted by `unit_price DESC`. When items share the same price, use `line_no ASC` as a tie-breaker. Explain why `ORDER BY unit_price` alone can be unstable.

### Exercise 4 — Distinguishing NULLs

Compute `string_agg(note, ', ')`, `array_agg(note)`, and `json_agg(note)` for order 1001. Describe the three outputs and the meaning of null elements inside PostgreSQL arrays and JSON arrays.

### Exercise 5 — Orders Without Items

From `orders LEFT JOIN order_items`, write a query returning all orders with an `items` JSON array column. Order 1004 must have **`[]`**, not `[null]` or SQL `NULL`. Use `FILTER` on an item key and `COALESCE`.

### Exercise 6 — DISTINCT Product Names

Produce a list of **unique product names** for order 1001 using both `string_agg` and `array_agg`, sorted by `product_name`. Contrast this output with the list of **all line items** for the same order.

### Exercise 7 — DISTINCT by First Appearance

If each name should appear only once, ordered by its **`MIN(line_no)`**, use a CTE grouping by `(order_id, product_name)` and then `string_agg` in the outer query. Explain why you cannot write `string_agg(DISTINCT product_name, ', ' ORDER BY line_no)`.

### Exercise 8 — Multiple Conditions with FILTER

Write one query returning:

- All product names for the order.
- Names of items where `quantity >= 2`.
- An array of non-null `note` values.

Use three aggregates in the same `GROUP BY order_id` with appropriate `FILTER` clauses.

### Exercise 9 — JSON Objects

Write a `jsonb_agg` query building an array of objects with `line_no`, `name`, `quantity`, and `price`, ordered by `line_no`. Explain the difference between keeping numbers as numeric JSON values versus converting everything to text.

### Exercise 10 — Multi-Level JSON

Design SQL returning **one row per customer** with a JSON array of orders, where each order contains a JSON array of items:

1. Aggregate items by `order_id`.
2. Join the aggregated items to `orders`.
3. Aggregate orders by `customer_id`.
4. Order items by `line_no` and orders by `ordered_at, order_id`.

Explain how to handle customers without orders and orders without items.

### Exercise 11 — JOIN Row Multiplication

Suppose order 1001 has three items and two comments. If you join `order_items` and `order_comments` simultaneously and call `json_agg(product_name)`, how many elements could appear in the array? Propose **aggregating both sources independently before joining** instead of abusing `DISTINCT`.

### Exercise 12 — Using VALUES to Contrast Numbers and Strings

With `VALUES (2), (10), (100)`, compare `string_agg(n::text, ', ' ORDER BY n::text)` and `string_agg(n::text, ', ' ORDER BY n)`. Why does string sorting not match numeric order?

### Exercise 13 — Limiting to 5 Elements

Write a query returning a JSON array of the **5 newest orders across the entire system**. Use a subquery with `ORDER BY ordered_at DESC, order_id DESC LIMIT 5`, then `json_agg` with the same sort order inside. Explain why placing `LIMIT 5` outside the aggregate does not satisfy the requirement.

### Exercise 14 — Top 2 per Customer

Use `row_number() OVER (PARTITION BY customer_id ORDER BY ordered_at DESC, order_id DESC)` to pick the two newest orders for **each customer**. Aggregate them with `json_agg` by `customer_id`. Why are both `row_number` and the aggregate's `ORDER BY` needed?

### Exercise 15 — Arrays and unnest

Build `array_agg(product_name ORDER BY line_no)` for order 1001, then use `unnest(...) WITH ORDINALITY` to expand it back into elements. Add `ORDER BY ordinality` to display elements in their original order.

### Exercise 16 — JSON Arrays and Array Elements

Build `jsonb_agg(jsonb_build_object(...) ORDER BY line_no)` for order 1001, then use `jsonb_array_elements(...) WITH ORDINALITY`. Read the `product` attribute with `->>` and explain why key order inside a JSON object does not substitute for array ordinality.

### Exercise 17 — Safe API Design

An items table gains an `internal_supplier_cost` column. The backend team currently uses `json_agg(i)` to return entire rows to clients. Explain the risk and rewrite it using `json_agg(json_build_object(...))` including only permitted fields.

### Exercise 18 — Choosing the Right Design

For three scenarios:

1. A compact report needing one string of product names.
2. PostgreSQL logic checking membership with `= ANY(...)`.
3. An API returning a list of name/quantity/price objects.

Choose `string_agg`, `array_agg`, or `json_agg`/`jsonb_agg` for each. Explain how to sort elements and handle empty groups in each option.

## Conclusion

**`string_agg`**, **`array_agg`**, and **`json_agg`** all collapse multiple values in a group into a single result, yet serve three different needs: **display strings**, **typed PostgreSQL arrays**, and **JSON arrays for structured data**. `jsonb_agg` is a useful variant when working further with `jsonb`.

The central rule is that **element order must be specified inside the aggregate itself**: `string_agg(value, separator ORDER BY key)`, `array_agg(value ORDER BY key)`, `json_agg(value ORDER BY key)`. `ORDER BY` at the end of the query sorts only **the output rows**; duplicate sort keys need an explicit tie-breaker.

When working with real data, distinguish **`NULL` from empty arrays**, remember that `string_agg` skips null inputs while `array_agg`/`json_agg` keep nulls as elements, and pair **`FILTER` + `COALESCE`** to avoid `[null]` from `LEFT JOIN`. `DISTINCT` deduplicates values but cannot replace choosing the right identity key or fixing row-multiplying joins; when sorting unique values by another key, pre-process in a CTE.

Finally, for multi-level JSON or large row sets, **aggregate bottom-up level by level**, cap elements before building arrays, and measure sort and memory costs. A well-designed aggregate does more than format output nicely—it delivers **a list with the right elements, right order, right type, and a stable data contract** for downstream layers.
