# JSONPath and Conditional Queries in PostgreSQL Documents

When an application stores orders, configurations, event logs, or external API payloads as `jsonb`, the question is often no longer "how do I read the `status` field?", but rather:

- Does the order **have any item** with `sku` equal to `SKU-RED`?
- Is there **a single item** that is both in the `sale` group and has quantity at least 2?
- Does the customer belong to the VIP tier **and** ship to Hanoi?
- In a document whose structure varies across API versions, is the `shipping.city` field present?
- How do you bind parameters from Java without dangerously concatenating strings into a JSONPath expression?
- Which JSONPath queries have a chance of using a **GIN index**?

PostgreSQL supports the `jsonpath` type along with operators and functions to traverse, filter, and inspect JSON data. **JSONPath** is a language for expressing paths and conditions *inside a JSON document*, not another name for a SQL `WHERE` clause.

This lesson belongs to the **JSON and Arrays** chapter and covers these essential mechanisms:

1. JSONPath structure: `$`, `@`, property access, arrays, wildcards, and filters `? (...)`.
2. Distinguishing the **`@?` operator** from the **`@@` operator**; understanding the pitfall of using a Boolean-returning expression with `@?`.
3. Functions `jsonb_path_exists`, `jsonb_path_match`, `jsonb_path_query`, `jsonb_path_query_first`, and `jsonb_path_query_array`.
4. Compound conditions `&&`, `||`, `!`, numeric/string comparisons, regex, and conditions on the same array element.
5. Handling **missing fields, JSON `null`, SQL `NULL`, mistyped data**, and `lax` / `strict` modes.
6. Variables `$sku` / `$min_qty` in JSONPath, JDBC parameterization, and indexing choices.
7. Hands-on exercises, reading `EXPLAIN`, and common application pitfalls.

> **Version scope:** Core JSONPath operators and functions have been supported since PostgreSQL 12. Newer SQL/JSON features may differ by major version; always consult the documentation for the server version you run.

## 1. Why Use JSONPath When -> and ->> Already Exist?

PostgreSQL has familiar JSON access operators:

```sql
SELECT
    '{"customer":{"id":"C001"},"status":"paid"}'::jsonb
        -> 'customer' AS customer_json,
    '{"customer":{"id":"C001"},"status":"paid"}'::jsonb
        -> 'customer' ->> 'id' AS customer_id;
```

- `->` returns a JSON/JSONB value.
- `->>` returns the text representation of the extracted value.
- `#>` and `#>>` access along a multi-component path array.
- `jsonb_array_elements` expands a JSON array into SQL rows.

Those are great tools for **fixed-path extraction**. However, when asking "is there at least one element in an array satisfying multiple conditions at once?", JSONPath usually states the intent more clearly:

```sql
SELECT
    '{"items":[{"sku":"SKU-RED","qty":2},{"sku":"SKU-BLUE","qty":1}]}'::jsonb
      @? '$.items[*] ? (@.sku == "SKU-RED" && @.qty >= 2)'
    AS has_requested_item;
```

The result is `true` because there is **one element** in `items` that both has the requested SKU and a quantity of at least 2.

JSONPath does not replace SQL. SQL still handles `JOIN`, `GROUP BY`, `ORDER BY`, window functions, transactions, and index design; JSONPath **describes conditions inside each JSON value**.

## 2. Practice Dataset

Examples use a dedicated schema `jsonpath_lab` on a test database. The `INSERT` statements should only be run once after table creation succeeds.

### 2.1. Creating the Table Holding jsonb Documents

```sql
CREATE SCHEMA IF NOT EXISTS jsonpath_lab;

CREATE TABLE jsonpath_lab.orders (
    order_id bigint PRIMARY KEY,
    created_at timestamptz NOT NULL,
    document jsonb NOT NULL,
    CONSTRAINT document_is_object
        CHECK (jsonb_typeof(document) = 'object')
);
```

A `jsonb` column stores documents shaped like:

```json
{
  "status": "paid",
  "customer": {
    "id": "C001",
    "vip": true,
    "email": "ana@example.test"
  },
  "shipping": {
    "city": "Hanoi",
    "country": "VN",
    "express": true
  },
  "items": [
    {"sku": "SKU-RED", "qty": 2, "unit_price": 120, "tags": ["sale", "new"]},
    {"sku": "SKU-BLUE", "qty": 1, "unit_price": 40, "tags": ["clearance"]}
  ],
  "total": 280,
  "coupons": ["WELCOME10"]
}
```

### 2.2. Inserting Six Documents with Diverse Structures

```sql
INSERT INTO jsonpath_lab.orders (order_id, created_at, document)
VALUES
(
    1,
    TIMESTAMPTZ '2026-10-01 09:00:00+00',
    $json$
    {
      "status": "paid",
      "customer": {"id": "C001", "vip": true, "email": "ana@example.test"},
      "shipping": {"city": "Hanoi", "country": "VN", "express": true},
      "items": [
        {"sku": "SKU-RED", "qty": 2, "unit_price": 120, "tags": ["sale", "new"]},
        {"sku": "SKU-BLUE", "qty": 1, "unit_price": 40, "tags": ["clearance"]}
      ],
      "total": 280,
      "coupons": ["WELCOME10"]
    }
    $json$::jsonb
),
(
    2,
    TIMESTAMPTZ '2026-10-02 10:00:00+00',
    $json$
    {
      "status": "pending",
      "customer": {"id": "C002", "vip": false, "email": "binh@example.test"},
      "shipping": {"city": "Ho Chi Minh City", "country": "VN", "express": false},
      "items": [
        {"sku": "SKU-GREEN", "qty": 3, "unit_price": 80, "tags": ["new"]}
      ],
      "total": 240,
      "coupons": []
    }
    $json$::jsonb
),
(
    3,
    TIMESTAMPTZ '2026-10-03 11:00:00+00',
    $json$
    {
      "status": "paid",
      "customer": {"id": "C003", "vip": true, "email": "chi@example.test"},
      "shipping": {"city": "Da Nang", "country": "VN", "express": true},
      "items": [
        {"sku": "SKU-RED", "qty": 1, "unit_price": 120, "tags": ["sale"]},
        {"sku": "SKU-GOLD", "qty": 2, "unit_price": 200, "tags": ["premium"]}
      ],
      "total": 520,
      "coupons": ["VIP20"]
    }
    $json$::jsonb
),
(
    4,
    TIMESTAMPTZ '2026-10-04 12:00:00+00',
    $json$
    {
      "status": "cancelled",
      "customer": {"id": "C004", "vip": false},
      "shipping": null,
      "items": [],
      "total": 0
    }
    $json$::jsonb
),
(
    5,
    TIMESTAMPTZ '2026-10-05 13:00:00+00',
    $json$
    {
      "status": "paid",
      "customer": {"id": "C005", "vip": false},
      "shipping": {"city": "Hanoi", "country": "VN"},
      "items": [
        {"sku": "SKU-BLUE", "qty": "3", "unit_price": "40", "tags": ["sale"]}
      ],
      "total": "120"
    }
    $json$::jsonb
),
(
    6,
    TIMESTAMPTZ '2026-10-06 14:00:00+00',
    $json$
    {
      "status": "pending",
      "customer": {"id": "C006", "vip": null},
      "items": [
        {"sku": "SKU-BLACK", "qty": 1, "unit_price": 300, "tags": []}
      ],
      "total": 300
    }
    $json$::jsonb
);

ANALYZE jsonpath_lab.orders;
```

These differences are **intentional**:

| Order | Characteristics Used for Testing |
| --- | --- |
| **1** | VIP, shipped to Hanoi, `SKU-RED` qty 2, has tag `sale` |
| **2** | Pending, `SKU-GREEN` qty 3 |
| **3** | VIP, `SKU-RED` qty 1 and `SKU-GOLD` qty 2 |
| **4** | `shipping` is JSON `null`, empty `items` array |
| **5** | `qty`, `unit_price`, `total` stored as **strings** instead of numbers |
| **6** | **Missing `shipping` field**, `customer.vip` is JSON `null` |

Record 5 is crucial: `"3"` and `3` are not the same JSON type. Never silently assume externally supplied JSON always follows the schema.

### 2.3. Viewing Data in Readable Form

```sql
SELECT
    order_id,
    jsonb_pretty(document) AS pretty_document
FROM jsonpath_lab.orders
ORDER BY order_id;
```

`jsonb_pretty` returns formatted text for human inspection. It is useful for learning and debugging; applications should process `jsonb` directly rather than parsing pretty-printed text.

## 3. Core Structure of JSONPath

A JSONPath expression has a starting root and traversal steps:

```text
$               the entire root document
$.customer      customer field at the root
$.customer.id   id field inside customer
$.items         items array
$.items[0]      first element (0-based index)
$.items[*]      all direct elements of the array
$.items[*].sku  sku field of every element
```

Common symbols:

| JSONPath | Meaning |
| --- | --- |
| `$` | Root JSON document |
| `@` | Current JSON item inside a filter expression |
| `.key` | Object member access |
| `."special key"` | Member whose name requires double quotes |
| `[0]` | First array element |
| `[*]` | All elements of an array |
| `[last]` | Last element of an array in JSONPath syntax |
| `.*` | Values of object members at the current level |
| `.**` | Traverses nested levels per the path engine |
| `? (condition)` | Retains only items satisfying the filter |
| `==`, `!=`, `>`, `>=`, `<`, `<=` | Comparisons in JSONPath |
| `&&`, `||`, `!` | Logical combine/negate conditions |

Note: JSONPath uses `==` for equality, unlike SQL which uses `=`.

### 3.1. $ and @ Do Not Mean the Same Thing

Example:

```sql
SELECT jsonb_path_query_array(
    '{
       "items": [
         {"sku":"SKU-RED","qty":2},
         {"sku":"SKU-BLUE","qty":1}
       ]
     }'::jsonb,
    '$.items[*] ? (@.qty >= 2)'
) AS selected_items;
```

- `$` refers to the root document.
- `$.items[*]` yields a sequence of **product objects**.
- The filter is applied to each object one by one.
- `@.qty` is the `qty` of **that specific current object**.
- Only objects with `qty >= 2` are kept.

Using `$.items[*].qty` in the wrong place can evaluate conditions across **the entire set of items**, failing to tie the condition to the same element as the target SKU.

### 3.2. Keys with Spaces or Special Characters

When a key cannot be written conveniently as `.identifier`, use JSONPath string member syntax:

```sql
SELECT jsonb_path_query_first(
    '{"delivery address":{"postal code":"100000"}}'::jsonb,
    '$."delivery address"."postal code"'
);
```

Double quotes are syntax **inside JSONPath**, while the outer single quotes are **SQL string literal** syntax.

### 3.3. Arrays Are 0-Based

```sql
SELECT
    jsonb_path_query_first(
        '{"items":["A","B","C"]}'::jsonb,
        '$.items[0]'
    ) AS first_item,
    jsonb_path_query_first(
        '{"items":["A","B","C"]}'::jsonb,
        '$.items[last]'
    ) AS last_item;
```

Expected: JSON strings `"A"` and `"C"`. JSONPath provides `last` for the final array index; do not try to embed SQL syntax like `array_length(...) - 1` inside the path string.

## 4. Filter ? (...) — Finding Elements Matching a Condition

This is the most important pattern in practice:

```text
$.items[*] ? (@.qty >= 2)
│         │ │
│         │ └─ condition applied to the current element
│         └─── filters traversed elements
└───────────── starts from the items array
```

Query finding orders with at least one item of quantity 2 or more:

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '$.items[*] ? (@.qty >= 2)'
ORDER BY order_id;
```

On sample records with properly typed numbers, orders **1, 2, and 3** match. Record 5 stores `qty` as a JSON string, so it is **not automatically treated as JSON number 3**.

### 4.1. Filters Can Apply to Scalar Values

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '$.status ? (@ == "paid")'
ORDER BY order_id;
```

Here `$.status` yields a JSON string value, and `@` represents that string itself. Expected output: orders 1, 3, and 5.

### 4.2. Filters on Multi-Field Objects

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '$.customer ? (@.vip == true)'
ORDER BY order_id;
```

The current item is the `customer` object, so `@.vip` accesses that object's `vip` boolean. Result: orders 1 and 3.

### 4.3. Filtering a JSON Array of Numbers Directly

```sql
SELECT jsonb_path_query_array(
    '{"scores":[55,80,92,37]}'::jsonb,
    '$.scores[*] ? (@ >= 80)'
) AS high_scores;
```

Expected: `[80, 92]`.

There is no need to expand the array into SQL rows if the goal is merely to keep matching values and return a JSON array.

## 5. Distinguishing @? and @@ — The Key Lesson Concept

PostgreSQL has two visually similar operators with different **result semantics**.

| Operator | Left Side | Right Side | Question Asked |
| --- | --- | --- | --- |
| `@?` | `jsonb` | `jsonpath` | **Does the path return at least one item?** |
| `@@` | `jsonb` | Predicate `jsonpath` | **What Boolean does the check expression return?** |

### 5.1. @? Used with a Path Returning Filtered Items

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '$.items[*] ? (@.sku == "SKU-RED")'
ORDER BY order_id;
```

The path iterates through items and retains only those with `SKU-RED`. `@?` returns true if **at least one** item remains after filtering.

Result: orders 1 and 3.

### 5.2. @@ Used with a Boolean Check Expression

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @@ '$.customer.vip == true'
ORDER BY order_id;
```

The right-hand side is a **predicate check expression** yielding a Boolean, rather than a path returning a list of customers.

Result: orders 1 and 3.

Another equivalent way to express the SKU check:

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @@ '$.items[*].sku == "SKU-RED"'
ORDER BY order_id;
```

In PostgreSQL, comparing against a sequence of array items checks whether any item matches under JSONPath semantics. Expected result: orders 1 and 3.

### 5.3. Pitfall: Putting a Predicate Returning false Inside @?

Here is an example that is **wrong in intent**:

```sql
SELECT
    '{"total":100}'::jsonb @? '$.total > 400'
        AS wrong_existence_test;
```

The expression `$.total > 400` is a **predicate check** that evaluates to Boolean `false`. However, `@?` only asks **whether the path returns any item**. A predicate returning a Boolean `false` item is still **one item**!

Therefore, the query above returns **true**, contradicting the intent "total is greater than 400."

Two **correct** ways:

```sql
-- Option 1: @@ checks the Boolean predicate itself.
SELECT '{"total":100}'::jsonb @@ '$.total > 400'
       AS correct_predicate;
```

```sql
-- Option 2: @? finds root items matching the filter.
SELECT '{"total":100}'::jsonb @? '$ ? (@.total > 400)'
       AS correct_filtered_existence;
```

**Easy rule to remember:**

- `@? '$.items[*] ? (@.qty > 2)'` — right: the path yields **filtered** items.
- `@@ '$.items[*].qty > 2'` — right: the JSONPath is a **Boolean predicate**.
- `@? '$.items[*].qty > 2'` — **wrong intent**: the predicate may return `false`, yet `@?` only sees "one result exists."

### 5.4. Using @@ with an Item-Returning Path Instead of a Boolean

Conversely:

```sql
SELECT
    '{"items":[{"sku":"SKU-RED"}]}'::jsonb
        @@ '$.items[*].sku' AS wrong_boolean_test;
```

is not the way to ask "does a SKU exist?". `@@` expects a Boolean predicate result; when the path does not evaluate to a single Boolean, it returns SQL `NULL`.

Better:

```sql
SELECT
    '{"items":[{"sku":"SKU-RED"}]}'::jsonb
        @? '$.items[*].sku' AS has_sku_field;
```

This asks whether at least one `sku` item exists in the path result sequence.

## 6. Conditions on the SAME Array Element

A common business bug scenario: finding orders that have a single item with **both** `SKU-RED` **and** quantity at least 2.

Correct approach:

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '
    $.items[*] ? (
        @.sku == "SKU-RED"
        && @.qty >= 2
    )
'
ORDER BY order_id;
```

The filter sits **after `$.items[*]`**, so both expressions apply to **the same current item object**.

Result: **only order 1**. Order 3 has `SKU-RED` with qty 1, and a different item `SKU-GOLD` with qty 2.

### 6.1. Wrong: Two Independent EXISTS Conditions

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '$.items[*] ? (@.sku == "SKU-RED")'
  AND document @? '$.items[*] ? (@.qty >= 2)'
ORDER BY order_id;
```

These two `@?` checks only require:

1. **Some item** exists with `SKU-RED`.
2. **Some item** exists with `qty >= 2`.

They **do not require it to be the same item**. Hence **order 3** also matches: `SKU-RED` has qty 1, while `SKU-GOLD` has qty 2.

This is the same mistake as splitting a correlated `JOIN`/`EXISTS` condition across two separate subqueries.

### 6.2. Multiple Compound Conditions in the Same Filter

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '
    $.items[*] ? (
        @.qty >= 2
        && @.unit_price >= 100
        && @.tags[*] == "sale"
    )
'
ORDER BY order_id;
```

Meaning: there exists one item with `qty >= 2`, `unit_price >= 100`, and `"sale"` in its `tags`. On the sample dataset, **order 1** matches.

The condition `@.tags[*] == "sale"` is evaluated against the **`tags` array of that exact filtered item**.

### 6.3. Combining OR Inside a Filter

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '
    $.items[*] ? (
        @.sku == "SKU-GOLD" || @.sku == "SKU-BLACK"
    )
'
ORDER BY order_id;
```

Result: orders 3 and 6.

Here `||` and `&&` are **JSONPath logical operators** inside the path string, not SQL string concatenation. Pay close attention to the outer single quotes and the inner double quotes around JSON strings.

### 6.4. Negating a Condition with !

You can write a negated condition inside the filter:

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '
    $.items[*] ? (!(@.sku == "SKU-RED"))
'
ORDER BY order_id;
```

This finds orders that have **at least one item that is not `SKU-RED`**. It **does not mean "contains no `SKU-RED` at all."**

Order 1 still matches because it contains `SKU-BLUE`, even though it also contains `SKU-RED`.

## 7. Checking "No Item Matches" and "Every Item Matches"

Suppose you want orders **containing no `SKU-RED` item**. Place the negation **outside the existence operator**:

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE NOT (
    document @? '$.items[*] ? (@.sku == "SKU-RED")'
)
ORDER BY order_id;
```

Result: orders 2, 4, 5, and 6.

This differs from `$.items[*] ? (!(@.sku == "SKU-RED"))` in the previous section.

### 7.1. Every Item Has qty >= 1

Use logical equivalence:

> Every item satisfies P is equivalent to no item violates P.

Example:

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE NOT (
    document @? '$.items[*] ? (@.qty < 1)'
)
ORDER BY order_id;
```

**However, be careful with mistyped data or missing fields.** If `qty` is a string or missing, `@.qty < 1` may fail to evaluate to true due to error suppression or unknown. In that case, simple negation **does not guarantee every item has a valid numeric `qty >= 1`**.

A more reliable design validates input schemas on write or explicitly checks field presence and types.

### 7.2. Empty Arrays and Vacuous Truth

Order 4 has `items=[]`. The statement "no item violates P" is true on an empty array.

If business logic requires **at least one item** and every item to satisfy the condition, add a non-empty array check:

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '$.items[0]'
  AND NOT (
      document @? '$.items[*] ? (@.qty < 1)'
  )
ORDER BY order_id;
```

On real business data, also verify that `items` is truly an array and `qty` has the right type, avoiding treating a scalar auto-wrapped by `lax` mode as a valid array.

## 8. Querying Deeply Nested Fields and Nested Arrays

JSONPath shines on multi-level object and array structures.

Simple example:

```sql
SELECT jsonb_path_query_array(
    '{
       "departments": [
         {
           "name": "engineering",
           "teams": [
             {"name":"backend","members":[{"name":"An"},{"name":"Binh"}]},
             {"name":"data","members":[{"name":"Chi"}]}
           ]
         }
       ]
     }'::jsonb,
    '$.departments[*].teams[*].members[*].name'
) AS member_names;
```

Returns a JSON array containing the three names `"An"`, `"Binh"`, `"Chi"`.

### 8.1. Filtering at the Right Level

Find the names of members in the `backend` team:

```sql
SELECT jsonb_path_query_array(
    '{
       "teams": [
         {"name":"backend","members":[{"name":"An"},{"name":"Binh"}]},
         {"name":"frontend","members":[{"name":"Dung"}]}
       ]
     }'::jsonb,
    '$.teams[*] ? (@.name == "backend").members[*].name'
) AS backend_members;
```

The path first selects team objects, filters by `@.name`, and only then descends into `members`. Placing the filter after `members[*]` would make `@` refer to a **member object**, making `@.name == "backend"` ask a completely different question.

### 8.2. Wildcard * and Recursive Descent **

`.*` accesses member values of the object at the current level. `.**` traverses across nested levels.

```sql
SELECT jsonb_path_query_array(
    '{
       "a": {"id": 1},
       "b": {"nested": {"id": 2}}
     }'::jsonb,
    'strict $.**.id'
) AS all_ids;
```

This example uses `strict` to avoid duplicate results caused by **lax auto-unwrapping** during recursive descent.

Note that `.**` is handy for exploring heterogeneous data, but it can traverse many nodes and add significant CPU cost. Its indexability also differs from fixed paths; never assume recursive searches are cheap.

## 9. Comparison Operators and JSON Data Types

Common JSONPath comparisons:

| Expression | Check |
| --- | --- |
| `@.qty == 2` | Equal |
| `@.qty != 2` | Not equal |
| `@.qty > 2` | Greater than |
| `@.qty >= 2` | Greater than or equal |
| `@.qty < 2` | Less than |
| `@.qty <= 2` | Less than or equal |
| `@.vip == true` | JSON boolean true |
| `@.status == "paid"` | JSON string |
| `@.shipping == null` | JSON null |

Example:

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @@ '$.total >= 300'
ORDER BY order_id;
```

With properly typed numbers, the result includes orders 3 and 6. Order 5 has `"total":"120"`, which is a string rather than numeric 120.

### 9.1. Do Not Treat "3" and 3 as the Same Type

```sql
SELECT
    jsonb_typeof('3'::jsonb) AS numeric_type,
    jsonb_typeof('"3"'::jsonb) AS string_type;
```

Expected: `number` and `string`.

JSONPath has structural adaptation rules in `lax` mode, yet **you must never use it as a data cleansing or type-validation step**. Numeric comparisons against string data may fail to match, yield unknown, or have errors suppressed depending on the expression.

For financial, monetary, and quantity data:

- Standardize schemas and types on ingestion.
- Use proper constraints and validation.
- Keep numbers as JSON numbers or extract them to explicitly typed SQL columns.
- Never expect JSONPath comparators to coerce strings into numbers automatically.

### 9.2. Arithmetic Expressions

JSONPath supports arithmetic on valid numeric values:

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '
    $.items[*] ? (@.qty * @.unit_price >= 200)
'
ORDER BY order_id;
```

On valid data, this checks the line total of **a single item line**, not the whole order total. For order 5, `qty` and `unit_price` are strings, so they should not be expected to participate in arithmetic without prior normalization.

For complex item-level aggregations, `jsonb_array_elements` combined with SQL `SUM` is more transparent and easier to type-check.

## 10. like_regex: Pattern Matching on Strings

Filters support `like_regex` for text pattern matching:

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '
    $.items[*] ? (@.sku like_regex "^SKU-(RED|BLUE)$")
'
ORDER BY order_id;
```

This selects orders containing at least one `SKU-RED` or `SKU-BLUE` item.

Case-insensitive flags can be enabled, for example:

```sql
SELECT jsonb_path_query_array(
    '{"names":["An","Binh","anna","CHI"]}'::jsonb,
    '$.names[*] ? (@ like_regex "^an" flag "i")'
) AS names_starting_with_an;
```

JSONPath `like_regex` follows SQL/JSON regex rules and PostgreSQL's regex engine interpretation. It is **not 100% identical** to JavaScript regexes, Java `Pattern`, or every feature of PostgreSQL's `~` operator.

### 10.1. Avoid Unconstrained Regexes

Complex regexes over very large documents can be CPU-intensive. Never let untrusted users supply arbitrary JSONPaths or complex patterns against huge tables without access controls, length limits, timeouts, and cost safeguards.

When checking an exact string, use equality:

```sql
WHERE document @? '$.items[*] ? (@.sku == "SKU-RED")'
```

which states intent more clearly and has a better chance of index support.

## 11. JSON null, SQL NULL, and Missing Fields

This is the single most common source of bugs on heterogeneous documents.

Look at three documents:

```json
{"shipping": null}
```

```json
{}
```

```json
{"shipping": {"city": "Hanoi"}}
```

They differ:

1. `shipping` **exists and has value JSON null**.
2. `shipping` **does not exist**.
3. `shipping` **exists and is an object**.

### 11.1. Query Checking Whether a Field Exists

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '$.shipping'
ORDER BY order_id;
```

`@?` checks whether `$.shipping` returns any item. In the sample data, orders **1–5** have the `shipping` key, including order 4 where its value is JSON null. Order 6 lacks the key.

### 11.2. Checking Whether a Field Equals JSON null

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '$.shipping ? (@ == null)'
ORDER BY order_id;
```

In the sample data, order 4 has `shipping` equal to JSON null.

SQL extraction makes the difference clear:

```sql
SELECT
    order_id,
    document ? 'shipping' AS key_exists,
    document -> 'shipping' AS shipping_json,
    jsonb_typeof(document -> 'shipping') AS shipping_json_type,
    document ->> 'shipping' AS shipping_text
FROM jsonpath_lab.orders
ORDER BY order_id;
```

- `document ? 'shipping'` checks the **top-level key** of the object.
- `document -> 'shipping'` returns SQL NULL if missing; if present with JSON null, it returns a **JSONB null value**.
- `jsonb_typeof(...)` returns the string `'null'` for JSON null, but SQL NULL when no JSON value exists.
- `->>` returns SQL NULL for both a missing field and JSON null.

### 11.3. Checking Whether a Nested Field Exists

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '$.shipping.city'
ORDER BY order_id;
```

Expected: orders 1, 2, 3, and 5; order 4 has JSON null at `shipping`, and order 6 lacks `shipping`.

### 11.4. Three-Valued Logic in JSONPath

JSONPath comparisons and filters can produce `true`, `false`, or `unknown` depending on data, types, and expressions. SQL's `@@` operator returns SQL NULL when the predicate does not yield a proper Boolean or when errors are suppressed per operator rules.

In SQL `WHERE`, only rows evaluating to **true** are kept. Both `false` and `NULL` exclude the row, yet they **do not represent the same data state**.

When you need to distinguish "missing field", "null field", "wrong type", and "value out of range", write explicit checks instead of trying to collapse everything into one comparison.

## 12. strict and lax Modes: Heterogeneous JSON Structures

A JSONPath expression runs in one of two modes:

- **`lax`** — default: the engine adapts minor structural mismatches, auto-wraps/unwraps arrays in certain contexts, and silently turns remaining structural errors into empty matches.
- **`strict`** — structure must match the path explicitly; missing members or structural mismatches raise errors.

Example on JSON lacking `shipping`:

```sql
SELECT jsonb_path_query_array(
    '{"status":"pending"}'::jsonb,
    'lax $.shipping.city'
);
```

In `lax` mode, a non-matching path yields an empty sequence, so the result is `[]`.

Try `strict`:

```sql
SELECT jsonb_path_query_array(
    '{"status":"pending"}'::jsonb,
    'strict $.shipping.city'
);
```

Here, accessing a non-existent member raises a structural error in strict mode.

### 12.1. Lax Does Not Mean Data Validation

Suppose an API sometimes sends `items` as an object and sometimes as an array. `lax` may adapt certain traversal steps instead of failing immediately.

While convenient when exploring messy JSON, this **can hide upstream schema violations**.

If the application requires `items` to always be an array, verify explicitly:

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE jsonb_typeof(document -> 'items') = 'array'
ORDER BY order_id;
```

and consider schema constraints on write.

### 12.2. Lax Can Produce Duplicate Results in Recursive Descent

With `.**`, lax mode performs automatic array unwrapping in certain cases. Combining recursive traversal with unwrapping can put the same value into the result sequence multiple times.

When exact nesting depth matters, use explicit paths or `strict` mode where structures match; never assume `.**` returns a deduplicated set of values.

### 12.3. Why Does @? Not Error Even with a strict Path?

`@?` and `@@` **suppress several error categories** such as missing object members/array elements, unexpected JSON types, and numeric/datetime errors.

```sql
SELECT
    '{"status":"paid"}'::jsonb
        @? 'strict $.shipping.city' AS safe_match_test;
```

Even though the path says `strict`, `@?` applies its defined error-suppression behavior, returning `false` instead of throwing an exception.

By contrast:

```sql
SELECT jsonb_path_query(
    '{"status":"paid"}'::jsonb,
    'strict $.shipping.city'
);
```

`jsonb_path_query` **raises an error** on strict structural access failures by default. Do not assume all JSONPath functions and operators share the same error handling.

## 13. The jsonb_path_* Functions: Choosing the Right Output

Alongside `@?` and `@@`, PostgreSQL provides functions for `jsonpath`.

| Function | Meaning | Typical Return Type |
| --- | --- | --- |
| `jsonb_path_exists(target, path [, vars [, silent]])` | Does the path return any item? | `boolean` |
| `jsonb_path_match(target, path [, vars [, silent]])` | Result of a predicate check | `boolean` or SQL NULL |
| `jsonb_path_query(target, path [, vars [, silent]])` | Returns **multiple rows**, one per matching item | `SETOF jsonb` |
| `jsonb_path_query_first(target, path [, vars [, silent]])` | Returns the first matching item | `jsonb` or SQL NULL |
| `jsonb_path_query_array(target, path [, vars [, silent]])` | Collects all matching items into a JSON array | `jsonb` |

The `vars` argument is a `jsonb` object supplying `$name` variables. The `silent` argument is a boolean requesting suppression of supported error classes. These functions do not guarantee that every possible runtime error is ignored.

### 13.1. jsonb_path_exists — Existence Check

```sql
SELECT
    order_id,
    jsonb_path_exists(
        document,
        '$.items[*] ? (@.sku == "SKU-RED")'
    ) AS contains_red
FROM jsonpath_lab.orders
ORDER BY order_id;
```

In basic purpose, this corresponds to `document @? '$.items[*] ? (...)'`.

### 13.2. jsonb_path_match — Boolean Predicate Check

```sql
SELECT
    order_id,
    jsonb_path_match(
        document,
        '$.customer.vip == true'
    ) AS is_vip
FROM jsonpath_lab.orders
ORDER BY order_id;
```

This is the functional counterpart to `@@`. Do not pass a path that merely returns an object into `jsonb_path_match` and expect any non-NULL value to mean Boolean true.

### 13.3. jsonb_path_query — Returning Multiple Rows

```sql
SELECT
    o.order_id,
    item.item_json
FROM jsonpath_lab.orders AS o
CROSS JOIN LATERAL jsonb_path_query(
    o.document,
    '$.items[*] ? (@.qty >= 2)'
) AS item(item_json)
ORDER BY o.order_id;
```

Each matching item becomes **one SQL row**. `CROSS JOIN LATERAL` invokes the function against each order row's document.

If an order has no matching items, it drops out of a **`CROSS JOIN`**. To preserve orders with no matches, consider `LEFT JOIN LATERAL ... ON TRUE`.

### 13.4. jsonb_path_query_array — Collecting into a JSON Array

```sql
SELECT
    order_id,
    jsonb_path_query_array(
        document,
        '$.items[*] ? (@.qty >= 2).sku'
    ) AS matching_skus
FROM jsonpath_lab.orders
ORDER BY order_id;
```

Expected output is a JSON array, e.g., order 1 returns `["SKU-RED"]`, order 3 returns `["SKU-GOLD"]`, and orders with no qualifying items return `[]`.

This function works well when an API wants a list of extracted JSON values per document.

### 13.5. jsonb_path_query_first — First Match

```sql
SELECT
    order_id,
    jsonb_path_query_first(
        document,
        '$.items[*].sku'
    ) AS first_sku_json
FROM jsonpath_lab.orders
ORDER BY order_id;
```

If the path finds no item, the function returns **SQL NULL**. If the first matched item is JSON null, it returns **JSONB null** — two distinct states.

Never treat `jsonb_path_query_first` as a substitute for "cheapest item" or "most recent item." Business ordering requires explicit sorting.

## 14. Extracting Values to SQL for Joining, Aggregating, and Sorting

JSONPath excels at structural selection; SQL remains the right tool for aggregation.

Example expanding SKUs into rows:

```sql
SELECT
    o.order_id,
    sku.sku_json #>> '{}' AS sku
FROM jsonpath_lab.orders AS o
CROSS JOIN LATERAL jsonb_path_query(
    o.document,
    '$.items[*].sku'
) AS sku(sku_json)
ORDER BY o.order_id, sku;
```

Here `#>> '{}'` converts a **JSON scalar value** into text using the JSONB extraction operator. Watch the data type: if the path returns an object or array, text conversion may not suit business needs.

### 14.1. Type-Checked Aggregation in SQL

To sum quantities for orders with valid numeric JSON:

```sql
SELECT
    o.order_id,
    SUM((item.elem ->> 'qty')::integer) AS total_qty
FROM jsonpath_lab.orders AS o
CROSS JOIN LATERAL jsonb_array_elements(
    o.document -> 'items'
) AS item(elem)
WHERE jsonb_typeof(item.elem -> 'qty') = 'number'
GROUP BY o.order_id
ORDER BY o.order_id;
```

This filters items whose `qty` is `number` and casts them to integer in SQL. Even so, **JSON numbers can be fractional or exceed integer range**, so this remains a dataset example rather than complete production validation.

For untrusted external data, validate numeric values first, choose `numeric` or another appropriate SQL type, and define error/missing-value handling.

### 14.2. When to Use JSONPath vs. jsonb_array_elements?

- **Checking existence only:** `@?` or `jsonb_path_exists` is usually concise.
- **Multi-level filtering returning a JSON array:** `jsonb_path_query_array` is helpful.
- **Needing rows for joining or grouping:** `jsonb_path_query` or `jsonb_array_elements`.
- **Extracting a few fixed fields:** `->`, `->>`, `#>>` can be more readable.
- **Business calculations and data constraints:** consider promoting critical fields to explicitly typed SQL columns.

Never assume JSONPath is always faster than other JSON operators; check plans, workloads, and indexes.

## 15. Using $name Variables in JSONPath

A common application bug is concatenating user input directly into a JSONPath string:

```text
'$.items[*] ? (@.sku == "' + userInput + '")'
```

If input contains quotes, escape sequences, or path syntax fragments, the expression can break or change meaning. Use **JSONPath variables** instead of string concatenation.

### 15.1. jsonb_path_exists with vars

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE jsonb_path_exists(
    document,
    '$.items[*] ? (@.sku == $sku)',
    jsonb_build_object('sku', 'SKU-RED')
)
ORDER BY order_id;
```

- `$sku` is a variable inside the JSONPath.
- `jsonb_build_object('sku', 'SKU-RED')` supplies the corresponding JSON string.
- PostgreSQL binds the variable inside the JSONPath engine rather than splicing text into path syntax.

Result: orders 1 and 3.

### 15.2. Multiple Variables in the Same Filter

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE jsonb_path_exists(
    document,
    '$.items[*] ? (@.sku == $sku && @.qty >= $min_qty)',
    jsonb_build_object(
        'sku', 'SKU-RED',
        'min_qty', 2
    )
)
ORDER BY order_id;
```

Result: order 1.

`$min_qty` is passed as a **JSON number**, and `$sku` as a JSON string. Passing `'2'` as text instead of the number `2` can alter comparison behavior.

### 15.3. JSONPath Variables Are Not SQL Placeholders

There are two independent layers:

- **SQL parameter:** `?` in a JDBC prepared statement, bound by the driver for the SQL statement.
- **JSONPath variable:** `$sku` inside a `jsonpath` value, resolved from the `vars` object.

Using both layers together is the cleanest way to handle application input.

### 15.4. silent for Handling Inconsistent Structures

```sql
SELECT
    order_id,
    jsonb_path_exists(
        document,
        'strict $.shipping.city ? (@ == "Hanoi")',
        '{}'::jsonb,
        true
    ) AS hanoi_in_strict_silent_mode
FROM jsonpath_lab.orders
ORDER BY order_id;
```

The fourth argument `true` suppresses eligible JSONPath errors, useful when documents lack `shipping.city`.

**Do not use `silent=true` to mask all data errors.** When the schema requires a field, validate and report ingestion errors according to policy.

## 16. JDBC: Safe Parameterized JSONPath Queries

Java/PgJDBC example combining SQL bind parameters with JSONPath variables:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

public class OrderSearchRepository {
    private final DataSource dataSource;

    public OrderSearchRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public List<Long> findOrdersWithItem(
            String sku, int minimumQuantity) throws SQLException {

        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku is required");
        }
        if (minimumQuantity < 1) {
            throw new IllegalArgumentException("minimumQuantity must be positive");
        }

        String sql = """
            SELECT order_id
            FROM jsonpath_lab.orders
            WHERE jsonb_path_exists(
                document,
                '$.items[*] ? (@.sku == $sku && @.qty >= $min_qty)',
                jsonb_build_object(
                    'sku', CAST(? AS text),
                    'min_qty', CAST(? AS integer)
                )
            )
            ORDER BY order_id
            """;

        List<Long> ids = new ArrayList<>();

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {

            ps.setString(1, sku);
            ps.setInt(2, minimumQuantity);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    ids.add(rs.getLong("order_id"));
                }
            }
        }

        return ids;
    }
}
```

In this SQL:

- The JSONPath string is an **application-controlled constant**.
- `sku` and `minimumQuantity` are **SQL bind parameters**.
- `jsonb_build_object` constructs the object supplying `$sku` and `$min_qty` to JSONPath.
- User input is never concatenated into a path string.
- `try-with-resources` closes the connection, prepared statement, and result set.

### 16.1. Index Caveats with Parameters

The fact that `document @? '...constant...'` can use a GIN index **does not guarantee** that rewriting it as `jsonb_path_exists(document, path, vars)` has identical indexability. Function calls and indexable operators can generate different query plans.

Test with `EXPLAIN` and pick the right strategy. If using a JSONPath literal with constant values for index matching, never construct that literal by concatenating user input.

### 16.2. Prepared Statements and Generic/Custom Plans

PostgreSQL may use custom or generic plans depending on how the application submits queries and runtime conditions. The same parameterized SQL can choose different scans as parameter values vary.

When tuning:

- Record the PostgreSQL version, index definitions, and statistics.
- Use parameter values representative of real workloads.
- Inspect `EXPLAIN (ANALYZE, BUFFERS)` in a realistic environment.
- Do not conclude an index is broken simply because an unselective parameter triggers a Seq Scan.

## 17. GIN Indexes for JSONPath Queries

Without an index, PostgreSQL may evaluate JSONPath across many rows in the table.

GIN is well suited for indexing multiple components of `jsonb`. PostgreSQL provides two common operator classes:

- **`jsonb_ops`:** default, flexible, supports a broad set of operators.
- **`jsonb_path_ops`:** optimized for containment/JSONPath patterns, often smaller and more selective in suited workloads, but does not support every operator that `jsonb_ops` supports.

### 17.1. jsonb_ops Index

```sql
CREATE INDEX idx_orders_document_gin_ops
ON jsonpath_lab.orders
USING GIN (document jsonb_ops);
```

### 17.2. jsonb_path_ops Index

```sql
CREATE INDEX idx_orders_document_gin_path
ON jsonpath_lab.orders
USING GIN (document jsonb_path_ops);
```

In real systems, you **do not normally create both GIN indexes on the same column** just to have more indexes. Each index adds disk usage and DML cost. Because the lab dataset is tiny, the planner may still choose Seq Scan after index creation.

### 17.3. Operator Support Matrix

| Operator on jsonb | `jsonb_ops` | `jsonb_path_ops` |
| --- | :---: | :---: |
| `@>` — containment | ✓ | ✓ |
| `@?` — JSONPath exists | ✓ | ✓ |
| `@@` — JSONPath predicate | ✓ | ✓ |
| `?` — key / top-level array string exists | ✓ | ✕ |
| `?|` — at least one key in list exists | ✓ | ✕ |
| `?&` — all keys in list exist | ✓ | ✕ |

**Read the scope accurately:** this table describes operator class support. Supporting an operator **does not mean every JSONPath expression can be served efficiently by the index**.

### 17.4. JSONPath Forms Easy to Extract into GIN

Example:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '$.items[*] ? (@.sku == "SKU-RED")';
```

GIN can extract conditions of the form **accessor chain == constant** from JSONPath, such as the path to `sku` and value `"SKU-RED"`, to locate candidate rows.

After finding candidates via the index, PostgreSQL still verifies exact JSONPath semantics when necessary. The index does not prove every clause of an arbitrary JSONPath in one lookup.

### 17.5. Range Comparisons Are Not Necessarily Indexed

Example:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '$.items[*] ? (@.qty >= 2)';
```

GIN JSONPath extraction focuses on **constant equality** conditions along paths. A filter consisting solely of `>=` or regex does not automatically become an efficient index scan just because a GIN index exists.

If combined:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '
    $.items[*] ? (@.sku == "SKU-RED" && @.qty >= 2)
';
```

PostgreSQL may use the equality on SKU to narrow candidate rows and then check `qty`, depending on the planner and index. **Never assume every filter condition is pushed down into GIN.**

### 17.6. Recursive Wildcards and Operator Classes

GIN `jsonb_ops` supports extracting certain accessor chains containing `.*` or `.**` in JSONPath. `jsonb_path_ops` does not support these wildcard forms in the corresponding condition extraction.

Therefore, if your workload relies heavily on recursive wildcard paths, do not pick `jsonb_path_ops` just because a single containment benchmark ran faster; evaluate the entire query mix.

### 17.7. jsonb_path_ops and Value-Less Structures

`jsonb_path_ops` stores index entries differently from `jsonb_ops` and has limitations with value-less structures such as empty objects in certain queries. It does not suit every "key exists" or empty-structure search.

Inspect actual predicates and data before choosing an operator class.

## 18. Expression Indexes and B-trees for Simple Conditions

Not every JSON query needs JSONPath and GIN.

If most queries simply filter on `status`:

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document ->> 'status' = 'paid';
```

You can create a B-tree expression index:

```sql
CREATE INDEX idx_orders_status_text
ON jsonpath_lab.orders ((document ->> 'status'));
```

This index targets the **matching SQL expression**. It does not mean PostgreSQL automatically rewrites `document @? '$.status ...'` into the B-tree expression `document ->> 'status'`.

Another design option: if `status` is accessed and filtered constantly, consider making it a typed, constrained SQL column instead of extracting it from JSONB on every query.

### 18.1. Partial Index with an Explicit SQL Predicate

Example:

```sql
CREATE INDEX idx_orders_pending_created
ON jsonpath_lab.orders (created_at)
WHERE document ->> 'status' = 'pending';
```

Query:

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document ->> 'status' = 'pending'
  AND created_at >= TIMESTAMPTZ '2026-10-01 00:00:00+00';
```

can use the partial index when the planner proves the query predicate implies the index predicate.

Rewriting `status = pending` using JSONPath does not guarantee the planner will match it to a partial-index predicate written with `->>`. Never assume visual semantic equivalence without checking the plan.

### 18.2. Containment @> Can Be Simpler Than JSONPath

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @> '{"status":"paid"}'::jsonb
ORDER BY order_id;
```

For simple containment checks, `@>` is both concise and supported by both GIN `jsonb` operator classes.

For arrays of objects:

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @> '{"items":[{"sku":"SKU-RED"}]}'::jsonb
ORDER BY order_id;
```

This is a short way to check structural containment. When you need range checks, regexes, or compound conditions on **the same item**, JSONPath is usually more direct.

## 19. Reading EXPLAIN for JSONPath

After creating indexes and running `ANALYZE`:

```sql
ANALYZE jsonpath_lab.orders;

EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '$.items[*] ? (@.sku == "SKU-RED")';
```

Possible plan nodes include:

- `Seq Scan` with `Filter: (document @? ...)`.
- `Bitmap Index Scan` using GIN.
- `Bitmap Heap Scan` with `Recheck Cond` on JSONPath.
- Other nodes chosen by the planner.

**Do not treat a Seq Scan on a 6-row table as an index bug.** Scanning 6 rows is cheaper than probing a GIN index. To evaluate indexes properly, use a table whose size, SKU distribution, and filter selectivity reflect production workloads.

### 19.1. Index Candidates and Recheck

A GIN index may only identify a set of **candidate** rows based on conditions extracted from JSONPath. Complex parts—such as `qty >= 2` or multiple OR branches—still need re-evaluation.

Thus, seeing `Recheck Cond` or `Filter` in a plan does not mean GIN "isn't working"; it reflects exact verification after candidate lookup.

### 19.2. BUFFERS and Caching

`EXPLAIN (ANALYZE, BUFFERS)` reports shared buffer hits/reads and temp I/O from PostgreSQL's perspective. `shared read` does not prove physical SSD/HDD I/O occurred, as the OS page cache may satisfy reads.

When benchmarking index options:

1. Use the same data and distribution.
2. Run multiple iterations after proper warm-up.
3. Test representative search parameters.
4. Compare p50/p95 latency and I/O, not just planner cost.
5. Observe GIN maintenance impact during `INSERT` / `UPDATE`.

### 19.3. Write Overhead of GIN

GIN indexes speed up reads at a cost:

- Index storage footprint.
- CPU/I/O when new `jsonb` data is written.
- WAL volume and index maintenance work.
- GIN pending list behavior (depending on configuration) and potential latency spikes.

Never index every `jsonb` column out of habit. If queries mostly touch a few fixed fields, smaller expression indexes may fit better.

## 20. How SQL/JSONPath Differs from SQL WHERE

JSONPath executes **within each individual JSON value**. SQL `WHERE` decides **which rows** are kept.

Example:

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE created_at >= TIMESTAMPTZ '2026-10-01 00:00:00+00'
  AND document @? '$.items[*] ? (@.sku == "SKU-RED")';
```

Outside JSONPath:

- `created_at >= ...` is a SQL predicate on a `timestamptz` column.
- `document @? ...` is a SQL Boolean predicate produced by evaluating JSONB contents.
- Inside JSONPath, `? (...)` filters JSON items.

Both can work together so the planner can exploit a B-tree on `created_at` and/or a GIN index on `document` in appropriate plans. The planner is not forced to use both indexes.

### 20.1. Do Not Treat JSONPath as a SQL Subquery

`$` in JSONPath is the **root document**, not a SQL parameter placeholder or a `FROM` alias. `@` in JSONPath is the item being filtered, not the `@?` operator.

PostgreSQL parses a path expression as a **`jsonpath` value**, not dynamic SQL that can select tables, join rows, or mutate data.

## 21. Checking Key Existence: ? and @? Differ

The JSONB `?` operator and the JSONPath `@?` operator operate at different scopes:

```sql
SELECT
    '{"customer":{"email":"a@example.test"}}'::jsonb
        ? 'customer' AS has_top_level_customer_key,
    '{"customer":{"email":"a@example.test"}}'::jsonb
        ? 'email' AS has_top_level_email_key,
    '{"customer":{"email":"a@example.test"}}'::jsonb
        @? '$.customer.email' AS has_nested_email_path;
```

Expected:

- `? 'customer'` returns true, because the key is at the root level.
- `? 'email'` returns false, because `email` is nested inside `customer`.
- `@? '$.customer.email'` returns true, because JSONPath traverses into nested fields.

`?` also checks top-level string elements of a JSONB array. It **does not automatically search keys at arbitrary nesting depths**.

### 21.1. The ?| and ?& Operators

```sql
SELECT
    '{"a":1,"b":2}'::jsonb
        ?| ARRAY['a', 'x'] AS has_any_key,
    '{"a":1,"b":2}'::jsonb
        ?& ARRAY['a', 'b'] AS has_all_keys;
```

- `?|`: at least one key in the list exists.
- `?&`: all keys in the list exist.

These operators belong to `jsonb_ops` in GIN and are not directly supported by `jsonb_path_ops`. Use them when checking top-level keys without needing full JSONPath filters.

## 22. JSONPath Return Values and Safe Representation

Example:

```sql
SELECT
    jsonb_path_query_first(
        '{"total":280}'::jsonb,
        '$.total'
    ) AS total_json;
```

The output is a `jsonb` value representing the number 280, not a SQL `numeric` column inferred from a JSON schema.

To perform SQL arithmetic:

```sql
SELECT
    (document ->> 'total')::numeric AS total_numeric
FROM jsonpath_lab.orders
WHERE jsonb_typeof(document -> 'total') = 'number'
ORDER BY order_id;
```

In the sample dataset, record 5 has `total` as a string and is excluded. Casting still requires checking value ranges (overflow, decimal scale, data structure).

### 22.1. JSONPath Queries Returning Multiple Items

`jsonb_path_query` is a set-returning function that can emit **multiple rows for one document**. If joined with other tables without accounting for item multiplicity, rows can duplicate and distort aggregations.

For example, lateral-joining an order with two items against `jsonb_path_query(document, '$.items[*]')` produces two order rows. Taking `SUM(total)` at the order level without handling the one-to-many expansion would double-count `total`.

Separate clearly:

- Order-level totals: computed on **one row per order**.
- Item-level totals: expand items first, then aggregate per item.
- Joining back to other tables: verify cardinality and join keys.

## 23. JSONPath and Security Requirements

JSON data often arrives from external APIs or user requests; design two layers of protection.

### 23.1. Never Concatenate Input into Path Syntax

Wrong:

```java
String path = "$.items[*] ? (@.sku == \"" + skuFromUser + "\")";
```

This depends on raw input and is vulnerable to quoting/escaping bugs. Replace it with SQL bind parameters + `jsonb_build_object` as shown in the JDBC section.

### 23.2. Do Not Grant Untrusted Users Arbitrary JSON Querying

Even without SQL injection, an unrestricted JSONPath can:

- Deeply traverse with `.**`.
- Run CPU-heavy regexes.
- Produce huge intermediate result sets.
- Scan across many large JSONB rows.
- Return oversized responses.

If your application exposes a dynamic query builder, define a **fixed allowlist of supported filters**, limit path size and complexity, and enforce statement timeouts, pagination, and row limits.

### 23.3. Sensitive Data in JSON

Never dump full JSON documents into logs or APM traces during debugging, especially if they contain emails, phone numbers, tokens, or user data. Keep sample queries using synthetic data like `example.test`, redact sensitive fields in logs, and enforce field-level access controls.

## 24. Schema Validation: JSONPath Does Not Replace CHECK Constraints

A JSONPath query can detect non-conforming documents, but it does not stop new writes from violating the schema.

Example finding rows where `items` is not an array:

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE jsonb_typeof(document -> 'items') IS DISTINCT FROM 'array'
ORDER BY order_id;
```

You can add a simple constraint:

```sql
-- Illustrative only; before applying to real data,
-- confirm every existing document satisfies the condition.
ALTER TABLE jsonpath_lab.orders
ADD CONSTRAINT items_must_be_array
CHECK (jsonb_typeof(document -> 'items') = 'array');
```

**Important note on CHECK:** in SQL, a `CHECK` constraint fails only when the expression evaluates to **false**; SQL NULL is not automatically treated as false. To make the `items` field mandatory, require **both key presence** and type.

Example:

```sql
ALTER TABLE jsonpath_lab.orders
ADD CONSTRAINT items_required
CHECK (
    document ? 'items'
    AND jsonb_typeof(document -> 'items') = 'array'
);
```

In the sample dataset, every order has `items` as an array, so this constraint passes. If real data might omit the field, clean existing rows before adding the constraint.

### 24.1. Extract Critical Columns Out of JSON When Needed

If the application needs:

- `UNIQUE` on order codes.
- Foreign keys to customers.
- Large time-range queries.
- Exact numeric revenue aggregations.
- Complex SKU searches thousands of times per second.

a partially normalized relational design is often more sensible:

```text
orders(order_id, created_at, status, customer_id, total_amount, metadata jsonb)
order_items(order_id, sku, qty, unit_price, tags jsonb)
```

JSONB fits variable metadata and flexible attributes; there is no reason to push core relational invariants into JSON just because JSONPath can query them.

## 25. Common Mistakes When Writing JSONPath

| Misconception | Why It Is Wrong | Fix |
| --- | --- | --- |
| `@? '$.total > 400'` checks `total > 400` | The predicate can return a Boolean `false`, yet `@?` still sees one item | Use `@@ '$.total > 400'` or `@? '$ ? (@.total > 400)'` |
| `@@ '$.items[*].sku'` checks key existence | `@@` requires a Boolean predicate | Use `@? '$.items[*].sku'` |
| Two `EXISTS` checks on `items` ensure the same item | They can be satisfied by **two different items** | Combine both checks inside one filter after `items[*]` |
| `!(@.sku == "RED")` means no `RED` in any item | Negated filter checks each item; another item can still match | Use `NOT (doc @? '$.items[*] ? (@.sku == "RED")')` |
| JSON `"3"` always equals JSON `3` | Different types (string vs. number) | Normalize and validate |
| JSON null is the same as a missing field | One has the key, the other does not | Use `?`, `@? '$.key'`, and `jsonb_typeof` |
| SQL NULL is the same as JSON null | SQL NULL means absent SQL value; JSON null is a JSON value | Inspect extraction and type |
| `lax` guarantees valid input | `lax` can adapt/mask structural mismatches | Validate schema on ingestion |
| `strict` always errors under `@?` | Operators apply error suppression | Understand each operator/function's semantics |
| GIN supports `@?`, so every path uses the index | The index only extracts specific conditions | Read `EXPLAIN` |
| `jsonb_path_ops` supports `?` | That opclass does not support key-existence operators | Use `jsonb_ops` or another index |
| `.**` has the same index support as fixed paths | Path extraction varies by opclass | Check accessors and workload |
| `jsonb_path_exists(...vars)` always uses GIN like `@?` | Function and operator optimization paths can differ | Measure real plans |
| Regex is always better than equality | Regex adds overhead and limits index extraction | Use equality when exact match suffices |
| `jsonb_path_query` always returns one row | Can return zero or many items | Understand `JOIN LATERAL` cardinality |
| JSONPath replaces SQL `JOIN`/`GROUP BY` | It only selects/navigates within JSON | Combine with SQL in its proper role |
| `EXPLAIN ANALYZE` does not execute SQL | It **runs** the query | Be careful with DML and cost |
| More GIN indexes always mean faster queries | Indexes add write, disk, and WAL cost | Choose indexes based on workload |

## 26. Runbook for Diagnosing a Slow or Incorrect JSONPath Query

**Step 1 — Inspect the actual JSON.** Sample representative documents (redacting sensitive fields) and check whether fields exist, are arrays or objects, numbers or strings, JSON null or missing.

**Step 2 — Restate the business condition.** Ask "must one single item satisfy all conditions?" or "must there be at least one item for each condition?" These two are not equivalent.

**Step 3 — Choose `@?` or `@@`.** If the path selects items with `? (...)`, usually use `@?`; if the path is a Boolean predicate, use `@@`.

**Step 4 — Test on a small JSON literal.** Construct passing, failing, empty, missing, and null cases and test the expression directly rather than guessing from huge production outputs.

**Step 5 — Check `lax`/`strict` and suppressed errors.** Never let mistyped data quietly become "no matches" without logging or validation.

**Step 6 — Bind variables with the right types.** For dynamic input, use `vars` and bind parameters; never concatenate JSONPath strings.

**Step 7 — Inspect the query plan.** `EXPLAIN` reveals Seq Scan vs. GIN Bitmap paths; `EXPLAIN ANALYZE` measures runtime when safe. Distinguish indexable equality extraction from range/regex rechecks.

**Step 8 — Evaluate index choices.** Compare `jsonb_ops`, `jsonb_path_ops`, containment `@>`, and B-tree expression indexes; do not create all of them at once.

**Step 9 — Verify cardinality when expanding JSON.** `jsonb_path_query` produces multiple rows; avoid duplicating rows during joins and aggregations.

**Step 10 — Benchmark on a representative workload.** Vary parameters, data sizes, caching, and concurrency; measure p95 latency and DML/GIN maintenance impact.

**Step 11 — Roll out changes with a rollback plan.** Record query/index definitions, PostgreSQL version, test results, and recovery steps in case of regression.

## 27. Practice Exercises

Use the `jsonpath_lab` schema from Section 2. Each exercise asks you to explain **why** an expression behaves as it does, not merely run SQL.

### Exercise 1 — Basic Path Selection

Use `jsonb_path_query_first` to retrieve `customer.id` and `items[0].sku` for order 1. Then try `items[last].sku`.

Why can a path return SQL NULL when no item matches?

### Exercise 2 — Finding a SKU with @?

Write a query finding orders with at least one `items[*].sku` equal to `SKU-RED`. Verify the output against orders 1 and 3.

Explain the roles of `$`, `@`, and `? (...)`.

### Exercise 3 — Boolean Condition with @@

Find orders where `customer.vip == true` using `@@`. Rewrite it using `@?` with a filter on `customer`.

Why should you avoid `@? '$.customer.vip == true'`?

### Exercise 4 — Predicate Pitfall with @?

```sql
SELECT
    '{"total":100}'::jsonb @? '$.total > 400' AS a,
    '{"total":100}'::jsonb @@ '$.total > 400' AS b;
```

Predict `a` and `b` and explain how the two operators handle the JSONPath result differently.

### Exercise 5 — Conditions on the Same Item

Find orders that have **the same item** with `SKU-RED` and `qty >= 2`. Then split it into two independent `@?` conditions.

Why does order 3 appear in the second query but not in the first?

### Exercise 6 — Negating Existence

Write two queries:

1. Has **at least one item that is not `SKU-RED`**.
2. Has **no item** equal to `SKU-RED`.

Test both on order 1 (which contains both `SKU-RED` and `SKU-BLUE`) and explain why the results differ.

### Exercise 7 — Empty Arrays

Order 4 has `items=[]`. Write conditions requiring:

- No item has `qty < 1`.
- There is at least one item.
- All items, when present, have `qty >= 1` as valid JSON numbers.

Why is "no violating item exists" insufficient to guarantee a non-empty array?

### Exercise 8 — JSON null and Missing Fields

For orders 4 and 6, check:

```sql
SELECT
    order_id,
    document ? 'shipping' AS has_key,
    document -> 'shipping' AS shipping_json,
    jsonb_typeof(document -> 'shipping') AS json_type,
    document @? '$.shipping' AS path_exists
FROM jsonpath_lab.orders
WHERE order_id IN (4, 6)
ORDER BY order_id;
```

Which is JSON null, which is SQL NULL, and which is a missing field?

### Exercise 9 — Numeric Type Mismatches

Compare `qty = 3` in order 2 with `qty = "3"` in order 5. Write a query using `jsonb_typeof` to find items whose `qty` field is not a JSON number.

Why should JSONPath comparisons not double as schema validation?

### Exercise 10 — strict and lax

Take a document missing `shipping` and the path `$.shipping.city`. Run `jsonb_path_query_array` in both `lax` and `strict` modes.

Then use `@?` with a `strict` path and explain the operator's error suppression.

### Exercise 11 — Extracting Multiple Items

Use `jsonb_path_query_array` to collect all SKUs of order 1. Use `jsonb_path_query` with `CROSS JOIN LATERAL` to return each SKU as a SQL row.

In a `JOIN` that sums order totals, what must you watch out for regarding the extra rows produced?

### Exercise 12 — Regex

Find items whose SKU starts with `SKU-` and ends with `RED` or `BLUE` using `like_regex`. Try the `i` flag on an array of mixed-case names.

When is equality better than regex?

### Exercise 13 — JSONPath Variables

Write `jsonb_path_exists(document, path, vars)` with variables `$sku = "SKU-RED"` and `$min_qty = 2`.

Why is `vars` safer and more type-explicit than concatenating user input into JSONPath?

### Exercise 14 — GIN Opclasses

Create `jsonb_ops` or `jsonb_path_ops` on `document` in a lab environment. Compare the support matrix for `@>`, `@?`, `@@`, and `?`.

Why cannot `jsonb_path_ops` replace `jsonb_ops` if the application frequently checks keys with `?`?

### Exercise 15 — Equality vs. Range Indexability

Compare these two queries:

```sql
EXPLAIN
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '$.items[*] ? (@.sku == "SKU-RED")';
```

```sql
EXPLAIN
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '$.items[*] ? (@.qty >= 2)';
```

Which condition is easier for GIN equality extraction? Why can you not prove the index helps on a 6-row table?

### Exercise 16 — Expression Index or JSONPath?

Suppose 95% of queries filter by `status` and only 5% filter nested items. Compare:

- A B-tree expression index for `document ->> 'status'`.
- A GIN `jsonb` index if nested workload justifies it.
- Or promoting `status` to a standard SQL column.

Explain the write/disk trade-offs and the benefits of type constraints.

### Exercise 17 — JDBC PreparedStatement

Write a Java method searching orders by SKU and minimum quantity, combining SQL bind parameters with JSONPath `vars`. Never concatenate user input into a JSONPath literal.

If the method could return hundreds of thousands of order IDs, what pagination and load-limiting mechanisms should be added?

### Exercise 18 — Checking All Items Match a Condition

Suppose business rules require **every item to have a numeric `qty >= 1`**, and `items` to be a non-empty array.

Design a validation strategy covering:

- Verifying `items` is an array.
- Verifying at least one element exists.
- Checking every element has a properly typed `qty` field.
- Checking no element has `qty < 1`.
- Handling errors or out-of-range business values.

Why is `NOT (document @? '$.items[*] ? (@.qty < 1)')` alone not enough?

### Exercise 19 — Comparing Containment and JSONPath

Write two equivalent queries to find orders containing `SKU-RED`:

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @> '{"items":[{"sku":"SKU-RED"}]}'::jsonb;
```

and:

```sql
SELECT order_id
FROM jsonpath_lab.orders
WHERE document @? '$.items[*] ? (@.sku == "SKU-RED")';
```

Now add `qty >= 2` on the same item. Which form expresses the range condition more directly?

### Exercise 20 — Production Runbook

A service stores millions of `jsonb` documents where `items` is sometimes an array and sometimes null, and `qty` may be a number or a string. The API needs low-SLA queries by SKU and quantity.

Draft a runbook covering:

1. Auditing schema variants and validation strategy.
2. Choosing `@?` vs. `@@` with the right semantics.
3. Ensuring SKU and `qty` match on **the same item**.
4. Safely binding variables into JSONPath.
5. Comparing `jsonb_ops`, `jsonb_path_ops`, expression indexes, and schema normalization.
6. Using `EXPLAIN` on representative volumes and selectivity.
7. Measuring p95 latency, write overhead, caching, and GIN size.
8. Preparing a controlled rollout and rollback plan.

## 28. Summary

**JSONPath is a language for navigating and filtering inside JSON documents**, especially valuable for nested arrays and objects. In PostgreSQL:

- `$` represents the **root document**, while `@` represents the **item currently being filtered**.
- `$.items[*] ? (@.qty >= 2)` selects items with quantity 2 or more.
- **`@?` checks whether at least one JSONPath result exists**, so use it with filtered paths or field accesses; never pass a bare Boolean predicate directly to `@?`.
- **`@@` evaluates the Boolean result of a predicate check**, such as `document @@ '$.customer.vip == true'`.
- To apply multiple conditions to **the same item**, place them inside **the same filter** after `items[*]`.
- To check "no item satisfies P," negate **the existence operator on the outside**; this differs from "an item exists that does not satisfy P."
- Distinguish **JSON null, SQL NULL, and missing fields**; validate numeric/string types on ingestion.
- Default `lax` mode handles inconsistent structures gracefully but can mask schema bugs; `strict` catches structural errors, while `@?` and `@@` suppress certain error classes.
- Pick from `jsonb_path_exists`, `jsonb_path_match`, `jsonb_path_query`, `jsonb_path_query_first`, and `jsonb_path_query_array` based on the output shape needed.
- Use `vars` and JDBC parameter binding instead of concatenating user input into JSONPath strings.
- GIN `jsonb_ops` and `jsonb_path_ops` can accelerate `@?` and `@@`, especially for extractable equality conditions; **not every JSONPath expression is indexable**.
- For simple, frequently queried fields, `->>` with a B-tree expression index or a typed SQL column is often a better fit.
- Performance must be measured via `EXPLAIN`, real workloads, and write cost, not assumed from the presence of a GIN index.

When designing conditional queries inside JSON, always ask: **which item is the condition applied to, is this an existence or Boolean check, are types enforced, and do edge cases preserve business meaning?** Answering these four questions prevents most JSONPath pitfalls in PostgreSQL.

## 29. PostgreSQL Reference Documentation

- [JSON Functions and Operators — JSONPath, @?, @@, jsonb_path_*](https://www.postgresql.org/docs/current/functions-json.html)
- [JSON Types — jsonb indexing, jsonb_ops and jsonb_path_ops](https://www.postgresql.org/docs/current/datatype-json.html)
- [JSONPath Type — syntax, expressions, methods, and filters](https://www.postgresql.org/docs/current/datatype-json.html#DATATYPE-JSONPATH)
- [GIN Indexes — operator classes and index lookup mechanics](https://www.postgresql.org/docs/current/gin.html)
- [EXPLAIN — reading plans and options](https://www.postgresql.org/docs/current/sql-explain.html)
- [Index Types — choosing B-tree, GIN, and suitable access methods](https://www.postgresql.org/docs/current/indexes-types.html)

The `current` links point to the latest PostgreSQL documentation. Before deploying features in production, check `SHOW server_version;` and consult the documentation for **your exact major version**, especially for newer SQL/JSON functions, GIN operator classes, or planner optimizations.
