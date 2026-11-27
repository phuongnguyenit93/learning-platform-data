# Node States and the Lifecycle of Joining, Leaving, or Being Replaced in Apache Cassandra

## Learning Objectives

After this lesson, you will be able to:

1. Read both dimensions **Status** and **State** of `nodetool status` accurately: `U/D` reflects reachability, while `N/J/L/M` reflects token ring membership state.
2. Distinguish a temporarily unreachable node (`DN`) from a node that has been **decommissioned**, **removed** (`removenode`), or **replaced**; understand why Cassandra does not automatically remove a member from the ring simply because the node is DOWN.
3. Describe the lifecycle of a **newly bootstrapped node**: cluster discovery, receiving tokens/vnodes, streaming token ranges, and transitioning from `UJ` to `UN`.
4. Know when to use `nodetool decommission` for a **live** node, `nodetool removenode` for a **dead** node, and the **replace** procedure to bring a new node into the old node's position.
5. Explain the impact of replication factor (RF), datacenter/rack, streaming, hints, repair, and cleanup on availability and consistency during topology changes.
6. Monitor progress using `nodetool status`, `netstats`, logs, driver metadata, and latency/timeout metrics rather than inferring from a single flag.
7. Design a **runbook with pre/post conditions, stop points, and failure handling plans**, without executing destructive commands in production before verifying the target node and impact scope.
8. Understand how a Java Driver 4.x application reacts to topology changes, connection pools, token-aware routing, and consistency levels.

This lesson belongs to the **Topology Changes** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. The module focuses on the distributed and wide-column architecture of Apache Cassandra: partition keys, query-driven table design, read/write consistency, CQL, replication, compaction, repair, incidents, and Java clients. This lesson covers **node lifecycle management** rather than schema changes or optimizing an individual `SELECT` query.

> **Safety scope:** The topology-changing `nodetool` commands below are **runbook examples for learning and review**, not instructions to run directly against a cluster whose state is unverified. Only operate after obtaining operational authorization, verifying the version, RF/DC, replica health, backup/recoverability, and an approved change procedure.

## 1. The Token Ring and Cluster Membership

### 1.1. From Partition Key to Replicas

In Cassandra:

- A **partition key** is converted by the partitioner into a **token**; the token determines the logical position in the token ring.
- Each node can own **multiple virtual nodes (vnodes)**, i.e., a set of tokens/ranges, depending on `num_tokens` and token allocation.
- The **replication strategy** and RF determine which replicas belong to a token range; across multiple DCs, `NetworkTopologyStrategy` also considers per-DC RF and rack placement.
- A **coordinator** receives the query, determines the appropriate replicas for the partition key and consistency level, and coordinates reads/writes.

Simplified model:

```text
                  Token ring (illustrative)
              +-----------------------+
              |                       |
        Node A (token ranges)    Node B (token ranges)
              |                       |
              +------ Node C ---------+
                     |
                     v
              Replica placement

Partition key (account_id, event_day)
              |
          hash/token
              |
       replicas by RF/DC/rack
              |
       read/write via coordinator
```

Do not equate **"a node owns a token range"** with **"that node is the sole copy of data in that range"**. A range has multiple replicas; a node joining or leaving can cause **replica placement** to change.

### 1.2. Gossip, Failure Detector, and Membership

Cassandra uses an inter-node state exchange mechanism (gossip) and a failure detector to assess reachability. However, there are **two independent questions**:

1. **Is the node reachable?** A node can be seen as Up or Down **from the perspective of the observing node**.
2. **Which stage of the ring lifecycle is the node in?** Joining, Normal, Leaving, Moving, or already removed from membership.

When a node loses connectivity:

```text
Normal + Up = UN
        |
        | missed heartbeats / unreachable
        v
Normal + Down = DN
        |
        +--> recovers to Up/Normal if not removed
        |
        +--> operator decides to replace or removenode
               after confirming the node will truly not return
```

**DN does not mean the node has left the ring.** Cassandra does not permanently redistribute all token ranges just because a node is temporarily DOWN: this avoids unnecessary data movement caused by brief network glitches. Removing or replacing a node is an **explicit operational action**.

**Locality of Up/Down:** Two observing nodes can temporarily see different Up/Down states, especially during a network partition or before gossip has converged. Therefore, do not draw cluster-wide conclusions from `nodetool status` run on a single host when a network incident is suspected.

## 2. Reading nodetool status Correctly

Basic inspection command:

```bash
nodetool status

# Optionally specify a keyspace to view effective ownership according to
# that keyspace's replication, depending on the Cassandra version.
nodetool status app_events
```

**Simulated output** example:

```text
Datacenter: dc1
====================
Status=Up/Down
|/ State=Normal/Leaving/Joining/Moving
--  Address      Load      Tokens  Owns (effective)  Host ID          Rack
UN  10.1.0.11    78 GiB    16      55.0%             <uuid-node-a>    rack1
UN  10.1.0.12    84 GiB    16      50.0%             <uuid-node-b>    rack2
UJ  10.1.0.14    12 GiB    16      ?                 <uuid-node-d>    rack3
DN  10.1.0.13    81 GiB    16      48.0%             <uuid-node-c>    rack3
```

The `10.1.0.x` addresses, percentages, and `<uuid-node-x>` values above are **illustrative**, not output from a live cluster. In real `status` output, column layout and `Owns (effective)` display vary by version and keyspace argument.

### 2.1. How Are the First Two Characters Interpreted?

| Character | Group | Meaning |
| --- | --- | --- |
| `U` | Status | Up: the observing node considers the endpoint reachable. |
| `D` | Status | Down: the observing node considers the endpoint unreachable. |
| `N` | State | Normal: normal member of the ring. |
| `J` | State | Joining: node is joining/bootstrapping. |
| `L` | State | Leaving: node is leaving the ring/decommissioning. |
| `M` | State | Moving: node is moving token position, when supported by the operation/version. |

Common combinations:

| Display | Interpretation | What can be done next? |
| --- | --- | --- |
| `UN` | Up/Normal | Normally expected state of a serving node. |
| `UJ` | Up/Joining | Check streaming/bootstrap; do not treat as finished joining yet. |
| `UL` | Up/Leaving | Decommission is in progress; monitor streams and membership. |
| `UM` | Up/Moving | Token movement is occurring; check version, progress, and purpose. |
| `DN` | Down/Normal | Node is recorded in the ring but unreachable from the current viewpoint. |
| `DJ`/`DL` | Down/Joining or Down/Leaving | Interrupted or unreachable operation; investigate, do not automatically force. |

After **leaving the ring successfully**, the old node typically **no longer appears** as a member in normal output. This is **different** from `DN` — a member that is still present but Down.

### 2.2. Reading the Remaining Columns in Context

- **Address:** internal endpoint; a cluster may use separate ports/broadcast addresses depending on version; do not equate IP address with Host ID.
- **Load:** locally reported data size, not the cluster's unique logical byte count.
- **Tokens:** number of tokens/vnodes held by the node. Do not confuse this with RF or partition count.
- **Owns (effective):** ownership share accounting for replication and keyspace; does not necessarily sum to 100% across all nodes, especially when RF is greater than one.
- **Host ID:** node identifier within the cluster; **different from IP**. Important for `removenode`.
- **Rack/DC:** logical location used for placement and network topology; misconfiguration can affect replica diversity.

**Wrong example:** seeing `DN 10.1.0.13` and immediately running `nodetool removenode 10.1.0.13`. In common versions, `removenode` requires the **Host ID**, not the IP address.

## 3. Lifecycle Diagram: Joining, Normal, Leaving, Dead/Replaced

```text
       Provision new node, clean config
                  |
                  v
             Joining (UJ)
          select tokens, streaming
                  |
          bootstrap completes
                  v
             Normal (UN)
              /      \
             /        \ unreachable
            /          v
     decommission    Down/Normal (DN)
          |               |
          v               +--> recovers --> UN
     Leaving (UL)         |
          |               +--> replace dead node
          |               |        |
          v               |        v
   Leaves membership      |    new node streams
   (row disappears)       |        |
                          |        v
                          |       UN
                          |
                          +--> removenode from live node
                                   |
                                   v
                          remove dead member from ring
```

This is a **logical diagram**; it does not promise that every version displays all intermediate states at all times. A replace operation has phases where `status` on other nodes may temporarily show `DN`; `nodetool netstats` and logs on the replacement node are key progress sources.

### 3.1. Non-Synonymous Operations

| Action | Target Node | Purpose | Changes membership/token placement? |
| --- | --- | --- | --- |
| Restart Cassandra | Existing node | Restart the service | Normally **no**, if configuration/identity remain intact. |
| `nodetool drain` | Running node | Flush/prepare for controlled stop | **Not a decommission**. |
| Bootstrap | **New** node | Join the ring and receive ranges | **Yes**. |
| `nodetool decommission` | **Live** node | Permanently leave cluster, stream data | **Yes**. |
| `nodetool removenode <host-id>` | **Dead** node | Remove dead node membership, re-replicate from live nodes | **Yes**. |
| Replace node | New node replacing **dead** node | Take over dead node's position/tokens and stream data | **Yes**, to replace that position. |
| `nodetool cleanup` | Nodes still holding data outside new ownership | Delete local data no longer owned after safety verification | **Does not change membership**. |
| `nodetool repair` | Nodes/replicas per repair scope | Synchronize data across replicas | **Does not add/remove nodes itself**. |

A node that is DOWN for a few minutes of maintenance does not become a "removed" node just because the operator stopped Cassandra. If you intend to restart it, **do not run decommission/removenode/replace**.

## 4. Safety Before Any Topology Change

### 4.1. Operational Preflight

Before adding/removing/replacing a node, verify:

1. **Correct cluster:** cluster name, environment, datacenter, rack, endpoints; never operate on lab/staging/production by mistake.
2. **Correct node:** address **and** Host ID, node role, whether the node is actually alive or unreachable?
3. **Version/compatibility:** Cassandra version, node replacement method, and exact supported flags/`nodetool` commands.
4. **Replication:** what strategy each keyspace uses, RF per DC, and whether enough live replicas remain to satisfy consistency and streaming?
5. **Capacity:** free disk, memory, CPU, network, and headroom on nodes that will receive additional ranges.
6. **Cluster health:** are any other nodes DOWN, or are long-running repairs/compactions/streaming or large pending tasks active?
7. **Recoverability:** snapshots/backups, restore runbook, monitoring, rollback/forward recovery, and approver.
8. **Application:** do read/write p95/p99, timeouts, retries, QPS, and connection pools have budget to absorb data movement?
9. **Ordering:** perform only **one related topology operation at a time** unless using a proven orchestration mechanism; avoid concurrent range movements that leave replicas short of data.

Common inspection commands:

```bash
# READ-ONLY: run on an appropriate node with JMX permissions.
nodetool status
nodetool describecluster
nodetool netstats
nodetool tpstats
nodetool compactionstats

# Token/rack/host ID inspection depending on version:
nodetool ring
nodetool gossipinfo
```

In environments with secured JMX, `nodetool` requires host/port/credential details. Do not pass passwords directly on the command line when your governance process provides a password file or secret manager. Do not store stdout containing internal addresses/Host IDs in public log repositories.

### 4.2. Capacity and RF Are Critical Guardrails

Suppose DC `dc1` has only **three nodes** and a keyspace sets `RF=3`. If you permanently decommission one node without adding capacity, the DC is left with two physical nodes; it cannot maintain three distinct replicas for each partition. `nodetool decommission` in modern versions may refuse and offers a `--force` option, but **forcing a removal does not create a third replica**.

Rule: **ensure RF remains achievable after the topology change**, or change RF via a controlled data plan. Never use `--force` to bypass a data-safety invariant.

### 4.3. Metadata and Ownership May Not Converge Instantly

While a node is Joining/Leaving, other nodes or the Java client may not observe the exact same state at the exact same millisecond. Diagnostic commands should be run from **multiple observing nodes** when gossip/network anomalies are suspected; also check logs and stream progress on the target node.

Do not set up automation like "see `UN` once, immediately run cleanup and close the ticket". You must verify **streaming completion**, stable availability, read/write errors within thresholds, and proper replica coverage.

## 5. Adding a New Node: Bootstrap and UJ → UN Transition

### 5.1. When Do You Need to Add a Node?

- Disk usage or throughput is approaching safe limits.
- Additional read/write load distribution or expansion of an existing DC is needed.
- Adding capacity ahead of a controlled decommission of an old node.

Adding a node **does not immediately fix an extremely large hot partition** if the application's partition key concentrates data. A single partition is still placed on replicas according to its token; scaling out may not split that partition itself.

### 5.2. Configuration to Prepare

A new node needs values matching the actual cluster, for example:

```yaml
# THIS IS AN ILLUSTRATIVE SNIPPET, NOT a complete cassandra.yaml.
cluster_name: 'orders-prod'            # must match existing cluster name
listen_address: 10.1.0.14              # actual internal endpoint of new node
rpc_address: 0.0.0.0                   # requires firewall and broadcast_rpc_address control
num_tokens: 16                         # example; choose per actual strategy/version
seed_provider:
  - class_name: org.apache.cassandra.locator.SimpleSeedProvider
    parameters:
      - seeds: "10.1.0.11,10.1.0.12"
endpoint_snitch: GossipingPropertyFileSnitch
```

The example above is **for comprehension only**; do not copy verbatim into production. Properly configure `broadcast_address`, `broadcast_rpc_address`, DC/rack, TLS, authentication, encryption, ports, data/commitlog/cache paths, JVM, and network policies according to your distribution.

Points to distinguish:

- **Seed nodes** help **discover** the cluster at startup; they are not "masters" and are not automatically the sole replicas for all tokens.
- **Datacenter/rack** must be accurate so the replication strategy places replicas according to topology; fixing a wrong snitch/DC after a node already holds data is a separate, risky procedure.
- **`num_tokens`** controls the node's vnode count, not the replication factor. Optimal values/allocators depend on version and workload; do not assume all clusters must use 256 tokens.
- A new node normally needs a **clean data directory and a new identity**. Never copy `system` keyspace/Host ID from another node, to avoid two nodes sharing the same identity.
- Do not casually set `auto_bootstrap: false` to skip streaming; that is a specialized mode used only in specific recovery/initialization runbooks.

### 5.3. Bootstrap Progression

```text
New node prepares clean configuration / storage
            |
            v
Connects to seeds/gossip, learns topology/ring
            |
            v
Selects tokens/vnodes and newly assigned ranges
            |
            v
Joining (UJ): receives SSTable ranges via streaming
            |
            v
Completes streaming, updates ownership/replica placement
            |
            v
Up/Normal (UN), verify stability
```

Monitoring:

```bash
# On the new node or an appropriate admin node:
nodetool status
nodetool netstats

# Auxiliary inspection commands for investigating load:
nodetool tpstats
nodetool compactionstats
```

`netstats` is a key source of information about active streaming sessions. `status` shows membership state, but does not necessarily show full bootstrap/replace progress. In logs, look for handshake errors, gossip issues, schema agreement problems, streaming failures, disk exhaustion, or endpoint/DC mismatches.

### 5.4. After the Node Reaches UN

Consider bootstrap complete only after:

1. `nodetool status` from multiple vantage points shows the new node stably `UN`.
2. `nodetool netstats` has no remaining in-progress transfers for this operation.
3. Replica placement, RF/DC/rack, and target keyspaces match expectations.
4. Controlled test reads/writes at appropriate consistency succeed.
5. Latency, timeouts, unavailables, pending tasks, and disk load are within acceptable bounds.

After **range movement completes and is verified**, some older nodes may still hold local data for ranges they no longer own. At that point the operator can schedule `nodetool cleanup` on **the nodes that lost ownership of ranges**, per version guidance. **Do not run cleanup while bootstrap is incomplete or coverage is unverified**, and do not treat cleanup as an unconditional automatic step on every node.

### 5.5. Failed or Interrupted Bootstrap

If `UJ` drags on, do not immediately wipe the data directory or start a second bootstrap:

- Check `netstats`, logs, disk, network, stream sources, and any DOWN nodes.
- Check version documentation: `nodetool bootstrap resume` may support resuming streaming.
- For an incomplete bootstrap state, `cassandra.reset_bootstrap_progress` has dangerous semantics if previously streamed data remains on disk; do not toggle `true`/`false` by guesswork.
- Do not disable consistent range movement just to "make it keep running" without assessing the risk of missing data.

**Bootstrap recovery runbooks must match the Cassandra version in use**, ideally tested on staging with representative data before applying in production.

## 6. Removing a Live Node: Decommission and UL

### 6.1. When to Use Decommission?

`nodetool decommission` is for a **running node capable of participating in streaming**, when the operator wants to **permanently** remove that node from the ring, for example:

- Shrinking the cluster while **still keeping enough nodes for RF** of every keyspace.
- Planned hardware replacement via an "add new node first, remove old node later" pattern.
- Retiring an unneeded node after ensuring data already has target replicas.

Do not use it to "restart the service cleanly" or for "a two-minute maintenance window".

### 6.2. Logical Workflow

```text
Before: Node A UN, Node B UN, Node C UN, Node D UN
                    |
          verify capacity/RF/health
                    |
             decommission Node D
                    |
             Node D transitions to UL
                    |
          stream data from Node D per new ownership
                    |
          complete, leaves token ring
                    |
          Node D is no longer in membership
```

Command **for illustration only**:

```bash
# DANGEROUS: modifies membership and data.
# Run ONLY on the EXACT live node to be removed (or target with -h),
# after confirming RF/capacity, backups, and approval.
nodetool decommission

# Observe from REMAINING nodes:
nodetool status
nodetool netstats
```

If using `nodetool -h <host> decommission`, `<host>` is **the node to be decommissioned**, not an "arbitrary coordinator". Carefully verify the JMX target before running.

### 6.3. What Changes?

- The leaving node may show `UL`.
- Required data is streamed from the leaving node to the newly responsible nodes.
- Upon success, that node is **no longer in the ring**.
- **Local data is not automatically wiped completely** after decommission; do not rejoin with the same old data/identity by arbitrarily starting the service again.
- RF and remaining node count determine whether the cluster can maintain the desired number of replicas.

If you need to repurpose the old node as a fresh node later, disk/config reuse procedures must be standardized; never assume "service stopped = clean new node".

### 6.4. When Decommission Gets Stuck

Before forcing or aborting, check:

1. Are streaming sources and targets reachable, and do they have enough disk/network?
2. Is another node DOWN, preventing range transfer from completing?
3. Do target replicas have enough space; does RF exceed the remaining node count?
4. What errors are in the logs? What remaining transfers or failed sessions appear in `nodetool netstats`?
5. Is the application generating heavy load, starving data movement of bandwidth?

**Do not use `nodetool decommission --force` as a default workaround.** In some versions, `--force` allows proceeding even when replica count falls below configured RF; it is a **safety-reducing** option, not a fix for load or insufficient nodes.

## 7. Node DOWN: Recover, Replace, or Remove?

### 7.1. DN Is a Symptom to Investigate, Not Yet a Decision

```text
nodetool status from Node A:

DN  10.1.0.13  ...  <host-id-C>  rack3
```

First distinguish:

- **Temporary network / JMX / process loss:** the node can return with its existing data/Host ID, requiring no membership change.
- **Permanent host/disk loss:** requires replacement or removal to restore placement.
- **Network partition:** some nodes see Down, others see Up; mistakenly removing a live node can cause conflicts or data loss.
- **Planned node stop:** check the maintenance runbook; do not self-diagnose as "permanently dead".

### 7.2. Decision Matrix

| Situation | Typical Approach | Mandatory Conditions |
| --- | --- | --- |
| Brief shutdown/restart, data intact | **Restore old node** | Valid identity and storage; gossip/replicas verified. |
| Want to retire an **Up** node permanently | **Decommission** | Sufficient RF/capacity, streaming completes. |
| Node **permanently dead**, want a new machine in old node's position | **Replace** | Old node no longer running, sufficient stream sources, version-correct config/flags. |
| Node **permanently dead**, not directly replacing that position | **Removenode** | Enough live replicas to re-replicate, accurate Host ID, monitoring in place. |
| Node Down due to split-brain, unclear which side is alive | **Halt topology decisions**, investigate | Do not remove/replace while risk of old node returning exists. |
| Data lost and only remaining replica is Down | **Recovery/backup procedure**, do not force removal | Assess risk of losing the last copy. |

Choosing replace vs. removenode depends on the final topology goal, capacity, outage duration, and consistency requirements. **Do not casually combine both operations for the same node.**

## 8. Removing a Dead Node with removenode

### 8.1. How Does It Differ from Decommission?

With `decommission`, the **leaving node is alive** and participates in sending data. With `removenode`, the **dead node cannot stream**; Cassandra must use surviving replicas to restore data and update membership.

Before invoking removenode:

- Confirm the target node is truly unrecoverable.
- Record the exact **Host ID** from `nodetool status` and cross-check on multiple nodes.
- Verify other replicas have sufficient data/health to re-replicate.
- Budget for disk/network usage and the consistency impact of losing a replica.
- Confirm **no replacement operation for the same Host ID/token location is running**.

### 8.2. Runbook Example — Do Not Execute on a Live Cluster

```bash
# READ: run from a live node with admin privileges.
nodetool status

# DANGEROUS: removes a dead member from the ring.
# Replace the placeholder with the REAL Host ID of the dead node.
nodetool removenode 00000000-0000-4000-8000-0000000000cc

# Monitor removal/streaming progress:
nodetool removenode status
nodetool netstats
nodetool status
```

The UUID in the command above is **fictional**, not corresponding to any cluster node. `removenode status` and `removenode force` syntax depend on version but are documented in current official releases.

### 8.3. Risks of Forcing or Using the Wrong Host ID

If the dead node held updates that had not yet reached surviving replicas, removing it can leave data missing. In some versions, `removenode force` forcibly terminates the removal process **without** guaranteeing that sufficient data has been re-replicated.

**Do not use `nodetool assassinate` as a "fast removenode".** It is a last-resort option that can erase membership **without re-replicating**, appropriate only in emergency procedures with data-loss assessment and special approval.

If the old node is accidentally powered back on **after being removed**, do not reconnect it to the cluster as a normal node with its old metadata. Follow version-appropriate isolation/recovery procedures and verify Host ID/token ownership.

## 9. Replacing a Dead Node with a New Node

### 9.1. What Is Replacement?

**Replace** is not synonymous with adding an arbitrary node and deleting the old one. In the typical case, the new node is configured to **take over the dead node's position/token ranges** and stream the necessary data from other replicas.

Scenario:

```text
Before:
   Node A UN
   Node B UN
   Node C DN   <-- machine C is permanently lost

Replacement:
   Verify C is truly offline
   Prepare machine D with a clean data directory
   D starts with replacement address = C
   D bootstraps data from A/B per ownership
   Monitor netstats / logs / gossip

After:
   Node A UN
   Node B UN
   Node D UN   <-- C's position replaced per version semantics
   C must never be allowed to start back into the cluster
```

### 9.2. Version-Specific Flags and Configuration

In Apache Cassandra 4.x/5.x topology changes documentation, the typical method is starting the **new node** with the JVM system property:

```text
-Dcassandra.replace_address_first_boot=<dead_node_ip>
```

Replace `<dead_node_ip>` with the **actual address of the dead node** per version/config semantics. This is a Cassandra **startup parameter**, not a CQL statement and not a command run on a live node.

Some configuration docs also describe `cassandra.replace_address`; exact usage depends on the Cassandra release. **Do not swap the two flag names by guesswork**: verify the release/config and runbook in use before starting.

**Minimum preconditions:**

1. Node C is truly dead and can never run concurrently with D.
2. D has environment/config matching the cluster, datacenter/rack, seeds, and storage **meeting new-node standards**.
3. D does not carelessly reuse `system` data/Host ID from another node.
4. Surviving replicas can supply data for streaming.
5. A data reconciliation and repair plan exists if the node-loss window was prolonged.

### 9.3. Replacement May Appear as DN During One Phase

Per Cassandra operational documentation, a replacing node can start in **hibernate** state; other nodes see the associated endpoint as Down/Normal for a period while the new node sees itself as Up. Therefore:

- Do not assume replacement is "stuck" solely from one `DN` line in `status` on another node.
- Check `nodetool netstats` on the replacing node to observe streaming progress.
- Check logs, traffic, and incoming token ranges.
- Mark complete only when bootstrap finishes and membership/traffic stabilize.

### 9.4. Same IP vs. Different IP Carry Different Risks

Per topology documentation:

- A node replacing with a **different IP** may receive writes during the bootstrap phase depending on version conditions.
- When **reusing the old IP**, write reception behavior during replacement differs; a prolonged downtime window increases the risk of missed writes.
- If the node was dead longer than the hints window (`max_hint_window` or corresponding version config name) or same-IP replacement exceeded that window, documentation requires **repair** to recover missed writes.

Therefore you must track **when the old node died, when replacement completed, how long hints are retained, and repair status**. Never conclude "reaching UN means data is definitely complete" in every case.

### 9.5. Post-Replacement

Checklist:

1. Node D is stably `UN` when observed from multiple nodes.
2. `netstats` shows no pending replacement streaming.
3. Verify RF/replica placement in target keyspaces and DC/rack.
4. Run **repair per runbook** if conditions for missed writes/hints existed or data convergence is uncertain; do not use repair as a fix for arbitrary config issues.
5. Verify reads/writes using application prepared queries/consistency along with latency/timeout metrics.
6. Only then consider cleanup on nodes that lost ranges due to movement, if applicable.
7. Ensure the **old node cannot restart** with conflicting identity/address.

## 10. Streaming, Hints, Repair, and Cleanup: Four Distinct Things

### 10.1. Streaming Transfers Range Data

Bootstrap, decommission, replacement, and removal can initiate **streaming** of SSTable ranges to place data on the newly responsible replicas.

```text
Old replica(s)                  New responsible replica
      |                                  |
      |---- stream token ranges -------->|
      |                                  |
      |    update ownership/membership   |
      |--------------------------------->|
```

Streaming can affect network, disk, compaction/flush, and client latency. Stream duration does not depend solely on theoretical GB count: tombstones, SSTable fragmentation, checksum/transfer errors, scheduling, and slow nodes can all skew progress.

### 10.2. Hints Do Not Replace Repair

On certain write paths, Cassandra stores **hints** for a temporarily unavailable replica and attempts redelivery within a configured window. Hints:

- Assist in certain short-term replica outage scenarios.
- Are not a permanent changelog or a guarantee of retaining **every** write across any outage duration.
- Do not replace repair after prolonged downtime or a replacement with risk of missed writes.

If the operator does not know the downtime/hints window, they should not mark a replacement consistent based solely on `nodetool status`.

### 10.3. Repair Reconciles Replicas, Not Membership

Repair detects and synchronizes data discrepancies across replicas per scope/version. Conceptual command example:

```bash
# Can be very I/O- and network-intensive; run per schedule/runbook,
# do not run cluster-wide automatically after every event.
nodetool repair <keyspace>
```

You must define the keyspace, incremental/full repair, DC scope, concurrency, and version compatibility. Do not claim "running repair on one node suffices for the entire cluster" without a concrete coverage plan.

### 10.4. Cleanup Reclaims Data Outside Current Ownership

After a successful movement, nodes that **lost** ranges may still hold SSTables containing data from those ranges. `cleanup` removes data no longer owned by the node:

```bash
# Run ONLY AFTER placement/movement completion is confirmed.
# Run on target nodes requiring cleanup per plan; I/O-intensive.
nodetool cleanup <keyspace>
```

Never run cleanup while bootstrap/replace/decommission is unstable, and never treat cleanup as synonymous with repair. Deleting needed data prematurely before placement is safe can cause severe consequences.

## 11. Danger Zone: Actions Never to Take Reflexively

| Situation | Dangerous Reflex | Why |
| --- | --- | --- |
| A node shows `DN` for a few minutes | Immediate `removenode` | May just be a network blip; removes membership when the node could recover. |
| New node bootstraps slowly | Wipe data directory and restart | Can lose progress/data and create dangerous partial bootstrap state. |
| 2 nodes left with `RF=3` | Decommission third node with `--force` | Cannot maintain three distinct replicas, increasing data loss risk. |
| Node replacement still running | Boot the old node back up | Risk of ownership/identity conflict and inconsistency. |
| Host ID unknown | Pass IP as argument to `removenode` | Wrong command semantics; risks targeting wrong node. |
| Data just finished streaming | Immediately cleanup everything | Replica sufficiency and range ownership not yet verified. |
| Hints window expired | Assume new UN node has all writes | Missed writes require reconciliation/repair. |
| Single trace/status from one node | Conclude cluster-wide agreement | Up/Down is a local assessment; gossip may not have converged. |
| Bootstrap/decommission in progress | Start unrelated movements arbitrarily | Multiple concurrent movements overload cluster and endanger replica coverage. |
| Application queries time out | Only increase timeouts/retries | If streaming/cluster is overloaded, retries amplify load. |

**Operational stop point:** whenever you cannot verify "old node is truly dead", "RF is sufficient", "streaming has intact sources", or "backup/restore is tested", **halt destructive actions** and investigate/escalate to incident procedures.

## 12. Observing Topology Changes: A Minimum Dashboard

### 12.1. Observation Tools

| Tool | Questions It Answers |
| --- | --- |
| `nodetool status` | Node Up/Down, Joining/Normal/Leaving; Host ID, rack/DC? |
| `nodetool netstats` | Streaming ranges being sent/received, progress, and network work? |
| `nodetool describecluster` | Cluster name, schema versions, metadata overview? |
| `nodetool gossipinfo` | Gossip application states across endpoints? |
| `nodetool ring` | Token placement/ownership from the tool's perspective? |
| `nodetool tpstats` | Pending/blocked work across thread pools? |
| `nodetool compactionstats` | What compaction is doing; is there a large backlog? |
| Cassandra system/debug logs | Bootstrap/streaming errors, gossip, seed, disk, schema, transport issues? |
| Client + server metrics | p95/p99 latency, retries, timeouts, unavailable, pending reads/writes? |

**Non-destructive observation practice example:**

```bash
# Run from an appropriate node with JMX and log access.
nodetool status
nodetool netstats
nodetool describecluster
nodetool tpstats
```

Repeat observations at intervals during the process rather than taking a single `status` snapshot. When nodes disagree on Up/Down, inspect DNS/broadcast address, firewalls, internode TLS, ports, clocks, and logs instead of forcing membership.

### 12.2. Progress Tracking Table Example

| Time | Node | Status/State | Streaming | API p99 | Decision |
| --- | --- | --- | --- | --- | --- |
| T0 | D | Not yet in ring | Not running | Baseline | Approve preparation |
| T1 | D | `UJ` | Receiving | Monitoring | Continue monitoring |
| T2 | D | `UN` | Completed | Within threshold | Begin verification |
| T3 | D | Stable `UN` | No pending work | Within threshold | Close change / conditional cleanup |

T0–T3 are **logical milestones**, not fixed durations; do not fabricate stream speeds or SLAs from token count. A node receiving a few GB and a node receiving terabytes have vastly different time and resource requirements.

### 12.3. Thresholds and Rollback/Forward Recovery

Before starting, define:

- Application p95/p99, read/write timeout, and unavailable thresholds.
- Safe free disk space and maximum streaming throughput.
- Concurrency limits for bootstrap/repair/cleanup; plan to shed read/write load if retry storms occur.
- **Pause**/stop criteria before irreversible steps.
- **Forward recovery** plan once decommission/removenode has updated membership: do not assume you can "undo" like a SQL transaction.

**Some topology commands have no single-step rollback.** Recovery may require a new bootstrap/replacement or restoring from backup, not just restarting the old node.

## 13. Impact on Java Driver and In-Flight Queries

### 13.1. The Driver Observes Topology, It Does Not Decide for the Operator

Java Driver 4.x maintains node metadata and topology discovery. When a node is joining/leaving or goes down:

- The driver can update topology and connection pools based on events from Cassandra.
- Token-aware routing locates replicas for a partition key when metadata is complete.
- In-flight requests may hit timeouts or `Unavailable` if replicas or coordinators change availability.
- Prepared statements and metadata may need refreshing per driver mechanisms; the application must not manage the cluster by trying to hit a single hardcoded IP.

However, **driver metadata is not the authoritative source for issuing `removenode`/`decommission`.** Operators still must inspect Cassandra's ring/streaming/Host IDs with operational tools.

### 13.2. Java Example: Inspecting Node Metadata

**Java 17 + Apache Cassandra Java Driver 4.x** example:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.metadata.Node;
import java.net.InetSocketAddress;

// Illustrative connection example, not a complete production configuration.
try (CqlSession session = CqlSession.builder()
        .addContactPoint(new InetSocketAddress("10.1.0.11", 9042))
        .withLocalDatacenter("dc1")
        .build()) {

    // Driver metadata may update asynchronously after topology changes.
    for (Node node : session.getMetadata().getNodes().values()) {
        System.out.printf(
            "id=%s dc=%s rack=%s state=%s endpoint=%s%n",
            node.getHostId(),
            node.getDatacenter(),
            node.getRack(),
            node.getState(),
            node.getEndPoint());
    }
}
```

**Note:** The driver's `NodeState` (e.g., Up/Down/Unknown) is not the two-character `UN/UJ/UL` combination from `nodetool status`. Never use `node.getState()` to infer that bootstrap is complete and directly drive topology changes.

Production requires multiple contact points, TLS/authentication, retry policies, timeouts, and topology-aware monitoring; the code snippet above only illustrates reading metadata.

### 13.3. Java Query Example During Node Transitions

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.LocalDate;
import java.util.UUID;

// Assumes an active valid session and keyspace "app_events".
PreparedStatement query = session.prepare("""
    SELECT occurred_at, event_id, event_type
    FROM events_by_account_day
    WHERE account_id = ? AND event_day = ?
    """);

BoundStatement bound = query.bind(
    UUID.fromString("11111111-1111-4111-8111-111111111111"),
    LocalDate.parse("2026-11-20")
).setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
 .setIdempotent(true);

Row first = session.execute(bound).one();
if (first != null) {
    System.out.println(first.getUuid("event_id"));
}
```

This snippet illustrates a prepared SELECT by **full partition key**. There is no guarantee `LOCAL_QUORUM` will remain available if RF/DC and live replica count fail to satisfy the requirement. `setIdempotent(true)` informs the retry policy of the query's nature; it does **not** permit infinite retries or turn an entire sequence of reads into a transaction.

On a cluster with RF=3 in the queried DC, `LOCAL_QUORUM` typically requires **2 replicas** to respond appropriately; if only one replica is alive, requests may fail with `Unavailable`. During replacement/bootstrap, consistency level and replica health can affect latency; do not arbitrarily downgrade consistency just to silence errors without understanding data requirements.

### 13.4. What Applications Should Monitor

| Application Signal | What May Happen During Topology Change | How to Respond |
| --- | --- | --- |
| Read/write p99 spikes | Streaming competes for disk/network, or coordinator/replicas are loaded | Reduce batch concurrency, monitor, adjust change schedule. |
| `Unavailable` | Insufficient replicas to satisfy consistency | Check RF, node health; do not blindly retry. |
| `ReadTimeout`/`WriteTimeout` | Slow/congested replicas or active movement | Bounded backoff; avoid retry storms. |
| Prepared query on keyspace fails | Unconverged schema agreement/config or query error | Inspect schema/driver; do not assume bootstrap fixes it automatically. |
| Driver sees newly appeared node | Discovery/metadata updated | Verify node is truly `UN` via nodetool/netstats. |
| Errors affect one tenant/hot partition | A specific token/range is impacted | Use partition key, token routing, and metrics to scope impact. |

Never hardcode a single endpoint as a "master node" for the application: Cassandra has no single-master node in that sense. Also never invoke `nodetool` from an application HTTP request to "heal" a down node.

## 14. Scenario Practice: Read First, Decide Later

### Scenario A — Seeing DN During Planned Maintenance

**Context:** `nodetool status` shows one node `DN`, while the ops team reports a service restart is underway.

**Reasoning steps:**

1. Verify the maintenance change is registered and whether the node is restarting.
2. Check `status` from a couple of other nodes; inspect gossip, network, and logs.
3. Monitor the node returning to `UN` and reads/writes recovering at application consistency.
4. **Do not** run `decommission` or `removenode` for a planned restart.

**Correct outcome:** DN can be a transient event; membership does not necessarily change.

### Scenario B — Need to Add a Node Due to High Disk Usage

**Context:** A DC still satisfies RF, all nodes `UN`, capacity expansion needed.

**Reasoning steps:**

1. Size capacity, rack/DC placement, vnode selection, and new node config.
2. Start a clean node with normal bootstrap; monitor `UJ`, `netstats`, and logs.
3. Once `UN`, verify replica placement, read/write metrics, and consistency.
4. Schedule **conditional** cleanup on nodes holding leftover ranges.
5. Monitor post-change, record the new Host ID, and update version/topology baseline.

**Stop point:** a source replica becomes unavailable, streaming stalls, or target disk lacks space.

### Scenario C — Retiring a Live Node

**Context:** Four nodes in a DC with a keyspace at RF=3; want to scale down to three nodes.

**Reasoning steps:**

1. Verify every keyspace/DC still has at least three nodes and sufficient capacity after removal.
2. Verify target node is `UN` and the cluster has no concurrent/abnormal movements.
3. Only on the target node, run decommission per runbook.
4. Monitor `UL`, `netstats`, errors/latency, and membership state.
5. Once complete, the departed node is absent from `status`; handle local data per policy.

**Stop point:** decommission causes replica deficit, stream failures, or lack of recoverability.

### Scenario D — Permanently Dead Node

**Context:** Server and storage of node C failed and cannot be powered back on.

**Reasoning steps:**

1. Verify identity, isolate node C, record outage start time, RF/consistency, and hints window.
2. Choose **replace** if you want capacity in the old position; **removenode** if you want to drop membership and redistribute across surviving replicas.
3. Execute only **one** approved path; monitor streaming and data scope.
4. After completion, verify replica placement/repair as needed and test the application.

**Stop point:** insufficient live replicas as sources, or uncertainty whether node C might come back.

## 15. Exercises and Solutions

### Exercise 1. Distinguish UN, UJ, UL, and DN

**Prompt:** A sample status shows:

```text
UN  10.1.0.11
UJ  10.1.0.14
UL  10.1.0.12
DN  10.1.0.13
```

Explain the four lines and state which line **proves the node has completely left the ring**.

**Answer:** `UN` Up/Normal; `UJ` Up/Joining; `UL` Up/Leaving; `DN` Down/Normal. **None of the lines** prove the node has completely left the ring; once membership has been removed, the old node no longer appears as a member in normal status output.

### Exercise 2. Is a Down Node Automatically Removed?

**Prompt:** A node is Down for 10 minutes due to a network fault and then reconnects. Must Cassandra re-bootstrap a brand-new node?

**Answer:** **No.** The failure detector evaluates reachability and does not automatically remove membership for a brief outage. If the old node and its data/identity remain valid, it can recover to `UN`. Remove/replace is done only when the operator confirms appropriate conditions.

### Exercise 3. RF=3 Across Three Nodes

**Prompt:** A `NetworkTopologyStrategy` keyspace has DC `dc1` with RF=3 and exactly three nodes. You want to decommission one node without adding another. Is it safe for keeping three replicas?

**Answer:** **No**: with two physical nodes left in the DC, it is impossible to maintain three distinct replicas. You must add capacity or alter the RF design via a proper process; `--force` does not conjure extra replicas.

### Exercise 4. Choosing the Right Tool

**Prompt:** Match each scenario to the command/procedure:

1. Healthy node being permanently retired.
2. Dead node, want to remove membership, no replacement machine for that position.
3. Dead node, new machine ready to take over.
4. Node just went unreachable due to a planned restart.

**Answer:** (1) `decommission`; (2) `removenode <host-id>` after checking source replicas; (3) **replace** using the version-appropriate startup flag/runbook; (4) monitor the **restart**, do not remove membership.

### Exercise 5. Does Host ID Equal IP?

**Prompt:** An operator sees a dead node with `Address=10.1.0.13` and `Host ID=1234...`. Which value does `removenode` require?

**Answer:** The full **Host ID** provided by `nodetool status`. IP is only an endpoint, not a Host ID, and should not be substituted. Verify identity from multiple nodes if a network partition is suspected.

### Exercise 6. New Node Stuck in UJ for Hours

**Prompt:** Should you immediately set `auto_bootstrap: false` and restart so it becomes UN faster?

**Answer:** **No.** Skipping bootstrap can leave the node missing data for its assigned ranges. Check `netstats`/logs, stream sources, disk/network, RF, and version; handle resume/recovery per runbook.

### Exercise 7. When to Run Cleanup?

**Prompt:** A new node was just added and shows `UJ`. To reclaim disk on old nodes, can you call `nodetool cleanup` right away?

**Answer:** **No.** Wait until movement/streaming finishes, verify the new node is `UN` and replica placement is safe. Run cleanup only on appropriate nodes/ranges per plan, with I/O monitoring.

### Exercise 8. Repair After Replace

**Prompt:** A node was dead longer than the hints window, and the replacement has reached UN. Can you conclude data is always complete?

**Answer:** **No.** Per topology guidelines, an outage exceeding the hints window may leave missed writes; run repair/reconciliation per runbook and verify consistency. `UN` reflects node state, not a guarantee that all replicas hold identical cells.

### Exercise 9. Losing One Node with LOCAL_QUORUM

**Prompt:** RF=3 in one DC; one node is Down, two nodes remain Up. In terms of replica count, how many responses does `LOCAL_QUORUM` typically require?

**Answer:** Typically `floor(3/2)+1 = 2` replicas. If the two appropriate replicas are alive and responsive, the request has a **chance** to succeed, though it still depends on token/placement, network, and timeouts. Seeing a node Up in status does not prove every query will succeed.

### Exercise 10. Why Do Two Nodes Show Different Status?

**Prompt:** Node A sees Node C as DN; Node B sees Node C as UN. Should you run removenode immediately from A?

**Answer:** **No.** Up/Down is a local assessment; investigate network, gossip, and logs to verify whether Node C is genuinely alive or partitioned before removing it. Mistakenly removing a node can destabilize data/ownership.

### Exercise 11. Java Driver Reports Timeouts During Bootstrap

**Prompt:** While adding a node, p99 increases and Java sees some `ReadTimeout` errors. Should you enable unlimited retries and maximize page size?

**Answer:** **No.** Streaming may be competing for I/O/network; unlimited retries amplify load. Use bounded retry/backoff, monitor consistency/replicas, and tune concurrency/throttling of topology operations.

### Exercise 12. Decommission or Drain?

**Prompt:** You need to shut down a node to upgrade RAM and will restart it with the same disks/config. Should you call `nodetool decommission` or a controlled stop procedure?

**Answer:** A **controlled stop/restart** procedure is appropriate; `nodetool drain` may be a step in the shutdown runbook. **Do not decommission**, because it removes membership and transfers data, defeating the purpose of temporary maintenance.

## 16. Implementation and Post-Verification Checklist

### Before Changing Topology

- [ ] Verified cluster, environment, DC/rack, version, node address **and Host ID**.
- [ ] Cross-checked `nodetool status` from multiple vantage points if anomalies exist.
- [ ] Confirmed exact objective: **add**, **restart**, **decommission**, **replace**, or **removenode**.
- [ ] Ensured RF/keyspace/DC, sufficient live replicas, and free capacity after the change.
- [ ] Prepared backup/restore, runbook, change window, stop points, owner, and incident contacts.
- [ ] Verified no concurrent unexpected streaming/movement/repair is running.
- [ ] Measured baseline p95/p99, timeouts, disk/network, and client retry rate.

### During the Change

- [ ] Monitor `status`, `netstats`, logs, compaction/threads, and data movement.
- [ ] Do not confuse `UJ`/`UL` with `UN`, nor `DN` with a node that left the ring.
- [ ] Do not run `--force`/`assassinate`/`auto_bootstrap: false` just to "go faster".
- [ ] Do not restart the dead node after replacement has taken over without an isolation plan.
- [ ] Control concurrency, traffic, retries, and stop points if errors rise.

### After the Change

- [ ] Membership/tokens/DC/rack are accurate; no unexpected old node appears.
- [ ] New/replacement node is stably `UN`; `netstats` has no incomplete streaming.
- [ ] Replica placement and consistency on critical keyspaces are verified.
- [ ] Determined whether **repair** is needed due to outage/hints gap.
- [ ] **Cleanup** is scheduled only after ownership and data are safe.
- [ ] Java APIs, prepared queries, test reads/writes, p95/p99, and error rates meet acceptance criteria.
- [ ] Updated node inventory, Host IDs, topology baseline, logs, and change completion record.

**Remember:** `Up/Down` answers "is the node currently reachable?", while `Normal/Joining/Leaving/Moving` answers "which stage of the ring lifecycle is the node in?". **A DOWN node is not automatically removed.** Adding a node requires bootstrap/streaming; retiring a live node uses decommission; a dead node requires deciding between replace and removenode based on replica coverage. Every topology change must be verified via **membership, streaming, replication/consistency, and application metrics**, not a single `UN` line.

## References

- [Apache Cassandra — Adding, replacing, moving and removing nodes](https://cassandra.apache.org/doc/latest/cassandra/managing/operating/topo_changes.html)
- [Apache Cassandra — Use Nodetool: status, gossip and diagnostic commands](https://cassandra.apache.org/doc/latest/cassandra/troubleshooting/use_nodetool.html)
- [Apache Cassandra — nodetool status](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/status.html)
- [Apache Cassandra — nodetool netstats](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/netstats.html)
- [Apache Cassandra — nodetool decommission](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/decommission.html)
- [Apache Cassandra — nodetool removenode](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/removenode.html)
- [Apache Cassandra — nodetool cleanup](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/cleanup.html)
- [Apache Cassandra — nodetool bootstrap: resume](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/bootstrap.html)
- [Apache Cassandra — Architecture: Dynamo and failure detection](https://cassandra.apache.org/doc/latest/cassandra/architecture/dynamo.html)
- [Apache Cassandra — cassandra-env.sh startup properties](https://cassandra.apache.org/doc/latest/cassandra/managing/configuration/cass_env_sh_file.html)
- [Apache Cassandra Java Driver 4.x — Manual](https://docs.datastax.com/en/developer/java-driver/4.17/manual/)
