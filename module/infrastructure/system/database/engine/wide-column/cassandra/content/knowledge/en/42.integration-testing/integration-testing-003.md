# Distinguishing a Started Node from Data Served at the Required CL in Apache Cassandra

> **Chapter:** Integration Testing  
> **Lesson Goal:** Design tests that prove **data for a specific query/operation is actually served at the committed consistency level (CL)**, rather than merely checking that Docker/containers are running, port 9042 is open, or the driver created a `CqlSession`. Examples use Apache Cassandra, CQL, Java 17, Java Driver 4.x, JUnit 5, and Testcontainers 2.x. Any topology-changing or node-restart operations apply only to authorized lab clusters.

## 1. Learning Outcomes

After this lesson, learners can:

1. Distinguish the six layers: **process started → native transport reachable → CQL responsive → schema agreed → replica quorum reachable → business data visible**.
2. Explain why `nodetool status` returning `UN` or `SELECT release_version FROM system.local` succeeding **does not prove** `LOCAL_QUORUM`/`QUORUM` for all partitions.
3. Calculate the required replica responses by RF/CL, specifically `ONE`, `LOCAL_ONE`, `QUORUM`, `LOCAL_QUORUM`, `EACH_QUORUM`, and `ALL`.
4. Understand how coordinators, natural replicas, token/partition keys, local DC, and node-state/gossip affect test conditions.
5. Distinguish **CL availability** from **properly streamed/repaired data** and **read-after-write observing the expected value**.
6. Choose the right *test oracle*: write a record at the required CL, read at the required CL, and compare the business value/version rather than assuming “no exception thrown” suffices.
7. Write a **single-node** Testcontainers Cassandra integration test verifying CL ONE, plus a negative test with RF=2/CL TWO on one node **without shutting down any machine**.
8. Know when a multi-node/multi-DC test is mandatory and why a single-node container cannot prove RF3 `LOCAL_QUORUM` behavior.
9. Implement deadline/backoff polling, distinguishing transient startup errors from permanent config/schema errors.
10. Build readiness gates for bootstrap, replace, RF changes, migrations, restore/repair, and rolling restarts with clear metrics/rollback rules.

**Scope `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`:** Cassandra is a distributed wide-column database whose tables are designed around access patterns. The partition key determines the token/natural replicas; the consistency level is the read/write contract between coordinator and replicas. Java tests are trustworthy only when they verify the exact **keyspace, table, token/partition, DC, CL, and data** of the production workload. `SPECIAL_NOTE` has no additional constraints.

## 2. Six Readiness Layers: From “Process Up” to “Usable Data”

~~~text
L0  OS/Docker process RUNNING
       |
       v
L1  Native TCP port 9042 listening / accepting connections
       |
       v
L2  CQL coordinator responds to system.local
       |
       v
L3  Schema agreed, migrations/tables exist
       |
       v
L4  Natural replicas of the partition meet required count/CL
       |
       v
L5  Business write/read at the exact CL succeeds,
    value/version/TTL/visibility match the oracle
       |
       v
PRODUCTION-READY for a defined set of access patterns
~~~

**Never infer that a higher layer automatically holds because a lower layer PASSED.** Port 9042 can accept connections before schema/data are ready. An `UN` node may act as a usable coordinator while the partition's replicas lack quorum. Even three `UN` nodes **do not prove** a restore/repair finished or data is valid post-migration.

### 2.1. Signals Table and What They Do Not Prove

| Observed Signal | Valid Conclusion | **Invalid** Conclusion |
|---|---|---|
| Docker `running` | Container process is alive | Cassandra is ready to accept CQL |
| TCP connect `:9042` succeeds | Endpoint accepts connections | Auth/CQL/schema/replica read-write work |
| `cqlsh` opens a session | At least one CQL path works | All token ranges meet CL |
| `SELECT release_version FROM system.local` | Coordinator serves local system table | User keyspaces/tables/ring are serviceable |
| `nodetool status` reports `UN` | Node appears Up/Normal from the tool's view | Whole cluster has enough replicas for every CL |
| Driver `CqlSession` created | Enough connectivity/metadata to build client | All business queries will succeed |
| Schema agreement PASS | **Currently UP** nodes agree on schema version | DOWN nodes are ready or data has streamed |
| `INSERT` at `ONE` succeeds | Received enough ACKs for ONE | `QUORUM` reads/writes will certainly succeed |
| `SELECT` at `LOCAL_QUORUM` throws no exception | Enough responses to finish this read | Value definitely matches business expectation |
| Read after write on same PK at target CL with matching value | One real test case met CL and oracle | All partitions/times/racks/traffic are ready |

### 2.2. Readiness Checks Must Carry **Context**

A complete readiness statement takes the form:

~~~text
In cluster C, local DC D, keyspace K (RF map R),
table T, query family Q on partition key P,
with CLread=RCL and CLwrite=WCL,
within timeout/deadline B,
write/read completes and data matches oracle O.
~~~

Without **CL**, you do not know how many replicas are required. Without **partition key**, you do not know the natural replicas. Without **DC/RF**, you cannot compute quorum at the check site. Without an **oracle**, a read returning 0 rows may look like protocol “success” while failing business correctness.

## 3. Process/Port/CQL Layers: Baseline Checks

### 3.1. A Running Container Is Only a Prerequisite

~~~bash
docker ps
docker inspect cassandra-lab --format '{{.State.Running}}'
~~~

These two commands only measure Docker lifecycle. Cassandra still has to initialize the JVM, system keyspaces, commitlog, memtables, gossip, token metadata, native transport, authentication, schemas, and any streaming from bootstrap/replace.

**Never** treat a simple container healthcheck as “data-ready at CL QUORUM” if it only probes TCP or runs `cqlsh` against `system.local`.

### 3.2. Purposeful Native Transport Check

~~~bash
# On a Linux environment with cqlsh:
cqlsh 127.0.0.1 9042
~~~

~~~sql
SELECT cluster_name, data_center, release_version
FROM system.local;
~~~

This check is useful for catching wrong ports, TLS/auth issues, Cassandra not yet listening on CQL, or protocol mismatches. It reads the **coordinator's `system.local`**, not business data across distributed replicas.

### 3.3. `nodetool status` and the Two-Character State

~~~bash
nodetool status
nodetool status my_keyspace
~~~

In the first column:

- `U` / `D`: node **Up/Down** from the status view.
- `N` / `J` / `L` / `M`: node **Normal/Joining/Leaving/Moving**.
- `UN` = Up + Normal; `UJ` = Up + Joining; `DN` = Down + Normal.

Illustrative example:

~~~text
Datacenter: dc1
Status=Up/Down
|/ State=Normal/Leaving/Joining/Moving
--  Address       Load       Tokens  Owns ... Rack
UN  10.0.1.11     1.2 GiB    16      ...     rack1
UN  10.0.1.12     1.1 GiB    16      ...     rack2
DN  10.0.1.13     ?         16      ...     rack3
~~~

`nodetool status my_keyspace` displays ownership per **specific keyspace** replication rather than a generic percentage meaningless across differing RFs. Still, it is not a write/read test at a CL, and one node's view does not guarantee every client/replica shares the same network reachability. See [nodetool status — DataStax OSS](https://docs.datastax.com/en/cassandra-oss/2.1/cassandra/tools/toolsStatus.html).

### 3.4. Driver Node Awareness Differs from Cassandra Gossip

In Java Driver 4.x:

~~~java
session.getMetadata().getNodes().values().forEach(node ->
    System.out.printf("node=%s state=%s distance=%s openConnections=%d%n",
        node.getEndPoint(),
        node.getState(),
        node.getDistance(),
        node.getOpenConnections()));
~~~

`getNodes()` includes down and ignored nodes, **not** only connected nodes. `Node.getState()` reflects the driver's perspective and may transiently diverge from gossip; `Node.getDistance()` also depends on the load-balancing policy. These metrics help diagnose topology, **not replace** business probes at target CL. [Driver Node metadata](https://apache.github.io/cassandra-java-driver/4.18.0/core/metadata/node/).

## 4. CL, RF, and Calculating Required ACKs

Let `N` be the number of **full replicas** of the partition within the scope of the CL under consideration. For a DC with RF=3 full replicas:

\[
quorum(N) = \lfloor N/2 \rfloor + 1 = 2.
\]

### 4.1. Common Consistency Levels

| CL | Scope | Typical Requirement | Notes |
|---|---|---|---|
| `ONE` | Natural replicas | ≥1 replica responds | Reads may return stale data |
| `TWO` | Natural replicas | ≥2 replicas | RF1 fails with only 1 replica |
| `THREE` | Natural replicas | ≥3 replicas | Valid only with enough replicas |
| `QUORUM` | Partition's full replicas cluster-wide | Majority, `floor(total RF/2)+1` | Differs from local quorum in multi-DC |
| `LOCAL_ONE` | Coordinator's DC | ≥1 local replica | Does not verify remote DCs |
| `LOCAL_QUORUM` | Coordinator's DC | Majority of full replicas in that DC | E.g. RF3 → 2 local |
| `EACH_QUORUM` | **Writes** across multiple DCs | Majority of full replicas in **each** DC | Not a typical read CL |
| `ALL` | All natural replicas | All full replicas | Poor node-failure tolerance |
| `ANY` | **Writes** | Replica ACK or coordinator stores hint | Invalid for reads; hints ≠ data on replicas |
| `SERIAL`/`LOCAL_SERIAL` | Paxos/LWT | Dedicated serial phase | Does not replace normal CL for whole op |

With **transient replication**, counting full vs transient replicas and supported CLs have version/config exceptions; examples in this lesson **assume full-replica RFs** and do not use the table above for transient setups. See [Apache Cassandra Dynamo architecture](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo).

### 4.2. Single DC with RF3

~~~text
Keyspace NTS: dc1=3 full replicas
  r1 = UP    r2 = UP    r3 = DOWN

CL ONE          needs 1 -> may PASS
CL LOCAL_ONE    needs 1 -> may PASS
CL LOCAL_QUORUM needs 2 -> may PASS
CL QUORUM       needs 2 -> may PASS
CL ALL          needs 3 -> cannot PASS

If r2 also goes DOWN:
CL ONE          may still PASS
CL LOCAL_QUORUM insufficient -> UNAVAILABLE
~~~

**Do not equate “UP” with “ACK returned”.** The lines above count *known live replicas* only. Under slow network/storage, the coordinator may initially see enough live replicas yet later throw `ReadTimeoutException`/`WriteTimeoutException` if responses miss the deadline.

### 4.3. Two DCs with Different RFs

Suppose:

~~~text
dc1 RF3; dc2 RF2; total full RF=5

dc1: r1 UP, r2 UP, r3 DOWN
dc2: r4 UP, r5 DOWN
~~~

| CL | How Many Needed? | Availability Outcome in Example |
|---|---|---|
| `LOCAL_QUORUM` from dc1 | 2 in dc1 | Can succeed |
| `LOCAL_QUORUM` from dc2 | 2 in dc2 | Cannot succeed |
| `QUORUM` | 3 out of 5 total | Can succeed with 2 dc1 + 1 dc2 |
| `EACH_QUORUM` for writes | 2 in dc1 **and** 2 in dc2 | Cannot succeed (dc2 short by 1) |
| `ALL` | 5 | Cannot succeed |

This is why a passing `LOCAL_QUORUM` test in dc1 cannot declare **dc2 ready as well**. Coordinator DC, Java Driver `basic.load-balancing-policy.local-datacenter`, RF map, and natural replica placement must align.

### 4.4. `ANY` Is Not a Data-Readiness Check

In an `ANY` write, Cassandra may return success by **only storing a hint** to forward the mutation later. That does not prove data is served by replicas or immediately readable. Never use `ANY` as a readiness gate for apps requiring read-after-write, and never downgrade CL to `ANY` just to pass a test.

## 5. Natural Replicas by Token: Cluster-Wide UP Is Not Enough

### 5.1. Each Partition Has Its Own Replica Set

~~~text
partition key: (tenant_id='t1', day=2026-11-21)
                      |
                partitioner hash
                      |
                    TOKEN
                      |
         keyspace replication strategy
                      |
          natural replicas for this token
            /           |           \
        node A        node C       node F
                      |
              CL determines ACK count
~~~

Node B may be `UN` and answer `system.local` while **not** being a natural replica for `t1/day`'s token. It can only act as coordinator. An arbitrary UP node in the cluster cannot substitute for a replica required by `LOCAL_QUORUM`.

### 5.2. Testing One Partition Proves Only One Slice

A probe on partition `tenant=smoke` returning expected data at `CL=QUORUM` proves **that token's execution path** at that instant. Other tokens may map to different replica sets where another node is down or streaming slowly. Production readiness should cover:

- At least the application's critical query families.
- **Deterministic partition keys** whose data has verified oracles and TTLs.
- Optionally **multiple representative token ranges** if the cluster is large or undergoing topology changes.
- Explicit DC/rack and per-keyspace RF scope; never claim “globally ready” after testing one local DC.

### 5.3. Coordinator Is Not Necessarily a Natural Replica

A token-aware driver usually prefers a node in the replica set, yet query plans, load balancing, and network issues may pick a coordinator that does not own the partition. That coordinator forwards reads/writes to the natural replicas. Therefore:

~~~text
Connected to node B?  -> Yes.
Node B UN?             -> Yes.
Node B is replica P?   -> Possibly NO.
P's CL satisfied?      -> Must check actual replica responses.
~~~

Never tie readiness to a single hostname/port when data serving depends on the distributed **replica set**.

## 6. “Enough Live Replicas” Still Differs from “Read/Write Completed”

### 6.1. Two Distinct Checks

**Topology-based expectation:**

~~~text
Per metadata/gossip:
  natural replicas(P) = {A, B, C}
  local full replicas UP = {A, B}
  CL LOCAL_QUORUM RF3 requires 2
  ==> Chance to meet CL exists (sufficient known-live).
~~~

**Request-based proof:**

~~~text
Java executes INSERT / SELECT on exact partition P
  with LOCAL_QUORUM
  within configured request timeout
  and receives ACK/rows with expected data
  ==> This request met the test requirement.
~~~

Key distinctions:

- **`UNAVAILABLE`:** the coordinator determines insufficient live replicas exist for the CL **before** or during request evaluation.
- **`READ_TIMEOUT`/`WRITE_TIMEOUT`:** the coordinator had a path to proceed, but not enough responses arrived before the deadline.
- **`READ_FAILURE`/`WRITE_FAILURE`:** a replica/coordinator reported an execution error, not merely slowness.
- **`DriverTimeoutException`:** the **Java driver's client deadline** expired before receiving a result; may stem from queues, connections, network, retries, or server work.
- **`AllNodesFailedException`:** the driver tried multiple coordinators and recorded per-node errors; does not mean every replica is dead.
- **`NoNodeAvailableException`:** no usable coordinator could be tried; may be due to local DC/contact points/driver topology rather than missing data replicas.

### 6.2. Two Requests with the Same CL Can Yield Different Outcomes

~~~text
Req 1: SELECT partition P1, CL LOCAL_QUORUM
       natural replicas A B C -> A+B healthy -> PASS

Req 2: SELECT partition P2, CL LOCAL_QUORUM
       natural replicas C D E -> only C healthy -> UNAVAILABLE

Req 3: SELECT partition P1, CL LOCAL_QUORUM
       A+B alive but disk overloaded -> READ_TIMEOUT
~~~

Hence a liveness probe returning a single boolean `clusterAvailable=true` is usually insufficient for multi-token/multi-rack systems. Build a **matrix** across keyspace/query family/CL and representative partitions.

### 6.3. Request-Level Success Does Not Automatically Meet SLA

A request ACKed at `LOCAL_QUORUM` after 8 seconds satisfies CL yet **fails** a 500 ms API SLO. Readiness gates should check together:

1. **Correctness:** matching row/value/version against the test oracle.
2. **Consistency:** reads/writes use the intended CL and local DC.
3. **Availability:** sufficient replicas, no unavailable/failure errors.
4. **Latency:** completes within the configured request deadline/SLO.
5. **Sustainability:** retries/GC/disk/backlog stay within bounds (for production canaries).

A passing `SELECT 1` when business query latency exceeds deadlines is **insufficient to serve real traffic**.

## 7. CL Availability Differs from Data Freshness and Business Correctness

### 7.1. Successful Reads Can Return Stale Values

Suppose RF3 in one DC, write at `ONE` and read at `ONE`:

~~~text
Write value=PAID
  replica A ACKs
  replicas B,C do not have the update yet

Read ONE from B -> may observe NEW

Both write ONE and read ONE "succeeded at CL"
yet read-after-write does not see PAID.
~~~

Thus, when testing **visibility**, do not only assert `row != null`: assert the value, version, event ID, timestamp, or business condition.

### 7.2. Quorum Intersection — The Fundamental Condition

Within the same set of N full replicas, if writes require W ACKs and reads require R responses, the classic condition:

\[
W+R>N
\]

forces the two replica sets to **overlap**, e.g. RF3, W=2, R=2. In Cassandra, this underpins `QUORUM`/`LOCAL_QUORUM` read-after-write **under appropriate scope and assumptions**. It does not automatically provide strict linearizability under concurrent writes, unsynchronized clocks, custom-timestamp mutations, LWT, or complex multi-DC paths. See [Apache Cassandra Dynamo](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo).

| RF | Write CL | Read CL | W+R > RF? | Interpretation |
|---:|---|---|---|---|
| 3 | ONE (1) | ONE (1) | 2 > 3: no | May read stale data |
| 3 | ONE (1) | QUORUM (2) | 3 > 3: no | No overlap guarantee |
| 3 | QUORUM (2) | QUORUM (2) | 4 > 3: yes | Overlaps within same replica set |
| 3 | ALL (3) | ONE (1) | 4 > 3: yes | Very poor write node-failure tolerance |
| dc1 RF3 | LOCAL_QUORUM (2) | LOCAL_QUORUM (2) | 4 > 3: yes | Overlap guaranteed in **dc1**, not implicitly dc2 |

### 7.3. What “Read an Existing Row” vs “Write Then Read” Probes Prove

**Seeded-data read check:**

- Confirms pre-loaded data (from snapshot/restore/migration) is readable at target CL with expected values.
- Catches missing data, wrong partition/codec, tombstones, and schema mismatches.
- Does not prove the new write path is healthy.

**Write → read probe:**

- Confirms a coordinator can write and read back **the newly written record** in the keyspace/query path at required CL.
- Does not prove historical data finished migrating/repairing.
- Does not prove all token ranges have enough replicas or all query/TTL/LWT paths work.

A solid readiness suite uses **both** when the app must read historical data and serve new writes.

### 7.4. LWT and Conditional Correctness

For workflows needing atomic compare-and-set/uniqueness, a single `INSERT ... IF NOT EXISTS` at normal CL does not verify full Paxos semantics. Tests must specify:

- **Normal CL** for the read/write phase, e.g., `LOCAL_QUORUM`.
- **Serial CL** for the conditional transaction, e.g., `LOCAL_SERIAL`.
- Both `[applied]` result and expected record/version; LWT retries require care because `[applied]=false` after a retry may mean the first attempt already committed.

Do not use LWT in frequent production readiness probes when a simple INSERT/SELECT suffices; avoid unnecessary load and contention.

## 8. Schema Agreement: Necessary but Insufficient

### 8.1. Why DDL and Data Have Separate Lifecycles

~~~text
CREATE TABLE t
     |
     v
Node A knows schema t
     |
Gossip/schema agreement
     |
Nodes B, C know schema t
     |
------------------- Schema agreement PASS
     |
     v
Data ingest / bootstrap / restore / streaming / repair
     |
     v
Expected partitions are served
     |
------------------- DATA READINESS must be checked separately
~~~

Driver 4.x usually **waits for schema agreement** after DDL: when table creation returns, the coordinator may have applied the schema while peer nodes are still converging. The driver polls schema versions of **currently UP** nodes within a timeout; if it expires, the DDL query may complete with `isSchemaInAgreement=false`. However, passing agreement does not mean **DOWN nodes** updated or data streamed. [Driver schema agreement](https://apache.github.io/cassandra-java-driver/4.18.0/core/metadata/schema/).

### 8.2. Checking Schema Agreement in Java

~~~java
boolean agreed = session.checkSchemaAgreement();
if (!agreed) {
    throw new IllegalStateException(
        "Schema not agreed among currently UP nodes");
}
~~~

After DDL:

~~~java
ResultSet ddlResult = session.execute(
    "CREATE TABLE IF NOT EXISTS ready_lab.probe_by_bucket " +
    "(bucket text, id uuid, value text, " +
    "PRIMARY KEY ((bucket), id))");

if (!ddlResult.getExecutionInfo().isSchemaInAgreement()) {
    // Do not mark "data ready"; optionally poll agreement within a deadline.
    throw new IllegalStateException("DDL schema agreement not reached");
}
~~~

**Subtlety:** `ExecutionInfo.isSchemaInAgreement()` is **meaningful right after executing DDL**. Per the Javadoc, for non-schema-altering queries this flag always returns true, so **never** call `SELECT...getExecutionInfo().isSchemaInAgreement()` to prove real agreement. [Javadoc ExecutionInfo](https://apache.github.io/cassandra-java-driver/4.18.1/api/com/datastax/oss/driver/api/core/cql/ExecutionInfo.html).

### 8.3. Metadata Snapshots Do Not Auto-Update

~~~java
var oldSnapshot = session.getMetadata();

session.execute("CREATE TABLE IF NOT EXISTS ready_lab.probe_by_bucket "
    + "(bucket text, id uuid, value text, "
    + "PRIMARY KEY ((bucket), id))");

// WRONG: oldSnapshot may not reflect the DDL just executed.
// var oldTable = oldSnapshot.getKeyspace("ready_lab")...

var freshSnapshot = session.getMetadata();
var keyspace = freshSnapshot.getKeyspace("ready_lab");
if (keyspace.isEmpty()) {
    throw new IllegalStateException("Keyspace not visible in driver metadata");
}
~~~

`Metadata` is largely an immutable snapshot; you must call `session.getMetadata()` **again** to observe changes. Even when metadata shows the table exists, still **execute queries** in integration tests. [Driver metadata](https://apache.github.io/cassandra-java-driver/4.18.0/core/metadata/).

### 8.4. How Schema Agreement Can Cause a “False Green”

| Situation | Agreement | Data Readiness? |
|---|---|---|
| 3 nodes UP, same schema, new empty table | PASS | Does not prove historical data |
| 2 nodes UP, 1 node DOWN, two UP nodes share schema | May PASS | DOWN node is not ready |
| After SSTable restore, table metadata matches | PASS | Restored data may be incomplete |
| After RF change, new schema propagated | PASS | New replicas may not yet hold historical data |
| App queries only `system.local` | Skips user tables | Does not prove data path |

Never use schema agreement as a **“data synchronization complete”** signal.

## 9. Readiness Contract for Integration Tests

### 9.1. Concrete Contract Example

~~~yaml
readiness_check:
  environment: staging
  cluster: orders-cassandra
  local_dc: dc1
  keyspace: orders_ks
  replication: {dc1: 3, dc2: 3}
  table: orders_by_id
  partition_pattern: tenant_id
  query_family: orders.getById
  expected_read_cl: LOCAL_QUORUM
  expected_write_cl: LOCAL_QUORUM
  required_value: status_and_revision_match
  require_schema_agreement: true
  max_total_wait: 60s
  per_attempt_timeout: 3s
  attempt_interval: 1s
  token_sampling: representative_partitions
  scope: dc1_only
~~~

This is an example contract structure in documentation, **not** a file to add to the repository. The 60s/3s/1s numbers are illustrative; local tests and production readiness use different budgets. In CI, allow enough headroom for startup while failing within a bounded limit rather than hanging forever.

### 9.2. Separating the Gates

| Gate | Question | How to Check |
|---|---|---|
| G0 Process | Does the process/container exist? | Docker/K8s process health |
| G1 Transport | Is CQL port open, auth/TLS valid? | Driver handshake/CQL |
| G2 Node | Are node/ring states as expected? | `nodetool status`/driver metadata |
| G3 Schema | Tables/columns/UDTs and schema agreement? | DDL result, `checkSchemaAgreement`, metadata |
| G4 CL availability | Do queries on the keyspace/partition at target CL respond? | Java `execute`/`setConsistencyLevel` |
| G5 Data oracle | Does seeded/write/read data match value/version? | Assert content/PK/TTL/rows |
| G6 Stability | Over an observation window, are success/error/p99 steady? | Repeated bounded probes + metrics |

For a single-node container serving a CL ONE lesson, G0–G5 can PASS. **Never infer G4/G5 at RF3 `LOCAL_QUORUM`** from that test.

### 9.3. Pass/Fail Rules

~~~text
PASS:
  - correct keyspace/schema
  - CQL read/write at declared CL returns success
  - expected key/value/version match
  - elapsed <= test deadline
  - CL not lowered to hide errors

FAIL:
  - unavailable/timeout/invalid query/permission error
  - read succeeds but returns stale row/NULL/wrong revision
  - agreement not reached within required budget
  - test skipped due to mismatched environment conditions

INCONCLUSIVE:
  - write timeout/unknown outcome, not yet reconciled
  - driver loses connection before learning server outcome
  - chaos test lacks sufficient oracle/metrics to confirm
~~~

Never turn `INCONCLUSIVE` into PASS via `catch(Exception ignored)` or infinite retries. When a write outcome is unknown, keep a **fixed probe ID** and reconcile state instead of generating a new probe every time.

## 10. Single-Node CQL Lab: Proving CL ONE While Failing CL TWO

**Goal:** The exact same Cassandra node can report `UN`/`system.local` OK and serve `ONE`, yet **cannot serve TWO** on an RF2 keyspace when only one natural replica is available. No need to stop nodes or break networking.

### 10.1. Environment and Constraints

- **Single-node lab** Cassandra 4.1 or 5.0 with working `cqlsh`.
- Permission to create test keyspaces/tables; never execute on production keyspaces.
- `SimpleStrategy` is for lab use only; multi-DC production uses `NetworkTopologyStrategy`.
- Read actual DC name from `system.local`/`nodetool status`; the JUnit example below uses the value returned by the container.

### 10.2. RF1 Keyspace — Write/Read at ONE

~~~sql
CREATE KEYSPACE IF NOT EXISTS ready_one_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS ready_one_lab.probes_by_tenant_day (
  tenant_id text,
  day date,
  probe_id uuid,
  expected_value text,
  revision int,
  PRIMARY KEY ((tenant_id, day), probe_id)
);

CONSISTENCY ONE;

INSERT INTO ready_one_lab.probes_by_tenant_day
  (tenant_id, day, probe_id, expected_value, revision)
VALUES (
  'tenant-lab', '2026-11-21',
  11111111-1111-1111-1111-111111111111,
  'READY_ONE', 7
);

SELECT expected_value, revision
FROM ready_one_lab.probes_by_tenant_day
WHERE tenant_id = 'tenant-lab'
  AND day = '2026-11-21'
  AND probe_id = 11111111-1111-1111-1111-111111111111;
~~~

Expected output: `READY_ONE`, revision `7`. This test proves a single write/read request at `ONE` on an RF1 keyspace and this record. It **does not** prove node-failure tolerance or RF3 CL behavior.

### 10.3. RF2 Keyspace on Only One Node — Negative Test

~~~sql
CREATE KEYSPACE IF NOT EXISTS ready_two_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 2
};

CREATE TABLE IF NOT EXISTS ready_two_lab.probes (
  probe_id uuid PRIMARY KEY,
  expected_value text
);

CONSISTENCY ONE;

INSERT INTO ready_two_lab.probes
  (probe_id, expected_value)
VALUES (
  22222222-2222-2222-2222-222222222222,
  'WRITTEN_AT_ONE'
);

CONSISTENCY TWO;

SELECT expected_value
FROM ready_two_lab.probes
WHERE probe_id = 22222222-2222-2222-2222-222222222222;
~~~

On a cluster **that genuinely has only one node**, the `TWO` SELECT typically returns:

~~~text
Unavailable: Required 2 live replicas, but only 1 available
~~~

Accurate statements:

1. The Cassandra node is still **running** and may be `UN`.
2. The CQL query at `ONE` succeeded.
3. An RF2 keyspace can be declared, yet **2 physical replicas do not exist** on a single-node cluster.
4. Hence the `TWO` request **lacks sufficient replicas** and fails as expected.
5. **This is an intentional negative test**, not a Docker/Testcontainers bug or driver defect.

`CREATE KEYSPACE RF2` may warn that RF exceeds node count; never turn this example into operational config. Afterward, use disposable/test namespaces; never auto-run `DROP KEYSPACE` where data not owned by the test may reside.

### 10.4. Why Is This Test Pedagogically Valuable?

It eliminates hard-to-control variables like network drops, disk overload, or JVM GC pauses. Because only one physical node holds data, **there is no way to obtain two replica ACKs**. We prove:

\[
\text{node up} \not\Rightarrow
\text{data available at requested CL}.
\]

In production multi-node RF3/DC clusters, `UNAVAILABLE` also depends on the *natural replica set*, coordinator view, and DC/rack placement, so an RF2 lab test **illustrates the principle** rather than replacing full chaos testing.

## 11. Java Driver 4.x: Readiness Probes Must Set CL Explicitly

### 11.1. Common Mistake

~~~java
try (CqlSession session = CqlSession.builder().build()) {
    session.execute("SELECT release_version FROM system.local");
    System.out.println("Cassandra READY");
}
~~~

This code only proves one coordinator can answer `system.local`. The driver's default consistency may not match the business CL, and `CqlSession.builder().build()` also depends on contact points/local DC/config loaders. Never signal “READY” to a load balancer from that check alone.

### 11.2. Setting CL on the Statement

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Duration;
import java.time.LocalDate;
import java.util.UUID;

PreparedStatement read = session.prepare(
    "SELECT expected_value, revision " +
    "FROM ready_one_lab.probes_by_tenant_day " +
    "WHERE tenant_id = ? AND day = ? AND probe_id = ?");

BoundStatement request = read.bind(
        "tenant-lab",
        LocalDate.parse("2026-11-21"),
        UUID.fromString(
            "11111111-1111-1111-1111-111111111111"))
    .setConsistencyLevel(DefaultConsistencyLevel.ONE)
    .setTimeout(Duration.ofSeconds(2))
    .setIdempotent(true);

Row row = session.execute(request).one();
if (row == null
        || !"READY_ONE".equals(row.getString("expected_value"))
        || row.getInt("revision") != 7) {
    throw new IllegalStateException("Data oracle mismatch");
}
~~~

**Points to note:**

- `setConsistencyLevel` is set **explicitly**; the RF1 lab uses ONE.
- Prepared/BoundStatement uses the exact partition key and CQL types (`String`/`LocalDate`/`UUID`).
- `setTimeout` enforces the **client** deadline for this request; it does not turn a server into a new replica.
- `setIdempotent(true)` is valid for a read-only SELECT; never enable it blindly on every write.
- Assert **row contents**, not merely that `execute` threw no error.
- Never treat a row read back at CL ONE as proof of production `LOCAL_QUORUM`.

### 11.3. Pattern with CL QUORUM

Once an RF3 cluster and verified local DC are available, the same statement pattern can be tested with `DefaultConsistencyLevel.LOCAL_QUORUM`. However, you must use an **NTS RF3 keyspace** with enough full replicas in the local DC; **do not change the CL of an RF1 lab** and label the failure a bug.

~~~java
BoundStatement productionRead = prepared.bind(
        tenantId, day, probeId)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setTimeout(Duration.ofSeconds(3))
    .setIdempotent(true);
~~~

The snippet assumes `prepared` targets an appropriate production keyspace/table, not `ready_one_lab` RF1. Outside the lab, enforce tenant authorization and protect probe IDs/values from PII exposure.

### 11.4. Don't Set CL Only on Reads and Forget Writes

~~~java
BoundStatement write = insertPrepared.bind(
        tenantId, day, probeId, expectedValue, revision)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setTimeout(Duration.ofSeconds(3));

BoundStatement readBack = selectPrepared.bind(
        tenantId, day, probeId)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setTimeout(Duration.ofSeconds(3));
~~~

When testing read-after-write, explicitly record **both WCL and RCL**. If writing at `ONE` and reading at `LOCAL_QUORUM`, `W+R` does not exceed RF3; observing a stale read does not mean Cassandra malfunctioned. Production apps may intentionally choose lower CLs, but test oracles must reflect **the real contract**, never assuming stronger guarantees.

## 12. Testcontainers 2.x + JUnit 5: Single-Node End-to-End Testing

### 12.1. Choosing Controlled Versions

Testcontainers Java **2.x** moved the Cassandra module to `org.testcontainers.cassandra.CassandraContainer` and artifact `org.testcontainers:testcontainers-cassandra`. Older Testcontainers 1.x examples use `org.testcontainers.containers.CassandraContainer` and `org.testcontainers:cassandra`; do not mix the two generations in one POM without verifying.

Illustrative Gradle Kotlin DSL:

~~~kotlin
dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.12.2")
    testImplementation("org.testcontainers:testcontainers-junit-jupiter:2.0.5")
    testImplementation("org.testcontainers:testcontainers-cassandra:2.0.5")
    testImplementation("org.apache.cassandra:java-driver-core:4.18.1")
}

tasks.test {
    useJUnitPlatform()
}
~~~

JDK 17 and a Docker daemon are prerequisites. Versions shown are released builds, not automatically **latest**. In real projects, pin the Cassandra image by version/digest and manage dependency versions via a BOM for reproducible CI. See [Testcontainers Cassandra module](https://java.testcontainers.org/modules/databases/cassandra/) and [Testcontainers 2.0 release](https://github.com/testcontainers/testcontainers-java/releases).

### 12.2. Complete JUnit 5 Test — Positive ONE + Negative TWO

~~~java
package example;

import com.datastax.oss.driver.api.core.AllNodesFailedException;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.DriverException;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.servererrors.UnavailableException;
import java.time.Duration;
import java.time.LocalDate;
import java.util.UUID;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.testcontainers.cassandra.CassandraContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;
import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
final class CassandraReadinessIT {
    @Container
    static final CassandraContainer CASSANDRA =
        new CassandraContainer(
            DockerImageName.parse("cassandra:4.1"));

    private static CqlSession session;

    @BeforeAll
    static void initSchema() {
        session = CqlSession.builder()
            .addContactPoint(CASSANDRA.getContactPoint())
            .withLocalDatacenter(CASSANDRA.getLocalDatacenter())
            .build();

        session.execute(
            "CREATE KEYSPACE IF NOT EXISTS ready_one_lab " +
            "WITH replication = {'class':'SimpleStrategy', " +
            "'replication_factor':1}");
        session.execute(
            "CREATE TABLE IF NOT EXISTS ready_one_lab.probes " +
            "(probe_id uuid PRIMARY KEY, expected_value text)");

        session.execute(
            "CREATE KEYSPACE IF NOT EXISTS ready_two_lab " +
            "WITH replication = {'class':'SimpleStrategy', " +
            "'replication_factor':2}");
        session.execute(
            "CREATE TABLE IF NOT EXISTS ready_two_lab.probes " +
            "(probe_id uuid PRIMARY KEY, expected_value text)");

        assertTrue(session.checkSchemaAgreement(),
            "Schema must be agreed before probes");
    }

    @AfterAll
    static void shutdown() {
        if (session != null) {
            session.close();
        }
    }

    @Test
    void nodeCanServeDataAtOne() {
        UUID id = UUID.fromString(
            "11111111-1111-1111-1111-111111111111");

        PreparedStatement insert = session.prepare(
            "INSERT INTO ready_one_lab.probes " +
            "(probe_id, expected_value) VALUES (?, ?)");
        BoundStatement write = insert.bind(id, "READY")
            .setConsistencyLevel(DefaultConsistencyLevel.ONE)
            .setTimeout(Duration.ofSeconds(3));
        session.execute(write);

        PreparedStatement select = session.prepare(
            "SELECT expected_value FROM ready_one_lab.probes " +
            "WHERE probe_id = ?");
        BoundStatement read = select.bind(id)
            .setConsistencyLevel(DefaultConsistencyLevel.ONE)
            .setTimeout(Duration.ofSeconds(3))
            .setIdempotent(true);

        Row row = session.execute(read).one();
        assertNotNull(row, "Probe row must be visible");
        assertEquals("READY", row.getString("expected_value"));
    }

    @Test
    void oneNodeCannotSatisfyTwoForRfTwo() {
        PreparedStatement select = session.prepare(
            "SELECT expected_value FROM ready_two_lab.probes " +
            "WHERE probe_id = ?");
        BoundStatement request = select.bind(
                UUID.fromString(
                    "22222222-2222-2222-2222-222222222222"))
            .setConsistencyLevel(DefaultConsistencyLevel.TWO)
            .setTimeout(Duration.ofSeconds(3))
            .setIdempotent(true);

        DriverException error = assertThrows(
            DriverException.class,
            () -> session.execute(request));

        assertTrue(containsUnavailable(error),
            "Expected UNAVAILABLE because RF2 has only one live node, " +
            "got " + error.getClass().getName());
    }

    private static boolean containsUnavailable(Throwable error) {
        if (error instanceof UnavailableException) {
            return true;
        }
        if (error instanceof AllNodesFailedException all) {
            return all.getAllErrors().values().stream()
                .flatMap(java.util.List::stream)
                .anyMatch(CassandraReadinessIT::containsUnavailable);
        }
        return error.getCause() != null
            && error.getCause() != error
            && containsUnavailable(error.getCause());
    }
}
~~~

**Why must negative tests inspect the exact error?** Calling `assertThrows(RuntimeException.class)` without inspecting the cause can PASS on classpath/CQL syntax/auth errors without ever proving insufficient replicas. `containsUnavailable` checks for `UnavailableException` directly **or inside `AllNodesFailedException.getAllErrors()`**, preventing a “false green”.

### 12.3. Expected Results and Limitations

| Test | Expectation | What It Proves |
|---|---|---|
| `nodeCanServeDataAtOne` | PASS | CL ONE write/read on probe under RF1 |
| `oneNodeCannotSatisfyTwoForRfTwo` | PASS upon seeing `UNAVAILABLE` | Even with node running and CQL reachable, single-node RF2 cannot meet CL TWO |
| `session.checkSchemaAgreement` | true | Schema among UP nodes is agreed |
| An RF3 `LOCAL_QUORUM` test | **Not in this suite** | Requires a real multi-node fixture |

**Do not build a three-node cluster by creating three separate `CassandraContainer` instances** and calling it a shared ring. Seed lists, broadcast addresses, DC/rack, ports, tokens/streaming, and networking must be coordinated; trustworthy multi-node tests should use a verified fixture/operator/Compose setup. Gradle/Testcontainers were not executed while authoring this document; commands are instructions for learners to run in an appropriate environment.

### 12.4. Testcontainers Container-Ready Is Not Business-Ready

Testcontainers' `CassandraModule` has a wait strategy to wait until the container satisfies module readiness; `CASSANDRA.isRunning()` and `new CqlSession` succeeding prove bootstrap. However, **only** `nodeCanServeDataAtOne` adds the “CQL data oracle at CL” layer; the second test proves a stronger CL condition can still fail even after the container passes its wait strategy.

## 13. Multi-Node Integration Tests: Genuinely Testing RF3 `LOCAL_QUORUM`

### 13.1. The Fixture Must Be a Real Cluster

A three-node fixture for `LOCAL_QUORUM` simultaneously requires:

1. Three Cassandra processes belonging to **the same cluster name/ring**, not three standalone clusters.
2. Compatible seed list, internode/broadcast addresses, snitch/DC/rack, and network port mappings.
3. `NetworkTopologyStrategy` keyspace with `dc1:3`, providing **3 full replicas** in dc1.
4. Nodes in a stable state (typically `UN`), **with no unexpected JOINING/LEAVING/MOVING**.
5. Schema agreement across UP nodes with DDL/migrations completed.
6. CQL access from the JVM to the appropriate **advertised addresses**, not just 127.0.0.1 of one container.
7. Read/write statements at `LOCAL_QUORUM` **plus data oracle assertions**.

**Multi-node Testcontainers does not happen automatically** by calling `new CassandraContainer(...)` three times. Without a verified fixture, use a dedicated integration-test staging cluster or a Docker Compose/Kubernetes operator test cluster with proper network/DC wiring.

### 13.2. CQL to Initialize the RF3 Fixture (3-Node Lab Cluster Only)

~~~sql
CREATE KEYSPACE IF NOT EXISTS ready_quorum_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS ready_quorum_lab.orders_by_tenant (
  tenant_id text,
  order_id uuid,
  status text,
  revision int,
  PRIMARY KEY ((tenant_id), order_id)
);
~~~

Before running test data, verify:

~~~bash
nodetool status ready_quorum_lab
nodetool describecluster
nodetool netstats
~~~

If a node is `UJ` or `DN`, deciding whether `LOCAL_QUORUM` tests may run depends on **the exact scenario**: one DOWN node in RF3 can still satisfy `LOCAL_QUORUM` (2 ACKs), whereas an **“all nodes ready before rollout”** test requires a stricter gate. Never silently equate “all UN” with the minimum condition to satisfy quorum.

### 13.3. Java RF3 `LOCAL_QUORUM` Probe

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Duration;
import java.util.UUID;

// Assumes session is connected to a 3-node cluster in dc1
// and ready_quorum_lab actually has RF3 with NTS.
UUID orderId = UUID.fromString(
    "33333333-3333-3333-3333-333333333333");

PreparedStatement upsert = session.prepare(
    "INSERT INTO ready_quorum_lab.orders_by_tenant " +
    "(tenant_id, order_id, status, revision) " +
    "VALUES (?, ?, ?, ?)");

BoundStatement write = upsert.bind(
        "tenant-smoke", orderId, "PAID", 42)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setTimeout(Duration.ofSeconds(3));

session.execute(write);

PreparedStatement getOne = session.prepare(
    "SELECT status, revision FROM ready_quorum_lab.orders_by_tenant " +
    "WHERE tenant_id = ? AND order_id = ?");

BoundStatement read = getOne.bind("tenant-smoke", orderId)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setTimeout(Duration.ofSeconds(3))
    .setIdempotent(true);

Row row = session.execute(read).one();
if (row == null
        || !"PAID".equals(row.getString("status"))
        || row.getInt("revision") != 42) {
    throw new AssertionError("LOCAL_QUORUM data oracle failed");
}
~~~

One PASS indicates **this probe query** works at RF3 `LOCAL_QUORUM` in dc1 across both write and read paths. However, a single smoke probe does not replace full token-range coverage, concurrent-write consistency tests, or prior data recovery validation.

### 13.4. Testing Availability When One Node Is DOWN — Only in Authorized Fixtures

With RF3 and local quorum=2:

| Replica State of Partition P | Expectation at `LOCAL_QUORUM` |
|---|---|
| A/B/C UP and responding on time | PASS |
| A/B UP, C DOWN | Can PASS if A/B are healthy |
| Only A UP | UNAVAILABLE |
| A/B UP, but B misses timeout | Possible `READ_TIMEOUT`/`WRITE_TIMEOUT` |

**Never** run `nodetool stop`/`docker kill` in production just to test. When running in fault-injection staging, record **which replica was stopped**, exact token ownership, baseline reads/writes, expected error, and recovery; otherwise stopping a node **outside the probe's replica set** might not affect the result at all.

### 13.5. Probing Multiple Representative Partitions

~~~text
Probe P1 -> natural replicas A,B,C
Probe P2 -> natural replicas B,C,D
Probe P3 -> natural replicas C,D,E
...

Each probe:
  write(WCL) -> read(RCL) -> assert value/revision
  capture coordinator, latency, retry/error types
~~~

Use a controlled, fixed list of partition IDs spanning key racks/token ranges so tests remain reproducible. Do not create millions of partitions and run readiness checks every second; that belongs in a separate workload/soak test.

## 14. Startup Races and Deadline-Bounded Polling

### 14.1. Why `Thread.sleep(10000)` Is Weak

~~~java
container.start();
Thread.sleep(10_000);
session.execute("SELECT release_version FROM system.local");
~~~

On a dev laptop, 10 seconds may be excessive; on a cold CI Docker runner with slow disk or JVM startup, it may be too short. Conversely, if ready in 1 second, waiting 9 extra seconds wastes time. **Never** use fixed sleeps to prove data readiness.

### 14.2. Proper Bounded Polling

~~~java
import java.time.Duration;
import java.util.concurrent.Callable;
import java.util.concurrent.locks.LockSupport;

public final class ReadinessAwait {
    private ReadinessAwait() {}

    public static void until(
            String description,
            Duration totalBudget,
            Duration interval,
            Callable<Boolean> probe) throws Exception {

        long deadline = System.nanoTime() + totalBudget.toNanos();
        Throwable lastTransient = null;
        int attempts = 0;

        while (System.nanoTime() < deadline) {
            attempts++;
            try {
                if (Boolean.TRUE.equals(probe.call())) {
                    return;
                }
            } catch (com.datastax.oss.driver.api.core.servererrors
                    .UnavailableException transientUnavailable) {
                lastTransient = transientUnavailable;
            } catch (com.datastax.oss.driver.api.core
                    .DriverTimeoutException transientTimeout) {
                lastTransient = transientTimeout;
            }

            long nanosRemaining = deadline - System.nanoTime();
            if (nanosRemaining <= 0) {
                break;
            }
            LockSupport.parkNanos(
                Math.min(interval.toNanos(), nanosRemaining));
            if (Thread.interrupted()) {
                throw new InterruptedException(
                    "Readiness wait interrupted");
            }
        }

        AssertionError failure = new AssertionError(
            description + " not ready after " + attempts +
            " attempts within " + totalBudget);
        if (lastTransient != null) {
            failure.initCause(lastTransient);
        }
        throw failure;
    }
}
~~~

**Distinguishing transient vs permanent errors:** The example catches only `UnavailableException` and `DriverTimeoutException`, never wrapping every exception in a retry loop. If CQL syntax is invalid, permissions are missing, the table does not exist, or Java codecs mismatch, tests must **fail fast**. Some driver errors may be wrapped inside `AllNodesFailedException`; production helpers should inspect nested errors explicitly instead of `catch(Exception ignored)`.

### 14.3. Keep Per-Attempt Timeout Smaller Than `totalBudget`

~~~java
BoundStatement probe = statement
    .setTimeout(Duration.ofSeconds(2));

ReadinessAwait.until(
    "orders_by_id LOCAL_QUORUM",
    Duration.ofSeconds(45),
    Duration.ofMillis(750),
    () -> {
        Row row = session.execute(probe).one();
        return row != null
            && "PAID".equals(row.getString("status"));
    });
~~~

If an app requires a strict suite-wide hard deadline, check remaining time before each attempt and cap the request timeout accordingly. The pattern above can overshoot the deadline by up to **one in-flight attempt**; it is a lesson polling helper, not a hard-cancelling scheduler.

**Never poll on a driver Netty I/O thread.** In JUnit, blocking waits on the test thread are by design; in reactive/async production code, use nonblocking schedulers with appropriate jitter.

### 14.4. Poll Reads Instead of Blindly Replaying Writes

If a probe write times out, the outcome may be unknown. Do not put `session.execute(INSERT)` inside a polling loop with a **brand-new UUID on each iteration** to “wait until the write succeeds”. Instead:

1. Generate a **fixed probe ID** per logical run/attempt.
2. Write at the designated WCL; on success, switch to read polling.
3. If the write times out or loses its response, mark `UNKNOWN_OUTCOME`.
4. Re-check by PK using an appropriate RCL/source of truth before deciding to replay.
5. Replay only if the upsert/idempotency contract has been reviewed.

### 14.5. Startup Retry Budget Guidelines

| Error | Short Startup Retry Allowed? | Notes |
|---|---|---|
| TCP connection refused during boot window | Bounded | Container/native port not open yet |
| `UNAVAILABLE` while waiting for replicas UP | Bounded | While topology is converging |
| Transient `READ_TIMEOUT` | Bounded, inspect server metrics | Never retry indefinitely on slow disks |
| InvalidQuery / unconfigured table right after DDL | Only after checking schema agreement | Schema may still be propagating, but genuinely broken queries must fail |
| Unauthorized / invalid credentials | **No** | Fix auth/RBAC |
| Wrong local DC | **No** | Fix driver config |
| Wrong value/revision after stabilization window | **No PASS** | Investigate data/restore/repair |

## 15. When Nodes Are JOINING, MOVING, LEAVING, or REPLACING

### 15.1. Topology States Are a Process, Not Proof of Data Readiness

~~~text
Node process starts
    |
Gossip joins ring (UJ may appear)
    |
Token ownership / streaming / bootstrap
    |
Node normal (UN)
    |
Data/replica CL service must be verified empirically
    |
Node traffic promoted per readiness contract
~~~

Never treat `UJ` as “streaming finished”. Conversely, even once a node is `UN`, still verify Cassandra for **the exact keyspace/token/CL**, especially during replace, restore, or active ingest.

### 15.2. Node Readiness and Service Readiness Can Diverge

For example, under RF3 while node C is bootstrapping:

- The service may still serve `LOCAL_QUORUM` via A+B **without** C.
- That does not mean C is ready to receive all traffic/new tokens.
- Nor does C being unready force the whole service to FAIL if the contract permits degraded operation with sufficient replicas.

Track separately:

~~~text
node_ready_for_new_traffic
query_family_ready_at_CL
cluster_ready_for_next_topology_step
data_migration_complete
~~~

All four states can differ simultaneously. A good controller/operator evaluates multiple gates rather than one `ready` boolean.

### 15.3. Adding Nodes or Increasing RF

For a keyspace increasing RF from 2 to 3:

~~~text
ALTER KEYSPACE ... replication RF=3
             |
       Schema agreement
             |
    Natural replica mapping changes
             |
 Existing SSTables must reach new replicas
             |
  Full repair/streaming per runbook/version
             |
  Readiness probe seeded historical partitions
             |
       Migration gate complete
~~~

**Never assume `ALTER KEYSPACE` automatically copies all historical data.** After an RF change, execute the data synchronization/repair workflow per version docs and verify real data. [Apache Cassandra Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html) explains that a full repair is typically needed to distribute data after an RF increase. A probe written **after** the RF change and read back successfully does not prove all records written **before** the RF change have full replicas.

### 15.4. Restoring a Snapshot

After restoring SSTables/snapshots:

1. Verify keyspace/table/schema compatibility.
2. Verify required SSTables were loaded/refreshed properly.
3. If topology/RF changed, follow a dedicated streaming/repair and verification plan.
4. Read **sample seeded records from before the backup timestamp**, not only newly inserted records.
5. Cross-check counts/checksums/versions against partitions/business oracles; meeting CL alone does not prove complete data.

A Cassandra node can be `UN` and answer `SELECT release_version` while many historical partitions remain unrestored. That is the clearest illustration of **process readiness** vs **data readiness**.

## 16. Test Matrix for Startup and Data Scenarios

| Scenario | Container/Process | Local CQL | Schema Agreement | Required CL | Data Oracle |
|---|---|---|---|---|---|
| Node bootstrapping, native port closed | RUNNING | FAIL | Unknown | FAIL | Not tested |
| Single UN node, RF1, ONE | RUNNING | PASS | PASS | PASS | Can PASS |
| Single UN node, RF2, TWO | RUNNING | PASS | PASS | **FAIL** | Cannot verify at TWO |
| RF3, 2 healthy replicas, LOCAL_QUORUM | RUNNING | PASS | Can PASS | Can PASS | Must read/compare |
| RF3, 1 healthy replica, LOCAL_QUORUM | RUNNING | PASS | Can PASS on UP nodes | **FAIL** | Unproven |
| 3 UN cluster, table not yet created | RUNNING | PASS | Can PASS for existing schema | Query fails | FAIL |
| 3 UN cluster, historical data unrestored | RUNNING | PASS | PASS | Can PASS with empty row | **FAIL** if expected row missing |
| 3 UN cluster, write ONE/read ONE | RUNNING | PASS | PASS | Both calls can PASS | May read stale |
| NTS dc1 RF3 dc2 RF2, one dc2 node DOWN | RUNNING | PASS | Can PASS | dc1 LQ PASS, dc2 LQ FAIL | Differs by DC |
| Full repair saturating disk, replicas UP | RUNNING | PASS | PASS | May timeout | May miss SLO |
| App driver local DC misconfigured | RUNNING | May reach seed | Uncertain | Routing/connection FAIL | Insufficient proof |
| Auth role lacks SELECT on user table | RUNNING | `system.local` can PASS | PASS | Unexecutable | FAIL |

**Note:** “Can PASS” states a **possibility**. To declare a test passed, execute commands on a real fixture and inspect responses/values rather than inferring from a table.

### 16.1. Controlled Pairings on the Same Cluster

A strong test suite includes **contrast pairs**:

~~~text
T1 - RF1 / CL ONE / 1 node:
  EXPECT_SUCCESS

T2 - RF2 / CL TWO / 1 node:
  EXPECT_UNAVAILABLE

T3 - RF3 / CL LOCAL_QUORUM / 3 nodes UP:
  EXPECT_SUCCESS

T4 - RF3 / CL LOCAL_QUORUM / 1 natural replica UP:
  EXPECT_UNAVAILABLE

T5 - RF3 / CL LOCAL_QUORUM / 2 natural replicas UP:
  EXPECT_SUCCESS_IF_RESPONSES_IN_DEADLINE

T6 - Restore test: schema agreed, seeded row absent:
  EXPECT_DATA_ORACLE_FAILURE
~~~

T3–T5 require a **multi-node fixture**. T4–T5 should only be fault-injected in an approved isolated staging environment with known replica placement. T6 requires a seed manifest, checksum, or source-of-truth—not merely `SELECT`ing a row created after restore.

### 16.2. Which Checks Should Be Separated from the Integration Suite?

| Test Type | Goal | When to Run |
|---|---|---|
| Java unit tests | Mapper/codec/CL selection, no Cassandra needed | Every commit |
| Single-node Testcontainers | Valid CQL, migrations, RF1/ONE, oracle | Regular CI |
| Multi-node integration | RF3 `LOCAL_QUORUM`, per-token availability | CI with adequate infra or scheduled |
| Fault injection | Node/network/slow replica, retries/timeouts | Controlled staging |
| Restore/repair rehearsal | Historical data integrity, RPO/RTO | Pre-release/periodic |
| Production canary | Real data/latency within SLO | Deploy/traffic change, minimal load |

Do not force every pull request to boot a 6-node multi-DC cluster if CI lacks resources; **neither should you skip multi-node testing altogether** and claim single-node tests proved RF/CL behavior.

## 17. Kubernetes Liveness, Readiness, and Startup Probes

### 17.1. Three Probes Do Not Mean the Same Thing

| Probe | Purpose | Appropriate Check |
|---|---|---|
| `startupProbe` | Allows slow Cassandra startup before liveness applies | Basic process/JVM/native transport |
| `livenessProbe` | Detects wedged processes needing restart | Process health; avoid strict cluster-wide quorum dependencies |
| `readinessProbe` | Decides whether node/pod receives traffic | Fits node role, though not necessarily cluster-wide business CL |

**Never set a `LOCAL_QUORUM` query on user data as the `livenessProbe` for every Cassandra pod.** When two replicas hiccup, every pod can fail simultaneously and Kubernetes will restart the remaining healthy pods, worsening the outage. Liveness checks the **node process**, whereas quorum readiness should be evaluated by the service/operator/gateway from **multiple signals**.

### 17.2. CQL Coordinator Readiness Differs from Service Data Readiness

A node may open CQL and answer system tables while lacking natural replicas for every keyspace. Application load balancers should:

- Check session/connections and usable nodes.
- Have canary or startup integration gates for the **application's keyspace/CL**.
- Monitor production error rates, p95/p99, and replica availability.
- Separate “this node accepts connections” from “this feature may take traffic at required CL”.

If a Cassandra operator exposes conditions for bootstrap/repair/safe-to-drain, use them as supplemental signals while still validating **data oracles** for migrations/restores.

### 17.3. False Restart Loop from Misused Quorum Readiness

~~~text
Node B DOWN
    |
Liveness on A/C reads LOCAL_QUORUM on a partition owned by B
    |
Several probes time out
    |
Kubernetes restarts A/C even though A/C are healthy
    |
Available replicas drop further
    |
Cluster outage cascades
~~~

An availability check can **block rollout/traffic promotion**, yet should rarely **kill pods**. Keep gate failure actions distinct.

## 18. Java Application Readiness and Admission Control

### 18.1. An App Can Serve HTTP Before Cassandra Meets CL

A Spring Boot service can finish JVM startup, listen on port 8080, and return 200 on `/health` while the Cassandra keyspace is unmigrated or lacks local quorum. To prevent false greens:

~~~text
App boot
   |
JVM/HTTP basic startup
   |
Connect Cassandra
   |
Schema/CL/data readiness probe
   |
Enable business endpoints / traffic
   |
Observe ongoing errors and p99
~~~

The app may open `/live` early (telling the orchestrator the process is alive) while `/ready` only PASSES when **required dependencies** reach their target state. If a feature does not depend on Cassandra, do not fail the entire service needlessly; apply **dependency-aware degradation** and route gating by design.

### 18.2. Never Create a Session per Readiness Request

~~~java
// WRONG for an HTTP readiness endpoint called every second:
public boolean isReady() {
    try (CqlSession s = CqlSession.builder().build()) {
        return s.execute("SELECT release_version FROM system.local")
            .one() != null;
    }
}
~~~

Repeatedly opening/closing sessions triggers reconnects, metadata refreshes, and auth/TLS handshakes that can overwhelm Cassandra right as it recovers. Use **one shared `CqlSession`** and evaluate state/CL at controlled intervals. Liveness should check process state only, without running user-data CQL.

### 18.3. Distinguishing Fail-Closed vs Degrade

| Use Case | When Cassandra Lacks CL | Action |
|---|---|---|
| Financial/transactional writes | Cannot uphold consistency contract | Fail closed; return coded error; avoid blind writes |
| Non-critical historical reads | Strong CL temporarily unavailable, valid cache exists | May serve stale cache if contract permits |
| Admin API | Authorized to inspect status without writes | Allow read-only status routes |
| Metrics/telemetry | Avoid worsening outages | Rate-limit health probes; use cached indicators |
| Batch worker | Lacks quorum/repair | Pause job, checkpoint, resume when gate PASSES |

**Never silently downgrade CL from `LOCAL_QUORUM` to `ONE`** just to turn readiness green, unless business requirements explicitly define a degraded mode and test for stale/unknown data.

## 19. Test Data and Oracles: Don't Measure “Empty Is OK”

### 19.1. Two Probe Styles to Separate

| Probe Type | Where Is the Data? | What Does It Prove? | Limitations |
|---|---|---|---|
| **Synthetic write/read** | Test creates a dedicated row, then reads it back | Write/read path works at WCL/RCL | Does not prove historical data exists |
| **Seeded known-data read** | Pre-loaded via manifest/snapshot/migration | Prior data is visible with expected value/version | Does not prove new write path is healthy |
| **Real workload canary** | Authorized business keys | Query shape/latency close to production | Must guard PII/side effects |
| **Token-range sample** | Probe IDs spread across tokens/racks | Multiple natural replica sets can serve | Does not prove entire dataset |
| **Checksum/count verification** | Migration/backup dataset | Detects missing/altered data | Cassandra `COUNT(*)` can be very costly; avoid full table scans |

During restores/migrations, you need **seeded data** whose oracle lives outside the target cluster (backup manifest, event source, audit log). If a test merely INSERTs a new row post-restore, it only proves the new data path—and can easily PASS while 90% of historical SSTables are missing.

### 19.2. Avoid Full-Table `COUNT(*)` for Readiness

~~~sql
-- Do not use for periodic liveness/readiness:
SELECT COUNT(*) FROM huge_orders_table;
~~~

Cassandra is not optimized for global counts across billions of rows; the query scans many partitions, spikes disk/CPU, triggers paging/timeouts, and worsens cluster recovery. Instead:

- Check **known partition keys** from a manifest and expected revision/hash.
- Check **representative samples** across tokens/tenants/time buckets.
- Use **offline checksum/SSTable verification** and source/target reconciliation for large migrations.
- State tolerances/coverage and report exact scope—never claim “100% table verified” when sampling.

### 19.3. Seeded Data with TTL or Tombstones

~~~text
Manifest expects:
  tenant = t1, order = o1, status = PAID
  created_at = T0
  TTL = 24h

Probe at T0+25h:
  row missing

Do not immediately conclude "node cannot serve CL":
  TTL may have expired by design.
~~~

Probes must understand TTLs, tombstones/deletes, and expected visibility at probe time. For long-lived sentinel rows, use a separately managed dataset that does not auto-expire when validating historical restores. Conversely, synthetic writes should use bounded TTLs to prevent unbounded growth, yet long enough not to expire mid-test.

### 19.4. Synthetic Probes Can Generate Tombstones

A common pattern:

~~~text
Readiness every second:
  INSERT probe -> SELECT probe -> DELETE probe
~~~

Continuous repetition creates mutation/tombstone churn, unsuitable for arbitrary APIs/tenants and harmful to an already stressed cluster. Alternatives:

- Rely primarily on cached readiness + error metrics, running lightweight probes on a controlled cadence.
- Use a sparse dedicated table/partition with bounded IDs and appropriate TTLs.
- Avoid continuous DELETEs when controlled TTL/cleanup suffices.
- Cap concurrency; never run millions of probes.
- Never mutate or delete production business rows for testing.

### 19.5. Stable Probe IDs and Idempotency Risks

If a write probe times out and Java does not know whether the coordinator persisted it, generating a new ID and retrying can create duplicate rows. A good integration test tracks:

~~~text
run_id = deterministic within one test run
probe_id = stable for this logical probe
written_revision = monotonic or fixed within run
write_outcome = ACK / UNKNOWN
readback = expected value / version / missing
cleanup = isolated by environment or bounded TTL
~~~

Under concurrent writes or LWW timestamp conflicts, probes must use dedicated keys/values to prevent collisions across suites or parallel tests.

## 20. Java Error Taxonomy: “Quorum Unmet” vs “Misconfigured Test”

### 20.1. Distinct Exception Categories

| Java Driver 4.x Error | Issue Class | First Things to Diagnose |
|---|---|---|
| `UnavailableException` | Too few live replicas for CL at coordinator | RF/DC/replica set/gossip liveness |
| `ReadTimeoutException` | Replica read responses missed deadline | Read path, disk/GC/network, tombstones |
| `WriteTimeoutException` | Write ACKs missed deadline; outcome may be unknown | Commitlog/memtable, disk/GC, CL/replicas |
| `ReadFailureException` | Replica read execution error | Node logs/IO/repair |
| `WriteFailureException` | Replica write execution error | Node logs/IO/commitlog |
| `DriverTimeoutException` | Client/driver deadline expired | Pool, queue, retries, network, server latency |
| `AllNodesFailedException` | Per-coordinator error collection | `getAllErrors()`; may contain mixed causes |
| `NoNodeAvailableException` | No usable node in query plan | Local DC/contact points/connection policy |
| `InvalidQueryException` | Invalid query/schema | Migrations/DDL/columns/types |
| `UnauthorizedException` | Insufficient role/grants | Test credentials/RBAC |
| Codec/marker mismatch | Wrong Java binding | DTO/CQL types/prepared metadata |

### 20.2. Handling Aggregated Per-Node Errors

~~~java
import com.datastax.oss.driver.api.core.AllNodesFailedException;
import com.datastax.oss.driver.api.core.metadata.Node;
import java.util.List;
import java.util.Map;

void reportSanitizedErrors(AllNodesFailedException error) {
    for (Map.Entry<Node, List<Throwable>> entry :
            error.getAllErrors().entrySet()) {
        Node node = entry.getKey();
        for (Throwable cause : entry.getValue()) {
            System.err.printf(
                "coordinator=%s type=%s%n",
                node.getHostId(),
                cause.getClass().getSimpleName());
        }
    }
}
~~~

`AllNodesFailedException` does not prove “all Cassandra nodes are dead”; it might wrap `UNAVAILABLE` on node A, a connection error on node B, and a read timeout on node C. A readiness suite must preserve **root causes** instead of throwing an uninformative `AssertionError("cluster not ready")`.

### 20.3. Failure Reason Mapping

~~~text
readiness test FAIL
        |
        +-- Cannot connect / open session?
        |      -> Docker/startup/auth/TLS/contact point/local DC
        |
        +-- Invalid CQL / schema?
        |      -> Migration/DDL/schema agreement
        |
        +-- UNAVAILABLE?
        |      -> RF/CL/replica liveness/placement
        |
        +-- READ/WRITE TIMEOUT?
        |      -> Replica response deadline/disk/GC/queue
        |
        +-- Row present but wrong value?
        |      -> Wrong key/TTL/tombstone/repair/LWW/version
        |
        +-- Right value but too slow?
               -> SLO/partition size/compaction/capacity
~~~

Never report “Docker failed” when the container is running yet requests fail CL. Never report generic “Cassandra unavailable” when the Java driver has the **wrong DC** or the schema lacks a table.

### 20.4. Startup Retries Differ from Business Retries

A test may poll `UNAVAILABLE` while waiting for nodes to finish bootstrapping, but **must not** retry:

- All exceptions indefinitely.
- `InvalidQuery` when a migration is genuinely missing.
- `Unauthorized` caused by bad credentials.
- `WriteTimeout` on non-idempotent operations when the outcome is unknown.
- Persistent data-oracle mismatches as if they were “transient” until hitting a generic timeout.

Permitted retries must have **bounded attempts/deadlines**, preserve the last cause, emit retry telemetry, and avoid overloading a booting cluster.

## 21. Observability: Measuring Liveness, CL, and Data Paths Together

### 21.1. Signal Layers

~~~text
CONTAINER
  process status / restart count / CPU/memory

NODE / GOSSIP
  nodetool status, ring, joining/leaving, repair/streaming

DRIVER
  nodes UP, connections, request/client timeouts
  retries/speculation, coordinator, pool in-flight

CASSANDRA SERVER
  ClientRequest.Read/Write Latency, Unavailables
  pending compaction, SSTables-per-read, tombstones, GC

BUSINESS PROBE
  WCL / RCL / partition sample, expected value/version
  pass/fail/unknown, elapsed latency
~~~

Each layer answers a different question. Never substitute a Docker `ready=1` flag for Cassandra server metrics, and never conclude every keyspace/CL is available solely because nodes report UP.

### 21.2. Safe Observation Commands

~~~bash
nodetool status
nodetool status ready_quorum_lab
nodetool describecluster
nodetool netstats
nodetool tpstats
nodetool compactionstats
nodetool tablestats ready_quorum_lab.orders_by_tenant
~~~

These commands read state without repairing, moving, or removing nodes. They do not directly answer “was record X written at `CL=LOCAL_QUORUM`?”—that requires a record-specific read/write oracle.

### 21.3. Useful Driver Metrics

~~~hocon
datastax-java-driver {
  advanced.metrics {
    session.enabled = [
      connected-nodes,
      cql-requests,
      cql-client-timeouts
    ]
    node.enabled = [
      cql-messages,
      errors.request.unavailables,
      errors.request.read-timeouts,
      errors.request.write-timeouts,
      retries.total,
      pool.in-flight,
      pool.open-connections
    ]
  }
}
~~~

These are **driver metric option names** in the 4.x line; exported names in Prometheus/Dropwizard/Micrometer depend on the backend. Enabling config alone does not export metrics without a registry/reporter. Before using a dashboard as a release gate, verify the series are actually scraped.

### 21.4. KPI Table for a Readiness Suite

| Metric | Meaning | Caution |
|---|---|---|
| `process_up_ratio` | Running process count | Does not measure CL |
| `node_state_UN_ratio` | Nodes Normal per gossip | Does not guarantee data correctness |
| `schema_agreement_success` | UP nodes agree on schema | Does not measure historical data |
| `probe_success_by_cl` | Probe success rate at CL | Label by CL/keyspace/query family, never raw keys |
| `probe_value_mismatch` | Data oracle mismatch | Critical even if CQL returned 200 |
| `probe_unavailable_count` | Insufficient replicas during probe | Break down by DC/CL |
| `probe_read_write_timeout_count` | Queries missing deadlines | Investigate both server and client |
| `probe_p95/p99_latency` | Probe SLO | Never estimate server latency by subtracting p99s |
| `streaming/repair_backlog` | Active data movement | Does not prove any specific row is valid |
| `cql_messages/request` | Amplification from retries/speculation | Compare across same scope/window |

**Avoid metric labels** containing tenant IDs, per-probe UUIDs, raw tokens, or PII due to high cardinality and data leakage. Stick to bounded-cardinality labels: query family, environment, keyspace, DC, CL, and outcome type.

## 22. Variables That Easily Cause “False Greens” in Integration Tests

### 22.1. CL Silently Falling Back to Default

~~~java
PreparedStatement p = session.prepare(
    "SELECT status FROM ready_quorum_lab.orders_by_tenant " +
    "WHERE tenant_id=? AND order_id=?");

// WRONG: omits CL, relies on default execution profile.
Row row = session.execute(p.bind(tenantId, orderId)).one();
assertNotNull(row);
~~~

If the default profile is `LOCAL_ONE`, this test **never checks `LOCAL_QUORUM`** even if the PR calls it `readAtQuorum`. Fix:

~~~java
BoundStatement checked = p.bind(tenantId, orderId)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setIdempotent(true);
Row row = session.execute(checked).one();
~~~

When using named execution profiles, inspect both effective `REQUEST_CONSISTENCY` and any explicit statement overrides. Do not rely solely on reading `application.conf` text because system properties or programmatic loaders may take higher precedence.

### 22.2. Changing RF Without Updating the Math

~~~text
Before:
  dc1 RF=2 -> LOCAL_QUORUM requires 2

After:
  dc1 RF=3 -> LOCAL_QUORUM requires 2

Later:
  dc1 RF=4 -> LOCAL_QUORUM requires 3
~~~

If a test hardcodes `required=2` for every local quorum, RF4 with only two UP replicas will falsely PASS. Read actual schema replication metadata and policies; for transient replication, apply the proper calculation rather than the simple full-RF formula.

### 22.3. Changing Local DC While Tests Still Target the Old DC

~~~text
Service newly deployed in dc2
Driver config still has local-datacenter=dc1
LOCAL_QUORUM probe succeeds by routing to dc1
=> Does not prove service can serve dc2 local quorum.
~~~

Verify the `CqlSession`'s actual local DC, contact points, coordinator in `ExecutionInfo`, and Cassandra `system.local.data_center`; test per deployment location. `LOCAL_QUORUM` follows the **coordinator's local DC**, not the test author's assumption.

### 22.4. Stale Test Data Causing False Passes

If tests reuse the same `probe_id` in a persistent table across CI runs, yesterday's row may still be present:

~~~text
Today's run:
  WRITE did not actually succeed (unknown outcome)
  READ sees old row == "READY"
  Test falsely reports PASS.
~~~

Fix this with **unique run IDs/revisions** and verify expected version/timestamp. For concurrent tests, isolate namespaces/keyspaces or partitions/IDs; when retrying within the same run, keep the operation ID stable to avoid duplicates.

### 22.5. Short TTL Causing Random Probe Disappearances

Read-after-write with a 1-second TTL and a 5-second CI cold start can fail even when replicas are healthy. Readiness tests should use sufficiently long TTLs or non-TTL records with explicit cleanup; avoid tiny TTLs that force unrepresentative failures.

### 22.6. Driver Retries Masking a Bad Node While Data Meets CL

A `LOCAL_QUORUM` request can PASS after retrying coordinator B while coordinator A is network-isolated:

~~~text
Result correctness PASS
Retry count > 0
Coordinator A errors > baseline
~~~

PASS on **functional CL/data readiness** does not equal PASS on **cluster health/SLO readiness**. During rollouts, monitor retries, per-node failures, p99, and token/rack coverage. Never mark the entire cluster healthy solely from a retried success.

### 22.7. Overgeneralizing Read-Your-Writes

If W=`ONE`, R=`ONE` happens to return the newest value in a test, never document “Cassandra always provides read-your-writes at ONE”. That could be due to hitting the same coordinator/replica or lucky timing. Tests must rely on **the RF/CL contract**, never generalizing one lucky run into a consistency guarantee.

### 22.8. Testing `system.local` Instead of the User Keyspace

`system.local` holds local node info and does not share the application keyspace's RF/quorum or data. It is great for **liveness**, insufficient for **business readiness**.

### 22.9. Running `nodetool status` from Only One Node

Gossip liveness and network partitions can give nodes divergent views. `UN` from coordinator A does not prove coordinator B or another DC sees the same state. During multi-DC incidents, gather signals from multiple vantage points, cross-checking driver node metadata, errors, and actual CL queries.

### 22.10. Enough Replicas, Wrong CQL Permissions

Running `cqlsh` as superuser may PASS, while the service role can only SELECT system tables and lacks permissions on business tables. Readiness tests should run with **the same role/TLS/auth and execution profile as the application**, never using admin credentials to validate the environment.

## 23. Readiness Runbook: GO / HOLD / STOP

### 23.1. Preflight Before Opening Traffic or Raising RF

1. **Define objective:** Cassandra node restart, RF change, schema migration, restore, adding a DC, or deploying a Java service.
2. **Lock scope:** Cluster, keyspace, DC/rack, query family, partition/token samples, read/write CL, RF map.
3. **Verify topology:** `nodetool status <keyspace>`, UP/DOWN/JOINING nodes, and streaming/repair plan.
4. **Verify schema:** DDL results/schema agreement and refreshed driver metadata.
5. **Verify data oracle:** Seeded historical samples if required; synthetic WCL/RCL probes if testing write paths.
6. **Set budgets:** Total deadline, per-attempt timeout, retry interval, and max load.
7. **Enable metrics:** Client errors/retries/p95/p99 and server read/write latencies, GC/disk/compaction.
8. **Protect data:** Read-only probes where possible; synthetic writes in isolated namespaces/partitions with fixed IDs and controlled cleanup.
9. **Ensure rollback:** Clear owner and ability to halt rollout/drain routing while investigating.

### 23.2. Gate Sequence

~~~text
T0  Process/container started
        |
T1  Native CQL reachable + correct credentials/DC
        |
T2  Check nodetool/driver metadata node states
        |
T3  Check schema agreement + migrations
        |
T4  Check CL availability for representative keys
        |
T5  Verify seeded/historical oracle
        |
T6  Verify synthetic write/read at declared WCL/RCL
        |
T7  Observe stability for configured interval
        |
         +-------------------------------+
         |                               |
      ALL PASS                       FAIL/UNKNOWN
         |                               |
      GO canary                    HOLD/STOP rollout
         |                        classify cause
      Expand traffic                     |
         |                         Investigate/
      Recheck metrics                 reconcile
         |                               |
      Record evidence            Retest same contract
~~~

Every gate needs an **owner** and defined retryable startup errors. Never let a “TCP port open” check bypass missing seed data or unmet CL/quotas.

### 23.3. Decision Table

| Signal | Decision | Action |
|---|---|---|
| Docker RUNNING, 9042 not open yet | **HOLD** | Wait within bounded startup; inspect logs |
| CQL `system.local` PASS, user table missing | **STOP** | Fix migration/schema agreement |
| RF3 LQ, only 1 natural replica UP | **STOP** | Restore replica; do not lower CL |
| RF3 LQ, 2 replicas UP, probe PASS, p99 steady | **Controlled GO** | Accept degraded mode per SLO |
| LQ probe PASS, but historical row missing | **STOP** data restore gate | Restore/repair/manifest reconciliation |
| Query PASS at CL ONE, production requires LQ | **HOLD** | Insufficient evidence for target CL |
| Transient `UNAVAILABLE` during bootstrap, budget left | **HOLD with bounded retry** | Monitor topology |
| `DriverTimeoutException` with rising disk/GC | **HOLD** | Address capacity/queue/I/O; don't raise retries blindly |
| Auth/role error | **STOP** | Fix RBAC; do not retry |
| Probes PASS, but retries/connection churn rising | **HOLD** | Investigate hidden fault before expanding |
| Token/DC samples pass, p99 and oracle steady | **GO** | Expand traffic incrementally |

### 23.4. What Does Rollback Mean?

Rolling back a **deployment config** does not automatically roll back writes:

- If Cassandra applied a mutation during a test timeout, the outcome may be unknown; keep the operation ID and reconcile.
- If an RF/schema migration committed, “rolling back the Java service” does not revert data topology.
- If nodes started streaming/repairing, do not kill/stop them arbitrarily; follow the operator runbook.
- If only a health gate changed, reverting the gate does not fix missing data—data oracle failures still require investigation.

After rollback, re-run **the same contract** across T4–T6, confirm no missing data, and wait for SLOs/resources to return to safe bounds. Never just read a reverted config file and mark `ROLLBACK_COMPLETE`.

### 23.5. Post-Deploy Verification Sheet

~~~text
CHANGE_ID:
SERVICE / LOCAL_DC:
CASSANDRA VERSION / JAVA DRIVER VERSION:
KEYSPACE / RF PER DC:
QUERY FAMILY / TABLE:
SAMPLED TOKEN RANGES / PARTITION COUNT:
WCL / RCL:
SCHEMA AGREEMENT (UP nodes):
NODE STATUS / STREAMING / REPAIR:
SEEDED DATA ORACLE:
SYNTHETIC WRITE-READ ORACLE:
TIMEOUT / ERRORS / RETRIES:
P95/P99 / SERVER RESOURCE:
GO / HOLD / STOP:
UNRESOLVED UNKNOWN OUTCOMES:
OWNER / UTC TIME / NEXT ACTION:
~~~

This template is a documentation checklist, not a file to create. The accurate conclusion should be **“ready for query family X at CL Y on samples Z, at time T within SLO B”** rather than an unconditional “Cassandra 100% ready”.

## 24. Real-World Test Cases and Incident Scenarios

### Case A — Docker Health Check Green, Java Fails Connecting to 9042

**Symptom:** Container runs and Cassandra logs show “startup complete”, yet the driver throws connection refused or TLS handshake exceptions.

**Analysis:** The healthcheck may only check the process or JMX; native transport may not be open yet, IP/port mapping may be wrong, SSL may require client certs, or a firewall may block traffic.

**Test:** Use Testcontainers' `getContactPoint()` or service discovery endpoints, the real local DC, and application-matching credentials/TLS. Do not test CL before CQL connectivity is confirmed.

### Case B — `system.local` Returns 1 Row, Application Table Does Not Exist

**Symptom:** `SELECT release_version FROM system.local` PASSES, while `SELECT ... FROM orders_by_id` returns `unconfigured table`.

**Cause:** Migration has not run, schema has not propagated, or wrong keyspace. This is a G3 issue, before G4/G5.

**Decision:** STOP routes touching the user table; wait for bounded schema agreement/verify DDL instead of retrying the same failing query forever.

### Case C — Single-Node Cassandra RF1/ONE Runs Fine, Team Claims “Quorum Tested”

**Wrong:** RF1/ONE needs only one replica and never exercises inter-replica gossip or quorum.

**Right:** Single-node CI only verifies CQL/mappers/migrations; explicitly record that multi-node RF3 `LOCAL_QUORUM` was not tested. A negative RF2/TWO test on one node can **illustrate the principle**, not replace multi-node tests.

### Case D — Single-Node RF2, CQL Port Open, CL TWO Returns UNAVAILABLE

**Conclusion:** This is **expected behavior** because the keyspace defines 2 full replicas on only one physical node. Do not bump a 2s timeout to 30s hoping a second replica appears.

**Test:** Assert the exact `UnavailableException`, including when wrapped inside `AllNodesFailedException`.

### Case E — RF3, Two Replicas UP, One DOWN, `LOCAL_QUORUM` Still Passes

**Conclusion:** The service can still satisfy CL=2 for that token. However, the DOWN node still needs recovery, and losing one more node will break quorum.

**Decision:** GO degraded/canary if business/SLO allows; HOLD further topology changes. Do not mark “all nodes ready”.

### Case F — RF3, All Three Nodes `UN`, Yet `READ_TIMEOUT`

**Analysis:** Gossip/driver see nodes UP; I/O, GC, compaction, or queues prevent enough timely ACKs. `UN` does not guarantee responses within deadlines.

**Test:** Measure server read latency, SSTables-per-read, tombstones, disk await, and request timeouts; avoid infinite waits or downgrading CL when LQ is required.

### Case G — RF3, Write ONE Succeeds, Read ONE Returns `NEW` Instead of `PAID`

**Analysis:** W=1, R=1 gives no quorum-intersection guarantee; another replica can return the stale version.

**Test:** Never assume stronger guarantees than the contract provides. If local-DC read-your-writes is required, evaluate WCL/RCL `LOCAL_QUORUM` and business concurrency/version policies.

### Case H — Both Write and Read at `LOCAL_QUORUM` Succeed Without Error, Yet Status Is Wrong

**Cause:** Wrong partition key written, codec/binding swapped two strings, LWW timestamp from a concurrent writer won, or test read an older row.

**Decision:** FAIL G5 data oracle even though G4 CL availability PASSED. Inspect primary keys, revision/timestamp, source events, schema, and access patterns.

### Case I — Raised RF2 to RF3, Schema Agreement PASSES, Historical Records Still Missing

**Cause:** Schema replication updated, yet new replicas may not have received/repaired historical SSTables yet.

**Test:** Use **seeded historical keys** across multiple token ranges; run streaming/repair per runbook and check values/versions. Do not merely write a new row and read it immediately.

### Case J — Snapshot Restored, All Nodes `UN`, New Probe PASSES, Old Data Missing

**Analysis:** The new write/read path works, but the snapshot/import may miss SSTables, target the wrong keyspace/schema, or be incomplete.

**Decision:** STOP “restore complete”; reconcile manifests, checksums, time coverage, and token-range samples—never use `CREATE TABLE`/`system.local` as restore proof.

### Case K — `dc1` RF3 and `dc2` RF2, `dc2` Loses One Node

**Signal:** `LOCAL_QUORUM` from dc1 can PASS while dc2 FAILS. Cluster-wide `QUORUM` can PASS with ≥3/5 replicas; `EACH_QUORUM` writes need ≥2/3 in dc1 **and** ≥2/2 in dc2, so they FAIL.

**Lesson:** Readiness depends on **CL + DC + RF map**, not raw total UP node counts.

### Case L — Java Driver Has Wrong Local DC After Region Move

**Symptom:** Cassandra dc2 nodes are `UN`, yet the driver opens no usable connections or routes to dc1. `cqlsh` run inside dc2 may PASS while Java FAILS.

**Test:** Use the service's actual driver config, inspect `getMetadata().getNodes()` and coordinator/host errors, and verify `basic.load-balancing-policy.local-datacenter`. Fix routing before blaming data replicas.

### Case M — Tests Use Superuser, Production Role Lacks SELECT

**Symptom:** CI health probes PASS, yet the live service throws `UnauthorizedException`.

**Cause:** Tests bypassed the application's real credentials/RBAC.

**Decision:** Add integration probes using an equivalent least-privilege test role; never grant superuser to the app just to turn readiness green.

### Case N — JUnit Test Flakes Due to `Thread.sleep(10000)`

**Symptom:** Passes on laptop, fails on cold CI Docker, passes on CI retry.

**Cause:** Variable startup timing; fixed sleeps ignore actual readiness conditions.

**Test:** Replace with bounded polling against the right keyspace/CL/data oracle, per-attempt timeouts, and preserved last errors. With Testcontainers, leverage module wait strategies while still asserting business oracles.

### Case O — Repeated Tests Pass Falsely Using Leftover Probes from a Prior Run

**Symptom:** Today's write timed out, yet read saw `READY` and the suite PASSED.

**Cause:** Reused probe ID/value persisted from a previous run without checking revision/run ID.

**Test:** Use a unique revision/run ID per run, keeping the ID fixed **within retries of that run**, and prevent collisions across concurrent suites.

### Case P — LWT Uniqueness Test Uses SELECT Instead of CAS Result

**Symptom:** SELECT finds the row, and the team concludes the current request's `INSERT IF NOT EXISTS` applied.

**Cause:** The row could have been inserted by an earlier request or concurrent actor. LWT requires checking `[applied]` and normal/serial CL, especially when retrying after timeouts.

**Test:** Check the CAS result, row version, business operation ID, and re-read on ambiguous outcomes; never infer transaction success merely from row existence.

### Case Q — Health Check Uses `COUNT(*)`, Causing Recovering Nodes to Time Out

**Cause:** Full-table scans traverse many partitions/tombstones, spiking disk/CPU and p99 during recovery.

**Fix:** Known-key probes and manifest checksums/offline validation; reduce cadence and avoid full-table scans on health endpoints.

### Case R — Kubernetes Liveness Wired to `LOCAL_QUORUM` Triggers Cascading Pod Restarts

**Symptom:** One replica goes DOWN → quorum health fails → orchestrator restarts still-healthy nodes.

**Fix:** Liveness checks only the process; readiness/traffic gates depend on dependencies and CL without using cluster-wide availability to kill individual nodes.

### Case S — Retry Policy Lets Test PASS, Yet p99 Violates SLO

**Symptom:** Driver switches coordinator/retries after timeout; the request eventually succeeds but takes too long while a bad node remains.

**Test:** Assert elapsed time/SLO, measure retries, `cql-messages`, and server resources. HOLD even if the functional oracle PASSES.

### Case T — Node in `UJ`, Certain Token Ranges Still Streaming

**Symptom:** CQL accepts queries, yet probes on token A PASS while token B sees latency/errors.

**Analysis:** Bootstrap/streaming is unfinished or replica placement is still converging.

**Decision:** Never promote a new node solely from TCP/`UN` snapshots; monitor streaming/topology and run multi-token data probes. Never kill bootstrap/repair arbitrarily to “reduce load”.

## 25. Integration Acceptance Checklist

### 25.1. Environment and Topology

- [ ] Cassandra, driver, and Testcontainers versions are pinned and recorded.
- [ ] Explicitly documented whether Docker runs a real cluster or a single-node fixture.
- [ ] Contact points, advertised addresses, and port mappings are valid.
- [ ] Driver local DC matches the service's DC; auth/TLS/roles mirror production semantics.
- [ ] `nodetool status`/driver metadata are not mistaken for data readiness.
- [ ] Keyspace replication strategy and per-DC RF map have been read back.
- [ ] Full vs transient replicas are distinguished where transient replication is used.
- [ ] No unaccounted topology changes or active streaming are hidden in scope.
- [ ] Representative partitions/token ranges and expected replica sets are mapped.

### 25.2. Schema and Data

- [ ] DDL/migrations ran in order; schema agreement verified across **UP nodes**.
- [ ] `ExecutionInfo.isSchemaInAgreement` from a SELECT is not used as DDL agreement proof.
- [ ] Driver metadata is refreshed/re-read after schema changes.
- [ ] Tables/columns/UDTs/indexes align with CQL/Java codecs.
- [ ] Seeded historical data oracle exists for restore/migration/repair tests.
- [ ] Separate synthetic probe exists when verifying the write path.
- [ ] Record ID/revision/run ID are distinct so stale data cannot cause false passes.
- [ ] TTL/tombstones/cleanup policies are appropriate without infinite churn.
- [ ] No periodic global `COUNT(*)` on large tables for readiness.
- [ ] No PII/bind values logged or high-cardinality metric labels emitted.

### 25.3. Consistency Contract

- [ ] Both read CL **and** write CL are set explicitly on statements.
- [ ] For RF3: team knows local quorum requires 2 timely full-replica ACKs.
- [ ] For multi-DC: `QUORUM`/`LOCAL_QUORUM`/`EACH_QUORUM` are clearly distinguished.
- [ ] `ANY` writes are never used to claim read-after-write visibility.
- [ ] `SERIAL`/`LOCAL_SERIAL` are recognized as the LWT serial phase, distinct from normal CL.
- [ ] Tests assert expected key/value/revision/size, not just `row != null`.
- [ ] Multi-node CL tests run on a **real multi-node cluster**, not single-node proxies.
- [ ] Negative tests assert `UnavailableException` specifically, not “any exception”.
- [ ] Driver retries/speculation are tracked and bounded by deadlines/SLOs.
- [ ] Unknown write outcomes are reconciled rather than blindly retried with new IDs.

### 25.4. Stability and Operations

- [ ] Total budget, per-attempt timeout, and bounded polling/backoff are configured.
- [ ] Transient vs permanent errors are separated; `InvalidQuery`/`Unauthorized` are never swallowed.
- [ ] Metrics exist for read/write timeouts, unavailables, failures, retries, and p95/p99.
- [ ] Server disk/GC/compaction/streaming/repair health is observed.
- [ ] Readiness gates are not miswired to Kubernetes liveness causing restart loops.
- [ ] Canary GO/HOLD/STOP has guardrails and an owner, not a lone boolean.
- [ ] Rollback plans include checking data oracles and unknown outcomes.
- [ ] No destructive node/network/iptables fault injection is run in production.
- [ ] Step 4 authors documentation; build/test/academic QA runs in a separate specialized review.

## 26. Self-Assessment Questions and Suggested Answers

**Q1.** Does Docker reporting a container RUNNING prove Cassandra has opened port 9042?  
**Answer:** No; the JVM/native transport may still be initializing.

**Q2.** Does a connectable TCP port 9042 prove user tables can serve requests?  
**Answer:** No; auth, schema, replica quorum, and data remain unverified.

**Q3.** What does a successful `SELECT release_version FROM system.local` prove?  
**Answer:** At least one CQL coordinator can serve system tables; it does not prove user keyspaces.

**Q4.** What do the two characters `UN` in `nodetool status` mean?  
**Answer:** U=Up, N=Normal from the status view, not “all data synced”.

**Q5.** Does `UJ` mean a node has finished bootstrapping/streaming?  
**Answer:** No; U=Up, J=Joining.

**Q6.** When a node is `UN`, can we assert all `LOCAL_QUORUM` queries will succeed?  
**Answer:** No; enough natural replicas must ACK within deadlines for that partition/CL.

**Q7.** With RF3 in one DC, what is quorum?  
**Answer:** 2 full replica responses (assuming standard replication).

**Q8.** With RF4 in one DC, how many does `LOCAL_QUORUM` require?  
**Answer:** 3.

**Q9.** With RF3, 2 replicas UP and 1 DOWN, will `LOCAL_QUORUM` definitely PASS?  
**Answer:** It **can** satisfy live replica count, yet can still timeout/fail if the two nodes miss deadlines.

**Q10.** With RF3 and only 1 replica UP, can `LOCAL_QUORUM` succeed?  
**Answer:** No; typically the coordinator returns `UNAVAILABLE`.

**Q11.** How does `UNAVAILABLE` differ from `READ_TIMEOUT`?  
**Answer:** Insufficient known-live replicas vs attempted execution with too few timely responses.

**Q12.** Is `DriverTimeoutException` synonymous with Cassandra server `ReadTimeoutException`?  
**Answer:** No; the driver deadline can expire before the server returns any result or error.

**Q13.** In NTS dc1 RF3, dc2 RF2, how many ACKs does `LOCAL_QUORUM` from dc2 need?  
**Answer:** 2 in dc2.

**Q14.** With the same total RF5 cluster-wide, how many ACKs does `QUORUM` need?  
**Answer:** 3 full replicas total.

**Q15.** What does an `EACH_QUORUM` write require when dc1 is RF3 and dc2 is RF2?  
**Answer:** At least 2 in dc1 **and** 2 in dc2; 3 total across DCs is not enough.

**Q16.** Can you read at `ANY`?  
**Answer:** No; `ANY` is write-only and may succeed via hinted handoff.

**Q17.** Writing at `ONE` and reading at `QUORUM` with RF3—is overlap guaranteed?  
**Answer:** No; W+R = 1+2 = 3, which is not greater than RF3.

**Q18.** Do `QUORUM` writes and reads with RF3 create quorum intersection?  
**Answer:** Yes, within the same full replica set (2+2>3), assuming no out-of-model concurrent/timestamp conflicts.

**Q19.** Is quorum intersection alone enough to guarantee linearizability for every query?  
**Answer:** No; concurrent writes, timestamps/LWW, LWT, and DC semantics still matter.

**Q20.** Can a `SELECT` at `LOCAL_QUORUM` returning 0 rows PASS G5?  
**Answer:** Only if the oracle expects the row not to exist; if a seeded row is expected, it FAILS the data oracle.

**Q21.** Does `schema agreement = true` prove DOWN nodes also have the updated schema?  
**Answer:** No; the driver checks **currently UP** nodes.

**Q22.** After DDL, does `isSchemaInAgreement() == false` mean the DDL rolled back?  
**Answer:** No; some nodes may already have updated while convergence exceeded the timeout.

**Q23.** On a `SELECT`, is `ExecutionInfo.isSchemaInAgreement() == true` solid evidence?  
**Answer:** No; per Javadoc, that flag is always true for non-DDL queries.

**Q24.** Why must `session.getMetadata()` be called again after DDL?  
**Answer:** Metadata is an immutable snapshot (aside from certain node state fields); an old snapshot can be stale.

**Q25.** Which `CassandraContainer` package does Testcontainers 2.x use?  
**Answer:** `org.testcontainers.cassandra.CassandraContainer`; do not mix with the 1.x package.

**Q26.** Can a single-node Testcontainers Cassandra instance prove RF3 `LOCAL_QUORUM`?  
**Answer:** No; a real cluster with multiple full replicas in the same DC is required.

**Q27.** Why is RF2 on one node at CL `TWO` a valid negative test?  
**Answer:** Two physical replicas do not exist; tests should observe `UNAVAILABLE` even while the CQL port and local ring work.

**Q28.** Why shouldn't negative tests just use `assertThrows(Exception.class)`?  
**Answer:** Bad CQL/permissions/ports also throw exceptions; you must check specifically for `UnavailableException` or its nested cause.

**Q29.** What determines natural replicas?  
**Answer:** Partition key → token, keyspace replication strategy/RF, and ring/DC/rack topology.

**Q30.** Must the coordinator node be a natural replica of the partition?  
**Answer:** No; a coordinator can forward reads/writes to natural replicas.

**Q31.** Does a single probe key passing at target CL prove all tokens in the cluster?  
**Answer:** No; that covers one token/replica set at one point in time. Representative coverage is required.

**Q32.** Why do restore tests need seeded historical keys?  
**Answer:** New probes only prove the write/read path, not that pre-backup data was restored.

**Q33.** Why is schema agreement after increasing RF insufficient for data readiness?  
**Answer:** New historical replicas may lack data yet; repair/streaming and read oracles are required.

**Q34.** Why is full-table `COUNT(*)` usually unsuitable as a health probe?  
**Answer:** Cassandra may scan large amounts of partitions/SSTables, burning CPU/I/O and adding load during recovery.

**Q35.** If a probe has a 1-second TTL and fails after 5 seconds, is a replica necessarily broken?  
**Answer:** No; the data may simply have expired per its TTL.

**Q36.** Why do data probes need a revision/run ID?  
**Answer:** To prevent false passes from leftover rows of prior runs or cross-test races.

**Q37.** Is checking SELECT in `cqlsh` as superuser enough to prove the Java service role is ready?  
**Answer:** No; tests must use the same auth/role/driver/DC as the real application.

**Q38.** If `LOCAL_QUORUM` succeeds but p99 exceeds SLO, can readiness FAIL?  
**Answer:** Yes; availability and latency are distinct criteria.

**Q39.** Why shouldn't a `LOCAL_QUORUM` query be used as a Cassandra pod's `livenessProbe`?  
**Answer:** It can fail due to peer replicas and trigger cascading restarts while the local pod is healthy.

**Q40.** Can an app open HTTP port 8080 yet still not be ready to serve Cassandra data?  
**Answer:** Yes; dependency readiness gates for schema/CL/data are needed.

**Q41.** Why shouldn't `Thread.sleep(10000)` replace a wait-ready check?  
**Answer:** Startup timing varies; use conditional bounded polling with clear timeouts and causes.

**Q42.** When a write probe times out with no ACK, what should be recorded?  
**Answer:** `UNKNOWN_OUTCOME`; preserve the fixed ID and reconcile before retrying.

**Q43.** When `AllNodesFailedException` reaches Java, what should be inspected?  
**Answer:** `getAllErrors()` per coordinator/node and causes to distinguish unavailable/network/timeout.

**Q44.** Why can `UN` on all nodes still coincide with historical data mismatches?  
**Answer:** Healthy node/ring states do not confirm restore/repair or source-of-truth consistency.

**Q45.** Does a `LOCAL_QUORUM` canary passing after multiple retries mean the cluster is completely healthy?  
**Answer:** No; inspect retries, p99, server resources, and token coverage.

**Q46.** When dc1 PASSES `LOCAL_QUORUM`, can dc2 be declared PASS?  
**Answer:** No; each DC has its own RF and replica availability.

**Q47.** With LWT, does reading an existing row prove the current request's `INSERT IF NOT EXISTS` applied?  
**Answer:** No; inspect `[applied]`/version/operation ID and serial CL.

**Q48.** What should readiness tests roll back if wrong values appear post-deploy?  
**Answer:** Halt rollout, investigate data/migrations, and reconcile; rolling back code/config does not automatically revert Cassandra writes/schemas.

## 27. Summary: Tests Must Prove **the Right CL and the Right Data**

~~~text
PROCESS RUNNING?
       |
       v
TCP/CQL REACHABLE?
       |
       v
SCHEMA EXISTS + AGREED (among UP nodes)?
       |
       v
RF/DC/KEYSPACE/PARTITION MAPPING KNOWN?
       |
       v
EXPECTED CL AVAILABLE FOR NATURAL REPLICAS?
       |
       v
WRITE AT WCL + READ AT RCL (when required)?
       |
       v
EXPECTED BUSINESS VALUE/REVISION VISIBLE?
       |
       v
TIMEOUT/RETRY/LATENCY WITHIN SLO?
       |
       v
READY for explicit scope + time window
~~~

### 27.1. Five Mandatory Conditions for a “Ready” Verdict

1. **Clear scope:** cluster, DC, keyspace, table, query family, partition/token samples.
2. **Exact consistency contract:** RF and read/write CLs are genuinely enforced.
3. **Timely responses:** No `UNAVAILABLE`/timeouts breaching the gate.
4. **Correct data:** seeded/migration and synthetic probes have matching oracles, never accepting “empty result” when data is expected.
5. **Bounded stability:** deadlines/p95/p99/errors/retries, clear owner, and rollback path.

**Key takeaway:** `nodetool status UN` means the node is **Up/Normal**. It **does not say** 2/3 natural replicas for every partition ACKed in time, nor that historical data was repaired/restored properly. Trustworthy integration tests **must execute CQL at the business-required CL and verify real values**, rather than stopping at container health, port 9042, or schema agreement.

### 27.2. Separating Learning Content from Deep QA

This lesson provides reproducible labs on single-node Cassandra and guidance for multi-node expansion. Within the lesson-authoring workflow, **STEP 4 authors content** without running Gradle, fault-injecting live clusters, or treating unexecuted snippets as empirically verified integration tests. STEP 6/new or specialized engineering teams will evaluate correctness and executability on target versions/environments.

## References

- [Apache Cassandra — Dynamo architecture and consistency](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo) — natural replicas, RF, coordinators, CLs, quorums, and read/write semantics.
- [Apache Cassandra — Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html) — full repair/streaming, especially after RF increases.
- [Apache Cassandra — Monitoring metrics](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html) — request latency, errors, compaction, thread pools.
- [Apache Cassandra — Data modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html) — query-first design, partition keys, and token placement.
- [Apache Cassandra — cqlsh](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html) — `CONSISTENCY`, CQL, and diagnostics.
- [Apache Java Driver 4.18 — Node metadata](https://apache.github.io/cassandra-java-driver/4.18.0/core/metadata/node/) — known nodes, states, distance, open connections.
- [Apache Java Driver 4.18 — Schema metadata/agreement](https://apache.github.io/cassandra-java-driver/4.18.0/core/metadata/schema/) — schema propagation among UP nodes, DDL waiting, metadata refresh.
- [Apache Java Driver 4.18 — Metadata overview](https://apache.github.io/cassandra-java-driver/4.18.0/core/metadata/) — immutable snapshots, token/schema/node consistency.
- [Apache Java Driver 4.18 — Session API](https://apache.github.io/cassandra-java-driver/4.18.1/api/com/datastax/oss/driver/api/core/session/Session.html) — `checkSchemaAgreement`, metadata.
- [Apache Java Driver 4.18 — ExecutionInfo API](https://apache.github.io/cassandra-java-driver/4.18.1/api/com/datastax/oss/driver/api/core/cql/ExecutionInfo.html) — `isSchemaInAgreement` meaningful only after DDL.
- [Apache Java Driver 4.18 — Retry policies](https://apache.github.io/cassandra-java-driver/4.18.1/core/retries/) — `UNAVAILABLE`, timeouts, and retry decisions.
- [Apache Java Driver 4.18 — Configuration](https://apache.github.io/cassandra-java-driver/4.18.1/core/configuration/) — execution profiles, CL, and timeouts.
- [Testcontainers for Java — Cassandra module](https://java.testcontainers.org/modules/databases/cassandra/) — `CassandraContainer`, `getContactPoint`, `getLocalDatacenter`.
- [Testcontainers Java 2.0 release notes](https://github.com/testcontainers/testcontainers-java/releases) — artifact/module package relocation.
- [JUnit 5 User Guide](https://docs.junit.org/current/user-guide/) — lifecycle annotations, test assertions, and extension model.
- [DataStax nodetool status](https://docs.datastax.com/en/cassandra-oss/2.1/cassandra/tools/toolsStatus.html) — `UN`/`UJ`/`DN` states, keyspace ownership, and informational limits.
