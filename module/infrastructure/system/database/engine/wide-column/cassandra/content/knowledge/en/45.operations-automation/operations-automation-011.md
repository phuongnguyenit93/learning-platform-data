# Alerting, Runbooks, and Administrative Action Audit Logging

> **Chapter:** Operations Automation  
> **Module scope:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — Distributed Apache Cassandra and the wide-column model; partition keys, query-driven table design, replication, read/write consistency, compaction, repair, maintenance, and Java applications.

Suppose at 10:42 UTC, an event-writing Java API starts seeing an increase in `WriteTimeoutException`. The Cassandra dashboard reports high `PendingCompactions`, one node is nearly out of disk space, and terminal history only shows that someone ran `nodetool` a few minutes earlier. The on-call team has three questions they cannot answer immediately:

1. Which alerts actually indicate **user impact** and require paging the on-call engineer, rather than merely reflecting a single degraded metric?
2. Which runbook helps choose **safe diagnostic checks**, scope the failure, and request approval when cluster state changes are needed?
3. Who did what, on which node, with which parameters, for what reason, and with what outcome — including actions taken via SSH, JMX, `nodetool`, CQL, or automation?

An operable Cassandra system needs more than dashboards. It requires a closed loop: **signals → contextualized alerts → runbook → controlled action → evidence → recovery verification → improvement**. This lesson designs that closed loop using mechanisms that can be practiced in a lab cluster, emphasizing the differences between **Cassandra audit logging**, **OS/automation-level administrative action logs**, and **application request tracing**.

**Example scope:** Cassandra 4.1 and 5.0, Java Driver 4.x, JMX/metrics exporters, illustrative Prometheus/Alertmanager rules, `nodetool` CLI, `cqlsh`, and controlled logging systems. Prometheus metric names depend on the exporter; any custom normalized names introduced in this lesson must be mapped before use. No claim is made that these have been deployed or tested on a production cluster.

> **Safety guardrails:** Do not run `repair`, `cleanup`, `rebuild`, `decommission`, `drain`, `truncatehints`, `clearsnapshot`, change RF/CL, stop nodes, or disable TLS in production to "follow along with this lesson." Even read-only commands can generate load/JMX overhead and must be bounded. All scenarios and measurements in this lesson are **synthetic data**; run experiments only on an isolated learning cluster.

## 1. Objectives and Design Principles

After completing this lesson, learners will be able to:

1. Build an alert catalog grounded in **SLIs/SLOs and data risk**, rather than simply setting CPU thresholds.
2. Distinguish Cassandra node/coordinator/table/DC metrics from Java Driver and HTTP/gateway metrics.
3. Propose thresholds and sustained-duration conditions, account for RF/CL dependencies, and handle missing telemetry and alert fatigue.
4. Write alerts that include `owner`, `severity`, `runbook_url`, blast scope, and verification mechanisms.
5. Design a Cassandra runbook following the phases **observe → hypothesize → verify → approve → intervene → verify recovery → handoff**.
6. Distinguish read-only operations, state-changing operations, and destructive/hard-to-reverse `nodetool`/CQL operations.
7. Enable, filter, and inspect **CQL audit logging** in Cassandra 4.x/5.x, understanding both its strengths and limitations.
8. Explain why Cassandra audit logs **do not automatically capture** `nodetool`, `cassandra.yaml` edits, SSH sessions, or Kubernetes/cloud changes.
9. Propose an audit wrapper/automation ledger capturing actor, approval, command fingerprint, before/after state, exit code, and evidence links.
10. Maintain log integrity, retention, and security while avoiding exposure of passwords, query literals, PII, and private keys.
11. Design two-person approval, least privilege, idempotency, and kill switches for conditional remediation.
12. Walk through a tabletop exercise and distinguish immediate mitigation from consistency/data integrity verification.

**Definition of Done for an alert:** the alert has a recipient, context/scope, initial diagnostic checks, escalation conditions, and tested notification/clear behavior. **Definition of Done for an administrative action:** it records who and why, authorization, exact node/command, UTC timestamp, outcome, before/after state, and a tamper-resistant audit record. Never equate "command exited 0" with "incident resolved."

## 2. Three Signal Layers to Connect

### 2.1. Users, Drivers, and Cassandra Do Not Measure the Same Thing

~~~mermaid
flowchart LR
    U["User / API SLI"] --> A["Service + gateway metrics"]
    A --> D["Java Driver metrics and exception types"]
    D --> C["Coordinator CQL metrics"]
    C --> R["Replicas / storage / compaction"]
    R --> H["Host / disk / network / JVM"]
    X["Change + audit ledger"] --> A
    X --> C
    X --> H
    A --> I["Incident timeline and evidence"]
    D --> I
    C --> I
    H --> I
    X --> I
~~~

| Layer | Signals | Inference Traps |
|---|---|---|
| API/gateway | Success rate, p95/p99, requests/s, business transactions | A 504 can occur before a CQL request is ever sent |
| Java Driver | `DriverTimeoutException`, `ReadTimeoutException`, `WriteTimeoutException`, pool in-flight, throttling | Driver timeouts differ from coordinator timeouts; failed writes have uncertain outcomes |
| Coordinator | `ClientRequest.Read/Write.Timeouts`, `Unavailables`, `Latency` | Coordinator errors alone do not prove which replica is the root cause |
| Replica/table | `SSTablesPerReadHistogram`, `TombstoneScannedHistogram`, disk/compaction | Slowness in one table/partition may not slow down every API |
| Host/JVM | disk free, IO await, GC pause, NIC packet loss, heap | High CPU alone does not prove user impact |
| Control plane | deploys, schema/grant changes, nodetool, SSH, TLS certs, config diffs | These events may **not appear in the Cassandra CQL audit log** |

To determine whether an incident started **before or after an operation**, normalize all timestamps to UTC and record clock sources and clock skew. Never treat the time an alert fired as the start of the fault; account for the `for` duration, scrape interval, and ingestion lag.

### 2.2. Metric Types Determine How Alerts Are Configured

| Data Type | Cassandra Examples | How to Read |
|---|---|---|
| Counter | `ClientRequest.Read.Timeouts`, `Storage.Exceptions` | Rate of increase or delta over a window; handle resets on restart |
| Gauge | `Compaction.PendingTasks`, `ThreadPools.PendingTasks` | Current value or trend; do not blindly apply `rate` |
| Histogram | `Table.SSTablesPerReadHistogram`, `TombstoneScannedHistogram` | Distribution and tail; exporter bucket mapping matters |
| Timer/Latency | `ClientRequest.Read.Latency` | Unit and observation window; do not average p99 across nodes |
| Meter | `DroppedMessage.Dropped`, `HintsService.HintsFailed` | Event count or rate; semantics vary by type and exporter |
| State/event | Node Down/Up, schema agreement, audit action | Discrete events; can be lost due to log rotation or network drops |

Cassandra uses Dropwizard Metrics, exposing many metrics over JMX for collection by an exporter. A name such as `org.apache.cassandra.metrics:type=ClientRequest scope=Read name=Timeouts` describes **node-level** data, not a single cluster-wide metric. In Prometheus, the exporter determines metric names, labels, units, and counter `_total` conversions.

### 2.3. Do Not Mistake Missing Telemetry for a "Healthy System"

A dead node can stop emitting metrics at the exact moment real errors surge. You therefore need **meta-monitoring**:

- `up` or exporter scrape health metrics, verifying target counts match inventory.
- Expected vs. observed node/DC map to detect disappearing time series.
- Clock skew, remote-write lag, scrape interval, and data retention.
- Log ingestion lag/saturation, and audit log drops/rotation/retention.
- Synthetic requests/canaries at the appropriate CL to confirm user-side availability.

A graph showing "WriteTimeout rate = 0" while exporters on three nodes are Down **is not evidence** that errors stopped. Never conclude "cluster healthy" from a green dashboard without knowing telemetry coverage and actual data sources.

## 3. Building an Actionable, Impact-Driven Alert Catalog

### 3.1. Severity Tiers by Purpose

| Tier | When | Action |
|---|---|---|
| **SEV1 / page immediately** | Critical API loses availability, proven data corruption, or cluster cannot satisfy required CL | Open incident, coordinate on-call and data owners |
| **SEV2 / page** | Fast error budget burn, one DC impaired with remaining redundancy, or disk will fill before intervention | Triage within committed SLA deadline |
| **Warning / ticket** | Sustained compaction backlog, node flapping, repair/snapshot overdue without breaching SLO | Investigate during business hours |
| **Info / dashboard** | Short-lived noise, scheduled maintenance restart, controlled CPU increase | Preserve context, avoid waking on-call |

Actual severity levels must reflect SLAs/SLOs and business impact. One `DN` node under RF3 may still allow `LOCAL_QUORUM` if two natural replicas remain alive, though a redundancy layer is lost; under RF1, the same `DN` causes request unavailability. Always evaluate token ownership, RF, DC, and CL before escalating severity.

### 3.2. Alert Source and Runbook Catalog

| Category | Primary Signals | First Triage |
|---|---|---|
| API availability | Error rate by endpoint/service, sample count | Gateway, driver, or coordinator? |
| API latency | p95/p99 alongside timeout/error rate | Compare deployments, query classes, and CQL calls/request |
| Cassandra request errors | `ClientRequest.Read/Write.Timeouts,Failures,Unavailables` | CL/RF/DC, replica liveness, server exceptions |
| Membership | Expected node missing/Down across multiple views | Gossip, JVM/host/network, topology changes |
| Disk | Bytes free, positive growth slope, time-to-full | Data/commitlog/hints/snapshot/log directories |
| Commitlog | `PendingTasks`, `WaitingOnCommit` | Fsync/disk latency, offered writes |
| Compaction | `Compaction.PendingTasks` + read p99/disk IO | Table strategy, backlog growth, throughput |
| Thread pool | `ThreadPools.PendingTasks/TotalBlockedTasks` | Bottlenecked stages, request load |
| Dropped messages | `DroppedMessage.Dropped` per type | Request class, packet/network/queues |
| Hints | `HintsService.HintsFailed/TimedOut`, not-stored | Hint holders, target health, max hint window |
| Repair schedule | Last successful complete repair + range coverage | Grace window, owner, preflight health |
| Backup/restore | Last verified restore, actual RPO/RTO, evidence gaps | Manifest, validation gate, and recovery owner |
| Audit logging | Disabled/archiving failure, retention gap | Security owner, node runtime setting |
| Security | Unauthorized logins, unscheduled DDL/DCL | CQL audit + change-control correlation |
| Telemetry | Exporter missing, scrape gaps, clock skew | Expected inventory and log ingestion |

A single metric like `PendingCompactions=20` is insufficient to declare an outage; compare against baseline, growth slope, IO/GC, latency, and offered traffic. Alerts should specify an owner, severity, runbook, and escalation path; never send the same page for unrelated root causes.

### 3.3. Contract of an Actionable Alert

~~~yaml
alert_id: CASS-READ-ERROR-BURN
objective: "events-api read success >= 99.9% over 30 days"
scope: "service + dc + query-class"
signal: "user-facing error rate correlated with Cassandra exception types"
window: "5m fast detection and 1h confirmation (illustrative)"
traffic_floor: "enough requests for a meaningful ratio"
severity: "page on sustained multi-window burn"
owner: "DB-oncall + service-oncall"
runbook_url: "https://runbooks.example.invalid/cassandra/read-errors"
stop_condition: "change only with matching approval and rollback plan"
verify: "success, p99 and required consistency semantics recovered"
data_risk: "unknown write outcomes and read freshness assessed"
~~~

The URL above is a **placeholder**, not an existing runbook. Production alerts must link to a versioned page with an owner, on-call rotation, and a "do not do" section.

### 3.4. SLO Burn Rate and Realistic Thresholds

With a 99.9% success SLO, the error budget is 0.1% of total requests. A 1.44% error rate yields a burn rate of:

\[
\frac{0.0144}{0.001}=14.4.
\]

**Multi-window burn-rate** alerts pair a short window to confirm an ongoing fault with a long window to filter transient noise. Under very low traffic, a handful of errors can spike the percentage sharply; use a traffic floor or dedicated rules for rare critical transactions.

Never rely on successful-request p99 as your sole SLO: the slowest requests may time out and drop out of the success histogram, making p99 appear artificially better while errors climb. Always display traffic, success/error rate, and latency together.

### 3.5. Time-to-Full Disk Alerting

A disk at 85% utilization during heavy compaction/repair/streaming can be riskier than a completely idle disk at 92%, depending on required cluster headroom. Monitor:

~~~text
disk free bytes / total bytes
positive growth slope and estimated time-to-full
data/commitlog/hints/audit/snapshot volumes
ongoing compaction, hints, repair and streaming
available inodes / filesystem mount health
~~~

When snapshots use hardlinks, `du -sh snapshots/` does not necessarily equal the actual space freed upon deletion. Never run `clearsnapshot` or purge commitlogs blindly to "fix" a disk alert. Transition to state-changing actions only via a runbook that evaluates retention, backups, and data loss risk.

## 4. Configuring Alerts with Prometheus/Alertmanager

### 4.1. Normalized Metric Names Are Not Default Mappings

The examples below use **illustrative names normalized by a custom telemetry pipeline**:

~~~text
cassandra_client_read_timeouts_total
cassandra_client_write_timeouts_total
cassandra_node_disk_free_bytes
cassandra_node_disk_total_bytes
cassandra_compaction_pending_tasks
cassandra_audit_logging_enabled
service_http_requests_total
service_http_errors_total
~~~

These **are not necessarily the exact metric names emitted by Cassandra/JMX exporters**. Before deploying, verify JMX exporter mappings, units, counters, `{cluster,dc,node,service}` labels, and confirm the series actually exist. The JMX `AuditLogEnabled` attribute requires an explicit mapping or dedicated collector. "No series" is not the same as "value equals 0."

### 4.2. Illustrative Prometheus Alerts

~~~yaml
groups:
  - name: cassandra-observability-example
    interval: 30s
    rules:
      - alert: CassandraExporterDown
        expr: up{job="cassandra-jmx"} == 0
        for: 2m
        labels:
          severity: warning
          team: database
        annotations:
          summary: "JMX exporter unavailable"
          description: "Check node inventory, export process and host reachability"
          runbook_url: "https://runbooks.example.invalid/cassandra/telemetry"

      - alert: CassandraReadTimeoutsSustained
        expr: |
          sum by (cluster, dc) (
            rate(cassandra_client_read_timeouts_total[5m])
          ) > 0.1
        for: 5m
        labels:
          severity: warning
          team: database
        annotations:
          summary: "Coordinator read timeout rate increased"
          description: "Correlate with API errors and request CL/RF"
          runbook_url: "https://runbooks.example.invalid/cassandra/reads"

      - alert: CassandraDiskHeadroomLow
        expr: |
          (
            cassandra_node_disk_free_bytes
            /
            cassandra_node_disk_total_bytes
          ) < 0.12
        for: 10m
        labels:
          severity: warning
          team: database
        annotations:
          summary: "Disk headroom below illustrative threshold"
          runbook_url: "https://runbooks.example.invalid/cassandra/disk"

      - alert: CassandraAuditLoggingDisabled
        expr: cassandra_audit_logging_enabled == 0
        for: 5m
        labels:
          severity: security
          team: security
        annotations:
          summary: "Audit logging disabled on an expected node"
          runbook_url: "https://runbooks.example.invalid/cassandra/audit"
~~~

Thresholds like `0.1 timeout/s`, `12% disk free`, and `for` durations **are purely for syntax illustration**, not universal cluster policies. `up==0` detects targets **still present in service discovery that fail scrapes**; if a target disappears from discovery altogether, you need an inventory comparison or separate heartbeat. The `enabled==0` audit alert will not fire if the metric is missing completely, so pair it with an exporter/collector meta-alert.

### 4.3. Filtering Errors with Denominators and Traffic Floors

An expression over normalized service metrics:

~~~promql
(
  sum by (service) (rate(service_http_errors_total[5m]))
  /
  clamp_min(
    sum by (service) (rate(service_http_requests_total[5m])),
    0.000001
  )
) > 0.0144
and on (service)
sum by (service) (rate(service_http_requests_total[5m])) > 1
~~~

This covers only **a single 5-minute window** with an illustrative threshold, not a complete multi-window alert. It is valid only when numerator and denominator requests use matching filters/labels, errors are not double-counted, and **timeouts are not omitted**.

### 4.4. Labels, Grouping, Inhibition, and Silences

Choose labels sufficient for action: `cluster, dc, service, alertname, severity, team`. Never put `user_id, partition_key, request_id` into metric labels, as cardinality will explode and privacy may be exposed.

Alertmanager supports grouping by cluster/DC, routing to DB/SRE/Security teams, and alert inhibition. However, **never inhibit all Cassandra alerts merely because an exporter is Down**: absence of telemetry can mask a genuine disk outage. Maintenance silences must record `change_id, actor, scope, UTC start/end, expiry`; never silence indefinitely just to keep dashboards green.

### 4.5. Testing Alerts Like Code

1. Verify metric mappings and units from JMX through the exporter.
2. Use recorded series or unit tests to simulate counter resets, node reboots, missing scrapes, and zero traffic.
3. Verify `for` durations, grouping, and escalation rules across RF1, RF3, and multi-DC topologies.
4. Test Alertmanager routing to the on-call receiver and confirm runbook links do not return 404.
5. Measure false positives and false negatives under baseline and peak traffic.
6. Record the Git commit, diff, approval, deployment timestamp, and rollback path for alert rules.

Test results must capture **an alert firing event, a notification delivery event, an acknowledgement event, and a clear event**. Successfully parsing a rule in Prometheus **does not prove** the on-call engineer will receive actionable context and be able to follow the runbook.

## 5. Cassandra Incident Lifecycle: From Page to Closure

### 5.1. Six Distinct Milestones

~~~text
T_last_good      last bucket/request known healthy
T_first_bad      first bucket/request observed failing
T_alert_fire     alert evaluation + for duration completed
T_ack            human on-call acknowledged
T_mitigated      user impact reduced by a verified mitigation
T_resolved       SLO and correctness and residual risks handled
~~~

**Never label `T_alert_fire` as incident onset.** Scrape/remote-write/aggregation lag and `for: 5m` introduce delay. Record timezone/clock offset per source; if only 5-minute buckets are available, state a window such as "first-known-bad between 10:40–10:45Z" instead of fabricating second-level precision.

### 5.2. Minutes 0–5

- Confirm **user impact**: error/success rate, business operations, reads/writes, CL, RF, DC, and traffic volume.
- Identify potential data-loss classes: unresolved write outcomes, deletes, full disks, total unavailability, or corrupted SSTables.
- Assign incident ID, severity, incident commander, DB owner, and communication channel.
- Capture initial application/Driver/coordinator/host charts **before restarting or changing configuration**, provided doing so does not delay urgent mitigation.
- Check whether the alert reflects a real symptom or missing telemetry.
- If node quorum is lost or disk is critical, escalate per runbook prioritizing data safety.

### 5.3. Minutes 5–15

Build an **impact matrix** instead of concluding "Cassandra is broken":

| Dimension | Affected | Healthy Controls | Unknown |
|---|---|---|---|
| Service/deployment | v28 API events | v27 in same AZ | Versions in other DCs |
| CQL shape | latest-N with pageSize 100 | point read by PK | Full range queries |
| Keyspace/table | `events_by_device_day` | `metadata_by_device` | Other tables |
| Consistency | `LOCAL_QUORUM` write | `LOCAL_ONE` read | Retry/CL overrides |
| DC/rack/node | dc1/N2 | dc2 controls | N2 token/replica overlap |
| Time | first-bad 10:42–10:45Z | 10:35–10:40Z | Clock skew |

Compare changes **effective** prior to first-bad: app/config deploys, CQL schema/role changes, TLS keys, RF/CL, node join/leave, compaction/repair/backups, network/DNS/load bursts, and TTL cohorts. Having no recent deploy **does not mean** workload or data shape remained static.

### 5.4. Minutes 15–30: Falsifiable Hypotheses

Every hypothesis must state predicted observations, a falsifier, and test risk:

~~~text
H1: N2 disk saturation raises coordinator write p99.
Expected: N2 IO await/commitlog stalls increase before errors;
          requests involving N2 more affected.
Falsifier: nodes have healthy IO during same UTC window,
           and only new app deployment shows driver queue pressure.
Low-risk probe: host/JMX metrics, nodetool info/tpstats,
                node/replica routing evidence.
Risk: diagnostic overhead; no repair/restart yet.
~~~

Tag claims as `OBSERVED` / `INFERRED` / `NOT_COLLECTED` with confidence levels. Choose tests that distinguish among multiple hypotheses with minimal impact; avoid executing data-mutating operations "to see if errors stop" without a rollback plan.

### 5.5. Mitigation Decisions and Verification

Evaluate each proposed mitigation against:

1. **Business invariant:** Does it compromise consistency, data retention, or authorization?
2. **Scope:** Which nodes, DCs, tables, clusters, or service versions are affected?
3. **Blast radius:** If the action fails, which replicas lose availability?
4. **Approval:** Who serves as incident commander, DB owner, and second approver?
5. **Before evidence:** Capture a minimal snapshot of metrics, configuration, and data state.
6. **Stop/rollback:** If p99/errors/disk/pending repairs worsen, when do we stop?
7. **After evidence:** Compare identical windows, labels, and traffic levels—not merely whether the alert cleared.

After mitigation, distinguish `MITIGATED` (user impact reduced) from `RESOLVED` (root cause, residual risks, and consistency addressed). Shedding offered traffic from 5,000 to 500 requests/s may lower p99 while leaving the underlying overload unresolved.

### 5.6. Handoff Without Forcing the Next Shift to Restart Investigation

~~~text
Incident / severity / owner / next update UTC:
Last good - first bad UTC with uncertainty:
Affected and healthy cohorts:
Write/read CL and RF/DC:
Errors by gateway / driver / coordinator:
Current best hypotheses and falsifiers:
Evidence IDs / dashboards / log gaps:
Actions already taken (actor, UTC, change ID):
Actions explicitly NOT taken:
Data integrity / UNKNOWN writes / repair state:
Next safe check and stop condition:
~~~

**Never close an incident solely because the pager stopped ringing** if dashboards lack telemetry, deleted data resurrects, write timeouts remain unreconciled, or an interrupted repair lacks an owner.

## 6. Standardizing Executable Runbooks

### 6.1. Minimal Runbook Structure

~~~markdown
# RB-CASS-READ-ERRORS — Version 2

Owner: DB SRE | Reviewed UTC: YYYY-MM-DD
Triggers: alert IDs, thresholds, exceptions
Scope: Cassandra 4.1/5.0, keyspace/table/DC/service
User impact: SLI/SLO and data correctness risk
Required access: read-only JMX/metrics/log access
Preconditions: verified environment/cluster ID and maintenance state

## First 5 minutes
- Confirm business impact, node health, metrics coverage
- Save exact UTC window + request CL and error class

## Read-only checks
- Command/query, rationale, expected output, limits
- Healthy and affected comparison

## Decision tree
- Symptoms -> hypotheses -> falsifiers
- Evidence needed before choosing any action

## Controlled mitigations (not automatic)
- Approval, commands with exact scope, dry-run where supported
- Risk, before snapshot, stop and rollback condition

## Verification and exit
- User SLO at representative traffic
- Correct read/write semantics and data integrity
- Audit record and communication link

## Escalation and handoff
- DB, app, infra, security owners + contact procedures
~~~

A runbook is **not** a bare list of 20 `nodetool` commands. It is a decision document defining permission boundaries, preconditions for command use, and verification criteria.

### 6.2. Classifying Commands by Consequence

| Tier | Examples | Requirements |
|---|---|---|
| **READ / observation** | `nodetool status`, `info`, `tpstats`, `compactionstats`, `netstats`, `tablestats` | Node/source/UTC, read-only credentials, rate limits |
| **READ with heavy load** | `tablehistograms` across many tables, sampled tracing, `repair --preview` | CPU/IO budget, change window, stop gate |
| **Reversible STATE_CHANGE** | Toggle a runtime feature, change logging level, adjust throttle | Approval, expiry, and config restore procedure |
| **Heavy STATE_CHANGE** | `repair`, `cleanup`, `rebuild`, compaction, bootstrap operations | Topology health, concurrency limits, data integrity review |
| **DESTRUCTIVE / hard to reverse** | `truncatehints`, `clearsnapshot`, `decommission`, CQL `TRUNCATE/DROP` | Dual approval, backup/recovery plan, blast radius analysis |

Some **read** commands still impose heavy CPU/IO cost (for example, `repair --preview` builds Merkle trees). Conversely, commands that alter runtime settings—even when reversible—can temporarily jeopardize durability or availability. Classify operations by **actual impact** for your release and workload.

### 6.3. Diagnostic Command Set During Incidents

~~~bash
# Observe from an authorized host; verify nodetool help for your release.
date -u +"%Y-%m-%dT%H:%M:%SZ"
nodetool status
nodetool describecluster
nodetool info
nodetool tpstats
nodetool proxyhistograms
nodetool compactionstats
nodetool netstats
nodetool tablestats incident_lab.events_by_device_day
~~~

Record the exact node queried: `status` output on N1 and N3 can diverge during gossip or network partitions. `netstats` reflects streaming, not hints backlog counters; `proxyhistograms` reports coordinator latency, not API p99. Never average p99 values across nodes or sum layer p99 latencies into an end-to-end p99.

### 6.4. Using Help and Proper Credential Handling

~~~bash
nodetool help status
nodetool help repair
nodetool help enableauditlog
~~~

Never pass passwords via `-pw` on the command line where they can leak into process lists or shell history. When JMX auth requires credentials, use securely managed password files or secret injection, enforcing strict file permissions and log redaction. Never post raw terminal outputs containing IPs, usernames, or sensitive queries to public systems.

### 6.5. Runbook Readiness Criteria

- Assigned owner and version/last-reviewed date.
- Reviewed by relevant DBA/SRE/Security teams and rehearsed at least once in a lab.
- Working dashboard/log links and valid on-call rotation contacts.
- Accurately reflects the real Cassandra release, DC/RF/CL, and topology with data protections.
- Specifies preflight checks, commands, expected output, failure branches, stop conditions, and rollback.
- Contains no hardcoded admin passwords, private keys, or production endpoints.
- Every update passes code review/approval and carries a change ID.

A checklist saying "restart all nodes" or "run cluster-wide repair" without assessing quorum, scope, and failure modes **is not a safe runbook**.

## 7. Three Core Playbooks: Quorum, Disk, and Repair

### 7.1. RB-1: Rising Read/WriteTimeout or Unavailable Errors

**Trigger:** user-facing error rate rises; Java logs show `DriverTimeoutException` / `ReadTimeoutException` / `WriteTimeoutException` / `UnavailableException`.

**Observe before intervening:**

1. Build a UTC timeline covering first-bad, changes, and `T_alert_fire`.
2. Separate HTTP/gateway timeouts, Driver deadlines, and coordinator READ/WRITE_TIMEOUTs. Never lump all errors into a single "timeout" counter.
3. Inspect query RF/DC/CL and liveness of **natural replicas** (distinct from the coordinator).
4. Gather node status from multiple nodes if gossip disagreement is suspected.
5. Check client connection pools/throttlers, retries, and speculative execution; total CQL attempts may exceed HTTP requests.
6. Examine disk/GC/network/table tombstones/compaction and formulate falsifiable hypotheses.

**Do not do autonomously:** lower CL to eliminate Unavailable errors, stack multi-layer retries, raise request timeouts unboundedly, or restart multiple replicas simultaneously.

**Exit:** successful reads/writes at required CL, error rate within SLO under representative traffic, unknown writes reconciled or assigned, and verified topology and data integrity evidence.

### 7.2. RB-2: Critical Disk Headroom

**Trigger:** estimated time-to-full is shorter than safe intervention time, or free space falls below safety headroom for compaction/commitlog.

**Safe steps:**

1. Separate mounts for data, commitlog, hints, snapshots, logs/audit, and remote backup staging.
2. Gather disk bytes/inodes plus growth trend and active compaction/streaming/hints/backup jobs.
3. Identify growth drivers after deploys, TTL expirations, write bursts, or repair concurrency.
4. Estimate headroom required for **ongoing compaction/streaming**; a low used-% alone may still leave insufficient space for active tasks.
5. If reducing offered write rate or pausing jobs is required, obtain SLA approval with a rollback plan.
6. Check whether audit log archival alerts are hitting quota as well; never disable auditing arbitrarily to reclaim disk space.

**Do not do autonomously:** delete commitlogs, SSTables, hints, or snapshots without verifying backups/retention; run major compaction to "clean up" when disk is already nearly full.

**Exit:** stable disk free space/growth headroom, healthy CQL writes, unblocked commitlog/compaction/backup/audit paths, and preserved data invariants.

### 7.3. RB-3: Overdue Repair Schedule or Inconsistency

**Trigger:** time since last successful repair exceeds policy, `gc_grace_seconds` risk, or unstored hints / evidenced replica divergence.

**Preflight:**

- Distinguish hinted handoff, read repair, and anti-entropy repair.
- Check RF/DC, natural replicas Up, target topology Normal, and repair history.
- Choose full vs. incremental, ranges/tables, concurrency, and disk/network budgets.
- With `-pr`, a cluster-wide schedule must cover primary ranges across all relevant nodes/DCs per runbook; running it on a single node **is not** a full cluster repair.
- If purged tombstones and data resurrection are suspected, **do not repair blindly**, as repair can propagate stale data.
- `--preview` can still consume significant resources despite not streaming; enforce budget and approval.

**Exit:** repair job succeeds within committed scope, SSTable/streaming errors are reconciled, and sample data plus application consistency pass checks. Never infer from `UN` in `nodetool status` that replicas have converged.

### 7.4. RB-4: Authentication/Authorization Errors After a Change

**Trigger:** `UnauthorizedException`, failed logins, or CQL DCL changes outside maintenance windows.

**Observe:** CQL audit logs (`AUTH/DCL/ERROR`) across all relevant coordinators; deployment identity, certificate/truststore/KMS metadata, schema/role grants, and `system_auth` RF/repair state. Separate TLS handshake failures (pre-CQL) from CQL login/authz failures. Confirm the app uses the intended local DC, identity, and role.

**Do not do autonomously:** disable TLS or authentication, grant superuser to applications, log passwords, or paste private keys into incident chat. Execute controlled rollout/rollback per the security runbook.

### 7.5. Coincident Two-Issue Scenarios

If pending compactions rise at the exact moment Java v28 deploys, that alone is insufficient proof that v28 **caused compaction** or that compaction **caused timeouts**. Compare identical query shapes/CL across v27/v28 alongside per-node IO/GC. Minute-level temporal correlation does not prove causality. Runbooks should force responders to write **predictions distinguishing the two hypotheses** instead of jumping straight to restarts or changing compaction strategies.

## 8. Cassandra Audit Logging: Capturing CQL and Authentication

### 8.1. What Can and Cannot Cassandra 4.0+ Record?

Apache Cassandra introduced **Audit Logging** in version 4.0, configured **per node** via `audit_logging_options` or `nodetool enableauditlog`. It can capture successful and failed CQL requests as well as authentication/authorization events, governed by categories and filters.

| Event Type | Captured by CQL Audit When Filters Allow? | Examples |
|---|---|---|
| DDL | Yes | `CREATE TABLE`, `ALTER KEYSPACE`, `DROP INDEX`, `TRUNCATE` |
| DCL | Yes | `GRANT`, `REVOKE`, `CREATE ROLE`, `ALTER ROLE` |
| DML | Yes | `UPDATE`, `DELETE`, `INSERT`, and batches per release taxonomy |
| QUERY/PREPARE | Yes | `SELECT`, prepared requests |
| AUTH/ERROR | Yes | Login success/failure, unauthorized attempt, request failure |
| `nodetool repair` / `cleanup` / `disablehandoff` | **No** | These are JMX/management operations |
| Editing `cassandra.yaml` / `logback.xml` | **No** | Filesystem/deployment operations |
| SSH/sudo, container/Kubernetes/cloud actions | **No** | Activity outside the native CQL protocol |

**Key takeaway:** Cassandra's audit log is not a complete DBA/operator log. Official documentation explicitly states it **does not capture `nodetool` commands or `cassandra.yaml` edits**. To know who ran repair, changed RF, drained, or restarted nodes, you must maintain an independent **administrative action ledger**.

### 8.2. Fields in a CQL Audit Entry

Depending on the implementation, an entry includes:

~~~text
timestamp        Unix timestamp of the request from the source
user             CQL role
source           client IP + port
host             coordinator node receiving the request
keyspace         keyspace involved
scope            table/aggregate/function/role if applicable
category/type    DDL, DCL, DML, QUERY, PREPARE, AUTH, ERROR
operation        CQL command or operation name
batch            batch identifier if applicable
state/options    request state and options per logger/version
~~~

**Audit records are written on the coordinator handling the CQL request**, not replicated by RF like table data. Under RF3, an `UPDATE` acknowledged by two replicas may produce only one audit record on its coordinator. Consequently, collect audit logs from **every node capable of acting as a coordinator**, not just a table's natural replicas.

### 8.3. Implementations and Security Considerations

| Logger | Characteristics | Considerations |
|---|---|---|
| `BinAuditLogger` | Binary Chronicle Queue segments | Uses `auditlogviewer`; requires rolling/archiving/permissions |
| `FileAuditLogger` | Text via the logging framework | Human-readable, but different performance/retention tradeoffs |
| `NoOpAuditLogger` | Writes no audit records | Unsuitable for policies mandating audit trails |

Do not blindly enable **Full Query Logging (FQL)** in place of audit logging: FQL targets replay/debugging/performance with different semantics, overhead, and PII exposure; audit logging targets CQL and auth events rather than replaying all business operations.

**Privacy:** CQL text may contain sensitive literals; prepared statement audits do not necessarily log bound values during EXECUTE, but **never assume logs are inherently safe**. Malformed statements, query literals, and custom loggers can leak sensitive data. Cassandra masks passwords in certain DCL patterns, which does not replace redaction or testing malformed statements. Enforce encryption, retention, access controls, and auditing of read access to the logs themselves.

### 8.4. Illustrative Cassandra 5.0 Configuration

~~~yaml
# cassandra.yaml for isolated lab ONLY; requires per-node approval/rollout.
audit_logging_options:
  enabled: true
  logger:
    - class_name: BinAuditLogger
  audit_logs_dir: /srv/cassandra-audit-lab
  included_categories: AUTH,ERROR,DDL,DCL,PREPARE
  excluded_keyspaces: system,system_schema,system_virtual_schema
  roll_cycle: HOURLY
  block: true
  max_queue_weight: 268435456
  max_log_size: 17179869184
~~~

**Scope:** setting `included_categories` as above **does not capture every DML/QUERY**; this is strictly a lab policy focused on administrative CQL and auth, so you cannot claim "all CQL is audited." If compliance requires capturing all operations, review filters, retention, cost, and PII exposure. Reaching `max_log_size` can delete older segments; configure archiving aligned with policy and storage capacity.

Cassandra supports `archive_command` to move logs off ephemeral disks. An archive command executed by the Cassandra process requires threat modeling around shell/script permissions, file lifecycles, and withholding JMX access from untrusted actors. Runtime settings via `nodetool enableauditlog` can **override** `cassandra.yaml` values on that node; verify actual runtime state.

### 8.5. Safely Observing Audit Logging

~~~bash
# Inspect runtime config; exact syntax depends on Cassandra version:
nodetool getauditlog

# Can be cross-checked with JMX StorageService AuditLogEnabled.

# On a copy of binary logs in an isolated lab:
auditlogviewer /srv/cassandra-audit-lab
~~~

Check `nodetool help getauditlog` / `auditlogviewer --help` for your release. Never toggle `enableauditlog` or `disableauditlog` in production just to experiment without assessing storage, performance, and security impact. Showing enabled on one node does not prove other nodes have it enabled or that collectors shipped files to an independent audit store.

### 8.6. Testing CQL Audit Filters in a Learning Cluster

In an isolated cluster whose actual datacenter name is `dc1`, create lab schema:

~~~sql
CREATE KEYSPACE IF NOT EXISTS audit_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 1
};

CREATE TABLE IF NOT EXISTS audit_lab.action_probe (
    id uuid PRIMARY KEY,
    note text
);

INSERT INTO audit_lab.action_probe (id, note)
VALUES (11111111-1111-4111-8111-111111111111, 'lab-check');

SELECT note FROM audit_lab.action_probe
WHERE id = 11111111-1111-4111-8111-111111111111;
~~~

With `included_categories` limited to `AUTH,ERROR,DDL,DCL,PREPARE`, `CREATE TABLE` may appear, whereas `INSERT/SELECT` **are excluded**; this acts as a **negative control** proving filters work. `CREATE KEYSPACE IF NOT EXISTS` when the keyspace already exists creates no new object even though the request itself may still be audited.

After testing, inspect binary logs on the **actual coordinator** and verify fields, timestamps, categories, and archiving. Do not expect three audit copies under RF3. If an event is missing, verify `enabled`, filters, node identity, UTC time, and logdir/collector health before concluding the command never ran.

## 9. Administrative Logs Must Extend Beyond CQL Audit

### 9.1. Evidence Sources Per Operational Channel

| Channel | Examples | Evidence Sources |
|---|---|---|
| CQL native | `ALTER TABLE`, `GRANT`, `TRUNCATE` | Coordinator CQL audit + change ticket |
| JMX/`nodetool` | `repair`, `disablehandoff`, `drain` | Command wrapper + host process audit + change ID |
| SSH/sudo | Service restart, file/mount edits | OS auditd/sudo logs, session recording where appropriate |
| Kubernetes | Scale StatefulSet, config rollout/pod restart | Kubernetes API audit, deployment events |
| Cloud platform | Disk resize, firewall, KMS/secrets | IAM/cloud activity trail |
| Configuration repository | `cassandra.yaml`, JVM flags, logging | Git commit, review, signed build/rollout |
| CI/CD scheduler | Automated repair/backup/cert rollout | Workflow run ID, identity, approvals |
| Alertmanager | Silence/inhibition, threshold change | Ruleset commit, silence actor/expiry |

**One log type cannot replace another.** Cassandra seeing `ALTER TABLE` does not prove who restarted a Kubernetes pod; the OS seeing a `nodetool` process does not prove the command repaired the entire cluster; a change ticket records intent, not execution.

### 9.2. Minimum Fields in an Administrative Action Ledger

~~~text
action_id              unique, stable across retries
incident_id/change_id  approved reason and operator context
actor_principal        human/service identity via SSO/workload identity
approver_principal     independent approval for high-risk operations
host_identity          exact host ID and data center
cluster_identity       cluster and environment allowlist
operation_class        READ / CONFIG_CHANGE / REPAIR / DESTRUCTIVE
command_name           nodetool repair, CQL ALTER TABLE, ...
sanitized_argv         structured arguments, secrets REDACTED
command_fingerprint    digest of safe canonical command and target
planned_time_utc       approval time
started_time_utc       actual execution start
finished_time_utc      observed finish or UNKNOWN
exit_code              integer or NO_RESULT
before_evidence_ids    metrics/config/status snapshots
after_evidence_ids     same UTC filters and data checks
rollback_or_stop       planned and observed status
audit_storage_ref      immutable log or object version ID
~~~

Never record full raw stdin/stdout if it might contain secrets, partition values, or user tokens. Bound output size, apply redaction, and audit log access. `sanitized_argv` must remain clear enough to identify the command without exposing credentials.

### 9.3. Intent, Execution, and Outcome Are Three Separate Events

~~~text
10:41:10Z  APPROVED  CHG-42: repair table X on node N2
10:42:01Z  EXECUTED  ACT-87: nodetool repair -pr X
10:58:31Z  VERIFIED  repair completed for selected scope
~~~

If APPROVED but the job never ran, do not record EXECUTED. When a process is killed or output is lost, record `EXECUTION_OUTCOME_UNKNOWN`. `exit_code=0` proves neither full-cluster repair nor that every client now reads correct data.

### 9.4. Four Properties of an Audit Ledger

1. **Attribution:** accountable human or workload identity; never a shared OS account alone.
2. **Integrity:** append-only storage, tamper-evident signatures, or object lock; actors cannot delete their own evidence.
3. **Completeness:** sanctioned paths go through wrappers/CI/JIT access; host/cloud logs detect bypasses.
4. **Correlation:** action IDs link incidents, changes, clusters, nodes, UTC timestamps, and metrics.

If audit records live solely on the same Cassandra node experiencing disk exhaustion, they can be lost right when needed most. Ship them to an independent audit store and verify log retention and restore procedures.

### 9.5. Desired State Differs from Runtime State

After a GitOps rollout, `cassandra.yaml` on disk may have changed while the Cassandra process has not restarted yet, or a JMX override may have altered a runtime option. Track separately:

~~~text
desired_config_hash
deployed_file_hash
observed_runtime_JMX_values
restart_required
last_rollout_success_utc
nodes_not_converged
~~~

A Git commit **does not** prove every node applied the change. Action audits should link the commit/build digest, deployment phase, per-node completion, and runtime state checks.

## 10. Log Schemas and Integrity Controls

### 10.1. Proposed JSONL Event Format

~~~json
{
  "schema_version": 1,
  "action_id": "ACT-20261121-0087",
  "run_id": "RUN-20261121-04",
  "incident_id": "INC-20261121-11",
  "change_id": "CHG-42",
  "event_type": "ACTION_FINISHED",
  "actor": "workload:db-maintenance-runner",
  "approver": "role:db-second-approver",
  "cluster": "cass-lab-a",
  "environment": "isolated-lab",
  "datacenter": "dc1",
  "node_id": "node-2",
  "command": "nodetool",
  "argv_redacted": ["repair", "-pr", "audit_lab", "action_probe"],
  "category": "STATE_CHANGE",
  "started_utc": "2026-11-21T10:42:01Z",
  "finished_utc": "2026-11-21T10:58:31Z",
  "exit_code": 0,
  "result": "COMMAND_COMPLETED_VERIFICATION_PENDING",
  "before_evidence": ["EV-001", "EV-002"],
  "after_evidence": ["EV-010"],
  "evidence_ref": "audit://runs/RUN-20261121-04/action-ACT-0087"
}
~~~

This is a **synthetic record**, not a built-in Cassandra API. `audit://` is purely an internal illustration. Production implementations also need `actor_identity_source`, `approval_expires_utc`, binary/script digest, exit signal, redacted stdout/stderr digests, node host ID, and collector status.

### 10.2. Never Store the Audit Ledger Only Inside the Failing Cassandra Cluster

If the action ledger is written **solely to the Cassandra cluster being repaired**, an outage or full disk prevents recording the very events you need most. Use an **external durable audit sink** such as append-only object storage, a SIEM, or a hardened log service. You may keep an indexed query copy, but audit durability must not depend solely on the system suffering an outage.

Fail-closed rules:

- Without valid approval, lease, and writable audit sink for risky actions, **do not execute**.
- Emergency break-glass must follow a pre-approved mechanism with session recording, offline evidence, and post-incident backfill tagged `BREAK_GLASS`.
- Anyone authorized to run commands must not have permission to delete or alter evidence.
- An audit sink outage is an observability/security incident requiring its own escalation.

### 10.3. Hash Chains with a Trusted Anchor

A tamper-evident design:

~~~text
event_hash_i = SHA256(canonical_json(event_i) || event_hash_(i-1))
signed_checkpoint = SIGN_KMS(event_hash_i, UTC, run_id)
storage = immutable object versions + restricted delete privileges
~~~

A hash chain detects tampering only when paired with an external **trusted anchor**. If an attacker can alter both the chain and the anchor, SHA-256 alone provides no protection. Combine KMS signatures, object lock, separation of duties, retention, and strict audit read controls.

### 10.4. Timestamps and Verifiable Evidence

~~~text
event_time_utc         timestamp measured by the agent
received_at_utc        collector ingest time
clock_offset_estimate  if known
monotonic_duration_ms  duration measured within a single process
source_host_id         source of evidence
collector_version      log schema/mapping
~~~

If a node's clock drifts by 90 seconds, never sort commands and errors by raw timestamp to claim causality. Record uncertainty whenever reliable time synchronization is unavailable, and preserve evidence IDs/links so reviewers can audit independently.

## 11. Automation Wrappers: Minimal Privilege, Before-and-After Evidence

### 11.1. Contract of an Operation

A wrapper must not simply run `ssh host "nodetool repair ..."` and record an exit code. It must enforce **preconditions** and **postconditions**:

~~~mermaid
flowchart TD
    A["Alert or change request"] --> B{"Target in allowlist?"}
    B -->|No| X["BLOCKED + audit event"]
    B -->|Yes| C{"Action allowed by policy?"}
    C -->|No| X
    C -->|Yes| D{"Approval + lease + audit sink OK?"}
    D -->|No| X
    D -->|Yes| E["Save BEFORE + planned action"]
    E --> F["Exec argv, no shell, bounded timeout"]
    F --> G["Save exit/signal/output digest"]
    G --> H["Verify expected SLO and data invariants"]
    H --> I["Immutable AFTER event + release lease"]
~~~

Provide no bypass branch that skips BEFORE snapshots/approval because a collector is slow while still reporting PASS. Emergencies require a pre-approved **break-glass policy**.

### 11.2. Risk-Tiered Operation Registry

~~~yaml
environment: isolated-cassandra-lab
allowed_cluster_ids: ["cass-lab-a"]
operations:
  status:
    executable: nodetool
    argv_template: ["status"]
    risk: READ
    approval: false
    max_duration_seconds: 60
  compactionstats:
    executable: nodetool
    argv_template: ["compactionstats"]
    risk: READ
    approval: false
    max_duration_seconds: 60
  repair_selected_table:
    executable: nodetool
    argv_template: ["repair", "-pr", "{keyspace}", "{table}"]
    risk: STATE_CHANGE
    approval: two_person
    max_duration_seconds: 7200
  truncatehints:
    risk: DESTRUCTIVE
    enabled: false
~~~

This is a **custom design schema**, not a configuration Cassandra or a runner automatically understands. Template parameters must be validated against an allowlist of keyspaces/tables; never concatenate strings into a shell. Risk depends on topology, so an action approved for a lab does not automatically authorize production execution.

### 11.3. Runner Framework Pseudocode

~~~text
function execute_change(request):
    action_id = allocate_unique_id()
    require(request.cluster_id in approved_clusters)
    require(request.environment == "isolated-lab")
    require(validate_operation_and_args(request))
    require(valid_change_id_and_not_expired(request))
    require(approval_for_risk_class(request))
    lease = acquire_cluster_operation_lock(request.cluster_id)
    if lease unavailable:
        emit_audit(BLOCKED, "another change in progress")
        return BLOCKED

    try:
        require(audit_sink_is_writable())
        before = collect_bounded_read_only_evidence(request)
        emit_audit_durably(PLANNED, action_id, before, redacted_args)
        result = exec_without_shell(
            argv=validated_fixed_executable_and_args,
            timeout=request.deadline,
            cwd=controlled_working_directory,
            env=allowlisted_environment)
        emit_audit_durably(EXECUTION_FINISHED, result.code, output_hash)
        after = collect_bounded_read_only_evidence(request)
        verify = verify_postconditions_and_data_invariants(after)
        emit_audit_durably(VERIFIED_OR_FAILED, verify, after)
        return verify
    catch error:
        safe_capture_and_notify(error)
        return FAILED_OR_UNKNOWN
    finally:
        release_lease(lease)
~~~

This is **pseudocode**, omitting authentication, durable transport, crash recovery, signal/exit handling, and secret management. Never deploy it verbatim as a production runner. If the process is killed after the command starts but before the FINISHED event is written, an external watchdog must inspect host audits/server state and report `OUTCOME_UNKNOWN`; never retry a destructive command merely because a log entry is missing.

### 11.4. Retries and Idempotency

| Scenario | Policy | Rationale |
|---|---|---|
| `nodetool status` transient TCP error | Bounded retry with backoff | Read-only |
| Audit sink 503 | Retry before command; if still failing, BLOCKED | No changes without audit evidence |
| `repair` loses connection mid-run | Do not blindly repeat; query server job state | The job may still be running |
| `cleanup` timeout | Verify before retrying | SSTables may already have changed |
| `ALTER TABLE` timeout | Check schema agreement before resubmitting | DDL may already have applied |
| KMS/credentials rejected | Fail and escalate | Never weaken security to proceed |
| Wrong cluster ID | ABORT immediately | Safety violation; retries cannot fix it |

### 11.5. Never Auto-"Fix" Unknown Root Causes

A dangerous auto-remediator:

~~~text
WHEN ReadTimeout > threshold:
  restart all Cassandra nodes
  lower consistency level
  run full repair
~~~

These actions can destroy quorum, increase stale reads, saturate disk IO, and erase forensic evidence. Safe automation can **capture metric/log snapshots, correlate alerts, create tickets, and prepare action proposals**; state-changing actions require approval and risk-tiered safety policies.

### 11.6. Concurrency Budgets and Stop Conditions

- Cluster/DC/token-range leases preventing overlapping repairs when prohibited by runbook.
- Budgets for disk, inodes, IOPS, network, CPU, GC, and user-impact limits.
- Rollback to the **previous version/config hash**, not blindly to stock defaults.
- Per-stage timeouts, canary-first rollout, and automatic stop if SLO/host safety degrades.
- Block operations during schema disagreement or moving topology when stable token ownership is required.

Good automation knows **when not to run**, not merely command syntax.

## 12. Authorization, Security, Retention, and Auditability

### 12.1. Least Privilege by Role

| Role | Permitted | Should Not Be Permitted |
|---|---|---|
| Observer / Tier-1 on-call | View redacted SLO/JMX/host logs, `nodetool status/info` | `repair`, `TRUNCATE`, schema/RF edits |
| DBA operator | Approved scoped maintenance | Deleting audit evidence or self-approving high-risk actions |
| Change approver | Approve plans/risk, oversee changes | Impersonating runners, altering audit logs |
| Security auditor | Read CQL/OS/cloud audits and signed records | CQL admin mutations |
| Automation runner | Fixed argv/clusters in registry, short-lived identity | Arbitrary shell/root/all-cluster access |
| Evidence collector | Append/ship events to audit store | Deleting or editing sealed segments |
| Break-glass operator | Policy-governed emergency actions | Arbitrarily bypassing MFA or post-action review |

JMX exposes powerful management APIs; never assume all JMX read APIs are safe sandboxes without fine-grained permissions. CQL grants do not restrict privileged SSH/root access. Separate SSO, cloud/Kubernetes, OS/JMX, and CQL identities; avoid long-lived shared accounts.

### 12.2. What to Log vs. What to Avoid Logging

**Log:** action/actor/target/UTC, operation class, keyspace/table scope, sanitized arguments, desired vs. actual version, exit/signal, before/after metrics, approval, change ID, and evidence references.

**Do not log by default:** raw CQL bound values, customer IDs, passwords/JMX secrets, TLS private keys, token-bearing URLs, or full STDOUT from data queries. To correlate a real key safely, use a **keyed HMAC** or approved fixture IDs; unkeyed hashes of predictable IDs offer inadequate protection.

CQL audit may mask passwords in certain DCL patterns, though not reliably for malformed queries; test redaction rules in a lab. Never upload audit segments or production logs to public issue trackers.

### 12.3. Queue and Availability Tradeoffs

- **Block/backpressure** when the audit queue fills can raise request latency while lowering the risk of dropped logs, depending on implementation.
- **Drop-on-overload** preserves throughput at the cost of lost evidence, unsuitable for many compliance policies.

Do not assume `block: true` alone guarantees zero log loss if a disk/node crashes or archiving fails. Benchmark capacity and performance in a lab, monitor queues/disk/archivers, configure retention, and alert separately on logging failures.

### 12.4. Retention and Key Management

Example internal policy:

~~~text
hot audit search: 7-30 days
immutable archive: 90-365+ days where required
incident legal hold: longer when authorized
KMS key version: retained for full evidence lifetime
read access: SSO/JIT/MFA with access logs
deletion: approved, logged, separated from action operator
~~~

These durations **are purely illustrative**, neither Cassandra defaults nor legal mandates. Retention must satisfy privacy policy, minimize unnecessary data storage, and keep decryption keys/permissions valid throughout the retention lifecycle.

### 12.5. "Enabled" Audit Logging Is Not Enough

A coverage verification checks:

1. `AuditLogEnabled` on every node, including nodes that recently joined after maintenance.
2. Categories/keyspaces/users included/excluded per policy.
3. Actual output files exist and segments ship to an independent store.
4. Archive failures, disk/log rotation/retention, and log generation rates.
5. Clock sync, collector uptime, missing-node detection, and log gaps.
6. Permitted sample CQL events appear on the expected coordinator with expected fields.
7. `nodetool`/SSH/cloud activity is audited **outside Cassandra**.

A node reporting `AuditLogEnabled=true` that fails to ship logs—or excludes the DBA role—**fails audit compliance**.

### 12.6. Modifying Audit Policy Is Also a Privileged Change

Changing `included_categories` or `max_log_size` can spike log volume or reduce audit coverage. Require a capacity plan, policy owner, staged rollout, per-node event verification, rollback, and out-of-window change alerts. Record policy modifications in the **independent action ledger**, because CQL audit may not log logging-configuration changes themselves.

### 12.7. Logs Complement One Another

| Source | Answers What Question? | Limitations |
|---|---|---|
| Cassandra audit | Which CQL/auth requests hit the coordinator? | Does not record `nodetool`/config/SSH |
| OS/JMX wrapper | Who ran an admin command, on which host? | Does not prove replica convergence |
| Kubernetes/cloud audit | Who changed infrastructure or triggered a rollout? | Does not explain CQL data semantics |
| Git/change ticket | Intent and approval | Does not guarantee rollout completion |
| Full Query Logging | Query replay/debugging/performance | Distinct from CQL audit; carries overhead and sensitive data |
| Application traces | Business requests and CQL attempts | Does not cover non-application actors |

During an incident, you may need to join **multiple sources** by UTC timestamp, actor, host, request ID, and change ID. If a source does not exist, record `EVIDENCE_GAP`; never invent a causal narrative from guesswork.

## 13. Lab: Testing Alert → Runbook → Audit Evidence

### 13.1. Objectives and Environment

This lab offers two tracks:

- **Tabletop without Cassandra:** use synthetic metric/event series to design alert conditions, an incident timeline, an action ledger, and an evidence report.
- **Isolated Cassandra lab (if available):** create a synthetic keyspace/table, enable auditing in the test environment per capacity policy, execute a DDL statement and inspect the coordinator record; then run `nodetool status` to observe that CQL audit **does not** capture it.

Minimum setup:

~~~text
Cluster: cass-lab-a, Cassandra 4.1/5.0
DC: actual name confirmed (e.g., dc1)
Table: audit_lab.action_probe
Data: synthetic UUID, no production/customer records
Actors: CQL lab role, observer JMX identity, audit collector
Time: synchronized UTC within known tolerance
Expected output: incident report + action/evidence ledger
Forbidden: stop node, disable auth/TLS, production keys,
           delete hints/snapshots, force repair without lab approval
~~~

If the cluster has only one node, use RF1; **never use an RF1 lab to claim RF3 quorum tolerance when a node goes Down**. Learners lacking permission to enable audit logging may complete the tabletop track with sample logs without requesting production DBA credentials.

### 13.2. P0 — Baseline and Metrics Coverage

Read-only checks in the lab:

~~~bash
date -u +"%Y-%m-%dT%H:%M:%SZ"
nodetool info
nodetool status
nodetool describecluster
nodetool tpstats
nodetool compactionstats
nodetool getauditlog
~~~

Record: source host/DC, Cassandra release, keyspace RF, expected nodes vs. JMX exporter targets, audit enabled/filters/dir, log collector heartbeat, last successful test alert notification, and alert ruleset Git digest.

The goal of P0 is establishing a baseline and confirming the right lab target; never wire `nodetool status` into an automatic node-restart trigger.

### 13.3. P1 — Proving CQL Audit Behavior

Using the synthetic schema from Section 8.6 in an environment where you hold permission:

~~~sql
-- Table exists only in the isolated lab:
CREATE TABLE IF NOT EXISTS audit_lab.action_probe (
  id uuid PRIMARY KEY, note text
);

-- A controlled DDL statement to test the DDL audit category:
ALTER TABLE audit_lab.action_probe ADD audit_marker text;
~~~

**Run only once when the column does not yet exist.** `ALTER TABLE` mutates schema and requires lab approval plus a `DESCRIBE TABLE` preflight; never run it on shared/production keyspaces. If schema edits to existing tables are not permitted, `CREATE TABLE` with a run-specific name instead of altering an existing table.

Collect:

1. Actual coordinator hostname and UTC timestamp from the CQL client session if available.
2. Cassandra `DDL` audit record showing redacted user/scope/operation.
3. Command wrapper/CI approval and source terminal/session logs.
4. Post-operation schema agreement/metadata and any mismatch.
5. With filters restricted to DDL/DCL/AUTH, confirm routine `SELECT`/`INSERT` statements do not appear as designed—this reflects a coverage choice, not a bug.

### 13.4. P2 — Proving `nodetool` Is Absent from CQL Audit

Run `nodetool status` **through an approved READ wrapper** in the lab. Expected observations:

~~~text
ACTION_LEDGER:
  action_id=ACT-LAB-002, type=READ, command=nodetool status
  actor=observer, target=cass-lab-a/N1, result=SUCCESS

CASSANDRA_CQL_AUDIT:
  no corresponding nodetool command event expected

HOST_OR_WRAPPER_AUDIT:
  actor, process, invocation time, exit code present
~~~

**Not finding a record in CQL audit is expected behavior by design, not proof that `nodetool` never ran.** Flag `ADMIN_AUDIT_GAP` only if wrapper/host audits also lack the event. Standalone shell history is insufficient for compliance evidence because it can be edited/deleted and omits full stdin/actor details.

### 13.5. P3 — Validating Alerts with Synthetic Metric Series

No need to stop a real node: use Prometheus rule unit tests or replay sample time series into a sandbox environment. Example:

| UTC | API Traffic | HTTP Error Rate | Cassandra Read Timeouts/s | Exporter Up | Prediction |
|---|---:|---:|---:|---:|---|
| 10:00 | 2,000/s | 0.02% | 0.00 | 1 | Do not page |
| 10:05 | 2,100/s | 0.10% | 0.02 | 1 | Baseline investigation |
| 10:10 | 2,000/s | 2.00% | 0.40 | 1 | Error budget burn, responder notified |
| 10:12 | 2,100/s | 2.20% | 0.43 | 1 | Confirm sustained condition |
| 10:17 | 2,050/s | 0.03% | 0.00 | 1 | Wait for clear per window/for |
| 10:20 | 0/s | N/A | N/A | 0 | Telemetry unavailable; do **not** conclude healthy |

Values are entirely **synthetic** to test logic. With `for: 5m`, the timeout alert will not necessarily fire at exactly 10:10:00Z; timing depends on evaluation ticks and window coverage, so do not infer second-level precision from the table.

Collect test notification evidence: labels, severity, runbook link, receiver, and fired/ack/clear UTC timestamps. If the alert fails to reach the owner, the test FAILS even when the PromQL expression is valid.

### 13.6. P4 — Fail-Closed Negative Tests

In a simulated or lab-only environment:

- Submit a change targeting `cluster_id=production` outside the allowlist → `BLOCKED_WRONG_TARGET`, no process spawned.
- Attempt to run an approved action after approval expiration → `BLOCKED_APPROVAL_EXPIRED`.
- Drop the audit sink before EXECUTE → `BLOCKED_AUDIT_UNAVAILABLE`, no state mutation performed.
- Drop the connection between action start and command result → `OUTCOME_UNKNOWN`, never marked PASS.
- Stop a node from exporting audit logs after rotation → fire `AUDIT_INGEST_GAP`, never auto-delete segments.

**Never create negative tests by breaking production auditing.** Use mocks/fake transports in the runner test suite or cleanable isolated lab objects.

### 13.7. Lab Worksheet

| Evidence ID | Source | UTC / Scope | What It Proves | Limitations |
|---|---|---|---|---|
| EV-01 | Target inventory | _fill in_ | Lab target ID is accurate | Does not prove permissions |
| EV-02 | Prometheus unit test | _fill in_ | Rules fire/clear on sample data | Does not prove prod exporters |
| EV-03 | Alertmanager receiver log | _fill in_ | Notifications reach the right recipient | Does not prove mitigation |
| EV-04 | Cassandra audit | _fill in_ | Lab DDL recorded on coordinator | Does not include nodetool |
| EV-05 | Wrapper/OS audit | _fill in_ | Actor executed nodetool status | Does not prove data consistency |
| EV-06 | Change approval | _fill in_ | Action had authority and scope | Does not prove execution |
| EV-07 | Negative fail-closed | _fill in_ | Wrong target/sink error blocked | Test environment only |

**Lab PASS** requires all 7 evidence classes (or an acknowledged skip reason with documented coverage impact); never mark PASS if telemetry or notification delivery is missing. Correct answers must explicitly articulate the boundary between Cassandra CQL auditing and external action auditing.

## 14. Six Worked Incident Scenarios

### 14.1. Case A — Quorum Still Met While One Node Is Down

**Assumptions:** RF3 in dc1. N2 is Down; N1/N3 still serve writes at `LOCAL_QUORUM`. A node-down alert has been firing for 2 minutes, while API p99 and success rate remain unaffected.

**Assessment:** not necessarily SEV1 because 2/3 natural replicas still satisfy quorum, yet one layer of redundancy is gone; losing a second replica could make read/write quorum unavailable. Escalate based on outage duration, hints/repair schedules, write volume, node disk/GC, and recovery RTO. Collect `nodetool status` from multiple nodes; never restart N1 or N3 while only two replicas remain up.

**Evidence:** node views, RF/CL, lost-redundancy alert, repair/backup/DB owner, incident status. **Never** write "node Down = guaranteed data loss."

### 14.2. Case B — Coincident New Deployment and Compaction Backlog

**Assumptions:** v28 increases page size and CQL requests per HTTP request; concurrently, `Compaction.PendingTasks` rises on N2. v28 API instances show degraded p99, while v27 remains healthy.

**Assessment:** map affected vs. healthy cohorts by app version, DC, query shape, coordinator, and partition. Inspect CQL attempts/request, driver throttling, N2 disk/GC, and the change timeline. H1: query regression in v28; H2: IO saturation on N2; both may hold simultaneously. Before auto-intervening with compaction throttling, test H1 via an approved canary or rollback.

**Evidence:** deployment digest, parameter-free CQL fingerprint, UTC p99/errors, compaction metrics, approved mitigation, and post-change verification. **Never** pick a root cause from temporal correlation alone.

### 14.3. Case C — Out-of-Window CQL DCL Change

**Assumptions:** the app begins receiving `UnauthorizedException` after 11:03Z. CQL audit shows `REVOKE SELECT ON KEYSPACE ...` issued by an operator role on one coordinator at 11:02Z, with no matching change ticket.

**Assessment:** confirm the event occurred, identify actor/source IP, roles/grants, and affected services; correlate SSO, cloud, OS, and authorization changes. Escalate a security incident if unauthorized; obtain approver sign-off before restoring permissions. Avoid granting broad superuser privileges as a temporary workaround.

**Evidence:** CQL DCL audit, external action ledger (if available), role/grant state, approvals, and service recovery. **Never** paste passwords or sensitive query literals into incident chat.

### 14.4. Case D — Audit Logging "Enabled" Yet Evidence Missing

**Assumptions:** JMX `AuditLogEnabled=true` on N1, but the collector failed to ship segments, and local log quota rotated and deleted records from two days ago. Because the alert checked only enablement, it never fired.

**Assessment:** upgrade audit monitoring to track **enabled + ingestion lag + archive success + expected node coverage + oldest retained timestamp**. Review `max_log_size`, roll cycle, archive command, disk space, and KMS/permissions. Restore observability per the security runbook and transparently record `EVIDENCE_GAP`.

**Never** declare "auditing sufficient" based on a single Boolean, and never alter or delete audit files to fabricate a timeline.

### 14.5. Case E — A DBA Runs `nodetool repair` Over Direct SSH

**Assumptions:** after a deployment, latency spikes; shell history on one host contains `nodetool repair -pr ks table`, yet Cassandra CQL audit contains no matching record.

**Assessment:** Cassandra auditing does not log `nodetool`, so absence from CQL audit is **by design**. Gather OS/sudo/session-recorder logs, process events, change tickets, JMX/repair logs, and metrics. Inspect repair scope, job status, and IO impact. If a shared OS identity was used, establish attribution via SSO/JIT logs rather than blaming whoever appears in `sudoers`.

**Remediation:** enforce running privileged JMX actions through a wrapper/automation ledger, restrict direct SSH, and alert on bypasses. Never fabricate fake CQL events to "pass" compliance.

### 14.6. Case F — Silent Alert Due to Missing Data

**Assumptions:** an exporter goes down for 10 minutes; a Prometheus panel shows ReadTimeouts = 0 because `or vector(0)` is used in the dashboard, while the API continues returning 504s. On-call assumes Cassandra recovered.

**Assessment:** `or vector(0)` masks missing series as zeros; never treat it as health evidence without confirming successful node scrapes. Configure alerts on inventory mismatch / `up==0` and synthetic service requests; mark the incident `TELEMETRY_UNAVAILABLE`.

**Lesson:** monitoring is a second distributed system that can fail alongside Cassandra; "absence of data" must be monitored explicitly.

### 14.7. Quick Comparison

| Case | Initial Signal | Evidence Needed Beyond Cassandra Metrics |
|---|---|---|
| A | N2 Down, quorum intact | RF/CL, on-call notes, repair/backup state |
| B | v28 p99 + compaction | Deployment/code diff, driver traces, approvals |
| C | Unauthorized errors | CQL audit DCL, SSO/role/change ticket |
| D | Missing audit archives | Collector/KMS/cloud audit, archive health |
| E | Repair via SSH | Host/JMX/SSH process audit, repair status |
| F | Fake green dashboard | Exporter inventory, scrape gaps, API SLO |

## 15. Incident Reports, Postmortems, and Runbook Governance

### 15.1. Practical Report Template

~~~markdown
# INC-... — Cassandra symptom / remediation audit

## Summary
- Severity/status: INVESTIGATING / MITIGATED / RESOLVED
- Last known good UTC: ... (source and uncertainty)
- First known bad UTC: ... (source and uncertainty)
- Alert firing/acknowledgement UTC: ...
- User impact: service/error%/p99/affected operations

## Technical scope
- Cassandra version, cluster, DC/rack/node IDs:
- RF, effective read/write CL, Java Driver/execution profile:
- Keyspace/table/CQL fingerprint (redacted):
- Affected vs healthy control cohorts:
- Telemetry health and missing series:

## Hypotheses
- H1: prediction / falsifier / evidence / confidence
- H2: prediction / falsifier / evidence / confidence

## Administration changes
- Change ID, requester, approver, approved window:
- Operation type, sanitized args, target host ID:
- Execution start/end UTC, exit/signal, action_id:
- BEFORE/AFTER evidence, stop/rollback outcome:
- Cassandra CQL audit vs external action logs:

## Verification
- User SLO at representative offered traffic:
- CL/replica health, repair/hints/backup state:
- Unknown writes, TTL/tombstone risks:
- Audit/metrics/log ingestion gaps:

## Next steps
- Owners, deadlines, runbook/change links:
- Residual risks and next scheduled update:
~~~

Never declare `root cause=confirmed` simply because latency dropped after a restart without verifying the mechanism and confounding variables. A good report states clearly **what was observed, what was inferred, and what remains unknown**.

### 15.2. When Is an Incident Considered RESOLVED?

| Axis | Exit Criteria |
|---|---|
| Users | Error/success and latency SLOs recovered under representative traffic |
| Client | Retry/throttle/pool errors stable, appropriate request CL |
| Cassandra | Node/DC health, pending tasks, disk/GC/network headroom |
| Data | UNKNOWN writes, stale reads, repair/TTL risks handled or owned |
| Audit | Action evidence sealed; critical gaps documented and escalated |
| Operations | Mitigation configs have owner/expiry/rollback; runbooks updated |

**Alert cleared ≠ incident resolved.** A consistency incident can persist even while the API returns 200; a node showing `UN` does not prove all replicas are synchronized, and repairing one table does not cover all keyspaces.

### 15.3. Ten Postmortem Questions

1. How long was detection delayed after first-bad? Due to `for`, scrape/ingestion lag, silences, or missing coverage?
2. Did the page include owner, cluster/DC, RF/CL, and runbook?
3. Did any dashboard have wrong units/labels or improperly averaged p99 latencies?
4. Were any changes approved without execution records, or executed outside their window?
5. Did shared accounts obscure attribution?
6. Were Cassandra audit filters too narrow, or were logs lost to local quota?
7. Were admin/JMX/SSH/Kubernetes events missing?
8. Did mitigation prove data integrity or merely shed traffic?
9. Were any runbooks outdated or mismatched to the Cassandra version?
10. Does every action item have a fixture test and an owner for follow-up verification?

Postmortems must be **blameless**, focusing on improving controls, training, runbooks, and automation. If root cause remains unknown, publish `ROOT_CAUSE_UNRESOLVED` alongside the remaining hypotheses.

### 15.4. Measuring Program Maturity

| Metric | Why It Matters |
|---|---|
| % paging alerts with valid runbook URL + owner | Pages must be actionable |
| MTTD / MTTA / MTTR by service tier | Separates detection, acknowledgement, and recovery |
| False-page rate / repeat incidents | Reduces noise without masking failures |
| % privileged actions with change/action IDs | Control-plane audit coverage |
| % high-risk actions with dual approval | Real enforcement rather than paper policy |
| Audit ingestion lag / missing-node count | Measures evidence completeness |
| % runbooks reviewed/tested within window | Prevents stale operational knowledge |
| % incidents with user impact + integrity gate | Prevents closing incidents on green infrastructure metrics alone |

Low MTTR achieved by lowering CL or disabling security is not a success if data integrity is violated. Every KPI must be paired with safety guardrails, error budgets, and sampling coverage.

### 15.5. Versioning Runbooks After an Incident

~~~text
Observe: one triage step was misleading or unsafe
Propose: runbook diff with a test incident fixture
Review: DBA + SRE + Security for privileged changes
Simulate: isolated lab/tabletop with observed output
Release: signed version, changelog, on-call notification
Measure: lower time-to-diagnosis without higher data risk
~~~

Never convert a workaround from a past incident into blind auto-remediation for every request hitting the same exception class. `WriteTimeoutException` does not mean a mutation failed to persist; non-idempotent retries can corrupt data.

## 16. Exercises, Scenario Questions, and On-Call Checklists

### Exercise 1 — Does Cassandra Audit Log `nodetool`?

A DBA runs `nodetool repair -pr ks table`; CQL audit shows no matching entry. Can we conclude the command never ran?

**Answer:** No. Cassandra audit logging records coordinator CQL/auth activity, **not `nodetool`**. Use an external action ledger, host OS/JMX/session logs, and repair status to establish actor, command, and outcome.

### Exercise 2 — Is One Down Node Automatically SEV1?

In a single-DC RF3 cluster, N2 is Down while writes at `LOCAL_QUORUM` still succeed. Must the node-down alert always be SEV1?

**Answer:** Not automatically. Redundancy is degraded, yet quorum can still be met. Severity depends on business SLOs, remaining replicas, repair/hints/downtime age, and risk of losing a second node; escalate over time and based on recovery posture.

### Exercise 3 — Green Dashboard from Missing Data

The exporter is Down, all Cassandra timeout series vanish, and the panel defaults to displaying zero. Can the incident be closed?

**Answer:** No. Record `TELEMETRY_UNAVAILABLE`, inspect exporter/inventory health, and check user-facing SLIs, logs, and synthetic requests; never equate missing series with zero events.

### Exercise 4 — Averaging p99

N1 reports p99 of 12ms over 20,000 requests; N2 reports p99 of 500ms over 100 requests. An operator computes `(12+500)/2` as cluster p99.

**Answer:** Mathematically invalid. Aggregate percentiles must be derived from combined distributions/histogram samples with identical semantics; never average p99 values across nodes or add driver + coordinator + network p99s.

### Exercise 5 — Unscheduled CQL Role `REVOKE`

The app encounters `UnauthorizedException`, and CQL DCL audit shows `REVOKE` before first-bad with no change ticket. What is the first response?

**Answer:** Preserve the audit record/source/UTC, verify roles/grants and attribution, open a security/change incident, verify approved state, and then restore permissions per policy once approved. Never grant broad superuser permissions arbitrarily or expose passwords.

### Exercise 6 — `HintsSucceeded` and Data Convergence

A node returns to `UN` and `HintsSucceeded` climbs. Does that prove all replicas are synchronized?

**Answer:** No. Hints are best effort; they may not have been stored due to `max_hint_window`, failed deliveries, or divergence outside the read path. Verify hint holders/targets, repair history, data/CL semantics, and integrity.

### Exercise 7 — Audit Log Only on One Node

In Cassandra RF3, a CQL `INSERT` is acknowledged by two replicas; an auditor demands three audit entries, one per replica. Is the auditor right?

**Answer:** Incorrect. CQL audit events are logged on the coordinator receiving the request; they are not replicated per RF. Collect logs from all potential coordinators, not by natural replica count.

### Exercise 8 — Is Enabling Audit on N1 Sufficient?

`nodetool getauditlog` on N1 shows enabled, while N2/N3 are unknown. Can the cluster claim full audit coverage?

**Answer:** No. Audit configuration and runtime enablement are **per-node**; check every coordinator, filters, logdirs, archivers/collectors, and retention. A single enabled Boolean does not prove retrievable evidence.

### Exercise 9 — Retrying Repair After Runner Crash

A CI runner launches `nodetool repair`, then loses connectivity and receives no exit code. Should the entire command be retried immediately?

**Answer:** No. The repair may still be running or have completed part of the dataset; inspect server-side repair logs/job state, the action ledger, and resource budgets. Report `OUTCOME_UNKNOWN` and avoid blindly duplicating workload.

### Exercise 10 — Disk Alert and Snapshot Hardlinks

A dashboard reports the snapshots directory as "500 GiB" while disk free space is only 5 GiB; an operator suggests `clearsnapshot` to reclaim 500 GiB.

**Answer:** You cannot assume all 500 GiB will be freed because SSTable hardlinks share underlying blocks. Verify backups/retention, compaction needs, and real disk accounting; remove snapshots only via an approved runbook.

### Exercise 11 — Paging After a 5-Minute `for` Window

First-bad occurred in the 10:00–10:01Z bucket; the alert fired at 10:06Z. Is logging onset as 10:06Z valid?

**Answer:** No. That is the notification time after evaluation and `for`; estimate onset from last-good/first-bad and metric resolution, noting uncertainty.

### Exercise 12 — Silences During Maintenance

A team silences all Cassandra alerts for a month to avoid noise during a migration. What are the consequences?

**Answer:** It can hide unrelated disk or multi-replica failures, miss SLO breaches, and violate compliance. Silences must be narrowly scoped by cluster/alert/window, backed by an approval/change ID, owner/expiry, and paired with dedicated alerts for missing telemetry.

### Exercise 13 — Command Succeeded While Users Still See Errors

`nodetool cleanup` exits with code 0, yet API 5xx errors and p99 still violate SLO; can the incident be marked RESOLVED?

**Answer:** No. Exit 0 reflects only the scoped command result, not end-to-end service readiness. Verify app/driver/coordinator metrics, actual CL, offered traffic, and data correctness.

### Exercise 14 — CQL Audit Missing `PREPARE` or Bound Values

An application uses prepared statements; audit logs capture the prepared CQL but omit literal bind values. Is that a parser bug?

**Answer:** Not necessarily. Prepared statement audit logging does not log bound values on EXECUTE by design; verify release/logger/filter docs. Never turn on full query logging across production just to capture PII. For business attribution, pass safely designed operation IDs/hashes at the application layer.

### Exercise 15 — Audit Enabled but Archiving Fails

A node has auditing enabled, yet older local segments rotate out before the collector fetches them. Can compliance claim "no logs lost"?

**Answer:** No. Record an evidence gap, investigate the archiver/disk/retention/collector, remediate under security approval, and verify queries across all coordinators. Monitoring must track **ingestion lag and missing segments**, not just enablement.

### Exercise 16 — Break-Glass Without an Available Approval Service

A node faces critical disk exhaustion requiring emergency intervention while the approval service is temporarily unreachable. What is the right approach?

**Answer:** Follow the **pre-approved break-glass procedure**, confirm actor/target, capture maximum feasible session and offline evidence, escalate, enforce least-privilege time bounds, and complete post-facto review. Never treat "emergency" as license to bypass all auditing or fabricate logs afterward.

### Checklist for Alert Authors

- [ ] Signal ties directly to a user SLO, data correctness invariant, or concrete operational hazard.
- [ ] Includes owner, severity, clean labels, and a working runbook URL.
- [ ] Distinguishes application, Driver, and Cassandra exception/latency semantics.
- [ ] Thresholds/`for`/traffic floors are grounded in baseline data, not illustrative numbers.
- [ ] JMX-to-exporter mappings, units, and counter resets are verified.
- [ ] No customer/partition/request IDs appear in metric labels.
- [ ] Tested against no-traffic, missing-series, node restarts, scrape gaps, and stale metrics.
- [ ] Tested Alertmanager routing, acknowledgements, escalation, and silence expiry.
- [ ] Meta-monitoring covers both the audit collector and metric exporters.
- [ ] Alert rule changes carry a Git diff, reviewer, and rollback path.

### Checklist for On-Call Responders

- [ ] Recorded UTC timestamps, last-known-good/first-known-bad, and window uncertainty.
- [ ] Verified user-facing impact: errors, p95/p99, traffic, and data risk.
- [ ] Identified RF/CL/DC, cluster/release/node IDs, and affected cohorts.
- [ ] Correlated CQL error classes, Driver pool/timeouts, and coordinator metrics.
- [ ] Captured sufficient before-evidence without delaying urgent mitigation.
- [ ] Reviewed active changes/deploys and administrative actions inside the incident window.
- [ ] Formulated hypotheses with predictions/falsifiers instead of assuming causality from correlation.
- [ ] Refrained from blindly restarting multiple replicas, lowering CL, purging hints/snapshots, or running blind repair.
- [ ] Checked allowlist, approval, rollback, and audit sink before any state-changing action.
- [ ] Logged EXECUTED and VERIFIED separately; never treated exit 0 as proof of data correctness.
- [ ] Confirmed alert clearance aligns with recovered SLO/consistency and healthy telemetry.
- [ ] Handed off root-cause confidence, residual risks, owners, and next update time.

### Checklist for Auditors

- [ ] Collected CQL audits from **all coordinators**, not a single node.
- [ ] Verified runtime enablement, category/role/keyspace filters, archiving, and retention.
- [ ] Cross-checked `nodetool`/JMX/SSH/Kubernetes/cloud activity via external audit sources.
- [ ] Linked change ID, action ID, actor, approver, target, UTC timestamps, and command fingerprint.
- [ ] Verified least privilege and avoided shared admin identities where feasible.
- [ ] Confirmed BEFORE/AFTER evidence and policy-compliant log output redaction.
- [ ] Reported every `EVIDENCE_GAP`, clock skew, or missing-node metric.
- [ ] Verified audit store integrity, retention, key recovery, and separation of duties.
- [ ] Confirmed audit policy/silence changes and emergency break-glass events are logged.
- [ ] Scoped PASS/FAIL reporting with explicit limitations without overgeneralizing from lab samples.

## 17. References

These links point to **official documentation or relevant tool specification pages**. Always confirm your running Cassandra release, Java Driver, and Prometheus versions before applying syntax. Never copy lab configuration examples directly into production policy without review.

1. Apache Cassandra — [Audit Logging (4.0+)](https://cassandra.apache.org/doc/latest/cassandra/managing/operating/auditlogging.html): CQL/auth scope, **omits `nodetool`/`cassandra.yaml`**, coordinator-only logging, filters, `BinAuditLogger`, archiving, and viewer.
2. Apache Cassandra — [Audit Logging (overview)](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/audit_logging.html): `DDL/DCL/DML/AUTH/ERROR/PREPARE/QUERY` categories and prepared statements.
3. Apache Cassandra — [Monitoring Metrics](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html): per-node Dropwizard/JMX metrics, ClientRequest, ThreadPools, Compaction, CommitLog, DroppedMessages, and table histograms.
4. Apache Cassandra — [cassandra.yaml Configuration](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html): `audit_logging_options`, runtime/config options, JVM/storage parameters.
5. Apache Cassandra — [nodetool Overview](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/nodetool.html): distinguishing status/metrics commands from cluster-mutating commands.
6. Apache Cassandra — [nodetool help](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/help.html): version-specific command syntax.
7. Apache Cassandra — [nodetool getauditlog](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/getauditlog.html): inspecting runtime audit logging configuration.
8. Apache Cassandra — [nodetool enableauditlog](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/enableauditlog.html) and [disableauditlog](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/disableauditlog.html): changing audit state requires per-node approval and rollout.
9. Apache Cassandra — [Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html): anti-entropy, incremental/full repair, primary ranges, IO, and `gc_grace_seconds`.
10. Apache Cassandra — [nodetool repair](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/repair.html): `--full`, `-pr`, `--preview`, `--validate`, scope, and risks.
11. Apache Cassandra — [Hints](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/hints.html): best-effort hinted handoff, failure/backlog, and delivery metrics.
12. Apache Cassandra — [Compaction and Tombstones](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/tombstones.html): TTL/deletion/grace period, avoiding blind repair when resurrection risk exists.
13. Apache Cassandra Java Driver 4.19 — [Retries](https://apache.github.io/cassandra-java-driver/4.19.0/core/retries/): distinguishing timeouts, unavailable errors, and unknown write outcomes.
14. Apache Cassandra Java Driver 4.19 — [Metrics](https://apache.github.io/cassandra-java-driver/4.19.0/core/metrics/): session/node metrics, pool capacity, and disabled-by-default metrics.
15. Apache Cassandra Java Driver 4.19 — [Tracing](https://apache.github.io/cassandra-java-driver/4.19.0/core/tracing/): request/query tracing and sampling overhead.
16. Prometheus — [Alerting Rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/): expressions, `for`, `keep_firing_for`, labels/annotations.
17. Prometheus — [Alerting Best Practices](https://prometheus.io/docs/practices/alerting/): symptom-based alerts, user-visible impact, and avoiding noise.
18. Prometheus — [PromQL Functions](https://prometheus.io/docs/prometheus/latest/querying/functions/): `rate`, `increase`, handling counter resets, and histogram functions.
19. Prometheus Alertmanager — [Configuration](https://prometheus.io/docs/alerting/latest/configuration/): routing, grouping, inhibition, and receiver configuration.
20. Kubernetes — [Auditing](https://kubernetes.io/docs/tasks/debug/debug-cluster/audit/): API request audit events for scaling/rollout/cluster-resource operations outside Cassandra native auditing.

**Summary:** A good alert ties to **the right symptom, the right recipient, the right runbook, and sufficient telemetry**. A good runbook includes **preflight checks, low-impact diagnostics, approval gates, stop/rollback criteria, and data-correctness verification**. A sound administrative action leaves behind an **independent chain of evidence**—who approved it, who executed it, on which target, when, with what outcome, and how it affected users. Cassandra CQL auditing is only **one component** in that chain; it cannot by itself replace logging for `nodetool`, the operating system, CI/CD, and the control plane.
