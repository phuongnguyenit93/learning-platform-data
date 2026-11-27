# Partial JSON Updates and Storage / Binary Log Optimization Conditions

MySQL stores values in a `JSON` column using a syntax-validated internal binary format rather than keeping raw JSON strings like an ordinary text column. When modifying only a few paths in a large JSON document, resending and rewriting the entire document can consume significant CPU, I/O, undo/redo, and binary log space. MySQL can optimize certain updates by modifying only the necessary portion of the JSON document in the storage engine and, when configured, logging only that diff into the binary log.

This optimization does not automatically apply to every UPDATE statement involving a JSON column. Expression structure, the function used, the size of the new value, free space inside the binary representation, binary log format, and server configuration all affect it. This lesson focuses on `JSON_SET()`, `JSON_REPLACE()`, `JSON_REMOVE()`, measuring with `JSON_STORAGE_SIZE()`/`JSON_STORAGE_FREE()`, and enabling `PARTIAL_JSON` for row-based binary logging.

This lesson belongs to the `DATABASE_MYSQL` module, where you master table design, data types, keys, SQL queries, indexes, transactions, concurrency control, execution plan reading, query tuning, and relational database operations. The goal is to update with accurate semantics, preserve safety under concurrent transactions, and know how to verify storage/binary log gains rather than assuming every JSON update is partial.

After this lesson, you will be able to:

- Explain the difference between JSON binary storage and plain JSON text strings.
- Choose `JSON_SET`, `JSON_REPLACE`, or `JSON_REMOVE` according to update semantics.
- Write UPDATE statements giving MySQL the opportunity to perform in-place partial updates.
- State the conditions and cases that force MySQL to rewrite the entire JSON document.
- Measure storage size with `JSON_STORAGE_SIZE()` and free space with `JSON_STORAGE_FREE()`.
- Distinguish storage-engine partial-update optimization from partial JSON in the binary log.
- Enable and verify `binlog_row_value_options=PARTIAL_JSON` in row-based logging.
- Understand the distinct roles of `binlog_format`, `binlog_row_image`, and `binlog_row_value_options`.
- Design JSON updates safe against lost updates, concurrency hazards, and replication issues.

## 1. Preparing the Practice Table

Create a table storing customer profiles with a JSON column:

```sql
DROP TABLE IF EXISTS customer_profile;

CREATE TABLE customer_profile (
    customer_id BIGINT UNSIGNED NOT NULL,
    profile JSON NOT NULL,
    version_no BIGINT UNSIGNED NOT NULL DEFAULT 1,
    updated_at TIMESTAMP(6) NOT NULL
        DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (customer_id)
) ENGINE = InnoDB;

INSERT INTO customer_profile (customer_id, profile)
VALUES
(101, JSON_OBJECT(
    'name', 'An',
    'preferences', JSON_OBJECT(
        'theme', 'light',
        'language', 'vi',
        'notifications', TRUE
    ),
    'usage', JSON_OBJECT('login_count', 0),
    'tags', JSON_ARRAY('new', 'newsletter'),
    'address', JSON_OBJECT(
        'city', 'Ho Chi Minh City',
        'district', 'District 1'
    )
)),
(102, JSON_OBJECT(
    'name', 'Binh',
    'preferences', JSON_OBJECT(
        'theme', 'dark',
        'language', 'en',
        'notifications', FALSE
    ),
    'usage', JSON_OBJECT('login_count', 0),
    'tags', JSON_ARRAY('returning'),
    'address', JSON_OBJECT(
        'city', 'Da Nang',
        'district', 'Hai Chau'
    )
));
```

Inspect the documents:

```sql
SELECT
    customer_id,
    JSON_PRETTY(profile) AS profile,
    version_no,
    updated_at
FROM customer_profile
ORDER BY customer_id;
```

The `profile` column has type JSON. MySQL validates JSON on write and stores it in binary JSON format to support path-based access. Binary JSON is not a plain text string that can be safely edited via string concatenation.

## 2. Three Key Update Functions

The three functions commonly used for partial updates are `JSON_SET()`, `JSON_REPLACE()`, and `JSON_REMOVE()`.

| Function | Behavior | When Path Does Not Exist |
| --- | --- | --- |
| `JSON_SET(doc, path, value, ...)` | Inserts or replaces the value at path | Creates the element at path if structure permits |
| `JSON_REPLACE(doc, path, value, ...)` | Replaces only existing values | Does not insert a new element |
| `JSON_REMOVE(doc, path, ...)` | Removes the element at path | Leaves unchanged if path does not exist |

### 2.1. JSON_SET: Insert or Replace

Change customer 101's theme:

```sql
UPDATE customer_profile
SET profile = JSON_SET(
    profile,
    '$.preferences.theme', 'dark'
)
WHERE customer_id = 101;
```

If `$.preferences.theme` already exists, the value is replaced with the JSON string `"dark"`. If the path does not exist yet and the parent path is valid, `JSON_SET()` can insert the new element.

A single call can update multiple paths:

```sql
UPDATE customer_profile
SET profile = JSON_SET(
    profile,
    '$.preferences.theme', 'dark',
    '$.preferences.notifications', FALSE,
    '$.last_updated_by', 'profile-service'
)
WHERE customer_id = 101;
```

Combining changes to the same document into one UPDATE avoids multiple reads/writes and keeps edits within a single statement.

### 2.2. JSON_REPLACE: Modify Only Existing Paths

```sql
UPDATE customer_profile
SET profile = JSON_REPLACE(
    profile,
    '$.preferences.language', 'ja'
)
WHERE customer_id = 101;
```

If the path does not exist, `JSON_REPLACE()` does not create it. Use this function when the data contract requires updating only existing properties; if new properties must be added, use `JSON_SET()`.

### 2.3. JSON_REMOVE: Remove a Path

```sql
UPDATE customer_profile
SET profile = JSON_REMOVE(
    profile,
    '$.address.district'
)
WHERE customer_id = 101;
```

`JSON_REMOVE()` deletes the specified property. When removing a property, use this function rather than assigning SQL `NULL`.

### 2.4. SQL NULL and JSON null Are Not the Same

An SQL `NULL` value passed to `JSON_SET()` becomes a JSON null value at the path, not a command to delete the path:

```sql
UPDATE customer_profile
SET profile = JSON_SET(profile, '$.middle_name', NULL)
WHERE customer_id = 101;
```

The result contains:

```json
{"middle_name": null}
```

If you want to delete the `middle_name` property, use:

```sql
UPDATE customer_profile
SET profile = JSON_REMOVE(profile, '$.middle_name')
WHERE customer_id = 101;
```

Clearly define your application contract: a missing property, JSON null, and SQL NULL can carry different business meanings.

## 3. Writing UPDATEs for Partial-Update Eligibility

Basic pattern:

```sql
UPDATE customer_profile
SET profile = JSON_SET(profile, '$.preferences.theme', 'dark')
WHERE customer_id = 101;
```

The key point is that the JSON expression is applied directly to the JSON column and the result is assigned back to that same column in UPDATE. MySQL can recognize the transformation and update only the required portion in binary JSON instead of serializing and rewriting the entire document.

The example below typically does not give a similar opportunity for partial update:

```sql
-- Application reads the whole document, edits the string, and writes back the complete document
UPDATE customer_profile
SET profile = '{"name":"An","preferences":{"theme":"dark"}}'
WHERE customer_id = 101;
```

This is a full-document replacement. Any properties absent from the new string disappear. It also risks overwriting changes made by another transaction to a different path after the application's read.

### 3.1. General Conditions for Storage Partial Updates

MySQL can apply partial-update optimization only when the statement structure and document satisfy engine conditions. Conditions to verify include:

1. The updated target is a column of type `JSON` in the table.
2. The UPDATE statement uses `JSON_SET()`, `JSON_REPLACE()`, or `JSON_REMOVE()` to produce the new value for the JSON column.
3. The JSON column being updated is passed directly as the input document to the update function and the result is assigned back to that same column.
4. Every change must replace the value of an existing object/array element; no new elements may be added to a parent object or array. Thus, `JSON_SET()` adding a new key is ineligible for partial storage update, even if the document has free space.
5. The replacement value must be no larger than the old value. Exception: if a prior partial update left enough free space, a new value larger than the old value may still be written in place by reusing that free space.
6. All paths and values must be valid under MySQL's JSON path and data-type rules.

Multiple JSON columns can be updated in the same UPDATE; MySQL evaluates each column independently and partially updates only those updated with supported functions. `JSON_SET()`, `JSON_REPLACE()`, and `JSON_REMOVE()` can be nested in various combinations, provided the input column and target column remain the same column.

These conditions create the opportunity for optimization; they are not a guarantee that every superficially qualifying statement will execute partially. If the new value requires unavailable space, the structure changes too much, or the statement is not of a supported form, MySQL may rewrite the entire document.

### 3.2. Replacing with a Value Larger Than the Old Value

Example replacing a short string with a substantially longer string:

```sql
UPDATE customer_profile
SET profile = JSON_REPLACE(
    profile,
    '$.preferences.theme',
    'a-much-longer-preference-value-than-before'
)
WHERE customer_id = 101;
```

If existing binary space and retained free space are insufficient, MySQL must perform a full JSON document update in the storage engine. If the document already had free space from an earlier smaller update, replacing an existing path with a larger value may still reuse that free space. Even if the storage engine must rewrite the whole document, the row-based binary log can still record a JSON diff if partial binary logging conditions are met and `PARTIAL_JSON` is enabled. Do not judge based on string length alone; measure on real data.

### 3.3. Adding a New Path

`JSON_SET()` can add a new path:

```sql
UPDATE customer_profile
SET profile = JSON_SET(profile, '$.marketing.source', 'campaign-2026')
WHERE customer_id = 101;
```

Adding a property changes document structure. Adding a new element to an object/array does not meet partial storage update conditions, even if binary JSON has free space; the storage engine must rewrite the document. However, if general conditions regarding the JSON column, update function, and matching input/target column are satisfied, the row-based binary log can still represent this change as a JSON diff when `PARTIAL_JSON` is enabled. This clearly demonstrates that partial storage updates and partial binary logging are two separate optimizations.

### 3.4. Patterns That Typically Forfeit Optimization

- Reading JSON into the application, editing the entire object, and sending back a new JSON string.
- Assigning the result to a different column or merely SELECTing the result without updating the JSON column itself.
- Using document-building/aggregating functions outside the supported partial-update group.
- Manually concatenating JSON strings with `CONCAT()`.
- Replacing the entire JSON column with a new document inside UPDATE.

If you need to modify a few paths, use JSON functions directly inside UPDATE on the server. If business logic requires replacing the whole document, do so intentionally with an appropriate concurrency mechanism.

## 4. Measuring JSON Storage Size

MySQL provides two useful functions to inspect the size and free space of a JSON column:

- `JSON_STORAGE_SIZE(json_val)`: number of bytes used by the binary JSON representation. For a JSON column, the value reflects the document size when stored in full, prior to subsequent partial updates.
- `JSON_STORAGE_FREE(json_val)`: number of bytes freed inside the JSON column representation by previous partial updates. For JSON expressions other than a stored JSON column, the function returns 0.

Check before/after an update:

```sql
SELECT
    customer_id,
    JSON_STORAGE_SIZE(profile) AS storage_bytes,
    JSON_STORAGE_FREE(profile) AS free_bytes
FROM customer_profile
WHERE customer_id = 101;
```

To observe free space, use a document with a sufficiently long property and replace it with a shorter value:

```sql
UPDATE customer_profile
SET profile = JSON_SET(
    profile,
    '$.address.district',
    'D1'
)
WHERE customer_id = 102;

SELECT
    JSON_STORAGE_SIZE(profile) AS storage_bytes,
    JSON_STORAGE_FREE(profile) AS free_bytes
FROM customer_profile
WHERE customer_id = 102;
```

If a path is replaced with smaller content and MySQL performs a partial update, `JSON_STORAGE_FREE()` can become greater than 0. This free space resides inside the document's binary JSON area, not free space in the tablespace or filesystem.

### 4.1. Interpreting the Two Measurement Functions Correctly

| Observation | Interpretation |
| --- | --- |
| `JSON_STORAGE_SIZE()` is larger than `LENGTH(profile)` | Normal: binary JSON has headers, offsets, and its own encoding; cannot compare directly as two identically formatted strings |
| `JSON_STORAGE_FREE()` increases after replacing a value with a shorter one | Space inside the document was freed by a partial update |
| `JSON_STORAGE_FREE()` equals 0 | Does not prove partial update did not happen; same-size replacements may leave zero free space |
| `JSON_STORAGE_FREE()` decreases after the next update | Previously freed space may have been reused |
| `JSON_STORAGE_FREE()` equals 0 after replacing the entire document | Consistent with full replacement producing a fresh binary JSON |

`JSON_STORAGE_SIZE()` is not the exact number of bytes guaranteed to be written to disk during every UPDATE. It describes binary JSON size per the function's semantics. To assess I/O, redo, undo, and latency, combine benchmarks, Performance Schema, and storage engine metrics.

### 4.2. Standalone Experiment with a Larger Document

Create a lab table:

```sql
DROP TABLE IF EXISTS json_partial_lab;

CREATE TABLE json_partial_lab (
    id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    doc JSON NOT NULL
) ENGINE = InnoDB;

INSERT INTO json_partial_lab (id, doc)
VALUES (
    1,
    JSON_OBJECT(
        'description', REPEAT('x', 200),
        'status', 'ACTIVE',
        'counter', 0
    )
);

SELECT
    JSON_STORAGE_SIZE(doc) AS storage_bytes,
    JSON_STORAGE_FREE(doc) AS free_bytes
FROM json_partial_lab
WHERE id = 1;
```

Replace `description` with a short string:

```sql
UPDATE json_partial_lab
SET doc = JSON_REPLACE(doc, '$.description', 'short')
WHERE id = 1;

SELECT
    JSON_STORAGE_SIZE(doc) AS storage_bytes,
    JSON_STORAGE_FREE(doc) AS free_bytes
FROM json_partial_lab
WHERE id = 1;
```

Next, try replacing an existing path's value with one that is larger than before yet still smaller than or equal to the available free space; observe `JSON_STORAGE_FREE()` decrease as free space is reused. Try adding a new path separately to see that adding does not perform a partial storage update. Exact numbers depend on version, binary JSON layout, and data strings. Never use a fixed free-bytes number as a universal pass/fail criterion across all environments.

## 5. Binary Log and Partial JSON

Partial updates in the storage engine and partial JSON in the binary log are two related yet independent optimizations:

- **Storage partial update:** MySQL can modify only the required portion of binary JSON in the column instead of rewriting the whole document.
- **Binary log partial update:** with row-based logging, MySQL can record only the changed portion of the JSON column in the row event rather than logging the entire new JSON value.

An UPDATE statement may be optimized at the storage engine while the binary log still records according to full-value configuration. To reduce JSON data written to the row-based binary log, enable the `PARTIAL_JSON` option.

### 5.1. Checking Related Variables

```sql
SELECT
    @@global.binlog_format AS global_binlog_format,
    @@session.binlog_format AS session_binlog_format,
    @@global.binlog_row_image AS global_row_image,
    @@session.binlog_row_image AS session_row_image,
    @@global.binlog_row_value_options AS global_row_value_options,
    @@session.binlog_row_value_options AS session_row_value_options;
```

Each variable has a distinct role:

| Variable | Controls |
| --- | --- |
| `binlog_format` | How changes are logged: STATEMENT, ROW, or MIXED |
| `binlog_row_image` | Which columns are logged in row events: FULL, MINIMAL, or NOBLOB |
| `binlog_row_value_options` | How certain values are represented in row events; `PARTIAL_JSON` enables logging partial JSON updates |

`PARTIAL_JSON` does not automatically switch `binlog_format` to ROW and does not replace `binlog_row_image`. This optimization applies to row-based binary logging.

### 5.2. Enabling PARTIAL_JSON for a Test Session

On a MySQL version supporting this option, configure the session running the UPDATE:

```sql
SET SESSION binlog_row_value_options = 'PARTIAL_JSON';

SELECT
    @@session.binlog_format,
    @@session.binlog_row_value_options;
```

Testing requires row-based logging:

```sql
SET SESSION binlog_format = 'ROW';
```

Changing `binlog_format` has restrictions based on transaction state and routine context; set it before starting a transaction. In production, DBAs manage global settings and replication policies rather than letting individual requests arbitrarily switch formats.

If it should apply to new connections, a DBA can set the global option:

```sql
SET GLOBAL binlog_row_value_options = 'PARTIAL_JSON';
```

Session variables on already-open connections do not automatically change when global variables change. Check `@@session.binlog_row_value_options` on the actual connection executing UPDATE. Changing global settings may require administrative privileges and must be controlled via deployment configuration.

### 5.3. Conditions and Scope of Partial Binary Logging

- Binary logging must be enabled.
- Changes must be logged in row-based format to use partial JSON row values.
- `binlog_row_value_options` on the session executing DML must contain `PARTIAL_JSON`.
- The JSON column must be the same input and target column of one of the supported update functions. Adding new elements or replacing with larger values may force the storage engine into a full update, yet does not necessarily prevent the binary log from generating a JSON diff.
- Servers in the replication chain must support the emitted row event format. Check versions and compatibility before enabling across multi-version topologies.

`binlog_row_image` still decides which columns are included in row events. `PARTIAL_JSON` controls how the modified portion of a JSON value is represented when a row event is generated. The two settings complement rather than replace each other. Unlike partial storage updates, partial binary logging does not require the last two storage-optimization conditions: adding no new elements and new value not exceeding old value. Therefore, a full update in the storage engine can still be logged as partial JSON in the binary log.

### 5.4. Operational Benefits

For large JSON documents where each UPDATE modifies a small path, partial binary logging can reduce:

- Row event size in the binary log.
- Relay log size and network volume transferred to replicas.
- Amount of JSON data that must be decoded/applied on replicas.
- Storage and I/O impact associated with writing entire JSON values in row events.

Actual reduction depends on document size, change size, updated row count, row image, and other columns in the row event. Do not infer savings merely from enabling the variable; inspect actual binlogs and measure the workload.

## 6. Inspecting Binary Logs in a Lab

In a test environment with binary logging and appropriate privileges:

1. Verify `binlog_format=ROW` on the session.
2. Verify `binlog_row_value_options` includes `PARTIAL_JSON`.
3. Record the binary log position before UPDATE.
4. Run a small UPDATE using JSON_SET/REPLACE/REMOVE.
5. Record the position after UPDATE.
6. Use `mysqlbinlog` with row-event decoding mode to inspect the logged change.
7. Compare against a full-document replacement.

Basic inspection statements:

```sql
SHOW MASTER STATUS;
SHOW BINARY LOGS;
```

On MySQL 8.4, `SHOW BINARY LOG STATUS` is the preferred newer command name for binary log status; use syntax matching your running server version. Reading binlog files is typically performed via the `mysqlbinlog` utility on a host with file access.

Example terminal command:

```bash
mysqlbinlog --base64-output=DECODE-ROWS -vv binlog.000123
```

Verbose output lets you inspect row events and logged payloads. Exact partial JSON display format depends on tool and server versions; do not conclude an event is not partial merely because output is harder to read than plain JSON text. Comparing event sizes or verifying on a replica provides additional evidence.

Do not toggle binary logging or alter production configuration solely for lab exercises. Use an isolated instance with synthetic data and appropriate binary log retention.

## 7. Safe JSON Updates Under Concurrent Transactions

A major advantage of server-side updates is avoiding full-document read-modify-write loops in the application.

### 7.1. Avoiding Lost Updates When Applications Rewrite Whole Documents

Suppose two requests read the same initial document version:

- Request A changes `$.preferences.theme`.
- Request B changes `$.preferences.language`.

If both edit a copy in the application and write back the entire JSON, the later write can erase the earlier write's change because it sends an old document lacking the updated path.

Instead, each request updates its path directly:

```sql
UPDATE customer_profile
SET profile = JSON_SET(profile, '$.preferences.theme', 'dark')
WHERE customer_id = 101;

UPDATE customer_profile
SET profile = JSON_SET(profile, '$.preferences.language', 'ja')
WHERE customer_id = 101;
```

InnoDB locks the row and applies each UPDATE to the current column value in transaction execution order. Updates to different paths can both be preserved instead of the later request overwriting with an outdated full document.

### 7.2. Updating the Same Path Still Requires Business Rules

If two requests set `$.preferences.theme` to different values, the final outcome depends on commit/write order. Partial updates do not resolve business conflicts. When conflict detection is required, use a version column and optimistic locking:

```sql
UPDATE customer_profile
SET
    profile = JSON_SET(profile, '$.preferences.theme', 'dark'),
    version_no = version_no + 1
WHERE customer_id = 101
  AND version_no = 7;
```

The application checks affected rows. If 0, the version changed or the row no longer exists; re-read and decide whether to retry/merge per business rules.

### 7.3. Atomic Numeric Mutations

If you need to increment a counter stored inside JSON, compute it from the current value inside the same UPDATE:

```sql
UPDATE customer_profile
SET profile = JSON_SET(
    profile,
    '$.usage.login_count',
    COALESCE(
        CAST(
            JSON_UNQUOTE(JSON_EXTRACT(profile, '$.usage.login_count'))
            AS UNSIGNED
        ),
        0
    ) + 1
)
WHERE customer_id = 101;
```

This snippet assumes the path holds a numeric value or does not exist yet. If data could contain strings, objects, arrays, or negative numbers, validate `JSON_TYPE` and handle per business schema before CASTing. A separate numeric column is usually better if the counter is updated frequently, used in filter predicates, or needs an index.

## 8. JSON Paths, Indexes, and Remaining Costs

Partial updates reduce JSON document write work in supported cases; they do not make all JSON-related operations free.

- `WHERE` conditions still need a suitable access path. Use a primary key or an index on an identifier column to avoid full table scans.
- If queries frequently filter by a JSON property, consider a generated column and an index on that generated column.
- If a partial update modifies a path used in an indexed generated column, MySQL must still maintain the corresponding index.
- If a document has many independently updated high-frequency paths, consider normalizing hot attributes into relational columns.
- Do not use JSON for data with frequent relationships, constraints, joins, or aggregations if a relational structure is clearer.

Example indexing a `theme` property:

```sql
ALTER TABLE customer_profile
ADD COLUMN theme VARCHAR(20)
    GENERATED ALWAYS AS (
        JSON_UNQUOTE(JSON_EXTRACT(profile, '$.preferences.theme'))
    ) STORED,
ADD INDEX idx_customer_profile_theme (theme);
```

Query:

```sql
SELECT customer_id
FROM customer_profile
WHERE theme = 'dark';
```

The index helps queries filter by `theme`. It does not replace `JSON_SET()` when updating the document, nor does it eliminate index maintenance cost when `theme` changes.

## 9. When Not to Force Partial Updates

- Changing most of the document or restructuring the JSON schema: replacing the full document may be clearer and more appropriate.
- Application must validate the entire object via schema/version before writing: use validation and optimistic locking, then replace the document in a controlled manner.
- Very small documents: I/O savings may be negligible compared to added complexity.
- Paths updated constantly while also needing filtering/joins/aggregation: extracting into relational columns may fit better.
- Updates modifying many interdependent paths: combine into one JSON_SET/REPLACE if semantics are clear, or construct a fresh document explicitly.

Optimization is not an independent goal. Prioritize accurate semantics, consistency, and operability; optimize for partial updates only when measurements show real benefit.

## 10. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Sending a new JSON string to change one path | Rewrites the full document and risks losing other properties | Use JSON_SET/REPLACE/REMOVE directly on the column |
| Using JSON_REPLACE to add a property | Missing path is not created | Use JSON_SET when adding is needed |
| Assigning SQL NULL to delete a path | Sets JSON null instead of removing the property | Use JSON_REMOVE |
| Assuming JSON_SET is always partial | MySQL may perform a full update if space/conditions fail | Measure JSON_STORAGE_FREE and check binlog |
| Assuming JSON_STORAGE_FREE = 0 proves full update | Same-size replacements leave zero free space | Interpret both storage functions accurately |
| Assuming PARTIAL_JSON enables ROW logging automatically | Binary log still depends on binlog_format | Verify format and option on the same session |
| Confusing binlog_row_image with PARTIAL_JSON | Misconfigured target setting | Understand row image and JSON value representation are separate options |
| Checking only global variables | Current session may still use old values | Check `@@session` on the connection running UPDATE |
| Ignoring replica versions | Replicas may not support emitted row events | Verify compatibility across the entire replication chain |
| Read-modify-write full documents in the app | Lost updates between requests | Update paths server-side or use version checks |
| Assuming partial updates eliminate index cost | Generated/secondary indexes must still be maintained | Measure both write path and index maintenance |

## 11. Workflow for Verifying Optimizations

1. Select a representative JSON document in terms of size and structure.
2. Record MySQL version, storage engine, `binlog_format`, `binlog_row_image`, and `binlog_row_value_options`.
3. Run an UPDATE replacing a path with a shorter value using JSON_SET/REPLACE.
4. Measure `JSON_STORAGE_SIZE()` and `JSON_STORAGE_FREE()` before and after.
5. Run an UPDATE replacing a path with a larger value and observe when a full update occurs.
6. Run a full-document replacement as a comparison baseline.
7. If evaluating binary logs, enable ROW and PARTIAL_JSON in a lab and inspect row events.
8. Measure latency, binlog bytes, redo/undo, replica apply lag, and server resources under a sufficiently large repeated workload.
9. Test concurrency: two sessions updating two different paths and the same path.
10. Verify the final JSON result is accurate and no properties were unintentionally lost.

Do not draw conclusions from a single run on a small table. Use representative data, multiple iterations, equivalent cache state, and identical replication conditions.

## 12. Deployment Checklist

- [ ] Column has type JSON and valid documents.
- [ ] Chosen JSON_SET, JSON_REPLACE, or JSON_REMOVE accurately per semantics.
- [ ] Directly updating the JSON column inside UPDATE.
- [ ] Sufficiently selective WHERE clause, typically using a key/index.
- [ ] Not serializing and rewriting the whole document when only one path needs editing.
- [ ] Understand partial storage update triggers and full-update fallback cases.
- [ ] Measured JSON_STORAGE_SIZE and JSON_STORAGE_FREE with proper semantics.
- [ ] Separated storage partial updates from partial JSON in the binary log.
- [ ] If partial row logging is needed, verified ROW and PARTIAL_JSON on the writing session.
- [ ] Checked `binlog_row_image` and not confused it with `binlog_row_value_options`.
- [ ] Verified version compatibility across all replicas/downstream servers.
- [ ] Have a concurrency strategy: server-side path updates, version checks, or locks.
- [ ] Evaluated indexes/generated columns and index maintenance overhead.
- [ ] Benchmarked and monitored binlog size, latency, replica lag, and I/O.
- [ ] Have a configuration and migration rollback plan if gains fall short of expectations.

## 13. Practice Exercises

1. Create table `json_partial_lab` and insert a document containing a long string.
2. Change a path using JSON_SET with a shorter value; measure JSON_STORAGE_FREE.
3. Change an existing path using JSON_REPLACE; verify non-existent paths are not created.
4. Add a new path using JSON_SET and compare sizes before and after.
5. Delete a path using JSON_REMOVE; inspect the document and free space.
6. Pass SQL NULL into JSON_SET and compare against JSON_REMOVE.
7. Replace the entire document and check JSON_STORAGE_FREE after full replacement.
8. Run two sessions updating two different paths with JSON_SET; verify both changes are retained.
9. Run two sessions updating the same path; describe the conflict policy and final outcome.
10. Enable ROW and PARTIAL_JSON in a lab; compare row events of a partial update against full replacement.
11. Switch `binlog_row_image` between FULL and MINIMAL in a test environment; explain why it is not synonymous with PARTIAL_JSON.
12. Add a generated column/index on a path; update that path and evaluate index maintenance overhead.
13. Write a benchmark report including MySQL version, configuration variables, document size, free bytes, binlog bytes, latency, and replica lag.

## 14. Completion Criteria

You have completed this lesson when you can choose the right JSON function according to semantics, write UPDATEs directly on the column to enable partial storage update eligibility, explain why MySQL may still need to rewrite the whole document, measure size and free space, configure partial JSON row logging properly, distinguish the three related binlog variables, and ensure updates do not lose concurrent changes. You should also back claims with benchmark evidence rather than asserting partial updates are always faster.

## References

- [MySQL 8.4 Reference Manual — Partial Updates of JSON Values](https://dev.mysql.com/doc/refman/8.4/en/json.html#json-partial-updates)
- [MySQL 8.4 Reference Manual — JSON Utility Functions](https://dev.mysql.com/doc/refman/8.4/en/json-utility-functions.html)
- [MySQL 8.4 Reference Manual — The Binary Log](https://dev.mysql.com/doc/refman/8.4/en/binary-log.html)
- [MySQL 8.4 Reference Manual — System Variables: binlog_row_value_options](https://dev.mysql.com/doc/refman/8.4/en/replication-options-binary-log.html#sysvar_binlog_row_value_options)
- [MySQL 8.4 Reference Manual — Row-Based Replication](https://dev.mysql.com/doc/refman/8.4/en/replication-formats.html)
