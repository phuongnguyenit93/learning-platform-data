# Selecting Columns to Update and Impact on Unsent Columns in Cassandra

When updating a customer profile, an application might know only the new phone number without knowing the customer's current name, email, or settings. In Apache Cassandra, choosing **which columns appear in the mutation** determines which columns are actually written. This is the foundation for implementing safe partial updates with CQL and the Java Driver.

This lesson belongs to the **CQL Writes and Deletes** chapter of module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**. Cassandra is a distributed system using the wide-column model: the **partition key** determines partition placement and the **full primary key** identifies a row. Column-level updates must be understood alongside timestamp-based writes, replication, TTL, and tombstones; a Java application must accurately distinguish new values from unsent fields.

After this lesson, you will be able to:

- Write `INSERT` or `UPDATE` statements that touch only the columns that need changing.
- Predict post-write state when certain columns are absent from a CQL statement.
- Distinguish **omitted columns**, **columns assigned NULL**, **UNSET parameters**, and **new values**.
- Understand how assigning an entire collection differs from modifying a single collection element.
- Control the effects of TTL, timestamps, and concurrent writes on different columns.
- Write safe Java prepared statements for partial-update APIs.

## 1. Sample table and initial state

Suppose an account management application reads profiles by `account_id`. The `demo` keyspace is assumed to exist:

```sql
CREATE TABLE demo.accounts_by_id (
    account_id uuid PRIMARY KEY,
    display_name text,
    email text,
    phone text,
    locale text,
    notification_opt_in boolean,
    preferences map<text, text>,
    tags set<text>,
    updated_at timestamp
);
```

In this example, `account_id` is both the partition key and the full primary key. The remaining fields are regular columns. Each write with the same `account_id` targets the same logical row; Cassandra does not automatically create another row on a duplicate-key `INSERT`.

Initialize the row:

```sql
INSERT INTO demo.accounts_by_id (
    account_id, display_name, email, phone, locale,
    notification_opt_in, preferences, tags
)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'Mai Anh',
    'mai@example.test',
    '0900000001',
    'vi-VN',
    true,
    {'theme': 'light', 'digest': 'daily'},
    {'customer', 'beta'}
);

SELECT *
FROM demo.accounts_by_id
WHERE account_id = 11111111-1111-4111-8111-111111111111;
```

State to keep in mind:

| Column | Value after initial `INSERT` |
| --- | --- |
| `display_name` | `'Mai Anh'` |
| `email` | `'mai@example.test'` |
| `phone` | `'0900000001'` |
| `locale` | `'vi-VN'` |
| `notification_opt_in` | `true` |
| `preferences` | `{'theme': 'light', 'digest': 'daily'}` |
| `tags` | `{'customer', 'beta'}` |
| `updated_at` | `null` (never written) |

To make the steps easy to follow, assume no other clients are writing concurrently, the table has no TTL, and no unusual custom timestamps are used.

## 2. UPDATE writes only the columns specified

Requirement: change the phone number while leaving everything else intact.

```sql
UPDATE demo.accounts_by_id
SET phone = '0900000099'
WHERE account_id = 11111111-1111-4111-8111-111111111111;
```

An `UPDATE` statement's `SET` clause describes the columns actually being written. In this example:

- **Written column:** `phone` receives the new value.
- **Columns omitted from `SET`:** `display_name`, `email`, `locale`, `notification_opt_in`, `preferences`, `tags`, and `updated_at` are neither modified nor deleted by this statement.
- **Key:** `account_id` identifies the target row; primary key components cannot be modified via `SET`.

State after the statement:

| Column | Before | After |
| --- | --- | --- |
| `phone` | `'0900000001'` | `'0900000099'` |
| `email` | `'mai@example.test'` | `'mai@example.test'` |
| `locale` | `'vi-VN'` | `'vi-VN'` |
| `updated_at` | `null` | `null` |

There is no implicit update to `updated_at`: if the application wants to record the modification time, it must include that column in the mutation:

```sql
UPDATE demo.accounts_by_id
SET phone = '0900000088',
    updated_at = '2026-11-21 09:15:00+0700'
WHERE account_id = 11111111-1111-4111-8111-111111111111;
```

The timestamp here is merely a sample value for an application column. It is **distinct** from the write timestamp that Cassandra uses to reconcile cell versions.

### A common misunderstanding about "keeping unchanged"

"Unsent columns remain unchanged" means **the mutation in question does not overwrite those columns**. A value can still change because another client is writing concurrently, because an old value's TTL expires, or because replica reconciliation reveals a higher-timestamp winner. Do not interpret this as a guarantee of an immutable row-wide snapshot in a distributed system.

## 3. INSERT can also write only a subset of columns

In Cassandra, a regular `INSERT` is also an **upsert**, not a full-row replacement:

```sql
INSERT INTO demo.accounts_by_id (account_id, locale)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'en-US'
);
```

If the same key already exists, `locale` is overwritten to `'en-US'`. Other columns, including `phone` and `email`, are not deleted just because they are absent from the `INSERT` column list.

Comparison:

| Statement | Written columns | Omitted columns |
| --- | --- | --- |
| `INSERT INTO ... (account_id, locale) VALUES (...)` | `locale` | Remaining regular columns |
| `UPDATE ... SET locale = ... WHERE account_id = ...` | `locale` | Remaining regular columns |
| `UPDATE ... SET locale = ..., phone = ... WHERE ...` | `locale`, `phone` | Other regular columns |

For the sample table, updating regular columns via `UPDATE` requires locating the row by its primary key. In tables with composite keys, specify all key components for the target row; you cannot replace key predicates with `WHERE email = '...'` because `email` here is a regular column. Tables with `static` columns have partition-level update rules of their own, which do not apply to this example.

**When should you choose INSERT versus UPDATE?** `UPDATE ... SET` usually expresses a "modify a few fields" API more clearly, whereas `INSERT` can fit ingesting or upserting records. Requiring create-only or update-existing-only behavior is **not** determined by the statement keyword; those requirements must use appropriate conditions such as `IF NOT EXISTS` or `IF EXISTS`.

## 4. Clearly distinguishing the three states of a field

When implementing a PATCH endpoint, define three cases:

| Input | Request meaning | Write representation |
| --- | --- | --- |
| No `email` field | Do not change email | Omit `email` from CQL, or bind the marker as **UNSET** |
| Has `"email": "new@example.test"` | Change email | Write the new value for `email` |
| Has `"email": null` | Delete email (if the API contract permits) | Write **NULL** or `DELETE email`, creating a tombstone |

### Omit the column from the mutation

```sql
UPDATE demo.accounts_by_id
SET locale = 'en-US'
WHERE account_id = 11111111-1111-4111-8111-111111111111;
```

This statement **does not** touch `email`: Cassandra receives no mutation for the email cell from this statement.

### Assigning NULL is a delete operation

```sql
UPDATE demo.accounts_by_id
SET email = NULL
WHERE account_id = 11111111-1111-4111-8111-111111111111;

-- Explicit column deletion syntax:
DELETE email
FROM demo.accounts_by_id
WHERE account_id = 11111111-1111-4111-8111-111111111111;
```

Both examples express the intent to remove the existing value of the `email` column. Run **only one of the two** when practicing; there is no need to delete twice. CQL `NULL` on a regular column is not equivalent to "column omitted." Cassandra writes a deletion marker (*tombstone*) so replicas that missed the delete do not resurrect stale data.

Once the delete takes effect at the read consistency level, `SELECT email` returns `null`. Reading `null` does not tell you whether email **never had a value** or **was deleted**; both cases can surface as `null` in query results.

### UNSET in prepared statements

**UNSET** is used when binding parameters in a prepared statement, meaning **do not update the corresponding column**. It differs from `NULL`:

```text
email omitted from SET / marker is UNSET
    => mutation writes nothing to the email cell.

email bound to NULL
    => mutation writes a tombstone for the email cell.

email bound to a new string
    => mutation writes the new value to the email cell.
```

Do not bind `NULL` or `UNSET` to required primary key components; the primary key must be supplied with valid values to identify the row. If every updatable column is absent, the application should treat the request as a **no-op** and avoid executing an `UPDATE` with no meaningful assignments.

## 5. The specific pitfall of INSERT JSON

With column-list syntax, absent columns are skipped. However, when using `INSERT ... JSON`, you must explicitly define how **missing properties** are handled.

```sql
-- Keep columns absent from the JSON unchanged:
INSERT INTO demo.accounts_by_id JSON
'{"account_id":"11111111-1111-4111-8111-111111111111","locale":"ja-JP"}'
DEFAULT UNSET;
```

In CQL, `INSERT JSON` defaults to the **DEFAULT NULL** policy for missing properties unless `DEFAULT UNSET` is specified. The difference has major consequences for existing rows:

| Syntax | Column absent from JSON | Impact on existing row |
| --- | --- | --- |
| `INSERT ... JSON '...' DEFAULT UNSET` | Ignored | Keeps existing values of those columns |
| `INSERT ... JSON '...' DEFAULT NULL` | Treated as NULL | Can create tombstones and delete existing values |
| `INSERT ... JSON '...'` | Uses default DEFAULT NULL | Also risks deleting unsent columns |

For instance, a request intending only to update `locale` can accidentally delete `display_name`, `email`, and `phone` if using a JSON insert without `DEFAULT UNSET`. When designing partial-update APIs, prefer prepared `UPDATE` statements with selected columns or specify `DEFAULT UNSET` when appropriate. Never concatenate client-supplied JSON directly into a CQL statement.

## 6. Collections: omitting the column versus replacing an element

A collection column has two levels of choice: **whether to write the collection at all**, and if written, **whether to overwrite the entire collection or modify individual elements**. The sample table includes:

- `preferences map<text, text>`: configuration key/value pairs.
- `tags set<text>`: account tag set.

### Omitting the collection: the collection remains unchanged

```sql
UPDATE demo.accounts_by_id
SET phone = '0900000077'
WHERE account_id = 11111111-1111-4111-8111-111111111111;
```

The mutation does not write `preferences` or `tags`, so existing elements are not deleted.

### Assigning the entire collection: replaces that collection's contents

```sql
UPDATE demo.accounts_by_id
SET preferences = {'theme': 'dark'}
WHERE account_id = 11111111-1111-4111-8111-111111111111;
```

For a non-`frozen` `map`, assigning an entire new map replaces the old map contents: the `'digest': 'daily'` entry disappears simply because it is absent from the **new map value**. This is a critical distinction compared to **omitting the map column**.

### Updating a single map element

```sql
UPDATE demo.accounts_by_id
SET preferences['theme'] = 'dark'
WHERE account_id = 11111111-1111-4111-8111-111111111111;
```

This statement modifies only the `'theme'` entry of the map; the `'digest'` entry is not removed by this statement.

### Adding an element to a set

```sql
UPDATE demo.accounts_by_id
SET tags = tags + {'priority'}
WHERE account_id = 11111111-1111-4111-8111-111111111111;
```

This adds an element to a non-`frozen` set rather than reassigning all of `tags`. Conversely, `SET tags = {'priority'}` replaces the entire set of tags and can remove previous tags. Collection operations carry distinct semantics and write/delete costs and must be chosen based on business intent.

| Scenario | Expected outcome |
| --- | --- |
| `UPDATE ... SET phone = ...`, omitting `preferences` | Map keeps its old value |
| `SET preferences = {'theme': 'dark'}` | Replaces the entire map with the assigned value |
| `SET preferences['theme'] = 'dark'` | Updates only one map entry |
| `SET tags = tags + {'priority'}` | Adds an element to the set |
| `SET tags = {'priority'}` | Replaces the entire set with the assigned set |

For `frozen` collections, the value is generally treated as an atomic blob; not all element-level mutation operations available on non-`frozen` collections apply. Always verify the schema before using element-level updates.

## 7. Timestamps, TTL, and unsent data

To understand the exact impact of a mutation, separate three concepts:

1. **Column value:** the data observed on reads.
2. **Cell timestamp:** metadata Cassandra uses to reconcile competing write versions.
3. **Cell TTL:** remaining time before the value is considered expired.

### Unsent columns do not receive a new timestamp

Consider two consecutive statements:

```sql
UPDATE demo.accounts_by_id
SET display_name = 'Mai Anh Nguyen'
WHERE account_id = 11111111-1111-4111-8111-111111111111;

UPDATE demo.accounts_by_id
SET phone = '0900000066'
WHERE account_id = 11111111-1111-4111-8111-111111111111;
```

The second statement does not automatically "refresh the timestamp" of `display_name`. You can inspect write times at the cell level:

```sql
SELECT display_name,
       WRITETIME(display_name) AS name_written_at,
       phone,
       WRITETIME(phone) AS phone_written_at
FROM demo.accounts_by_id
WHERE account_id = 11111111-1111-4111-8111-111111111111;
```

`WRITETIME` returns the timestamp in microseconds since the Unix epoch for a written scalar value. This is not the business `updated_at` column and does not necessarily mirror the real-world order in which users issued requests if clock skew or custom timestamps are involved.

### TTL affects only the written values

```sql
UPDATE demo.accounts_by_id USING TTL 1800
SET phone = '0900000055'
WHERE account_id = 11111111-1111-4111-8111-111111111111;

SELECT phone, TTL(phone),
       display_name, TTL(display_name)
FROM demo.accounts_by_id
WHERE account_id = 11111111-1111-4111-8111-111111111111;
```

In a table without a default TTL:

- `phone` is written with a 1,800-second TTL; `TTL(phone)` shows the remaining time.
- `display_name` does not appear in the mutation, so it **does not receive a new TTL** from this statement.
- `TTL(display_name)` is typically `null` if the name value has no TTL.
- Once `phone`'s TTL expires, that column can read back as `null`, even while name and email remain.

If the table has `default_time_to_live` configured, columns written without an explicit TTL can inherit the default TTL. When overwriting a column that currently has a TTL, the new data takes the TTL characteristics of the **new write**. This differs from an omitted column: the old TTL of an omitted column continues counting down.

### Competing versions on the same column

If two clients write the same column:

```text
Client A: phone = '0900000002', timestamp = 2_000_000
Client B: phone = '0900000003', timestamp = 1_000_000

During reconciliation, A's value wins because its timestamp is higher,
even if B's request arrived later in wall-clock time.
```

Cassandra uses timestamp-based reconciliation for regular cells, often described as *last-write-wins*. Two clients writing **different columns** usually do not contend over the same cell; each column has its own write history. However, partial updates do not automatically form a compare-and-set transaction: if you require "change email only if the old value is still X," use a statement with an appropriate `IF` clause instead of reading first and running an unconditional `UPDATE`.

Example:

```sql
UPDATE demo.accounts_by_id
SET email = 'mai.new@example.test'
WHERE account_id = 11111111-1111-4111-8111-111111111111
IF email = 'mai@example.test';
```

This is a **lightweight transaction (LWT)**: the application must check the `[applied]` result. LWT requires more coordination than regular writes, making it appropriate when old-value conditions are a business constraint. `QUORUM` or `ONE` are read/write acknowledgment consistency levels across replicas, not a substitute for an `IF` condition.

## 8. Java Driver: implementing partial updates by field presence

In Java applications, the most common bug is turning a payload containing a single field into a mutation containing **many NULL columns**. The culprit is usually a nullable DTO: when deserializing JSON into an object, both "field absent" and "field present as null" end up represented as Java `null`.

For example, a client sends:

```json
{
  "phone": "0900000099"
}
```

If the backend binds `email = null` and `display_name = null` because those two fields are missing from the JSON, it will unintentionally delete unrelated data. You must track **presence** per field.

### Approach 1: CQL containing only the columns to modify

The application validates the list of allowed fields in the request, then selects the matching CQL statement:

```sql
UPDATE demo.accounts_by_id
SET phone = ?
WHERE account_id = ?;
```

This is a clean option when an endpoint has few column combinations or uses predefined prepared statements. Column names must come from an application-controlled allowlist; **never** take arbitrary column names from the client and concatenate them into CQL. Values must be bound.

### Approach 2: Fixed prepared statement and UNSET

With Apache Cassandra Java Driver 4.x, you can prepare a CQL statement with multiple markers while binding only the submitted fields. The example below assumes an existing `CqlSession session`, `UUID accountId`, and `JsonNode patch` (a Jackson JSON object):

```java
PreparedStatement ps = session.prepare(
    "UPDATE demo.accounts_by_id " +
    "SET display_name = :display_name, " +
    "    email = :email, " +
    "    phone = :phone " +
    "WHERE account_id = :account_id"
);

BoundStatementBuilder builder = ps.boundStatementBuilder()
    .setUuid("account_id", accountId)
    .unset("display_name")
    .unset("email")
    .unset("phone");

boolean changed = false;

if (patch.has("phone")) {
    JsonNode value = patch.get("phone");
    if (value.isNull()) {
        builder.setToNull("phone");
    } else if (value.isTextual()) {
        builder.setString("phone", value.textValue());
    } else {
        throw new IllegalArgumentException("phone must be a string or null");
    }
    changed = true;
}

if (patch.has("email")) {
    JsonNode value = patch.get("email");
    if (value.isNull()) {
        builder.setToNull("email");
    } else if (value.isTextual()) {
        builder.setString("email", value.textValue());
    } else {
        throw new IllegalArgumentException("email must be a string or null");
    }
    changed = true;
}

if (patch.has("display_name")) {
    JsonNode value = patch.get("display_name");
    if (value.isNull()) {
        builder.setToNull("display_name");
    } else if (value.isTextual()) {
        builder.setString("display_name", value.textValue());
    } else {
        throw new IllegalArgumentException("display_name must be a string or null");
    }
    changed = true;
}

if (changed) {
    session.execute(builder.build());
}
```

Required imports from the driver and Jackson are omitted to focus on patch-handling logic. In a real application, validate payload schema, reject disallowed fields, enforce length and format constraints, and check update permissions before executing.

Key takeaways of the snippet:

| JSON state | Check | Binder |
| --- | --- | --- |
| Key `email` absent | `patch.has("email") == false` | Keep `unset("email")` |
| Has `"email": null` | `value.isNull()` | `setToNull("email")` |
| Has `"email": "..."` | `value.isTextual()` | `setString("email", ...)` |

If the API **does not allow deleting email**, the JSON null case must be rejected during validation instead of calling `setToNull`. If the request contains no valid updatable fields, return a no-op response or validation error per the API contract, avoiding executing a mutation with no changes.

### Row existence and retries on network errors

An unconditional `UPDATE` can create a new row containing only the updated columns if the key does not exist yet. If the requirement is to modify only an existing account, use `UPDATE ... IF EXISTS` and read `[applied]`, or apply an appropriate existence-control mechanism at the business layer. `SELECT` followed by an unconditional `UPDATE` leaves a race window.

When a write times out, you cannot know for sure that the mutation failed completely: some replicas may already have received the data. Retrying an update with the same key and values is generally easier to reason about than additive operations, yet timestamps, TTL, LWT, and concurrent writes can still affect the final outcome. The application must define its retry policy based on business semantics.

## 9. Hands-on lab: predicting column-by-column changes

To keep results independent of earlier examples, use a different UUID and run only in a practice environment.

**Step 1 — Create the initial row**

```sql
INSERT INTO demo.accounts_by_id (
    account_id, display_name, email, phone, locale,
    preferences, tags
)
VALUES (
    55555555-5555-4555-8555-555555555555,
    'Huy',
    'huy@example.test',
    '0911111111',
    'vi-VN',
    {'theme': 'light', 'digest': 'weekly'},
    {'standard'}
);

SELECT display_name, email, phone, locale, preferences, tags
FROM demo.accounts_by_id
WHERE account_id = 55555555-5555-4555-8555-555555555555;
```

**Step 2 — Change only phone**

```sql
UPDATE demo.accounts_by_id
SET phone = '0922222222'
WHERE account_id = 55555555-5555-4555-8555-555555555555;
```

Expected: `phone` changes, `email` remains `'huy@example.test'`, and `preferences` still contains both `theme` and `digest`.

**Step 3 — Modify only a map entry**

```sql
UPDATE demo.accounts_by_id
SET preferences['theme'] = 'dark'
WHERE account_id = 55555555-5555-4555-8555-555555555555;
```

Expected: `preferences` becomes `{'theme': 'dark', 'digest': 'weekly'}`. Replacing this with `SET preferences = {'theme': 'dark'}` would remove `digest`.

**Step 4 — Delete a column**

```sql
UPDATE demo.accounts_by_id
SET email = NULL
WHERE account_id = 55555555-5555-4555-8555-555555555555;

SELECT email, display_name, phone, preferences
FROM demo.accounts_by_id
WHERE account_id = 55555555-5555-4555-8555-555555555555;
```

Expected: `email` reads as `null`; name, phone, and map retain their values from the previous step.

**Step 5 — INSERT JSON without losing unsent columns**

```sql
INSERT INTO demo.accounts_by_id JSON
'{"account_id":"55555555-5555-4555-8555-555555555555","locale":"en-US"}'
DEFAULT UNSET;
```

Expected: `locale` changes to `'en-US'`, and other columns are not rewritten by this statement. Inspect the row again with `SELECT` to verify.

### Summary table of expected results

| After step | `email` | `phone` | `locale` | `preferences['theme']` | `preferences['digest']` |
| --- | --- | --- | --- | --- | --- |
| 1 | huy@example.test | 0911111111 | vi-VN | light | weekly |
| 2 | huy@example.test | 0922222222 | vi-VN | light | weekly |
| 3 | huy@example.test | 0922222222 | vi-VN | dark | weekly |
| 4 | null | 0922222222 | vi-VN | dark | weekly |
| 5 | null | 0922222222 | en-US | dark | weekly |

These expectations assume no concurrent writes, TTLs, or special timestamps. Use this example to practice predicting **which columns are affected** before observing via CQL.

## 10. Common mistakes and how to avoid them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Binding Java `null` for every missing field in PATCH | Deletes unintended columns in bulk and generates tombstones | Track field presence; use `UNSET` or omit columns from CQL |
| Using `INSERT JSON` and forgetting `DEFAULT UNSET` | Properties missing from JSON may be treated as NULL | Specify `DEFAULT UNSET` explicitly or use prepared `UPDATE` |
| Assigning an entire map/set when changing only one element | Other elements get removed | Use the appropriate element/collection update syntax |
| Assuming `updated_at` changes automatically when other columns change | Business audit trail becomes inaccurate | Write `updated_at` explicitly when needed |
| Assuming `UPDATE` only modifies existing rows | Can create sparse rows at non-existent keys | Use `IF EXISTS` when existence must be enforced |
| Assuming unsent columns will never change | TTL or other clients can still alter data | Account for consistency levels and contention rules |
| Reading first then updating unconditionally to "prevent overwrites" | Race condition between read and write | Use LWT/`IF` when old-value checks are required |
| Concatenating arbitrary column names from payload into CQL | Can produce invalid or unsafe CQL statements | Accept column names only from an allowlist; bind values |

### Self-check questions

1. A row already has `email` and `phone`. If you run `UPDATE ... SET phone = 'x'`, is email deleted? **No**, that mutation itself does not write email.
2. A client omits the email field from a JSON PATCH. Should the backend bind email to NULL? **No**; keep it unchanged using UNSET or omit email from the CQL statement.
3. A client sends `"email": null`, and the API permits deletion. How does Cassandra handle it? **Writes a tombstone** for email; reads typically see `null` once the deletion is observed.
4. Does `SET preferences = {'theme': 'dark'}` preserve the old `digest`? **No**; that reassigns the map. Use `preferences['theme'] = 'dark'` if you only want to change one entry.
5. Does an update to phone automatically extend the TTL of display_name? **No**; unwritten columns do not receive a new TTL from this mutation.
6. If you must ensure an account exists before updating, which syntax is appropriate? **`UPDATE ... IF EXISTS`**, then inspect `[applied]`.

## 11. Design principles for Java applications

Align the meaning of "partial update" from the API down to the database:

1. **Identify the full primary key** from query-driven table design; do not update rows based on arbitrary regular columns.
2. **Write only the columns that need changing**; unsent columns are a no-op, not converted to NULL by default.
3. **Clearly distinguish missing from explicit null** in JSON, DTOs, and prepared statements.
4. **Understand collection boundaries**: omitting the column, replacing the whole collection, and editing a single element are three distinct operations.
5. **Manage auxiliary business fields yourself** such as `updated_at`; Cassandra does not automatically touch the entire row whenever one cell changes.
6. **Consider TTL, tombstones, compaction, and repair** if columns are frequently deleted or rewritten: those are the physical costs of logical design.
7. **Choose consistency levels and write conditions** according to business needs; replication and consistency coordinate distributed data, while `IF` protects contested conditions.

**Takeaway:** In Cassandra, **only the columns written in a mutation are directly affected by that write**. Omitted columns and the UNSET marker mean "do not change"; NULL means "delete value"; and assigning an entire collection can remove elements absent from the new value. Mastering these boundaries enables building safe PATCH APIs, preventing data loss, and reducing unnecessary tombstones.
