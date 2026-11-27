# Native JSON Data Type and Supported Version Differences

Oracle Database has supported JSON processing across multiple release generations. The most important milestone is the introduction of the **native SQL JSON data type** in Oracle Database 21c. Prior to this release, JSON was commonly stored as text in VARCHAR2, CLOB, or BLOB columns and validated with the `IS JSON` condition. Starting in 21c, you can declare a column with the `JSON` data type; Oracle stores the content in the OSON binary format for more efficient JSON processing.

When choosing how to store JSON, three concepts should be distinguished:

1. **Textual JSON:** JSON content stored in VARCHAR2, CLOB, or BLOB. Applications and SQL/JSON functions read that textual content.
2. **Native SQL JSON data type:** the `JSON` type introduced in Oracle Database 21c, which stores the OSON binary representation and guarantees column values are valid JSON.
3. **PL/SQL JSON object types:** such as `JSON_ELEMENT_T`, `JSON_OBJECT_T`, and `JSON_ARRAY_T`, used to parse and manipulate JSON structures in memory. These are programming APIs, not the native SQL JSON column type.

Understanding the distinction among these three concepts helps you choose the right column type, write queries compatible with your running version, and plan data upgrades.

## 1. Textual JSON Prior to Oracle Database 21c

In releases prior to 21c, Oracle did not have a dedicated SQL JSON data type. Applications stored JSON documents in a character or binary data type:

| Column Type | Usage | When Appropriate |
|---|---|---|
| VARCHAR2 | Stores textual JSON of bounded size | Small documents with controlled size |
| CLOB | Stores character-based JSON with large content | Large documents, Unicode text, and content needing character handling |
| BLOB | Stores JSON bytes, typically UTF-8 | Data received from other systems as bytes or when preserving byte representation |

To make Oracle validate whether a column's content is valid JSON, use the `IS JSON` condition in a CHECK constraint:

~~~sql
CREATE TABLE orders_text (
  order_id NUMBER PRIMARY KEY,
  payload  CLOB
    CONSTRAINT orders_payload_is_json
    CHECK (payload IS JSON)
);
~~~

If you need to enforce strict JSON syntax according to the JSON standard, you can use `IS JSON STRICT`:

~~~sql
CREATE TABLE customer_documents (
  customer_id NUMBER PRIMARY KEY,
  document    CLOB
    CONSTRAINT customer_document_json
    CHECK (document IS JSON STRICT)
);
~~~

Oracle defaults to accepting lax JSON syntax in many SQL/JSON contexts. Use `STRICT` when the system must validate content against strict JSON syntax. Keep this policy consistent across constraints, applications, and ingested external data.

Example inserting a JSON document:

~~~sql
INSERT INTO orders_text (order_id, payload)
VALUES (
  1001,
  '{"orderId":1001,"customer":"An","total":125.5,"status":"NEW"}'
);
~~~

If the string is not valid JSON per the constraint condition, the INSERT or UPDATE statement fails. The constraint prevents malformed data from entering the table even when written by another application.

### Querying Textual JSON

SQL/JSON functions allow reading and transforming data without manual string parsing:

- `JSON_VALUE`: retrieves a scalar value such as a string, number, or date converted to the return type.
- `JSON_QUERY`: retrieves a JSON object or array.
- `JSON_EXISTS`: checks whether a path matches the data.
- `JSON_TABLE`: projects JSON properties into relational columns and rows.

Example retrieving order ID, customer, and total amount:

~~~sql
SELECT order_id,
       JSON_VALUE(payload, '$.customer' RETURNING VARCHAR2(100)) AS customer_name,
       JSON_VALUE(payload, '$.total' RETURNING NUMBER) AS total_amount
  FROM orders_text
 WHERE JSON_VALUE(payload, '$.status' RETURNING VARCHAR2(20)) = 'NEW';
~~~

Retrieving a child object:

~~~sql
SELECT JSON_QUERY(payload, '$.shipping' WITH WRAPPER) AS shipping_json
  FROM orders_text
 WHERE order_id = 1001;
~~~

Checking whether a property exists:

~~~sql
SELECT order_id
  FROM orders_text
 WHERE JSON_EXISTS(payload, '$.discount');
~~~

Converting a JSON array into relational rows:

~~~sql
SELECT o.order_id,
       item.product_id,
       item.quantity
  FROM orders_text o,
       JSON_TABLE(
         o.payload,
         '$.items[*]'
         COLUMNS (
           product_id NUMBER PATH '$.productId',
           quantity   NUMBER PATH '$.quantity'
         )
       ) item;
~~~

Thus, even when data is stored in CLOB or VARCHAR2, applications can still use SQL to filter, project, join, and aggregate. The limitation is that the data is stored as text, so Oracle may have to parse the textual representation during processing.

## 2. Native JSON Type in Oracle Database 21c

Oracle Database 21c introduced the SQL `JSON` data type. Instead of declaring a CLOB or VARCHAR2 column and adding a CHECK constraint, you can declare directly:

~~~sql
CREATE TABLE orders_native (
  order_id NUMBER PRIMARY KEY,
  payload  JSON
);
~~~

The native JSON type stores documents in the **OSON** (*Optimized Binary JSON*) binary format. OSON is an internal representation optimized for Oracle Database; it is not a UTF-8 JSON string meant to be sent directly to an external system.

Key benefits:

- Oracle knows the column type is JSON, eliminating the need for an `IS JSON` CHECK constraint to verify value validity.
- The OSON representation is optimized for accessing and processing JSON properties.
- SQL/JSON functions work directly on values of the JSON type.
- Reduces the need to re-parse JSON text across many operations.
- The JSON type can be used in SQL and PL/SQL in supported releases.

Example inserting a document into a JSON column:

~~~sql
INSERT INTO orders_native (order_id, payload)
VALUES (
  1001,
  JSON('{"orderId":1001,"customer":"An","total":125.5,"status":"NEW"}')
);
~~~

The `JSON(...)` constructor converts the input JSON representation into a JSON-type value. The JSON column receives a JSON value already parsed and stored by Oracle in its internal format.

Querying with SQL/JSON remains familiar:

~~~sql
SELECT order_id,
       JSON_VALUE(payload, '$.customer' RETURNING VARCHAR2(100)) AS customer_name,
       JSON_VALUE(payload, '$.total' RETURNING NUMBER) AS total_amount
  FROM orders_native
 WHERE JSON_VALUE(payload, '$.status' RETURNING VARCHAR2(20)) = 'NEW';
~~~

This means moving to the native JSON type preserves the SQL/JSON query model. The major change lies in the data type and how Oracle represents the data internally.

## 3. OSON and Textual JSON

Textual JSON is an easily interchangeable representation across systems. Example:

~~~json
{
  "orderId": 1001,
  "customer": "An",
  "total": 125.5,
  "status": "NEW"
}
~~~

OSON is an internal binary representation optimized by Oracle for storing and accessing JSON. OSON bytes should not be treated as ordinary textual JSON content.

| Criterion | Textual JSON | Native JSON (OSON) |
|---|---|---|
| Storage representation | JSON characters or bytes | Binary OSON |
| Direct readability in a text editor | Yes, if decoded with the right character set | Not ordinary JSON text |
| Validity enforcement | Typically uses an `IS JSON` constraint | Guaranteed by the JSON data type |
| Exchange over HTTP or JSON files | Can be sent directly once text is retrieved | Needs serialization to textual JSON |
| Property processing | SQL/JSON parses the textual content | Oracle operates on an optimized binary representation |

When you need to output a native JSON value as text, use `JSON_SERIALIZE`:

~~~sql
SELECT JSON_SERIALIZE(
         payload
         RETURNING CLOB
         PRETTY
       ) AS payload_text
  FROM orders_native
 WHERE order_id = 1001;
~~~

The result is textual JSON that can be sent to applications, written to files, or exchanged with systems that do not understand OSON. You can choose an appropriate return type such as VARCHAR2, CLOB, or BLOB based on application and version requirements.

## 4. Native JSON Type vs. JSON_OBJECT_T

A common confusion is treating `JSON_OBJECT_T` as the native JSON column data type. These two concepts serve different purposes:

| Component | Role | Where Used |
|---|---|---|
| `JSON` | SQL data type storing JSON values, using OSON representation from 21c | Table columns, SQL expressions, and PL/SQL in supported releases |
| `JSON_ELEMENT_T` | Base type representing any JSON element | PL/SQL |
| `JSON_OBJECT_T` | Represents a JSON object, supporting reading and modifying properties | PL/SQL |
| `JSON_ARRAY_T` | Represents a JSON array, supporting element manipulation | PL/SQL |

These PL/SQL object types were introduced in Oracle Database 12.2, meaning you can use them even when the database does not yet support the native SQL JSON column type. They help parse text, manipulate JSON structures in memory, and convert the result back to text.

Example parsing and updating JSON with `JSON_OBJECT_T`:

~~~sql
DECLARE
  l_document JSON_OBJECT_T;
BEGIN
  l_document := JSON_OBJECT_T.parse(
    '{"orderId":1001,"customer":"An","status":"NEW"}'
  );

  DBMS_OUTPUT.PUT_LINE(
    'Customer: ' || l_document.get_string('customer')
  );

  l_document.put('status', 'PAID');
  l_document.put('verified', TRUE);

  DBMS_OUTPUT.PUT_LINE(l_document.to_string());
END;
/
~~~

In the example:

- `parse` converts a JSON string into an in-memory object.
- `get_string` retrieves the customer property as VARCHAR2.
- `put` adds or replaces a property.
- `to_string` serializes the object back to textual JSON.

If you need to update a table column, write the serialized result to a VARCHAR2/CLOB/BLOB column or use a JSON-type value in supported releases. Creating a `JSON_OBJECT_T` in PL/SQL does not automatically modify data in a table.

## 5. History of JSON Support by Release

Oracle releases have added JSON capabilities incrementally. The table below summarizes key milestones for JSON storage and processing:

| Release | Notable Capabilities | JSON Storage Type |
|---|---|---|
| 12.1.0.2 | Initial JSON support in SQL; `IS JSON`, query functions such as JSON_VALUE, JSON_QUERY, JSON_EXISTS, and JSON_TABLE | VARCHAR2, CLOB, or BLOB |
| 12.2 | Added JSON generation functions, PL/SQL JSON object types, and many SQL/JSON enhancements | Still VARCHAR2, CLOB, or BLOB |
| 18c | Continued expanding and refining SQL/JSON capabilities | Still textual JSON in existing column types |
| 19c | Added and refined many JSON capabilities, widely used in production systems | No native SQL JSON data type |
| 21c | Introduced the SQL `JSON` data type and OSON binary storage; added JSON operations such as JSON_TRANSFORM | Native JSON type can be used alongside textual types |
| 23c / 23ai | Continued expanding JSON; introduced JSON Relational Duality Views to work with relational data through a JSON document interface | Supports native JSON type and textual types |

### Oracle Database 12.1.0.2

This was the key milestone when Oracle brought SQL/JSON into the database. Data was still stored in existing column types. The `IS JSON` constraint validated content and SQL/JSON functions enabled querying the structure.

In a 12.1 environment, you cannot declare a column of type `JSON` as in 21c. If an application needs to store JSON, choose VARCHAR2, CLOB, or BLOB and apply the appropriate constraint.

### Oracle Database 12.2

12.2 expanded JSON generation in SQL and introduced JSON object types in PL/SQL. Applications could generate JSON using functions like `JSON_OBJECT`, `JSON_ARRAY`, `JSON_OBJECTAGG`, and `JSON_ARRAYAGG`, while parsing and modifying JSON with `JSON_OBJECT_T` or `JSON_ARRAY_T`.

PL/SQL object types made working with nested structures more convenient, but did not replace textual column types. Columns storing JSON remained VARCHAR2, CLOB, or BLOB.

### Oracle Database 18c and 19c

These two releases continued expanding SQL/JSON and indexing, querying, and JSON generation capabilities. However, Oracle Database 19c still lacks the native SQL JSON data type. This is important to remember when working with 19c systems: although many modern JSON functions are available, you cannot use the 21c `payload JSON` column syntax.

On 19c systems, a common design is storing large documents in CLOB, adding an `IS JSON` CHECK constraint, and using SQL/JSON functions for queries. When manipulation in PL/SQL is needed, `JSON_OBJECT_T` and `JSON_ARRAY_T` can be used.

### Oracle Database 21c

21c introduced the native SQL JSON type and OSON. This was a storage-model change, not merely an added query function. You can use a JSON-type column, read properties with SQL/JSON functions, and serialize when exchanging as text.

21c also added JSON update operations such as `JSON_TRANSFORM`, allowing partial document updates directly in SQL without the application downloading the entire document, modifying the string, and writing it back.

Example updating an order status:

~~~sql
UPDATE orders_native
   SET payload = JSON_TRANSFORM(
                   payload,
                   SET '$.status' = 'PAID'
                 )
 WHERE order_id = 1001;
~~~

### Oracle Database 23c / 23ai

The 23c family, broadly released under the name Oracle Database 23ai, continued expanding the JSON model. One notable feature is **JSON Relational Duality Views**: applications can work with a JSON document while the data is stored and managed in underlying relational tables.

Duality Views do not mean all JSON data must be stored in a single CLOB or JSON column. They provide a way to expose relational data as JSON documents while supporting document-style read and write operations. Table organization, keys, relationships, and write privileges still need clear design.

## 6. Comparing the Same Problem on 19c vs. 21c and Later

Suppose an application needs to store orders with ID, customer, total amount, and status.

### Implementation on Oracle 19c

~~~sql
CREATE TABLE orders_19c (
  order_id NUMBER PRIMARY KEY,
  payload  CLOB
    CONSTRAINT orders_19c_payload_json
    CHECK (payload IS JSON)
);

INSERT INTO orders_19c (order_id, payload)
VALUES (
  1001,
  '{"customer":"An","total":125.5,"status":"NEW"}'
);

SELECT order_id,
       JSON_VALUE(payload, '$.customer' RETURNING VARCHAR2(100)) AS customer_name,
       JSON_VALUE(payload, '$.total' RETURNING NUMBER) AS total_amount
  FROM orders_19c;
~~~

Here CLOB stores JSON text. The constraint validates data and JSON_VALUE retrieves the required fields.

### Implementation on Oracle 21c and Later

~~~sql
CREATE TABLE orders_21c (
  order_id NUMBER PRIMARY KEY,
  payload  JSON
);

INSERT INTO orders_21c (order_id, payload)
VALUES (
  1001,
  JSON('{"customer":"An","total":125.5,"status":"NEW"}')
);

SELECT order_id,
       JSON_VALUE(payload, '$.customer' RETURNING VARCHAR2(100)) AS customer_name,
       JSON_VALUE(payload, '$.total' RETURNING NUMBER) AS total_amount
  FROM orders_21c;
~~~

The two SELECT statements are nearly identical. The difference lies in the column declaration and how data is loaded: 19c stores text in CLOB and validates via constraint; 21c can use the native JSON type.

## 7. Choosing VARCHAR2, CLOB, BLOB, or JSON?

Not every system needs to migrate to the native JSON type. Choose the column type based on document size, database version, data exchange patterns, and compatibility requirements.

| Criterion | VARCHAR2 | CLOB | BLOB | Native JSON |
|---|---|---|---|---|
| Primary data | Small JSON text | Large JSON text | JSON bytes, typically UTF-8 | Oracle-managed JSON |
| Size limit | Per configured VARCHAR2 limit | Suitable for large documents | Suitable for large byte data | Per JSON type limits and Oracle configuration |
| Readable in text editor | Yes | Yes | Requires UTF-8 decoding | Requires serialization |
| JSON validation | CHECK `IS JSON` | CHECK `IS JSON` | CHECK `IS JSON` for valid JSON content | Data type enforces valid JSON |
| Version requirement | Available in older releases | Available in older releases | Available in older releases | Oracle Database 21c and later |
| Common scenarios | Small attributes, short documents | API payloads, configs, large documents | Receiving or storing UTF-8 byte representations | New systems needing direct JSON processing in Oracle |

### When to Use VARCHAR2

Use VARCHAR2 when documents are small, have clearly bounded sizes, and the application needs to store or exchange content as strings. Consider `MAX_STRING_SIZE` and the database's VARCHAR2 type limits. Do not choose VARCHAR2 solely because current JSON payloads are short if document sizes may grow significantly.

### When to Use CLOB

CLOB is suitable when JSON is large textual content that may exceed the VARCHAR2 limit or requires character semantics. It is a common choice for Oracle 19c and older releases when storing large JSON.

### When to Use BLOB

BLOB is suitable when the application works with JSON bytes, such as receiving UTF-8 payloads from another system and needing to preserve the byte representation. When using BLOB to store JSON, content must use UTF-8 (AL32UTF8) as required by Oracle. BLOB does not automatically decode bytes into characters for the application.

### When to Use the Native JSON Type

On 21c and later, the native JSON type fits when applications frequently query and update JSON structures inside the database. OSON is an internal representation that helps Oracle operate on properties without treating the document as a text string at every step.

If the system must remain compatible with older databases or clients, verify native JSON type support before changing schemas. In many systems, keeping CLOB and SQL/JSON functions remains a practical choice.

## 8. Indexes and JSON Query Performance

Whether data resides in CLOB or the native JSON type, JSON queries still require proper design and performance measurement. If an application frequently filters on a property, consider a function-based index on the JSON_VALUE expression.

Example on a CLOB column in supported releases:

~~~sql
CREATE INDEX orders_text_status_ix
ON orders_text (
  JSON_VALUE(payload, '$.status' RETURNING VARCHAR2(20))
);
~~~

Query with a matching expression:

~~~sql
SELECT order_id
  FROM orders_text
 WHERE JSON_VALUE(payload, '$.status' RETURNING VARCHAR2(20)) = 'NEW';
~~~

For documents with many queried paths, Oracle also supports JSON search indexes. Creation syntax and specific capabilities depend on the release, column type, and search requirements. Do not create indexes simply because a column contains JSON; identify actual paths and query patterns.

When comparing CLOB with native JSON, measure:

- Query time for frequently accessed properties.
- Cost of updating a single property inside a document.
- Storage and index space usage.
- Document count, average size, and maximum size.
- Ratio of queries returning full documents vs. queries returning a few properties.
- Serialization cost when sending data to applications.

OSON can improve certain operations, but does not automatically make every query faster. Path design, indexes, selectivity, and execution plans remain critical.

## 9. Updating JSON: String Editing, PL/SQL Objects, or JSON_TRANSFORM?

There are multiple ways to update JSON content:

**Editing text in the application:** suitable when the application already owns the entire document and needs to write back the modified document. Be careful when multiple processes update concurrently, as they can overwrite each other's changes.

**Using JSON_OBJECT_T in PL/SQL:** suitable when you need to manipulate nested structures, traverse objects or arrays, apply conditional logic, and serialize back.

**Using JSON_TRANSFORM:** suitable when you want to change one or several properties directly in SQL on supported releases, avoiding round-tripping the document to the application just to edit one field.

Example updating order status:

~~~sql
UPDATE orders_native
   SET payload = JSON_TRANSFORM(
                   payload,
                   SET '$.status' = 'PAID'
                 )
 WHERE order_id = 1001;
~~~

Check the JSON value type to be written. A JSON boolean is `true` or `false`, different from the text string `'true'`. When updating boolean properties in SQL, expression syntax depends on the release and value types accepted by JSON_TRANSFORM; verify against the exact release documentation. For critical data, verify the result using JSON_VALUE or JSON_QUERY after updating.

## 10. Upgrading from Textual JSON to the Native JSON Type

When upgrading a database from 19c to 21c or later, you do not need to convert every JSON column immediately. You can proceed step by step:

1. **Schema inventory:** identify VARCHAR2, CLOB, and BLOB columns containing JSON, CHECK constraints, function-based indexes, JSON search indexes, views, triggers, and dependent applications.
2. **Data audit:** find invalid rows, establish strict/lax policies, and fix bad data before converting.
3. **Verify version and clients:** confirm database release, compatibility level, JDBC/ODP.NET drivers, and whether ETL, backup, and export tools support the native JSON type.
4. **Create a new JSON column in a test environment:** you can add a JSON column alongside the textual column to test conversion and compare results.
5. **Convert data:** convert valid textual content into native JSON values using the JSON constructor appropriate for the release.
6. **Reconcile:** compare business values via JSON_VALUE/JSON_QUERY, row counts, NULL data, arrays, and nested objects.
7. **Rebuild indexes and adjust SQL:** review index expressions, queries, views, and write operations.
8. **Switch applications:** update how data is bound/fetched if drivers use dedicated APIs for the JSON type. If an application requires text, serialize to CLOB/VARCHAR2 or BLOB per the interface.
9. **Controlled rollout:** shift read and write flows according to plan, monitoring conversion errors, performance, and space usage.

Illustrative example converting a CLOB column to a JSON column on a release supporting the JSON type:

~~~sql
ALTER TABLE orders_text
  ADD (payload_native JSON);

UPDATE orders_text
   SET payload_native = JSON(payload);

COMMIT;
~~~

The snippet above assumes every non-NULL value in `payload` is valid JSON and the database supports the JSON constructor and JSON data type. In production environments, handle NULL rows, invalid data, and conversion failures separately before running bulk updates. Test on a copy of the data and measure transaction impact before migrating large tables.

Once verified, you can export textual content using:

~~~sql
SELECT order_id,
       JSON_SERIALIZE(payload_native RETURNING CLOB) AS payload_text
  FROM orders_text;
~~~

Keeping the textual column during the transition makes comparison and rollback easier. Drop the old column only after all applications, reports, and integration pipelines have moved to the new model.

## 11. Compatibility Across Versions and External Systems

The native JSON type introduces a new compatibility requirement: the target database and client must understand the JSON type. Oracle Database 19c does not have the native SQL JSON type, so you cannot assume a schema with a JSON column from 21c can be deployed as-is on 19c.

When exchanging data between environments:

- If both source and target support the native JSON type, use data transfer mechanisms compatible with the versions and tools in use.
- If the target is an older release, serialize native JSON values into textual JSON and load them into CLOB/VARCHAR2/BLOB with appropriate CHECK constraints.
- When sending over HTTP, message queues, or files, send textual JSON in an agreed encoding, typically UTF-8.
- Do not send OSON bytes as if they were textual JSON.
- Check whether drivers support binding and fetching the JSON type or need to receive data as CLOB/VARCHAR2.
- Verify Data Pump, database links, ETL, and admin tools for the exact source/target version pair; compatibility does not depend solely on SQL statements.

If a system runs multiple Oracle versions concurrently, an API contract exchanging textual JSON is often easier to keep compatible than requiring all parties to understand OSON. Databases can use an appropriate internal storage type and serialize at integration boundaries.

## 12. Common Misconceptions

**Having JSON_OBJECT_T means the database has a JSON column type:** incorrect. JSON_OBJECT_T is a PL/SQL object type supported since 12.2; the native SQL JSON type only exists from 21c onward.

**Oracle 19c does not support JSON:** incorrect. 19c supports many SQL/JSON functions, the IS JSON constraint, PL/SQL object types, and other JSON features. What 19c lacks is the native SQL JSON data type.

**CLOB with CHECK IS JSON is identical to the native JSON type:** both ensure content is valid JSON, but storage differs. CLOB stores text; the native JSON type uses the OSON binary representation.

**OSON is a JSON format for sending over REST:** incorrect. OSON is Oracle's internal binary format. When exchanging with external systems, serialize to textual JSON.

**Using the native JSON type automatically makes every query faster:** incorrect. Performance still depends on query paths, indexes, document size, execution plans, and how applications read data.

**All legacy JSON columns must be converted when upgrading:** not mandatory. VARCHAR2/CLOB/BLOB columns with IS JSON can continue operating. Conversion should be based on benefits and compatibility requirements.

**JSON Relational Duality Views completely replace relational design:** incorrect. Duality Views provide a way to view and manipulate relational data as JSON; underlying tables, keys, and relational constraints remain essential.

## 13. Checking Supported Capabilities in Your Running Environment

Before using new syntax or data types, confirm the database version:

~~~sql
SELECT *
  FROM product_component_version;
~~~

Or check version information in `V$VERSION` if the account has access privileges:

~~~sql
SELECT banner
  FROM v$version;
~~~

Then consult Oracle documentation for the exact installed version and Release Update. Verify:

- Whether the JSON data type is supported in that release.
- Whether the SQL/JSON functions and syntax being used exist.
- Whether PL/SQL JSON object types support the required methods.
- Whether features like JSON_TRANSFORM or JSON Relational Duality Views are supported.
- Whether client drivers and deployment tools understand the new data type.
- Whether database compatibility settings and operational policies permit using the feature.

Do not infer feature support solely from a major version number. Release Updates, configurations, and deployment platforms can affect specific features.

## 14. Project Selection Workflow

When starting to design a table containing JSON, you can follow this sequence:

1. Identify the lowest Oracle version the system must support.
2. Estimate document size and data growth rate.
3. Determine whether applications operate on text, bytes, or JSON structures.
4. Choose VARCHAR2 for small documents, CLOB for large text, BLOB for UTF-8 JSON bytes, or native JSON when the database supports it and applications are prepared.
5. Configure JSON validation for textual columns.
6. Choose SQL/JSON functions or PL/SQL JSON object types based on processing needs.
7. Design indexes around frequently queried paths.
8. Test serialization, integration, backup/restore, and cross-version data transfer.
9. Measure performance with representative data before finalizing the choice.

For example, a system running Oracle 19c with many legacy applications can continue storing JSON in CLOB with CHECK IS JSON. When upgrading to 21c or later, the development team can pilot native JSON columns for tables with heavy JSON querying while keeping CLOB for integration flows needing backward compatibility with older systems.

## 15. Conclusion

Oracle has supported JSON since 12.1.0.2 through textual column types and SQL/JSON functions. 12.2 added JSON generation functions and PL/SQL JSON object types. Releases 18c and 19c further expanded JSON capabilities but still lacked a native SQL JSON data type. From 21c onward, you can declare `JSON` columns and use the OSON binary representation. The 23c/23ai family continued expanding JSON document capabilities, including JSON Relational Duality Views.

When designing, distinguish the native JSON type from JSON stored in CLOB/VARCHAR2/BLOB and from PL/SQL `JSON_OBJECT_T`/`JSON_ARRAY_T` types. Choose storage based on the lowest supported version, document size, access patterns, and integration requirements. Native JSON is a useful option on newer releases, while textual JSON with SQL/JSON remains a valid and necessary approach in many backward-compatible systems.
