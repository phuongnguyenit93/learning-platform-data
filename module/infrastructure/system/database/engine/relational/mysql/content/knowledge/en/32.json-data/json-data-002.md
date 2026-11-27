# JSON Objects, Arrays, Scalars, and Differences Between JSON null and SQL NULL

MySQL supports storing and processing JSON data via the `JSON` column type along with functions for building, validating, extracting, and modifying JSON documents. Before querying JSON, you need to understand the structures of a JSON document: **object**, **array**, and **scalar**. You also need to clearly distinguish the JSON literal `null`, SQL `NULL`, and the case where a JSON path does not exist. These three cases have different meanings and directly affect filter conditions, data updates, and application logic.

This lesson belongs to the **DATABASE_MYSQL** module. The module aims at mastering MySQL from table design, data types, keys, and SQL queries to indexes, transactions, and concurrency control; as well as practicing reading execution plans, query tuning, authorization, backups, and handling relational database operational issues. Within the **JSON** chapter, this lesson focuses on JSON objects, arrays, scalars, and the differences between JSON `null` and SQL `NULL`. `SPECIAL_NOTE` is provided empty, so there are no additional custom constraints for this lesson.

## 1. What Value Types Make Up a JSON Document?

JSON defines six basic value types:

| Type | JSON Example | Meaning |
|---|---|---|
| Object | `{"id": 10, "name": "Lan"}` | Collection of key/value pairs; keys are strings. |
| Array | `["red", "green", "blue"]` | Ordered list of values. |
| String | `"MySQL"` | Character string, always enclosed in JSON double quotes. |
| Number | `42`, `19.95`, `-3` | Numeric value, not enclosed in quotes. |
| Boolean | `true`, `false` | JSON logical value, lowercase. |
| Null | `null` | Empty value according to the JSON data model. |

Object and array are the two container structures; string, number, boolean, and null are scalars. A document can contain nested containers and scalars at any valid position.

Example of a document combining multiple types:

```json
{
  "customerId": 1001,
  "name": "Lan Nguyen",
  "active": true,
  "nickname": null,
  "tags": ["premium", "newsletter"],
  "address": {
    "city": "Da Nang",
    "postalCode": "550000"
  }
}
```

The root value of this document is an object. Inside the object are a number, string, boolean, JSON null, array, and a nested object.

## 2. JSON Object

An object is a collection of key/value pairs enclosed in `{}`. Each key must be a JSON string and is separated from its value by a colon `:`. Pairs are separated by commas:

```json
{
  "productId": 501,
  "productName": "Mechanical Keyboard",
  "price": 1250000,
  "inStock": true
}
```

Rules to remember:

- Keys are strings and must be enclosed in double quotes `"` per JSON syntax.
- Values can be an object, array, or any JSON scalar.
- Keys/values are separated by `:`, and pairs are separated by `,`.
- Do not use a trailing comma after the last element.
- JSON is case-sensitive for key names; `name` and `Name` are two different keys.
- Key order within an object does not carry meaning like array element order does. Do not write logic that depends on key order after MySQL stores and normalizes the document.

Duplicate key names should be avoided because they cause confusion for applications. When MySQL normalizes a JSON object with duplicate keys, the last-occurring value is retained in the normalized document.

Example to avoid:

```json
{
  "status": "NEW",
  "status": "PAID"
}
```

Ensure each key appears only once in objects sent by the application to the database.

## 3. JSON Array

An array is an ordered list of values enclosed in `[]`. Each element can be of any JSON type:

```json
[
  "mysql",
  8,
  true,
  null,
  {"topic": "index"}
]
```

Arrays use 0-based indexing in JSON paths:

| Element | JSON Path |
|---|---|
| First element | `$[0]` |
| Second element | `$[1]` |
| Third element | `$[2]` |

Example of nested arrays/objects:

```json
{
  "orderId": 9001,
  "items": [
    {"sku": "KB-200", "quantity": 1},
    {"sku": "MS-100", "quantity": 2}
  ]
}
```

`items` is an array of two objects. The first element has path `$.items[0]`; the SKU attribute of the first element has path `$.items[0].sku`.

Array element order is meaningful. If you need to preserve display order or priority order, an array is more suitable than an object.

## 4. JSON Scalar

A scalar is a single value that does not contain key/value pairs or child lists. The four JSON scalar types are string, number, boolean, and null.

### 4.1. String

A JSON string is always enclosed in double quotes:

```json
"MySQL"
```

The empty string `""` differs from JSON null and SQL NULL. The string `"null"` is also a four-character string, not JSON null.

### 4.2. Number

Numbers are not enclosed in quotes:

```json
125
19.95
-3
1.25e3
```

`"125"` is a string, whereas `125` is a number. Do not store numbers intended for calculation as strings if the application expects to process them as numeric values.

### 4.3. Boolean

JSON has only two lowercase boolean literals:

```json
true
false
```

`"true"` is a string; `TRUE` is not a valid JSON boolean literal.

### 4.4. Null

JSON null is the lowercase literal:

```json
null
```

JSON null represents a null value inside a JSON document. It is not synonymous with SQL NULL on a table column.

## 5. Objects, Arrays, and Scalars at the Root Position

A valid JSON document can have an object, array, or scalar as its root value:

```json
{"kind": "object"}
```

```json
["mysql", "json"]
```

```json
"a scalar string"
```

```json
123
```

```json
true
```

```json
null
```

Not every document has to start with `{`. If the application needs metadata with multiple attributes, an object is usually the convenient choice. If the data is just a list, an array may fit. A scalar at the root is valid, but the data contract should be standardized so all clients know the expected root type.

## 6. JSON Text and JSON String Are Two Different Concepts

JSON text is the textual representation of a JSON value. A JSON value itself can be a string. Therefore, a JSON string at the root must have double quotes inside the JSON text:

```sql
-- The JSON document is an object.
SELECT JSON_TYPE('{"name": "Lan"}');

-- The JSON document is a scalar string.
SELECT JSON_TYPE('"Lan"');

-- The JSON document is a scalar number.
SELECT JSON_TYPE('42');
```

In SQL statements, literals are wrapped in SQL single quotes; the double quotes inside are JSON syntax. Do not confuse the SQL string `'Lan'` (which is not valid JSON text if used directly as a document) with the JSON text `'"Lan"'`.

## 7. MySQL's Native JSON Data Type

MySQL provides the `JSON` column type. When writing a value to a JSON column, MySQL checks whether the input text is valid JSON. The value is stored in an internal binary format so the server can access elements without re-parsing the entire text on every read.

Example table creation:

```sql
CREATE TABLE customer_profiles (
    customer_id BIGINT NOT NULL PRIMARY KEY,
    profile JSON NOT NULL
) ENGINE = InnoDB;
```

Inserting an object:

```sql
INSERT INTO customer_profiles (customer_id, profile)
VALUES (
    1001,
    '{"name": "Lan Nguyen", "active": true, "tags": ["vip", "email"]}'
);
```

Inserting using JSON constructor functions:

```sql
INSERT INTO customer_profiles (customer_id, profile)
VALUES (
    1002,
    JSON_OBJECT(
        'name', 'Minh Tran',
        'active', CAST('true' AS JSON),
        'tags', JSON_ARRAY('new', 'mobile')
    )
);
```

`JSON_OBJECT()` constructs an object; `JSON_ARRAY()` constructs an array. These functions help build JSON without manually concatenating strings and handling character escaping.

Notes:

- A JSON column only accepts valid JSON, or SQL NULL if the column allows NULL.
- Syntactically invalid JSON strings are rejected when written to a JSON column.
- MySQL normalizes the JSON representation; do not expect returned text to preserve the input's exact whitespace or key order.
- Native JSON does not replace relational design for attributes requiring foreign keys, constraints, frequent joins, or direct B-tree indexes.

## 8. Checking JSON Types with JSON_TYPE and JSON_VALID

`JSON_TYPE()` returns the type of a JSON value:

```sql
SELECT JSON_TYPE('{"name": "Lan"}') AS value_type;
SELECT JSON_TYPE('["mysql", "json"]') AS value_type;
SELECT JSON_TYPE('"MySQL"') AS value_type;
SELECT JSON_TYPE('42') AS value_type;
SELECT JSON_TYPE('true') AS value_type;
SELECT JSON_TYPE('null') AS value_type;
```

The corresponding results are OBJECT, ARRAY, STRING, INTEGER, BOOLEAN, and NULL. Here, the result string `'NULL'` (case-insensitive when comparing strings under an appropriate collation) is the name of the JSON null type, not SQL NULL.

`JSON_VALID()` checks whether a string has a valid JSON representation:

```sql
SELECT JSON_VALID('{"id": 10, "active": true}') AS valid_document;
SELECT JSON_VALID('{"id": 10,}') AS invalid_document;
SELECT JSON_VALID('"plain string"') AS valid_scalar;
SELECT JSON_VALID('plain string') AS invalid_text;
```

`JSON_VALID()` returns 1 if the argument is valid JSON and 0 if invalid; if the SQL argument is NULL, the result is SQL NULL. This function is useful when data is stored in a TEXT column or when validating input before converting to the JSON type.

For a native JSON column, MySQL already checks validity at write time. Therefore, there is no need to call `JSON_VALID(profile)` in every SELECT just to re-verify the column's invariant.

## 9. JSON null and SQL NULL

Two similarly named concepts belong to two different layers:

- **JSON null** is a valid JSON value inside a document, e.g., `{"nickname": null}`.
- **SQL NULL** is the SQL column's NULL value, indicating the column has no value in SQL semantics.

A nullable JSON column can hold both a JSON document whose root value is null and SQL NULL:

```sql
CREATE TABLE json_null_demo (
    id INT NOT NULL PRIMARY KEY,
    payload JSON NULL
) ENGINE = InnoDB;

INSERT INTO json_null_demo (id, payload)
VALUES
    (1, 'null'),
    (2, NULL),
    (3, '{"nickname": null}'),
    (4, '{"name": "Lan"}');
```

Interpretation:

| id | payload Value | Meaning |
|---:|---|---|
| 1 | `null` | JSON document whose root value is JSON null. |
| 2 | SQL NULL | SQL column has no value. |
| 3 | `{"nickname": null}` | Object exists; the nickname property has JSON null. |
| 4 | `{"name": "Lan"}` | Object does not have the nickname property. |

Therefore, you cannot simply look at the word "null" in text output and conclude it is SQL NULL. You must inspect using the appropriate SQL operators and JSON functions.

## 10. Distinguishing SQL NULL, JSON null, and Missing Paths

Assume the `json_null_demo` table above:

| State | `payload IS NULL` | `JSON_TYPE(payload)` | `JSON_CONTAINS_PATH(payload, 'one', '$.nickname')` |
|---|---:|---|---:|
| SQL NULL at id 2 | 1 | SQL NULL | SQL NULL |
| JSON null at root, id 1 | 0 | `NULL` (JSON type name) | 0 |
| Object with nickname:null, id 3 | 0 | OBJECT | 1 |
| Object without nickname, id 4 | 0 | OBJECT | 0 |

Both an object missing the path and an object whose path holds JSON null differ from SQL NULL for the entire column. `JSON_CONTAINS_PATH()` helps check whether an attribute exists, even when the attribute value is JSON null.

You can inspect each row individually:

```sql
SELECT
    id,
    payload IS NULL AS sql_null,
    JSON_TYPE(payload) AS root_json_type,
    JSON_CONTAINS_PATH(payload, 'one', '$.nickname') AS has_nickname,
    JSON_TYPE(JSON_EXTRACT(payload, '$.nickname')) AS nickname_json_type
FROM json_null_demo
ORDER BY id;
```

Reading notes:

- `payload IS NULL` checks SQL NULL at the column level.
- `JSON_TYPE(payload)` returns the root JSON type if payload is not SQL NULL.
- `JSON_CONTAINS_PATH(...)` checks whether the path exists.
- `JSON_TYPE(JSON_EXTRACT(...))` returns the type of the extracted value; if the path does not exist or the argument is SQL NULL, the result may be SQL NULL.

For id 3, the path exists and the extracted value type is JSON NULL. For id 4, the path does not exist and extraction returns SQL NULL. To distinguish these two cases reliably, combine with checking path existence.

## 11. JSON Paths for Accessing Objects and Arrays

A JSON path in MySQL starts with the `$` symbol, representing the root document. Then key-access or array-index syntax follows:

| Structure | JSON Path | Meaning |
|---|---|---|
| Top-level key | `$.name` | The name property on the root object. |
| Nested key | `$.address.city` | The city property inside address. |
| Array element | `$.items[0]` | First element of items. |
| Property inside array | `$.items[0].sku` | SKU of the first object in items. |
| Key with spaces | `$."display name"` | Key containing whitespace. |
| All array elements | `$.items[*]` | All elements of the items array. |

Extraction examples:

```sql
SELECT
    JSON_EXTRACT(
        '{"name": "Lan", "address": {"city": "Da Nang"}}',
        '$.address.city'
    ) AS city;

SELECT
    JSON_EXTRACT(
        '{"items": [{"sku": "KB-200"}, {"sku": "MS-100"}]}',
        '$.items[0].sku'
    ) AS first_sku;
```

`JSON_EXTRACT()` returns a JSON value. If the path does not match the document, the result is SQL NULL. If the path matches an attribute whose value is JSON null, the result is JSON null. This is why you must combine with `JSON_CONTAINS_PATH()` when you need to know whether the attribute exists.

## 12. JSON Constructor Functions and Scalar Handling

### 12.1. JSON_OBJECT

`JSON_OBJECT(key, value, ...)` creates an object from key/value pairs:

```sql
SELECT JSON_OBJECT(
    'customerId', 1001,
    'name', 'Lan Nguyen',
    'active', CAST('true' AS JSON),
    'nickname', NULL
) AS customer_json;
```

SQL NULL values are converted to JSON null inside the object. Each key must have a corresponding value; the argument count must be even, and a key cannot be SQL NULL.

### 12.2. JSON_ARRAY

`JSON_ARRAY(value, ...)` creates an array; values are kept in the order passed:

```sql
SELECT JSON_ARRAY(
    'mysql',
    8,
    CAST('true' AS JSON),
    NULL,
    JSON_OBJECT('topic', 'json')
) AS values_json;
```

An SQL NULL passed to JSON_ARRAY is represented as a JSON null element, rather than turning the entire array into SQL NULL.

### 12.3. JSON_QUOTE and JSON_UNQUOTE

`JSON_QUOTE()` converts an SQL string into valid JSON string text, including double quotes and escaping special characters:

```sql
SELECT JSON_QUOTE('A "quoted" value');
```

`JSON_UNQUOTE()` strips the JSON double quotes from a JSON string:

```sql
SELECT JSON_UNQUOTE('"MySQL"') AS plain_text;
```

Do not use JSON_UNQUOTE to check data types. If you need to know whether a value is a string, number, boolean, or JSON null, use `JSON_TYPE()`.

## 13. JSON_EXTRACT, the -> and ->> Operators

MySQL provides `JSON_EXTRACT(document, path)` to retrieve values by JSON path. You can use the `->` operator as shorthand when accessing a JSON column:

```sql
SELECT
    profile->'$.name' AS name_json,
    JSON_EXTRACT(profile, '$.active') AS active_json
FROM customer_profiles;
```

`->` returns a JSON value, so a string still carries its quoted JSON representation. The `->>` operator combines extraction and unquoting to return the value as an SQL string:

```sql
SELECT
    profile->>'$.name' AS name_text
FROM customer_profiles;
```

Choose the approach according to your purpose:

- Need to keep the JSON type to pass onward to JSON functions: use `JSON_EXTRACT()` or `->`.
- Need an unquoted string for display or text comparison: use `->>` or `JSON_UNQUOTE(JSON_EXTRACT(...))`.
- Need to check the type: use `JSON_TYPE()`.
- Need to check whether a path exists even when the value is JSON null: use `JSON_CONTAINS_PATH()`.

Do not assume every extracted value is a string. A path may return an object, array, number, boolean, or JSON null.

## 14. Writing SQL Conditions with JSON null and SQL NULL

Do not use `= NULL` or `<> NULL` comparisons in SQL. SQL NULL must be checked using `IS NULL` or `IS NOT NULL`:

```sql
SELECT *
FROM json_null_demo
WHERE payload IS NULL;

SELECT *
FROM json_null_demo
WHERE payload IS NOT NULL;
```

To find documents whose root value is JSON null, check the JSON type:

```sql
SELECT *
FROM json_null_demo
WHERE payload IS NOT NULL
  AND JSON_TYPE(payload) = 'NULL';
```

To find objects that have the nickname property and whose value is JSON null:

```sql
SELECT *
FROM json_null_demo
WHERE JSON_CONTAINS_PATH(payload, 'one', '$.nickname') = 1
  AND JSON_TYPE(JSON_EXTRACT(payload, '$.nickname')) = 'NULL';
```

To find objects that do not have the nickname property:

```sql
SELECT *
FROM json_null_demo
WHERE payload IS NOT NULL
  AND JSON_TYPE(payload) = 'OBJECT'
  AND JSON_CONTAINS_PATH(payload, 'one', '$.nickname') = 0;
```

The order of checks helps prevent confusion between SQL NULL and JSON null. If data can contain multiple different root types, check the root type before applying object-specific paths.

## 15. Using CASE to Classify States

You can use CASE to turn the states into clear labels:

```sql
SELECT
    id,
    CASE
        WHEN payload IS NULL THEN 'SQL NULL'
        WHEN JSON_TYPE(payload) = 'NULL' THEN 'JSON null at root'
        WHEN JSON_CONTAINS_PATH(payload, 'one', '$.nickname') = 0
            THEN 'nickname missing'
        WHEN JSON_TYPE(JSON_EXTRACT(payload, '$.nickname')) = 'NULL'
            THEN 'nickname is JSON null'
        ELSE 'nickname has a value'
    END AS nickname_state
FROM json_null_demo
ORDER BY id;
```

CASE checks SQL NULL before calling JSON functions to make the intent clear and avoid relying on function behavior over SQL NULL. For id 1, the root document is JSON null so there is no nickname; id 2 is SQL NULL; id 3 has nickname set to JSON null; id 4 is missing nickname.

## 16. JSON null Differs from Removing a Property

In an object, the following two states are not the same:

```json
{"nickname": null}
```

```json
{}
```

The first document has the key `nickname` with value JSON null. The second document does not have that key. This difference matters if an API uses an omitted key to mean "send no change", while JSON null means "clear current value" or "value unknown".

MySQL provides `JSON_REMOVE()` to remove a path:

```sql
SELECT JSON_REMOVE(
    '{"name": "Lan", "nickname": null}',
    '$.nickname'
) AS without_nickname;
```

The result is an object with the nickname key removed. Meanwhile, an object having a key with JSON null can still be created using `JSON_SET()`:

```sql
SELECT JSON_SET(
    '{"name": "Lan"}',
    '$.nickname',
    CAST('null' AS JSON)
) AS nickname_set_to_json_null;
```

When updating JSON from an application, agree on the contract: what business meaning an omitted key, a key with JSON null, and a column SQL NULL each carry.

## 17. Storing Objects, Arrays, and Scalars in a JSON Column

A JSON column can store many JSON value types, not just objects:

```sql
CREATE TABLE json_root_values (
    id INT NOT NULL PRIMARY KEY,
    document JSON NOT NULL
) ENGINE = InnoDB;

INSERT INTO json_root_values (id, document)
VALUES
    (1, '{"kind": "object"}'),
    (2, '["mysql", "json"]'),
    (3, '"scalar string"'),
    (4, '123'),
    (5, 'true'),
    (6, 'null');

SELECT
    id,
    JSON_TYPE(document) AS root_type,
    document
FROM json_root_values
ORDER BY id;
```

The root types are respectively OBJECT, ARRAY, STRING, INTEGER, BOOLEAN, and NULL. With `document JSON NOT NULL`, row 6 is still valid because `'null'` is a JSON document whose root value is JSON null, not SQL NULL.

If you try inserting SQL NULL into a `document NOT NULL` column, MySQL rejects it for violating the column's NOT NULL constraint:

```sql
INSERT INTO json_root_values (id, document)
VALUES (7, NULL);
```

If the column is declared nullable, SQL NULL can be stored separately from JSON null.

## 18. Testing Malformed JSON and Common Syntax Errors

MySQL's JSON parser validates syntax. Some common errors:

| Input | Problem |
|---|---|
| `{name: "Lan"}` | Key not enclosed in double quotes. |
| `{"name": "Lan",}` | Trailing comma at the end of the object. |
| `{"active": True}` | Capitalized boolean, invalid JSON literal. |
| `{'name': 'Lan'}` | JSON uses double quotes for strings/keys. |
| `[1, 2,]` | Trailing comma at the end of the array. |

Testing:

```sql
SELECT JSON_VALID('{"name": "Lan"}') AS valid_json;
SELECT JSON_VALID('{name: "Lan"}') AS invalid_key;
SELECT JSON_VALID('{"active": True}') AS invalid_boolean;
SELECT JSON_VALID('[1, 2,]') AS invalid_array;
```

When writing an invalid JSON string to a JSON column, MySQL throws an error rather than storing it as a valid document. If you want to store free-form text that does not need to conform to JSON, use VARCHAR or TEXT.

## 19. Choosing JSON or the Relational Model?

JSON is useful when data has a flexible structure, attributes vary by record type, or you need to store a structured payload from another system. However, you should not put all data into a single JSON column just because MySQL supports this type.

| Data Characteristic | Design Direction to Consider |
|---|---|
| Stable attributes needing NOT NULL/UNIQUE/FK | Regular relational columns. |
| Frequent JOINs with other tables | Relational tables and foreign keys. |
| Group of optional attributes varying by entity type | JSON may be used. |
| Child list requiring independent querying, filtering, updating | Consider a child table instead of a JSON array. |
| External system payload needing near-verbatim structure storage | A JSON column may fit. |
| Values needing frequent indexing and filtering | Relational column or generated column/index over an appropriate JSON expression. |

JSON does not automatically create foreign keys for IDs inside a document and does not automatically guarantee that internal values share the same business type across all records. The application must define the expected schema, validate input, and design how the JSON structure evolves.

## 20. Guidelines When Working with JSON

- Use objects for named properties; use arrays for ordered lists.
- Use numbers for values requiring computation; do not store numbers as strings without reason.
- Use JSON booleans `true`/`false`, not strings `"true"`/`"false"` as substitutes.
- Explicitly decide the meaning of JSON null, SQL NULL, and a missing key.
- Use JSON_OBJECT/JSON_ARRAY instead of building JSON via manual string concatenation.
- Use JSON_TYPE to check types, JSON_VALID to validate input text, and JSON_CONTAINS_PATH to check path existence.
- Do not depend on object key order after MySQL normalizes the document.
- Avoid duplicate keys in objects.
- Store in JSON only the attributes that truly need flexibility; core attributes should have relational columns.
- If filtering frequently by a JSON attribute, evaluate a generated column or functional index appropriate for your MySQL version.

## 21. Comprehensive Lab

The following lab creates a table storing customer profiles, including nested objects, arrays, scalars, JSON null, and missing properties. Run it in a practice schema; if the table already exists, check existing data before recreating it.

### 21.1. Create Table and Data

```sql
CREATE TABLE json_profile_lab (
    customer_id BIGINT NOT NULL PRIMARY KEY,
    profile JSON NULL
) ENGINE = InnoDB;

INSERT INTO json_profile_lab (customer_id, profile)
VALUES
    (
        1001,
        JSON_OBJECT(
            'name', 'Lan Nguyen',
            'active', CAST('true' AS JSON),
            'nickname', NULL,
            'tags', JSON_ARRAY('vip', 'email'),
            'address', JSON_OBJECT('city', 'Da Nang')
        )
    ),
    (
        1002,
        '{"name": "Minh Tran", "active": false, "tags": [], "address": {"city": "Hue"}}'
    ),
    (1003, 'null'),
    (1004, NULL);
```

### 21.2. Inspect Root Types

```sql
SELECT
    customer_id,
    profile IS NULL AS is_sql_null,
    JSON_TYPE(profile) AS root_type
FROM json_profile_lab
ORDER BY customer_id;
```

Row 1003 has root type NULL (JSON type); row 1004 has SQL NULL, so `JSON_TYPE(profile)` returns SQL NULL.

### 21.3. Extract Nested Properties

```sql
SELECT
    customer_id,
    profile->>'$.name' AS customer_name,
    profile->>'$.address.city' AS city,
    JSON_TYPE(JSON_EXTRACT(profile, '$.active')) AS active_type,
    JSON_EXTRACT(profile, '$.tags[0]') AS first_tag
FROM json_profile_lab
WHERE profile IS NOT NULL
  AND JSON_TYPE(profile) = 'OBJECT'
ORDER BY customer_id;
```

The filter excludes SQL NULL and non-object root documents before accessing object paths.

### 21.4. Distinguish Null Nickname from Missing Nickname

```sql
SELECT
    customer_id,
    JSON_CONTAINS_PATH(profile, 'one', '$.nickname') AS has_nickname,
    JSON_TYPE(JSON_EXTRACT(profile, '$.nickname')) AS nickname_type
FROM json_profile_lab
WHERE profile IS NOT NULL
  AND JSON_TYPE(profile) = 'OBJECT'
ORDER BY customer_id;
```

Customer 1001 has the nickname key with JSON null. Customer 1002 does not have the nickname key. Combine the has_nickname and nickname_type columns to distinguish the two cases.

### 21.5. Inspect and Remove a Property

```sql
SELECT JSON_REMOVE(profile, '$.nickname') AS profile_without_nickname
FROM json_profile_lab
WHERE customer_id = 1001;
```

The function above returns a document with the nickname key removed. This is a transformation returning a JSON value; it does not automatically update the row in the table. To write the result back, you must run a separate UPDATE statement and clearly define the business intent.

## 22. Self-Practice Exercises

### Exercise 1: Identify JSON Types

Use `JSON_TYPE()` to determine the types of object, array, string, integer, decimal, boolean, and null.

**Requirement:** explain why `"42"` and `42` have different types.

### Exercise 2: Build Objects and Arrays

Create a customer object with id, name, active status, tags list, and nested address.

**Requirement:** use `JSON_OBJECT()` and `JSON_ARRAY()`, not manual JSON string concatenation.

### Exercise 3: Access JSON Paths

Given a document with an items array containing sku and quantity objects.

**Requirement:** retrieve the first element's SKU, the second element's quantity, and the data type of each value.

### Exercise 4: Distinguish Three Null States

Create three rows: an SQL NULL column, a JSON null document at the root, and an object with a JSON null nickname property; add one more row with an object missing nickname.

**Requirement:** write a single SELECT classifying all four states using `IS NULL`, `JSON_TYPE()`, and `JSON_CONTAINS_PATH()`.

### Exercise 5: JSON null or Deleted Key?

Use `JSON_SET()` to set nickname to JSON null, then use `JSON_REMOVE()` to delete the key.

**Requirement:** prove the two documents have different structures using `JSON_CONTAINS_PATH()`.

### Exercise 6: Validate Invalid JSON

Test strings with unquoted keys, trailing commas, capitalized booleans, and single quotes.

**Requirement:** use `JSON_VALID()` to classify and explain the errors.

### Exercise 7: Choose a Data Model

An order has customer_id, created_at, total_amount, and a set of optional metadata.

**Requirement:** propose which attributes should be relational columns and which can be stored as JSON; explain JOIN, constraint, and index needs.

## 23. Checklist When Designing and Querying JSON

- [ ] Determined the expected root type: object, array, or scalar.
- [ ] Object keys are valid strings and not duplicated.
- [ ] Arrays are used when element order is meaningful.
- [ ] Numbers, booleans, and strings are represented with their proper JSON types.
- [ ] Distinguished the JSON string `"null"` from JSON null `null`.
- [ ] Distinguished JSON null from column SQL NULL.
- [ ] Distinguished a property having JSON null from a non-existent path.
- [ ] Use `IS NULL`/`IS NOT NULL` to check SQL NULL.
- [ ] Use `JSON_TYPE()` to check JSON types.
- [ ] Use `JSON_CONTAINS_PATH()` to check key/path existence.
- [ ] Use `JSON_VALID()` when validating input strings.
- [ ] Use `JSON_OBJECT()`/`JSON_ARRAY()` to construct documents safely.
- [ ] Do not rely on object key order after normalization.
- [ ] Evaluated relational columns, constraints, and generated columns before placing attributes into JSON.
- [ ] Agreed on the business meaning of an omitted key, JSON null, and SQL NULL.

## 24. Key Takeaways

JSON has six value types: object, array, string, number, boolean, and null. Objects store key/value pairs; arrays store ordered lists; scalars are string, number, boolean, or null. A JSON document can have an object, array, or scalar as its root value.

MySQL uses the JSON column type to validate and store documents in an internal format. Use JSON_TYPE to identify types, JSON_VALID to validate text, JSON_OBJECT/JSON_ARRAY to build documents, and JSON_EXTRACT with JSON paths to access data.

SQL NULL, JSON null, and a non-existent path are three distinct states. Use IS NULL to check SQL NULL, JSON_TYPE(...) = 'NULL' to identify JSON null, and JSON_CONTAINS_PATH to confirm whether a property exists. When designing, keep core attributes in the relational model; use JSON for genuinely flexible data with a clear contract with the application.
