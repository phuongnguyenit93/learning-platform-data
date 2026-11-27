# Indexing JSON, Path Conditions, and Query Selection in Oracle

## 1. Why Does JSON Data Need an Indexing Strategy?

JSON allows a document to contain many attributes with a flexible structure. Two rows in the same table can have different fields, nested objects, or arrays with varying numbers of elements. This flexibility is useful for applications, but it makes querying and indexing different from relational tables with fixed columns.

Example purchase order:

```json
{
  "PONumber": 1600,
  "Reference": "AB-2026-001",
  "Customer": {
    "Name": "Minh Anh",
    "Region": "South"
  },
  "Status": "OPEN",
  "LineItems": [
    {
      "ItemNumber": 1,
      "Part": {"Number": "A100", "Description": "Keyboard"},
      "Quantity": 2,
      "UnitPrice": 45
    },
    {
      "ItemNumber": 2,
      "Part": {"Number": "B200", "Description": "Monitor"},
      "Quantity": 1,
      "UnitPrice": 180
    }
  ]
}
```

A query might look up an order by `PONumber`, filter by `Customer.Region`, check whether any line item has a `Quantity` greater than a threshold, or read each element of `LineItems`.

Without an appropriate index, Oracle may have to read many rows and evaluate JSON expressions on every document. For small tables, the cost may be acceptable. With millions of documents, repeated queries can generate heavy I/O and CPU usage.

Oracle supports several approaches to indexing JSON with different goals:

- **JSON search index:** a general-purpose index for flexible JSON queries, multiple paths, and existence/content conditions.
- **Function-based B-tree index:** a targeted index for a known scalar path, such as order number, status, amount, or date.
- **Virtual column combined with a B-tree index:** exposes a JSON scalar path as a virtual column for reuse in SQL, constraints, and indexes.
- **Standard relational index or composite index:** combines relational columns with JSON expressions when the workload frequently filters by tenant, record type, or date before filtering JSON.

There is no single best index for every query. You should start from the actual predicates, JSON value data types, selectivity, update frequency, and execution plans.

This lesson belongs to the **JSON and XML** chapter and focuses on JSON path expressions, path conditions, `JSON_EXISTS`, `JSON_VALUE`, `JSON_QUERY`, `JSON_TABLE`, JSON search indexes, function-based indexes, query selection, and how to verify index usage by the optimizer.

## 2. Preparing a Table to Store JSON

Oracle can store JSON in textual types such as `VARCHAR2`, `CLOB`, `BLOB`, and supports the native JSON data type in newer releases. SQL/JSON functions work with JSON data according to the storage type and supported version.

### 2.1. JSON Table Stored in CLOB

```sql
CREATE TABLE purchase_orders (
    order_id NUMBER PRIMARY KEY,
    tenant_id NUMBER NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    po_document CLOB
        CONSTRAINT po_document_is_json CHECK (po_document IS JSON)
);
```

`IS JSON` is a condition that checks whether the column content is valid JSON under Oracle semantics. The constraint helps prevent non-JSON data from entering a text column used as a JSON document.

In legacy systems, JSON may be stored using `VARCHAR2` or `BLOB`; you must check size limits, character sets, and how the client transmits data.

### 2.2. Native JSON Type

Oracle Database 21c introduced the native JSON data type in supported configurations. Conceptual example:

```sql
CREATE TABLE native_json_orders (
    order_id NUMBER PRIMARY KEY,
    po_document JSON
);
```

The native JSON type stores data in an Oracle-managed binary format rather than storing plain JSON text. Specific capabilities depend on the database version and service. Do not use native JSON syntax if the target system does not yet support it; CLOB/BLOB with `IS JSON` remains a common pattern in earlier versions.

### 2.3. JSON Is Typed Data, Not Arbitrary Strings

In a JSON document, values have types:
- Number: `1600`, `45.5`.
- String: `"OPEN"`.
- Boolean: `true`, `false`.
- JSON null: `null`.
- Object: `{ ... }`.
- Array: `[ ... ]`.

When querying, preserve the proper type. Compare numbers using SQL `NUMBER` values rather than converting numbers to strings and comparing lexicographically. Likewise, do not use a scalar path if the path can return an object or an array.

## 3. Basic JSON Path Syntax

A SQL/JSON path expression identifies a location or set of values in a JSON document. A path usually starts with `$`, representing the root.

Examples with `po_document`:

| Path | Meaning |
|---|---|
| `$` | The entire document |
| `$.PONumber` | The `PONumber` property at the root |
| `$.Customer.Name` | Customer name inside the `Customer` object |
| `$.Customer.Region` | Customer region |
| `$.LineItems` | The `LineItems` array |
| `$.LineItems[0]` | The first element of the array by path index |
| `$.LineItems[*]` | All elements in the array |
| `$.LineItems[*].Quantity` | The `Quantity` property of each element |
| `$.LineItems[*].Part.Number` | Part number of each line item |

Property names in paths are case-sensitive according to the field names in the JSON document. `$.PONumber` and `$.ponumber` should not be treated as the same path.

### 3.1. Accessing Objects and Arrays

Objects use field names:

```sql
'$.Customer.Region'
```

Arrays use an index or wildcard:

```sql
'$.LineItems[0].Quantity'
'$.LineItems[*].Quantity'
```

`[*]` selects all elements in the array. If the path traverses an object or array that does not match the expected shape, the result depends on the path mode and the semantics of the SQL/JSON function.

### 3.2. Strict and Lax Path Modes

Oracle SQL/JSON paths support two modes:
- `lax`: allows flexible structural conversions while traversing the path; this is the default mode.
- `strict`: requires the path to match the described structure more strictly.

Example:

```sql
JSON_VALUE(po_document, 'strict $.PONumber' RETURNING NUMBER)
```

Use `strict` when the data structure is controlled and you want to detect path mismatches. `lax` is useful when documents have acceptable structural variations. Choose the mode deliberately rather than relying on implicit flexibility if the data requires a strict contract.

### 3.3. Filter Expressions in Paths

Filter expressions use `?()` to filter elements. The `@` symbol represents the current element being evaluated.

Example finding LineItems elements with quantity at least 2:

```sql
'$.LineItems[*]?(@.Quantity >= 2)'
```

Finding elements with part number `"A100"`:

```sql
'$.LineItems[*]?(@.Part.Number == "A100")'
```

Finding line items that have both high quantity and high unit price:

```sql
'$.LineItems[*]?(@.Quantity >= 2 && @.UnitPrice > 100)'
```

Conditions within the same filter are evaluated on the same current array element. This is important when checking multiple attributes of a single line item.

### 3.4. Passing Dynamic Values into Paths with PASSING

Do not concatenate user input strings into a JSON path. Use `PASSING` to pass SQL values safely:

```sql
SELECT order_id
FROM purchase_orders
WHERE JSON_EXISTS(
    po_document,
    '$.LineItems[*]?(@.Quantity >= $minQty)'
    PASSING :min_quantity AS "minQty"
);
```

`:min_quantity` is a SQL bind variable. `$minQty` is the variable referenced in the path; `"minQty"` is the alias assigned in `PASSING`.

Benefits:
- Avoids concatenating untrusted input into the path string.
- Uses bind variables, supporting cursor sharing.
- Preserves the value's data type according to the passed parameter.
- Separates path logic from input data.

### 3.5. Combining Multiple Conditions on an Array

If you need to find orders that have a line item where that same line item satisfies both conditions, write a single filter:

```sql
JSON_EXISTS(
    po_document,
    '$.LineItems[*]?(@.Part.Number == "A100" && @.Quantity >= 2)'
)
```

Do not split into two independent JSON_EXISTS conditions if business logic requires the same element:

```sql
-- These two conditions may match two different LineItems elements.
JSON_EXISTS(po_document, '$.LineItems[*]?(@.Part.Number == "A100")')
AND JSON_EXISTS(po_document, '$.LineItems[*]?(@.Quantity >= 2)')
```

The first condition could match line item 1 while the second matches line item 2. When they must apply to the same item, combine the conditions into one filter expression.

## 4. Choosing a SQL/JSON Function Based on Query Goal

SQL/JSON functions have distinct purposes. Choosing the right function keeps SQL clear and gives the optimizer the best chance to use an appropriate index.

| Function/Condition | Purpose | Return Type |
|---|---|---|
| `JSON_EXISTS` | Check whether a path matches | Boolean condition in SQL |
| `JSON_VALUE` | Extract a single scalar | SQL scalar such as VARCHAR2, NUMBER |
| `JSON_QUERY` | Extract a JSON object or array | JSON fragment |
| `JSON_TABLE` | Project JSON document into relational rows/columns | Table-like row source |
| `JSON_TEXTCONTAINS` | Search text content by path with a JSON search index | Text search condition, depending on version support |

### 4.1. JSON_EXISTS: Checking Existence

Use `JSON_EXISTS` when you only need to know whether a path or condition matches:

```sql
SELECT order_id
FROM purchase_orders
WHERE JSON_EXISTS(po_document, '$.Customer.Region');
```

Find orders with status OPEN:

```sql
SELECT order_id
FROM purchase_orders
WHERE JSON_EXISTS(
    po_document,
    '$.Status?(@ == "OPEN")'
);
```

Find orders with a line item having quantity greater than 5:

```sql
SELECT order_id
FROM purchase_orders
WHERE JSON_EXISTS(
    po_document,
    '$.LineItems[*]?(@.Quantity > 5)'
);
```

`JSON_EXISTS` is well suited for existence predicates, especially when checking nested objects/arrays without needing to project values into the SELECT list.

### 4.2. JSON_VALUE: Extracting Typed Scalars

```sql
SELECT order_id,
       JSON_VALUE(
           po_document,
           '$.PONumber' RETURNING NUMBER
       ) AS po_number
FROM purchase_orders;
```

Filter by purchase order number:

```sql
SELECT order_id
FROM purchase_orders
WHERE JSON_VALUE(
    po_document,
    '$.PONumber' RETURNING NUMBER
) = :po_number;
```

Filter by scalar region:

```sql
SELECT order_id
FROM purchase_orders
WHERE JSON_VALUE(
    po_document,
    '$.Customer.Region' RETURNING VARCHAR2(30)
) = :region;
```

`JSON_VALUE` is intended for a single scalar. If the path points to an object or array, use `JSON_QUERY` or `JSON_TABLE`.

You can specify behavior for missing paths or type mismatches:

```sql
JSON_VALUE(
    po_document,
    '$.PONumber'
    RETURNING NUMBER
    NULL ON EMPTY
    ERROR ON ERROR
)
```

Choose `ERROR ON ERROR` when structurally invalid data must be caught; choose `NULL ON ERROR` when the application contract allows unreadable values to be represented as SQL NULL. Do not let default error behavior become an implicit business condition.

### 4.3. JSON null, Missing Fields, and SQL NULL

Three cases must be distinguished:
- The field does not exist in the document.
- The field exists with the JSON value `null`.
- The SQL expression returns SQL `NULL` due to path/type/error behavior.

`JSON_VALUE` typically returns SQL NULL for JSON null and can return NULL for a non-existent field per `ON EMPTY`/default behavior. Therefore, checking `JSON_VALUE IS NULL` alone may not distinguish the two cases.

If you need to check whether a field exists, use `JSON_EXISTS`:

```sql
SELECT order_id
FROM purchase_orders
WHERE JSON_EXISTS(po_document, '$.Customer.Region');
```

If you need to distinguish a field that exists with JSON null, design predicates and test them explicitly against the `JSON_EXISTS` and `JSON_VALUE` semantics of your Oracle version.

### 4.4. JSON_QUERY: Extracting Objects or Arrays

```sql
SELECT order_id,
       JSON_QUERY(
           po_document,
           '$.Customer'
           RETURNING CLOB
       ) AS customer_json
FROM purchase_orders;
```

Extract the LineItems array:

```sql
SELECT order_id,
       JSON_QUERY(
           po_document,
           '$.LineItems'
           RETURNING CLOB
       ) AS line_items_json
FROM purchase_orders;
```

`JSON_QUERY` is for JSON objects/arrays or fragments; do not use it in place of `JSON_VALUE` to extract a scalar number or string.

### 4.5. JSON_TABLE: Turning JSON into Rows and Columns

When you need to join, aggregate, or process individual array elements with relational SQL, `JSON_TABLE` is usually the natural choice:

```sql
SELECT p.order_id,
       jt.item_number,
       jt.part_number,
       jt.quantity,
       jt.unit_price
FROM purchase_orders p,
     JSON_TABLE(
         p.po_document,
         '$'
         COLUMNS (
             po_number NUMBER PATH '$.PONumber',
             NESTED PATH '$.LineItems[*]'
             COLUMNS (
                 item_number NUMBER PATH '$.ItemNumber',
                 part_number VARCHAR2(50) PATH '$.Part.Number',
                 quantity NUMBER PATH '$.Quantity',
                 unit_price NUMBER PATH '$.UnitPrice'
             )
         )
     ) jt;
```

Each `LineItems` element becomes one row. Columns inside `NESTED PATH` are evaluated relative to the current element.

Use `JSON_TABLE` when:
- You need to turn a JSON array into multiple rows.
- You need to JOIN with relational tables.
- You need GROUP BY, SUM, COUNT, or analytic functions over JSON elements.
- You need to project multiple scalar paths in a single pass over the document.

### 4.6. JSON_TEXTCONTAINS: Searching Text Content

In releases supporting a JSON search index, `JSON_TEXTCONTAINS` can search for tokens/text inside a path's content:

```sql
SELECT order_id
FROM purchase_orders
WHERE JSON_TEXTCONTAINS(
    po_document,
    '$.Customer.Name',
    'Minh'
);
```

This is a text search following Oracle Text semantics, not equivalent to exact scalar comparison with `JSON_VALUE`. Use `JSON_VALUE` for scalar equality/range and `JSON_TEXTCONTAINS` for supported text-search requirements.

## 5. JSON Search Index: General-Purpose Index for Flexible Queries

A JSON search index is a domain index created with `CREATE SEARCH INDEX ... FOR JSON`. It is designed to support many types of JSON queries, especially when the application queries many different paths and creating a separate B-tree index per path is impractical.

### 5.1. Creating a JSON Search Index

```sql
CREATE SEARCH INDEX po_document_search_ix
ON purchase_orders (po_document)
FOR JSON;
```

This index indexes JSON content to accelerate Oracle-supported document queries, such as `JSON_EXISTS` predicates and certain text/path queries.

A JSON search index is suitable when:
- Many different paths are queried.
- Queries contain filters on nested objects/arrays.
- Flexible JSON content search is needed.
- You cannot predict every path the application will query.

### 5.2. Example Using a Search Index with JSON_EXISTS

```sql
SELECT order_id
FROM purchase_orders
WHERE JSON_EXISTS(
    po_document,
    '$.Customer?(@.Region == "South")'
);
```

Or:

```sql
SELECT order_id
FROM purchase_orders
WHERE JSON_EXISTS(
    po_document,
    '$.LineItems[*]?(@.Quantity >= 3 && @.UnitPrice > 50)'
);
```

The optimizer can use the JSON search index if the query shape and predicates qualify. Creating the index does not guarantee every JSON query will use it; the optimizer still relies on cost, statistics, and index capabilities.

### 5.3. Synchronizing a JSON Search Index

The JSON search index is built on the Oracle Text domain index infrastructure. Pay attention to the index synchronization policy after DML.

You can configure synchronization on commit:

```sql
CREATE SEARCH INDEX po_document_search_ix
ON purchase_orders (po_document)
FOR JSON
PARAMETERS ('SYNC (ON COMMIT)');
```

`SYNC (ON COMMIT)` keeps the index synchronized when a transaction commits, but it can increase commit time and DML cost. For write-heavy workloads, teams may choose scheduled or manual synchronization per operational policy.

Manual synchronization, when configured and properly privileged:

```sql
BEGIN
    CTX_DDL.SYNC_INDEX('PO_DOCUMENT_SEARCH_IX');
END;
/
```

The index name passed to `CTX_DDL` is usually specified according to the schema object name. Verify package execution privileges and sync policies in your environment.

### 5.4. Cost of a JSON Search Index

A search index is not free:
- Consumes storage for index structures and token/path metadata.
- DML on JSON can incur index maintenance or sync work.
- Sync on commit can increase commit latency.
- Index builds and syncs consume CPU and I/O.
- When documents are large or updated frequently, evaluate index lag and storage footprint.

Do not create a JSON search index simply because a column contains JSON. Create it when actual query workloads benefit.

## 6. Function-Based B-tree Index for Scalar Paths

If queries frequently filter on a few known scalar paths, a function-based B-tree index is often leaner and more efficient than a general-purpose JSON search index.

### 6.1. Creating an Index on JSON_VALUE

For example, `PONumber` is numeric:

```sql
CREATE INDEX po_number_ix
ON purchase_orders (
    JSON_VALUE(
        po_document,
        '$.PONumber' RETURNING NUMBER
    )
);
```

Query with a matching expression:

```sql
SELECT order_id
FROM purchase_orders
WHERE JSON_VALUE(
    po_document,
    '$.PONumber' RETURNING NUMBER
) = :po_number;
```

Oracle can use the function-based index to look up the scalar value via B-tree instead of reading and evaluating JSON on every row.

### 6.2. Data Types Must Match

If `PONumber` is a number, use `RETURNING NUMBER`:

```sql
JSON_VALUE(po_document, '$.PONumber' RETURNING NUMBER)
```

If `Region` is a string, use an appropriate character type:

```sql
JSON_VALUE(
    po_document,
    '$.Customer.Region' RETURNING VARCHAR2(30)
)
```

Do not index as a number and query as a string. Inconsistent type conversions can alter semantics, cause data errors, or prevent the optimizer from matching the index expression.

### 6.3. Query Expression Should Match Index Expression

For the optimizer to recognize a function-based index, keep these consistent:
- Source JSON column.
- JSON path.
- Return type.
- Error/empty handling options included in the expression.
- Any additional transformations such as `UPPER`, `TRIM`, if present.

Example index:

```sql
CREATE INDEX po_region_ix
ON purchase_orders (
    JSON_VALUE(
        po_document,
        '$.Customer.Region'
        RETURNING VARCHAR2(30)
        NULL ON EMPTY
        NULL ON ERROR
    )
);
```

The query should use the same expression:

```sql
SELECT order_id
FROM purchase_orders
WHERE JSON_VALUE(
    po_document,
    '$.Customer.Region'
    RETURNING VARCHAR2(30)
    NULL ON EMPTY
    NULL ON ERROR
) = :region;
```

If the query uses a different expression—for example casting or wrapping with `UPPER` that the index lacks—Oracle may not use that index. Check the execution plan rather than guessing.

### 6.4. Indexing Dates or Timestamps

If JSON contains dates in a controlled format, you can use `JSON_VALUE` with a version-supported return type and appropriate expression. Be especially careful with formats and time zones.

Another approach is standardizing dates to ISO-8601 in JSON and using a supported SQL/JSON type, or creating a virtual column with explicit conversion. Do not compare arbitrary date strings as if they were DATE values.

## 7. Virtual Columns for JSON Paths

When multiple queries share the same path, a virtual column names the scalar expression and avoids repeating long expressions.

### 7.1. Creating a Virtual Column

```sql
ALTER TABLE purchase_orders ADD (
    po_number GENERATED ALWAYS AS (
        JSON_VALUE(
            po_document,
            '$.PONumber' RETURNING NUMBER
        )
    ) VIRTUAL
);
```

Create a B-tree index:

```sql
CREATE INDEX po_number_virtual_ix
ON purchase_orders (po_number);
```

Query:

```sql
SELECT order_id
FROM purchase_orders
WHERE po_number = :po_number;
```

### 7.2. Virtual Column Combined with Relational Columns

If every query filters by tenant and then by order attribute, create a composite index:

```sql
ALTER TABLE purchase_orders ADD (
    po_region GENERATED ALWAYS AS (
        JSON_VALUE(
            po_document,
            '$.Customer.Region' RETURNING VARCHAR2(30)
        )
    ) VIRTUAL
);

CREATE INDEX po_tenant_region_ix
ON purchase_orders (tenant_id, po_region);
```

Query:

```sql
SELECT order_id
FROM purchase_orders
WHERE tenant_id = :tenant_id
  AND po_region = :region;
```

Column order in a composite B-tree index should match common predicates and filtering selectivity. Equality on the leading column usually lets the index serve subsequent conditions; evaluate actual workloads and execution plans.

### 7.3. Virtual Columns Can Support Constraints

If a JSON path represents a business key that must be unique, consider a unique index on the virtual column:

```sql
CREATE UNIQUE INDEX po_number_unique_ix
ON purchase_orders (po_number);
```

Only do this if `PONumber` truly must be unique across the entire table. If unique per tenant, use a composite unique index `(tenant_id, po_number)`.

You must define semantics for missing fields, JSON null, and invalid data. B-tree indexes handle SQL NULL under their own rules; rows where the key expression evaluates to NULL may not create an entry in a single-column index. If a field must exist, enforce it with proper validation/constraints rather than relying on an index to replace data checks.

## 8. Indexes and Array Paths

Arrays pose a different challenge: a single document can contain multiple values for the same path. For example, `LineItems[*].Part.Number` has multiple part numbers in one document.

### 8.1. When Is a JSON Search Index Appropriate?

If you need to find documents where any array element matches a condition:

```sql
SELECT order_id
FROM purchase_orders
WHERE JSON_EXISTS(
    po_document,
    '$.LineItems[*]?(@.Part.Number == "A100")'
);
```

A JSON search index is typically the general choice to support flexible path/filter queries like this.

### 8.2. Do Not Force Arrays into a Scalar

`JSON_VALUE` is designed to extract one scalar. If a path can match multiple elements, do not assume `JSON_VALUE` will return all values in the array. Use:
- `JSON_EXISTS` if you only need to know whether a matching element exists.
- `JSON_TABLE` if you need to turn every element into a row.
- JSON search index for supported ad hoc path/array queries.

### 8.3. JSON_TABLE for Filtering Array Elements

```sql
SELECT DISTINCT p.order_id
FROM purchase_orders p,
     JSON_TABLE(
         p.po_document,
         '$.LineItems[*]'
         COLUMNS (
             part_number VARCHAR2(50) PATH '$.Part.Number',
             quantity NUMBER PATH '$.Quantity'
         )
     ) li
WHERE li.part_number = :part_number
  AND li.quantity >= :minimum_quantity;
```

This approach is useful when you need to join or aggregate over individual elements. However, `JSON_TABLE` may have to read and project elements across many documents. If the query only checks existence, `JSON_EXISTS` can be simpler and more amenable to a JSON search index.

### 8.4. Multivalue Indexes in Newer Releases

Some newer Oracle releases support multivalue index mechanisms for multiple scalar values extracted from a JSON array. Exact syntax, path limitations, and optimizer usage depend on the release. If a workload primarily filters on a known array path, check the target release documentation on multivalue function-based indexes before choosing a general JSON search index or `JSON_TABLE`.

Do not copy multivalue index syntax from another release without confirming support on the target database.

## 9. Choosing Between JSON_EXISTS, JSON_VALUE, JSON_QUERY, and JSON_TABLE

A common mistake is using one function for every query pattern. Choose based on the result you need.

### 9.1. Only Need to Know If It Matches: JSON_EXISTS

```sql
SELECT order_id
FROM purchase_orders
WHERE JSON_EXISTS(
    po_document,
    '$.Customer?(@.Region == "South")'
);
```

There is no need to extract `Region` into SQL just to test existence/equality.

### 9.2. Need a Scalar for Comparison or Display: JSON_VALUE

```sql
SELECT order_id,
       JSON_VALUE(po_document, '$.PONumber' RETURNING NUMBER)
FROM purchase_orders
WHERE JSON_VALUE(po_document, '$.PONumber' RETURNING NUMBER) >= :min_po;
```

This is the right choice for a known scalar path that can be indexed with a function-based index.

### 9.3. Need a JSON Object or Array: JSON_QUERY

```sql
SELECT JSON_QUERY(
           po_document,
           '$.Customer'
           RETURNING CLOB
       )
FROM purchase_orders;
```

Do not turn an object/array into a scalar string with JSON_VALUE.

### 9.4. Need to Decompose Documents into Relations: JSON_TABLE

```sql
SELECT p.order_id,
       jt.part_number,
       SUM(jt.quantity) AS total_quantity
FROM purchase_orders p,
     JSON_TABLE(
         p.po_document,
         '$.LineItems[*]'
         COLUMNS (
             part_number VARCHAR2(50) PATH '$.Part.Number',
             quantity NUMBER PATH '$.Quantity'
         )
     ) jt
GROUP BY p.order_id, jt.part_number;
```

`JSON_TABLE` enables JOIN, GROUP BY, and analytic SQL over JSON content.

### 9.5. Need Word Search in Text Content: JSON_TEXTCONTAINS

Use when the goal is path-scoped text/token search and a JSON search index supports it. It does not replace scalar equality or range comparisons.

## 10. Combining Relational Columns with JSON Predicates

Many applications use JSON for flexible attributes while keeping relational columns for tenant, processing status, creation timestamp, or primary key.

Example:

```sql
SELECT order_id
FROM purchase_orders
WHERE tenant_id = :tenant_id
  AND created_at >= :from_time
  AND JSON_EXISTS(
      po_document,
      '$.Status?(@ == "OPEN")'
  );
```

Multiple strategies are possible:
- B-tree index on `(tenant_id, created_at)` to narrow the row set first.
- JSON search index on `po_document` to support JSON predicates.
- Function-based index on `JSON_VALUE(... '$.Status' ...)` if status inside JSON is queried frequently.
- Composite index of relational column + virtual column if the workload has a stable pattern.

Not every predicate needs to be served by a single index. The optimizer may pick one index, combine multiple access paths, or perform a full scan depending on cost.

### 10.1. When a JSON Path Is Stable and Selective

For example, JSON status is queried frequently:

```sql
CREATE INDEX po_status_ix
ON purchase_orders (
    JSON_VALUE(po_document, '$.Status' RETURNING VARCHAR2(20))
);
```

Query:

```sql
SELECT order_id
FROM purchase_orders
WHERE JSON_VALUE(
    po_document,
    '$.Status' RETURNING VARCHAR2(20)
) = 'OPEN';
```

If status only has two values and most of the table is OPEN, a B-tree index may not provide the expected benefit. Selectivity and clustering factor influence the optimizer's choice.

### 10.2. When Tenant Is the Leading Predicate

```sql
CREATE INDEX po_tenant_status_ix
ON purchase_orders (
    tenant_id,
    JSON_VALUE(po_document, '$.Status' RETURNING VARCHAR2(20))
);
```

Queries should supply both predicates:

```sql
SELECT order_id
FROM purchase_orders
WHERE tenant_id = :tenant_id
  AND JSON_VALUE(
      po_document,
      '$.Status' RETURNING VARCHAR2(20)
  ) = :status;
```

This works well when the query pattern is repetitive and stable. If paths vary by user, a JSON search index may be more suitable.

## 11. JSON Search Index vs. B-tree Index: Choosing Between Them

| Criterion | JSON Search Index | Function-Based B-tree Index |
|---|---|---|
| Scope | Multiple paths and flexible JSON queries | One specific expression/path |
| Paths | Can support many different paths | Path explicitly declared in expression |
| Scalar equality/range | Can support depending on query and release; check plan | Well suited for known scalar paths |
| Array/filter | Usually suited for JSON_EXISTS and flexible path queries | Requires specialized multivalue index in supported releases |
| Text search | Can support JSON_TEXTCONTAINS | Does not replace full-text search |
| Storage | Can be large due to general path/token indexing | Focused on the key expression |
| DML maintenance | Domain index sync/maintenance cost | B-tree maintenance cost on each DML |
| Design | Less need to create separate indexes per path | Created individually for key queries |
| Best fit | Ad hoc JSON search, many paths | Stable queries on a few scalar paths |

### 11.1. JSON Search Index Does Not Always Win

If the application only filters `PONumber = :x` on a single scalar path, a B-tree function-based index can be smaller and more efficient. A general search index can introduce unnecessary storage and sync overhead.

### 11.2. B-tree Is Not Always Enough

If users can search across many nested paths, arrays, and varying content conditions, creating one B-tree per path becomes hard to manage. A JSON search index can serve this better.

### 11.3. Both Can Be Used Together

A table can have a JSON search index for flexible queries alongside a few B-tree indexes for critical scalar paths. Balance:
- Storage.
- DML throughput.
- Sync duration.
- Rebuild cost.
- Likelihood of the optimizer choosing the access path.

Only create indexes when the workload proves their value.

## 12. Index Expressions, Data Types, and Error Handling

JSON indexes depend closely on how JSON data is converted to SQL scalars.

### 12.1. Numeric Path

```sql
CREATE INDEX po_quantity_ix
ON purchase_orders (
    JSON_VALUE(
        po_document,
        '$.Priority' RETURNING NUMBER
        NULL ON EMPTY
        ERROR ON ERROR
    )
);
```

The query needs a matching expression:

```sql
SELECT order_id
FROM purchase_orders
WHERE JSON_VALUE(
    po_document,
    '$.Priority' RETURNING NUMBER
    NULL ON EMPTY
    ERROR ON ERROR
) >= :min_priority;
```

If a document contains the string `"high"` in a field expected to be numeric, `ERROR ON ERROR` ensures invalid data is caught instead of silently turning into NULL.

### 12.2. Missing Fields and NULL Index Keys

If a path does not exist and the expression returns SQL NULL, a single-column B-tree index does not create an entry for NULL keys. This means a `... IS NULL` query may not be served like a normal equality lookup by a single-column index.

If you need to find rows missing a field, consider:
- A JSON search index with `JSON_EXISTS`/appropriate condition.
- A virtual column combined with a NOT NULL column in a composite index.
- Input validation so mandatory fields always exist.
- A dedicated status or flag column if this query is important.

Do not invent arbitrary NULL-replacement expressions if the replacement value could collide with valid data.

### 12.3. Controlling Malformed Structures

A JSON column may be syntactically valid while violating business schema—for example `Quantity` stored as a string instead of a number. You can:
- Validate in the application before writing.
- Use `JSON_VALUE ... ERROR ON ERROR` in appropriate queries/constraints.
- Use `JSON_TABLE` with explicit column types.
- Use JSON schema validation if supported by your version and architecture.
- Normalize critical fields into relational columns.

### 12.4. Do Not Arbitrarily Wrap Expressions

Example:

```sql
WHERE TO_NUMBER(
    JSON_VALUE(po_document, '$.PONumber')
) = :po_number
```

If the index was created on `JSON_VALUE(... RETURNING NUMBER)`, the expression `TO_NUMBER(JSON_VALUE(...))` may fail to match the index. Prefer a `JSON_VALUE` expression with an explicit return type from the start.

## 13. Path Conditions and Data Types

### 13.1. Comparing Number to Number

```sql
JSON_EXISTS(
    po_document,
    '$.LineItems[*]?(@.Quantity >= 10)'
)
```

The path condition compares numeric values according to JSON typing. If the actual data contains the string `"10"` instead of the number `10`, semantics differ and it may not match as expected.

### 13.2. Comparing Strings

```sql
JSON_EXISTS(
    po_document,
    '$.Status?(@ == "OPEN")'
)
```

Strings in a JSON path use double quotes inside the single-quoted SQL string literal.

### 13.3. Boolean and null

JSON Boolean values are `true` and `false`, not the strings `"true"` or `"false"`. JSON `null` also differs from the string `"null"` and from SQL NULL.

Test predicates against documents containing:
- Missing fields.
- JSON null.
- Values of the expected type.
- Values of the wrong type.
- Empty arrays.
- Nested objects without the field.

### 13.4. Filter Path vs. SQL Predicate

You can use a `JSON_EXISTS` filter:

```sql
WHERE JSON_EXISTS(
    po_document,
    '$.LineItems[*]?(@.Quantity > 3)'
)
```

Or use `JSON_TABLE` to project `Quantity` into SQL and filter:

```sql
SELECT DISTINCT p.order_id
FROM purchase_orders p,
     JSON_TABLE(
         p.po_document,
         '$.LineItems[*]'
         COLUMNS (quantity NUMBER PATH '$.Quantity')
     ) jt
WHERE jt.quantity > 3;
```

Choose a filter path when you only need to test existence. Choose JSON_TABLE when you need element values in JOINs, projections, or aggregations.

## 14. Verifying Whether the Optimizer Uses an Index

Creating an index does not guarantee the optimizer will use it. Oracle chooses access paths based on statistics, cardinality, selectivity, bind values, I/O and CPU costs, and predicate compatibility.

### 14.1. Gathering Statistics

After creating an index or loading test data, gather statistics per DBA policy:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'PURCHASE_ORDERS',
        cascade => TRUE
    );
END;
/
```

In production, follow established statistics policies; do not run broad manual statistics gathering without assessing impact.

### 14.2. Viewing Execution Plans

```sql
EXPLAIN PLAN FOR
SELECT order_id
FROM purchase_orders
WHERE JSON_VALUE(
    po_document,
    '$.PONumber' RETURNING NUMBER
) = 1600;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

To view the actual execution plan and runtime statistics, execute the query with appropriate statistics collection and run:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE'
    )
);
```

### 14.3. What to Look For

In the execution plan, inspect:
- Index range scan or index unique scan on the function-based index.
- Domain index operation for the JSON search index.
- Whether Predicate Information shows the expected JSON expression/path.
- Whether Estimated Rows and Actual Rows diverge significantly.
- Buffer gets and elapsed time.
- Whether a full table scan occurs and whether it is actually expensive.

A full table scan is not always bad. If a query returns most of the table or the table is small, a full scan can be cheaper than index lookups.

### 14.4. Testing with Representative Data

Benchmarks should include:
1. Document counts close to real workloads.
2. Missing/null field ratios and schema variations similar to production.
3. Realistic value distributions and selectivity.
4. Identical bind values or a representative bind set.
5. Measurement of both query latency and DML/index maintenance cost.
6. Verification of correct results under array semantics.
7. Comparison once indexes are synced and statistics are updated.

Do not benchmark a query on a few dozen rows and extrapolate to a table with millions of documents.

## 15. Maintenance Cost of JSON Indexes

Indexes speed up reads but add resource overhead on writes.

### 15.1. B-tree Function-Based Indexes

When a JSON document is inserted or updated, Oracle must evaluate the index expression and update the corresponding key. If a table has multiple JSON path indexes, every DML operation may have to maintain multiple B-trees.

### 15.2. JSON Search Indexes

A search index must maintain path/value structures and synchronize per its policy. The index can increase:
- Storage.
- CPU for indexing and sync.
- I/O.
- Commit latency if using sync on commit.
- Rebuild and operational time.

### 15.3. Choosing Indexes by Read/Write Workload

| Workload | Guidance |
|---|---|
| Read-heavy, JSON rarely changes | Can invest in search index and key scalar B-trees |
| Frequent JSON writes, few ad hoc queries | Limit unnecessary general-purpose indexes |
| Few scalar paths filtered frequently | Function-based B-tree index |
| Many paths, flexible objects/arrays | JSON search index |
| Need array joins and aggregations | JSON_TABLE with appropriate predicates/indexes |
| Tenant + stable scalar path | Composite index or virtual column |

Do not index every JSON field just because the field exists.

## 16. Choosing Queries by Scenario

### 16.1. Looking Up an Order by Scalar Code

Use `JSON_VALUE` and a function-based index:

```sql
CREATE INDEX po_number_ix
ON purchase_orders (
    JSON_VALUE(po_document, '$.PONumber' RETURNING NUMBER)
);

SELECT order_id
FROM purchase_orders
WHERE JSON_VALUE(
    po_document,
    '$.PONumber' RETURNING NUMBER
) = :po_number;
```

### 16.2. Finding Documents Matching a Status

If the status path is important and stable, use a B-tree on JSON_VALUE. If status is just one of many flexibly queried paths, a search index may fit better.

```sql
SELECT order_id
FROM purchase_orders
WHERE JSON_EXISTS(
    po_document,
    '$.Status?(@ == "OPEN")'
);
```

### 16.3. Finding Any Line Item Above a Threshold

```sql
SELECT order_id
FROM purchase_orders
WHERE JSON_EXISTS(
    po_document,
    '$.LineItems[*]?(@.Quantity > $q)'
    PASSING :minimum_quantity AS "q"
);
```

This is an existence predicate over an array. A JSON search index is the general option to evaluate first.

### 16.4. Finding Line Items and Computing Totals

```sql
SELECT p.order_id,
       SUM(jt.quantity * jt.unit_price) AS line_total
FROM purchase_orders p,
     JSON_TABLE(
         p.po_document,
         '$.LineItems[*]'
         COLUMNS (
             quantity NUMBER PATH '$.Quantity',
             unit_price NUMBER PATH '$.UnitPrice'
         )
     ) jt
GROUP BY p.order_id;
```

Use JSON_TABLE because multiple elements must be projected into rows for relational computation.

### 16.5. Fetching the Entire Customer Object

```sql
SELECT order_id,
       JSON_QUERY(po_document, '$.Customer' RETURNING CLOB)
FROM purchase_orders;
```

Use JSON_QUERY because the result is an object.

### 16.6. Searching Words in a Description Field

If full-text/token search is needed and supported by the release:

```sql
SELECT order_id
FROM purchase_orders
WHERE JSON_TEXTCONTAINS(
    po_document,
    '$.Description',
    'wireless'
);
```

Use a JSON search index and verify text-search semantics per Oracle Text configuration.

## 17. Complete Index Design Pattern

Suppose the primary workload is:
- Every query filters on `tenant_id`.
- Some queries filter on `PONumber`.
- Some queries search array items by condition.
- Some queries search text inside descriptions.

You can evaluate this design:

```sql
CREATE INDEX po_tenant_number_ix
ON purchase_orders (
    tenant_id,
    JSON_VALUE(po_document, '$.PONumber' RETURNING NUMBER)
);
```

JSON search index:

```sql
CREATE SEARCH INDEX po_document_search_ix
ON purchase_orders (po_document)
FOR JSON;
```

Scalar query:

```sql
SELECT order_id
FROM purchase_orders
WHERE tenant_id = :tenant_id
  AND JSON_VALUE(
      po_document,
      '$.PONumber' RETURNING NUMBER
  ) = :po_number;
```

Array query:

```sql
SELECT order_id
FROM purchase_orders
WHERE tenant_id = :tenant_id
  AND JSON_EXISTS(
      po_document,
      '$.LineItems[*]?(@.Part.Number == $part)'
      PASSING :part_number AS "part"
  );
```

Text query:

```sql
SELECT order_id
FROM purchase_orders
WHERE tenant_id = :tenant_id
  AND JSON_TEXTCONTAINS(
      po_document,
      '$.Description',
      :search_text
  );
```

This is a guiding pattern, not a universal optimal index formula for every table. Examine how the optimizer combines relational indexes and domain indexes on your specific release, then measure plans and DML overhead.

## 18. Common Mistakes When Writing Paths and Indexes

| Mistake | Consequence | Fix |
|---|---|---|
| Wrong case in field name | Path does not match | Match the exact field name case in JSON |
| Using JSON_VALUE for objects/arrays | Fails to extract desired fragment | Use JSON_QUERY or JSON_TABLE |
| Using JSON_QUERY for scalars | Output does not match target | Use JSON_VALUE |
| Comparing numbers as strings | Wrong ordering/type or mismatch | Use `RETURNING NUMBER` |
| Concatenating input into JSON path | Injection risk and poor cursor sharing | Use PASSING / bind variables |
| Splitting two JSON_EXISTS for the same array element | May match two different elements | Combine conditions into a single filter |
| Wrapping JSON_VALUE in another function | Fails to match expression index | Use identical expression or index the wrapped expression |
| Omitting return type | Ambiguous type conversion | Specify RETURNING explicitly |
| Using `NULL ON ERROR` to hide bad data | Schema errors turn into NULL | Choose ERROR ON ERROR if invalid data must be flagged |
| Creating search index without managing sync | Index can lag behind DML | Choose sync on commit, manual, or scheduled |
| Indexing every path | Increases storage and DML overhead | Index only critical queries |
| Assuming optimizer always uses the index | Wrong performance conclusions | Check DBMS_XPLAN and statistics |
| Using `FETCH FIRST 1 ROW` to hide multiple matches | Masks data/cardinality issues | Define element selection rules or enforce uniqueness |

## 19. Comprehensive Practice Exercises

The examples use a dedicated table in a lab schema. Table/index creation privileges and an appropriate tablespace are required. Search indexes may require relevant Oracle Text privileges. Do not run tests on production.

### Step 1. Create the Table and JSON Data

```sql
CREATE TABLE lab_purchase_orders (
    order_id NUMBER PRIMARY KEY,
    tenant_id NUMBER NOT NULL,
    po_document CLOB
        CHECK (po_document IS JSON)
);
```

Insert documents:

```sql
INSERT INTO lab_purchase_orders (
    order_id,
    tenant_id,
    po_document
)
VALUES (
    1,
    10,
    '{
      "PONumber": 1600,
      "Status": "OPEN",
      "Customer": {"Name": "Minh Anh", "Region": "South"},
      "LineItems": [
        {"ItemNumber": 1, "Part": {"Number": "A100"}, "Quantity": 2, "UnitPrice": 45},
        {"ItemNumber": 2, "Part": {"Number": "B200"}, "Quantity": 1, "UnitPrice": 180}
      ]
    }'
);

INSERT INTO lab_purchase_orders (
    order_id,
    tenant_id,
    po_document
)
VALUES (
    2,
    10,
    '{
      "PONumber": 1601,
      "Status": "CLOSED",
      "Customer": {"Name": "Lan", "Region": "North"},
      "LineItems": [
        {"ItemNumber": 1, "Part": {"Number": "A100"}, "Quantity": 5, "UnitPrice": 40}
      ]
    }'
);

COMMIT;
```

### Step 2. Test JSON_EXISTS

```sql
SELECT order_id
FROM lab_purchase_orders
WHERE JSON_EXISTS(
    po_document,
    '$.Customer?(@.Region == "South")'
);
```

### Step 3. Test JSON_VALUE

```sql
SELECT order_id,
       JSON_VALUE(po_document, '$.PONumber' RETURNING NUMBER) AS po_number
FROM lab_purchase_orders
WHERE JSON_VALUE(po_document, '$.PONumber' RETURNING NUMBER) >= 1600;
```

### Step 4. Create a Function-Based Index

```sql
CREATE INDEX lab_po_number_ix
ON lab_purchase_orders (
    JSON_VALUE(po_document, '$.PONumber' RETURNING NUMBER)
);
```

Re-run the query from Step 3 and inspect the execution plan.

### Step 5. Test a Virtual Column

```sql
ALTER TABLE lab_purchase_orders ADD (
    po_status GENERATED ALWAYS AS (
        JSON_VALUE(
            po_document,
            '$.Status' RETURNING VARCHAR2(20)
        )
    ) VIRTUAL
);

CREATE INDEX lab_po_status_ix
ON lab_purchase_orders (tenant_id, po_status);
```

Query:

```sql
SELECT order_id
FROM lab_purchase_orders
WHERE tenant_id = 10
  AND po_status = 'OPEN';
```

### Step 6. Test JSON_TABLE

```sql
SELECT p.order_id,
       jt.part_number,
       jt.quantity
FROM lab_purchase_orders p,
     JSON_TABLE(
         p.po_document,
         '$.LineItems[*]'
         COLUMNS (
             part_number VARCHAR2(30) PATH '$.Part.Number',
             quantity NUMBER PATH '$.Quantity'
         )
     ) jt;
```

### Step 7. Test JSON_EXISTS on an Array

```sql
SELECT order_id
FROM lab_purchase_orders
WHERE JSON_EXISTS(
    po_document,
    '$.LineItems[*]?(@.Part.Number == "A100" && @.Quantity >= 3)'
);
```

Note that both conditions apply to the same `LineItems` element.

### Step 8. Create a JSON Search Index

```sql
CREATE SEARCH INDEX lab_po_search_ix
ON lab_purchase_orders (po_document)
FOR JSON;
```

If sync on commit is needed and supported by the environment, create the index with the corresponding parameters:

```sql
CREATE SEARCH INDEX lab_po_search_rt_ix
ON lab_purchase_orders (po_document)
FOR JSON
PARAMETERS ('SYNC (ON COMMIT)');
```

Do not create both indexes simultaneously in a lab unless comparing them; the second example illustrates a different sync policy.

### Step 9. Inspect Index Metadata

```sql
SELECT index_name,
       index_type,
       status,
       visibility
FROM user_indexes
WHERE table_name = 'LAB_PURCHASE_ORDERS'
ORDER BY index_name;
```

Check JSON LOB metadata if needed:

```sql
SELECT table_name,
       column_name,
       securefile
FROM user_lobs
WHERE table_name = 'LAB_PURCHASE_ORDERS';
```

### Step 10. View Execution Plan

```sql
EXPLAIN PLAN FOR
SELECT order_id
FROM lab_purchase_orders
WHERE JSON_VALUE(
    po_document,
    '$.PONumber' RETURNING NUMBER
) = 1600;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

### Step 11. Sync the Search Index Manually If Manual Mode Was Chosen

```sql
BEGIN
    CTX_DDL.SYNC_INDEX('LAB_PO_SEARCH_IX');
END;
/
```

Only use this when the index is configured for manual sync and the account has the required privileges.

### Step 12. Clean Up Lab Objects

Only when you are certain these are objects you created and the data is no longer needed:

```sql
DROP INDEX lab_po_search_ix;
DROP INDEX lab_po_number_ix;
DROP INDEX lab_po_status_ix;
DROP TABLE lab_purchase_orders PURGE;
```

If you created the sync-on-commit index in Step 8, drop it before dropping the table:

```sql
DROP INDEX lab_po_search_rt_ix;
```

`DROP TABLE ... PURGE` deletes the table and its data, bypassing the recycle bin. DDL issues an implicit commit. Do not run on business objects or shared data.

## 20. Workflow for Choosing JSON Indexes

When tuning a JSON query, follow this sequence:

1. **Write the real predicate:** identify the path, condition, data type, and whether arrays are involved.
2. **Choose the right function:** `JSON_EXISTS` for existence/filters, `JSON_VALUE` for scalars, `JSON_QUERY` for fragments, `JSON_TABLE` for relational projection.
3. **Determine path stability:** a few stable scalar paths usually suit B-trees; many ad hoc paths usually suit a search index.
4. **Combine relational columns:** check whether tenant, status, timestamp, or partition keys can narrow the dataset first.
5. **Choose the return type:** use `RETURNING NUMBER`/`VARCHAR2` matching the data.
6. **Define error handling:** decide on `NULL ON EMPTY`, `ERROR ON ERROR`, or appropriate behavior.
7. **Create the minimum necessary indexes:** every index increases storage and DML overhead.
8. **Gather statistics:** ensure the optimizer has accurate estimation data.
9. **Inspect the execution plan:** verify the actual access path and predicates.
10. **Benchmark:** measure read latency, DML throughput, storage, and sync overhead on representative data.

### 20.1. Quick Decision Matrix

| Question | Recommended Approach |
|---|---|
| Only need to check if a path exists? | `JSON_EXISTS` |
| Need to compare a stable scalar path? | `JSON_VALUE` + function-based B-tree index |
| Many ad hoc queries across many paths? | JSON search index |
| Need to match conditions inside an array? | `JSON_EXISTS` filter; consider search index |
| Need each array item as a row? | `JSON_TABLE` |
| Need to return an object/array intact? | `JSON_QUERY` |
| Scalar path commonly paired with tenant_id? | Virtual column or composite index |
| Need word search inside text? | JSON search index + `JSON_TEXTCONTAINS` when appropriate |
| Very write-heavy data? | Limit index count, measure maintenance cost |
| Index is not being used? | Check expression, data type, statistics, and plan |

## 21. Self-Check Questions

**Question 1.** What does the JSON path `$` represent?

**Answer:** The root of the JSON document.

**Question 2.** What is `[*]` used for?

**Answer:** Selecting all elements of an array.

**Question 3.** What is the `@` symbol in a filter expression?

**Answer:** The current element being evaluated.

**Question 4.** When should JSON_EXISTS be used?

**Answer:** When you need to check whether a path or condition matches without extracting a scalar into SQL.

**Question 5.** What kind of data does JSON_VALUE return?

**Answer:** A SQL scalar with the specified return type or the default type per Oracle semantics.

**Question 6.** What data is JSON_QUERY suited for?

**Answer:** An object, array, or JSON fragment.

**Question 7.** What does JSON_TABLE do?

**Answer:** Projects JSON data into a row source with SQL columns, useful for JOIN, GROUP BY, and array processing.

**Question 8.** Which workload suits a JSON search index?

**Answer:** Flexible JSON queries across many paths, objects/arrays, and supported search predicates.

**Question 9.** When is a function-based B-tree index suitable?

**Answer:** When you have a stable scalar path frequently filtered by equality or range.

**Question 10.** Why must the RETURNING type be consistent between the index and the query?

**Answer:** Because the expression and data type must match so the optimizer recognizes the expression index and avoids unwanted conversions.

**Question 11.** How does PASSING help?

**Answer:** Passes bind values into JSON paths safely without concatenating input strings into the path.

**Question 12.** Why combine two array conditions into a single filter?

**Answer:** To ensure both conditions match on the same array element.

**Question 13.** Is JSON null the same as SQL NULL?

**Answer:** No. JSON null is a value inside the document; SQL NULL is the null state of a SQL expression. JSON_VALUE can map JSON null to SQL NULL.

**Question 14.** Is a JSON search index always used?

**Answer:** No. The optimizer decides based on query shape, index capabilities, statistics, and cost.

**Question 15.** Why do indexes make DML more expensive?

**Answer:** Oracle must maintain keys or domain index structures when JSON documents are inserted or updated; search indexes also incur sync work.

**Question 16.** When should JSON_TABLE be used instead of JSON_EXISTS?

**Answer:** When you need to extract individual elements as rows to join, project, aggregate, or process relationally.

**Question 17.** Is a full table scan always bad?

**Answer:** No. For small tables or queries returning most of the rows, a full scan can be cheaper than index lookups.

**Question 18.** After creating an index, what should you do to confirm effectiveness?

**Answer:** Gather appropriate statistics, inspect DBMS_XPLAN, measure actual rows/buffers/latency, and check DML overhead.

## 22. Conclusion

JSON index design starts from the predicate shapes and the values queries need to return. `JSON_EXISTS` suits testing existence or path conditions, `JSON_VALUE` extracts typed scalars, `JSON_QUERY` extracts objects/arrays, and `JSON_TABLE` turns documents or arrays into relational rows and columns. Path expressions must use accurate field names, array wildcards, filters, and data types; `PASSING` safely supplies dynamic values without concatenating input strings into paths.

A JSON search index is the general choice for many paths and flexible JSON queries. A function-based B-tree index suits a few stable scalar paths requiring equality or range predicates; virtual columns name and reuse expressions, while composite indexes can combine tenant or relational columns. For arrays, use JSON_EXISTS when only checking existence and JSON_TABLE when processing individual elements; verify release-specific multivalue index support if the workload needs to index multiple scalar values within an array.

Every index increases storage and maintenance overhead. Search indexes require a sync policy; B-trees require expressions and return types that match the query. After creating indexes, gather statistics, check `DBMS_XPLAN`, and benchmark both reads and writes on representative data. Keep only the indexes that benefit your actual workload, rather than indexing every JSON field by habit.
