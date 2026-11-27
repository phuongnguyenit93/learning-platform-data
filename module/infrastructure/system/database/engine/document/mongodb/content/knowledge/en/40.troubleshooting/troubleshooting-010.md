# Replication Lag, Quorum Loss, and Insufficient Oplog for Sync in MongoDB

## 1. Introduction: Three Easily Confused Incidents

A system uses a three-node MongoDB replica set:

```text
                        Java Application
                               |
                               v
                     Replica Set rsOrders
                               |
             +-----------------+----------------+
             |                 |                |
             v                 v                v
           mongo-a           mongo-b          mongo-c
           PRIMARY           SECONDARY        SECONDARY
           writes            replay oplog     replay oplog
```

During an operational day, the engineering team sees three alerts:

1. `mongo-b` is 45 seconds behind the primary.
2. Connectivity is lost to two nodes, and the application cannot find a primary.
3. `mongo-c` was stopped for several days, came back up, and cannot catch up with the oplog.

All three relate to replication, but their causes and remediation **are not the same**:

- **Replication lag:** the secondary is still able to replicate, but its applied data position is behind the source.
- **Quorum loss:** the replica set lacks the required number of votes to elect or maintain a primary; writes may be unavailable, even though a few `mongod` processes are still running.
- **Insufficient oplog:** the secondary needs changes that are too old and have already been dropped from the oplog of any eligible source; it cannot simply `getMore` or speed up to recover the missing gap and usually requires an **initial sync/resync** following supported procedures.

> **Remediation priority:** protect data and identify the source of truth first; restore majority and connectivity safely; then optimize lag or rebuild members. Do not run `force reconfig`, delete `dbPath`, or start multiple standalone primaries simply because the system cannot accept writes.

---

## 2. Learning Objectives

After this lesson, learners will be able to:

- Explain oplog-based replication and the roles of primary, secondary, and sync source.
- Read `rs.status()`, `optime` fields, `lastHeartbeat`, and `syncSourceHost`.
- Distinguish replication lag, configured replication delay, and application read staleness.
- Calculate the **oplog window** from the oldest/newest entries and understand the impact of write bursts.
- Understand why lag can lead to a secondary becoming too stale to catch up.
- Calculate voting majority and determine why there is no primary.
- Distinguish election quorum from `writeConcern: "majority"` in a replica set with an arbiter.
- Handle network outages, host restarts, disk full, election loops, and slow apply.
- Decide when to fix the replication path versus when to perform an initial sync.
- Build a safe runbook with stop conditions and post-recovery verification.
- Write Java applications with appropriate timeouts, retries, and idempotency for failover.
- Design meaningful alerts, run lab exercises, and verify safety.

---

# PART I — REPLICATION FUNDAMENTALS

## 3. What Does the Primary Write to the Oplog?

In a replica set, data-bearing members use the **oplog** to synchronize changes.

```text
Client write
    |
    v
PRIMARY applies data changes
    |
    v
Records replication history to oplog
    |
    +---- SECONDARY B fetches records ----> applies changes
    |
    +---- SECONDARY C fetches records ----> applies changes
```

The oplog is stored in the system collection:

```text
local.oplog.rs
```

It is a **capped collection** or oplog mechanism with storage retention limits governed by server version rules. When history exceeds the retention threshold, old entries are removed to make room for new entries.

### 3.1. The Oplog Is Not a Permanent Audit Log

Do not use the oplog as an archive of every change for years. It serves replication and operations that depend on change history such as Change Streams.

### 3.2. The Oplog Contains Replication Operations

It may contain inserts, updates, deletes, transaction-related entries, and internal operations according to the release format. Do not assume that one business request always produces exactly one oplog entry.

### 3.3. Secondaries Do Not Read Source Documents on Every Sync

After initial sync, a secondary normally pulls the needed oplog entries from its sync source and applies them. If a segment of history has already been truncated, having only the current documents on the primary **is not enough** to recover via normal incremental replication.

---

## 4. Replica Set Members

| Member state | Operational meaning |
| --- | --- |
| `PRIMARY` | Can accept writes routed to the primary |
| `SECONDARY` | Follows and applies changes from a sync source |
| `STARTUP2` | In startup/initial sync phases depending on release |
| `RECOVERING` | Not yet ready to serve as a normal secondary |
| `ROLLBACK` | Processing divergence of a data branch |
| `ARBITER` | Has voting rights but stores no copy of data |
| `DOWN`/unreachable | Member cannot be contacted as observed |
| `UNKNOWN` | Node has not yet determined the state of another member |

State is an important signal, but **not sufficient** to conclude lag or data safety. A `SECONDARY` node may lag by many minutes; a `PRIMARY` node may fail to satisfy majority write concern if the topology only has one data copy left.

### 4.1. Hidden Member

A hidden secondary is excluded from normal read selection and must have `priority: 0`. It can still participate in voting if configured with votes. Do not assume hidden means "does not affect quorum".

### 4.2. Delayed Member

A delayed secondary intentionally applies the oplog late according to `secondaryDelaySecs` in applicable versions. Large lag on this member **may be by design**, not an error. However, it still needs sufficient oplog to sustain the delay and catch-up capability.

### 4.3. Non-Voting Member

`votes: 0` does not count toward election voting majority. Still, the node can contribute data copies and serve backup/limited read purposes. You must check both `votes` and `priority`.

---

## 5. `optime`: Where Is the Secondary Positioned?

A replica set tracks replication checkpoints, typically including:

- **Last applied optime:** the newest entry the node has applied to its data.
- **Last durable optime:** the entry persisted durably according to storage engine semantics.
- **Last committed optime:** the majority commit point of the replica set.
- **Primary latest optime:** the newest change position observed on the primary.

Exact field names and response structures may vary across MongoDB versions.

### 5.1. Time-Based Lag

An intuitive estimate:

```text
Primary latest applied:   14:00:00
Secondary latest applied: 13:59:20

Replication lag ≈ 40 seconds
```

This is an **estimated time distance between oplog operations**, not necessarily equal to the exact latency before a write becomes visible in an API.

### 5.2. Operation-Count Lag

If the primary writes 100,000 ops/s, 10 seconds of lag can correspond to a huge backlog. If the workload is idle, timestamps can make simple comparisons less useful.

### 5.3. NTP and Clock Skew

Nodes need stable clocks. If clocks drift, timestamp-based metrics can be misleading. Do not rely on a raw wall-clock subtraction as your sole conclusion.

---

## 6. Majority Commit Point Differs from Secondary Latest Applied

A write can be accepted by the primary before it is acknowledged by a majority of data-bearing members. In a failover scenario, writes that have not been majority acknowledged may be at risk of rollback under replication semantics.

Example:

```text
A PRIMARY:   applied up to op 110
B SECONDARY: applied up to op 108
C SECONDARY: applied up to op 105

Majority applied boundary may be at 108,
but check the server's actual lastCommittedOpTime.
```

`lastCommittedOpTime` is maintained by the server; do not compute a median of a few timestamps yourself and claim an exact result.

### 6.1. `w: 1` and `w: "majority"`

- `w: 1`: the primary can acknowledge the write before secondaries apply it.
- `w: "majority"`: waits for the required number of data-bearing voting members according to the deployment's majority write concern rules.
- `wtimeout` can return an error if enough acknowledgments do not arrive in time.

### 6.2. Timeout Does Not Mean Rollback

A `writeConcern` timeout **does not guarantee the write was undone**. The write may already have been applied on the primary and subsequently replicated successfully. The application must verify the outcome before retrying non-idempotent side effects.

---

## 7. Replication Pipeline Viewed from the Secondary

A secondary must:

1. Connect to an appropriate sync source.
2. Fetch unreceived oplog records.
3. Maintain its buffer/queue and load data according to capacity.
4. Apply changes to collections/indexes.
5. Record applied/durable optime.
6. Track majority commit point and state.

A node can be slow at any phase.

```text
Sync source --> Network fetch --> Receive buffer --> Apply --> Disk durability
                   |                  |               |           |
                bandwidth           memory          CPU/index     IOPS
```

### 7.1. Slow Fetch vs. Slow Apply

If network throughput is low, the secondary does not receive enough events. If it receives them quickly but CPU/disk is weak, the apply backlog grows. The two bottlenecks require different fixes.

### 7.2. The Sync Source Is Not Always the Primary

MongoDB can use **chained replication**, where a secondary syncs from another secondary. Therefore, when troubleshooting, check `syncSourceHost` rather than looking only at the primary directly.

### 7.3. Flow Control

MongoDB includes a flow control mechanism in certain versions/topologies to throttle the primary's write acceptance rate when replication lag risks stalling the majority commit point. Flow control helps cap divergence, but it can **increase primary write latency** and does not replace scaling secondary capacity.

---

# PART II — DIAGNOSING REPLICATION LAG

## 8. First Status Check

Connect with `mongosh` using appropriate privileges, preferring a direct connection to the primary when possible:

```javascript
rs.status();
```

Or:

```javascript
db.adminCommand({
  replSetGetStatus: 1
});
```

Look for:

- `set`, `date`, `myState`.
- `members[].name`, `health`, `stateStr`.
- `members[].optime`, `optimeDate`.
- `members[].lastHeartbeat`, `lastHeartbeatRecv`.
- `members[].lastHeartbeatMessage`.
- `members[].syncSourceHost`.
- `optimes.lastCommittedOpTime` and applied/durable checkpoints if returned by the server.

### 8.1. Quickly Summarize Key Fields

```javascript
const status = rs.status();

printjson({
  replicaSet: status.set,
  observedAt: status.date,
  members: status.members.map(m => ({
    name: m.name,
    state: m.stateStr,
    health: m.health,
    optimeDate: m.optimeDate,
    syncSourceHost: m.syncSourceHost,
    lastHeartbeat: m.lastHeartbeat,
    lastHeartbeatMessage: m.lastHeartbeatMessage
  }))
});
```

**Note:** fields may be `undefined` if a member is down or the server version does not provide them. Do not expect an unresponsive node to report a current `optimeDate`.

### 8.2. If There Is No Primary

`rs.status()` can be run on any reachable member, though some admin actions or helpers require a primary. Do not treat a command's inability to run as proof of data loss.

---

## 9. Helpers in `mongosh`

On supported environments:

```javascript
rs.printReplicationInfo();
rs.printSecondaryReplicationInfo();
```

`rs.printReplicationInfo()` provides information about the current oplog size and time range. `rs.printSecondaryReplicationInfo()` displays observed secondary lag information.

### 9.1. Do Not Treat Helpers as an Absolute Source of Truth

Helpers can:

- Return data sampled at slightly different moments across members.
- Produce unexpected output when no primary exists.
- Report lag on a delayed member even when intentional by configuration.
- Not clearly distinguish slow apply from slow fetch.
- Be affected by network latency and timestamp representation.

Combine them with `rs.status()`, metrics, logs, and application observations.

### 9.2. Cross-Check with Atlas/Monitoring

If using MongoDB Atlas, metrics for replication lag, oplog window, and node status are available by tier/version. Use them alongside election events and write latency to pinpoint when lag began rising.

---

## 10. Classifying Lag by Behavior Pattern

| Observed pattern | Priority hypothesis |
| --- | --- |
| Lag rises steadily | Secondary apply/fetch slower than source write rate |
| Lag spikes during import | Write burst expands oplog volume |
| Lag rises after secondary restart | Cold cache, disk pressure, catch-up |
| One member slow, two members healthy | Node-specific CPU/IOPS/network/disk |
| All secondaries slow | Primary write overload, shared network, config/hardware |
| Fixed 1-hour lag on one member | Possibly a configured delayed secondary |
| Lag rises then drops periodically | Workload peaks or backup/index build |
| Lag accompanied by `getMore` errors | Sync source/network/history issue |
| High lag with `RECOVERING` | Node not ready; may be stale |
| Lag drops but `w:majority` still times out | Check voting/data-bearing topology and majority commit |

### 10.1. "30 Seconds of Lag" Alone Is Not a Severity

If RPO/read policies require data freshness within 1 second, 30 seconds is severe. If a reporting secondary is allowed to lag by a few minutes, 30 seconds may be acceptable.

### 10.2. Evaluate the Trend

Five minutes of lag that is shrinking rapidly can be less dangerous than 30 seconds of lag that is **continuously growing** at a high rate. Monitor both backlog and the oplog window.

---

## 11. Cause Group A: Secondary CPU Starvation

A secondary must apply operations, maintain indexes, and serve reads if targeted for reads.

Causes:

- Saturated CPU.
- Too many concurrent analytical queries on the secondary.
- Heavy index maintenance.
- Compression/decompression.
- Container CPU limits set too low.
- Host affected by a noisy neighbor.

### 11.1. Signals

- Sustained high CPU.
- Replication lag increases when report queries run.
- Disk IOPS is not necessarily saturated.
- Slow application secondary reads.
- Lag starts decreasing after stopping the reporting workload.

### 11.2. Remediation

- Reduce/throttle heavy reports and aggregations.
- Scale compute according to the supported topology.
- Optimize indexes/queries.
- Separate analytical workloads onto a reporting cluster/dedicated read nodes as needed.
- Avoid scheduling heavy index builds or batch exports when replication is already strained.

**Do not** replace a secondary with an arbiter to "save CPU" when durability or majority writes are required.

---

## 12. Cause Group B: Disk I/O and Cache Pressure

Replication apply generates writes and index updates on the secondary. High disk latency reduces the apply rate.

Measure:

- Read/write IOPS.
- Disk await/service time.
- Queue depth.
- Disk utilization.
- WiredTiger cache pressure/eviction.
- Journal latency.
- Free disk and inode availability.
- Cloud volume throughput limits.

### 12.1. Secondary Does Not Mean Low Load

A secondary still has to write roughly the same volume of data and index modifications. If it handles heavy reads while applying the oplog, it can overload.

### 12.2. Full Disk Is a Critical Incident

If disk free space drops very low, the secondary may fail to write further and fall behind until history is lost. Do not "just wait for the replica to heal itself"; reduce pressure, expand the volume, or free data **authorized** for deletion by the runbook.

### 12.3. Do Not Delete Storage Files Manually

Never manually delete files inside `dbPath`, WiredTiger data files, or `local.oplog.rs` to reclaim space. Doing so can prevent the member from starting or break consistency.

---

## 13. Cause Group C: Network Fetch and Sync Source

Symptoms:

- A node experiences packet loss or high RTT.
- Firewall/security group blocks MongoDB ports.
- DNS resolves to the wrong IP.
- Invalid TLS/certificate.
- Internal authentication mismatch in keyfile/certificates.
- Sync source is unreachable.
- Network bandwidth is smaller than the oplog generation rate.
- Cross-region links have high latency.

### 13.1. `syncSourceHost` Is a Useful Field

```javascript
rs.status().members.map(m => ({
  host: m.name,
  source: m.syncSourceHost,
  state: m.stateStr
}));
```

If `mongo-c` syncs from `mongo-b`, an issue on `mongo-b` can affect `mongo-c` even while the primary is healthy.

### 13.2. Chained Replication Is Not Inherently Broken

Chained replication is a design supported by MongoDB. Treat it as harmful only when the specific sync path causes lag, slowness, or lacks needed history.

### 13.3. Changing the Sync Source

MongoDB has automatic sync source selection and admin helpers on supported versions. Do not force a sync source or configuration change arbitrarily without understanding the topology, because the chosen source must have the needed oplog and adequate connectivity.

---

## 14. Cause Group D: Write Bursts, Bulk Imports, and Index Churn

On the primary:

```text
Normal:
  5,000 oplog events/min
  oplog window ~ 24 hours

Bulk migration:
  400,000 oplog events/min
  oplog window rapidly shrinks
```

If a secondary is lagging due to network issues and the primary continues generating many oplog entries, available history can shrink rapidly.

### 14.1. Jobs That Commonly Trigger This

- Bulk writes/backfills.
- Modifying many documents with `updateMany`.
- Large-scale deletes.
- TTL cleanup backlogs.
- Schema migrations.
- Building multiple indexes during high load.
- Many large transactions according to release semantics.
- Services generating high write amplification events.

### 14.2. Do Not Automatically Blame TTL

TTL deletes can create significant writes when a backlog is large, but check `metrics.ttl` and oplog/write rates before concluding.

### 14.3. Rate-Limit Bulk Jobs

Running a bulk migration slightly slower keeps replication stable and prevents excessive contraction of the oplog window. Thresholds depend on actual headroom and SLOs.

---

## 15. Cause Group E: Intentional Member Configuration

Before declaring an incident, inspect:

```javascript
rs.conf();
```

Check:

- `priority`.
- `votes`.
- `hidden`.
- `secondaryDelaySecs`.
- `buildIndexes`.
- Relevant tags/replica set settings.
- Sync source topology.

A delayed secondary with `secondaryDelaySecs: 3600` will intentionally lag by roughly one hour. If monitoring groups all members together without distinguishing roles, the system will fire false lag alerts all day.

### 15.1. Delayed Secondaries Still Need a Wide Enough Oplog

If the delay is 1 hour but the oplog window is only 40 minutes, the node cannot reliably sustain its configured delay. Sufficient history is needed so delayed operations remain available.

### 15.2. Hidden Members Can Vote

`hidden:true` does not automatically imply `votes:0`. When calculating quorum, read the actual `votes` value.

---

## 16. Flow Control: Lag Directly Affects Write Latency

In some deployments, when lag affects the ability to advance the majority commit point, the primary may throttle write ticket issuance via replication flow control.

Diagram:

```text
Secondary apply falling behind
             |
             v
Majority commit point advances slowly
             |
             v
Primary flow control may engage
             |
             v
Application write latency increases
```

Metrics may appear in `db.serverStatus().flowControl` depending on MongoDB version.

```javascript
const server = db.serverStatus();
printjson(server.flowControl);
```

### 16.1. Do Not Disable Flow Control Arbitrarily

Disabling flow control without understanding the root cause can allow the primary to race further ahead of secondaries, worsening lag and oplog pressure. Fix the resource bottleneck or tune the workload based on version documentation and operational guidance.

---

# PART III — QUORUM LOSS AND NO PRIMARY

## 17. What Does Quorum Mean?

**Election quorum** is the number of votes required to elect or sustain a primary.

Given `V` total voting members:

```text
election majority = floor(V / 2) + 1
```

Examples:

| Voting members | Needed for majority |
| ---: | ---: |
| 1 | 1 |
| 2 | 2 |
| 3 | 2 |
| 4 | 3 |
| 5 | 3 |
| 7 | 4 |

Do not use **all members** as `V`; count only members with `votes:1`.

### 17.1. Three Members, One Node Down

```text
A PRIMARY    UP
B SECONDARY  UP
C SECONDARY  DOWN

Votes reachable: 2/3
Election majority: 2
```

A primary can be sustained/elected provided other election constraints are met.

### 17.2. Three Members, Two Nodes Down

```text
A formerly PRIMARY  UP
B SECONDARY         DOWN
C SECONDARY         DOWN

Votes reachable: 1/3
Election majority: 2
```

Insufficient election quorum. The replica set cannot safely sustain a primary to accept normal writes.

### 17.3. A Running Process Does Not Mean There Is a Primary

Clients can connect directly to `mongod`, but normal write commands are still disallowed if the node is not in a valid primary state.

---

## 18. Arbiter: Holds a Vote Without Holding Data

Topology:

```text
A PRIMARY    data-bearing, votes=1
B SECONDARY  data-bearing, votes=1
C ARBITER    no data,      votes=1
```

If B goes down, A+C still hold an **election majority** of 2/3. However, only **one data-bearing member** remains.

### 18.1. Majority Write Concern in PSA

`w:"majority"` requires acknowledgment from a majority of data-bearing voting members; an arbiter does not store or acknowledge data writes like a secondary. When B is unavailable, `w:"majority"` cannot be satisfied and writes will wait/time out per the write concern.

**Therefore: a PRIMARY can exist while the application still hits writeConcern timeouts.**

### 18.2. Do Not Treat an Arbiter as a Data Copy

An arbiter cannot restore data, cannot serve normal secondary reads, and does not replace backups.

### 18.3. Implicit Default Write Concern May Differ

Certain replica set topologies with arbiters affect how MongoDB determines the implicit default write concern. Do not assume every deployment defaults to `w:"majority"`; verify `getDefaultRWConcern` and application configuration for your release.

---

## 19. Quorum and Reader Availability

During an outage with no primary:

- Normal writes through the replica set are unavailable.
- Primary read preference finds no readable node.
- Some secondary reads may still work if configuration/read concern allows.
- Data read from secondaries may be **stale**.
- Operations requiring majority commit/snapshot have different constraints.

Do not use successful secondary reads as evidence that the replica set is serving normal transactional traffic.

---

## 20. Why Does Election Fail Even with Enough Votes?

Quorum is a necessary condition, not the only condition. Causes include:

- Voting members lack true two-way communication.
- Candidate is ineligible due to `priority:0`.
- Candidate is not sufficiently up to date under election rules.
- Replica set config/term is inconsistent.
- A member is in initial sync or `RECOVERING`.
- Network partition/heartbeat failures.
- Internal authentication/TLS failures.
- Clock skew/stale state on some members.
- An election is still in progress and has not completed.

### 20.1. Priority 0 and Delayed/Hidden Members

A `priority:0` member cannot be elected primary. If all reachable data-bearing nodes have priority 0, none can become primary even though total votes appear sufficient.

### 20.2. Last Optime Matters

A member that is too far behind should not be elected primary if doing so violates election freshness requirements. The system prioritizes replication safety over "just electing any random node".

---

## 21. Split-Brain and Why You Must Not Force a Primary

A network partition can split 5 voters into:

```text
Partition A: 3 voting members
Partition B: 2 voting members
```

Only the side with a proper majority can elect/sustain a primary by algorithm design. This prevents two primaries from accepting concurrent writes.

### 21.1. Force Reconfig Can Break Safety Guarantees

Certain admin commands support `rs.reconfig(..., { force: true })` in emergencies, but MongoDB warns it can lead to data divergence/rollback of previously acknowledged writes depending on configuration and events.

**Do not use force reconfig as a default fix** on quorum loss. Consider it only under an official disaster recovery procedure, after protecting data, inspecting latest opTimes/backups, and securing DBA/SRE approval.

### 21.2. Never Re-Initiate Separate Replica Sets on Surviving Nodes

If two partitions are turned into two independent replica sets that both accept writes, the result can be divergent branches that cannot be "auto-merged".

---

## 22. Losing One Data Center

Suppose 5 voting members are placed as:

```text
DC1: A, B, C   (3 votes)
DC2: D, E      (2 votes)
```

If DC1 goes down, DC2 has 2/5 votes: **insufficient majority**.

Conversely, if DC2 is lost, DC1 has 3/5: elections and a primary can continue.

### 22.1. Placement Must Follow Failure Domains

Placing all 5 members inside a single availability zone provides no zone-level fault tolerance even though quorum math is correct.

### 22.2. Arbiter in a Third Site

Adding an arbiter purely for a third vote can improve election availability in some PSA topologies, but it adds no data copies and does not substitute for majority write durability. Evaluate network latency, partition behavior, and policy.

### 22.3. Data Center Outage Does Not Automatically Mean Data Loss

If quorum remains and data was majority acknowledged, the cluster can preserve a safe state. If quorum is lost, focus on restoring connectivity/members rather than immediately rebuilding from backup by default.

---

## 23. Application Errors When the Primary Is Lost

The Java MongoDB Driver may report:

- Server selection timeout because no primary was found.
- `NotWritablePrimary` or replica state-change errors.
- Network exceptions when connections are closed.
- Write concern timeouts when acknowledgments are missing.
- Transient transaction errors when an election interrupts a transaction.

### 23.1. Do Not Treat Every Error as "MongoDB Lost Data"

Distinguish between:

- Command was never sent because no primary was found.
- Command was sent to the old primary and the response was lost.
- Write applied on the primary without reaching write concern.
- Transaction commit outcome is unknown.
- Read preference picked a stale secondary.

Retry and reconciliation policies depend on the outcome category.

---

# PART IV — OPLOG WINDOW AND STALE SECONDARIES

## 24. What Is the Oplog Window?

The **oplog window** is the time span covered between the oldest and newest entries currently retained in the oplog.

```text
Oldest entry                         Newest entry
    |                                     |
    v                                     v
  10:00 ------------------------------ 14:00
                 4 hours
```

It answers: how far back in time can replication history serve catch-up right now?

### 24.1. Oplog Window Is Not Fixed in Hours Without Proper Retention Policy

A fixed oplog size retains by **storage volume**, not a fixed time duration:

- Under low writes, the window can be long.
- Under heavy writes, the window can be short.
- A large batch migration can shrink the window rapidly.

### 24.2. Oplog Window Is Not RPO

RPO depends on write concern, backups, and cutover behavior. The oplog window is strictly a metric of **remaining change history available for replication/resume**.

---

## 25. How to Inspect the Oplog Window

On a data-bearing replica set member:

```javascript
rs.printReplicationInfo();
```

This helper may print:

- Configured oplog size.
- Actual oplog size.
- Timestamps of the first and last entries.
- `oplog length start to end` expressed in time.

### 25.1. Inspecting the `local.oplog.rs` Collection

```javascript
const oplog =
    db.getSiblingDB("local").getCollection("oplog.rs");

printjson(oplog.stats());
```

If you need to inspect boundary entries:

```javascript
const oldest = oplog.find()
    .sort({ $natural: 1 })
    .limit(1)
    .toArray();

const newest = oplog.find()
    .sort({ $natural: -1 })
    .limit(1)
    .toArray();

printjson({
  oldest: oldest[0],
  newest: newest[0]
});
```

**Warning:** oplog entries can contain sensitive data/operation details and huge output. Never dump raw oplog entries or scan the entire oplog during an incident.

### 25.2. Take Consistent Observations

Reading the primary and a secondary at different times can show different windows. Record the node, timestamp, version, and measurement tool.

---

## 26. Estimating Window from Write Rate and Oplog Size

A rough calculation:

```text
Oplog allocated:       40 GiB
Avg oplog generation:   5 GiB/hour

Estimated window ≈ 8 hours
```

If peak workload rises to 20 GiB/hour:

```text
Estimated window ≈ 2 hours
```

### 26.1. Why Is This Only an Estimate?

- Oplog capped/retention behavior depends on version.
- Compression and representation differ.
- Oplog entry sizes vary.
- Burst writes.
- Transactions and internal operations.
- Minimum retention policy if configured.
- Disk capacity and storage engine behavior.

### 26.2. Practical Sizing Formula

```text
Required history >= maximum tolerated replication outage
                 + worst-case catch-up duration
                 + maintenance/failover headroom
```

If the organization needs a node to survive 12 hours offline plus 4 hours to catch up, a 6-hour oplog window during peak is insufficient.

---

## 27. When Does a Secondary Become "Too Stale to Catch Up"?

Suppose a secondary stopped at oplog timestamp:

```text
Secondary latest applied: 10:00

Primary oplog still contains:
  oldest  = 11:30
  newest  = 16:00
```

The secondary needs operations starting right after 10:00, but the sync source no longer retains data prior to 11:30. There is a **history gap**.

```text
Secondary needs:
    10:00 -> 16:00

Source has:
             11:30 -> 16:00

Missing:
    10:00 -> 11:30
```

You cannot simply raise `batchSize`, add CPU, or retry `getMore` to recover oplog entries that have already been dropped.

### 27.1. Consequence

MongoDB may log that the secondary is too stale and cannot continue incremental replication. The node may sit in `RECOVERING` or another state depending on release.

### 27.2. Identify the True Cause

Not every `RECOVERING` secondary is too stale. It could also be:

- Recovering after a restart.
- Processing a rollback.
- Running initial sync.
- Waiting for a stable sync source.
- Hitting disk/network/auth errors.
- Experiencing a storage issue.

Always check logs, oplog boundaries, and `rs.status()`.

---

## 28. Does Growing the Oplog Help After History Is Lost?

**It does not restore entries that were already truncated.**

Increasing oplog size or minimum retention **before** a long outage helps prevent staleness; once a gap already exists, expanding the oplog does not bring deleted history back.

### 28.1. Possibility of an Alternate Sync Source

If another data-bearing member in the replica set **still retains enough history**, the secondary may have a viable sync path. This requires verifying compatibility, sync source selection, and release procedures.

Do not pick an alternate sync source merely because it is online: verify that it holds the needed history **contiguously** and that its data has not diverged.

### 28.2. If No Member Has History

You generally need to perform an **initial sync** to rebuild data from a valid source, or follow a supported resync/backup-based initial sync procedure.

---

## 29. Initial Sync vs. Incremental Catch-Up

| Operation | Goal | Typical condition |
| --- | --- | --- |
| Incremental replication | Apply unprocessed oplog | Source still holds full history |
| Initial sync | Rebuild member data from valid source | New member or resync needed |
| Rollback | Discard writes from an unselected branch | Per replication history/rollback semantics |
| Restore backup | Restore data from backup | Valid backup exists |
| Clone/new member | Provision new node copying from source | Capacity, security/config valid |

### 29.1. Initial Sync Is Not Just Copying a Snapshot and Being Done

It typically includes:

1. Selecting a sync source.
2. Cloning required data and metadata.
3. Fetching oplog changes made during the clone.
4. Applying those changes to catch up.
5. Transitioning state once eligible.

If initial sync takes longer than history retention can sustain and the server lacks a protective mechanism, the job can fail/restart.

### 29.2. Resource Requirements

Initial sync can consume heavy network, disk I/O, and CPU on both source and destination. If the source serves production with tight headroom, resyncing during peak hours can cause the remaining members to lag.

---

## 30. Preconditions Before Rebuilding a Secondary

Before any destructive action, verify:

- The exact **node** to rebuild; never mistake the primary.
- The replica set retains enough majority/voting members.
- At least one data-bearing source is healthy with accurate data.
- Any non-majority-acknowledged writes are handled per incident policy.
- A verified backup or restore point exists.
- No local-only data needs preservation on the target node.
- Storage/disk/network capacity is sufficient.
- Version/FCV/TLS/auth match.
- The initial sync procedure is supported for the version/topology.
- Change approval and on-call coordination are in place.
- A plan exists to wait for catch-up before rebuilding the next member.

### 30.1. Never Delete `dbPath` Without Verifying the Node

A simplistic "delete `/var/lib/mongodb` and restart" instruction can destroy the only surviving copy if an operator picks the wrong host.

### 30.2. Do Not Resync All Secondaries Simultaneously

If both B and C need initial sync, plan sequencing and capacity carefully. Rebuilding them together can leave only one data-bearing member, impacting majority, durability, and write availability.

### 30.3. Backups Are Mandatory Before Risky Actions

A stale node may still hold data needed for forensics when acknowledged write history is uncertain. Never erase evidence before a recovery decision is made.

---

## 31. Conceptual Runbook for Handling a Stale Secondary

Example:

```text
A PRIMARY    healthy/current
B SECONDARY  healthy/current
C RECOVERING too-stale
```

With A/B healthy and proper majorities preserved:

1. Confirm C is truly stale using logs + oplog boundaries.
2. Ensure A/B are replicating cleanly and backups are valid.
3. Select the C rebuild procedure matching the MongoDB Manual/edition/version.
4. Stop C via the service manager.
5. Prepare a clean data directory **only on C**, after verifying path/permissions and approval.
6. Start C into the valid topology to begin initial sync.
7. Monitor initial sync progress, CPU, disk, network, and oplog source.
8. Wait until C reaches `SECONDARY` and lag drops within acceptable bounds.
9. Verify majority writes, application health, and monitoring.
10. Touch another member only after C is stable.

### 31.1. Never Provide a One-Size-Fits-All Delete Command

`dbPath` paths vary across services, Docker, Atlas, Windows, and deployment automation. This lesson discourages copy-pasting `rm -rf` in production.

### 31.2. Initial Sync May Be Platform-Managed

With Atlas, Ops Manager, or automated platforms, use the **platform's replace/resync member workflow** rather than editing data files manually as in self-managed setups.

---

# PART V — ORDERED INCIDENT RUNBOOK

## 32. Step 0: Determine Urgency Level

Distinguish:

- **SEV-1:** primary/quorum loss, writes completely stopped.
- **SEV-1/2:** risk of durability loss or a secondary nearly stale.
- **SEV-2:** majority write timeouts/high latency.
- **SEV-3:** one reporting secondary lagging while the service remains healthy within SLO.

Exact severity levels follow organizational policy; these are illustrative examples.

### 32.1. First Facts to Record

- When did it start?
- All tenants or a subset?
- Are writes failing?
- Read latency/errors?
- Were there recent version/index upgrades, backups, maintenance, or bulk jobs?
- Are there node/network/storage alerts?
- Which copy holds the latest data?
- Current oplog window and whether lag is rising or falling?

---

## 33. Step 1: Preserve Evidence and Avoid Destructive Changes

Before acting:

- Save `rs.status` output from a reachable node.
- Save logs around the start of the incident.
- Record each member's `host`, `votes`, `priority`, `health`, and `optime`.
- Record monitoring graphs and deployment events.
- Confirm the latest backup.
- Pause non-essential bulk jobs if they are adding pressure.
- Do not force reconfig, stepdown, or restart the entire cluster.

### 33.1. Why Not Restart Everything?

Mass restarts can:

- Break remaining quorum.
- Push a catching-up secondary back into recovery.
- Prolong the outage.
- Obscure diagnostic trails.
- Spike cache cold-starts and disk I/O.

### 33.2. One Change at a Time

If multiple issues exist (network, disk, config), choose the change with the highest probability of recovery and clean rollback, then observe its effect.

---

## 34. Step 2: Determine Actual Topology

```javascript
const c = rs.conf();

printjson(c.members.map(m => ({
  host: m.host,
  votes: m.votes,
  priority: m.priority,
  hidden: m.hidden,
  secondaryDelaySecs: m.secondaryDelaySecs,
  arbiterOnly: m.arbiterOnly
})));
```

**Note:** `rs.conf()` requires accessing an eligible member; if unavailable, consult saved configuration from automation/runbooks and cross-check once nodes recover.

### 34.1. Do Not Count Only Online Nodes

Distinguish:

- Data-bearing vs. arbiter.
- Voting vs. non-voting.
- `priority > 0` vs. `0`.
- Hidden/delayed.
- Members with genuine two-way connectivity.

### 34.2. Quorum Calculation Example

A replica set has A/B/C/D/E with votes `[1,1,1,0,0]`. Five processes exist, but only **3 voting members**; election majority is **2**, not 3.

---

## 35. Step 3: Check Network and DNS

If you see `health:0` or heartbeat errors:

- Use ping/route only for basic reachability checks.
- Verify TCP ports, security groups, firewalls, and load balancers.
- Verify consistent hostname resolution across members.
- Check TLS cert SANs, expiration, and internal authentication.
- Check clocks/NTP.
- Check packet drops/latency between AZs/regions.
- Check if a deployment event changed IPs/DNS/ports.

### 35.1. One-Way Connectivity Is Not Enough

Node A might reach B while B cannot reach A. Elections and replication require appropriate bidirectional communication, not just a single connection from an admin laptop.

### 35.2. Do Not Rush to Edit Hostnames in Config

Changing replica set member hostnames carries conditions and risks; prioritize restoring DNS/network as designed first.

---

## 36. Step 4: Check Compute and Disk

Measure per member:

- CPU throttling.
- Free RAM/swap pressure.
- Disk free space.
- Disk IOPS/latency.
- Journal/storage errors.
- WiredTiger cache eviction.
- Network throughput.
- Container restarts/OOM kills.
- Cloud volume burst credits and caps.

### 36.1. If a Secondary Has a Full Disk

Prioritize freeing space via MongoDB- and platform-supported means or expanding storage. Never manually delete WiredTiger files or oplog entries.

### 36.2. If the Primary Disk Is Full

This is a critical risk to write availability and durability. Coordinate with the incident team, backups, and storage recovery; do not force the primary to accept writes on a full volume.

---

## 37. Step 5: Determine Whether History Is Lost or Lag Is Simply Large

Inspect together:

```javascript
rs.status();
rs.printReplicationInfo();
rs.printSecondaryReplicationInfo();
```

Then compare:

```text
Latest primary oplog timestamp
Oldest retained source oplog timestamp
Latest applied optime of slow secondary
```

### 37.1. If Secondary Latest Remains Within the Source Window

Incremental catch-up may still be viable; focus on resolving throughput/network/apply bottlenecks.

### 37.2. If Secondary Needs History Prior to the Oldest Retained Entry

Staleness risk; inspect logs and alternate sources before choosing initial sync.

### 37.3. Do Not Compare Timestamps Alone

Ensure the history chain and oplog entries are consistent, avoiding divergence or missing required events. MongoDB validates replication conditions automatically; operators should never manually "splice the oplog".

---

## 38. Step 6: Protect Quorum Before Any Maintenance

Example with 3 data-bearing members:

```text
A PRIMARY UP
B SECONDARY UP
C SECONDARY LAGGING
```

If you restart B while C is unhealthy, you can lose data-bearing majority even though C still appears in config.

### 38.1. One Change Per Iteration

- Restart/replace only one member at a time.
- Wait for the node to stabilize and catch up.
- Re-evaluate majority after each step.
- Verify `w:majority` and application writes.
- Avoid stopping a healthy sync source serving an active initial sync whenever possible.

### 38.2. Prefer Recovering the Original Node Before Force Reconfig

If a member went down due to service or network issues, restoring that exact node is often safer than reconfiguring because it preserves identity, data, and voting membership.

---

## 39. Step 7: Verify Application Health After Recovery

Do not stop just because `rs.status()` displays a primary.

Check:

- A small write succeeds with policy-compliant acknowledgment.
- Read-after-write behavior.
- Primary discovery from the Java Driver.
- Transaction/commit behavior.
- Retryable writes working properly.
- Replication lag decreasing and stabilizing.
- `lastCommittedOpTime` advancing.
- Sufficient oplog window headroom.
- Backup/PITR and Change Streams consumers running.
- Metrics (p95/p99/errors) returning within SLO.

### 39.1. Do Not Corrupt Business Data with Test Writes

If you must test writes, use an authorized test collection/namespace and clean up afterward; never insert dummy records into production business collections.

---

# PART VI — OPLOG SIZING AND STALE SECONDARY PREVENTION

## 40. When Should You Grow the Oplog?

You may need more capacity or minimum retention if:

- The oplog window is shorter than your maintenance/outage budget.
- Cross-region nodes frequently lag due to network conditions.
- Bulk imports run regularly.
- Initial sync needs longer history.
- Change Streams consumers experience long downtimes.
- A delayed secondary must remain delayed for several hours.
- Retention headroom drops too low during peak load.

### 40.1. Options to Expand

- Increase configured oplog size using server-supported commands.
- Configure minimum oplog retention hours if supported by the release.
- Reduce write bursts/replication lag.
- Improve secondary throughput.
- Adjust architecture capacity.

### 40.2. Increasing Retention Is Not Free

Minimum retention can cause the oplog to **consume more disk than its configured size** in order to keep entries long enough under policy. Account for disk headroom and monitoring, otherwise a lag problem can become a disk-full incident.

---

## 41. `replSetResizeOplog` in Self-Managed MongoDB

On MongoDB versions supporting dynamic oplog sizing:

```javascript
db.adminCommand({
  replSetResizeOplog: 1,
  size: 16384
});
```

In this command, `size` is typically specified in **MiB**: `16384` corresponds to roughly 16 GiB. The command has version/topology/permission restrictions; run it **on the right data-bearing replica set member**, not through `mongos` or in production without approval.

Example setting minimum retention on supported releases:

```javascript
db.adminCommand({
  replSetResizeOplog: 1,
  minRetentionHours: 48
});
```

### 41.1. Check Exact Version and Syntax

Not all MongoDB versions support identical options. Consult the `replSetResizeOplog` documentation for your specific version/edition and deployment configuration before applying.

### 41.2. Resizing Does Not Resurrect Truncated Oplog History

If a secondary is already too stale, increasing the size helps prevent recurrence, but you still need recovery for the existing gap.

### 41.3. Size Based on Reality

For example, if peak generation is 6 GiB/hour and you require 36 hours of headroom:

```text
6 GiB/h × 36 h = 216 GiB (rough sizing)
```

Include safety margin, disk capacity, storage overhead, and workload profile to determine final sizing.

---

## 42. Oplog Minimum Retention vs. Configured Size

Two distinct policies:

- **Oplog size:** target/storage capacity, sensitive to entry generation rate.
- **Minimum retention hours:** prevents truncating entries newer than a defined age on supported releases.

### 42.1. Example

```text
Configured oplog size:       20 GiB
Minimum retention:          24 hours
Peak generation:            3 GiB/hour

24h history requires:        ~72 GiB
```

The server may retain more oplog than the configured size to honor minimum retention, subject to disk space and server behavior.

### 42.2. Do Not Set Minimum Retention Beyond Physical Disk Limits

If only 30 GiB is free while retention requires 70 GiB more, that policy can trigger severe disk pressure.

### 42.3. Alert on **Actual Window**, Not Just Configuration

A 100 GiB oplog can still shrink to just a few hours during a write burst. Measure actual oldest/newest timestamps against expected outage budgets.

---

## 43. Optimizing Sync Source and Placement

With a multi-region topology:

```text
Region A:
  A PRIMARY
  B SECONDARY

Region B:
  C SECONDARY
  D SECONDARY
```

C/D may incur high network RTT if forced to fetch across regions constantly. Chained replication can affect bandwidth usage and catch-up speed.

### 43.1. Tradeoffs to Balance

- Latency and bandwidth between regions.
- Failure domains.
- Whether C/D can participate in elections.
- Write concern tags or majority rules.
- Oplog retention.
- Cross-region traffic cost.
- Recovery if an entire region is lost.
- Source selection and replication history availability.

### 43.2. Do Not Pick a Sync Source Based on Proximity Alone

A nearby node that is already lagging/stale or disk-bottlenecked makes a poor source. Inspect data freshness, oplog window, and health.

---

## 44. Backups Do Not Replace Oplog, But Support Recovery

The oplog powers replication and CDC resume. Backups enable data recovery when oplog history or primary data is no longer valid.

A DR plan requires:

- Scheduled backups.
- Topology-appropriate PITR.
- Restore rehearsals.
- Encryption/KMS key retention.
- Backup consistency.
- Snapshot classification by version/FCV.
- Procedures to reintroduce a restored member safely into a replica set.
- Post-restore data reconciliation.

### 44.1. Never Restore an Old Snapshot and Immediately Elect It Primary

If a member is restored from an older snapshot, it may lack recent writes. Follow proper initial sync/recovery procedures and ensure it cannot create divergent history.

### 44.2. Backup-Only Recovery May Involve an RPO Tradeoff

If only a pre-incident backup remains, recent unbacked-up writes may be lost. That is a business data decision requiring formal approval.

---

# PART VII — JAVA DRIVER IN REPLICATION INCIDENTS

## 45. Replica Set URI for Automatic Primary Discovery

Example:

```text
mongodb://mongo-a:27017,mongo-b:27017,mongo-c:27017/
  ?replicaSet=rsOrders&retryWrites=true
```

In real configuration, the URI must be a single line with TLS/auth and secure secret management.

### 45.1. Avoid `directConnection=true` for Failover-Capable Applications

If an app connects to a single host and forces a direct connection, it will fail to discover a new primary as expected under the standard replica set model.

### 45.2. Multiple Seeds in the URI Do Not Guarantee a Primary Exists

Seeds help the driver discover the topology. When quorum is lost, the driver cannot conjure a primary or bypass consensus rules.

---

## 46. Java Sync Driver with Explicit Write Concern

Example:

```java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

import java.util.concurrent.TimeUnit;

public final class MongoClientFactory {

    public static MongoClient create(String uri) {
        MongoClientSettings settings =
            MongoClientSettings.builder()
                .applyConnectionString(
                    new ConnectionString(uri)
                )
                .retryWrites(true)
                .readPreference(
                    ReadPreference.primary()
                )
                .writeConcern(
                    WriteConcern.MAJORITY
                        .withWTimeout(10, TimeUnit.SECONDS)
                )
                .applyToClusterSettings(
                    builder -> builder.serverSelectionTimeout(
                        10, TimeUnit.SECONDS
                    )
                )
                .build();

        return MongoClients.create(settings);
    }
}
```

### 46.1. Driver Version

Builder methods and timeout semantics depend on the Java Driver version. Consult the Javadocs for your active dependency.

### 46.2. `serverSelectionTimeout`

Bounds how long the driver waits to find an eligible server. It does not make a quorumless replica set elect a primary.

### 46.3. `wtimeout`

A write concern timeout does not guarantee the write failed to apply on the primary. Never blindly retry entire external business transactions such as payments or emails.

### 46.4. `retryWrites`

Supports retryable writes when server, driver, and operation qualify; it does not cover every bulk write, transaction, external API call, or logic error.

---

## 47. Safe Error Handling When Write Outcome Is Uncertain

Example:

```java
try {
    orders.insertOne(order);
    return "ACKNOWLEDGED";
} catch (com.mongodb.MongoException error) {
    logger.warn(
        "MongoDB write not confirmed for orderId={}",
        order.get("_id"),
        error
    );
    throw error;
}
```

This is a **sketch**, insufficient by itself for critical applications. You need a protocol:

1. Generate a stable `orderId`/idempotency key **before** writing.
2. Enforce a unique key on the business operation.
3. On an uncertain timeout, query by ID via an appropriate read path once the cluster is healthy.
4. Retry only operations with idempotent semantics.
5. Never re-invoke external payment/email systems purely due to a MongoDB write timeout.
6. For uncertain transaction commits, inspect error labels and retry commit per driver documentation.

### 47.1. Do Not Query a Stale Secondary Immediately to Conclude a Record Is Missing

If the app executes `insertOne` on the primary and immediately reads a lagging secondary, the document may not appear yet. Check read preference/concern and replication health.

---

## 48. Read Preference and Stale Reads

If the application uses:

```java
ReadPreference.secondaryPreferred()
```

while replication lag rises, reads may return stale data.

### 48.1. `maxStalenessSeconds`

The Java Driver supports read preferences with **maximum staleness** within server/driver constraints:

```java
import com.mongodb.ReadPreference;

ReadPreference preference =
    ReadPreference.secondary(
        120,
        java.util.concurrent.TimeUnit.SECONDS
    );
```

Meaning: the driver avoids selecting secondaries estimated to be stale beyond the threshold under applicable rules. This is not an absolute per-read SLA and carries minimum value constraints.

### 48.2. When No Eligible Secondary Remains

A secondary-only read preference may fail instead of reading from the primary. `secondaryPreferred` can fall back to the primary when no secondary qualifies, depending on topology.

### 48.3. Critical Reads

Financial flows, token verification, or inventory checks must define explicit read consistency guarantees. Never assume secondary reads provide read-your-writes.

---

## 49. Transactions and Primary Elections

During a primary stepdown or quorum loss, application transactions can be aborted or return transient errors.

The driver provides error labels such as:

- `TransientTransactionError`.
- `UnknownTransactionCommitResult`.

### 49.1. Semantic Retries

- For transient transaction errors, retrying the full transaction body may be needed.
- For unknown commit results, retrying commit safely may be possible **without** replaying all external side effects.
- Use `withTransaction` or helpers appropriate for your driver version and application.

### 49.2. Callbacks Must Not Trigger Non-Idempotent Side Effects

If a `withTransaction` callback can re-execute, never call a payment gateway or email service directly inside the callback without an outbox/idempotency pattern.

---

# PART VIII — SPECIFIC SCENARIOS AND REMEDIATION

## 50. Scenario A: Secondary Lag Rises from 5 to 300 Seconds

Observation:

```text
A PRIMARY    healthy
B SECONDARY  lag 5s -> 30s -> 300s
C SECONDARY  lag < 1s
```

Initial hypothesis: node-specific resource/network issue on B.

### 50.1. Diagnosis

- Is B experiencing CPU/disk saturation?
- Is B running a reporting query/index build?
- What is B's `syncSourceHost`?
- Did B restart recently?
- How much oplog window remains on the sync source?
- Does lag drop when read workload decreases?

### 50.2. Actions

1. Leave C untouched if healthy.
2. Reduce read workload on B if needed.
3. Fix the disk/network bottleneck.
4. Watch B catch up.
5. Adjust oplog size/retention if stale risk is high.
6. If B is already too stale with no history available, plan initial sync.

### 50.3. Mistake

Restarting A/B/C together or running force reconfig just because B lags while quorum is healthy.

---

## 51. Scenario B: Losing Two Voters in a Three-Node Replica Set

```text
A: reachable
B: unreachable
C: unreachable

Votes: 1/3
Election majority: 2
No PRIMARY
```

### 51.1. Priorities

1. Restore network/service on B or C, prioritizing the node with newer, safe data.
2. Check logs to rule out split-brain.
3. Avoid force reconfig until member data states are understood.
4. Once votes are restored, wait for election to finish.
5. Verify application writes and `w:majority`.
6. Recover the remaining member in a safe sequence.

### 51.2. Do Not Arbitrarily "Lower Majority"

Specialized DR procedures exist when voting members are permanently unrecoverable, but forcing configuration carries data-loss risk and must follow MongoDB documentation, backup/restore assessment, and escalation.

---

## 52. Scenario C: PSA Leaves Primary and Arbiter, Missing Secondary

```text
A PRIMARY    data
B SECONDARY  DOWN
C ARBITER    vote only
```

A+C retain an election majority, but lack data-bearing acknowledgment for `w:"majority"`.

### 52.1. Symptoms

- Driver can still discover the primary.
- `w:1` writes can succeed.
- `w:"majority"` writes block/time out.
- Write durability is degraded.
- Monitoring may not report "no primary".

### 52.2. Remediation

Restore B as soon as possible. Do not downgrade write concern to `w:1` purely to "turn dashboards green" if the business requires majority durability; that is a data-risk decision requiring approval.

---

## 53. Scenario D: Secondary Offline 12 Hours, 2-Hour Window Remaining

```text
C last applied:  00:00
A oplog oldest:  10:00
A oplog latest:  12:00
```

C needs history from 00:00–10:00 that the source no longer retains.

### 53.1. Actions

1. Confirm C is genuinely too stale.
2. Check whether any other source still holds enough oplog history.
3. Do not keep retrying incremental replication forever.
4. If no history exists, plan rebuild/initial sync.
5. Protect majority on A/B.
6. Secure backups and approval before removing any local data on C.
7. Resize oplog/tune capacity to reduce recurrence risk.

### 53.2. No Miracles

Growing the oplog from 2 GiB to 200 GiB at 12:00 will not recreate entries that disappeared before 10:00.

---

## 54. Scenario E: Lag After Bulk Updating Millions of Documents

```text
Normal oplog window: 20 hours
During migration:    3 hours
B replication lag:   2 hours and growing
```

### 54.1. Risk

If the bulk update keeps generating oplog entries at high speed, B can lose the history needed to catch up.

### 54.2. Actions

- Throttle/pause controllable bulk operations.
- Inspect B's I/O, CPU, and network.
- Track the actual oplog window over time.
- Increase oplog capacity if feasible and appropriate.
- Chunk the migration job smaller with rate limiting.
- Do not spin up more workers to "finish faster" while the source/replicas are overloaded.

---

## 55. Scenario F: Delayed Secondary Reports Exactly One Hour of Lag

```text
D SECONDARY
secondaryDelaySecs: 3600
Observed lag:        ~3600 seconds
```

This can be **intended behavior**.

### 55.1. Proper Monitoring

- Separate deliberate delay from unexpected extra lag.
- Alert only if actual lag exceeds configured delay plus headroom.
- Ensure oplog window > configured delay + outage/catch-up budget.
- Ensure the member has sufficient disk and the source holds required history.

### 55.2. Do Not "Fix" by Removing Delay Without Approval

A delayed member may serve a logical corruption recovery use case. Changing this config strips away a logical protection layer.

---

## 56. Scenario G: `writeConcern` Timeout After Election

A write was waiting for majority acknowledgment when the primary changed.

### 56.1. Possible Outcomes

- Write was not applied.
- Write applied, but the response was lost.
- Write applied and later replicated.
- Write had not reached the requested durability level at timeout time.

### 56.2. Application Responsibilities

- Use a stable operation ID.
- Re-read the outcome once topology stabilizes.
- Retry according to driver error labels/semantics.
- Never repeat non-idempotent side effects.
- Monitor write concern error/timeout rates.

### 56.3. Do Not Assert a Timeout Guarantees Data Was Lost

Diagnose based on the actual outcome and commit state, not solely the exception string.

---

## 57. Scenario H: Initial Sync Overloads the Source

Node C is being rebuilt and pulls data from A. B is healthy, but A's disk/CPU is near limits.

### 57.1. Symptoms

- A read IOPS rises.
- A write latency/p99 spikes.
- B's lag starts rising.
- C's initial sync drags on.
- Oplog window shrinks.
- Application errors increase.

### 57.2. Remediation

- Throttle non-essential workloads.
- Schedule during lower-traffic windows if possible.
- Consider another healthy sync source per procedure.
- Add resource capacity.
- Evaluate supported clone/backup-based resync options.
- Do not restart B while B is a critical majority data copy.

---

# PART IX — ALERTING, PREVENTION, AND EXERCISES

## 58. Metrics to Monitor Continuously

| Metric | Meaning |
| --- | --- |
| Replica set PRIMARY availability | Whether a valid leader exists |
| Voting members reachable | Whether election majority exists |
| Data-bearing members healthy | Durability/replication capability |
| Replication lag per member | Sync delay per secondary |
| Lag growth rate | Risk of falling irreparably behind |
| Oplog window per sync source | History headroom |
| Oplog generation rate | Risk of window shrinkage from write bursts |
| Majority commit point lag | Write durability/flow control |
| Write concern timeouts | Majority acknowledgments missing deadline |
| Election/stepdown frequency | Topology instability |
| Network RTT/errors | Sync fetch reliability |
| Disk free/IOPS/latency | Apply and storage health |
| CPU/cache pressure | Secondary apply bottleneck |
| Flow control engaged | Primary throttled by replication |
| Initial sync progress/retries | Recovery health |
| Change Stream consumer lag | Oplog-dependent consumers |
| Client server selection errors | Application impact |

### 58.1. Alert on Headroom

Example policy:

```text
warning:
  replication lag > 2 min sustained
  or oplog window < 12 hours

critical:
  no primary
  or majority unavailable
  or lag approaches remaining oplog window
```

These thresholds are **only examples**. A 24/7 payment system with strict DR policies needs different thresholds than a reporting-only environment.

### 58.2. Lag/Window Ratio

An early warning indicator:

```text
replication lag / oplog window
```

Example:

```text
lag = 90 min
window = 120 min
ratio = 75%
```

The secondary is nearing the danger boundary if lag continues rising. Consider the window's rate of change, outage budget, and sync chain rather than relying on a static ratio alone.

---

## 59. Three-Question Runbook

When an alert fires, ask:

**Question 1: Do we have a PRIMARY and election majority?**

- No → restore network/services/voting members safely first.
- Yes → proceed to Question 2.

**Question 2: Are majority writes and data-bearing members healthy?**

- No → resolve write concern/data copy availability, especially in PSA.
- Yes → proceed to Question 3.

**Question 3: Does the lagging secondary still have the history it needs?**

- Yes → fix slow fetch/apply and workload pressure.
- No → verify staleness, look for a source with history, or follow initial sync procedures.

Flowchart:

```text
Replication incident
        |
        v
Primary + election quorum?
        |
       / \
     No   Yes
     |     |
Restore    v
healthy   Majority write concern healthy?
voters     |
          / \
        No   Yes
        |     |
   Repair data-bearing
   availability
              |
              v
       Lagging member needs history?
              |
             / \
          Yes   No
           |     |
      Fix fetch/apply
      bottleneck      Evaluate alternate
                      source / initial sync
```

---

## 60. Practical Incident Checklist

- [ ] Record start time, blast radius, and business impact.
- [ ] Know topology, votes/priority, and failure domains.
- [ ] Capture `rs.status()` from a reachable member.
- [ ] Determine current primary/election quorum.
- [ ] Distinguish data-bearing members from arbiters.
- [ ] Check `w:"majority"` and write concern timeouts.
- [ ] Identify hidden/delayed secondaries.
- [ ] Record replication lag **per member**.
- [ ] Inspect `syncSourceHost` and network/DNS/TLS.
- [ ] Inspect CPU, disk free space, IOPS, RAM/cache.
- [ ] Check running bulk jobs/DDL/backups.
- [ ] Measure actual oplog window.
- [ ] Compare secondary latest applied against oldest retained oplog.
- [ ] Never assume every RECOVERING node is too stale.
- [ ] Never run force reconfig as a first step.
- [ ] Never delete dbPath without verifying node, backup, and approval.
- [ ] Preserve majority before every restart/resync.
- [ ] Rebuild only one secondary at a time within capacity.
- [ ] Verify data source and adequate oplog history.
- [ ] Never assume resizing the oplog revives truncated history.
- [ ] After recovery, verify write concern and app reads/writes.
- [ ] Monitor majority commit point and oplog headroom.
- [ ] Update backup/recovery plans and alert thresholds.

---

## 61. Lab Exercise: Observing Lag on an Isolated Replica Set

**Perform only in an isolated test environment**, never in production.

Assume three `mongod` nodes running in replica set `rs0` with hostnames reachable by one another:

```javascript
rs.initiate({
  _id: "rs0",
  members: [
    { _id: 0, host: "mongo-a:27017", priority: 2 },
    { _id: 1, host: "mongo-b:27017" },
    { _id: 2, host: "mongo-c:27017" }
  ]
});
```

This is a topology example only; it omits TLS/keyfile/auth and network isolation required in real deployments. Never expose unauthenticated MongoDB to the Internet.

### 61.1. Generate Moderate Writes

On the lab primary:

```javascript
const lab = db.getSiblingDB("replication_lab");
lab.events.createIndex({ createdAt: 1 });

for (let i = 0; i < 1000; i++) {
  lab.events.insertOne({
    sequence: i,
    createdAt: new Date(),
    payload: "example"
  });
}
```

### 61.2. Inspect Status

```javascript
rs.status();
rs.printReplicationInfo();
rs.printSecondaryReplicationInfo();
```

### 61.3. Simulate Stopping One Secondary in the Lab

In the test environment, you can stop **one** secondary, run additional writes on the primary, then restart it and observe catch-up. Do not stop multiple members simultaneously unless deliberately testing quorum loss.

### 61.4. Takeaways

- Lag increases while the secondary is offline.
- Upon restart, it can catch up if history remains.
- If offline too long and oplog history is lost, incremental catch-up fails.
- Rebuilding requires a safe procedure, not merely increasing network timeouts.

---

## 62. Quorum Loss Lab: Controlled Demonstration

In a three-voting-member lab replica set:

1. Ensure A is primary and B/C are secondaries.
2. Capture a baseline `rs.status()`.
3. Stop B and observe A/C still maintain majority.
4. Stop C **only in the lab**, and observe primary/writes becoming unavailable per election rules.
5. Restart one healthy member.
6. Wait for election and confirm `PRIMARY` returns.
7. Start the remaining member.
8. Compare logs and election events.

### 62.1. Lab Safety

- No production data.
- Snapshots/fixtures available to reset.
- Network/service operations controlled by the test environment.
- Never use `force:true` to force a primary.
- Never delete data directories.

---

## 63. Exercise 1 — Lag or Stale?

```text
Primary oldest oplog:   10:00
Primary latest oplog:   14:00
Secondary latest:       13:45
```

**Question:** Can the secondary catch up from currently retained history?

**Answer:** By simple timeline comparison, 13:45 is inside the 10:00–14:00 window; incremental catch-up may still be possible. Check history chain, sync source, health, and logs—not timestamps alone.

---

## 64. Exercise 2 — Already Too Stale

```text
Primary oldest oplog:   12:00
Secondary latest:       08:00
```

**Answer:** There is a missing gap from 08:00–12:00 unless another source still holds that history. Growing the oplog now will not recover old entries; evaluate supported initial sync/restore procedures.

---

## 65. Exercise 3 — Majority of 5 Voters

A replica set has 5 voters; 2 members are down.

**Answer:** 3/5 remain, meeting election majority by vote count provided connectivity and candidate eligibility are also satisfied.

---

## 66. Exercise 4 — Only 2/5 Remaining

5 voters, 3 members down.

**Answer:** Only 2/5 remain, insufficient majority to sustain or elect a primary normally.

---

## 67. Exercise 5 — PSA

Primary + arbiter are up; the data-bearing secondary is down.

**Question:** Can there still be a primary? Is `w:"majority"` guaranteed to succeed?

**Answer:** Election majority and a primary can still exist. However, the arbiter stores no data to acknowledge writes; majority write concern can block/time out with only one data-bearing member up.

---

## 68. Exercise 6 — Hidden Member

A secondary has `hidden:true, votes:1, priority:0`.

**Answer:** It is ineligible to become primary and excluded from normal client reads, yet still contributes a vote in elections. Do not omit it from quorum math.

---

## 69. Exercise 7 — Delayed Member

Lag is 3600 seconds, configured with `secondaryDelaySecs:3600`.

**Answer:** This may be intentional lag. Alert on excess lag/health and oplog window rather than forcing the member to catch up immediately.

---

## 70. Exercise 8 — Oplog Size

Oplog is 30 GiB, average rate 5 GiB/hour, peak 15 GiB/hour.

**Answer:** Estimated window is about 6 hours normally and about 2 hours at peak, before factoring compression/retention/overhead. Size for worst-case load and headroom.

---

## 71. Exercise 9 — Flow Control

Primary latency rises at the same time secondaries lag.

**Answer:** Likely related to flow control/majority commit pressure. Inspect `serverStatus().flowControl`, replication lag, disk/network, and workload; do not disable flow control blindly.

---

## 72. Exercise 10 — Write Concern Timeout

Application receives a timeout after `insertOne` with `w:majority`.

**Answer:** This is not proof that the insert was never applied. Use a stable `_id`/idempotency key, verify outcome, and retry properly by semantics without duplicating payment/email calls.

---

## 73. Exercise 11 — Secondary `RECOVERING`

A node is `RECOVERING`, and the team wants to delete `dbPath`.

**Answer:** Wrong without finding root cause first. It might be recovering, rolling back, running initial sync, or hitting disk errors; inspect logs and oplog boundaries and protect data/backups before destructive recovery.

---

## 74. Exercise 12 — Multiple Secondaries Lagging

Both B and C lag after a large bulk migration.

**Answer:** Check primary write burst, oplog window, each secondary's throughput, shared network, and resource pressure. Rate-limiting the migration and increasing headroom may be needed.

---

## 75. Exercise 13 — Only One Secondary Lagging

B has high lag while C has none.

**Answer:** Prioritize node-specific CPU/disk/network/source issues on B before altering primary configuration.

---

## 76. Exercise 14 — Quorum and Network Faults

A can reach B, but B cannot reach A; C is down.

**Answer:** Do not rely on one-way ping; verify bidirectional TCP/DNS/TLS/heartbeat. Elections and replication fail without complete connectivity.

---

## 77. Exercise 15 — Resize Oplog

A secondary has lost 8 hours of history. An operator grows the oplog from 10 to 100 GiB.

**Answer:** This does not restore old history. Initial sync or an alternate source with full history is needed; growing the oplog only helps future retention.

---

## 78. Exercise 16 — Initial Sync During Peak

Primary CPU/disk is at 95%, and one secondary needs initial sync.

**Answer:** Carefully consider timing/capacity and sync source, as initial sync puts heavy load on the source/replica set. Do not start blindly during severe load.

---

## 79. Exercise 17 — Reading from Secondaries

The app just wrote to primary, then read via `secondaryPreferred`, and did not see the record.

**Answer:** Likely caused by lag/read preference. Define read-your-writes requirements and choose appropriate read concern/read preference/session handling.

---

## 80. Exercise 18 — Loss of Primary

The Java Driver cannot find a primary and `serverSelectionTimeout` triggers.

**Answer:** The driver cannot create quorum on its own. Restore members/election and handle errors/retries in the application.

---

## 81. Exercise 19 — Force Reconfig

During an outage, someone suggests running `rs.reconfig(config, {force:true})` immediately.

**Answer:** Not a default fix. Carries data divergence/loss risk; follow a supported DR runbook only after assessing latest data, backups, split-brain risk, and approvals.

---

## 82. Exercise 20 — Concurrent Change Risk

During maintenance, the team plans to upgrade all `mongod` nodes, run index builds, run a bulk import, and rebuild a lagging secondary.

**Answer:** Risk increases sharply when combining concurrent changes, obscuring root cause attribution. Phase changes separately, safeguard quorum/oplog headroom, and prepare rollback plans.

---

## 83. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| "Lag 0 means there are no problems." | You still need to check majority commit, write concern, and health. |
| "`SECONDARY` means caught up." | A secondary can still be lagging. |
| "`RECOVERING` means data is corrupted." | Many valid operational causes trigger this state. |
| "A 3-process replica set always has majority 2." | Must inspect actual voting membership. |
| "Hidden nodes don't vote." | Hidden nodes can vote if configured to. |
| "Delayed lag is a bug." | It may be an intentional configuration. |
| "An arbiter is a third data copy." | Arbiters store no data. |
| "If there's a primary, `w:majority` always works." | A PSA set missing its secondary can time out majority writes. |
| "No primary means data is lost." | It may simply be election quorum or network loss. |
| "Restarting the whole cluster fixes lag." | It can break quorum and prolong recovery. |
| "The oplog window is constant." | It shifts with write rates and retention policy. |
| "Doubling oplog size immediately doubles history." | Depends on workload and current entries. |
| "Resizing oplog restores old history." | Already-truncated entries cannot be regenerated. |
| "Too stale just needs a bigger timeout." | Missing oplog history cannot be fixed with timeouts. |
| "An online sync source guarantees enough history." | It must retain the needed entries contiguously. |
| "Initial sync has zero production impact." | It can consume substantial I/O, CPU, and network bandwidth. |
| "Deleting a secondary's `dbPath` is always safe." | Must verify node identity, backups, sync source, and quorum. |
| "Force reconfig has no risk." | It can cause data divergence and rollbacks. |
| "Write concern timeout always means insert failed." | The outcome may simply be uncertain. |
| "Retrying every failed app request is always safe." | External side effects can be duplicated. |
| "Flow control is a bug and should be disabled." | It caps lag; diagnose the underlying bottleneck instead. |
| "Adding an arbiter improves durability." | It adds a vote only, not another data copy. |
| "Adding more workers always lowers lag." | It can intensify primary/oplog pressure. |
| "Lag timestamps are always exact." | Clock skew, idle load, and metric semantics impose limits. |
| "Oplog replaces backups." | Oplog retention is bounded; backups/PITR remain essential. |
| "With quorum intact, a full disk can be ignored." | A disk-full member still threatens consistency and availability. |
| "Secondary reads always see latest data." | Secondary reads can be stale. |
| "Recovery is done once PRIMARY appears." | Writes, lag, app SLOs, and backups still need verification. |

---

## 84. Official Reference Documentation

Use these sources to cross-check version-specific behavior:

1. [Replication — MongoDB Manual](https://www.mongodb.com/docs/manual/replication/) — replica set and replication architecture.
2. [Replica Set Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/) — oplog, retention, and history boundaries.
3. [Replica Set Secondary Members](https://www.mongodb.com/docs/manual/core/replica-set-secondary/) — secondary roles and synchronization.
4. [Replica Set Elections](https://www.mongodb.com/docs/manual/core/replica-set-elections/) — quorum, votes, priority, and elections.
5. [Replica Set Arbiter](https://www.mongodb.com/docs/manual/core/replica-set-arbiter/) — voting member without data storage.
6. [Replica Set Member States](https://www.mongodb.com/docs/manual/reference/replica-states/) — PRIMARY, SECONDARY, RECOVERING...
7. [rs.status()](https://www.mongodb.com/docs/manual/reference/method/rs.status/) — member states, optime, and heartbeats.
8. [replSetGetStatus](https://www.mongodb.com/docs/manual/reference/command/replSetGetStatus/) — response fields.
9. [rs.printReplicationInfo()](https://www.mongodb.com/docs/manual/reference/method/rs.printReplicationInfo/) — oplog window and size.
10. [rs.printSecondaryReplicationInfo()](https://www.mongodb.com/docs/manual/reference/method/rs.printSecondaryReplicationInfo/) — secondary lag output.
11. [Replication Lag](https://www.mongodb.com/docs/manual/tutorial/troubleshoot-replica-sets/#replication-lag) — troubleshooting replication.
12. [replSetResizeOplog](https://www.mongodb.com/docs/manual/reference/command/replSetResizeOplog/) — oplog size and minimum retention.
13. [Replica Set Initial Sync](https://www.mongodb.com/docs/manual/core/replica-set-sync/) — initial sync process.
14. [Resync a Member of a Replica Set](https://www.mongodb.com/docs/manual/tutorial/resync-replica-set-member/) — procedural member rebuild.
15. [Replica Set Maintenance](https://www.mongodb.com/docs/manual/administration/replica-set-maintenance/) — operations and administration.
16. [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — majority, wtimeout, and durability.
17. [Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/) — secondary reads and staleness.
18. [Replication Flow Control](https://www.mongodb.com/docs/manual/tutorial/troubleshoot-replica-sets/#flow-control) — throttling primary during lag.
19. [serverStatus](https://www.mongodb.com/docs/manual/reference/command/serverStatus/) — replication, flow control, and storage metrics.
20. [Java Sync Driver — Connection Options](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/) — topology and timeouts.
21. [Java Sync Driver — CRUD Write Concern](https://www.mongodb.com/docs/drivers/java/sync/current/crud/configure/) — driver write/read concerns.
22. [Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/) — retries and error labels.

**Note:** `rs.status` fields, helper output, dynamic oplog sizing, initial sync, flow control, read/write concern, and driver APIs may vary by MongoDB Server version, FCV, edition, topology, and Atlas vs. self-managed deployment. During production incidents, always follow documentation and approved runbooks for your exact version.

---

## 85. Conclusion

These three problems must be diagnosed separately:

1. **Replication lag:** the secondary can still replicate but cannot keep up with the write stream. Identify bottlenecks across fetch, network, CPU, disk, or workload, and evaluate lag trends against the oplog window.
2. **Quorum loss:** the replica set lacks enough reachable voting members/eligible candidates to elect or sustain a primary; prioritize safely restoring network and members. An arbiter adds a vote, not a data copy or majority write acknowledgment.
3. **Insufficient oplog:** the source no longer holds the history needed for the secondary to catch up; growing the oplog at that stage will not restore old entries. Check alternate sources or execute initial sync/resync per procedure while preserving quorum.

**An effective remediation order is: preserve evidence and data copies → verify quorum/primary → verify majority write concern → measure lag, oplog window, and bottlenecks → recover one member at a time → verify application behavior, durability, and backups.**

**A healthy replica set requires more than enough `mongod` processes running. It needs an electable majority, data keeping pace within oplog retention, and the ability to acknowledge writes at the durability level the application demands.**
