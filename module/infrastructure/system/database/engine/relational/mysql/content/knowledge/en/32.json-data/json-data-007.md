# JSON_SET, JSON_INSERT, JSON_REPLACE, and JSON_REMOVE

MySQL stores JSON as structured documents rather than plain text strings. When an application needs to modify a few attributes in a document, it does not have to load the entire JSON into the application, edit a string, and overwrite the whole column. JSON modification functions let you perform updates directly inside SQL expressions:

- `JSON_SET()` adds a property or element if the path does not exist, and replaces the value if the path already exists.
- `JSON_INSERT()` only inserts at paths that do not exist; if the path already has a value, it leaves it unchanged.
- `JSON_REPLACE()` only replaces values at paths that already exist; if the path does not exist, it ignores it.
- `JSON_REMOVE()` deletes values at one or more paths.

Choosing the wrong function can cause an application to accidentally overwrite existing settings, fail to create a new property, or delete the wrong array element. This lesson explains the semantics of each function, how MySQL evaluates JSON paths, evaluation order when passing multiple path-value pairs, how objects and arrays are handled, and how to apply them safely in UPDATE statements.

The examples target MySQL 8.4. Certain row-alias syntax and JSON storage optimization capabilities have specific version milestones; those points are noted where used.

## Learning Objectives

After this lesson, you will be able to:

- Precisely distinguish the behaviors of JSON_SET, JSON_INSERT, JSON_REPLACE, and JSON_REMOVE.
- Read JSON paths for object members, nested objects, and array indices.
- Modify multiple positions in the same document in a deterministic order.
- Understand why JSON modification functions do not automatically create all missing parent objects.
- Distinguish SQL NULL from JSON null.
- Avoid storing a JSON object as a quoted JSON string.
- Add, update, and delete array elements without index-shift mistakes.
- Use JSON_EXTRACT, JSON_TYPE, and JSON_CONTAINS_PATH to inspect before modifying.
- Update JSON directly inside UPDATE statements and transactions.
- Reduce the risk of overwriting concurrent requests' changes.
- Understand the conditions for MySQL to optimize partial updates on JSON columns.
- Design indexes for frequently queried JSON properties.
- Write tests covering existing paths, missing paths, and mistyped data.

## 1. The JSON Document Model in MySQL

JSON is a structurally validated data type. When inserting or updating a JSON column, MySQL validates the input content and rejects invalid JSON documents. MySQL stores the document in an internal format optimized for component access; do not treat a JSON column like an ordinary VARCHAR.

Example profile document:

    {
      "name": "An",
      "email": "an@example.test",
      "preferences": {
        "language": "en",
        "theme": "light"
      },
      "tags": ["mysql", "sql"],
      "temporary_token": "tmp-123"
    }

A document can contain:

- Objects: collections of key-value pairs.
- Arrays: ordered lists of elements.
- Strings, numbers, and booleans.
- JSON null.
- Nested objects or arrays.

A JSON column does not enforce a fixed business schema the way relational columns do. Therefore, the application must standardize key names, data types, the meaning of absent fields, and how null values are handled.

Create a practice table:

    CREATE TABLE customer_profile (
        customer_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
        profile JSON NOT NULL,
        version_no BIGINT UNSIGNED NOT NULL DEFAULT 0,
        updated_at TIMESTAMP NOT NULL
            DEFAULT CURRENT_TIMESTAMP
            ON UPDATE CURRENT_TIMESTAMP
    ) ENGINE = InnoDB;

Insert a profile:

    INSERT INTO customer_profile (
        customer_id,
        profile
    )
    VALUES (
        1,
        JSON_OBJECT(
            'name', 'An',
            'email', 'an@example.test',
            'preferences',
                JSON_OBJECT(
                    'language', 'en',
                    'theme', 'light'
                ),
            'metadata', JSON_OBJECT(),
            'tags', JSON_ARRAY('mysql', 'sql'),
            'temporary_token', 'tmp-123'
        )
    );

JSON_OBJECT and JSON_ARRAY build structured JSON values. This approach is safer than manual JSON string concatenation, especially when values contain quotes, escape characters, or Unicode data.

## 2. JSON Paths: Address of the Value to Modify

The four functions in this lesson accept a JSON document and one or more JSON paths. Each path indicates the position to add, replace, or remove.

### 2.1. Root Path

The `$` symbol represents the entire document.

    SELECT JSON_EXTRACT(
        '{"name":"An","active":true}',
        '$'
    );

### 2.2. Object Member

The dot operator accesses an object property:

    $.name
    $.preferences
    $.preferences.language

JSON member names are case-sensitive. `$.Name` and `$.name` are two different paths.

If a key contains dots, spaces, or special characters, use quoted key syntax:

    $."display.name"
    $."user settings".theme

Example:

    SELECT JSON_EXTRACT(
        '{"display.name":"An"}',
        '$."display.name"'
    );

### 2.3. Array Index

Arrays use 0-based indices:

    $[0]
    $.tags[1]
    $.orders[0].total

Given the array:

    ["mysql", "sql", "database"]

Path `$[0]` points to `"mysql"`; `$[2]` points to `"database"`.

### 2.4. Wildcards Do Not Fit JSON Modification Functions

JSON paths support wildcards in certain query functions, but JSON_SET, JSON_INSERT, JSON_REPLACE, and JSON_REMOVE require concrete paths. Do not use `*` or `**` in paths for these functions.

For instance, a path like `$.items[*].active` is not a way to bulk-update all elements with JSON_SET. Iterate rows/elements using appropriate SQL logic, or normalize data into a relational table if set-based updates are needed frequently.

### 2.5. Parent Paths Must Exist

JSON modification functions do not automatically build an entire intermediate object tree when a parent object is missing.

If the document is:

    {"name":"An"}

The operation:

    SELECT JSON_SET(
        '{"name":"An"}',
        '$.preferences.language',
        'vi'
    );

does not automatically create the `preferences` object and then add `language`. The intermediate path `preferences` does not exist yet, so there is nowhere to attach the child property.

Create the parent object first, or use a nested expression with type checking. Do not assume a deep path will auto-generate all missing intermediate nodes.

## 3. JSON_SET: Insert or Replace

JSON_SET(document, path, value[, path, value] ...) has two behaviors:

- If the path identifies an existing value, replace that value.
- If the path does not exist yet and the location can be created inside an existing parent object/array, insert the new value.

This is the general-purpose function when business logic permits both insert and replace.

### 3.1. Replacing an Existing Value

Initial document:

    {
      "name": "An",
      "preferences": {
        "language": "en",
        "theme": "light"
      }
    }

Replace `language`:

    SELECT JSON_SET(
        '{
          "name": "An",
          "preferences": {
            "language": "en",
            "theme": "light"
          }
        }',
        '$.preferences.language',
        'vi'
    );

Result:

    {
      "name": "An",
      "preferences": {
        "language": "vi",
        "theme": "light"
      }
    }

Other keys remain unchanged.

### 3.2. Adding a New Member to an Existing Parent Object

    SELECT JSON_SET(
        '{"name":"An","preferences":{"language":"en"}}',
        '$.preferences.timezone',
        'Asia/Ho_Chi_Minh'
    );

The result adds `timezone` inside `preferences`:

    {
      "name": "An",
      "preferences": {
        "language": "en",
        "timezone": "Asia/Ho_Chi_Minh"
      }
    }

The `preferences` object already exists, so MySQL can add the `timezone` member.

### 3.3. Updating a JSON Column in a Table

    UPDATE customer_profile
    SET profile = JSON_SET(
        profile,
        '$.preferences.language',
        'vi'
    )
    WHERE customer_id = 1;

The function produces the new JSON value for the SET expression; the UPDATE statement writes the result back to the column. Calling JSON_SET in a SELECT only returns the computed value without persisting changes to the table.

### 3.4. Modifying Multiple Paths in One Call

    UPDATE customer_profile
    SET profile = JSON_SET(
        profile,
        '$.preferences.language', 'vi',
        '$.preferences.theme', 'dark',
        '$.last_updated_by', 'settings-page'
    )
    WHERE customer_id = 1;

Each path-value forms a pair. The function can modify multiple positions within a single SQL expression, avoiding multiple separate UPDATEs.

### 3.5. Behavior with Arrays

Array indices start at 0. When the path points to an existing element, JSON_SET replaces that element:

    SELECT JSON_SET(
        '["mysql","sql","redis"]',
        '$[1]',
        'postgresql'
    );

Result:

    ["mysql", "postgresql", "redis"]

If you want to append an element at the end of an array, use an index equal to the current array length. For general append operations, JSON_ARRAY_APPEND usually expresses intent more clearly than JSON_SET.

## 4. JSON_INSERT: Insert Only When the Path Does Not Exist

JSON_INSERT(document, path, value[, path, value] ...) inserts a value at a position that does not exist yet. If the path already identifies a value, that pair is skipped; the existing value is not overwritten.

### 4.1. Adding a New Member

    SELECT JSON_INSERT(
        '{"name":"An","email":"an@example.test"}',
        '$.status',
        'active'
    );

Result:

    {
      "name": "An",
      "email": "an@example.test",
      "status": "active"
    }

### 4.2. Keeping Existing Paths Unchanged

    SELECT JSON_INSERT(
        '{"name":"An","status":"pending"}',
        '$.status',
        'active'
    );

The result remains:

    {"name":"An","status":"pending"}

JSON_INSERT fits default data or metadata that is initialized only once. It is not suitable if the goal is always syncing values from new requests.

### 4.3. Adding Multiple Members While Skipping Existing Ones

    SELECT JSON_INSERT(
        '{"name":"An","status":"pending"}',
        '$.status', 'active',
        '$.created_by', 'registration',
        '$.source', 'web'
    );

`status` remains `pending`; `created_by` and `source` are added because they do not exist yet.

### 4.4. Appending an Element at the End of an Array

For a three-element array, the next index is 3:

    SELECT JSON_INSERT(
        '["mysql","sql","redis"]',
        '$[3]',
        'mongodb'
    );

Result:

    ["mysql", "sql", "redis", "mongodb"]

If the path points to an existing array index, JSON_INSERT neither replaces the element nor shifts existing elements to the right. To insert in the middle and shift elements, look at JSON_ARRAY_INSERT; that is a different function.

### 4.5. Conditional Initialization

For example, the application wants to add a `beta` flag if the document has not declared it yet:

    UPDATE customer_profile
    SET profile = JSON_INSERT(
        profile,
        '$.flags.beta',
        TRUE
    )
    WHERE customer_id = 1;

This example assumes the `flags` object already exists. If `flags` does not exist yet, the intermediate path is not created automatically. Initialize the parent object first or use a nested expression with type checking.

## 5. JSON_REPLACE: Replace Only Existing Paths

JSON_REPLACE(document, path, value[, path, value] ...) only replaces values at existing paths. If a path does not exist, the function skips that pair; no new member is added.

### 5.1. Replacing an Existing Value

    SELECT JSON_REPLACE(
        '{"name":"An","status":"pending"}',
        '$.status',
        'active'
    );

Result:

    {"name":"An","status":"active"}

### 5.2. Not Adding When Path Does Not Exist

    SELECT JSON_REPLACE(
        '{"name":"An"}',
        '$.status',
        'active'
    );

The result remains:

    {"name":"An"}

JSON_REPLACE is useful when business logic only allows updating already-initialized fields. It prevents accidentally extending the document schema due to typos in path names.

### 5.3. Replacing Multiple Existing Values

    UPDATE customer_profile
    SET profile = JSON_REPLACE(
        profile,
        '$.preferences.language', 'vi',
        '$.preferences.theme', 'dark'
    )
    WHERE customer_id = 1;

If `language` exists but `theme` does not, `language` is still replaced while `theme` is skipped. No error occurs merely because one path does not match.

### 5.4. When Missing Paths Need to Be Detected

JSON_REPLACE does not raise a business error when a path does not exist. If the application needs to distinguish "updated" from "field not found", check beforehand:

    SELECT
        customer_id,
        JSON_CONTAINS_PATH(
            profile,
            'one',
            '$.preferences.theme'
        ) AS has_theme
    FROM customer_profile
    WHERE customer_id = 1;

Or filter in UPDATE:

    UPDATE customer_profile
    SET profile = JSON_REPLACE(
        profile,
        '$.preferences.theme',
        'dark'
    )
    WHERE customer_id = 1
      AND JSON_CONTAINS_PATH(
          profile,
          'one',
          '$.preferences.theme'
      );

This condition ensures the UPDATE selects only documents that have the path to replace.

## 6. JSON_REMOVE: Removing Members or Elements

JSON_REMOVE(document, path[, path] ...) returns a document with values at the specified paths removed.

### 6.1. Removing an Object Member

    SELECT JSON_REMOVE(
        '{"name":"An","temporary_token":"tmp-123"}',
        '$.temporary_token'
    );

Result:

    {"name":"An"}

### 6.2. Removing a Nested Member

    SELECT JSON_REMOVE(
        '{
          "name":"An",
          "preferences":{
            "language":"vi",
            "debug_mode":true
          }
        }',
        '$.preferences.debug_mode'
    );

Result:

    {
      "name": "An",
      "preferences": {
        "language": "vi"
      }
    }

The parent `preferences` object remains; only the `debug_mode` member is removed.

### 6.3. Removing an Array Element

    SELECT JSON_REMOVE(
        '["mysql","sql","redis","mongodb"]',
        '$[1]'
    );

Result:

    ["mysql", "redis", "mongodb"]

When an array element is removed, subsequent elements shift left and their indices change. No "hole" is left at the removed position.

### 6.4. Removing Multiple Paths

    UPDATE customer_profile
    SET profile = JSON_REMOVE(
        profile,
        '$.temporary_token',
        '$.debug'
    )
    WHERE customer_id = 1;

Non-existent paths are ignored. Multiple paths can be passed in a single call.

### 6.5. Removing Multiple Array Indices: Order Matters

JSON_REMOVE evaluates paths left to right on the document resulting from the previous step. When removing array elements, subsequent indices shift.

Suppose:

    ["a","b","c","d"]

Remove index 3 first, then index 1:

    SELECT JSON_REMOVE(
        '["a","b","c","d"]',
        '$[3]',
        '$[1]'
    );

Result:

    ["a","c"]

If index 1 is removed first, the array becomes `["a","c","d"]`. The subsequent path `$[3]` no longer has an element to delete, leaving `["a","c","d"]`.

Rule of practice: when removing multiple original indices from the same array, process indices in descending order. This avoids shifting the indices of remaining elements before the next path is applied.

### 6.6. Cannot Remove the Root Document

Path `$` represents the entire document. JSON_REMOVE does not allow removing the root document via this path. If business logic wants to clear the entire JSON value, use an intentional UPDATE to assign another JSON document, or SQL NULL if the schema allows it and that is genuinely the intended meaning.

## 7. Comparison Table of the Four Functions

| Scenario | JSON_SET | JSON_INSERT | JSON_REPLACE | JSON_REMOVE |
|---|---|---|---|---|
| Path already exists | Replace | Skip | Replace | Remove |
| Path does not exist, valid parent | Insert | Insert | Skip | Skip |
| Uses path-value pairs | Yes | Yes | Yes | No |
| Multiple paths in one call | Yes | Yes | Yes | Yes |
| Removes object member | No | No | No | Yes |
| Removes array element | No | No | No | Yes |
| Auto-creates missing parent objects | No | No | No | Not applicable |

Quick selection:

- Want to "set value to X whether it exists or not" -> JSON_SET.
- Want to "initialize only if missing" -> JSON_INSERT.
- Want to "modify only already-created fields" -> JSON_REPLACE.
- Want to "remove a field or element" -> JSON_REMOVE.

## 8. Evaluation Order of Multiple Path-Value Pairs

JSON_SET, JSON_INSERT, and JSON_REPLACE evaluate path-value pairs from left to right. The document produced after each pair becomes the input to the next pair.

Example:

    SELECT JSON_SET(
        '{"profile":{}}',
        '$.profile.preferences',
        JSON_OBJECT('theme', 'dark'),
        '$.profile.preferences.language',
        'vi'
    );

First, `preferences` is created. Then the `language` path has a valid parent and is inserted.

If the order is reversed:

    SELECT JSON_SET(
        '{"profile":{}}',
        '$.profile.preferences.language',
        'vi',
        '$.profile.preferences',
        JSON_OBJECT('theme', 'dark')
    );

The first pair cannot traverse the non-existent parent `preferences`, so `language` is not created. Only the second pair creates `preferences`. The result lacks `language`.

For JSON_REMOVE, paths are also applied sequentially to the result of the prior removal. This is why the order of array-index removal paths must be carefully considered.

If two paths overlap—such as one path replacing an entire parent object and the next replacing a child member—the outcome depends on order. Write the order explicitly and test on representative documents.

## 9. Value Data Types: Strings Do Not Automatically Become JSON Objects

Values passed to JSON modification functions are converted to JSON values based on their SQL type. A string containing JSON-like characters remains a JSON string unless parsed/cast.

### 9.1. Common Mistake: Saving an Object as a String

    SELECT JSON_SET(
        '{"profile":{}}',
        '$.profile',
        '{"language":"vi"}'
    );

The value at path `profile` is a JSON string containing `{"language":"vi"}`, not an object with a `language` member.

### 9.2. Using CAST to Turn JSON Text into a JSON Value

    SELECT JSON_SET(
        '{"profile":{}}',
        '$.profile',
        CAST('{"language":"vi"}' AS JSON)
    );

Result:

    {"profile":{"language":"vi"}}

### 9.3. Using JSON_OBJECT and JSON_ARRAY

It is usually better to build the structure directly:

    SELECT JSON_SET(
        '{"profile":{}}',
        '$.profile',
        JSON_OBJECT(
            'language', 'vi',
            'enabled', TRUE,
            'roles', JSON_ARRAY('reader', 'editor')
        )
    );

The result contains properly typed objects, booleans, and arrays.

### 9.4. Distinguishing JSON null and SQL NULL

JSON null is a value inside a document; SQL NULL is the absence of a value for an expression/column. These two concepts are not the same.

To set JSON null explicitly:

    SELECT JSON_SET(
        '{"nickname":"An"}',
        '$.nickname',
        CAST('null' AS JSON)
    );

Result:

    {"nickname": null}

Do not use SQL NULL in place of JSON null if the goal is keeping a member with a null value. JSON modification functions return SQL NULL when the input document or path is SQL NULL; check nullable parameters and use CAST('null' AS JSON) when an explicit JSON null value is needed.

Check the difference:

    SELECT
        JSON_TYPE(
            JSON_EXTRACT(
                '{"nickname":null}',
                '$.nickname'
            )
        ) AS json_value_type,
        JSON_EXTRACT(
            '{"nickname":null}',
            '$.missing'
        ) IS NULL AS missing_path_is_sql_null;

JSON_TYPE on the `nickname` member indicates `NULL` as the JSON type; the `missing` path returns SQL NULL.

## 10. Creating Nested Objects When the Parent Does Not Exist

This is a frequent scenario in configuration data. For example, the document only has:

    {"name":"An"}

The application wants to set:

    $.preferences.notifications.email = true

You cannot simply call JSON_SET with the deep path because `preferences` and `notifications` do not exist yet.

### 10.1. Initializing Parent Objects Step by Step

First, create `preferences` if missing or if the current value is not an object:

    UPDATE customer_profile
    SET profile = JSON_SET(
        profile,
        '$.preferences',
        CASE
            WHEN JSON_TYPE(
                JSON_EXTRACT(profile, '$.preferences')
            ) = 'OBJECT'
            THEN JSON_EXTRACT(profile, '$.preferences')
            ELSE JSON_OBJECT()
        END
    )
    WHERE customer_id = 1;

This expression preserves `preferences` if it is already an object; if missing or another type, it replaces it with an empty object. This is a business decision that could discard a mistyped `preferences` value, so use it only when the application intentionally accepts that normalization policy.

Next, create the `notifications` object and set `email`:

    UPDATE customer_profile
    SET profile = JSON_SET(
        profile,
        '$.preferences.notifications',
        CASE
            WHEN JSON_TYPE(
                JSON_EXTRACT(
                    profile,
                    '$.preferences.notifications'
                )
            ) = 'OBJECT'
            THEN JSON_EXTRACT(
                profile,
                '$.preferences.notifications'
            )
            ELSE JSON_OBJECT()
        END,
        '$.preferences.notifications.email',
        TRUE
    )
    WHERE customer_id = 1;

The two pairs are evaluated left to right. The first pair ensures `notifications` is an object; the second adds `email`.

### 10.2. Avoiding Unintended Overwrites of Parent Objects

Do not use:

    JSON_SET(
        profile,
        '$.preferences',
        JSON_OBJECT('notifications', JSON_OBJECT('email', TRUE))
    )

if you need to preserve `preferences.language`, `preferences.theme`, or other members. The expression above replaces the entire `preferences` object with a new object and loses any unpassed members.

Retrieve the current object, check its type, and modify the child member; or use multi-path operations in the appropriate order.

## 11. Safe Array Manipulation

Arrays are ordered, with 0-based indices. When adding, replacing, or removing elements, distinguish positional updates from insertions that shift elements.

### 11.1. Replacing an Existing Element

    SELECT JSON_SET(
        '{"tags":["mysql","sql","redis"]}',
        '$.tags[1]',
        'database'
    );

Result:

    {"tags":["mysql","database","redis"]}

### 11.2. Inserting Only If the Index Does Not Exist

    SELECT JSON_INSERT(
        '{"tags":["mysql","sql"]}',
        '$.tags[2]',
        'redis'
    );

Result:

    {"tags":["mysql","sql","redis"]}

If the path points to an existing index, JSON_INSERT skips it; it does not push existing elements to the right. To insert in the middle of an array, use JSON_ARRAY_INSERT.

### 11.3. Removing an Element and Shifting Indices

    SELECT JSON_REMOVE(
        '{"tags":["mysql","sql","redis"]}',
        '$.tags[0]'
    );

Result:

    {"tags":["sql","redis"]}

The `sql` element moves from index 1 to index 0.

### 11.4. Do Not Assume Arrays Always Exist

Before modifying a path like `$.tags[0]`, check:

    SELECT
        JSON_TYPE(JSON_EXTRACT(profile, '$.tags')) AS tags_type,
        JSON_LENGTH(profile, '$.tags') AS tags_length
    FROM customer_profile
    WHERE customer_id = 1;

If `tags` is missing, JSON null, or scalar, array modification statements may fail to achieve the intended result. Define a clear policy: initialize the array, skip, or reject schema-invalid data.

## 12. Combining Modification Functions with JSON Inspection Functions

You should not always call a modification function immediately. Before updating, read/inspection functions help verify paths, types, and business conditions.

### 12.1. JSON_CONTAINS_PATH

Check whether one or more paths exist:

    SELECT JSON_CONTAINS_PATH(
        profile,
        'one',
        '$.preferences.theme'
    )
    FROM customer_profile
    WHERE customer_id = 1;

`one` means at least one path exists; `all` requires all paths to exist.

### 12.2. JSON_TYPE

Check the JSON type:

    SELECT
        JSON_TYPE(
            JSON_EXTRACT(profile, '$.preferences')
        ) AS preferences_type
    FROM customer_profile
    WHERE customer_id = 1;

Results can be OBJECT, ARRAY, STRING, INTEGER, DOUBLE, BOOLEAN, or NULL depending on the value.

### 12.3. JSON_EXTRACT and Shorthand Operators

    SELECT
        JSON_EXTRACT(profile, '$.preferences.language'),
        profile->'$.preferences.language',
        profile->>'$.preferences.language'
    FROM customer_profile
    WHERE customer_id = 1;

`->` is equivalent to JSON_EXTRACT when accessing a JSON column. `->>` returns the value with JSON quoting stripped for scalar results. When passing extracted values into JSON modification functions, preserve the JSON type if an object/array is needed; when comparing text, use the appropriate unquoted form.

### 12.4. JSON_LENGTH

Count members or elements:

    SELECT
        JSON_LENGTH(profile, '$.tags')
    FROM customer_profile
    WHERE customer_id = 1;

The result is useful for checking how many elements an array currently holds or validating structure before inserting.

## 13. Practical UPDATE Patterns

JSON functions are typically invoked inside UPDATE. Identify rows by relational keys, use conditions to restrict scope, and modify only the required paths.

### 13.1. Updating User Settings

    UPDATE customer_profile
    SET profile = JSON_SET(
        profile,
        '$.preferences.theme',
        'dark'
    )
    WHERE customer_id = 1;

### 13.2. Initializing Metadata If Absent

    UPDATE customer_profile
    SET profile = JSON_INSERT(
        profile,
        '$.metadata.created_by',
        'registration-service'
    )
    WHERE customer_id = 1;

This command assumes `metadata` already exists. If the parent `metadata` does not exist yet, create the parent first; JSON_INSERT does not auto-create all intermediate objects.

### 13.3. Modifying Only Existing Fields

    UPDATE customer_profile
    SET profile = JSON_REPLACE(
        profile,
        '$.preferences.language',
        'vi'
    )
    WHERE customer_id = 1
      AND JSON_CONTAINS_PATH(
          profile,
          'all',
          '$.preferences',
          '$.preferences.language'
      );

The condition guarantees the target path already exists. If the path is absent, no row is selected for update.

### 13.4. Removing a Temporary Token

    UPDATE customer_profile
    SET profile = JSON_REMOVE(
        profile,
        '$.temporary_token'
    )
    WHERE customer_id = 1;

If the token already does not exist, JSON_REMOVE leaves the document unchanged.

### 13.5. Replacing a Child Object While Preserving the Rest

If you only want to change `preferences.theme`, update that exact child path. Do not replace the entire `profile` with a stale JSON payload sent by the application, because the stale payload may lack recent changes to other members.

## 14. Transactions and Consistency

JSON functions do not create separate transactions. When called inside an UPDATE on InnoDB, JSON modifications obey statement-level and current transaction boundaries.

Example:

    START TRANSACTION;

    UPDATE customer_profile
    SET profile = JSON_SET(
        profile,
        '$.preferences.language',
        'vi'
    )
    WHERE customer_id = 1;

    UPDATE customer_profile
    SET profile = JSON_REMOVE(
        profile,
        '$.temporary_token'
    )
    WHERE customer_id = 1;

    COMMIT;

If one step fails and the application decides to abort the entire operation:

    ROLLBACK;

There is no need to read JSON into the application and overwrite the entire document just to change one member. Let MySQL apply the path modification on the current column value inside UPDATE.

### 14.1. Avoiding Lost Updates from Stale Payloads

Suppose two requests both read version 5 of a JSON document. Request A changes `theme`; request B changes `language`. If both modify the JSON copy in application memory and overwrite the entire column, the later write can erase the earlier request's change.

Instead, send path-targeted updates:

    UPDATE customer_profile
    SET profile = JSON_SET(
        profile,
        '$.preferences.theme',
        'dark'
    )
    WHERE customer_id = 1;

    UPDATE customer_profile
    SET profile = JSON_SET(
        profile,
        '$.preferences.language',
        'vi'
    )
    WHERE customer_id = 1;

The two UPDATEs are serialized by InnoDB row locks. Because each expression modifies the current column value, changes to different paths can both be preserved. However, if two requests modify the same path, business rules are still needed to determine which request wins.

### 14.2. Optimistic Locking with Version

When you need to detect whether data changed since the client read it:

    UPDATE customer_profile
    SET profile = JSON_SET(
            profile,
            '$.preferences.theme',
            'dark'
        ),
        version_no = version_no + 1
    WHERE customer_id = 1
      AND version_no = 7;

The application checks the affected row count:

- 1 row: version matched, update succeeded.
- 0 rows: record does not exist or version changed; re-read and resolve the conflict.

This prevents silent overwrites when APIs use optimistic concurrency.

## 15. Partial Updates and JSON Storage Cost

JSON_SET, JSON_REPLACE, and JSON_REMOVE can allow MySQL to optimize in-place partial updates for JSON columns under qualifying conditions. This does not mean every expression always writes only a subset of bytes.

Key conditions include:

- The updated column must have type JSON.
- The UPDATE must use one of the supported partial-update functions directly on the target JSON column.
- The input value to the modification must come from the target JSON column itself.
- The change must satisfy space and structural constraints so the storage engine can apply an in-place optimization.

Example eligible for partial update:

    UPDATE customer_profile
    SET profile = JSON_SET(
        profile,
        '$.preferences.theme',
        'dark'
    )
    WHERE customer_id = 1;

Example replacing the entire document from a payload:

    UPDATE customer_profile
    SET profile = CAST(
        '{"name":"An","preferences":{"theme":"dark"}}'
        AS JSON
    )
    WHERE customer_id = 1;

The second example replaces the whole document; do not expect similar partial-update optimization.

MySQL provides functions to observe storage usage:

    SELECT
        JSON_STORAGE_SIZE(profile) AS storage_bytes,
        JSON_STORAGE_FREE(profile) AS reusable_bytes
    FROM customer_profile
    WHERE customer_id = 1;

JSON_STORAGE_SIZE reports the storage footprint of the JSON document; JSON_STORAGE_FREE reports free space remaining after eligible partial updates. These are diagnostic metrics, not a guarantee that every edit happens in place.

In row-based binary logging, the `PARTIAL_JSON` setting can affect how JSON changes are written to the binary log. Check replication configuration and documentation for your running version before changing `binlog_row_value_options`.

Do not micro-optimize based solely on function names. Measure document sizes, update frequency, secondary index count, and replication cost on realistic workloads.

## 16. Indexes for Frequently Queried JSON Data

A JSON column does not automatically index every key inside the document. If the application frequently filters by a JSON property, consider a generated column or functional index.

Example frequently querying by `plan`:

    ALTER TABLE customer_profile
    ADD COLUMN plan_code VARCHAR(30)
        GENERATED ALWAYS AS (
            profile->>'$.plan.code'
        ) STORED,
    ADD INDEX idx_customer_plan (plan_code);

Then query:

    SELECT customer_id, profile
    FROM customer_profile
    WHERE plan_code = 'PRO';

A generated column materializes a JSON property as a typed, clearly indexed column. Choose length, collation, and data type appropriate for actual values.

If you only update JSON with JSON_SET without an index on the filtered path, SELECTs using JSON_EXTRACT may scan many rows. Do not put critical business attributes into JSON if they need joins, unique constraints, foreign keys, or high-selectivity queries.

## 17. NULL, Invalid Paths, and Malformed Data

JSON modification functions do not replace input validation. Common errors include:

- Document is not valid JSON.
- JSON path has invalid syntax.
- Using wildcards in a modification function path.
- Passing an invalid number of path-value arguments.
- Parent path does not exist.
- Value at path has a type different from application assumptions.
- An SQL NULL argument causes the function to return SQL NULL.

Example invalid path:

    SELECT JSON_SET(
        '{"name":"An"}',
        '$.preferences[',
        'vi'
    );

A syntactically invalid path raises an error rather than being silently corrected.

### 17.1. Validating Input Documents

If data arrives as text before writing to a JSON column:

    SELECT JSON_VALID(
        '{"name":"An","active":true}'
    );

JSON_VALID returns 1 if the text is valid JSON and 0 if invalid. JSON columns self-validate on write; this check is more useful at boundaries ingesting text data.

### 17.2. Checking Types Before Modifying

Do not assume `preferences` is always an object:

    SELECT
        JSON_TYPE(
            JSON_EXTRACT(profile, '$.preferences')
        )
    FROM customer_profile
    WHERE customer_id = 1;

If `preferences` is a string or array, a child path like `preferences.theme` does not mean the same thing as when the parent is an object. Reject schema-invalid data or normalize it under explicitly defined rules.

## 18. Safety When Paths Come from the Application

Never concatenate paths from untrusted input into SQL strings. Instead:

- Use prepared statements for document values and paths.
- Allowlist paths the application is permitted to edit, e.g., only `preferences.theme` and `preferences.language`.
- Do not let clients pick arbitrary paths if doing so could alter roles, permissions, billing, or security state.
- Validate types and allowed values before writing.
- Limit JSON payload size.
- Log business-level audits for sensitive changes.

Prepared statements prevent SQL injection, but they do not by themselves prevent a client from modifying an unauthorized business path. Authorization must check both the record and the editable fields.

## 19. Business-Case Function Selection Matrix

| Business Need | Function | Reason |
|---|---|---|
| Always set language to a new value | JSON_SET | Can insert or replace |
| Create beta flag only if absent | JSON_INSERT | Does not overwrite existing values |
| Change theme only if field already exists | JSON_REPLACE | Prevents creating new paths due to typos |
| Delete temporary token after use | JSON_REMOVE | Removes member |
| Edit multiple settings at once | JSON_SET | Multiple path-value pairs in one call |
| Add metadata members while keeping old ones | JSON_INSERT | Only inserts missing members |
| Delete multiple known members | JSON_REMOVE | Multiple paths in one call |
| Insert array element in the middle and shift elements | JSON_ARRAY_INSERT | Specialized for array insertion |
| General array append | JSON_ARRAY_APPEND | Specialized for array appending |

No single function completely replaces the others. Choose based on existence conditions and desired effect.

## 20. Practice Lab: Managing Customer Profiles

This lab uses the `customer_profile` table created at the start of the lesson. Run it in a test schema.

### Step 1: Inspect the Current Document

    SELECT
        customer_id,
        JSON_PRETTY(profile)
    FROM customer_profile
    WHERE customer_id = 1;

### Step 2: Change Language with JSON_SET

    UPDATE customer_profile
    SET profile = JSON_SET(
        profile,
        '$.preferences.language',
        'vi'
    )
    WHERE customer_id = 1;

Verify `language` changed to `vi` and `theme` remains intact.

### Step 3: Add a Member Only When Missing

    UPDATE customer_profile
    SET profile = JSON_INSERT(
        profile,
        '$.metadata.source',
        'web'
    )
    WHERE customer_id = 1;

Run a second time with a different `source` value. The first value is still preserved.

### Step 4: Replace Only Existing Fields

    UPDATE customer_profile
    SET profile = JSON_REPLACE(
        profile,
        '$.preferences.theme',
        'dark',
        '$.preferences.unknown_setting',
        'ignored'
    )
    WHERE customer_id = 1;

`theme` changes to `dark`; `unknown_setting` is not added.

### Step 5: Remove the Token

    UPDATE customer_profile
    SET profile = JSON_REMOVE(
        profile,
        '$.temporary_token'
    )
    WHERE customer_id = 1;

Verify `temporary_token` is no longer in the document.

### Step 6: Replace an Array Element

    UPDATE customer_profile
    SET profile = JSON_SET(
        profile,
        '$.tags[0]',
        'database'
    )
    WHERE customer_id = 1;

Verify the second element is still `sql`.

### Step 7: Remove an Array Element

    UPDATE customer_profile
    SET profile = JSON_REMOVE(
        profile,
        '$.tags[0]'
    )
    WHERE customer_id = 1;

Verify the array now holds only `sql` and its index shifted to 0.

### Step 8: Check Types and Size

    SELECT
        JSON_TYPE(profile) AS root_type,
        JSON_TYPE(
            JSON_EXTRACT(profile, '$.preferences')
        ) AS preferences_type,
        JSON_LENGTH(profile, '$.tags') AS tag_count,
        JSON_STORAGE_SIZE(profile) AS storage_bytes,
        JSON_STORAGE_FREE(profile) AS reusable_bytes
    FROM customer_profile
    WHERE customer_id = 1;

### Step 9: Test Optimistic Locking

    UPDATE customer_profile
    SET profile = JSON_SET(
            profile,
            '$.preferences.theme',
            'light'
        ),
        version_no = version_no + 1
    WHERE customer_id = 1
      AND version_no = 0;

Check the updated row count. If `version_no` is no longer 0, the UPDATE modifies no rows and the application must handle the conflict.

## 21. Common Design Mistakes

- Using JSON_INSERT when you want to always update the value.
- Using JSON_REPLACE and being surprised that a new path is not created.
- Using JSON_SET with a deep path when the parent object does not exist yet.
- Thinking JSON_INSERT inserts into the middle of an array and shifts elements.
- Removing array indices in ascending order and deleting the wrong elements.
- Confusing JSON null with SQL NULL.
- Passing a JSON string into the value argument and accidentally storing it as a JSON string.
- Replacing an entire parent object and losing unpassed members.
- Sending a stale JSON payload from the client and overwriting newer changes.
- Not checking JSON_TYPE before operating on an object or array.
- Using wildcard paths in JSON modification functions.
- Concatenating untrusted paths into SQL.
- Allowing clients to modify sensitive paths without authorization checks.
- Storing attributes needing joins, unique constraints, or foreign keys in JSON just for convenience.
- Assuming every JSON_SET receives partial-update optimization.
- Failing to check index, binary log, and replication costs when updating large documents.

## 22. Pre-Deployment Checklist

- Chosen the right function for insert, replace, replace-only, or remove semantics.
- Verified JSON paths are syntactically valid and contain no wildcards.
- Verified parent objects/arrays exist and have the expected type.
- Verified array indices start at 0.
- Determined the evaluation order of overlapping paths.
- Handled array removals in descending index order when necessary.
- Distinguished SQL NULL from JSON null.
- Used CAST(... AS JSON), JSON_OBJECT, or JSON_ARRAY when structured values are needed.
- Used UPDATE with a WHERE clause targeting the exact rows.
- Used transactions or optimistic versioning when business logic requires it.
- Tested existing paths, missing paths, and mistyped parents.
- Verified post-edit values using JSON_EXTRACT/JSON_TYPE/JSON_PRETTY.
- Evaluated generated columns or functional indexes for frequently queried paths.
- Measured partial updates rather than assuming they always happen.
- Used prepared statements and path allowlists from the application.
- Tested on representative data before release.

## 23. References

- MySQL 8.4 Reference Manual — JSON Modification Functions: https://dev.mysql.com/doc/refman/8.4/en/json-modification-functions.html
- MySQL 8.4 Reference Manual — JSON Path Syntax: https://dev.mysql.com/doc/refman/8.4/en/json.html
- MySQL 8.4 Reference Manual — The JSON Data Type: https://dev.mysql.com/doc/refman/8.4/en/json.html
- MySQL 8.4 Reference Manual — Partial Updates of JSON Values: https://dev.mysql.com/doc/refman/8.4/en/json.html
- MySQL 8.4 Reference Manual — JSON Utility Functions: https://dev.mysql.com/doc/refman/8.4/en/json-utility-functions.html
- MySQL 8.4 Reference Manual — Generated Column Indexes: https://dev.mysql.com/doc/refman/8.4/en/create-table-generated-columns.html

JSON_SET inserts or replaces; JSON_INSERT only inserts; JSON_REPLACE only replaces existing values; JSON_REMOVE removes paths. The four functions evaluate paths from left to right, so parent-child paths and array indices can alter the outcome. JSON paths must be concrete, parents must exist and have the right type, and JSON null must be distinguished from SQL NULL. When used inside UPDATE, modify exact paths on the current column value, restrict rows with WHERE, use transactions/versioning when needed, and verify storage, index, and replication costs. Selecting functions by business intent rather than by name alone prevents data loss and keeps JSON structures consistent.
