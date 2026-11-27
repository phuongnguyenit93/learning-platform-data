# Checking Schema, Topology Metadata, and Background Task State During Apache Cassandra Upgrades

## 1. The Problem: A Node Starting Up Does Not Mean the Upgrade Is Complete

Apache Cassandra is a distributed **wide-column** database: data is routed by **partition key**, replicated according to replication strategies, and queried via coordinators at a **consistency level** (CL). Java applications use CQL and drivers to read/write, while nodes continuously flush memtables, compact SSTables, run repairs, deliver hints, and stream data during topology changes.

In the **Upgrades and Compatibility** chapter of module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**, a core operational question is: after upgrading one or more nodes, does the cluster still have **schema agreement, accurate topology/replica placement, and controlled background tasks**?

A node can report **`UN`** in `nodetool status` yet still suffer from:

- Unpropagated schemas, causing some coordinators to reject newer tables or columns.
- Peers, racks, datacenters, or tokens deviating from design, causing wrong routing and replication.
- Overloaded repair/compaction/streaming driving up read/write p99 and timeouts.
- The Java Driver connecting cleanly while prepared statements, CQL types, or protocol features behave unexpectedly.
- Legacy SSTables remaining on disk or format upgrades omitted against version instructions.

Therefore, the critical rule is:

> **An upgrade passes only when data state, topology, background tasks, and applications are verified**—not merely when a Cassandra process starts up again.

This lesson provides an evidence-based verification workflow; **it does not replace release notes or upgrade guides for your exact source/target version pair**. Commands and system tables vary across Cassandra 3.x, 4.x, 5.x, patch releases, and vendor distributions.

## 2. Three Layers to Verify

| Layer | Key question | Common evidence sources | Consequences if skipped |
|---|---|---|---|
| **Schema** | Do nodes share identical keyspace, table, type, and index definitions plus valid schema versions? | `cqlsh DESCRIBE`, `system_schema`, `nodetool describecluster`, driver metadata | Query errors, invalid prepared statements, inconsistent CQL behavior |
| **Topology metadata** | Do host IDs, node addresses, tokens, DC/rack, RF, and peers match the design? | `nodetool status`, `nodetool gossipinfo`, `system.local`, `system.peers`/`system.peers_v2` | Wrong replica placement, missed CL, broken DC routing |
| **Background tasks** | Are compaction, flush, streaming, repair, hints, or stages bottlenecked? | `nodetool tpstats`, `compactionstats`, `netstats`, logs/JMX/metrics, repair tracking | Full disks, p99 spikes, timeouts, outages during subsequent node upgrades |

These three layers **depend on one another**. For example, a node booting with the wrong rack destabilizes topology; immediately launching repairs or adding nodes can trigger streaming and compaction that cascade the outage.

~~~mermaid
flowchart TD
    A["Begin change window"] --> B["Verify release/upgrade path"]
    B --> C["Save baseline schema + topology + task metrics"]
    C --> D["Canary / upgrade one node per runbook"]
    D --> E["Schema agreement and CQL smoke tests"]
    E --> F["Topology: host IDs, tokens, DC/rack, peers"]
    F --> G["Background: compaction, repair, streams, queues"]
    G --> H{"All gates pass?"}
    H -->|Yes| I["Record evidence, advance to next node"]
    H -->|No| J["Halt rollout, investigate and handle per playbook"]
    J --> E
    I --> K["Verify whole cluster and apps post-upgrade"]
~~~

In environments supporting rolling upgrades, **each node is a checkpoint**, yet exact order and allowable mixed-version states must come from **the official guide for the upgrade path being executed**.

## 3. Before Measuring: Lock Down the Compatibility Matrix

### 3.1. What Requires Exact Version Details

You cannot design a sound workflow knowing only "we run Cassandra." Before starting, record:

1. **Exact source and target versions**, including patch release and distribution.
2. **Supported upgrade path**; never assume jumping from 3.x to 5.x or mixing arbitrary releases works.
3. **Supported mixed-version duration**, schema agreement behavior, and restricted operational commands during that window.
4. **Supported Java runtime/JDK** per Cassandra release, GC configs, kernel, and storage.
5. **Java Driver version**, CQL protocol negotiation, authentication, TLS, and connection policies.
6. **SSTable format and SSTable upgrade procedure** if required by the release.
7. **Snitch, partitioner, token allocation, topology**, network protocols, and DC/rack mappings.
8. **Active CQL/DDL features**: UDTs, collections, indexes, LWTs, CDC, views, counters, etc.
9. **Downgrade/rollback policy**: some steps make reverting to the old binary unsupported.
10. **Restorable backups** and node replacement/recovery plans if upgrading fails.

**Never infer compatibility from release dates or major numbers.** For instance, "both 4.x and 5.x speak CQL" does not guarantee every rolling upgrade pairing or Java Driver feature is supported.

### 3.2. Pre-Upgrade Inventory Table Example

| Attribute | Node A | Node B | Node C | Expected outcome |
|---|---|---|---|---|
| Cassandra version | Old V | Old V | Old V | Planned source version |
| Datacenter | dc1 | dc1 | dc1 | Matches topology map |
| Rack | rack1 | rack2 | rack3 | Spread across failure domains |
| Host ID | H-A | H-B | H-C | **Unique**, never changed unintentionally |
| Token ownership | Per baseline ring | Per baseline ring | Per baseline ring | No unexpected shifts |
| Schema | Version S | Version S | Version S | Agreed before change |
| Task status | Stable | Stable | Stable | No unhandled risky tasks |
| Backups | Tested | Tested | Tested | Viable recovery plan ready |

This is an **illustrative inventory schema**, not a live cluster state. With vnodes, each node owns many tokens; the "Token ownership" column should reference the token list/hash/evidence path rather than just the first token.

### 3.3. Do Not Upgrade When Baseline Conditions Are Unstable

Before touching binaries, check for:

- Down nodes or unresolved `UJ`/`UL`/`UM` states.
- Schema disagreement.
- Incomplete hints/repair/streaming required by the runbook.
- Near-full disks, chronically growing compaction backlogs, or commit log/I/O errors.
- p99, timeouts, unavailable errors, or dropped messages already breaching SLOs.
- Latest backups lacking restore proof, or snapshots missing token coverage.
- Concurrent topology changes, bulk imports, backfills, or large schema migrations.

If any exist, **stop and resolve them** or secure an explicit risk-assessed change decision. Upgrading is not a default cure for an already overloaded cluster.

## 4. Schema Agreement: Concept and Limits

### 4.1. Schema Is State Propagated Between Nodes

Cassandra schemas cover keyspaces, replication settings, tables, columns, primary keys, types, indexes, views, and other release-specific objects. Nodes must reach **agreement** on schemas to route and parse CQL consistently.

When DDL changes, Cassandra distributes schema metadata via release-specific mechanisms. Briefly, nodes may report differing schema versions; drivers typically wait/check for agreement on certain DDL statements.

Distinguish clearly:

- **Schema agreement:** relevant nodes report matching schema versions.
- **Schema correctness:** the CQL definition matches application expectations.
- **Data correctness:** logical table data remains complete and accurate.
- **Protocol compatibility:** Java Driver and coordinators execute CQL along supported paths.

**Agreement is necessary, not sufficient**: the entire cluster can agree on a *broken* schema that was just deployed.

### 4.2. Checking from `cqlsh`

~~~cql
-- Run in cqlsh connected to a verified node/cluster.
DESCRIBE KEYSPACE telemetry;

-- Common system tables in modern Cassandra:
SELECT keyspace_name, replication, durable_writes
FROM system_schema.keyspaces
WHERE keyspace_name = 'telemetry';

SELECT table_name
FROM system_schema.tables
WHERE keyspace_name = 'telemetry';
~~~

`DESCRIBE` is a **`cqlsh` command**, not a CQL statement sent verbatim through the Java Driver. `SELECT` against `system_schema` exposes structural metadata when the running version supports those tables and columns.

**Do not build cross-version parsers on `SELECT *` over system tables**: metadata tables and columns evolve across releases. When comparing upgrades, record normalized DDL and explicit required fields.

### 4.3. Checking via `nodetool`

~~~bash
# Verify nodetool version and commands on the node.
nodetool version
nodetool help

# Some versions display cluster info and schema versions.
nodetool describecluster
~~~

Output from `describecluster` helps detect **multiple schema versions** inside a cluster at capture time. However:

- Output format varies by release.
- A single node/gossip view may temporarily miss a peer.
- Matching schema versions do not prove business queries work accurately.
- Down nodes do not respond or may not have completed schema propagation.
- During mixed-version operation, comparison/interpretation must follow the specific upgrade guide.

Measure **repeatedly over time and across trusted nodes** rather than relying on one snapshot.

### 4.4. What Must Be Compared in DDL

| Component | What to check before/after | Why it matters |
|---|---|---|
| Keyspace RF and replication strategy | `NetworkTopologyStrategy`, per-DC RF | Governs replica placement and CL satisfaction |
| `durable_writes` | Preserved per durability policy | Affects commit log write path |
| Table primary key | Partition key, clustering columns, order | Governs tokens and query patterns |
| Column definitions | Names, types, static/regular, UDTs | Driver codecs and data decoding |
| Table options | Compaction, compression, TTL, `gc_grace_seconds` | Read/write amplification, tombstones, storage |
| Indexes/views | Existence, rebuild state/compatibility | Secondary lookups and background load |
| Functions/aggregates | Only if used and version-supported | Runtime and Java/UDF features can differ |
| Auth/role metadata | `SELECT`/`MODIFY` permissions and resource scope | Prevents broken app logins or privilege creep |

Do not compare table names alone. Two tables with the same name but altered clustering keys, types, or RF can fail reads/writes or shift replica load.

## 5. Standard Schema Example for Smoke Testing

Suppose an app records telemetry by device and day:

~~~cql
CREATE KEYSPACE telemetry
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE telemetry.events_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    metric_value double,
    PRIMARY KEY ((device_id, event_day), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);
~~~

This is an **illustrative lab schema**, not an instruction to recreate production keyspaces. After upgrading, run **read-only queries or approved test writes into a dedicated test table**.

~~~cql
-- In cqlsh, use a CL matching test RF and datacenter.
CONSISTENCY LOCAL_QUORUM;

SELECT event_time, metric_value
FROM telemetry.events_by_device_day
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21'
LIMIT 20;
~~~

Verify:

- Does CQL parse cleanly and return expected types and row counts?
- Can you distinguish `UNAVAILABLE`, read timeouts, auth errors, and unknown table errors?
- Is `LOCAL_QUORUM` satisfied by healthy replicas in the DC?
- Does the driver receive accurate metadata, codecs, and prepared statements?
- Do queries use the full partition key, avoiding `ALLOW FILTERING` or full scans just for smoke testing?

**Never `CREATE`/`ALTER`/`DROP` tables during mixed-version if the upgrade guide forbids DDL.** Test schema creation belongs in labs or approved phases.

## 6. Topology Metadata: More Than Just Three Letters `UN`

### 6.1. Attributes to Capture in Baseline

In a Cassandra cluster, each node has:

- **Host ID**: node identity at the Cassandra layer.
- **Addresses/ports**: gossip/internode, CQL/native transport, and potentially multiple endpoints depending on version.
- **Datacenter and rack**: from snitch/topology config, governing replica placement.
- **Tokens**: ring positions defining data ownership ranges.
- **Node state**: up/down, joining/leaving/moving, and other transitional states.
- **Release version, schema version**: part of cluster-visible node info.
- **Pending ranges/streams** during certain topology operations, per tooling/version.

Changing or misreading any attribute can sever connectivity, misplace replicas, or turn an upgrade into an unintended topology migration.

### 6.2. Commands to Inspect State

~~~bash
# Ring nodes, token ownership, datacenter/rack, and state.
nodetool status

# Cluster view and schema versions, if supported.
nodetool describecluster

# Detailed gossip endpoints and state seen by this node.
# Output can be large, version-sensitive, and requires selective reading.
nodetool gossipinfo

# Current node details, heap/uptime, and general status.
nodetool info

# Streaming status during topology transitions.
nodetool netstats
~~~

These commands generally report a **local/JMX view**. Never assume node A seeing B as `UN` means node C shares the exact same view at that instant.

### 6.3. Reading `nodetool status` Correctly

Common status codes:

| Code | General operational meaning | Action needed |
|---|---|---|
| **`UN`** | Up and Normal | Still verify schema, reads/writes, and tasks; insufficient alone to declare healthy |
| **`DN`** | Down and Normal (last observed state) | Investigate node/network; do not arbitrarily upgrade other nodes |
| **`UJ`** | Up and Joining | Bootstrap/data streaming may still be incomplete |
| **`UL`** | Up and Leaving | Node is leaving the cluster |
| **`UM`** | Up and Moving | Token movement may be underway |
| **`?`** or other states | Version- and output-dependent | Check help/logs; never guess |

`UN` states that the node is **Up/Normal from that view**; it does not guarantee SSTables are format-upgraded, repairs are done, or p99 is healthy. A `UJ` node may be burning heavy disk/network receiving SSTables.

### 6.4. Distinguish the Token Ring from Physical Topology

With `NetworkTopologyStrategy`, replica placement depends on tokens and datacenters/racks. Tokens may span many vnodes; therefore:

- Do not take one token as representing the entire node.
- Do not infer ring position from IP addresses.
- Do not confuse **Owns** shown in `nodetool status` with exact physical disk size or exclusive ownership; percentages depend on replication/keyspaces.
- Do not infer from "three nodes in a DC" that RF is right or all three replicas are healthy.
- Never alter snitch/rack configs mid-upgrade without a separate topology migration plan.

If the replication factor changes accidentally, `LOCAL_QUORUM` behavior and fault tolerance shift even if CQL queries look unchanged.

## 7. `system.local`, `system.peers`, and `system.peers_v2`

### 7.1. Metadata from One Node

On supporting versions, query **the connected node**:

~~~cql
SELECT cluster_name, data_center, rack,
       host_id, release_version, schema_version
FROM system.local;
~~~

`system.local` reports **local info of the node answering the query**. If `cqlsh` connects via a proxy/load balancer, verify the exact coordinator you hit so you do not mistake its output for another node.

For peers, the system table depends on version:

~~~cql
-- Many environments provide system.peers:
SELECT peer, data_center, rack,
       host_id, release_version, schema_version
FROM system.peers;

-- Some Cassandra 4.x+ releases add system.peers_v2,
-- containing richer endpoint/port metadata.
-- Verify actual table/columns via DESCRIBE before using.
~~~

**Never assume `system.peers_v2` works on Cassandra 3.x.** One version's docs/commands are not a contract across all releases.

### 7.2. Some Metadata Is a Local View, Not Cluster-Wide Truth

`system.peers` or `system.peers_v2` reflects peers known to **the queried node**. While gossip settles, during network faults, or while nodes join, views can diverge.

When inspecting topology metadata:

1. Record the **source node** of the output.
2. Compare host IDs, DCs/racks, versions, and schema versions across multiple sampled nodes.
3. Check for missing/duplicated nodes, wrong addresses/ports, or stale metadata.
4. Compare against the planned topology diagram from the change plan.
5. Use `nodetool status` and logs to verify peers are genuinely UP/Normal.
6. Never manually edit `system.local`/`system.peers` tables via CQL.

**Manually updating/deleting system tables** can corrupt gossip, token/host ID metadata, or Cassandra invariants. If metadata is wrong, follow the version-exact runbook for replacing nodes, snitch/rack fixes, or supported remediation.

### 7.3. Reconciling Tokens and Host IDs

Practical steps:

- Capture `nodetool status` before upgrading.
- Save host IDs, DC/rack, and vnode/token lists (using version-supported tools).
- After each node upgrade, confirm its host ID **was not unintentionally replaced**.
- If a node boots with a new host ID, halt rollout and distinguish **proper node replacement** from **lost metadata due to a wrong data directory**.
- If token ownership or rack changes, investigate immediately before running repairs, streaming, or upgrading the next node.

Never assume a changed IP means a new host ID, nor assume a node keeping the same IP automatically retained its Cassandra identity.

## 8. Background Tasks: Remaining Backlogs Mean Not Ready Yet

### 8.1. Key Background Tasks During Upgrades

| Task | Purpose | Why it impacts upgrades |
|---|---|---|
| **Memtable flush** | Writes RAM data to SSTables | Drives disk writes; backlogs raise commit log pressure |
| **Compaction** | Merges SSTables, reconciles versions/tombstones per rules | Adds CPU/I/O and temp space, affecting p99 |
| **Repair** | Anti-entropy replica reconciliation | Consumes CPU/disk/network; may stream data |
| **Streaming** | Transfers SSTables for bootstrap/rebuild/repair/topology changes | Competes for disk and network across nodes |
| **Hints / hinted handoff** | Delivers missed mutations to returning replicas | Can burst write/network load when upgraded node rejoins |
| **SSTable format upgrade** | Rewrites/re-reads files into release-required format | I/O-heavy and can require large temporary disk |
| **Index/view build** | Creates or rebuilds secondary structures | Costs storage/CPU and changes query behavior |
| **Commit log replay** | Restores un-flushed memtable state at startup | Lengthens node startup; watch for errors |

No single `nodetool` command reveals **every** background task completely and accurately. Combine multiple commands, logs, and metrics.

## 9. `nodetool tpstats`: Are Executors Busy and Messages Dropped?

~~~bash
nodetool tpstats
~~~

Common fields:

| Field | Meaning | How to read properly |
|---|---|---|
| `Active` | Currently executing tasks | High values can be fine if throughput is healthy |
| `Pending` | Tasks queued waiting | Watch **sustained upward vs. downward trends** |
| `Completed` | Cumulative completed tasks in counter scope | Compute deltas over time |
| `Blocked`, `All time blocked` | Executor-specific blocked task counts per release | Do not confuse with waiting network sockets |
| Dropped messages | Dropped messages by type | Compute deltas and correlate with errors/timeouts; not 1:1 with failed CQL queries |

Example of two snapshots 60 seconds apart:

~~~text
Time    ReadStage Pending    Completed    READ dropped
10:00            20            500000              4
10:01           620            509000             64

Completed delta: 9,000 tasks / 60 s = 150 tasks/s
Pending delta:   +600
Dropped delta:   +60 messages
~~~

Stage and counter names are illustrative; newer releases may use different names. You can conclude **queues and dropped messages are climbing**, yet cannot immediately blame thread count alone: disk stalls, network issues, GC pauses, heavy scans, or streaming all cause queuing.

If `tpstats` shows mutation/flush stages backed up after a restart, inspect commitlog, heap/disk, and write rates before moving to the next node.

## 10. `nodetool compactionstats`: Backlogs and Temporary Disk Space

~~~bash
nodetool compactionstats
~~~

In many releases, this shows pending compactions and active tasks, often including keyspace/table, bytes processed/total, or progress.

### 10.1. Questions to Answer

- Are pending tasks **draining as the node stabilizes** or climbing steadily?
- Is a huge compaction running on a hotspot table?
- Does the node have enough free disk for **output SSTables** while source SSTables stay pinned?
- Are upgrade-related compactions/SSTable rewrites overlapping with repairs?
- Are read p99 and SSTables per read degrading?
- Do logs show I/O errors, corrupt files, or failed compactions?

**Hypothetical** example:

~~~text
10:00  pending compactions = 8
10:10  pending compactions = 50
10:20  pending compactions = 160
       disk free            = 13%
       read p99             = 900 ms
~~~

This is a clear signal **not to rush upgrading the next node**. Yet never conclude from `pending=160` that you must raise compaction concurrency: if disks are saturated, adding threads worsens latency.

### 10.2. SSTable Format Conversion Is a Separate Operation

Some upgrade paths require or recommend running **`nodetool upgradesstables`** once all nodes reach the target release and satisfy upgrade guide preconditions. This command can **rewrite SSTables**, consuming disk/CPU and temporary space.

~~~bash
# VIEW HELP ONLY while investigating; never run blindly on production.
nodetool help upgradesstables

# Avoid running upgradesstables without approval,
# headroom calculations, and official guidance for the version pair.
~~~

**Booting the new binary cleanly does not mean SSTables changed format.** Conversely, not every upgrade requires rewriting all SSTables immediately. Read release docs and preserve rollback options before triggering irreversible work.

## 11. `nodetool netstats`: Streaming and Topology Shifts

~~~bash
nodetool netstats
~~~

Depending on version, this displays active **SSTable streaming** sessions (sending/receiving), files/bytes transferred, peers, and progress.

Distinguish clearly:

- **Streaming:** bulk data transfer during bootstrap, rebuild, replace, and certain repair phases.
- **Replica messaging/CQL:** coordinator-to-replica traffic for normal requests.
- **Gossip:** membership/state exchange.
- **Driver-to-coordinator:** Java application traffic.

`netstats` **does not report all network traffic**. When zero streams appear, Cassandra can still carry heavy CQL, gossip, or hint traffic.

Example with two snapshots of the same session:

~~~text
11:00:00 transferred = 120 GiB
11:02:00 transferred = 126 GiB

Average rate over 120 seconds
= 6 GiB / 120 s ≈ 51.2 MiB/s
~~~

If the session restarted or byte totals reset, never subtract values across distinct sessions. Likewise, 95% progress **does not mean** 5% remaining wall time; duration depends on remaining file sizes, network, and finalization steps.

### 11.1. When a Node Is Joining

If `nodetool status` reports `UJ`, the node does not yet hold full data for its future ownership. Monitor `netstats`, logs, and node state—do not treat `process UP` as ready to proceed with rollout.

### 11.2. When Repair Is Running

Some repair phases do not stream continuously. Empty `netstats` **does not prove repair finished**. Track version-appropriate repair status/logs and metrics rather than inferring from one command.

## 12. Hints, Flushes, Commit Logs, and Repairs: Easily Overlooked Load Sources

### 12.1. Hints After Node Restart

During a rolling upgrade, a node goes temporarily offline. Other replicas/coordinators may store hints for missed mutations to replay when the node returns, if enabled and within limits.

When the node returns:

- Hint delivery can burst write and network load.
- The restarted node may simultaneously replay commit logs, flush, and compact.
- Under heavy read/write traffic, p99 can exceed baseline.
- Hints **do not replace repair** across prolonged outages or diverged replicas.

Before upgrading the next node, verify the cluster is healthy and background tasks settled back to acceptable levels; never equate "back UP" with "received every missed mutation."

### 12.2. Flushes and Commit Logs

After restart, commitlog replay can take time. Cassandra uses commit logs to recover un-flushed mutations into SSTables while logs remain valid. Slow disks cause flush/compaction backlogs and prevent commitlog segments from recycling.

Monitor:

- Startup/replay logs, node readiness, and CQL health.
- Free disk on both **data** and **commitlog** volumes.
- Flush pending queues via `tpstats`/metrics.
- Write latency, unavailable/timeouts, and I/O errors.
- SSTable counts and compaction backlogs.

Never delete commit logs or SSTables manually just because disk usage looks high; they may hold un-flushed data.

### 12.3. Repair Readiness

Before upgrading, know the repair schedule and status. Repair provides anti-entropy between replicas yet consumes heavy I/O and network.

During mixed-version operation:

- Do not launch full-cluster repairs or alter repair settings if restricted by the upgrade guide.
- Do not extend replica downtime near hint/tombstone policy limits without risk review.
- Do not assume passing `LOCAL_QUORUM` reads prove all replicas match.
- If a repair is mid-flight, record the task/phase, owner, and handling plan before restarting nodes.

### 12.4. Recording Background Job States Without Single-Command Output

Per-node checklist before advancing:

| Task | Confirmed state | Source |
|---|---|---|
| Flush | Pending stable/draining | `tpstats`, metrics |
| Compaction | No dangerous backlog | `compactionstats`, disk telemetry |
| Streaming | No unexpected sessions | `netstats` and logs |
| Repair | None left half-broken per workflow | Repair logs/metrics/management tools |
| Hints | Delivery not overloading node | Hints metrics/logs |
| Commitlog replay | Completed, zero I/O errors | Startup logs, readiness |
| Index/view builds | Finished or safe to continue | Version-appropriate tools/logs |
| SSTable format | Matches phase and version policy | Upgrade guide, tooling |

**"Saw no errors" is not a verified state.** Record exact evidence sources and timestamps, or mark **UNKNOWN**.

## 13. Checkpoint-Gated Upgrade Workflow

### 13.1. Phase A — Pre-Upgrade Baseline

Before executing operations that alter data or metadata:

1. Verify supported upgrade paths, rollback/downgrade rules, and JVM/driver requirements.
2. Capture schema: DDL, `system_schema`, schema versions, and object inventory.
3. Capture topology: `nodetool status`, host IDs, tokens, DC/rack, RF, and peer metadata.
4. Capture background state: `tpstats`, `compactionstats`, `netstats`, repairs/hints/flushes.
5. Capture performance: QPS, read/write p50/p95/p99, errors, timeouts, disk/network/GC.
6. Verify backups/snapshots and a recent restore drill.
7. Confirm no down nodes or unfinished topology changes exist.
8. Record UTC timestamp, accountable owners, and change boundaries.

### 13.2. Phase B — Canary / First Upgraded Node

**Exact service stop/start, drain, binary swap, and config steps must follow the runbook for the exact version pair.** This lesson does not assert a single shutdown sequence valid for every release.

Once the node comes back up:

- Verify process/readiness and logs, not merely TCP port 9042 listening.
- Verify right release, host ID, DC/rack, tokens, and `UN`.
- Verify schema agreement and run CQL smoke tests.
- Verify the driver receives metadata and executes queries/codecs cleanly.
- Check `tpstats`/`compactionstats`/`netstats` and error logs.
- Confirm remaining replicas still cover real application CLs.
- Check which tasks must finish per the upgrade guide before proceeding.

### 13.3. Phase C — During Mixed-Version Operation

While old and new nodes run together (if allowed by the upgrade path):

- **Enforce feature/DDL/protocol limits** from release notes.
- Avoid unauthorized or unnecessary schema changes.
- Do not run SSTable format upgrades, large repairs, or risky rollbacks unless permitted by the guide.
- Do not upgrade more nodes concurrently than RF/CL fault budgets tolerate.
- Monitor per DC/rack to avoid breaking quorum simultaneously.
- Watch closely for driver errors/retries and topology drift.
- Track per-node versions so "in-progress rollout" is never mistaken for an error.

### 13.4. Phase D — Cluster-Wide Post-Upgrade

Once all nodes run the target version:

1. Confirm cluster membership, host IDs, tokens, DC/rack, and RF match the plan.
2. Verify schema agreement and diff DDL against baseline, accounting for any changes.
3. Run read/write smoke tests **on safe workloads** with proper permissions and data safety.
4. Verify driver compatibility, prepared statements, LWTs (if used), counters, and paging.
5. Verify `tpstats`, compaction, streaming, hints, repairs, and flushes show no bottlenecks.
6. Run SSTable format upgrades or enable new features only after passing official gates.
7. Monitor p50/p95/p99 and timeouts long enough to observe real traffic.
8. Update version records, backup status, topology docs, and rollback policies.

## 14. Java Driver 4.x: Verifying Metadata and a Query

Do not test with `cqlsh` alone; Java apps may use different protocol negotiation, prepared statements, codecs, and authentication. A targeted test should **connect to the right cluster, inspect metadata, and run a partition-keyed query**.

~~~java
import com.datastax.oss.driver.api.core.CqlIdentifier;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.metadata.Metadata;
import com.datastax.oss.driver.api.core.metadata.Node;

import java.net.InetSocketAddress;
import java.time.LocalDate;
import java.util.UUID;

public final class UpgradeSmokeTest {
    public static void main(String[] args) {
        // Example for LAB or an approved endpoint.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress(
                    "10.50.0.11", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            Metadata metadata = session.getMetadata();
            if (!metadata.getKeyspace(
                    CqlIdentifier.fromCql("telemetry")).isPresent()) {
                throw new IllegalStateException(
                    "Expected keyspace telemetry was not found");
            }

            for (Node node : metadata.getNodes().values()) {
                System.out.println(
                    "nodeId=" + node.getHostId() +
                    " dc=" + node.getDatacenter() +
                    " rack=" + node.getRack());
            }

            PreparedStatement ps = session.prepare(
                "SELECT event_time, metric_value " +
                "FROM telemetry.events_by_device_day " +
                "WHERE device_id = ? AND event_day = ? LIMIT 10"
            );
            BoundStatement bound = ps.bind(
                    UUID.fromString(
                        "11111111-1111-1111-1111-111111111111"),
                    LocalDate.of(2026, 11, 21))
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM);

            Row first = session.execute(bound).one();
            System.out.println(
                "SELECT completed; firstRowPresent=" + (first != null));
        }
    }
}
~~~

This illustrates **Java Driver 4.x APIs**, not production-ready TLS/auth/driver tuning. `node.getHostId()` and metadata snapshots reflect **the driver's view**, which can lag behind topology changes; never rely on driver metadata as the sole source of membership truth.

Important notes:

- If the test table has no matching row, `first == null` is valid; verify execution succeeded rather than reporting "data lost."
- `LOCAL_QUORUM` requires matching keyspace RF and healthy nodes in the local DC.
- Contact points and local DC must point to **the target cluster**, never confusing lab with production.
- For real applications, test all actual query shapes and codecs used—not just one `SELECT`.
- If using async/paging, LWTs, collections/UDTs, add dedicated smoke tests for each critical feature.
- Cross-check every version pair against the official **Java Driver and Cassandra compatibility matrix**.

### 14.1. Nuances Around Driver Schema Agreement

The driver can track/check schema agreement and refresh metadata. However:

- A delayed metadata snapshot does not automatically mean the server schema is broken.
- A query succeeding on one coordinator does not prove all nodes share the same schema.
- DDL queries and keyspace metadata changes during mixed-version periods may carry specific restrictions.
- Never spam DDL retries to "force schema agreement" while gossip/metadata is unhealthy.

If the driver reports schema-related errors, capture driver version, coordinator, statement template, schema versions, and logs instead of blindly flushing caches/prepared statements.

## 15. Incident Analysis: Schema Agreement Fails

**Scenario:** After upgrading node B, `nodetool describecluster` reports two schema versions while A/C keep serving requests.

### Step 1 — Capture State Instead of Running DDL

Record UTC timestamp, versions of A/B/C, `nodetool status`, schema versions, and node B logs. Do not fire random `ALTER TABLE` statements hoping to reset hashes/versions.

### Step 2 — Check Connectivity/Gossip and Node Membership

Confirm B has the right DC/rack, host ID, and addresses, and is not `UJ` or `DN`. Inspect `gossipinfo` and any network errors.

### Step 3 — Compare DDL and Metadata per View

Inspect `DESCRIBE KEYSPACE`, `system_schema`, and metadata from relevant nodes. If one node simply hasn't received the schema yet, check propagation timing and log errors; if DDLs genuinely differ, never pick "the newest" by timestamp while ignoring compatibility.

### Step 4 — Check Version-Pair Support

During mixed-version operation, schema transport and allowed CQL features may be constrained. Consult official guidance and never force new DDL that older nodes cannot parse.

### Step 5 — Hold Rollout Until Evidenced

Advance to the next node only once schema, topology, app smoke tests, and task queues pass approved gates. If unresolvable, execute a rollback/recovery plan **accounting for SSTable and metadata compatibility**—not merely swapping back the old binary.

## 16. Incident Analysis: Node Is `UN` Yet Topology Metadata Differs from Baseline

**Scenario:** Node B restarts and reports `UN`. However, its `data_center` or `rack` differs from baseline, or a brand-new host ID appeared.

Hypotheses to investigate:

- Snitch/rack config changed accidentally during package update.
- Config file reset or wrong volume mounted.
- Wrong data directory/system metadata caused the node to boot with a new identity.
- A node-replace workflow was skipped or misapplied.
- Stale gossip view or unrefreshed peer metadata.
- Internode address/port changed from old config, causing unstable connections.

Safe workflow:

1. **Halt upgrading the next node.**
2. Diff planned config/manifests against live settings using approved tooling; this lesson covers methodology rather than editing live configs.
3. Capture `nodetool status`, `gossipinfo`, `system.local`, and peer views.
4. Confirm host ID, DC/rack, tokens/placement, and the root cause of drift.
5. Never "patch" system tables via CQL to force host IDs or tokens.
6. Use the version's **identity-restore/node-replace** runbook if required.
7. Verify RF/CL, data, and streaming/repair after membership recovers.

**A node keeping the old hostname/IP yet holding a different host ID or token set** threatens data/replication far more severely than a simple failed client connection.

## 17. Incident Analysis: Prolonged Compaction and Streaming Post-Upgrade

**Scenario:** Node A upgrade completed per process status. Yet 30 minutes later, pending compactions climbed from 5 to 140, `netstats` shows heavy incoming streams, write p99 jumped, and free disk dropped.

### Step-by-Step Investigation

1. **Find stream source:** is the node joining/rebuilding/repairing/replacing? Is the stream part of the upgrade plan?
2. **Measure compaction:** does `compactionstats` show active tasks progressing or backlogs growing?
3. **Measure disk I/O:** await/p99, free bytes, write throughput, throttling, and I/O errors.
4. **Measure executors:** `tpstats`, pending/dropped messages on read/mutation/flush stages.
5. **Measure application:** p95/p99, timeouts/unavailable, driver retries, and in-flight requests.
6. **Check logs/version:** is SSTable rewriting required by the upgrade guide, or an unrelated task?
7. **Pause decision:** do not upgrade the next node if stop conditions trigger; consider shedding non-essential load per runbook.

### What Never to Do

- Never delete old SSTables or commit logs to "free disk space."
- Never raise compaction concurrency when storage is already saturated.
- Never lower read/write CL to hide timeouts without evaluating correctness.
- Never kill active streaming/repair arbitrarily while recovering replicas.
- Never trigger extra `upgradesstables` just because old SSTables were spotted without headroom and upgrade policy approval.

**`UN` + heavy background backlog = insufficient evidence to continue rollout.**

## 18. Dashboards and Measurement Gates

### 18.1. Illustrative Baseline Template

| Metric | Pre-upgrade baseline | Illustrative monitoring gate |
|---|---:|---|
| API read p99 | 80 ms | Within approved SLO |
| API write p99 | 35 ms | Within approved SLO |
| Timeout rate | 0.05% | Within error budget |
| Worst-node data disk free | 38% | Above practical safety floor |
| Compaction pending | 5–15 | Trend does not grow unbounded |
| Stage pending/dropped | Stable | No sustained abnormal spikes |
| Streaming sessions | None unscheduled | Active tasks have owner, progress, and reason |
| Schema versions | Agreed | Per version gate and node state |
| Host IDs/DC/rack | Matches baseline | Zero unexplained drift |

**Numbers are hypothetical to illustrate gating**, not default Cassandra thresholds. Real change docs must define observation windows and sample sizes sufficient for decisions.

### 18.2. Distinguish Point Snapshots from Trends

Single snapshots of `nodetool tpstats` and `compactionstats` can hide recent spikes. You should:

- Capture multiple snapshots over time on the same node and version.
- Compute deltas on counters (e.g., Completed, Dropped) rather than treating cumulative totals as throughput.
- Account for counter resets on node restarts before computing deltas.
- Compare metrics of **matching scope and units**; never subtract coordinator p99 from driver p99 to deduce network latency.
- Never average per-node p99s to get cluster p99; aggregate histograms/distributions properly.
- Track p99 **alongside** timeouts/errors; slow timed-out requests drop out of success latency histograms.

### 18.3. Post-Node Result Form Example

~~~text
CHANGE ID:
Node/host ID:
Expected DC/rack/tokens:
Source version -> target version:
Upgrade guide/path reference:
Timestamp UTC:

Schema:
  describecluster schema versions:
  keyspace/table/UDT smoke check:
  DDL diff explained? PASS/FAIL/UNKNOWN

Topology:
  nodetool status:
  host ID preserved? PASS/FAIL/UNKNOWN
  DC/rack/tokens match baseline? PASS/FAIL/UNKNOWN
  peer metadata consistent? PASS/FAIL/UNKNOWN

Background:
  tpstats active/pending/dropped trend:
  compactionstats pending/progress:
  netstats sessions/owner:
  repair/flush/hints/replay status:

Application:
  Java Driver version/protocol tested:
  read/write p99:
  timeout/unavailable:
  prepared statement/UDT/LWT/paging tests:

Decision:
  GO / HOLD / ROLLBACK-PLAN
  Approver / evidence links:
~~~

Record **UNKNOWN** whenever evidence is lacking. Never mark PASS simply because the node looks alive.

## 19. Common Mistakes

| Claim/action | Why it is wrong | Proper practice |
|---|---|---|
| "Node is `UN`, so upgrade is done." | Fails to check schema, tasks, driver, or data | Enforce all three gate layers |
| "`describecluster` shows one schema version, so schema is right." | All nodes can agree on a broken schema | Diff DDL/invariants against baseline |
| "`system.peers` is cluster-wide topology truth." | Local view, can be stale | Cross-check multiple nodes, `status`, and change plan |
| "Host ID changing after restart is normal." | May signal wrong data dir or unintended replace | Halt rollout, investigate identity |
| "DC/rack doesn't matter if all nodes are UP." | Replication placement depends on topology | Verify snitch, DC/rack, and RF |
| "Reads succeed, so all replicas are in sync." | CL may allow lagging replicas | Check repair/replica health |
| "Empty `netstats` means zero network traffic." | CQL/gossip/hints are not SSTable streaming | Check network and driver metrics |
| "Repair is done when `netstats` is empty." | Repair has non-streaming phases | Check repair status/logs |
| "Pending compaction is high, so raise threads." | Saturated disks worsen under extra threads | Check I/O, headroom, and progress |
| "Upgrade SSTable format right after the first node." | Can break rolling compatibility/rollback | Follow version-pair guide |
| "Any CQL driver works with any server release." | Protocol/feature/codec support varies | Test against exact driver/version matrix |
| "Disable schema checks to reduce errors." | Masks issues without fixing schema propagation | Investigate gossip/metadata and DDL |
| "Backups exist without restore tests; good enough." | Backups may miss files or be incompatible | Rehearse restore into an isolated cluster |
| "Average of node p99s equals cluster p99." | Percentiles are not additive | Aggregate histograms properly |
| "Swapping back the old binary always rolls back." | SSTables/metadata may have changed | Follow rollback policy and backups |

## 20. Exercises and Scenarios with Answers

### Question 1 — Schema Version

After upgrading node B, `nodetool describecluster` reports two schema versions. Can you immediately upgrade C because B is `UN`?

**Answer:** No. Verify schema agreement, gossip, version compatibility, and DDL diffs; `UN` status does not resolve schema disagreement.

### Question 2 — Host ID

A node restarts post-upgrade with the same IP yet a different host ID. Is this merely cosmetic?

**Answer:** No. It may indicate an improper new node/replace, wrong data directory, or corrupted metadata. Halt rollout and verify tokens/identity against the supported runbook before proceeding.

### Question 3 — Reading `system.local`

You connect CQL to node A and query `system.local`. Can you treat the result as local info for node B currently being upgraded?

**Answer:** No, unless you confirm the query actually executed on B. `system.local` reflects the node serving the query; verify endpoint/coordinator.

### Question 4 — Version 3.x and `peers_v2`

A runbook written for 4.x instructs querying `system.peers_v2` on a 3.x cluster. Is the table guaranteed to exist?

**Answer:** No. System metadata schemas vary across versions; check docs and live tables on the source release and use the appropriate query.

### Question 5 — Completed Counter

`ReadStage Completed` rises from 1,000,000 to 1,012,000 in 60 seconds. What is the approximate task completion rate?

**Answer:** `12,000 / 60 = 200` tasks/s. Do not assume this equals 200 CQL SELECTs/s, as one request can spawn multiple internal tasks.

### Question 6 — Post-Upgrade Compaction

Node B shows rising pending compactions, 8% free disk, and write p99 multiplied severalfold. Should you immediately raise compaction concurrency?

**Answer:** No. Disk I/O and temporary space may be bottlenecked. Halt rollout, measure resources, and relieve pressure per runbook before tuning.

### Question 7 — Streaming

`nodetool netstats` shows zero active sessions. Can you conclude no background tasks or network traffic are running?

**Answer:** No. Compaction, flushes, hints, gossip, CQL, and certain repair phases do not necessarily appear as SSTable streams.

### Question 8 — Schema Agreement vs. Business Correctness

All nodes share the same schema version, yet a column in DDL was changed to an incompatible type before the upgrade. Can schema be considered passing?

**Answer:** Schema may have **agreement**, yet **correctness** failed. Diff DDL against baseline and test codecs/business queries.

### Question 9 — Mixed-Version

After the first node, the team wants to start using a target-only CQL feature right away. Should they enable it app-wide?

**Answer:** Not until the upgrade guide confirms mixed-version support and nodes meet prerequisites. Usually wait for the proper phase and test protocol/driver compatibility.

### Question 10 — RF and CL

Keyspace RF=3, app uses `LOCAL_QUORUM` in DC1. If two DC1 replicas stop simultaneously during upgrade, what happens?

**Answer:** Quorum of two out of three cannot be reached with only one live replica; requests fail with unavailable/timeouts. Schedule outages according to RF/CL and live capacity.

### Question 11 — SSTable Format

An operator wants to run `nodetool upgradesstables` right after upgrading the first node to "clean up." Is this a read-only status command?

**Answer:** No. It rewrites SSTables, burns I/O, and impacts rollback/mixed compatibility. Run only at the documented phase/version with budgeted headroom.

### Question 12 — Repair and `netstats`

`netstats` is empty, yet logs state repair is in validation. Is that a contradiction?

**Answer:** No. Repair has multiple phases; validation does not necessarily maintain continuous streaming sessions. Check version-appropriate repair status/logs.

### Question 13 — Driver Metadata

The Java Driver sees 3 nodes and confirms the keyspace exists. Can you conclude all application prepared statements are compatible with the new version?

**Answer:** No. Metadata discovery is only one signal; test statements, types/UDTs, paging, LWTs, retries, and protocol negotiation under real workloads.

### Question 14 — "Better" p99 After Upgrade

Successful read p99 dropped from 400 ms to 100 ms, while timeout rate jumped from 0.1% to 5%. Is this a win?

**Answer:** No. Slow requests timed out and dropped out of the success latency histogram. Gates must evaluate **latency, error budgets, and throughput together**.

## 21. Summary Checklist Before Advancing to the Next Node

~~~text
UPGRADE GATE — Cassandra node N
--------------------------------
[ ] Verified supported source -> target version pair.
[ ] Mixed-version restrictions/rollback policy read and enforced.
[ ] Backups/restore and quorum/availability plans ready.
[ ] Node has exact host ID, DC/rack, and tokens.
[ ] nodetool status shows sensible node and peers; zero topology drift.
[ ] system.local / peers metadata shows no unexplained discrepancies.
[ ] Schema agreement achieved per version-pair rules.
[ ] DDL diff matches baseline; zero unplanned schema changes.
[ ] Java Driver version/protocol and CQL smoke tests pass.
[ ] tpstats Pending/Dropped show no abnormal growth.
[ ] compactionstats shows no dangerous backlog/disk pressure.
[ ] netstats/repair/streaming have clear state and owners.
[ ] Commit log replay, flush, hints, and I/O errors checked.
[ ] Free disk, CPU/GC, network, and read/write p99 within thresholds.
[ ] Timeouts/unavailable/retries within error budget.
[ ] Recorded UTC timestamp, evidence, GO/HOLD decision, and approver.
~~~

Do not mechanically "wait for every pending count to hit 0" if legitimate background tasks run continuously. Base gates on **baselines, trends, SLO impact, and upgrade rules**.

## 22. Summary

Verifying Cassandra upgrades rests on three pillars:

1. **Schema:** check both agreement *and* DDL correctness; matching version hashes alone do not guarantee business queries succeed.
2. **Topology:** compare host IDs, tokens, DC/rack, RF, peers, gossip, and `UN`/`UJ` states against baseline; never manually edit system tables or confuse IPs with node identity.
3. **Background tasks:** monitor `tpstats`, `compactionstats`, `netstats`, flushes, repairs, hints, commit-log replay, and SSTable rewrites alongside disk/network/GC.
4. **Version compatibility:** verify every command, metadata table, protocol feature, and rolling upgrade path **for your exact release pair**; never assume 3.x/4.x/5.x behave identically.
5. **Client correctness:** smoke-test the Java Driver using real prepared statements, partition keys, and application CLs rather than just checking if the CQL port responds.
6. **Operational gating:** record baselines, advance through verifiable phases, enforce evidence-based GO/HOLD gates, and keep rollback/recovery plans intact.
7. **User-facing quality:** p50/p95/p99, throughput, timeouts, and error budgets define upgrade success.

The closing question at every step is not **"Is Cassandra running again?"**, but rather **"Do all nodes agree on the right schema, preserve expected topology, keep background tasks within capacity, and let Java clients read/write accurately at the designed consistency level?"** Advance to the next node only when numbers and evidence answer yes.
