# Mutation Timestamps and the Last-Write-Wins Rule in Apache Cassandra

## 1. Context: Multiple Replicas Can Receive Different Versions

Apache Cassandra is a **distributed wide-column** database. A partition is stored across multiple replicas according to the replication configuration; writes can arrive at those replicas in different orders, especially when there is network latency, retries, or concurrent writes from multiple applications. Cassandra needs a deterministic rule to choose a value when versions conflict.

The default rule for regular data is **last-write-wins (LWW)**: for the same data cell (*cell*), the version with the **higher mutation timestamp** takes precedence. The word "last" here refers to the **write timestamp**, not necessarily the operation that arrived at a replica last or the operation the user performed last in wall-clock time.

For example, the same customer has a `display_name` column written from two places:

| Write command | Replica arrival time | Mutation timestamp (microseconds) | Value |
|---|---|---:|---|
| A | Arrived later | `1760000000001000` | `An` |
| B | Arrived earlier | `1760000000002000` | `Bình` |

After the versions are reconciled, **`Bình` wins** because B's timestamp is higher, even though A arrived later. This is the core concept for understanding write conflicts in Cassandra.

## 2. What Is a Mutation Timestamp?

A **mutation** is a data modification, such as `INSERT`, `UPDATE`, or `DELETE`. Each regular data cell is assigned a 64-bit integer **write timestamp**, representing the number of **microseconds since the Unix epoch (1970-01-01 00:00:00 UTC)**. Cassandra uses this number when reconciling data versions across replicas.

- **Not an application column:** `created_at timestamp` or `updated_at timestamp` columns that you design yourself are just table data; Cassandra does not automatically use those columns for LWW ordering.
- **Not the time received on disk:** a write that arrives at a node later can still lose if its mutation timestamp is lower.
- **Can be supplied from multiple places:** CQL specifies it via `USING TIMESTAMP`, the driver attaches a query timestamp, or the coordinator generates a default timestamp if the request does not provide one. The actual behavior depends on the driver configuration and the write path.
- **Microsecond resolution:** unlike the CQL `timestamp` data type, which usually represents time at millisecond resolution. Confusing milliseconds with microseconds can cause unexpected write ordering.
- **Applied at the cell level:** a single `UPDATE` statement can write multiple cells with the same timestamp, yet columns within a row can still hold different timestamps from different updates.

When you want to inspect the actual timestamp attached to a regular column, use the CQL `writetime()` function:

```sql
SELECT customer_id, display_name, writetime(display_name)
FROM customer_profiles
WHERE customer_id = 11111111-1111-1111-1111-111111111111;
```

`writetime(display_name)` returns the timestamp of the existing cell (in microseconds). Do not use this function on primary key columns or counters; deleted or nonexistent cells are typically represented as `null` in the query result.

## 3. How Does the LWW Rule Work?

Suppose two mutations modify the **same cell** of the same partition/row:

1. Cassandra compares the mutation timestamps of the versions.
2. **The higher timestamp wins** and becomes the visible value once the replicas have reconciled.
3. If two versions have **equal timestamps**, Cassandra uses another deterministic tie-breaking rule; in the case of a write versus a tombstone at the same timestamp, **the tombstone takes precedence**. For two different live values, you must not assume the command sent later will win. Applications should avoid intentionally creating conflicting writes with the same timestamp.

The key point is that **the unit of conflict resolution is the cell**, not the entire row. If request X changes `display_name` at timestamp `T2` and request Y changes `email` at `T3`, both changes can coexist in the row because they affect two different cells.

```text
                 Partition: customer_id = ...
                         |
              +----------+----------+
              |                     |
    display_name (T2)           email (T3)
        "Bình"              "binh@example.com"

    Each cell keeps the winning version according to its own timestamp.
```

When an operation writes multiple columns, those columns are assigned the timestamp corresponding to that mutation; however, LWW does **not** turn the entire row into an atomically replaced object. For collection types, Cassandra also has specific details around cells/elements and `frozen` types, so do not generalize the simple cell example to all data structures.

## 4. CQL Hands-On: Observing Older Writes, Newer Writes, and Deletes

The following commands run in a **test keyspace** that has already been created and selected with `USE <keyspace>;`. Use a `customer_id` that has never been written before so results are not affected by timestamps left over from another run.

### Step 1 — Create the Table and Write Initial Data

```sql
CREATE TABLE IF NOT EXISTS customer_profiles (
    customer_id uuid PRIMARY KEY,
    display_name text,
    email text
);

INSERT INTO customer_profiles (customer_id, display_name, email)
VALUES (
    11111111-1111-1111-1111-111111111111,
    'An',
    'an@example.com'
)
USING TIMESTAMP 1760000000000000;

SELECT display_name, writetime(display_name),
       email, writetime(email)
FROM customer_profiles
WHERE customer_id = 11111111-1111-1111-1111-111111111111;
```

Both the `display_name` and `email` cells carry the timestamp `1760000000000000`.

### Step 2 — Attempt a Write with an **Older** Timestamp

```sql
UPDATE customer_profiles
USING TIMESTAMP 1759999999999000
SET display_name = 'Bình'
WHERE customer_id = 11111111-1111-1111-1111-111111111111;

SELECT display_name, writetime(display_name)
FROM customer_profiles
WHERE customer_id = 11111111-1111-1111-1111-111111111111;
```

The result is still **`An`**, and the timestamp is still `1760000000000000`: the `'Bình'` version has a lower timestamp, so it cannot replace the winning cell, even though the `UPDATE` statement executed successfully.

### Step 3 — Write with a **Newer** Timestamp

```sql
UPDATE customer_profiles
USING TIMESTAMP 1760000000002000
SET display_name = 'Bình'
WHERE customer_id = 11111111-1111-1111-1111-111111111111;

SELECT display_name, writetime(display_name),
       email, writetime(email)
FROM customer_profiles
WHERE customer_id = 11111111-1111-1111-1111-111111111111;
```

Now `display_name = 'Bình'` has timestamp `1760000000002000`, while `email = 'an@example.com'` still carries the old timestamp. This is a direct demonstration of cell-level LWW.

### Step 4 — Deletes Create Tombstones

```sql
DELETE display_name FROM customer_profiles
USING TIMESTAMP 1760000000003000
WHERE customer_id = 11111111-1111-1111-1111-111111111111;

-- Written later in wall-clock time, but the timestamp is older than the tombstone.
UPDATE customer_profiles
USING TIMESTAMP 1760000000002500
SET display_name = 'Chi'
WHERE customer_id = 11111111-1111-1111-1111-111111111111;

SELECT display_name, email
FROM customer_profiles
WHERE customer_id = 11111111-1111-1111-1111-111111111111;
```

`display_name` remains `null`; the `email` column still has data. `DELETE` does not merely erase a string from a record—it creates a **tombstone** to mark the data as deleted. A tombstone with timestamp `1760000000003000` shadows older versions (and live versions with an equal timestamp), preventing replicas holding stale data from resurrecting the value during synchronization.

Only a write with a timestamp **higher than the tombstone** can make a visible value appear again:

```sql
UPDATE customer_profiles
USING TIMESTAMP 1760000000004000
SET display_name = 'Chi'
WHERE customer_id = 11111111-1111-1111-1111-111111111111;
```

> **Experiment note:** The timestamps above are intentionally fixed to illustrate conflict ordering. Do not reuse those numbers as manual timestamps for real data. If you have run tests multiple times on the same primary key, use a new key to avoid leftover tombstones or timestamps from previous runs affecting the results.

## 5. How LWW Interacts with Replication and Consistency Levels

With replication factor `RF = 3`, a partition has three replicas. If you write at `CL = ONE`, the coordinator can acknowledge once that number of replicas satisfies the consistency level; other replicas may not see the new version immediately. On read, Cassandra reconciles the data retrieved from the replicas participating in the query and uses timestamps to resolve differing versions. Replica repair and synchronization mechanisms bring the data into a consistent state over time.

```text
       Application A                      Application B
       writes name=An                     writes name=Bình
       ts=100                             ts=200
             \                           /
              \                         /
               v                       v
                  Cassandra cluster
               /          |          \
           Replica 1   Replica 2    Replica 3
           sees ts=100 sees ts=200  temporarily stale
               \          |          /
                +--- reconciliation -+
                       ts=200 wins
```

**Consistency level** and **LWW** answer two different questions:

| Mechanism | Question answered | What it does not guarantee |
|---|---|---|
| `ONE`, `QUORUM`, `ALL` on write/read | How many replicas must participate or respond for the operation to meet the requested consistency level? | Does not automatically make a lower timestamp win. |
| Last-write-wins | When multiple versions of the same cell conflict, which version wins? | Does not guarantee the winning write is the last operation sent by a user in wall-clock time. |
| Lightweight transaction (`IF ...`, Paxos) | Can conditions be checked and updates coordinated when stricter ordering/conditions are needed? | Not free: adds latency and coordination overhead. |

For example, raising the write consistency level to `ALL` does not rescue a new update whose timestamp is lower than an existing tombstone. Even overlapping `QUORUM` read/write pairs do not change the rule of choosing versions by timestamp. When business logic requires **compare-and-set**, conditional overwrite protection, or state transitions that must progress in a strict order, consider **lightweight transactions (LWT)** and appropriate key design rather than relying solely on LWW.

## 6. Clock Skew Timestamps and Hard-to-Detect Bugs

LWW depends directly on the timestamp placed into the mutation by the client or coordinator. Therefore, clock skew across machines can affect data for much longer than transient network delays.

**Future timestamp scenario:** machine A has a fast clock and writes `'Approved'` with a future timestamp `T+10 minutes`. Machine B has an accurate clock and updates `'Cancelled'` one minute later in real time, yet B's timestamp is still smaller than A's. LWW continues to pick `'Approved'`. Raising `CL` cannot fix this ordering.

Operational principles:

1. Synchronize clocks across hosts/coordinators using a time synchronization service, and monitor **clock skew**.
2. Only supply `USING TIMESTAMP` manually when there is an explicit ordering requirement from the event source, and ensure the unit is **microseconds**. If multiple services use self-generated timestamps, standardize the source, unit, and conflict-handling rules.
3. In Java applications, check the Cassandra driver's **timestamp generator** configuration. Some drivers generate timestamps client-side, which can guarantee monotonic increases within a single process; that does not automatically solve clock skew across multiple machines.
4. When retrying the same event, reuse a stable mutation timestamp if business logic requires idempotency. Generating a new timestamp on every retry can accidentally make an older event overwrite a newer one.
5. Avoid assigning excessively large or future timestamps. They can cause subsequent normal writes to be shadowed continuously.

### Java Example

Assuming the application already has a `CqlSession` connected to the cluster via the DataStax/Apache Cassandra Java Driver, you can pass the source timestamp through a prepared statement:

```java
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public class CustomerProfileRepository {
    private final CqlSession session;
    private final PreparedStatement updateName;

    public CustomerProfileRepository(CqlSession session) {
        this.session = session;
        this.updateName = session.prepare(
            "UPDATE customer_profiles " +
            "USING TIMESTAMP ? " +
            "SET display_name = ? WHERE customer_id = ?"
        );
    }

    public void updateName(UUID customerId, String name, long eventTimeMicros) {
        session.execute(updateName.bind(eventTimeMicros, name, customerId));
    }
}
```

`eventTimeMicros` must be a **`long` representing microseconds**, computed and controlled according to business policy. Do not pass `System.currentTimeMillis()` directly to this parameter: its return value is in **milliseconds** and will be off by roughly a factor of 1,000 compared to current microsecond timestamps. If there is no reason to control timestamps manually, let the driver/coordinator apply the configured timestamp policy.

## 7. Distinguishing Mutation Timestamps, TTL, and Other Time Concepts

In the **Timestamps and TTL** chapter, distinguish three concepts:

| Concept | Role | Example |
|---|---|---|
| **Mutation timestamp** | Determines which cell version wins in a conflict | `USING TIMESTAMP 1760000000002000`, `writetime(display_name)` |
| **TTL (time to live)** | Specifies how long data lives before expiring and being treated as deleted | `USING TTL 3600` makes a cell expire after about one hour |
| **CQL `timestamp` column** | Stores an application-level point in time for querying | `created_at timestamp`, `event_time timestamp` |

For example, you can write `INSERT ... USING TIMESTAMP <microseconds> AND TTL 3600`: the timestamp governs version resolution, while the TTL governs data lifecycle. An expired value is treated like expired/tombstoned data in Cassandra. Do not think of TTL as a "newer timestamp" or assume that having a TTL makes a mutation always win over other mutations.

**Important exception:** `counter` columns use their own update mechanism and do not follow standard LWW writes; do not attach `USING TIMESTAMP` manually to counter updates. LWT operations (`IF NOT EXISTS`, `IF ...`) also have their own coordination rules and must be evaluated separately when conditional correctness is required.

## 8. How to Diagnose a Write That "Succeeded, Yet the New Value Isn't Visible"

When an `UPDATE` returns successfully yet `SELECT` still shows the old value, check in the following order:

| Step | Check | Reason |
|---|---|---|
| 1 | Verify the exact keyspace, partition key, clustering key, and updated column | Two mutations only conflict when targeting the exact same data location. |
| 2 | `SELECT value, writetime(value)` on a live column | See the currently winning version and its mutation timestamp. |
| 3 | Inspect `USING TIMESTAMP`, the driver's timestamp generator, and event logs | Look for wrong-unit, older, or future timestamps. |
| 4 | Check any `DELETE` statements and TTLs that may have been applied | Tombstones can shadow older writes; `writetime()` does not directly show the timestamp of a deleted tombstone. |
| 5 | Cross-check RF, consistency level, unavailable replicas, and repair status | Distinguish version conflicts from replicas that have not yet synchronized. |

Tombstones also interact with **compaction**, tombstone retention time (`gc_grace_seconds` where applicable), and **repair**. Purging tombstones too early while a replica still holds old data can cause deleted data to reappear (*zombie data*). Therefore, planning replica repair intervals and tombstone cleanup policies is part of Cassandra operations, not merely storage optimization.

## 9. Self-Check Questions

**Exercise 1.** For the same cell, replica X has `'A'` at timestamp `500`, and replica Y has `'B'` at timestamp `700`. X received its mutation after Y. Which version wins? **Answer:** `'B'`, because `700 > 500`.

**Exercise 2.** The `name` column was written at timestamp `900`; the `email` column was updated at timestamp `1000`. Does an older command rewriting `name` at timestamp `800` lose `email`? **Answer:** No. `name` keeps the version at timestamp `900`; `email` keeps the version at timestamp `1000`, because they are two separate cells.

**Exercise 3.** A tombstone deleting `name` has timestamp `1200`, and later a client retries writing `name` with timestamp `1100`. Can it resurrect the name? **Answer:** No; the tombstone still wins. A valid new mutation with a higher timestamp is required, and you must also evaluate whether business logic actually permits restoring deleted data.

**Exercise 4.** Service A always supplies microseconds, while service B passes milliseconds into `USING TIMESTAMP`. What is the consequence? **Answer:** B's timestamps are roughly 1,000 times smaller than the current time, so B's writes typically lose to versions written with proper timestamps. Standardize the unit or remove manual assignment.

**Key takeaway:** Cassandra reconciles versions by **cell-level mutation timestamp**; the higher timestamp wins, tombstones shadow older versions, and that order can differ from the real-world order of operations. Query-driven table design, clock skew management, consistency level selection, and considering LWT when conditional updates are needed are related decisions, each serving a distinct role.
