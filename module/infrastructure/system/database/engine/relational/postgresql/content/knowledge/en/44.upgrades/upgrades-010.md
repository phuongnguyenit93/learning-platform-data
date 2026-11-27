# Rehearsing, Measuring Downtime, and Preparing a PostgreSQL Rollback Plan

A PostgreSQL upgrade plan is trustworthy only after it has been rehearsed on a production-like environment, timed step-by-step, and backed by a rollback plan executable within committed time limits.

**Downtime** is the period during which the service cannot serve business operations at an acceptable level. This window can start when applications stop accepting writes, when the database stops, or when traffic is drained from the old cluster; and it ends only when the new database is verified, applications reconnect cleanly, and critical transactions run normally.

**Rollback** is the plan to restore service to an acceptable state if the upgrade fails. Rollback is never as simple as pointing a connection string back to the old cluster. If the new cluster has accepted writes, the old cluster lacks those changes. If hard-link mode was used, the old cluster is not even an independent dataset once the new cluster starts.

The lesson **“Rehearsing, Measuring Downtime, and Preparing a Rollback Plan”**, part of the **Upgrades** chapter of the **Database Engine Relational PostgreSQL** module, covers defining RTO/RPO, structuring rehearsals, timing each phase, selecting a transfer mode, preparing backups/restores, establishing GO/NO-GO gates, handling data divergence, and writing runbooks for both the success path and the failure path.

> **Principle:** there is no reliable rollback unless you have defined which dataset is authoritative, the exact point at which the old cluster loses fallback viability, and how applications recover in each scenario. Rehearse both the success path and the failure path.

---

## 1. Why Rehearse Before Upgrading?

A successful run in a development environment does not prove a production upgrade will finish within its maintenance window.

Production typically features larger databases, multiple tablespaces, concurrent workloads, connection pools, extensions, replication, backups, monitoring, scheduled jobs, and external consumers. Storage throughput can also differ sharply from test environments.

Rehearsals expose missed steps, capture real timings, identify dependencies, and validate rollback before production pressure hits.

## 2. Defining RTO and RPO Targets

Two targets must be agreed upon before designing the plan.

- **RTO (Recovery Time Objective):** maximum acceptable time for the service to resume operating after an incident.
- **RPO (Recovery Point Objective):** maximum acceptable data loss, usually expressed as time or data position.

| Target | Illustrative Value | Meaning |
|---|---:|---|
| RTO | 60 minutes | Service must resume within at most 60 minutes |
| RPO | 0 minutes | Zero loss of committed transactions allowed |
| Maintenance window | 90 minutes | Scheduled allowable disruption window |

RTO and the maintenance window are not necessarily identical. A maintenance window may include buffers, checks, and communications. RTO can also govern unplanned failures.

RPO=0 is meaningful only when backups, replication, and failover procedures genuinely protect committed transactions as required. A backup taken before the upgrade does not contain writes committed afterward.

## 3. Defining Downtime Precisely

Do not use a vague milestone like “the database started” to declare downtime over.

Define explicit milestones:

1. **Write freeze:** applications stop sending writes.
2. **Traffic drain:** in-flight requests and transactions finish or are handled.
3. **Old cluster stop:** old PostgreSQL shuts down cleanly.
4. **Upgrade start:** actual upgrade begins.
5. **Upgrade complete:** `pg_upgrade` finishes successfully.
6. **New cluster ready:** new cluster starts and passes health checks.
7. **Validation complete:** schemas, extensions, roles, and data checks pass.
8. **Application ready:** applications connect, and smoke tests plus representative transactions pass.
9. **Traffic restored:** traffic reopens per plan.

The business must agree on which milestones bound downtime. Multiple metrics may apply: write unavailability, read unavailability, and full application outage.

## 4. Distinguishing Write Downtime from Full Downtime

Some systems can serve read-only traffic during part of the maintenance window, provided that mode is designed and tested.

Example:

- Write freeze starts at 01:00.
- Read-only service continues until 01:10.
- Database stops at 01:10.
- New database is ready at 01:45.
- Application validation finishes at 02:00.
- Full traffic reopens at 02:05.

When reporting, state write downtime, full database/application outage, and validation/reconnect time separately. Never report downtime as merely `pg_upgrade` execution duration.

## 5. Defining Rehearsal Scope

A worthwhile rehearsal simulates the factors that directly govern duration and outcome:

- Exact source and target PostgreSQL major versions.
- Data size and relation distribution.
- Number of databases, schemas, tables, and indexes.
- Tablespaces and filesystem mounts.
- Extensions and external dependencies.
- Memory, WAL, replication, and authentication configuration.
- Storage class, throughput, and IOPS.
- CPU, RAM, and memory limits.
- Applications, connection pools, and background workers.
- Backup/restore and monitoring tools.

If copying full production data is infeasible, build a dataset closely matching scale and access patterns. Document differences to adjust projections.

## 6. Production-Like Environment

The rehearsal should run on infrastructure equivalent to production in aspects that directly affect the upgrade.

| Component | Requirement |
|---|---|
| PostgreSQL versions | Exact source and target |
| OS and architecture | Compatible with production |
| Filesystem | Same type and required features |
| Storage | Production-like throughput and latency |
| Data size | Near production or calibrated extrapolation model |
| Extensions | Same packages and versions |
| Configuration | Same relevant settings |
| Application | Same drivers and migration behavior |
| HA/backup | Same workflow or faithful simulation |

A tiny VM works for validating command syntax, but cannot predict how long copying terabytes will take.

## 7. Pre-Rehearsal Inventory

Capture old-cluster details:

~~~sql
SELECT version();

SELECT
    datname,
    pg_size_pretty(pg_database_size(datname)) AS database_size
FROM pg_database
ORDER BY pg_database_size(datname) DESC;

SELECT
    spcname,
    pg_tablespace_location(oid) AS location
FROM pg_tablespace;

SELECT
    extname,
    extversion
FROM pg_extension
ORDER BY extname;
~~~

Also document roles and memberships, database owners/grants, replication slots/subscriptions, publications, foreign servers/wrappers, large objects, collations, `shared_preload_libraries`, SSL files, archive commands, scheduled jobs, ETL, and application endpoints.

The inventory becomes the baseline for post-upgrade comparison.

## 8. Choosing the Upgrade Method Before Measuring

If using `pg_upgrade`, pick the transfer mode before rehearsing because each mode has distinct duration, disk requirements, and rollback semantics.

| Mode | Mechanism | Impact |
|---|---|---|
| Copy | Creates independent data files | Measures full data copy and disk throughput |
| Link | Hard links sharing inodes | Very fast; old cluster loses independence once new starts |
| Clone | Reflink/copy-on-write | Fast if filesystem supports it; measures COW growth |
| Copy-file-range | Kernel-assisted copy | Independent files; depends on kernel/filesystem |

Never measure copy mode and use that timing to predict link or clone. Conversely, never use link-mode timings to commit to a copy-mode window.

## 9. Pre-Rehearsal Compatibility Check

Run `pg_upgrade --check` on the rehearsal copy:

~~~bash
/path/to/new/bin/pg_upgrade \
  -b /path/to/old/bin \
  -B /path/to/new/bin \
  -d /path/to/old/data \
  -D /path/to/new/data \
  --check
~~~

Save output and logs. Resolve unsupported source versions, extensions missing binaries/update paths, prepared transactions, invalid indexes, tablespace paths, locale/collation differences, data checksums, disk capacity, and objects needing manual intervention.

Passing `--check` is not an actual upgrade timing measurement. It verifies only the conditions checkable by that pre-check step.

## 10. Backup and Restore Rehearsal

Before measuring the upgrade, prove you can recover the cluster.

A backup plan may include:

- Base backup.
- WAL archive.
- Configuration and certificate backups.
- Extension package inventory.
- Storage snapshots where consistency is guaranteed.
- External secrets stored per security policy.

The restore rehearsal must verify the backup is readable, WAL archives are contiguous, the restore targets the right version/path, PostgreSQL starts, databases/roles exist, test applications connect, and actual restore duration is measured.

An untested backup is not a proven rollback plan.

## 11. Timing Backups Separately

Record start/end timestamps, source size, backup size, WAL replay volume, throughput, CPU/storage utilization, backup verification time, and restore duration separately.

Do not count an online backup inside downtime if executed before maintenance. However, include backup/restore duration in recovery time if rollback requires restoring from backup.

## 12. Breaking Down the Maintenance Window

| Phase | Contents |
|---|---|
| A. Preflight | Check backups, binaries, disk, extensions |
| B. Freeze | Stop writes and scheduled jobs |
| C. Drain | Finish transactions, close connections |
| D. Shutdown | Cleanly stop old PostgreSQL |
| E. Upgrade | Run `pg_upgrade` |
| F. Startup | Start new cluster |
| G. Post-upgrade | Analyze, extension updates, config |
| H. Validation | Check DB and application |
| I. Cutover | Open traffic and monitor |

Preflight checks, package installation, and backups can happen ahead of downtime. Only steps genuinely requiring a stopped cluster belong inside the outage window.

## 13. Identifying the Critical Path

Certain steps are strictly sequential:

~~~text
Freeze writes
     |
     v
Drain sessions
     |
     v
Stop old cluster
     |
     v
pg_upgrade
     |
     v
Start new cluster
     |
     v
Post-upgrade validation
     |
     v
Application smoke tests
     |
     v
Open traffic
~~~

Independent tasks can be prepared in parallel before maintenance: installing target binaries, installing extension packages, preparing configs, verifying backups, configuring monitoring, testing endpoint routing, and staging test scripts.

Do not sum durations of parallel tasks as if they run sequentially. Document the true critical path and dependencies.

## 14. Creating a Timing Worksheet

Every step requires a planned duration, actual duration, and owner.

| Step | Planned | Actual | Start/End | Owner |
|---|---:|---:|---|---|
| Freeze writes | 5 min |  |  | Application |
| Drain sessions | 5 min |  |  | DBA |
| Stop old cluster | 3 min |  |  | DBA |
| `pg_upgrade` | 25 min |  |  | DBA |
| Start new cluster | 3 min |  |  | DBA |
| Analyze | 10 min |  |  | DBA |
| Validation | 10 min |  |  | QA/App |
| Restore traffic | 4 min |  |  | Operations |

Numbers above are examples only. Use your own system's rehearsal measurements for planning.

## 15. Recording Timestamps from a Unified Clock

All operators should use synchronized clocks (NTP or an appropriate time service). Runbooks should record timezone-aware timestamps.

~~~text
01:00:00+07:00  Write freeze requested
01:03:12+07:00  Application confirmed no new writes
01:07:45+07:00  Active transactions drained
01:10:02+07:00  Old cluster stopped
01:10:10+07:00  pg_upgrade started
01:34:28+07:00  pg_upgrade completed
01:37:15+07:00  New cluster ready
01:47:30+07:00  Validation passed
01:50:00+07:00  Application traffic restored
~~~

Record when each command starts, ends, and when the owner confirms the result. Never rely on memory after maintenance.

## 16. Timing Individual Commands

Measure execution time with an appropriate shell utility. Linux example:

~~~bash
/usr/bin/time -v /path/to/new/bin/pg_upgrade \
  -b /path/to/old/bin \
  -B /path/to/new/bin \
  -d /path/to/old/data \
  -D /path/to/new/data \
  --jobs=4 \
  --copy
~~~

Capture elapsed wall-clock time, user/system CPU time, maximum resident set size if reported, filesystem I/O, exit code, and logs.

Command duration excludes manual steps outside the command such as checks, endpoint switching, or waiting for application confirmation.

## 17. Measuring Throughput and Disk Utilization

In copy mode, duration typically depends on data size and sustained read/write speeds.

Track read throughput on the old data volume, write throughput on the new data volume, IOPS, queue depth, latency, CPU utilization, free filesystem space, and separate tablespace volumes.

If a volume hits its IOPS ceiling, adding jobs will not improve throughput and can worsen storage contention.

## 18. Estimating Duration from Data Size

A rough model:

~~~text
copy_time ≈ bytes_to_copy / effective_copy_throughput
~~~

For instance, copying 1.2 TB at a sustained throughput of 300 MB/s yields a theoretical duration around 4,000 seconds, roughly 67 minutes.

This is only a coarse estimate. Real runs include metadata, many files, tablespaces, concurrent I/O, fsync, startup, and post-upgrade work.

Never treat short burst peak speeds as sustained throughput. Rely on rehearsal results over equivalent storage.

## 19. Measuring the Impact of `--jobs`

Test several job counts in separate rehearsal runs:

| Jobs | Upgrade Time | Storage Latency | CPU | Notes |
|---:|---:|---:|---:|---|
| 1 |  |  |  | Baseline |
| 2 |  |  |  |  |
| 4 |  |  |  |  |
| 8 |  |  |  |  |

Do not assume doubling jobs halves duration. Find the sweet spot where throughput peaks while storage and CPU remain stable.

## 20. Measuring Post-Upgrade `ANALYZE`

After upgrading, planner statistics must be regathered per plan.

~~~bash
/path/to/new/bin/vacuumdb \
  --all \
  --analyze-in-stages \
  --jobs=4
~~~

Record separate durations for small vs. large databases, large tables, partitioned tables, job counts, CPU/I/O utilization, and the time until query plans reach an acceptable state.

You may prioritize critical tables/queries first if the runbook permits, provided a plan exists to finish remaining statistics.

## 21. Measuring Startup and Readiness

A running PostgreSQL process does not mean the service is ready.

The readiness gate should confirm the process is up, ports/sockets accept connections, databases open, primary/recovery role matches topology, extensions load cleanly, required schemas/roles exist, startup logs are clean of errors, and read/write probes succeed per policy.

For HA clusters, verify leader state and fencing/replication state per runbook. Never open writes merely because a health endpoint returns HTTP 200.

## 22. Measuring Application Reconnect

Applications may need additional time after the database is ready:

- DNS caches expiring.
- Load balancers updating endpoints.
- Connection pools retiring stale connections.
- Drivers opening new connections.
- Workers restarting.
- Retry/backoff loops completing.
- Application caches warming up.

Record when the database became ready and when the first business transaction succeeded. The gap between those two points is part of real downtime.

## 23. Verifying Transaction Drain

Before stopping the old cluster:

- Stop accepting new requests or switch services to maintenance mode.
- Wait for in-flight requests to finish.
- Handle long-running transactions.
- Check prepared transactions.
- Check `idle in transaction` sessions.
- Stop background jobs and schedulers.
- Confirm connection pools are not reconnecting to the old cluster.

Inspect via:

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    query_start,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
~~~

Never terminate sessions en masse without understanding transaction owners and business impact.

## 24. Checking Prepared Transactions

Two-phase commit can leave prepared transactions requiring coordinator resolution.

~~~sql
SELECT
    transaction,
    gid,
    prepared,
    owner,
    database
FROM pg_prepared_xacts;
~~~

Before upgrading, coordinate with applications/coordinators to commit or roll back each transaction per business rules. Put prepared transactions on the preflight checklist to avoid surprises during the maintenance window.

## 25. Preparing the Write Freeze

The runbook must specify concrete actions:

- Enable maintenance mode in applications/APIs.
- Stop consumers or queue workers that issue writes.
- Pause scheduled jobs, ETL, and batch imports.
- Block write sources outside the main application.
- Check active sessions and transaction counts.
- Confirm zero new writes remain.

When multiple applications or direct database clients exist, obtain sign-off from each source's owner. A maintenance banner on a website does not prove the database stopped receiving writes.

## 26. Copy Mode and the Old Cluster

With `pg_upgrade` copy mode:

- Relation files are copied to the new cluster.
- The old cluster retains independent files.
- The new cluster can be tested while the old cluster preserves the exact state at upgrade time.
- Disk space is needed for both clusters.

This is the easiest option for planning rollback when disk space allows.

However, once the new cluster accepts writes, the old cluster lacks those changes. Being able to start the old cluster does not mean you can switch applications back without losing data.

## 27. Rollback Boundary in Link Mode

With `pg_upgrade` link mode, old and new relation files share the same inodes.

Before the new cluster starts, a path back to the old cluster may exist per your specific version's documentation. Once the new cluster starts operating and writes to linked files, the old cluster is no longer an independent fallback.

~~~text
pg_upgrade link complete
        |
        v
New cluster not started?
        |
    +---+---+
    |       |
   Yes      No
    |       |
    v       v
Rollback   Old cluster is not an
may be    independent fallback
possible  after linked writes
~~~

Never start the old cluster once the new cluster has written to hard-linked files.

## 28. Clone Mode and Rollback

Clone/reflink creates logically independent files via copy-on-write where supported by the filesystem.

This preserves the old cluster as a frozen fallback. Yet once the new cluster accepts writes, the old cluster does not automatically receive new transactions.

If forced to revert to the old cluster after writes occurred on the new one, determine which transactions were acknowledged to clients, which writes must be retained, whether they can be exported/reconciled or replayed, and the actual RPO if every transaction cannot be preserved.

Do not mistake copy-on-write for replication.

## 29. Copy-File-Range and Rollback

Copy-file-range is a kernel-assisted file range copy mechanism on supported environments. It creates independent files, leaving the old cluster intact.

However, like copy and clone, the old cluster reflects pre-upgrade state. Writes on the new cluster do not flow back to the old one. Post-cutover rollback still requires resolving write divergence.

## 30. Defining Rollback Triggers

Never wait until the maintenance window is nearly over to debate whether to roll back.

Define triggers beforehand:

- `pg_upgrade` fails and cannot be fixed within remaining time.
- New cluster fails to start.
- Required extensions fail to load.
- Databases or tablespaces are incomplete.
- Role/authentication failures break applications.
- Data validation discrepancies exceed thresholds.
- Critical query latency breaches SLOs.
- Application smoke tests fail.
- Replication/backups fail to meet requirements.
- Single-writer or HA safety cannot be verified.

Each trigger requires a designated decision-maker and a decision deadline.

## 31. Go/No-Go Gates

| Gate | GO Condition | If NO-GO |
|---|---|---|
| Preflight | Backups, binaries, disk, extensions ready | Do not start |
| Freeze | Writes stopped and sessions drained | Continue draining or abort |
| Upgrade | `pg_upgrade` succeeds | Fix within time budget or roll back |
| Startup | New cluster ready | Keep traffic closed, investigate |
| Validation | Data/roles/extensions pass | Roll back per boundary |
| Application | Smoke tests and critical transactions pass | Do not open broad traffic |
| Cutover | Monitoring and owners ready | Stay in maintenance mode |

Never skip a gate just because the maintenance window is running low. Rolling back earlier may be essential to leave enough time for recovery.

## 32. Setting a Rollback Decision Deadline

Example 90-minute maintenance window:

- 0–10 min: freeze/drain/shutdown.
- 10–40 min: `pg_upgrade`.
- 40–55 min: startup and post-upgrade checks.
- 55–70 min: validation.
- 70–80 min: application smoke tests.
- 80–90 min: buffer / rollback decision.

Milestones are illustrative only. Rehearsals must supply real numbers.

Set a final deadline to decide between proceeding and rolling back. If critical gates remain unmet at the deadline, execute the pre-planned branch rather than troubleshooting indefinitely.

## 33. Rollback Before the New Cluster Accepts Writes

This is the simplest case with copy/clone mode:

1. Keep applications in maintenance mode.
2. Block write endpoints to the new cluster.
3. Stop the new cluster cleanly.
4. Preserve logs and the new data directory for investigation.
5. Verify the old cluster remains independent and untouched.
6. Start the old cluster with the old binaries.
7. Verify databases and roles.
8. Switch endpoints back to the old cluster.
9. Reconnect applications.
10. Run smoke tests and reopen traffic.

For link mode, execute rollback only if the new cluster has not started/written and the target version's rollback procedure permits it. When unsure, stop and use the backup recovery procedure.

## 34. Rollback After the New Cluster Accepts Writes

This is the more complex scenario.

The old cluster lacks transactions committed on the new cluster. Simply switching endpoints loses those new writes from the application's view.

Assess:

- Which transactions were acknowledged?
- Can changes be exported from the new cluster?
- Is there a logical audit or CDC stream?
- Is there a business event log capable of replay?
- Can we forward-fix on the new cluster instead?
- Can a backup be restored and WAL replayed per recovery design?
- What RPO defines acceptable write loss if any?

Some systems choose to forward-fix on the new cluster because rolling back data is unsafe. Decide based on failure mode and data consistency, not speed alone.

## 35. Do Not Conflate Code Rollback with Data Rollback

You might roll back application binaries while database schemas and data have already changed.

For example, a new application release uses a new schema; the database migration added or altered data; reverting application code does not automatically revert the schema. Old application code may be incompatible with the new schema.

Prepare a compatibility strategy:

- Expand/contract migrations.
- Backward-compatible schema changes.
- Feature flags.
- Versioned application deployments.
- Data migration checkpoints.
- Forward-fix plan.

Database major upgrades and application schema migrations must be managed as related yet distinct risks.

## 36. PITR Is Not an Instant Rollback

Point-in-time recovery can restore a cluster to a moment prior to an incident using a base backup and WAL archive.

Typical steps:

1. Select the right base backup.
2. Restore into a separate data directory.
3. Configure WAL archive recovery.
4. Specify target time/LSN/transaction per version support.
5. Run recovery.
6. Verify data.
7. Open endpoints once approved.

PITR can take considerable time and discards transactions after the recovery target. Measure restore/replay timings during rehearsal; never assume PITR finishes in a few minutes.

## 37. Rollback via Backup Restore

If the old cluster is no longer usable or link mode crossed the rollback boundary:

- Isolate the failed cluster.
- Restore an independent backup onto a fresh cluster.
- Replay WAL to the appropriate target point.
- Verify database consistency.
- Update configuration and extensions.
- Verify applications.
- Switch endpoints.

This is a separate recovery path whose RTO may exceed restarting an old cluster. It must be rehearsed with real backups.

## 38. Choosing the Old Cluster vs. a Backup for Fallback

| Scenario | Recovery Path to Consider |
|---|---|
| Copy/clone, new has no writes | Old frozen cluster can serve as fallback |
| Link, new has not started | Follow exact version-specific rollback procedure |
| Link, new has written | Do not use old cluster independently; restore/recover |
| New accepted writes, old missing data | Reconcile, forward-fix, or PITR per policy |
| Old cluster damaged | Restore backup and replay WAL |
| Data corruption replicated | PITR/backup to before corruption |

An old cluster is not always the right target. If the upgrade failed due to data corruption or storage defects, old files might also be impacted depending on mode and infrastructure.

## 39. New Backup Before Deleting the Old Cluster

Once the new cluster stabilizes:

- Take a base backup of the new major version.
- Verify WAL archiving.
- Run a restore test.
- Verify monitoring and alerting.
- Record backup retention.
- Keep the old cluster until the rollback window closes per policy.

Never run the generated cleanup script or delete the old data directory solely because traffic reopened.

## 40. Measuring Downtime Across Multiple Rehearsals

A single rehearsal can be skewed by warm caches, storage noise, or unrepresentative workloads.

Run multiple rehearsals in an environment resettable to baseline:

- Rehearsal 1: validate the procedure and uncover blockers.
- Rehearsal 2: measure timing after fixes.
- Rehearsal 3: confirm stable timing and rehearse rollback.
- Additional rehearsals: test failure injection or recovery paths if needed.

You do not need to repeat every step once stability is proven, though major changes in data size, storage, binaries, or extensions warrant re-testing.

## 41. Recording Median and Worst Observed Durations

Record each step's duration across rehearsals.

| Step | Run 1 | Run 2 | Run 3 | Worst Observed |
|---|---:|---:|---:|---:|
| Drain |  |  |  |  |
| Shutdown |  |  |  |  |
| Upgrade |  |  |  |  |
| Startup |  |  |  |  |
| Analyze |  |  |  |  |
| Validation |  |  |  |  |
| App reconnect |  |  |  |  |

Use the median to understand a typical run and worst observed to size buffers. With few samples, worst observed is not a reliable statistical percentile; record trial counts and conditions explicitly.

## 42. Extrapolating When Production Data Exceeds Rehearsal

If the rehearsal dataset is smaller than production:

- Compare total relation bytes, not just database count.
- Compare file counts and tablespaces.
- Compare index/TOAST proportions.
- Compare storage throughput.
- Separate fixed overhead from data-size-proportional duration.
- Run an extra rehearsal on a larger snapshot if feasible.

Never extrapolate linearly without nuance. A cluster with millions of small files can incur far higher metadata overhead than raw byte volume suggests.

## 43. Post-Upgrade Data Validation

Validation must match workload semantics:

- Database/schema/table inventory.
- Row counts or critical business aggregates.
- Sequence values and ownership.
- Constraints and index validity.
- Extension state.
- Roles, owners, and grants.
- Large objects if used by applications.
- Collation warnings.
- Critical stored procedures.
- Representative query results.

Example business aggregate:

~~~sql
SELECT
    count(*) AS order_count,
    min(created_at) AS oldest_order,
    max(created_at) AS newest_order,
    sum(total_amount) AS total_amount
FROM public.orders;
~~~

Pick business-meaningful invariants. Full row counts on every table are not mandatory if they blow the maintenance window; run targeted validation queries upfront and deeper audits post-cutover.

## 44. Application Smoke Tests

A smoke test suite should cover:

1. Logging in with the application role.
2. Reading a critical record.
3. Writing a test transaction if policy allows.
4. Committing and reading the result back.
5. Performing an update/delete on a recoverable test fixture.
6. Checking sequence-generated keys.
7. Executing critical stored procedures.
8. Checking background jobs and queue consumers.
9. Checking connection pools and retries.
10. Confirming zero remaining connections to the old endpoint.

Smoke tests must run during rehearsal with archivable results.

## 45. Checking Extensions and Configuration

Once the new cluster starts:

~~~sql
SELECT
    extname,
    extversion
FROM pg_extension
ORDER BY extname;

SELECT
    name,
    setting,
    source,
    context
FROM pg_settings
WHERE source <> 'default'
ORDER BY name;
~~~

Cross-check against the pre-upgrade inventory. Verify extension libraries, `shared_preload_libraries`, authentication, TLS, archive settings, logging, and memory parameters.

A cluster can open databases while a critical extension or background worker still fails.

## 46. Replication and HA Validation

If using physical replication:

- Verify standbys are rebuilt/rejoined on the exact target version.
- Check WAL receivers.
- Check replay progress.
- Check replication slots and WAL retention.
- Verify archive/restore.
- Rehearse failover in staging.

If using logical replication/CDC:

- Check publications and subscriptions.
- Verify logical slots and consumers.
- Monitor lag and WAL retention.
- Confirm external connectors support the target version.

Never open production traffic if backup/replication readiness is part of service readiness and remains unmet.

## 47. Connection Routing and DNS

After upgrading, endpoints may need updating across:

- DNS records.
- Virtual IPs.
- Load balancer backends.
- Service discovery.
- PgBouncer/HAProxy configs.
- Application connection strings.

Measure propagation and reconnect times. DNS TTLs do not guarantee every client drops caches on time; connection pools can also hold stale sessions.

Keep the old endpoint isolated or read-only by design to prevent applications from accidentally writing to the old cluster post-cutover.

## 48. Communication Plan and Role Assignments

The runbook must specify maintenance start/end, affected services, read-only vs. full outage status, status channels, GO/NO-GO decision-makers, DBA/application/infrastructure/QA coordinators, rollback authority, and escalation paths.

Example role breakdown:

| Role | Responsibility |
|---|---|
| Change owner | Overall accountability and final decisions |
| DBA lead | Backups, stop, `pg_upgrade`, startup, SQL validation |
| Infrastructure | Storage, filesystems, VMs, network, monitoring |
| Application lead | Write freeze, drain, reconnect, smoke tests |
| QA | Execute test cases and report outcomes |
| Incident commander | Track timeline, trigger rollback/escalation |
| Communications | Send status updates to stakeholders |

Every critical step needs one clear owner. Avoid “everyone is responsible.”

## 49. Preparing the Execution Runbook

The runbook must contain:

- Preconditions.
- Exact commands with real paths and ports.
- Expected output or exit codes.
- Log locations.
- Owner.
- Timeout.
- Verification query.
- Failure branch.
- Rollback action.
- Contact/escalation.

Never leave placeholders in the final production runbook. Study examples can use `/path/to/...`, but operators must substitute real paths and have them peer-reviewed prior to maintenance.

## 50. Command Logs and Evidence

Each step should record timestamp, operator, command/action, exit code, output/log reference, verification outcome, and decision.

Never write passwords, tokens, or connection secrets into command logs. Use a credential manager or secret injection per policy.

Evidence supports postmortems and comparisons across rehearsals.

## 51. Controlled Failure Injection

You can rehearse failure scenarios in staging:

- Out of disk space.
- Missing extension binary.
- `pg_upgrade --check` reporting blockers.
- New cluster failing to start due to config errors.
- Application authentication failure.
- Slow DNS/endpoint propagation.
- Standby failing to rejoin.
- Slow backup restore.
- A smoke test returning wrong results.

Each test requires a resettable environment and supervision. Never inject failures in production just to test a runbook.

## 52. Rehearsing the Rollback Decision

Do not test only rollback commands; rehearse the decision-making loop too:

1. Simulate a critical validation failure.
2. Decision-makers review evidence.
3. Evaluate against rollback triggers.
4. Make the decision before the deadline.
5. Close write paths to the new cluster.
6. Execute the matching recovery path.
7. Verify the old/restored cluster.
8. Reconnect applications.
9. Measure recovery duration.
10. Document missing runbook steps.

An untested rollback procedure is a hypothesis, not a proven capability.

## 53. Sample Runbook Timeline

The table below illustrates tracking structure, not standard timings:

| Time | Action | Gate |
|---|---|---|
| T-7 days | Restore rehearsal, extension check | Backup restore passes |
| T-1 day | Preflight, disk, `pg_upgrade --check` | Zero blockers |
| 01:00 | Write freeze | App owners confirm |
| 01:05 | Drain sessions | Zero active writes |
| 01:10 | Stop old cluster | Process stopped |
| 01:12 | Run `pg_upgrade` | Exits cleanly |
| 01:40 | Start new cluster | Readiness passes |
| 01:48 | Analyze and extension checks | Zero critical errors |
| 02:00 | DB/application validation | All critical tests pass |
| 02:10 | Restore traffic | Monitoring healthy |
| 02:25 | End heightened watch | Owners sign off |

T-7 days and T-1 day represent pre-change preparation. In practice, certain tasks may span multiple days or multiple rehearsals.

## 54. GO Decision After Rehearsal

A rehearsal passes when:

- Runbook steps are repeatable.
- Timings fit within the maintenance window with buffer.
- Backup restore is proven.
- Rollback is rehearsed for the chosen mode.
- Extensions and external dependencies are ready.
- Application smoke tests pass.
- Owners and escalation paths are clear.
- Zero unmitigated blockers remain.
- Actual RTO/RPO align with targets.

If actual duration exceeds the window, adjust method, infrastructure, or scope and rehearse again. Never weaken validation criteria just to fit the schedule.

## 55. Post-Cutover: Heightened Monitoring

Immediately after cutover, step up monitoring of:

- Connection counts and failed logins.
- Query latency and error rates.
- CPU, memory, and storage I/O.
- Deadlocks and lock waits.
- Autovacuum/analyze.
- WAL generation and replication lag.
- Temp files.
- Checkpoint behavior.
- Backup jobs.
- Application queue backlogs.
- Critical business transactions.

Define the heightened monitoring duration and assigned watchers beforehand.

## 56. When Can the Old Cluster Be Deleted?

Delete the old cluster only when:

- The new cluster has run stably.
- Application owners sign off.
- A new backup completed and restored cleanly.
- WAL archiving/replication meet requirements.
- Monitoring/alerts are working.
- The rollback window has expired or been closed by the change owner.
- Logs, evidence, and configuration inventories are archived.

If using link mode, do not use the old cluster for rollback after the new cluster starts. Still ensure an independent backup exists prior to upgrading.

## 57. Production Upgrade Checklist

**Before maintenance**

1. Confirm supported source/target major versions.
2. Read release notes and `pg_upgrade` docs.
3. Inventory databases, roles, tablespaces, and extensions.
4. Verify backup/restore and WAL archiving.
5. Rehearse on a production-like clone.
6. Choose copy/link/clone/copy-file-range based on rollback, disk, and filesystem.
7. Install target binaries and extension packages.
8. Run `initdb` on the new cluster with compatible settings.
9. Run `pg_upgrade --check`.
10. Finalize the maintenance window and rollback boundary.

**During maintenance**

11. Stop writes and scheduled jobs.
12. Shut down the old cluster cleanly.
13. Verify data directories and tablespaces.
14. Run the actual `pg_upgrade`.
15. Save logs and generated scripts.
16. Review the new configuration.
17. Start the new cluster and read logs.

**After upgrade**

18. Run `ANALYZE` per plan.
19. Update extensions where needed.
20. Verify roles, grants, databases, tablespaces, and objects.
21. Check collation/index warnings.
22. Restore backups, monitoring, and replication.
23. Run application smoke tests and representative workloads.
24. Switch traffic after validation sign-off.
25. Delete the old cluster only after the rollback window closes.

## 58. Practice Exercises

### Exercise 1 — RTO

What does RTO measure?

**Hint:** maximum acceptable time for the service to recover.

### Exercise 2 — RPO

What does RPO measure?

**Hint:** acceptable data loss under recovery objectives.

### Exercise 3 — Downtime

Why is `pg_upgrade` runtime not the entire downtime?

**Hint:** it omits freeze, drain, startup, validation, and reconnect.

### Exercise 4 — Rehearsal

Why is a production-like environment required?

**Hint:** timings depend on data size, filesystem, storage, and workload.

### Exercise 5 — Timing Worksheet

Which fields should be recorded for each step?

**Hint:** planned/actual duration, timestamps, owner, and result.

### Exercise 6 — Critical Path

Why distinguish sequential tasks from parallel tasks?

**Hint:** do not sum parallel tasks as if they execute sequentially.

### Exercise 7 — Backup

Does an untested backup prove rollback viability?

**Hint:** no.

### Exercise 8 — Copy Mode

How does copy mode preserve the old cluster?

**Hint:** independent relation files preserving pre-upgrade state.

### Exercise 9 — Link Mode

When does the old cluster lose independence?

**Hint:** once the new cluster starts using/writing to the hard-linked files.

### Exercise 10 — Clone Mode

How does clone differ from copy?

**Hint:** copy-on-write/reflink can share initial extents.

### Exercise 11 — Post-Cutover Writes

Why can you not merely point endpoints back to the old cluster?

**Hint:** the old cluster lacks writes committed on the new cluster.

### Exercise 12 — Write Freeze

Which write sources must be stopped?

**Hint:** APIs, workers, ETL, schedulers, and direct clients.

### Exercise 13 — Transaction Drain

Which view helps inspect sessions and transaction start times?

**Hint:** `pg_stat_activity`.

### Exercise 14 — Prepared Transactions

Which view lists prepared transactions?

**Hint:** `pg_prepared_xacts`.

### Exercise 15 — Readiness

Is a running PostgreSQL process enough to open traffic?

**Hint:** no; DB, extension, role, and application validation are required.

### Exercise 16 — Application Reconnect

What factors slow down application reconnection?

**Hint:** DNS caches, connection pools, retry/backoff, and worker restarts.

### Exercise 17 — Rollback Triggers

Give three examples of triggers requiring rollback.

**Hint:** startup failure, critical validation mismatch, application smoke test failure.

### Exercise 18 — Decision Deadline

Why is a GO/NO-GO deadline necessary?

**Hint:** to preserve enough time for the rollback branch.

### Exercise 19 — PITR

Which components does PITR require?

**Hint:** a base backup and continuous WAL archiving.

### Exercise 20 — Link Rollback

Can the old cluster serve as a rollback target after the new cluster writes to linked files?

**Hint:** unsafe.

### Exercise 21 — Copy Rollback

Does copy mode automatically sync new writes back to the old cluster?

**Hint:** no.

### Exercise 22 — RTO Measurement

Between which milestones is RTO measured?

**Hint:** per the agreed service recovery definition—typically until applications execute transactions successfully.

### Exercise 23 — ANALYZE

Why can post-upgrade `ANALYZE` belong inside the maintenance plan?

**Hint:** planner statistics must be regathered.

### Exercise 24 — Storage Throughput

Why measure IOPS and latency alongside throughput?

**Hint:** bottlenecks can be IOPS/latency, not merely MB/s.

### Exercise 25 — Parallel Jobs

Does increasing jobs always reduce elapsed time?

**Hint:** no; storage contention may rise.

### Exercise 26 — Data Validation

Name one business invariant to check.

**Hint:** order count, total amount, or a critical aggregate.

### Exercise 27 — Extension Readiness

Why must extension packages be prepared beforehand?

**Hint:** the target server requires compatible native libraries and control files.

### Exercise 28 — HA Readiness

After a major upgrade, why must standbys be verified?

**Hint:** old standbys may need rebuilding/reseeding for the target version.

### Exercise 29 — Old Cluster Cleanup

When may the old cluster be deleted?

**Hint:** after validation, backup/restore tests, monitoring, and the rollback window finish.

### Exercise 30 — Rehearsal Results

What evidence must a passing rehearsal produce for GO approval?

**Hint:** timings, backup restore proof, rollback drill, validation, and owner sign-off.

## 59. Frequently Asked Questions

### Does downtime start when the database stops?

Not necessarily. If applications stopped accepting writes beforehand, write downtime begins at write freeze. Define explicit service metrics.

### Is RTO equal to the maintenance window?

No. RTO is a recovery objective; the maintenance window is the scheduled change period. They relate closely but are not identical.

### Does rehearsal require real production data?

Not strictly, though the dataset must be representative in size, relation layout, extensions, and workload. When using anonymized or scaled-down data, document extrapolation limits.

### Can we time `pg_upgrade` on a small machine and multiply by size?

That yields only a rough estimate. Filesystem metadata, tablespaces, IOPS, and file counts make scaling non-linear. Rehearse on production-like storage.

### Does a pre-upgrade backup cover every rollback scenario?

No. You must verify restore capability, WAL continuity, RPO, and recovery time. Backups also do not capture writes made after the backup.

### Does copy mode allow reverting after the new cluster accepts writes?

The old cluster stays independent yet lacks new writes. Returning without losing data requires reconciliation/replay or a dedicated recovery plan.

### Is clone mode equivalent to replication?

No. Clone creates an independent copy-on-write snapshot at clone time; subsequent changes are not synced between clusters.

### Can link mode be rolled back?

Only within the narrow window before the new cluster uses/writes to linked files and per the exact version's procedure. Afterward, the old cluster is no longer independent.

### What if the new cluster started but accepted no application writes?

Internal writes and startup activity must still be assessed. With link mode, never assume the old cluster is safe; follow the target version's exact rollback procedure and rehearsed proof.

### What if smoke tests fail after writes occurred?

Hold traffic per incident policy, identify committed writes, and pick forward-fix, reconciliation, or recovery paths. Never mechanically point endpoints back to the old cluster.

### Can PITR replace keeping the old cluster?

It can serve as a recovery path, yet restore/replay duration and data loss depend on backups and WAL. Measure it during rehearsal.

### Should every validation run before opening traffic?

Critical validations should finish before opening writes. Certain deep checks can continue post-cutover if risk-assessed with an assigned owner.

### Do we still need a rollback drill when using copy mode?

Yes. Copy mode only keeps old files independent; operators still must prove stopping the new cluster, starting the old one, switching endpoints, and verifying applications.

### When should heightened monitoring end?

Once metrics and business transactions stabilize across a representative workload cycle, backups/replication pass, and owners sign off.

## 60. Summary

An actionable rehearsal and rollback plan requires:

1. Defining downtime, RTO, and RPO.
2. Building a production-like rehearsal environment.
3. Inventorying the cluster, extensions, tablespaces, HA, and application dependencies.
4. Testing actual backups and restores.
5. Running `pg_upgrade --check`.
6. Choosing copy/link/clone/copy-file-range based on filesystem, disk, and rollback requirements.
7. Separating preflight tasks from the maintenance window.
8. Measuring freeze, drain, shutdown, upgrade, startup, analyze, validation, and reconnect.
9. Recording timestamps, owners, exit codes, and evidence.
10. Defining the critical path, buffers, and decision deadlines.
11. Establishing rollback triggers and GO/NO-GO gates.
12. Rehearsing rollback prior to the production change.
13. Never reverting mechanically to the old cluster if the new cluster accepted writes.
14. Validating extensions, roles, data invariants, replication, and applications.
15. Taking a new backup and verifying restore before deleting the old cluster.

Key principles to remember:

- Downtime must be measured by application serviceability, not just database process stop time.
- RTO and RPO must be agreed upon and tested.
- Rehearsals require representative data, storage, binaries, and extensions.
- `pg_upgrade --check` is a preflight check, not an actual timing run.
- Copy preserves old data independently yet does not sync new writes.
- Link imposes a strict rollback boundary once the new cluster starts or writes.
- Clone/reflink keeps clusters independent yet is not replication.
- A backup has value only once restored and timed.
- Set a rollback deadline well before the maintenance window expires.
- Critical validations must pass before opening traffic.
- Once writes occur on the new cluster, resolve data divergence before reverting to the old cluster.
- Retain logs, evidence, and the old cluster until the rollback window closes.
- Close the change only once applications, backups, replication, and monitoring are all verified.

Decision diagram:

~~~text
             Rehearsal completed
                     |
                     v
          Backup restore proven?
               /          \
             No            Yes
             |              |
             v              v
          NO-GO       pg_upgrade --check
                            |
                            v
                   Actual upgrade rehearsal
                            |
                            v
                   Startup + validation
                            |
                     All critical gates?
                       /          \
                     No            Yes
                     |              |
                     v              v
              Rollback drill    Open traffic
                     |              |
                     v              v
             Recovery verified  Heightened monitoring
                                    |
                                    v
                         Backup/replication stable?
                              /           \
                            No             Yes
                            |               |
                            v               v
                         Continue       Close rollback
                         monitoring     window safely
~~~

**Conclusion:** Upgrade rehearsals must measure the entire journey from write freeze until the application completes its first transaction on the new cluster. Rollback plans must align with the transfer mode, backups, and post-cutover write state. Only after timing every step, defining critical gates, and rehearsing rollback does an operations team have a solid basis to commit to a maintenance window and make controlled GO/NO-GO decisions.
