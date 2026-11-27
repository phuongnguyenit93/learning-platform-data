# Multi-Session and Node-Loss Lab to Verify Read/Write Conditions

An important question when studying Apache Cassandra **read/write consistency** is: **If a replica stops running while two clients are reading and writing, which operations still succeed and what data can be observed?** You can learn `R + W > N` on paper, yet only when running across multiple client sessions, observing `Unavailable`/`Timeout` errors, and recovering nodes do the meanings of **ACK thresholds**, **read paths**, **replica scope**, and **indeterminate write outcomes** become crystal clear.

This lab belongs to the **Read/Write Consistency** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. It connects distributed architecture and the wide-column model with partition keys, query-driven table design, CQL, replication, error handling, hinted handoff, repair, compaction, and Java applications. The goal is not to break things recklessly, but to **form hypotheses, run controlled experiments, and distinguish what was observed from what is logically guaranteed**.

> **Safety boundary:** All node stops, network delays, or data deletions in this lesson are **strictly for an isolated lab cluster and synthetic data**. Never run `docker compose stop`, fault-injection networking, `TRUNCATE`, or service-disrupting tests on a production cluster.

## 1. Objectives and Deliverables

By the end of this lesson, you will be able to:

1. Open **two separate `cqlsh` sessions**, set CL independently, and confirm each session must choose its own CL.
2. Calculate thresholds for `ONE`, `TWO`, `QUORUM`, and `ALL` at RF=3 before stopping replicas.
3. Observe behavior when **three, two, or one replica** of a partition can respond.
4. Explain why `WriteTimeout`/`Unavailable` **does not mean** "the mutation was definitely not applied."
5. Verify a **prediction about overlapping ACK/response sets** when `R + W > N`, without mistaking an incidental fresh read for a general guarantee.
6. Demonstrate the difference between **request order** and **winning timestamp under last-write-wins**.
7. Contrast same-DC vs. cross-DC `LOCAL_QUORUM`, global `QUORUM`, and `EACH_QUORUM` writes in the multi-datacenter extension.
8. Write a Java Driver 4.x client setting CL per statement and classifying errors.
9. Produce a table recording results, root causes of discrepancies, recovery steps, and what the experiment **did not prove**.

**Expected deliverable:** a "prediction → observation → explanation" results table, topology diagram, log of CLs used, and an explanation of why response counting does not replace knowledge of timestamps, reconciliation, or LWT.

## 2. Theoretical Model Before Running

### 2.1. Replication Factor and Partitions

Cassandra distributes data by **partition key**. The replication strategy, RF, and token placement determine a partition's **target replicas**. The node receiving a request is the **coordinator**, which may or may not be a target replica.

In a single-datacenter lab with **three nodes and RF=3**, each partition has three full replicas. Call them `R1`, `R2`, and `R3`:

```text
                     Cqlsh A                 Cqlsh B
                        |                       |
                        v                       v
                 Coordinator R1          Coordinator R2
                         \                 /
                          \               /
                          +---------------+
                          |   Partition P |
                          +---------------+
                          /       |       \
                         v        v        v
                        R1       R2        R3

             Replica set of P: S={R1,R2,R3}, N=3.
```

The two client sessions have **different coordinators**, yet because they query the same partition, they still target **the same replica set `S`** under a stable topology. Running two sessions does not create two independent copies of data; the two sessions are simply two observers and drivers of operations.

### 2.2. Consistency Level Is a Response Threshold

In a single DC with RF=3:

| CL | Minimum Responses | Example When One Replica Is Down |
| --- | ---: | --- |
| `ONE` | 1 | Can be satisfied. |
| `TWO` | 2 | Can be satisfied if the remaining two replicas respond in time. |
| `THREE` | 3 | Cannot be satisfied. |
| `QUORUM` | `floor(3/2)+1=2` | Can be satisfied if the remaining two replicas respond in time. |
| `ALL` | 3 | Cannot be satisfied. |
| `LOCAL_ONE` | 1 local replica | In a single-DC lab, same replica scope as `ONE`. |
| `LOCAL_QUORUM` | 2 local replicas | In a single-DC lab, same threshold as `QUORUM`. |

`ANY` is a **write-only** CL. In supported scenarios, an `ANY` write can return success solely via coordinator **hint** storage with **zero target replica ACKs**. With a cluster of only three nodes and RF=3, if **all three replicas are down**, there is also no live coordinator left to test this case; never infer "`ANY` can always write even if the whole cluster is off."

### 2.3. Intersection Condition

Suppose a write **returned success** after `W` ACKs from the same set `S` of `N` replicas. A subsequent successful read receives at least `R` valid responses from the same set `S`. When:

\[
R + W > N
\]

the two replica sets **must intersect in at least one element**. Brief proof:

\[
|A \cap B| = |A|+|B|-|A\cup B|\ \ge\ R+W-N
\]

With RF=3:

| Write CL → Read CL | `W` | `R` | `W+R>N`? | Conclusion |
| --- | ---: | ---: | --- | --- |
| `ONE` → `ONE` | 1 | 1 | `2>3`: false | **No guaranteed** overlap. |
| `ONE` → `QUORUM` | 1 | 2 | `3>3`: false | **No guaranteed** overlap. |
| `QUORUM` → `ONE` | 2 | 1 | `3>3`: false | **No guaranteed** overlap. |
| `QUORUM` → `QUORUM` | 2 | 2 | `4>3`: true | **Guaranteed overlap**. |
| `ALL` → `ONE` | 3 | 1 | `4>3`: true | Guaranteed overlap, **if the `ALL` write actually succeeded**. |
| `ONE` → `ALL` | 1 | 3 | `4>3`: true | Guaranteed overlap, **if the `ALL` read actually succeeded**. |

**Key point:** `R+W>N` is a **sufficient** set-theoretic condition, not a necessary condition for every single run. When `R+W≤N`, the two sets **may** be disjoint, yet if the client happens to query the replica that just wrote, it will still read the new data.

The intersection condition also **does not guarantee linearizability** for concurrent updates; timestamps, deletes/tombstones, TTL, and execution ordering still govern the returned logical value.

## 3. Building a Three-Node, Single-DC Lab Cluster

You can use an existing Cassandra 4.x/5.x cluster with three nodes in the same DC. To make this lab self-contained, here is an **illustrative Docker Compose** configuration for Cassandra 4.1. It requires Docker with enough CPU/RAM for three JVMs; never run it alongside a production cluster.

Create `compose.yaml` in **a separate temporary lab directory** (not this lesson's directory):

```yaml
services:
  cass1:
    image: cassandra:4.1
    environment:
      CASSANDRA_CLUSTER_NAME: rw-consistency-lab
      CASSANDRA_DC: dc1
      CASSANDRA_RACK: rack1
      CASSANDRA_ENDPOINT_SNITCH: GossipingPropertyFileSnitch
      CASSANDRA_SEEDS: cass1
    ports:
      - "9042:9042"

  cass2:
    image: cassandra:4.1
    environment:
      CASSANDRA_CLUSTER_NAME: rw-consistency-lab
      CASSANDRA_DC: dc1
      CASSANDRA_RACK: rack2
      CASSANDRA_ENDPOINT_SNITCH: GossipingPropertyFileSnitch
      CASSANDRA_SEEDS: cass1
    depends_on:
      - cass1

  cass3:
    image: cassandra:4.1
    environment:
      CASSANDRA_CLUSTER_NAME: rw-consistency-lab
      CASSANDRA_DC: dc1
      CASSANDRA_RACK: rack3
      CASSANDRA_ENDPOINT_SNITCH: GossipingPropertyFileSnitch
      CASSANDRA_SEEDS: cass1
    depends_on:
      - cass1
```

Start the seed node first; allow the remaining nodes to join only after the seed is ready:

```bash
# Control terminal, in the directory containing compose.yaml
docker compose up -d cass1

# Confirm cass1 has booted enough for nodetool to work.
docker compose exec cass1 nodetool status

# Then add the remaining two nodes.
docker compose up -d cass2 cass3

# Check the ring from a live node.
docker compose exec cass1 nodetool status
```

Wait for `nodetool status` to display **three `UN` (Up/Normal) nodes** in the same `dc1`, and verify schema agreement before attempting writes. `depends_on` only orders container startup; it does **not** guarantee Cassandra inside is ready for CQL. If your image, memory, or network environment differs, adjust startup accordingly. **Never sleep a fixed duration** and assume nodes are UP.

### Checks to Confirm Before Testing

| Check Item | Expected State |
| --- | --- |
| Cluster name | `rw-consistency-lab`, not a real cluster. |
| Datacenter | Single DC `dc1`. |
| Nodes | `cass1`, `cass2`, `cass3` all in `UN` state. |
| CQL | `cqlsh` connects to each node. |
| Data | Synthetic IDs in the lab namespace only. |
| Permissions | Permitted to stop/start lab containers with zero impact on real users. |

**Reliability note:** This is a minimal lab configuration, not a production deployment template. It omits authentication, TLS, persistent volumes, healthchecks, and monitoring. On managed Cassandra services, replace Docker steps with the fault-injection mechanism permitted in your test environment.

## 4. Preparing Tables and Two Independent `cqlsh` Sessions

### 4.1. Open Three Terminals

Open three terminal windows **on the same lab host**:

**Terminal A — primary write client session, coordinator `cass1`:**

```bash
docker compose exec cass1 cqlsh
```

**Terminal B — concurrent read/write client session, coordinator `cass2`:**

```bash
docker compose exec cass2 cqlsh
```

**Terminal C — fault control and ring observation:**

```bash
docker compose exec cass1 nodetool status
```

Keep both `cqlsh` sessions A/B open during the experiment; each session stores **its own consistency setting**. When you stop a node hosting a `cqlsh` session, that session will disconnect; reopen it on a remaining live node.

### 4.2. Create an RF=3 Keyspace and Partition-Keyed Tables

In **Terminal A**, run:

```sql
CREATE KEYSPACE IF NOT EXISTS session_failure_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS session_failure_lab.order_state_by_id (
  order_id uuid PRIMARY KEY,
  state text,
  operation_id uuid,
  updated_at timestamp
);

CREATE TABLE IF NOT EXISTS session_failure_lab.seat_by_key (
  seat_key text PRIMARY KEY,
  owner_id uuid,
  operation_id uuid
);
```

`order_id` and `seat_key` are the **partition keys**. Using `WHERE order_id = ?` on the read path directs both sessions to the exact same partition replica set. Do not substitute full-table scans or two separate denormalized tables and apply the intersection proof.

In **Terminal B**, verify the schema is visible:

```sql
DESCRIBE KEYSPACE session_failure_lab;
```

Proceed only once nodes agree on schema. In a **three-node RF=3** lab, every node in the DC is a replica for every partition; in clusters with more nodes than RF, you must verify **the exact partition's replica placement**, rather than treating any arbitrary down node as a "lost replica."

### 4.3. Record Each Session's Separate CL

In A:

```sql
CONSISTENCY QUORUM;
CONSISTENCY;
```

In B:

```sql
CONSISTENCY ONE;
CONSISTENCY;
```

`CONSISTENCY` is a **`cqlsh` command**, not a clause attached to `SELECT` or `UPDATE`. A using `QUORUM` does not alter B's CL. After every step, record the **actual CL in both sessions**, rather than assuming from another session's earlier setting.

## 5. Experiment 1 — Healthy Cluster, Two Sessions Reading and Writing

**Hypothesis:** With RF=3 and all three replicas healthy, a `QUORUM` write (W=2) and `QUORUM` read (R=2) overlap; a `ONE` read has no overlap guarantee yet still commonly sees the new value when replication runs normally.

### Step 1 — A Writes Initial State

In A:

```sql
CONSISTENCY QUORUM;

INSERT INTO session_failure_lab.order_state_by_id
  (order_id, state, operation_id, updated_at)
VALUES (
  11111111-1111-4111-8111-111111111111,
  'CREATED',
  22222222-2222-4222-8222-222222222222,
  '2026-11-21 08:00:00+0000'
);
```

This is a mutation on an RF=3 partition; if `INSERT` returns success, the write received enough ACKs for `QUORUM`. Do not infer from that alone that every replica already holds the data simultaneously.

### Step 2 — B Reads at ONE

In B:

```sql
CONSISTENCY ONE;

SELECT order_id, state, operation_id
FROM session_failure_lab.order_state_by_id
WHERE order_id = 11111111-1111-4111-8111-111111111111;
```

**Expected observation:** usually returns `CREATED`. This **does not prove `ONE` guarantees read-after-write**: in a healthy cluster, mutations typically reach all replicas very quickly, so even a weak level can see the fresh copy.

### Step 3 — A Updates; B Reads at QUORUM

In A:

```sql
CONSISTENCY QUORUM;

UPDATE session_failure_lab.order_state_by_id
SET state = 'PAID',
    operation_id = 33333333-3333-4333-8333-333333333333,
    updated_at = '2026-11-21 08:05:00+0000'
WHERE order_id = 11111111-1111-4111-8111-111111111111;
```

After A receives success, in B:

```sql
CONSISTENCY QUORUM;

SELECT state, operation_id, WRITETIME(state)
FROM session_failure_lab.order_state_by_id
WHERE order_id = 11111111-1111-4111-8111-111111111111;
```

**Expected observation:** `PAID` and the new operation ID. `WRITETIME(state)` displays the timestamp of the **winning cell**, not the entire mutation history or proof every replica flushed SSTables.

### Step 4 — Compare Against Theory

Write `A`'s ACK set has at least 2 of 3 replicas; read `B`'s response set has at least 2 of 3. Since `2+2>3`, the two sets overlap. Absent competing timestamp-winning updates and assuming the read path completes, this is why a quorum pair lets you expect **reading the newly written mutation**.

**Do not infer:** this does not prove Cassandra is linearizable for all competing writes, nor that `ONE` reads share the same guarantee. Step 2 merely showed an observation on data that had already propagated in time.

## 6. Experiment 2 — Stop One Replica and Test Each CL

**Hypothesis:** When `cass3` is down while `cass1` and `cass2` stay alive, with RF=3:

- `ONE`, `TWO`, and `QUORUM` **can** complete because 2 replicas still respond.
- `THREE` or `ALL` **lack** enough responses.
- A failure at `ALL` can be `Unavailable` or a timeout depending on when liveness updates.

### Step 1 — Stop the Target Replica in the Lab

In **Terminal C** (the lab host shell, not inside `cqlsh`):

```bash
docker compose stop cass3

docker compose exec cass1 nodetool status
```

Wait for failure detection to reflect `cass3` is no longer serving, typically `DN` (*Down/Normal*) while the node remains in the ring. **Do not assume a node is marked DOWN the instant the container stops.** While the node is still temporarily seen as UP, operations may time out before the failure detector updates.

### Step 2 — A Writes at QUORUM

In A:

```sql
CONSISTENCY QUORUM;

UPDATE session_failure_lab.order_state_by_id
SET state = 'PACKED',
    operation_id = 44444444-4444-4444-8444-444444444444,
    updated_at = '2026-11-21 08:10:00+0000'
WHERE order_id = 11111111-1111-4111-8111-111111111111;
```

If both `cass1` and `cass2` ACK in time, the write **can succeed** at quorum even though `cass3` is down. Cassandra does not need all replicas to ACK for `QUORUM`.

### Step 3 — B Reads at QUORUM

In B:

```sql
CONSISTENCY QUORUM;

SELECT state, operation_id
FROM session_failure_lab.order_state_by_id
WHERE order_id = 11111111-1111-4111-8111-111111111111;
```

In this topology, the two healthy replicas are `cass1` and `cass2`, so the `QUORUM` read can collect enough responses. The expected result is `PACKED`. This step shows **one down replica does not necessarily halt a `QUORUM`/`QUORUM` pair at RF=3**.

### Step 4 — Test ALL

In A:

```sql
CONSISTENCY ALL;

SELECT state
FROM session_failure_lab.order_state_by_id
WHERE order_id = 11111111-1111-4111-8111-111111111111;
```

`ALL` requires 3/3 replicas. While `cass3` is down, the operation **cannot meet the threshold**, so it will not return a successful `ALL` read result. Depending on when the down node was detected, the client may see `Unavailable` or `ReadTimeout`; **record the exact error type**, rather than normalizing every failure into one label.

If you want to test the `ALL` write path, use **a fresh lab partition** (do not overwrite data used as an observation baseline), because some replicas may apply the mutation even when the write fails its CL:

```sql
CONSISTENCY ALL;

INSERT INTO session_failure_lab.order_state_by_id
  (order_id, state, operation_id, updated_at)
VALUES (
  55555555-5555-4555-8555-555555555555,
  'ALL_TEST',
  66666666-6666-4666-8666-666666666666,
  '2026-11-21 08:15:00+0000'
);
```

**Prediction:** you cannot receive an `ALL` write confirmation while one target replica is DOWN; however, **never conclude zero replicas received the mutation** if the request failed mid-processing.

### Why Not Lower RF from 3 to 2 to "Rescue" the Experiment?

Changing RF alters **the replica set and quorum threshold**, invalidating comparisons with prior steps. This lesson measures behavior under **node failures on the same topology**, not a reconfiguration exercise. Keep the keyspace at RF=3 throughout every step.

## 7. Experiment 3 — Only One Replica of the Partition Remains

**Hypothesis:** With RF=3 and only `cass1` running, `ONE` can complete; `QUORUM` and `ALL` lack enough live replicas.

### Step 1 — Stop cass2 as Well

In Terminal C:

```bash
docker compose stop cass2
docker compose exec cass1 nodetool status
```

Session B attached to `cass2` will lose its connection; that is **not proof data vanished**. Use only Session A on `cass1` during this phase and note when `cass2` is marked DOWN.

### Step 2 — Read/Write at ONE

In A:

```sql
CONSISTENCY ONE;

UPDATE session_failure_lab.order_state_by_id
SET state = 'SHIPPED',
    operation_id = 77777777-7777-4777-8777-777777777777,
    updated_at = '2026-11-21 08:20:00+0000'
WHERE order_id = 11111111-1111-4111-8111-111111111111;

SELECT state, operation_id
FROM session_failure_lab.order_state_by_id
WHERE order_id = 11111111-1111-4111-8111-111111111111;
```

If `cass1` is healthy and the coordinator handles the request, `ONE` can succeed. With only one available replica, the next read also fetches its value from `cass1`.

**Important subtlety:** even though `R=1, W=1, N=3` means **`R+W≤N`**, in **this specific run where only `cass1` is alive**, both ACK and response sets may be `{cass1}` and therefore still overlap. `R+W>N` is a **sufficient condition guaranteeing overlap across all valid response sets**, not a necessary condition for overlap in a given run.

### Step 3 — Verify QUORUM Is No Longer Available

In A:

```sql
CONSISTENCY QUORUM;

SELECT state
FROM session_failure_lab.order_state_by_id
WHERE order_id = 11111111-1111-4111-8111-111111111111;
```

With RF=3, quorum requires 2 replicas. `cass1` is the sole running replica, so `QUORUM` **cannot be confirmed**. The actual error is typically `Unavailable` once the failure detector updates; timeouts can still occur if liveness has not yet reflected the outage or another replica is stalling.

**Never retry infinitely or auto-downgrade CL in production** just because the lab showed `ONE` still works. Dropping from `QUORUM` to `ONE` changes the ACK contract; the business must decide explicitly whether to accept that.

## 8. Experiment 4 — Recover Replicas and Reconcile Freshness

**Hypothesis:** After both nodes return, Cassandra can catch them up via normal writes, hinted handoff, and repair, yet **there is no fixed deadline guaranteeing instantaneous uniformity**.

### Step 1 — Restart the Stopped Nodes

In Terminal C:

```bash
docker compose start cass2 cass3
docker compose exec cass1 nodetool status
```

Wait until `cass1`, `cass2`, and `cass3` all return to `UN`. A node being UP means it can participate in the ring, **not direct proof every missed mutation was fully delivered**.

### Step 2 — Reopen Session B

In Terminal B:

```bash
docker compose exec cass2 cqlsh
```

In B's `cqlsh`:

```sql
CONSISTENCY ONE;

SELECT state, operation_id
FROM session_failure_lab.order_state_by_id
WHERE order_id = 11111111-1111-4111-8111-111111111111;
```

**Possible outcomes:** `SHIPPED` if the replica already caught up or the read coordinator selected the up-to-date replica; a stale observation is also possible before convergence, depending on read path/replication and timing. Seeing `SHIPPED` from a `ONE` read **cannot prove all three replicas match**.

### Step 3 — Read at QUORUM and Observe Reconciliation

In A or B:

```sql
CONSISTENCY QUORUM;

SELECT state, operation_id, WRITETIME(state)
FROM session_failure_lab.order_state_by_id
WHERE order_id = 11111111-1111-4111-8111-111111111111;
```

When replicas hold differing versions, the coordinator can compare **data/digests**, fetch additional full data, and **reconcile** by timestamp/tombstone. Depending on version and configuration, the read path may also trigger **read repair** for replicas found out of sync.

**Do not conflate three concepts:**

- **Hinted handoff:** retains and replays mutations missed by a replica, within config limits and as **best effort**.
- **Read reconciliation/read repair:** resolves discrepancies discovered on the read path, typically within the queried data scope.
- **Anti-entropy repair:** compares replica data across a broader range, used in scheduled/post-incident operations when needed.

**Compaction** manages SSTables and tombstones and **does not replace anti-entropy repair**. If a node was down long, hints expired, or deletes involve tombstones, review your repair strategy and version-specific `gc_grace_seconds` settings.

### Step 4 — Do Not Mistake Readability for Prior Failed Writes Succeeding

In Experiment 2, an `ALL` write failed to receive a success confirmation. After nodes return, reading that write's value (if present) only shows the mutation **existed/propagated to some replicas**; it **does not retroactively turn the previously failed `ALL` response into an ACKed success**.

## 9. Experiment 5 — Concurrent Writes from Two Sessions and Timestamp Rules

**Goal:** Prove quorum intersection does not mean "the request sent later always wins" or "two clients cannot update the same cell concurrently."

### 9.1. Two Sequential Writes with Inverted Timestamps

Use **a new partition** to avoid interference from earlier steps' timestamps. In A:

```sql
CONSISTENCY QUORUM;

INSERT INTO session_failure_lab.order_state_by_id
  (order_id, state, operation_id, updated_at)
VALUES (
  88888888-8888-4888-8888-888888888888,
  'VALUE_A',
  99999999-9999-4999-8999-999999999999,
  '2026-11-21 09:00:00+0000'
) USING TIMESTAMP 2000000;
```

Only after A receives success, in B:

```sql
CONSISTENCY QUORUM;

UPDATE session_failure_lab.order_state_by_id
USING TIMESTAMP 1000000
SET state = 'VALUE_B'
WHERE order_id = 88888888-8888-4888-8888-888888888888;

SELECT state, WRITETIME(state)
FROM session_failure_lab.order_state_by_id
WHERE order_id = 88888888-8888-4888-8888-888888888888;
```

**Expected result:** `state='VALUE_A'` with `WRITETIME(state)=2000000`. Both requests can satisfy `QUORUM`, yet Cassandra reconciles **cells by timestamp**, so `VALUE_B@1000000` cannot beat `VALUE_A@2000000`, even though B was sent later in wall-clock time.

**Note:** `USING TIMESTAMP` takes **microseconds**, and these small values are solely for a brand-new partition in a lab. Never copy manual timestamps like these into production data; choosing abnormal timestamps can prevent legitimate later updates from winning as expected.

### 9.2. Testing the Check-Then-Write Race

Suppose sessions A and B both read `FREE` at `QUORUM` and then both run normal `UPDATE`s. Both mutations can still receive success ACKs because **`SELECT` and `UPDATE` are two separate commands**, not an atomic compare-and-write.

To truly protect a unique seat, use LWT on the same `seat_key` partition:

In A:

```sql
CONSISTENCY QUORUM;

INSERT INTO session_failure_lab.seat_by_key
  (seat_key, owner_id, operation_id)
VALUES (
  'show-42:A07',
  11111111-1111-4111-8111-111111111111,
  22222222-2222-4222-8222-222222222222
) IF NOT EXISTS;
```

In B, try the same `seat_key` with another customer:

```sql
CONSISTENCY QUORUM;

INSERT INTO session_failure_lab.seat_by_key
  (seat_key, owner_id, operation_id)
VALUES (
  'show-42:A07',
  33333333-3333-4333-8333-333333333333,
  44444444-4444-4444-8444-444444444444
) IF NOT EXISTS;
```

**Prediction:** with both requests processed successfully within the same Paxos scope, one row creation yields `[applied]=true`; the other yields `[applied]=false` because the key already exists. Under true simultaneous contention, retries or errors may occur, so do not assume both responses always arrive at the exact same instant.

LWT uses **Paxos**. `SERIAL`/`LOCAL_SERIAL` define the consensus scope, a separate axis from normal CLs like `QUORUM`/`LOCAL_QUORUM`. Never use plain `QUORUM` and claim it provides compare-and-set.

## 10. Enabling Tracing and Reading Evidence Across Sessions

When you need to inspect how the coordinator dispatches requests/receives responses in a **lab**, `cqlsh` supports tracing:

```sql
TRACING ON;

CONSISTENCY QUORUM;

SELECT state
FROM session_failure_lab.order_state_by_id
WHERE order_id = 11111111-1111-4111-8111-111111111111;

TRACING OFF;
```

Traces can show the coordinator, contacted replicas, latencies, and internal stages. Trace details depend on version, read optimizations, digests, speculative retry, and cluster state:

- **Do not** assume a `QUORUM` request always sends exactly two messages.
- Do not infer from a digest response that the client downloaded the entire row from that replica.
- Never use a **single** read's trace to claim "`ONE` always reads node R3."
- Do not enable tracing broadly in production, as it adds overhead and generates trace rows.

### Result Recording Sheet Template

| Trial | Coordinator/Session | Nodes UP | Write CL | Read CL | Prediction | Actual Result/Error Type |
| --- | --- | --- | --- | --- | --- | --- |
| T1 | A writes, B reads | 3/3 | `QUORUM` | `QUORUM` | Same RF=3, overlap holds. | *Fill after running* |
| T2 | A writes, B reads | 2/3 | `QUORUM` | `QUORUM` | Can succeed. | *Fill after running* |
| T3 | A reads | 2/3 | — | `ALL` | Insufficient responses. | *Fill after running* |
| T4 | A writes/reads | 1/3 | `ONE` | `ONE` | Can succeed on remaining healthy replica. | *Fill after running* |
| T5 | A reads | 1/3 | — | `QUORUM` | Insufficient responses. | *Fill after running* |
| T6 | B after recovery | 3/3 | — | `ONE` | May be fresh/stale depending on convergence and replica choice. | *Fill after running* |
| T7 | A writes, B writes/reads | 3/3 | `QUORUM` | `QUORUM` | Higher timestamp wins in cell. | *Fill after running* |
| T8 | A/B LWT | 3/3 | `QUORUM` + serial | — | One creates key with `[applied]=true`. | *Fill after running* |

To draw conclusions, cross-reference **three facts**: *requested response level*, *remaining responsive replicas*, and *request path/timestamps*. A single run is **observational evidence**, not a replacement for proving properties across all execution histories.

## 11. Why Can Losing Nodes Cause Unavailable or Timeout?

When a coordinator receives a request, it relies on liveness/failure detection to judge how many replicas can serve the CL. Two distinct cases occur:

1. **`UnavailableException`:** the coordinator determines **too few replicas are considered alive** to satisfy the CL. E.g., RF=3, `ALL` when `cass3` is already marked DOWN.
2. **`ReadTimeoutException` / `WriteTimeoutException`:** the coordinator already sent requests or still considers replicas UP, yet **failed to gather enough responses or finish the data path before deadline**.

Other errors include:

| Error | Practical Meaning to Record |
| --- | --- |
| `UnavailableException` | Insufficient replicas for CL, from coordinator's perspective. |
| `ReadTimeoutException` | Failed to finish read response/data conditions on time. |
| `WriteTimeoutException` | Write not confirmed to CL before deadline; **mutation may have applied on some replicas**. |
| `ReadFailureException` / `WriteFailureException` | Replicas reported processing errors; other replicas may still have processed it. |
| `DriverTimeoutException` | Driver wait expired; server may have finished while response failed to reach client. |
| Lost connection to coordinator | May be network/host error; does not prove all replicas are dead. |

**Especially for writes:** missing a success ACK **does not prove the mutation was not written**. Retries must consider primary keys, timestamps, idempotency, counters, TTLs, LWTs, and external side effects. Never silently downgrade `QUORUM` to `ONE` and describe the response as a quorum-confirmed write.

## 12. Extension: Two Datacenters and LOCAL Scopes

The three-node Docker lab above verifies **single-DC thresholds**; it is insufficient to conclude behavior for cross-DC `LOCAL_QUORUM` or `EACH_QUORUM`. If you have a **separate six-node lab** spanning `dc1` and `dc2`, you can perform the following calculations and tests.

### 12.1. RF=3+3

```text
dc1: A1 A2 A3  (RF=3)
dc2: B1 B2 B3  (RF=3)

Total RF = 6
QUORUM            = floor(6/2)+1 = 4
LOCAL_QUORUM      = 2 in coordinator's DC
EACH_QUORUM write = 2 ACKs dc1 AND 2 ACKs dc2
```

| Write | Read | Overlap Prediction |
| --- | --- | --- |
| Cluster-wide `QUORUM` (4) | Cluster-wide `QUORUM` (4) | **Yes:** `4+4>6`, within the same replica set. |
| `LOCAL_QUORUM` dc1 (2/3) | `LOCAL_QUORUM` dc1 (2/3) | **Yes:** `2+2>3` within dc1. |
| `LOCAL_QUORUM` dc1 (2/3) | `LOCAL_QUORUM` dc2 (2/3) | **Not guaranteed:** two sets in different DCs. |
| `EACH_QUORUM` write (2 per DC) | `LOCAL_QUORUM` dc2 (2/3) | **Yes:** dc2 has both write quorum ACKs and read quorum responses. |
| Cluster-wide `QUORUM` (4) | `LOCAL_QUORUM` dc1 (2/3) | **Not guaranteed:** write could hit A1+B1+B2+B3, read hits A2+A3. |

**Suggested experiment:** open one `cqlsh` session on a `dc1` node and one on a `dc2` node, setting `CONSISTENCY LOCAL_QUORUM;` in each. Write from dc1 and read immediately from dc2. **Observing stale data is not guaranteed**: WAN replication in a lab can be very fast. Reading fresh data only shows **that run** received the mutation, not that local quorums in different DCs are forced to overlap.

### 12.2. Stopping an Entire Remote DC in a Separate Lab

If the coordinator is in dc1 and all of dc2 is unreachable:

- `LOCAL_ONE`/`LOCAL_QUORUM` in dc1: can succeed while enough local replicas exist.
- `QUORUM` at RF=3+3: needs 4/6, dc1 has at most 3 so it fails.
- `EACH_QUORUM` write: lacks quorum in dc2, fails.
- `ALL`: fails.

**Do not apply mechanically to skewed RFs.** If `dc1 RF=5` and `dc2 RF=1`, global `QUORUM` of six replicas needs 4 and **can be satisfied solely in dc1** while dc1 is healthy. An `EACH_QUORUM` write still requires one ACK in dc2.

### 12.3. Prerequisites Before Expanding the Lab

Verify accurately:

- The keyspace uses `NetworkTopologyStrategy` with declared per-DC RFs.
- Both sessions' coordinators genuinely reside in the intended DCs (do not guess from terminal location).
- Both queries use **the same partition key** and the same replica set defined by topology.
- During testing, no bootstrap/decommission, RF changes, token moves, or topology changes are occurring.
- Faults are injected only in an authorized lab with recovery plans and synthetic data.

## 13. Java Driver 4.x: Reproducing the Experiments from an Application

`cqlsh` helps inspect individual commands, while Java Driver 4.x typically uses `PreparedStatement` and `BoundStatement`. The example below assumes a `CqlSession` properly connected to the lab cluster with `local datacenter=dc1`. In multi-node Docker setups, an application running outside the container network also needs **contact points/routing reachable at the addresses Cassandra advertises**; mapping only one container's `9042` port does not guarantee host Java access to every node.

### 13.1. Minimal Repository Setting CL per Statement

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.DriverTimeoutException;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.servererrors.ReadTimeoutException;
import com.datastax.oss.driver.api.core.servererrors.UnavailableException;
import com.datastax.oss.driver.api.core.servererrors.WriteTimeoutException;

import java.time.Instant;
import java.util.UUID;

public final class ConsistencyLabRepository {
    private final CqlSession session;
    private final PreparedStatement write;
    private final PreparedStatement read;

    public ConsistencyLabRepository(CqlSession session) {
        this.session = session;
        this.write = session.prepare(
            "UPDATE session_failure_lab.order_state_by_id " +
            "SET state = ?, operation_id = ?, updated_at = ? WHERE order_id = ?");
        this.read = session.prepare(
            "SELECT state FROM session_failure_lab.order_state_by_id " +
            "WHERE order_id = ?");
    }

    public void writeQuorum(
            UUID orderId, String state, UUID operationId, Instant at) {
        BoundStatement statement = write
            .bind(state, operationId, at, orderId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

        try {
            session.execute(statement);
        } catch (UnavailableException e) {
            // Insufficient replicas considered alive for CL at coordinator.
            throw e;
        } catch (WriteTimeoutException | DriverTimeoutException e) {
            // Some replicas may have applied the mutation or ACK was lost.
            // Business layer must reconcile with operationId.
            throw e;
        }
    }

    public String readQuorum(UUID orderId) {
        BoundStatement statement = read.bind(orderId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

        try {
            Row row = session.execute(statement).one();
            return row == null ? null : row.getString("state");
        } catch (UnavailableException | ReadTimeoutException e) {
            // Read error is not proof that "order does not exist."
            throw e;
        }
    }

    public String readOne(UUID orderId) {
        BoundStatement statement = read.bind(orderId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_ONE);

        Row row = session.execute(statement).one();
        return row == null ? null : row.getString("state");
    }
}
```

In a **single-DC RF=3** lab, `LOCAL_QUORUM` shares the 2-replica threshold with `QUORUM`, and `LOCAL_ONE` has threshold 1 like `ONE`. When expanding to multiple DCs, `LOCAL_*` choices must be evaluated relative to the **coordinator's DC**.

### 13.2. Never Run Two Competing Writes and Infer Completion Order

If two threads concurrently update the same cell with ordinary `UPDATE`s, Cassandra may ACK both at quorum and reconcile by **timestamp**. To enforce an invariant like **"only one client may create the seat,"** use LWT and check `[applied]`:

```java
PreparedStatement reserve = session.prepare(
    "INSERT INTO session_failure_lab.seat_by_key " +
    "(seat_key, owner_id, operation_id) VALUES (?, ?, ?) IF NOT EXISTS");

BoundStatement request = reserve.bind(seatKey, ownerId, operationId)
    .setConsistencyLevel(DefaultConsistencyLevel.QUORUM)
    .setSerialConsistencyLevel(DefaultConsistencyLevel.SERIAL);

boolean applied = session.execute(request).wasApplied();
```

`SERIAL`/`LOCAL_SERIAL` control the **Paxos phase**, distinct from normal CL. If an LWT times out, a retry may return `[applied]=false` because the initial attempt already created the row; inspect the **operation ID** before assuming someone else won.

### 13.3. Evaluate Retries for Each Data Type

| Mutation Type | Behavior on Timeout |
| --- | --- |
| `UPDATE` fixed value, stable key and timestamp | Can be designed idempotently, though watch for competing writes. |
| `INSERT` preserving primary key and event ID | Prevents creating multiple rows for the same event. |
| Counter increment | **Not idempotent**: retries can increment twice. |
| Collection append, TTL | Not safe to retry by default; evaluate concrete semantics. |
| Conditional LWT | Distinguish `[applied]=false` from **indeterminate** timeouts. |
| Mutation coupled with email/external event publish | Needs workflow/outbox/deduplication, not just database retries. |

Never auto-downgrade `QUORUM` to `ONE` on error to get a success response when the business still requires the original ACK count. `setIdempotent(true)` in the driver is **merely a hint** for retry policies; it does not make a mutation idempotent by itself.

## 14. Analyzing Results: What Was Proven, What Was Not?

After the lab, separate conclusions into three groups.

### 14.1. Directly Verifiable

- Live / considered-alive replica counts in `nodetool status`.
- `CONSISTENCY` is set **independently** per `cqlsh` session.
- `QUORUM` operations with 2/3 replicas left **can** succeed, while `ALL` lacks threshold.
- With only 1/3 replica left, `ONE` can succeed while `QUORUM` lacks threshold.
- A write with a lower timestamp may lose to a higher-timestamp value even when sent later.
- A successful `IF NOT EXISTS` LWT returns conditional status via `[applied]`, unlike normal writes.

### 14.2. Cannot Be Proven from a Single Observation

- "`ONE` reads are always stale" or "`ONE` reads are always fresh" — queried replicas and replication timing vary.
- "`QUORUM` reads always return the latest write in wall-clock time" — timestamps and concurrent writes still affect outcomes.
- "A write hitting `WriteTimeout` definitely reached zero replicas" — ACKs may arrive late or be lost.
- "Nodes are UP so all mutations are synchronized" — hinted handoff/repair may still be running.
- "One `QUORUM` read means every replica was repaired" — read repair scope depends on version/config/query.
- "In a single-DC lab `LOCAL_QUORUM` matched `QUORUM`, so it behaves identically across two DCs" — false because scopes differ.

### 14.3. A Conclusion Must State All Assumptions

Example of a solid answer:

> With RF=3 **in one DC**, stable topology, a `QUORUM` write **confirmed successful**, a `QUORUM` read starting **after** the write, the same partition, and no competing timestamp-winning mutation, `R+W=2+2>3` forces the write-ACK and read-response sets to intersect. Cassandra read-path reconciliation provides the basis to read the newly written version. This does **not** prove all concurrent updates are linearizable.

This is a technically defensible statement, far stronger than simply saying "quorum is always fresh."

## 15. Traps That Lead Experiments to Wrong Conclusions

1. **Having only two nodes yet configuring RF=3**, then expecting healthy three-replica behavior. Always check `UN` and real replica counts.
2. **Accidentally stopping the coordinator hosting `cqlsh`**, then blaming `QUORUM` for the disconnect. Those belong to different layers.
3. **Using a non-replica node** in a cluster with more nodes than RF. Always verify placement.
4. **Failing to track each session's CL separately.** `CONSISTENCY QUORUM` in A does not change B's CL.
5. **Changing RF mid-experiment while testing node failures.** `N` is no longer constant.
6. **Seeing a fresh `ONE` read and assuming sufficient guarantees.** That is just one observation; `R+W≤N` still allows disjoint sets.
7. **Stopping and starting nodes and expecting stale reads on demand.** Hints may replay very fast; stale reads are not guaranteed to appear.
8. **Treating `WriteTimeout` as a rollback.** Cassandra does not roll back mutations already delivered to replicas just because the client missed ACKs.
9. **Running multiple mutations on the same partition without controlling timestamps.** Last-write-wins can mask the behavior you meant to test.
10. **Equating read repair with cluster-wide compaction/repair.** These are distinct mechanisms.
11. **Injecting slow networks/stopping nodes in production.** Fault testing is valid only in controlled labs.
12. **Using a retry policy that silently alters CL.** Responses quietly change freshness/ACK contracts without visibility.

## 16. Extended Exercises and Answers

### Exercise 1 — Thresholds After One Node Goes Down

RF=3, `cass3` is down, `cass1` and `cass2` work normally. Can `ONE`, `QUORUM`, and `ALL` succeed?

**Answer:** `ONE` needs 1 so yes; `QUORUM` needs 2 so yes; `ALL` needs 3 so it fails.

### Exercise 2 — Stopping Another Node

RF=3, only `cass1` stays alive. Why can `ONE` succeed while `QUORUM` cannot?

**Answer:** `QUORUM=2` out of three replicas, while `ONE=1`. Only one target replica is responding.

### Exercise 3 — R+W Not Greater Than N

RF=3, both `ONE` write and `ONE` read succeed while only `cass1` is alive. Can the two sets actually overlap?

**Answer:** Yes, both can be `{cass1}`. `R+W>N` is a **sufficient condition to guarantee overlap across all valid sets**, not a necessary condition for every execution.

### Exercise 4 — Write QUORUM, Read ONE

RF=3, a `QUORUM` write succeeds on `R1,R2`, and a `ONE` read hits lagging `R3`. Can stale data be returned?

**Answer:** Yes. `W=2`, `R=1`, `R+W=3≤3`; the two sets can be disjoint.

### Exercise 5 — Never Seeing a Stale Read

In a healthy cluster, you run a thousand `ONE` reads after `QUORUM` writes without seeing stale data. Can you claim `ONE` guarantees read-after-write?

**Answer:** No. Empirical runs reflect only observed cases. `2+1≤3` still fails to guarantee overlap in the worst case.

### Exercise 6 — ALL Fails When a Node Stops

One replica is down. An `ALL` write returns `Unavailable`. Can we be certain zero live replicas received the mutation?

**Answer:** Do not generalize like that. The error indicates the request was not confirmed to CL; under other error/timing paths, mutations may still reach some replicas. Classify the specific error and reconcile.

### Exercise 7 — Timeout vs. Unavailable

Three replicas are marked UP, yet one ACK arrives too late; at `QUORUM`, what error can occur? What if the coordinator already knows only one replica is UP?

**Answer:** The first case can raise `ReadTimeout`/`WriteTimeout` depending on operation; the second can raise `Unavailable` because fewer than two replicas are considered alive.

### Exercise 8 — Local Quorum Across Two DCs

RF=3+3, write `LOCAL_QUORUM` in dc1 and read `LOCAL_QUORUM` in dc2. Must the two operations overlap?

**Answer:** No. The two response sets lie in two different DCs, even though each is a local majority.

### Exercise 9 — Writing EACH_QUORUM

RF=3+3. An `EACH_QUORUM` write succeeds; does a `LOCAL_QUORUM` read in dc2 overlap?

**Answer:** Yes, the write obtained at least two ACKs in dc2 and the read requires two responses from dc2's three replicas; `2+2>3`.

### Exercise 10 — Cluster-Wide QUORUM When Losing a DC

RF=5+1, the RF=1 DC is down, the RF=5 DC stays healthy. Can a cluster-wide `QUORUM` write succeed?

**Answer:** Yes. Total RF=6, global quorum=4, and the large DC has five replicas. An `EACH_QUORUM` write still fails because it requires one ACK from the small DC.

### Exercise 11 — Out-of-Order Timestamps

Client A writes `VALUE_A@2000000` and Client B later writes `VALUE_B@1000000`, both `QUORUM` writes succeeding. What does `SELECT` return absent other mutations?

**Answer:** `VALUE_A`, because timestamp 2000000 exceeds 1000000. This does not violate quorum intersection.

### Exercise 12 — Two Clients Reserve the Same Seat

Both sessions run `SELECT QUORUM` and then `UPDATE QUORUM` when the seat is empty. Is at most one write guaranteed to succeed? If not, what is the fix?

**Answer:** No. Read-check-write is non-atomic. Use `INSERT ... IF NOT EXISTS` (LWT/Paxos) on the same `seat_key` and inspect `[applied]`.

### Exercise 13 — Node and Data Recovery

Two nodes just restarted and show `UN`. `SELECT ONE` sees `SHIPPED`. Can we conclude all replicas hold `SHIPPED`?

**Answer:** No. `ONE` needs only one response; verify convergence and run appropriate repair to assess broader replica consistency.

### Exercise 14 — Retrying an Indeterminate Write

A `QUORUM` write hits `WriteTimeout`. The client immediately generates a new UUID and re-writes the same event. What is the main risk?

**Answer:** The first attempt may have applied on some replicas; retrying with a new UUID can create **two events**. Keep event/operation IDs stable and design idempotency/reconciliation.

## 17. Cleanup and Lab Restoration

Once finished, ensure **all lab nodes** are restored before wrapping up:

```bash
docker compose start cass1 cass2 cass3
docker compose exec cass1 nodetool status
```

If you want to keep the lab around for further study, simply exit `cqlsh` and save your findings. If you are certain this is a **temporary cluster with no important data**, you can tear down the Docker Compose resources:

```bash
# Run only in the exact directory of your test lab's compose.yaml.
docker compose down

# Only when you are certain you want to wipe all lab volumes/data as well:
# docker compose down --volumes
```

Never run volume/data deletion commands if the same Compose project serves another person's lab. Restarting nodes does not replace scheduled **anti-entropy repair** if replicas stayed down long or missed mutations past the hint window.

## 18. Summary

The two-session `cqlsh` lab demonstrates that **CL is a per-request/session property**, while success conditions depend on how many replicas **can actually respond within the CL scope**. In a single DC with RF=3, with two replicas left, `QUORUM` can succeed while `ALL` fails its threshold; with one replica left, `ONE` can succeed while `QUORUM` fails. When nodes recover, data converges through separate mechanisms, yet **an UP node does not automatically mean all copies are in sync**.

The **`R+W>N`** formula proves **mandatory overlap** between the ACK set of a **successful write** and the response set of a **successful read** over **the same replica set**. It does not make `ONE` reads always stale or always fresh, does not turn timeouts into rollbacks, and does not replace LWT for conditional updates. **Interpreting lab results properly** means recording topology, CLs, node states, error types, timestamps, operation ordering, and the boundaries of what can be inferred.

### References

- [Apache Cassandra — Dynamo / Tunable Consistency](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html): replication, read/write thresholds, coordinators, and replicas.
- [Apache Cassandra — CQL Data Manipulation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): `INSERT`, `UPDATE`, `SELECT`, `USING TIMESTAMP`, and conditional statements.
- [Apache Cassandra — cqlsh](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html): `CONSISTENCY` and `TRACING` in the shell.
- [Apache Cassandra — Hints](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/hints.html): hinted handoff when replicas miss mutations.
- [Apache Cassandra — Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html): role of anti-entropy repair and convergence after node failures.
