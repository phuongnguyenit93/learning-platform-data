# Protection Modes, Apply Lag, Transport Lag, and Data Verification

Oracle Data Guard maintains one or more standby databases from a primary database's redo. However, having a standby does not automatically guarantee zero data loss. Actual protection depends on protection mode, redo transport, network latency, standby redo log writes, Redo Apply throughput, and whether DBAs verify data state.

The three common protection modes are Maximum Protection, Maximum Availability, and Maximum Performance. They represent trade-offs among primary availability, redo synchronization level, and potential data loss when the primary fails. In daily operations, two critical metrics are **transport lag** (redo not yet received at the standby) and **apply lag** (redo received but not yet applied). These two metrics help pinpoint whether an issue lies in the network/transport layer or in standby apply.

This lesson progresses from data-protection semantics to configuration, monitoring, resolving lag/gaps, and verification. Verification spans confirming Data Guard status, checking redo continuity, detecting block corruption, and performing logical data comparisons when business requirements demand independent proof.

After completing this lesson, you will be able to:

- Distinguish protection modes from redo transport modes.
- Explain Maximum Protection, Maximum Availability, and Maximum Performance.
- Understand how SYNC/ASYNC and AFFIRM/NOAFFIRM affect commit latency and durability.
- Select a protection mode based on RPO, RTO, and uptime requirements.
- Distinguish transport lag, apply lag, archive gaps, and apply throughput.
- Monitor Data Guard using V$DATAGUARD_STATS, V$ARCHIVE_DEST_STATUS, and related views.
- Understand the role of standby redo logs and real-time apply.
- Use Data Guard Broker to inspect status and validate configuration.
- Handle transport failures, apply backlogs, and missing archived logs.
- Verify blocks/datafiles and logical data between primary and standby.
- Design monitoring thresholds, alerts, failover drills, and operational runbooks.

> Syntax, broker features, and dynamic performance view columns vary by Oracle release. Examples assume common Data Guard physical standby setups; check Data Guard Concepts and Administration / Database Reference for your exact release, RAC/CDB topology, and licensing before applying.

## 1. Data Guard and High Availability Objectives

### 1.1. Primary and Standby

The primary database serves the read/write workload and generates redo for changes. The standby database receives redo from the primary and applies it to maintain a state close to the primary.

Common standby types:

- Physical standby: maintains a physical copy via Redo Apply.
- Logical standby: applies SQL equivalent to redo via SQL Apply, subject to data type and feature restrictions.
- Snapshot standby: can open temporarily read/write for certain test scenarios, then convert back to a physical standby and resume applying redo.

This lesson focuses primarily on physical standbys because protection modes, transport lag, and apply lag are typically operated around redo transport and Redo Apply.

### 1.2. Data Guard Is Not a Backup

A standby protects against certain host/site failures and supports role transitions. However, accidental data deletions, logic errors, or logical corruption can propagate to the standby via redo. Therefore, Data Guard does not replace independent backups, retention policies, and restore testing.

### 1.3. RPO and RTO

- RPO (Recovery Point Objective): maximum data loss tolerated by the organization when an incident occurs.
- RTO (Recovery Time Objective): maximum allowed duration to restore service.

Protection mode impacts RPO during sudden primary loss. Failover procedures, detection, client reconnection, DNS/service relocation, and application recovery impact RTO.

### 1.4. Two Stages of the Redo Path

```text
PRIMARY DATABASE
      |
      v
Online Redo Log / LGWR
      |
      v
Redo Transport (SYNC or ASYNC)
      |
      v
STANDBY REDO LOG (SRL)
      |
      v
Redo Apply
      |
      v
PHYSICAL STANDBY DATAFILES

Transport lag: redo has not reached the standby
Apply lag: redo reached the standby but is not yet applied
```

### 1.5. High Availability Is a Multi-Component System

Recoverability also depends on:

- Networking between primary and standby.
- Storage and I/O latency at both sites.
- Standby redo log configuration.
- Redo Apply processes and CPU capacity.
- Archive log retention and gap resolution.
- Broker/Clusterware and failover policies.
- Application services, connection pools, and client failover.
- Backups, monitoring, and operators.

A strict protection mode cannot compensate for an offline standby, insufficient storage, or unrehearsed failover procedures.

## 2. Protection Mode and Transport Mode

### 2.1. Protection Mode

Protection mode defines the primary's data-protection goal when shipping redo to standbys. The three primary modes:

- Maximum Protection.
- Maximum Availability.
- Maximum Performance.

A mode is a database configuration-level policy, not merely a network setting.

### 2.2. Redo Transport Mode

Redo transport has two primary modes:

- SYNC: primary waits for acknowledgment from the standby per configured transport semantics before confirming the corresponding commit.
- ASYNC: primary does not wait for the standby to receive redo on every commit; redo is shipped asynchronously.

SYNC and ASYNC are transport destination attributes. Protection mode governs the synchronization guarantee required and how the primary reacts when standbys cannot comply.

### 2.3. AFFIRM and NOAFFIRM

AFFIRM requires the standby to write redo to the standby redo log before acknowledging per transport semantics. NOAFFIRM permits acknowledgment before redo is durably written to the SRL. This can lower latency, though if the standby host/storage fails immediately after acknowledgment and before redo is persisted, protection guarantees differ from AFFIRM.

SYNC/AFFIRM provides stronger durability semantics at the expense of commit latency from network round-trips and standby I/O. SYNC/NOAFFIRM reduces remote disk write wait at the standby, while altering protection guarantees if the standby fails concurrently before redo is durably written.

### 2.4. Common Combinations

| Protection Mode | Typical Transport | Meaning |
| --- | --- | --- |
| Maximum Protection | SYNC AFFIRM | Does not confirm commits unless redo is durably protected at a synchronized standby; primary halts if no eligible standby remains |
| Maximum Availability | SYNC AFFIRM or SYNC NOAFFIRM depending on config/release | Prioritizes zero data loss while standby is synchronized, yet keeps primary running if standby disconnects |
| Maximum Performance | Typically ASYNC NOAFFIRM | Prioritizes primary performance; unshipped redo may be lost during failover |

These are common combinations, not the exhaustive list of supported configurations. Verify specific requirements for your protection mode and Oracle release.

### 2.5. Why You Cannot Look Only at the Word SYNC

SYNC indicates the primary waits for acknowledgment, whereas AFFIRM/NOAFFIRM dictates when the standby sends that acknowledgment relative to writing redo to the SRL. Furthermore, protection mode and standby state determine whether the database currently achieves the intended protection level.

### 2.6. Protection Mode vs. Protection Level

V$DATABASE exposes:

- PROTECTION_MODE: the configured mode.
- PROTECTION_LEVEL: the actual protection level currently achieved at observation time.

The two values can differ. For example, Maximum Availability may be configured while the synchronous standby is unavailable; the database may temporarily operate at a lower level. Monitoring must alert on degraded protection level rather than checking only the configured mode.

## 3. Maximum Protection

### 3.1. Objective

Maximum Protection places highest priority on preventing loss of committed data due to primary failure by requiring redo to be shipped synchronously and protected per configuration before commits are acknowledged.

In standard configurations, at least one standby must satisfy SYNC/AFFIRM and remain synchronized for the primary to continue operating.

### 3.2. Behavior When the Standby Disconnects

If no standby remains that satisfies the required protection level, the primary shuts down rather than continuing to commit without equivalent protection. This preserves RPO at the expense of primary availability when networks or standbys fail.

### 3.3. Trade-Offs

Advantages:

- Highest data protection among the standard protection modes.
- Minimizes risk of losing committed transactions on primary failure, provided synchronous standbys and infrastructure satisfy configured semantics.

Disadvantages:

- Primary may halt if standbys/networks become unavailable.
- Commit latency is impacted by network round-trips and standby I/O.
- Demands highly reliable network, standby, and storage design.
- Unsuitable if primary uptime outweighs near-zero RPO.

### 3.4. When to Use

Use only when the business mandates strict data protection and accepts halting primary service if synchronous standbys cannot respond. Requires reliable standby sites/networks, monitoring, and rapid recovery runbooks.

### 3.5. Maximum Protection Does Not Replace Backups

Maximum Protection does not guard against logic errors, accidental deletions replicated via redo, logical corruption, or loss of all copies in the same failure domain. Independent backups, immutable/offsite copies, and restore tests remain mandatory.

## 4. Maximum Availability

### 4.1. Objective

Maximum Availability aims for zero data loss while a synchronous standby is available, yet prioritizes keeping the primary operational if the standby or network temporarily disconnects.

### 4.2. When the Synchronous Standby Is Active

While the synchronous standby responds, commits coordinate with redo transport per SYNC configuration. With SYNC/AFFIRM, acknowledgment waits for redo to be durably written to the standby redo log.

### 4.3. When the Standby/Network Is Unavailable

The primary continues processing transactions instead of shutting down. During the unsynchronized period, protection level may degrade; if the primary also fails before redo is shipped, unshipped redo can be lost.

Thus, Maximum Availability is not an unconditional zero-data-loss guarantee across all failure states. Synchronous protection must be restored promptly, and monitoring must track degraded duration.

### 4.4. Trade-Offs

Advantages:

- Very high data protection while synchronous standbys are healthy.
- Primary remains available during transient standby/network outages.
- Often provides a strong balance between RPO and availability for production.

Disadvantages:

- Higher commit latency than ASYNC.
- During standby interruptions, effective RPO temporarily diverges from synchronized protection.
- Requires monitoring protection level and unsynchronized durations.

### 4.5. When to Use

Suitable for systems requiring very low RPO without wanting the primary to self-halt immediately on transient standby disconnects. Explicitly define acceptable degraded-protection duration and escalation procedures when thresholds are exceeded.

## 5. Maximum Performance

### 5.1. Objective

Maximum Performance prioritizes primary performance and availability. Redo is typically shipped ASYNC so commits do not wait for standbys to receive redo.

### 5.2. Behavior

The primary acknowledges commits before the corresponding redo reaches the standby. If the primary fails, the standby may lack the latest untransported, unreceived, or unapplied redo.

### 5.3. Trade-Offs

Advantages:

- Commit latency is largely insulated from round-trips to the standby.
- Primary keeps operating through standby/network disruptions.
- Suited for long geographic distances or latency-sensitive workloads.

Disadvantages:

- Most recent data may be lost upon failover.
- RPO depends on transport lag and unprotected redo at the standby.
- Requires lag monitoring and data-loss-aware failover decisions.

### 5.4. When to Use

Suitable when primary performance/availability takes priority and the business accepts a non-zero RPO. Quantify maximum tolerable data loss and ensure lag alerts and response procedures function properly.

### 5.5. Does Not Mean "Unsafe"

Maximum Performance can be the right choice when its RPO is acceptable and the standby is actively monitored. The danger lies in operating blind to lag or failing to test failover, not that ASYNC is inherently wrong.

## 6. Comparing Protection Modes by RPO/RTO

### 6.1. Selection Table

| Criterion | Maximum Protection | Maximum Availability | Maximum Performance |
| --- | --- | --- | --- |
| Priority | Highest data protection | Balances protection and availability | Primary performance/availability |
| Typical transport | SYNC AFFIRM | SYNC AFFIRM/NOAFFIRM per design | ASYNC |
| Commit waits for standby | Yes | Yes when synchronous standby is active | Does not wait per commit |
| When standby is lost | Primary shuts down if no eligible standby remains | Primary continues; protection may degrade | Primary continues |
| Data loss on primary failure | Prevented when mode/standby requirements hold | Prevented while synchronized; possible during degraded window | Untransported redo may be lost |
| Latency | Typically highest | Higher than ASYNC while sync is active | Lower since no sync ACK wait |

### 6.2. RPO Is More Than Just a Protection Mode

Actual RPO also depends on:

- Transport lag at failure time.
- Whether redo was received or still in flight on the network.
- Whether standby redo logs durably persisted the redo.
- Apply lag and standby readiness to open read/write after failover.
- Whether trailing redo can be salvaged from primary/online redo logs.
- Failure type: primary process, host, site, network, or storage.

### 6.3. RTO Is Not Determined by Protection Mode Alone

RTO also depends on detection, failover decisions, Broker/Observer, startup/recovery, service relocation, DNS/network updates, and application reconnection. Even a Maximum Protection system can suffer a long RTO without fast failover execution.

### 6.4. Defining Service-Level Objectives

Example operational targets:

| Objective | Metric |
| --- | --- |
| RPO | Maximum business-tolerable data loss |
| RTO | Time from incident start to healthy service |
| Transport lag | Delay of unreceived redo |
| Apply lag | Delay of unapplied redo |
| Protection level | Actual protection level currently achieved |
| Availability | Percentage of time the service is available |

Set thresholds per workload and SLA rather than copying numbers from another system.

## 7. SYNC, ASYNC, AFFIRM, and NOAFFIRM

### 7.1. SYNC

SYNC requires the primary to await a response from the synchronous destination per redo transport semantics. This introduces network latency and standby write latency into the commit path.

If the primary sits far from the standby, round-trip latency can inflate commit times. Standby placement, network paths, bandwidth, and QoS directly affect OLTP user experience.

### 7.2. ASYNC

ASYNC ships redo asynchronously. The primary does not wait for standby acknowledgment per commit, insulating commits from network latency.

If redo generation outpaces transport throughput, transport lag grows. If the primary fails before the backlog ships, unreceived redo can be lost during failover.

### 7.3. AFFIRM

AFFIRM requires the standby to write redo to the standby redo log before acknowledging per transport semantics. It strengthens guarantees that redo is durable on standby storage, while making commits wait on both network and standby I/O.

### 7.4. NOAFFIRM

NOAFFIRM allows acknowledgment before redo is durably persisted to the SRL. This reduces latency, though if the standby host/storage fails immediately after acknowledgment and prior to persistence, protection differs from AFFIRM.

### 7.5. LOG_ARCHIVE_DEST_n Examples

Illustrative synchronous destination configuration:

```sql
ALTER SYSTEM SET LOG_ARCHIVE_DEST_2 =
  'SERVICE=stby_sync
   SYNC AFFIRM
   VALID_FOR=(ONLINE_LOGFILES,PRIMARY_ROLE)
   DB_UNIQUE_NAME=STBY'
  SCOPE=BOTH;
```

Illustrative asynchronous destination:

```sql
ALTER SYSTEM SET LOG_ARCHIVE_DEST_2 =
  'SERVICE=stby_async
   ASYNC NOAFFIRM
   VALID_FOR=(ONLINE_LOGFILES,PRIMARY_ROLE)
   DB_UNIQUE_NAME=STBY'
  SCOPE=BOTH;
```

These are illustrative snippets. Service names, DB_UNIQUE_NAME, NET_TIMEOUT, REOPEN, MAX_FAILURE, compression, encryption, and other attributes must reflect actual design. Do not overwrite destinations managed by Data Guard Broker when Broker controls the configuration.

### 7.6. NET_TIMEOUT

NET_TIMEOUT defines how long to wait for a synchronous redo transport response before triggering timeout handling per Oracle mechanics. Too low a value risks false timeouts on network jitter; too high a value delays fault detection and prolongs commit/session stalls.

Choose timeouts based on high-percentile latency, network SLAs, and failure detection targets; verify release-specific semantics.

### 7.7. Bandwidth and Redo Generation

ASYNC does not eliminate bandwidth requirements. If average or peak redo generation exceeds sustained network throughput, transport backlogs accumulate. SYNC likewise needs ample bandwidth to keep latency low; link saturation inflates commit latency.

Measure redo bytes/sec, network throughput, packet loss, retransmissions, and latency during peak hours.

## 8. Standby Redo Logs (SRL)

### 8.1. Role

Standby redo logs receive redo from the primary before it is archived on the standby. With real-time apply, Redo Apply can read redo as it is written to the SRL, reducing delay relative to waiting for archiving to finish.

### 8.2. SRLs vs. Archived Logs

An SRL is a standby log group dedicated to receiving the redo stream. Once an SRL fills or switches, it is archived into an archived redo log on the standby. SRLs are not backups and do not replace archive log retention.

### 8.3. Sizing and Count

Common configuration guidelines:

- Each redo thread needs enough SRL groups to handle transport and log switches.
- Oracle recommends at least one more SRL group per thread than the corresponding number of online redo log groups.
- SRL size must equal or exceed the largest online redo log for that thread.
- In RAC, create SRLs for every thread requiring standby support, not only the current instance's thread.

Verify exact counts in Oracle Data Guard documentation for your topology and release.

### 8.4. Inspecting SRLs

```sql
SELECT
    thread#,
    group#,
    sequence#,
    bytes,
    archived,
    status
FROM v$standby_log
ORDER BY thread#, group#;
```

Compare against online redo logs on the primary:

```sql
SELECT
    thread#,
    group#,
    sequence#,
    bytes,
    members,
    archived,
    status
FROM v$log
ORDER BY thread#, group#;
```

### 8.5. Real-Time Apply

Real-time apply lets the standby apply redo from SRLs while redo is actively arriving, instead of waiting for archive log completion. Configuration and apply syntax vary across releases; modern releases typically use real-time apply automatically when SRLs exist and conditions apply. Older releases may use USING CURRENT LOGFILE.

Common example to start managed recovery:

```sql
ALTER DATABASE RECOVER MANAGED STANDBY DATABASE
  DISCONNECT FROM SESSION;
```

Do not blindly add or omit USING CURRENT LOGFILE out of habit; check your release and Broker state. In Broker-managed setups, controlling apply via Broker ensures greater consistency.

### 8.6. Inspecting Redo Apply Processes

```sql
SELECT
    name,
    role,
    action,
    thread#,
    sequence#
FROM v$dataguard_process
ORDER BY name;
```

V$DATAGUARD_PROCESS is used on modern releases to view Data Guard processes. Some older releases use V$MANAGED_STANDBY; verify which view is supported on your version.

### 8.7. Missing or Undersized SRLs

Missing SRLs can prevent real-time apply or degrade transport behavior from design intent. SRLs smaller than online redo logs cause issues when receiving larger logs. Inspect each thread and provision appropriate groups during a maintenance window.

## 9. Transport Lag

### 9.1. Definition

Transport lag describes the delay between when redo is generated on the primary and when the corresponding redo is received at the standby. If the primary keeps generating redo while the standby cannot receive fast enough, transport lag rises.

Transport lag commonly stems from:

- Network latency, packet loss, or bandwidth saturation.
- Failing listeners, services, or redo transport connections.
- Standby failing to write redo to SRL/archive destinations.
- Primary redo bursts exceeding transport capacity.
- Unavailable standby destinations or storage.

### 9.2. Transport Lag vs. Archive Gaps

Transport lag is the time/redo delay between primary and standby. An archive gap is one or more missing archived log sequences needed to continue recovery/apply. Gaps can halt apply; transport lag can climb during transport bottlenecks even before an explicit gap is reported.

### 9.3. Inspecting V$DATAGUARD_STATS

On the standby:

```sql
SELECT
    name,
    value,
    unit,
    time_computed,
    datum_time
FROM v$dataguard_stats
WHERE name IN (
    'transport lag',
    'apply lag',
    'apply finish time',
    'estimated startup time'
)
ORDER BY name;
```

VALUE is typically expressed as a time duration. TIME_COMPUTED indicates when the metric was computed; DATUM_TIME relates to the redo timestamp received from the primary. If DATUM_TIME stops advancing across multiple polls, the standby may not be receiving new redo or metric updates may have stalled.

### 9.4. Inspecting Destinations on the Primary

```sql
SELECT
    dest_id,
    status,
    type,
    database_mode,
    recovery_mode,
    protection_mode,
    destination,
    error
FROM v$archive_dest_status
WHERE status <> 'INACTIVE'
ORDER BY dest_id;
```

Cross-check with V$ARCHIVE_DEST to inspect destination attributes and configuration. Columns can differ by release; select columns present in your running version.

### 9.5. Checking Archive Gaps on the Standby

```sql
SELECT
    thread#,
    low_sequence#,
    high_sequence#
FROM v$archive_gap;
```

V$ARCHIVE_GAP generally reports gaps currently blocking recovery. Zero rows does not prove the entire archive history is intact; it only reflects gaps detected by the view at query time.

### 9.6. Reading Lag Over Time

A lag reading of 0 at a single poll does not prove continuous synchronization. Collect timestamped metric series, tracking peaks, degraded durations, and post-burst recovery rates.

### 9.7. Distinguishing Network Delays from Redo Backlogs

If transport lag climbs alongside degraded network throughput/latency, inspect the link and transport processes. If the network is stable while redo generation spikes, recalculate bandwidth and transport capacity. If the primary reports destination errors, check services, authentication, TNS, listeners, and standby storage.

## 10. Apply Lag

### 10.1. Definition

Apply lag describes how far behind received redo is from being applied to standby datafiles relative to the primary timeline. Apply lag can increase even when transport lag is near 0.

### 10.2. Common Causes

- Redo Apply throughput lower than redo generation rate.
- Standby lacking CPU or storage IOPS.
- High datafile write latency.
- SQL Apply/Redo Apply stopped or errored.
- Recovery process bottlenecked by contention or read-only workloads.
- Archive gaps preventing apply from advancing.
- Standby executing reporting queries competing for CPU/I/O.

### 10.3. Both Apply Lag and Transport Lag Rising

If both climb, investigate transport first. Until the standby receives fresh redo, apply cannot catch up. Once transport recovers, apply may still need time to drain the backlog.

### 10.4. Low Transport Lag, High Apply Lag

This usually signals redo has reached the standby, but apply is slow. Check apply processes, CPU, I/O, SRL/archive logs, gaps, and standby workloads. Adding network bandwidth will not resolve the bottleneck if transport is already keeping pace.

### 10.5. Apply Finish Time

V$DATAGUARD_STATS may report `apply finish time`, an estimate of the time required to apply redo already received as of metric computation. This is a dynamic estimate shifting with backlog and throughput, not an SLA guarantee.

### 10.6. Measuring Trends

Track:

- Apply lag over time.
- Redo generation rate on the primary.
- Apply throughput on the standby.
- CPU utilization and I/O latency.
- Archive gaps and recovery process state.
- Read-only/backup workloads running on the standby.

If backlog grows steadily, standby capacity cannot sustain the primary workload.

## 11. Monitoring Lag and Redo Throughput

### 11.1. Periodic Snapshots

Collect V$DATAGUARD_STATS from the standby on a short interval aligned with SLAs, such as every 30–60 seconds. Record collection timestamps in your monitoring system to calculate durations and trends.

### 11.2. Transport Destinations on the Primary

```sql
SELECT
    dest_id,
    status,
    destination,
    error,
    synchronization_status,
    db_unique_name
FROM v$archive_dest_status
WHERE status <> 'INACTIVE'
ORDER BY dest_id;
```

Some synchronization status columns differ by release. If a query fails, run `DESC V$ARCHIVE_DEST_STATUS` and select supported columns. Never ignore ERROR just because STATUS reads VALID.

### 11.3. Redo Generation Rate

Estimate generated redo bytes from system statistics:

```sql
SELECT
    name,
    value
FROM v$sysstat
WHERE name IN (
    'redo size',
    'redo entries',
    'redo writes'
);
```

Take two snapshots separated by a known interval to compute delta redo size/second. Account for instance restarts, counter resets, or clock changes in calculations.

### 11.4. Log Switch Rate

```sql
SELECT
    thread#,
    COUNT(*) AS switches,
    MIN(first_time) AS first_switch,
    MAX(first_time) AS last_switch
FROM v$log_history
WHERE first_time >= SYSDATE - 1/24
GROUP BY thread#
ORDER BY thread#;
```

High log switch rates increase archive file counts and pressure on archivers and standbys. Evaluate redo log sizes, batch workloads, and transaction rates before resizing logs.

### 11.5. Lag History

```sql
SELECT
    name,
    time,
    unit,
    count,
    last_time_updated
FROM v$standby_event_histogram
WHERE name IN ('transport lag', 'apply lag')
ORDER BY name, time;
```

This histogram view may not be populated in all releases/configurations. It helps inspect distributions of recorded lag intervals, without replacing external time-series monitoring.

### 11.6. Data Guard Processes

```sql
SELECT
    name,
    role,
    action,
    thread#,
    sequence#,
    block#,
    blocks
FROM v$dataguard_process
ORDER BY name;
```

Inspect whether processes are active, waiting, or advancing sequences. Process names and actions vary by release; read alongside alert logs and broker status.

### 11.7. Alert Logs and Status Messages

```sql
SELECT
    timestamp,
    severity,
    message
FROM v$dataguard_status
WHERE timestamp > SYSTIMESTAMP - INTERVAL '2' HOUR
ORDER BY timestamp;
```

V$DATAGUARD_STATUS logs Data Guard messages. Combine with alert logs to catch network failures, gaps, stopped apply, or destination errors.

## 12. Setting Thresholds and Lag Alerts

### 12.1. Do Not Use One Threshold for All Databases

A low-RPO OLTP system may require a threshold of seconds; a distant reporting database may tolerate longer lag. Thresholds must derive from RPO, RTO, redo generation, and recovery capability.

### 12.2. Multi-Tier Alerting

Illustrative model:

| Level | Illustrative Condition | Action |
| --- | --- | --- |
| Notice | Slight short-lived lag increase | Track trend |
| Warning | Lag exceeds warning SLA across multiple polls | Inspect transport/apply and capacity |
| Critical | Lag exceeds RPO budget or rises steadily | Escalate to DBA/on-call, evaluate failover exposure |
| Recovery | Lag drops below stable threshold | Confirm backlog cleared |

Actual values must be set by system owners. Use hysteresis to prevent alert flapping when metrics hover near thresholds.

### 12.3. Alerting on Protection Level

Beyond lag, alert whenever PROTECTION_LEVEL drops below business requirements or a synchronous destination loses synchronization. This is critical under Maximum Protection/Availability.

### 12.4. Distinguishing Stale Metrics from Zero Lag

If DATUM_TIME stops advancing, never treat VALUE = 0 as a healthy standby. Alerts should evaluate datum/time_computed age alongside lag values.

### 12.5. Alerting on Backlog Growth

A falling 30-second lag can be less dangerous than a 10-second lag climbing continuously. Track the slope:

- Current lag.
- Peak lag within window.
- Delta lag per minute.
- Continuous duration above threshold.
- Redo generation vs. apply throughput.

## 13. Analyzing Transport Bottlenecks

### 13.1. Network

Check latency, packet loss, retransmissions, bandwidth, routing, firewall timeouts, and network congestion. Under SYNC, round-trip latency directly impacts commits. Under ASYNC, insufficient bandwidth builds backlogs.

### 13.2. Services and Connectivity

Check TNS aliases/services, listeners, authentication, password files, DB_UNIQUE_NAME, and LOG_ARCHIVE_DEST_n. When Data Guard Broker manages the setup, inspect Broker configuration before editing parameters directly.

### 13.3. Standby Storage

Redo transport can slow if SRL storage latency is high or archive destinations fail to write. Inspect I/O latency, ASM disk groups, filesystems, free space, and alert logs.

### 13.4. Redo Generation Spikes

Batch updates, index rebuilds, bulk loads, ETL, or maintenance can spike redo generation. Compare redo bytes/sec against network throughput and archive creation. You may need to adjust batch schedules, add bandwidth, or refine transport architecture.

### 13.5. Transport Processes

Check Data Guard process states, destination errors, and broker warnings. Never kill LNS/ARCn processes to "reset lag"; diagnose the transport root cause first and use supported Data Guard administrative commands.

### 13.6. Far Sync

A Far Sync instance receives redo synchronously near the primary and forwards it asynchronously to remote standbys, reducing WAN latency impact on the primary in certain architectures. Far Sync is not a full standby database with datafiles that can open like a physical standby; it is a redo transport component. Design dedicated availability and protection semantics for it.

## 14. Analyzing Apply Bottlenecks

### 14.1. Redo Apply Processes

Confirm managed recovery is active and error-free. With Broker, inspect apply state and broker logs. In SQL-managed setups, inspect V$DATAGUARD_PROCESS and alert logs.

### 14.2. CPU

Apply can become CPU-bound during high redo rates, heavy block changes, or competing standby workloads. Inspect host CPU, run queues, Oracle process utilization, and apply throughput.

### 14.3. I/O

The standby writes datafile blocks while reading redo/archive logs. High storage latency, queue depth, ASM contention, or busy shared storage can throttle apply.

### 14.4. Standby Read Workloads

If a physical standby is open read-only with Active Data Guard, reporting queries can contend for CPU/I/O with Redo Apply. Monitor resource consumption and consider Resource Manager, workload limits, or rescheduling reports.

### 14.5. Parallel Redo Apply

Some releases support parallel apply and auto-tuning parallelism. Increasing parallelism will not boost throughput if storage/CPU is already saturated or the workload has sequential dependencies. Benchmark before/after and use release-supported parameters/commands.

### 14.6. Gaps and Stopped Apply

If an archived log is missing, apply can stall despite ample CPU/I/O. Check V$ARCHIVE_GAP and Data Guard status before scaling resources.

### 14.7. Apply Rate vs. Redo Rate

Estimating backlog growth:

```text
Redo generated: 80 MB/s
Redo received: 80 MB/s
Redo applied: 55 MB/s

Backlog grows by approximately 25 MB/s
```

This is an arithmetic illustration. If apply throughput stays below redo generation, apply lag grows until workload subsides or capacity increases.

## 15. Archive Gaps and Gap Resolution

### 15.1. What Is a Gap?

A gap is a missing segment of redo in the sequence chain needed for standby apply. Gaps can stem from network outages, premature archive log deletion, destination errors, storage file loss, or missed log backups/transfers.

### 15.2. Detecting Gaps

On the standby:

```sql
SELECT thread#, low_sequence#, high_sequence#
FROM v$archive_gap;
```

On the primary, query V$ARCHIVED_LOG to verify whether corresponding sequences still exist. In RAC, match the exact thread.

### 15.3. Automatic Gap Resolution

Data Guard includes mechanisms to fetch missing archived logs from the primary when properly configured and files remain available. FAL (Fetch Archive Log) and modern transport mechanisms automate gap handling. However, gaps cannot self-resolve if source logs were deleted or destinations are unreachable.

### 15.4. Manual Gap Resolution

If automatic fetching fails:

1. Identify missing DBID/incarnation, thread, and sequences.
2. Locate archive files on the primary, FRA, backups, or another standby copy.
3. Transfer files to a readable location on the standby.
4. Catalog/register logs per release procedure.
5. Restart or resume Redo Apply.
6. Confirm the gap clears and apply lag drops.

Never copy a file sharing the same sequence number from a different incarnation.

### 15.5. When Archived Logs Are Gone

If required redo cannot be recovered, the standby may require incremental roll-forward from the primary or rebuilding/recreating the standby per Data Guard procedures. Choose based on gap size, backup availability, downtime, and release.

### 15.6. Do Not Bypass Gaps Arbitrarily

Never register mismatched archived logs to force recovery forward, reset the standby just to clear errors, or open the standby read/write outside procedures. Remediation must preserve redo consistency.

## 16. Data Guard Broker

### 16.1. Role

Data Guard Broker manages the configuration, database members, redo transport, apply states, switchover/failover, and observer/FSFO when configured. Broker provides a unified management interface rather than editing disparate parameters manually.

### 16.2. Connecting to DGMGRL

```text
dgmgrl /
```

Or connect securely per DBA policy. Never store plaintext credentials in scripts.

### 16.3. Viewing Configuration

```text
SHOW CONFIGURATION;
SHOW CONFIGURATION VERBOSE;
```

Output shows configuration status, protection mode, and overall warnings/errors.

### 16.4. Inspecting Individual Databases

```text
SHOW DATABASE VERBOSE 'PRIMARY_DB';
SHOW DATABASE VERBOSE 'STANDBY_DB';
```

Substitute your actual DB_UNIQUE_NAME. Inspect transport/apply state, lag, properties, and errors.

### 16.5. Validating Configuration

Broker provides `VALIDATE DATABASE` and `VALIDATE NETWORK CONFIGURATION` in supported releases. Use release-appropriate syntax to verify prerequisites, static connect identifiers, redo transport, SRLs, and role-transition readiness.

Successful validation confirms the setup passes Broker checks; it does not replace restore tests, data comparisons, or live failover drills.

### 16.6. Changing Protection Mode via Broker

In Broker-managed environments, change protection mode via DGMGRL using release syntax, e.g.:

```text
EDIT CONFIGURATION SET PROTECTION MODE AS MAXAVAILABILITY;
```

Broker mode names are typically MAXPROTECTION, MAXAVAILABILITY, and MAXPERFORMANCE. Before changing, check synchronous standbys, transport attributes, availability, and restart/state requirements. Never run example commands blindly if prerequisites are unmet.

### 16.7. Broker vs. Direct SQL Parameters

When Broker manages the configuration, editing LOG_ARCHIVE_DEST_n directly can cause Broker state to diverge from operational intent or get overwritten by Broker. Treat Broker as the source of truth for Broker-managed settings; edit SQL parameters directly only per runbook and resync Broker afterward.

## 17. Checking Protection Mode and Database Status

### 17.1. V$DATABASE

On the primary:

```sql
SELECT
    name,
    db_unique_name,
    database_role,
    open_mode,
    protection_mode,
    protection_level,
    switchover_status
FROM v$database;
```

Protection mode reflects configuration target; protection level reflects currently achieved protection. Display both on dashboards.

### 17.2. Archive Destinations

On the primary:

```sql
SELECT
    dest_id,
    status,
    target,
    destination,
    error
FROM v$archive_dest
WHERE status <> 'INACTIVE'
ORDER BY dest_id;
```

Match standby destinations with status/error. A VALID destination does not automatically prove apply is keeping up.

### 17.3. Standby Database Role/Open Mode

On the standby:

```sql
SELECT
    name,
    database_role,
    open_mode,
    protection_mode,
    protection_level,
    switchover_status
FROM v$database;
```

A physical standby may be MOUNTED or READ ONLY WITH APPLY depending on configuration and licensing. Confirm the state aligns with workload and release.

### 17.4. Managed Recovery State

Inspect V$DATAGUARD_PROCESS and Broker. If no apply process exists, determine whether it was intentionally stopped, is restarting, or errored out. Never infer Redo Apply is running from open_mode alone.

## 18. Verifying Redo and Apply Status

### 18.1. Confirming Received Archived Logs

On the standby:

```sql
SELECT
    thread#,
    sequence#,
    first_change#,
    next_change#,
    first_time,
    next_time,
    applied,
    deleted,
    status,
    name
FROM v$archived_log
ORDER BY thread#, sequence#;
```

V$ARCHIVED_LOG can hold multiple records per sequence across destinations/copies. Distinguish received, archived, applied, and deleted copies via metadata.

### 18.2. APPLIED Status

On a physical standby, the APPLIED column in V$ARCHIVED_LOG indicates archived log apply status per metadata. Exact values and semantics follow the release; common values are YES, NO, or IN-MEMORY. IN-MEMORY means redo was applied in memory under real-time apply without necessarily yet being archived/applied in the manner represented by YES.

Do not merely count rows with APPLIED='YES'. Examine thread/sequence, current SRLs, gaps, and apply lag.

### 18.3. Checking Current Apply Sequence

Combine V$DATAGUARD_PROCESS, V$ARCHIVED_LOG, and V$DATAGUARD_STATS to determine the sequence currently being processed and delay. Processes may be applying directly from SRLs before the current sequence appears as a completed archived log.

### 18.4. Confirming Zero Current Gaps

```sql
SELECT * FROM v$archive_gap;
```

Zero rows indicates no recovery-blocking gap reported by the view at query time. Still verify lag, process state, and redo continuity.

### 18.5. Checking Redo Transport Messages

```sql
SELECT
    timestamp,
    severity,
    message
FROM v$dataguard_status
WHERE severity IN ('Error', 'Fatal', 'Warning')
ORDER BY timestamp DESC;
```

If columns or severity strings differ on your release, run `DESC` and filter per the actual schema. Keep alert logs as a complementary diagnostic source.

## 19. Block and Datafile Verification

### 19.1. Physical Consistency

A physical standby maintains blocks via redo apply. To verify files/blocks, DBAs can use RMAN VALIDATE, DBVERIFY, V$DATABASE_BLOCK_CORRUPTION, and datafile header metadata.

### 19.2. RMAN VALIDATE

Examples:

```text
RMAN> VALIDATE DATABASE;
RMAN> VALIDATE CHECK LOGICAL DATABASE;
```

VALIDATE tests readability and detects certain physical block corruptions. CHECK LOGICAL adds logical block integrity checks. These commands can generate heavy I/O; schedule timing and scope carefully.

### 19.3. V$DATABASE_BLOCK_CORRUPTION

```sql
SELECT
    file#,
    block#,
    blocks,
    corruption_type,
    corruption_change#
FROM v$database_block_corruption
ORDER BY file#, block#;
```

This view records block corruptions Oracle has already encountered. Zero rows does not prove all datafiles have been scanned/validated; run appropriate validation jobs.

### 19.4. Datafile Headers

```sql
SELECT
    file#,
    status,
    error,
    recover,
    fuzzy,
    checkpoint_change#,
    checkpoint_time
FROM v$datafile_header
ORDER BY file#;
```

On a lagging standby, checkpoint/SCN values may trail the primary. Do not expect primary and standby header SCNs to match identically while redo is actively shipping/applying; consider apply state and target consistency.

### 19.5. RMAN Validation on the Standby

Validation capability and scope depend on database role, open mode, release, and privileges. Validation can run on the primary, standby, or a suitable clone, provided the command is supported in the current state and I/O is controlled. Avoid running heavy validation during peak workloads if it impacts apply.

### 19.6. Block Repair

Certain Active Data Guard setups support automatic block media recovery: when the standby detects block corruption, it can fetch a healthy block from the primary to repair it. This capability depends on licensing, networking, configuration, and corruption type. Never treat it as a substitute for backups or periodic validation.

## 20. Logical Data Verification

### 20.1. Why Redo Status Checks Alone Are Not Enough

Error-free Redo Apply and low apply lag are strong evidence of physical standby synchronization, yet they do not answer every business question. DBAs may need to verify critical tables, row counts, keys, monetary totals, or business invariants after migrations, upgrades, or role transitions.

### 20.2. Comparing at a Common Data Point

When comparing primary and standby, verify the standby has applied up to the corresponding redo point. If the primary keeps accepting writes while metrics are collected on both sides, results can differ simply due to skewed snapshot timing.

Ways to control timing:

- Pause/freeze writes during a maintenance window if business permits.
- Pick a common SCN/restore point and query both sides as of that snapshot if objects/undo retention support it.
- Wait for the standby to apply up to a recorded SCN before comparing.
- Use DBMS_COMPARISON or a reconciliation workflow with suitable locking/partitioning.

Never run two queries at different times and conclude Data Guard is broken.

### 20.3. Row Counts and Aggregates

Checks like COUNT(*), MIN/MAX keys, SUM(amount), and per-partition counts help catch gross discrepancies:

```sql
SELECT
    COUNT(*) AS row_count,
    MIN(order_id) AS min_order_id,
    MAX(order_id) AS max_order_id,
    SUM(total_amount) AS total_amount
FROM orders;
```

Run at the identical snapshot/SCN on primary and standby. Aggregate figures do not prove row-by-row equality; two differing datasets can yield identical counts or sums.

### 20.4. Hashes/Checksums

Hashes can be computed by key/partition to cut data transfer during reconciliation. Hash designs must:

- Include every business-relevant column.
- Standardize NULLs, data types, time zones, collations, and numeric formatting.
- Enforce deterministic column ordering.
- Chunk by key/partition to isolate mismatches.
- Provide collision handling and row-level verification whenever hashes differ.

Hashes are not absolute proof against collisions. Never rely on hashes alone as the sole criterion for high-value data.

### 20.5. DBMS_COMPARISON

DBMS_COMPARISON compares data between two database objects, typically over a database link with comparison metadata. It identifies differing rows by key/column and persists scan results.

General workflow:

1. Select a table/object with a stable unique key.
2. Create a secure database link to the target database.
3. Create a comparison definition in an appropriate utility schema.
4. Execute COMPARE with a suitable scan mode.
5. Inspect scan status and row differences.
6. Investigate mismatches; use CONVERGE only with explicit decisions on the authoritative source and write permissions.

### 20.6. DBMS_COMPARISON on a Physical Standby

A physical standby is normally read-only or read-only with apply. Comparison packages may need to write scan metadata to a local schema, so do not assume the entire workflow can execute directly on a read-only standby. Run from an appropriate utility/primary database using a database link to the standby in line with privileges and release rules.

### 20.7. Logical Standby

A logical standby relies on SQL Apply and carries restrictions across certain data types, DDLs, and features. Logical verification must account for objects unsupported by SQL Apply, skip rules, and SQL Apply errors. Do not assume physical block-for-block consistency for a logical standby.

## 21. Data Guard Broker and Role Transition Validation

### 21.1. VALIDATE DATABASE

Broker can validate database readiness for switchover/failover, transport/apply settings, and prerequisites. Run `VALIDATE DATABASE` with the database name per release syntax, and read all warnings rather than stopping at a SUCCESS line.

### 21.2. VALIDATE NETWORK CONFIGURATION

Supported releases include a network configuration validation command to test connect identifiers/communication among members. This is a Broker-level reachability check; it does not replace continuous latency, bandwidth, or packet loss monitoring.

### 21.3. Switchover Readiness

Before switchover, verify:

- Standby has applied to the required point.
- Zero archive gaps exist.
- Transport/apply states are healthy.
- Broker configuration status is SUCCESS.
- Switchover status permits role transition.
- Services/client routing and target capacity are ready.

### 21.4. Failover Readiness

Failover can cause data loss under Maximum Performance or degraded Maximum Availability. Before deciding, assess whether the primary can recover, how much redo the standby received, whether trailing redo can be retrieved from the primary, and what data loss the business accepts.

### 21.5. Fast-Start Failover

Fast-Start Failover (FSFO) automates failover via Broker/Observer conditions when configured and prerequisites are met. The Observer requires proper network paths and placement. FSFO does not eliminate the need to monitor lag, protection level, data-loss exposure, and application reconnection testing.

### 21.6. After Role Transition

After switchover/failover:

- Confirm database_role and protection_mode/level.
- Verify redo transport destinations switched to match the new roles.
- Check apply/transport processes and lag.
- Verify service registration and client connections.
- Confirm backups, archive retention, and FRA.
- Verify business data at the target.
- Reconfigure/reinstate the former primary per runbook.

## 22. Symptom-Based Diagnostic Workflows

### 22.1. Both Transport Lag and Apply Lag Rising

1. Check V$ARCHIVE_DEST_STATUS and destination ERROR on the primary.
2. Check network latency, bandwidth, packet loss, and listeners/services.
3. Check for redo generation spikes.
4. Check standby SRL/storage and archive destinations.
5. Restore transport first, then monitor apply catching up.

### 22.2. Low Transport Lag, Rising Apply Lag

1. Confirm Redo Apply processes are running.
2. Check V$ARCHIVE_GAP.
3. Check CPU, I/O latency, and standby workloads.
4. Check apply throughput and backlog.
5. Adjust resources/workloads or apply configuration based on evidence.

### 22.3. Protection Level Lower Than Mode

1. Check synchronous destinations and synchronization status.
2. Check network/standby errors.
3. Verify actual configured mode and transport attributes.
4. Restore standby synchronization per runbook.
5. Confirm protection level returns to the required state.

### 22.4. Archive Gap

1. Query V$ARCHIVE_GAP.
2. Identify missing thread/sequence/incarnation.
3. Locate archived logs on primary, FRA, backups, or other standbys.
4. Restore/copy/catalog per procedure.
5. Resume apply and verify the gap clears.

### 22.5. Standby Not Receiving Redo

Check destination errors, services, listeners, TNS, password files, DB_UNIQUE_NAME, LOG_ARCHIVE_DEST_STATE_n, network routes, and alert logs at both sites. If using Broker, check Broker status and logs before altering configuration.

### 22.6. Apply Process Not Running

Check Broker apply state, V$DATAGUARD_PROCESS, alert logs, and recovery errors. Restart apply using Broker or SQL matching your management method. Never run two conflicting management mechanisms concurrently.

### 22.7. Logical Data Mismatch


## 23. Operational Monitoring Matrix

### 23.1. What to Collect

| Category | Source | Questions to Answer |
| --- | --- | --- |
| Protection | V$DATABASE, Broker | What are the configured mode and current protection level? |
| Transport | V$ARCHIVE_DEST_STATUS, alert log | Is the primary shipping redo and are destinations error-free? |
| Transport lag | V$DATAGUARD_STATS | Has the latest redo reached the standby? |
| Apply | V$DATAGUARD_PROCESS, Broker | Is Redo Apply running? |
| Apply lag | V$DATAGUARD_STATS | Is received redo being applied promptly? |
| Gaps | V$ARCHIVE_GAP, V$ARCHIVED_LOG | Are any sequences/threads missing? |
| SRL | V$STANDBY_LOG | Does the standby have enough redo log groups and sizes? |
| Integrity | RMAN, V$DATABASE_BLOCK_CORRUPTION | Has any block corruption been detected? |
| Logical data | DBMS_COMPARISON, business checks | Do critical tables match at the same snapshot? |
| Capacity | OS, storage, FRA | Do network, CPU, I/O, and archive storage retain headroom? |

### 23.2. Polling Frequency

Lag and process states generally require more frequent polling than integrity scans. Example:

- Lag/protection status: every 30–60 seconds depending on SLA.
- Destination errors/process state: every 1–5 minutes plus event-driven alerts if available.
- FRA/storage capacity: every few minutes.
- Block validation: scheduled within maintenance/backup windows.
- Logical comparison: on business schedules, post-migration, or post-role-transition.

These are starting suggestions. Reduce polling if monitoring queries cause noticeable load; increase granularity during incidents.

### 23.3. Timestamp Correlation

Synchronize clocks across primary, standby, observer, monitoring, and OS layers. Clock skew distorts transport/apply lag readings and incident timelines. Store both source timestamps and collection timestamps.

### 23.4. Minimum Dashboard

A Data Guard dashboard should display:

- Primary/standby roles and open modes.
- Protection mode/level.
- Current and peak transport/apply lag.
- Destination status/errors.
- Apply process state.
- Archive gaps.
- Redo generation rate and apply throughput.
- FRA/storage utilization.
- Last successful backup/validation.
- Last switchover/failover drill.

### 23.5. Actionable Alerts

Useful alerts specify database, site, destination, thread/sequence if applicable, lag duration, trend, protection level, and runbook link. Avoid generic messages like "Data Guard lag high" without context.

## 24. Designing Layered Data Verification

### 24.1. Layer 1 — Configuration Validation

Verify protection mode, transport attributes, destinations, SRLs, Broker configuration, and role-transition prerequisites. This layer answers whether configuration matches design.

### 24.2. Layer 2 — Operational State Validation

Verify destinations are active, redo is arriving, apply processes run, lag meets SLA, and zero gaps exist. This layer answers whether the redo pipeline is operating.

### 24.3. Layer 3 — Physical Integrity

Use RMAN VALIDATE, CHECK LOGICAL, block corruption views, and backup validation to detect read/block errors. This layer answers whether blocks/files show corruption.

### 24.4. Layer 4 — Logical Data Comparison

Compare rows/keys/columns or business aggregates at the same SCN/snapshot. This layer answers whether business data matches across both databases.

### 24.5. Layer 5 — Application Validation

Execute health checks, post-transition read/write tests, transaction ID reconciliation, and verify application services/connection pools work. This layer answers whether users can actually use the service.

### 24.6. Do Not Substitute One Layer for Another

Broker status SUCCESS does not prove datafiles are free of corruption. RMAN VALIDATE does not prove business rows are logically accurate. Matching row counts do not prove individual rows match. Choose verification layers aligned with goals and risks.

## 25. Data Comparison and Business Reconciliation

### 25.1. Selecting Critical Tables

Prioritize tables with high business value or used to prove consistency:

- Ledgers/transaction journals.
- Orders/payments.
- Customer/account masters.
- Inventory/balances.
- Critical mapping and reference tables.

Not every table needs the same comparison frequency; classify by RPO, criticality, and cost.

### 25.2. Choosing Keys

Each comparison should use a stable primary key or unique key. Without a unique key, define a composite key or partitioned comparison strategy. Never use ROWID as a cross-database identifier for migrated or rebuilt data.

### 25.3. Snapshot Consistency

For accurate comparison, both sides must reflect the same logical state. Pause writes, select a common SCN using consistent read/Flashback if objects and undo retention allow, or wait for the standby to apply up to a recorded point.

Never compare an actively written primary against a lagging standby and conclude Data Guard is inaccurate.

### 25.4. DBMS_COMPARISON

DBMS_COMPARISON creates comparison definitions and scans objects across local and remote databases via a database link. The package stores scan results, row differences, and comparison status in corresponding data dictionary views.

General steps:

1. Confirm object data types, collations, and keys are supported.
2. Create a least-privilege database link to the peer database.
3. Create a comparison via `DBMS_COMPARISON.CREATE_COMPARISON` with appropriate schema/object/key.
4. Run `DBMS_COMPARISON.COMPARE` with an appropriate scan mode.
5. Query `DBA_COMPARISON`, `DBA_COMPARISON_SCAN`, and `DBA_COMPARISON_ROW_DIF`.
6. Verify every difference with business owners.

### 25.5. COMPARE Is Not CONVERGE

COMPARE detects and logs differences. CONVERGE modifies data on one side per specified rules. For a standby managed by Redo Apply, never run CONVERGE to write directly to a physical standby. Converge only between writable databases and only after establishing the authoritative source, transaction window, and rollback plan.

### 25.6. Partitioned Checksums

For very large tables, slicing by date/partition/key range and computing row counts and hashes per chunk helps isolate mismatches. When a chunk differs, perform row-level comparison within that chunk. Normalize NULLs, decimals, timestamps/time zones, character encodings, and column order.

### 25.7. Business Reconciliation

Checks can verify business invariants such as:

- Balanced total debits and credits per ledger.
- Order/payment counts by status.
- Balance totals by account/branch.
- Absence of logical orphan foreign keys.
- Transaction counts per batch ID matching upstream sources.

These checks complement physical integrity; they do not prove the entire database is identical.

## 26. Failover Drills and Protection Testing

### 26.1. Drill Objectives

Drills must prove both database and applications recover within RPO/RTO:

- Standby receives/applies redo.
- Broker/Observer detects the incident.
- Role transition completes.
- Services move to the new primary.
- Clients reconnect and resolve transaction outcomes cleanly.
- Backups/redo transport are re-established post-transition.

### 26.2. Periodic Switchover Testing

Controlled switchover tests readiness without simulating primary loss. Plan ahead, drain workloads, verify lag/gaps, run Broker validation, and execute switchover per runbook. Time each step.

### 26.3. Failover Testing in Appropriate Environments

Failover can lose data depending on protection mode and transport state. Test in non-production environments or during approved disaster recovery exercises. Never sever a production primary for a "quick test."

### 26.4. Measuring RPO

Record the last transaction ID/SCN committed on the primary prior to failure and the last transaction present on the standby after failover. Reconcile business records to measure real data loss. Reading dashboard transport lag alone does not prove RPO.

### 26.5. Measuring RTO

Measure from incident onset until the application successfully serves requests, not just until the database reports OPEN. Include detection, decision, role transition, service relocation, pool reconnection, cache warm-up, and application validation.

### 26.6. Post-Drill Actions

Document issues involving DNS, services, firewalls, wallets, broker, lag, backups, and application retries. Update runbooks, monitoring, and capacity plans; repeat drills after major architectural changes.

## 27. Common Errors and Remediation

| Symptom | Possible Cause | Investigation Direction |
| --- | --- | --- |
| Protection level lower than protection mode | Synchronous destination no longer synchronized | Check V$DATABASE, destination status, network, and standby |
| Transport lag rising | Network, service, destination, or redo rate | Check destination ERROR, network throughput, and redo generation |
| Apply lag rising, transport lag low | Low apply throughput or gap | Check V$DATAGUARD_PROCESS, V$ARCHIVE_GAP, CPU/I/O |
| Apply process stopped | Broker/apply state, recovery error, or admin action | Read alert log, Broker status, and process state |
| Archive gap | Missing archived log sequence/thread | Locate files on primary, backups, FRA, or another standby |
| ORA-16047 | DB_UNIQUE_NAME mismatch in destination | Check destination attributes and DB_UNIQUE_NAME |
| ORA-16055 | FAL request or archive gap fetch rejected | Check primary availability, FAL/transport config, and alert log |
| ORA-16766 | Redo Apply not running per Broker | Check apply state, recovery errors, and Broker logs |
| ORA-16778 | Redo transport error per Broker | Check destination status, network, and authentication |
| ORA-16853 | Apply lag exceeds Broker threshold | Check apply throughput and lag trends |
| ORA-16855 | Transport lag exceeds Broker threshold | Check network/transport and redo rate |
| Standby lags after batch | Redo generation spike | Compare redo bytes/sec against transport/apply throughput |
| Standby cannot real-time apply | Missing/mis-sized SRLs or apply config | Check V$STANDBY_LOG and recovery state |
| Data comparison mismatch | Skewed snapshot or object differences | Verify SCN, keys, SQL Apply rules, and row-level comparison |
| Block corruption | Storage/block corruption or latent issue | Check RMAN validate, V$DATABASE_BLOCK_CORRUPTION, and repair plan |

### 27.1. ORA-16853 and ORA-16855

These Broker warnings indicate lag exceeded configured thresholds. They do not by themselves identify whether the fault is network or apply. Inspect transport/apply lag separately, process states, and workload metrics to isolate the bottleneck.

### 27.2. Destination Errors

Read the full ERROR text in V$ARCHIVE_DEST/V$ARCHIVE_DEST_STATUS. Verify listeners/services, TNS, password files, DB_UNIQUE_NAME, LOG_ARCHIVE_DEST_STATE_n, network ACLs/firewalls, and remote destination storage.

### 27.3. Broker Configuration Warnings

SHOW CONFIGURATION can report WARNING when lag crosses thresholds or a database is in an unexpected state. Use SHOW DATABASE VERBOSE and VALIDATE DATABASE to pinpoint the exact property or error. Never disable Broker solely to clear warnings.

### 27.4. Apply Stopped After Error

Inspect the alert log for the first sequence, datafile, block, or ORA error. Fix the underlying cause, ensure required archived logs are available, and resume apply via Broker or SQL per your management method. Never launch multiple parallel managed recovery sessions.

### 27.5. Data Mismatch

First confirm both sides share the exact same snapshot. Then distinguish:

- Unapplied redo: wait or resolve lag/gaps.
- Object unsupported/skipped by SQL Apply: inspect logical standby rules.
- Logical/block corruption: run validation and investigate storage.
- Replicated application data error: resolve via business remediation or restore point, rather than expecting Data Guard to fix it automatically.

## 28. Daily Data Guard Health Check Runbook

### 28.1. Verify Role and Protection

```sql
SELECT
    name,
    db_unique_name,
    database_role,
    open_mode,
    protection_mode,
    protection_level
FROM v$database;
```

Compare protection level against service RPO requirements.

### 28.2. Check Transport

On the primary, check destination status/errors and confirm standby destinations are VALID/synchronized as configured. Inspect alert logs and redo generation rates.

### 28.3. Check Lag

On the standby:

```sql
SELECT name, value, unit, time_computed, datum_time
FROM v$dataguard_stats
WHERE name IN ('transport lag', 'apply lag', 'apply finish time');
```

Inspect values, metric age, and trends across multiple polls.

### 28.4. Check Apply/Gaps

```sql
SELECT name, role, action, thread#, sequence#
FROM v$dataguard_process
ORDER BY name;

SELECT thread#, low_sequence#, high_sequence#
FROM v$archive_gap;
```

If apply stops or a gap appears, open an incident and follow the gap runbook.

### 28.5. Check SRLs and Capacity

Confirm sufficient SRLs per thread, remaining headroom in archive destinations/FRA, and error-free standby storage. Inspect CPU/I/O if apply lag rises.

### 28.6. Check Broker

If using Broker, run SHOW CONFIGURATION and SHOW DATABASE VERBOSE for each member. Address warnings at their root cause rather than merely clearing status.

### 28.7. Record Findings

Log timestamps, roles, protection levels, transport/apply lag, destination states, sequence/thread numbers, gaps, FRA usage, backup/validation status, and incident tickets. Use time-series data to compare daily and weekly peaks.

## 29. Lab: Observing Protection Modes and Lag

Execute only in authorized Data Guard lab/test environments. Never alter protection modes or sever production networks for testing.

### 29.1. Verify the Primary

On the primary:

```sql
SELECT
    database_role,
    protection_mode,
    protection_level,
    switchover_status
FROM v$database;

SELECT
    dest_id,
    status,
    destination,
    error
FROM v$archive_dest
WHERE status <> 'INACTIVE';
```

### 29.2. Verify the Standby

On the standby:

```sql
SELECT
    database_role,
    open_mode,
    protection_mode,
    protection_level
FROM v$database;

SELECT name, value, unit, time_computed, datum_time
FROM v$dataguard_stats;
```

### 29.3. Generate Controlled Redo

In a lab schema, run a small DML batch and commit. Observe transport lag and apply lag across multiple polls. Do not generate massive workloads purely to force lag.

### 29.4. Observe Real-Time Apply

Inspect SRL status and V$DATAGUARD_PROCESS while redo is shipping. Observe sequence/block progression and archived logs after log switches.

### 29.5. Compare Lag

Maintain an external time-series table or log timestamped outputs:

| Timestamp | Transport Lag | Apply Lag | Destination | Apply State |
| --- | --- | --- | --- | --- |
| T0 | | | | |
| T1 | | | | |
| T2 | | | | |

Determine whether transport keeps up with redo generation and whether apply clears backlogs.

### 29.6. Transport Interruption Test

Only in a lab with a recovery plan, simulate a brief network/destination interruption per infrastructure guidance. Observe destination errors, transport lag, protection level, Broker warnings, and resynchronization after network recovery.

Never deliberately sever a Maximum Protection synchronous standby on a shared system; the primary may shut down by design.

## 30. Lab: Verifying Primary/Standby Data

### 30.1. Choose a Test Table

Create a lab table with a primary key, numeric/date/character columns, and a small dataset. Do not use production tables or sensitive data.

### 30.2. Generate Data and Record SCN

On the primary, commit a batch with a clear request ID. Record the post-commit SCN/time using appropriate DBA tools and wait for the standby to apply past that point.

### 30.3. Compare Aggregates

Run the same query on primary and standby once the standby has applied up to the target point:

```sql
SELECT
    COUNT(*) AS row_count,
    MIN(id) AS min_id,
    MAX(id) AS max_id,
    SUM(amount) AS total_amount
FROM dg_lab_orders;
```

Compare results. This is a preliminary check, not proof of row-level equality.

### 30.4. Row-Level Comparison

Use DBMS_COMPARISON in a suitable environment with a database link and scan definition. Compare by primary key, inspect row differences, and verify causes. Never run CONVERGE on a physical standby.

### 30.5. Block Check

During a maintenance window, run RMAN VALIDATE appropriate for your release and database state. Check V$DATABASE_BLOCK_CORRUPTION before and after. Save output and I/O duration.

### 30.6. Record Evidence

Save SCN/snapshot, role, lag, query outputs, comparison scan results, corruption view output, and RMAN validation output. Evidence must document the exact common state at which data was compared.

## 31. Best Practices

1. **Choose protection mode per RPO/RTO.** Do not select solely on commit speed or a short benchmark.
2. **Distinguish protection mode from transport attributes.** Mode sets the target; SYNC/ASYNC/AFFIRM/NOAFFIRM govern transport behavior.
3. **Monitor protection level.** Configured mode can differ from actual achieved protection.
4. **Understand SYNC commit latency.** Network round-trips and standby I/O sit in the commit path.
5. **Quantify ASYNC data-loss exposure.** Transport lag and failure scenarios determine potential redo loss.
6. **Configure SRLs per thread.** RAC requires provisioning for all redo threads and matching log sizes.
7. **Use real-time apply when appropriate.** Verify SRLs and release behavior.
8. **Measure transport and apply separately.** These two lags have distinct causes and remedies.
9. **Track DATUM_TIME.** Stale metrics do not mean zero lag.
10. **Check for gaps.** Zero current gaps do not prove complete archive history integrity.
11. **Maintain proper archive retention.** Never purge logs ahead of backup/apply needs.
12. **Treat Broker as the source of truth when Broker manages.** Avoid direct configuration edits that cause state drift.
13. **Verify across multiple layers.** Configuration, operational state, physical integrity, logical data, and application.
14. **Compare at the same snapshot.** Lagging standbys or ongoing writes legitimately produce differing results across staggered queries.
15. **Do not treat row counts/hashes as absolute proof.** Use row-level comparison for critical data.
16. **Data Guard does not replace backups.** Maintain independent backups and immutable/offsite copies.
17. **Rehearse switchover/failover.** Measure RPO/RTO at the application level.
18. **Build alerts with trends and runbooks.** Distinguish rising lag, stale metrics, and recovering lag.
19. **Do not force failover merely due to high lag.** Assess primary, standby, trailing redo, and data-loss exposure.
20. **Document operational evidence.** Timestamp, SCN, sequence/thread, role, protection level, and validation results.

## 32. Self-Check Questions

1. How does protection mode differ from redo transport mode?
2. How does Maximum Protection react when no synchronous standby remains?
3. How does Maximum Availability keep the primary running when a standby temporarily disconnects?
4. Which redo can be lost during failover under Maximum Performance?
5. How do SYNC and ASYNC affect commit latency?
6. How do AFFIRM and NOAFFIRM differ in acknowledgment timing?
7. How do PROTECTION_MODE and PROTECTION_LEVEL differ?
8. Which components influence RPO and RTO?
9. What does transport lag measure?
10. What does apply lag measure?
11. Can you have low transport lag alongside high apply lag? Why?
12. Why is DATUM_TIME important?
13. What does V$ARCHIVE_GAP show, and what are its limitations?
14. How does an SRL differ from an archived redo log?
15. Why does RAC require SRLs per thread?
16. How does real-time apply use SRLs?
17. When should V$DATAGUARD_PROCESS be used instead of V$MANAGED_STANDBY?
18. How does Broker help manage Data Guard?
19. Does VALIDATE DATABASE prove business data matches?
20. What does RMAN VALIDATE CHECK LOGICAL verify?
21. Why do identical row counts not prove two tables are identical?
22. How does DBMS_COMPARISON assist with reconciliation?
23. Why should CONVERGE never be run directly on a physical standby?
24. How do you ensure both sides are compared at the same snapshot?
25. Why does Data Guard not replace backups?
26. When both transport lag and apply lag rise, in what order should you investigate?
27. When transport lag is low while apply lag is high, what should you check?
28. Which application components must be verified after failover?
29. How do you measure actual RPO during a failover drill?
30. How do you measure RTO at the service level?

## 33. Memory Model

```text
BUSINESS REQUIREMENTS
       |
       +-- RPO: how much data loss is acceptable?
       +-- RTO: how fast must service recover?
       |
       v
PROTECTION MODE
       |
       +-- MAXIMUM PROTECTION
       |      SYNC/AFFIRM, primary halts if protection is lost
       |
       +-- MAXIMUM AVAILABILITY
       |      SYNC when standby is healthy, primary continues when standby drops
       |
       +-- MAXIMUM PERFORMANCE
              ASYNC, primary prioritizes performance
       |
       v
REDO TRANSPORT
       |
       +-- SYNC / ASYNC
       +-- AFFIRM / NOAFFIRM
       +-- Network / SRL / Bandwidth
       |
       v
STANDBY
       |
       +-- Transport lag: unreceived redo
       +-- Apply lag: received redo, not yet applied
       +-- Archive gap: missing sequence/thread
       +-- Real-time apply from SRL
       |
       v
DATA VALIDATION
       |
       +-- Configuration / Broker validation
       +-- Redo process / gaps / lag
       +-- RMAN / block corruption
       +-- DBMS_COMPARISON / business reconciliation
       +-- Application health
       |
       v
FAILOVER DRILL
       |
       +-- Measure RPO
       +-- Measure RTO
       +-- Verify service/client reconnect
       +-- Update runbook
```

**Key Takeaway:** Protection mode defines data-protection guarantees and primary behavior; SYNC/ASYNC alongside AFFIRM/NOAFFIRM govern how redo is shipped and acknowledged. Transport lag indicates redo has not reached the standby, while apply lag indicates received redo is not yet applied. Data Guard verification requires multiple layers: configuration, redo state, block integrity, logical data comparison, and application failover drills.
