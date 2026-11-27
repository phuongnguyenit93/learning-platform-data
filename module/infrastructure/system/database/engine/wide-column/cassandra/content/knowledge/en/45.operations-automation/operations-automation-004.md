# Repair Scheduling Based on Data Scope and Tombstone Grace Retention

> **Chapter:** Operations Automation  
> **Module:** DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA  
> **Scope:** Scheduling, tracking, and accepting Apache Cassandra anti-entropy repairs by keyspace, table, token range, replica/DC, and tombstone retention time; combining CQL, Java Driver, RF/CL, compaction, TTL, and operational failure handling.  
> **Operational objective:** Ensure replicas responsible for storing the same data are reconciled frequently enough, not merely that a "repair command ran."

## 1. The problem: weekly repair schedule, yet deleted data can still resurrect

A Cassandra cluster serves tenant order events. The table has **gc_grace_seconds = 864000** (10 days). The operations team sets up a weekly Sunday repair cron job and sees it running steadily. However:

- A node holding replicas for partition K goes DOWN for more than 10 days.
- The Sunday job still launches, yet some **token ranges** or nodes fail and are not fully repaired.
- A DELETE of K is acknowledged on the healthy replicas, while the DOWN node never receives the tombstone.
- The tombstone becomes eligible for purging after grace and may be dropped by compaction.
- The old node comes back without knowing K was deleted; under the right conditions, the deleted data can **resurrect (zombie data)**.

What must be measured is not "how many times the cron ran," but **when each data scope was successfully repaired, across which replicas, and whether it remains inside the tombstone protection window**.

Two concepts must be separated:

1. **Job schedule:** When the orchestrator creates a repair job.
2. **Verified coverage:** Which keyspace/table, token ranges, and DC/replicas actually completed appropriate repair and were verified as successful.

A job returning exit code 0 is insufficient if it only processed a small subset of ranges, skipped a DC, or had metadata/workers misreport scope completion.

### Learning objectives

Upon completing this lesson, you can:

- Explain repair, tombstones, TTL, `gc_grace_seconds`, and zombie conditions.
- Define **scheduling units** by keyspace/table/token range/replica/DC rather than one global cron schedule.
- Calculate a **time budget** from the grace window, repair execution duration, failure retries, and node unavailability.
- Design a **coverage ledger** and criteria for marking COMPLETED/PARTIAL/FAILED/STALE.
- Schedule by risk level, data size, and capacity, with admission control, backoff, and stop gates.
- Distinguish incremental/full repair and select scopes per Cassandra version.
- Use CQL and read-only `nodetool` commands to verify schema, RF, TTL, compaction, and progress.
- Write illustrative Java code for scoring repair deadlines, tracking the ledger, and testing the scheduler.
- Build runbooks for missed repairs, node outages, topology changes, and approaching deadlines.
- Avoid mistakes such as lowering `gc_grace` to purge tombstones, running overlapping I/O-contending repairs, or ignoring failed ranges.

> **Safety rule:** Cluster-mutating commands (repair, rebuild, decommission, RF changes, forced compaction, snapshot deletion) may only be triggered by authorized tooling/runbooks in an appropriate environment. This lesson does not instruct running arbitrary repairs in production; configuration examples are lab designs that must be verified against your exact Cassandra/operator version.

## 2. Why is repair needed in distributed Cassandra?

Cassandra distributes data by **partition key → token → replica set** according to the replication strategy. In a DC using **NetworkTopologyStrategy**, RF=3 means each partition is placed on three replicas per placement strategy. A coordinator receives CQL and interacts with the selected replicas.

Suppose a client writes DELETE K at **LOCAL_QUORUM** while one replica is DOWN:

~~~text
Partition K, RF=3 in dc1

A (UP):   receives DELETE K, holds tombstone
B (UP):   receives DELETE K, holds tombstone
C (DOWN): still holds old version of K

LOCAL_QUORUM: A+B suffice to acknowledge the write in this example.
Yet C is not guaranteed to have received the DELETE.
~~~

Repair uses **anti-entropy**, comparing data state across token ranges among relevant replicas and synchronizing differences. It helps prevent a stale replica from reintroducing an old version after tombstones disappear.

However:

- Repair is **not a backup**; it cannot undo a valid yet business-erroneous DELETE.
- Repair **does not fix** a newer INSERT whose timestamp is higher than a tombstone from a business standpoint.
- Repair **cannot infer** which row ought to have been deleted once both the tombstone and deletion evidence are gone.
- A **partial** repair session does not prove the whole table, DC, or cluster has converged.
- Hinted handoff and read repair have version/path limitations; they **do not replace a verified periodic anti-entropy repair strategy**.

### 2.1. Tombstones and gc_grace_seconds

A DELETE is represented by a **tombstone** carrying a timestamp. TTL expiration also creates expired cell states that must be handled safely during data merges. **gc_grace_seconds** is the table's grace period governing when tombstones become eligible for removal from SSTables.

Example:

~~~text
gc_grace_seconds = 864000 seconds = 10 days

DELETE K at T0:
  The tombstone shadows older versions of K.

Within the protection window:
  Any replica that missed the delete needs an opportunity to synchronize.

Once the tombstone is eligible for purge:
  Compaction may drop the marker if other conditions allow.

If a stale replica returns after the marker is gone:
  K risks resurrecting.
~~~

**Do not treat 10 days as a guaranteed timestamp when tombstones vanish.** Purging also depends on compaction, SSTable overlap, and version-specific safety checks. Equally, **do not treat purge delays as a safety guarantee** when the repair schedule has already overrun the grace window.

### 2.2. Distinguishing three time concepts

| Concept | Meaning | Do not confuse with |
|---|---|---|
| **TTL** | Lifetime of a cell written with TTL, in seconds | Repair schedule |
| **gc_grace_seconds** | Tombstone protection window before eligibility for garbage collection | Duration of a single compaction |
| **Repair interval/coverage lag** | Time elapsed between valid completed repairs of a data scope | Cron trigger counter |

A short TTL does not mean `gc_grace_seconds` should be shortened to match. A table with a few-hour TTL may still need an appropriate grace window and repair schedule to prevent stale replicas from reintroducing expired data under certain conditions.

### 2.3. Compaction is not a repair schedule

Compaction merges SSTables, drops eligible obsolete/tombstone data, and impacts disk/CPU/read p99. Repair reconciles replicas. **Compaction has no idea whether a replica in another DC missed a DELETE**, so "compaction just ran" cannot be used as proof that all token ranges are repaired.

## 3. Unit to track: table × token range × replica scope

A cluster-level cron job does not reveal which scopes are actually protected. The orchestrator should maintain a **coverage ledger** keyed at minimum by:

| Field | Meaning |
|---|---|
| **Cluster/environment** | Avoid confusing staging with production |
| **Keyspace/table** | Each table has distinct `gc_grace`, TTL, compaction, and data volume |
| **Token range / subrange** | Range of partition keys compared across replicas |
| **DC/replica scope** | Which replicas must be included per repair strategy and version |
| **Repair mode** | Full/incremental or operator-managed mechanism |
| **Topology generation** | Flags that ownership changed after bootstrap/replace/decommission |
| **Last verified success** | Time the scope finished and was verified, not merely job start |
| **Previous failures** | Missing ranges, retry budget, and failure causes |
| **Next deadline** | Grace window minus safety margin and estimated completion time |
| **Evidence** | Repair session ID, logs/metrics, version, and success manifest |

One range can be huge or hot while another holds little data. **Per-table/range scheduling** enables:

- Prioritizing scopes closest to exhausting tombstone protection.
- Splitting large repairs into subranges as supported by version/tooling.
- Tracking failed ranges without reporting "whole table OK."
- Reordering when repair durations and replica availability differ.
- Spreading work so multiple jobs do not hammer the same node concurrently.

### 3.1. Coverage is not a simple byte percentage

A report stating "99% of bytes repaired" can miss a tiny range containing critical tombstones. Coverage must be evaluated against the **set of required scopes**: which ranges, tables, and DCs/replicas. Byte counts track progress but do not replace the list of completed scopes.

Example:

~~~text
Table events_by_tenant_day
  dc1 / range R1: COMPLETED
  dc1 / range R2: COMPLETED
  dc1 / range R3: FAILED
  dc1 / range R4: PENDING

Result:
  Table repair = PARTIAL, not VERIFIED COMPLETE.
  R3/R4 must have dedicated deadlines and owners.
~~~

### 3.2. Topology changes require re-evaluating the ledger

When nodes are added or replaced, token range ownership and replica sets can change. Evidence that "range R was repaired among A/B/C last week" does not necessarily cover new replicas after bootstrap.

The orchestrator must:

1. Record topology generation/cluster metadata at start time.
2. Detect owner/DC/rack/RF changes before accepting job success.
3. Determine which scopes require re-checking/re-repairing per version-specific runbook.
4. Never mark an entire range covered solely because bytes streamed to a new node.
5. Avoid overlapping repairs while topology is unstable and operators require waiting.

## 4. Cataloging tables by tombstone risk and workload

Not every table requires the same operational priority. The catalog should capture:

| Attribute | Question |
|---|---|
| **Data purpose** | Orders, TTL sessions, event history, or audit? |
| **Delete/TTL pattern** | Heavy deletes, short TTL, or few tombstones? |
| **gc_grace_seconds** | What is the actual configured value per table? |
| **Size / SSTables / partition distribution** | How large is each range/table; are there hot partitions? |
| **Compaction strategy** | STCS/LCS/TWCS or version-specific choice |
| **RF/DC** | Which DCs hold data; which replicas can fail? |
| **Availability requirement** | Maximum duration a node can stay DOWN? |
| **Repair coverage SLA** | How often must each scope be re-verified? |
| **Historical failures** | Which scopes frequently time out or get skipped? |
| **Load sensitivity** | Peak traffic, read p99, compaction/backup windows? |

### 4.1. Example catalog, not a standard schedule

| Hypothetical table | Pattern | Assumed grace | Risk | Scheduling direction |
|---|---|---|---|---|
| **order_state_by_id** | DELETE/UPDATE, strict state correctness | 10 days | High on missing replica | Priority scope, frequent verified coverage |
| **sessions_by_id** | Short TTL, heavy expirations | 10 days | Tombstone pressure and stale replicas | I/O-budgeted repair, dedicated TTL/compaction tracking |
| **events_by_tenant_day** | Append/bucketed, retention TTL | 10 days | Large volume and late writes | Split ranges/repair windows, monitor TWCS if used |
| **test_fixture** | Disposable lab data | Per lab config | Low business risk, still needs cluster safety | Separate schedule, zero production impact |

**Assumed grace values are not default recommendations for every table.** Read the actual schema and choose schedules based on repair completion capacity in your concrete topology.

### 4.2. Immutable data does not grant arbitrary repair exemption

An append-only table can still experience TTL expirations, retention tombstones, late writes, failed replicas, and many SSTables. Only when the design, data-loss tolerance, immutability, and Cassandra/compaction guidance have been thoroughly evaluated should an alternative policy be considered. Never use an "append-only" label to skip repair without evidence and approval.

## 5. Time budgeting: finish before deadline, not merely start before deadline

Let:

- **G:** the table's `gc_grace_seconds`, converted into allowable duration.
- **I:** interval from one scheduled start to the next scheduled start for the same scope.
- **Dmax:** maximum expected repair duration for the scope, from start to completion/verification.
- **F:** reserve delay for job failures, controlled retries, or queuing.
- **O:** additional time/delay when a replica is unavailable or topology is transitioning.
- **B:** safety buffer for schedule jitter, metric delay, timezone/clock skew, and operational variance.

A **conservative scheduling design estimate**:

\[
L_{budget} = I + D_{max} + F + O + B
\]

Target requirement:

\[
L_{budget} < G
\]

**Warning:** This inequality is **not a proof of data safety**. It only aids planning when scopes are fully repaired, node availability fits assumptions, and version-specific conditions hold. If a replica stays DOWN longer than the protection window or coverage remains incomplete, a clean schedule still fails.

### 5.1. Budget example on a 10-day grace table

| Component | Allowance |
|---|---:|
| Grace G | 10 days |
| Schedule interval I | 3 days |
| Repair duration Dmax | 1.5 days |
| Retry/queue F | 1 day |
| Outage/maintenance O | 2 days |
| Buffer B | 1 day |
| **Total Lbudget** | **8.5 days** |
| **Headroom** | **1.5 days** |

This hypothetical plan has margin under the formula, but it is only a **design input**. If a node outage stretches another 2 days or a job leaves failed ranges, the scope must transition to **AT_RISK**/escalation rather than waiting for the next cron run.

### 5.2. Tracking age since last verified repair

A useful operational clock:

~~~text
coverage_age = now - last_verified_success_at
coverage_headroom = grace - coverage_age - repair_eta - buffer

If coverage_headroom <= 0:
    cannot promise safe completion under current schedule;
    fire high-priority alert, investigate replicas/repair.

If job PENDING while grace still has margin:
    enqueue by priority + resource budget.

If job FAILED or topology changed:
    do not treat previous START time as fresh coverage.
~~~

Use **UTC timestamps** and monotonic/elapsed durations, not "it is Sunday again." In production you want to bound **the oldest unpropagated tombstone**, which is rarely directly observable; therefore `coverage_age` is a conservative indicator to avoid neglecting scopes, not proof every delete is safe.

### 5.3. Estimating Dmax from real telemetry

Never derive Dmax mechanically from raw GB alone. Repair involves validation, comparison, and potentially streaming divergent data; duration depends on:

- Number of SSTables/ranges and data size.
- Network sender/receiver capacity and cross-DC links.
- Disk read/write IOPS and latency.
- GC/heap/off-heap pressure and pending compactions.
- Number of concurrent sessions, repair mode, and topology.
- Data divergence across replicas and DOWN/lagging nodes.
- Overlapping backups, bootstraps, or other streaming tasks.

Use **observed p95/p99 repair duration per table/range** with conservative bounds; update Dmax when topology or data size changes. Never assume repairing 10 TB finishes in 1 hour just because the initial run on an empty table was fast.

## 6. Choosing full, incremental, and subrange repair by version

Cassandra supports several repair mechanisms/variants depending on version and operational tooling. Common modes include **full repair**, **incremental repair**, **primary-range repair**, DC/host/range selection, and specialized operator/repair-service orchestration.

### 6.1. No single repair command fits every cluster

| Decision | Objective | What must be verified |
|---|---|---|
| **Full repair** | Compare data across scopes using full validation on relevant replicas | Version, impact on repaired/unrepaired SSTables, I/O, duration |
| **Incremental repair** | Reduce work via repaired-data tracking and version scheduling | Preconditions, bookkeeping, failure recovery, and compatibility |
| **Subrange repair** | Split large work into smaller token ranges | Range syntax, ownership, and gap-free coverage |
| **Primary-range repair** | Partition repair across primary ranges per tool mechanics | Do all ranges and replicas/DCs get covered over a full cycle? |
| **DC-scoped repair** | Limit repaired scope to a specific DC | Multi-DC business invariants; could another DC miss deletes? |
| **Operator-managed repair** | Automate job/lock/metric orchestration | Does tooling truly track completed ranges, topology, and retries? |

Do not pick **incremental** merely because the name sounds lighter. How repaired SSTables are marked/reconciled, how failed jobs recover, and how full/incremental interact change across Cassandra versions. Schedule according to official documentation for your **pinned version** and staging evidence.

### 6.2. Why do subranges help automation?

A massive full-table repair can run for a long time, have an unpredictable ETA, and hurt read p99 during peak traffic. Splitting by token ranges supports:

1. Tracking exactly which scopes completed.
2. Prioritizing ranges closest to exhausting their grace budget.
3. Limiting concurrency on participating nodes.
4. Retrying only failed ranges (when safely supported by tooling/version).
5. Pausing dispatch of new tasks per SLO without discarding existing progress evidence.

**Trap:** A skipped range does not magically succeed because 99 other ranges finished. Total coverage must be the **union of all required ranges in the current topology**, with no invalid overlaps or gaps in token ownership.

### 6.3. Do not mix repaired/unrepaired state carelessly

Some incremental modes maintain metadata tracking repaired/unrepaired SSTables or pending repair states. If a job is interrupted, which actions can resume/retry and which ranges truly finalized depend on the version.

The runbook must record:

- Repair mode and version for each job.
- SSTable/pending repair state if surfaced by tooling.
- Scopes meeting the tool's full completion criteria, not merely "validation started."
- Behavior on session failure, coordinator crash, or topology change.
- Vendor/version-approved procedures for recovering/fixing bookkeeping.

Never edit system tables or SSTable metadata directly to "mark repaired" without evidence.

## 7. CQL lab: reading grace, TTL, and data scopes

### 7.1. Query-driven keyspace and tables

Lab example using one DC **dc1**, RF=3; run only when the lab cluster has matching replicas.

~~~sql
CREATE KEYSPACE IF NOT EXISTS repair_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

-- Tenant + day event history supporting partitioned queries.
CREATE TABLE IF NOT EXISTS repair_lab.events_by_tenant_day (
    tenant_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((tenant_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (
    occurred_at DESC, event_id ASC
) AND gc_grace_seconds = 864000;

-- Point lookup by logical request.
CREATE TABLE IF NOT EXISTS repair_lab.state_by_request (
    tenant_id uuid,
    request_id uuid,
    state text,
    updated_at timestamp,
    PRIMARY KEY ((tenant_id, request_id))
) WITH gc_grace_seconds = 864000;
~~~

**Explanation:**

- **(tenant_id, event_day)** is the composite partition key for events; daily queries must bind both.
- **(tenant_id, request_id)** identifies one logical request. It supports write/delete reconciliation on timeout without minting new IDs on retry.
- Both tables can accumulate tombstones from DELETE/TTL and need repair by token/replica scope.
- **gc_grace_seconds** here is a hypothetical lab choice, not a value to copy blindly into production.
- Data size, partition count, and tombstone ratio differ between the two tables, so Dmax and repair priority differ.

### 7.2. Reading actual metadata instead of guessing defaults

~~~sql
SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'repair_lab';

SELECT keyspace_name, table_name, gc_grace_seconds,
       default_time_to_live, compaction
FROM system_schema.tables
WHERE keyspace_name = 'repair_lab';

SELECT column_name, kind, position, type
FROM system_schema.columns
WHERE keyspace_name = 'repair_lab'
  AND table_name = 'events_by_tenant_day';
~~~

An automated catalog must **re-read schema periodically** because new tables or `ALTER TABLE` statements can change grace, TTL, or compaction without the scheduler knowing. If metadata differs across nodes, resolve **schema agreement** before trusting coverage or scheduling against new values.

### 7.3. Writing with TTL, deleting, and inspecting cells

~~~sql
-- Fixture with deterministic request ID; TTL is for lab illustration only.
INSERT INTO repair_lab.state_by_request (
    tenant_id, request_id, state, updated_at
) VALUES (
    11111111-1111-4111-8111-111111111111,
    22222222-2222-4222-8222-222222222222,
    'ACTIVE', '2026-11-21T08:00:00Z'
) USING TTL 600;

SELECT state,
       TTL(state) AS state_ttl_seconds,
       WRITETIME(state) AS state_write_micros
FROM repair_lab.state_by_request
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND request_id = 22222222-2222-4222-8222-222222222222;

DELETE FROM repair_lab.state_by_request
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND request_id = 22222222-2222-4222-8222-222222222222;
~~~

**TTL(state)** returns remaining seconds on a TTL-enabled cell; **WRITETIME(state)** returns the cell's write timestamp in microseconds. After DELETE or expiration, standard CQL cannot inspect full tombstone/replica history for a row, so one SELECT result cannot prove repair safety.

**Note:** `updated_at` is business metadata; passing a fixed historical timestamp does not make the TTL expire immediately. TTL is evaluated from mutation time, not from `updated_at`.

### 7.4. Data scope is more than row count

When selecting repair ranges, know:

- Partition key distribution, token ownership, and replication topology.
- SSTable bytes, tombstone density, disk I/O, and compaction backlog.
- Whether the table uses TTL/default TTL, is delete-heavy, or is append-only.
- Partition size / hot partition thresholds.
- Whether other tables sharing the same nodes/volumes carry heavy workloads.

Low row count does not guarantee lightweight repair if large SSTables, dense tombstones, or congested disks exist. Never let the scheduler run `ALLOW FILTERING`/full-table scans to count rows during preflight; rely on schema, metrics, token/range estimates, and proper read-only monitoring.

## 8. DC/replica scope and the nuances of LOCAL_QUORUM

Suppose a keyspace uses **NetworkTopologyStrategy**:

~~~text
dc1: RF = 3
dc2: RF = 3

A partition K has:
  dc1: A, B, C
  dc2: D, E, F
~~~

A DELETE at **LOCAL_QUORUM** from dc1 can satisfy local replicas without guaranteeing every replica in dc2 has received the delete. If applications read from dc2 or other writers exist, the repair strategy must account for **cross-DC consistency and scope** per your configuration and version.

### 8.1. Mandatory questions before selecting DC scope

1. In which DCs must data be preserved; is cross-DC replication active?
2. Do APIs read/write at **LOCAL_ONE, LOCAL_QUORUM, QUORUM**, or another CL?
3. Which DCs accept writes, and are LWT/serial-consistency operations used?
4. Is the repair tool configured **local-DC only**, or does it compare replicas across DCs?
5. Has any network partition or WAN outage lasted near the grace window?
6. Is completing a scope in dc1 sufficient under cluster-wide coverage policy?
7. Are there data-residency constraints restricting cross-region repair/streaming?

### 8.2. Avoid false conclusions from one healthy DC

A dc1 dashboard showing "100% repaired" does not prove dc2 is fully reconciled. The scheduler must track **per-DC scope** and report system-wide status against the business consistency policy rather than copying dc1 success onto dc2.

Likewise, raising consistency level cannot resurrect a purged tombstone. If zombie data occurs, you need an audit/deletion ledger or business source of truth and a reconciliation plan.

### 8.3. Replica downtime exceeding grace is a special case

If a replica was unavailable longer than `gc_grace_seconds` and deletes occurred during that period:

- **Do not automatically return the node to service** merely because gossip reports UP.
- Do not assume a subsequent repair run suffices once tombstones may have purged.
- DBA/SRE must assess potential zombie data and follow version-specific rebuild/replace/quarantine procedures and source-of-truth reconciliation.
- Preserve logs, snapshots/backups, repair sessions, and topology evidence.
- Classify status as **AT_RISK / ESCALATE** immediately even if the next cron run is still days away.

## 9. Automation architecture: planner, runner, ledger, and verifier

~~~mermaid
flowchart TD
    A["Schema & topology discovery"] --> B["Coverage ledger per table/range/DC"]
    C["Repair metrics & job history"] --> B
    B --> D["Planner: risk/deadline & duration estimate"]
    D --> E{"Eligibility: health, capacity, change window"}
    E -->|No| F["DEFER + alert + updated deadline"]
    E -->|Yes| G["Acquire shared lease/fencing"]
    G --> H["Repair runner via approved operator/tool"]
    H --> I["Collect range/session result + logs"]
    I --> J{"Verified coverage matches plan?"}
    J -->|Yes| K["Update last_verified_success_at"]
    J -->|Partial/failed| L["Record uncovered ranges, retry/escalation"]
    K --> B
    L --> B
~~~

### 9.1. Clear separation of responsibilities

| Component | Role | Must not do |
|---|---|---|
| **Discovery** | Read schema options, RF/DC, topology, table catalog | Alter schemas to fit the schedule |
| **Planner** | Compute deadlines and priorities, choose eligible scopes | Treat job start as success |
| **Admission** | Check node health, SLO, headroom, maintenance overlap | Start multiple jobs on full disks |
| **Runner** | Invoke approved repair tooling, track sessions | Issue CQL to simulate replica repair |
| **Verifier** | Verify repair status/coverage per scope | Mark whole table complete from one range |
| **Ledger** | Persist scopes, last success, failures, and evidence | Store only the latest cron timestamp |
| **Alerting** | Alert on near-deadline, stale/failed coverage | Alert only when cron process exits non-zero |

### 9.2. States to support

~~~text
DISCOVERED
  -> ELIGIBLE
  -> PLANNED
  -> RUNNING
  -> VERIFYING
  -> COMPLETED (verified scope)
  -> STALE (by time or topology)

RUNNING/VERIFYING
  -> PARTIAL (some ranges incomplete)
  -> FAILED (job could not complete)
  -> UNKNOWN (missing evidence, lost coordinator/scheduler)

FAILED/PARTIAL/STALE/UNKNOWN
  -> RETRY_ELIGIBLE or ESCALATED
  -> PLANNED if still safe and approved
~~~

**Rule:** Transition to **COMPLETED** only after the verifier holds evidence that the plan's table/ranges/DC/replica scope finished per tool/version rules. A timer, network retry, or worker reboot must never flip UNKNOWN to COMPLETE.

### 9.3. Durable, contention-free ledger

A scheduler can crash after repair finishes on Cassandra but before updating the ledger. Conversely, the ledger can say "RUNNING" while server-side repair already failed. Therefore you need:

- An immutable **run ID / plan ID** for each logical repair scope.
- Scoped lease/lock/fencing to prevent two runners from over-repairing shared nodes.
- **Startup reconciliation**: inspect actual repair job/session state before launching new work.
- Recorded **evidence pointers** (logs, session IDs, verifier output) for auditing.
- Never rely on a Cassandra row TTL lock as an across-system exactly-once transaction; runners need proper fencing and idempotency.
- Never cram metadata for millions of scopes into **one hot partition** if using Cassandra as the ledger; model tables for queries and capacity.

### 9.4. Keep policy changes under service-owner review

A repair planner must not autonomously alter `gc_grace`, RF, compaction strategy, or repair mode when nearing a deadline. Those are DBA/SRE decisions requiring data and version impact review. The scheduler only **measures, prioritizes, rejects unsafe jobs, alerts, and invokes approved runbooks**.

## 10. Admission control: never repair when the cluster lacks headroom

An on-time repair that times out every Cassandra request or fills disks is bad automation. The planner needs a **resource gate** before the runner starts new work.

### 10.1. Minimum gate signals

| Layer | Metric/check | Why it matters |
|---|---|---|
| **Topology** | Nodes UP/NORMAL, schema agreement, DC/rack, ownership | Do not start while the cluster is transitioning outside a runbook |
| **Replica availability** | Replicas available to serve CL | Avoid increasing quorum-loss risk |
| **Storage headroom** | Absolute and % free disk, SSTable forecast | Streaming/compaction can consume extra disk |
| **Disk performance** | Read/write IOPS, queue depth, await/p99 | Repair validation competes for I/O with CQL |
| **Network** | Bytes/s, retransmits, cross-DC link | Repair streaming can saturate WAN/NIC |
| **JVM** | GC pauses, heap/off-heap, CPU | Validation/streaming increases memory/CPU pressure |
| **Cassandra internals** | Pending compactions, thread pools, dropped tasks | Reveals existing background bottlenecks |
| **User-facing** | Successful RPS, p95/p99, timeout/error budget | Protects Java services |
| **Maintenance** | Bootstrap, upgrade, backup copy, restore | Prevents unapproved overlapping background tasks |
| **Repair operations** | Active sessions, failed ranges, duration | Prevents overlapping scopes/nodes |

### 10.2. Concurrency rules must be per node, not just job count

Two different token ranges can both touch nodes A and B. Running two repairs concurrently just because they are "different ranges" can still saturate disk on A.

Maintain a **conflict graph**: each job has a set of participating nodes; run concurrently only when aggregate resources remain sufficient. Cross-DC WAN links also need a shared bandwidth budget. You can:

- Cap concurrent repair jobs cluster-wide and per node/DC.
- Cap streaming bandwidth where tooling/version supports it.
- Reserve windows for backups, bootstraps, upgrades, and DR drills.
- Prioritize near-deadline jobs without forcing execution when the cluster loses quorum.
- Trigger escalation when deadlines conflict with SLO/capacity, rather than silently skipping.

### 10.3. GO / DEFER / STOP / ESCALATE states

| State | When | Action |
|---|---|---|
| **GO** | Valid scope, healthy nodes, sufficient capacity, within deadline | Acquire lease and start per runbook |
| **DEFER** | Outside maintenance window or temporary headroom shortage with margin left | Reschedule explicitly, keep alerts if lag grows |
| **THROTTLE** | Running repair raises p99/I/O and tooling supports throttling | Rate-limit using version-specific mechanisms |
| **STOP/PAUSE** | Correctness, quorum, SLO, or disk safety threatened | Stop dispatching new jobs; handle active jobs per runbook |
| **ESCALATE** | Near grace, prolonged failed coverage, long-stale replica | DBA/SRE decides fix-forward/quarantine/rebuild/reconciliation |

**STOP does not mean killing the Cassandra process.** An active repair session may require a specific terminate/resume procedure; never manually delete repair metadata or SSTables.

### 10.4. Illustrative SLO profile

~~~yaml
example_policy_only:
  app_read_p99_ms_max: 250
  logical_error_percent_max: 1.0
  min_successful_rps: 900
  disk_free_min_percent: 20
  disk_free_absolute_gib_min: "<estimated-stream-and-compaction-headroom>"
  max_repair_jobs_per_node: 1
  max_cluster_concurrent_repairs: 2
  pause_new_repairs_during:
    - "bootstrap"
    - "restore"
    - "heavy-backup-copy"
  escalate_when_remaining_grace_hours_below: 48
~~~

Values like **250 ms, 900 RPS, 20%, 1 or 2 jobs** are illustrative environment assumptions, not Cassandra standards. Derive thresholds from actual cluster SLOs and capacity measurements. On large disks, free percentage alone cannot predict repair/SSTable streaming headroom needs.

## 11. Scheduling is more than a CronJob

### 11.1. Cron only wakes up the planner

A Kubernetes CronJob or host cron can periodically invoke the **repair planner**, while the planner evaluates deadlines, coverage, and health to choose scopes.

~~~mermaid
sequenceDiagram
    participant T as Cron trigger
    participant P as Repair planner
    participant L as Coverage ledger
    participant H as Health & metrics
    participant R as Approved repair runner
    participant V as Verifier
    T->>P: Wake up
    P->>L: Read table/range/DC coverage
    P->>H: Read RF/topology, p99, disk, active jobs
    P->>P: Compute deadlines & select eligible scope
    P->>R: Acquire lease and execute approved plan
    R-->>P: Execution status + run ID
    P->>V: Verify ranges, replica scope and evidence
    V-->>L: Persist verified success or uncovered scopes
    P-->>T: Summary + alerts
~~~

If cron misses a run, the scheduler must alert rather than waiting for the next tick if any scope nears grace. Triggers can also arrive twice, so runners must be idempotent by plan ID with global lease/fencing.

### 11.2. Illustrative Kubernetes CronJob skeleton

~~~yaml
# SKELETON: requires implementing image, RBAC, service account,
# secrets, HA state/lease, and approved repair orchestrator separately.
apiVersion: batch/v1
kind: CronJob
metadata:
  name: cassandra-repair-planner
spec:
  schedule: "0 2 * * *"
  timeZone: "Etc/UTC"
  concurrencyPolicy: Forbid
  startingDeadlineSeconds: 3600
  successfulJobsHistoryLimit: 7
  failedJobsHistoryLimit: 7
  jobTemplate:
    spec:
      backoffLimit: 0
      activeDeadlineSeconds: 7200
      template:
        spec:
          serviceAccountName: cassandra-repair-planner
          restartPolicy: Never
          containers:
            - name: planner
              image: registry.example.invalid/cassandra-repair-planner:<pinned-tag>
              command: ["/app/repair-planner"]
              args:
                - "--mode=plan-and-dispatch"
                - "--policy=approved-staging"
              resources:
                requests:
                  cpu: "100m"
                  memory: "128Mi"
                limits:
                  cpu: "500m"
                  memory: "512Mi"
~~~

**Do not apply this template directly to a real cluster.** Image and binary are placeholders; this example **does not provide** an actual repair runner or grant Cassandra permissions. `spec.timeZone` support depends on Kubernetes version; check your cluster API before using. CronJob `Forbid` only prevents overlap among jobs managed by **that same CronJob**; it is **not a distributed lock across other repair tools**.

### 11.3. When the planner disconnects or exceeds its deadline

- **STARTED** does not mean COMPLETE.
- Upon restart, the planner must inspect the ledger and operator repair session state before deciding to retry.
- A job exceeding `activeDeadlineSeconds` may be terminated at the container level by Kubernetes while server-side repair is still running or needing tool-specific cleanup.
- Prolonged scheduler downtime increases **coverage age**; alerts must identify overdue or low-margin scopes.
- Mark unconfirmed scopes **UNKNOWN**, never speculative success.

### 11.4. Fencing to prevent double execution

Global leases must guard against:

1. Two schedulers picking up the same scope.
2. Worker A holding a lease, pausing (e.g., GC/network), lease expiring, and worker B claiming the scope.
3. Worker A waking back up and issuing repair commands after losing ownership.

Solutions include **lease + fencing token/epoch** validated by the runner before issuing new operations, or a repair operator with built-in concurrency control; either way, partial failures and reconciliation must still be handled.

A Cassandra row lock TTL **does not guarantee workflow-wide exactly-once execution**. With LWT lock claims, understand `[applied]` true/false/`UNKNOWN`, serial consistency, and lease expiration while a job is still running.

## 12. Java: computing repair deadlines and scope priorities without calling nodetool

**The Java Driver does not provide a CQL `REPAIR` statement** to invoke directly. Planner logic can be written in pure Java, reading metadata, the ledger, and metrics, then delegating execution to an **approved operator or repair tool**.

Below is an example function scoring a scope from its last verified success timestamp. It intentionally makes no OS calls and performs no cluster mutations.

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

public final class RepairDeadlinePolicy {
    public enum Urgency {
        MISSING_COVERAGE,
        STALE_TOPOLOGY,
        CRITICAL,
        SCHEDULE_SOON,
        NORMAL
    }

    public static final class Decision {
        public final Urgency urgency;
        public final Instant latestSafeStartEstimate;
        public final Duration timeUntilLatestStart;

        public Decision(Urgency urgency,
                Instant latestSafeStartEstimate,
                Duration timeUntilLatestStart) {
            this.urgency = urgency;
            this.latestSafeStartEstimate =
                latestSafeStartEstimate;
            this.timeUntilLatestStart =
                timeUntilLatestStart;
        }
    }

    private RepairDeadlinePolicy() {}

    public static Decision evaluate(
            Instant now,
            Instant lastVerifiedSuccess,
            Duration gcGrace,
            Duration estimatedRepairDuration,
            Duration retryReserve,
            Duration safetyBuffer,
            Duration notifyWindow,
            boolean scopeVerified,
            boolean topologyMatches) {

        Objects.requireNonNull(now);
        Objects.requireNonNull(gcGrace);
        Objects.requireNonNull(estimatedRepairDuration);
        Objects.requireNonNull(retryReserve);
        Objects.requireNonNull(safetyBuffer);
        Objects.requireNonNull(notifyWindow);

        if (gcGrace.isNegative() || gcGrace.isZero()
                || estimatedRepairDuration.isNegative()
                || retryReserve.isNegative()
                || safetyBuffer.isNegative()
                || notifyWindow.isNegative()) {
            throw new IllegalArgumentException(
                "Durations must be nonnegative; gcGrace > 0");
        }

        if (!topologyMatches) {
            return new Decision(
                Urgency.STALE_TOPOLOGY, null, null);
        }
        if (!scopeVerified || lastVerifiedSuccess == null) {
            return new Decision(
                Urgency.MISSING_COVERAGE, null, null);
        }

        // Estimate only; NOT an assertion of tombstone safety.
        Instant latest = lastVerifiedSuccess
            .plus(gcGrace)
            .minus(estimatedRepairDuration)
            .minus(retryReserve)
            .minus(safetyBuffer);
        Duration remaining = Duration.between(now, latest);

        if (!now.isBefore(latest)) {
            return new Decision(Urgency.CRITICAL, latest, remaining);
        }
        if (remaining.compareTo(notifyWindow) <= 0) {
            return new Decision(
                Urgency.SCHEDULE_SOON, latest, remaining);
        }
        return new Decision(Urgency.NORMAL, latest, remaining);
    }
}
~~~

**Crucial limitations:**

- `lastVerifiedSuccess` reflects valid, topology-matching scope completion, not job start timestamp.
- `latestSafeStartEstimate` is only a conservative planning deadline, not a guarantee that tombstones have not purged.
- When `scopeVerified=false` or topology changed, the function demands investigation rather than auto-triggering repair or forging a success time.
- It does not check **node health, RF/DC, disk headroom, maintenance overlap, or failed repair sessions**; an external admission gate must verify those before running.
- A node DOWN past grace requires escalation even if other replicas have recent last-success timestamps.
- Production requires synchronized UTC clocks and real repaired coverage/duration data; never rely on unmanaged local wall-clocks.

### 12.1. Policy application example

~~~java
Instant now = Instant.parse("2026-11-21T08:00:00Z");
Instant lastOk = now.minus(Duration.ofDays(7));

RepairDeadlinePolicy.Decision decision =
    RepairDeadlinePolicy.evaluate(
        now,
        lastOk,
        Duration.ofDays(10),
        Duration.ofHours(12),
        Duration.ofHours(12),
        Duration.ofDays(1),
        Duration.ofDays(2),
        true,
        true);

System.out.println(
    "Repair urgency = " + decision.urgency);
// Expected: SCHEDULE_SOON, as little margin remains until latest safe start.
~~~

This is pure time arithmetic with no I/O or cluster mutations. Across thousands of scopes, the planner can sort by **ascending `timeUntilLatestStart`**, then filter through admission control to defer ineligible scopes. Never suppress **CRITICAL/MISSING_COVERAGE** alerts merely because a job could not start due to cluster overload; alert the owner.

### 12.2. JUnit tests for budget exhaustion

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import java.time.Duration;
import java.time.Instant;

import org.junit.jupiter.api.Test;

public class RepairDeadlinePolicyTest {
    private static final Instant NOW =
        Instant.parse("2026-11-21T08:00:00Z");

    @Test
    void marksCriticalWhenNoBudgetToFinish() {
        RepairDeadlinePolicy.Decision result =
            RepairDeadlinePolicy.evaluate(
                NOW, NOW.minus(Duration.ofDays(10)),
                Duration.ofDays(10), Duration.ofDays(1),
                Duration.ofHours(2), Duration.ofHours(12),
                Duration.ofDays(2), true, true);

        assertEquals(
            RepairDeadlinePolicy.Urgency.CRITICAL,
            result.urgency);
    }

    @Test
    void missingCoverageIsNotTreatedAsSuccess() {
        RepairDeadlinePolicy.Decision result =
            RepairDeadlinePolicy.evaluate(
                NOW, NOW.minus(Duration.ofDays(1)),
                Duration.ofDays(10), Duration.ofDays(1),
                Duration.ofDays(1), Duration.ofDays(1),
                Duration.ofDays(2), false, true);

        assertEquals(
            RepairDeadlinePolicy.Urgency.MISSING_COVERAGE,
            result.urgency);
        assertNull(result.latestSafeStartEstimate);
    }

    @Test
    void topologyChangeInvalidatesOldCoverage() {
        RepairDeadlinePolicy.Decision result =
            RepairDeadlinePolicy.evaluate(
                NOW, NOW.minus(Duration.ofHours(3)),
                Duration.ofDays(10), Duration.ofDays(1),
                Duration.ZERO, Duration.ofDays(1),
                Duration.ofDays(2), true, false);

        assertEquals(
            RepairDeadlinePolicy.Urgency.STALE_TOPOLOGY,
            result.urgency);
    }

    @Test
    void marksNormalWhenSufficientPlanningMargin() {
        RepairDeadlinePolicy.Decision result =
            RepairDeadlinePolicy.evaluate(
                NOW, NOW.minus(Duration.ofDays(1)),
                Duration.ofDays(10), Duration.ofDays(1),
                Duration.ofHours(12), Duration.ofDays(1),
                Duration.ofDays(2), true, true);

        assertEquals(
            RepairDeadlinePolicy.Urgency.NORMAL,
            result.urgency);
    }
}
~~~

These unit tests verify only **time and coverage logic**; they do not prove repair actually synchronized Cassandra. Integration tests require replica, failed-repair, and topology evidence along with version-specific tool verification.

## 13. Java Driver 4.x: reading schema for safe cataloging

The Java Driver is used to **read CQL/schema and observe workloads**, not as an API replacing `nodetool repair`. Below is a probe that reads table metadata, classifies tables, and feeds the planner.

~~~java
import java.net.InetSocketAddress;
import java.util.ArrayList;
import java.util.List;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class RepairTableCatalogReader {
    public static final class TableOptions {
        public final String tableName;
        public final int gcGraceSeconds;
        public final int defaultTtlSeconds;

        public TableOptions(String tableName,
                int gcGraceSeconds, int defaultTtlSeconds) {
            this.tableName = tableName;
            this.gcGraceSeconds = gcGraceSeconds;
            this.defaultTtlSeconds = defaultTtlSeconds;
        }
    }

    public static List<TableOptions> read(
            CqlSession session, String keyspace) {
        PreparedStatement query = session.prepare(
            "SELECT table_name, gc_grace_seconds, " +
            "default_time_to_live " +
            "FROM system_schema.tables " +
            "WHERE keyspace_name = ?");

        List<TableOptions> results = new ArrayList<>();
        for (Row row : session.execute(query.bind(keyspace))) {
            results.add(new TableOptions(
                row.getString("table_name"),
                row.getInt("gc_grace_seconds"),
                row.getInt("default_time_to_live")));
        }
        return results;
    }

    public static void main(String[] args) {
        // LAB ONLY. Production: configure TLS/auth, DC and secrets.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            List<TableOptions> catalog =
                read(session, "repair_lab");

            for (TableOptions option : catalog) {
                System.out.printf(
                    "table=%s grace=%ds defaultTTL=%ds%n",
                    option.tableName,
                    option.gcGraceSeconds,
                    option.defaultTtlSeconds);
            }
        }
    }
}
~~~

### 13.1. What this probe can and cannot do

**Can do:**

- Read `gc_grace_seconds`/default TTL for tables visible to the session.
- Detect new tables or grace/retention changes requiring planner review.
- Supply inputs to the **deadline budget** once combined with the ledger and repair duration.
- Run read-only under least privilege.

**Cannot do:**

- Know for sure that every node in every DC received a tombstone.
- Prove full repair range coverage; that evidence must come from the operator/session verifier.
- Conclude a table can lower grace solely from its default TTL.
- Measure data size, compaction, or token ownership from schema options alone.
- Trigger anti-entropy repair through regular `SELECT`/CQL statements.
- Infer the **business source of truth** of a DELETE once tombstones are gone.

### 13.2. Catalog caching and schema changes

There is no need to query `system_schema` on every Java application request. The scheduler can run **periodic discovery** paired with schema/topology change events. However, if an `ALTER TABLE` lowers grace or a new table is created between runs, mark affected scopes **REVIEW_REQUIRED** and recompute deadlines before scheduling.

If schema metadata differs across nodes, verify schema agreement first; **never start repair against an unstable catalog**.

### 13.3. Managing credentials

Use a read-only account for catalog/metrics whenever possible, and a separate privileged account for the repair operator. Never grant user-facing Java APIs permission to trigger `nodetool repair`. Secrets must flow through approved secret management; never hardcode production passwords or contact points in documentation or logs.

## 14. Metrics and nodetool: evidence for coverage, not just CPU

### 14.1. Read-only observation commands

According to your Cassandra version's syntax and support:

~~~bash
# Node status, DC/rack, and JOINING/UP/DOWN state.
nodetool status

# Node info and resource usage.
nodetool info

# Streaming/repair network activity (version-dependent).
nodetool netstats

# Pending/dropped thread pool tasks.
nodetool tpstats

# Active compactions and backlog.
nodetool compactionstats

# Table-level SSTable/read/write/tombstone statistics.
nodetool tablestats repair_lab.events_by_tenant_day

# Partition-size/row-size histograms if supported by version.
nodetool tablehistograms repair_lab events_by_tenant_day

# Snapshot retention when diagnosing disk headroom.
nodetool listsnapshots
~~~

A single snapshot of `nodetool netstats` is insufficient to measure streaming throughput; collect samples over time and distinguish bytes sent/received and failed sessions. Likewise, `nodetool status = UN` does not prove anti-entropy repair has completed.

### 14.2. Repair runner must record completion evidence

| Data group | Required fields |
|---|---|
| **Plan identity** | Cluster, planId, runId, mode/version |
| **Scope** | Keyspace/table, token ranges, DC/replicas |
| **Timing** | Enqueued, started, completed, verified timestamps |
| **Result** | COMPLETED/PARTIAL/FAILED/UNKNOWN and failed scopes |
| **Progress** | Validation ranges, streaming sessions/bytes, pending tasks |
| **Resource** | Per-node disk/CPU/GC/network, compaction backlog |
| **Service** | Successful RPS, p95/p99, Read/WriteTimeout, Unavailable |
| **Audit** | Tool/operator version, repair command profile, log pointers |
| **Topology** | Token ownership/replica scope at start and verification |
| **Safety** | Quorum, disk headroom, and stop-gate decisions |

A sound verifier **reconciles planned scopes against scopes actually marked complete by the tool**. If a table has 10 ranges and only 9 succeed, mark PARTIAL and keep the 10th range queued/alerting.

### 14.3. Correlating repair with Java application errors

Suppose repair raises disk await and the Java application sees `DriverTimeoutException`/`ReadTimeoutException`/`OverloadedException`. Build a combined timeline:

~~~text
T0  : healthy baseline p99
T1  : repair R1 start
T2  : disk reads + pending compactions rise
T3  : read p99 & client timeouts rise
T4  : operator throttles/pauses per runbook
T5  : latency and backlog recover
T6  : repair R1 completed or PARTIAL recorded by verifier
~~~

**Never** equate correlation with causation automatically; check concurrent backups/ETL, hot partitions, GC, and traffic shifts. Even when repair appears to be the trigger, interventions must follow **change/incident protocol**.

### 14.4. Alerts should bind to scope and action

Example alert:

~~~json
{
  "alert": "REPAIR_COVERAGE_NEAR_DEADLINE",
  "cluster": "staging-cassandra-a",
  "keyspace": "repair_lab",
  "table": "events_by_tenant_day",
  "dc": "dc1",
  "range_id": "range-07",
  "last_verified_success_utc": "2026-11-14T12:00:00Z",
  "gc_grace_seconds": 864000,
  "estimated_repair_hours": 18,
  "remaining_start_budget_hours": 36,
  "last_job_state": "PARTIAL",
  "next_action": "DBA review failed ranges and health gates"
}
~~~

This JSON is a **hypothetical payload sample**, not a built-in Cassandra metric/alert. In production, include **real config, UTC timestamps, metric sources, and owner**; avoid logging raw tenant keys, payloads, secrets, or sensitive IPs/hostnames to broad channels.

## 15. Handling failed jobs: partial, retry, unknown, and resume

### 15.1. State-based decision table

| Event | Ledger | Right action |
|---|---|---|
| Job scheduled but not yet running | PLANNED | Check trigger/queue and deadline |
| Job running normally | RUNNING | Monitor SLO, I/O, progress, and lease |
| Some ranges complete, others fail | PARTIAL | Keep completed evidence; plan uncovered ranges |
| Node/coordinator dies mid-repair | UNKNOWN or FAILED per evidence | Read session/tool status before re-issuing |
| Validation finished, streaming failed | PARTIAL/FAILED | Do not record whole-range success |
| Ledger not updated after tool finishes | VERIFYING/UNKNOWN | Reconcile using runId/session evidence |
| Topology changes mid-job | STALE_TOPOLOGY or ESCALATE | Re-evaluate owners/ranges; drop old scope |
| Outage exceeds grace, stale replica returns | AT_RISK/ESCALATE | Follow DBA runbook; never repair blindly |
| Disk/correctness/SLO breaches stop gate | PAUSE/STOP | Halt new dispatches; intervene on active job per tool |
| Duplicate job from scheduler restart | DEDUP/RECONCILE | Enforce lease/fencing; avoid concurrent runs |

### 15.2. Exponential backoff is only a secondary guard

Retrying a repair session carries heavy resource cost, unlike retrying a `SELECT`. Raising retry counts will not fix a DOWN node, bad TLS/auth, full disk, or WAN partition.

Illustrative policy:

~~~text
on FAILED:
  1. Record exact uncovered scopes and error taxonomy.
  2. If configuration/auth/disk/full quorum issue:
       ESCALATE, do not blind-retry.
  3. If transient and still enough grace/deadline:
       schedule retry with bounded backoff/jitter.
  4. Before retry:
       recheck topology, health, active sessions and lease.
  5. After completion:
       verify full scope, update last_verified_success.
  6. On repeated failures or near deadline:
       page DBA/SRE; do not silently wait for next cron.
~~~

**Never assume a retry resumes from the exact byte/step where it stopped.** Resume semantics depend on version, tooling, and repair mode. If the full scope must rerun, factor the extra Dmax and capacity into the deadline.

### 15.3. Stopping mid-run differs from undoing work

- Stopping the planner only halts **new dispatches**; it does not guarantee server-side sessions stopped.
- When a coordinator disconnects, repair may leave state requiring cleanup/inspection.
- Never manually delete logs, temporary metadata, or SSTables without DBA confirmation.
- Whether a token range completed before job failure counts as committed depends on mode/version; the verifier must follow tool semantics.
- Never mark an entire table successful simply because the job ran for the expected duration.

### 15.4. Fail-open vs. fail-closed

When monitoring or the ledger is unresponsive, two extremes are dangerous:

- **Fail-open:** keep launching repairs without checking scopes, health, or conflicts; risks overloading the cluster.
- **Absolute fail-closed:** halt all repairs for days, causing coverage to breach grace.

The right approach is **UNKNOWN + owner escalation**, enabling controlled runbook execution or audited overrides when needed. Never grant cluster-mutation authority from an unauthenticated fallback code path.

## 16. Overlapping background tasks: repair, bootstrap, compaction, and backup

Cassandra shares disk, network, and CPU across CQL reads/writes and maintenance. When repair runs alongside other tasks:

~~~text
CQL read/write       -> coordinator + replica disk/commitlog/memtable
Repair validation    -> SSTable reads + CPU/IO
Repair streaming     -> Network + disk read/write
Bootstrap/replace    -> Token ownership + SSTable streaming
Compaction           -> SSTable reads/writes + CPU
Backup snapshot      -> SSTable hard-link retention
Backup copy/upload   -> Disk reads + network/compression
~~~

A deadline-only scheduler lacking health/capacity gates can fire multiple repairs while bootstrap or backup already consumes most I/O.

### 16.1. Test tasks individually before overlapping

| Test | Condition | Metrics to retain |
|---|---|---|
| **C0** | Baseline, no new maintenance started | Successful RPS, p99, errors, disk, GC |
| **R1** | Single repair scope | Duration, validation/stream bytes, p99 impact |
| **R2** | Two supposedly non-conflicting repairs | Per-node disk/network, queues, p99 |
| **B1** | Backup copy alone | Disk read/network impact |
| **X1** | Approved repair + backup | Non-linear queuing, SLO, stop gates |
| **C1** | Post-maintenance recovery | Backlog/latency return to baseline |

If a single repair already violates SLOs, never crank up concurrency to "optimize throughput" before fixing capacity or throttling.

### 16.2. Disk headroom example

Suppose a node sees about **300 MiB/s** disk reads during API traffic, repair validation adds an estimated **220 MiB/s**, and effective capacity for a similar workload is around **450 MiB/s**:

~~~text
Rough demand       = 300 + 220 = 520 MiB/s
Effective headroom = 450 - 300 = 150 MiB/s
Shortfall vs est.  = 70 MiB/s
~~~

This is a **rough back-of-the-envelope estimate**, not an exact IOPS/latency rule. Under random read/write workloads, disk queues and I/O p99 can degrade well before hitting sequential MiB/s limits. The scheduler must watch **latency/queues** and validate load in staging.

## 17. Practical operational lifecycle: end-to-end

### 17.1. Preflight before starting repair

- Cluster/topology stable, no unexpected DOWN nodes.
- Schema agreement, keyspace/table options, and RF/DC verified.
- Previous repair cycle ledger complete; uncovered scopes known.
- Current backup/recovery points exist per policy.
- No unapproved overlapping restore/bootstrap/upgrade.
- Disk/network/CPU/GC headroom and green SLOs confirmed.
- Plan specifies version/tool-appropriate full/incremental/subrange/DC scope.
- Operator permissions, lease/fencing, log correlation, and rollback/stop plans in place.
- Duration estimate and grace-expiry/STOP thresholds defined.
- Clear owner assigned if repair ends partial or unknown.

### 17.2. During execution

1. Record **start UTC, runId, planId, topology generation**.
2. Track each range, status, and replica participant.
3. Collect validation progress, bytes streamed, retries, and failures.
4. Monitor app p95/p99, successful RPS, error budget, and disk/GC/compaction.
5. Never lower app consistency levels to mask errors.
6. If stop gates trip, block new jobs and handle active sessions per runbook.
7. If a node drops, classify partial/unknown and prevent cron from stacking another job on top.
8. Log every DEFER/PAUSE/ESCALATE decision and rationale.

### 17.3. After completion

1. Verify actual scope equals planned scope per tool/version.
2. Update `last_verified_success_at` **only** for genuinely completed scopes.
3. Retain failed/uncovered scopes with updated deadlines; never auto-clear alerts.
4. Verify node health, schema/topology, and SSTable/compaction backlog.
5. Measure a recovery window until p99/throughput/errors stabilize.
6. Cross-check sample keys/partitions via CQL if fixtures exist.
7. Compare duration/I/O against Dmax and tune schedules/queues.
8. Archive evidence, dashboards, incident notes, and change records.
9. Update the backup/repair calendar to avoid future overlaps.
10. Clearly report **COMPLETED, PARTIAL, FAILED, or UNKNOWN**.

## 18. Five operational scenarios and scheduling decisions

### 18.1. Case A — Cron reports green while one range was missed

**Hypothetical context:** A table has 20 token ranges per the chunking policy. Sunday's cron runs reliably and the job dashboard is green, yet the verifier finds:

~~~text
Run 2026-W47:
  19 ranges COMPLETED
   1 range FAILED: dc1/range-R11
  Job controller exit: 0
  Coverage ledger: R11 has no verified success for 11 days
  Table gc_grace_seconds: 864000 (10 days)
~~~

**Analysis:** Exit code 0 does not prove table-wide repair. **R11 has exceeded its grace budget**; inspect node outages, prior repairs, tombstone purges, and actual data. If R11 held deletes that were not sufficiently propagated, zombie risk exists, though coverage age alone is not final proof.

**Decision:** **ESCALATE**; DBA investigates the failed range, replicas, and data; preserve evidence and follow the repair/recovery/reconciliation runbook. Fix the verifier so the controller never marks COMPLETE when failed scopes remain.

### 18.2. Case B — Replica DOWN approaching grace

~~~text
Table grace = 10 days
Node C DOWN 8 days
DELETEs still written via quorum A+B
Next regular repair = 3 days away
Estimated duration = 1 day
~~~

Waiting for the regular schedule risks C crossing grace before syncing. **On-time cron is not enough.**

**Decision:**

1. Transition the scope to **AT_RISK** based on outage duration and repair budget.
2. DBA/SRE verifies node health, token ownership, deletion history, and recovery path.
3. Never force node C back into service if stale data is suspected.
4. Prioritize safe recovery, repair/rebuild/reconciliation via runbook.
5. Alert earlier so teams do not wait until day 10.

### 18.3. Case C — Repair overlapping backup copy breaches p99 SLO

~~~text
Baseline read p99  = 140 ms
Repair alone       = 200 ms
Backup copy alone  = 190 ms
Both concurrently  = 480 ms, with ReadTimeout
Approved SLO       = 250 ms
~~~

Resource contention can scale **non-linearly** across disk, queues, compaction, GC, and network. Never add p99 numbers linearly to predict overlap impact.

**Decision:** When the stop gate trips, halt new dispatches, throttle tasks via approved tooling, reschedule maintenance, and re-measure in staging. If coverage nears grace, **ESCALATE capacity/scheduling** rather than quietly pushing repair to next week.

### 18.4. Case D — Node replacement invalidates the ledger

~~~text
Before replace:
  range R7 owners = A, B, C
  last verified repair = 2 days ago

After replace:
  range R7 owners = A, B, D
  ledger still lists A, B, C with status COMPLETE
~~~

Old coverage does not automatically guarantee replica D received all data and tombstones, even if bootstrap streaming reported success.

**Decision:** Mark **STALE_TOPOLOGY**, verify replace/streaming/schema/token placement, and run version-specific repair/verification steps. Never copy the old success timestamp onto the new scope.

### 18.5. Case E — Grace lowered via ALTER below the schedule

~~~text
T0: gc_grace_seconds = 864000 (10 days)
I + D + F + O + B = 8.5 days
T1: ALTER TABLE lowers grace to 432000 (5 days)
Planner has not refreshed its catalog
~~~

The old schedule no longer fits the budget. A schema change can turn a NORMAL scope into **CRITICAL/AT_RISK**.

**Decision:** Schema changes must trigger immediate catalog invalidation and policy review, never waiting for the next cron cycle. Lowering grace requires DBA evaluation against outages, repairs, and compaction—not increasing repair runner timeouts.

## 19. Integration testing the scheduler in staging

### 19.1. Separating unit tests, orchestrator tests, and Cassandra cluster tests

| Test layer | Purpose | Does not prove |
|---|---|---|
| **Java unit tests** | Deadline math, state transitions, priority, null/error handling | Anti-entropy repair actually ran |
| **Scheduler integration** | Cron, lease/fencing, ledger persistence, missed runs, retries | Replicas converged accurately on data |
| **Repair operator integration** | Tool invocation, session progress, range verification, failure recovery | All production topologies behave identically |
| **Multi-node Cassandra lab** | RF/CL, repair ranges, temporary node unavailability, tombstone behavior | Any prolonged outage is safe |
| **Load/fault testing** | p99, throughput, disk/network pressure, stop gates | Business source of truth is intact |
| **Recovery drill** | Restore, reconciliation, post-failure coverage | Recovery always works under different versions/data |

A **single-node RF1 Testcontainers** setup is good for basic CQL schema/TTL checks, not for proving repair across RF3 replicas or two DCs.

### 19.2. Testing a missed scheduled run

~~~text
T0: ledger R1 has latest verified success.
T1: planner CronJob misses a run due to controller downtime.
T2: timeUntilLatestStart shrinks.
T3: controller recovers and scans all scopes.
Expected:
  - Do not auto-update R1 last success.
  - Prioritize R1 if near deadline.
  - Emit missed-run/cadence alert.
  - Dispatch only after health gates pass and lease is acquired.
~~~

The verification point is the **ledger and action taken**, not how many CronJobs spawned.

### 19.3. Testing partial repair (9/10 ranges completed)

~~~text
Plan has R1..R10.
Tool result:
  R1..R9 = COMPLETED
  R10 = FAILED

Expected:
  Table = PARTIAL.
  R1..R9 get verified timestamps only if tool semantics allow.
  R10 retains old last success (or UNKNOWN).
  Alert R10 near deadline.
  No table-wide green status.
~~~

Simulate the case where **tool exit code is 0 yet the coverage report lists failed ranges**. The verifier must never trust exit codes alone.

### 19.4. Testing crash after completion before ledger update

~~~text
1. Repair runner completes scope R2 per tool.
2. Planner crashes before writing ledger.
3. Planner restarts, sees R2 = VERIFYING/UNKNOWN.
4. Query repair operator/session evidence by runId.
5. If evidence confirms scope completed:
     update last_verified_success_at with actual completion time.
   If not:
     keep UNKNOWN and escalate; never assume success.
6. Never start a second repair session for the same scope while
   unsure if the old session is still running.
~~~

This is **at-least-once triggering with idempotent orchestration**, not automatic exactly-once execution provided by CronJob.

### 19.5. Testing topology changes and RF/DC

In multi-node staging, simulate a topology generation change (or perform a replace via approved runbook). Verify:

- Old ledger entries are marked **STALE_TOPOLOGY**.
- The scheduler never uses the old owner set to validate new coverage.
- The planner waits for cluster stability and re-runs discovery.
- The verifier evaluates ranges/replicas against the new topology.
- Cross-DC coverage is recorded accurately when per-DC RFs differ.
- Success in dc1 is never copied as success in dc2.

### 19.6. Testing stop gates under repair overload

Using a Java Driver 4.x workload with **bounded arrival rate and in-flight requests**, measure baseline p95/p99/successful RPS. Run an approved staging repair scope and observe:

- Read/WriteTimeout, Unavailable, Overloaded, and retry amplification.
- Disk await/queues, compaction backlog, and network traffic.
- Repair progress/streamed bytes and tool status.
- Gate **PAUSE dispatch** when SLO or disk headroom crosses thresholds.
- Post-pause/post-completion recovery window.
- Never lower test consistency levels mid-measurement, as that breaks comparability.

If fault injection fails to trigger the target condition or telemetry is missing, mark **INCONCLUSIVE**—never force PASS by relaxing thresholds inside the test.

### 19.7. Never induce zombies in production to test

Zombie conditions require missed replicas and tombstone purges under specific circumstances. Only consider reproducing them on a **disposable cluster** with synthetic data, runbooks/approvals, and a recovery path. Do not treat killing nodes, setting `gc_grace_seconds` to 0, or editing SSTables directly as "standard lesson steps."

A safer test makes a lab replica temporarily unavailable for **less than grace**, issues a DELETE at appropriate CL, restores the replica, and runs repair per runbook to verify deleted data does not reappear. This proves the **tested scenario**, not that every outage is safe.

## 20. Common repair scheduling mistakes

| Anti-pattern | Consequence | Fix |
|---|---|---|
| **Cron succeeded = repair succeeded** | Failed ranges go unnoticed | Verify coverage per scope |
| **One `last_repair` timestamp for the whole cluster** | Unknown which table/DC/range is stale | Ledger keyed by table/range/replica scope |
| **Starting before grace is enough** | Job may finish past deadline | Compute `I + Dmax + F + O + B` |
| **Using average duration instead of worst-case** | Large/busy ranges miss deadlines | p95/p99 duration, buffer, and alerts |
| **Lowering `gc_grace_seconds` to reduce tombstones** | Stale replicas can cause zombies | Assess outages, repair, and compaction |
| **`gc_grace_seconds=0` on all TTL tables** | Ignores missed replicas and late writes | Version-specific review and testing |
| **Relying on read repair/hints instead of anti-entropy** | Misses unread partitions and long outages | Scope-verified repair schedule |
| **One DC repaired, mark all DCs green** | Cross-DC replicas may miss deletes | Track explicit per-DC coverage policy |
| **Ignoring topology generation** | Old success applied to new replica owners | Invalidate scopes on topology changes |
| **Mixing full/incremental without understanding modes** | Broken repaired state/verification | Version-specific Cassandra runbook |
| **Treating 99% bytes repaired as 100% safe** | Low-byte critical ranges missed | Verify every required range |
| **Retrying repair immediately when disk is full** | Increases I/O and availability risk | Fix capacity, admission, and backoff |
| **Running different ranges concurrently on the same node** | I/O/GC/network contention | Conflict graph and per-node limits |
| **Overlapping repair with bootstrap/heavy backup** | Tail latency, streaming overload | Maintenance calendar and gates |
| **Force-killing repair sessions when p99 rises** | Partial/pending states need cleanup | Tool/version-approved pause/stop |
| **Deleting snapshots to free disk in an incident** | Risks losing recovery points | Backup verification and retention approval |
| **Restarting a node past grace then immediately repairing** | Risks spreading stale values | DBA risk assessment, quarantine/rebuild if needed |
| **Dropping failure history** | Same ranges fail weekly unnoticed | Alerts, owner, escalation deadlines |
| **Dropping completion timestamp on planner crash** | Ledger diverges from real state | Reconcile runId/session evidence |
| **Checking only `nodetool status` UN** | Node is UP while repair/data/SLO fail | Metrics + verified coverage |
| **Treating repair as backup** | Accidental DELETE or DC loss unrecoverable | Out-of-band backups + restore drills |
| **Exposing repair triggers on user Java HTTP APIs** | Privilege and load risks, no governance | Dedicated operator, least privilege |
| **Lowering app CL so repair looks harmless** | Breaks SLO/consistency comparability | Keep CL contract, measure honestly |
| **Using local time/DST for deadlines** | Schedule drift or skipped runs | UTC + explicit timezone config |
| **Hiding UNKNOWN as COMPLETE** | Unverified ranges dropped from queue | Fail-closed state machine and verifier with escalation |

### 20.1. Distinguishing data remediation from schedule fixes

Once zombie data exists, **fixing future repair schedules does not delete existing bad rows**. You need a business source of truth, audit/deletion ledger, and reconciliation. Conversely, simply re-deleting one row without fixing coverage or outage policies invites recurrence.

### 20.2. Version dependency is mandatory

Changing Cassandra major/minor version, compaction strategy, repair tool/operator, or topology can change:

- Repair flags, partitioning, and range semantics.
- How incremental/full manage SSTables.
- How tooling reports progress, partial failures, and resumed state.
- Validation/streaming overhead and safety during topology changes.
- Monitoring schemas and refusal behavior when replicas are missing.

Therefore, a schedule validated on an older release must be **revalidated** after upgrades rather than assuming all settings and behaviors stay identical.

## 21. Scenario exercises and suggested answers

### Exercise 1 — Is a 7-day schedule safe with 10-day grace?

A table has **G=10 days**, repair start-to-start **I=7 days**, Dmax=2 days, retry delay F=1 day, outage allowance O=1 day, and buffer B=1 day.

**Question:** Does the budget meet the formula in this lesson?

**Answer:** `Lbudget = 7 + 2 + 1 + 1 + 1 =` **12 days**, exceeding 10 days. **Does not meet the design criterion.** Shorten cadence, reduce duration, add headroom, handle outages, or review grace with the DBA. Do not merely change the cron day while ignoring failed ranges.

### Exercise 2 — Repair ran, yet no last verified success exists

Cron finished five minutes ago; the ledger for range R7 remains UNKNOWN because the verifier lost connection to the operator.

**Question:** Should `last_success_at` be updated to now?

**Answer:** No. Reconcile using `runId`/session results to prove R7 and its replica scope finished. Without evidence, keep UNKNOWN/ESCALATE.

### Exercise 3 — A range with very few bytes

100 ranges total; 99 ranges holding 99.9% of bytes repaired successfully, while the remaining range holding 0.1% of bytes FAILED.

**Question:** Can we report 99.9% safe?

**Answer:** You can report byte progress, **never full coverage**. The missing range can still contain tombstones; keep PARTIAL and a dedicated deadline.

### Exercise 4 — GC grace lowered by a migration

The scheduler plans around `gc_grace_seconds=864000`. A migration alters the table to `432000`, while the catalog refreshes only weekly.

**Question:** What are the risk and fix?

**Answer:** A 10-day schedule can overshoot the 5-day grace window, creating risk. Schema changes must invalidate and recalculate plans immediately with review, rather than waiting for periodic cache refreshes.

### Exercise 5 — Repair mostly validation, little streaming

The team sees `netstats` streamed only a few MiB and assumes repair is cheap.

**Question:** Is that true?

**Answer:** No. Validation still reads SSTables and uses CPU/I/O to compare data; measure disk await, CPU/GC, compaction, and app p99. Little divergence does not mean repair is free.

### Exercise 6 — Node DOWN 12 days, grace 10 days

DELETEs were written while node C was DOWN. Node C returns after 12 days, and the orchestrator wants to auto-run repair to "catch up."

**Question:** Should it handle this automatically as routine?

**Answer:** No. Tombstones may already have purged; the stale replica could propagate old data. Mark **AT_RISK/ESCALATE**, preserve evidence, and let the DBA evaluate rebuild/quarantine/reconciliation per runbook. Never assume repair restores lost deletes.

### Exercise 7 — Does LOCAL_QUORUM eliminate the need for repair?

RF3 in dc1, and all deletes are acknowledged at `LOCAL_QUORUM`.

**Question:** Can repair be skipped?

**Answer:** No. One replica can still miss a DELETE even when two replicas ACK. Repair provides anti-entropy and prevents risk when tombstones purge; per-replica/range coverage is still required.

### Exercise 8 — Hinted handoff is enabled

The system has hinted handoff and frequent `LOCAL_QUORUM` SELECTs. Can these replace the entire repair schedule?

**Answer:** No. Hints have finite retention/lifecycles, and read repair depends on read paths/versions and misses unread partitions. Scoped anti-entropy repair still requires a DBA-validated strategy.

### Exercise 9 — DC1 at 100%, DC2 unrepaired

A keyspace has NTS RF3 in dc1 and RF3 in dc2. The ledger records success only in dc1.

**Question:** Can the whole keyspace be marked repaired?

**Answer:** Not if coverage policy requires data in both DCs. Understand tool semantics and DC scope, and record results per replica group without copying dc1 timestamps onto dc2.

### Exercise 10 — Hot partition and repair deadline

A tenant table uses only `tenant_id` as partition key; one large tenant creates an extremely hot partition that slows repair past Dmax.

**Question:** Is a `SCHEDULE_SOON` flag enough to solve this?

**Answer:** No. The scheduler only sets priority. Measure partition size, token skew, and disk pressure, and consider redesigning bucketing/sharding around queries. If deadlines cannot be met, ESCALATE capacity/data modeling rather than retrying endlessly.

### Exercise 11 — Using short TTL to skip repair?

A sessions table uses a 1-hour TTL; the team proposes `gc_grace_seconds=0` and zero repairs because "everything expires anyway."

**Answer:** Insufficient justification. TTL expiration, offline replicas, late writes, compaction strategies, and tombstone purges interact subtly. Review specific immutable/TTL/TWCS cases against version semantics and correctness requirements; never apply a blanket rule.

### Exercise 12 — Overlap on node A

R1 and R2 are distinct token ranges, yet both read SSTables on node A. The scheduler allows up to two cluster-wide jobs, so it runs them concurrently.

**Question:** Why can overload still occur?

**Answer:** Both jobs contend for disk/CPU/network on the same node A. Enforce a resource conflict graph / per-node concurrency rather than just a cluster-wide job cap.

### Exercise 13 — Disconnected right after job completion

The runner disconnects; afterward the operator reports repair completed, yet the ledger remains RUNNING.

**Question:** Should we immediately rerun the same scope?

**Answer:** No. Reconcile against operator evidence/`runId` and real cluster state, updating `last_verified_success` if valid. Avoid double execution caused by reconnects and concurrency races.

### Exercise 14 — Repair and backup at the same hour

Baseline p99 is 140 ms; repair alone 200 ms; backup alone 190 ms; both together hit 480 ms against a 250 ms SLO.

**Question:** What is the right action?

**Answer:** Obey the stop gate, halt new dispatches, and throttle/reschedule maintenance via runbook, then re-measure. If coverage nears grace, escalate and adjust capacity rather than silently skipping schedules.

### Exercise 15 — Full vs. incremental repair

A team runs incremental repair on one Cassandra version, then wants to switch to weekly full repair without evaluating repaired SSTable metadata.

**Question:** Is this acceptable?

**Answer:** Not automatically. Review version-specific semantics, duration/capacity, active session states, full/incremental scope, and migration steps to avoid coverage gaps or broken bookkeeping.

### Exercise 16 — Does CronJob `Forbid` replace a distributed lease?

A Kubernetes CronJob sets `concurrencyPolicy=Forbid`, while another repair operator also runs on the cluster.

**Question:** Does that prevent overlapping repairs?

**Answer:** No. `Forbid` governs only jobs spawned by that single CronJob; system-wide shared leases/fencing or operator coordination are needed to detect external jobs.

### Exercise 17 — Repair finished, yet zombie data already exists

A deleted row reappeared. The team fixes the repair schedule and runs a successful repair.

**Question:** Does that guarantee removing the zombie row?

**Answer:** No. Once the tombstone is gone, repair may actually converge replicas onto the old row. You need the business source of truth, audit/deletion ledger, reconciliation, and incident remediation. Fixing the schedule only prevents future occurrences.

### Exercise 18 — Should we prioritize the largest-byte job?

The queue holds large range R1 with 7 days of grace left, and small range R2 with only 12 hours left before latest safe start.

**Question:** Which job should run?

**Answer:** R2 has the more urgent deadline if health and leases permit. Prioritize by **risk/`timeUntilLatestStart`** first, then factor in resources and fair scheduling to avoid starvation. R1 still requires planning sufficient duration.

### Exercise 19 — A job runs longer than the Cron interval

Cron runs daily at 02:00, repairing scope A takes 36 hours, no global lock exists, and the planner spawns a new job each day.

**Question:** What is the risk?

**Answer:** Overlapping validation/streaming, higher disk/network/p99 pressure, and conflicting ledger state. Enforce scoped leases, active session reconciliation, and scheduling based on actual duration, never launching a new job while the old one is still active.

### Exercise 20 — Hours since last success ignoring topology

Range R7 was repaired 1 day ago; today node C is replaced by D. The scheduler sees coverage age = 1 day and marks NORMAL.

**Question:** What is wrong?

**Answer:** Ownership changed and the scope has not been re-verified. Mark `STALE_TOPOLOGY`, update the owner set, follow the node replacement/bootstrap runbook, and verify fresh coverage.

### Exercise 21 — Partial repair while dashboard stays silent

Monday's job FAILED 3 ranges; Tuesday's cron reran only the already-succeeded ranges. The dashboard reads "weekly run success."

**Question:** Where should the scheduling algorithm be fixed?

**Answer:** The ledger must persist **failed/uncovered scopes** and prioritize them; the verifier must compare planned vs. actual scopes rather than trusting cron success. Add deadline alerts/owners and tests for partial coverage.

### Exercise 22 — High tombstone volume, long GC grace remaining

Read p99 rises due to tombstones, and the team wants to cut grace from 10 days to 1 day.

**Answer:** Diagnose the data model, TTL/delete rate, tombstone scans, compaction strategy, repair/outage SLA, and disk first. Lowering grace creates zombie risk; change it only after safety evaluation and change approval. Bucketing, TTL, or retention redesign may be needed instead of "purging tombstones faster."

## 22. Repair automation implementation checklist

### 22.1. Data and coverage policy

- [ ] Complete catalog of tables/keyspaces, RF/DC, compaction, TTL, and actual `gc_grace_seconds`.
- [ ] Classified delete-heavy, TTL-heavy, hot-partition, and strict-correctness tables.
- [ ] Scope defined by **table/token range/replica/DC** and mode/version.
- [ ] Owner assigned to every repair policy with review rights when grace/schema changes.
- [ ] `last_verified_success_at` derived from actual verified coverage, never cron start.
- [ ] Coverage invalidated when topology, ownership, or RF changes.
- [ ] Per-DC / multi-DC coverage rules enforced; never mark green from a single DC.
- [ ] Time budget `I + Dmax + F + O + B` calculated with real buffer.
- [ ] Failed/partial/skipped ranges recorded with timestamps and states.
- [ ] Never use short TTL or compaction as proof repair can be skipped.

### 22.2. Scheduler and operational safety

- [ ] Cron only triggers the planner; the planner inspects every scope and deadline.
- [ ] Shared lease/fencing prevents duplicate runners.
- [ ] Health gates check node status, quorum, schema agreement, and topology.
- [ ] Capacity gates check free disk/await, GC, compaction, network, and app p99.
- [ ] Per-node and per-DC concurrency limits enforced, not just a global job limit.
- [ ] No unapproved overlap with bootstrap, restore, upgrade, or heavy backup.
- [ ] Bounded backoff/retry budget and deadline-aware escalation in place.
- [ ] Never auto-reissue repair after runner disconnect without checking existing sessions.
- [ ] Never force-kill repair/`nodetool` or edit system tables to release locks.
- [ ] PAUSE/STOP/ESCALATE runbooks and owner approvals established.
- [ ] Version-specific full/incremental/subrange options verified.
- [ ] Never rely on a single lock TTL as a cluster-wide exactly-once guarantee.

### 22.3. Evidence, observability, and incidents

- [ ] Persist `planId`, `runId`, mode/version, topology generation, and UTC timestamps.
- [ ] Verifier compares planned vs. actual scopes, not just process exit codes.
- [ ] Alerts configured for near-grace, failed ranges, missed cron, stale topology, and long outages.
- [ ] Track validation/streaming, compaction, disk/network/GC, and client p99/errors.
- [ ] Post-repair recovery window and evidence confirming backlogs return within thresholds.
- [ ] Integration tests cover partial repair, planner crash, failed retries, and topology changes.
- [ ] Multi-node staging tests verify CL/RF, not only RF1 Testcontainers.
- [ ] Off-fault-domain backups and restore drills in place; repair never replaces backups.
- [ ] Runbook ready for replicas DOWN past grace and suspected zombie reconciliation.
- [ ] Log only permitted operation IDs and metadata; never leak secrets or tenant payloads.
- [ ] Reports distinguish COMPLETED, PARTIAL, FAILED, UNKNOWN, STALE, and AT_RISK.
- [ ] Do not claim academic QA or guaranteed data safety solely from job status.

## 23. Summary

**Repair scheduling in Apache Cassandra is a coverage and safety-deadline problem**, not merely a cron expression. **gc_grace_seconds** defines the table's tombstone protection window; if a replica misses a DELETE and repair fails to cover that scope before tombstones become eligible for purging, old data risks resurrecting. TTL, compaction, and hinted handoff cannot substitute for understanding replica and repair coverage.

A resilient automation design requires **per-table cataloging → scoping by token range/replica/DC → a ledger with last verified success → buffered grace budgets → deadline-prioritized scheduling → capacity/quorum gates → execution via approved tooling → per-scope verification → retry/escalation on partial/unknown outcomes**.

With the Java Driver, applications can read schema/metadata and monitor errors/load, while actual repair execution must flow through **authorized operators/`nodetool` and runbooks**. Measure p99, read/write throughput, disk/network/GC/compaction alongside repair status so you never trade availability for a "green" job. Once a scope passes grace or zombies may occur, **repair alone cannot restore business truth**: you need a source of truth, evidence, and a controlled reconciliation plan.

**The final completion criterion is not "the job ran," but "the right data and replica scopes were reconciled within the safety budget with evidence, while the Java/Cassandra system continued meeting operational requirements."**
