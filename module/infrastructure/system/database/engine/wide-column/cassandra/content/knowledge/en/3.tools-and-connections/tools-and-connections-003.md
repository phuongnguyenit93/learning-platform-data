# CONSISTENCY, SERIAL CONSISTENCY, PAGING, and TRACING in cqlsh

## 1. What Do These Four Commands Help Control and Observe?

Apache Cassandra is a distributed wide-column database: a partition's data is placed on replicas according to the keyspace's replication configuration. A CQL statement is sent to a **coordinator** (the node receiving the request), which then coordinates with the replicas to read or write. Within **Tools and Connections**, four **cqlsh** commands help inspect different parts of this path:

| cqlsh Command | Question to Answer | Scope of Impact |
| --- | --- | --- |
| `CONSISTENCY` | How many replicas must respond for a read or write? | Consistency level for subsequent operations in the cqlsh session. |
| `SERIAL CONSISTENCY` | Which level is needed for the consensus phase of a conditional `IF` write? | Affects only the **serial/Paxos phase** of a lightweight transaction (LWT). |
| `PAGING` | How many result rows does cqlsh fetch and display at a time? | Pagination behavior for read queries in the session. |
| `TRACING` | What steps did the coordinator and replicas execute? | Enables/disables trace collection and printing for subsequent queries in the session. |

**Distinguish from the start:** `CONSISTENCY` and `SERIAL CONSISTENCY` relate to *consistency guarantees*, `PAGING` relates to *how results are fetched*, and `TRACING` relates to *observation and diagnostics*. Enabling tracing or lowering page size does not increase the replication factor; raising consistency does not fix a poorly designed partition key.

After this lesson, you will be able to:

1. Choose a consistency level suited to the replication factor, datacenter, and read/write requirements.
2. Run `INSERT ... IF NOT EXISTS` and `UPDATE ... IF ...` with serial consistency and read the `[applied]` column.
3. Use `PAGING` to iterate through results page by page, distinguishing page size from `LIMIT`.
4. Enable `TRACING` to inspect query execution flow, then disable it and interpret trace limitations.
5. Connect cqlsh actions with configuring queries in a Java application.

## 2. Preparing the Environment and Lab Data

Requirements: Cassandra is running, cqlsh can connect to the native port (default **9042**), and the account has permission to create keyspaces/tables in the learning environment. The examples below use **a single node with RF = 1** so they can be executed locally; explanations of multi-replica quorum will use a separate hypothetical scenario.

From the terminal:

~~~bash
cqlsh 127.0.0.1 9042
~~~

In cqlsh:

~~~sql
SHOW HOST;
SHOW VERSION;

CREATE KEYSPACE IF NOT EXISTS cqlsh_consistency_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

USE cqlsh_consistency_lab;

-- Table designed for the query: events of 1 device on 1 day.
CREATE TABLE IF NOT EXISTS events_by_device_day (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  temperature_c decimal,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

-- Small table to illustrate conditional updates (LWT).
CREATE TABLE IF NOT EXISTS device_lease (
  device_id text PRIMARY KEY,
  holder text,
  generation int
);
~~~

Events with the same `(device_id, event_day)` belong to the same **logical partition**. `event_time` and `event_id` are **clustering columns**, which distinguish and order rows within the partition. The query patterns in this lesson always filter on the full partition key; avoid adding `ALLOW FILTERING` to patch a query that does not fit the table structure.

Insert six rows so pagination will be clearly visible later:

~~~sql
INSERT INTO events_by_device_day
  (device_id, event_day, event_time, event_id, temperature_c)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:01:00Z',
        11111111-1111-4111-8111-111111111111, 25.1);

INSERT INTO events_by_device_day
  (device_id, event_day, event_time, event_id, temperature_c)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:02:00Z',
        22222222-2222-4222-8222-222222222222, 25.2);

INSERT INTO events_by_device_day
  (device_id, event_day, event_time, event_id, temperature_c)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:03:00Z',
        33333333-3333-4333-8333-333333333333, 25.3);

INSERT INTO events_by_device_day
  (device_id, event_day, event_time, event_id, temperature_c)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:04:00Z',
        44444444-4444-4444-8444-444444444444, 25.4);

INSERT INTO events_by_device_day
  (device_id, event_day, event_time, event_id, temperature_c)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:05:00Z',
        55555555-5555-4555-8555-555555555555, 25.5);

INSERT INTO events_by_device_day
  (device_id, event_day, event_time, event_id, temperature_c)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:06:00Z',
        66666666-6666-4666-8666-666666666666, 25.6);
~~~

Fixed UUIDs and timestamps ensure that re-running the lab does not create extra rows because `INSERT` with the same primary key is an **upsert** operation. If the table already exists with a different schema, `IF NOT EXISTS` does not update it automatically; if an error occurs, use `DESCRIBE TABLE` to inspect.

## 3. CONSISTENCY: Required Acknowledgment Level for Reads and Writes

### 3.1. How to Set It in cqlsh

~~~sql
-- Set for subsequent operations in this session.
CONSISTENCY ONE;

SELECT event_time, temperature_c
FROM cqlsh_consistency_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
LIMIT 6;

-- Example that should only be chosen after checking the real cluster's RF/datacenter.
CONSISTENCY LOCAL_QUORUM;

-- Return to the level suitable for the single-node lab.
CONSISTENCY ONE;
~~~

`CONSISTENCY` is a **cqlsh-specific command** that sets the consistency level for subsequent read/write operations in the **open cqlsh session**. It does not alter the keyspace, change the number of replicas, or affect other cqlsh sessions or Java applications. To check the syntax supported by your version of cqlsh, run `HELP CONSISTENCY;`.

### 3.2. Replication Factor and Quorum

**Replication factor (RF)** describes the number of copies of a partition according to the keyspace's replication strategy. **Consistency level (CL)** describes the acknowledgment requirement for *a single operation*. The two concepts are independent:

- With **RF = 3** in a datacenter and `LOCAL_QUORUM`, an operation requires at least **2 replicas** in that datacenter to respond successfully.
- `LOCAL_ONE` and `ONE` typically require only **1 replica** to respond (differing in local-datacenter scope).
- `ALL` requires all relevant replicas to respond, so one unavailable replica can cause the operation to fail.
- `QUORUM` calculates quorum across the total number of applicable replicas; `LOCAL_QUORUM` calculates it across replicas **in the local datacenter**. In multi-datacenter deployments, this difference is critical for latency and fault tolerance.
- The `ANY` level is for **writes**, accepting a hint when no replica is available; do not use it as a consistency level for read queries.

Examples of choices (assuming RF = 3 in one datacenter):

| Level | Required Responses for RF = 3 | Trade-off |
| --- | --- | --- |
| `ONE` | 1 replica | Lower latency; may read stale values when other replicas are not yet synchronized. |
| `LOCAL_QUORUM` | 2 replicas in the same datacenter | Balances availability and consistency within the datacenter. |
| `ALL` | All 3 replicas | Stricter requirement; more likely to fail if a replica is missing. |

In multi-datacenter systems, inspect the exact `NetworkTopologyStrategy` configuration and replica count **per datacenter** rather than mechanically applying this RF = 3 table.

#### Quorum Reads/Writes Do Not Equal SQL Transactions

In a single-datacenter RF = 3 model, writing with `W = 2` and reading with `R = 2` yields `W + R = 4 > 3`. The responding replica sets of the two operations must overlap, providing stronger read/write guarantees under appropriate conditions. However:

- Cassandra still uses cell timestamps/versions to reconcile versions; concurrent writes, clock skew, retries, and deletions can affect actual behavior.
- Quorum **does not create multi-row transactions**, does not guarantee an entire sequence of queries is atomic, and does not replace **LWT** when compare-and-set is required.
- `CONSISTENCY ONE` does not automatically mean writes fail when other replicas are slow; availability and record visibility depend on replica state and synchronization mechanisms.

**For the RF = 1 lab:** `ONE` only needs the single replica. `LOCAL_QUORUM` with RF = 1 in that datacenter also only needs one replica, so it does not demonstrate multi-node quorum behavior. Do not set `TWO` or `THREE` expecting a single-node lab to satisfy it: there are not enough replicas.

### 3.3. When Does an Operation Fail?

Possible errors include:

- `Unavailable`: the system determines that not enough replicas are currently available for the requested consistency.
- `ReadTimeout` or `WriteTimeout`: not enough responses arrived within the configured timeout window.
- `ReadFailure` or `WriteFailure`: replicas reported errors while processing the request.

**A write timeout does not prove the data was not written.** Some replicas may have applied the operation before the client received the timeout; before retrying, understand the CQL statement's idempotency. For conditional writes, avoid blind automatic retries without checking the outcome and data state.

## 4. SERIAL CONSISTENCY: The Paxos Phase of Conditional Writes

### 4.1. Why Are Conditional Writes Needed?

Regular writes in Cassandra are upserts by primary key. If two clients simultaneously try to claim ownership of a device by checking with `SELECT` and then running `INSERT`, both may read an empty state before writing. This scenario requires a **lightweight transaction (LWT)**: an `INSERT ... IF NOT EXISTS` or `UPDATE ... IF ...` statement.

LWT uses Paxos consensus to perform conditional compare-and-modify within supported condition scopes. Compared to regular writes, LWT incurs extra coordination steps and latency; use it only when conditional semantics are needed.

### 4.2. The Two Levels: SERIAL and LOCAL_SERIAL

~~~sql
-- Regular level applied to the write/learn phase.
CONSISTENCY ONE;

-- Applied to the consensus phase of LWT.
SERIAL CONSISTENCY SERIAL;

-- Or restrict consensus to the local datacenter when the architecture allows.
SERIAL CONSISTENCY LOCAL_SERIAL;
~~~

`SERIAL CONSISTENCY` only accepts `SERIAL` or `LOCAL_SERIAL`; it does not accept `ONE` or `LOCAL_QUORUM` as a serial value. According to cqlsh documentation, this setting applies to **conditional updates** (`INSERT`, `UPDATE`, `DELETE` with `IF`). In an LWT, there are two levels to distinguish:

| Setting | Phase | Meaning |
| --- | --- | --- |
| `SERIAL CONSISTENCY SERIAL` / `LOCAL_SERIAL` | Serial/Paxos phase | Coordinates consensus to decide whether the condition is satisfied and applied. |
| `CONSISTENCY ONE` / `LOCAL_QUORUM` / etc. | Regular/learn phase | Required acknowledgments and visibility of the write after the consensus phase. |

`SERIAL` spans across datacenters; `LOCAL_SERIAL` limits consensus scope to the local datacenter where architecture permits. In multi-DC distributed systems, choose based on coordination requirements and replication configuration; do not assume `LOCAL_SERIAL` fits every system-wide uniqueness constraint.

### 4.3. Practicing INSERT IF NOT EXISTS

In the lab, ensure you are using the appropriate keyspace and set the consistency levels:

~~~sql
USE cqlsh_consistency_lab;
CONSISTENCY ONE;
SERIAL CONSISTENCY SERIAL;

INSERT INTO device_lease (device_id, holder, generation)
VALUES ('sensor-01', 'worker-A', 1)
IF NOT EXISTS;
~~~

If the row does not exist yet, the output typically looks like:

~~~text
 [applied]
-----------
      True
~~~

Re-running **that exact statement** will not create or overwrite the row:

~~~sql
INSERT INTO device_lease (device_id, holder, generation)
VALUES ('sensor-01', 'worker-A', 1)
IF NOT EXISTS;

SELECT * FROM device_lease WHERE device_id = 'sensor-01';
~~~

The repeated command typically returns `[applied] = False` along with the existing values. If the lab already had a row beforehand, even the first run can return `False`; verify the current state before interpreting the result.

### 4.4. UPDATE IF and Optimistic Concurrency

~~~sql
-- Succeeds if the actual generation equals 1.
UPDATE device_lease
SET holder = 'worker-B', generation = 2
WHERE device_id = 'sensor-01'
IF generation = 1;

-- The old condition is no longer true; this statement will not overwrite.
UPDATE device_lease
SET holder = 'worker-C', generation = 3
WHERE device_id = 'sensor-01'
IF generation = 1;

SELECT holder, generation
FROM device_lease
WHERE device_id = 'sensor-01';
~~~

When only one client updates the generation from 1 to 2, `[applied] = True` confirms the statement met the condition. A subsequent client with `IF generation = 1` receives `False` and must re-read the state and decide how to proceed. Do not mistake `[applied] = False` for a network error; it is the **business outcome of an unmet condition**.

**Note:** RF = 1 is sufficient to rehearse the syntax, but it does not simulate fault tolerance or Paxos latency in a multi-node cluster. In real environments, test consistency levels against the actual RF and topology. `IF` does not turn a multi-partition workflow into a general-purpose transaction.

## 5. PAGING: Reading Results Page by Page

### 5.1. Syntax and Experience in cqlsh

~~~sql
-- Enable paging if currently turned off.
PAGING ON;

-- Fetch at most 2 rows per page for easier observation.
PAGING 2;

SELECT event_time, temperature_c
FROM cqlsh_consistency_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21';
~~~

With 6 rows in the lab, cqlsh displays roughly **2 rows/page**, then waits for the user to request the next page. Because the table has `CLUSTERING ORDER BY (event_time DESC, event_id ASC)`, we expect newer timestamps first. The prompt format for advancing pages depends on the cqlsh version and terminal.

~~~sql
-- Return to cqlsh's default page size.
PAGING ON;

-- Disable paging for small queries if genuinely needed.
PAGING OFF;

-- Re-enable paging before viewing large result sets.
PAGING ON;
~~~

`PAGING <n>` sets the target number of rows per page; the client/driver uses a paging state to fetch subsequent results. This is **not** the number of replicas, nor is it the number of rows Cassandra stores in a partition.

### 5.2. How Does PAGING Differ from LIMIT?

| Mechanism | Controls | Example | Meaning |
| --- | --- | --- | --- |
| `PAGING 2` | Number of rows per fetch/display batch | Query has 6 rows → about 3 pages | You can keep fetching pages until all results are retrieved. |
| `LIMIT 3` | Maximum total rows returned by the SELECT statement | Query has 6 rows → at most 3 rows | You cannot retrieve a 4th row from that same query. |
| `PAGING OFF` | Disables interactive pagination in cqlsh | May print many rows at once | Can easily produce huge output or high memory usage on large result sets. |

You can combine both:

~~~sql
PAGING 2;
SELECT event_time, temperature_c
FROM cqlsh_consistency_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
LIMIT 3;
~~~

Here, the maximum number of rows returned is **3**; cqlsh may fetch and print them across two pages. `LIMIT` is not always sufficient to control full query cost: a query missing the partition key can trigger a wide scan even with a small `LIMIT`. Design queries to match the primary key first.

### 5.3. Choosing a Page Size

A page size that is too small causes excessive client–server round trips; a page size that is too large increases memory footprint, per-round-trip bandwidth, and page wait time. The right size depends on row width, query characteristics, network, and client resources.

**A few notes:**

- Paging is **incremental result fetching**; it does not provide a point-in-time consistent snapshot across pages when concurrent writes occur.
- Paging does not fix a hot partition or an oversized partition; choose appropriate partition keys and bucket sizes.
- Do not use `PAGING OFF` for production exports with millions of rows. Bulk export/import and backup have dedicated operational tools.
- In Java applications, paging is controlled via the driver (fetch size, paging state, reactive/async iteration) and is unaffected by `PAGING` commands in another cqlsh session.

## 6. TRACING: Observing the Query Execution Path

### 6.1. Enabling and Disabling Tracing Properly

~~~sql
-- Enable only when investigating a specific query.
TRACING ON;

SELECT event_time, temperature_c
FROM cqlsh_consistency_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
LIMIT 3;

-- Disable immediately after the target query.
TRACING OFF;
~~~

When tracing is enabled, cqlsh prints trace events after the query finishes. Fields that may appear include **activity**, **timestamp**, **source** (executing node), and **source_elapsed** (elapsed time at source). Depending on the version, cqlsh also shows the tracing session ID. Do not treat the trace lines or latency numbers below as constants: they vary by cluster and load.

Example of the information format to read:

~~~text
Tracing session: <trace-session-uuid>
activity                  | source       | source_elapsed
--------------------------+--------------+---------------
Preparing statement ...   | <node-A>     | ...
Executing ...             | <node-A>     | ...
Sending message to ...    | <node-A>     | ...
Received response from ...| <node-B>     | ...
~~~

Exact event text is not fixed, and on a single-node lab there may be no cross-node network messaging steps. From a trace, we mainly observe **what the coordinator does, which replicas participate, which stage takes time, and whether there is abnormal fan-out**.

### 6.2. Reviewing a Tracing Session

Some cqlsh versions support reviewing a recorded trace:

~~~sql
-- Replace the UUID below with the ACTUAL session id shown in an earlier trace.
SHOW SESSION 123e4567-e89b-12d3-a456-426614174000;
~~~

The command above illustrates **syntax**; the UUID is a placeholder and will have no data unless a matching session was generated. Cassandra stores tracing events in tracing system tables with a finite time-to-live (TTL); trace data may be incomplete or expired. If using a different cqlsh version, check `HELP SHOW` and the corresponding version's documentation.

### 6.3. When Is Tracing Useful?

| Symptom | Questions TRACING Can Help Investigate | What TRACING Does Not Replace |
| --- | --- | --- |
| Slow SELECT by partition key | Are multiple replicas contacted? Which step has high latency? | Server metrics, logs, profiling, infrastructure checks. |
| Read timeout when raising consistency | Which replicas did the coordinator wait on for responses? | Checking node/down state, RF, and network. |
| Query returning many rows | Are there signs of multiple pages or excessive read activity? | Schema/partition key design and data distribution analysis. |
| Slow LWT | Are coordination-related stages visible? | Measuring contention rate, analyzing retries and system load. |

**Tracing overhead:** enabling event collection on nodes adds overhead and writes trace records. Enable it only for the query under investigation, then run `TRACING OFF`; never leave it enabled during load tests. Trace contents can contain technical details or query data, so handle them according to your environment's operational policies.

## 7. Combining All Four Commands in a Diagnostic Session

Suppose a request states: "Reading device events is somewhat slow and the client occasionally reports timeouts." A sensible practice sequence:

~~~sql
SHOW HOST;
DESCRIBE KEYSPACE cqlsh_consistency_lab;
DESCRIBE TABLE cqlsh_consistency_lab.events_by_device_day;

-- RF=1 lab: safe read/write choice for illustration.
CONSISTENCY ONE;
PAGING 2;

-- Enable tracing only for the target query.
TRACING ON;
SELECT event_time, temperature_c
FROM cqlsh_consistency_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
LIMIT 3;
TRACING OFF;

-- This setting only affects subsequent LWTs.
SERIAL CONSISTENCY SERIAL;
~~~

Read the results in order:

1. Confirm the current endpoint/cluster via `SHOW HOST`; confirm the keyspace's replication.
2. Check whether `WHERE` includes the full partition key and suitable clustering conditions.
3. Verify whether the requested consistency can be satisfied by the **RF and currently active replicas**.
4. Check pagination so you do not mistake "waiting for the next page" for a hung query.
5. Inspect the trace of a representative query; combine with metrics and logs when analyzing root causes.

**Do not try increasing or lowering consistency in production just because of one unusual trace.** Changing CL alters the read/write contract, which can affect functional consistency and cause failures when replicas are unavailable. If stronger consistency is required, evaluate replication, topology, concurrency, and business requirements.

## 8. Connection to Java Applications

The cqlsh commands above apply only to that shell session. In **Apache Cassandra Java Driver 4.x**, applications configure consistency and serial consistency per statement or via driver default configuration/profiles.

Example using a conditional statement; assumes `CqlSession session` is already created and connected to the right datacenter:

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

// Illustrative example for a cluster with a suitable topology.
SimpleStatement statement = SimpleStatement.builder(
    "INSERT INTO cqlsh_consistency_lab.device_lease " +
    "(device_id, holder, generation) " +
    "VALUES ('sensor-02', 'worker-A', 1) IF NOT EXISTS")
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL)
    .build();

ResultSet result = session.execute(statement);
boolean applied = result.wasApplied();
System.out.println("Condition applied: " + applied);
~~~

In this example:

- `setConsistencyLevel` corresponds to the role of `CONSISTENCY` in cqlsh; `setSerialConsistencyLevel` corresponds to `SERIAL CONSISTENCY` for LWT.
- `result.wasApplied()` reflects the condition outcome in LWT; when `false`, the application should check current data and decide whether to retry or report a conflict.
- On an RF = 1 lab, `LOCAL_QUORUM` for the single datacenter still requires only 1 replica; the driver example does not implicitly create extra replicas.
- Java Driver paging uses fetch size and paging state; manage when pages are fetched and avoid loading large result sets into a single in-memory list.
- Enabling tracing in cqlsh does not enable tracing for other Java sessions. To investigate applications, use driver and cluster tracing/observability in a controlled manner.

Production applications should use **prepared statements + bind parameters** instead of embedding literal values directly into CQL strings. The snippet above only demonstrates attaching consistency and serial consistency to a statement.

## 9. Common Errors and Misconceptions

| Symptom | Causes to Check | Resolution |
| --- | --- | --- |
| `CONSISTENCY TWO` on an RF = 1 keyspace fails | Requesting more replicas than can respond | Run `DESCRIBE KEYSPACE` and pick a suitable CL; proper RF/topology is required for real quorum. |
| Changing `SERIAL CONSISTENCY` does not affect regular `SELECT` | Serial consistency does not replace the CL of regular queries | Use `CONSISTENCY` for regular reads/writes; serial for LWT. |
| `INSERT ... IF NOT EXISTS` returns `[applied] = False` | Row already exists so the condition is unmet | Read the current state; distinguish a business conflict from a connection error. |
| `UPDATE ... IF generation = 1` does not update | Current generation value has already changed | Re-read and apply optimistic concurrency per business logic. |
| `PAGING 2` output shows only the first two rows | cqlsh is waiting for a request for the next page | Advance to the next page or increase page size if appropriate. |
| `LIMIT 3` does not return the entire table | `LIMIT` caps the total number of rows returned | Remove/increase `LIMIT` only if the query is well-formed and data size is bounded. |
| `TRACING ON` slows queries down | Overhead of collecting/writing trace events | Disable immediately after investigating; compare against metrics with tracing off. |
| Expected trace events are missing | Single-node cluster, incomplete trace writes, expired session, or version differences | Try a simpler query, check versions and related logs/metrics. |
| Timeout during LWT write | Consensus or write phase did not receive enough responses | Check state before retrying, inspect replicas and logs; avoid creating ambiguous duplicate operations. |

## 10. Comprehension Practice Exercises

1. Set up an RF = 1 lab, insert 6 events, then set `CONSISTENCY ONE` and read using the full partition key. Explain why `LOCAL_QUORUM` on RF = 1 does not mean "two replicas."
2. Assume a datacenter with RF = 3. Calculate the minimum replicas needed for `ONE`, `LOCAL_QUORUM`, and `ALL`; predict what happens when one replica is unavailable.
3. Run `INSERT ... IF NOT EXISTS` twice and observe `[applied]`. Change `generation` via `UPDATE ... IF generation = ...` and explain the result when the old condition is no longer true.
4. Run `PAGING 2` to read the 6 rows sequentially. Compare with a `LIMIT 3` query and describe what differs after the second page ends.
5. Enable `TRACING ON` for a query with a full partition key, record at least three meaningful trace fields, and run `TRACING OFF` immediately afterward.
6. Explain why changing `CONSISTENCY` in cqlsh does not change the consistency level of a running Java application, and identify the Java Driver API used to set it on a statement.

**Completion criteria:** distinguish regular and serial consistency, predict response counts in an RF = 3 scenario, interpret `[applied]` results, explain page size versus `LIMIT`, and know how to enable/disable tracing for controlled investigation.

## References

- [Apache Cassandra — cqlsh: the CQL shell](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html): syntax and behavior of `CONSISTENCY`, `SERIAL CONSISTENCY`, `PAGING`, `TRACING`, and `SHOW SESSION`.
- [Apache Cassandra — Architecture: Dynamo](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html): replication, consistency levels, and request routing.
- [Apache Cassandra — CQL documentation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/index.html): `INSERT`, `UPDATE`, `IF`, primary keys, and table modeling.
- [Apache Cassandra Java Driver 4.x](https://docs.datastax.com/en/developer/java-driver/4.17/): per-statement consistency, serial consistency, paging, and result-set API.
