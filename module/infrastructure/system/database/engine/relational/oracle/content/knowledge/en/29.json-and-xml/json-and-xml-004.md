# JSON_TABLE and Transforming JSON Structures into Relational Tables

JSON typically represents data as objects, arrays, and scalars. SQL, meanwhile, works with rows, columns, and relational data types. Oracle provides the SQL/JSON function JSON_TABLE to map a JSON document into a virtual set of rows and columns, which you can then SELECT, JOIN, GROUP BY, filter, and load into relational tables.

JSON_TABLE is especially useful when:

- A BLOB/CLOB/VARCHAR2 column contains JSON documents.
- JSON has an array of elements that must be turned into multiple rows.
- Each element contains nested child objects or arrays.
- You need to combine JSON data with customer, product, order, or catalog tables.
- You need to load JSON data into relational tables via INSERT ... SELECT or MERGE.

Core idea: **the row path determines where each JSON row is generated from; COLUMNS and column paths determine which values become SQL columns.** Once JSON_TABLE produces the virtual table, SQL treats it like a normal row source.

## 1. From JSON Document to Relation

Example JSON document:

~~~json
{
  "orderId": 7001,
  "customerId": 101,
  "status": "NEW",
  "items": [
    {"productId": 501, "sku": "KB-01", "quantity": 2, "unitPrice": 125000},
    {"productId": 502, "sku": "MS-02", "quantity": 1, "unitPrice": 250000}
  ]
}
~~~

The JSON has a single object holding order details and an `items` array with two objects. If you need to analyze each line item, the desired relational output might be:

| ORDER_ID | CUSTOMER_ID | STATUS | PRODUCT_ID | SKU | QUANTITY | UNIT_PRICE |
|---:|---:|---|---:|---|---:|---:|
| 7001 | 101 | NEW | 501 | KB-01 | 2 | 125000 |
| 7001 | 101 | NEW | 502 | MS-02 | 1 | 250000 |

The values `orderId`, `customerId`, and `status` are repeated on each item row. This is array flattening: a parent object is paired with each element of its child array.

JSON_TABLE creates a virtual row source for SQL to read. It does not automatically create a physical table or write data to the database.

## 2. Basic Syntax of JSON_TABLE

General syntax:

~~~sql
JSON_TABLE(
    json_expression,
    row_path_expression
    COLUMNS (
        column_definition,
        ...
    )
    error_handling_clause
)
~~~

Where:

- `json_expression`: a column, variable, or expression containing JSON.
- `row_path_expression`: the JSON path identifying the nodes that generate rows.
- `COLUMNS`: declares the SQL columns to extract.
- `column_definition`: column name, data type, path, and error/missing-value handling.
- `error_handling_clause`: error handling at the JSON_TABLE level, if specified.

Example JSON_TABLE for a single object:

~~~sql
SELECT jt.order_id,
       jt.customer_id,
       jt.status
FROM JSON_TABLE(
    '{
       "orderId": 7001,
       "customerId": 101,
       "status": "NEW"
     }',
    '$'
    COLUMNS (
        order_id    NUMBER        PATH '$.orderId',
        customer_id NUMBER        PATH '$.customerId',
        status      VARCHAR2(20)  PATH '$.status'
    )
) jt;
~~~

The result is one row:

| ORDER_ID | CUSTOMER_ID | STATUS |
|---:|---:|---|
| 7001 | 101 | NEW |

The path `'$'` selects the root object. Each column path is evaluated relative to the current node selected by the row path.

## 3. JSON_TABLE Operates with Two Path Layers

JSON_TABLE has two path layers to distinguish:

1. Row path: selects JSON nodes to generate rows.
2. Column path: extracts fields from the current row's node to populate columns.

Example:

~~~sql
SELECT jt.product_id,
       jt.quantity
FROM JSON_TABLE(
    '{
       "items": [
         {"productId": 501, "quantity": 2},
         {"productId": 502, "quantity": 1}
       ]
     }',
    '$.items[*]'
    COLUMNS (
        product_id NUMBER PATH '$.productId',
        quantity   NUMBER PATH '$.quantity'
    )
) jt;
~~~

The row path `$.items[*]` selects each element in the `items` array, so JSON_TABLE generates two rows. The column paths `$.productId` and `$.quantity` read fields from each element under consideration.

If you use row path `'$'` instead of `'$.items[*]'`, JSON_TABLE generates only one row for the root object. In that case, column paths must access the `items` structure appropriately, or use NESTED PATH to unnest the array.

### 3.1 Path '$'

`'$'` represents the root of the JSON document.

Example:

~~~sql
JSON_TABLE(
    payload,
    '$'
    COLUMNS (
        document_id NUMBER PATH '$.id'
    )
)
~~~

### 3.2 Path '$.field'

Accesses an object property:

~~~text
$.customerId
$.address.city
$.metadata.createdBy
~~~

For example, `$.address.city` navigates from the root to the `address` object and retrieves the `city` field.

### 3.3 Path '$.array[*]'

Selects all elements of an array:

~~~text
$.items[*]
$.orders[*]
$.events[*]
~~~

If the array has N matching elements, the row path typically generates N rows.

### 3.4 Specific Index Path

You can select an element by array index:

~~~text
$.items[0]
$.items[1]
~~~

JSON array indexes start at 0. This differs from JSON_TABLE's `FOR ORDINALITY`, which numbers rows starting at 1.

### 3.5 Wildcards and Complex Paths

JSON paths support richer node selection expressions depending on Oracle version and SQL/JSON path syntax. When writing stable APIs, prefer clear paths and avoid overly complex expressions whose types and cardinality are hard to control.

## 4. Declaring SQL Columns in COLUMNS

Each column can declare its name, data type, and JSON path:

~~~sql
COLUMNS (
    order_id    NUMBER         PATH '$.orderId',
    customer_id NUMBER         PATH '$.customerId',
    status      VARCHAR2(20)   PATH '$.status',
    created_at  TIMESTAMP      PATH '$.createdAt'
)
~~~

Declare explicit SQL data types so the result has a clear schema.

### 4.1 NUMBER

Use NUMBER for numeric data:

~~~sql
quantity NUMBER PATH '$.quantity'
~~~

If JSON contains the string `"2"` instead of the number `2`, Oracle may convert it according to target type rules and error handling. Do not rely on implicit conversion if JSON formatting is inconsistent.

### 4.2 VARCHAR2

Use VARCHAR2 for bounded strings:

~~~sql
sku VARCHAR2(40 CHAR) PATH '$.sku'
~~~

Specify length with character semantics if the data contains Unicode. If a string exceeds the column limit, the outcome depends on error handling and may raise a conversion/size error.

### 4.3 DATE and TIMESTAMP

JSON commonly represents timestamps as strings, such as ISO 8601:

~~~json
{"createdAt": "2026-11-14T09:30:00"}
~~~

When converting to DATE/TIMESTAMP, determine the format and timezone rules. JSON_TABLE column projection can convert to SQL types, but for non-standard formats or when timezone matters, extract the string and convert explicitly using TO_TIMESTAMP/TO_TIMESTAMP_TZ with an appropriate format mask.

Example extracting the string:

~~~sql
SELECT jt.created_at_text
FROM JSON_TABLE(
    '{"createdAt":"2026-11-14T09:30:00"}',
    '$'
    COLUMNS (
        created_at_text VARCHAR2(40) PATH '$.createdAt'
    )
) jt;
~~~

Then convert:

~~~sql
TO_TIMESTAMP(
    jt.created_at_text,
    'YYYY-MM-DD"T"HH24:MI:SS'
)
~~~

Do not ignore timezone if the input string includes an offset or timezone region. Use TIMESTAMP WITH TIME ZONE and TO_TIMESTAMP_TZ when multi-timezone instant semantics must be preserved.

### 4.4 Columns Without Explicit PATH

Certain syntax forms allow defaulting the path to the column name, but this easily causes confusion when SQL column names differ from JSON field names or require case sensitivity. In documentation and production code, declaring PATH explicitly keeps the schema readable and predictable.

## 5. FOR ORDINALITY: Generating Row Sequence Numbers

FOR ORDINALITY creates a sequence number column for each row generated by the row path:

~~~sql
SELECT jt.item_no,
       jt.product_id,
       jt.quantity
FROM JSON_TABLE(
    '{
       "items": [
         {"productId": 501, "quantity": 2},
         {"productId": 502, "quantity": 1},
         {"productId": 503, "quantity": 4}
       ]
     }',
    '$.items[*]'
    COLUMNS (
        item_no    FOR ORDINALITY,
        product_id NUMBER PATH '$.productId',
        quantity   NUMBER PATH '$.quantity'
    )
) jt
ORDER BY jt.item_no;
~~~

Result:

| ITEM_NO | PRODUCT_ID | QUANTITY |
|---:|---:|---:|
| 1 | 501 | 2 |
| 2 | 502 | 1 |
| 3 | 503 | 4 |

FOR ORDINALITY is useful when:

- You need to preserve the element's position in the JSON array.
- You need to sort results in their original order.
- You need to write sequence numbers into a relational table.
- You need to correlate errors back to the source element.

Sequence numbering starts at 1 for the corresponding row source. JSON array indexes in paths start at 0, so do not confuse these two conventions.

## 6. NESTED PATH: Expanding Nested Arrays

Real-world JSON often has parent objects and child arrays. NESTED PATH lets you declare columns for child elements directly inside COLUMNS.

Example:

~~~json
{
  "orderId": 7001,
  "customerId": 101,
  "status": "NEW",
  "items": [
    {"productId": 501, "sku": "KB-01", "quantity": 2},
    {"productId": 502, "sku": "MS-02", "quantity": 1}
  ]
}
~~~

Query:

~~~sql
SELECT jt.order_id,
       jt.customer_id,
       jt.status,
       jt.item_no,
       jt.product_id,
       jt.sku,
       jt.quantity
FROM JSON_TABLE(
    '{
       "orderId": 7001,
       "customerId": 101,
       "status": "NEW",
       "items": [
         {"productId": 501, "sku": "KB-01", "quantity": 2},
         {"productId": 502, "sku": "MS-02", "quantity": 1}
       ]
     }',
    '$'
    COLUMNS (
        order_id    NUMBER        PATH '$.orderId',
        customer_id NUMBER        PATH '$.customerId',
        status      VARCHAR2(20)  PATH '$.status',
        NESTED PATH '$.items[*]'
        COLUMNS (
            item_no    FOR ORDINALITY,
            product_id NUMBER        PATH '$.productId',
            sku        VARCHAR2(40)  PATH '$.sku',
            quantity   NUMBER        PATH '$.quantity'
        )
    )
) jt
ORDER BY jt.item_no;
~~~

Parent columns are repeated for each child row. The result has one row per item.

### 6.1 Parent-Child Relationship in JSON_TABLE

JSON_TABLE organizes nested columns into a parent-child relationship:

- The outer row path generates parent rows.
- NESTED PATH generates child rows using a path relative to the parent node.
- Parent columns are paired with child rows.
- An unmatched nested path can still preserve the parent row with NULL child columns under parent-child outer join semantics.

This differs from directly choosing row path `'$.items[*]'` and cross joining JSON_TABLE, where documents with no matching items produce no rows in the row source.

### 6.2 Multiple Levels of NESTED PATH

JSON can be nested to multiple levels:

~~~json
{
  "orderId": 7001,
  "items": [
    {
      "productId": 501,
      "options": [
        {"name": "color", "value": "black"},
        {"name": "layout", "value": "US"}
      ]
    }
  ]
}
~~~

Query:

~~~sql
SELECT jt.order_id,
       jt.product_id,
       jt.option_no,
       jt.option_name,
       jt.option_value
FROM JSON_TABLE(
    '{
       "orderId": 7001,
       "items": [
         {
           "productId": 501,
           "options": [
             {"name": "color", "value": "black"},
             {"name": "layout", "value": "US"}
           ]
         }
       ]
     }',
    '$'
    COLUMNS (
        order_id NUMBER PATH '$.orderId',
        NESTED PATH '$.items[*]'
        COLUMNS (
            product_id NUMBER PATH '$.productId',
            NESTED PATH '$.options[*]'
            COLUMNS (
                option_no    FOR ORDINALITY,
                option_name  VARCHAR2(40) PATH '$.name',
                option_value VARCHAR2(100) PATH '$.value'
            )
        )
    )
) jt
ORDER BY jt.option_no;
~~~

The deepest columns describe each option. `order_id` and `product_id` are carried down to their corresponding child rows.

### 6.3 Multiple Sibling NESTED PATHs Are Not a Cartesian Product

A common pitfall: sibling NESTED PATH clauses at the same level inside a COLUMNS clause are combined using Oracle's union join semantics, not by multiplying every element of two arrays into a Cartesian product.

For example, if JSON has `tags` and `notes` arrays, two sibling nested paths generate rows for their respective branches, with columns from the other branch set to NULL on rows not belonging to that branch. If you need every tag paired with every note, write separate joins/JSON_TABLE calls explicitly.

Do not assume two sibling arrays will produce N × M rows. Verify the result structure and use separate queries when business logic requires a Cartesian combination.

## 7. JSON_TABLE on a Relational Table Column

In practice, JSON is typically stored in a table column:

~~~sql
CREATE TABLE order_documents (
    document_id NUMBER PRIMARY KEY,
    payload     CLOB CHECK (payload IS JSON)
);
~~~

You can combine each document with JSON_TABLE:

~~~sql
SELECT d.document_id,
       jt.order_id,
       jt.customer_id,
       jt.status
FROM order_documents d,
     JSON_TABLE(
         d.payload,
         '$'
         COLUMNS (
             order_id    NUMBER PATH '$.orderId',
             customer_id NUMBER PATH '$.customerId',
             status      VARCHAR2(20) PATH '$.status'
         )
     ) jt;
~~~

JSON_TABLE can reference columns from a preceding row source in the FROM clause. This is a common correlated row source pattern.

### 7.1 One Row per Document

With row path `'$'`, a valid object typically produces one row. If `payload` is NULL or the JSON lacks the matching structure, the result depends on error/empty handling and data types.

### 7.2 Multiple Rows per Document

If the row path is `'$.items[*]'`, each item can generate a row:

~~~sql
SELECT d.document_id,
       jt.item_no,
       jt.product_id,
       jt.quantity
FROM order_documents d,
     JSON_TABLE(
         d.payload,
         '$.items[*]'
         COLUMNS (
             item_no    FOR ORDINALITY,
             product_id NUMBER PATH '$.productId',
             quantity   NUMBER PATH '$.quantity'
         )
     ) jt;
~~~

A document with 5 matching items produces 5 rows. A document with no matching items produces no rows in this row source; when using a comma join/cross join, that document does not appear in the output.

### 7.3 Preserving Documents Even When the Array Is Empty

If you need to retain the parent document even when it has no child elements, use the root row path and NESTED PATH:

~~~sql
SELECT d.document_id,
       jt.order_id,
       jt.product_id,
       jt.quantity
FROM order_documents d,
     JSON_TABLE(
         d.payload,
         '$'
         COLUMNS (
             order_id NUMBER PATH '$.orderId',
             NESTED PATH '$.items[*]'
             COLUMNS (
                 product_id NUMBER PATH '$.productId',
                 quantity   NUMBER PATH '$.quantity'
             )
         )
     ) jt;
~~~

With an empty or unmatched array, the root row can still be preserved with NULL child columns under parent-child outer join semantics.

## 8. Transforming JSON into Multiple Relational Tables

A document may contain a parent entity and multiple child entities. You do not have to put everything into a single flat table.

Example JSON:

~~~json
{
  "orderId": 7001,
  "customerId": 101,
  "createdAt": "2026-11-14T09:30:00",
  "items": [
    {"lineNo": 1, "productId": 501, "quantity": 2, "unitPrice": 125000},
    {"lineNo": 2, "productId": 502, "quantity": 1, "unitPrice": 250000}
  ]
}
~~~

Target tables:

~~~sql
CREATE TABLE orders (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    created_at TIMESTAMP
);

CREATE TABLE order_items (
    order_id NUMBER NOT NULL,
    line_no NUMBER NOT NULL,
    product_id NUMBER NOT NULL,
    quantity NUMBER(12,3) NOT NULL,
    unit_price NUMBER(14,2) NOT NULL,
    CONSTRAINT pk_order_items PRIMARY KEY(order_id, line_no)
);
~~~

Loading header:

~~~sql
INSERT INTO orders(order_id, customer_id, created_at)
SELECT jt.order_id,
       jt.customer_id,
       TO_TIMESTAMP(
           jt.created_at_text,
           'YYYY-MM-DD"T"HH24:MI:SS'
       )
FROM order_documents d,
     JSON_TABLE(
         d.payload,
         '$'
         COLUMNS (
             order_id        NUMBER PATH '$.orderId',
             customer_id     NUMBER PATH '$.customerId',
             created_at_text VARCHAR2(40) PATH '$.createdAt'
         )
     ) jt
WHERE d.document_id = :document_id;
~~~

Loading details:

~~~sql
INSERT INTO order_items(
    order_id,
    line_no,
    product_id,
    quantity,
    unit_price
)
SELECT jt.order_id,
       jt.line_no,
       jt.product_id,
       jt.quantity,
       jt.unit_price
FROM order_documents d,
     JSON_TABLE(
         d.payload,
         '$'
         COLUMNS (
             order_id NUMBER PATH '$.orderId',
             NESTED PATH '$.items[*]'
             COLUMNS (
                 line_no    NUMBER PATH '$.lineNo',
                 product_id NUMBER PATH '$.productId',
                 quantity   NUMBER PATH '$.quantity',
                 unit_price NUMBER PATH '$.unitPrice'
             )
         )
     ) jt
WHERE d.document_id = :document_id;
~~~

Both INSERT operations must run in the same transaction if header and details form a single business unit. The caller or higher-level procedure decides when to COMMIT after both succeed.

## 9. Combining JSON_TABLE with JOIN

Once JSON_TABLE produces a row source, you can join it with relational tables:

~~~sql
SELECT jt.order_id,
       jt.product_id,
       p.product_name,
       jt.quantity,
       p.category_id
FROM order_documents d,
     JSON_TABLE(
         d.payload,
         '$.items[*]'
         COLUMNS (
             order_id   NUMBER PATH '$.orderId',
             product_id NUMBER PATH '$.productId',
             quantity   NUMBER PATH '$.quantity'
         )
     ) jt
JOIN products p
  ON p.product_id = jt.product_id;
~~~

This example assumes each item contains `orderId`. If `orderId` is on the parent object, use row path `'$'` and NESTED PATH `'$.items[*]'` to retrieve both parent and child columns.

### 9.1 Joining with Customers

~~~sql
SELECT d.document_id,
       jt.order_id,
       c.customer_name
FROM order_documents d,
     JSON_TABLE(
         d.payload,
         '$'
         COLUMNS (
             order_id NUMBER PATH '$.orderId',
             customer_id NUMBER PATH '$.customerId'
         )
     ) jt
JOIN customers c
  ON c.customer_id = jt.customer_id;
~~~

### 9.2 Filtering by Projected JSON Columns

~~~sql
SELECT jt.order_id,
       jt.status
FROM order_documents d,
     JSON_TABLE(
         d.payload,
         '$'
         COLUMNS (
             order_id NUMBER PATH '$.orderId',
             status VARCHAR2(20) PATH '$.status'
         )
     ) jt
WHERE jt.status = 'PAID';
~~~

The predicate is applied on the SQL column produced by JSON_TABLE. The optimizer may apply appropriate transformations, though actual performance should be verified via the execution plan.

## 10. JSON_TABLE with Conditions and Aggregation

You can GROUP BY projected columns:

~~~sql
SELECT jt.status,
       COUNT(*) AS order_count
FROM order_documents d,
     JSON_TABLE(
         d.payload,
         '$'
         COLUMNS (
             status VARCHAR2(20) PATH '$.status'
         )
     ) jt
GROUP BY jt.status;
~~~

Summing quantity by product:

~~~sql
SELECT jt.product_id,
       SUM(jt.quantity) AS total_quantity
FROM order_documents d,
     JSON_TABLE(
         d.payload,
         '$.items[*]'
         COLUMNS (
             product_id NUMBER PATH '$.productId',
             quantity NUMBER PATH '$.quantity'
         )
     ) jt
GROUP BY jt.product_id;
~~~

Calculating order totals:

~~~sql
SELECT jt.order_id,
       SUM(jt.quantity * jt.unit_price) AS order_total
FROM order_documents d,
     JSON_TABLE(
         d.payload,
         '$'
         COLUMNS (
             order_id NUMBER PATH '$.orderId',
             NESTED PATH '$.items[*]'
             COLUMNS (
                 quantity NUMBER PATH '$.quantity',
                 unit_price NUMBER PATH '$.unitPrice'
             )
         )
     ) jt
GROUP BY jt.order_id;
~~~

For financial data, define precision/scale, rounding rules, currency, and validation. JSON_TABLE converts data to NUMBER, but does not automatically enforce full monetary business rules.

## 11. Handling Missing Values, JSON null, and Conversion Errors

A field in JSON can:

1. Have a value of the expected type.
2. Be absent.
3. Be present with JSON `null`.
4. Have an incompatible type, such as a string instead of a number.
5. Have an unmatched path or invalid structure.
6. Have multiple values when the SQL column expects a scalar.

These cases should not be treated identically.

### 11.1 ON ERROR

JSON_TABLE supports error handling at both table and column levels. Common options:

- NULL ON ERROR: returns NULL when an error within the clause's scope occurs.
- ERROR ON ERROR: raises an error.
- DEFAULT expr ON ERROR: returns a default value on error.

Example:

~~~sql
SELECT jt.quantity
FROM JSON_TABLE(
    '{"quantity":"not-a-number"}',
    '$'
    COLUMNS (
        quantity NUMBER PATH '$.quantity'
            DEFAULT 0 ON ERROR
    )
) jt;
~~~

Using DEFAULT 0 is only appropriate if the business truly treats corrupt data as 0. In financial or inventory data, turning invalid data into 0 can mask errors and skew results. Usually use ERROR ON ERROR during strict ingestion steps, or NULL ON ERROR while logging errors per policy.

### 11.2 ON EMPTY

ON EMPTY controls the case where a path finds no value:

~~~sql
SELECT jt.discount
FROM JSON_TABLE(
    '{"orderId":7001}',
    '$'
    COLUMNS (
        discount NUMBER PATH '$.discount'
            NULL ON ERROR
            DEFAULT 0 ON EMPTY
    )
) jt;
~~~

If the `discount` field is absent, the example returns 0 per ON EMPTY. If the field has a value that cannot be converted to NUMBER, ON ERROR applies.

Oracle syntax places ON ERROR before ON EMPTY. Verify exact syntax for your database version when using DEFAULT variants.

### 11.3 JSON null vs. Missing Field

JSON:

~~~json
{"discount": null}
~~~

differs from:

~~~json
{"orderId": 7001}
~~~

The first has a `discount` field with JSON `null`; the second lacks the field. When projected into a SQL scalar column, both may become SQL NULL in many situations. If business logic must distinguish them, check node existence/type using an appropriate SQL/JSON expression or validate the payload upfront.

Do not rely on a single SQL NULL column to determine whether the cause was a missing field, JSON null, or a conversion error if the error policy also returns NULL.

### 11.4 Default ON ERROR Does Not Replace Validation

If omitted, Oracle applies the defaults of the respective SQL/JSON function and clause. Defaults often turn errors into NULL. For critical ingestion, specify explicit policies so corrupt data is not silently ignored.

### 11.5 Unmatched Row Path

If the row path finds no matching nodes, JSON_TABLE can produce zero rows. This differs from a row being generated where a column path returns NULL.

Example:

~~~sql
SELECT COUNT(*)
FROM JSON_TABLE(
    '{"items":[]}',
    '$.items[*]'
    COLUMNS (
        item_id NUMBER PATH '$.id'
    )
);
~~~

An empty array produces zero rows. `COUNT(*)` returns 0.

## 12. Validating JSON Data Before Projection

JSON_TABLE assumes the input is valid JSON under the active rules. For columns storing JSON in CLOB/VARCHAR2/BLOB, you can use an IS JSON constraint:

~~~sql
CREATE TABLE inbound_messages (
    message_id NUMBER PRIMARY KEY,
    payload CLOB NOT NULL,
    CONSTRAINT ck_inbound_payload_json
        CHECK (payload IS JSON)
);
~~~

The constraint prevents non-JSON text from being saved into the column.

### 12.1 IS JSON Does Not Validate the Full Business Schema

Syntactically valid JSON can still be invalid for the business:

- Missing `orderId`.
- Non-existent `customerId`.
- Negative `quantity`.
- `status` not in the allowed list.
- `items` is not an array as contracted.
- Field has the right type but an out-of-range value.

After verifying JSON syntax, validate schema and business rules using JSON_TABLE, relational constraints, or application-layer validation.

### 12.2 Storing Raw JSON and Relational Data

An ingestion architecture can:

1. Store the raw payload for audit/replay.
2. Validate JSON syntax.
3. Use JSON_TABLE to project data.
4. Validate data types and business rules.
5. Load header/detail tables.
6. Mark the processing status.

If step 5 fails, the transaction must preserve a consistent ingestion state. You can retain the raw payload with a REJECTED status and error details according to business design.

## 13. Converting a JSON Array into Multiple Rows

This is the most common use case for JSON_TABLE.

JSON:

~~~json
{
  "events": [
    {"eventId": 1, "type": "LOGIN"},
    {"eventId": 2, "type": "PURCHASE"},
    {"eventId": 3, "type": "LOGOUT"}
  ]
}
~~~

Query:

~~~sql
SELECT jt.event_no,
       jt.event_id,
       jt.event_type
FROM JSON_TABLE(
    :payload,
    '$.events[*]'
    COLUMNS (
        event_no   FOR ORDINALITY,
        event_id   NUMBER PATH '$.eventId',
        event_type VARCHAR2(30) PATH '$.type'
    )
) jt
ORDER BY jt.event_no;
~~~

Each object in `events` creates a row. This converts an array into a rowset.

### 13.1 Scalar Arrays

JSON arrays do not have to contain objects:

~~~json
{"tags": ["new", "priority", "export"]}
~~~

You can project each scalar using the row path:

~~~sql
SELECT jt.tag_no,
       jt.tag
FROM JSON_TABLE(
    '{"tags":["new","priority","export"]}',
    '$.tags[*]'
    COLUMNS (
        tag_no FOR ORDINALITY,
        tag VARCHAR2(30) PATH '$'
    )
) jt;
~~~

Within each row source, the path `'$'` points to the current scalar selected by the row path.

### 13.2 Object Arrays with Missing Fields

JSON:

~~~json
{
  "items": [
    {"productId": 501, "quantity": 2},
    {"productId": 502},
    {"productId": 503, "quantity": 4}
  ]
}
~~~

With `quantity` missing from the second element, the `quantity` column may become SQL NULL under default empty handling or the declared clause. Decide whether the field is mandatory or optional. If mandatory, validation must catch it rather than letting NULL enter a target table that happens to allow NULL.

## 14. JSON_TABLE and Multiple Independent Arrays

Suppose JSON is:

~~~json
{
  "orderId": 7001,
  "items": [
    {"productId": 501},
    {"productId": 502}
  ],
  "payments": [
    {"method": "CARD"},
    {"method": "VOUCHER"}
  ]
}
~~~

If you need to extract `items` and `payments` as two separate relations, use two separate JSON_TABLE expressions:

~~~sql
SELECT d.document_id,
       i.product_id
FROM order_documents d,
     JSON_TABLE(
         d.payload,
         '$.items[*]'
         COLUMNS (
             product_id NUMBER PATH '$.productId'
         )
     ) i;
~~~

~~~sql
SELECT d.document_id,
       p.method
FROM order_documents d,
     JSON_TABLE(
         d.payload,
         '$.payments[*]'
         COLUMNS (
             method VARCHAR2(30) PATH '$.method'
         )
     ) p;
~~~

The two queries produce two independent rowsets. Joining both rowsets solely on `document_id` can multiply `items` rows × `payments` rows. Only do that if business logic genuinely requires every combination pair.

### 14.1 Sibling Nested Paths and Union Join

If you declare multiple NESTED PATH clauses at the same level in one JSON_TABLE, Oracle combines the branches using union join semantics. This differs from cross-joining two independent JSON_TABLE expressions. Choose the structure based on business relationships:

- Parent-child: NESTED PATH.
- Two independent collections: two separate JSON_TABLE calls/row sources.
- Intentional Cartesian product: explicit join.

## 15. JSON_TABLE vs. JSON_QUERY

JSON_TABLE builds a rowset and SQL columns. JSON_QUERY extracts a JSON object/array as JSON text or a supported return type.

| Function | Purpose |
|---|---|
| JSON_VALUE | Extracts a scalar as a SQL type |
| JSON_QUERY | Extracts a JSON object/array |
| JSON_EXISTS | Checks whether a path exists/matches |
| JSON_TABLE | Converts JSON into relational rows/columns |

Example:

~~~sql
SELECT JSON_VALUE(payload, '$.status') AS status
FROM order_documents;
~~~

If you only need one scalar, JSON_VALUE is usually more direct. If you need multiple fields or an array expanded into multiple rows, JSON_TABLE is more suitable.

### 15.1 Avoiding Unnecessary Multiple JSON_VALUE Calls

Example:

~~~sql
SELECT JSON_VALUE(payload, '$.orderId'),
       JSON_VALUE(payload, '$.customerId'),
       JSON_VALUE(payload, '$.status')
FROM order_documents;
~~~

When needing multiple fields from the same document, JSON_TABLE can group the paths into one row source:

~~~sql
SELECT jt.order_id,
       jt.customer_id,
       jt.status
FROM order_documents d,
     JSON_TABLE(
         d.payload,
         '$'
         COLUMNS (
             order_id NUMBER PATH '$.orderId',
             customer_id NUMBER PATH '$.customerId',
             status VARCHAR2(20) PATH '$.status'
         )
     ) jt;
~~~

The optimizer may rewrite SQL/JSON expressions, so do not draw conclusions merely from how many function calls appear in the source SQL. Inspect the execution plan and measure on your actual Oracle version.

## 16. JSON_TABLE with INSERT/MERGE

JSON_TABLE is frequently used as a data source for DML.

### 16.1 INSERT ... SELECT

~~~sql
INSERT INTO order_items(
    order_id,
    line_no,
    product_id,
    quantity
)
SELECT jt.order_id,
       jt.line_no,
       jt.product_id,
       jt.quantity
FROM inbound_messages m,
     JSON_TABLE(
         m.payload,
         '$'
         COLUMNS (
             order_id NUMBER PATH '$.orderId',
             NESTED PATH '$.items[*]'
             COLUMNS (
                 line_no NUMBER PATH '$.lineNo',
                 product_id NUMBER PATH '$.productId',
                 quantity NUMBER PATH '$.quantity'
             )
         )
     ) jt
WHERE m.message_id = :message_id;
~~~

A single INSERT statement can load multiple rows from one JSON document.

### 16.2 MERGE

~~~sql
MERGE INTO product_inventory target
USING (
    SELECT jt.product_id,
           jt.available_qty
    FROM inbound_messages m,
         JSON_TABLE(
             m.payload,
             '$.inventory[*]'
             COLUMNS (
                 product_id NUMBER PATH '$.productId',
                 available_qty NUMBER PATH '$.availableQty'
             )
         ) jt
    WHERE m.message_id = :message_id
) source
ON (target.product_id = source.product_id)
WHEN MATCHED THEN
    UPDATE SET target.available_qty = source.available_qty
WHEN NOT MATCHED THEN
    INSERT (product_id, available_qty)
    VALUES (source.product_id, source.available_qty);
~~~

MERGE fits when the JSON source may contain both existing and new records. Ensure the source does not contain multiple rows with the same target key if that would update a single target row multiple times; validate or deduplicate the source using clear rules.

## 17. Building Views on JSON_TABLE

If multiple queries need the same JSON structure, you can create a view:

~~~sql
CREATE OR REPLACE VIEW v_order_document_items AS
SELECT d.document_id,
       jt.order_id,
       jt.customer_id,
       jt.item_no,
       jt.product_id,
       jt.quantity
FROM order_documents d,
     JSON_TABLE(
         d.payload,
         '$'
         COLUMNS (
             order_id NUMBER PATH '$.orderId',
             customer_id NUMBER PATH '$.customerId',
             NESTED PATH '$.items[*]'
             COLUMNS (
                 item_no FOR ORDINALITY,
                 product_id NUMBER PATH '$.productId',
                 quantity NUMBER PATH '$.quantity'
             )
         )
     ) jt;
~~~

Callers can query the view like a relational table:

~~~sql
SELECT product_id,
       SUM(quantity) AS total_qty
FROM v_order_document_items
GROUP BY product_id;
~~~

A view does not necessarily materialize results. Each query may need to evaluate JSON_TABLE over the relevant documents. For heavy workloads, check the plan and consider relational projections, materialized views, or normalized tables.

## 18. JSON Data Type and JSON Storage by Release

JSON_TABLE works with input types supported by Oracle for SQL/JSON, typically including VARCHAR2, CLOB, BLOB, and the native JSON type in supported releases.

### 18.1 Oracle 19c

In Oracle 19c, JSON is typically stored in VARCHAR2, CLOB, or BLOB with an IS JSON constraint. Example:

~~~sql
CREATE TABLE api_messages (
    message_id NUMBER PRIMARY KEY,
    payload CLOB NOT NULL,
    CONSTRAINT ck_api_messages_json
        CHECK (payload IS JSON)
);
~~~

### 18.2 Native JSON Data Type

Oracle Database 21c introduced the native JSON data type, using the OSON binary format to store JSON. Subsequent releases further expanded support. Specific DDL syntax and capabilities should be checked against the deployed release.

If the system must remain compatible across multiple versions, design schemas and code around data types supported in the lowest version in the deployment scope.

### 18.3 BLOB JSON and Encoding

When JSON is stored in BLOB, specify the encoding per Oracle SQL/JSON rules. In practice, UTF-8 is typically used for JSON BLOBs. Do not store text bytes in arbitrary encodings and assume Oracle will automatically detect them accurately in all cases.

## 19. JSON_TABLE Performance

JSON_TABLE can generate large rowsets from a single document. Performance depends on:

- JSON document size.
- Number of elements in arrays.
- Number of projected paths/columns.
- Depth of nested paths.
- Data types and conversions.
- Number of documents scanned.
- Predicates and joins after flattening.
- Storage format and Oracle version.

### 19.1 Project Only Needed Columns

Do not declare dozens of JSON columns if the query only uses three. Unnecessary extractions increase parsing/conversion work.

### 19.2 Filter Documents Before Flattening

When possible, filter the document set using relational conditions before expanding arrays:

~~~sql
SELECT d.document_id,
       jt.product_id
FROM order_documents d,
     JSON_TABLE(
         d.payload,
         '$.items[*]'
         COLUMNS (
             product_id NUMBER PATH '$.productId'
         )
     ) jt
WHERE d.document_id BETWEEN :from_id AND :to_id;
~~~

Predicate pushdown and execution order are decided by the optimizer; inspect the actual plan to confirm. Do not assume the written order of FROM/WHERE guarantees physical processing order.

### 19.3 Watch Array Cardinality

A single document with 10,000 elements can generate 10,000 rows. If a query scans 100,000 documents, the total row source can be huge.

Estimate:

~~~text
Rows produced ≈ number of documents × average matching array elements
~~~

This is a rough estimate; nested paths and data structure can alter cardinality. Check A-Rows and E-Rows in the execution plan.

### 19.4 Search Indexes and Function-Based Indexes

Oracle supports JSON search indexes for eligible JSON queries:

~~~sql
CREATE SEARCH INDEX order_payload_search_ix
ON order_documents(payload)
FOR JSON;
~~~

A search index can speed up certain path/JSON_EXISTS/JSON_VALUE queries depending on expressions and release. It does not automatically optimize every JSON_TABLE projection or every array flattening operation.

For frequently queried scalar paths, consider a function-based index:

~~~sql
CREATE INDEX order_status_json_ix
ON order_documents (
    JSON_VALUE(
        payload,
        '$.status'
        RETURNING VARCHAR2(20)
    )
);
~~~

Queries must match the index expression for the optimizer to use it. Check the plan, statistics, and index maintenance overhead when payloads change.

### 19.5 Materialize Relational Data When Queried Frequently

If the same JSON array is flattened for many reports or frequent joins, load the data into normalized relational tables instead of computing JSON_TABLE on every query.

Consider:

- Read vs. write frequency.
- JSON size.
- Synchronization latency.
- Payload replayability.
- How item updates/deletes are handled.
- Storage cost of duplicated data.

JSON_TABLE excels at ingestion and projection; it is not necessarily optimal for every repeated analytical query.

## 20. Controlling Schemas and Heterogeneous Data

JSON is flexible, but if the same field has varying types, SQL projection becomes unpredictable:

~~~json
{"quantity": 2}
~~~

~~~json
{"quantity": "2"}
~~~

~~~json
{"quantity": null}
~~~

~~~json
{}
~~~

A good JSON schema should specify:

- Mandatory/optional fields.
- Data types.
- Value domains.
- Date/time formats.
- Null rules.
- Payload version.
- Array and object structure.

You can store `schema_version` inside the document:

~~~json
{
  "schemaVersion": 2,
  "orderId": 7001,
  "items": []
}
~~~

When JSON structures evolve, JSON_TABLE may need to handle multiple versions. You can use separate views/packages per version or transform older payloads to the standard schema before loading.

### 20.1 Defaults Do Not Replace Migrations

If a new field is absent in older payloads, DEFAULT ON EMPTY can help with compatibility. However, if a field's meaning changes, assigning a default can corrupt business logic. Define clearly which defaults are safe and when older payloads must be rejected.

## 21. Common Errors When Using JSON_TABLE

| Symptom | Cause | Resolution |
|---|---|---|
| No rows returned | Row path does not match or array is empty | Check row path and JSON structure |
| Rows exist but columns are NULL | Column path missing, JSON null, or ON ERROR returns NULL | Distinguish empty/null/conversion error |
| NUMBER conversion error | JSON field is an invalid string or exceeds precision | Normalize payload, choose explicit type and ON ERROR |
| Only one row instead of many | Row path selects root object instead of `array[*]` | Point row path to the array to expand |
| Parent row disappears when array is empty | Cross-joining JSON_TABLE using an array row path | Use root row path with NESTED PATH to retain parent |
| Unexpected row multiplication | Multiple row sources cross-joined | Verify parent-child relationship and cardinality |
| Sibling arrays produce confusing results | Confusing union join with Cartesian product | Split JSON_TABLE or join explicitly |
| Row order changes | Missing ORDER BY | Use FOR ORDINALITY and ORDER BY |
| Date/time shifted | String converted to DATE/TIMESTAMP without explicit format/timezone | Extract string and convert explicitly |
| Query slow across many documents | Parsing/flattening too much JSON or missing filter/index | Check plan, filter documents, add search/function-based index |
| MERGE fails with multiple matching source rows | JSON array has duplicate keys | Validate/deduplicate source |
| Bad data enters table | NULL ON ERROR masks errors or only JSON syntax is checked | Add schema and business rule validation |

## 22. JSON-to-Relational Ingestion Workflow

A pipeline can include:

1. Receive payload and attach request/message ID.
2. Check size, encoding, and JSON syntax.
3. Identify schema version.
4. Use JSON_TABLE to project header and child arrays.
5. Validate mandatory fields, types, value domains, and FK references.
6. Load header/details in an appropriate transaction.
7. Record processing status or errors.
8. Use an idempotency key to prevent duplicate ingestion.
9. Retain raw payload if audit/replay is required.
10. Monitor row counts produced, conversion errors, and processing latency.

Do not simply run JSON_TABLE followed by INSERT without defining policies for invalid payloads or duplicates.

## 23. Comprehensive Example: Reading JSON Orders and Joining Catalogs

JSON:

~~~json
{
  "schemaVersion": 1,
  "orderId": 7001,
  "customerId": 101,
  "status": "NEW",
  "items": [
    {"lineNo": 1, "productId": 501, "quantity": 2},
    {"lineNo": 2, "productId": 502, "quantity": 1}
  ]
}
~~~

Query:

~~~sql
SELECT d.document_id,
       jt.order_id,
       jt.customer_id,
       jt.status,
       jt.line_no,
       jt.product_id,
       p.product_name,
       jt.quantity
FROM order_documents d,
     JSON_TABLE(
         d.payload,
         '$'
         COLUMNS (
             schema_version NUMBER PATH '$.schemaVersion',
             order_id NUMBER PATH '$.orderId',
             customer_id NUMBER PATH '$.customerId',
             status VARCHAR2(20) PATH '$.status',
             NESTED PATH '$.items[*]'
             COLUMNS (
                 line_no NUMBER PATH '$.lineNo',
                 product_id NUMBER PATH '$.productId',
                 quantity NUMBER PATH '$.quantity'
             )
         )
     ) jt
JOIN products p
  ON p.product_id = jt.product_id
WHERE d.document_id = :document_id
  AND jt.schema_version = 1
ORDER BY jt.line_no;
~~~

The query performs:

- Selecting a single document by relational key.
- Projecting parent-level order information.
- Expanding `items` into multiple rows.
- Joining `product_id` with the PRODUCTS table.
- Filtering by schema version.
- Sorting by `line_no`.

## 24. Self-Check Practice Lab

Exercises should be run in a test schema with payloads structured similarly to the examples.

### Exercise 1 — JSON Object to Single Row

Create JSON with `orderId`, `customerId`, and `status`. Use JSON_TABLE with row path `'$'` to project three SQL columns.

### Exercise 2 — Array to Multiple Rows

Create a document with an `items` array containing five objects. Use row path `'$.items[*]'` and count the resulting rows.

### Exercise 3 — FOR ORDINALITY

Add a FOR ORDINALITY column. Sort by sequence number and compare with 0-based indexing in JSON paths.

### Exercise 4 — NESTED PATH

Create an order JSON with `items`. Use the root row path and NESTED PATH to bring order header and items into the same rowset.

### Exercise 5 — Empty Array

Test row path `'$.items[*]'` with an empty array, then test root path + NESTED PATH. Compare how parent rows are retained.

### Exercise 6 — Two Independent Arrays

Create JSON with `items` and `payments`. Use two separate JSON_TABLE calls. Observe cardinality when cross-joining and explain when a Cartesian product is incorrect.

### Exercise 7 — Scalar Array

Use a JSON array of tag strings. Project each scalar using path `'$'` and FOR ORDINALITY.

### Exercise 8 — Missing, JSON null, and Conversion Errors

Test a missing field, a JSON null field, and a field with a string that cannot convert to NUMBER. Compare NULL ON EMPTY, ERROR ON ERROR, and DEFAULT ON ERROR.

### Exercise 9 — Dates and Times

Extract `createdAt` as an ISO string and convert using TO_TIMESTAMP and TO_TIMESTAMP_TZ. Explain the difference when an offset is present.

### Exercise 10 — INSERT Header/Detail

Use two INSERT ... SELECT statements with JSON_TABLE to load header and items into two relational tables within the same transaction.

### Exercise 11 — MERGE

Use JSON_TABLE as the source for MERGE into an inventory table. Test a payload with duplicate `productId` values and clean/deduplicate the source before MERGE.

### Exercise 12 — Indexes and Execution Plans

Create many JSON documents. Compare JSON_VALUE/JSON_TABLE queries with no index, a function-based index, and a suitable JSON search index. Use actual execution plans and buffer gets to evaluate.

## 25. JSON_TABLE Design Checklist

**Structure**

- Does the row path select the right node to generate rows?
- Are column paths relative to the current node?
- Which arrays need to be expanded into multiple rows?
- Should NESTED PATH preserve the parent row when a child array is empty?
- Are sibling arrays mistakenly assumed to produce a Cartesian product?
- Is FOR ORDINALITY needed to preserve order?

**Data Types**

- Are NUMBER/VARCHAR2/DATE/TIMESTAMP chosen explicitly?
- Are string lengths sufficient with appropriate BYTE/CHAR semantics?
- Are date/time formats and timezones defined?
- Are bytes and characters properly distinguished?

**Errors and Validation**

- Are ON ERROR and ON EMPTY specified explicitly?
- Are missing fields, JSON null, and conversion errors distinguished?
- Is JSON syntax validated?
- Are schema version and business rules validated?
- Are duplicate keys and FKs handled?

**Performance**

- Are only necessary fields projected?
- Are documents filtered by relational keys/conditions?
- Has actual cardinality been verified?
- Is a JSON search index or function-based index needed?
- Should projections be materialized into relational tables for repeated read workloads?

**Data Loading**

- Are header and details in the same transaction?
- Is there an idempotency key?
- Are raw payloads and error statuses stored?
- Does the MERGE source contain duplicate keys?
- Are row counts and errors logged per request ID?

## 26. Key Terms to Remember

| Component | Role |
|---|---|
| JSON_TABLE | Converts JSON into a relational row source |
| Row path | Selects nodes that generate rows |
| COLUMNS | Defines output SQL columns |
| Column PATH | Extracts a field from the current node |
| FOR ORDINALITY | Numbers rows starting from 1 |
| NESTED PATH | Expands child arrays/objects in a parent-child relationship |
| ON ERROR | Specifies behavior when an error occurs |
| ON EMPTY | Specifies behavior when a path finds no value |
| JSON null | The null value inside JSON |
| Missing field | Path does not find the field |
| CROSS JOIN row source | Documents with no matching JSON rows may be excluded from results |
| Nested parent-child | Unmatched children can preserve the parent with NULL child columns |
| JSON_VALUE | Extracts a scalar |
| JSON_QUERY | Extracts an object/array |
| JSON_EXISTS | Checks a path |
| IS JSON | Validates JSON syntax |
| INSERT ... SELECT | Loads multiple rows from JSON |
| MERGE | Synchronizes a JSON rowset with a relational table |
| JSON search index | Supports eligible JSON queries |
| Function-based index | Accelerates queries on specific scalar paths |

JSON_TABLE is the bridge between the document model and the relational model. Choose the row path at the right data level, use explicit column paths, expand arrays with NESTED PATH, preserve order with FOR ORDINALITY, and define explicit error/missing-value handling. Once projected into a row source, JSON data can be joined, aggregated, INSERTed, or MERGEd just like relational data. For large workloads, always verify cardinality and execution plans, and consider materializing data if the same projection is queried frequently.
