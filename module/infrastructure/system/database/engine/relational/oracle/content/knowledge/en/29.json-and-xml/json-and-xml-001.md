# Storing JSON in VARCHAR2/CLOB/BLOB and Validating with IS JSON

JSON is a popular data interchange format for APIs, events, configurations, and business documents. In Oracle Database, applications can store JSON as text in VARCHAR2 or CLOB, or store UTF-8 bytes in BLOB. When using these text/LOB storage types, the database does not automatically make every value valid JSON just because a column is named JSON_PAYLOAD. You need to validate JSON syntax using the **IS JSON** SQL condition, typically placed in a CHECK constraint so invalid data cannot be written into the table.

The choice of column type affects size limits, how clients pass data, memory usage, and LOB operations. VARCHAR2 fits small documents with bounded length; CLOB fits large text JSON; BLOB fits cases where you want to store JSON bytes in UTF-8. Starting with Oracle Database 21c, the database provides a native JSON data type stored in the OSON binary format; Oracle 19c systems still commonly use VARCHAR2/CLOB/BLOB.

This lesson belongs to the **JSON and XML** group in Database Engine Relational Oracle. The content focuses on storing JSON in the three data types VARCHAR2, CLOB, and BLOB; IS JSON syntax; strict/lax syntax; unique object keys; CHECK constraints; NULL semantics; checking legacy data; querying JSON documents; version differences; and hands-on practice.

After this lesson, you will be able to:

- Choose VARCHAR2, CLOB, or BLOB for JSON payloads based on size and how the application uses the data.
- Understand VARCHAR2 limits under STANDARD and EXTENDED configurations.
- Explain the UTF-8 requirement when storing JSON in BLOB.
- Use IS JSON to validate document syntax.
- Distinguish between lax syntax and strict syntax.
- Use WITH UNIQUE KEYS when duplicate object keys are not allowed.
- Define CHECK constraints to protect data during INSERT/UPDATE.
- Combine NOT NULL with IS JSON to distinguish SQL NULL from JSON null.
- Inspect and clean up legacy data before adding a constraint.
- Use JSON_VALUE, JSON_QUERY, JSON_EXISTS, and JSON_TABLE to read stored data.
- Understand that IS JSON does not replace structural validation and business rules.
- Recognize the native JSON data type introduced in Oracle Database 21c and how it differs from 19c.

> **Example scope:** The primary syntax targets Oracle Database 19c, where JSON is commonly stored as VARCHAR2/CLOB/BLOB. Notes on the native JSON data type and SQL BOOLEAN are distinguished by release; check your version/RU before deploying.

## 1. How Is JSON Stored in Oracle?

JSON is structured text composed of objects, arrays, strings, numbers, booleans, and null. Example:

~~~json
{
  "orderId": 9001,
  "status": "NEW",
  "total": 125.50,
  "items": [
    {"productId": 101, "quantity": 2},
    {"productId": 205, "quantity": 1}
  ]
}
~~~

In Oracle 19c, this content can be stored in:

- VARCHAR2: character string with a length limit.
- CLOB: large object containing characters.
- BLOB: large object containing bytes; JSON is stored as UTF-8 bytes.

The database can validate the content of these types using the IS JSON condition.

### 1.1. JSON in a Column Is Not Automatically Validated

Example:

~~~sql
CREATE TABLE api_event_lab (
    event_id NUMBER PRIMARY KEY,
    payload VARCHAR2(4000)
);
~~~

The PAYLOAD column is just a VARCHAR2. Without a constraint, an application can write:

~~~sql
INSERT INTO api_event_lab(event_id, payload)
VALUES (1, '{"event":"created","id":101}');

INSERT INTO api_event_lab(event_id, payload)
VALUES (2, '{this is not json}');
~~~

Both values are valid strings for the VARCHAR2 data type. The database does not automatically know that the second string has invalid JSON syntax without validation.

### 1.2. IS JSON Confirms Syntax

You can check directly:

~~~sql
SELECT payload
FROM api_event_lab
WHERE payload IS JSON;
~~~

IS JSON is a SQL condition used to determine whether a value is valid JSON according to the selected syntax mode. It does not automatically fix, normalize, or convert an invalid string into JSON.

### 1.3. JSON Syntax vs. Business Validation

A document can be syntactically valid yet invalid for the business domain:

~~~json
{
  "orderId": -1,
  "status": "UNKNOWN",
  "total": -500
}
~~~

This is still syntactically valid JSON. IS JSON does not know that orderId must be positive, status can only accept NEW/PAID/CANCELLED, or total must not be negative. Those rules must be enforced at the application layer, with appropriate constraints, or through dedicated validation.

## 2. Choosing VARCHAR2, CLOB, or BLOB

The three data types serve different use cases.

| Column Type | Content | Suitable When | Points to Note |
| --- | --- | --- | --- |
| VARCHAR2 | JSON text | Small documents with bounded size | Byte/character limits and MAX_STRING_SIZE |
| CLOB | Large JSON text | Large documents processed via character/LOB APIs | LOB storage, locators, and LOB operations |
| BLOB | JSON bytes | Need to store UTF-8 JSON bytes or large binary-form payloads | Must supply UTF-8 encoded JSON |

### 2.1. VARCHAR2 for Small JSON

Example:

~~~sql
CREATE TABLE small_json_lab (
    event_id NUMBER PRIMARY KEY,
    payload VARCHAR2(4000 BYTE)
        CONSTRAINT ck_small_json_lab CHECK (payload IS JSON)
);
~~~

Advantages:

- Simple structure.
- Easy to bind from applications as a string.
- Convenient for small payloads.
- No LOB locator handling required.

Limitations:

- Has size limits.
- Requires distinguishing between BYTE and CHAR semantics.
- A payload exceeding the limit cannot be written to the column.

### 2.2. VARCHAR2 Limits in SQL

With MAX_STRING_SIZE = STANDARD, the VARCHAR2 limit in SQL is typically up to 4000 bytes. With MAX_STRING_SIZE = EXTENDED, the maximum limit can be 32767 bytes. The actual limit also depends on the length declaration, byte/char semantics, and database character set.

Check the configuration:

~~~sql
SELECT name, value
FROM v$parameter
WHERE name = 'max_string_size';
~~~

Access to V$PARAMETER depends on configuration and grants. Do not change MAX_STRING_SIZE solely to store one large JSON payload; it is a database-wide setting requiring DBA procedures and has broad impact.

### 2.3. BYTE and CHAR Semantics

~~~sql
payload_bytes VARCHAR2(4000 BYTE)
payload_chars VARCHAR2(4000 CHAR)
~~~

BYTE limits by number of bytes; CHAR limits by number of characters. With multi-byte UTF-8 characters, a single character can occupy multiple bytes. Declaring CHAR does not mean the column can always store 4000 characters in every database character set if it hits the data type's maximum byte limit.

For JSON containing Vietnamese or multiple languages, verify the character set, actual byte length, and how the driver binds data.

### 2.4. CLOB for Large Text JSON

~~~sql
CREATE TABLE document_json_lab (
    document_id NUMBER PRIMARY KEY,
    payload CLOB
        CONSTRAINT ck_document_json_lab
        CHECK (payload IS JSON)
);
~~~

CLOB stores character data larger than the VARCHAR2 limit. It is suitable for:

- Large API requests/responses.
- JSON documents with many elements.
- Long event or message payloads.
- Documents read/written using character LOB APIs.

CLOB is managed as a LOB, typically via locators and DBMS_LOB or driver LOB support. Do not assume every CLOB operation has the same cost as VARCHAR2.

### 2.5. BLOB for UTF-8 JSON

~~~sql
CREATE TABLE binary_json_text_lab (
    document_id NUMBER PRIMARY KEY,
    payload BLOB
        CONSTRAINT ck_binary_json_text_lab
        CHECK (payload IS JSON)
);
~~~

When storing JSON in BLOB, the JSON content must be UTF-8 encoded according to Oracle JSON rules. BLOB stores bytes and does not track a character set on its own. Applications must send valid UTF-8 bytes; you cannot put a string in an arbitrary character set into BLOB and expect the database to guess it accurately.

BLOB is suitable when:

- The application already has JSON as UTF-8 bytes.
- You need to preserve payload bytes in their wire/transport format.
- You use LOB APIs/drivers that work naturally with binary data.
- You need to handle large documents without converting through a character LOB.

If the application primarily handles character strings, CLOB is usually easier to use than BLOB.

### 2.6. BLOB Does Not Mean Native Binary JSON

BLOB in this example still holds JSON text encoded into UTF-8 bytes. It is not the same concept as the native JSON data type using OSON in Oracle Database 21c and later. The BLOB data type name does not automatically convert content into OSON.

## 3. The IS JSON Condition

IS JSON is a SQL condition that determines whether a value contains valid JSON.

### 3.1. Basic Syntax

~~~sql
expression IS JSON
~~~

Or:

~~~sql
expression IS NOT JSON
~~~

You can add syntax mode and unique keys requirements:

~~~sql
expression IS JSON STRICT
expression IS JSON LAX
expression IS JSON WITH UNIQUE KEYS
expression IS JSON STRICT WITH UNIQUE KEYS
~~~

By default, Oracle uses lax syntax if neither STRICT nor LAX is specified. When you need JSON following strict syntax, specify STRICT explicitly in the constraint.

### 3.2. IS JSON Works with VARCHAR2/CLOB/BLOB

Example table with all three column types:

~~~sql
CREATE TABLE json_storage_lab (
    id NUMBER PRIMARY KEY,
    json_short VARCHAR2(4000),
    json_text CLOB,
    json_bytes BLOB,
    CONSTRAINT ck_json_short_lab CHECK (json_short IS JSON),
    CONSTRAINT ck_json_text_lab CHECK (json_text IS JSON),
    CONSTRAINT ck_json_bytes_lab CHECK (json_bytes IS JSON)
);
~~~

With BLOB, the data must use the UTF-8 encoding supported by Oracle for JSON. With CLOB/VARCHAR2, the content is character data in the database character set.

### 3.3. IS NOT JSON

IS NOT JSON is useful for finding invalid values:

~~~sql
SELECT id, json_short
FROM json_storage_lab
WHERE json_short IS NOT JSON;
~~~

Note on SQL NULL: testing on NULL evaluates to UNKNOWN, not TRUE. Therefore, this query does not return rows with SQL NULL. To find both NULL and invalid JSON:

~~~sql
SELECT id, json_short
FROM json_storage_lab
WHERE json_short IS NULL
   OR json_short IS NOT JSON;
~~~

### 3.4. IS JSON Does Not Transform Data

The IS JSON condition only validates. It does not:

- Convert a JSON string into an object type.
- Normalize key ordering.
- Strip whitespace.
- Fix wrong quotes or commas.
- Automatically add required fields.
- Cast a string to a number.

If data is invalid, the application must fix the payload before writing, or a migration must handle it separately.

## 4. Strict JSON and Lax JSON

Oracle supports strict syntax and lax syntax for JSON text in supported contexts.

### 4.1. Strict Syntax

Strict syntax follows standard JSON rules: field names and strings use double quotes, with no extensions outside JSON syntax.

~~~json
{
  "customerId": 501,
  "name": "Nguyen An",
  "active": true
}
~~~

Validation:

~~~sql
SELECT '{"customerId":501,"name":"Nguyen An","active":true}' IS JSON STRICT
FROM dual;
~~~

### 4.2. Lax Syntax

Lax syntax allows certain extended forms that Oracle accepts beyond strict JSON. Illustrative example:

~~~text
{customerId: 501, name: 'Nguyen An'}
~~~

This is not strict JSON because field names are not enclosed in double quotes and strings use single quotes. Oracle lax mode can accept extensions like this.

### 4.3. Testing Strict and Lax

~~~sql
SELECT
    CASE
        WHEN '{customerId:501,name:''Nguyen An''}' IS JSON LAX
        THEN 'VALID LAX'
        ELSE 'INVALID LAX'
    END AS lax_result
FROM dual;
~~~

For payloads sent by external APIs, it is generally best to standardize on strict JSON to improve compatibility with clients, message brokers, and other systems.

### 4.4. Choosing Strict in a CHECK Constraint

~~~sql
CREATE TABLE strict_json_lab (
    id NUMBER PRIMARY KEY,
    payload CLOB NOT NULL,
    CONSTRAINT ck_strict_json_lab
        CHECK (payload IS JSON STRICT)
);
~~~

This constraint requires payload to be non-NULL and its content to be strict JSON.

### 4.5. When to Use Lax?

Lax can be useful when ingesting legacy JSON sources or Oracle JSON data generated with extended syntax. However, if the system exchanges data across multiple platforms, strict is usually more predictable.

Do not enable lax just to let malformed upstream data slip through without understanding the source of the error and downstream impact.

## 5. WITH UNIQUE KEYS

A JSON object can contain the same field name multiple times within one object:

~~~json
{
  "status": "NEW",
  "status": "PAID"
}
~~~

This is syntactically valid JSON in many parsers, but the meaning of duplicate keys is inconsistent across consumers. One parser might take the first value, another the last value, or keep both.

### 5.1. Do Not Assume Keys Are Unique by Default

Using basic IS JSON alone does not mean every object is required to have no duplicate keys. If unique field names are part of the contract, declare WITH UNIQUE KEYS.

### 5.2. Constraint with Unique Keys

~~~sql
CREATE TABLE unique_json_lab (
    id NUMBER PRIMARY KEY,
    payload CLOB NOT NULL,
    CONSTRAINT ck_unique_json_lab
        CHECK (payload IS JSON STRICT WITH UNIQUE KEYS)
);
~~~

This condition requires:

- Payload is strict JSON.
- Object keys do not repeat according to Oracle's unique keys rules.

### 5.3. Unique Keys vs. Primary Key

WITH UNIQUE KEYS only checks field names within each JSON object. It does not create a relational primary key and does not guarantee:

- Each document has a unique customerId across the entire table.
- A required field exists.
- A value is unique across multiple rows.
- A value belongs to a business domain.

If you need uniqueness by customerId across the entire table, extract the value using JSON_VALUE into a virtual column/function-based index or store it in a relational column with an appropriate unique constraint.

### 5.4. When Not to Enable Unique Keys?

If you must ingest legacy data that contains duplicate keys, adding WITH UNIQUE KEYS immediately can cause new INSERT/UPDATE statements to fail. Before migration, inspect and normalize the source data. Do not rely on differing parser behaviors to handle duplicate keys.

## 6. Combining CHECK Constraints with IS JSON

Placing validation directly in the database ensures every write path adheres to the same rule, whether data comes from an application, batch job, or SQL client.

### 6.1. Creating a Table with CHECK

~~~sql
CREATE TABLE order_json_lab (
    order_id NUMBER PRIMARY KEY,
    payload CLOB NOT NULL,
    CONSTRAINT ck_order_json_lab
        CHECK (payload IS JSON STRICT WITH UNIQUE KEYS)
);
~~~

### 6.2. INSERT Valid JSON

~~~sql
INSERT INTO order_json_lab(order_id, payload)
VALUES (
    9001,
    '{"orderId":9001,"status":"NEW","total":125.50}'
);
~~~

### 6.3. INSERT Invalid JSON Syntax

~~~sql
INSERT INTO order_json_lab(order_id, payload)
VALUES (
    9002,
    '{"orderId":9002,"status":NEW}'
);
~~~

The value NEW is missing double quotes, so it is not a strict JSON string. The CHECK constraint rejects this row and Oracle raises a constraint violation error, typically ORA-02290.

### 6.4. INSERT Duplicate Keys

~~~sql
INSERT INTO order_json_lab(order_id, payload)
VALUES (
    9003,
    '{"orderId":9003,"status":"NEW","status":"PAID"}'
);
~~~

The WITH UNIQUE KEYS constraint rejects a document with duplicate object field names.

### 6.5. CHECK and SQL NULL

A CHECK constraint does not replace NOT NULL. In SQL, CHECK only rejects a row when the condition evaluates to FALSE; UNKNOWN is not treated as FALSE. With a SQL NULL payload, the expression payload IS JSON evaluates to UNKNOWN, so CHECK may still allow the row.

Therefore, if a document is required:

~~~sql
payload CLOB NOT NULL,
CONSTRAINT ck_payload_json CHECK (payload IS JSON STRICT)
~~~

Or:

~~~sql
CHECK (payload IS NOT NULL AND payload IS JSON STRICT)
~~~

Declaring NOT NULL separately is usually easier to read and manage.

### 6.6. SQL NULL vs. JSON null

The following two cases are different:

- SQL NULL: the column has no SQL value.
- JSON null: the payload contains the JSON literal text null or a property whose value is null.

Example document:

~~~json
{"orderId":9001,"note":null}
~~~

this is a JSON document containing a NOTE field with JSON null. It differs from a PAYLOAD column containing SQL NULL.

## 7. Adding an IS JSON Constraint to an Existing Table with Data

When a table already contains payloads, do not add a constraint right away without checking the existing data.

### 7.1. Finding SQL NULL

~~~sql
SELECT COUNT(*) AS null_count
FROM legacy_json_lab
WHERE payload IS NULL;
~~~

### 7.2. Finding Invalid JSON

~~~sql
SELECT id, payload
FROM legacy_json_lab
WHERE payload IS NOT NULL
  AND payload IS NOT JSON;
~~~

If strict is required:

~~~sql
SELECT id, payload
FROM legacy_json_lab
WHERE payload IS NOT NULL
  AND payload IS NOT JSON STRICT;
~~~

If unique keys are required:

~~~sql
SELECT id, payload
FROM legacy_json_lab
WHERE payload IS NOT JSON STRICT WITH UNIQUE KEYS;
~~~

### 7.3. Cleaning Up Data First

A typical migration workflow includes:

1. Counting the number of NULL, invalid, and duplicate-key rows.
2. Identifying the source generating invalid data.
3. Fixing payloads through a controlled application/migration process.
4. Confirming every row satisfies the new policy.
5. Adding the constraint with ENABLE VALIDATE.

Do not automatically fix JSON using simple string replacement. For example, replacing single quotes with double quotes can corrupt string contents or escape sequences. Use a proper JSON parser/generator to parse and re-serialize.

### 7.4. Adding and Validating the Constraint

~~~sql
ALTER TABLE legacy_json_lab
ADD CONSTRAINT ck_legacy_json_lab
CHECK (payload IS JSON STRICT WITH UNIQUE KEYS)
ENABLE VALIDATE;
~~~

ENABLE VALIDATE requires existing data to satisfy the constraint and continues checking new DML statements. If invalid rows exist, adding/validating the constraint will fail until the data is fixed.

### 7.5. ENABLE NOVALIDATE

In a multi-phase migration, you can use:

~~~sql
ALTER TABLE legacy_json_lab
ADD CONSTRAINT ck_legacy_json_lab
CHECK (payload IS JSON STRICT)
ENABLE NOVALIDATE;
~~~

ENABLE NOVALIDATE starts enforcing the constraint for new DML without verifying that all legacy rows are already valid. This is a transitional state, not proof that historical data is clean.

After fixing legacy data:

~~~sql
ALTER TABLE legacy_json_lab
ENABLE VALIDATE CONSTRAINT ck_legacy_json_lab;
~~~

### 7.6. Disabling a Constraint

~~~sql
ALTER TABLE legacy_json_lab
DISABLE CONSTRAINT ck_legacy_json_lab;
~~~

When a constraint is disabled, the database no longer enforces that rule while in the disabled state. Only disable during approved migrations/maintenance; re-enable and validate once completed.

## 8. IS JSON and Business Structure Validation

IS JSON only answers one question: is the value syntactically valid JSON according to the policy?

### 8.1. Checking Required Properties

For example, an order payload must have orderId:

~~~sql
SELECT order_id
FROM order_json_lab
WHERE JSON_EXISTS(payload, '$.orderId');
~~~

JSON_EXISTS checks whether a path matches the data. It can be combined with a CHECK constraint if the expression is supported and semantics are clear, though conversion errors and legacy data must be verified.

### 8.2. Checking Property Data Types

~~~sql
SELECT
    order_id,
    JSON_VALUE(
        payload,
        '$.total'
        RETURNING NUMBER
        NULL ON ERROR
    ) AS total_amount
FROM order_json_lab;
~~~

JSON_VALUE extracts a scalar. RETURNING NUMBER requires the value to be convertible to NUMBER; NULL ON ERROR makes conversion errors return NULL instead of failing the entire query. For critical data, do not use NULL ON ERROR to silently hide errors without monitoring.

### 8.3. Distinguishing Missing Fields from Null Fields

A property can be:

- Absent.
- Present with JSON null.
- Present with an empty string.
- Present with a number/boolean/object/array.

JSON_VALUE typically returns SQL NULL in many missing or JSON null cases under default behavior. When you need to distinguish them, use JSON_EXISTS/path conditions or JSON_QUERY with appropriate error/empty clauses.

### 8.4. Checking Business Rules

For example, total must be non-negative:

~~~sql
SELECT order_id
FROM order_json_lab
WHERE JSON_VALUE(
          payload,
          '$.total' RETURNING NUMBER NULL ON ERROR
      ) < 0;
~~~

IS JSON does not replace data type rules, value domains, required fields, or cross-field relationships.

### 8.5. Validation at the Right Layer

A typical design combines:

- IS JSON STRICT to validate syntax.
- WITH UNIQUE KEYS to prohibit duplicate keys.
- NOT NULL to require a document.
- CHECK/JSON functions or application validation for shape rules.
- Relational columns and constraints for data requiring joins, indexes, foreign keys, or unique business keys.

Do not cram the entire relational model into a single JSON CLOB just because JSON is flexible.

## 9. Reading Stored JSON

Once data is stored and validated, Oracle SQL/JSON functions can query the content.

### 9.1. JSON_VALUE

Extract a scalar:

~~~sql
SELECT
    order_id,
    JSON_VALUE(payload, '$.status' RETURNING VARCHAR2(20)) AS status
FROM order_json_lab;
~~~

### 9.2. JSON_QUERY

Extract an object or array:

~~~sql
SELECT JSON_QUERY(payload, '$.items' RETURNING CLOB)
FROM order_json_lab;
~~~

JSON_QUERY is suitable when the path result is a JSON object/array. You can specify wrapper/empty/error behavior according to the release's SQL/JSON syntax.

### 9.3. JSON_EXISTS

Check whether a property/path exists:

~~~sql
SELECT order_id
FROM order_json_lab
WHERE JSON_EXISTS(payload, '$.items');
~~~

### 9.4. JSON_TABLE

Transform JSON into relational rows/columns:

~~~sql
SELECT
    o.order_id,
    j.product_id,
    j.quantity
FROM order_json_lab o,
     JSON_TABLE(
         o.payload,
         '$.items[*]'
         COLUMNS (
             product_id NUMBER PATH '$.productId',
             quantity NUMBER PATH '$.quantity'
         )
     ) j;
~~~

JSON_TABLE is useful when a JSON array contains multiple elements and needs to be joined/filtered/aggregated using SQL.

### 9.5. Using JSON Functions Does Not Eliminate the Role of IS JSON

JSON_VALUE/JSON_QUERY/JSON_TABLE have their own error handling. When data is protected by an IS JSON constraint, these functions can rely on valid syntax. Without a constraint, each query must decide ON ERROR/ON EMPTY and how to handle malformed payloads.

## 10. Indexes and Performance When Storing JSON

Storing JSON in CLOB/BLOB does not mean every path query is as fast as querying a relational column with a B-tree index.

### 10.1. Function-Based Index on JSON_VALUE

If you frequently filter by a scalar field:

~~~sql
CREATE INDEX ix_order_json_status_lab
ON order_json_lab (
    JSON_VALUE(payload, '$.status' RETURNING VARCHAR2(20))
);
~~~

Corresponding query:

~~~sql
SELECT order_id
FROM order_json_lab
WHERE JSON_VALUE(
          payload,
          '$.status' RETURNING VARCHAR2(20)
      ) = 'PAID';
~~~

The expression in the query should match the index definition and return type. Inspect the execution plan to confirm the optimizer uses the index.

### 10.2. JSON Search Index

Oracle supports JSON search indexes for flexible searching across JSON content:

~~~sql
CREATE SEARCH INDEX ix_order_json_search_lab
ON order_json_lab(payload)
FOR JSON;
~~~

A search index suits varied paths/filters, but incurs storage, DML maintenance, and indexing overhead. Do not create this index if the workload only queries a single simple field; consider a function-based index or relational projection instead.

### 10.3. Relational Columns for Frequently Queried Fields

If STATUS, CUSTOMER_ID, or CREATED_AT is always used for joining/filtering/sorting, you can also store it in relational columns:

~~~sql
CREATE TABLE order_document_lab (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    status VARCHAR2(20) NOT NULL,
    payload CLOB NOT NULL,
    CONSTRAINT ck_order_document_json_lab
        CHECK (payload IS JSON STRICT)
);

CREATE INDEX ix_order_document_customer_lab
ON order_document_lab(customer_id);
~~~

Keep key fields as columns with explicit types and constraints, while JSON holds flexible extensions. Ensure duplicated values between relational columns and JSON stay synchronized.

### 10.4. Choosing a Storage Type Does Not Replace Index Design

VARCHAR2, CLOB, and BLOB determine how payloads are stored. Query performance also depends on:

- Path expressions.
- Document count and document size.
- Predicate selectivity.
- Function-based/search indexes.
- Optimizer statistics.
- INSERT/UPDATE frequency.
- LOB storage and buffer/cache behavior.

Benchmark using realistic workloads rather than choosing BLOB/CLOB assuming one is always faster.

## 11. BLOB JSON and UTF-8

BLOB stores bytes, so the client and database must agree on the encoding.

### 11.1. UTF-8 Is a Critical Requirement

JSON in BLOB must be UTF-8 encoded. If a client sends data in another encoding and stores the raw bytes directly, Oracle may fail to recognize valid JSON or characters may become corrupted.

With ASCII-only content, ASCII bytes have the same values in UTF-8, so simple examples may appear to work. With Vietnamese, emojis, and non-ASCII characters, you must explicitly encode as AL32UTF8.

### 11.2. Writing BLOB with PL/SQL

Example creating a temporary BLOB, writing UTF-8 bytes, then inserting:

~~~sql
DECLARE
    l_blob BLOB;
    l_raw  RAW(32767);
    l_text VARCHAR2(1000) :=
        '{"message":"Hello","status":"NEW"}';
BEGIN
    l_raw := UTL_I18N.STRING_TO_RAW(l_text, 'AL32UTF8');

    DBMS_LOB.CREATETEMPORARY(l_blob, TRUE);
    DBMS_LOB.WRITE(
        l_blob,
        UTL_RAW.LENGTH(l_raw),
        1,
        l_raw
    );

    INSERT INTO binary_json_text_lab(document_id, payload)
    VALUES (1, l_blob);

    COMMIT;
    DBMS_LOB.FREETEMPORARY(l_blob);
END;
/
~~~

This example assumes the BINARY_JSON_TEXT_LAB table has been created with a PAYLOAD BLOB column having an IS JSON constraint. For payloads larger than the RAW single-write limit, split into multiple chunks or use streaming LOB APIs/drivers.

### 11.3. Reading BLOB JSON

When querying JSON in BLOB, Oracle SQL/JSON functions can process BLOB according to supported JSON and encoding rules. Do not blindly cast BLOB to a short VARCHAR2 if the payload may exceed the limit or contain multi-byte characters.

### 11.4. Client Drivers

Java/JDBC, .NET, Python, or OCI applications must bind the appropriate LOB/binary type:

- CLOB: bind the appropriate character stream/Clob.
- BLOB: bind a binary stream/Blob containing UTF-8 bytes.
- VARCHAR2: bind a string of appropriate length.

Validate encoding at the application boundary; do not assume the database automatically repairs wrongly encoded bytes.

## 12. Oracle Native JSON Type and Version Differences

### 12.1. Oracle 19c

In Oracle Database 19c, JSON is typically stored in VARCHAR2, CLOB, or BLOB. You can use IS JSON constraints to validate content and SQL/JSON functions to query it.

Example:

~~~sql
CREATE TABLE json_19c_lab (
    id NUMBER PRIMARY KEY,
    doc CLOB NOT NULL,
    CONSTRAINT ck_json_19c_lab CHECK (doc IS JSON STRICT)
);
~~~

### 12.2. Oracle 21c and Later

Oracle Database 21c introduced the native JSON data type. This type stores JSON in the OSON binary format optimized by Oracle for JSON processing. It is a true database-level JSON data type, distinct from a BLOB containing UTF-8 JSON text.

Conceptual example on a supported release:

~~~sql
CREATE TABLE native_json_lab (
    id NUMBER PRIMARY KEY,
    doc JSON
);
~~~

Do not run this DDL on Oracle 19c; 19c does not have the native SQL JSON data type shown in this example.

### 12.3. OSON vs. BLOB

| Characteristic | BLOB Containing JSON Text | Native JSON |
| --- | --- | --- |
| Storage | UTF-8 bytes of JSON text | Binary OSON |
| Format | Encoded JSON text | Optimized internal format |
| Direct text reading | Can be decoded from UTF-8 | Not treated as plain JSON text |
| Version | Supported in 19c | From 21c |
| Goal | Store text payload as bytes | Optimize native JSON storage/processing |

Do not call every BLOB column containing JSON "OSON". BLOB JSON text must still comply with UTF-8 and IS JSON.

### 12.4. Oracle 23c/23ai

Oracle Database 23c, marketed as Oracle Database 23ai, continues supporting native JSON and adds SQL/JSON capabilities. Syntax, JSON schema validation, JSON relational duality, and new features may depend on the release/RU. When portability is needed, check version documentation rather than inferring from data type names.

### 12.5. Migration Roadmap

When upgrading from 19c:

1. Inventory existing JSON columns and the ratio of VARCHAR2/CLOB/BLOB.
2. Check IS JSON constraints and strict/lax policies.
3. Verify whether client drivers support the native JSON data type.
4. Benchmark workloads on the new release.
5. Determine whether migrating to native JSON brings benefits or if continuing with LOBs makes more sense.
6. Prepare migration/rollback plans and test application compatibility.

Do not convert every JSON CLOB to native JSON just because the new type exists; measure the benefits and verify application compatibility.

## 13. Managing Constraints in the Data Dictionary

### 13.1. Viewing CHECK Constraints

~~~sql
SELECT
    constraint_name,
    table_name,
    status,
    validated,
    search_condition
FROM user_constraints
WHERE constraint_type = 'C'
ORDER BY table_name, constraint_name;
~~~

USER_CONSTRAINTS shows ENABLE/DISABLE and VALIDATED/NOVALIDATED status. SEARCH_CONDITION has a dictionary data type that depends on the release; for long queries, use an appropriate view/column such as SEARCH_CONDITION_VC if available.

### 13.2. Viewing Columns and Data Types

~~~sql
SELECT
    table_name,
    column_name,
    data_type,
    data_length,
    char_length,
    nullable
FROM user_tab_columns
WHERE table_name IN (
    'ORDER_JSON_LAB',
    'DOCUMENT_JSON_LAB',
    'BINARY_JSON_TEXT_LAB'
)
ORDER BY table_name, column_id;
~~~

### 13.3. Viewing Constraints by Table

~~~sql
SELECT
    constraint_name,
    constraint_type,
    status,
    validated
FROM user_constraints
WHERE table_name = 'ORDER_JSON_LAB';
~~~

### 13.4. Checking Invalid Rows Before Enabling a Constraint

~~~sql
SELECT COUNT(*) AS invalid_count
FROM legacy_json_lab
WHERE payload IS NOT NULL
  AND payload IS NOT JSON STRICT WITH UNIQUE KEYS;
~~~

If INVALID_COUNT is non-zero, clean up the data before running ENABLE VALIDATE.

## 14. Common Errors

| Error/Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| ORA-02290 | INSERT/UPDATE violates IS JSON CHECK constraint | Check payload, strict/lax mode, and duplicate keys |
| ORA-01400 | JSON column declared NOT NULL received SQL NULL | Supply a document or handle missing-payload cases |
| ORA-12899 | JSON exceeds VARCHAR2 limit | Switch to CLOB/BLOB or design smaller payloads |
| IS JSON returns FALSE | Content violates syntax under the active mode | Check quotes, escapes, commas, and encoding |
| Valid JSON but application fails | Syntax is valid but missing fields/wrong type/business rule violation | Add shape and business validation |
| Duplicate keys are accepted | Constraint does not use WITH UNIQUE KEYS | Add unique-key policy after cleaning up data |
| BLOB rejects JSON | Bytes are not UTF-8 or payload is invalid | Encode explicitly as AL32UTF8 and verify bytes |
| Adding constraint fails | Historical data violates rule | Find invalid rows, clean up, then validate |
| ENABLE NOVALIDATE still has bad legacy data | NOVALIDATE does not re-check all existing data | Clean up data and run ENABLE VALIDATE |
| JSON_VALUE returns NULL | Missing field, JSON null, or conversion error under ON ERROR | Use JSON_EXISTS/JSON_QUERY and error clauses to distinguish |
| Slow JSON queries | Missing appropriate index or high scan/LOB cost | Check plan, function-based index, JSON search index, or relational columns |
| Native JSON DDL fails on 19c | Native JSON data type does not exist in 19c | Use VARCHAR2/CLOB/BLOB on 19c |

## 15. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| A column named JSON_PAYLOAD automatically validates JSON | Must use IS JSON or other validation |
| IS JSON validates business rules | It validates JSON syntax |
| CHECK IS JSON automatically prohibits SQL NULL | CHECK evaluates to UNKNOWN for NULL; use NOT NULL |
| JSON null and SQL NULL are the same | JSON null is a value inside the document; SQL NULL is the absence of a column value |
| IS JSON always defaults to strict | Oracle defaults to lax if STRICT is not specified |
| IS JSON implies unique object keys | Requires WITH UNIQUE KEYS if policy demands it |
| WITH UNIQUE KEYS creates a unique key across rows | It checks duplicate field names within an object, not a relational unique constraint |
| BLOB JSON is OSON | BLOB may simply contain UTF-8 JSON text |
| CLOB is always faster than BLOB | Performance depends on workload, encoding, LOB access, and indexes |
| VARCHAR2 can always store large JSON | Subject to STANDARD/EXTENDED limits |
| ENABLE NOVALIDATE verifies all legacy data | It enforces new DML without validating all existing rows |
| JSON_VALUE replaces IS JSON constraints | The function extracts data; constraints protect all write paths |
| Oracle 19c has a native JSON data type | The native JSON data type was introduced in 21c |

## 16. Type and Validation Policy Checklist

**Storage Type**

- Is the payload small with a clear bound suitable for VARCHAR2?
- Do you need to store large JSON text as CLOB?
- Does the application already have UTF-8 bytes and need BLOB?
- Does the database version support the native JSON type?
- Does the driver bind the correct data type/LOB?

**Validation**

- Is strict JSON required?
- Are duplicate object keys prohibited?
- Must the column be NOT NULL?
- Do you need to validate required fields, data types, and business values?
- Has legacy data been checked before adding constraints?
- Is the constraint ENABLE VALIDATE or ENABLE NOVALIDATE?

**Querying**

- Which fields are frequently filtered/joined/sorted?
- Should those fields be extracted into relational columns?
- Is a function-based index or JSON search index needed?
- Have you reviewed execution plans and run benchmarks?

**Operations**

- Is there a workflow for handling malformed upstream payloads?
- Are validation errors logged without exposing secrets?
- Is UTF-8 encoding verified at the BLOB boundary?
- Is there a migration plan when upgrading from 19c to 21c/23ai?

## 17. Comprehensive Hands-On Lab

This lab creates three tables to compare storage types, apply IS JSON, and read JSON using SQL/JSON functions.

### Step 1 — VARCHAR2

~~~sql
CREATE TABLE json_varchar_lab (
    id NUMBER PRIMARY KEY,
    payload VARCHAR2(4000 BYTE) NOT NULL,
    CONSTRAINT ck_json_varchar_lab
        CHECK (payload IS JSON STRICT WITH UNIQUE KEYS)
);

INSERT INTO json_varchar_lab(id, payload)
VALUES (
    1,
    '{"customerId":501,"status":"NEW","total":125.50}'
);
~~~

### Step 2 — CLOB

~~~sql
CREATE TABLE json_clob_lab (
    id NUMBER PRIMARY KEY,
    payload CLOB NOT NULL,
    CONSTRAINT ck_json_clob_lab
        CHECK (payload IS JSON STRICT WITH UNIQUE KEYS)
);

INSERT INTO json_clob_lab(id, payload)
VALUES (
    1,
    '{"customerId":501,"status":"NEW","items":[{"productId":101,"qty":2}]}'
);
~~~

### Step 3 — BLOB

~~~sql
CREATE TABLE json_blob_lab (
    id NUMBER PRIMARY KEY,
    payload BLOB NOT NULL,
    CONSTRAINT ck_json_blob_lab
        CHECK (payload IS JSON STRICT WITH UNIQUE KEYS)
);
~~~

Write a UTF-8 payload:

~~~sql
DECLARE
    l_blob BLOB;
    l_raw RAW(32767);
    l_text VARCHAR2(1000) :=
        '{"customerId":501,"status":"NEW","note":"Hello"}';
BEGIN
    l_raw := UTL_I18N.STRING_TO_RAW(l_text, 'AL32UTF8');
    DBMS_LOB.CREATETEMPORARY(l_blob, TRUE);
    DBMS_LOB.WRITE(l_blob, UTL_RAW.LENGTH(l_raw), 1, l_raw);

    INSERT INTO json_blob_lab(id, payload)
    VALUES (1, l_blob);

    COMMIT;
    DBMS_LOB.FREETEMPORARY(l_blob);
END;
/
~~~

### Step 4 — Test Invalid Data

~~~sql
INSERT INTO json_varchar_lab(id, payload)
VALUES (2, '{"customerId":502,status:"NEW"}');
~~~

The statement should be rejected because the payload is not strict JSON.

### Step 5 — Test Duplicate Keys

~~~sql
INSERT INTO json_clob_lab(id, payload)
VALUES (
    2,
    '{"customerId":502,"status":"NEW","status":"PAID"}'
);
~~~

The statement should be rejected due to the WITH UNIQUE KEYS constraint.

### Step 6 — Read JSON

~~~sql
SELECT
    id,
    JSON_VALUE(payload, '$.status' RETURNING VARCHAR2(20)) AS status,
    JSON_VALUE(payload, '$.customerId' RETURNING NUMBER) AS customer_id
FROM json_varchar_lab;
~~~

### Step 7 — Check Constraint Status

~~~sql
SELECT constraint_name, status, validated
FROM user_constraints
WHERE table_name IN (
    'JSON_VARCHAR_LAB',
    'JSON_CLOB_LAB',
    'JSON_BLOB_LAB'
)
ORDER BY table_name, constraint_name;
~~~

### Step 8 — Clean Up Lab (Optional)

~~~sql
DROP TABLE json_varchar_lab PURGE;
DROP TABLE json_clob_lab PURGE;
DROP TABLE json_blob_lab PURGE;
~~~

Run only if you are sure the tables belong to the lab and the data is no longer needed. DROP is DDL with an implicit commit.

## Self-Check Questions

1. Which data types can store JSON in Oracle 19c?
2. When should you choose VARCHAR2?
3. What are the VARCHAR2 SQL limits with MAX_STRING_SIZE STANDARD and EXTENDED?
4. How do BYTE and CHAR semantics differ?
5. What encoding is required when storing JSON in BLOB?
6. How does CLOB differ from BLOB in terms of stored data format?
7. What does IS JSON check?
8. Does IS JSON automatically fix syntactically invalid JSON?
9. How do strict and lax syntax differ?
10. Which mode does Oracle use by default if STRICT/LAX is not specified?
11. What problem does WITH UNIQUE KEYS solve?
12. Does WITH UNIQUE KEYS create a unique constraint on data across rows?
13. Why should CHECK IS JSON be combined with NOT NULL?
14. How does SQL NULL differ from JSON null?
15. Does IS NOT JSON return rows with SQL NULL?
16. How does ENABLE NOVALIDATE differ from ENABLE VALIDATE?
17. Does IS JSON validate required fields and business rules?
18. How do JSON_VALUE and JSON_QUERY differ?
19. What is JSON_TABLE used for?
20. When should you consider a function-based index on JSON_VALUE?
21. What kind of queries does a JSON search index suit?
22. Why shouldn't you store every frequently joined/filtered field solely inside JSON?
23. In which version did Oracle's native JSON data type appear?
24. How does BLOB JSON text differ from native JSON OSON?
25. What needs to be checked when migrating from 19c to 21c/23ai?

**Answer Key:**

1. VARCHAR2, CLOB, and BLOB.
2. When documents are small, have bounded size, and clients handle strings conveniently.
3. STANDARD typically up to 4000 bytes; EXTENDED up to 32767 bytes, depending on declaration and character set.
4. BYTE limits by bytes; CHAR limits by characters while still subject to the data type's byte limit.
5. UTF-8.
6. CLOB stores character data; BLOB stores bytes.
7. JSON syntax according to the specified mode.
8. No.
9. Strict follows standard JSON; lax allows certain extensions accepted by Oracle.
10. Lax.
11. Prevents duplicate field names within an object.
12. No; it is not a relational unique constraint.
13. CHECK evaluates to UNKNOWN for SQL NULL and does not reject the row; NOT NULL requires a value.
14. JSON null resides inside the document; SQL NULL is the absence of a column value.
15. No; conditions on SQL NULL evaluate to UNKNOWN.
16. NOVALIDATE enforces new data without verifying all existing rows; VALIDATE checks existing data.
17. No; separate shape and business validation is required.
18. JSON_VALUE extracts a scalar; JSON_QUERY extracts an object/array or JSON fragment.
19. Converts a JSON structure into rows/columns for SQL use.
20. When a scalar path is frequently filtered and the expression matches.
21. Flexible searches across multiple paths/fields in JSON.
22. Because relational columns provide clearer typing, constraints, joins, and indexing.
23. Oracle Database 21c.
24. BLOB contains UTF-8 JSON text; native JSON stores binary OSON.
25. Client/driver support, data type support, constraints, workload, migration, and rollback plan.

## Oracle Reference Documentation

- [Oracle Database JSON Developer's Guide — JSON Data Types and Storage](https://docs.oracle.com/en/database/oracle/oracle-database/19/adjsn/json-data-types.html): storing JSON in VARCHAR2, CLOB, and BLOB.
- [Oracle Database SQL Language Reference — JSON Condition](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SQL-JSON-Conditions.html): IS JSON, strict/lax, and unique keys.
- [Oracle Database JSON Developer's Guide — JSON Constraints](https://docs.oracle.com/en/database/oracle/oracle-database/19/adjsn/creating-a-table-with-a-json-column.html): CHECK constraints to ensure valid JSON.
- [Oracle Database SQL Language Reference — JSON_VALUE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/JSON_VALUE.html): extracting scalars from JSON.
- [Oracle Database SQL Language Reference — JSON_QUERY](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/JSON_QUERY.html): extracting objects/arrays.
- [Oracle Database SQL Language Reference — JSON_TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/JSON_TABLE.html): mapping JSON to rows and columns.
- [Oracle Database SQL Language Reference — JSON_EXISTS](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/JSON_EXISTS.html): checking path existence.
- [Oracle Database JSON Developer's Guide — JSON Search Index](https://docs.oracle.com/en/database/oracle/oracle-database/19/adjsn/indexes-for-json-data.html): indexes for JSON queries.
- [Oracle Database 21c JSON Developer's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/21/adjsn/): native JSON data type and OSON.

**Key takeaway:** VARCHAR2 fits small JSON; CLOB stores large text JSON; BLOB stores JSON bytes in UTF-8. Use IS JSON to protect syntax, STRICT to require standard JSON, WITH UNIQUE KEYS to prohibit duplicate object keys, and NOT NULL to require a document. IS JSON does not validate business structure. Oracle 19c uses VARCHAR2/CLOB/BLOB; the native JSON type with OSON starts in 21c. Choose the storage type based on payload and workload, inspect legacy data before enabling constraints, and measure query performance with appropriate SQL/JSON functions and indexes.
