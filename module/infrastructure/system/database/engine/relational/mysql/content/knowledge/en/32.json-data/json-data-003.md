# JSON Paths, JSON_EXTRACT, and the -> and ->> Operators

MySQL stores JSON documents in the JSON data type and provides JSON paths to locate a value inside a document. Once you know the path, you can use JSON_EXTRACT to retrieve the value, the -> operator as shorthand for JSON_EXTRACT, and the ->> operator to retrieve the value as unquoted text without JSON quotes. These three forms let you query semi-structured data without splitting the entire document into many columns up front.

Within the DATABASE_MYSQL module, this lesson focuses on JSON path syntax, traversing objects and arrays, handling wildcards and multiple paths, distinguishing SQL NULL from JSON null, and choosing between JSON_EXTRACT, ->, and ->>. At the end of the lesson, there are examples of indexing frequently filtered JSON properties to avoid scanning documents across every row.

## 1. Preparing a JSON Table for Practice

MySQL's JSON type validates document syntax on write and stores data in an internal format optimized for component access. A JSON column can contain an object, array, string, number, boolean, or JSON null at the root level.

The JSON data type has existed since MySQL 5.7.8. The -> operator is supported starting in MySQL 5.7.9 and the ->> operator starting in MySQL 5.7.13. If the system runs an older version, use JSON_EXTRACT and JSON_UNQUOTE(JSON_EXTRACT(...)) according to version capabilities.

Create an example table:

~~~sql
CREATE TABLE customer_profiles (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    profile JSON NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB;
~~~

Insert some documents:

~~~sql
INSERT INTO customer_profiles (profile)
VALUES
(
    '{
      "name": "Lan",
      "age": 29,
      "address": {
        "city": "Da Nang",
        "country": "VN"
      },
      "tags": ["premium", "newsletter"],
      "orders": [
        {"sku": "KB-100", "amount": 850000},
        {"sku": "MS-200", "amount": 320000}
      ],
      "preferences": {
        "nickname": null,
        "language": "vi"
      }
    }'
),
(
    '{
      "name": "Minh",
      "age": 35,
      "address": {
        "city": "Ha Noi",
        "country": "VN"
      },
      "tags": ["business"],
      "orders": [],
      "preferences": {
        "language": "en"
      }
    }'
);
~~~

Read the documents:

~~~sql
SELECT customer_id, profile
FROM customer_profiles;
~~~

The first document has nested objects, arrays, numbers, strings, and JSON null. The second document does not have the preferences.nickname property. These two cases will help distinguish a JSON null value from a non-existent path.

## 2. JSON Paths Start with the $ Symbol

A JSON path is an expression indicating a location in a JSON document. In MySQL, the $ symbol represents the document root. Subsequent segments select an object member or an array element.

| Syntax | Meaning | Example |
|---|---|---|
| $ | Entire document | $ |
| $.name | Member name in the root object | $.name |
| $.address.city | Nested member | $.address.city |
| $.orders[0] | First element of the array | $.orders[0] |
| $.orders[1].sku | Member of the second element | $.orders[1].sku |
| $.tags[*] | All elements of the array | $.tags[*] |
| $.address.* | Direct members inside the address object | $.address.* |

Array indices start at 0. Therefore $.orders[0] is the first element, while $.orders[1] is the second element.

Member names in JSON objects are case-sensitive. If a document has the key CustomerName, the path $.customername does not point to the same key.

## 3. Accessing Nested Objects

Use a dot to traverse from one object to a member of a child object:

~~~sql
SELECT
    customer_id,
    JSON_EXTRACT(profile, '$.name') AS customer_name,
    JSON_EXTRACT(profile, '$.address.city') AS city,
    JSON_EXTRACT(profile, '$.address.country') AS country
FROM customer_profiles;
~~~

JSON_EXTRACT returns a JSON value. Therefore strings may display wrapped in double quotes, such as "Lan". This is the JSON representation, not an unquoted SQL string.

You can retrieve an entire child object:

~~~sql
SELECT JSON_EXTRACT(profile, '$.address')
FROM customer_profiles;
~~~

The result is a JSON object containing city and country. Path $ retrieves the entire document; path $.address retrieves only the address object.

## 4. Keys with Spaces or Special Characters

When a member name does not fit standard member-writing rules, enclose the name in double quotes inside the path:

~~~sql
SELECT JSON_EXTRACT(
    '{"shipping address":{"city":"Hue"}}',
    '$."shipping address".city'
) AS shipping_city;
~~~

Similarly, a key with a dot in its name must be quoted so the dot is not interpreted as a hierarchy separator:

~~~sql
SELECT JSON_EXTRACT(
    '{"contact.email":"lan@example.com"}',
    '$."contact.email"'
) AS contact_email;
~~~

In SQL, a path is a string, so it is also subject to string literal escaping rules. When a key contains double quotes or backslashes, it must be properly escaped at both the SQL layer and the JSON path layer. If an application builds paths from user-supplied key names, control escaping instead of arbitrarily concatenating strings.

## 5. Accessing Array Elements

JSON arrays are accessed by index inside square brackets:

~~~sql
SELECT
    JSON_EXTRACT(profile, '$.orders[0].sku') AS first_sku,
    JSON_EXTRACT(profile, '$.orders[1].amount') AS second_amount
FROM customer_profiles;
~~~

To retrieve the entire array:

~~~sql
SELECT JSON_EXTRACT(profile, '$.orders')
FROM customer_profiles;
~~~

To retrieve one element:

~~~sql
SELECT JSON_EXTRACT(profile, '$.tags[0]')
FROM customer_profiles;
~~~

An out-of-range index does not cause MySQL to automatically create a new element. If the path finds no value, JSON_EXTRACT returns SQL NULL. Validate the path and array length if logic requires a mandatory element.

## 6. Wildcards in JSON Paths

Wildcards allow selecting multiple members or elements:

- .* selects direct members of an object.
- [*] selects all direct elements of an array.
- ** is recursive descent, used to find members at nested levels matching the remainder of the path.

Example retrieving SKUs of all orders:

~~~sql
SELECT JSON_EXTRACT(profile, '$.orders[*].sku') AS all_skus
FROM customer_profiles;
~~~

The result of a wildcard path is returned as an array containing the matching values. If the source array is empty or no elements match, the result may be an empty array depending on the path expression.

Object wildcard:

~~~sql
SELECT JSON_EXTRACT(profile, '$.address.*') AS address_values
FROM customer_profiles;
~~~

Recursive descent can find members with the same name at different depths:

~~~sql
SELECT JSON_EXTRACT(
    '{"item":{"sku":"A-1"},"nested":{"item":{"sku":"B-2"}}}',
    '$**.sku'
) AS all_skus;
~~~

Wildcards are useful when nesting structure is not fixed, though the result can be large. Do not use overly broad paths on large documents when the application only needs a few specific attributes.

## 7. JSON_EXTRACT: Function to Retrieve JSON Values

Syntax:

~~~sql
JSON_EXTRACT(json_doc, path[, path] ...)
~~~

The first parameter is a JSON document or an expression returning JSON. Each path specifies a location to retrieve. The function returns JSON; it does not automatically convert JSON strings into unquoted SQL strings.

Example:

~~~sql
SELECT
    JSON_EXTRACT(profile, '$.name') AS name_json,
    JSON_EXTRACT(profile, '$.age') AS age_json,
    JSON_EXTRACT(profile, '$.address.city') AS city_json
FROM customer_profiles;
~~~

JSON_EXTRACT can retrieve an object, array, string, number, boolean, or JSON null. If the path is valid but matches no value, the result is SQL NULL. If the document or a path argument is SQL NULL, the function can also return SQL NULL.

A syntactically invalid path is not equivalent to a non-existent path: an invalid path can cause the statement to error. Therefore, dynamic path data must be validated before use.

## 8. Passing Multiple Paths to JSON_EXTRACT

JSON_EXTRACT allows passing multiple paths in a single call:

~~~sql
SELECT JSON_EXTRACT(
    profile,
    '$.name',
    '$.age',
    '$.address.city'
) AS selected_values
FROM customer_profiles;
~~~

When multiple paths are passed, matching values are automatically wrapped in an array in the order of the paths supplied. For example, with the first document, the result looks like:

~~~json
["Lan", 29, "Da Nang"]
~~~

This differs from calling JSON_EXTRACT with a single path, where the function returns the value at that path directly. A non-matching path does not inject a synthetic JSON null element into the result array; if no path matches, the function returns SQL NULL. Inspect the results carefully when mixing mandatory and optional paths.

## 9. The -> Operator as Shorthand for JSON_EXTRACT

The -> operator provides concise JSON path access:

~~~sql
SELECT
    profile -> '$.name' AS name_json,
    profile -> '$.address.city' AS city_json,
    profile -> '$.orders[0].sku' AS first_sku_json
FROM customer_profiles;
~~~

Semantically, the expression:

~~~sql
profile -> '$.name'
~~~

is equivalent to:

~~~sql
JSON_EXTRACT(profile, '$.name')
~~~

The -> operator still returns a JSON value. If the value is a string, the result keeps its double-quoted JSON representation. If you need a plain text string for display, string concatenation, or comparison with an SQL value, consider ->> or JSON_UNQUOTE.

In the operator syntax, the left-hand side must be a column identifier and the right-hand side a string-literal path. If the left-hand expression is complex or the path needs to be passed dynamically, use explicit JSON_EXTRACT when appropriate for MySQL syntax and version. Never concatenate user-supplied paths into SQL without validation and escaping.

## 10. The ->> Operator to Retrieve Unquoted Values

The ->> operator is shorthand for:

~~~sql
JSON_UNQUOTE(JSON_EXTRACT(json_doc, path))
~~~

Example:

~~~sql
SELECT
    profile -> '$.name' AS name_json,
    profile ->> '$.name' AS name_text,
    profile ->> '$.address.city' AS city_text
FROM customer_profiles;
~~~

For the JSON string value "Lan":

- profile -> '$.name' returns the JSON representation "Lan".
- profile ->> '$.name' returns the string Lan without JSON quotes.

For numbers or booleans, ->> returns the textual representation of the value. It does not automatically turn a numeric string into an SQL numeric type; when arithmetic or numeric-domain comparisons are needed, use an explicit CAST.

For objects or arrays, the result remains the JSON textual representation of the object/array. ->> does not flatten nested structures.

## 11. Comparing the Three Forms

| Form | Meaning | Result |
|---|---|---|
| JSON_EXTRACT(profile, '$.name') | Function retrieving a value by path | JSON |
| profile -> '$.name' | Shorthand operator for JSON_EXTRACT | JSON |
| profile ->> '$.name' | JSON_UNQUOTE(JSON_EXTRACT(...)) | Text with JSON quotes stripped |

Choose the form based on your goal:

- Use JSON_EXTRACT when you need multiple paths or want to make the function call explicit.
- Use -> when querying a single simple path and wanting to preserve the JSON type.
- Use ->> when retrieving a scalar as text for display or type casting.

Do not use ->> just because the output looks easier to read. If you need to compare numbers, dates, or booleans, convert and validate the data type according to business rules.

## 12. Distinguishing SQL NULL, JSON null, and Missing Paths

This is a critical distinction when querying JSON:

- SQL NULL is the state of having no SQL value.
- JSON null is a valid value inside a JSON document.
- A non-existent path means the document lacks the requested member or element; JSON_EXTRACT returns SQL NULL.

With the first document:

~~~sql
SELECT
    JSON_EXTRACT(profile, '$.preferences.nickname') AS nickname,
    JSON_EXTRACT(profile, '$.preferences.timezone') AS timezone
FROM customer_profiles
WHERE customer_id = 1;
~~~

nickname exists and has the value JSON null. timezone does not exist, so the result is SQL NULL.

You can check whether a path exists:

~~~sql
SELECT
    JSON_CONTAINS_PATH(
        profile,
        'one',
        '$.preferences.nickname'
    ) AS has_nickname,
    JSON_CONTAINS_PATH(
        profile,
        'one',
        '$.preferences.timezone'
    ) AS has_timezone
FROM customer_profiles
WHERE customer_id = 1;
~~~

JSON_CONTAINS_PATH returns 1 if at least one path is found with mode one, and 0 if no path matches. Mode all requires all supplied paths to exist.

Check JSON null with JSON_TYPE:

~~~sql
SELECT
    JSON_TYPE(
        JSON_EXTRACT(profile, '$.preferences.nickname')
    ) AS nickname_type,
    JSON_TYPE(
        JSON_EXTRACT(profile, '$.preferences.timezone')
    ) AS timezone_type
FROM customer_profiles
WHERE customer_id = 1;
~~~

For nickname, JSON_TYPE returns the string NULL to indicate the JSON null type. For the non-existent timezone, JSON_EXTRACT returns SQL NULL, so JSON_TYPE also returns SQL NULL. Do not rely solely on IS NULL when you need to distinguish these two cases.

## 13. Checking Data Types Before Conversion

JSON_TYPE tells you the type of a JSON value:

~~~sql
SELECT
    JSON_TYPE(JSON_EXTRACT(profile, '$.name')) AS name_type,
    JSON_TYPE(JSON_EXTRACT(profile, '$.age')) AS age_type,
    JSON_TYPE(JSON_EXTRACT(profile, '$.tags')) AS tags_type
FROM customer_profiles;
~~~

Common results include OBJECT, ARRAY, STRING, INTEGER, DOUBLE, DECIMAL, BOOLEAN, and NULL. A missing path produces SQL NULL rather than a JSON type.

If an application expects age to be a number but a document might contain the string "29", check JSON_TYPE or perform intentional CASTing. Do not assume all documents follow the same schema merely because the column type is JSON.

Example converting age to an integer:

~~~sql
SELECT
    customer_id,
    CAST(profile ->> '$.age' AS UNSIGNED) AS age_number
FROM customer_profiles;
~~~

CAST helps define the SQL result type. However, invalid or unconvertible data can produce warnings, unexpected results, or errors depending on context and SQL mode. For untrusted input data, check types and value ranges before using them in calculations.

## 14. Filtering Rows Using JSON Paths

You can use JSON_EXTRACT or -> in WHERE:

~~~sql
SELECT customer_id, profile ->> '$.name' AS customer_name
FROM customer_profiles
WHERE profile ->> '$.address.city' = 'Da Nang';
~~~

For numeric properties:

~~~sql
SELECT customer_id
FROM customer_profiles
WHERE CAST(profile ->> '$.age' AS UNSIGNED) >= 30;
~~~

For array elements, JSON_CONTAINS can check whether a JSON value is contained in the document:

~~~sql
SELECT customer_id
FROM customer_profiles
WHERE JSON_CONTAINS(profile, '"premium"', '$.tags');
~~~

JSON_CONTAINS is a JSON structure/value containment check; it is not synonymous with substring matching via LIKE. Choose the function matching the data semantics.

When using CAST in WHERE, MySQL may have to evaluate the expression for many rows if no suitable index exists. If a path frequently appears in filter conditions, consider a generated column or a functional index appropriate for the version.

## 15. Indexing Frequently Queried JSON Properties

A JSON column cannot be indexed directly like a normal numeric or string column to look up arbitrary nested values. A common approach is to create a generated column extracting the needed path and then index that column.

Example creating a city column:

~~~sql
ALTER TABLE customer_profiles
    ADD COLUMN city VARCHAR(80)
        GENERATED ALWAYS AS (
            profile ->> '$.address.city'
        ) STORED,
    ADD INDEX idx_customer_profiles_city (city);
~~~

Queries can filter by city:

~~~sql
SELECT customer_id
FROM customer_profiles
WHERE city = 'Da Nang';
~~~

A generated column specifies a clear SQL type and allows creating a standard index. STORED persists the generated value in the row; VIRTUAL computes the value on read yet can still be indexed under MySQL's generated column rules.

For numeric properties, declare a numeric type and an explicit CAST:

~~~sql
ALTER TABLE customer_profiles
    ADD COLUMN age_number INT
        GENERATED ALWAYS AS (
            CAST(profile ->> '$.age' AS UNSIGNED)
        ) STORED,
    ADD INDEX idx_customer_profiles_age (age_number);
~~~

Before deploying, ensure existing JSON data has convertible age values within the INT range. If documents lack age or contain an unsuitable type, define the desired behavior and validate data before adding the generated column.

## 16. Generated Columns and Functional Indexes

A generated column is suitable when:

- A path is used across multiple queries.
- An explicit SQL type such as VARCHAR, INT, or DECIMAL is needed.
- You want to name the JSON property like a readable business column.
- You want an index and optimizer statistics on that property.

MySQL 8.0.13 and later also support functional key parts to index an expression directly. However, JSON expressions must be written with explicit types and collations; generated columns are often easier to inspect and reuse.

Illustrative functional index example for string values:

~~~sql
CREATE INDEX idx_profile_city_expression
ON customer_profiles (
    (CAST(profile ->> '$.address.city' AS CHAR(80)))
);
~~~

Whether the index can be used depends on the query expression matching the indexed expression, data type, and collation. Use EXPLAIN to confirm the optimizer actually chooses the index; successfully creating an index does not guarantee every query will use it.

## 17. JSON Paths in SELECT, WHERE, and ORDER BY

JSON paths can appear in multiple parts of a query:

~~~sql
SELECT
    customer_id,
    profile ->> '$.name' AS customer_name,
    CAST(profile ->> '$.age' AS UNSIGNED) AS age_number
FROM customer_profiles
WHERE profile ->> '$.address.country' = 'VN'
ORDER BY CAST(profile ->> '$.age' AS UNSIGNED) DESC;
~~~

In this example, the same age path is extracted and cast in both SELECT and ORDER BY. If this query runs frequently on a large table, generated columns age_number and city/country can make the query clearer and provide index opportunities.

Avoid writing different paths for the same property due to inconsistent casing or key naming. A stable JSON schema convention reduces query bugs and makes indexes easier to maintain.

## 18. Multiple Paths and Wildcards Can Increase Result Size

JSON_EXTRACT can return large objects or arrays if the path fetches a whole branch of a document or uses wildcards. That increases network transfer volume and parsing work in the application.

Example:

~~~sql
-- Fetch the entire address object.
SELECT JSON_EXTRACT(profile, '$.address')
FROM customer_profiles;

-- Fetch only city.
SELECT profile ->> '$.address.city'
FROM customer_profiles;
~~~

If the application only needs city, choosing a specific path reduces result size. When a wildcard path matches many elements, check the element count and avoid returning the entire array when only an aggregate is needed.

## 19. Common Mistakes When Using JSON Paths and Operators

| Mistake | Cause | How to Handle |
|---|---|---|
| Using $.orders[1] expecting the first element | Arrays are 0-indexed | Use [0] for the first element |
| Key has a space but writing $.shipping address | Path does not parse the key as expected | Use $."shipping address" |
| Comparing a JSON string to text with wrong type | JSON_EXTRACT returns quoted JSON | Use ->> or JSON_UNQUOTE |
| Using ->> and assuming the result is a number | The result is text | CAST to a numeric type after validating data |
| Treating JSON null as SQL NULL | Two distinct states | Combine JSON_CONTAINS_PATH and JSON_TYPE |
| Failing to distinguish invalid path from missing path | Invalid syntax may error; valid missing path returns SQL NULL | Validate paths and check existence |
| Using wildcards on very large documents | Output can be a large array | Choose narrow paths and limit data |
| Filtering JSON on a large table without an index | Expression is evaluated for many rows | Use a generated column or functional index |
| Assuming JSON paths are case-insensitive | JSON member names are case-sensitive | Use exact key names |
| Concatenating paths from unescaped input | Keys with special characters break the path or alter meaning | Escape and validate member names |

## 20. Workflow for Choosing How to Access Values

1. Identify the JSON document and the key to retrieve.
2. Write the path starting with $, checking each member and array index.
3. If a key contains spaces or dots, use quoted member syntax.
4. Use JSON_EXTRACT to verify the JSON value first.
5. Choose -> if you need the JSON representation; choose ->> if you need text.
6. Use JSON_TYPE to verify types when data may be heterogeneous.
7. Distinguish JSON null, SQL NULL, and non-existent paths.
8. Explicitly CAST when numeric or other SQL types are needed.
9. If a path appears frequently in WHERE/ORDER BY, consider a generated column or functional index.
10. Use EXPLAIN to verify the plan and measure on representative data.
11. Verify MySQL version and path syntax before deployment.
12. Keep key naming conventions and JSON schemas consistent across services.

## 21. Practice Exercises

1. Create the customer_profiles table and insert the two sample JSON documents from the beginning of the lesson.
2. Use JSON_EXTRACT to retrieve name, age, and address.city.
3. Retrieve the entire address object and the first element of orders.
4. Use the path $."shipping address".city on a document containing a key with spaces.
5. Use the wildcard $.orders[*].sku to retrieve the list of SKUs.
6. Call JSON_EXTRACT with two or three paths and observe the automatic array result.
7. Compare profile -> '$.name' with profile ->> '$.name'.
8. Use JSON_TYPE to distinguish STRING, INTEGER, ARRAY, OBJECT, and JSON null.
9. Use JSON_CONTAINS_PATH to distinguish nickname having value JSON null from a missing timezone.
10. Filter customers by city and age; CAST age to a numeric type before comparing.
11. Create a generated column city and an index; use EXPLAIN to inspect a query filtering by city.
12. Create a generated column age_number, validate the input data, and then index it.
13. Compare a query fetching the entire address object against a query fetching only address.city in terms of result size.
14. Explain when to use JSON_EXTRACT, ->, and ->> in an API that reads customer profiles.

You have completed this lesson when you can write accurate JSON paths for objects and arrays, distinguish JSON results from unquoted text, properly handle JSON null and non-existent paths, and move frequently filtered JSON attributes into indexed generated columns. JSON is flexible at the storage layer, yet efficient querying still requires clearly designed data types, paths, and indexes.
