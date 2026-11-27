# Monitoring Replication Lag, Oplog Window, and Member States in MongoDB

## 1. Context: The Cluster Is Running, So How Far Behind Is the Data?

Suppose an e-commerce application writes orders to a MongoDB replica set with one primary and two secondaries. Normally the API writes orders to the primary, while reporting jobs read from a secondary. One day, the system shows these symptoms:

- The API writes successfully, but reporting screens reading from the secondary do not yet see newly created orders.
- One secondary is still running but continuously falling further behind the primary.
- Another secondary just lost network connectivity for 90 minutes.
- The primary is receiving heavy writes, so oplog history only spans about 2 hours.
- When the disconnected secondary returns, it can no longer catch up because the required oplog entries have already been evicted.

This problem cannot be resolved with a single question like "Is MongoDB running?". You must **observe three signal groups simultaneously**:

1. **Replication lag:** how far behind is a secondary compared to its sync source or the primary?
2. **Oplog window:** how long a history of changes does a member retain?
3. **Member state:** is each member `PRIMARY`, `SECONDARY`, `RECOVERING`, `DOWN`, `STARTUP2`, or another state, and are heartbeats still succeeding?

### 1.1. Lesson Objectives

After this lesson, you will be able to:

- Explain the write path through the oplog and the apply process on secondaries.
- Read `rs.status()` and `replSetGetStatus` without conflating health, optime, heartbeat, and member state.
- Use `rs.printSecondaryReplicationInfo()`, `rs.printReplicationInfo()`, and `db.getReplicationInfo()` for their intended purposes.
- Measure and interpret **applied lag**, **oplog window**, and **replication headroom**; detect when a secondary risks becoming **too stale**.
- Distinguish **primary**, **secondary**, **arbiter**, **delayed secondary**, **hidden/non-voting secondary**, and members undergoing **initial sync**.
- Analyze lag caused by network, disk, CPU, cache, write bursts, indexes/maintenance, sync sources, and elections.
- Design dashboards, thresholded alerts, evidence collection, remediation runbooks, and safe hands-on exercises.

### 1.2. Two First Principles

**Zero replication lag does not prove a cluster is healthy.** A member might not be receiving heartbeats, the cluster might have no new writes, or a delayed secondary might display lag in a misleading way.

**A large oplog window does not guarantee a secondary can catch up.** Compare the member's **last applied position** against the **oldest entry still present on its sync source**, while factoring in write rate, apply rate, and how the window shifts during recovery.

## 2. Replica Set Fundamentals and Synchronization Flow

### 2.1. A Simple Replica Set

```text
                     Client / Java Driver
                              |
                      Write to PRIMARY
                              |
                              v
                      +---------------+
                      | mongo-a       |
                      | PRIMARY       |
                      | oplog         |
                      +---------------+
                        /           \
                pull oplog          pull oplog
                      /               \
                     v                 v
             +---------------+ +---------------+
             | mongo-b       | | mongo-c       |
             | SECONDARY     | | SECONDARY     |
             | apply oplog   | | apply oplog   |
             +---------------+ +---------------+
```

In a replica set, writes on the primary are recorded as operation entries in the oplog. Secondaries fetch entries from a sync source and apply them to maintain a replica of the data.

**Replication is fundamentally asynchronous.** The primary accepting a write does not mean every secondary has already applied it at that exact instant.

### 2.2. A Secondary Can Sync from Another Secondary

Another topology:

```text
PRIMARY mongo-a
      |
      v
SECONDARY mongo-b
      |
      v
SECONDARY mongo-c
```

`mongo-c` can select `mongo-b` as its **sync source** via the sync source selection mechanism. Therefore, when analyzing the risk of falling out of the oplog window, do not inspect only the primary's window—check **where each member is actually syncing from**.

### 2.3. Three Stages That Do Not Necessarily Move at the Same Speed

```text
PRIMARY writes oplog
       |
       v
SECONDARY fetches/writes oplog
       |
       v
SECONDARY applies operations
       |
       v
SECONDARY durability/journal and read concern visibility
```

When reading metrics, distinguish **written**, **applied**, and **durable**. Exact exposed fields depend on the MongoDB version; MongoDB 8.0 adds `optimeWritten` and `optimeWrittenDate` in `replSetGetStatus`.

## 3. Three Core Quantities and Their Relationships

### 3.1. Replication Lag

In a basic example, subtract the timestamp of the latest oplog entry applied by the secondary from that applied by the primary:

\[
\text{lag}_{s} \approx
\text{primaryLastAppliedTime} -
\text{secondaryLastAppliedTime}
\]

If the primary is at `12:00:30` and the secondary is at `12:00:10`, the observed difference is roughly **20 seconds**.

This is an **approximation based on oplog progress timestamps**, not a pure network latency measurement; nor does it prove the exact moment a document becomes visible under every read concern.

### 3.2. Oplog Window

The oplog is a capped collection with configured size and retention rules. The oplog window is the time span between the newest and oldest entries **still in a member's oplog**:

\[
\text{oplogWindow} =
\text{newestOplogTimestamp} -
\text{oldestOplogTimestamp}
\]

For example, if the oldest entry is at 08:00 and the newest at 12:00, **window = 4 hours**, even if the current wall clock is 12:10 when the cluster is quiet.

### 3.3. Replication Headroom

When assessing whether a secondary still has time to catch up before required history is evicted, a common observability estimate is:

\[
\text{headroom} \approx
\text{syncSourceOplogWindow} -
\text{secondaryReplicationLag}
\]

Example:

```text
Sync source oplog window = 3 hours
Secondary lag            = 1 hour 30 minutes
------------------------------------------------
Replication headroom     ≈ 1 hour 30 minutes
```

**This is an indicative calculation, not a guarantee of exactly 90 minutes remaining.** Write throughput can surge, the oplog window can shrink, and the sync source can change.

### 3.4. A Quick Reference Table

| Replication lag | Oplog window | Headroom | Initial interpretation |
|---:|---:|---:|---|
| 2 seconds | 72 hours | Very wide | Normal for many workloads |
| 20 minutes | 24 hours | Wide | Lag exists; find cause and trend |
| 20 hours | 24 hours | 4 hours | Risky; prioritize investigation |
| 8 hours | 6 hours | Negative | Possibly outside window; check too stale |
| Unknown | 24 hours | Unknown | Never turn missing metrics into 0 |

Do not adopt the numbers in this table as default SLAs. Thresholds must derive from read requirements, failover targets, downtime tolerance, backups, and workload characteristics.

## 4. Replication Lag Does Not Equal Network Latency

Replication slowness can originate at one or more stages:

```text
PRIMARY writes
   |
   +-- CPU / storage / oplog generation
   |
   v
Network transport
   |
   +-- RTT / packet loss / bandwidth
   |
   v
SECONDARY receives oplog
   |
   +-- fetch / buffer
   |
   v
SECONDARY applies
   |
   +-- disk IOPS, cache, CPU, long operations, concurrency
   |
   v
Read visibility / durability
```

A secondary can have a network RTT of just 2 ms yet suffer 60 seconds of replication lag because its disk lacks the IOPS to apply writes. Conversely, elevated cross-region RTT can drive up lag even when CPU and disk are healthy.

Thus, when investigating, **do not look at `pingMs` alone and conclude the entire replication status**.

## 5. Lab: Preparing Connections Properly

### 5.1. Practice Scope

The commands in this lesson are designed to **read/observe** a replica set you manage or an authorized lab environment.

Example connection string:

```bash
mongosh "mongodb://mongo-a.example.internal:27017,mongo-b.example.internal:27017,mongo-c.example.internal:27017/?replicaSet=rsLab&tls=true" --tlsCAFile /secure/certs/ca.pem --username monitor_lab --authenticationDatabase admin --password
```

Hosts, TLS certificates, and usernames are placeholders, not a live environment. Use a least-privilege monitoring account such as `clusterMonitor` where compatible with the commands and RBAC policy.

### 5.2. Commands Have Different Scopes

| Command | Purpose | Where to run? |
|---|---|---|
| `rs.status()` | Replica set and member status | Recommended from primary for cluster-wide view |
| `db.adminCommand({replSetGetStatus:1})` | Underlying command wrapped by `rs.status()` | Connected member |
| `rs.printSecondaryReplicationInfo()` | Text lag report | Recommended from primary |
| `rs.printReplicationInfo()` | Current member oplog report | Connect directly to target member |
| `db.getReplicationInfo()` | Structured oplog details | Connect directly to target member |
| `rs.conf()` | Voting, priority, delay, hidden config | Appropriate privilege; read only, do not reconfig |
| `db.serverStatus()` | Current member metrics | Current member |
| `db.hello()` | Server role/hello info | Current connected member |

**No single command answers every question.** `rs.status()` describes health and member progress; `db.getReplicationInfo()` returns the oplog window of the connected node rather than automatically aggregating the entire replica set.

### 5.3. Notes on MongoDB Atlas

On Atlas, **Replication Lag**, **Replication Oplog Window**, **Replication Headroom**, and **Oplog GB/Hour** appear in the cluster charts and alerts for supported deployments. Some `mongosh` commands are unavailable or restricted on M0/Flex; use Atlas metrics/APIs matching your deployment tier.

Never grant excessive admin privileges just to run a monitoring command.

## 6. `rs.status()`: Where Investigation Begins

In `mongosh` connected to the replica set:

```javascript
const status = rs.status();
printjson(status);
```

`rs.status()` is a wrapper for:

```javascript
db.getSiblingDB("admin").runCommand({
  replSetGetStatus: 1
});
```

### 6.1. Important Fields

Depending on version and configuration, the output contains:

```javascript
{
  set: "rsLab",
  date: ISODate("2026-11-14T12:00:40Z"),
  myState: 1,
  term: NumberLong("9"),
  members: [
    {
      _id: 0,
      name: "mongo-a.example.internal:27017",
      health: 1,
      state: 1,
      stateStr: "PRIMARY",
      optimeDate: ISODate("2026-11-14T12:00:30Z")
    },
    {
      _id: 1,
      name: "mongo-b.example.internal:27017",
      health: 1,
      state: 2,
      stateStr: "SECONDARY",
      optimeDate: ISODate("2026-11-14T12:00:28Z"),
      pingMs: NumberLong("2"),
      syncSourceHost: "mongo-a.example.internal:27017"
    },
    {
      _id: 2,
      name: "mongo-c.example.internal:27017",
      health: 1,
      state: 2,
      stateStr: "SECONDARY",
      optimeDate: ISODate("2026-11-14T11:58:10Z"),
      pingMs: NumberLong("3"),
      syncSourceHost: "mongo-b.example.internal:27017"
    }
  ],
  ok: 1
}
```

This is an **illustrative abbreviated output**, not the full JSON returned across every version.

### 6.2. Do Not Confuse `myState` and `members[n].state`

`myState` is the state of the **member executing the command**. `members[n].state` is the state of **each member from the queried node's perspective**.

When connected to the primary, you typically see:

```text
myState = 1 (PRIMARY)
members[0].state = 1
members[1].state = 2
members[2].state = 2
```

If querying a secondary, `myState` can be `2`. During a network partition, different members' views can diverge.

### 6.3. `health` Is Not Data Freshness

`health: 1` means the member is considered healthy/reachable from the perspective of the node running `status`. It does **not** mean the secondary has applied the latest writes.

`health: 0` indicates the member is unhealthy or unreachable from that perspective; verify heartbeats, network, and logs.

### 6.4. `optimeDate` Is Not `status.date`

`status.date` is when the status report was generated.

`members[n].optimeDate` is the timestamp of the last **applied** oplog entry according to metadata. Never compute:

```text
status.date - secondary.optimeDate
```

and call it replication lag without comparing against the primary. When the cluster has **no new writes**, both primary and secondary have older `optimeDate` values while still being completely caught up.

## 7. Member States: Codes and Meanings

Standard state codes:

| Code | `stateStr` | Operational meaning |
|---:|---|---|
| 0 | `STARTUP` | Node is starting up, not yet an active member |
| 1 | `PRIMARY` | Normally accepts writes for the replica set |
| 2 | `SECONDARY` | Replicating data; can serve reads if configured |
| 3 | `RECOVERING` | Not ready to serve reads; may be recovering |
| 5 | `STARTUP2` | May be performing initial sync or startup transition |
| 6 | `UNKNOWN` | State unknown from other members' view |
| 7 | `ARBITER` | Votes only; holds no copy of the data |
| 8 | `DOWN` | Member unreachable from the current view |
| 9 | `ROLLBACK` | Performing rollback; does not serve normal reads |
| 10 | `REMOVED` | Member removed from the replica set |

### 7.1. Do Not Apply a Rule That "Anything Other Than SECONDARY Is an Error"

`STARTUP2` and `RECOVERING` can be **normal during initial sync or startup**, though prolonged durations warrant investigation. `ROLLBACK` can be a normal recovery step after failover rather than a disk failure.

### 7.2. Arbiters Do Not Have Replication Lag Like Data-Bearing Secondaries

Arbiters do not store data or an oplog; they only participate in elections. **Do not include arbiters in average lag or headroom calculations**, and do not count an arbiter as a data replica for read availability.

### 7.3. Single Primary and Write Authority

A replica set normally has **one primary at a time**. During a network partition, a former primary might briefly believe it is still primary, while majority write concern and election terms govern commit capability—keep this in mind when reading status from different views.

Never rely on status from an isolated node to claim the cluster definitely has a healthy primary.

## 8. Heartbeats, `pingMs`, and Sync Source

### 8.1. Heartbeat Metadata

Common fields in `rs.status().members[]`:

- `lastHeartbeat`: time the last heartbeat was sent from the current view.
- `lastHeartbeatRecv`: time the last heartbeat was received from the peer.
- `lastHeartbeatMessage`: related status or error message.
- `pingMs`: heartbeat round-trip response time, not replication lag.
- `syncSourceHost`: host currently used as the replication source.
- `uptime`: reachable/active duration per field definition.

### 8.2. Interpreting `pingMs`

Example:

```text
pingMs = 5 ms
replicationLag = 40 seconds
```

The network may be fast while the secondary applies writes slowly due to disk or cache pressure. Conversely, higher `pingMs` alone does not prove lag—verify actual replication metrics.

### 8.3. `syncSourceHost` Pinpoints the Bottleneck

With chained replication:

```text
mongo-a PRIMARY
    |
    v
mongo-b SECONDARY lag 2s
    |
    v
mongo-c SECONDARY lag 90s
```

If `mongo-c.syncSourceHost` is `mongo-b`, inspect `mongo-b`'s oplog window, network, and sync serving capacity as well.

Do not assume `mongo-c` is pulling directly from the primary.

## 9. `rs.printSecondaryReplicationInfo()`: Quick Visual Lag Check

Recommended to run **on the primary** for the most up-to-date view:

```javascript
rs.printSecondaryReplicationInfo();
```

Sample output:

```text
source: mongo-b.example.internal:27017
    syncedTo: Sat Nov 14 2026 12:00:28 GMT+0000 (UTC)
    2 secs (0 hrs) behind the primary

source: mongo-c.example.internal:27017
    syncedTo: Sat Nov 14 2026 11:58:10 GMT+0000 (UTC)
    140 secs (0 hrs) behind the primary
```

### 9.1. This Method Does Not Return Stable JSON for Parsing

`rs.printSecondaryReplicationInfo()` **prints a human-readable report**; it does not return a JSON object suitable as a monitoring contract.

For scripts and exporters, use `rs.status()` or the `replSetGetStatus` command to obtain structured data.

### 9.2. Zero or Negative Results When Idle

Per MongoDB documentation:

- When the primary is **idle**, `optimeDate` can age even though secondaries are caught up.
- A **delayed member** can show 0 seconds behind when idle time exceeds `secondaryDelaySecs`.
- Reports can occasionally show **negative lag** because a secondary received a new write before the primary's status updated via heartbeat; this **does not mean the secondary is ahead of the primary**.

Therefore:

```text
Lag = -1s
```

should not appear on a dashboard as "secondary is 1 second ahead of primary" in a causal sense.

### 9.3. Read Lag as a Trend

A single 30-second lag sample is not necessarily severe after a write burst if it quickly returns to 0. However, lag climbing steadily 5 -> 10 -> 30 -> 90 -> 180 seconds signals that **the secondary cannot keep up with the write generation rate**.

Measure **slope**, **duration**, and **workload context**, not just the maximum of one sample.

## 10. Building a Structured Member + Applied Lag Table Yourself

A `mongosh` example run on the primary, reading `rs.status()`:

```javascript
const s = rs.status();
const primary = s.members.find(m => m.stateStr === "PRIMARY");

if (!primary || !(primary.optimeDate instanceof Date)) {
  print("NO_PRIMARY_REFERENCE: cannot calculate lag safely");
} else {
  const referenceMs = primary.optimeDate.getTime();
  const summary = s.members.map(m => {
    const valid = m.optimeDate instanceof Date;
    const rawLagSeconds = valid
      ? (referenceMs - m.optimeDate.getTime()) / 1000
      : null;

    return {
      host: m.name,
      state: m.stateStr,
      health: m.health,
      appliedAt: valid ? m.optimeDate : null,
      lagSeconds: m.stateStr === "SECONDARY"
        ? rawLagSeconds
        : null,
      syncSourceHost: m.syncSourceHost || null,
      pingMs: m.pingMs ?? null
    };
  });

  printjson(summary);
}
```

### 10.1. Why Is an Arbiter's `lagSeconds` Null?

Arbiters store neither data nor an oplog. Even if `optimeDate` were absent or placeholder, subtracting it would produce meaningless numbers.

### 10.2. Why Not Immediately Clamp with `Math.max(0, lag)`?

Negative lag can arise from **unsynchronized view updates**, especially after idle periods or heartbeat timing skew. Monitoring can clamp displayed values to 0 while keeping raw values or quality flags for diagnostics rather than silently hiding anomalies.

### 10.3. This Code Is Only a Snapshot from the Primary

`rs.status()` is a **point-in-time snapshot from one node's perspective**. For certainty during elections or network partitions, gather data from individual members or Atlas events while bounding query frequency and permissions.

## 11. Primary, Secondary, and Optime Types

Important fields in `replSetGetStatus`:

| Field | Interpretation |
|---|---|
| `members[n].optime` | Timestamp/term of the last applied operation |
| `members[n].optimeDate` | Timestamp corresponding to the last applied oplog entry |
| `members[n].optimeDurable` | Operation durable in the journal |
| `members[n].optimeDurableDate` | Timestamp of the durable optime |
| `members[n].optimeWritten` | Latest entry written to the oplog; available in MongoDB 8.0+ |
| `members[n].optimeWrittenDate` | Timestamp of the written optime; MongoDB 8.0+ |
| `optimes.lastCommittedOpTime` | Majority commit point from the member's perspective |
| `optimes.readConcernMajorityOpTime` | Point supporting majority read semantics (when present) |

### 11.1. Applied Differs from Durable

An entry **applied** on a secondary is not automatically **journal-durable**; reads and write concerns enforce different requirements.

### 11.2. Majority Committed Differs from All Secondaries Applied

Write concern `{w: "majority"}` requires acknowledgment from a **majority of eligible voting data-bearing members** per MongoDB semantics, rather than waiting for every secondary.

Example with 3 data-bearing members:

```text
Primary A:    applied at t100
Secondary B:  applied at t100
Secondary C:  applied at t80

Majority point can advance to t100
while C remains behind.
```

Exact durable/majority journal and failover behavior depends on configuration and version. Never substitute "low lag" for checking write concern or the majority commit point.

### 11.3. Term Matters During Elections

`optime.ts` carries a timestamp/increment, whereas `optime.t` is the **election term**. During elections or rollbacks, do not rely solely on `Date` assuming simple linear ordering across all updates.

### 11.4. Do Not Use Host Wall Clock as Primary Optime

If the primary receives no writes for an hour:

```text
Wall clock = 13:00
Primary last applied = 12:00
Secondary last applied = 12:00
```

**Replication lag ≈ 0**, even though `Date.now()-optimeDate` ≈ 1 hour. If a dashboard displays "secondary behind 1 hour" using wall clock time, that metric is wrong.

## 12. What Is the Oplog and Why Is the Window Variable?

The oplog lives in the `local` database, collection `oplog.rs`, on each data-bearing member:

```text
local.oplog.rs

oldest                                            newest
  |                                                 |
  v                                                 v
[op1]-[op2]-[op3]-[op4] ... [opN-1]-[opN]
  ^                                                ^
  08:00                                            12:00

Window = 4 hours
```

The oplog is bounded by configured size and retention rules. As new writes arrive, older entries are gradually truncated once truncation conditions are met.

### 12.1. Oplog Size Does Not Translate Directly into Hours

Suppose an oplog is capped at roughly 10 GiB:

| Oplog write rate | Approximate steady-state window |
|---:|---:|
| 0.5 GiB/hour | 20 hours |
| 1 GiB/hour | 10 hours |
| 2 GiB/hour | 5 hours |
| 5 GiB/hour | 2 hours |

This is an **approximate arithmetic model**, ignoring minimum retention, the majority commit point, individual oplog entry sizes, and workload shape.

The same-sized oplog can retain 4 days during quiet periods yet shrink to just a few hours during a heavy import or bulk update.

### 12.2. Each Member Maintains Its Own Oplog

The primary and each secondary have their own oplog. When measuring windows:

```text
mongo-a  window 72h
mongo-b  window 55h
mongo-c  window 60h
```

These can be three different values. Do not measure only the primary and assume every secondary matches.

### 12.3. Impact on Change Streams

Change Stream resume tokens also depend on accessible oplog history. An overly short oplog window can prevent a paused consumer from **resuming** with an older token.

This is why monitoring the window matters even when no secondary lags: CDC and change-stream processors may require retention longer than maintenance windows.

## 13. `rs.printReplicationInfo()`: Quick Check of Oplog Window

Connect **directly to the target data-bearing member** and run:

```javascript
rs.printReplicationInfo();
```

Illustrative output:

```text
configured oplog size:   10240MB
log length start to end: 86400secs (24hrs)
oplog first event time:  Fri Nov 13 2026 12:00:00 GMT+0000
oplog last event time:   Sat Nov 14 2026 12:00:00 GMT+0000
now:                     Sat Nov 14 2026 12:00:20 GMT+0000
```

### 13.1. How to Read It

- `configured oplog size`: configured oplog size.
- `log length start to end`: time span between the earliest and latest **retained** entries.
- `oplog first event time` and `last event time`: those two timestamps.
- `now`: current shell time, not the newest oplog entry if the cluster is idle.

### 13.2. Prints Text, Not for Script Parsing

`rs.printReplicationInfo()` prints a formatted text report. In scripts, use **`db.getReplicationInfo()`**.

### 13.3. Verify Which Member You Are Measuring

If you connect using a replica set URI and the driver/shell automatically selects the primary, you may accidentally measure the primary when intending to inspect a secondary. For per-node checks, connect directly to the target member with proper privileges and TLS.

## 14. `db.getReplicationInfo()`: Structured Data for Scripts

```javascript
const info = db.getReplicationInfo();
printjson(info);
```

Example:

```javascript
{
  logSizeMB: 10240,
  usedMB: 8710,
  timeDiff: 86400,
  timeDiffHours: 24,
  tFirst: "Fri Nov 13 2026 12:00:00 GMT+0000",
  tLast: "Sat Nov 14 2026 12:00:00 GMT+0000",
  now: "Sat Nov 14 2026 12:00:20 GMT+0000"
}
```

Values are illustrative; certain fields and value formats vary by `mongosh` version.

### 14.1. Fields to Export to Monitoring

| Field | Meaning |
|---|---|
| `logSizeMB` | Configured oplog size |
| `usedMB` | Space currently occupied by entries |
| `timeDiff` | Oldest-to-newest span in seconds |
| `timeDiffHours` | Same span in hours |
| `tFirst` | Timestamp of the earliest retained entry |
| `tLast` | Timestamp of the latest entry |
| `errmsg` | Present if the oplog has no entries yet |

### 14.2. Distinguish `used` and `configured`

`usedMB=8.7GiB` on `logSizeMB=10GiB` does not guarantee "1.3 GiB remains before truncation starts" in every setup. Oplog growth and truncation depend on retention settings and the majority commit point.

### 14.3. Never Replace `timeDiff` with `now - tFirst`

On an idle cluster:

```text
tFirst = 10:00
tLast  = 11:00
now    = 13:00
```

`timeDiff` is **1 hour**, not 3 hours. It measures **the span between two actual operation entries**.

## 15. Connecting Directly to a Member to Inspect Its Oplog

In some tools, a connection string routes to primary or secondary automatically. To target the exact member you want to observe:

```bash
mongosh "mongodb://mongo-b.example.internal:27017/admin?directConnection=true&tls=true" --tlsCAFile /secure/certs/ca.pem --username monitor_lab --password
```

Once connected:

```javascript
printjson(db.hello());
printjson(db.getReplicationInfo());
```

`directConnection=true` pins the connection to the specified host in this example; valid networking, TLS certs, and privileges are still required, and `directConnection` must not be used carelessly as the primary URI for an application requiring replica-set failover.

### 15.1. Not Every Member Has an Oplog

- Data-bearing primary and secondary members have an oplog.
- Arbiters do not store data or an oplog.
- A standalone node outside a replica set will not have `local.oplog.rs`.

If `db.getReplicationInfo()` reports a missing oplog or `errmsg`, never coerce that into a 0-hour window and fire a "0h oplog" alert; classify the member role first.

### 15.2. Raw Oplog Inspection Only When Needed

A **bounded read** example to inspect the first and last entry timestamps:

```javascript
const oplog = db.getSiblingDB("local").getCollection("oplog.rs");

const first = oplog.find({}, { ts: 1, _id: 0 })
  .sort({ $natural: 1 }).limit(1).toArray()[0];

const last = oplog.find({}, { ts: 1, _id: 0 })
  .sort({ $natural: -1 }).limit(1).toArray()[0];

printjson({ first, last });
```

Never run `find().toArray()` across a large oplog just to compute the window. For periodic monitoring exporters, `db.getReplicationInfo()` is generally cleaner.

## 16. Oplog Window, Lag, and Recovery Margin

### 16.1. Secondary Lagging but Still Within the Window

```text
Sync source oplog:
  oldest=08:00 newest=12:00

Secondary last applied:
  10:30

Window = 4h
Lag    = 1h30
Headroom ≈ 2h30
```

The secondary can still fetch and apply subsequent entries, **provided the required entries have not yet been truncated**.

### 16.2. Secondary Lagging Past the Window

```text
Sync source oplog:
  oldest=11:00 newest=12:00

Secondary last applied:
  10:30

Entries after 10:30 may already have been evicted.
```

If the member cannot find the history needed to continue, it can become **too stale** and require **initial sync / resynchronization** following a supported procedure.

### 16.3. "Headroom = Window - Lag" Is an Indicator, Not a Guarantee

Keep three factors in mind:

1. Secondary **lag** based on apply progress.
2. **Window** on the actual sync source.
3. **Rate of progress** on both the source and the secondary.

A secondary with 1 hour of headroom whose apply rate is slower than the write rate will continue falling behind. If write throughput triples, the window can shrink much faster than projected.

### 16.4. Watch Trends

```text
T0: lag 10 min, window 6h, headroom 5h50
T1: lag 20 min, window 4h, headroom 3h40
T2: lag 40 min, window 2h, headroom 1h20
T3: lag 70 min, window 1h30, headroom 20 min
```

Even though lag grew from 40 to 70 minutes, headroom collapsed because **both sides worsened simultaneously**. That is why dashboards must plot them on a shared timeline.

## 17. Oplog Retention and Sizing

### 17.1. Size-Based Default

The oplog is a capped collection with a configured size; once it exceeds the limit and meets truncation rules, MongoDB drops old entries to keep the window near the configured storage cap.

Never assume "10 GiB oplog" equals "24 hours of retention" for every workload.

### 17.2. Minimum Oplog Retention

MongoDB supports configuring a minimum retention period:

```yaml
storage:
  oplogMinRetentionHours: 72
```

MongoDB only removes an entry when **both conditions** are met:

1. The oplog has reached its configured maximum size.
2. The entry is older than the minimum retention period based on the system clock.

Consequently, the oplog **can grow beyond its configured size** to honor the retention floor.

### 17.3. An Unexpected Disk Growth Case

```text
Configured oplog size: 20 GiB
Min retention:          72 hours
Write rate:             2 GiB/hour

72h data volume ≈ 144 GiB
```

This is illustrative arithmetic, not a byte-exact forecast. **Do not set high minimum retention without provisioning disk capacity**: the disk can fill up and hurt availability.

### 17.4. Majority Commit Point

MongoDB may also allow the oplog to exceed its configured size to avoid truncating entries needed for the **majority commit point**. Thus `logSizeMB` is a target size, not always an absolute ceiling on physical usage.

### 17.5. Do Not Change Retention Just to Silence an Alert

Increasing oplog size or minimum retention can be the right fix when **write workload is normal** and the window is simply too narrow for target maintenance/downtime.

However, if a secondary lags due to disk failure, enlarging the oplog only **buys time**—it does not fix apply throughput.

## 18. Inspecting and Adjusting the Oplog on Self-Managed Deployments

### 18.1. Reading Configuration

On an appropriate member:

```javascript
const local = db.getSiblingDB("local");
printjson(local.getCollection("oplog.rs").stats());
```

To check the minimum retention setting when supported:

```javascript
const ss = db.getSiblingDB("admin").serverStatus();
printjson(ss.oplogTruncation?.oplogMinRetentionHours ?? null);
```

### 18.2. `replSetResizeOplog`

On **self-managed** MongoDB, after change approval, this command adjusts size/minimum retention without restarting:

```javascript
// ILLUSTRATION ONLY, DO NOT RUN IN PRODUCTION.
db.adminCommand({
  replSetResizeOplog: 1,
  size: Double(16384),
  minRetentionHours: 72
});
```

Here `size` is in **MB**, and the command applies only to **the connected member**. It does not automatically resize the oplog across all replica set members.

### 18.3. Two Critical Warnings

- **`replSetResizeOplog` is not supported on Atlas clusters**; Atlas provides UI/API controls for minimum oplog window depending on deployment tier.
- **Reducing size or retention can truncate entries immediately**, preventing lagging secondaries or change-stream consumers from resuming. This is a high-risk change requiring planning and verification.

### 18.4. Resource Characteristics of Resizing

`replSetResizeOplog` may acquire an exclusive lock on the oplog during execution. Shrinking the size does not necessarily return disk space immediately to the OS.

Never schedule an oplog resize during peak hours without consulting the relevant documentation, resource headroom, and recovery plan.

## 19. Detecting Members That Are Too Old: `tooStale`

In `replSetGetStatus`, a status can show:

```javascript
{
  tooStale: true,
  // ...
}
```

This indicates the member fell too far behind and is stuck in `RECOVERING` because required oplog history is no longer available under the replication mechanism.

### 19.1. Never Try to Fix by Forcing the Member to Become Primary

A `tooStale` secondary cannot be "fixed" by forcing an election or `stepUp`. Promoting stale data as the write source poses severe data-integrity risks.

### 19.2. Remediation Steps

1. Verify the issue on the affected member and its sync source.
2. Check logs for `RECOVERING`/`too stale` and inspect oplog windows.
3. Confirm the replica set still has a healthy primary and sufficient healthy members.
4. Plan **initial sync / resync** per MongoDB documentation for your environment.
5. Estimate disk space, disk I/O, network bandwidth, and sync duration.
6. Monitor `STARTUP2` -> `RECOVERING` -> `SECONDARY`.
7. Never delete data directories or run `rs.reconfig()` impulsively.

### 19.3. `tooStale` Is Not Every `RECOVERING` Case

`RECOVERING` can also appear during startup, rollback, or transient transitions. Only conclude `tooStale` when **status, logs, and metrics** corroborate it—not from `stateStr` alone.

## 20. Delayed Secondaries: Intentional Lag

A replica set can configure a **delayed secondary**, often to retain a time-delayed copy to aid recovery from certain operational mistakes.

Example member configuration:

```javascript
{
  _id: 2,
  host: "mongo-c.example.internal:27017",
  priority: 0,
  hidden: true,
  secondaryDelaySecs: 3600
}
```

This is an illustrative `rs.conf().members[]` fragment, **not advice to modify production config**.

### 20.1. Intentional Does Not Mean Unmonitored

With a 1-hour delay, ~1 hour of observed lag matches the design. Still:

- The member still needs healthy networking, disk, and replication.
- The oplog window must cover the delay plus downtime/catch-up margin.
- It can fall **even further** behind the configured delay due to faults.
- When the primary is idle, `rs.printSecondaryReplicationInfo()` may display 0 seconds even though delay is configured.

### 20.2. Thresholds Must Match Member Role

Do not apply a blanket `lag > 30s` alert to a 3600s delayed secondary. You can compute:

```text
effectiveExcessLag ≈ measuredLag - configuredDelay
```

only as a supplemental signal alongside heartbeats, state, headroom, and measurement conditions. On a low-write primary, raw lag does not reflect steady delay; evaluate in context.

### 20.3. Delayed Secondaries Do Not Replace Backups

For mistakes discovered later than the delay window, or if an attacker has permissions to delete across the replica set, a delayed member cannot guarantee recovery. Backups, PITR, and access controls remain essential.

## 21. Hidden/Non-Voting Members and Voting Eligibility

### 21.1. Hidden Secondary

A hidden member replicates data but is omitted from the member list normal drivers pick for reads. It remains useful for backups, reporting, or specialized workloads.

If a hidden member lags and is not on the API serving path, user impact differs from a read-serving secondary, yet **lag must still not be ignored**.

### 21.2. Priority and Votes

In `rs.conf()`:

- `priority` influences preference to become primary.
- `votes` determines voting rights in elections.
- `hidden` controls visibility to clients.
- `secondaryDelaySecs` configures replication delay.
- `arbiterOnly` marks an arbiter.

These fields describe **intended roles**. `rs.status().stateStr` reports **current operational state**.

### 21.3. Do Not Count Every Secondary as a Failover Candidate

A `priority: 0` member cannot become primary through normal elections. Delayed and hidden members are typically configured not to run for primary.

Therefore, a "healthy" secondary does not automatically mean the replica set has another viable primary candidate.

## 22. Elections: Reading Status During Primary Transitions

### 22.1. Signals

When a primary goes down or steps down, you may observe:

- The former primary transitioning from `PRIMARY` to `SECONDARY`, `RECOVERING`, or unreachable.
- An eligible secondary being elected `PRIMARY`.
- `term` incrementing.
- Drivers detecting a topology change.
- Some write operations retrying or returning transient errors.

### 22.2. Do Not Rely on a Single Status Sample for Long-Term Conclusions

Within 1–2 heartbeat intervals, status reports can show a stale view. You should:

1. Fetch status from the new primary once elected.
2. Inspect election logs and events.
3. Verify majority availability.
4. Check `term` and `optimes`.
5. Review driver retries and application error rates.

### 22.3. What Should Never Be Automated Blindly?

Never build a monitoring script that reacts to a 5-second primary absence by calling:

```javascript
rs.stepDown();
rs.reconfig();
rs.remove();
```

These are **topology-mutating commands**, not observation commands. Calling them improperly can prolong outages or break quorum.

## 23. Initial Sync: A Special Member Phase

A new member or one needing resynchronization goes through:

```text
STARTUP
   |
   v
STARTUP2 (initial sync)
   |
   v
RECOVERING
   |
   v
SECONDARY
```

### 23.1. What to Monitor?

- Member state and duration spent in `STARTUP2`.
- Volume of data and indexes being copied/built.
- Oplog entries accumulating to apply during cloning.
- Disk capacity, write rate, and network bandwidth.
- `initialSyncStatus` fields when present.
- Progress/error logs and sync source selection.

### 23.2. `initialSyncStatus` Is Not Always Present

In `replSetGetStatus`, `initialSyncStatus` appears only when relevant to the initial sync state/method. A normally running member will not include this field.

Monitoring must treat `field missing` as "not applicable / unavailable," not as an error.

### 23.3. Watch the Load Imposed by Initial Sync

Initial sync pulls heavy data from the sync source and generates substantial I/O. Adding multiple members simultaneously to an already busy cluster increases the risk of:

- Network saturation.
- Disk/cache pressure on the sync source.
- An oplog window too short to retain changes throughout the clone.

Plan capacity and scheduling rather than resyncing multiple secondaries concurrently without justification.

## 24. Rollback and Replication Lag After Failover

### 24.1. What Is Rollback?

When a former primary accepted writes that never became part of the new primary's committed history, the former primary may need to roll back those divergent writes when rejoining the replica set.

### 24.2. The `ROLLBACK` State

`ROLLBACK` requires investigation. It is very different from "a secondary is simply 10 seconds behind."

Check:

- Election timeline.
- Write concern used by the application.
- Rollback logs and metadata.
- Majority commit point.
- Business impact if writes were acknowledged without reaching majority.

### 24.3. Do Not Conclude Data Loss from Lag Metrics Alone

High lag does not automatically prove lost writes. Conversely, low lag does not replace **durability and write concern guarantees**.

Correlate:

```text
writeConcern + majorityCommit + memberState + optime + election logs
```

to assess risk accurately.

## 25. Diagnosing Lag: Categorizing Root Causes

| Category | Symptoms | Metrics / investigation |
|---|---|---|
| Network | Rising RTT/packet loss, heartbeat errors | `pingMs`, network monitoring, logs |
| Disk/I/O | Slow secondary apply, high write latency | Disk latency/IOPS/queue, storage metrics |
| CPU/cache | Cache eviction or CPU near saturation | `serverStatus()`, WiredTiger cache, CPU |
| Write burst | Sharp surge in primary oplog generation | Oplog GB/hour, opcounters, load timeline |
| Long-running ops | Operations competing for resources | Current ops, profiler, slow logs |
| Sync source | Down/slow source or suboptimal chaining | `syncSourceHost` and source health |
| Oplog window | Window shrinking fast, headroom falling | `getReplicationInfo()`, Atlas metrics |
| Initial sync | Copying/building indexes/applying | `STARTUP2`, `initialSyncStatus`, logs |
| Election/rollback | Term/state changes, retried writes | `rs.status()`, log events |
| Capacity/config | Full disk, underprovisioning | Atlas/OS storage, CPU, cache, network |

### 25.1. Finding the "Starting Point" on the Timeline

Suppose:

```text
09:00  batch import deployed
09:03  oplog GB/hour rises
09:05  secondary disk IOPS hits ceiling
09:07  lag begins climbing
09:15  headroom drops to 20 minutes
```

Looking only at lag at 09:15 shows the symptom. The timeline reveals **write burst + secondary disk bottleneck** as the likely cause.

### 25.2. Do Not Confuse Correlation with Causation

If primary CPU rises alongside secondary lag, that alone does not prove "high primary CPU caused secondary lag." Inspect source throughput, network, apply metrics, and workload shifts.

## 26. Diagnosing Network Lag and Heartbeats

### 26.1. Gathering Evidence

On authorized hosts:

- RTT, packet loss, and bandwidth between members.
- DNS resolution, firewall, or security group changes.
- TLS certificate expiration and authentication failures.
- `lastHeartbeat`, `lastHeartbeatMessage`, `pingMs`.
- Connection resets and retries in logs.

### 26.2. Geography and Multi-Region

A replica set spanning multiple regions has varying RTTs. If a secondary sits far from the primary, lag can grow during write bursts without indicating infrastructure failure.

Still, persistent packet loss or constrained bandwidth can keep oplog fetching from keeping pace.

### 26.3. Do Not Rely on ICMP `ping` Alone

ICMP `ping` and MongoDB heartbeats traverse different layers and behaviors. Network diagnostics must verify the real endpoint, TLS, and application-level metrics when available.

## 27. Diagnosing Disk, WiredTiger Cache, and Oplog Apply

### 27.1. Secondary Resources

If the secondary's disk I/O is saturated:

```text
Primary: 500 writes/s
Secondary disk: effectively handles only 350 ops/s

Backlog grows -> lag grows
```

Remediation may include upgrading IOPS/storage tier, reducing contention from reporting/backups, or optimizing the workload.

### 27.2. WiredTiger Cache

On a member, inspect:

```javascript
const ss = db.serverStatus();
printjson(ss.wiredTiger?.cache?.[
  "pages evicted by application threads"
] ?? null);
```

In `mongosh` JavaScript, access property names containing spaces via bracket notation:

```javascript
const pagesEvictedByApp = db.serverStatus()
  .wiredTiger?.cache?.["pages evicted by application threads"];

printjson(pagesEvictedByApp);
```

If this metric **climbs** steadily, cache pressure may be forcing application threads to assist eviction. A single non-zero total is merely cumulative; measure **the rate of increase over time**.

### 27.3. Disk Metrics

Track:

- Disk latency (read/write).
- Disk IOPS vs. quota.
- Disk queue depth.
- Disk used/free and growth rate.
- WiredTiger cache usage and eviction.
- Competing secondary read workloads.

### 27.4. Do Not Arbitrarily Tweak Internals

Server parameters governing concurrency, flow control, or oplog sizing carry complex trade-offs. Never change production settings based on a blog or forum post without benchmarking and checking your exact version.

## 28. Flow Control and Majority Lag

MongoDB includes **flow control** to throttle write rates so majority-committed lag does not fall too far behind.

On the primary:

```javascript
const flow = db.serverStatus().flowControl;
printjson(flow);
```

Some versions expose:

```javascript
db.serverStatus().flowControl?.isLagged
```

### 28.1. When Should You Inspect Flow Control?

If you observe:

```text
replication lag rising
write latency rising
flowControl engaged
```

flow control may be **a symptom of the system throttling writes to protect replication**, rather than the root cause of the lag.

### 28.2. Do Not Blindly Disable Flow Control

Disabling or relaxing flow control may let the primary accept writes faster in the short term while pushing secondaries even further behind and exhausting headroom.

Preferred steps:

1. Identify which member is lagging.
2. Measure apply throughput, disk, and cache.
3. Throttle write bursts or add capacity if warranted.
4. Re-check majority lag and write latency.
5. Evaluate flow control parameter changes only through formal engineering review.

## 29. Tracking Oplog GB/Hour and Write Pressure

### 29.1. Why Does Oplog GB/Hour Matter?

The oplog window responds directly to the volume of changes written over time. When oplog generation speeds up:

```text
oplogSize ≈ 20 GiB
oplogRate ≈ 1 GiB/hour -> estimated 20h
oplogRate ≈ 5 GiB/hour -> estimated 4h
```

This is only a steady-state estimate; retention, majority commit constraints, and transaction overhead can alter actuals.

### 29.2. Bulk Writes and Deletes

A cleanup job:

```javascript
db.events.deleteMany({ createdAt: { $lt: cutoffDate } });
```

can generate a huge volume of oplog entries and spike oplog generation rate. Never run this on production just to test lag.

### 29.3. Controlling Batches

For legitimate bulk operations:

- Batch by time range or ID.
- Ensure filters use an appropriate index.
- Monitor oplog rate, lag, and headroom while running.
- Pause or reduce concurrency when hitting guardrails.
- Schedule during lower-traffic windows.

Do not crank up bulk concurrency until I/O saturates and a `tooStale` alert fires.

## 30. Observability on MongoDB Atlas

Per current Atlas documentation, key metrics and alerts include:

| Metric | Meaning |
|---|---|
| **Replication Lag** | Approximate time a secondary trails the primary |
| **Replication Oplog Window** | Time span of retained oplog history |
| **Replication Headroom** | Difference between sync source window and replication lag |
| **Oplog GB/Hour** | Rate of oplog data generation |
| **Disk IOPS/Latency** | Apply capacity |
| **CPU/WiredTiger Cache** | Compute and cache pressure |
| **Network** | Bandwidth and connection throughput |
| **Election/Availability** | Primary changes or unhealthy members |

### 30.1. Inspect Every Node Individually

Do not rely solely on a cluster-wide aggregated chart. One secondary lagging by 10 minutes can be masked by two members at 0 seconds if a dashboard averages them.

Group by:

```text
project / cluster / replicaSet / host / state / region / role
```

### 30.2. Metric Granularity

Atlas collects metrics at specific granularities; per monitoring documentation, some Replication Lag and Headroom metrics are collected roughly every **85 seconds** in standard configurations.

This means:

- A brief few-second spike may not show up clearly.
- Atlas alerts may trail real-time console snapshots slightly.
- Use explicit collection intervals and aggregation windows.

### 30.3. M0/Flex and Command Limits

Free/shared tiers do not support all the commands and metrics available on dedicated clusters. Do not assume `local.oplog.rs` readability on self-managed deployments carries over to shared/free deployments.

## 31. Designing Dashboards

### 31.1. Replica Set Overview

```text
┌───────────────────────────────────────────────┐
│ Replica Set: rsLab                            │
├─────────────┬───────────┬──────────┬──────────┤
│ Member      │ State     │ Lag      │ SyncSrc  │
├─────────────┼───────────┼──────────┼──────────┤
│ mongo-a     │ PRIMARY   │ —        │ —        │
│ mongo-b     │ SECONDARY │ 2 s      │ mongo-a  │
│ mongo-c     │ SECONDARY │ 140 s    │ mongo-b  │
└─────────────┴───────────┴──────────┴──────────┘

PRIMARY oplog window: 12 h
Worst lag:             140 s
Min headroom:          11 h 57 m 40 s (estimated)
Write oplog rate:      0.8 GiB/h
Elections (24h):       0
```

Values in the table are simulated. **Actual headroom must be calculated against each secondary's sync source**, not just the primary, especially with chained replication.

### 31.2. Detailed Per-Member Dashboard

- Role, `health`, state duration.
- `optimeDate`/`optimeDurableDate`, plus `optimeWrittenDate` on supported versions.
- Lag seconds as a time series.
- Oplog window of the member and its sync source.
- Headroom seconds.
- Heartbeat/ping/network errors.
- Disk latency/IOPS/queue, cache eviction, CPU.
- Sync source host and source switches.
- Initial sync progress when in `STARTUP2`.

### 31.3. Rules to Avoid Misleading Charts

Do not:

```text
Lag = null -> 0
Oplog window = null -> 0
Member DOWN -> 0 second lag
```

Instead:

```text
Lag = unknown / data missing
Member DOWN = availability alert
Oplog window = not applicable or unavailable
```

**Missing observability data is a state to monitor**, not proof that everything is fine.

## 32. Designing Alerts

### 32.1. Alert Categories

| Alert | Suggested trigger | Meaning |
|---|---|---|
| **No Primary** | No primary beyond grace period | Write availability impacted |
| **Member Unreachable** | `DOWN` / sustained heartbeat failure | Availability/topology |
| **Member in RECOVERING** | Prolonged outside maintenance/initial sync | Needs root-cause check |
| **Lag High** | Lag > SLO across multiple samples | Secondary falling behind |
| **Lag Growing** | Sustained positive lag slope | Escalating risk |
| **Oplog Window Low** | Window < target downtime + margin | Insufficient history |
| **Headroom Low** | Headroom < time-to-recover + margin | Risk of oplog exhaustion |
| **Oplog Rate Spike** | GB/hour surged vs. baseline | Window may shrink rapidly |
| **Disk Saturated** | Abnormal latency/IOPS | Can throttle apply rate |
| **Election Storm** | Rising election count | Topology/network instability |
| **Metrics Missing** | Missing status/oplog samples | Monitoring interrupted |

### 32.2. Do Not Apply One Universal Lag Threshold

Examples by use case:

- Near-real-time read secondary: lag SLO might be a few seconds.
- End-of-day reporting secondary: acceptable lag may be longer.
- 1-hour delayed secondary: ~1 hour of lag is intentional.
- Cross-region DR secondary: thresholds depend on RPO, network, and write throughput.

Thresholds must be **defined jointly with product/SRE**, not copied blindly from a blog post.

### 32.3. Preventing Alert Flapping

For brief spikes:

```text
lag=1s -> 6s -> 1s
```

alerting every time it crosses 5 seconds creates noise. Use sustained durations, p95, or appropriate burn rates—but **never delay alerting when headroom approaches 0** just to avoid noise.

### 32.4. Severity Tiering

An example policy:

```text
WARNING:
  lag growing for 5 minutes
  or oplog window below downtime target

HIGH:
  headroom < estimated recovery time + buffer
  or critical read-secondary lag exceeds SLO

CRITICAL:
  tooStale
  no primary
  loss of required quorum
  headroom near 0 while lag is still growing
```

Do not copy these thresholds verbatim onto every cluster; real conditions must be measured and approved.

## 33. Runbook 1 — Secondary Lag Rising While Still SECONDARY

### Step 1: Verify the Situation

On the primary:

```javascript
rs.status();
rs.printSecondaryReplicationInfo();
```

Record:

- Name of the lagging member.
- State and health.
- Lag across multiple timestamps.
- Sync source.
- Oplog window and headroom.

### Step 2: Assess Urgency

If headroom remains wide, investigate methodically. If headroom is approaching 0, prioritize mitigation before the member becomes `tooStale`.

### Step 3: Check Resources

- Disk latency/IOPS on the secondary.
- CPU and WiredTiger cache.
- Network/ping/packet loss.
- Whether backups or analytics are reading from the secondary.
- Recent deployments, bulk writes, index builds, or migrations.

### Step 4: Mitigate the Root Cause

Based on evidence:

- Throttle or adjust batch imports.
- Shift reporting load off the overloaded secondary.
- Upgrade storage IOPS/tier.
- Fix network routing or packet loss issues.
- Optimize indexes/filters causing resource contention.

### Step 5: Confirm Recovery

Lag must **decline steadily**, headroom must grow, the member must be healthy with no new errors, and primary/write latency must stay within bounds.

Never declare "resolved" simply because lag temporarily dropped to 0 during a quiet write period.

## 34. Runbook 2 — Oplog Window Shrinking Rapidly

### Symptoms

```text
12:00 window 48h
12:10 window 24h
12:20 window 12h
12:30 window 6h
```

### Investigation

1. Run `db.getReplicationInfo()` on affected members.
2. Measure **Oplog GB/Hour** and write rate.
3. Check for recent batch imports, updates, or deletes.
4. Check for changed workloads, index builds, or transaction behavior.
5. Verify configured oplog size and minimum retention.
6. Check free disk space and majority commit point.
7. Measure lag and headroom of all secondaries.

### Actions to Consider

- Temporarily throttle write bursts within business constraints.
- Tune batch sizes.
- Increase oplog capacity or minimum window per plan (self-managed and Atlas mechanisms differ).
- Protect lagging secondaries before they lose history.
- Adjust backup/maintenance windows.

### What Not to Do

Never shrink oplog size to "free disk space" while a secondary is near the edge of the window. Further truncation can push it into `tooStale`.

## 35. Runbook 3 — Member DOWN or UNKNOWN

### Step 1: Distinguish View Failures from Truly Down Members

`rs.status()` from one node may mark a peer `DOWN` due to a network partition. Cross-check:

- Host/process monitoring.
- Actual network reachability along the real path.
- Node logs and TLS/auth events.
- Views from other members.
- Election and majority status.

### Step 2: Protect Quorum

Avoid restarting or reconfiguring additional nodes while the replica set is near losing majority. One wrong move can prevent electing a primary and halt writes.

### Step 3: Estimate Safe Downtime

```text
current window at sync source
  - member offline duration
  - lag accumulated before going offline
  ≈ remaining history margin (approximate)
```

Remember that safe downtime estimates become inaccurate if the window shrinks due to rising write workload.

### Step 4: Recovery

Once the member reconnects, monitor whether it returns to `SECONDARY` with falling lag or transitions to `RECOVERING`/`tooStale`. Never wipe data directories for a fresh initial sync without verifying first.

## 36. Runbook 4 — Member `tooStale`

Once `tooStale` is confirmed:

1. Verify which data-bearing members are healthy and confirm majority health.
2. Check oplog windows on available sync sources.
3. Collect logs plus last applied and last fetched timestamps.
4. Plan resync following version-specific documentation.
5. Check source/target disk capacity, disk I/O, and network.
6. Avoid running multiple concurrent resyncs if the source cannot sustain the load.
7. Monitor initial sync progress and `STARTUP2`.
8. Confirm `SECONDARY`, applied lag, and headroom after resync completes.
9. Address the root cause: network outage, write burst, or undersized window.

**Do not treat resync as a permanent fix** if the workload still generates oplog entries faster than the secondary can apply them.

## 37. Runbook 5 — Continuous Elections

If the primary keeps changing:

- Record election timestamps, `term` values, and candidates.
- Check for network partitions, heartbeat errors, and CPU/disk stalls.
- Verify quorum and voting configuration.
- Inspect whether members have unexpected priority, delay, or hidden settings.
- Correlate driver connection errors and application write retries.
- Assess rollback risk, write concern, and majority commit point.
- Never use `rs.stepDown()` or `rs.reconfig()` as diagnostic probes.

The goal is stabilizing the underlying **network, resource, or topology** cause—not forcing a pinned primary through arbitrary commands.

## 38. Integrating Monitoring with the Java Sync Driver

A Java application can query `replSetGetStatus` if its identity has sufficient privileges. **This is an internal monitoring task**, not a public endpoint exposing hostnames and cluster topology.

### 38.1. Java Example

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;
import java.util.Date;
import java.util.List;

public final class ReplicaHealthSample {
    public static void main(String[] args) {
        // Demo URI: production deployments require credentials/TLS/secret management.
        String uri = System.getenv("MONGODB_MONITOR_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                "MONGODB_MONITOR_URI is required");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase admin = client.getDatabase("admin");
            Document status = admin.runCommand(
                new Document("replSetGetStatus", 1));

            @SuppressWarnings("unchecked")
            List<Document> members =
                (List<Document>) status.get("members");

            Document primary = null;
            for (Document member : members) {
                if ("PRIMARY".equals(member.getString("stateStr"))) {
                    primary = member;
                    break;
                }
            }

            Date primaryApplied = primary == null
                ? null : primary.getDate("optimeDate");

            for (Document member : members) {
                String name = member.getString("name");
                String state = member.getString("stateStr");
                Date applied = member.getDate("optimeDate");

                Double lagSeconds = null;
                if ("SECONDARY".equals(state)
                        && primaryApplied != null
                        && applied != null) {
                    lagSeconds =
                        (primaryApplied.getTime() - applied.getTime())
                        / 1000.0;
                }

                System.out.printf(
                    "member=%s state=%s lagSeconds=%s%n",
                    name, state,
                    lagSeconds == null ? "unknown" : lagSeconds);
            }
        }
    }
}
```

### 38.2. Notes on Java Version and Permissions

This example uses `String.isBlank()` (Java 11+). You need the appropriate MongoDB Java Sync Driver version and an identity permitted to run `replSetGetStatus`.

Depending on deployment and driver configuration, routing commands to a specific node requires explicit intent; do not treat one member's output as absolute truth during failover.

### 38.3. Never Expose Monitoring Directly Over Public HTTP

Do not create:

```text
GET /admin/replica-status
-> returns raw rs.status() to any user
```

Raw output contains hostnames, network addresses, and topology metadata. Enforce AuthN/AuthZ, strip unnecessary details, rate-limit, and follow security policies.

### 38.4. Controlled Polling

Do not query `rs.status()` dozens of times per second from hundreds of application instances. Use a central exporter or monitoring agent with a reasonable scrape interval.

## 39. A Consolidated `mongosh` Script for the Lab

The following script is **read-only**, summarizing state, applied lag, and oplog window **of the connected member**. To compute headroom for each secondary, also collect the window from its respective sync source.

```javascript
function collectReplicaMetrics353() {
  const s = rs.status();
  const primary = s.members.find(
    m => m.stateStr === "PRIMARY");

  const primaryTime = primary?.optimeDate instanceof Date
    ? primary.optimeDate.getTime()
    : null;

  const members = s.members.map(m => {
    const secondary = m.stateStr === "SECONDARY";
    const time = m.optimeDate instanceof Date
      ? m.optimeDate.getTime() : null;

    return {
      name: m.name,
      state: m.stateStr,
      health: m.health,
      lagSeconds: secondary &&
        primaryTime !== null && time !== null
          ? (primaryTime - time) / 1000
          : null,
      source: m.syncSourceHost || null
    };
  });

  const info = db.getReplicationInfo();

  return {
    sampledAt: new Date(),
    replicaSet: s.set,
    observerState: s.myState,
    oplogWindowHoursOnObserver:
      typeof info.timeDiffHours === "number"
        ? info.timeDiffHours : null,
    oplogUsedMBOnObserver: info.usedMB ?? null,
    members
  };
}

printjson(collectReplicaMetrics353());
```

**Intentional limitations:**

- `oplogWindowHoursOnObserver` represents **only the connected node**.
- Without a primary, lag is `null`.
- Arbiters have no lag.
- Never fire alerts from a single sample.
- If `rs.status()` lacks privileges or an election is in progress, the script may error; exporters must record collection failures explicitly.

## 40. Using `serverStatus()` and Monitoring Privileges

MongoDB exposes rich metrics via:

```javascript
db.getSiblingDB("admin").serverStatus();
```

You can inspect:

- `opcounters`, `opcountersRepl`.
- `flowControl`.
- `wiredTiger.cache`.
- `connections`.
- `network`.
- `metrics.repl` or related branches depending on version.
- `oplogTruncation` where supported.

### 40.1. Do Not Hardcode Immutable Metric Names

The structure of `serverStatus()` evolves across MongoDB releases. An exporter should:

1. Check server version.
2. Detect field availability.
3. Mark missing values as unknown.
4. Maintain compatibility tests.
5. Never silently map missing metrics to `0`.

### 40.2. RBAC

The `clusterMonitor` role covers most cluster monitoring needs. However, certain queries against `local.oplog.rs` or configuration metadata may require additional privileges depending on deployment. Instead of granting `root` to an exporter, determine the minimal required actions and define a custom role when necessary.

## 41. Sharded Clusters: Monitoring Each Shard's Replica Set Separately

In a MongoDB sharded cluster:

```text
Application -> mongos
                |
                +-- Shard A replica set
                |     A-P, A-S1, A-S2
                |
                +-- Shard B replica set
                |     B-P, B-S1, B-S2
                |
                +-- Config server replica set
                      C-P, C-S1, C-S2
```

### 41.1. There Is No Single Lag Metric Across All Shards

One shard may have 2 seconds of lag while another has 20 minutes. Averaging across shards masks the risk.

Display metrics hierarchically:

```text
cluster -> replicaSet -> member
```

and define "worst lag/headroom" per appropriate group.

### 41.2. Config Servers Also Need Monitoring

The config server replica set stores critical sharding metadata. If its members become unstable, the cluster can be impacted even while shard data nodes stay up.

Do not inspect config server metadata by modifying `config.*` collections to "test replication." Use only supported monitoring tools.

### 41.3. Do Not Treat `mongos` as a Data-Bearing Replica Member

`mongos` is a router and does not hold `local.oplog.rs` like shard primaries and secondaries. To check lag or oplog window, query the individual shard replica sets or per-shard Atlas metrics.

## 42. Impact on Reads, Write Concern, and Failover

### 42.1. Secondary Reads Can Be Stale

If an application uses:

```text
readPreference = secondary
```

it may read data that has not yet applied the most recent writes. If the business requires read-your-writes or strong consistency, revisit read preference, read concern, and session guarantees.

### 42.2. Lag and Max Staleness

Drivers support **`maxStalenessSeconds`** on appropriate read preferences to avoid selecting secondaries that lag too far behind according to driver criteria.

This is not a full replacement for monitoring:

- Drivers observe topology via SDAM and heartbeats.
- Staleness estimates do not measure exact per-document freshness.
- Minimum threshold rules and version requirements from driver docs must be respected.
- If no secondary qualifies, server selection behavior depends on read preference and topology.

### 42.3. Write Concern `majority`

Write concern `majority` ties write acknowledgment to majority replication guarantees, yet it does not wait for every slow secondary to catch up.

If lag is high on a secondary serving reporting queries, an application using majority writes can still see stale reports on that member.

### 42.4. Failover Readiness

If the primary is lost:

- Only an eligible secondary can be elected as replacement.
- Lag increases failover risk and potential staleness.
- Heavily lagging members are poor candidates.
- Arbiters store no data and cannot become primary.

Dashboards must distinguish **"N nodes are healthy"** from **"how many data-bearing voting/electable members are genuinely eligible"**.

## 43. Common Mistakes

| Mistake | Consequence | Correct understanding |
|---|---|---|
| Using `Date.now()-secondary.optimeDate` as lag | False alarms when cluster is idle | Compare secondary to primary optime |
| Checking only `health=1` | Misses secondary lag | Check state + optime + headroom |
| Treating `pingMs` as replication lag | Misdiagnoses network vs. apply | Measure network and oplog progress separately |
| Parsing `rs.printSecondaryReplicationInfo()` as JSON | Fragile scripts | Use `rs.status()` |
| Using primary's `rs.printReplicationInfo()` for all members | Hides differing windows | Measure each member/sync source directly |
| Assuming 10 GB oplog = 10h retention | Fails when write rate shifts | Track actual window and GB/hour |
| Ignoring headroom | Reacting too late to `tooStale` | Compare window against lag |
| Evaluating headroom only against primary | Wrong under chained replication | Inspect actual `syncSourceHost` |
| Coercing missing lag to 0 | Hides `DOWN`/`UNKNOWN` | Keep unknown and health alerts |
| Treating negative lag as secondary ahead of primary | Misinterprets heartbeat skew | Keep context and re-sample |
| Alerting `lag > 30s` on a 1h delayed secondary | Constant false alarms | Use role-specific thresholds |
| Treating arbiter as a data secondary | Overestimates resiliency | Exclude arbiters from lag/data replicas |
| Treating `STARTUP2` as always an error | False alarms during initial sync | Monitor progress and duration |
| Treating `RECOVERING` as always `tooStale` | Misdiagnosis | Verify `tooStale` and logs |
| Confusing `applied` with `durable` | Wrong durability assumptions | Check optime fields and write concern |
| Disabling flow control immediately when seen | Lag can spike severely | Investigate secondary bottleneck |
| Enlarging oplog to "fix" a failing disk | Only delays the outage | Fix slow apply cause |
| Setting high min retention without disk math | Risk of filling disk | Perform capacity planning |
| Shrinking oplog while a secondary lags | Can drop needed history | Follow change review |
| Calling `replSetResizeOplog` on Atlas | Command unsupported | Use Atlas settings |
| Calling `rs.reconfig()` from monitoring | Dangerous topology mutation | Monitoring must be read-only |
| Averaging lag across shards | Hides a severely lagging shard | Per-member/per-shard dashboards |
| Treating replication as backup | Valid deletes replicate too | Use separate backups/PITR |
| Ignoring metric sampling intervals | Misses spikes or misreads timing | Understand granularity |
| Declaring resolved from one sample | May just be idle or transient | Verify sustained trend |

## 44. Hands-On Exercises

### Exercise 1 — Reading a Replication Diagram

Draw a three-member replica set with one primary and two secondaries, where one secondary chains through the other secondary. Label the sync source, oplog fetch flow, and potential lag points.

### Exercise 2 — Computing Lag

Primary `optimeDate=12:00:40`; secondary B `12:00:36`; secondary C `11:59:10`. Compute approximate lag and explain why the formula does not use the current wall clock.

### Exercise 3 — Idle Cluster

Wall clock is `15:00`; both primary and secondary have their last oplog entry at `14:00`. A dashboard reports 3600 seconds of lag. Identify the error and write the correct formula.

### Exercise 4 — Reading `rs.status()`

Given:

```javascript
{
  members: [
    { name:"A", stateStr:"PRIMARY", health:1,
      optimeDate:ISODate("2026-11-14T12:00:00Z") },
    { name:"B", stateStr:"SECONDARY", health:1,
      optimeDate:ISODate("2026-11-14T11:59:58Z") },
    { name:"C", stateStr:"SECONDARY", health:1,
      optimeDate:ISODate("2026-11-14T11:58:00Z") }
  ]
}
```

Which member should be investigated first? Why does `health=1` not guarantee fresh data?

### Exercise 5 — States

Classify `PRIMARY`, `SECONDARY`, `STARTUP2`, `RECOVERING`, `UNKNOWN`, `ARBITER`, `DOWN`, and `ROLLBACK`. Which state holds no copy of the data? Which states can be normal during initial sync?

### Exercise 6 — Heartbeats

Member B has `pingMs=3` yet 120 seconds of lag. List at least five non-network-RTT causes to investigate.

### Exercise 7 — Oplog Window

In the oplog, `oldest=08:00` and `newest=12:30`. Compute the window. If current wall clock is `13:45`, can you replace `newest` with `13:45`?

### Exercise 8 — Window by Write Rate

An oplog holds roughly 12 GiB. At steady-state workloads of 1 GiB/h and 4 GiB/h, calculate approximate retention. Why might actual retention differ?

### Exercise 9 — Headroom

Secondary lag is 2 hours and sync source window is 3 hours. Calculate approximate headroom. If over the next 20 minutes the window shrinks to 2h10m while lag rises to 2h05m, interpret the risk level.

### Exercise 10 — Too Stale

Sync source's oldest oplog entry is `11:00`; secondary's last applied is `10:20`. The member is `RECOVERING` with `tooStale=true`. Write a safe runbook and explain why forcing `stepUp` or deleting data directories arbitrarily is unsafe.

### Exercise 11 — Delayed Secondary

A delayed member has `secondaryDelaySecs=1800`, yet reports occasionally show 0 lag. Give at least two valid reasons and explain how to design role-aware alerts.

### Exercise 12 — Writing a Script

Use `rs.status()` to return a table of `host`, `stateStr`, `health`, `optimeDate`, `syncSourceHost`, and lag relative to the primary. Exclude arbiters and do not coerce `null` to zero.

### Exercise 13 — Structured Window Inspection

Use `db.getReplicationInfo()` to collect `timeDiff`, `timeDiffHours`, `tFirst`, `tLast`, `usedMB`, and `logSizeMB`. Why is `rs.printReplicationInfo()` a poor data source for scripts?

### Exercise 14 — Slow Writes on Secondary

Secondary disk IOPS hits its limit while primary write rate increases. Design a timeline-based investigation and propose safe load-reduction/remediation steps.

### Exercise 15 — Flow Control

Replication lag rises alongside write latency, and `flowControl.isLagged` appears. Why shouldn't you disable flow control immediately? What else should you measure?

### Exercise 16 — Oplog Retention

You set minimum retention to 72 hours, write rate is 3 GiB/h, and configured oplog size is 20 GiB. Estimate accumulated volume and explain the disk risk. What two conditions must hold for MongoDB to truncate an entry?

### Exercise 17 — Resizing the Oplog

Contrast self-managed `replSetResizeOplog` with Atlas options. Why can shrinking size or minimum retention impact Change Streams and secondaries?

### Exercise 18 — Elections

A cluster has A (primary), B (secondary, priority 1), C (hidden, priority 0), and D (arbiter). If A fails, who can become primary? What voting/quorum and other conditions must also be checked?

### Exercise 19 — Initial Sync

A new member has been in `STARTUP2` for 4 hours while copying data to disk and the oplog window is shrinking. Which metrics distinguish healthy progress from a failing initial sync?

### Exercise 20 — Sharded Monitoring

A sharded cluster has two shard replica sets and a config server replica set. Design a dashboard showing per-member lag and window so that a cluster average does not hide heavy lag on Shard A.

### Exercise 21 — Atlas Alerts

Propose three alerts: Replication Lag, Replication Oplog Window, and Replication Headroom. Explain why enabling only Lag High is insufficient.

### Exercise 22 — Java Monitoring

Write a Java Sync Driver snippet calling `replSetGetStatus`, reading the primary's optime, and computing secondary lag. Explain how to handle missing `optimeDate` and protect the monitoring URI.

### Exercise 23 — Read Staleness

An application reads from a secondary right after writing to the primary. Discuss read preference, read concern, and session options, and why monitoring lag alone does not guarantee read-your-writes.

### Exercise 24 — 90-Minute Network Outage Incident

A secondary is offline for 90 minutes; the oplog window started at 4 hours but shrank to 1 hour during the outage. When it reconnects, what is the `tooStale` risk? What evidence should you collect?

### Exercise 25 — Complete Runbook

Design an incident response for:

```text
Lag grows: 5m -> 20m -> 40m
Oplog window: 3h -> 2h -> 1h
Member state: SECONDARY
Write throughput: 4x increase
Disk latency: rising
```

Specify triage order, priority metrics, short-term mitigations, long-term fixes, incident closure criteria, and actions **never to automate blindly**.

## 45. Operational Checklist

### 45.1. Before Moving a Replica Set to Production

1. Per-member dashboards exist for state, health, and lag.
2. Oplog window metrics exist per member, or at least for every relevant sync source.
3. Headroom metrics and alerts are configured relative to recovery time targets.
4. Oplog GB/Hour is monitored to forecast window compression.
5. CPU, disk, cache, and network metrics exist to pinpoint lag causes.
6. Alerts cover elections, no primary, `DOWN`, and prolonged `RECOVERING`.
7. Delayed, hidden, and arbiter members are clearly distinguished.
8. Monitoring accounts use least-privilege RBAC and TLS.
9. Alerts exist for failed metric collection.
10. Resync/initial sync runbooks and capacity plans are documented.

### 45.2. During Ongoing Operations

1. Track baselines and trends across daily and peak hours.
2. Check the oplog window after major workload changes.
3. Verify whether bulk imports or cleanups erode headroom.
4. Monitor secondary read and reporting workloads.
5. Confirm backups and change-stream consumers remain within the window.
6. Review topology after adding/removing members or elections.
7. Check `syncSourceHost` whenever lag increases.
8. Test alerts for missing metrics and `DOWN` states.
9. Maintain event logs, owners, SLAs, and resolution criteria.
10. Never make risky config changes without change approval.

## 46. Summary

**Replication lag, oplog window, and member state are three perspectives that must be combined.** Lag reflects apply progress relative to the primary; oplog window reflects retained change history on a member; member state and heartbeats indicate whether the member is syncing, reachable, and operationally eligible.

**Use the right tools:** `rs.status()` and `replSetGetStatus` for structured member snapshots; `rs.printSecondaryReplicationInfo()` for quick lag reading from the primary; `rs.printReplicationInfo()` for quick oplog window reading on a member; and `db.getReplicationInfo()` for structured windows in scripts. On Atlas, Replication Lag, Replication Oplog Window, Replication Headroom, and Oplog GB/Hour provide historical views and alerting.

**Never treat a single number as absolute truth.** Zero lag can occur on an idle cluster; negative lag can stem from unsynchronized heartbeat views; arbiters hold no data; delayed members carry intentional lag; and the oplog window fluctuates with write rate. The calculation `headroom = window - lag` is a vital indicator, not a second-accurate guarantee when workloads shift.

**Effective responses target root causes and recovery paths.** When a secondary lags, inspect network, disk, CPU/cache, workload, sync source, and flow control. When the window shrinks and headroom nears exhaustion, protect oplog history and reduce the cause of lag; when a member becomes `tooStale`, resync using the official runbook. Never run `rs.reconfig()`, `rs.stepDown()`, shrink the oplog, or delete data files as ad-hoc "tests" to cure lag.

A strong observability system does not merely say "secondary is slow"—it tells you **how far behind it is, relative to which source, how much headroom remains, what the failover risk is, and which safe actions will restore health**.

## 47. References

- [MongoDB Manual — Troubleshoot Replication Lag](https://www.mongodb.com/docs/manual/troubleshooting/replication-lag/): measuring lag and diagnosing network, disk, and resource causes.
- [MongoDB Manual — Troubleshoot Replica Sets](https://www.mongodb.com/docs/manual/tutorial/troubleshoot-replica-sets/): `rs.status()`, lag, and flow control.
- [MongoDB Manual — replSetGetStatus](https://www.mongodb.com/docs/manual/reference/command/replsetgetstatus/): member state, heartbeats, optimes, and `tooStale`.
- [MongoDB Manual — Replica Set Member States](https://www.mongodb.com/docs/manual/reference/replica-states/): state codes and normal vs. error states.
- [MongoDB Manual — Replica Set Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/): oplog window and retention.
- [MongoDB Manual — rs.printSecondaryReplicationInfo()](https://www.mongodb.com/docs/manual/reference/method/rs.printsecondaryreplicationinfo/): text-formatted lag report.
- [MongoDB Manual — rs.printReplicationInfo()](https://www.mongodb.com/docs/manual/reference/method/rs.printreplicationinfo/): text-formatted oplog window report.
- [MongoDB Manual — db.getReplicationInfo()](https://www.mongodb.com/docs/manual/reference/method/db.getreplicationinfo/): structured oplog metrics for scripts.
- [MongoDB Manual — replSetResizeOplog](https://www.mongodb.com/docs/manual/reference/command/replsetresizeoplog/): adjusting oplog on self-managed deployments and caveats.
- [MongoDB Atlas — Review Alert Conditions](https://www.mongodb.com/docs/atlas/reference/alert-conditions/): Replication Lag, Oplog Window, Headroom, and GB/hour.
- [MongoDB Atlas — Review Cluster Metrics](https://www.mongodb.com/docs/atlas/monitor-cluster-metrics/): metric granularity and retention.
- [MongoDB Atlas — Fix Oplog Issues](https://www.mongodb.com/docs/atlas/reference/alert-resolutions/replication-oplog/): diagnosing oplog window and write rate.
