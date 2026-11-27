# Key/Value Maps, Missing Elements, and Conditional Updates in Apache Cassandra

> **Chapter:** Collections and UDTs  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — Apache Cassandra, a distributed wide-column database. This lesson connects `map<K,V>` operations to partition keys, query-driven table design, consistency levels, replication, repair/compaction, and Java connectivity.

## 1. Scenario: What Does a Missing Configuration Key Mean?

Suppose an online learning application stores several preferences per user:

```text
user_id = 11111111-1111-4111-8111-111111111111
settings = {
  'language': 'vi',
  'theme':    'dark'
}
```

The application may need to add `timezone`, change `theme`, change `language` only if the data version has not changed, or create an option **only if that key is not already present**. These requirements look similar yet involve three distinct notions of existence:

1. **Does the row exist?** Is there live data for primary key `user_id`?
2. **Does the map column have a value?** Does `settings` currently have any entries, or is it `null`/empty?
3. **Does the sub-key exist?** Does the current map contain an entry with key `'timezone'`?

Cassandra provides `IF EXISTS` and `IF NOT EXISTS` for **row existence** in the corresponding statement. They do not mean "a sub-key of the map already/does not yet exist." If the problem demands a conditional operation on **a specific map key**, pick an appropriate mechanism: row-wide version control via *lightweight transactions* (LWT), or modeling each key as its own row so you can run `INSERT ... IF NOT EXISTS` directly against that key.

## 2. What Is `map<K,V>` and When Should You Use It?

`map<K,V>` maps **unique keys** of type `K` to **values** of type `V`. A map does not preserve insertion order for the application to treat as a list; entries are compared/sorted by key according to type. Values can repeat across different keys, while each key holds at most one value in any observed state.

```sql
-- Map from preference name to text value.
settings map<text, text>
```

| Business requirement | Is `map<text,text>` suitable? | Why |
| --- | --- | --- |
| Each user has at most a few dozen flexible attributes | Can be suitable | Read the whole map by `user_id`, update by sub-key |
| Update one attribute whose name is known | Yes | Direct entry update syntax exists |
| Need to preserve the order in which the user entered attributes | Not satisfied natively | Maps do not carry business ordering |
| Need to query all users with `theme = dark` | Requires a dedicated read model/index | Partition key `user_id` does not serve that reverse query |
| Hundreds of thousands of keys, needing key pagination | Not recommended | Oversized collection in one row; cannot paginate as independent rows |
| Each key has its own history, TTL, owner, and lifecycle | Consider a separate table | Better suited for per-item identification and conditions |

Collection keys and values cannot use `null` as a valid element. To represent **the absence of a key**, delete the entry rather than trying to assign `settings['key'] = null`. If fields are always fixed and have differing types (`notifications_enabled boolean`, `font_size int`), scalar columns or a UDT can be clearer than `map<text,text>`.

## 3. Creating the Schema, Sample Data, and Querying a Map

The examples below assume the keyspace `app` already exists with replication configured for your environment. `revision` illustrates conditional updates; it is an **application-managed version number**, not Cassandra's `counter` type.

```sql
CREATE TABLE app.user_preferences (
    user_id uuid PRIMARY KEY,
    settings map<text, text>,
    revision int
);

INSERT INTO app.user_preferences (user_id, settings, revision)
VALUES (
    11111111-1111-4111-8111-111111111111,
    {'language':'vi', 'theme':'dark'},
    1
);

-- Read the entire map and stored version.
SELECT settings, revision
FROM app.user_preferences
WHERE user_id = 11111111-1111-4111-8111-111111111111;

-- Fetch only the value for key theme from the collection.
SELECT settings['theme'] AS theme
FROM app.user_preferences
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

In CQL, `{key: value}` is the `map` literal; note the `:` between key and value. The queries above are **scoped by primary key**. Selecting a single entry in the `SELECT` list does not turn that entry into a partition key and does not make the map paginatable element by element.

## 4. Reading a Missing Key

Suppose the sample state does not yet have key `'timezone'`:

```sql
SELECT settings['timezone'] AS timezone
FROM app.user_preferences
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Selecting a missing entry evaluates to **`null` for the selected field** (while the row itself exists). However, **do not infer from a single `null` value** that the map key is necessarily missing:

- Key `'timezone'` may never have been written, or it may have been deleted or expired via TTL.
- The entire `settings` column may have no value.
- The `user_id` row itself may not exist; in that case `SELECT ... WHERE user_id = ...` returns **zero rows**, which differs from "row exists with a null projected field."

To distinguish these cases, the application should check whether `Row` exists, read relevant columns (`settings`, `revision`), and explicitly define the semantics of "unconfigured," "using default," and "deleted." Do not use a fake `null` sentinel inside a map value to encode absence.

Example in Java Driver 4.x:

```java
Row row = session.execute(selectStatement.bind(userId)).one();
if (row == null) {
    // No row found for the given primary key.
} else {
    Map<String, String> settings = row.getMap(
        "settings", String.class, String.class
    );
    if (settings == null || !settings.containsKey("timezone")) {
        // Row exists, but timezone is not stored in the map.
    }
}
```

This snippet assumes `selectStatement` is a prepared statement for `SELECT settings ... WHERE user_id = ?` and `userId` is a `UUID`; key absence should be handled as a normal business branch rather than a silently swallowed error.

## 5. Adding a New Key: `UPDATE` Is an Upsert

```sql
-- If timezone is absent, creates a new entry. If present, replaces the old value.
UPDATE app.user_preferences
SET settings['timezone'] = 'Asia/Ho_Chi_Minh'
WHERE user_id = 11111111-1111-4111-8111-111111111111;

-- Merge multiple entries into the existing map; duplicate keys are updated.
UPDATE app.user_preferences
SET settings = settings + {'font':'large', 'theme':'light'}
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Both statements are **insert-or-update (upsert)** operations, not "add only if the key is absent." In Cassandra, a plain `UPDATE` can also create data for **a nonexistent row** given the full primary key. Consequently, the statement can materialize a new row whose `revision` the application has not yet initialized.

If the requirement is **never create a new row**, consider `UPDATE ... IF EXISTS`; if the requirement is **never overwrite an existing map key**, `IF EXISTS` alone is still insufficient. Later sections cover CAS on `revision` and turning each entry into its own row when conditions must bind directly to the sub-key.

### Writing One Key vs. Replacing the Whole Map

```sql
-- Update one entry: other keys are unaffected by this statement.
UPDATE app.user_preferences
SET settings['theme'] = 'light'
WHERE user_id = 11111111-1111-4111-8111-111111111111;

-- Replace the entire map: keys absent from the new literal are removed.
UPDATE app.user_preferences
SET settings = {'theme':'light'}
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

These express two different business intents. The first **patches one attribute**; the second **sets the final state of the entire map**. For a non-frozen map, Cassandra manages entries in separate cells, so patching by key fits better when multiple clients edit different keys. Replacing the entire map can create deletion markers shadowing old entries, increase tombstones, and easily overwrite another client's changes when built from a stale snapshot.

## 6. Deleting a Nonexistent Key: Looks Like a No-Op, Still Has a Cost

```sql
-- Delete the entry with key theme.
DELETE settings['theme']
FROM app.user_preferences
WHERE user_id = 11111111-1111-4111-8111-111111111111;

-- Delete a key assumed not to exist.
DELETE settings['does_not_exist']
FROM app.user_preferences
WHERE user_id = 11111111-1111-4111-8111-111111111111;

-- Delete the entire map column, completely different from deleting one entry.
DELETE settings
FROM app.user_preferences
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

In application read results, deleting an absent key may look like **no change at all**. Yet a delete command is not necessarily a storage-level *no-op*: Cassandra may write a **tombstone** for the entry to ensure stale values from other replicas or SSTables do not reappear. Tombstones must be evaluated during reads and compaction; repeatedly deleting nonexistent keys at high frequency can still create operational load.

Do not adopt a pattern of "delete an arbitrary key on every incoming request" unnecessarily. If you need to distinguish "the key was already absent" from "the key was just deleted," build an explicit state or conditional mechanism; a plain `DELETE` does not return a flag confirming whether the key previously existed.

## 7. Conditional Updates: Row Conditions Differ from Key Conditions

### 7.1. `INSERT ... IF NOT EXISTS` Is Row-Scoped

```sql
-- Attempt to create a row with primary key user_id if the row does not yet exist.
INSERT INTO app.user_preferences (user_id, settings, revision)
VALUES (
    22222222-2222-4222-8222-222222222222,
    {'theme':'dark'},
    1
)
IF NOT EXISTS;
```

This is a **lightweight transaction (LWT)**; the result includes an `[applied]` column indicating whether the write passed the condition. `IF NOT EXISTS` checks **the row by primary key** `user_id`. It does **not** mean "add key `'theme'` if it is not yet in the map of an existing row." If the user already has a row—even if the map lacks `'theme'`—`INSERT ... IF NOT EXISTS` will not apply the desired change.

### 7.2. `UPDATE ... IF EXISTS` Also Checks the Row

```sql
-- Update the entry only if the row for user_id already exists.
UPDATE app.user_preferences
SET settings['theme'] = 'dark'
WHERE user_id = 11111111-1111-4111-8111-111111111111
IF EXISTS;
```

This statement blocks the case where **the row** is missing. However, if the row exists and `settings['theme']` is absent, it **can still create key `theme`**. If the key already exists, it can still overwrite it. Avoid interpreting `IF EXISTS` as a check on the existence of a map element.

| Statement | Actual condition | What it does NOT guarantee |
| --- | --- | --- |
| `INSERT ... IF NOT EXISTS` | Row with that primary key does not yet exist | That a sub-key is absent in an existing row |
| `UPDATE ... IF EXISTS` | Row with that primary key exists | That a sub-key already exists or keeps its old value |
| `UPDATE ... IF revision = N` | Value of column `revision` in the row equals `N` | Writers that fail to follow the same versioning protocol |
| `UPDATE` without `IF` | No CAS check | Preventing row creation or preventing key overwrites |

### 7.3. How Do You Implement "Add Only If Key Is New"?

There are two approaches, depending on query characteristics:

1. **Keep a small map in one row:** read the map state and `revision`, check in the application layer that the key is absent, and then **CAS on `revision`**. If CAS fails, re-read and decide based on the new state. Every writer modifying the map must adhere to the version-increment protocol for this condition to hold.
2. **Create a separate row per key:** design the primary key with `user_id` and `preference_key`; then `INSERT ... IF NOT EXISTS` checks the existence of **the business entry** corresponding directly to that key.

Do not rely on a bare **`SELECT` then `UPDATE`** flow to ensure a key is absent when multiple clients run concurrently: two clients can both read "key missing" and both write. Consistency level `QUORUM` does not automatically turn those two statements into a conditional read-modify-write transaction.

## 8. CAS by Row Version: Keeping a Map While Controlling Contention

Suppose a row currently has `revision = 1` and `settings = {'language':'vi','theme':'dark'}`. Client A wants to switch `theme` to `light`, but **only if nobody modified the row state since A read it**.

```sql
-- When A reads:
SELECT settings, revision
FROM app.user_preferences
WHERE user_id = 11111111-1111-4111-8111-111111111111;

-- A attempts to update the entry and increment revision in the same conditional statement.
UPDATE app.user_preferences
SET settings['theme'] = 'light', revision = 2
WHERE user_id = 11111111-1111-4111-8111-111111111111
IF revision = 1;
```

If the condition holds, Cassandra applies the mutation and returns `[applied] = true`. If another writer already changed `revision`, the condition fails and `[applied] = false`; the client must decide whether to re-read and surface a conflict, retry with the new revision, or reject the operation. **Never loop endlessly with the same stale revision** and never ignore the `[applied]` flag.

To implement "add key only if absent" reliably with this workflow:

1. The client reads the map, confirms the target key is absent, and retrieves the current `revision`.
2. The client sends `UPDATE ... SET settings['new_key'] = ..., revision = new_revision ... IF revision = old_revision`.
3. If `[applied] = false`, the client re-reads all required state. If the key has appeared, return "key already exists"; if still absent, consider retrying with the new revision.
4. **Every code path that writes the map must update `revision` consistently.** A single writer updating an entry with an unconditional `UPDATE` without changing `revision` breaks the protocol's guarantee.

Do not write `revision = revision + 1` as an ordinary arithmetic increment on an `int` column in `SET`: Cassandra does not support counter-style updates on an arbitrary `int` column that way. The application computes `new_revision = old_revision + 1` and sends the new value; in production, handle version overflow and initialization explicitly.

**Limitation to understand:** This version-based CAS checks **the entire row**. Two clients modifying two different map keys still contend on `revision`, even though each entry could update independently under ordinary mutations. This trade-off can be acceptable for small maps with low write rates, but quickly becomes a bottleneck on rows with high writer concurrency.

## 9. Alternative Design: One Row per Key/Value to CAS Directly on the Key

If each key needs **independent existence checks, deletes, TTLs, ownership, or history**, promote it into the primary key of a dedicated read table:

```sql
CREATE TABLE app.preference_by_user_key (
    user_id uuid,
    preference_key text,
    preference_value text,
    PRIMARY KEY ((user_id), preference_key)
);

-- If row (user_id, preference_key) does not exist yet, insert a new key.
INSERT INTO app.preference_by_user_key
    (user_id, preference_key, preference_value)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'theme',
    'dark'
)
IF NOT EXISTS;

-- Update the value only if the current value matches the condition.
UPDATE app.preference_by_user_key
SET preference_value = 'light'
WHERE user_id = 11111111-1111-4111-8111-111111111111
  AND preference_key = 'theme'
IF preference_value = 'dark';

-- Read a specific key via the full primary key.
SELECT preference_value
FROM app.preference_by_user_key
WHERE user_id = 11111111-1111-4111-8111-111111111111
  AND preference_key = 'theme';

-- Or read all keys for a user (provided partition size is bounded).
SELECT preference_key, preference_value
FROM app.preference_by_user_key
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

In this model, `INSERT ... IF NOT EXISTS` genuinely checks **the business key** `(user_id, preference_key)` because each key is its own row. `UPDATE ... IF preference_value = 'dark'` also checks that row's current value directly. No shared `revision` is needed solely to stop two writers from altering the same entry. In return, the application manages multiple rows and must watch partition size if a single user could accumulate huge numbers of preferences.

If row pagination is needed, clustering key `preference_key` orders rows by key; that order is **not user drag-and-drop order**. If you need to find all users having a given key/value pair, this table still does **not** serve that query direction directly; you need an additional attribute-partitioned table or a workload-appropriate indexing strategy.

## 10. LWT, Paxos, and Consistency Levels

In Cassandra, statements with `IF` trigger a **lightweight transaction** that evaluates the condition and decides the write across the affected data scope using a Paxos-style consensus protocol. This path adds extra replica round trips compared to a plain `UPDATE`, so **coordination latency and cost are typically higher**. Do not use LWT on every operation simply to "be safer" when there is no business condition requiring it.

Two consistency concepts must be distinguished:

- **Regular consistency level** (`ONE`, `LOCAL_QUORUM`, `QUORUM`, ...): governs normal read/write replica acknowledgments per replication and datacenter scope.
- **Serial consistency** (`SERIAL`, `LOCAL_SERIAL`): governs the consensus phase of conditional operations; choose it according to datacenter scope and deployment rules.

LWT does not automatically create general ACID transactions across multiple tables or arbitrary partitions. If a workflow must update both `user_preferences` and a reverse lookup table, design cross-table consistency and handle failures and intermediate states deliberately. When an LWT times out, the client must determine **whether the outcome was accepted**, rather than assuming the condition never passed.

A practical rule of thumb: use a normal `UPDATE settings['k'] = ...` when overwriting is acceptable under business rules; use LWT when **a condition is part of the data contract** (do not overwrite if present, or transition only from an expected value/version).

## 11. Concurrency: Two Different Keys vs. the Same Key

Suppose two clients A and B both read the map `{'language':'vi'}`.

### 11.1. Two Different Keys: Per-Entry Mutations

```sql
-- Client A:
UPDATE app.user_preferences
SET settings['theme'] = 'dark'
WHERE user_id = 11111111-1111-4111-8111-111111111111;

-- Client B:
UPDATE app.user_preferences
SET settings['timezone'] = 'Asia/Ho_Chi_Minh'
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

With a non-frozen map, entries are managed at key granularity, so two updates to different keys can coexist once replicas reconcile data. That is not true if A and B both rewrite **the entire map** from an old snapshot: one snapshot can shadow the entry added by the other client.

### 11.2. Same Key: Contention by Timestamp or Condition

```sql
-- Both update theme, but want different values:
UPDATE app.user_preferences SET settings['theme'] = 'dark'
WHERE user_id = 11111111-1111-4111-8111-111111111111;

UPDATE app.user_preferences SET settings['theme'] = 'light'
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Cassandra resolves competing writes using cell timestamp metadata and tie-breakers; the moment a user clicks a button **does not guarantee** winning order. If business logic requires writing only when the prior value has not changed, use a version check or a per-key row model. If your application supplies `USING TIMESTAMP` explicitly, understand clock skew and late-write implications; do not fabricate artificially large timestamps to force wins.

## 12. TTL, Tombstones, Compaction, and Repair with Maps

Each entry of a non-frozen map can be written with a TTL in its mutation:

```sql
-- Only the newly written banner entry receives the 600-second TTL from this statement.
UPDATE app.user_preferences USING TTL 600
SET settings['banner'] = 'trial'
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Other entries in the map do not inherit the 600-second TTL from this command. When a TTL expires or an entry is removed via `DELETE`, Cassandra must retain deletion metadata (*tombstones*) so replicas that have not yet seen the change do not bring deleted values back. Compaction can reclaim tombstones once safety conditions are met; repair schedules, settings like `gc_grace_seconds`, and replica state must all be considered.

If a map undergoes thousands of key updates/deletes per second on one row, numerous entries/tombstones and SSTable reconciliation can inflate read latency. If keys have complex lifecycles and unboundedly growing counts, moving to a separate table is the data-modeling fix rather than merely tuning compaction to compensate for an oversized collection.

### Does `frozen<map<K,V>>` Help Enforce Key Conditions?

`frozen<map<text,text>>` stores **the whole map as a single cell**; it does not support direct mutations like `settings['theme'] = 'light'`. To add or delete one key, the client must provide **the complete new snapshot**. Competing writes contend on the entire value, and TTL applies to the snapshot cell. It is a solid fit when a map is small, rarely modified, and always managed as an immutable versioned block, but it does not automatically solve "add only if key is absent."

## 13. Java Driver 4.x: Reading Maps, Assigning Entries, and Checking `[applied]`

The example below uses a `CqlSession` already configured with contact points, local datacenter, and appropriate authentication. In production, **cache and reuse prepared statements**. The code highlights two distinct operations: overwriting an entry and `revision`-based CAS.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.UUID;

class PreferenceRepository {
    private final CqlSession session;
    private final PreparedStatement patchKey;
    private final PreparedStatement updateIfVersion;

    PreferenceRepository(CqlSession session) {
        this.session = session;
        this.patchKey = session.prepare(
            "UPDATE app.user_preferences " +
            "SET settings[?] = ? WHERE user_id = ?"
        );
        this.updateIfVersion = session.prepare(
            "UPDATE app.user_preferences " +
            "SET settings[?] = ?, revision = ? " +
            "WHERE user_id = ? IF revision = ?"
        );
    }

    void upsertKey(UUID userId, String key, String value) {
        // Upsert: missing key is added, existing key is overwritten.
        session.execute(patchKey.bind(key, value, userId));
    }

    boolean updateIfRevision(
        UUID userId, String key, String value,
        int expectedRevision
    ) {
        int nextRevision = Math.addExact(expectedRevision, 1);
        BoundStatement statement = updateIfVersion.bind(
            key, value, nextRevision, userId, expectedRevision
        ).setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
         .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL);

        Row result = session.execute(statement).one();
        if (result == null) {
            throw new IllegalStateException("Missing LWT result");
        }
        return result.getBoolean("[applied]");
    }
}
```

**Implementation notes:**

- The `?` markers for map **key/value** are bind parameters, not column names; a `null` map key is invalid input. Whether subscript binding is supported depends on the CQL/driver version: if your running version rejects `settings[?]`, use a statement with a fixed key literal or the `settings = settings + ?` mutation passing a single-entry map parameter such as `Map.of(key, value)`.
- `LOCAL_QUORUM`/`LOCAL_SERIAL` are **examples** suited to multi-replica deployments within the same datacenter; your actual choice must reflect datacenter topology and consistency requirements.
- Consider the operation successful only when `[applied] = true`. When false, re-read state; if the call times out, do not assume the condition failed.
- All writers participating in version control must update `revision` using the same protocol. If one code path writes the map directly without bumping `revision`, CAS no longer protects all business mutations.
- `upsertKey` means **overwriting is allowed**; it does not replace an "add key only if it does not exist" workflow.

## 14. Case Exercises and Suggested Answers

**Scenario A — Missing key.** A user's row already exists with `settings={'language':'vi'}`. The application executes `UPDATE ... SET settings['theme']='dark' IF EXISTS`. Will the statement be rejected because `theme` is missing?  
**Hint:** No. `IF EXISTS` checks **the row**, not the key. Since the row exists, the new key can be added.

**Scenario B — Insert only if absent.** Two clients concurrently try to create `theme` for the first time. Both run `SELECT`, see the key is missing, and issue a regular `UPDATE`. Can you guarantee only one client wins?  
**Hint:** No. Use CAS on a `revision` column honored by every writer, or turn each key into its own row so `INSERT ... IF NOT EXISTS` checks the business key directly.

**Scenario C — Appears to be a no-op.** An application deletes key `never_seen` many times per second even though the key has never existed. Can you ignore the cost?  
**Hint:** You should not. Deletes can create entry tombstones, adding read and compaction work; inspect the workload and eliminate unnecessary deletes.

**Scenario D — Two different keys.** Client A changes `theme`, B changes `language`. Why does per-key patching carry less lost-update risk than rewriting the whole map from an old snapshot?  
**Hint:** Non-frozen maps manage entries by key; two mutations to different keys can coexist. Replacing the whole snapshot can shadow the other client's update.

**Scenario E — Many keys and differing TTLs.** A user has hundreds of thousands of keys, each needing its own TTL, search, and pagination. Is `frozen<map<text,text>>` suitable?  
**Hint:** No. Use separate rows with an appropriate query key and bucketing when needed. `frozen` makes per-key updates harder and provides no row-level pagination over elements.

**Scenario F — CAS failure.** A client reads `revision=7`, attempts a write with `IF revision=7`, and gets `[applied]=false`. Should it immediately force an unconditional write to avoid inconveniencing the user?  
**Hint:** No. Re-read, determine what changed the data, and apply a bounded conflict/retry policy; forcing a write can overwrite valid concurrent changes.

## 15. Pre-Production Design Checklist

1. **What is the read path?** Do you access `settings` by `user_id`, or do you need reverse lookups by key/value? Design the schema around actual queries.
2. **Maximum key count?** Is the collection strictly small and bounded? If not, consider separate tables and bucketing.
3. **What does a missing key mean?** Default value, uninitialized, deleted, or an error condition? Distinguish a missing row from a missing entry.
4. **Are overwrites allowed?** If yes, per-entry mutations may suffice. If not, use conditions on version/value and verify `[applied]`.
5. **Where does the condition apply?** `IF EXISTS`/`IF NOT EXISTS` defaults to **the row**; if you need per-key semantics, design the primary key or a CAS protocol accordingly.
6. **Who writes concurrently?** Do all writers share `revision`? Are there automatic retries? Are there dependencies on timestamps, TTL, or clock skew?
7. **How will it operate?** Monitor tombstones, repair, compaction, p95/p99 latency, and LWT impact on replicas before scaling write frequency.

## 16. Key Takeaways

- `map<K,V>` uses **unique keys** to identify entries; a normal `settings['key']` update is an **upsert**.
- A missing key can read back as `null`, but you must distinguish **missing key**, **null column**, and **nonexistent row**.
- `IF EXISTS`/`IF NOT EXISTS` checks **the row by primary key**, not automatically whether a sub-key exists inside a map.
- To enforce "add only if the key is absent," use **row-wide version-based CAS** across all writers, or model **each key as its own row** and use `INSERT ... IF NOT EXISTS`.
- LWT incurs Paxos/serial-consistency overhead and requires handling `[applied]`, timeouts, and conflicts; normal `QUORUM` consistency does not replace CAS.
- Deleting even an absent entry can create **tombstones**; compaction and repair are essential to distributed Cassandra operations.
- Collections should stay **small and bounded**. When you need reverse queries, independent TTLs/conditions, pagination, or unboundedly growing keys, design a query-driven table with appropriate partition and clustering keys.
