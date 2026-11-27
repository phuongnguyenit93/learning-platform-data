# Native JSON Type, Validation, and Storage Structure

MySQL provides a native `JSON` data type to store JSON documents in a column with automatic syntax checking. When writing to a JSON column, MySQL parses the input value, rejects invalid documents, and stores the content in an internal binary JSON format rather than keeping the raw text string like a regular `TEXT` column.

The JSON type is suitable when part of the data has a flexible structure, such as webhook payloads, extended attributes, or metadata that varies by event type. Important attributes frequently used for JOINs, filtering, sorting, or constraints should be considered for storage as strongly typed relational columns. JSON does not replace the relational model; it complements it with a storage mechanism for variable-structure data.

This lesson focuses on the native JSON type, valid syntax, differences between JSON and TEXT, distinguishing SQL `NULL` from JSON `null`, how MySQL normalizes and stores binary JSON, size-inspection tools, and the limits to consider when designing tables.

## 1. JSON as a Native Data Type in MySQL

MySQL has supported the `JSON` type since MySQL 5.7.8. It is a data type with JSON semantics, not merely an alias for `VARCHAR` or `TEXT`.

When declared as:

```sql
CREATE TABLE webhook_events (
    event_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    event_type VARCHAR(100) NOT NULL,
    payload JSON NOT NULL,
    received_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (event_id)
) ENGINE=InnoDB;
```

the `payload` column accepts only values with valid JSON syntax. MySQL parses the content on write and stores the value in an internal binary JSON representation. Applications can still send JSON as a string over the SQL protocol; converting that string to the JSON type happens when MySQL processes the value for the column.

The JSON type supports JSON value types such as object, array, string, number, boolean, and JSON `null`. Not every document is required to have an object root, unless the application schema or a table constraint enforces it.

## 2. What Structures Make Up a JSON Document?

JSON has six basic value categories:

| Type | Example | Meaning |
| --- | --- | --- |
| Object | `{"id": 10, "name": "Lan"}` | Collection of key/value pairs |
| Array | `["mysql", "sql", "json"]` | Ordered list |
| String | `"payment.created"` | Unicode string enclosed in double quotes |
| Number | `42`, `19.95`, `-3` | Numeric value |
| Boolean | `true`, `false` | Logical value |
| Null | `null` | Empty value according to JSON |

Example of a nested object:

```json
{
  "eventType": "payment.created",
  "eventId": "evt_1001",
  "occurredAt": "2026-11-19T09:30:00Z",
  "attempt": 1,
  "test": false,
  "customer": {
    "id": 42,
    "region": "VN"
  },
  "tags": ["checkout", "card"],
  "metadata": null
}
```

JSON objects have string keys; keys and string values must use double quotes. Number, boolean, and null values are not placed in quotes if you want to preserve their JSON types. For example, `"attempt": "1"` is a string, whereas `"attempt": 1` is a number.

## 3. Creating a JSON Column and Writing Valid Data

Example table creation:

```sql
CREATE TABLE integration_messages (
    message_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    source VARCHAR(80) NOT NULL,
    message_type VARCHAR(100) NOT NULL,
    payload JSON NOT NULL,
    received_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (message_id),
    KEY idx_messages_type_time (message_type, received_at)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4;
```

Writing a JSON object:

```sql
INSERT INTO integration_messages (source, message_type, payload)
VALUES (
    'billing-service',
    'payment.created',
    '{"paymentId":"pay_9001","amount":125000,"currency":"VND"}'
);
```

Writing an array or scalar is also syntactically valid JSON:

```sql
INSERT INTO integration_messages (source, message_type, payload)
VALUES
    ('catalog-service', 'catalog.tags', '["database", "mysql"]'),
    ('system', 'system.flag', 'true'),
    ('system', 'system.note', '"maintenance"');
```

In application design, standardize on an object root document if the payload represents an entity/event with multiple attributes. Choose a root array/scalar only when the data contract genuinely requires it and all consumers clearly understand that structure.

## 4. MySQL Checks JSON Syntax on Write

If a string that is not valid JSON is assigned to a JSON column, the write statement is rejected:

```sql
INSERT INTO integration_messages (source, message_type, payload)
VALUES ('legacy-client', 'broken.event', '{"id": 1,}');
```

The snippet above is invalid because of a trailing comma before the closing brace of the object. MySQL raises a JSON conversion/parse error (typically error 3140, `Invalid JSON text`) and does not write the invalid value into the JSON column.

Some common syntax errors:

```text
{"name": 'Lan'}          -- JSON strings must use double quotes
{"enabled": True}        -- JSON booleans are lowercase true/false
{"value": undefined}     -- JSON does not have undefined
{"items": [1, 2,]}       -- no trailing comma at the end of an array
{id: 10}                  -- keys must be strings in double quotes
```

Having the JSON column automatically check syntax protects data against any client writing to the table, including clients that do not use Java or bypass application-tier validation.

## 5. JSON_VALID(): Checking JSON Strings Before Storage

`JSON_VALID()` checks whether a value has a valid JSON representation:

```sql
SELECT JSON_VALID('{"id": 10, "active": true}') AS is_valid;
-- 1

SELECT JSON_VALID('{"id": 10,}') AS is_valid;
-- 0

SELECT JSON_VALID(NULL) AS is_valid;
-- NULL
```

Results:

- `1`: the value is valid JSON.
- `0`: the value is not valid JSON.
- `NULL`: the SQL input is `NULL`.

`JSON_VALID()` is useful when data is currently stored in `VARCHAR`/`TEXT`, when importing legacy data, or when checking before a conversion operation. For a native JSON column, MySQL has already validated syntax on write; calling `JSON_VALID(payload)` again is usually unnecessary to prove the value in the column is still valid.

## 6. Valid JSON Syntax Differs from Valid Business Structure

A document can be syntactically valid JSON yet fail to meet the business contract:

```json
{"amount": "a lot", "currency": 123}
```

This is syntactically valid JSON, but it may violate the contract if `amount` must be a number and `currency` must be a currency-code string.

Three validation layers must be distinguished:

1. **JSON syntax:** whether brackets, commas, quotes, and literals conform to JSON. The native JSON column checks this layer automatically.
2. **Structure/schema:** whether the root is an object, whether required attributes exist, and whether each attribute has the right type.
3. **Business rules:** positive amounts, status within the allowed set, existing tenant ID, valid timestamps, and logical relationships between fields.

Do not assume that a `JSON` column understands the entire business schema on its own. Structural and business validation must be designed separately in the application, via constraints, or with a JSON Schema mechanism appropriate for the version.

## 7. JSON_SCHEMA_VALID() in MySQL 8.0.17+

MySQL 8.0.17 added `JSON_SCHEMA_VALID()` and `JSON_SCHEMA_VALIDATION_REPORT()` to validate documents against JSON Schema (supporting JSON Schema Draft 4). Example:

```sql
SET @payment_schema = '{
  "$schema": "http://json-schema.org/draft-04/schema#",
  "type": "object",
  "required": ["paymentId", "amount", "currency"],
  "properties": {
    "paymentId": {"type": "string"},
    "amount": {"type": "number", "minimum": 0},
    "currency": {"type": "string", "minLength": 3, "maxLength": 3}
  },
  "additionalProperties": false
}';

SELECT JSON_SCHEMA_VALID(
    @payment_schema,
    '{"paymentId":"pay_9001","amount":125000,"currency":"VND"}'
) AS schema_valid;
```

`JSON_SCHEMA_VALID()` returns `1` if the document satisfies the schema and `0` if it does not. `JSON_SCHEMA_VALIDATION_REPORT()` provides a more detailed report on validation errors.

JSON Schema helps validate types, required properties, bounds, and nested structures. It does not replace business rules that need to query the database or call other services. If the system runs MySQL earlier than 8.0.17, do not assume these two functions exist; validate the schema in the application or use an appropriate compatible mechanism.

## 8. CHECK Constraints for Simple Rules

MySQL has enforced `CHECK` constraints since version 8.0.16. Before this version, CHECK syntax was accepted, but the constraint was not enforced as expected.

Example requiring the JSON root to be an object:

```sql
CREATE TABLE object_documents (
    document_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    payload JSON NOT NULL,
    PRIMARY KEY (document_id),
    CONSTRAINT chk_payload_is_object
        CHECK (JSON_TYPE(payload) = 'OBJECT')
) ENGINE=InnoDB;
```

The JSON column checks syntax automatically; the CHECK constraint here additionally verifies that the root value must have type `OBJECT`. A JSON array or scalar, even if syntactically valid, is still rejected by the constraint.

CHECK is suitable for local, deterministic rules on the same row. Do not use it to replace checks that need to query other tables, call routines, or apply complex logic. When supporting multiple MySQL versions, verify the version enforcing CHECK before relying on the constraint.

## 9. Differences Between a JSON Column and a TEXT Column

| Criterion | `JSON` Type | `TEXT`/`LONGTEXT` Storing JSON |
| --- | --- | --- |
| Syntax check on write | MySQL parses automatically and rejects invalid JSON | Does not validate JSON automatically |
| Storage representation | Internal binary JSON format | Character string according to the column's charset/collation |
| Component access | JSON functions work on parsed JSON values | Often requires parsing/converting the string before JSON processing |
| Normalization | MySQL normalizes the document when parsing/storing | Original string may preserve whitespace/key order as entered |
| Purpose | Data requiring JSON semantics in the database | Storing verbatim payload, archiving, or legacy compatibility |
| Schema validation | Can combine with JSON Schema/constraints | Requires separate validation; can add CHECK JSON_VALID on supported versions |

If a `TEXT` column is used as a JSON store, a constraint can be added:

```sql
CREATE TABLE legacy_payloads (
    payload_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    raw_payload LONGTEXT NOT NULL,
    PRIMARY KEY (payload_id),
    CONSTRAINT chk_raw_payload_json
        CHECK (JSON_VALID(raw_payload))
) ENGINE=InnoDB;
```

The constraint above is only enforced starting in MySQL 8.0.16. On older versions, validation must be done in the application or an appropriate trigger; do not rely on an ignored CHECK constraint.

Use TEXT when the goal is to preserve the exact payload bytes/string per the storage contract or for legacy system compatibility. Use JSON when you want MySQL to understand, validate, and process the data as a JSON document.

## 10. Binary JSON Storage Structure

MySQL does not store a native JSON column as an intact plain-text JSON string. Upon receiving a value, the server parses the document and converts it into an internal binary JSON representation.

Conceptually, this representation contains information allowing MySQL to recognize value types and locate components:

- Objects/arrays contain structural information and element counts.
- Objects have keys and values; keys are represented alongside position/length information.
- Arrays preserve element order and element-location information.
- Values carry a type tag to distinguish string, number, literal, object, or array.
- Offsets/lengths enable accessing components without scanning and re-parsing the entire text string from the beginning as TEXT requires.

The binary format is designed for more efficient component access. It is a MySQL internal format; applications should not manually parse internal JSON bytes or depend on a specific layout across versions.

## 11. How Objects and Arrays Are Organized in Binary JSON

A JSON object is a set of key/value pairs. The binary representation must store keys, value types, and value positions so attributes can be looked up by key. An array stores values in order, along with the information needed to access elements by index.

An object:

```json
{
  "customerId": 42,
  "region": "VN",
  "verified": true
}
```

and an array:

```json
[42, "VN", true]
```

are represented with different structures because an object must manage key names while an array only needs element positions. MySQL uses internal types and offsets to support access; do not assume each component is stored as an independent string.

The benefit is that JSON functions can access part of a document without the application having to deserialize the entire payload itself. However, JSON access still incurs CPU cost, operations on large documents can consume significant resources, and queries filtering by frequent attributes need proper column/index design.

## 12. MySQL Normalizes JSON on Parse

When a document is parsed into a JSON value, MySQL may normalize its representation, including removing insignificant whitespace and sorting object keys according to internal rules. If an input object has duplicate keys, MySQL keeps the last value of the duplicate key during normalization.

For example, the input:

```json
{"status":"pending", "status":"paid", "amount":100}
```

should not be used as a way to represent multiple values for the same attribute. After parsing, duplicate key values are not preserved as a list of repeated key pairs; the last value is retained.

Because normalization can change how the document looks compared to the original string:

- Do not rely on key order when comparing JSON objects.
- Do not use whitespace or formatting to determine whether two documents differ.
- Do not send objects with duplicate keys; check and reject them in the producer/serializer.
- If you must keep the verbatim request for legal compliance or digital signatures, store the raw payload separately in a binary/text column alongside the parsed JSON column.

## 13. JSON Objects Are Not a Contract on Key Order

Semantically, a JSON object is an unordered set of name/value pairs; consumers should not rely on key order. MySQL may sort keys when normalizing the internal representation. Therefore, the read/serialized result may not keep the key order of the submitted string.

Arrays differ from objects: array element order is part of the data and must be preserved according to JSON semantics.

If an application digitally signs a payload based on original bytes, it must retain the exact raw bytes/string as received and define an explicit canonicalization algorithm. Do not sign the JSON string returned by MySQL assuming it matches the input bytes.

## 14. SQL NULL Differs from JSON null

These are two different values:

- SQL `NULL`: the column has no SQL value.
- JSON `null`: a valid JSON value inside the document.

Example:

```sql
CREATE TABLE nullable_json_examples (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    sql_null_doc JSON NULL,
    json_null_doc JSON NULL,
    PRIMARY KEY (id)
);

INSERT INTO nullable_json_examples (sql_null_doc, json_null_doc)
VALUES (NULL, 'null');
```

Check:

```sql
SELECT
    sql_null_doc IS NULL AS is_sql_null,
    json_null_doc IS NULL AS json_column_is_sql_null,
    JSON_TYPE(sql_null_doc) AS sql_null_type,
    JSON_TYPE(json_null_doc) AS json_value_type
FROM nullable_json_examples;
```

`sql_null_doc IS NULL` returns `1`; `json_null_doc IS NULL` returns `0`; `JSON_TYPE(json_null_doc)` returns the string `NULL` to indicate the JSON null type. `JSON_TYPE(sql_null_doc)` returns SQL NULL.

This difference affects filter conditions, defaults, validation, and how Java maps data. Decide clearly whether "no payload" means SQL NULL or a JSON payload with value null.

## 15. Checking Root Type with JSON_TYPE()

`JSON_TYPE()` returns the JSON type of a value:

```sql
SELECT JSON_TYPE('{"id": 1}') AS value_type; -- OBJECT
SELECT JSON_TYPE('[1, 2]') AS value_type;      -- ARRAY
SELECT JSON_TYPE('42') AS value_type;          -- INTEGER
SELECT JSON_TYPE('true') AS value_type;        -- BOOLEAN
SELECT JSON_TYPE('null') AS value_type;        -- NULL
```

This is useful when checking the root document before applying logic suitable only for objects or arrays. Example:

```sql
SELECT message_id
FROM integration_messages
WHERE JSON_TYPE(payload) = 'OBJECT';
```

Do not confuse the JSON string `"42"` with the JSON number `42`: the former has type `STRING`, while the latter has type `INTEGER` (or the appropriate numeric type for the value). The data type matters for comparisons and validation.

## 16. Measuring JSON Size with JSON_STORAGE_SIZE()

MySQL provides `JSON_STORAGE_SIZE()` to inspect the number of bytes used by a JSON representation:

```sql
SELECT
    message_id,
    JSON_STORAGE_SIZE(payload) AS json_storage_bytes
FROM integration_messages
ORDER BY message_id;
```

This function measures the size of the internal JSON representation of the value, not the size of the entire InnoDB row, indexes, page overhead, or bytes transferred over the network. When comparing against the length of the input JSON string, remember that the binary representation has its own metadata/offsets and normalization.

You can use `OCTET_LENGTH()` on a text JSON string to measure the byte count of the string:

```sql
SELECT OCTET_LENGTH('{"name":"Nguyễn An"}') AS input_bytes;
```

Do not compare those two numbers and conclude that binary JSON is always smaller than TEXT. The binary format is designed for efficient access; actual size depends on structure, keys, strings, numbers, and overhead.

## 17. JSON_STORAGE_FREE() and Partial Updates

Starting in MySQL 5.7.22, `JSON_STORAGE_FREE()` can report how much space has been freed inside a JSON value after certain eligible partial updates.

Illustrative example:

```sql
CREATE TABLE json_storage_lab (
    id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    doc JSON NOT NULL
) ENGINE=InnoDB;

INSERT INTO json_storage_lab (id, doc)
VALUES (1, '{"name":"Lan","description":"A long description for update test"}');

UPDATE json_storage_lab
SET doc = JSON_REMOVE(doc, '$.description')
WHERE id = 1;

SELECT
    JSON_STORAGE_SIZE(doc) AS storage_bytes,
    JSON_STORAGE_FREE(doc) AS free_bytes
FROM json_storage_lab
WHERE id = 1;
```

MySQL can optimize certain `JSON_SET()`, `JSON_REPLACE()`, or `JSON_REMOVE()` operations using partial in-place updates if engine/version conditions are met—such as modifying the JSON column directly and the new value fitting within the existing storage area. Not every modification is updated in place; changes that make the document larger or ineligible expressions may require rewriting the value.

`JSON_STORAGE_FREE()` is not a measure of InnoDB file space returned to the operating system. It describes free space within the JSON representation of the value after partial-update optimization. Do not use it as the sole metric to evaluate tablespace fragmentation.

## 18. JSON Storage in InnoDB and Large Documents

The JSON type is an SQL-layer data type; how it is stored on pages and records is also affected by InnoDB, row format, page size, and value size. Small documents may be stored inline with the record; large values may require off-page storage mechanisms similar to other large values. Do not assume all JSON always fits completely inline in the record or that all JSON is always stored off-page.

Design implications:

- Large JSON can increase I/O when queries fetch the full payload.
- `SELECT *` can pull unnecessary JSON data.
- Many large documents increase table size, backup size, and transfer time.
- Updating part of a document may still require parsing/validation and incur write cost.
- JSON documents should not become a place to stuff large binary files; use object storage or BLOB according to storage requirements.

If the application typically only needs `event_type`, `tenant_id`, `created_at`, and a few filter attributes, store those attributes as separate relational columns. JSON should hold extended metadata or genuinely flexible payloads.

## 19. Size Limits and max_allowed_packet

JSON document size is subject to packet/client/server mechanisms and processing resource limits. `max_allowed_packet` limits the packet size accepted by the server/client; the exact value depends on configuration and version.

Check:

```sql
SHOW VARIABLES LIKE 'max_allowed_packet';
```

When sending very large JSON, errors may occur in the client driver, packet protocol, server memory, or storage limits. Do not solve this by increasing `max_allowed_packet` indefinitely; evaluate whether large files/objects should be split out to object storage, batched, or streamed.

JSON size is not just character count. Unicode can occupy more bytes than the number of characters; the JSON binary representation also has metadata. Measure actual bytes and test with a production-like driver.

## 20. Charset, Unicode, and Strings in JSON

JSON text uses Unicode; MySQL processes JSON strings with a charset compatible with `utf8mb4`. Use `utf8mb4` for schemas/connections to fully support characters outside the BMP, Vietnamese characters, and emoji.

Example:

```sql
INSERT INTO integration_messages (source, message_type, payload)
VALUES (
    'profile-service',
    'profile.updated',
    '{"displayName":"Nguyễn Ánh 🌱","city":"Hồ Chí Minh"}'
);
```

Check connection and column charsets when data suffers from garbled diacritics or replacement characters. Do not fix strings by repeatedly encoding/decoding; establish the encoding cleanly at the application and connection boundaries.

## 21. Storing JSON via Java/JDBC

Java applications typically serialize an object to a JSON string using a JSON library and then bind the value to a JSON column via a prepared statement:

```java
String sql = "INSERT INTO integration_messages "
        + "(source, message_type, payload) VALUES (?, ?, ?)";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, "billing-service");
    statement.setString(2, "payment.created");
    statement.setString(3, jsonMapper.writeValueAsString(payload));
    statement.executeUpdate();
}
```

MySQL verifies that the bound string is valid JSON when assigning it to the `payload` column. Use parameter binding instead of concatenating JSON strings into SQL to avoid quoting issues and SQL injection.

In Java, avoid serializing monetary amounts as `double` when decimal precision is required; use `BigDecimal` and configure the serializer accordingly. Standardize timestamp representation (typically ISO-8601 with an explicit timezone/offset) and null/missing-field rules between producers and consumers.

## 22. Designing Relational Columns and JSON Together

A hybrid model is often effective:

```sql
CREATE TABLE webhook_events (
    event_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    occurred_at DATETIME(6) NOT NULL,
    payload JSON NOT NULL,
    received_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (event_id),
    KEY idx_webhook_tenant_type_time (tenant_id, event_type, occurred_at)
) ENGINE=InnoDB;
```

`tenant_id`, `event_type`, and `occurred_at` are relational columns because they are frequently needed for filtering, partitioning, aggregation, and indexing. `payload` holds the portion of content that varies by event type.

Do not put every attribute into JSON just for schema flexibility. If `tenant_id` lives only inside JSON, authorization, joins, indexing, and constraints become harder. Conversely, there is no need to create dozens of nullable columns for rare attributes that differ across event types when JSON is a better fit.

## 23. Indexing JSON Attributes Is a Separate Topic

Do not create a B-tree index directly on an entire JSON document as you would on an ordinary numeric/date column. When frequent filtering by a JSON attribute is needed, you can extract the scalar into a generated column and index that column, or use a functional index appropriate for the MySQL version.

Illustrative direction:

```sql
ALTER TABLE webhook_events
ADD COLUMN payload_customer_id BIGINT
    GENERATED ALWAYS AS (
        CAST(JSON_UNQUOTE(JSON_EXTRACT(payload, '$.customerId')) AS UNSIGNED)
    ) STORED,
ADD INDEX idx_webhook_customer (payload_customer_id);
```

This example merely illustrates the boundary between document storage and attribute indexing. You must check data types, missing/NULL values, unconvertible values, and cardinality/distribution before creating a generated column/index. JSON path optimization and indexing are covered in their dedicated lesson.

## 24. Common Mistakes and Misconceptions

| Misconception / Mistake | Reality | How to Handle |
| --- | --- | --- |
| JSON only accepts objects | MySQL accepts valid JSON values such as objects, arrays, and scalars | Use CHECK/JSON Schema if the root must be an object |
| A JSON column keeps the submitted string verbatim | MySQL parses and stores a binary representation, with normalization | Store raw payload separately if verbatim preservation is needed |
| JSON_VALID checks business rules | It checks JSON syntax | Use JSON Schema and business validation |
| JSON null is the same as SQL NULL | These are two distinct values | Use `IS NULL` and `JSON_TYPE()` appropriately |
| TEXT validates JSON automatically | TEXT only stores strings | Use a JSON column or CHECK JSON_VALID on supported versions |
| Binary JSON is always smaller than text | Binary format has metadata/offsets; size depends on content | Measure with JSON_STORAGE_SIZE and input bytes |
| Object key order is preserved | MySQL may normalize/sort keys | Do not depend on object key order |
| Duplicate keys are kept as multiple properties | MySQL normalizes and keeps the last value of duplicate keys | Reject duplicate keys at the producer |
| A JSON column understands business schema automatically | Native type only guarantees JSON syntax | Use CHECK, JSON_SCHEMA_VALID, and application validation |
| JSON documents have unlimited size | Packet, memory, and storage limits still apply | Control payload size and `max_allowed_packet` |
| JSON is the right place for every attribute | Frequently filtered/joined attributes should have relational columns | Use a hybrid relational + JSON model |

## 25. Workflow for Designing and Testing a JSON Column

1. Identify which data is genuinely flexible and which is stable relational attributes.
2. Choose the root type (usually object for events/entities) and document the payload schema.
3. Create a `JSON` column if you want MySQL to validate syntax and process JSON natively.
4. Use `NOT NULL` if the payload is required; distinguish SQL NULL from JSON null.
5. Use CHECK for simple constraints such as root type on MySQL 8.0.16+.
6. Use JSON Schema functions from MySQL 8.0.17+ when Draft 4 structural validation in the database is needed.
7. Validate business rules in the layer that owns the use case.
8. Do not send objects with duplicate keys and do not rely on key order.
9. Measure `JSON_STORAGE_SIZE()` and actual payload bytes; check `max_allowed_packet`.
10. Use `utf8mb4` and parameter binding on the client.
11. Move frequently filtered/joined attributes out to relational columns or appropriately indexed generated columns.
12. Test large data, NULL, JSON null, scalars, arrays, Unicode, and invalid payloads.

## 26. Practice Exercises

1. Create a table with a `JSON NOT NULL` column; insert an object, array, string, number, boolean, and JSON null.
2. Try inserting syntactically invalid JSON; record the MySQL error and verify no invalid row was saved.
3. Use `JSON_VALID()` to distinguish valid JSON, invalid JSON, and SQL NULL.
4. Create a TEXT table storing JSON; compare TEXT's self-validation capability with that of a JSON column.
5. On MySQL 8.0.16+, create a CHECK requiring the JSON root to be an OBJECT; try inserting an array and a scalar.
6. On MySQL 8.0.17+, use `JSON_SCHEMA_VALID()` to validate a payment payload; test missing required fields and wrong types.
7. Compare SQL NULL with JSON null using `IS NULL` and `JSON_TYPE()`.
8. Write an object with duplicate keys and observe the result after reading it back; explain why producers should not send duplicate keys.
9. Compare key order and whitespace of input JSON with the result MySQL returns.
10. Use `JSON_STORAGE_SIZE()` to measure short, long, multi-key, and multi-element array payloads.
11. Test `JSON_STORAGE_FREE()` after an eligible partial update; distinguish free space inside the document from tablespace space.
12. Store a payload containing Vietnamese text and emoji; verify connection/schema charsets.
13. Use Java/JDBC to bind a JSON string to a JSON column; test valid and invalid payloads.
14. Design a hybrid table with `tenant_id`, `event_type`, `occurred_at`, and `payload`; explain why primary filter columns should not reside solely inside JSON.

## 27. Key Takeaways

MySQL's native `JSON` type (since 5.7.8) automatically parses and validates syntax on write, then stores the document in an internal binary JSON representation. JSON can be an object, array, or scalar; if the business logic requires a root object or specific schema, add CHECK constraints (enforced from MySQL 8.0.16), JSON Schema functions (MySQL 8.0.17+), or application-level validation.

Binary JSON contains type and component-location metadata to support access; MySQL may normalize whitespace and object keys while retaining the last value on duplicate keys. Do not rely on key order or use a JSON column to preserve raw payload bytes verbatim. SQL NULL differs from JSON null; `JSON_VALID`, `JSON_TYPE`, `JSON_STORAGE_SIZE`, and `JSON_STORAGE_FREE` serve distinct checking/measurement purposes. Large documents are also subject to packet, memory, and InnoDB large-value storage limits. Design a hybrid model: relational columns for stable, frequently filtered/joined attributes; JSON for flexible payloads. Use `utf8mb4`, bind parameters, validate schemas, and measure sizes with realistic data.
