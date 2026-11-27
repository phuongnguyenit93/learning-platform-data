# Testing Restarts, Single-Node Loss, and Data Reconciliation

## 1. Experiment Objectives and Limitations

Apache Cassandra is a **distributed wide-column** database: a **partition key** maps to a token, and the keyspace replication strategy determines which **replicas** hold the data. Every read/write request goes to a **coordinator**; the **consistency level (CL)** governs how many replicas must respond before the client receives a result. Therefore, one node going down does not necessarily halt the cluster, though not every consistency level continues to succeed.

This lesson moves the learner from basic CQL usage to **controlled observation**: writing data while three nodes are healthy, stopping and restarting one node sequentially, writing additional data while a replica is absent, reconciling results after the node returns, and understanding the roles of **hints, read repair, and anti-entropy repair**.

By the end of this lesson, you will be able to:

1. Build a **3-node, single-datacenter, RF=3** test cluster with a Docker network and **separate volumes per node**.
2. Inspect the same ring from three perspectives using `nodetool status` and `system.local/system.peers_v2`.
3. Establish baseline data and compare reads/writes under `LOCAL_ONE`, `LOCAL_QUORUM`, and `ALL` while **one node is temporarily stopped**.
4. Distinguish a **graceful stop** from a **simulated crash**, and recognize `UN`, `DN`, native transport, and CQL serving capability.
5. Analyze why a timed-out/failed write **does not always mean no replica applied the write**.
6. Inspect evidence of hints/streaming/repair, and understand why a `SELECT` from a newly returned node **does not prove** the data is persisted in that node's local SSTables.
7. Recover all three nodes, reconcile the sample table, record an audit log, and clean up containers **without accidentally deleting data**.

> **Safety:** run only in an **isolated lab with no real data**. Never run these stop/kill/repair commands on production, shared clusters, or nodes serving other users. Three containers on one laptop are three Cassandra processes, **not three independent hosts or failure domains**.

## 2. Model to Understand Before Practicing

### 2.1. Three Nodes, One Datacenter, and Three Replicas

```text
                      Client (cqlsh / Java Driver)
                         ┌────────────┐
                         │ Coordinator│
                         └─────┬──────┘
                               │
     Network: pe010-net        │            Cluster: pe010-lab
                ┌──────────────┼─────────────┐
                │              │             │
         pe010-n1         pe010-n2       pe010-n3
         dc1/rack1        dc1/rack2      dc1/rack3
         volume_n1        volume_n2      volume_n3
                │              │             │
         Replica 1        Replica 2      Replica 3
                └────────── RF=3 ────────────┘

Local datacenter = dc1; LOCAL_QUORUM = floor(3/2)+1 = 2.
```

In this lab, each partition in keyspace `pe010_lab` has **three replicas** across the three nodes (once all three complete bootstrapping). The table uses **partition key `device_id`**, so a query with `WHERE device_id = ...` is routed by the coordinator to the owning replicas.

**Rack1/rack2/rack3 are purely logical labels.** Because all three run on one Docker host, losing that host, disk, or power source takes down all three nodes together. Never treat these lab results as proof of production disaster recovery or HA.

### 2.2. RF Differs from Consistency Level

| CL in `dc1` with RF=3 | Replicas Required to Respond | When All Three Are Healthy | When n3 Is Down, n1/n2 Healthy |
|---|---:|---|---|
| `LOCAL_ONE` | 1 | Can succeed | **Can succeed** |
| `LOCAL_QUORUM` | 2 | Can succeed | **Can succeed** |
| `ALL` | 3 | Can succeed | **Fewer than 3 replicas**, typically returns unavailable or timeout |

With **reads and writes at `LOCAL_QUORUM`**, the two responding replica sets in the same DC with RF=3 must overlap because **2 + 2 > 3**. That supports observing written data under normal conditions. However, Cassandra uses **mutation timestamps** for conflict resolution; clock skew, client-supplied timestamps, tombstones, timeouts, and real failures must still be evaluated separately. CL is not strict serializable SQL transactions, nor does it replace repair.

`LOCAL_ONE` requires fewer responses and can return a replica that **has not yet received the mutation**. `ALL` waits for all three, sacrificing availability when any replica is absent. `ANY` applies only to **writes** and can accept a hint in place of a replica ack; since it does not fit direct data verification here, this lesson **does not use `ANY`**.

### 2.3. Different Verification Layers

| Observation Layer | Tool | What You Can Conclude | What You Cannot Conclude From It Alone |
|---|---|---|---|
| Container/process | `docker ps -a`, `docker inspect` | Whether the process is running or stopped | That CQL or the ring is ready |
| Gossip/ring | `nodetool status` | Nodes seen as `UN`/`DN`, tokens/racks | That all replicas hold identical data |
| Native transport | `nodetool statusbinary` | Server accepts CQL over binary protocol | That keyspace reads/writes will succeed |
| Metadata | `system.local`, `system.peers_v2` | Cluster/DC/rack/host ID, known peers | That clients on other networks can reach every peer |
| CQL | SELECT/INSERT with chosen CL | Real request succeeded or failed | That a SELECT via n3 read from n3's **local** SSTables |
| Hints/repair | `listpendinghints`, logs, metrics, `nodetool repair` | Evidence that sync work is running or completed | That one query proves all replicas are fully identical |

## 3. Practice Prerequisites

### 3.1. Resources, Networking, and Version

This example uses **Cassandra 5.0.9**, Docker Engine/Docker Desktop running Linux containers, **three named volumes**, and one user-defined Docker bridge network. For three JVMs to run smoothly, a host with around **24 GiB RAM** is a **convenient lab reference**, capping each container at 4 GiB and JVM heap at 2 GiB. On hosts with less RAM, reduce load or adjust resources appropriately; **never use an under-provisioned setup to extrapolate production performance**.

In this example, **no CQL ports are published to the host**. `cqlsh` and `nodetool` run via `docker exec` **inside the nodes**. This avoids confusing host `localhost` with container IPs and avoids exposing an unauthenticated/non-TLS cluster to external networks.

Key ports **inside the network**:

- `7000/TCP`: internode/gossip/streaming (assuming default ports/TLS config).
- `9042/TCP`: native CQL for `cqlsh` and the Java Driver.
- `7199/TCP`: JMX for `nodetool`, not published to the host.

Pre-flight checks:

```bash
docker version
docker ps -a
docker network ls
docker volume ls
```

Names `pe010-net`, `pe010-n1`, `pe010-n2`, `pe010-n3`, and the three volumes below are dedicated to this lesson. If they **already exist**, inspect their origin/contents and **do not overwrite or delete** another lab.

### 3.2. Preparing the Network and Three Independent Volumes

Run on the host with Docker CLI (compatible with Bash or PowerShell):

```bash
docker pull cassandra:5.0.9
docker network create pe010-net
docker volume create pe010_data_n1
docker volume create pe010_data_n2
docker volume create pe010_data_n3
```

**Never share volumes**: each node maintains its own system tables, host ID, tokens, commit log, and SSTables. Cassandra replicates data across nodes **over the internode protocol**, not by having multiple Cassandra processes write to a shared directory.

Volumes preserve data across `docker stop/start` and `docker rm` as long as volumes remain intact. However, recreating multi-node containers with **different broadcast IPs** may require address-change or node-replacement procedures; therefore, this lesson uses **stop/start on the existing container**, not deleting and recreating a populated node to simulate failure.

## 4. Initializing Three Nodes in Sequence

### 4.1. Node n1: Initial Seed

```bash
docker run -d --name pe010-n1 --network pe010-net --memory=4g --memory-swap=4g -e MAX_HEAP_SIZE=2G -e CASSANDRA_CLUSTER_NAME=pe010-lab -e CASSANDRA_ENDPOINT_SNITCH=GossipingPropertyFileSnitch -e CASSANDRA_DC=dc1 -e CASSANDRA_RACK=rack1 -v pe010_data_n1:/var/lib/cassandra cassandra:5.0.9
```

Wait for n1 to report `UN` and open CQL:

```bash
docker logs --tail 80 pe010-n1
docker exec pe010-n1 nodetool status
docker exec pe010-n1 nodetool statusbinary
docker exec pe010-n1 cqlsh -e "SELECT cluster_name, data_center, rack, release_version FROM system.local;"
```

Expected: `pe010-lab`, `dc1/rack1`, `status=UN`, `statusbinary=running`. Docker `Up` **is not enough** to conclude Cassandra is ready. If JMX/CQL fails to connect, check logs and wait for actual readiness.

### 4.2. Node n2: Joining via Seed n1

Run only after n1 is ready:

```bash
docker run -d --name pe010-n2 --network pe010-net --memory=4g --memory-swap=4g -e MAX_HEAP_SIZE=2G -e CASSANDRA_CLUSTER_NAME=pe010-lab -e CASSANDRA_SEEDS=pe010-n1 -e CASSANDRA_ENDPOINT_SNITCH=GossipingPropertyFileSnitch -e CASSANDRA_DC=dc1 -e CASSANDRA_RACK=rack2 -v pe010_data_n2:/var/lib/cassandra cassandra:5.0.9
```

```bash
docker exec pe010-n1 nodetool status
docker exec pe010-n2 nodetool status
docker logs --tail 80 pe010-n2
```

Expect **two `UN` rows** from both n1 and n2 once bootstrap completes. `CASSANDRA_SEEDS` is for initial discovery/gossip and **does not** turn n1 into a master/leader.

### 4.3. Node n3: Completing the Cluster

Run only after both n1 and n2 are `UN`:

```bash
docker run -d --name pe010-n3 --network pe010-net --memory=4g --memory-swap=4g -e MAX_HEAP_SIZE=2G -e CASSANDRA_CLUSTER_NAME=pe010-lab -e CASSANDRA_SEEDS=pe010-n1 -e CASSANDRA_ENDPOINT_SNITCH=GossipingPropertyFileSnitch -e CASSANDRA_DC=dc1 -e CASSANDRA_RACK=rack3 -v pe010_data_n3:/var/lib/cassandra cassandra:5.0.9
```

```bash
docker exec pe010-n1 nodetool status
docker exec pe010-n2 nodetool status
docker exec pe010-n3 nodetool status
docker exec pe010-n1 nodetool describecluster
```

Proceed to keyspace creation only when **every ring view displays three `UN` rows** in datacenter `dc1` across the three logical racks. Bootstrap completes **asynchronously**, so do not assume failure if a node briefly shows `UJ` (*Up/Joining*).

To verify three **non-duplicate** node identities:

```bash
docker exec pe010-n1 cqlsh -e "SELECT cluster_name, data_center, rack, host_id FROM system.local;"
docker exec pe010-n2 cqlsh -e "SELECT cluster_name, data_center, rack, host_id FROM system.local;"
docker exec pe010-n3 cqlsh -e "SELECT cluster_name, data_center, rack, host_id FROM system.local;"
docker exec pe010-n1 cqlsh -e "SELECT peer, peer_port, data_center, rack, host_id FROM system.peers_v2;"
```

A healthy node normally lists the **other two peers** in `system.peers_v2`. Cross-check peer metadata with `nodetool status`; if any node sees only itself in the ring, **do not** proceed with node-loss tests.

## 5. Baseline Data Before Stopping a Node

### 5.1. RF=3 Keyspace and Partition-Key Table

Open interactive `cqlsh` on n1:

```bash
docker exec -it pe010-n1 cqlsh
```

At `cqlsh>`, run:

```sql
SELECT cluster_name, data_center FROM system.local WHERE key = 'local';

CREATE KEYSPACE IF NOT EXISTS pe010_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS pe010_lab.events_by_device (
  device_id text,
  event_id text,
  event_time timestamp,
  payload text,
  PRIMARY KEY ((device_id), event_id)
);

DESCRIBE KEYSPACE pe010_lab;
```

Here `device_id` is the **partition key** and `event_id` is the **clustering key**. All events with the same `device_id` belong to one logical partition mapped across the keyspace's three replicas. Fixed `event_id` strings make subsequent row comparisons deterministic without generating random UUIDs.

**Note:** `CREATE KEYSPACE IF NOT EXISTS` does not alter RF if the keyspace already exists. After creation, verify actual replication via `DESCRIBE KEYSPACE` or:

```sql
SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'pe010_lab';
```

If your actual datacenter is not `dc1` or the cluster lacks three nodes, do not use this map verbatim. **RF=3 cannot conjure three replicas** when fewer than three nodes exist.

### 5.2. Writing the Baseline While All Three Nodes Are Healthy

In `cqlsh` on n1:

```sql
CONSISTENCY ALL;

INSERT INTO pe010_lab.events_by_device
  (device_id, event_id, event_time, payload)
VALUES
  ('device-010', 'a-baseline',
   '2026-11-21T08:00:00Z', 'written-while-all-up');

SELECT device_id, event_id, event_time, payload,
       WRITETIME(payload)
FROM pe010_lab.events_by_device
WHERE device_id = 'device-010';
```

With RF=3, a write succeeding at `ALL` means **all three replicas acknowledged** per CL. That establishes a strong baseline for the test, though it does not constitute a backup or bit-for-bit verification across all three disks.

Note: `WRITETIME(payload)` returns the cell's mutation timestamp in **microseconds since Unix epoch**, distinct from the business column `event_time`. Re-running scripts changes cell write times; to compare runs clearly, record both `event_id` and `payload`.

### 5.3. Checking Replica Endpoints

On the host:

```bash
docker exec pe010-n1 nodetool getendpoints pe010_lab events_by_device device-010
docker exec pe010-n1 nodetool tablestats pe010_lab
docker exec pe010-n1 nodetool status
```

`nodetool getendpoints` lists endpoints responsible for partition key `device-010`. With three healthy nodes, RF=3, and one DC, expect **three addresses**. This shows **replica placement**, without reading SSTable files to compare data hashes.

On n2, test reading the same partition with `cqlsh`:

```bash
docker exec pe010-n2 cqlsh -e "SELECT device_id, event_id, payload FROM pe010_lab.events_by_device WHERE device_id='device-010';"
```

The one-shot `-e` invocation uses `cqlsh`'s default consistency; to test `ALL` or `LOCAL_QUORUM`, set `CONSISTENCY ...` inside the **same interactive `cqlsh` session** running the `SELECT`. Node n2 acts as coordinator and does not necessarily read solely from n2's local disk.

## 6. Experiment A: Gracefully Stopping One Node and Continuing Reads/Writes

### 6.1. Stopping n3 with Docker (Allowing Shutdown Time)

Before acting, ensure baseline data exists and all three nodes are `UN`. Close or set aside n1's `cqlsh` session, then on the host:

```bash
docker stop --time 120 pe010-n3
docker ps -a --filter name=pe010-n3
docker exec pe010-n1 nodetool status
docker exec pe010-n2 nodetool status
```

`docker stop` sends a normal stop signal and grants a grace period before forcing termination. **It does not guarantee a clean shutdown in all cases**: if the process fails to exit within the timeout, Docker kills it forcibly. For planned maintenance in real Cassandra clusters, follow rolling-operation procedures and consider `nodetool drain` to stop writes and flush before stopping; `drain` is not a tool for simulating "sudden node death."

Once the failure detector/gossip updates, the two surviving nodes show n3 as **`DN`** (*Down/Normal*). Immediately after stopping, the status may not flip yet; **do not assume a fixed instant**. `system.peers_v2` can still retain n3's metadata: **`DN` does not mean the peer was removed from the cluster**.

### 6.2. Testing Reads at LOCAL_QUORUM While n3 Is Down

In the host terminal, open `cqlsh` on n1:

```bash
docker exec -it pe010-n1 cqlsh
```

In `cqlsh`:

```sql
CONSISTENCY LOCAL_QUORUM;

SELECT event_id, payload, WRITETIME(payload)
FROM pe010_lab.events_by_device
WHERE device_id = 'device-010';
```

Expect to still read `a-baseline`: the two healthy replicas n1/n2 satisfy **2/3**. If the query fails due to timeouts, CPU/disk contention, networking, or unhealthy surviving nodes, collect logs and metrics before blaming Cassandra's quorum logic.

### 6.3. Writing a **New** Row While n3 Is Absent

Keep `CONSISTENCY LOCAL_QUORUM` in n1's session and run:

```sql
INSERT INTO pe010_lab.events_by_device
  (device_id, event_id, event_time, payload)
VALUES
  ('device-010', 'b-while-n3-down',
   '2026-11-21T08:05:00Z', 'accepted-by-quorum');

SELECT event_id, event_time, payload
FROM pe010_lab.events_by_device
WHERE device_id = 'device-010';
```

With n1/n2 healthy, the `LOCAL_QUORUM` write succeeds even though n3 missed the live mutation. This demonstrates **availability governed by CL**. Cassandra may store a **hint** for the down replica, though hints are **best effort**; never treat write success as proof that a hint was guaranteed to be stored and replayed.

Using a **row with a distinct `event_id`** rather than updating the baseline row is intentional: if one step fails, you can inspect each row cleanly without confusing failures with last-write-wins timestamp races on the same cell.

### 6.4. Testing ALL with One Replica Missing — Read Only

In the same n1 session:

```sql
CONSISTENCY ALL;

SELECT event_id, payload
FROM pe010_lab.events_by_device
WHERE device_id = 'device-010';
```

With n3 still down, RF=3, and one replica absent, **`ALL` lacks three responses**. Expect an error such as `Unavailable` or a timeout depending on the failure detector, timing, and node state. This is **not a schema error**: it shows the requested CL exceeds the number of available replicas.

**Why test `SELECT` instead of `INSERT` at an expected-failure step?** A timed-out write may still have reached **one or more replicas** despite returning an error to the client. Therefore, you cannot assume "write failed so the data definitely does not exist" and blindly retry a non-idempotent operation. In real applications, retries need deterministic keys/idempotency and awareness of CL/timeout semantics.

Before continuing or testing other CQL statements, reset CL:

```sql
CONSISTENCY LOCAL_QUORUM;
```

## 7. Experiment B: Restarting n3 and Reconciling Data

### 7.1. Restoring the Exact Existing Container and Volume

On the host:

```bash
docker start pe010-n3
docker ps --filter name=pe010-n3
docker logs --tail 100 pe010-n3
docker exec pe010-n3 nodetool status
docker exec pe010-n3 nodetool statusbinary
```

After restarting, the node reads data from `pe010_data_n3`, initializes services, and rejoins the ring. `docker start` succeeding **does not mean** the node is `UN` or accepting CQL yet. Wait until n1, n2, and n3 all report **three `UN` rows**:

```bash
docker exec pe010-n1 nodetool status
docker exec pe010-n2 nodetool status
docker exec pe010-n3 nodetool status
docker exec pe010-n3 cqlsh -e "SELECT host_id, cluster_name, data_center FROM system.local;"
```

If n3 remains `UJ` or `DN`, check `docker logs`, `nodetool netstats` from live nodes, and CPU/disk before proceeding.

### 7.2. Comparing Both Rows Across Different Coordinators

Open `cqlsh` on n1 with `LOCAL_QUORUM`:

```bash
docker exec -it pe010-n1 cqlsh
```

```sql
CONSISTENCY LOCAL_QUORUM;

SELECT event_id, event_time, payload, WRITETIME(payload)
FROM pe010_lab.events_by_device
WHERE device_id = 'device-010';
```

Run the same read from n3 (in a **separate** `cqlsh` session):

```bash
docker exec -it pe010-n3 cqlsh
```

```sql
CONSISTENCY LOCAL_QUORUM;

SELECT event_id, event_time, payload, WRITETIME(payload)
FROM pe010_lab.events_by_device
WHERE device_id = 'device-010';
```

Expect both queries to return:

| `event_id` | Business Time | `payload` | Write Phase |
|---|---|---|---|
| `a-baseline` | 2026-11-21 08:00 UTC | `written-while-all-up` | Before stopping n3, CL=ALL |
| `b-while-n3-down` | 2026-11-21 08:05 UTC | `accepted-by-quorum` | While n3 was down, CL=LOCAL_QUORUM |

**Never conclude "n3 has the data on disk" solely because `cqlsh` connected to n3 and `SELECT` returned it.** Node n3 acted as coordinator; `LOCAL_QUORUM` can satisfy the read from **n1 and n2**, where the row was written while n3 was down. Even a CL=ALL read can trigger replica reconciliation/read repair; thus a successful post-restart read **does not by itself prove hints already replayed**.

If `WRITETIME` varies across script re-runs, remember each `INSERT` writes a new mutation timestamp. Keep fixed `event_id` and `payload` values to separate **business content** from **cell write time**.

### 7.3. When to Read at ALL to Confirm All Three Replicas

Once all three nodes are `UN`, in an n1 session:

```sql
CONSISTENCY ALL;

SELECT event_id, payload
FROM pe010_lab.events_by_device
WHERE device_id = 'device-010';
```

Succeeding at `ALL` requires all three replicas to participate according to Cassandra's read semantics, which may trigger read repair. It is a **stronger check of CL=ALL read availability**, yet **not an audit tool for all SSTables** or a guarantee that every other token range is synchronized.

If it still fails even when all nodes report `UN`, collect logs/metrics, `nodetool tpstats`, `nodetool netstats`, latencies, and disk stats; there may be timeouts, inconsistency/repair backlog, or another system fault.

## 8. Hints, Read Repair, and Anti-Entropy Repair: Evaluating Evidence Properly

### 8.1. Hinted Handoff After a Node Stop

When a coordinator processes a write for a temporarily absent replica, it **may** record a **hint** in the **coordinator's** `hints/` directory preserving the original mutation and timestamp, then replay it once the replica returns. Hints are normally enabled by default, bounded by outage duration (`max_hint_window`, defaulting to ~**3 hours**), resources, and delivery conditions.

**Hints are best effort and do not replace repair.** This lesson does not alter hint windows, disable repair, or force replay to "prettify" results.

Before and after restart, observe on surviving nodes:

```bash
docker exec pe010-n1 nodetool statushandoff
docker exec pe010-n1 nodetool listpendinghints
docker exec pe010-n2 nodetool listpendinghints
docker exec pe010-n1 sh -c "ls -la /var/lib/cassandra/hints"
docker logs --tail 100 pe010-n1
```

- `statushandoff` reports whether handoff is enabled/active on the **queried node**; it **does not** count pending hints precisely.
- `listpendinghints` lists queued hints; output can be **empty** because hints have not flushed yet, already delivered, were not created under test conditions, or requests routed through another coordinator.
- Hint files sit on the **node storing the hint**, not on the downed replica.
- A test writing only a few mutations may not produce large visible hint files. Verifying hinted handoff requires combining **metrics, logs, delivery timing, and proper diagnostics**, not just `ls hints/`.

Never run `nodetool truncatehints` when replicas still need synchronization: it **discards queued mutations**. Do not alter `max_hint_window` or throttling on real clusters just to mimic lab timing.

### 8.2. Why Is Repair Still Necessary?

A downed replica can **miss writes**, hints can expire past the window, be lost in a crash, or fail creation. Cassandra uses **anti-entropy repair** to compare data across replicas for matching token ranges (e.g., via Merkle trees) and stream missing/divergent data. Repair must also be scheduled in production, especially regarding tombstones/`gc_grace_seconds` and deletes.

Never treat a successful `SELECT` via n3 as proof that repair ran. **Read repair** assists some read paths, yet never scans unread partitions or token ranges. **Full/incremental repair** is a separate operational task with CPU/disk/network cost.

As an **optional extension and only when all three nodes are `UN`**, you can run a **full repair scoped to the single lab keyspace/table**:

```bash
docker exec pe010-n1 nodetool repair --full pe010_lab events_by_device
```

This consumes I/O/CPU and needs free disk space; it **must not be used routinely as a readiness check**. Running repair on one node covers **that node's token ranges** per selected flags, not automatically a full-cluster scheduled repair campaign. For full-cluster repair, Apache documentation outlines repairing **primary ranges** (`-pr`) systematically across nodes/datacenters.

Monitor:

```bash
docker exec pe010-n1 nodetool netstats
docker exec pe010-n1 nodetool tpstats
docker exec pe010-n1 nodetool compactionstats
docker logs --tail 100 pe010-n1
```

A successful `repair` on sample data proves **the lab repair operation worked**, not that a production cluster has repair schedules, backups, or zero divergence across all nodes.

### 8.3. Interpretation Table After a Single-Node Outage

| Observation | Valid Conclusion | Invalid Conclusion |
|---|---|---|
| n3 turns `DN` when stopped | Gossip/failure detector on n1/n2 noticed node is down | That n3's data was deleted |
| `LOCAL_QUORUM` write succeeds while n3 is down | Two replicas acknowledged per CL | That n3 already received the mutation or hints are guaranteed stored |
| `ALL` read fails while n3 is down | Fewer than three replicas available for the read | That the table is corrupt or keyspace is broken |
| n3 restarts and turns `UN` | Node is up and joined the ring | That all local rows on n3 match n1/n2 identically |
| `SELECT` via n3 returns the new row | Client queried successfully through coordinator n3 | That the new row is definitely in n3's local SSTables |
| `listpendinghints` is empty | No pending hints listed at the moment queried | That hints never existed or all replicas are fully synced |
| `nodetool repair` completes | Repair finished for its target scope | That snapshots/backups and every cluster token range are healthy |

## 9. Experiment C (Optional): Process Crash and Recovery

**Run only after Experiments A/B finish, all three nodes are `UN`, and you accept you might need to rebuild the lab.** The goal is to contrast a **graceful stop** with an **abrupt process termination**; never test by damaging physical disks.

### 9.1. Simulating a Killed Process

While all three nodes are healthy, write one more row at `LOCAL_QUORUM` on n1:

```sql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO pe010_lab.events_by_device
  (device_id, event_id, event_time, payload)
VALUES
  ('device-010', 'c-before-kill',
   '2026-11-21T08:10:00Z', 'pre-crash-write');
```

On the host **lab-only**:

```bash
docker kill --signal=KILL pe010-n2
docker exec pe010-n1 nodetool status
docker ps -a --filter name=pe010-n2
```

Unlike `docker stop`, `docker kill --signal=KILL` terminates the process immediately without graceful shutdown. Cassandra maintains a **commit log** to replay unflushed mutations **on that node** at startup, subject to actual durability and fsync settings. It **does not** mean every acknowledged write was immediately fsynced (especially depending on `commitlog_sync` and hardware), nor does it replace replication or backups.

Restart the exact same container/volume:

```bash
docker start pe010-n2
docker logs --tail 100 pe010-n2
docker exec pe010-n2 nodetool status
docker exec pe010-n1 nodetool status
```

Wait for all three nodes to reach `UN`, then verify all three rows at `LOCAL_QUORUM` from n1/n2. When reviewing logs, look for recovery/commitlog replay messages, though **do not require** a specific replay line to appear: writes that already flushed or synced differently may not leave obvious replay lines. Never declare "crash test passed" simply because the container restarted.

### 9.2. When Should You Skip Experiment C?

Skip it if the machine lacks RAM/disk, the cluster still has `UJ/DN` nodes, valuable data must be kept, or you are unsure how to recover a node. This test only simulates a **process kill on one Docker host**; it does not evaluate SSD failure, VM loss, network partitions, rack outages, or consistency across every failure mode.

## 10. Verification with the Java Driver

When one node is temporarily down, the Java Driver can route queries through surviving nodes provided **contact points, peer addresses, local datacenter, authentication/TLS, and networking** are configured properly. On Docker Desktop, internal IPs advertised by Cassandra are typically unroutable from the host; hence this example assumes the **Java app runs inside a container on the same Docker network `pe010-net`**.

With Java 17 and Apache Cassandra Java Driver 4.x (e.g., dependency `org.apache.cassandra:java-driver-core:4.19.4`), sample code:

```java
import java.net.InetSocketAddress;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

public class CassandraFailoverRead {
    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("pe010-n1", 9042))
                .addContactPoint(new InetSocketAddress("pe010-n2", 9042))
                .withLocalDatacenter("dc1")
                .build()) {
            SimpleStatement stmt = SimpleStatement.builder(
                    "SELECT event_id, payload FROM pe010_lab.events_by_device " +
                    "WHERE device_id = 'device-010'")
                    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
                    .build();

            for (Row row : session.execute(stmt)) {
                System.out.println(
                        row.getString("event_id") + " => " +
                        row.getString("payload"));
            }
        }
    }
}
```

A single query succeeding while n3 is down illustrates the client → coordinator → surviving replicas path; it **does not** prove full application failover works in every scenario. Real-world testing requires reusing `CqlSession`, tuning timeouts/retries/backoff, avoiding unbounded retries on non-idempotent writes, recording statement CLs, and confirming advertised peer addresses are routable from the application.

**Crucial distinction:** CL is set per **Java/`cqlsh` request**, not via port 9042 or a global `cassandra.yaml` setting for all clients. RF belongs to the **CQL keyspace**; raising CL does not create extra data replicas.

## 11. Common Errors During Node Stop/Start Tests

| Symptom | Hypothesis to Check | Tools and Remediation |
|---|---|---|
| n2/n3 fail to join n1 initially | Wrong seed, wrong Docker DNS/network, internode port blocked, cluster/DC mismatch | `docker network inspect pe010-net`, per-node `docker logs`, `nodetool status` from multiple views |
| Node stays `UJ` for a long time | Slow bootstrap, streaming, or I/O; low RAM/disk | `nodetool netstats`, `docker stats`, `docker logs`; never create RF=3 keyspaces before three `UN`s |
| After `docker stop`, n3 is not immediately `DN` | Failure detector hasn't tripped yet or node view differs | Monitor `nodetool status` on n1/n2; never expect instant transition |
| `LOCAL_QUORUM` fails when only n3 is down | One surviving replica unhealthy, timeout, schema unstable, wrong RF/DC | `nodetool status`, `DESCRIBE KEYSPACE`, logs, `tpstats`, latency |
| `ALL` fails when n3 is down | Fewer than three required replicas | **Expected outcome**, never a reason to wipe data |
| n3 restarts yet `cqlsh` cannot connect | Native transport not open yet, JVM/commitlog recovery running | `nodetool statusbinary`, `docker logs pe010-n3`, wait for readiness |
| `SELECT` via n3 sees row, unsure of local persistence | n3 is just coordinator; may read from n1/n2 or trigger read repair | Cross-check hints, logs, repair/metrics; never infer local persistence from one `SELECT` |
| Hints empty despite writes during outage | Hints are best effort, different coordinator handled write, unflushed/already delivered, short outage | Check `listpendinghints` across likely coordinators, logs/metrics, and hint window |
| Write times out yet retry creates duplicates | Request partially applied; retry lacked idempotency | Use fixed PKs/event IDs in labs; design idempotency in apps |
| n3 restarts to `UN`, then hits timeouts/slow repair | Hint backlog, compaction/IO, network, full disk | `nodetool netstats`, `compactionstats`, `df -h`, logs |
| Recreated container with old volume gets wrong peer IP | Docker assigned new IP while Cassandra metadata/broadcast address holds old IP | Keep existing containers for stop/start; for real node replacement use replace/IP-change procedures |
| Host Java app cannot reach peers | Broadcast RPC is container IP unroutable across Docker Desktop/NAT | Put app on same Docker network or design valid endpoint/address translation |
| `nodetool repair` errors or stalls | Nodes not `UN`, insufficient disk/network/CPU, conflicting repair session | Ensure healthy nodes, inspect logs/metrics; never force production repair just to rush a lab |

Useful diagnostic sequence: **process → logs → gossip/ring → native transport → keyspace RF/DC → client CL → partition-key data → hints/repair/IO → Java connectivity**. Never hand-edit system tables, change tokens, `assassinate` nodes, or delete volumes just to force `UN`.

## 12. Results Summary Table and Analysis Questions

### 12.1. Experiment Log

Record actual timestamps for each step rather than copying sample values:

| Milestone | n1 | n2 | n3 | CL and Operation | Result / Evidence |
|---|---|---|---|---|---|
| T0 — After bootstrap | `UN` | `UN` | `UN` | Write `a-baseline` at `ALL` | Three replicas responded per CL; `getendpoints` shows three nodes |
| T1 — Stop n3 | `UN` | `UN` | `DN` once detected | `SELECT` at `LOCAL_QUORUM` | Expect to read baseline |
| T2 — n3 still down | `UN` | `UN` | `DN` | Write `b-while-n3-down` at `LOCAL_QUORUM` | Expect write succeeds with two healthy replicas |
| T3 — n3 still down | `UN` | `UN` | `DN` | `SELECT` at `ALL` | Expect unavailable or timeout |
| T4 — Start n3 | `UN` | `UN` | `UN` | `SELECT` on n1/n3 at `LOCAL_QUORUM` | Expect both baseline and row written during outage |
| T5 — All three healthy | `UN` | `UN` | `UN` | `SELECT` at `ALL`; inspect hints/repair as needed | Reconcile data and sync activity |
| T6 — Optional crash test | `UN` | restart n2 | `UN` | Write `c-before-kill`, kill/restart n2 | Observe startup/recovery and data at chosen CL |

**What to record in your log:** Cassandra and JDK versions, cluster/datacenter names, all three host IDs, keyspace RF, exact CL per request, outputs/errors, node stop/start timestamps, hint changes, key log excerpts, and free disk space.

### 12.2. Self-Check Questions

1. With `RF=3` and three healthy nodes, how many replicas must respond for `LOCAL_QUORUM`? When n3 is down, why can `LOCAL_QUORUM` succeed while `ALL` fails?
2. A `SELECT` from `cqlsh` connected directly to n3 returns `b-while-n3-down`. Why can't you conclude the row is already stored in n3's local SSTables?
3. A write at CL `ALL` times out. Can you conclude no replica wrote the data? What safeguard do retries require?
4. Do hints sit on the downed replica or on the coordinator storing the hint? Why can't hints replace scheduled anti-entropy repair?
5. How do `WRITETIME(payload)` and `event_time` differ? How can clock skew break last-write-wins expectations?
6. Why does this lab require three separate volumes? How does deleting/recreating a container with a new IP differ from `docker stop/start`?
7. If `RF=3` were changed to `RF=1`, how would stopping the node holding a partition affect reads/writes? Does adding three nodes while keeping RF=1 automatically create three replicas?
8. Does `nodetool status` showing three `UN` rows prove there are no tombstones, hint backlogs, pending compactions, or divergent data?
9. What differs between `docker stop --time 120` and `docker kill --signal=KILL`? How does the commit log help after a crash, and what are its limits?
10. Why must the Java Driver be tested from the actual network where the app runs, rather than relying solely on `docker exec ... cqlsh`?
11. When is `nodetool repair --full pe010_lab events_by_device` a reasonable optional extension, and why is it not a routine health check?
12. Three containers on one laptop can test losing a process, but what is missing to claim the system survives real rack/datacenter failures?

### 12.3. Passing Criteria

Learners complete this lab once they have: initialized three independent nodes in the same cluster/DC; observed three `UN` rows and three host IDs; written the CL=ALL baseline; stopped n3, verified `LOCAL_QUORUM` reads/writes succeed and `ALL` fails due to insufficient replicas; restarted n3, seen three `UN`s, and reconciled rows from n1/n3; distinguished coordinator reads from local replica persistence; and documented hints/repair alongside experiment limits. This builds the foundation for deeper lessons on **replication, consistency, repair, compaction, fault handling, and Java applications**.

## 13. Stopping the Lab While Preserving Data

**Clean up only after all three nodes are recovered**, `cqlsh` sessions are closed, and no Java apps are querying the cluster. If you ran the crash test, wait for n2 to be healthy before shutting down.

```bash
docker stop --time 120 pe010-n3
docker stop --time 120 pe010-n2
docker stop --time 120 pe010-n1
docker rm pe010-n3 pe010-n2 pe010-n1
docker network rm pe010-net
docker volume ls
```

These commands delete containers and the network while **preserving named volumes** `pe010_data_n1`, `pe010_data_n2`, and `pe010_data_n3`. **Never run `docker volume rm` or `docker volume prune`** when preserving data. To start a **completely fresh cluster**, create three new volumes; never attach old datasets under a different IP/cluster identity as if they were a clean bootstrap.

Note: **volumes on the same host are not independent backups**. Durable production data requires tested backup/restore workflows and separate physical failure domains for replicas.

## 14. Official References

- [Apache Cassandra — Dynamo architecture and consistency levels](https://cassandra.apache.org/doc/latest/cassandra/architecture/dynamo.html): quorum calculation, read/write replicas, and hinted handoff.
- [Apache Cassandra — Hints](https://cassandra.apache.org/doc/latest/cassandra/managing/operating/hints.html): hint creation conditions, `max_hint_window`, and best-effort limits.
- [Apache Cassandra — Repair](https://cassandra.apache.org/doc/latest/cassandra/managing/operating/repair.html): anti-entropy, full/incremental repair, primary ranges, and I/O impact.
- [Apache Cassandra — nodetool status](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/status.html): ring states `UN`, `DN`, `UJ`.
- [Apache Cassandra — nodetool getendpoints](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/getendpoints.html): determining replica endpoints by partition key.
- [Apache Cassandra — nodetool listpendinghints](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/listpendinghints.html): inspecting pending hints on a node.
- [Apache Cassandra — nodetool drain](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/drain.html): stopping writes and flushing during maintenance.
- [Apache Cassandra — nodetool repair](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/repair.html): repair syntax and `--full`, `-pr` options.
- [Docker Hub — Cassandra Official Image](https://hub.docker.com/_/cassandra): multi-node Docker, `CASSANDRA_SEEDS`, and volumes.
- [Docker Docs — docker container stop](https://docs.docker.com/reference/cli/docker/container/stop/): shutdown signals and grace periods.
- [Apache Cassandra Java Driver](https://github.com/apache/cassandra-java-driver): `CqlSession`, contact points, and request consistency.
