# ON ERROR, ON EMPTY, and Distinguishing JSON null from SQL NULL in Oracle Database

When querying JSON with SQL, a NULL result can appear for several reasons: the column containing the JSON document is SQL NULL, the requested field is absent from the object, the field has a JSON null value, or the extraction encountered an error. If all of these cases are collapsed into a single SQL NULL value, the application may overlook malformed data, mistake a missing field for an explicitly sent null, or apply the wrong default rules.

Oracle provides the **ON ERROR** and **ON EMPTY** clauses for SQL/JSON query functions to determine how errors and non-existent fields are handled. The two clauses serve different purposes:

- ON ERROR specifies the result when SQL/JSON evaluation encounters a runtime error, such as invalid JSON, a path returning multiple values in JSON_VALUE, or a value that cannot be converted to the requested SQL data type.
- ON EMPTY specifies the result when the path is valid but the requested field/value is not found in the JSON.

To distinguish **JSON null** from **SQL NULL**, you need to understand the input data type and the function being used. JSON_VALUE extracts a JSON scalar into a SQL scalar; when that scalar is JSON null, the default result is SQL NULL. JSON_EXISTS can check whether a field exists and returns TRUE even when the field value is JSON null. JSON_QUERY returns JSON data, so it can preserve JSON null as JSON or JSON text depending on the data type and database version.

This document focuses on Oracle Database SQL/JSON functions, specifically JSON_VALUE, JSON_QUERY, JSON_EXISTS, and JSON_TABLE. The main examples use syntax compatible with the Oracle 19c/21c series; notes highlight key differences when using the SQL JSON data type and newer features in later releases.

## 1. Three Concepts Not to Confuse

Before using ON ERROR and ON EMPTY, you need to distinguish three states of JSON data along with one state at the SQL layer.

### 1.1 SQL NULL in the JSON Column

This is the case where the database column does not contain any JSON document:

~~~sql
payload IS NULL
~~~

For example, a row whose payload is SQL NULL. There is no document for the SQL/JSON path to query.

### 1.2 Field Does Not Exist in the JSON Document

The document is valid, but the object does not contain the requested field:

~~~json
{}
~~~

The path $.status does not find the status field. This is the **empty/missing match** case that ON EMPTY is designed to handle.

### 1.3 Field Exists and Has Value JSON null

The document has a status field, and its value is the JSON null literal:

~~~json
{"status":null}
~~~

JSON null is a valid value in the JSON language. The field exists; its value is not a missing field.

### 1.4 Error During JSON Evaluation

For example, the document is not valid JSON:

~~~text
{"status":
~~~

Or the path is syntactically valid, but JSON_VALUE receives multiple values or receives an object/array when a scalar is required. This is a runtime error handled by ON ERROR (if the error falls within the clause's scope).

### 1.5 Comparison Table

| State | Example | Nature |
|---|---|---|
| SQL NULL | Column payload is SQL NULL | No SQL value containing a JSON document |
| Field missing | {} and querying $.status | Document exists, but path finds no field |
| JSON null | {"status":null} | Field exists, JSON value is null |
| Runtime error | Malformed JSON or path returns incompatible type/cardinality | SQL/JSON evaluation encounters an error |

ON EMPTY does not mean "an empty JSON value". It is not synonymous with JSON string "", object {}, array [], or SQL NULL. It refers to the case where the path finds no match.

## 2. What Is ON ERROR?

ON ERROR is the error-handling clause of supported SQL/JSON functions and conditions. It defines the behavior when JSON evaluation raises a runtime error.

Common options:

| Clause | Behavior |
|---|---|
| NULL ON ERROR | Returns SQL NULL instead of raising an error |
| ERROR ON ERROR | Raises the corresponding Oracle error |
| DEFAULT literal ON ERROR | Returns a default literal on error; the literal must be compatible with the return type |

Not every function supports all options. For example, JSON_QUERY also supports EMPTY ARRAY ON ERROR and EMPTY OBJECT ON ERROR; JSON_EXISTS uses TRUE ON ERROR or FALSE ON ERROR, defaulting to FALSE in standard releases.

### 2.1 NULL ON ERROR

This is the default behavior of JSON_VALUE and many SQL/JSON query functions:

~~~sql
SELECT JSON_VALUE(
         '{"amount":"not-a-number"}',
         '$.amount' RETURNING NUMBER
         NULL ON ERROR
       ) AS amount
FROM dual;
~~~

The JSON value is the string "not-a-number", which cannot be converted to SQL NUMBER; with NULL ON ERROR, the result is SQL NULL.

The advantage is that the query can continue when encountering unexpected data. The disadvantage is that data errors may be masked if the application does not check or log the status.

### 2.2 ERROR ON ERROR

When you want malformed or invalid data to cause the query to fail, use:

~~~sql
SELECT JSON_VALUE(
         '{"amount":"not-a-number"}',
         '$.amount' RETURNING NUMBER
         ERROR ON ERROR
       ) AS amount
FROM dual;
~~~

Oracle raises a conversion error instead of returning NULL. This is useful for validating input data, running batch jobs that need fail-fast behavior, or during development to catch incorrect paths or data types.

### 2.3 DEFAULT ... ON ERROR

You can return a fallback value:

~~~sql
SELECT JSON_VALUE(
         '{"amount":"not-a-number"}',
         '$.amount' RETURNING NUMBER
         DEFAULT 0 ON ERROR
       ) AS amount
FROM dual;
~~~

The value 0 must match the NUMBER return type. The default literal is resolved at SQL compile time; you cannot use arbitrary dynamic expressions such as a bind variable in place of the default literal.

Do not pick a default value arbitrarily. If 0 is a valid business value, using DEFAULT 0 ON ERROR can make corrupted data look like valid data. Only use a fallback when business rules clearly define its meaning.

### 2.4 Which Errors Fall Under ON ERROR?

Common runtime errors:

- Input is not well-formed JSON.
- JSON_VALUE receives an object or array when a scalar is required.
- Path returns multiple values in a context expecting a single scalar.
- Converting the JSON value to the SQL type in RETURNING fails.
- The return type buffer is insufficient to hold the data.

The ON ERROR clause does not fix syntax errors in the SQL statement itself or in the path expression. A syntactically invalid path expression may be caught when parsing/compiling the statement; it is not turned into NULL ON ERROR.

## 3. What Is ON EMPTY?

ON EMPTY is used when the path expression is valid but cannot find the requested field or value. It allows you to handle a missing field differently from other runtime errors.

Commonly used options:

| Clause | Behavior When No Match Is Found |
|---|---|
| NULL ON EMPTY | Returns SQL NULL |
| ERROR ON EMPTY | Raises an Oracle error |
| DEFAULT literal ON EMPTY | Returns a default literal compatible with the result type |

### 3.1 NULL ON EMPTY

~~~sql
SELECT JSON_VALUE(
         '{"orderId":1001}',
         '$.customerName'
         NULL ON EMPTY
         ERROR ON ERROR
       ) AS customer_name
FROM dual;
~~~

The customerName field is absent from the document, so the result is SQL NULL. If another runtime error occurs, ERROR ON ERROR still applies.

### 3.2 ERROR ON EMPTY

~~~sql
SELECT JSON_VALUE(
         '{"orderId":1001}',
         '$.customerName'
         ERROR ON EMPTY
         NULL ON ERROR
       ) AS customer_name
FROM dual;
~~~

A missing customerName field is treated as an error per the data contract; Oracle raises an error. Other runtime errors are handled by NULL ON ERROR.

This is useful when a field is mandatory, such as orderId, tenantId, or createdAt. If a required field disappears, the input data should be rejected rather than silently receiving NULL.

### 3.3 DEFAULT ... ON EMPTY

~~~sql
SELECT JSON_VALUE(
         '{"orderId":1001}',
         '$.currency'
         RETURNING VARCHAR2(3)
         DEFAULT 'VND' ON EMPTY
         ERROR ON ERROR
       ) AS currency
FROM dual;
~~~

If the currency field does not appear, the result is VND. If the path encounters another runtime error, the query raises an error.

The default literal must be compatible with the return type. For example, DEFAULT 0 ON EMPTY for RETURNING NUMBER, or DEFAULT 'UNKNOWN' ON EMPTY for RETURNING VARCHAR2.

## 4. Precedence Between ON EMPTY and ON ERROR

This is a critical rule:

**If a field is missing and the SQL statement has both ON EMPTY and ON ERROR, ON EMPTY determines the result specifically for the missing-field case.** ON ERROR handles other runtime errors.

Example:

~~~sql
SELECT JSON_VALUE(
         '{"orderId":1001}',
         '$.customerName'
         RETURNING VARCHAR2(100)
         DEFAULT 'UNKNOWN' ON EMPTY
         ERROR ON ERROR
       ) AS customer_name
FROM dual;
~~~

- customerName does not exist: returns UNKNOWN.
- Malformed JSON, path returns an object/array, or other runtime error: raises an error.
- customerName exists with a valid scalar value: returns that value.
- customerName exists with JSON null: JSON_VALUE returns SQL NULL according to scalar extraction semantics; this is not an ON EMPTY case.

### 4.1 If Only ON ERROR Is Specified

~~~sql
JSON_VALUE(payload, '$.optionalField' ERROR ON ERROR)
~~~

If the path does not find the field, the missing case is handled according to ON ERROR, because there is no separate ON EMPTY to override it. Therefore, ERROR ON ERROR can cause an absent field to raise an error.

### 4.2 If Only ON EMPTY Is Specified

~~~sql
JSON_VALUE(payload, '$.optionalField' NULL ON EMPTY)
~~~

A missing field returns SQL NULL. Other runtime errors use the default behavior of JSON_VALUE, which is typically NULL ON ERROR.

### 4.3 If Both Clauses Are Omitted

~~~sql
JSON_VALUE(payload, '$.optionalField')
~~~

The default of JSON_VALUE is NULL ON ERROR; if the path does not find the field, the result is also SQL NULL. Consequently, looking only at a NULL result cannot tell whether the field was missing, the field contained JSON null, the input was SQL NULL, or an error was handled by default.

## 5. JSON_VALUE: Extracting Scalars and NULL Cases

JSON_VALUE extracts a JSON scalar and converts it into a SQL value. A scalar can be a string, number, Boolean, or null. If the path points to an object or array when the function expects a scalar, that is an error according to the function's semantics.

### 5.1 Basic Example

~~~sql
SELECT JSON_VALUE(
         '{"customer":{"id":42,"name":"Lan"}}',
         '$.customer.name'
         RETURNING VARCHAR2(100)
       ) AS customer_name
FROM dual;
~~~

The result is the SQL string Lan.

### 5.2 Path Does Not Find Field

~~~sql
SELECT JSON_VALUE(
         '{"customer":{"id":42}}',
         '$.customer.name'
         RETURNING VARCHAR2(100)
         NULL ON EMPTY
       ) AS customer_name
FROM dual;
~~~

The result is SQL NULL due to NULL ON EMPTY.

### 5.3 Field Has JSON null

~~~sql
SELECT JSON_VALUE(
         '{"customer":{"id":42,"name":null}}',
         '$.customer.name'
         RETURNING VARCHAR2(100)
       ) AS customer_name
FROM dual;
~~~

The result is also SQL NULL, but for a different reason: the path found the scalar JSON null, and JSON_VALUE maps JSON null to SQL NULL.

### 5.4 Field Has an Object or Array

~~~sql
SELECT JSON_VALUE(
         '{"customer":{"id":42,"name":"Lan"}}',
         '$.customer'
         RETURNING VARCHAR2(100)
         ERROR ON ERROR
       )
FROM dual;
~~~

The path $.customer points to an object. JSON_VALUE requires a scalar, so an error occurs; ERROR ON ERROR returns the error to the caller instead of turning it into SQL NULL.

### 5.5 Return Type and Conversion Errors

~~~sql
SELECT JSON_VALUE(
         '{"quantity":"abc"}',
         '$.quantity'
         RETURNING NUMBER
         DEFAULT 0 ON EMPTY
         ERROR ON ERROR
       ) AS quantity
FROM dual;
~~~

The field exists, but the string abc cannot be converted to NUMBER. This is a type/conversion error, not a missing field; ERROR ON ERROR handles that error. DEFAULT 0 ON EMPTY does not apply.

## 6. Distinguishing JSON null from SQL NULL

The two uses of "null" have different meanings:

- **JSON null** is a literal and a value in the JSON language.
- **SQL NULL** is the null state of a SQL data type, typically representing an absent, unknown, or inapplicable value.

In SQL, NULL is usually written in uppercase to distinguish it from the JSON null literal.

### 6.1 JSON null in a Textual JSON Document

For a VARCHAR2, CLOB, or BLOB column containing textual JSON:

~~~json
{"status":null}
~~~

The entire document is a non-null SQL value. However, when calling:

~~~sql
JSON_VALUE(payload, '$.status')
~~~

Oracle returns SQL NULL. JSON null is not returned as the SQL string 'null'.

### 6.2 SQL NULL in a JSON Column

~~~sql
SELECT JSON_VALUE(
         CAST(NULL AS VARCHAR2(100)),
         '$.status'
       ) AS status
FROM dual;
~~~

The input is SQL NULL, meaning there is no JSON document to read. The result is SQL NULL.

### 6.3 Missing Field and JSON null Can Both Yield JSON_VALUE = SQL NULL

Two documents:

~~~json
{}
~~~

~~~json
{"status":null}
~~~

When using JSON_VALUE(payload, '$.status') with default handling, both can produce SQL NULL. JSON_VALUE returns a SQL scalar, so it cannot represent the difference between a missing field and a scalar JSON null through that return value alone.

### 6.4 JSON_EXISTS Helps Identify Whether a Field Exists

JSON_EXISTS checks whether a path matches a JSON value. JSON null is still a value, so a path to a field containing JSON null still exists:

~~~sql
SELECT
    CASE
        WHEN JSON_EXISTS('{"status":null}', '$.status')
        THEN 'PRESENT'
        ELSE 'MISSING'
    END AS status_presence
FROM dual;
~~~

The result is PRESENT.

With an empty object:

~~~sql
SELECT
    CASE
        WHEN JSON_EXISTS('{}', '$.status')
        THEN 'PRESENT'
        ELSE 'MISSING'
    END AS status_presence
FROM dual;
~~~

The result is MISSING.

### 6.5 Using JSON_EXISTS and JSON_VALUE Together

This is a useful pattern to separate a missing field from a field that is present but extracts as SQL NULL:

~~~sql
SELECT
    CASE
        WHEN payload IS NULL THEN
            'SQL NULL DOCUMENT'
        WHEN NOT JSON_EXISTS(payload, '$.status') THEN
            'FIELD MISSING'
        WHEN JSON_VALUE(
                 payload,
                 '$.status'
                 RETURNING VARCHAR2(100)
             ) IS NULL THEN
            'FIELD PRESENT, SQL EXTRACTION IS NULL'
        ELSE
            'FIELD PRESENT WITH VALUE'
    END AS status_state
FROM json_documents;
~~~

The result FIELD PRESENT, SQL EXTRACTION IS NULL can include JSON null; for character return types, the empty JSON string "" must also be considered because Oracle SQL treats a zero-length character string as SQL NULL. If business logic must distinguish JSON null from an empty JSON string, keep the data in JSON representation or check the JSON type rather than relying solely on JSON_VALUE returning VARCHAR2.

## 7. JSON_EXISTS: Checking Existence Without Extracting a Value

JSON_EXISTS is suitable when the question is simply whether a field/path exists. It does not return a scalar value.

~~~sql
SELECT id
FROM json_documents
WHERE JSON_EXISTS(payload, '$.status');
~~~

This condition evaluates to TRUE when the path matches, even if the value at the path is JSON null.

### 7.1 JSON_EXISTS Does Not Use ON EMPTY

JSON_EXISTS is a condition, not a field-extracting function like JSON_VALUE. It does not have ON EMPTY like JSON_VALUE/JSON_QUERY. For evaluation errors, it supports FALSE ON ERROR or TRUE ON ERROR as needed; the common default is FALSE ON ERROR.

~~~sql
SELECT id
FROM json_documents
WHERE JSON_EXISTS(
        payload,
        '$.status'
        FALSE ON ERROR
      );
~~~

Do not use FALSE ON ERROR to hide malformed JSON data if the application needs to reject invalid inputs. When data validation is required, use an IS JSON constraint, a validation pipeline, or queries with ERROR ON ERROR as appropriate.

### 7.2 EXISTS Does Not Tell You Whether the Value Is null

JSON_EXISTS(payload, '$.status') returns TRUE for all of:

- {"status":"ACTIVE"}
- {"status":0}
- {"status":false}
- {"status":[]}
- {"status":{}}
- {"status":null}

If you need to know whether the value is JSON null, you must additionally check the JSON type or preserve the JSON representation using JSON_QUERY or the SQL JSON type.

## 8. JSON_QUERY: Returning JSON Data

JSON_QUERY is used to retrieve an object, an array, or a set of JSON values matching a path. Unlike JSON_VALUE, it returns JSON data as JSON text or as the SQL JSON type in supported versions/configurations.

### 8.1 Extracting an Object

~~~sql
SELECT JSON_QUERY(
         '{"customer":{"id":42,"name":"Lan"}}',
         '$.customer'
         RETURNING CLOB
       ) AS customer_json
FROM dual;
~~~

The result is a JSON fragment representing the customer object.

### 8.2 Preserving JSON null as JSON When the Return Type Supports It

In Oracle Database releases supporting the SQL JSON data type and JSON_QUERY ... RETURNING JSON, JSON null can be preserved as a JSON value:

~~~sql
SELECT JSON_QUERY(
         JSON('{"status":null}'),
         '$.status'
         RETURNING JSON
       ) AS status_json
FROM dual;
~~~

The result is a JSON null value, not SQL NULL. This is an important distinction when working with the native JSON data type.

For JSON stored in VARCHAR2/CLOB or returned as text, JSON_QUERY can return textual JSON null if the configuration/release permits scalar returns. Prior to Oracle Database 21c, RFC 8259 support for top-level JSON scalars was limited; WITH WRAPPER may be needed to return a scalar inside an array.

### 8.3 Using WITH WRAPPER for Scalars on Older Versions

~~~sql
SELECT JSON_QUERY(
         '{"status":null}',
         '$.status'
         WITH WRAPPER
         RETURNING VARCHAR2(100)
       ) AS status_json
FROM dual;
~~~

WITH WRAPPER wraps the result in a JSON array. For JSON null, the wrapped JSON content is [null]. Syntax and unwrapped scalar support depend on COMPATIBLE and the Oracle version.

### 8.4 ON ERROR and ON EMPTY in JSON_QUERY

JSON_QUERY provides error-handling clauses such as NULL ON ERROR, ERROR ON ERROR, EMPTY ARRAY ON ERROR, and EMPTY OBJECT ON ERROR in supported releases. ON EMPTY can return NULL, raise an error, or return an empty array/object depending on syntax/version.

~~~sql
SELECT JSON_QUERY(
         payload,
         '$.preferences'
         RETURNING CLOB
         EMPTY ARRAY ON EMPTY
         ERROR ON ERROR
       ) AS preferences_json
FROM json_documents;
~~~

If the path does not match, the result is []. If another runtime error occurs, the query raises an error. Verify the supported syntax in your target release, especially for EMPTY ARRAY ON EMPTY and EMPTY OBJECT ON EMPTY.

## 9. JSON_TABLE: Processing JSON as Rows and Columns

JSON_TABLE projects JSON into a virtual relational table. It has two path levels:

1. **Row path:** determines which JSON values produce a row.
2. **Column path:** extracts fields from each row source into relational columns.

Because there are two levels, you must distinguish errors at the row path from errors at the column path.

### 9.1 Basic Example

Suppose the document is:

~~~json
{
  "orderId": 1001,
  "items": [
    {"sku": "A10", "quantity": 2},
    {"sku": "B20", "quantity": 5}
  ]
}
~~~

You can unnest the elements in items into rows:

~~~sql
SELECT jt.order_id,
       jt.sku,
       jt.quantity
FROM json_documents d,
     JSON_TABLE(
         d.payload,
         '$.items[*]'
         COLUMNS (
             order_id NUMBER PATH '$.orderId',
             sku      VARCHAR2(30) PATH '$.sku',
             quantity NUMBER PATH '$.quantity'
         )
     ) jt;
~~~

Each array element produces a row source. Columns are evaluated relative to the row source; if you need parent fields, use a nested path or design the paths accordingly.

### 9.2 Row-level ON ERROR

The clause at the JSON_TABLE level handles invalid JSON input and cases where the row path finds no match:

~~~sql
SELECT jt.sku
FROM json_documents d,
     JSON_TABLE(
         d.payload,
         '$.items[*]'
         ERROR ON ERROR
         COLUMNS (
             sku VARCHAR2(30) PATH '$.sku'
         )
     ) jt;
~~~

With ERROR ON ERROR, invalid JSON or an unmatched row path raises an error. With NULL ON ERROR (the default), invalid data generates no additional rows; an unmatched row path also returns zero rows. Because JSON_TABLE can evaluate in streaming mode, in some cases rows may already be returned before the malformed portion of the document is encountered.

### 9.3 Row-level ON EMPTY

You can specify how to handle a row path that finds no row source:

~~~sql
SELECT jt.sku
FROM json_documents d,
     JSON_TABLE(
         d.payload,
         '$.items[*]'
         ERROR ON ERROR
         NULL ON EMPTY
         COLUMNS (
             sku VARCHAR2(30) PATH '$.sku'
         )
     ) jt;
~~~

ON EMPTY overrides ON ERROR behavior specifically when the row path has no match. In this example, other JSON/runtime errors are still raised; when there is no row source, NULL ON EMPTY is used according to JSON_TABLE semantics. Note that an unmatched row path producing no rows may result in zero rows in the result set; it does not create a synthetic row with all NULL columns.

### 9.4 Column-level Error Handling

JSON_TABLE allows defining error-handling behavior per column. A column-level handler can override the default inherited from the row-level clause.

~~~sql
SELECT jt.sku,
       jt.quantity
FROM json_documents d,
     JSON_TABLE(
         d.payload,
         '$.items[*]'
         NULL ON ERROR
         COLUMNS (
             sku      VARCHAR2(30) PATH '$.sku' ERROR ON ERROR,
             quantity NUMBER       PATH '$.quantity' NULL ON ERROR
         )
     ) jt;
~~~

In the example:

- Errors extracting sku are raised.
- Errors extracting quantity return SQL NULL.
- NULL ON ERROR at the JSON_TABLE level serves as the general default for columns without an explicit handler and for row-level handling.

### 9.5 Column-level ON EMPTY by Release

Newer Oracle releases allow ON EMPTY directly inside a JSON_VALUE_COLUMN definition of JSON_TABLE. For example, in releases supporting that syntax:

~~~sql
SELECT jt.customer_name
FROM json_documents d,
     JSON_TABLE(
         d.payload,
         '$'
         COLUMNS (
             customer_name VARCHAR2(100)
                 PATH '$.customer.name'
                 DEFAULT 'UNKNOWN' ON EMPTY
                 ERROR ON ERROR
         )
     ) jt;
~~~

Here, if customer.name is missing, it returns UNKNOWN, while other runtime errors raise an error. Exact syntax details for column-level ON EMPTY vary by release; check the SQL Language Reference for your database version before using it on older systems.

## 10. Using JSON_TABLE to Distinguish Missing Fields from JSON null

JSON_TABLE supports EXISTS columns, which use JSON_EXISTS semantics, and value columns, which use JSON_VALUE semantics. Combining the two column types lets you see the difference between a non-existent field and a field whose value is JSON null.

~~~sql
SELECT jt.status_exists,
       jt.status_value
FROM json_documents d,
     JSON_TABLE(
         d.payload,
         '$'
         COLUMNS (
             status_exists VARCHAR2(5)
                 EXISTS PATH '$.status',
             status_value VARCHAR2(100)
                 PATH '$.status'
         )
     ) jt;
~~~

For the document {}:

- status_exists is false.
- status_value is SQL NULL.

For the document {"status":null}:

- status_exists is true.
- status_value is SQL NULL.

Thus EXISTS preserves information about whether the field is present; the value column provides a SQL scalar but may return NULL for JSON null. This is an important pattern when mapping JSON to relational columns.

## 11. Result Matrix by Function

Assume the path is $.status, and the inputs are SQL NULL, an empty object, and an object with status:null.

| Input | JSON_EXISTS | Default JSON_VALUE | JSON_QUERY |
|---|---|---|---|
| SQL NULL document | FALSE/no match per condition | SQL NULL | SQL NULL |
| {} | FALSE | SQL NULL (missing/error default) | SQL NULL per default ON EMPTY |
| {"status":null} | TRUE | SQL NULL | Preserves JSON null when JSON/RETURNING type allows; textual JSON null when scalar return is supported |

For JSON_VALUE, the first three cases can all produce SQL NULL. Therefore, do not use a single IS NULL check on the result of JSON_VALUE to conclude whether a field is missing or JSON null.

## 12. ON ERROR Does Not Replace JSON Validity Checks

If a column stores textual JSON, you should add a constraint confirming the data is valid JSON:

~~~sql
CREATE TABLE json_documents (
    id      NUMBER PRIMARY KEY,
    payload CLOB,
    CONSTRAINT json_documents_payload_ck
        CHECK (payload IS JSON)
);
~~~

The IS JSON constraint prevents syntactically invalid textual JSON documents from being written to the column (SQL NULL still follows constraint semantics). This reduces runtime errors caused by non-well-formed data.

ON ERROR is still needed because:

- A path may return multiple results when the function expects a single scalar.
- A JSON value may fail conversion to the requested SQL data type.
- The result may exceed the return type size limit.
- Other runtime errors can still occur during data processing.

Note: ON ERROR is not a substitute for write-time validation. If data is invalid, decide upfront whether to reject, quarantine, log, or apply an explicit fallback.

## 13. Strict and Lax Path Modes

Oracle SQL/JSON paths support strict and lax modes. The default is typically lax:

- **Lax mode** allows certain structural adjustments so paths access data more flexibly, such as automatically unwrapping arrays in some situations.
- **Strict mode** requires the accessed structure to match the path expression more strictly.

The two modes affect whether a path matches and which runtime errors can occur. ON ERROR controls how runtime errors are handled during path matching; it does not turn a syntactically invalid path expression into a valid one.

When input data has a well-defined schema, strict paths help catch structural mismatches earlier. When compatibility with multiple JSON shapes is needed, lax paths can be convenient, but match results must be checked carefully.

## 14. Distinguishing ON EMPTY from Other Empty Forms

The following cases are not equivalent:

| Value/State | Meaning |
|---|---|
| Field missing | No member requested by the path exists |
| JSON null | Member exists, JSON value is null |
| JSON "" | Member exists, value is an empty JSON string |
| JSON [] | Member exists, value is an empty array |
| JSON {} | Member exists, value is an empty object |
| SQL NULL | No SQL value |
| NULL ON EMPTY | Policy to return SQL NULL when the path has no match |

EMPTY ARRAY ON EMPTY or EMPTY OBJECT ON EMPTY in JSON_QUERY generates an empty JSON array/object when the path does not match; it does not mean an existing field contains an empty array/object.

## 15. Do Not Confuse ON EMPTY with NULL ON NULL When Generating JSON

When generating JSON from relational data, Oracle has the NULL ON NULL and ABSENT ON NULL clauses. They belong to SQL/JSON generation functions such as JSON_OBJECT, JSON_ARRAY, JSON_OBJECTAGG, and JSON_ARRAYAGG—not to the ON EMPTY clause of query functions.

Example:

~~~sql
SELECT JSON_OBJECT(
         'name' VALUE CAST(NULL AS VARCHAR2(20))
         NULL ON NULL
       ) AS json_with_null
FROM dual;
~~~

The result contains the member "name": null.

~~~sql
SELECT JSON_OBJECT(
         'name' VALUE CAST(NULL AS VARCHAR2(20))
         ABSENT ON NULL
       ) AS json_without_member
FROM dual;
~~~

The result does not contain the member name.

Typically:

- JSON_OBJECT and JSON_OBJECTAGG default to NULL ON NULL.
- JSON_ARRAY and JSON_ARRAYAGG default to ABSENT ON NULL.

When reading JSON, ON EMPTY decides how an unmatched path is handled. When generating JSON, NULL ON NULL/ABSENT ON NULL decides how an input SQL NULL is represented in the output document.

## 16. Hands-On Example: Creating Data and Observing the Four States

### 16.1 Creating the Test Table

~~~sql
CREATE TABLE json_state_lab (
    id      NUMBER PRIMARY KEY,
    payload CLOB,
    CONSTRAINT json_state_lab_ck CHECK (payload IS JSON)
);
~~~

### 16.2 Loading Test Cases

~~~sql
INSERT INTO json_state_lab VALUES (1, NULL);
INSERT INTO json_state_lab VALUES (2, '{}');
INSERT INTO json_state_lab VALUES (3, '{"status":null}');
INSERT INTO json_state_lab VALUES (4, '{"status":"ACTIVE"}');
INSERT INTO json_state_lab VALUES (5, '{"status":""}');
INSERT INTO json_state_lab VALUES (6, '{"status":[]}');
INSERT INTO json_state_lab VALUES (7, '{"status":{}}');
COMMIT;
~~~

### 16.3 Comparing EXISTS and VALUE

~~~sql
SELECT id,
       CASE
           WHEN payload IS NULL THEN 'SQL NULL DOCUMENT'
           WHEN JSON_EXISTS(payload, '$.status') THEN 'FIELD PRESENT'
           ELSE 'FIELD MISSING'
       END AS field_state,
       JSON_VALUE(
           payload,
           '$.status'
           RETURNING VARCHAR2(100)
           NULL ON EMPTY
           NULL ON ERROR
       ) AS status_value
FROM json_state_lab
ORDER BY id;
~~~

Observations:

- ID 1: input document is SQL NULL.
- ID 2: document exists, but the field is missing.
- ID 3: field exists, value is JSON null.
- ID 4: field exists with a scalar string.
- ID 5: field exists, JSON empty string; when converted to a SQL character value, it may become SQL NULL per Oracle's empty string semantics.
- ID 6 and 7: path points to an array/object, not a valid scalar for JSON_VALUE; with NULL ON ERROR, the result may be SQL NULL.

### 16.4 Using ERROR ON EMPTY to Detect Missing Fields

~~~sql
SELECT JSON_VALUE(
         payload,
         '$.status'
         RETURNING VARCHAR2(100)
         ERROR ON EMPTY
         ERROR ON ERROR
       )
FROM json_state_lab
WHERE id = 2;
~~~

This query raises an error because the status field does not exist. If changed to id = 3, the path finds JSON null so ON EMPTY is not triggered; JSON_VALUE returns SQL NULL per JSON null semantics.

### 16.5 Using JSON_QUERY to Inspect JSON Representation

On releases and return types that support JSON scalars:

~~~sql
SELECT JSON_QUERY(
         payload,
         '$.status'
         RETURNING CLOB
         WITH WRAPPER
         EMPTY ARRAY ON EMPTY
         ERROR ON ERROR
       ) AS status_json
FROM json_state_lab
WHERE id IN (2, 3, 4, 5);
~~~

WITH WRAPPER wraps the match in a JSON array to handle scalars consistently on releases with scalar-return restrictions. EMPTY ARRAY ON EMPTY returns [] if the field is missing. A JSON null field can be represented as [null]; an empty string as [""]; a normal string as ["ACTIVE"].

Before running on older versions, verify scalar return support and EMPTY ARRAY ON EMPTY syntax for that release. If unsupported, use JSON_EXISTS to determine presence and a version-compatible query to display the data.

### 16.6 Cleaning Up Lab Data

~~~sql
DROP TABLE json_state_lab PURGE;
~~~

Only run the cleanup statement if this is the lab table just created and does not contain data you need to keep.

## 17. Choosing a Policy That Fits Business Rules

There is no single ON ERROR/ON EMPTY setting that fits every application. The policy depends on the meaning of the field.

| Field Type | Recommended Policy | Reason |
|---|---|---|
| Mandatory ID | ERROR ON EMPTY ERROR ON ERROR | Missing ID or invalid data must be rejected |
| Optional field | NULL ON EMPTY ERROR ON ERROR | Allows omitting the field, while invalid data is still detected |
| Field with business default | DEFAULT ... ON EMPTY ERROR ON ERROR | Applies the default only when the field is absent |
| Numeric field needing fallback | NULL ON EMPTY DEFAULT ... ON ERROR only with clear rules | Distinguishes missing field from conversion error |
| JSON fragment/object | Use JSON_QUERY, choose appropriate wrapper and ON EMPTY | Do not force objects/arrays into scalars |
| Presence check | Use JSON_EXISTS | Distinguishes missing field from field containing JSON null |
| Data requiring JSON null preservation | Use SQL JSON type / JSON_QUERY RETURNING JSON when supported | Avoids turning JSON null into SQL NULL |

### 17.1 Do Not Use DEFAULT to Mask Data Errors

For example, DEFAULT 0 ON ERROR can turn "abc" into 0. If 0 is a valid number, the system no longer knows the original input was invalid. For mandatory fields, ERROR ON ERROR is usually more appropriate.

### 17.2 Separate Validation from Extraction

A solid data pipeline typically follows these steps:

1. Verify the input column contains a JSON document (not SQL NULL if required).
2. Verify the JSON is well-formed.
3. Verify required fields exist.
4. Verify types and value ranges.
5. Extract into SQL types.
6. Log errors per row/document so they can be reprocessed.

Do not lump all steps into a single JSON_VALUE(... NULL ON ERROR) and treat the resulting NULL as valid data.

## 18. Common Mistakes

| Mistake | Cause | How to Fix |
|---|---|---|
| Thinking ON EMPTY catches JSON null | JSON null is a matched value | Use JSON_EXISTS to check presence |
| Thinking ON ERROR and ON EMPTY are identical | Missing field and runtime error are distinct cases | Configure separate policies for each case |
| Expecting JSON_VALUE to return the string 'null' | JSON null is mapped to SQL NULL | Use JSON_EXISTS/JSON_QUERY when preserving JSON representation |
| Using IS NULL to infer a missing field | Both JSON null and missing can become SQL NULL | Combine JSON_EXISTS and JSON_VALUE |
| Using JSON_VALUE to fetch an object | JSON_VALUE requires a scalar | Use JSON_QUERY or JSON_TABLE |
| Leaving default NULL ON ERROR for mandatory data | Errors can be masked as SQL NULL | Use ERROR ON ERROR and check ON EMPTY |
| Using DEFAULT ON ERROR for every field | Invalid data may be turned into fake valid values | Use fallbacks only when business rules specify |
| Thinking JSON "" always differs from SQL NULL after extraction | Oracle treats empty character strings as SQL NULL | Keep JSON representation or check type |
| Confusing ON EMPTY with EMPTY ARRAY | ON EMPTY is a policy; EMPTY ARRAY is a specific JSON result of JSON_QUERY | Read the clause and function carefully |
| Thinking JSON_EXISTS returns FALSE for JSON null | JSON null is still an existing value | JSON_EXISTS returns TRUE when path matches null |
| Using ERROR ON ERROR to catch bad path syntax | Path syntax errors can fail at compile time | Validate paths before running |
| Confusing JSON_TABLE row path with column path | Two processing levels have different handlers | Analyze row-level and column-level separately |
| Assuming JSON_TABLE no-match always creates a NULL row | Unmatched row paths usually produce zero rows | Use outer join/nested clause when preserving parent rows |
| Not checking database version | Scalar returns, SQL JSON type, and some clauses vary by release | Check the SQL Language Reference for your exact version |

## 19. Implementation Checklist

Before deploying JSON queries into an application, verify:

1. Is the input column SQL JSON, VARCHAR2, CLOB, or BLOB?
2. Can the column be SQL NULL?
3. Is the queried field mandatory or optional?
4. Is a missing field a business error?
5. Is JSON null allowed, and does it carry distinct meaning?
6. Do you need to distinguish JSON null from an empty JSON string?
7. Is JSON_VALUE appropriate because the field is always a scalar?
8. Should JSON_QUERY be used to preserve JSON objects/arrays/null?
9. Should JSON_EXISTS be used to check field presence?
10. Has ON EMPTY been configured independently of ON ERROR?
11. Is the default literal of the right type and aligned with business rules?
12. Does JSON_TABLE require separate row-level and column-level error policies?
13. Has the input been validated as well-formed JSON?
14. Is the path expression valid and tested against representative JSON shapes?
15. Is the syntax compatible with the running Oracle Database version?
16. Are errors converted to NULL logged or tracked?
17. Does the query preserve parent rows when JSON_TABLE finds no row source?
18. Do tests cover SQL NULL, missing, JSON null, scalar, object, array, and malformed JSON?

## 20. Summary

ON ERROR and ON EMPTY allow SQL/JSON queries to handle incomplete data under explicit policies:

- ON ERROR handles runtime errors during JSON evaluation.
- ON EMPTY handles valid paths that find no matching field/value; when both are present, ON EMPTY governs the missing case specifically.
- JSON_VALUE extracts scalars into SQL; JSON null defaults to SQL NULL.
- JSON_EXISTS checks whether a field exists; a field with JSON null is still considered present.
- JSON_QUERY returns JSON representation and can preserve JSON null when the data type and version support it.
- JSON_TABLE has a row path and column paths; distinguish row-level from column-level error handling.
- SQL NULL in the document column, a missing field, and JSON null are three distinct states. A SQL NULL result from an extraction alone is insufficient to distinguish them.
- NULL ON NULL/ABSENT ON NULL belong to generation functions; they differ from ON EMPTY in query functions.

Choose ON EMPTY based on whether a field is mandatory, choose ON ERROR based on validation strictness, and use JSON_EXISTS or JSON-preserving extraction when you need to maintain the distinction between a missing field, JSON null, and SQL NULL.

## 21. Oracle Reference Documentation

- Oracle Database 19c JSON Developer's Guide, “Clauses Used in SQL Query Functions and Conditions”: https://docs.oracle.com/en/database/oracle/oracle-database/19/adjsn/clauses-used-in-functions-and-conditions-for-json.html
- Oracle Database 19c JSON Developer's Guide, “SQL/JSON Function JSON_VALUE”: https://docs.oracle.com/en/database/oracle/oracle-database/19/adjsn/function-JSON_VALUE.html
- Oracle Database 21c SQL Language Reference, “JSON_TABLE”: https://docs.oracle.com/en/database/oracle/oracle-database/21/sqlrf/JSON_TABLE.html
- Oracle Database 26c JSON Developer's Guide, “Overview of JSON in Oracle AI Database” (JSON null and SQL NULL): https://docs.oracle.com/en/database/oracle/oracle-database/26/adjsn/overview-json-oracle-ai-database.html
- Oracle Database 26c JSON Developer's Guide, “Error Clause for SQL Functions and Conditions”: https://docs.oracle.com/en/database/oracle/oracle-database/26/adjsn/error-clause-sql-query-functions-and-conditions.html
- Oracle Database 26c JSON Developer's Guide, “Overview of JSON Generation”: https://docs.oracle.com/en/database/oracle/oracle-database/26/adjsn/overview-json-generation.html
