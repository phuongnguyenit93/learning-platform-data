# Incident Response, Change Logging, and Post-Maintenance Verification in MongoDB

## 1. Context and Objectives

A MongoDB system can run cleanly before maintenance yet fail after a driver upgrade, TLS configuration change, rolling restart, or new index build. Those failures do not always appear immediately: a replica set may have a healthy primary while a secondary falls behind on the oplog, an API may pass `ping` while a critical query runs ten times slower, or a Java application may fail only when its pool opens a new connection.

Consequently, MongoDB operations do not end at **"the command succeeded"**. Three linked disciplines are required:

1. **Incident response:** detect impact, investigate, mitigate damage, recover service, and perform root-cause analysis.
2. **Change management:** track who changed what, why, and when, alongside a rollback plan and approval evidence.
3. **Post-maintenance verification:** confirm topology, data, performance, security, and application functionality still meet agreed targets.

This lesson belongs to the **Database Engine Document MongoDB** module, **Operations and Upgrades** chapter, covering **Incident Response, Change Logging, and Post-Maintenance Verification**.

### 1.1. Learning Outcomes

After this lesson, you will be able to:

- Distinguish incident, alert, problem, change, and maintenance window.
- Assign severity based on user impact, data safety, and RPO/RTO.
- Establish roles for Incident Commander, MongoDB Operator, App Owner, Security, and Scribe.
- Capture MongoDB and driver evidence before intervening.
- Build an investigation timeline separating observations, hypotheses, and conclusions.
- Design change requests with preconditions, checkpoints, blast radius, and rollback plans.
- Apply safe rolling maintenance workflows for replica sets.
- Recognize distinct risks across Atlas-managed and self-managed clusters.
- Verify version/FCV, replication, oplog, sharding, indexes, client connectivity, and transactions post-maintenance.
- Define go/no-go gates and a post-change observation window.
- Record structured change logs with full evidence references while never leaking secrets.
- Write runbooks, smoke tests, exercises, and execution checklists.

**Core principle:** Never declare maintenance successful merely because the MongoDB process started. Success means the service actually serves accurate data with proper permissions within SLOs, backed by traceable verification evidence.

## 2. Terms to Keep Distinct

| Term | Meaning | Example |
|---|---|---|
| Alert | Signal that a monitoring threshold was breached | Secondary lag exceeds 30 seconds |
| Incident | Event actively or potentially degrading service | 30% of writes time out |
| Problem | Underlying cause behind one or more incidents | Recurring index/query regression |
| Change | Controlled action modifying the system | Upgrading MongoDB binaries |
| Maintenance window | Approved time slot for performing changes | 01:00–03:00 UTC |
| Release | Application code or configuration version | App v3.8.1 |
| Runbook | Step-by-step execution and exception guide | Rolling restart of a replica set |
| Rollback | Returning to a supported safe prior state | Reverting app to previous release |
| Forward fix | Applying a subsequent fix to reach desired state | Fixing a missing CA config |
| Postmortem / RCA | Post-incident analysis and preventive actions | Why didn't smoke tests catch it? |

### 2.1. Maintenance Does Not Exempt Incident Response

Planned maintenance can still become an incident if write availability drops unexpectedly, data is lost, or SLOs breach. Switch immediately to incident mode, log a timeline, and require severity-appropriate approvals.

### 2.2. Changes Do Not Always Break Immediately

For instance, dropping an index may cause zero API errors during low traffic. Twenty minutes later, when a batch report runs, disk I/O and p99 spike sharply. Change history must be detailed enough to correlate both events.

## 3. End-to-End Operational Model

~~~text
        Proposed Change                 Monitoring Alert
               |                              |
               v                              v
        Risk & Approval                 Impact Triage
               |                              |
               v                              v
      Preflight & Baseline             Incident Response
               |                              |
               +-----------+------------------+
                           |
                           v
                 Controlled Action
                           |
                           v
                 Verification Gates
                           |
              +------------+------------+
              |                         |
              v                         v
          PASS / CLOSE              FAIL / MITIGATE
              |                         |
              v                         v
       Change Log + Evidence       Rollback / Forward Fix
              |                         |
              +------------+------------+
                           |
                           v
                  Review / RCA / Actions
~~~

Not every change needs the ceremony of a major version upgrade. Still, even small actions require knowing **what can break** and **how to verify**.

## 4. Setting Recovery Targets Before Incidents Happen

### 4.1. Common Targets

- **SLI:** service level indicator, e.g., ratio of successful order read requests.
- **SLO:** target for an SLI, e.g., 99.9% of requests succeed within 200 ms.
- **RPO:** maximum acceptable data loss measured in time, e.g., 5 minutes max.
- **RTO:** maximum acceptable time to restore service, e.g., 1 hour.
- **MTTD:** mean time to detect a fault.
- **MTTA:** mean time to acknowledge an alert.
- **MTTR:** mean time to recover as defined by the organization.

**RPO and RTO are not numbers MongoDB promises automatically.** They are system requirements met through topology, backups, runbooks, operational readiness, and drills.

### 4.2. Example Targets by System

| Workload | Example RPO | Example RTO | What Must Be Verified |
|---|---:|---:|---|
| Ordering | 5 minutes | 60 minutes | Majority writes, PIT restore, reconciliation |
| Content API | 30 minutes | 2 hours | Read availability, backups, caching |
| Regenerable reports | 24 hours | 24 hours | Batch jobs and source data |
| Lab environment | Rebuildable | As needed | Re-provisioning automation |

These numbers are illustrative; real policies belong to business owners.

## 5. Classifying Incident Severity by Impact

| Severity | Typical Signals | Response |
|---|---|---|
| SEV-1 / Critical | Widespread write outage, data loss risk, lost cluster majority, data corruption | Page immediately, assign IC, focus on recovery |
| SEV-2 / High | Critical service degraded, sharp p99 spike, secondary staleness hurting users | App on-call + DBA, time-boxed mitigation |
| SEV-3 / Medium | Low-traffic workload slow, disk capacity at risk in a few days | Tracked ticket with assigned owner |
| SEV-4 / Low | Preventive warning, no SLO impact yet | Monitor and schedule remediation |

### 5.1. Base Severity on Impact

A few-second primary election may have zero user impact if driver retries succeed. Conversely, a TLS misconfiguration can break 100% of new connections even while CPU sits near idle.

### 5.2. Escalate Immediately on Data-Safety Signals

Look beyond HTTP 5xx: missing writes, undecryptable backups, unintended data edits, or unauthorized privilege changes demand immediate escalation under security/data incident policies.

## 6. Who Does What During a MongoDB Incident?

| Role | Responsibility |
|---|---|
| Incident Commander (IC) | Sets priorities and scope, approves plans, coordinates responders |
| MongoDB/Platform Operator | Inspects topology, storage, replication, configs; runs approved actions |
| Application Owner | Assesses user impact, driver/connection pools, app rollbacks |
| Security | Joins for auth, TLS, credential, or data-exposure events |
| Communications | Updates stakeholders and users per policy |
| Scribe | Records timeline, hypotheses, evidence, decisions, and outcomes |
| Change Owner | Ensures changes follow preflight, gates, and rollback plans |

People may wear multiple hats in minor incidents, yet you must never skip defining **who holds decision authority**.

### 6.1. Incident Bridge and Single Source of Truth

Record every major decision in one incident log with UTC timestamps. Prevent multiple teams from simultaneously altering configs, scaling, or restarting nodes blindly.

### 6.2. Break-Glass Access

Privileged roles such as `root`, Atlas Project Owner, KMS Decrypt, or production restore permissions must be used solely through audited emergency procedures with MFA/JIT/approval and revoked post-incident.

## 7. Eight-Step Incident Response Workflow

### Step 1 — Detect

Signal sources:

- API SLOs and error-budget burn.
- Atlas Alerts / Monitoring.
- `mongod` / `mongos` logs.
- Java driver command failures and pool checkout timeouts.
- Replica set elections and replication lag.
- Backup/PIT freshness.
- User reports.

### Step 2 — Acknowledge

On-call acknowledges, confirms ownership, and opens an incident matching impact. Never leave critical alerts as unread emails without acknowledgment or escalation.

### Step 3 — Assess Impact

Record:

- When did it start?
- Which endpoints, services, tenants, or regions are affected?
- How many requests/transactions are failing?
- Reads, writes, or both?
- Any data loss or corruption?
- Must we halt deploys, freeze writes, or shift traffic?

### Step 4 — Preserve Evidence

Capture metrics, logs, traces, config versions, topology, query plans, and change history **before restarting** whenever safe and feasible. Do not let evidence collection delay urgent mitigation needed to protect data.

### Step 5 — Hypothesize

Maintain an ordered list of hypotheses and tests rather than executing every runbook blindly at once.

### Step 6 — Mitigate

Reduce impact: pause batch jobs, roll back a release, throttle concurrency, scale, or isolate a failing node per runbook. Avoid actions that risk losing data or quorum.

### Step 7 — Verify Recovery

Confirm SLOs, error rates, correctness, primary/secondary health, lag, and traffic return to normal over a minimum observation window.

### Step 8 — Review

Write a postmortem and update runbooks, alert thresholds, tests, rollback procedures, and ownership.

## 8. Investigating with Falsifiable Hypotheses

Example incident: API latency spikes after a deployment.

| Hypothesis | Prediction If True | Verification |
|---|---|---|
| New query shape misses an index | `docsExamined` spikes; plan changed | `explain` and Query Profiler |
| Pool lacks connections | Pool wait rises; DB command time looks normal | Driver metrics |
| Replication lag | Secondary lag and majority commits slow down | `rs.status()`, lag metrics |
| Slow disk I/O | Read/write latency and `iowait` spike | OS/Atlas metrics |
| TLS/secret rotation failed | New connection/auth errors spike | Driver/TLS logs and change history |

A strong conclusion clearly separates **observed facts**, **hypotheses**, **test evidence**, and **remaining uncertainty**. Temporal correlation with a deployment alone does not prove causation.

### 8.1. Avoid "Intuition-Driven Fixes"

Do not blindly enlarge connection pools on timeouts before locating the bottleneck; larger pools can overload the server further. Do not add an index simply because `explain` shows `COLLSCAN` on a tiny collection. Do not lower `writeConcern` to hide majority latency without understanding durability trade-offs.

## 9. Incident Timeline in UTC

Example:

~~~text
2026-11-14T10:02:00Z  orders-api v3.2 deployed to 10%
2026-11-14T10:04:10Z  API p95 rises from 85ms to 600ms
2026-11-14T10:05:30Z  docsExamined/returned increases 100x
2026-11-14T10:06:00Z  SEV-2 alert fires
2026-11-14T10:07:15Z  On-call ACKs and opens incident
2026-11-14T10:10:20Z  Explain reveals suboptimal query plan
2026-11-14T10:12:00Z  Canary release rolled back
2026-11-14T10:15:00Z  API p95 and error rate return to baseline
2026-11-14T10:35:00Z  Post-incident monitoring starts
~~~

Clocks and timezones must stay consistent. You may display Vietnam local time for operators, while storing canonical UTC timestamps or explicit offsets.

### 9.1. Record More Than Commands

Change/incident logs should capture **why an action was chosen** and its observed outcome:

~~~text
Decision: rollback canary v3.2
Reason: confirmed query plan regression; rollback is low-risk
Approved by: IC + App Owner
Observed outcome: p95 dropped; no write errors observed
~~~

## 10. Low-Impact MongoDB Evidence Gathering

The commands below are read-only/diagnostic examples. They still require appropriate privileges and carry some overhead; avoid hammering an overloaded cluster with them.

### 10.1. Basic Connectivity Check

~~~javascript
db.adminCommand({ ping: 1 });
~~~

A successful `ping` **does not prove** business reads/writes or majority writes are healthy.

### 10.2. Check Version and Build

~~~javascript
db.version();

db.adminCommand({ buildInfo: 1 });
~~~

Record version/build per member/process during rolling maintenance; connecting through a load balancer or `mongos` does not prove the entire deployment matches one version.

### 10.3. Check Node Role

~~~javascript
db.hello();
~~~

On `mongod`, output includes `isWritablePrimary`, `secondary`, `setName`, and `hosts`. On `mongos`, responses include router indicators such as `msg: "isdbgrid"`. Exact fields depend on topology and version.

### 10.4. Server Statistics

~~~javascript
const s = db.adminCommand({ serverStatus: 1 });

printjson({
  host: s.host,
  uptime: s.uptime,
  connections: s.connections,
  opcounters: s.opcounters,
  network: s.network
});
~~~

Convert cumulative counters into rates and account for resets after restarts; never compare raw totals across nodes with different uptimes.

### 10.5. Replica Status

~~~javascript
rs.status();
rs.printSecondaryReplicationInfo();
rs.printReplicationInfo();
~~~

These helpers apply in replica set contexts and require monitoring privileges. They do not replace continuous time-series monitoring.

## 11. Carefully Inspecting Replication Health

Key questions to check:

- Is the primary healthy?
- Are all expected members in their intended states?
- Is secondary lag shrinking after maintenance?
- Are secondary optimes advancing?
- Does the oplog window cover downtime?
- Any heartbeat failures or unscheduled elections?
- Have majority reads and writes recovered?

~~~text
PRIMARY
   |
   +--> SECONDARY A: lag 0.8s
   |
   +--> SECONDARY B: lag 48s
~~~

A cluster cannot be called "fully healthy" merely because one secondary caught up quickly; Secondary B's lag must be explained.

### 11.1. Oplog Window vs. Maintenance Duration

If the oplog window is ~8 hours while a secondary stays offline for 12 hours, the secondary risks falling off the oplog and requiring an initial sync—a severe RTO impact. Shorten maintenance or adjust sizing/backup plans beforehand.

### 11.2. Do Not Apply One Generic Lag Threshold to Every Workload

A secondary serving user reads has tighter freshness requirements than a reporting secondary. Base severity on user impact, not a single arbitrary second count.

## 12. Query Troubleshooting with `explain`

Example in a lab database:

~~~javascript
db.orders.find({
  tenantId: "tenant-A",
  status: "OPEN"
}).sort({ createdAt: -1 })
  .explain("executionStats");
~~~

Inspect:

- Winning plan and `IXSCAN` / `COLLSCAN`.
- `totalDocsExamined`.
- `totalKeysExamined`.
- `nReturned`.
- `executionTimeMillis`.
- Whether a blocking sort occurs.
- Index name and key bounds.

### 12.1. An `IXSCAN` Query Can Still Be Slow

Scanning one million index entries just to return 10 documents is inefficient even though the planner used an index.

### 12.2. `COLLSCAN` Is Not Always a Bug

On a collection with a handful of documents, a collection scan can be optimal. Evaluate plans against representative production dataset sizes.

### 12.3. `explain` Does Not Replace Production p99

One `explain` on one connection does not capture concurrency, cache misses, driver pool waits, or shifting workloads.

## 13. Current Operations and Profiler

### 13.1. Inspecting Running Operations

~~~javascript
db.getSiblingDB("admin").aggregate([
  {
    $currentOp: {
      allUsers: true,
      localOps: true
    }
  },
  {
    $match: {
      active: true,
      secs_running: { $gte: 5 }
    }
  },
  {
    $project: {
      opid: 1,
      ns: 1,
      desc: 1,
      secs_running: 1,
      waitingForLock: 1
    }
  },
  { $limit: 20 }
]);
~~~

`$currentOp` must be the first stage in the pipeline; viewing all users' operations may require the `inprog` privilege. Output is a point-in-time snapshot of active operations.

### 13.2. Database Profiler

The profiler on `mongod` supports three levels:

| Level | Meaning |
|---|---|
| 0 | Profiler disabled |
| 1 | Logs slow operations matching threshold/filter |
| 2 | Logs all operations |

Never leave level 2 enabled permanently in production: it adds performance overhead and risks recording sensitive query values.

In a **self-managed lab**, when permitted:

~~~javascript
use operations_lab

db.getProfilingStatus();

db.setProfilingLevel(1, {
  slowms: 200,
  sampleRate: 0.1
});
~~~

Record previous settings, check version-specific docs, and restore after the investigation window:

~~~javascript
db.setProfilingLevel(0);
~~~

Note that `slowms`/`sampleRate` can affect diagnostic slow logging process-wide; `setProfilingLevel(0)` does not automatically restore every prior threshold value.

### 13.3. Never Log Queries Containing PII

In incident tickets, share query shapes, plan summaries, durations, and trace IDs—never paste full predicates holding emails, tokens, or customer records.

## 14. Separating Application, Driver, and MongoDB Server Faults

Sources of latency:

~~~text
API request
   |
   v
Application queue
   |
   v
MongoClient connection checkout
   |
   v
Server selection / TLS / network
   |
   v
MongoDB command execution
   |
   v
Response deserialize / business logic
~~~

If MongoDB command durations stay normal while API p99 climbs, check pool checkout, DNS, TLS, network, retries, and downstream dependencies before modifying MongoDB indexes.

### 14.1. Java Driver Errors to Classify

- Connection checkout timeout.
- Server selection timeout.
- Socket/network timeout.
- TLS certificate/hostname failure.
- `AuthenticationFailed` (code 18).
- Authorization failure (authenticated, yet missing roles).
- `NotPrimary` / server topology change.
- `WriteConcern` error.
- Transaction retry / `TransientTransactionError` labels.
- Application-level validation / duplicate key errors.

These errors **do not share one generic fix**. For example, `AuthenticationFailed` does not immediately mean "reset the password"—it may indicate the wrong `authSource` or secret version.

## 15. Checking Sharded Cluster Health

In a sharded deployment, verify:

- All shards and the config server replica set.
- All `mongos` endpoints.
- Balancer/chunk migration states if relevant.
- Read/write distribution per shard.
- Unexpected scatter-gather queries.
- Index consistency across shards.
- End-to-end application latency and errors across shards.
- Backup/restore plans preserving global consistency.

### 15.1. Status Output Can Be Very Long

~~~javascript
sh.status();
~~~

Run via `mongos` in a sharded context with appropriate privileges; never treat output from one router as full verification of every underlying member.

### 15.2. Hot Shards vs. Averages

~~~text
Shard A: CPU 95%, p99 1.6s
Shard B: CPU 25%, p99 70ms
Cluster average CPU: 60%
~~~

Evaluate metrics per shard. Never rush to change a shard key or reshard mid-incident without diagnosing the exact cause of skew.

## 16. Storage and WiredTiger Diagnostics

Key signals:

- Free disk bytes and time-to-full.
- Disk read/write latency and IOPS.
- Memory pressure and swap usage.
- WiredTiger cache, eviction, and dirty bytes.
- Checkpoint and journal stalls.
- Host hardware/OS error logs.
- Concurrent index builds or backups driving I/O.

Version-dependent example fields:

~~~javascript
const s = db.adminCommand({ serverStatus: 1 });
const cache = s.wiredTiger && s.wiredTiger.cache;

if (cache) {
  printjson({
    bytesInCache: cache["bytes currently in the cache"],
    maxBytes: cache["maximum bytes configured"],
    dirtyBytes: cache["tracked dirty bytes in the cache"]
  });
}
~~~

High cache utilization alone does not prove insufficient RAM; cross-check eviction rates, disk latency, and user-facing SLOs.

### 16.1. What Not to Do

Never delete WiredTiger data files or journal files directly to "free space". Never reboot multiple members together due to high disk I/O without verifying majority and quorum.

## 17. Planned Maintenance vs. Emergency Changes

| Change Class | Characteristics | Controls |
|---|---|---|
| Standard / pre-approved | Repetitive, low-risk, proven runbook and tests | Short change record + evidence |
| Normal | Version upgrades, index changes, TLS rotation, scaling | Risk review, approval, preflight, rollback |
| Emergency | Fixing active security/availability incidents | Incident commander approval, logged decision, post-review |

An emergency change never means skipping documentation or post-review. Approvals can accelerate, yet risk, outcomes, and accountability must still be recorded.

### 17.1. Multiple Change Units in One Maintenance Window

Upgrading MongoDB and bumping the Java Driver simultaneously makes fault isolation harder if errors appear. Separate changes into small units with verification checkpoints whenever possible.

## 18. Fields Every Change Request (CR) Needs

| Field | Example |
|---|---|
| Change ID | `CHG-2026-0142` |
| Title | Rolling MongoDB patch upgrade |
| Owner / executor | Platform team |
| Business owner | Orders service |
| Environment / topology | Production, 3-node replica set |
| Objective | Patch security bug |
| Scope | `mongod` binaries, member by member |
| Before state | Version/build, FCV, config hash |
| Desired after state | Supported target version |
| Impact / risk | Election, brief connection interruption |
| RPO / RTO / SLO | Per service policy |
| Prerequisites | Backups, healthy majority, oplog headroom |
| Approval | DBA + service owner |
| Window | UTC start/end |
| Steps | Versioned runbook |
| Validation gates | Replication, app smoke tests, SLOs |
| Rollback / forward fix | Version-supported recovery path |
| Communications | Pre / during / post |
| Evidence links | Metrics, logs, execution record |

### 18.1. Scope and Blast Radius

One index on one collection can impact writes and storage. One CA rotation can break all application clients. One shard topology edit can impact multiple tenants.

Document the **smallest unit that can be paused or rolled back** plus every downstream dependency to check.

## 19. YAML Change Record Template

This is an **illustrative governance schema**, not a MongoDB configuration file.

~~~yaml
changeId: CHG-2026-0142
title: Rolling MongoDB patch upgrade
environment: production
deployment: orders-rs0
changeType: normal
risk: medium
owner: platform-oncall
approvers:
  - database-lead
  - orders-service-owner
window:
  startUtc: 2026-11-15T01:00:00Z
  endUtc: 2026-11-15T03:00:00Z
before:
  mongodbVersion: recorded-per-member
  featureCompatibilityVersion: recorded
  topology: 1-primary-2-secondaries
  backupStatus: verified
planned:
  stepsRef: runbook-mongodb-rolling-upgrade-v3
  rollbackRef: runbook-mongodb-recovery-v2
gates:
  - majority-healthy
  - secondary-caught-up
  - service-smoke-pass
  - error-budget-within-policy
results:
  status: pending
  evidenceRef: null
~~~

Actual version and FCV values must be recorded straight from the live deployment—never pre-fill "verified" before measuring.

### 19.1. Never Store Secrets in Change Logs

Never place MongoDB URIs containing passwords, PEM private keys, KMS key material, or plaintext database backups inside change records.

### 19.2. Historical Traceability

Link each change ID to:

- Deployment/release pipeline runs.
- Source commits and infrastructure plans.
- Related incident IDs if any.
- Baseline metrics.
- Approvals.
- Postflight reports.
- Rollback decisions.
- Postmortems.

## 20. Preflight Before Any Impactful Maintenance

Preflight is a **go/no-go gate**, not rubber-stamp paperwork.

1. Confirm scope, owner, approvals, and runbook version.
2. Confirm maintenance window and stakeholder notifications.
3. Check SLOs, active alerts, and open incidents.
4. Check topology and majority quorum.
5. Check replication lag, oplog window, and member health.
6. Verify backups, snapshots, and PIT restore windows.
7. Verify disk, memory, and CPU headroom.
8. Check active index builds and migrations.
9. Identify active transactions and batch jobs.
10. Verify binary, driver, FCV, and app compatibility.
11. Confirm secrets, TLS certificates, and KMS keys stay valid throughout maintenance.
12. Confirm rollback plan and authorized decision-makers.
13. Capture pre-change baseline for comparison.
14. Configure alert routing and status communications.

### 20.1. Abort If a Secondary Is Already Unhealthy

If a 3-member replica set already has one unavailable secondary, restarting the primary or second secondary loses majority. Do not begin rolling maintenance until topology satisfies runbook preconditions.

### 20.2. Backups Only Count If Restorable

"Last backup succeeded" does not guarantee integrity or restore readiness. High-risk changes require a valid recovery point, accessible decryption keys, and a tested restore workflow.

### 20.3. Oplog Window Must Be Sufficient

If a secondary stays offline longer than the oplog window, it may require an initial sync—posing a major RTO risk.

## 21. Pre-Maintenance Baseline: What to Measure?

Capture a baseline with UTC timestamps and environment metadata:

| Signal | Pre-Change (Example) | Post-Change Acceptance |
|---|---|---|
| API read p95 | 70 ms | Within SLO |
| API error rate | 0.05% | Within error budget |
| DB command p95 | 20 ms | No regression beyond approved budget |
| Primary status | Healthy | Exactly one `PRIMARY` per topology |
| Max secondary lag | 1.5 s | Returns to baseline within recovery window |
| Free disk | 300 GB | No unexpected drop |
| Available connections | Ample headroom | No rejected-connection spikes |
| Backup point | Recently verified | Recovery point remains valid |

These numbers are **illustrative**, not default MongoDB SLOs.

### 21.1. Versions and Configurations to Record

Before making changes, archive:

- MongoDB binary versions per member.
- `featureCompatibilityVersion` (FCV), where supported and authorized.
- Driver versions and application release tags.
- Config revisions/hashes.
- TLS certificate expiry dates and CA trust stores.
- Relevant feature flags and cluster parameters.
- Critical index specifications.
- Shard/replica topology.

### 21.2. Pick a Representative Baseline Window

Five quiet minutes at 02:00 before maintenance do not represent 09:00 peak traffic. Compare against matching historical time-of-day windows and expected post-change load.

## 22. Recording Pre-Change Evidence via `mongosh`

### 22.1. Ping / Hello / Build

~~~javascript
printjson(db.adminCommand({ ping: 1 }));

printjson(db.hello());

printjson(db.adminCommand({ buildInfo: 1 }));
~~~

Never paste full sensitive outputs into public tickets; retain only required fields.

### 22.2. Feature Compatibility Version

Where supported by version and permissions:

~~~javascript
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});
~~~

FCV does not automatically change with binary versions. Changing FCV carries compatibility and rollback consequences; never run `setFeatureCompatibilityVersion` casually outside an official upgrade procedure.

### 22.3. Replica Set Status

~~~javascript
rs.status();
rs.printSecondaryReplicationInfo();
rs.printReplicationInfo();
~~~

Capture a per-member health summary rather than just the top lines of output.

### 22.4. Resource Statistics

~~~javascript
const s = db.adminCommand({ serverStatus: 1 });

printjson({
  host: s.host,
  uptimeSeconds: s.uptime,
  connections: s.connections,
  opcounters: s.opcounters,
  network: s.network
});
~~~

Cumulative counters reset on process restarts; postflight checks must compare **rates** and normalized metrics, never raw cumulative totals.

## 23. Safe Rolling Maintenance on a Replica Set

Example topology:

~~~text
       PRIMARY A
          |
     +----+----+
     |         |
SECONDARY B  SECONDARY C
~~~

For tasks permitting rolling restarts, standard principles are:

1. Verify all three members are healthy and backups are ready.
2. Select one secondary.
3. Maintain/restart **one member**.
4. Wait for the member to return to healthy `SECONDARY` and catch up.
5. Check replication lag, logs, and resource usage.
6. Advance to the next secondary only after gates pass.
7. Once secondaries are done, plan primary switchover/stepdown.
8. Verify election, majority, and application connections.
9. Maintain the former primary and wait for it to return as `SECONDARY`.
10. Verify system-wide topology, data, and SLOs.

This is a **workflow model**, not a substitute for runbooks tailored to your exact MongoDB version, OS, `clusterAuth`, and drivers.

### 23.1. Why Not Restart Simultaneously?

Replica sets need majority to sustain a primary and write availability. Restarting multiple voters together drops quorum and causes an outage.

### 23.2. Primary Stepdown Creates Client-Visible Transitions

A brief window without a primary may occur, and in-flight operations can fail or require retries. Application drivers must use topology discovery and proper retry settings; never promise absolute zero interruption.

### 23.3. Never Ignore Election Events

Log election timestamps, the new primary, driver errors, and recovery times. If repeated elections occur, halt rollout and investigate.

### 23.4. Arbiters Store No Data

Replica sets with arbiters must still track voting counts and failover capacity; arbiters never replace secondary data copies or backups.

## 24. MongoDB Version Upgrades: Binary vs. FCV

During a MongoDB upgrade, distinguish:

- **Binary version:** running `mongod`/`mongos` executable version.
- **Feature Compatibility Version (FCV):** controls release-gated features and formats.
- **Driver compatibility:** whether Java/Node/Python apps support the target server.
- **Application schema/index compatibility:** whether query shapes, aggregations, and index behaviors change.

### 24.1. Follow Version-Specific Upgrade Ordering

MongoDB requires exact upgrade sequences—often stepping major version by major version, verifying FCV upfront, rolling binaries per topology, and only then elevating FCV once preconditions hold.

**Never** embed a hardcoded command like `setFeatureCompatibilityVersion("x.y")` into a generic runbook without reading the official *source version → target version* guide.

### 24.2. FCV Impacts Rollbacks

Once a new FCV is enabled, certain features or on-disk formats make reverting to the old binary complex or unsupported. Confirm downgrade support, restore plans, and rollback cutoffs before raising FCV.

### 24.3. Version Skew During Rolling Upgrades

Temporarily running mixed binary versions across members is normal within supported upgrade guides. Do not treat temporary mixed versions as an error if allowed by the guide, yet enforce a bounded transition window and gate to reach uniform state.

### 24.4. Separate MongoDB and Driver Upgrades When Possible

Changing servers, drivers, auth mechanisms, TLS certificates, and query indexes in one change multiplies failure hypotheses if an incident hits. Split them into separate changes with checkpoints wherever policy allows.

## 25. Atlas-Managed Maintenance Differs from Self-Managed

With MongoDB Atlas, the platform manages much of patching, upgrades, failovers, and infrastructure. Application operators still need to:

- Read maintenance and upgrade notifications.
- Configure appropriate maintenance windows where supported.
- Check cluster tier and version constraints.
- Prepare driver retry and transaction handling.
- Measure before/after SLOs.
- Review project activity and event logs.
- Verify backups and PIT recovery.
- Verify API and worker functionality post-change.

### 25.1. Do Not Run Self-Managed Steps on Atlas

Never assume direct permissions to restart `mongod` or alter OS services on Atlas-managed clusters. Use the Atlas UI/CLI/API, supported workflows, and MongoDB Support as needed.

### 25.2. Incidents During Atlas Maintenance

Correlate timelines using Atlas Events, Metrics, and Alerts, and engage Support when needed, while still maintaining internal incident records and assessing user impact.

### 25.3. Atlas Alerts Do Not Replace Postflight Checks

A green cluster status badge in the UI does not prove a payment workflow using majority writes works or that a Java app trusts the current CA.

## 26. Self-Managed Maintenance: Dependencies to Check

Beyond `mongod` version and topology, check:

- OS packages and service managers.
- Disk filesystems and volume health.
- DNS and network firewalls.
- TLS CAs, certificate validity, and `clusterAuth`.
- Shared keyfiles or internal X.509 certificates.
- KMS/KMIP if using encryption at rest.
- Monitoring agents and exporters.
- Backup/restore tool versions.
- System limits and file descriptors.
- Clock synchronization.
- Host resource limits and cgroups.
- Persistent volumes and mount paths.

### 26.1. Avoid Rotating Multiple Secret Types Simultaneously Unnecessarily

Certificate rotation and keyfile rotation have distinct sequences. Combining binary upgrades with CA/internal-auth rotations makes handshake failures hard to isolate.

### 26.2. Protect Configs and Secrets

Change logs can store redacted config hashes/diffs, yet must never contain private keys, passwords, or KMS key material in public or broad-access artifacts.

## 27. Verification Gates: Criteria Between Steps

A **gate** is a mandatory check before advancing to the next step.

| Gate | Objective | If Failed |
|---|---|---|
| G0 Preflight | Health, backups, approvals | Defer change |
| G1 Single member | Node returns healthy, lag stabilizes | Halt rollout |
| G2 Majority | Primary/quorum stable, app writes recover | Incident / rollback |
| G3 Feature/FCV | Version and FCV valid | Do not enable new features |
| G4 Data | Counts, invariants, transactions healthy | Block broad traffic |
| G5 Security | Auth, TLS, roles working | Mitigate and investigate |
| G6 Application | Smoke tests and API SLOs pass | Rollback / forward fix |
| G7 Observation | No sustained regression | Keep monitoring; do not close change |

### 27.1. No-Go Is a Valid Outcome

If secondary lag fails to return to baseline or new pool connections keep failing, stop. Never push through a maintenance window at all costs.

### 27.2. Who Signs Off?

Platform/DBA signs off on nodes and topology; application owner signs off on smoke tests and SLOs; security signs off on auth/TLS if modified; change owner archives evidence and closes the change.

## 28. Postflight Layer 1: Cluster Topology

For a replica set:

~~~javascript
rs.status();
db.hello();
rs.printSecondaryReplicationInfo();
rs.printReplicationInfo();
~~~

Verify:

- Exact expected member count.
- Exactly one `PRIMARY` in a healthy view where topology requires.
- All intended secondaries are `SECONDARY` and caught up within thresholds.
- No member unexpectedly stuck in `RECOVERING` or `STARTUP2`.
- No lost votes or majority.
- No sustained heartbeat errors.
- Election count and timeline match executed actions.
- Adequate oplog window remains.
- No unexpected initial syncs.

### 28.1. Do Not Check Only Immediately After Restart

A secondary can enter `SECONDARY` before lag fully drains. Observe over a sustained window to catch lag creeping back up under normal traffic.

### 28.2. One Command Does Not Replace Per-Member Checks

Querying one router or primary does not verify every node's health. Monitoring must capture per-member metrics.

## 29. Postflight Layer 2: Versions and Configuration

- MongoDB binary/build version per member.
- FCV at the approved stage.
- Driver versions and application release.
- Storage engine and required settings.
- Authentication and authorization remain enabled.
- TLS chain and hostname validation pass.
- Backup and exporter agents remain running.
- Required index definitions remain intact.
- Config diff matches the approved change.
- No out-of-scope config drift.

### 29.1. Binary Upgraded Yet FCV Unchanged?

This can be an **intentional state** prior to the final gate. Never raise FCV impulsively merely because it differs from the binary version; follow the version's upgrade plan and rollback boundaries.

### 29.2. Do Not Rely on a Single `buildInfo`

During rolling upgrades, nodes temporarily run different versions. Record versions per node rather than running `db.version()` on one random connection.

## 30. Postflight Layer 3: Data and Correctness

A cluster can look healthy topologically while data is wrong after a migration, restore, or index/schema change.

Verify per business requirements:

1. Expected databases and collections exist.
2. Document counts/volumes show no unexpected drops.
3. Sample documents have valid keys and schemas.
4. Referential and business invariants hold.
5. Required indexes are ready.
6. Collations and unique constraints hold.
7. Transactions, `readConcern`, and `writeConcern` behave as designed.
8. Change stream resume behavior works if used.
9. TTL indexes and background jobs are not deleting unintended data.
10. Multi-tenant ACLs remain accurate.

### 30.1. Counts and Samples Alone Do Not Prove Data Integrity

Spot-checking `countDocuments()` or total counts misses subtle logical corruption. Run domain-appropriate consistency and invariant checks, especially after restores or data migrations.

### 30.2. Never Run Heavy Scans Mid-Incident

Running full collection scans across every document during an incident can worsen a struggling cluster. Use bounded samples, asynchronous checks, or an isolated restore target when appropriate.

### 30.3. Deleted Data Can Reappear After a Restore

When restoring an older backup, account for business updates and deletions that occurred after the recovery point and run a reconciliation plan before reopening traffic.

## 31. Postflight Layer 4: Application and Driver

A low-impact smoke test should verify:

- Creating a **new `MongoClient` / new TLS connection** succeeds.
- Authenticating with the right principal and `authSource`.
- Reading a valid document in a test namespace/tenant.
- Writing a test document/transaction via an approved mechanism.
- Reading it back and verifying invariants.
- Cleaning up test data safely if policy permits.
- Critical business queries using expected indexes.
- Change streams, workers, and ETL pipelines resuming.
- Zero connection checkout or server selection errors.
- p95/p99 latency and 5xx rates back at baseline.

### 31.1. Ping Is Only One Step

~~~javascript
db.adminCommand({ ping: 1 });
~~~

A successful `ping` does not prove app roles, query indexes, transactions, majority writes, or TLS trust across all clients.

### 31.2. Read-Only Smoke Test with `mongosh`

~~~javascript
const appDb = db.getSiblingDB("operations_lab");

printjson(appDb.orders.findOne(
  { _id: "smoke-reference" },
  { _id: 1, status: 1, updatedAt: 1 }
));
~~~

If the reference document does not exist, the probe lacks a valid fixture; prepare dedicated test fixtures beforehand. Never query arbitrary customer records in production as a probe.

### 31.3. Write Tests Must Be Idempotent

A smoke write can use a dedicated ID with a TTL or cleanup policy, yet must never leak synthetic data into business reports, billing, or change streams. Use a separate test namespace with clear rules.

## 32. Postflight Layer 5: Performance, Resources, and SLOs

Compare against pre-change baseline:

| Metric | Practice |
|---|---|
| API p95/p99 | Compare by endpoint and time-of-day window |
| Error rate | Compare against SLO / error budget |
| DB command duration | Check percentiles and query shapes |
| Docs/keys examined | Detect query plan regressions |
| Connections | Current, available, rejected if exposed |
| Disk | Free space, latency, IOPS |
| WiredTiger | Cache, eviction, checkpoints |
| Replication | Lag, oplog, flow control |
| Host | CPU, memory, network |
| Backups | Freshness and active agents |

### 32.1. Counters Reset on Restart

`opcounters`, `network.bytesIn`, and `connections.totalCreated` reset when a node restarts. Never subtract pre-restart totals from post-restart totals and claim traffic dropped by millions of operations.

### 32.2. Off-Peak SLOs Do Not Reflect Peak Load

Maintenance at 02:00 often finishes during quiet traffic. Keep an **observation window** open—sometimes through the first peak window per policy—before declaring zero regressions.

### 32.3. Compare Query Shapes Instead of Raw Query Values

Use query shapes from the Atlas Query Profiler/slow logs and sampled `explain` outputs. Never create metric labels containing emails or user IDs—that explodes cardinality and leaks PII.

## 33. Postflight Layer 6: Safety and Security

Verify:

- SCRAM/X.509/OIDC authentication still works.
- Users and roles did not change out of scope.
- TLS CA, SANs, and expiry pass on **new connections**.
- Internal member authentication has zero errors.
- KMS / encryption-at-rest holds required decrypt permissions.
- Audit logging and monitoring still emit events.
- Newly rotated API keys/secrets were picked up by consumers.
- Network ACLs and private endpoints remain accurate.
- Backup keys remain accessible for restoring historical backups.
- No unusual spike in authentication failures.
- Incident artifacts contain zero passwords or PEM keys.

### 33.1. Certificate Rotation Requires Testing Fresh Connections

Pooled TLS sessions opened prior to rotation may stay alive. Testing only an existing pool does not prove clients trust the newly presented certificate.

### 33.2. Never Disable TLS Verification

Never enable `tlsInsecure`, `tlsAllowInvalidHostnames`, or bypass hostname verification as a lasting workaround for cert mismatches. Fix the CA, truststore, or SANs and redeploy per runbook.

## 34. Postflight Layer 7: Backups and Recoverability

Especially critical after upgrades, storage migrations, backup agent updates, or KMS rotations.

Questions:

- Do scheduled backup jobs still run?
- Are new snapshots/PIT points appearing within policy?
- Did retention shrink unexpectedly?
- Are restore targets and permissions still valid?
- Are old KMS keys preserved for historical backups?
- Is the post-maintenance oplog window sufficient?
- Did the latest restore drill pass?
- Are encryption and backup agents error-free?

**Never mark backups verified merely because a file or snapshot object exists.** Run scheduled restore tests and confirm decryption works.

## 35. Criteria to Declare Maintenance Successful

Example decision summary:

~~~text
[PASS] Topology reached desired state
[PASS] Binary/config/FCV match plan
[PASS] Secondary lag returned within threshold
[PASS] Critical queries perform normally
[PASS] New driver/TLS connections succeed
[PASS] Zero auth/authorization regressions
[PASS] SLOs and error rates stable
[PASS] Disk/cache/queues show no unexpected degradation
[PASS] Backups/monitoring continue operating
[PASS] Evidence and change log complete
~~~

Transition the change status to **COMPLETED** only once all gates pass or have explicitly approved exceptions. Mark any unchecked gate `PENDING` rather than guessing `PASS`.

### 35.1. Ending Maintenance Differs from Closing the Change Record

Maintenance work may wrap up at 03:00, yet the change record stays open for 30–60 minutes or through peak monitoring per policy. Keep status at `MONITORING` until evidence is complete.

### 35.2. Partial Completion

If one secondary has not yet upgraded while the cluster serves cleanly, record the partial state and remaining plan—never report "all nodes upgraded".

## 36. Rollback vs. Forward-Fix Decisions

| Condition | Typical Preferred Option |
|---|---|
| New app release clearly caused regression | Roll back app |
| New config/cert fails while old remains safe | Restore prior config/cert per runbook |
| Binaries just upgraded, FCV unchanged | Check version-specific downgrade support |
| FCV raised and new features used | Forward fix or restore; do not force downgrade |
| Committed data migration cannot reverse cleanly | Forward fix or restore/reconcile |
| Old secret compromised | Never roll back to the compromised secret |
| Replica set lost majority | Restore quorum first via emergency runbook |

### 36.1. Rollbacks Must Be Tested Beforehand

"We have backups" is not a complete rollback plan. Know your RTO, data replay/reconciliation steps, endpoint updates, and restore privileges.

### 36.2. Do Not Auto-Roll Back When Incompatible

MongoDB major upgrades impose binary/FCV and feature-usage downgrade limits. Always consult **official documentation for your exact source/target version pair**.

### 36.3. Stop-the-Line Conditions

Halt rollout immediately if:

- Majority is lost or primary stays unavailable.
- Signs of data corruption or missing writes appear.
- Authentication/TLS failures spread widely.
- A secondary falls behind as the oplog window shrinks dangerously.
- Latency or error budgets clearly breach.
- Backup/recovery safety is compromised.
- Out-of-scope changes or unidentified operator actions appear.

## 37. Execution Log

An execution log captures **intent, actor, and outcome**—not merely a raw terminal transcript.

Example:

| UTC | Actor | Action | Expected | Observed | Gate |
|---|---|---|---|---|---|
| 01:00 | DBA | Preflight | 3 members healthy | PASS | G0 |
| 01:10 | DBA | Restart secondary B | B returns `SECONDARY` | PASS after 4 min | G1 |
| 01:20 | DBA | Restart secondary C | C returns `SECONDARY` | PASS | G1 |
| 01:35 | DBA | Planned stepdown | New `PRIMARY` | PASS, minor retries | G2 |
| 01:50 | App | Read/write smoke | Succeeds | PASS | G6 |
| 02:15 | Platform | SLO comparison | Within baseline | PASS | G7 |

These entries are illustrative, not a mandatory timeline for any specific deployment.

### 37.1. Link to External Evidence

If metrics or console logs live in separate systems, add access-controlled links/references. Never paste full diagnostic dumps containing PII.

### 37.2. Separate Actor and Approver

Separate executor and approver on high-risk changes. Automation pipelines should run under dedicated service identities with signed run metadata.

## 38. Post-Maintenance Report Template

~~~markdown
# Maintenance Report — CHG-2026-0142

- Deployment: orders-rs0 / production
- Scope: rolling MongoDB patch upgrade
- Planned window: 01:00–03:00 UTC
- Actual window: 01:08–02:20 UTC
- Owner: Platform
- Approval: CHG-2026-0142

## Before
- Members healthy: 3/3
- Primary: one expected
- Backup: verified
- Application SLO: within target
- MongoDB/FCV versions: recorded in evidence

## Actions
- Secondary B and C upgraded individually
- Planned primary stepdown
- Previous primary upgraded
- Indexes and configuration checked

## After
- Healthy members: 3/3
- Secondary lag: within baseline
- Primary stable: yes
- New TLS/MongoClient connection: pass
- App read/write smoke test: pass
- SLO/error rate: pass
- Backup agent: operational

## Deviations
- None / or list with incident ID

## Decision
- Status: MONITORING / COMPLETED
- Evidence: internal controlled links
- Approved by: DB lead + service owner
~~~

This is a report template, not tool output. Every `pass` in a real report must be backed by evidence.

## 39. Recording Risks and Exceptions

Not every system passes 100% of gates inside the maintenance window. If accepting an exception, document:

- Which gate failed?
- Reason and impact scope.
- Residual risk level.
- Risk acceptor.
- Remediation deadline.
- Additional monitoring rules.
- Escalation plan if metrics worsen.

Example:

~~~text
Exception:
Secondary C lag at 12s (baseline 2s),
steadily decreasing and serving zero user reads.
Owner: DBA
Review in: 30 minutes
Escalate if lag grows or oplog headroom shrinks.
~~~

Never convert an exception into a fake "PASS" just to close a change ticket conveniently.

## 40. Change History and Decision Provenance

A strong audit trail links:

~~~text
Change Request
     |
     +--> Approval
     +--> Runbook version
     +--> Source diff / IaC plan
     +--> Preflight evidence
     +--> Execution timeline
     +--> Postflight verification
     +--> Incident reference (if any)
     +--> Follow-up actions
~~~

### 40.1. Infrastructure as Code and Config Drift

With Terraform, Ansible, or Kubernetes Operators, version control is only half the picture. Inspect **actual live state** post-deploy and check for drift against defined config.

### 40.2. Never Store Secrets in Diffs

Config diffs must redact SCRAM passwords, TLS private keys, KMS key material, API tokens, and MongoDB URIs with credentials.

### 40.3. Rollout Automation Must Be Idempotent

If a pipeline retries a step, it must never re-execute destructive or non-idempotent actions—such as deleting data, altering FCV, or stepping down a primary—without checking current state first.

## 41. When Does Maintenance Become an Incident?

Example:

~~~text
01:00  Planned rolling restart begins
01:15  First secondary maintenance succeeds
01:25  Next node maintenance starts
01:26  App error rate spikes to 20%
01:27  Majority writes impacted
~~~

At 01:26:

1. **Halt the rollout.**
2. **Open an incident** and set severity by impact.
3. **Record the timeline** and assign owners.
4. **Mitigate impact** per runbook and approvals.
5. **Do not** push forward just to "finish on schedule".
6. After recovery, decide between rollback and forward fix.
7. Link the incident ID into the change record.

A maintenance window never authorizes ignoring availability gates.

## 42. Case Study A — Query Regression After Schema/Index Change

### Symptoms

- API p95 jumps from 80 ms to 800 ms.
- `docsExamined / nReturned` spikes sharply.
- Primary and quorum remain healthy.
- Incident began after a new query release.

### Investigation

~~~javascript
db.orders.find({
  tenantId: "tenant-A",
  status: "OPEN"
}).sort({ createdAt: -1 })
  .explain("executionStats");
~~~

Inspect query shape, index definitions, plan summary, and deployment diff.

### Mitigation

Roll back the query/release if evidence warrants, or apply a reviewed index change if rollback is unavailable. Check write amplification and disk headroom before building production indexes.

### Postmortem

Add representative dataset performance tests and require query-plan reviews in change checklists for critical endpoints.

## 43. Case Study B — Prolonged Replica Set Election After Maintenance

### Symptoms

- App server selection timeouts spike.
- Primary stays unavailable longer than expected.
- One secondary is unhealthy.
- Recently restarted node shows heartbeat errors.

### Investigation

~~~javascript
rs.status();
db.hello();
~~~

Cross-check host logs, networking, TLS, quorum, member states, FCV/binary compatibility, and planned stepdown timeline.

### Mitigation

Halt rollout and prioritize recovering the failed member/quorum per runbook; never restart the last healthy node.

### Postmortem

Add an explicit secondary-caught-up gate and member TLS verification before primary transitions.

## 44. Case Study C — TLS Certificate Rotated, Yet Java App Fails

### Symptoms

- Existing pooled connections stay alive.
- New client/TLS handshakes fail.
- Logs report certificate chain/SAN mismatches.

### Hypothesis

The new server certificate was signed by a CA absent from the Java truststore, or its SAN omits the target hostname.

### Verification

- Inspect the new certificate's issuer, SANs, and validity with PKI tools.
- Check Java truststore/`SSLContext` configuration.
- Open a **fresh connection** in canary with full TLS verification.
- Inspect TLS handshake errors and auth outcomes.

### Mitigation

Restore trust/certs per approved runbook; never enable `tlsInsecure`. During CA rollovers, use a trust-overlap stage where appropriate.

### Postmortem

Add a fresh-connection smoke test and maintain an inventory of all clients.

## 45. Case Study D — Disk Pressure After an Index Build

### Symptoms

- Free disk drops fast.
- Disk latency and p99 climb.
- An index build just started.
- Secondary replication lag increases.

### Investigation

- Disk growth rate and time-to-full.
- `currentOp` / index build status.
- WiredTiger cache and eviction pressure.
- Host storage limits.
- Write throughput and replication.
- Change timeline.

### Mitigation

Halt further rollouts, throttle batch loads, expand storage, or manage the index build per runbook. Never delete data or journal files directly.

### Postmortem

Add capacity forecasting and index-build resource estimates to preflight checklists.

## 46. Case Study E — Restore Completed, Yet Business Data Is Wrong

### Symptoms

- Restore job reports completed.
- Cluster has a primary and APIs connect.
- Some orders are missing line items, or payment reconciliation fails.

### Lesson

Process/cluster health does not prove business correctness. Recovery requires:

- Exact RPO timestamp.
- All expected collections and indexes.
- Cross-collection invariant tests.
- Replaying valid post-recovery-point writes if needed.
- Checking deletions against privacy/retention policies.
- Full verification before reopening wide traffic.

Never close an incident based solely on `ping` and total document counts.

## 47. Java Sync Driver: Smoke Test and Instrumentation Examples

### 47.1. Ping and Read-Only Smoke Test

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public class MongoPostMaintenanceSmoke {
    public static boolean run(MongoClient client) {
        MongoDatabase admin = client.getDatabase("admin");
        Document ping = admin.runCommand(new Document("ping", 1));

        Number ok = (Number) ping.get("ok");
        if (ok == null || ok.doubleValue() != 1.0) {
            return false;
        }

        MongoCollection<Document> collection =
            client.getDatabase("operations_lab")
                  .getCollection("smokeReference");

        Document item = collection.find(
            new Document("_id", "known-readonly-fixture")
        ).first();

        return item != null && "ACTIVE".equals(item.getString("status"));
    }
}
~~~

Succeeds only if the test fixture was pre-seeded and the app principal holds read permissions. Never use random production customer records as smoke fixtures.

### 47.2. Test with a Fresh `MongoClient`

A `MongoClient` running since before maintenance may hold pre-existing pooled connections. Instantiate a fresh client with official credentials/TLS to verify fresh handshakes, server selection, and authentication.

### 47.3. Listening for Command Failures

~~~java
import com.mongodb.event.CommandFailedEvent;
import com.mongodb.event.CommandListener;
import com.mongodb.event.CommandStartedEvent;
import com.mongodb.event.CommandSucceededEvent;

import java.util.concurrent.TimeUnit;

class SafeMongoListener implements CommandListener {
    @Override
    public void commandStarted(CommandStartedEvent event) {
        // Do not log event.getCommand(): may contain PII.
        System.out.println("Started " + event.getCommandName());
    }

    @Override
    public void commandSucceeded(CommandSucceededEvent event) {
        System.out.println(
            event.getCommandName() + " succeeded in " +
            event.getElapsedTime(TimeUnit.MILLISECONDS) + "ms"
        );
    }

    @Override
    public void commandFailed(CommandFailedEvent event) {
        System.out.println(
            event.getCommandName() + " failed in " +
            event.getElapsedTime(TimeUnit.MILLISECONDS) + "ms"
        );
    }
}
~~~

In production, export metrics and traces with cardinality/sampling controls rather than printing raw commands, URIs, or exception payloads that may leak secrets.

### 47.4. Read-Only Smoke Does Not Replace Write/Transaction Tests

If the system uses transactions and majority write concern, run a **controlled business test case** in an authorized environment/namespace. Never write synthetic records into live production payment collections automatically.

## 48. Rehearsal: Lab Sample Data

Examples for a **MongoDB lab** only:

~~~javascript
use operations_lab

db.orders.insertMany([
  {
    _id: "lab-001",
    tenantId: "tenant-A",
    status: "OPEN",
    amount: 100,
    createdAt: ISODate("2026-11-01T08:00:00Z")
  },
  {
    _id: "lab-002",
    tenantId: "tenant-A",
    status: "CLOSED",
    amount: 200,
    createdAt: ISODate("2026-11-02T08:00:00Z")
  },
  {
    _id: "lab-003",
    tenantId: "tenant-B",
    status: "OPEN",
    amount: 300,
    createdAt: ISODate("2026-11-03T08:00:00Z")
  }
]);

db.smokeReference.insertOne({
  _id: "known-readonly-fixture",
  status: "ACTIVE",
  updatedAt: new Date()
});
~~~

Fixed IDs mean re-running `insertMany` on the same collection will throw a duplicate key error. Use a fresh collection or idempotent upserts in automated lab runs.

### 48.1. Query Before and After Indexing

~~~javascript
db.orders.find({
  tenantId: "tenant-A",
  status: "OPEN"
}).sort({
  createdAt: -1
}).explain("executionStats");
~~~

Create the index **in the lab**:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "idx_tenant_status_created" }
);
~~~

Run `explain` again. With only three documents, the planner may still choose a collection scan; never judge production index effectiveness from a tiny 3-document lab.

## 49. Preflight Checklist Template for Rolling Maintenance

- [ ] Change ID, owner, approvals, and window ready.
- [ ] Runbook matches exact MongoDB version and topology.
- [ ] Application SLOs and baseline recorded.
- [ ] Backup/PIT restore point verified.
- [ ] Replica set has healthy majority and healthy members.
- [ ] Secondary lag and oplog window have sufficient headroom.
- [ ] Disk, CPU, and cache are not abnormally saturated.
- [ ] No open P1/P2 incidents.
- [ ] Driver version and retry behavior compatible.
- [ ] TLS, KMS, and cluster auth dependencies valid.
- [ ] Monitoring, exporters, and alerts active.
- [ ] Stop-the-line conditions defined.
- [ ] Version-accurate rollback plan ready.
- [ ] Approvers and operators confirmed on communication channels.

## 50. Postflight and Change Closure Checklist

### Topology and Versions

- [ ] MongoDB binary version per member matches plan.
- [ ] FCV matches the approved stage.
- [ ] Expected `PRIMARY` and voting member counts match topology.
- [ ] Secondaries caught up with stable lag.
- [ ] Oplog window meets requirements.
- [ ] No prolonged heartbeat or election errors.
- [ ] Sharded members, config servers, and `mongos` healthy.

### Data and Application

- [ ] Expected namespaces and indexes intact.
- [ ] Test fixture readable.
- [ ] Controlled write/transaction smoke test passes.
- [ ] Critical business invariants pass.
- [ ] Driver opens fresh TLS connection and authenticates cleanly.
- [ ] Change streams, jobs, and ETL pipelines recovered.
- [ ] Multi-tenant ACLs and roles unchanged unexpectedly.

### Performance and Security

- [ ] API p95/p99 and error rates within SLOs.
- [ ] No severe DB query shape regressions.
- [ ] Connection pools and driver retries normal.
- [ ] CPU, cache, disk, and queues normal.
- [ ] Backups, PIT, and monitoring active.
- [ ] TLS, secret, and KMS policies valid.
- [ ] Zero unresolved critical alerts.
- [ ] Observation window finished or exception assigned an owner.

### Change Record

- [ ] Actual UTC start/end timestamps recorded.
- [ ] Actions, outcomes, and actors fully logged.
- [ ] Preflight/postflight evidence archived with proper access control.
- [ ] Deviations and incidents linked to the change.
- [ ] Rollback/forward-fix decision recorded.
- [ ] Closure approval granted.
- [ ] Follow-up actions assigned owners and deadlines.

## 51. Hands-On Exercises and Scenarios

Run impactful commands only in **labs or approved environments**. Never run restarts, stepdowns, restores, or FCV changes in production purely as exercises.

### Exercise 1 — Distinguishing Concepts

Distinguish alert, incident, problem, change, maintenance, and RCA. Is a secondary lag alert always a P1 incident?

### Exercise 2 — Impact and Severity

An API experiences 20% write timeouts for 15 minutes. Identify what information must be collected before assigning severity.

### Exercise 3 — SLO / RPO / RTO

If RPO is 5 minutes, RTO is 1 hour, and the latest backup is 24 hours old, does the system satisfy policy?

### Exercise 4 — Incident Roles

Assign Incident Commander, DBA, app owner, and scribe during a primary-loss incident.

### Exercise 5 — Timeline

Write a UTC timeline covering deployment, alert firing, ACK, mitigation, and recovery verification.

### Exercise 6 — Facts vs. Hypotheses

Is "p99 rose after deploy" a fact or a root cause? What evidence is needed to conclude the release caused a query regression?

### Exercise 7 — MongoDB Diagnostics

Run `db.hello()`, `db.version()`, and `serverStatus` in a lab. Which distinct question does each answer?

### Exercise 8 — Counter Resets

Why can't you subtract pre-restart `opcounters` totals from post-restart totals to derive throughput?

### Exercise 9 — Replication Health

One secondary lags by 45 seconds while the primary is healthy. Is it safe to proceed to the next rolling upgrade step? What must be checked?

### Exercise 10 — Oplog Window

A secondary must stay offline for 12 hours while the oplog window is only 6 hours. What are the risks and preparation options?

### Exercise 11 — Query Explain

Why doesn't seeing `IXSCAN` automatically prove a query is optimized? Name three fields to inspect in `executionStats`.

### Exercise 12 — CurrentOp

Use `$currentOp` to find operations running over 5 seconds. Why shouldn't `killOp` be the default reflex?

### Exercise 13 — Atlas vs. Self-Managed

Which parts of maintenance does Atlas manage, and what must the application team still verify independently?

### Exercise 14 — FCV

Distinguish binary version from FCV. Why can changing FCV affect rollback and downgrade options?

### Exercise 15 — Majority Quorum

A 3-voter replica set already has one secondary down. Should you restart another member immediately to upgrade it?

### Exercise 16 — Rolling Maintenance

Diagram the workflow of maintaining secondaries first and the primary last, listing gates between every member.

### Exercise 17 — Change Request

Write the minimum fields for a rolling patch upgrade ticket, including rollback, impact, and evidence.

### Exercise 18 — Preflight Backups

Why is "backup job succeeded" insufficient proof of recoverability?

### Exercise 19 — Maintenance Becoming an Incident

During a patch upgrade, write errors jump 30%. What are the first steps and who holds decision authority?

### Exercise 20 — Postflight Topology

List conditions confirming a replica set is healthy after a planned election.

### Exercise 21 — Postflight Data

Why don't `ping` and matching document counts guarantee business consistency?

### Exercise 22 — Fresh TLS Connections

Existing app pools keep working yet new clients fail to connect. Which layers must be checked?

### Exercise 23 — Driver Retries

When MongoDB is overloaded, why can unbounded retries trigger a cascading failure?

### Exercise 24 — Sharded Cluster

Why must you compare per-shard metrics and verify `mongos`/config servers after maintenance?

### Exercise 25 — SLO Verification

Maintenance at 02:00 finishes under very low traffic. Should you close the change immediately or hold an observation window through peak traffic?

### Exercise 26 — Rollback

A new app release fails and can roll back, yet MongoDB FCV was just raised and new features were used. Can you downgrade arbitrarily?

### Exercise 27 — Secrets

Why must MongoDB URIs and private keys never appear in change records?

### Exercise 28 — Authorization

After an upgrade, the app authenticates cleanly yet writes are rejected. Distinguish authentication from authorization.

### Exercise 29 — Unexpected Disk Growth

After an index build, disk usage climbs quickly and lag rises. Draft a safe investigation and mitigation plan.

### Exercise 30 — Restore Correctness

A restore job completes yet orders are missing line items. Which business invariants must be checked?

### Exercise 31 — Postmortem

Draft an RCA containing trigger, contributing factors, impact, detection, mitigation, recovery, and action items with owners.

### Exercise 32 — Change Gate Decision

Topology gate passes and app smoke tests pass, yet the backup agent fails and one secondary's lag is climbing. Can the change be closed as `COMPLETED`? Explain.

### Exercise 33 — Execution Log

Write a four-row execution log with timestamp, actor, action, expected, observed, and gate.

### Exercise 34 — Comprehensive Rehearsal

Design a MongoDB upgrade runbook for an ordering system featuring:

- Three-member replica set.
- Java API and workers.
- SCRAM/TLS.
- Majority writes.
- Backups/PIT.
- p95 SLOs.
- Change request and approvals.
- Per-member gates.
- Fresh-client smoke test.
- Rollback/forward fix and incident escalation.
- Postflight report.

## 52. Summary

Safe MongoDB operations require more than running the right command:

1. **Incident response:** assess user/data impact, preserve evidence, test falsifiable hypotheses, mitigate safely, verify recovery, and write RCAs.
2. **Change management:** record objectives, scope, before/after versions and configs, approvals, blast radius, runbooks, rollbacks, execution timelines, and evidence.
3. **Checkpoint-driven maintenance:** replica set rolling maintenance preserves majority, waits for each member to recover, manages elections safely, and respects the oplog window.
4. **Version-aware upgrades:** binaries, FCV, drivers, and database features carry compatibility constraints; never downgrade or change FCV impulsively.
5. **Multi-layer verification:** topology, data invariants, roles/TLS, fresh `MongoClient` connections, API SLOs, query plans, backups, and monitoring must all pass or carry explicit approved exceptions.
6. **Close the loop:** after every incident or change, review alert thresholds, smoke tests, runbooks, and follow-up actions with owners and deadlines.

A maintenance cycle is truly **complete** only when evidence proves the system serves accurate data, enforces proper permissions, and meets SLOs after the change—not simply because the MongoDB process restarted.

## Official References

- [MongoDB Manual — Upgrade Self-Managed Deployments](https://www.mongodb.com/docs/manual/release-notes/upgrade/)
- [MongoDB Manual — Feature Compatibility Version](https://www.mongodb.com/docs/manual/reference/command/setFeatureCompatibilityVersion/)
- [MongoDB Manual — Replica Set Maintenance](https://www.mongodb.com/docs/manual/administration/replica-set-maintenance/)
- [MongoDB Manual — rs.status()](https://www.mongodb.com/docs/manual/reference/method/rs.status/)
- [MongoDB Manual — rs.printSecondaryReplicationInfo()](https://www.mongodb.com/docs/manual/reference/method/rs.printSecondaryReplicationInfo/)
- [MongoDB Manual — rs.printReplicationInfo()](https://www.mongodb.com/docs/manual/reference/method/rs.printReplicationInfo/)
- [MongoDB Manual — db.hello()](https://www.mongodb.com/docs/manual/reference/method/db.hello/)
- [MongoDB Manual — serverStatus](https://www.mongodb.com/docs/manual/reference/command/serverStatus/)
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Manual — Database Profiler](https://www.mongodb.com/docs/manual/tutorial/manage-the-database-profiler/)
- [MongoDB Manual — CurrentOp](https://www.mongodb.com/docs/manual/reference/operator/aggregation/currentOp/)
- [MongoDB Manual — Troubleshoot Replication Lag](https://www.mongodb.com/docs/manual/tutorial/troubleshoot-replica-sets/)
- [MongoDB Atlas — Configure Maintenance Windows](https://www.mongodb.com/docs/atlas/tutorial/cluster-maintenance-window/)
- [MongoDB Atlas — Alerts](https://www.mongodb.com/docs/atlas/alerts/)
- [MongoDB Atlas — Backup and Restore](https://www.mongodb.com/docs/atlas/backup-restore-cluster/)
- [MongoDB Java Sync Driver — Monitoring](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/monitoring/)
- [MongoDB Java Sync Driver — Connection Pool Configuration](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/connection-pools/)
