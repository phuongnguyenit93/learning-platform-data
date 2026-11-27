# Adding, Modifying, and Deleting JSON Elements and Update Costs in PostgreSQL

Applications often store flexible settings, supplementary metadata, or evolving attributes in a `jsonb` column. For example, a profile might look like:

~~~json
{
  "name": "Lan",
  "settings": {
    "theme": "light",
    "notifications": {
      "email": true,
      "sms": false
    }
  },
  "tags": ["vip", "email"],
  "addresses": [
    {"label": "home", "city": "Ha Noi"},
    {"label": "office", "city": "Da Nang"}
  ],
  "metrics": {"visits": 4},
  "nickname": null
}
~~~

When a user switches their theme from `light` to `dark`, the application only wants to **modify one nested value**, without overwriting the entire document in a way that loses unrelated attributes. When adding an address or removing a tag, the application must also understand how operations on a **JSON object** differ from operations on a **JSON array**.

PostgreSQL provides tools such as `jsonb_set`, `jsonb_insert`, and the `||`, `-`, and `#-` operators to perform these edits directly in SQL. However, **a logical partial update does not mean an in-place physical edit of a few bytes on disk**. PostgreSQL uses MVCC; an `UPDATE` creates a new row version and can trigger work on JSONB, TOAST, indexes, WAL, and VACUUM.

This lesson belongs to the **JSON and Arrays** chapter of the **Database Engine Relational PostgreSQL** module. You will learn how to:

- Distinguish `json` and `jsonb`, especially when modifying data.
- Add, update, and remove keys at the top level and in nested branches.
- Append, insert by position, replace, and delete JSON array elements.
- Handle missing paths, JSON `null`, SQL `NULL`, and mistyped data.
- Prevent overwriting concurrent transactions when updating the same document.
- Understand JSONB write costs with MVCC, TOAST, HOT updates, B-tree/GIN indexes, and WAL.
- Measure costs rather than assuming any JSONB function is inherently fast.
- Know when to keep data in JSONB and when to extract it into relational tables or columns.

## 1. Three Layers of a JSON Modification Operation

A request to "change theme to dark" has three distinct layers:

1. **Business semantics:** replace only `settings.theme`, preserving `tags`, `addresses`, and all other fields.
2. **SQL syntax:** use JSONB functions and operators to produce the new document value.
3. **Storage and concurrency:** PostgreSQL updates the tuple under MVCC, maintains affected indexes, and coordinates with concurrent transactions.

~~~mermaid
flowchart TD
    A["Request: change settings.theme"] --> B["jsonb_set: build result JSONB"]
    B --> C["UPDATE: new tuple version under MVCC"]
    C --> D["Heap and possibly TOAST"]
    C --> E["Index maintenance if affected"]
    C --> F["WAL and subsequent cleanup"]
    D --> G["COMMIT or ROLLBACK"]
    E --> G
    F --> G
~~~

Never conclude "only 5 characters changed, so PostgreSQL only writes 5 bytes." SQL performs a **logical partial modification**, while physical storage cost depends on row, JSONB, and index layout.

## 2. Choosing json or jsonb?

PostgreSQL has two main JSON types:

| Criterion | `json` | `jsonb` |
| --- | --- | --- |
| Storage format | Stores the raw JSON input text | Parsed binary representation |
| Input whitespace/key order | Preserved per original text | Key order and formatting are not guaranteed |
| Duplicate object keys | Can remain in stored text | Normalized to one value per key; last value wins |
| Querying/operators | Has extraction functions, fewer than JSONB | Rich set of operators and manipulation/comparison functions |
| GIN indexing | Not directly like JSONB | Dedicated operator classes for JSONB queries |
| Editing a branch with `jsonb_set` | Requires casting to JSONB first | Directly supported |
| When to choose | Must preserve verbatim input text for specific reasons | Most common for application documents queried and updated |

Example:

~~~sql
SELECT
    '{"a":1,"a":2}'::json AS original_json,
    '{"a":1,"a":2}'::jsonb AS normalized_jsonb;
~~~

With `jsonb`, the object does not keep both duplicate `a` entries as in the original text. Do not use JSONB if business logic genuinely depends on original text formatting or key order.

### Why Does This Lesson Use jsonb?

Functions like `jsonb_set` and `jsonb_insert`, deletion operators `-` and `#-`, and concatenation `||` in these examples operate on `jsonb`. If a column is typed as `json`, casting `::jsonb` during edits alters text formatting, and casting back adds overhead without preserving the original input layout.

**For data requiring frequent updates and attribute searches, `jsonb` is usually the practical choice.** Still, weigh update costs and schema design rather than choosing it merely because "binary" sounds faster.

## 3. JSON Objects, JSON Arrays, and Scalars Differ

All of these are valid JSON:

~~~json
{"key": "value"}
~~~

~~~json
["a", "b", 12, null]
~~~

~~~json
"hello"
~~~

~~~json
42
~~~

~~~json
true
~~~

~~~json
null
~~~

The `jsonb_typeof` function identifies the JSON type of a target value:

~~~sql
SELECT
    jsonb_typeof('{"a":1}'::jsonb) AS object_type,
    jsonb_typeof('["a","b"]'::jsonb) AS array_type,
    jsonb_typeof('"abc"'::jsonb) AS string_type,
    jsonb_typeof('null'::jsonb) AS null_type;
~~~

The results are `object`, `array`, `string`, and `null` respectively.

A **JSON array** is not a **PostgreSQL SQL array**:

~~~sql
SELECT
    '["vip","new"]'::jsonb AS json_array,
    ARRAY['vip','new']::text[] AS sql_array;
~~~

Both look like lists, yet they differ in functions, operators, element typing, and indexing. You cannot call SQL's `array_append` and expect it to edit a `jsonb` value directly.

## 4. Preparing the Practice Schema

The examples use schema `json_edit_lab`. The script starts with `DROP SCHEMA ... CASCADE` for easy repeatable resets.

**Warning:** this drops all objects inside `json_edit_lab` if present. Run it only in a **dedicated practice database**, never in production or a schema containing valuable data.

### 4.1. Creating the Profiles Table

~~~sql
-- RUN ONLY IN LAB DATABASE.
DROP SCHEMA IF EXISTS json_edit_lab CASCADE;
CREATE SCHEMA json_edit_lab;

CREATE TABLE json_edit_lab.customer_profiles (
    profile_id bigint PRIMARY KEY,
    email text NOT NULL UNIQUE,
    doc jsonb NOT NULL
        CHECK (jsonb_typeof(doc) = 'object'),
    version bigint NOT NULL DEFAULT 0
        CHECK (version >= 0),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
~~~

Intentional design choices:

- `profile_id` is a stable relational identifier, **independent of JSON paths**.
- `email` has a `UNIQUE` constraint for identity and deduplication.
- `doc` is a JSONB object, preventing top-level arrays or scalars.
- `version` demonstrates optimistic concurrency control.
- `updated_at` records modification time, not uniqueness.

Note that `CHECK (jsonb_typeof(doc) = 'object')` **only validates the top-level value is an object**. It does not guarantee `settings` is an object or `tags` is an array. When nested structure matters, enforce it via additional constraints, application checks, or schema validation.

### 4.2. Loading Three Profiles

~~~sql
INSERT INTO json_edit_lab.customer_profiles
    (profile_id, email, doc)
VALUES
(
    101,
    'lan@example.test',
    $json$
    {
      "name": "Lan",
      "settings": {
        "theme": "light",
        "notifications": {"email": true, "sms": false}
      },
      "tags": ["vip", "email"],
      "addresses": [
        {"label": "home", "city": "Ha Noi"},
        {"label": "office", "city": "Da Nang"}
      ],
      "metrics": {"visits": 4},
      "nickname": null
    }
    $json$::jsonb
),
(
    102,
    'minh@example.test',
    $json$
    {
      "name": "Minh",
      "settings": {
        "theme": "dark",
        "notifications": {"email": false}
      },
      "tags": [],
      "addresses": [],
      "metrics": {"visits": 0}
    }
    $json$::jsonb
),
(
    103,
    'hoa@example.test',
    $json$
    {
      "name": "Hoa",
      "tags": ["new"],
      "addresses": [
        {"label": "home", "city": "Hue"}
      ]
    }
    $json$::jsonb
);
~~~

Two intentional details:

- Profile **101** has full nested objects, multiple tags, multiple addresses, and `nickname: null`.
- Profile **103** **lacks** `settings` and `metrics`. It is used to demonstrate missing intermediate paths.

### 4.3. Inspecting the Data

~~~sql
SELECT
    profile_id,
    email,
    jsonb_typeof(doc) AS root_type,
    jsonb_pretty(doc) AS pretty_doc
FROM json_edit_lab.customer_profiles
ORDER BY profile_id;
~~~

`jsonb_pretty` is helpful for human-readable inspection; never rely on key order in its output to represent business ordering.

## 5. Reading Data Before Modifying

Key operators:

| Syntax | Meaning | Return Type |
| --- | --- | --- |
| `doc -> 'settings'` | Get JSON value at top-level key | `jsonb` |
| `doc ->> 'name'` | Get key value as text | `text` |
| `doc #> '{settings,theme}'` | Get JSONB value along multi-level path | `jsonb` |
| `doc #>> '{settings,theme}'` | Get value along path as text | `text` |
| `doc ? 'nickname'` | Does top-level key `nickname` exist? | `boolean` |
| `jsonb_typeof(doc->'tags')` | Inspect JSON type at branch | `text` |

Example:

~~~sql
SELECT
    profile_id,
    doc ->> 'name' AS full_name,
    doc #>> '{settings,theme}' AS theme_text,
    doc #> '{settings,notifications,email}' AS email_json,
    doc -> 'tags' AS tags_json,
    doc ? 'nickname' AS has_nickname
FROM json_edit_lab.customer_profiles
ORDER BY profile_id;
~~~

Expected result:

| profile_id | name | theme_text | email_json | tags_json | has_nickname |
| ---: | --- | --- | --- | --- | --- |
| 101 | Lan | light | true | ["vip","email"] | true |
| 102 | Minh | dark | false | [] | false |
| 103 | Hoa | SQL NULL | SQL NULL | ["new"] | false |

There is a crucial distinction between "key does not exist" and "key has value JSON null," explained separately below.

## 6. jsonb_set: The Core Function for Replacing a Value

Common signature:

~~~sql
jsonb_set(
    target jsonb,
    path text[],
    new_value jsonb,
    create_if_missing boolean DEFAULT true
)
~~~

Parameters:

1. `target`: initial JSONB document.
2. `path`: PostgreSQL `text[]` path; key names for objects, numeric positions as text for arrays.
3. `new_value`: **a valid JSONB value**, not arbitrary raw text.
4. `create_if_missing`: allows creating the **final path element** if missing under eligible conditions; defaults to `true`.

Pure function example (no database write):

~~~sql
SELECT jsonb_set(
    '{"name":"Lan","settings":{"theme":"light"}}'::jsonb,
    '{settings,theme}',
    '"dark"'::jsonb,
    false
) AS edited_doc;
~~~

Semantic result:

~~~json
{"name": "Lan", "settings": {"theme": "dark"}}
~~~

Data under key `name` is preserved unchanged.

### Common Pitfall: path Is a SQL Text Array

~~~sql
'{settings,theme}'::text[]
~~~

represents two path steps: `settings`, then `theme`. It is **not a JSON array** and not a JSONPath like `$.settings.theme`.

## 7. Updating a Nested Attribute in a Table

Changing Lan's theme:

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET
    doc = jsonb_set(
        doc,
        '{settings,theme}',
        '"dark"'::jsonb,
        false
    ),
    version = version + 1,
    updated_at = clock_timestamp()
WHERE profile_id = 101
RETURNING
    profile_id,
    doc #>> '{settings,theme}' AS new_theme,
    version;

ROLLBACK;
~~~

Inside the transaction, `new_theme = 'dark'` and `version = 1`. After `ROLLBACK`, the profile reverts to its initial seed state.

### Why Must doc Be Reassigned?

`jsonb_set` **returns a new JSONB value**; calling the function by itself does not mutate the stored column. To persist changes, you must assign it:

~~~sql
UPDATE ...
SET doc = jsonb_set(doc, ...)
~~~

Similarly:

~~~sql
SELECT jsonb_set(doc, ...)
FROM ...;
~~~

only returns the computed value without updating the table.

### Why Use RETURNING?

`RETURNING` returns the post-UPDATE values in the same statement without needing a second `SELECT` round-trip just to confirm. On an update request, you can check for `UPDATE 0` or zero returned rows to detect a missing ID or failed optimistic lock condition.

## 8. Passing Text into JSONB Properly

The syntax:

~~~sql
'"dark"'::jsonb
~~~

has **two layers of quotes**:

- Outer single quotes for the SQL string literal.
- Inner double quotes representing a **JSON string**.

If you write:

~~~sql
-- INTENTIONALLY WRONG: dark is not valid JSON text.
SELECT 'dark'::jsonb;
~~~

PostgreSQL raises a JSON parse error because bare token `dark` is not a double-quoted JSON string.

The clean approach for application parameters:

~~~sql
SELECT to_jsonb('dark'::text);
~~~

For objects:

~~~sql
SELECT jsonb_build_object(
    'theme', 'dark',
    'enabled', true,
    'max_items', 10
);
~~~

For arrays:

~~~sql
SELECT jsonb_build_array(
    'vip',
    'email',
    42,
    true
);
~~~

**Never assemble JSON via string concatenation** when values come from user input. Use bind parameters, `to_jsonb`, `jsonb_build_object`, or `jsonb_build_array` to avoid escaping bugs and malformed JSON.

## 9. Adding Top-Level Keys with the || Operator

The `||` operator concatenates two JSONB values. With **object || object**, it merges **top-level** keys; on key collision, the value from the right-hand object replaces the left-hand value.

~~~sql
SELECT
    '{"name":"Lan","tier":"standard"}'::jsonb
    ||
    '{"tier":"gold","active":true}'::jsonb AS result;
~~~

Result:

~~~json
{"name":"Lan","tier":"gold","active":true}
~~~

Adding a `language` key to a profile:

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET
    doc = doc || jsonb_build_object('language', 'vi'),
    version = version + 1,
    updated_at = clock_timestamp()
WHERE profile_id = 101
RETURNING doc ->> 'language' AS language;

ROLLBACK;
~~~

### When to Use ||?

- Adding one or a few top-level keys.
- Explicitly overwriting several top-level attributes.
- Concatenating array with array under JSONB rules (distinct from object merging).

**Warning:** `||` is **not a deep merge**. On nested objects, it replaces the entire value of the matching top-level key rather than merging nested keys recursively.

## 10. Shallow Merge Trap That Loses Nested Data

Document:

~~~json
{
  "settings": {
    "theme": "light",
    "notifications": {
      "email": true,
      "sms": false
    }
  }
}
~~~

If you run:

~~~sql
SELECT
    '{"settings":{"theme":"light","notifications":{"email":true,"sms":false}}}'::jsonb
    ||
    '{"settings":{"theme":"dark"}}'::jsonb
    AS result;
~~~

the logical result is:

~~~json
{"settings":{"theme":"dark"}}
~~~

The entire `notifications` branch was wiped out. This causes serious data loss if an application mistakenly expects `||` to perform a deep merge.

### Correct Way to Edit One Branch

~~~sql
SELECT jsonb_set(
    '{"settings":{"theme":"light","notifications":{"email":true,"sms":false}}}'::jsonb,
    '{settings,theme}',
    '"dark"'::jsonb
);
~~~

The result keeps `notifications`.

**Rule:** use `jsonb_set` when updating a specific deep path; use `||` only for top-level merges when you intend to overwrite every colliding top-level key.

## 11. Adding a Nested Key When Its Parent Exists

Suppose `settings.notifications` already exists in profile 101. Add a `push` flag:

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET doc = jsonb_set(
    doc,
    '{settings,notifications,push}',
    'true'::jsonb,
    true
)
WHERE profile_id = 101
RETURNING
    doc #> '{settings,notifications}' AS notifications;

ROLLBACK;
~~~

Result inside the transaction:

~~~json
{"email":true,"sms":false,"push":true}
~~~

Because `settings` and `notifications` already exist and are objects, `create_if_missing = true` allows adding the **final key `push`**.

### Adding Does Not Automatically Mean "Insert Only If Absent"

If the final key already exists, `jsonb_set` **replaces the old value** with `new_value`. It does not separate "create only" from "replace only."

To avoid overwriting an existing key, guard it in `WHERE`:

~~~sql
UPDATE json_edit_lab.customer_profiles
SET doc = jsonb_set(
    doc,
    '{settings,notifications,push}',
    'true'::jsonb,
    true
)
WHERE profile_id = 101
  AND NOT (
    (doc #> '{settings,notifications}') ? 'push'
  );
~~~

This condition assumes `settings.notifications` is an object; if real data might be missing or mistyped, handle that explicitly rather than applying `?` blindly.

## 12. create_if_missing Does Not Create Missing Ancestors

This is a very common mistake.

Profile 103 has no `settings` key. Try:

~~~sql
SELECT jsonb_set(
    doc,
    '{settings,theme}',
    '"dark"'::jsonb,
    true
) AS candidate
FROM json_edit_lab.customer_profiles
WHERE profile_id = 103;
~~~

Do not expect the output to automatically become:

~~~json
{"name":"Hoa","settings":{"theme":"dark"}, ...}
~~~

With `jsonb_set`, **all intermediate path components must already exist**. `create_if_missing` allows adding the final segment of the path, **not generating missing intermediate parent objects**.

### Building the Parent First

To create a new `settings` branch when absent, update the top-level key:

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET doc = jsonb_set(
    doc,
    '{settings}',
    jsonb_build_object('theme', 'dark'),
    true
)
WHERE profile_id = 103
RETURNING doc -> 'settings' AS settings;

ROLLBACK;
~~~

Now the parent `settings` is created directly without traversing a missing intermediate path.

### When the Parent Might Already Exist

A safer pattern preserves `settings` if it is already an object:

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET doc = jsonb_set(
    doc,
    '{settings}',
    (
        CASE
            WHEN jsonb_typeof(doc -> 'settings') = 'object'
                THEN doc -> 'settings'
            ELSE '{}'::jsonb
        END
        ||
        jsonb_build_object('theme', 'dark')
    ),
    true
)
WHERE profile_id IN (101, 103)
RETURNING profile_id, doc -> 'settings';

ROLLBACK;
~~~

This approach:

- Keeps all other keys of `settings` when the branch is already an object.
- Creates a new object if `settings` is missing or not an object.
- Adds or overwrites `theme`.

**Note:** the `ELSE '{}'` branch intentionally **replaces the value if `settings` is a scalar, array, or null**. In production, you may prefer **raising a validation error** instead of silently replacing the wrong type. Choose behavior per business rules.

## 13. Removing a Top-Level Key with the - Operator

On a JSONB object, `- text` deletes the specified top-level key:

~~~sql
SELECT
    '{"name":"Lan","nickname":null,"active":true}'::jsonb
    - 'nickname'
    AS without_nickname;
~~~

Result:

~~~json
{"name":"Lan","active":true}
~~~

Removing `nickname` in the table:

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET
    doc = doc - 'nickname',
    version = version + 1,
    updated_at = clock_timestamp()
WHERE profile_id = 101
RETURNING
    doc ? 'nickname' AS key_still_exists,
    doc;

ROLLBACK;
~~~

`key_still_exists` is `false` inside the transaction.

### Deleting a Key Differs from Setting JSON null

- `doc - 'nickname'`: **the key no longer exists**.
- `jsonb_set(doc,'{nickname}','null'::jsonb,true)`: **the key still exists**, with value JSON null.

This distinction matters when an API differentiates "no value provided," "explicitly deleted," and "explicitly set to null."

## 14. Removing a Nested Key with #-

The `#- text[]` operator deletes the element at a multi-level path:

~~~sql
SELECT
    '{"settings":{"theme":"light","notifications":{"email":true,"sms":false}}}'::jsonb
    #- '{settings,notifications,sms}'
    AS result;
~~~

Result:

~~~json
{
  "settings": {
    "theme": "light",
    "notifications": {"email": true}
  }
}
~~~

In the table:

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET doc = doc #- '{settings,notifications,sms}'
WHERE profile_id = 101
RETURNING doc #> '{settings,notifications}' AS remaining;

ROLLBACK;
~~~

### What Happens If the Path Does Not Exist?

If there is no element at the path to delete, the operation does not create anything new and returns the document unchanged. However, do not mistake that silent no-op as business confirmation that "an existing attribute was deleted."

If you need to know whether the key existed beforehand, check in a query or add a matching condition in `WHERE` and inspect `RETURNING` or the affected row count.

## 15. JSON Arrays: 0-Based Indexing

In JSONB paths pointing to array elements, indexes start at **0**:

~~~json
["vip", "email", "loyal"]
~~~

| Index | Value |
| ---: | --- |
| 0 | "vip" |
| 1 | "email" |
| 2 | "loyal" |
| -1 | "loyal" (from the end) |
| -2 | "email" |

Example:

~~~sql
SELECT
    '["vip","email","loyal"]'::jsonb -> 0 AS first_tag,
    '["vip","email","loyal"]'::jsonb -> -1 AS last_tag;
~~~

`text[]` paths pass index numbers as text:

~~~sql
'{tags,0}'
'{tags,-1}'
'{addresses,0,city}'
~~~

**Do not confuse** 0-based JSON array indexing with PostgreSQL's 1-based default SQL array indexing.

## 16. Replacing a JSON Array Element with jsonb_set

Profile 101 has `tags = ["vip","email"]`.

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET doc = jsonb_set(
    doc,
    '{tags,1}',
    '"priority"'::jsonb,
    false
)
WHERE profile_id = 101
RETURNING doc -> 'tags' AS tags;

ROLLBACK;
~~~

Inside the transaction:

~~~json
["vip", "priority"]
~~~

With index `1`, the function replaces the second array element.

### Replacing the Last Element

~~~sql
SELECT jsonb_set(
    '{"tags":["vip","email"]}'::jsonb,
    '{tags,-1}',
    '"last-updated"'::jsonb,
    false
);
~~~

Negative paths select elements counting from the end of the array.

### Do Not Trust Array Indexes Under Concurrent Edits

If client A reads a 2-element array, client B inserts an element at the beginning, and client A sends "edit index 1," index 1 now points to a **different element**.

When elements carry **business identity** (`address_id`, `item_id`), positional index updates are fragile if lists can be reordered, inserted into, or deleted from. Store stable IDs inside elements and check versions, or normalize into a child table.

## 17. Appending to the End of a JSON Array with ||

Concatenating two JSONB arrays:

~~~sql
SELECT
    '["vip","email"]'::jsonb
    ||
    '["priority"]'::jsonb AS merged_tags;
~~~

Result:

~~~json
["vip","email","priority"]
~~~

In the table:

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET doc = jsonb_set(
    doc,
    '{tags}',
    (doc -> 'tags') || jsonb_build_array('priority'),
    true
)
WHERE profile_id = 101
RETURNING doc -> 'tags' AS tags;

ROLLBACK;
~~~

### Use jsonb_build_array to Preserve Structure

When appending an address object:

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET doc = jsonb_set(
    doc,
    '{addresses}',
    (doc -> 'addresses')
      || jsonb_build_array(
           jsonb_build_object(
               'label', 'warehouse',
               'city', 'Hai Phong'
           )
         ),
    true
)
WHERE profile_id = 101
RETURNING doc -> 'addresses' AS addresses;

ROLLBACK;
~~~

`jsonb_build_array(jsonb_build_object(...))` creates **a single-element array containing one object**, and concatenates it onto the existing addresses array.

### What If tags Does Not Exist?

Profile 103 has `tags`, yet in general data it might be missing. When missing, you might see:

~~~sql
COALESCE(doc -> 'tags', '[]'::jsonb)
  || jsonb_build_array('priority')
~~~

This handles **SQL NULL from a missing key**. It does **not** verify that the branch is actually an array; if the value is JSON `null`, an object, or a scalar, `||` produces unexpected structures or semantics. Check `jsonb_typeof` before appending.

## 18. Inserting a JSON Array Element at a Position with jsonb_insert

`jsonb_insert` is used when you want to **insert** a new element rather than **overwrite** an existing one.

Signature:

~~~sql
jsonb_insert(
    target jsonb,
    path text[],
    new_value jsonb,
    insert_after boolean DEFAULT false
)
~~~

For arrays:

- `insert_after = false`: inserts **before** the specified position.
- `insert_after = true`: inserts **after** the specified position.

Example:

~~~sql
SELECT jsonb_insert(
    '{"tags":["vip","email"]}'::jsonb,
    '{tags,1}',
    '"priority"'::jsonb,
    false
) AS result;
~~~

Result:

~~~json
{"tags":["vip","priority","email"]}
~~~

Inserting after index 0:

~~~sql
SELECT jsonb_insert(
    '{"tags":["vip","email"]}'::jsonb,
    '{tags,0}',
    '"priority"'::jsonb,
    true
);
~~~

Logical result is the same:

~~~json
{"tags":["vip","priority","email"]}
~~~

### Difference from jsonb_set

| Function | With path pointing to array index 1 |
| --- | --- |
| `jsonb_set` | Replaces element at index 1 if it exists |
| `jsonb_insert` | Inserts adjacent to index 1, shifting remaining elements |

`jsonb_insert` also has specific rules when the final path element is an object key; it is not an arbitrary object merge function, and intermediate path branches must still exist.

## 19. Deleting an Array Element by Index

Use `#-` with a nested path:

~~~sql
SELECT
    '{"tags":["vip","email","priority"]}'::jsonb
    #- '{tags,1}' AS result;
~~~

Result:

~~~json
{"tags":["vip","priority"]}
~~~

In the table:

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET doc = doc #- '{addresses,0}'
WHERE profile_id = 101
RETURNING doc -> 'addresses' AS remaining_addresses;

ROLLBACK;
~~~

Profile 101 retains only the `office` address.

### Deleting Shifts Subsequent Indexes

Removing `addresses[0]` causes the element previously at `addresses[1]` to move to `addresses[0]`. A client storing "primary address = index 1" loses stability.

Use numeric indexes only when positional list order itself is the domain model. If elements need stable identity, add an `address_id` or normalize into a `profile_addresses` table with a primary key.

## 20. Deleting Array Elements by String Value

On a JSONB array containing strings, `- text` removes all matching string elements:

~~~sql
SELECT
    '["vip","email","vip","priority"]'::jsonb
    - 'vip' AS remaining_tags;
~~~

Result:

~~~json
["email","priority"]
~~~

In a table, extract the array branch, remove the element, and set it back:

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET doc = jsonb_set(
    doc,
    '{tags}',
    (doc -> 'tags') - 'vip',
    false
)
WHERE profile_id = 101
RETURNING doc -> 'tags' AS tags;

ROLLBACK;
~~~

### Distinguish Two Cases

- `doc - 'vip'` when `doc` is a top-level object: deletes the **top-level key `vip`**, not anywhere inside nested fields.
- `(doc -> 'tags') - 'vip'` when `tags` is an array: deletes matching **string** elements inside that array.

This operator does not delete an object inside an array just because the object has a field valued `"vip"`. For arrays of objects, filter/rebuild cleanly or use a relational model.

## 21. Deleting Objects from a JSON Array by Attribute

Suppose addresses look like:

~~~json
[
  {"label":"home","city":"Ha Noi"},
  {"label":"office","city":"Da Nang"}
]
~~~

To remove every object with `label = 'office'`, you cannot simply apply `- 'office'` to the array as with strings, because the array holds objects rather than that string.

One method is to expand the array into rows, filter, and re-aggregate in the original order:

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles AS p
SET doc = jsonb_set(
    p.doc,
    '{addresses}',
    COALESCE(
        (
            SELECT jsonb_agg(e.value ORDER BY e.ordinality)
            FROM jsonb_array_elements(p.doc -> 'addresses')
                 WITH ORDINALITY AS e(value, ordinality)
            WHERE e.value ->> 'label' IS DISTINCT FROM 'office'
        ),
        '[]'::jsonb
    ),
    false
)
WHERE p.profile_id = 101
  AND jsonb_typeof(p.doc -> 'addresses') = 'array'
RETURNING p.doc -> 'addresses' AS addresses;

ROLLBACK;
~~~

Inside the transaction, what remains is:

~~~json
[{"label":"home","city":"Ha Noi"}]
~~~

### Why ORDER BY ordinality?

`jsonb_array_elements` expands an array into multiple rows. In SQL, `jsonb_agg` **does not guarantee source order unless explicitly specified**. `WITH ORDINALITY` numbers elements from 1, and `ORDER BY e.ordinality` preserves the original relative order of surviving elements.

### Why COALESCE?

If the filter removes all elements, `jsonb_agg` returns **SQL NULL** on empty input. `COALESCE(..., '[]'::jsonb)` ensures `addresses` becomes an **empty array**, not SQL NULL.

### Risks

The query above rebuilds the entire array; for thousands of objects in one JSON document, CPU, value width, and UPDATE costs can be high. If searching or deleting addresses by ID happens frequently, a relational child table is usually a much better fit.

## 22. Editing an Attribute of an Object Inside a JSON Array

Example: changing the `city` of the first address:

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET doc = jsonb_set(
    doc,
    '{addresses,0,city}',
    to_jsonb('Hai Phong'::text),
    false
)
WHERE profile_id = 101
RETURNING doc -> 'addresses' AS addresses;

ROLLBACK;
~~~

Logical result inside the transaction:

~~~json
[
  {"label":"home","city":"Hai Phong"},
  {"label":"office","city":"Da Nang"}
]
~~~

`{addresses,0,city}` specifies three steps:

1. Key `addresses` on the object.
2. Array element at index `0`.
3. Key `city` inside that element object.

### Should You Use Index 0 to Update an Address?

Only when list order is well defined and the application is certain element 0 is still the target address. With concurrent additions, deletions, or reordering, use a **stable ID inside each element** plus version checks, or move to a child table with its own primary key.

## 23. Handling JSON null and SQL NULL

This is an easy way to lose data.

JSON containing:

~~~json
{"nickname": null}
~~~

and JSON:

~~~json
{}
~~~

are **not the same**.

On profile 101:

~~~sql
SELECT
    doc ? 'nickname' AS key_present,
    doc -> 'nickname' AS raw_json_value,
    jsonb_typeof(doc -> 'nickname') AS json_value_type,
    doc ->> 'nickname' AS text_value
FROM json_edit_lab.customer_profiles
WHERE profile_id = 101;
~~~

Meaning:

- `key_present = true`: the key exists.
- `raw_json_value` is JSONB `null`, **distinct from SQL NULL**.
- `json_value_type = 'null'`: this is a JSON null.
- `text_value` is SQL NULL when extracted with `->>`.

When the key does not exist, `doc -> 'nickname'` returns **SQL NULL**, and `jsonb_typeof(SQL NULL)` is also SQL NULL.

### Comparison Table

| Case | `doc ? 'nickname'` | `jsonb_typeof(doc->'nickname')` |
| --- | --- | --- |
| Key missing | `false` | SQL NULL |
| Key present with JSON null | `true` | text `'null'` |
| Key present with JSON string | `true` | text `'string'` |
| Key present with JSON number | `true` | text `'number'` |

**Never rely on `doc->>'nickname' IS NULL` alone to conclude a key is absent.** It can be NULL either because of JSON null or a missing key.

## 24. Setting JSON null Differs from Deleting a Key

Setting JSON null:

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET doc = jsonb_set(
    doc,
    '{nickname}',
    'null'::jsonb,
    true
)
WHERE profile_id = 102
RETURNING
    doc ? 'nickname' AS has_key,
    jsonb_typeof(doc -> 'nickname') AS value_type;

ROLLBACK;
~~~

Result: `has_key = true`, `value_type = 'null'`.

Deleting the key:

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET doc = doc - 'nickname'
WHERE profile_id = 101
RETURNING doc ? 'nickname' AS has_key;

ROLLBACK;
~~~

Result: `has_key = false`.

### SQL NULL in the new_value Parameter

Never casually pass `NULL::jsonb` to `jsonb_set` expecting it to mean the JSON literal `null`:

~~~sql
-- SQL NULL and JSON null are two distinct values.
SELECT
    NULL::jsonb AS sql_null,
    'null'::jsonb AS json_null;
~~~

Because `jsonb_set` is strict, passing **SQL NULL** as `new_value` causes `jsonb_set` to return SQL NULL, which violates a `doc NOT NULL` constraint if assigned directly.

Pass `'null'::jsonb` or use an API that handles NULL explicitly.

## 25. jsonb_set_lax and Policies for SQL NULL

Supported PostgreSQL versions provide `jsonb_set_lax` to define behavior when `new_value` is **SQL NULL**:

~~~sql
jsonb_set_lax(
    target jsonb,
    path text[],
    new_value jsonb,
    create_if_missing boolean DEFAULT true,
    null_value_treatment text DEFAULT 'use_json_null'
)
~~~

Supported strategies:

| `null_value_treatment` | Meaning when `new_value` is SQL NULL |
| --- | --- |
| `use_json_null` | Set the value to JSON null |
| `delete_key` | Delete the element at `path` |
| `return_target` | Return the original document unchanged |
| `raise_exception` | Raise an error forcing the caller to handle it |

Example deleting `nickname` when the incoming parameter is SQL NULL:

~~~sql
SELECT jsonb_set_lax(
    '{"nickname":"Lannie","active":true}'::jsonb,
    '{nickname}',
    NULL::jsonb,
    true,
    'delete_key'
);
~~~

Result:

~~~json
{"active":true}
~~~

When `new_value` is **not** SQL NULL, `jsonb_set_lax` behaves like `jsonb_set` for replacing the value at `path`.

### When to Use?

When an update interface cleanly separates:

- A concrete value to write.
- JSON null to keep the key as explicitly empty.
- Key deletion.
- No change.
- Rejecting invalid SQL NULLs.

Never let arbitrary Java/JDBC nulls automatically turn into "delete key" unless the API contract specifies that behavior.

## 26. JSONB Subscripting Assignment

In PostgreSQL versions supporting JSONB subscripting assignment (from PostgreSQL 14), paths can be updated with array-like subscript syntax:

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET
    doc['settings']['theme'] = '"dark"'::jsonb
WHERE profile_id = 101
RETURNING doc #>> '{settings,theme}' AS theme;

ROLLBACK;
~~~

This is **another syntax for updating JSONB**, not an in-place write of a few bytes on disk.

### Differences to Watch

- Older PostgreSQL versions do not support this syntax.
- Rules for missing intermediate branches, JSON nulls, or out-of-range array indexes **do not match every option of `jsonb_set`**.
- On arrays, subscripting beyond the current length can pad intervening positions with JSON nulls depending on the case.
- The assigned value must have the right JSONB type.

Before migrating working `jsonb_set` code to subscripting, verify semantics on **your exact major version** with missing paths and arrays.

**Do not pick the shorter syntax assuming lower physical UPDATE cost.** Both go through PostgreSQL's row/JSONB update mechanics.

## 27. Patching Multiple Attributes via Nested jsonb_set Calls

Suppose a single request changes the theme and enables push notifications. You can nest calls:

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET doc = jsonb_set(
    jsonb_set(
        doc,
        '{settings,theme}',
        '"dark"'::jsonb,
        false
    ),
    '{settings,notifications,push}',
    'true'::jsonb,
    true
)
WHERE profile_id = 101
RETURNING doc -> 'settings' AS settings;

ROLLBACK;
~~~

Advantages:

- One SQL `UPDATE` on one row.
- Both edits belong to the same statement and transaction.
- On a constraint or transaction error, one edit cannot commit without the other.

Trade-offs:

- Each nested call constructs an intermediate JSONB value for the outer expression.
- Across many paths and large documents, this can consume more CPU and allocations than updating small normalized structures.
- Measure on real data if PATCH requests regularly touch hundreds of paths.

### Simple Top-Level PATCH

If only modifying top-level keys, you can use:

~~~sql
doc || jsonb_build_object(
    'language', 'vi',
    'timezone', 'Asia/Ho_Chi_Minh'
)
~~~

but never use that pattern for deep merges where nested child keys must be preserved.

## 28. JSONB Does Not Automatically Validate Nested Schemas

The `jsonb` type allows all of these shapes:

~~~json
{"tags": ["vip", "new"]}
~~~

~~~json
{"tags": "vip"}
~~~

~~~json
{"tags": null}
~~~

If application code assumes `tags` is always an array and runs:

~~~sql
jsonb_array_elements(doc -> 'tags')
~~~

on a string scalar or JSON null, the query raises an error.

### Checking Type Inside UPDATE

~~~sql
UPDATE json_edit_lab.customer_profiles
SET doc = jsonb_set(
    doc,
    '{tags}',
    (doc -> 'tags') || jsonb_build_array('priority'),
    false
)
WHERE profile_id = 101
  AND jsonb_typeof(doc -> 'tags') = 'array';
~~~

This updates only when `tags` is an array.

### Enforcing Rules with CHECK When Needed

Example table requiring `tags` to always be an array:

~~~sql
CREATE TABLE json_edit_lab.strict_profiles (
    profile_id bigint PRIMARY KEY,
    doc jsonb NOT NULL,
    CHECK (
        jsonb_typeof(doc) = 'object'
        AND doc ? 'tags'
        AND jsonb_typeof(doc -> 'tags') = 'array'
    )
);
~~~

Validating complex multi-field schemas may require an explicit schema strategy, relational columns, or application-level validation alongside constraints. `CHECK` is not a full JSON Schema validator.

**Note on SQL three-valued logic:** a `CHECK` expression evaluating to `UNKNOWN`/`NULL` is **not** treated as a violation. To require a field to exist with a specific type, write the predicate so a missing path cannot slip through, as with `doc ? 'tags'` above.

## 29. SQL Arrays Differ from JSON Arrays When Editing

Suppose we have a SQL array column:

~~~sql
CREATE TABLE json_edit_lab.sql_array_demo (
    id integer PRIMARY KEY,
    tags text[] NOT NULL DEFAULT ARRAY[]::text[]
);

INSERT INTO json_edit_lab.sql_array_demo
    (id, tags)
VALUES
    (1, ARRAY['vip','email']);
~~~

Appending an element to a SQL array:

~~~sql
UPDATE json_edit_lab.sql_array_demo
SET tags = array_append(tags, 'priority')
WHERE id = 1;
~~~

Removing a value:

~~~sql
UPDATE json_edit_lab.sql_array_demo
SET tags = array_remove(tags, 'vip')
WHERE id = 1;
~~~

Reading:

~~~sql
SELECT id, tags, tags[1] AS first_tag
FROM json_edit_lab.sql_array_demo;
~~~

With SQL arrays, default indexes start at **1**; with JSON array subscripts, indexes start at **0**.

### Should You Choose a SQL Array or a JSON Array?

| Scenario | Option to Consider |
| --- | --- |
| Homogeneous list of `text`, `int`, etc. | SQL array |
| Array of multi-attribute objects | JSONB array or child table |
| Needs links to other tables, FKs, independent updates | Relational table |
| Flexible API payload with evolving schema | JSONB |
| Containment/overlap searches on large arrays | Compare operators and indexes for SQL arrays vs. JSONB |

No single choice fits every case. Decide based on query patterns, update frequency, constraints, and concurrency.

## 30. Does a JSONB UPDATE Patch Only a Small Piece In Place?

**Not in the sense of an "in-place patch of a few bytes inside stored JSONB."**

Suppose `doc` is 1 MB, and `settings.theme` is only 5 characters long. The statement:

~~~sql
UPDATE json_edit_lab.customer_profiles
SET doc = jsonb_set(
    doc,
    '{settings,theme}',
    '"dark"'::jsonb,
    false
)
WHERE profile_id = 101;
~~~

updates **the column's JSONB value** in a new PostgreSQL row version.

Under MVCC:

1. PostgreSQL must compute the new `doc` value.
2. `UPDATE` writes a new tuple version (subject to internal storage optimizations).
3. Depending on size, `doc` may be stored inline, compressed, or out-of-line via TOAST.
4. Affected indexes must insert new entries and clean up old ones under MVCC rules.
5. WAL records, dirty buffers, and future VACUUM work are generated.

**Do not claim PostgreSQL literally writes an exact 1 MB uncompressed block to disk every single time**, since TOAST/compression, WAL, page management, and unchanged-column optimizations make physical cost nuanced. Equally, never assume editing one path avoids JSONB reconstruction and write costs.

## 31. MVCC and Row Versions During Updates

PostgreSQL never overwrites an existing tuple in place in a way that would break older snapshots.

~~~text
T0: doc version A
    {"settings":{"theme":"light"}, ...}

T1: UPDATE jsonb_set(...)
    creates tuple version B
    {"settings":{"theme":"dark"}, ...}

Readers with an older snapshot can still see A.
Eligible readers after COMMIT see B.
VACUUM reclaims obsolete versions once no longer needed.
~~~

This applies equally to integers, text, and JSONB. Because JSONB values are complex and potentially very large, constructing the new value, compressing/TOASTing, and maintaining indexes consume far more resources than updating a small scalar column.

### A Row Holds More Than Just doc

If a table has:

~~~text
profile_id | email | doc | version | updated_at
~~~

and only `doc` changes, PostgreSQL still versions **the entire row**. Cost lives at the tuple and transaction level, not merely inside the `jsonb_set` call.

## 32. TOAST and Large JSONB Values

PostgreSQL uses **TOAST** for large column values exceeding heap tuple inline thresholds/strategies. Large JSONB values may be compressed, stored out-of-line, or both depending on storage settings and size.

For example, a document containing:

- 5,000 action history entries.
- 3,000 addresses or items.
- Hundreds of KB of descriptive text.
- A huge array of objects.

Simply changing `settings.theme` requires rebuilding the logical JSONB value, and because `doc` changed, TOAST must process the new value. Actual cost depends on compression ratios and storage settings.

### Unchanged TOAST Values vs. Modified JSONB Values

When a large TOASTed column is **not modified** during an `UPDATE` that touches a different column, PostgreSQL can reuse the pointer to the existing TOAST value.

When **`doc` itself is modified** by `jsonb_set`, never assume PostgreSQL can patch a tiny fragment of the TOAST value in place. Measure I/O, WAL, and TOAST behavior on realistic data.

### Design Impact

If a small field like `theme` changes constantly while multi-MB history rarely changes, consider **extracting `theme` into a relational column** or a small settings table rather than rewriting a huge JSONB document on every theme toggle.

## 33. How Do HOT Updates Relate to JSONB?

**HOT (Heap-Only Tuple)** is a PostgreSQL optimization allowing an `UPDATE` to skip adding new index entries when conditions hold — notably that no indexed column (excluding certain cases) changes and sufficient free space exists on the same heap page.

Suppose a table only has:

~~~sql
CREATE TABLE json_edit_lab.hot_demo (
    id bigint PRIMARY KEY,
    doc jsonb NOT NULL,
    note text
);
~~~

If only `id` is indexed, an `UPDATE` to `doc` can **qualify for HOT** when `id` stays unchanged and the heap page has room.

However, if you add:

~~~sql
CREATE INDEX idx_hot_demo_doc_gin
ON json_edit_lab.hot_demo
USING gin (doc);
~~~

an `UPDATE` modifying `doc` touches an indexed column, reducing or eliminating HOT eligibility for `doc` updates under index rules.

### Why Does This Matter?

Without HOT, new index entries must be written for every new tuple version. On tables with multiple indexes, write amplification grows substantially.

**Do not assume every JSONB UPDATE without GIN is HOT.** HOT eligibility also depends on:

- Free space on the heap page.
- Tuple width and row growth.
- Other indexes (including expression, partial, and `INCLUDE` indexes).
- Index types and version-specific optimizations.
- Table state and DML distribution.

## 34. GIN Indexes Help Reads at a Write Cost

JSONB is frequently queried with containment:

~~~sql
SELECT profile_id
FROM json_edit_lab.customer_profiles
WHERE doc @> '{"settings":{"theme":"dark"}}'::jsonb;
~~~

A GIN index can be created:

~~~sql
CREATE INDEX idx_customer_profiles_doc_gin
ON json_edit_lab.customer_profiles
USING gin (doc);
~~~

GIN serves multiple JSONB search operators when supported by the operator class.

### Benefits

- Finds objects/arrays containing matching key/value pairs.
- Queries flexible attributes without dedicated scalar columns.
- Can sharply reduce rows scanned on large datasets when predicates are selective.

### Costs

- Increased index disk footprint.
- JSONB `INSERT`/`UPDATE` must maintain many index entries.
- Extra CPU, buffer churn, WAL, and VACUUM/maintenance work.
- GIN `fastupdate`/pending-list mechanics with their own latency characteristics.
- Indexing the whole `doc` column can be very expensive when documents are large and frequently updated.

**A GIN index does not guarantee speeding up every JSONB query.** On the three-row lab table, PostgreSQL chooses Seq Scan because reading the whole table is trivial.

## 35. jsonb_ops and jsonb_path_ops

Two common GIN operator classes for JSONB:

~~~sql
CREATE INDEX idx_doc_ops
ON json_edit_lab.customer_profiles
USING gin (doc jsonb_ops);
~~~

~~~sql
CREATE INDEX idx_doc_path_ops
ON json_edit_lab.customer_profiles
USING gin (doc jsonb_path_ops);
~~~

Each operator class supports a different set of operators and entry layouts.

| Operator Class | Practical Characteristics |
| --- | --- |
| `jsonb_ops` | Default; supports broad JSONB operators including key-existence operators |
| `jsonb_path_ops` | Usually smaller and faster for supported containment/jsonpath queries, but lacks key-existence operators like `jsonb_ops` |

Example:

~~~sql
WHERE doc @> '{"settings":{"theme":"dark"}}'::jsonb
~~~

is a containment query where GIN is a candidate.

Whereas:

~~~sql
WHERE doc ? 'tags'
~~~

uses a top-level key-existence operator. Do not assume both operator classes support the same operators.

### Do Not Create Both Without Justification

Creating both `jsonb_ops` and `jsonb_path_ops` on the same column forces the application to pay write/maintenance costs for **both indexes**. Keep both only if distinct query patterns require them and measurements prove the benefit.

## 36. Expression Index for a Frequently Queried JSON Path

If the application primarily filters by `theme`, a full-document GIN index may be unnecessary. Consider a B-tree expression index:

~~~sql
CREATE INDEX idx_customer_profiles_theme
ON json_edit_lab.customer_profiles (
    (doc #>> '{settings,theme}')
);
~~~

Matching query:

~~~sql
SELECT profile_id
FROM json_edit_lab.customer_profiles
WHERE doc #>> '{settings,theme}' = 'dark';
~~~

### Benefits

- Indexes a **single scalar value** queried frequently.
- Usually smaller than a full-document GIN index.
- Easy to combine in composite or partial indexes when workloads warrant it.

### Trade-offs

- Updating `doc` still triggers index maintenance whenever the extracted expression changes (or per index rules).
- Queries using a different expression or comparison type may not match the index.
- Text comparisons and collations affect planning and ordering.
- A two-value `theme` field with a 50/50 split may not be selective enough for an index to help.

Never create an expression index merely because a path appears in `SELECT`. Measure selectivity, frequency, and write overhead.

## 37. JSONB or Relational Columns?

A profile table might hold:

~~~text
profile_id
email
doc: {
    "name": ...,
    "theme": ...,
    "tags": [...],
    "addresses": [...],
    "history": [...]
}
~~~

When should you split data out?

| Scenario | Direction to Consider |
| --- | --- |
| `theme` changes very frequently | `theme text` column or small settings table |
| Addresses need IDs, FKs, or independent updates | `profile_addresses` table |
| `tags` is a short, rarely edited list | JSONB array or SQL `text[]` may suffice |
| `history` grows unboundedly | Append-only event/history table |
| Metadata from multiple providers changes schemas | Flexible JSONB |
| Uniqueness needed per element inside an array | Relational table with `UNIQUE` constraint |
| Filtering on one hot path | Expression index or typed column |
| High concurrent updates to independent items | Normalize into separate rows to cut contention |

**JSONB complements a relational schema; it is not an excuse to discard constraints and relational modeling.**

## 38. Why Does a Huge JSONB Document Easily Become a "Hot Row"?

Suppose a table row holds:

~~~text
profile_id = 101
doc = { settings, tags, addresses, events, history, counters, ... }
~~~

Two services modify it concurrently:

- Service A updates `settings.theme`.
- Service B appends to `history[...]`.

Even though the two services touch **different paths**, PostgreSQL still updates **the exact same row**, forcing row-level lock coordination.

This can cause:

- Increased lock waits.
- Lower update throughput when multiple workers edit one profile.
- Higher risk of clients overwriting newer changes with stale documents.
- Higher JSONB reconstruction and TOAST overhead on large rows.
- Longer lock hold times if updates are complex.

### Splitting Out Hot Counters and History

If `metrics.visits` increments constantly, consider a dedicated counter column or table:

~~~sql
CREATE TABLE json_edit_lab.profile_counters (
    profile_id bigint PRIMARY KEY
        REFERENCES json_edit_lab.customer_profiles(profile_id),
    visits bigint NOT NULL DEFAULT 0
);
~~~

Update:

~~~sql
UPDATE json_edit_lab.profile_counters
SET visits = visits + 1
WHERE profile_id = 101;
~~~

The benefit is not only "an integer is smaller than JSONB," but also **isolating lock contention, data structure, and write lifecycle** from the large profile document.

## 39. Update Contention: Clients Reading and Writing the Whole Document

A scenario prone to data loss:

~~~text
Initial:
  doc = {"settings":{"theme":"light"},"tags":["vip"]}

Client A reads the entire doc.
Client B reads the entire doc.

A changes theme to dark and sends the whole doc:
  {"settings":{"theme":"dark"},"tags":["vip"]}

B adds tag priority on its stale copy and sends the whole doc:
  {"settings":{"theme":"light"},"tags":["vip","priority"]}

If B writes after A, A's theme change is overwritten back to light.
~~~

This is an **application-level lost update** caused by rebuilding the document from a stale snapshot and sending:

~~~sql
UPDATE json_edit_lab.customer_profiles
SET doc = $1::jsonb
WHERE profile_id = $2;
~~~

PostgreSQL locks and serializes writes on the row, yet it **cannot know** that client B's payload was built from an outdated snapshot that missed A's new theme.

### How to Prevent It

1. Send **only the path change** and compute the new value in SQL with `jsonb_set(doc, ...)` when semantics allow.
2. Use **optimistic locking** with a `version` column checked in `WHERE`.
3. Lock the row with `SELECT ... FOR UPDATE` when business logic must read, decide, and write in one transaction.
4. Design PATCH APIs that distinguish omitted keys, explicit nulls, and key deletions.
5. Split independently updated data into separate relational rows when high concurrency is needed.

## 40. Two Transactions Editing Different Paths with jsonb_set

Under `READ COMMITTED` with a direct SQL `UPDATE` in each transaction:

**Session A:**

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET doc = jsonb_set(
    doc,
    '{settings,theme}',
    '"dark"'::jsonb,
    false
)
WHERE profile_id = 101;

-- Keep transaction A uncommitted.
~~~

**Session B:**

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET doc = jsonb_set(
    doc,
    '{settings,notifications,sms}',
    'true'::jsonb,
    false
)
WHERE profile_id = 101;

-- B may wait for A on the same row.
~~~

**Session A:**

~~~sql
COMMIT;
~~~

After A commits, under `READ COMMITTED`, PostgreSQL re-evaluates B's `UPDATE` against the latest committed row version when the `WHERE` clause still matches. Because B computes `jsonb_set` **from the database's current `doc` column in SQL**, edits to **two disjoint paths** are both preserved.

**Session B:**

~~~sql
COMMIT;
~~~

Then inspect:

~~~sql
SELECT
    doc #>> '{settings,theme}' AS theme,
    doc #> '{settings,notifications,sms}' AS sms
FROM json_edit_lab.customer_profiles
WHERE profile_id = 101;
~~~

In the lab, the result has `theme = 'dark'` and `sms = true`.

### Limits of This Conclusion

- This does **not** mean B never waits; two `UPDATE`s on the same row still contend for the row lock.
- If two transactions edit **the same path**, the later commit overwrites the earlier one per execution order.
- Under `REPEATABLE READ` or `SERIALIZABLE`, one transaction can fail with SQLSTATE `40001` instead of re-evaluating like `READ COMMITTED`.
- If the application already built a full `doc` from a stale read and ran `SET doc = $full_document`, lost updates still occur.

**After running a two-session lab with real `COMMIT`s, reset the schema before subsequent exercises if you need the original seed.**

## 41. Atomic Increment Inside JSONB

Profile 101 has:

~~~json
"metrics": {"visits": 4}
~~~

A buggy application counter:

~~~text
A: reads visits = 4
B: reads visits = 4
A: writes visits = 5
B: writes visits = 5
-> one increment lost
~~~

Computing inside a single `UPDATE`:

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET doc = jsonb_set(
    doc,
    '{metrics,visits}',
    to_jsonb(
        (doc #>> '{metrics,visits}')::bigint + 1
    ),
    false
)
WHERE profile_id = 101
RETURNING doc #>> '{metrics,visits}' AS visits;

ROLLBACK;
~~~

In the lab, `visits` goes from 4 to 5.

### Under Concurrent Increments

With a single `UPDATE` computing directly from the current row value under `READ COMMITTED` locking and re-evaluation rules, increments serialize on the row rather than relying on stale client reads.

However:

- Each increment still logically updates **the entire JSONB value**.
- If `visits` is very hot, row contention rises.
- `metrics.visits` must exist and hold a value castable to `bigint`.
- If data is mistyped, the cast fails.

**In production systems with counters incrementing thousands of times per second, a dedicated relational column or counter table is usually far better than rewriting a large JSONB document on every increment.**

## 42. Optimistic Locking with a Version Column

The `version` column in the lab detects clients operating on stale data.

Client reads:

~~~sql
SELECT
    profile_id,
    version,
    doc
FROM json_edit_lab.customer_profiles
WHERE profile_id = 101;
~~~

Suppose it sees `version = 0`. On PATCH:

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET
    doc = jsonb_set(
        doc,
        '{settings,theme}',
        '"dark"'::jsonb,
        false
    ),
    version = version + 1,
    updated_at = clock_timestamp()
WHERE profile_id = 101
  AND version = 0
RETURNING profile_id, version;

ROLLBACK;
~~~

If `RETURNING` emits zero rows, then either:

- The ID does not exist.
- `version` changed since the client read it.
- Another `WHERE` condition no longer matched.

The application must reload state or return a conflict error, never assuming "UPDATE succeeded" just because SQL did not throw an error.

### What If Two Clients Both Read Version 0?

One client succeeds and bumps `version` to 1; the other tests `WHERE version = 0` after waiting/re-evaluating and updates **0 rows**. That detects the stale write before an old document can overwrite newer changes.

**Never read `version` on the client and omit the version check from the `UPDATE`.** The check must execute atomically inside the write statement.

## 43. When to Use SELECT FOR UPDATE?

If business logic needs to:

1. Read multiple paths.
2. Verify an invariant.
3. Run additional SQL statements in the same transaction.
4. Update the document based on what was read.

you can use:

~~~sql
BEGIN;

SELECT profile_id, doc, version
FROM json_edit_lab.customer_profiles
WHERE profile_id = 101
FOR UPDATE;

-- Verify business conditions on this connection.
-- Then UPDATE within the SAME transaction.

UPDATE json_edit_lab.customer_profiles
SET doc = jsonb_set(
    doc, '{settings,theme}', '"dark"'::jsonb, false
)
WHERE profile_id = 101;

COMMIT;
~~~

`FOR UPDATE` holds the row lock until the transaction ends under PostgreSQL rules. Never assume running `SELECT FOR UPDATE` in autocommit mode and closing the connection protects an `UPDATE` sent in a later transaction.

### Do Not Hold Row Locks Across Slow Network Calls

Holding a lock while calling an external service for 30 seconds blocks all other updates to that profile. Use state machines, outbox/idempotency patterns, or split transactions when external work is slow.

## 44. PATCH APIs: Missing Keys, JSON null, and Explicit Deletion

A well-designed PATCH API distinguishes at least three states:

| Request Payload | Possible Intended Semantics |
| --- | --- |
| `nickname` omitted | Keep existing `nickname` |
| `"nickname": null` sent | Set value to JSON null |
| Explicit delete operation | Remove key from the JSON object |

There is no single universal rule across all APIs. For example, JSON Merge Patch (RFC 7396) uses `null` to delete an object member, whereas JSON Patch (RFC 6902) has a dedicated `remove` operation. Follow whichever standard your API specifies consistently.

### Why Not Use COALESCE for Every PATCH?

Writing:

~~~sql
doc = jsonb_set(
    doc,
    '{nickname}',
    COALESCE($1::jsonb, doc -> 'nickname'),
    true
)
~~~

can accidentally conflate **SQL NULL from an omitted field** with **an intentional JSON null**, depending on how the application binds parameters.

It is better to parse and validate the request and execute an **explicit operation**: replace, add, remove, or no-op.

## 45. Observing JSONB Size

`pg_column_size` reports the storage size of a value in PostgreSQL:

~~~sql
SELECT
    profile_id,
    pg_column_size(doc) AS doc_storage_bytes,
    length(doc::text) AS json_text_characters
FROM json_edit_lab.customer_profiles
ORDER BY profile_id;
~~~

The two numbers differ:

- `pg_column_size(doc)` reflects the stored representation size.
- `length(doc::text)` counts characters in the rendered text output.

For large JSONB values, compression/TOAST and actual payload content can make these numbers diverge sharply. Never treat `length(doc::text)` as the exact WAL bytes or disk bytes written per `UPDATE`.

### Measuring Table and Index Size

~~~sql
SELECT
    pg_size_pretty(
        pg_table_size(
            'json_edit_lab.customer_profiles'::regclass
        )
    ) AS table_size,
    pg_size_pretty(
        pg_indexes_size(
            'json_edit_lab.customer_profiles'::regclass
        )
    ) AS indexes_size,
    pg_size_pretty(
        pg_total_relation_size(
            'json_edit_lab.customer_profiles'::regclass
        )
    ) AS total_size;
~~~

`pg_total_relation_size` gives the broader storage footprint including TOAST and index components. Comparing **before and after an identical DML workload** is far more informative than looking at a single point-in-time number.

## 46. Generating Many Rows to Observe Access Paths

A three-profile table is great for learning syntax, but too small to benchmark indexes.

In a **dedicated lab database**, create a benchmark table:

~~~sql
CREATE TABLE json_edit_lab.profile_bench (
    profile_id bigint PRIMARY KEY,
    doc jsonb NOT NULL
        CHECK (jsonb_typeof(doc) = 'object')
);

INSERT INTO json_edit_lab.profile_bench (
    profile_id, doc
)
SELECT
    g::bigint,
    jsonb_build_object(
        'name', 'Customer ' || g,
        'settings', jsonb_build_object(
            'theme', CASE
                WHEN g % 2 = 0 THEN 'dark'
                ELSE 'light'
            END,
            'language', 'vi'
        ),
        'tags', jsonb_build_array(
            CASE WHEN g % 10 = 0 THEN 'vip' ELSE 'regular' END
        ),
        'metrics', jsonb_build_object(
            'visits', g % 100
        ),
        'description', repeat(md5(g::text), 50)
    )
FROM generate_series(1, 30000) AS s(g);

ANALYZE json_edit_lab.profile_bench;
~~~

This seed creates 30,000 rows with nested objects and arrays. However, `repeat(md5(...), 50)` is repetitive and **compresses extremely well**; do not treat it as 1.6 KB of incompressible data or representative of large production documents in TOAST.

To benchmark TOAST realistically, generate data matching **compressed size, path count, element count, and UPDATE rate** from telemetry, ensuring all sensitive fields are anonymized.

## 47. Experimenting with Updates Before and After a GIN Index

### 47.1. Read Baseline

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT profile_id
FROM json_edit_lab.profile_bench
WHERE doc @> '{"tags":["vip"]}'::jsonb;
~~~

With roughly 10% of rows tagged `vip`, the planner may still choose Seq Scan on 30,000 rows depending on cost estimates.

### 47.2. Create a GIN Index

~~~sql
CREATE INDEX idx_profile_bench_doc_gin
ON json_edit_lab.profile_bench
USING gin (doc);

ANALYZE json_edit_lab.profile_bench;
~~~

Measure the same `SELECT` again:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT profile_id
FROM json_edit_lab.profile_bench
WHERE doc @> '{"tags":["vip"]}'::jsonb;
~~~

### 47.3. Measure an UPDATE in the Lab

~~~sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL, TIMING OFF)
UPDATE json_edit_lab.profile_bench
SET doc = jsonb_set(
    doc,
    '{settings,theme}',
    '"dark"'::jsonb,
    false
)
WHERE profile_id BETWEEN 1001 AND 2000
  AND doc #>> '{settings,theme}' = 'light';

ROLLBACK;
~~~

The `WAL` option in `EXPLAIN` is supported in PostgreSQL 13+. `EXPLAIN ANALYZE UPDATE` **actually executes the DML**, even though it is rolled back afterward.

### Reading the Output Properly

- `Execution Time`: statement cost under those conditions.
- `Buffers`: shared hits/reads/dirtied/written per plan and version.
- `WAL records/bytes`: WAL generated during execution, when supported.
- Actual rows updated.
- Whether an index scan or primary-key range located the rows.
- Whether the GIN index sped up reads while adding write work.

**Never compare one pre-index `UPDATE` against a post-index `UPDATE` on a dataset whose state already changed.** For a rigorous A/B test, reset/clone the dataset, control caching, match actual modified rows, and match concurrency.

## 48. Observing HOT Updates, Dead Tuples, and VACUUM

PostgreSQL tracks per-table statistics:

~~~sql
SELECT
    schemaname,
    relname,
    n_tup_ins,
    n_tup_upd,
    n_tup_hot_upd,
    n_tup_del,
    n_dead_tup,
    last_autovacuum,
    last_autoanalyze
FROM pg_stat_user_tables
WHERE schemaname = 'json_edit_lab'
ORDER BY relname;
~~~

Counters and estimates update asynchronously; do not read right after a single `UPDATE` expecting an instantaneous exact snapshot.

When updates occur during a measurement window:

\[
\mathrm{HOT\ ratio} =
\frac{\Delta \mathrm{n\_tup\_hot\_upd}}
{\Delta \mathrm{n\_tup\_upd}}
\]

Compute only when the denominator is greater than 0. Use **deltas over the benchmark window**, not cumulative lifetime totals, to evaluate the impact of a new index.

### What Role Does VACUUM Play?

`UPDATE` leaves behind old row versions that become dead tuples once no active snapshot needs them. `VACUUM` reclaims eligible dead tuples and maintains indexes, the visibility map, and transaction ID freezing.

Never treat `VACUUM FULL` as a routine step after JSONB updates. It rewrites the table under heavy locks with major operational impact, unlike regular `VACUUM` or autovacuum.

## 49. Measuring JSONB Update Throughput Under Concurrency

A single microbenchmark:

~~~sql
EXPLAIN (ANALYZE)
UPDATE ...
~~~

does not reveal:

- Multiple workers updating the same profile simultaneously.
- Row lock waits.
- Commit and WAL flush latency.
- TOAST and index growth over time.
- Cache eviction.
- Autovacuum activity and dead tuple accumulation.
- Replica lag during sustained write workloads.
- End-to-end p95/p99 application request latency.

A sound benchmark requires:

1. Sufficiently large datasets with realistic distributions.
2. Accurate read/write ratios.
3. Realistic client counts and prepared statement usage.
4. Matching row update counts and document sizes.
5. Committed transactions on a disposable database to measure real lifecycle costs.
6. Measuring TPS, p50/p95/p99 latency, errors, and lock waits.
7. Tracking WAL and storage growth, not SQL latency alone.
8. Hot-row contention levels matching production.

**Never assume a single 3 ms `UPDATE` means the system can sustain 1,000 updates/s on the same profile.**

## 50. GIN and Queries Are Not a "Free Index"

Check index usage via:

~~~sql
SELECT
    schemaname,
    relname,
    indexrelname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'json_edit_lab'
ORDER BY relname, indexrelname;
~~~

And measure sizes:

~~~sql
SELECT
    i.relname AS index_name,
    pg_size_pretty(pg_relation_size(i.oid)) AS index_size
FROM pg_class AS t
JOIN pg_namespace AS n
    ON n.oid = t.relnamespace
JOIN pg_index AS x
    ON x.indrelid = t.oid
JOIN pg_class AS i
    ON i.oid = x.indexrelid
WHERE n.nspname = 'json_edit_lab'
  AND t.relname = 'profile_bench'
ORDER BY pg_relation_size(i.oid) DESC;
~~~

When evaluating a GIN index:

- Do containment queries actually run frequently?
- What percentage of documents match?
- Do documents have so many keys/elements that the index bloats?
- Is `doc` updated frequently?
- Does the index hurt HOT updates and write throughput?
- Could a smaller B-tree expression index on one path replace it?

Low `idx_scan` **does not automatically prove an index is useless** if it serves a rare but critical query; however, an index yielding little benefit becomes an ongoing write tax.

## 51. Optimizing JSONB Through Lean Design

Ways to reduce overhead:

1. **Do not stuff unbounded logs or history** into a JSONB field on a frequently updated row.
2. **Extract hot fields** such as counters, status, or theme out of huge documents when update rates are high.
3. **Index only what queries genuinely need**; avoid full-document GIN when a small expression index suffices.
4. **Skip no-op UPDATEs**: check for value differences when workloads send many idempotent requests.
5. **Keep transactions short**, avoiding holding row locks across network calls.
6. **Define clear PATCH operations**: add, replace, remove, no-op, set-json-null.
7. **Use optimistic versioning** when clients read and submit multi-field updates.
8. **Never use array indexes as identity** for objects frequently inserted, deleted, or reordered.
9. **Use constraints and validation** to stop mistyped JSON from breaking path/array queries.
10. **Measure TOAST, HOT, WAL, VACUUM, and lock waits** before declaring any JSONB approach fast.

### Update Only When the Value Actually Changes

Example avoiding an `UPDATE` when theme is already `dark`:

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET doc = jsonb_set(
    doc,
    '{settings,theme}',
    '"dark"'::jsonb,
    false
)
WHERE profile_id = 101
  AND doc #>> '{settings,theme}' IS DISTINCT FROM 'dark'
RETURNING profile_id;

ROLLBACK;
~~~

With the seed data, profile 101 is `light` and gets updated. If it were already `dark`, the statement updates 0 rows.

**Note:** `IS DISTINCT FROM` handles SQL NULL safely in the comparison, yet if the intermediate path is missing, `jsonb_set` with a missing intermediate path adds nothing. When schemas allow missing parents, add explicit parent creation or validation.

## 52. Optimizing Does Not Mean Abandoning JSONB

JSONB fits well when:

- Metadata varies by entity type.
- Fields are sparse or optional.
- Per-document modification rates are low.
- Flexible containment searches are needed.
- Elements do not require complex FKs or unique constraints.
- Document sizes stay bounded.
- Proper schema validation is in place.

JSONB fits poorly when:

- One document is constantly edited by hundreds of workers.
- History or arrays grow without bound.
- Array objects need independent identity, permissions, or FKs.
- Hot scalar fields must be updated many times per second.
- Uniqueness is required across elements spanning many rows.
- Small edits force large documents to be reprocessed repeatedly.

Never decide out of bias like "JSONB is slow" or "JSONB is flexible so it beats SQL." **Good models follow real queries, write patterns, and data.**

## 53. Common Mistakes

### 53.1. Confusing json with jsonb

`jsonb_set` operates on `jsonb`. `json` columns require casting and do not preserve original text formatting across conversions.

### 53.2. Thinking || Is a Deep Merge

The object under `settings` is overwritten wholesale, wiping out `notifications`.

### 53.3. Forgetting That jsonb_set Returns a New Value

`SELECT jsonb_set(...)` does not update the stored column.

### 53.4. Passing 'dark'::jsonb Instead of '"dark"'::jsonb

Bare `dark` is not a valid JSON string; use `to_jsonb($1::text)` or properly quoted JSON string literals.

### 53.5. Expecting create_if_missing to Create All Ancestors

Intermediate branches must exist according to `jsonb_set` rules.

### 53.6. Not Checking Array Type Before jsonb_array_elements

If the path holds an object, null, or string, the array-expanding function raises an error.

### 53.7. Using jsonb_set When You Want to Insert Before an Element

`jsonb_set` replaces the element; `jsonb_insert` inserts by position.

### 53.8. Confusing 0-Based JSON Arrays with 1-Based SQL Arrays

The two structures use different subscripting conventions.

### 53.9. "Deleting" a Key by Setting JSON null

`- 'nickname'` removes the key; `jsonb_set(..., 'null'::jsonb)` keeps the key present.

### 53.10. Confusing SQL NULL with JSON null

`->>` returns SQL NULL for both a missing path and JSON null; use `?` and `jsonb_typeof` to distinguish them.

### 53.11. Using - text on the Root Object Expecting to Remove a Nested Tag

You must extract the array at its path, remove the tag, and set it back, or use `#-` with a path.

### 53.12. Treating Array Position as an Address Identifier

Inserting or deleting near the front shifts all subsequent indexes.

### 53.13. Calling jsonb_agg Without ORDER BY When Order Matters

After expanding and filtering an array, use `WITH ORDINALITY` and `ORDER BY` to restore original ordering.

### 53.14. Not Wrapping jsonb_agg with COALESCE When Returning SQL NULL

If filtering removes every element, the aggregate returns SQL NULL, not an empty JSON array.

### 53.15. Writing Back Whole Documents from Stale Client Reads

Overwrites concurrent changes from other requests despite row-level locks.

### 53.16. Thinking Two jsonb_set Calls on Different Paths Do Not Contend for Locks

Both still update the same row and serialize on its row lock.

### 53.17. Retrying Only the Final Statement After a Serialization Failure

On `40001`, you normally must retry **the entire transaction** with fresh reads.

### 53.18. Thinking a JSONB Update Patches a Few Bytes In Place

PostgreSQL produces a new JSONB result and a new MVCC row version, incurring TOAST, index, and WAL costs.

### 53.19. Assuming Every JSONB UPDATE Is HOT

HOT depends on indexes and heap-page free space; a GIN index on `doc` prevents HOT when `doc` changes.

### 53.20. Adding GIN to Every doc Without Measuring Write Throughput

GIN speeds up certain reads while potentially adding substantial index maintenance.

### 53.21. Skipping Measurements on Large / TOASTed Documents

Conclusions drawn from tiny 50-byte objects do not carry over to hundreds-of-KB documents.

### 53.22. Benchmarking on Three Rows and Concluding Indexes Are Slow

The planner picks Seq Scan on tiny tables; test on representative volumes.

### 53.23. Measuring Only SELECT While Ignoring INSERT/UPDATE/DELETE

An index can speed up JSON filters while inflating write WAL and CPU.

### 53.24. Treating EXPLAIN ANALYZE UPDATE as a Dry Run

`ANALYZE` **executes the DML**; use a lab database or wrap in a rolled-back transaction safely.

### 53.25. Skipping Constraints and Validation on JSON

Mistyped data breaks path/array functions and corrupts business semantics.

### 53.26. Failing to Align PATCH Semantics with the API

Conflating missing keys, JSON null, and remove requests leads to unintended data loss.

## 54. Practice Exercises with Answers

Use the `json_edit_lab` seed from Section 4. Wrap DML exercises in `BEGIN ... ROLLBACK` when testing so subsequent exercises see clean data. Run benchmarks only in a dedicated lab database.

### Exercise 1. How Do json and jsonb Differ?

**Answer:** `json` stores raw input text; `jsonb` stores a parsed binary format, supports rich operators and indexing, and does not preserve original key order or whitespace. For partial edits, `jsonb` is generally much more convenient.

### Exercise 2. Reading theme from a Nested Object

~~~sql
SELECT doc #>> '{settings,theme}' AS theme
FROM json_edit_lab.customer_profiles
WHERE profile_id = 101;
~~~

**Answer:** returns `'light'` as `text`.

### Exercise 3. Changing Profile 101's Theme

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET doc = jsonb_set(
    doc, '{settings,theme}', '"dark"'::jsonb, false
)
WHERE profile_id = 101
RETURNING doc #>> '{settings,theme}' AS theme;

ROLLBACK;
~~~

**Answer:** inside the transaction, `theme` becomes `'dark'`; rollback restores `'light'`.

### Exercise 4. Why Can This || Operation Lose Data?

~~~sql
SELECT
    '{"settings":{"theme":"light","notifications":{"email":true}}}'::jsonb
    ||
    '{"settings":{"theme":"dark"}}'::jsonb;
~~~

**Answer:** because `||` performs a shallow top-level merge. The right-hand `settings` key replaces the entire left-hand `settings` object, losing `notifications`.

### Exercise 5. Adding Top-Level language

~~~sql
SELECT
    '{"name":"Lan"}'::jsonb
    || jsonb_build_object('language', 'vi');
~~~

**Answer:** `{"name":"Lan","language":"vi"}` logically.

### Exercise 6. Adding push Inside notifications

~~~sql
SELECT jsonb_set(
    '{"settings":{"notifications":{"email":true}}}'::jsonb,
    '{settings,notifications,push}',
    'true'::jsonb,
    true
);
~~~

**Answer:** `notifications` gains `"push":true` while keeping `email`.

### Exercise 7. Why Might Adding settings.theme to Profile 103 Have No Effect?

**Answer:** Profile 103 has no parent `settings` object. `jsonb_set(..., '{settings,theme}', ..., true)` does not create missing ancestor objects; create `settings` first or use branch-building logic.

### Exercise 8. Deleting Key nickname

~~~sql
SELECT
    '{"name":"Lan","nickname":null}'::jsonb - 'nickname';
~~~

**Answer:** `{"name":"Lan"}`. The key is deleted and no longer exists with a null value.

### Exercise 9. Deleting Nested sms

~~~sql
SELECT
    '{"settings":{"notifications":{"email":true,"sms":false}}}'::jsonb
    #- '{settings,notifications,sms}';
~~~

**Answer:** `notifications` retains `{"email":true}`.

### Exercise 10. Replacing the Second Tag

~~~sql
SELECT jsonb_set(
    '{"tags":["vip","email"]}'::jsonb,
    '{tags,1}',
    '"priority"'::jsonb,
    false
);
~~~

**Answer:** `{"tags":["vip","priority"]}`.

### Exercise 11. Inserting a Tag Before Index 1

~~~sql
SELECT jsonb_insert(
    '{"tags":["vip","email"]}'::jsonb,
    '{tags,1}',
    '"priority"'::jsonb,
    false
);
~~~

**Answer:** `{"tags":["vip","priority","email"]}`. Differs from replacing in Exercise 10.

### Exercise 12. Appending a Tag to the End of an Array

~~~sql
SELECT
    '["vip","email"]'::jsonb
    || jsonb_build_array('priority');
~~~

**Answer:** `["vip","email","priority"]`.

### Exercise 13. Removing All "vip" String Elements

~~~sql
SELECT
    '["vip","email","vip","priority"]'::jsonb
    - 'vip';
~~~

**Answer:** `["email","priority"]`.

### Exercise 14. Removing the First Address Element

~~~sql
SELECT
    '{"addresses":[{"city":"Ha Noi"},{"city":"Da Nang"}]}'::jsonb
    #- '{addresses,0}';
~~~

**Answer:** only the `Da Nang` address object remains as the first element.

### Exercise 15. Changing city of the First Object

~~~sql
SELECT jsonb_set(
    '{"addresses":[{"city":"Ha Noi"}]}'::jsonb,
    '{addresses,0,city}',
    to_jsonb('Hai Phong'::text),
    false
);
~~~

**Answer:** `{"addresses":[{"city":"Hai Phong"}]}`.

### Exercise 16. Are JSON null and a Missing Key the Same?

**Answer:** No. `{"nickname":null}` contains the key; `{}` does not. `?` and `jsonb_typeof` distinguish them, whereas `->>` returns SQL NULL for both.

### Exercise 17. Setting nickname to JSON null

~~~sql
SELECT jsonb_set(
    '{"name":"Minh"}'::jsonb,
    '{nickname}',
    'null'::jsonb,
    true
);
~~~

**Answer:** `{"name":"Minh","nickname":null}`. The key remains present.

### Exercise 18. Using jsonb_set_lax with delete_key

~~~sql
SELECT jsonb_set_lax(
    '{"name":"Lan","nickname":"Lannie"}'::jsonb,
    '{nickname}',
    NULL::jsonb,
    true,
    'delete_key'
);
~~~

**Answer:** `{"name":"Lan"}`; handling of SQL NULL is explicitly defined as `delete_key`.

### Exercise 19. Why Can Updating One Path in a Large JSONB Document Be Costly?

**Answer:** `jsonb_set` builds a new JSONB value, `UPDATE` creates a new MVCC row version, and TOAST, index maintenance, WAL, and vacuum cleanup may follow. It is not an in-place patch of a few bytes.

### Exercise 20. How Does a GIN Index Affect HOT Updates?

**Answer:** When `doc` is GIN-indexed, updating `doc` touches an indexed column, reducing or eliminating HOT eligibility and increasing write work. Measure the exact effect by workload and PostgreSQL version.

### Exercise 21. How Do You Prevent Stale Client Overwrites?

**Answer:** Update specific paths directly in SQL when appropriate, or use a `version` column with `WHERE version = expected_version`, incrementing `version` in the same `UPDATE` and checking affected row counts. For multi-step logic, use a transaction with `FOR UPDATE`.

### Exercise 22. Atomic JSONB Increment

~~~sql
BEGIN;

UPDATE json_edit_lab.customer_profiles
SET doc = jsonb_set(
    doc,
    '{metrics,visits}',
    to_jsonb(
        (doc #>> '{metrics,visits}')::bigint + 1
    ),
    false
)
WHERE profile_id = 101
RETURNING doc #>> '{metrics,visits}' AS visits;

ROLLBACK;
~~~

**Answer:** in the lab this increments from 4 to 5. When paths might be missing or mistyped, validate first; for very hot counters, use a relational column or table.

### Exercise 23. Why Can jsonb_agg Change Array Order?

**Answer:** Aggregating after `jsonb_array_elements` does not guarantee order unless `ORDER BY` is specified inside the aggregate; use `WITH ORDINALITY` to preserve original positions.

### Exercise 24. What Does jsonb_agg Return If All Array Elements Are Filtered Out?

**Answer:** It returns SQL NULL on empty input. Use `COALESCE(jsonb_agg(...), '[]'::jsonb)` to produce an empty JSON array.

### Exercise 25. Comparing Expression Indexes and GIN

**Answer:** A B-tree expression index suits a fixed scalar path queried frequently; GIN is more flexible for containment and JSONB operators. Both carry storage and `UPDATE` costs; decide via workload and benchmarks.

### Exercise 26. Do SQL Arrays and JSON Arrays Start at the Same Index?

**Answer:** No. PostgreSQL SQL arrays normally start at lower bound 1; JSON array indexing starts at 0.

### Exercise 27. Why Must EXPLAIN ANALYZE UPDATE Be Used Carefully?

**Answer:** Because it **executes the actual UPDATE**. Use a lab database or wrap in a rolled-back transaction while learning; serious write benchmarks should commit on a disposable dataset.

### Exercise 28. When Should a JSON Array Become a Child Table?

**Answer:** When each element needs a stable ID, FKs/UNIQUE constraints, independent queries/updates, concurrent writers, or when the array grows very large. A relational table enables constraints and avoids rewriting the entire document per element edit.

## 55. Production Application Checklist

1. **Verify the column type** is `jsonb` and confirm document shape.
2. **Define PATCH semantics**: add, replace, remove, no-op, set-json-null.
3. **Use bind parameters + `to_jsonb` / `jsonb_build_object` / `jsonb_build_array`** instead of concatenating raw JSON strings.
4. **Inspect paths before editing**, validating nested object/array types.
5. **Remember `||` is a shallow merge**, not a deep merge.
6. **Use `jsonb_set` for path edits**, understanding `create_if_missing` applies only to the final element.
7. **Create missing parents explicitly** when intermediate paths might not exist.
8. **Use `jsonb_insert` to insert array elements**, not `jsonb_set`.
9. **Use `-` and `#-` to delete keys/paths**, distinct from JSON null.
10. **Preserve order when rebuilding arrays** via `WITH ORDINALITY` / `ORDER BY` and handle empty aggregates.
11. **Never treat array indexes as business identity** for mutable lists.
12. **Validate nested schemas** with constraints and/or application validation as needed.
13. **Do not send back whole stale documents from clients** without concurrency control.
14. **Use SQL atomic updates or optimistic versioning** with concurrent writers.
15. **Keep transactions short** and handle SQLSTATE retries cleanly.
16. **Measure large/TOASTed documents on representative data**, not tiny sample objects.
17. **Remember UPDATE creates a new MVCC row version**, not an in-place byte patch.
18. **Measure HOT ratio, WAL, dead tuples, index size, and update TPS** when adding GIN or expression indexes.
19. **Consider splitting hot fields, counters, and history** out of large JSONB documents.
20. **Monitor lock waits** when multiple workers update the same profile.
21. **Check `EXPLAIN` plans** on real queries rather than assuming GIN helps by name alone.
22. **Measure both `SELECT` and `INSERT`/`UPDATE`** before and after creating indexes.
23. **Never run heavy write benchmarks on production**; use staging or disposable databases.
24. **Draw conclusions only from realistic distributions**, parameters, and concurrency.
25. **Keep rollback plans ready** when changing schemas, indexes, or PATCH API semantics.

## 56. Official PostgreSQL Documentation

To verify exact syntax and behavior for **your PostgreSQL major version**, consult:

- [JSON Types](https://www.postgresql.org/docs/current/datatype-json.html) — `json` vs. `jsonb`, storage, and representation differences.
- [JSON Functions and Operators](https://www.postgresql.org/docs/current/functions-json.html) — `jsonb_set`, `jsonb_insert`, `jsonb_set_lax`, `||`, `-`, `#-`, subscripting, and JSONPath.
- [Array Functions and Operators](https://www.postgresql.org/docs/current/functions-array.html) — SQL arrays, `array_append`, `array_remove`, and differences from JSON arrays.
- [JSONB Indexing](https://www.postgresql.org/docs/current/datatype-json.html#JSON-INDEXING) — GIN operator classes, containment, and expression indexes.
- [Indexes on Expressions](https://www.postgresql.org/docs/current/indexes-expressional.html) — indexing scalar JSON paths.
- [Index Types](https://www.postgresql.org/docs/current/indexes-types.html) — B-tree, GIN, and other access methods.
- [Heap-Only Tuple Updates](https://www.postgresql.org/docs/current/storage-hot.html) — HOT conditions and index impact.
- [TOAST](https://www.postgresql.org/docs/current/storage-toast.html) — large value storage, compression, and out-of-line storage.
- [MVCC Introduction](https://www.postgresql.org/docs/current/mvcc-intro.html) — row versions and snapshots.
- [UPDATE](https://www.postgresql.org/docs/current/sql-update.html) — `SET`/`WHERE`/`RETURNING` and transaction semantics.
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html) — `READ COMMITTED`, `REPEATABLE READ`, `SERIALIZABLE`.
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html) — row-level locks and concurrency.
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html) — analyzing scans, buffers, and costs.
- [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html) — `ANALYZE`/`BUFFERS`/`WAL`.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — `pg_stat_user_tables` / `pg_stat_user_indexes` and counters.
- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html) — dead tuples and autovacuum.

`/current/` URLs point to the latest PostgreSQL documentation. When using version-dependent syntax such as JSONB subscripting or newer `EXPLAIN` options, verify against the documentation for the exact server version you run.

## 57. Summary

**PostgreSQL makes adding, modifying, and deleting JSONB components highly flexible**, yet you must separate **the logical meaning of an edit** from **its physical update cost**.

Core principles:

1. **`jsonb_set` updates or adds a value at a path**; intermediate branches must normally exist. Do not expect `create_if_missing` to create missing ancestors.
2. **`||` is a shallow merge for objects**; it can wipe out nested objects if used as a deep merge. On arrays, `||` concatenates elements under JSONB rules.
3. **`jsonb_insert` inserts into arrays**, while `jsonb_set` replaces existing elements. `-` and `#-` remove keys or elements by path.
4. **JSON null, SQL NULL, and missing keys differ**. PATCH APIs must clearly define setting null, removing a key, and leaving unchanged.
5. **JSON arrays are 0-indexed and shift on insertions/deletions**. Never use array position as business identity for mutable objects.
6. **A JSONB `UPDATE` is not an in-place patch of a few bytes**. MVCC creates a new row version and can incur TOAST, WAL, index maintenance, and VACUUM work.
7. **GIN and expression indexes speed up reads at a write cost** and affect HOT eligibility. Measure on large datasets and realistic read–write workloads.
8. **Concurrent transactions editing the same JSON document still contend on the same row**. Use SQL atomic updates, version checks, or transaction locks appropriately to prevent stale client overwrites.
9. **Extract fields into relational columns or child tables** when they change frequently, need FKs/UNIQUE/stable IDs, or bloat the JSONB document.

Choosing the right JSONB functions, data model, and concurrency strategy lets you perform partial document updates with **sound business semantics**, while keeping **storage, WAL, locking, and maintenance costs** firmly under control in PostgreSQL.
