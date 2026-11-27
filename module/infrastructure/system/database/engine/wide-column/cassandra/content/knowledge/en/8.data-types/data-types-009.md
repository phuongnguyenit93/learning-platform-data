# NULL, Unset Values, and Driver UNSET in Apache Cassandra

In Apache Cassandra, the three situations **"never stored a value,"** **"explicitly deleted a value with NULL,"** and **"omitted a field with UNSET"** can produce identical-looking `SELECT` results, yet **they do not have the same effect on data or performance**. If a Java application handles a PATCH request and turns every omitted field into `null`, it can unintentionally erase existing data, generate excessive **tombstones**, and degrade query latency or cause issues when replicas are out of sync.

This lesson belongs to the **Data Types** chapter of the **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA** module. In distributed Cassandra, the partition key governs data placement, queries are designed per table, and read/write consistency levels govern replica acknowledgments. Understanding `NULL` and `UNSET` therefore goes hand in hand with **CQL INSERT/UPDATE/DELETE, Java Driver 4.x, primary key design, retry handling, TTL, tombstones, compaction, and repair**.

## 1. Four States to Distinguish

In an update request, before binding to CQL, an application typically encounters four cases:

| Case | Business Intent | Appropriate Behavior |
|---|---|---|
| Field **not sent** in request | Leave current value unchanged | Omit from the mutation or bind **UNSET** |
| Field **present and `null`** | Explicitly clear current value, if the API defines it that way | Write **CQL NULL** or `DELETE` the column |
| Field **present with a concrete value** | Update/overwrite value | Bind the corresponding value |
| Field **present with an empty/zero/false valid value** | Store that exact empty/0/false value | Bind `""`, `0`, or `false` per type and contract |

Core points:

- **CQL `NULL` in a mutation:** typically means **delete the column**; Cassandra writes a **tombstone** so replicas learn about the deletion.
- **UNSET in a prepared statement:** the bound variable is marked **excluded from the mutation**. Existing data in that column remains untouched, and **no tombstone is generated for that skipped variable**.
- **Column never written:** no live value exists to return; a `SELECT` typically displays `null` for that column.
- **Deleted column:** reads may also return `null`; underneath, a tombstone may remain until eligible for cleanup.

**Seeing `null` in a `SELECT` result alone cannot prove whether a column never existed, was just deleted, or expired via TTL.** This is a fundamental distinction between *query semantics* and *physical storage history*.

## 2. Cassandra Does Not Store NULL as a Normal Value

### 2.1. A CQL Table Declares Columns, but Not Every Row Has Every Column

In CQL, the schema defines the columns that may appear in a table. Unlike some relational SQL intuitions, **non-primary-key** columns do not need to be written in every row.

Example:

~~~cql
CREATE TABLE customer_profiles_by_id (
    customer_id uuid PRIMARY KEY,
    display_name text,
    bio text,
    loyalty_points int,
    marketing_opt_in boolean,
    updated_at timestamp
);
~~~

Here:

- `customer_id` is the **partition key**: a valid value is required to identify the row.
- `display_name`, `bio`, `loyalty_points`, `marketing_opt_in`, and `updated_at` are **regular columns**: they may remain unwritten.
- The schema **does not auto-populate defaults** like `0` for `loyalty_points` or `false` for `marketing_opt_in`.
- `NULL` is **not** a valid partition key value; all `PRIMARY KEY` components must be supplied and non-null.

Some relational databases support `NOT NULL` constraints on regular columns and SQL three-valued null logic. Do not carry that assumption verbatim into Cassandra: **CQL focuses on primary-key writes/reads; missing data and deletions are handled through distributed storage structures.**

### 2.2. Why Do Deletions Create Tombstones?

In Cassandra, data is replicated across multiple **replicas**. When an application deletes a column, simply erasing bytes on one replica without leaving a marker would allow another replica still holding the old value to synchronize it back, causing deleted data to **resurrect**.

Cassandra uses a **tombstone** as a deletion marker carrying timestamp metadata. Tombstones propagate and reconcile across reads, writes, repairs, and compaction under system rules, telling replicas that an older value was deleted.

~~~text
Before deletion:
Replica A: bio = "Loves coffee"
Replica B: bio = "Loves coffee"

After writing DELETE/NULL (simplified illustration):
Replica A: tombstone for bio
Replica B: may still hold old value if mutation has not arrived yet

During Cassandra synchronization/reads:
a newer tombstone shadows the older value
~~~

**A tombstone is not a data corruption error.** It is the necessary mechanism for distributed deletes. Trouble arises when applications create **vast numbers of unnecessary tombstones**, such as sending NULLs in bulk for columns that were merely omitted.

Tombstones are not purged immediately. Cleanup depends on safety conditions, `gc_grace_seconds`, replica state, and compaction. Never assume a single compaction pass or TTL expiration instantly erases all deletion markers.

## 3. Practical CQL: Omitted Columns in INSERT, NULL, and DELETE

To see the exact effects, use the same `customer_profiles_by_id` table with a fixed key.

### Step 1 — Write Some Columns, Omit the Rest

~~~cql
INSERT INTO customer_profiles_by_id (
    customer_id, display_name, loyalty_points, marketing_opt_in
) VALUES (
    11111111-1111-4111-8111-111111111111,
    'Nguyễn Hà', 0, false
);

SELECT customer_id, display_name, bio,
       loyalty_points, marketing_opt_in
FROM customer_profiles_by_id
WHERE customer_id = 11111111-1111-4111-8111-111111111111;
~~~

A client tool typically displays something like:

~~~text
display_name | bio  | loyalty_points | marketing_opt_in
-------------+------+----------------+-----------------
Nguyễn Hà    | null | 0              | false
~~~

Here `bio` **was never written**—that does not mean the application sent a delete for `bio`. Conversely, `0` and `false` are **real values**, not null. CQL does not infer `false` for "no marketing consent yet" or `0` for "no points computed yet."

### Step 2 — INSERT Another Column on the Same Primary Key

~~~cql
INSERT INTO customer_profiles_by_id (customer_id, bio)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'Loves coffee and books'
);
~~~

An `INSERT` in Cassandra defaults to an **upsert**: if a row with the same primary key already exists, the columns listed in the statement are written/updated. Columns **omitted** from `INSERT ... VALUES` retain their previous values. In this example, `display_name`, `loyalty_points`, and `marketing_opt_in` are untouched.

This differs from default `INSERT JSON` (see Section 7), where **absent** fields are treated as NULL unless `DEFAULT UNSET` is specified.

### Step 3 — Write NULL to Delete a Column

~~~cql
UPDATE customer_profiles_by_id
SET bio = null
WHERE customer_id = 11111111-1111-4111-8111-111111111111;
~~~

This statement expresses **deleting `bio`**. A tombstone is recorded, and subsequent normal reads show `bio` has no live value. Other columns in the same row are not deleted just because `bio` became NULL.

The equivalent statement for deleting a column:

~~~cql
DELETE bio
FROM customer_profiles_by_id
WHERE customer_id = 11111111-1111-4111-8111-111111111111;
~~~

**Caution:** `DELETE bio` differs from `DELETE FROM customer_profiles_by_id WHERE ...`. The former deletes only the named column; the latter deletes the **entire row** at that primary key. Pick the deletion scope matching your business requirement.

### Step 4 — UPDATE Only the Supplied Column

~~~cql
UPDATE customer_profiles_by_id
SET display_name = 'Nguyễn Thị Hà'
WHERE customer_id = 11111111-1111-4111-8111-111111111111;
~~~

This statement writes only `display_name`. It **does not** delete `bio`, reset `loyalty_points = 0`, or change `marketing_opt_in`.

In Cassandra, `UPDATE` is also an **upsert** unless guarded by a condition: it can create data for a primary key that did not previously exist. Thus, "UPDATE" does not guarantee the row already existed; if existence must be enforced, evaluate `IF EXISTS` and its LWT cost.

## 4. Distinguishing NULL, UNSET, and Live Values: Decision Table

Suppose a customer's `bio` is currently `"Loves coffee"`:

| Write Operation | `bio` After Mutation Applies | Tombstone for `bio` from This Operation? | Affects Other Columns? |
|---|---|---|---|
| `INSERT` naming only `customer_id`, `display_name` | Keeps `"Loves coffee"` | No | Only named columns (and row metadata per statement) |
| `UPDATE SET bio = 'Loves tea'` | `"Loves tea"` | Not a deletion | No |
| `UPDATE SET bio = null` | No live value | **Yes** | No |
| `DELETE bio FROM ...` | No live value | **Yes** | No |
| Prepared `UPDATE SET bio = ?` with **UNSET** | Keeps `"Loves coffee"` | **No** | No for that variable |
| Prepared `UPDATE SET bio = ?` with **CQL NULL** | No live value | **Yes** | No for other columns |
| Prepared `UPDATE SET bio = ?` with `""` | Empty string, if contract allows | Not a deletion | No |

Keep two questions separate:

1. **Which mutation did the client intend?** (keep, overwrite, delete).
2. **What does `SELECT` currently read?** (live value, null, or no row).

Sometimes `SELECT` returning `bio = null` looks identical after "never written" and "deleted." Yet if you must prevent another replica holding an old value from resurrecting it, the tombstone is essential metadata. Never try to eliminate all tombstones by turning real deletions into UNSET.

## 5. UNSET in Java Driver 4.x

### 5.1. Concept: UNSET Is a State of a **Bind Variable**

In Apache Cassandra Java Driver 4.x, a **prepared statement** contains `?` positional or named bind markers. Since native protocol **v4** (Cassandra 2.2+), a bind variable can be left **UNSET**: Cassandra skips that value in the mutation instead of interpreting it as NULL.

Common operations in Java Driver 4.x:

| API | Meaning |
|---|---|
| `builder.setString(i, value)` | Bind a `text` value |
| `builder.setBoolean(i, value)` | Bind `true`/`false` |
| `builder.setToNull(i)` | Bind **CQL NULL**, requesting column deletion in an applicable mutation |
| `builder.unset(i)` | Mark variable **UNSET**; server ignores the corresponding column |
| `statement.isSet(i)` | Check if variable has been bound; a set-to-null variable is still **set** |
| `statement.isNull(i)` | Check if bound value is **NULL**; not equivalent to UNSET |
| `row.isNull("column")` | Check whether a column **in a SELECT result** is null |

`UNSET` is **not a value stored in a cell** and **not a NULL literal**. Regular non-prepared CQL text has no `unset` column value. UNSET exists only while **building and sending a mutation**, not as a "keep unchanged" marker persisted in the table.

**Important:** `PRIMARY KEY` components are required to locate/write a row; **never** bind NULL or UNSET to a key expecting Cassandra to pick a row. If a PATCH lacks an ID/partition key, reject it or resolve the key through a dedicated lookup path first.

### 5.2. Java Example: Preserving Columns with UNSET

Suppose the application wants to update `display_name` while leaving `bio` and `marketing_opt_in` untouched:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.util.UUID;

// session is a connected CqlSession with the target keyspace selected.
UUID customerId =
    UUID.fromString("11111111-1111-4111-8111-111111111111");

PreparedStatement patch = session.prepare(
    "UPDATE customer_profiles_by_id "
  + "SET display_name = ?, bio = ?, marketing_opt_in = ? "
  + "WHERE customer_id = ?");

BoundStatement bound = patch.boundStatementBuilder()
    .setString(0, "Nguyễn Thị Hà") // Write new value.
    .unset(1)                     // Leave bio unchanged.
    .unset(2)                     // Leave marketing_opt_in unchanged.
    .setUuid(3, customerId)       // Primary key is required.
    .build();

session.execute(bound);
~~~

The existing `bio` value is preserved, whether it currently holds a string or was never written. **No tombstones are created for UNSET columns** in this write.

In driver 4.x, `BoundStatement` is **immutable**: methods like `bound.unset(1)` return a new instance without modifying `bound`. With `BoundStatementBuilder` as shown above, setters mutate the builder before `build()`; afterward, the built statement is safe to share per driver rules.

~~~java
BoundStatement original = patch.bind(
    "Old Name", "Old Bio", true, customerId
);

BoundStatement modified = original.unset(1);

// original still has bio bound.
// modified has bio as UNSET.
session.execute(modified);
~~~

**Never ignore the return value of `unset()` on an immutable BoundStatement.** The following is a bug:

~~~java
BoundStatement wrong = patch.bind(
    "New Name", "Unwanted data", false, customerId
);
wrong.unset(1);      // Returns a new instance that is discarded.
session.execute(wrong); // Still writes the bound bio value.
~~~

### 5.3. Java Example: Explicitly Deleting a Column with NULL

If the user asks to clear their bio, **explicitly bind NULL**:

~~~java
BoundStatement clearBio = patch.boundStatementBuilder()
    .unset(0)                // Keep display_name.
    .setToNull(1)            // Explicitly delete bio.
    .unset(2)                // Keep marketing_opt_in.
    .setUuid(3, customerId)
    .build();

session.execute(clearBio);
~~~

This is a mutation deleting `bio`, not "nothing to write." Afterward `bio` reads as `null`, and the deletion is represented by a tombstone in Cassandra's storage path.

Some typed setters like `setString(index, null)` also bind NULL via their codec, yet in three-state business logic, **`setToNull` expresses deletion intent much more clearly**. For primitive types like `boolean` or `int`, use `setToNull` instead of trying to pass `null` to `setBoolean`/`setInt`.

### 5.4. Inspecting Bound State

~~~java
BoundStatement check = patch.boundStatementBuilder()
    .setString(0, "New Name")
    .unset(1)
    .setToNull(2)
    .setUuid(3, customerId)
    .build();

System.out.println(check.isSet(0)); // true: display_name has a value
System.out.println(check.isSet(1)); // false: bio is UNSET
System.out.println(check.isSet(2)); // true: marketing_opt_in is set to NULL
System.out.println(check.isNull(2)); // true: variable 2 is NULL
~~~

`isSet` and `isNull` answer **two different questions**. Never substitute `isNull` for `isSet` when deciding whether a field was supplied.

## 6. PATCH APIs: Separating Absent, Explicit Null, and Value

Suppose an API accepts JSON to update a customer.

### 6.1. Three Requests with Three Different Meanings

~~~json
{"displayName": "Nguyễn Hà"}
~~~

Updates only `display_name`. Absent fields (`bio`, `marketingOptIn`) must **remain unchanged** if that is the API's PATCH contract.

~~~json
{"bio": null}
~~~

Requests **clearing the bio** if the contract defines JSON `null` = clear.

~~~json
{"bio": "", "marketingOptIn": false, "loyaltyPoints": 0}
~~~

Requests writing **an empty string, false, and 0**. Never turn these three valid values into null or UNSET through checks like `if (value)`, `if (points > 0)`, or `if (!text.isBlank())` when they are legitimate values.

With some JSON-to-POJO deserializers, both an **absent** field and an **explicit null** field become a Java property equal to `null`. When a three-state model is required, use:

- A `PatchField<T>` wrapper with states `KEEP`, `CLEAR`, `SET`.
- Or a JSON tree/map checking **key presence** (e.g., `containsKey`) before reading the value.
- Or a DTO supporting explicit presence tracking managed by the API framework/contract.

**Using `Optional<T>` alone as a DTO property does not solve every case** if the deserializer already collapses absent fields and explicit nulls into the same state.

### 6.2. Java Pattern Combining Enum and Builder

The example below highlights the three-state logic for `bio`. Other fields follow the same pattern.

~~~java
import com.datastax.oss.driver.api.core.cql.BoundStatementBuilder;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.util.UUID;

enum PatchAction { KEEP, CLEAR, SET }

// patch is a PreparedStatement:
// UPDATE customer_profiles_by_id
// SET display_name=?, bio=?, marketing_opt_in=?
// WHERE customer_id=?

PatchAction bioAction = PatchAction.CLEAR;  // Example from API request.
String newBio = null;                       // Read only when SET.

BoundStatementBuilder builder = patch.boundStatementBuilder()
    .unset(0)
    .unset(1)
    .unset(2)
    .setUuid(3, customerId);

switch (bioAction) {
    case KEEP:
        builder.unset(1);
        break;
    case CLEAR:
        builder.setToNull(1);
        break;
    case SET:
        if (newBio == null) {
            throw new IllegalArgumentException("SET requires a value");
        }
        builder.setString(1, newBio);
        break;
}

session.execute(builder.build());
~~~

This example uses `CLEAR` to produce a tombstone because the user **genuinely requested deletion**. If a PATCH sends `displayName`, `marketingOptIn`, and `bio` together, make an **independent decision per field**; never turn everything into NULL just because one field is cleared.

### 6.3. When to Use an UPDATE Statement Listing Only Changed Columns?

For requests updating only a few columns, you can issue a targeted CQL statement **containing only the modified columns**:

~~~cql
UPDATE customer_profiles_by_id
SET marketing_opt_in = false
WHERE customer_id = 11111111-1111-4111-8111-111111111111;
~~~

This is explicit, uses fewer bind variables, and avoids accidental null binds. However, if an API allows many combinations of optional fields, the number of distinct prepared statements grows combinatorially; a single prepared statement using **UNSET** cleanly enables statement reuse.

Balance statement count, prepare/cache overhead, readability, and concurrency needs. Never concatenate user input into dynamic CQL strings; even if generating statements over a controlled set of column names, always **bind values** via prepared statements.

## 7. Important Exception: INSERT JSON DEFAULT NULL vs. DEFAULT UNSET

For `INSERT ... VALUES`, omitted columns are **left unchanged**. For **`INSERT JSON`**, however, Cassandra uses different default semantics.

According to CQL documentation, when using `INSERT JSON`:

- **`DEFAULT NULL`** (the default) treats columns **missing from the JSON** as NULL, which can erase previous values and generate tombstones.
- **`DEFAULT UNSET`** treats columns **missing from the JSON** as unset, preserving previous values and avoiding tombstones for those omissions.
- **An explicit JSON `null`** still writes NULL **even when `DEFAULT UNSET` is specified**; that option applies only to **omitted fields**, not explicit nulls.

For example, suppose the row already has `bio = 'Loves coffee'`:

~~~cql
-- WARNING: bio and other regular columns omitted from the JSON
-- can be treated as NULL, deleting their previous values.
INSERT INTO customer_profiles_by_id
JSON '{"customer_id":"11111111-1111-4111-8111-111111111111","display_name":"New Name"}'
DEFAULT NULL;
~~~

When you truly want to **preserve columns absent from the JSON**, specify it explicitly:

~~~cql
INSERT INTO customer_profiles_by_id
JSON '{"customer_id":"11111111-1111-4111-8111-111111111111","display_name":"New Name"}'
DEFAULT UNSET;
~~~

If the JSON contains `"bio": null`, the intent is **delete bio**:

~~~cql
-- DEFAULT UNSET protects only omitted columns;
-- bio is present with explicit null, so this remains a deletion mutation.
INSERT INTO customer_profiles_by_id
JSON '{"customer_id":"11111111-1111-4111-8111-111111111111","bio":null}'
DEFAULT UNSET;
~~~

**Review rule:** always distinguish **`INSERT ... VALUES`**, **`INSERT JSON DEFAULT NULL`**, and **`INSERT JSON DEFAULT UNSET`**. Never generalize "omitted means keep" from one CQL form to all CQL forms.

Also note that `DEFAULT UNSET` here is an **option on INSERT JSON**; it is not a column default definition inside `CREATE TABLE`.

## 8. SELECT: Never Confuse a Missing Row with a Null Column

### 8.1. Checking with Row and isNull

In Java Driver 4.x, before reading a column, separate two questions:

1. **Was a row returned?** `result.one() == null` means the query returned no row.
2. **If a row exists, does that column have a live value?** `row.isNull("column")` checks this.

~~~java
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.UUID;

PreparedStatement select = session.prepare(
    "SELECT display_name, bio, loyalty_points, marketing_opt_in "
  + "FROM customer_profiles_by_id WHERE customer_id = ?");

Row row = session.execute(select.bind(customerId)).one();

if (row == null) {
    // No live row found for this key.
} else {
    String bio = row.getString("bio"); // May be null.

    Integer points = row.isNull("loyalty_points")
        ? null : row.getInt("loyalty_points");

    Boolean marketing = row.isNull("marketing_opt_in")
        ? null : row.getBoolean("marketing_opt_in");

    // points == 0 and marketing == false are NOT equivalent to null.
}
~~~

Especially for primitive columns like `int` and `boolean`, **never read with a primitive getter and treat 0 or false as "missing value."** Check `row.isNull` first, then map to `Integer`/`Boolean` wrappers if business logic requires three states.

A `text` column can contain `""` (empty string)—distinct from `null`. A numeric column can contain `0`—distinct from `null`. A boolean column can contain `false`—distinct from `null`. For **collections**, verify version- and type-specific behavior rather than assuming `empty` vs. `null` behaves identically to `text`.

### 8.2. A SELECT Returning null Does Not Reveal Tombstone History

If `row.getString("bio") == null`, several causes are possible:

- `bio` was never written.
- `bio` was deleted via `DELETE bio` or `UPDATE SET bio = null`.
- `bio` previously had a value whose **TTL expired**.
- Data or replicas are in an inconsistent state awaiting convergence per consistency rules.

Never build business logic assuming "if `bio` is null, no bio ever existed." If you require an authoritative history of "previously existed and was deleted by whom and when," design a dedicated **audit event** table with keys, actor, timestamp, and retention policy.

Even when a row has only primary-key markers and no regular columns written yet, Cassandra's representation of **row liveness** differs from a NULL column value. Do not treat `row == null` and `row.isNull("bio")` as interchangeable states.

## 9. Querying by Missing Data State: Design a Dedicated Table

A common request is:

> "Find all profiles missing a `bio` or lacking marketing consent within a tenant."

Never assume Cassandra can efficiently scan the cluster with:

~~~cql
-- Do NOT use as a general Cassandra query pattern:
-- SELECT * FROM customer_profiles_by_id WHERE bio = null;
-- SELECT * FROM customer_profiles_by_id WHERE bio IS NULL;
~~~

Querying a **regular column** without an appropriate access path does not become cheap merely because you are looking for `null`. Clauses like `IS NULL`/`IS NOT NULL` appear in specialized CQL contexts such as **materialized view** definitions; they do not mean arbitrary tables support SQL-style `WHERE bio IS NULL` queries efficiently.

If the requirement is "list incomplete profiles by tenant and day," model the **pending-action state** as queryable key data:

~~~cql
CREATE TABLE profile_review_queue_by_tenant_day (
    tenant_id uuid,
    review_day date,
    created_at timestamp,
    customer_id uuid,
    reason text,
    PRIMARY KEY ((tenant_id, review_day), created_at, customer_id)
) WITH CLUSTERING ORDER BY (created_at ASC, customer_id ASC);
~~~

Query:

~~~cql
SELECT created_at, customer_id, reason
FROM profile_review_queue_by_tenant_day
WHERE tenant_id = 22222222-2222-4222-8222-222222222222
  AND review_day = '2026-11-21'
LIMIT 100;
~~~

Design notes for this approach:

- **`reason`** can hold `MISSING_BIO` or `PENDING_CONSENT` from an explicit business catalog, rather than inferring from null.
- The queue table is updated when profile status changes; design retries, reconciliation, and completion/deletion handling.
- `review_day` is a **partition bucket**. If a tenant has heavy backlog volume, use smaller buckets or sharding.
- Cassandra does not synchronize multiple query tables in a multi-partition ACID transaction. If immediate consistency is required, design write flows and consistency levels accordingly.

**Choosing NULL/UNSET is a column-write decision; choosing the partition key is a data-read decision.** Allowing columns to be null cannot substitute for query-driven modeling.

## 10. NULL/UNSET with TTL, Counters, Collections, and Primary Keys

### 10.1. TTL Can Make Values Disappear Without a PATCH

Cassandra can automatically expire data via **TTL** (in seconds). A normally written column can read back as null after TTL expires because the value is no longer live; expiration tombstones are handled by storage mechanics.

~~~cql
UPDATE customer_profiles_by_id
USING TTL 3600
SET bio = 'Temporary info'
WHERE customer_id = 11111111-1111-4111-8111-111111111111;
~~~

Once TTL expires, `bio` has no live value. Crucially, **UNSET does not start a new TTL** on the skipped column, because nothing is written to it. When rewriting a column with a new TTL, understand how that write resets TTL per column; never assume an unrelated update extends the lifetime of other columns.

Some applications query `TTL(column)` to check remaining seconds on a regular column. However, `TTL(column)` is not a full history; absent columns, non-TTL columns, and edge cases must be interpreted carefully per schema and version. **Never use TTL to definitively distinguish "never existed" from "was deleted."**

### 10.2. Primary Keys Cannot Be NULL or UNSET

~~~cql
-- INVALID: null cannot identify a partition key.
-- INSERT INTO customer_profiles_by_id (customer_id, display_name)
-- VALUES (null, 'Unknown');
~~~

If input data lacks an ID, the application must assign or require an ID prior to writing, or write to a staging structure with a valid primary key. Distinguishing "missing `customer_id`" belongs to **pre-write input state**, not a null partition key stored in Cassandra.

In a parameterized statement like `... WHERE customer_id = ?`, never unset the key variable expecting an UPDATE to mean "update all customers." Cassandra does not support that interpretation.

### 10.3. Collections, UDTs, and Types with Specific Rules

For `list`, `set`, `map`, `tuple`, or user-defined types, **column-level NULL** behaves differently from **element-level NULL** or **nested field updates**. Some structures forbid null elements, and certain collection mutations generate element- or collection-level tombstones. Never apply the "set null = delete whole column" rule mechanically to element-level operations.

For instance, updating a `frozen<udt>` replaces the whole value, unlike a non-frozen UDT whose fields can be mutated individually. Check the exact CQL rules for the type and operation before optimizing tombstones.

### 10.4. Counters Are Not Regular Numeric Columns

Cassandra provides the `counter` type updated via dedicated increment/decrement operations; never treat a `counter` as a nullable `bigint` where `SET count = null` or `UNSET` arbitrarily "resets" it. Resetting or adjusting counts requires a workflow designed around counter semantics and non-idempotent retries.

## 11. Tombstones and Distributed Systems: When NULL Is Needed vs. When UNSET Is Optimal

### 11.1. Why Do Excessive Tombstones Slow Queries?

In some workloads, every time an application sends an `UPDATE` containing many unnecessary NULL columns, Cassandra records deletion markers. Over time, SSTables accumulate tombstones; reads must scan and discard shadowed cells, increasing CPU, I/O, and compaction pressure.

For example, consider an ingest pipeline receiving 10 million records/day, each with 20 optional fields. Binding NULL for every omitted field generates far more deletion markers than business logic needs—even for columns that never held prior values.

**Solution:** when an omitted field means **leave unchanged**, use **UNSET** or omit the column from the mutation. When business logic requires **deleting** data, keep using NULL/DELETE so older values cannot survive.

### 11.2. gc_grace_seconds, Compaction, and Repair

Tombstones are purged only when Cassandra deems it safe under system rules. **`gc_grace_seconds`** retains deletion markers long enough to cover temporary replica outages; **repair** synchronizes replicas to prevent old data from resurrecting; **compaction** processes SSTables and drops eligible tombstones.

Never blindly set `gc_grace_seconds = 0` to "fix" slow queries caused by excessive NULLs. Dropping tombstones prematurely before offline replicas receive deletes risks **zombie data** (previously deleted values reappearing). Repair schedules, compaction strategies, TTL, and operational cadence must be evaluated together against real workload behavior.

**UNSET eliminates unnecessary tombstones, but does not replace genuine deletions or repair.**

### 11.3. Write Timestamps, Retries, and Conflicts

Cassandra attaches write-timestamp metadata to cells for conflict resolution. A deletion via NULL/DELETE writes a tombstone with timestamp metadata that shadows older values according to timestamp and mutation type; concurrent or later writes with different timestamps affect read outcomes.

In distributed systems, a timeout does not prove a write failed to apply. When a client retries:

- Keep the **same primary key** and the **same PATCH intent** for a single business request.
- For genuine deletions, retrying a delete is valid, while still accounting for **write timestamps** and concurrent updates (e.g., if the user re-entered a bio).
- Never swap `NULL` for `UNSET` on a retry: that **changes the mutation's semantics**.
- To guard against concurrent overwrites, track versions, evaluate **LWT/IF** on an appropriate key, or apply application coordination; `LOCAL_QUORUM` does not automatically enforce "latest wall-clock PATCH always wins" across concurrent writers.

In Cassandra, `WRITETIME(column)` exposes write metadata for a **regular column currently holding an applicable value**; it is not a full history of PATCH requests and does not replace an audit log. Nor does it turn a `null` in `SELECT` into proof of "never written."

## 12. Mappers and Conversion Bugs in the Java Layer

When using **DataStax/Apache Java Driver Mapper 4.x**, pay attention to **`NullSavingStrategy`** (configured on mapper/DAO operations):

| Strategy | Behavior for a `null` Java Property | Consequence |
|---|---|---|
| **`DO_NOT_SET`** | Does not bind that property, leaving it unset | Preserves existing values, avoids unnecessary tombstones |
| **`SET_TO_NULL`** | Binds CQL NULL for that property | Can delete existing values and create tombstones |

A Java entity with `bio == null` may mean **"bio is unknown because it wasn't loaded"** or **"delete bio."** A mapper cannot guess business intent on its own. Use a DTO/PATCH model that explicitly tracks field presence rather than relying solely on serialized entity objects.

Other common mistakes:

| Mistake | Consequence | Fix |
|---|---|---|
| Treating a missing JSON field as `null` to write | Unintentionally wipes columns | Check field presence and use UNSET |
| Treating an explicit JSON null as UNSET | User requested deletion, yet old value persists | Bind `setToNull` or `DELETE` |
| Calling `row.getBoolean` and treating `false` as missing | Loses true `false` semantics | Check `row.isNull` before reading |
| Treating `loyalty_points=0` as NULL | Wrong math and reporting | Preserve `0` as a valid value |
| Ignoring the return value of `bound.unset()` in driver 4 | Original statement unchanged, writes unwanted data | Reassign result or use builder |
| Using default `INSERT JSON` for partial updates | Missing fields can be deleted | Use `DEFAULT UNSET` or prepared statements |
| Binding `null` to a key column | No valid partition key | Validate entire primary key |
| Treating `null` from SELECT as "never written" | Wrong business history | Design dedicated audit/metadata tracking |
| Sending NULL for every optional field per request | Tombstone explosion, slow reads | UNSET unchanged fields |
| Turning DELETE into UNSET to "avoid tombstones" | Data is never actually deleted | Use DELETE/NULL for genuine deletions |
| Lowering `gc_grace_seconds` without analysis | Risk of zombie data reappearing | Run repair and compaction safely |

## 13. Scenario Exercises

### Exercise 1 — One PATCH, Three Different Values

Current row:

~~~text
customer_id = 11111111-1111-4111-8111-111111111111
display_name = "Hà"
bio = "Loves coffee"
marketing_opt_in = true
~~~

API receives:

~~~json
{"displayName": "Nguyễn Hà", "bio": null}
~~~

**Question:** after the PATCH, what state must `display_name`, `bio`, and `marketing_opt_in` have?

**Answer:** `display_name = "Nguyễn Hà"`, `bio` is deleted (`NULL`/tombstone), and `marketing_opt_in` remains `true` (UNSET/omitted). Never flip marketing consent to `false`.

### Exercise 2 — False and Null

A `marketing_opt_in boolean` column is queried. The application returns `false` for both rows that have no value yet and rows where the user explicitly opted out.

**Question:** where is the bug?

**Answer:** the application erased the distinction between **"undecided"** and **"opted out."** Check `row.isNull("marketing_opt_in")` before calling `getBoolean`, then represent it via `Boolean` or an explicit business state.

### Exercise 3 — INSERT JSON Causing Data Loss

A row has `bio = "Loves coffee"`. A worker executes:

~~~cql
INSERT INTO customer_profiles_by_id
JSON '{"customer_id":"11111111-1111-4111-8111-111111111111","display_name":"New Hà"}';
~~~

**Question:** is `bio` guaranteed to be preserved?

**Answer:** no. `INSERT JSON` defaults to treating omitted columns as NULL and can delete the old value. Use **`DEFAULT UNSET`** when intending a partial upsert; explicit JSON null still means delete.

### Exercise 4 — Are These Two Calls Equivalent?

~~~java
builder.unset(1);     // A
builder.setToNull(1); // B
~~~

**Answer:** no. A skips variable 1 and preserves the existing column value; B binds NULL and writes a tombstone to delete that column's value.

### Exercise 5 — Querying Missing Bios

Requirement: "Daily fetch the 100 newest profiles missing a bio for a tenant." The table has only `PRIMARY KEY(customer_id)`, with `tenant_id` and `bio` as regular columns.

**Question:** should you scan all profiles with `WHERE bio IS NULL`?

**Answer:** do not treat that as a default query path. Design a queue/lookup table keyed by `tenant_id + day`, clustered by timestamp and customer ID, or a proven indexing strategy; update the missing-bio status whenever profile data changes.

## 14. Checklist for Reviewing NULL, Missing Values, and UNSET

- [ ] Does the API distinguish **omitted fields**, **explicit nulls**, **concrete values**, and **valid empty/zero/false values**?
- [ ] On PATCH, are omitted fields **UNSET/skipped** instead of accidentally becoming CQL NULL?
- [ ] When deletion is genuinely required, is **NULL/DELETE** used instead of UNSET so replicas learn of the deletion?
- [ ] Are all `PRIMARY KEY` components populated and never bound to NULL or UNSET?
- [ ] Have `INSERT ... VALUES`, `INSERT JSON DEFAULT NULL`, and `INSERT JSON DEFAULT UNSET` been clearly distinguished?
- [ ] Does Java Driver 4.x properly use `unset`, `setToNull`, `isSet`, and handle `BoundStatement` immutability?
- [ ] On reads, are **missing Row** and **Row present with null column** handled separately?
- [ ] Do `false`, `0`, and `""` keep their valid semantics without being treated as missing?
- [ ] With TTL, is it understood that column expiration makes SELECT return null without proving the column never existed?
- [ ] If deletion auditing is needed, is there a dedicated log/event instead of inferring from null?
- [ ] Do queries for missing-data states use a matching **partition key/access path** rather than cluster-wide scans?
- [ ] Have tombstones, partition sizes, p95/p99 latency, and compaction/repair/`gc_grace_seconds` plans been measured?
- [ ] Do retries and concurrent writes on the same primary key preserve delete/keep/set intent and guard against stale overwrites?
- [ ] If using the Mapper, have `NullSavingStrategy.DO_NOT_SET` vs. `SET_TO_NULL` been verified?

## References

- [Apache Cassandra — CQL Data Manipulation (INSERT/UPDATE/DELETE)](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html).
- [Apache Cassandra — JSON Support and DEFAULT UNSET](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/json.html).
- [Apache Cassandra — Tombstones](https://cassandra.apache.org/doc/latest/cassandra/managing/operating/compaction/tombstones.html).
- [Apache Cassandra Java Driver 4.x — Prepared statements and UNSET](https://apache.github.io/cassandra-java-driver/4.18.0/core/statements/prepared/).
- [Apache Cassandra Java Driver 4.x — Mapper null saving strategy](https://apache.github.io/cassandra-java-driver/4.18.0/mapper/daos/null_saving/).
- [Apache Cassandra Java Driver 4.x — SettableByIndex.setToNull](https://apache.github.io/cassandra-java-driver/4.18.1/api/com/datastax/oss/driver/api/core/data/SettableByIndex.html).

**Remember:** **NULL deletes; UNSET skips; never stored means no live value exists**. Both unwritten and deleted columns can read back as `null`, yet deleting must leave proper metadata for replicas. In the Java Driver, design PATCH logic with three explicit states—**KEEP / CLEAR / SET**—bind `unset` or `setToNull` accordingly, and rely on clear primary keys and access paths. That preserves business semantics while avoiding unnecessary tombstones in distributed Cassandra.
