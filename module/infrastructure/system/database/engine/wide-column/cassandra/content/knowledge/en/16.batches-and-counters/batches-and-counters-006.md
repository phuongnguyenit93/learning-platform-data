# Timestamps in BATCH and Limits on Inferring Statement Order

In Apache Cassandra, `BATCH` helps group multiple CQL statements into one write request. However, **the order in which statements are listed inside a BATCH is not a guaranteed overwrite order**, and `BATCH` does not turn the statements into an SQL transaction with sequential execution order. To understand the final outcome, you must distinguish between **mutation timestamps**, **conflict resolution rules across records**, and **the guarantees of each BATCH type**.

This lesson belongs to the **BATCH and counters** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. The examples are set in the context of distributed Cassandra, the wide-column model, query-driven design, replication, and consistency levels; the goal is to know when you can reason from timestamps and when you must redesign writes to avoid relying on statement order.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain what a write timestamp in Cassandra is, its unit of measurement, and its role when two mutations touch the same cell.
- Distinguish between the default BATCH timestamp, a BATCH-level timestamp, and a per-statement timestamp.
- State why execution order, business order, or isolation cannot be inferred merely from statement order inside a BATCH.
- Use `WRITETIME` to inspect the timestamp of regular columns and recognize the limitations of that check.
- Design writes, retries, and counter handling so they do not depend on a false ordering assumption.

## 2. Timestamps Are Record Metadata, Not Statement Sequence Numbers

Cassandra stores mutations in a distributed model: data is identified by **partition key**, rows within a partition are ordered by **clustering key**, and regular columns hold values along with write metadata. For regular columns, a mutation's timestamp is one basis Cassandra uses to resolve conflicts between versions of the same cell during reads and data reconciliation across replicas.

- Cassandra timestamps are typically expressed in **microseconds since the Unix epoch (UTC)**. For example, `1700000000000200` is a microsecond value, not Java's millisecond `System.currentTimeMillis()`.
- **A higher timestamp generally wins** when two values for the same cell compete; this rule is commonly called *last-write-wins* (LWW). "Last" here refers to **the timestamp used for data reconciliation**, not necessarily the last request to arrive at the server.
- Same row does not mean same cell: two statements updating **two different columns** can coexist even with the exact same timestamp.
- If timestamps are **equal** on the same cell, Cassandra must apply tie-breaking rules (including favoring tombstones over live values, and comparing values for two live values). **Never use statement order in a BATCH to predict the winner.**

Consider two records arriving in real-world time as follows:

| Request Arrival Time | Mutation on `status` Cell | Write Timestamp | Reconciliation Outcome |
|---|---|---|---|
| Arrived earlier | `status = 'PAID'` | `1700000000000200` | Wins |
| Arrived later | `status = 'CREATED'` | `1700000000000100` | Loses due to smaller timestamp |

After replicas converge, the result is `PAID`, even though the `CREATED` request arrived later. Timestamps may be assigned by the coordinator or supplied by the client/driver via the protocol or CQL; thus **clock skew**, manually assigned timestamps, or retries can cause timestamp order to differ from real-world event order.

> **Important Boundary:** A timestamp is metadata for cell-level conflict resolution. It is not a transaction ID, not a reliable business sequence number, and does not confirm which statement finished executing before another.

## 3. How Are Timestamps Assigned in a BATCH?

### 3.1. Without Declaring `USING TIMESTAMP`

A BATCH has a default timestamp used for mutations that do not declare their own timestamp. With regular CQL statements, statements in the same BATCH share that default timestamp; the actual timestamp may be provided at the request level by the driver/client or assigned during processing inside Cassandra.

```sql
BEGIN BATCH
    UPDATE batch_lab.order_state
    SET status = 'PAID'
    WHERE order_id = 00000000-0000-0000-0000-000000000006;

    UPDATE batch_lab.order_state
    SET updated_by = 'payment-service'
    WHERE order_id = 00000000-0000-0000-0000-000000000006;
APPLY BATCH;
```

Two different columns receive mutations with the same default timestamp, but **you cannot infer from that that the `status` statement ran before the `updated_by` statement**. The two values should simply be viewed as two parts of the write outcome.

### 3.2. Declaring a BATCH-Level Timestamp

You can set an explicit timestamp for the BATCH using `USING TIMESTAMP`:

```sql
BEGIN BATCH USING TIMESTAMP 1700000000000300
    UPDATE batch_lab.order_state
    SET status = 'PROCESSING'
    WHERE order_id = 00000000-0000-0000-0000-000000000006;

    UPDATE batch_lab.order_state
    SET updated_by = 'worker-1'
    WHERE order_id = 00000000-0000-0000-0000-000000000006;
APPLY BATCH;
```

Here, mutations that do not declare their own timestamp receive `1700000000000300`. That is a **write timestamp**, not a signal that Cassandra will process the first statement before the second. Setting a fixed timestamp for every run can also produce multiple writes with identical timestamps; proactively avoid conflicts if your program reuses this value.

### 3.3. Declaring a Statement-Level Timestamp

A mutation can specify `USING TIMESTAMP` directly inside an `INSERT`, `UPDATE`, or `DELETE` statement. The statement-level timestamp is used for that mutation and overrides the BATCH's default timestamp for that corresponding mutation:

```sql
BEGIN BATCH USING TIMESTAMP 1700000000000300
    UPDATE batch_lab.order_state
    USING TIMESTAMP 1700000000000500
    SET status = 'DONE'
    WHERE order_id = 00000000-0000-0000-0000-000000000006;

    UPDATE batch_lab.order_state
    USING TIMESTAMP 1700000000000400
    SET updated_by = 'worker-2'
    WHERE order_id = 00000000-0000-0000-0000-000000000006;
APPLY BATCH;
```

When read back, `status` and `updated_by` can have two different timestamps despite being in the same row and same BATCH. Evaluate timestamps **per updated cell**; do not take a single number and attribute it to "the entire row."

| Scope | Syntax | Meaning |
|---|---|---|
| Default | `BEGIN BATCH ... APPLY BATCH` | Uses the request/BATCH default timestamp if a mutation does not declare its own |
| BATCH-level | `BEGIN BATCH USING TIMESTAMP <microseconds>` | Sets the shared default timestamp for mutations in the BATCH |
| Statement-level | `UPDATE ... USING TIMESTAMP <microseconds> SET ...` | Specifies the timestamp for that statement's mutation |

## 4. Why Can't Order Be Inferred from Statements in a BATCH?

Consider an example that deliberately **writes two different values to the same cell**:

```sql
BEGIN BATCH USING TIMESTAMP 1700000000000600
    UPDATE batch_lab.order_state
    SET status = 'QUEUED'
    WHERE order_id = 00000000-0000-0000-0000-000000000006;

    UPDATE batch_lab.order_state
    SET status = 'RUNNING'
    WHERE order_id = 00000000-0000-0000-0000-000000000006;
APPLY BATCH;
```

**Do not interpret this as `RUNNING` being guaranteed to win because it appears after `QUEUED`.** Both mutations compete on the same cell with the same timestamp, so BATCH syntax cannot be treated as a state-transition sequence. Even if a given Cassandra version yields a consistent outcome in a small test, that behavior is **not a business ordering contract** that applications may rely on.

Common misconceptions:

| Claim | Assessment | Explanation |
|---|---|---|
| "The second statement in a BATCH always beats the first statement." | False | Textual order does not define overwrite precedence; reconciliation uses timestamps and tie-breaking rules |
| "Same timestamp means they ran at the exact same instant." | False | Shared timestamps are write metadata, not a measurement of internal execution scheduling |
| "A higher timestamp means the business action happened later." | Not guaranteed | Clients can set timestamps manually; clocks across machines can drift |
| "Logged BATCH means everything is read like an SQL transaction." | False | BATCH does not provide isolation for concurrent reads |
| "Writing two different columns forces them to overwrite each other." | False | LWW resolves per conflicting cell, not across the entire row |

### 4.1. Atomicity, Isolation, and Statement Ordering Are Three Different Concepts

**Logged BATCH** supports atomicity in terms of eventual application of mutations: the batchlog mechanism helps recover/complete missing parts on failure. That **does not mean** concurrent readers only ever see the state "before the whole BATCH" or "after the whole BATCH." Especially across multiple partitions, a reader may observe data at different points in time.

**Unlogged BATCH** avoids batchlog overhead but does not guarantee atomicity across multiple partitions when errors occur. Mutations within the same partition have Cassandra's partition-level atomicity guarantees, yet **still do not create a business execution order for the statements**.

**Consistency levels** such as `ONE`, `QUORUM`, and `ALL` define how many replicas must acknowledge a read/write operation; they **do not add sequential ordering to statements**, do not turn a BATCH into a multi-partition transaction, and do not turn timestamps into business sequence numbers. Similarly, clustering keys define how rows are sorted when queried **within a partition**, not the order of `UPDATE` commands inside a BATCH.

### 4.2. Multi-Partition Example

```sql
BEGIN LOGGED BATCH
    UPDATE batch_lab.order_state
    SET status = 'SHIPPED'
    WHERE order_id = 00000000-0000-0000-0000-000000000006;

    UPDATE batch_lab.order_state
    SET status = 'SHIPPED'
    WHERE order_id = 00000000-0000-0000-0000-000000000007;
APPLY BATCH;
```

Two `order_id` values mean two partitions. The logged batch mechanism helps drive full application of mutations after a failure, but concurrent readers must not assume they will always observe the updated state of **both partitions at the same time**. Multi-partition logged batches also increase network and batchlog write overhead; do not use them to "speed up" bulk independent writes, and do not treat them as a general solution for multi-record consistency.

## 5. CQL Practice: Distinguishing Timestamps from Execution Order

This lab is intended for a learning Cassandra environment. For a single-node cluster, the keyspace below is purely illustrative; when deploying multi-node clusters, choose a replication strategy and replication factor suited to your real topology.

### Step 1: Create Sample Data

```sql
CREATE KEYSPACE IF NOT EXISTS batch_lab
WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};

CREATE TABLE IF NOT EXISTS batch_lab.order_state (
    order_id uuid PRIMARY KEY,
    status text,
    updated_by text
);

INSERT INTO batch_lab.order_state (order_id, status, updated_by)
VALUES (00000000-0000-0000-0000-000000000006, 'CREATED', 'api')
USING TIMESTAMP 1700000000000100;
```

### Step 2: Write a Value That Arrives Later with a Lower Timestamp

```sql
UPDATE batch_lab.order_state
USING TIMESTAMP 1700000000000200
SET status = 'PAID'
WHERE order_id = 00000000-0000-0000-0000-000000000006;

UPDATE batch_lab.order_state
USING TIMESTAMP 1700000000000150
SET status = 'RETRY_CREATED'
WHERE order_id = 00000000-0000-0000-0000-000000000006;

SELECT status, WRITETIME(status)
FROM batch_lab.order_state
WHERE order_id = 00000000-0000-0000-0000-000000000006;
```

**Expected:** `status = 'PAID'` and `writetime(status) = 1700000000000200`. The `RETRY_CREATED` statement ran later in terms of request dispatch, but it carries a lower timestamp and therefore does not override the winning value. To keep results reproducible, use a fresh `order_id` if you have previously run experiments with higher timestamps.

### Step 3: Write Two Columns in the Same BATCH and Observe Metadata

```sql
BEGIN BATCH USING TIMESTAMP 1700000000000300
    UPDATE batch_lab.order_state
    SET status = 'PROCESSING'
    WHERE order_id = 00000000-0000-0000-0000-000000000006;

    UPDATE batch_lab.order_state
    SET updated_by = 'worker-1'
    WHERE order_id = 00000000-0000-0000-0000-000000000006;
APPLY BATCH;

SELECT status, updated_by,
       WRITETIME(status), WRITETIME(updated_by)
FROM batch_lab.order_state
WHERE order_id = 00000000-0000-0000-0000-000000000006;
```

**Expected:** Both columns have timestamp `1700000000000300`; this is evidence of **identical write metadata**, not evidence of which statement ran first.

### Step 4: Write with Separate Timestamps on Each Statement

```sql
BEGIN BATCH USING TIMESTAMP 1700000000000300
    UPDATE batch_lab.order_state
    USING TIMESTAMP 1700000000000500
    SET status = 'DONE'
    WHERE order_id = 00000000-0000-0000-0000-000000000006;

    UPDATE batch_lab.order_state
    USING TIMESTAMP 1700000000000400
    SET updated_by = 'worker-2'
    WHERE order_id = 00000000-0000-0000-0000-000000000006;
APPLY BATCH;

SELECT status, updated_by,
       WRITETIME(status), WRITETIME(updated_by)
FROM batch_lab.order_state
WHERE order_id = 00000000-0000-0000-0000-000000000006;
```

**Expected:** `status = 'DONE'` with timestamp `1700000000000500`; `updated_by = 'worker-2'` with timestamp `1700000000000400`. Each column reconciles **its own** versions.

### What `WRITETIME` Helps With and What It Does Not

`WRITETIME(column)` returns the timestamp of the currently readable regular column value. It is an appropriate tool for inspecting the metadata in the examples above, but it is not enough to reconstruct a full history:

- It does not reveal execution order, request send/receive order, or when each replica finished writing.
- It does not reveal all overwritten versions; Cassandra is not an audit log system just by virtue of `WRITETIME`.
- It does not have the same meaning for primary keys or counters; when a value has been deleted, you cannot simply read `WRITETIME` of a no-longer-visible value to reconstruct the full tombstone history.
- If a client-supplied timestamp is wrong or deliberately set too high, the outcome can contradict real-world chronological order. Stored data may remain dominated by that timestamp until a newer mutation with a higher timestamp wins.

## 6. Special Case: Counters

**Counters** must not be interpreted under the regular-column model where "the highest value by `USING TIMESTAMP` wins." Counters use a dedicated increment/decrement mechanism; `COUNTER BATCH` is for counter mutations, must not mix counter mutations with regular mutations, and **does not use `USING TIMESTAMP` to impose ordering on counter increments/decrements**.

```sql
-- Assumes table batch_lab.page_stats already exists
-- with page_id uuid PRIMARY KEY, views counter.
BEGIN COUNTER BATCH
    UPDATE batch_lab.page_stats
    SET views = views + 1
    WHERE page_id = 00000000-0000-0000-0000-000000000006;
APPLY BATCH;
```

Counter increments **are not idempotent like reassigning a fixed value**. On a timeout where you do not know whether the update was applied, resending the same increment can cause double-counting. Design retries and deduplication mechanisms according to business requirements; do not expect BATCH-level timestamps to solve this.

## 7. Designing Java and CQL to Avoid Depending on BATCH Ordering

1. **Write the final state once:** If a workflow transitions from `CREATED` to `PAID` in a single operation, write only the target state to the `status` column; do not put two updates to the same cell inside a BATCH to simulate sequential steps.
2. **Separate event history from current state:** If you need to record `CREATED → PAID → SHIPPED`, use an event table with a clear business ordering key (e.g., `event_id`, `event_version`, or an application-level sequence) alongside a current-state table for queries. Do not treat write timestamps as the sole source of truth for event ordering.
3. **When concurrent condition checks are needed, consider LWT:** `UPDATE ... IF ...` (lightweight transaction) can guard conditional updates within partition scope as supported by Cassandra; evaluate Paxos overhead and operational limits. A standard BATCH does not replace this kind of concurrency control.
4. **Control client-generated timestamps in Java:** If using the Java driver and supplying timestamps manually, ensure **microsecond** units, consistent clock rules, and avoid accidentally passing milliseconds. Evaluate how the driver configures its timestamp generator and retries; unless specifically needed, avoid manually generating timestamps for every mutation.
5. **Batch for the right purpose:** Prefer grouping related writes in the same partition when appropriate. Across multiple partitions, only use a logged batch when eventual completion of the mutation group is genuinely needed; monitor batchlog cost and batch size.
6. **Design with the right consistency level:** Choose consistency levels based on read/write needs and replication. Even when using `QUORUM`, the application still needs to model business ordering and handle concurrent writes and timeouts explicitly.

A Java workflow that must guarantee "only advance from state A to state B if still in A" can use a conditional statement at the data layer:

```sql
UPDATE batch_lab.order_state
SET status = 'PAID'
WHERE order_id = 00000000-0000-0000-0000-000000000006
IF status = 'CREATED';
```

The application must inspect the `[applied]` result returned by Cassandra and have a policy for handling failed conditions. This serves a different purpose than a multi-statement write BATCH. Do not arbitrarily combine `USING TIMESTAMP` with conditional writes without verifying CQL constraints and your Cassandra version.

## 8. Self-Check Questions

1. In a BATCH containing two `UPDATE` statements on the same column with the same timestamp and different values, why can't you rely on statement position to determine the final value?
2. If a statement is sent later but carries a lower timestamp than an earlier statement, which value will Cassandra prefer when both update the same cell?
3. Does `BEGIN BATCH USING TIMESTAMP ...` prove that all statements executed simultaneously or that other readers only see all-or-nothing results?
4. What does `WRITETIME(status)` prove, and can it be used to reconstruct a complete state-transition history?
5. Why must counter increments and post-timeout retries be designed differently from a `SET status = 'PAID'` command?

**Reference Hints:** (1) Timestamps and tie-breaking determine the outcome; there is no statement-order contract; (2) the higher timestamp generally wins; (3) no, atomicity does not mean isolation or ordering; (4) it reads metadata of the current value, not an audit log; (5) increments can be re-applied and alter the total.

## Conclusion

In Cassandra, **BATCH groups mutations, timestamps drive data reconciliation, and business ordering must be guaranteed by your data model and application logic**. When you need to know which record wins, examine **the cell, the timestamp, and conflict resolution rules**. When you need a business-meaningful sequence of operations, use versioned/ordered events or appropriate conditional mechanisms rather than inferring order from statement positions inside `BEGIN BATCH ... APPLY BATCH`.
