# Readiness Checks, Startup, Shutdown, and Controlled Maintenance in MongoDB

A running MongoDB process does not mean the database is **ready to serve the application**. A replica set may have `mongod` listening on a TCP port yet have no primary; a secondary may be replicating slowly; a `mongos` may be running yet unable to reach config servers; an application may succeed with `ping` yet fail to write under its committed write concern.

Therefore, **startup, shutdown, and controlled maintenance** must be treated as an operational procedure with pre-, mid-, and post-operation gates—not merely running a restart command and checking service status.

This lesson, part of the **Operations and Upgrades** chapter in the **Database Engine Document MongoDB** module, covers:

1. Distinguishing liveness, readiness, application readiness, and maintenance readiness.
2. Checking processes, configuration, replication, quorum, performance, and connectivity before making changes.
3. Starting and stopping `mongod`/`mongos` properly on Linux, Windows, containers, and managed environments.
4. Rolling maintenance in a replica set, handling primary stepdowns, and quorum-loss scenarios.
5. Coordinating maintenance across a sharded cluster, config servers, shards, `mongos`, and the balancer.
6. Preflight workflows, traffic draining, change execution, smoke tests, rollback, and evidence reporting.
7. Failure scenarios, hands-on exercises, and checklists for building runbooks.

**Safety principle:** Stop, restart, stepdown, and infrastructure-change commands can cause service disruption or loss of write availability. Execute them only when authorized, after confirming the exact cluster/host, with an approved maintenance plan and recovery strategy. Command examples below are for lab environments or an approved runbook—never instructions to run mechanically in production.

## 1. Four Layers of Readiness to Distinguish

| Layer | Question | Example Evidence |
| --- | --- | --- |
| **Liveness** | Does the process exist and respond minimally? | Service/process status, TCP, `ping` |
| **Database readiness** | Can MongoDB serve operations according to its role? | Primary/secondary states, auth, quorum, read/write probe |
| **Application readiness** | Do APIs and critical features work properly? | Login, reads/writes, business smoke tests |
| **Maintenance readiness** | Are conditions safe to pause or modify a component? | Healthy majority, backup, replication lag, capacity, rollback |

One layer cannot substitute for another.

### 1.1. Process Running Does Not Equal Database Ready

A command like:

~~~bash
systemctl is-active mongod
~~~

may return `active`. Yet MongoDB could still be:

- Performing startup recovery or initial sync.
- Without an elected primary.
- Experiencing heavy replication lag.
- Out of disk space.
- Failing application authentication/TLS.
- Unable to satisfy majority write concern.
- Missing an index required by a critical API.

### 1.2. Ping Is Not Enough

The command:

~~~javascript
db.adminCommand({ ping: 1 });
~~~

proves basic connectivity and the ability to handle a trivial command; it **does not prove** data or business transactions are working properly.

### 1.3. Database Ready Does Not Mean Application Ready

An application can still fail due to a wrong connection string, expired credentials, an undersized connection pool, pending schema/data migrations, or background workers failing to start properly.

### 1.4. Maintenance Readiness Is a Stricter Gate

A replica set serving normally while missing one voting member may **not be safe to take another member offline**. Maintenance must evaluate the remaining failure budget, not just whether the system is currently online.

## 2. Operational Terminology

| Term | Meaning |
| --- | --- |
| **mongod** | Database server process, including standalone, replica set members, and shards/config servers |
| **mongos** | Query router for a sharded cluster |
| **Replica set** | Group of `mongod` instances maintaining replicated data with an election mechanism |
| **Primary** | Member accepting writes in a standard replica set topology |
| **Secondary** | Member replicating the oplog and optionally serving reads per configuration |
| **Election** | Process of choosing a new primary |
| **Quorum/majority** | Minimum number of voting members needed to elect a primary and satisfy majority mechanics |
| **Replication lag** | Delay between primary write progress and secondary application progress |
| **Oplog window** | Time span of history in the oplog available for replication/resumption |
| **Stepdown** | Requesting the primary to relinquish its role, triggering an election |
| **Graceful shutdown** | Controlled shutdown allowing the process to close resources cleanly |
| **Rolling maintenance** | Sequential maintenance across components to minimize disruption |
| **Drain** | Routing away/reducing new connections or requests before stopping a component |
| **Go/No-Go** | Decision to proceed with or halt maintenance based on defined criteria |
| **Rollback** | Returning to a prior software/config state when safe and supported |

**Note:** Rolling back binaries or configs is not automatically the same as rolling back data. After changing FCV/schema or accepting new writes, reverting to an older version may be restricted or unsafe.

## 3. Readiness State Flow

~~~text
Host/Container up
       |
       v
mongod process running
       |
       v
TCP/TLS/auth reachable
       |
       v
Replication topology healthy
       |
       +--> standalone: server ready
       |
       +--> replica set:
                 |
                 v
              Primary elected
                 |
                 v
              Majority reachable
                 |
                 v
              Reads/writes verified
       |
       v
Required indexes and dependencies ready
       |
       v
Application smoke tests pass
       |
       v
Service ready for business traffic
~~~

### 3.1. Health Signals to Record

Do not record only a single boolean.

~~~text
processHealthy: true
helloResponded: true
topologyRole: SECONDARY
primaryAvailable: true
replicationLagSeconds: 1.8
diskFreePercent: 27
applicationReadProbe: pass
applicationWriteProbe: pass
maintenanceEligible: true
~~~

These values are examples; thresholds must be defined by your organization based on workload and SLOs.

### 3.2. Do Not Expect Every Member to Be Primary

A healthy secondary is completely normal while **not writable**. Readiness probes must understand member roles and endpoint intent.

## 4. Classify the Deployment Before Taking Action

MongoDB supports multiple deployment topologies.

### 4.1. Standalone

~~~text
Application -> mongod
~~~

Stopping the single `mongod` makes the database temporarily unavailable. There is no automatic election.

### 4.2. Replica Set

~~~text
Application -> MongoDB driver
                   |
                   +-> PRIMARY mongod
                   +-> SECONDARY mongod
                   +-> SECONDARY mongod
~~~

Members can be maintained one at a time, while preserving voting majority and controlling primary transitions.

### 4.3. Sharded Cluster

~~~text
Application
     |
     v
  mongos routers
     |
     v
Config Server Replica Set
     |
     +-> Shard Replica Set A
     +-> Shard Replica Set B
     +-> Shard Replica Set C
~~~

Failure domains differ. A config server member is not the same as a shard secondary, and `mongos` is not a data primary.

### 4.4. MongoDB Atlas / Managed Services

The provider manages `mongod` processes, storage lifecycles, and part of maintenance. Never manually run `systemctl` on managed clusters. Use the service's supported maintenance, upgrade, backup, and observability features.

### 4.5. Kubernetes / Operators

MongoDB may run via a StatefulSet and an Operator. Kubernetes restarts Pods automatically based on probes/controllers, but does not replace understanding primary/quorum rules. When using a MongoDB Operator, prefer Operator-supported upgrade/rollout workflows.

## 5. Go/No-Go Criteria Before Maintenance

Every change should pass a **maintenance gate** asking:

1. Are the target cluster, environment, and host confirmed?
2. Are an owner and approved maintenance window defined?
3. Is there an inventory of nodes, versions, and roles?
4. Do all affected replica sets have a healthy majority?
5. Is there an up-to-date, electable secondary ready for primary stepdown?
6. Is replication lag within acceptable thresholds?
7. Is the oplog window large enough if a node stays offline longer than expected?
8. Are valid backups, recovery procedures, and restore permissions ready?
9. Do disk space, inodes, RAM, and CPU have sufficient headroom?
10. Are there no active production incidents or exhausted error budgets?
11. Have sensitive jobs, migrations, index builds, and database connections been addressed?
12. Has application retry/failover behavior been verified?
13. Are rollback/abort conditions and a decision-maker defined?
14. Are observability, alerts, and communication channels ready?
15. Are smoke tests prepared for after each step?

If critical criteria fail, **postpone or adjust the plan**—never force through with override flags.

## 6. Confirming the Exact Cluster and Version

Before running any commands, verify the connection context:

~~~javascript
db.adminCommand({ hello: 1 });
~~~

`hello` provides endpoint role/capability fields such as **isWritablePrimary**, **secondary**, **setName**, host lists, or `mongos` indicators depending on topology.

Check the server version when authorized:

~~~javascript
db.adminCommand({ buildInfo: 1 });
~~~

### 6.1. Do Not Trust Hostnames Alone

Hostnames can be reused or DNS records changed. Record cluster IDs, replica set names, and environment labels in runbooks, and cross-check against monitoring/control plane data.

### 6.2. mongos Differs from mongod

Connecting to `mongos` connects to a router; running **`rs.status()`** on `mongos` is not how you directly inspect a replica set member. Use the appropriate endpoints and monitoring tools.

### 6.3. Feature Compatibility Version

When maintenance includes an upgrade, check **FCV** and binary compatibility:

~~~javascript
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});
~~~

Features, syntax, and downgrade procedures depend on version. Never treat changing FCV as part of a routine restart.

## 7. Checking Replica Set Health

Connect to a member with appropriate privileges:

~~~javascript
rs.status();
~~~

Focus on these fields:

- Member name/address.
- State (`PRIMARY`/`SECONDARY`/`RECOVERING`/`STARTUP2`, etc.).
- Member health.
- Oplog timestamps/progress.
- Election term and current primary.
- Replication lag.
- Heartbeat failures.
- Sync source.
- Voting/electable configuration.

### 7.1. SECONDARY State Does Not Mean Caught Up

A secondary may be receiving oplog entries yet still lag significantly behind. Before stepping down a primary so a secondary can take over, verify catch-up readiness.

### 7.2. Do Not Rely on a Single Snapshot

Health and lag fluctuate over time. Observe multiple consecutive samples across an appropriate window before starting maintenance.

### 7.3. Election Priorities

Not every secondary is electable. Members with priority 0, non-voting members, or special configurations cannot replace the primary as expected.

### 7.4. Hidden/Delayed Members

Hidden or delayed members serve dedicated purposes; never treat them as primary candidates. Understand votes, priorities, and quorum impact before starting maintenance.

## 8. Majority and Failure Budget

For a replica set with $N$ voting members, the majority needed to elect a primary is:

\[
M = \left\lfloor\frac{N}{2}\right\rfloor + 1
\]

Examples:

| Voting members | Majority required | Voting members that can be lost while keeping majority |
| ---: | ---: | ---: |
| 1 | 1 | 0 |
| 2 | 2 | 0 |
| 3 | 2 | 1 |
| 4 | 3 | 1 |
| 5 | 3 | 2 |
| 7 | 4 | 3 |

### 8.1. Three-Voter Example

~~~text
PRIMARY      healthy
SECONDARY A  healthy
SECONDARY B  healthy
~~~

If B is stopped, 2 voters remain, preserving majority. If A is also stopped before B returns, only 1 voter remains, losing majority to elect a primary.

### 8.2. Quorum Does Not Guarantee Enough Data Nodes

A voting member can participate in elections without holding a full copy of data (e.g., an arbiter). A topology that still has majority votes may lack enough data-bearing nodes to satisfy expected writes or availability SLAs.

### 8.3. Majority Writes and Data Durability

If the application uses majority write concern, verify enough data-bearing acknowledgments remain available per configuration—not merely how many processes are alive.

### 8.4. Never Stop Multiple Voters Simultaneously Without an Explicit Plan

Standard rolling maintenance waits for each member to return healthy and caught up before moving to the next.

## 9. Checking Replication Lag and Oplog Window

A node taken offline for OS patching, volume replacement, or a restart must catch up on all operations written during its absence.

### 9.1. Replication Lag

~~~text
Primary latest optime:   T_now
Secondary applied optime: T_now - delta
Replication lag:         delta
~~~

A large delta affects election readiness and secondary recovery time.

### 9.2. Oplog Window

The oplog stores a bounded history of operations. If a member stays offline longer than the retained history window, it may require an **initial sync** instead of normal catch-up.

### 9.3. Do Not Rely on a Single Hardcoded Threshold

A 5-second lag may be acceptable for one workload and unacceptable for another. Set thresholds based on write rate, SLOs, and maintenance duration.

### 9.4. Multi-Sample Monitoring

Before restarting, monitor lag/optime over a time window; when the node returns, confirm it reaches `SECONDARY` and catches up before proceeding.

## 10. Checking System Resources

Key resources to verify:

| Resource | Question |
| --- | --- |
| Disk free | Enough headroom for journals, indexes, and compaction/maintenance? |
| Disk latency/IOPS | Is storage saturated, risking slow shutdown/startup? |
| CPU | Is sustained high load slowing elections? |
| RAM/WiredTiger cache | Any memory pressure or OOM risk? |
| Open files/limits | Are file descriptor limits sufficient? |
| Network | Any packet loss, TLS failures, or DNS issues? |
| Time sync | Are host clocks synchronized per policy? |
| Filesystem | Are volumes/persistent mounts operating properly? |
| Backup storage | Can we restore if the change fails? |
| Host health | Are nodes/VMs free of disk hardware errors? |

### 10.1. Avoid Major Maintenance While the Cluster Is Saturated

If only one healthy secondary remains and it is under heavy load, a stepdown can spike latency or prolong failover.

### 10.2. Disk Nearly Full

Starting MongoDB on a full volume can fail or behave unpredictably. Resolve capacity issues before approving maintenance.

### 10.3. Least-Privilege Metrics Access

Some metrics require a role such as `clusterMonitor`; never grant broad admin write privileges just so a readiness probe can read `serverStatus`.

## 11. MongoDB serverStatus and Monitoring

With appropriate privileges:

~~~javascript
db.serverStatus();
~~~

Common metric groups:

- Connections (`current`/`available`).
- Opcounters and throughput.
- WiredTiger memory/cache.
- Network bytes/requests.
- Operations/cursors.
- Lock contention.
- Replication/election events.
- Read/write concern failures.
- Disk utilization from OS/cloud metrics.

### 11.1. serverStatus Does Not Replace Application Metrics

A replica set that looks healthy internally while API p95 latency has spiked fivefold is not meeting operational goals.

### 11.2. Before/After Baseline

Record at least these metrics:

~~~text
API p95 latency
MongoDB operation error rate
Replica lag
Election count
Connections current
CPU / disk IOPS / disk free
Queue/CDC lag
Storage/write throughput
~~~

### 11.3. Track Trends Instead of Single Points

A brief spike right after an election can be normal, whereas steadily rising lag and sustained write errors signal you must halt the rollout.

## 12. Checking Backups Before Maintenance

Before any risky operation:

1. Verify the latest backup is within retention.
2. Confirm the true recovery point and RPO.
3. Verify storage location and access permissions.
4. Confirm encryption keys/credentials if encrypted.
5. Know the restore procedure for the current topology.
6. Check the date/outcome of the latest restore drill.
7. Confirm recovery readiness for configs and secrets.
8. Never rely on an in-progress backup that has not completed.

### 12.1. Backups Do Not Replace a Rollback Plan

Reverting a config change in minutes is a very different recovery path from restoring an entire cluster from backup.

### 12.2. A Restore Drill Is Stronger Evidence Than Backup Status

A backup marked "succeeded" that cannot be decrypted or restored does not protect the application.

### 12.3. Replication Is Not a Backup

Accidental deletions or logical corruption replicate across members. When maintenance changes schemas or data, backups/PITR provide a separate safety net.

## 13. Application Readiness Before Planned Maintenance

A MongoDB application should have:

- A connection string targeting the proper replica set/sharded endpoint.
- A driver version compatible with the server.
- Working server discovery and monitoring (SDAM).
- Appropriate network timeouts and retry policies.
- Defined behavior during the few seconds without a primary.
- Idempotency for retryable business operations.
- Graceful draining of API/worker instances when needed.
- Monitoring for write/read failures.
- Handling for change stream resumption or resync.

### 13.1. Retries Do Not Make Every Operation Safe

Retryable writes apply only to supported operations and conditions; multi-step workflows with external side effects still require business-level idempotency.

### 13.2. Avoid Retry Storms

During a primary election, many application instances retrying immediately can worsen the situation. Use backoff with jitter and bounded retry attempts.

### 13.3. Reading from Secondaries

If the application reads from secondaries, monitor consistency and replication lag. A healthy secondary does not always match the primary's latest state at every instant.

### 13.4. Maintenance Windows and SLOs

Notify teams in advance and define the downtime budget. Rolling restarts minimize downtime, yet brief write interruptions can still occur during primary transitions.

## 14. Principles for Starting mongod

MongoDB should be started using the **same service manager/orchestrator** used to deploy it—never launch extra processes outside the management layer.

Before starting, verify:

- Correct executable and version.
- Correct config file.
- `dbPath`/volumes mounted.
- Correct file permissions and ownership.
- Replica set name and member identity.
- TLS certificates/keyfile/authorization.
- Network `bindIp`, port, and firewall.
- No other `mongod` holding the same `dbPath`.
- Disk and journal state consistent after the prior stop.

### 14.1. Never Start Two mongod Processes on the Same Data Directory

Two processes accessing the same `dbPath` violate locking and risk data corruption. If a service manager already manages `mongod`, never run a second `mongod` manually with that config.

### 14.2. mongod May Need Startup Recovery

After an unclean shutdown, WiredTiger/the storage engine may run recovery before serving requests. Do not mistake slow readiness during the first seconds for a hang and repeatedly restart the process.

### 14.3. Never Delete Lock/Journal Files Reflexively

If startup fails, read the logs and version documentation before deleting any files. Arbitrary deletions can destroy recoverability.

## 15. Starting and Stopping on Linux systemd

Example when `mongod` is installed and registered as the **`mongod`** unit:

~~~bash
sudo systemctl status mongod
sudo systemctl start mongod
sudo systemctl stop mongod
sudo systemctl restart mongod
sudo systemctl is-active mongod
~~~

Inspect logs:

~~~bash
sudo journalctl -u mongod -n 100 --no-pager
~~~

### 15.1. Service Names Can Vary

Some deployments use custom unit names, containers, or operators. Never assume `mongod` is always the unit name on every host.

### 15.2. systemctl restart Does Not Guarantee HA

If the target is a primary or a critical quorum voter, restarting can trigger an election and interrupt writes.

### 15.3. Stop Commands Must Have Preconditions

Before stopping:

- Right host/cluster?
- Right member role?
- Healthy majority remains?
- Replacement node / caught-up secondary available?
- Stakeholders notified / workload drained if needed?
- Able to restart with the exact config and volume?

### 15.4. Observe Startup

After starting, check service active status, logs, `hello`, `rs.status`, and application smoke tests. An `active` status alone does not prove the node reached the expected `SECONDARY`/`PRIMARY` state.

## 16. Manual Startup with a Config File

In a lab environment, you may run:

~~~bash
mongod --config /path/to/mongod.conf
~~~

**Do not** run this command on a host where systemd, containers, or an operator manages the same `dbPath`.

### 16.1. Why Use a Config File?

A config file holds `dbPath`, `net`, `replication.replSetName`, `security`, logging, and storage options. Omitting one option manually can start the node in the wrong role.

### 16.2. Do Not Copy Configs Between Nodes Without Adjusting

Some fields contain host-, path-, or port-specific settings. A config copied from another node may not be valid.

### 16.3. Check File Permissions

The user running `mongod` must have permission to read configs, certs/keys, and write to `dbPath`/logs. Never switch to running as root "just to make it work" without assessing the risk.

### 16.4. Logs Are the Diagnostic Source

Distinguish config parsing errors, port already bound, disk full, filesystem permissions, TLS key mismatch, and storage recovery.

## 17. Starting and Stopping on Windows

If MongoDB is installed as a Windows service named **MongoDB**:

~~~powershell
Get-Service -Name MongoDB
Start-Service -Name MongoDB
Stop-Service -Name MongoDB
Restart-Service -Name MongoDB
~~~

### 17.1. Verify the Service Name

The name may differ depending on installation. Check the services list or Services console first.

### 17.2. Do Not Mix the Service with a Standalone mongod.exe

If the Windows service holds the data directory, never launch a second `mongod.exe` pointing to the same `dbPath`.

### 17.3. Check Windows Event Log and MongoDB Log

If startup fails, inspect logs, config path, service account, file permissions, and TLS settings.

### 17.4. Windows Restarts Do Not Replace Rolling Maintenance

In a replica set, rebooting the OS of a voter takes that member offline. Account for majority, applications, and failover state before rebooting the host.

## 18. MongoDB in Docker

Example container status inspection:

~~~bash
docker ps
docker logs --tail 100 mongo-demo
~~~

Stopping with a graceful timeout:

~~~bash
docker stop --time 120 mongo-demo
~~~

Starting an existing container:

~~~bash
docker start mongo-demo
~~~

Container names and settings are illustrative.

### 18.1. Persistent Storage

If data resides only in an unmanaged writable layer, deleting/recreating the container loses data. Proper persistent volumes/storage are required.

### 18.2. docker stop Timeout

If MongoDB does not finish shutting down before the timeout, the runtime may force-kill it. Set a grace period suited to your workload, data size, and shutdown behavior; verify clean exit and health.

### 18.3. Do Not Use docker rm as a Restart Step

`docker rm` deletes the container definition; without proper volumes and deployment configuration, it can cause data loss.

### 18.4. Container Readiness

A running container does not guarantee a replica member is ready. Healthchecks should understand member roles and not restart a member merely because an election is briefly underway.

## 19. MongoDB on Kubernetes

With a StatefulSet:

~~~bash
kubectl get statefulsets
kubectl get pods -o wide
kubectl describe pod mongo-0
kubectl logs mongo-0 --tail=100
~~~

These are example inspection commands; substitute actual resource names for your deployment.

### 19.1. StatefulSets and Persistent Volumes

A Pod may be rescheduled, but must reattach the PVC matching its identity. Never delete a PVC when you only intend to restart a Pod.

### 19.2. Rolling Updates

If using a MongoDB Operator, follow Operator-supported workflows. If managing a StatefulSet manually, update sequentially, preserve majority, and verify readiness/replication before advancing.

### 19.3. Liveness and Readiness Probes

- **Liveness**: is the process hung or unrecoverable?
- **Readiness**: is the Pod ready to serve traffic matching its role?
- **Startup probe**: allows extended startup/initial sync time before liveness checks take effect.

An overly aggressive liveness probe can trigger a restart loop while `mongod` is performing normal recovery.

### 19.4. Termination Grace Period

Kubernetes enforces a graceful termination timeout. If set too short, the runtime can kill the process before shutdown completes.

### 19.5. PodDisruptionBudget Does Not Replace Quorum Awareness

A PDB limits Kubernetes voluntary disruptions, but does not verify replication lag, electability, or application state. The DBA/operator must still monitor majority.

## 20. MongoDB Atlas and Managed Environments

In Atlas or managed services, starting and stopping `mongod` is typically handled by the control plane.

### 20.1. Do Not Run Manual systemctl/mongod Commands

Do not SSH into managed deployment nodes to restart processes manually. Use official maintenance/upgrade workflows, monitoring, backups, and support channels.

### 20.2. What to Check Before Managed Maintenance

- Configured window and timezone.
- Backup/PITR status.
- Cluster health.
- Application driver compatibility.
- Upgrade target and FCV requirements.
- Impact on latency and elections.
- Alerting and communication.
- Search/index readiness where applicable.

### 20.3. Managed Does Not Guarantee Zero-Downtime for Every Change

Even managed rolling maintenance can cause transient connection errors, elections, or latency spikes. Applications still need retries, idempotency, and monitoring.

### 20.4. Pausing a Cluster

Some managed offerings support pause/resume or scale-to-zero under specific conditions. Do not assume these options exist on every tier, and never equate pausing a cluster with gracefully restarting a single member.

## 21. Stopping mongod Gracefully

The goal of graceful shutdown is to stop MongoDB via a supported code path, closing connections/resources and flushing storage state cleanly.

Methods depend on the environment:

- `systemctl stop mongod`.
- Windows `Stop-Service` for the MongoDB service.
- Container orchestrator sending a termination signal per policy.
- Server shutdown command in `mongosh` with appropriate privileges.

Example when connected directly to a `mongod` authorized to stop:

~~~javascript
db.getSiblingDB("admin").shutdownServer();
~~~

### 21.1. A Closed Connection Does Not Necessarily Mean Shutdown Failed

When `mongod` shuts down cleanly, the client connection drops and the shell may report a connection error. Verify shutdown status via the service manager, process list, and logs.

### 21.2. Do Not Run shutdownServer on a Router by Guesswork

`mongos` and `mongod` have different operational requirements. Follow your service manager/orchestrator and official deployment docs for routers.

### 21.3. Avoid SIGKILL / kill -9

A forced kill bypasses graceful shutdown, increasing recovery time and failure risk during active storage writes. Reserve it strictly for approved incident procedures with a runbook.

### 21.4. Do Not Use fsyncLock as a General Pause Button

Filesystem backup locking commands have specific semantics; never use them to "freeze the database for an easier restart" without a supported plan.

## 22. Coordination Sequence Before Stopping

A recommended sequence:

~~~text
Approved maintenance window
         |
         v
Validate cluster + backup
         |
         v
Check majority/replication lag
         |
         v
Notify / drain affected workload
         |
         v
Stop or step down selected member
         |
         v
Perform change
         |
         v
Start member
         |
         v
Wait for topology recovery
         |
         v
Database/app smoke tests
         |
         v
Only then advance to next member
~~~

### 22.1. Draining Has Multiple Meanings

- For `mongos` routers: stop routing new requests to the router being stopped.
- For applications: temporarily throttle batch jobs or requests sensitive to elections.
- For replica members: ensure the member is not serving as primary if maintenance requires stepping down.
- For hosts: pause unrelated platform tasks that could compete for resources.

### 22.2. Do Not Drain All Traffic Uncontrolled

Draining all routers simultaneously turns maintenance into an outage. Keep enough endpoints active to meet SLAs.

## 23. Rolling Restart in a Three Data-Bearing Member Replica Set

Suppose:

~~~text
Node A: PRIMARY
Node B: SECONDARY
Node C: SECONDARY
~~~

A safer plan than restarting all nodes at once:

1. Verify A/B/C are healthy with minimal lag.
2. Select C for maintenance first.
3. Stop C gracefully.
4. Apply C's patch/config change.
5. Start C.
6. Wait for C to return to `SECONDARY` and catch up.
7. Verify majority, reads/writes, and metrics.
8. Repeat for B.
9. With A still primary, prepare a controlled primary transition.
10. Step down A once an electable/caught-up secondary is ready at an appropriate moment.
11. Confirm the new primary and application recovery.
12. Perform maintenance on A now that it is no longer primary.
13. Wait for A to return healthy and caught up.
14. Run comprehensive smoke tests and close maintenance.

### 23.1. Never Assume "Node A Will Always Be Primary"

After elections, roles can shift. **Re-read topology** at every step before picking the next target.

### 23.2. Do Not Maintain Node B While C Is Still RECOVERING

If C is not yet healthy/caught up and B is stopped, the failure budget shrinks or vanishes.

### 23.3. Elections Can Still Cause Brief Disruption

A primary transition can cause transient write errors, aborted/retried transactions, or driver connection re-routing. Plan communication and application retry logic accordingly.

### 23.4. Secondary Priorities and Voters Affect Ordering

Do not apply the three data-bearing node workflow verbatim to replica sets with arbiters, hidden/delayed members, priority 0 nodes, or multi-zone setups without evaluating quorum and electability.

## 24. Controlled Primary Stepdown

Before stopping a primary, you can instruct it to relinquish leadership when topology allows.

On the primary with proper privileges and change approval:

~~~javascript
rs.stepDown(60);
~~~

The example argument specifies the stepdown duration; exact semantics and catch-up options vary by version.

### 24.1. Preconditions Before Stepdown

- An electable, up-to-date secondary exists.
- Majority is healthy.
- Applications handle transient errors.
- No non-retryable critical transactions/jobs are in flight.
- Election monitoring and rollback strategy are active.
- Exact primary and maintenance window are confirmed.

### 24.2. Do Not Use Force Stepdown by Default

Without an eligible secondary, normal stepdown may refuse to complete. Forcing stepdown can eliminate write availability; never force it without explicit evaluation and approval.

### 24.3. Verification After Stepdown

- A new primary has been elected.
- Drivers have discovered the new primary.
- Majority writes succeed.
- API error rates return to normal.
- The former primary transitioned to its expected role.

### 24.4. Do Not Trust Only the Command Response

A primary stepdown can drop the shell's connection. Read topology from a fresh connection or monitoring instead of relying solely on the command return status.

## 25. Expected vs. Abnormal Disruptions During Elections

### 25.1. Expected

- A brief window without a primary.
- Some operations retried or returning retryable errors.
- Elevated latency during driver server discovery.
- Long-running cursors/transactions needing application-level handling per semantics.

### 25.2. Unacceptable by Default

- Absence of a primary exceeding SLO.
- Loss of majority votes.
- Unrecoverable secondary replication lag growth.
- Data loss beyond RPO.
- Application retry storms.
- Disabling access control "to bypass errors".
- Uncontrolled forced reconfig.

### 25.3. When to Halt Rollout?

If election duration, error rates, p95 latency, or replication lag exceed defined thresholds, do not move to the next member. Diagnose the root cause first.

## 26. When a Replica Set Has Only Two Voters

With two voting members, majority is two.

~~~text
PRIMARY   voter
SECONDARY voter
~~~

Stopping either voter removes the majority needed for elections and majority availability.

### 26.1. Rolling Restart Is Not Automatically Safe

Do not reuse the three-voter procedure verbatim. Design a topology with an appropriate failure budget or schedule a maintenance window accepting downtime.

### 26.2. Arbiters Have Trade-Offs

A primary/secondary/arbiter setup alters election quorum, yet an arbiter stores no data and limits durability/majority write capabilities. Evaluate trade-offs carefully instead of adding an arbiter purely to "enable restarts" without analysis.

### 26.3. A Single Voter Cannot Provide Self-Healing HA

A standalone or single-voter setup has no automatic failover margin until replication/topology is expanded.

## 27. Sharded Clusters: Inspecting Every Tier

A sharded cluster consists of:

- Config Server Replica Set (CSRS).
- One or more shard replica sets.
- One or more `mongos` routers.
- Balancer and chunk migration mechanisms.

### 27.1. Never Maintain the Entire Cluster with One Blanket Restart

Stopping multiple shard members or config voters together can break routing or quorum across the cluster.

### 27.2. Maintain Each Replica Set Individually

Within each shard and the CSRS, maintain majority and wait for each member to return healthy before stopping the next.

### 27.3. mongos Routers Are a Separate Tier

With multiple `mongos` instances behind a load balancer, drain and restart sequentially to limit impact. With only a single `mongos`, stopping it disrupts applications even while shards stay healthy.

### 27.4. Config Servers Are Critical

Losing config server majority affects cluster metadata and operations. Never treat stopping a config server like stopping a stateless router.

### 27.5. Version-Specific Upgrade/Maintenance Order

MongoDB major-version upgrade procedures define strict sequences across CSRS, shard replica sets, `mongos`, and FCV. Follow the **official upgrade procedure for your source/target versions** rather than assuming one fixed order for every release.

## 28. Balancer and Chunk Migrations During Sharded Cluster Maintenance

Balancing and chunk migrations add I/O and network load or can affect operational consistency during certain changes.

### 28.1. Must You Always Stop the Balancer?

**No.** It depends on the change type and your MongoDB version's documentation. Some procedures require stopping balancing or waiting for migrations to finish; others do not.

### 28.2. Record Initial State

If a runbook requires changing balancer state, record its prior state so you only re-enable it at the end if it was originally enabled.

### 28.3. Environment-Specific Command Examples

On `mongos`, with appropriate privileges, administrative helpers such as:

~~~javascript
sh.status();
~~~

and when explicitly required by the runbook:

~~~javascript
sh.stopBalancer();
~~~

then restore per the recorded baseline:

~~~javascript
sh.startBalancer();
~~~

Helpers and semantics vary by version; verify that active migrations have stopped per documentation before proceeding. **Never stop the balancer in production just because you saw an example.**

### 28.4. Do Not Forget to Re-Enable Paused Features

Leaving the balancer disabled long after maintenance can accumulate uneven data distribution across shards.

## 29. Maintaining mongos Routers

A plan when multiple routers exist:

1. Check all healthy `mongos` endpoints.
2. Identify the exact router targeted for maintenance.
3. Drain it from the load balancer or service discovery.
4. Wait for in-flight requests to finish per policy.
5. Stop the router via its service manager.
6. Patch/configure/start the router.
7. Verify routing, auth, TLS, and sample APIs.
8. Return the router to the pool.
9. Monitor error rates.
10. Only then proceed to the next router.

### 29.1. Do Not Restart All mongos Simultaneously

Applications can lose all routing paths even when shards are healthy.

### 29.2. Stateless Routers Still Need Draining

Active connections, cursors, and transactions passing through `mongos` can be disrupted. Drivers/applications need proper retries alongside planned load balancer draining.

### 29.3. Connection Strings

Clients connecting to a sharded cluster should use the deployment's official router endpoints. Never point an application directly at a shard to "bypass `mongos`".

## 30. Maintenance Combined with MongoDB Upgrades

Upgrade maintenance spans multiple layers:

- MongoDB binary version.
- Database Tools and drivers.
- OS packages and kernel.
- TLS certificates and crypto configuration.
- Storage volumes.
- Replica set configuration.
- FCV.
- Schema/index/data migrations.

### 30.1. Avoid Bundling Too Many Unrelated Changes

Changing OS, MongoDB major version, drivers, auth, and index schemas simultaneously makes rollback and root-cause analysis very hard. Separate steps unless compatibility requires coordination.

### 30.2. Verify the Compatibility Matrix

Before upgrading:

- Supported upgrade path.
- FCV prerequisites.
- Driver and driver-feature compatibility.
- Sharded/replica set topology support.
- Operating system compatibility.
- Deprecated commands/settings.
- Authentication/TLS support.
- Backup/restore tooling compatibility.

### 30.3. Binaries and FCV Are Two Separate Steps

A rolling binary upgrade can keep the older FCV during the transition per documentation. Raising FCV prematurely can enable features that make downgrading difficult or unsupported.

### 30.4. Plan Rollback Before Changing FCV

Never treat downgrading as merely restarting with the old binary. Release-specific constraints exist, and data may already contain new features or formats.

## 31. Graceful Shutdown Does Not Eliminate Every Risk

Graceful shutdown lets the database exit cleanly, yet:

- Client connections are still closed.
- Long-running operations may be interrupted.
- Primary transitions can create a brief window with no writes.
- Jobs/transactions need retry handling.
- CDC consumers may need to resume.
- Backups/index builds may be affected.

### 31.1. Shutdown Duration Is Not Fixed

Duration depends on load, storage engine, I/O, and environment. Service manager timeouts must allow sufficient time for normal shutdown.

### 31.2. Do Not Set Kill Timeouts Too Short

If the runtime sends forced termination before graceful shutdown completes, subsequent startup recovery can take much longer.

### 31.3. Do Not Trust a Single Log Line

Monitor service exit status, process status, logs, and readiness upon return.

## 32. After Restart: Verifying Recovery and Role

After a restart:

1. Process runs with the expected binary and config.
2. No fatal startup errors.
3. Disk mounts and permissions are valid.
4. TLS/auth works.
5. `hello` responds.
6. Member rejoins the correct replica set.
7. Replica state returns to expected `SECONDARY`/`PRIMARY`.
8. Replication lag returns within thresholds.
9. Majority and writable primary are stable.
10. Required application reads/writes pass.

### 32.1. A SECONDARY in STARTUP2 Is Not Ready Like a Stable SECONDARY

Initial sync or recovery may still be in progress. Do not count the member as caught up simply because the process is alive.

### 32.2. Newly Started Nodes Can Experience Sync Load

Monitor disk/network load and any impact on the primary or secondary sync source.

### 32.3. Wait Before Proceeding

Maintenance tools/orchestrators need a real measured gate, not merely a fixed 30-second sleep.

## 33. Database Smoke Tests After Each Node

A lightweight check from the application or `mongosh`:

~~~javascript
db.adminCommand({ ping: 1 });
~~~

Against an approved test database:

~~~javascript
db.getSiblingDB("ops_smoke")
  .validation
  .findOne({ _id: "known-test-record" });
~~~

### 33.1. Read Probes Use Dedicated Test Data

Use a deterministic test/tenant record. Never query sensitive data and dump results into logs.

### 33.2. Write Probes

When write verification is required, use an authorized test collection/record and clean up afterward:

~~~javascript
const coll = db.getSiblingDB("ops_smoke").validation;

coll.updateOne(
  { _id: "maintenance-probe-001" },
  {
    $set: {
      checkedAt: new Date(),
      purpose: "maintenance-smoke"
    }
  },
  { upsert: true }
);

coll.findOne({ _id: "maintenance-probe-001" });

coll.deleteOne({ _id: "maintenance-probe-001" });
~~~

### 33.3. Never Run Unapproved Test Writes in Production

Probe writes can emit audit events, triggers, change streams, and side effects. Use them only under clear scope and policy.

### 33.4. App-Level Smoke Tests Matter More Than mongosh Admin Tests

An application using least-privilege credentials can fail even when an admin `ping` and insert succeed.

## 34. Verifying Application readConcern/writeConcern

MongoDB operations use varying read and write concerns.

### 34.1. Majority Write Readiness

An application requiring majority writes must confirm the topology can still satisfy that write concern while a member is stopped.

### 34.2. Secondary Read Readiness

`secondary` read preference can expose applications to stale reads or missing read endpoints during rolling maintenance. Do not test only the primary.

### 34.3. Causal Consistency

Workflows relying on read-your-writes or causal consistency must be verified against driver/session configuration.

### 34.4. Transactions

A primary stepdown can abort in-flight transactions. Applications must handle transient transaction errors per driver guidance rather than blindly retrying non-idempotent business side effects.

## 35. Change Streams, Job Queues, and Scheduled Tasks

Maintenance can interrupt `mongod` connections and streams.

### 35.1. Change Streams

Consumers must handle reconnects and resume tokens. If maintenance lasts longer than the oplog window or alters topology in specific ways, a resync may be required.

### 35.2. Scheduled Jobs

A worker halfway through 1,000 records needs checkpoints and idempotency instead of restarting blindly.

### 35.3. Outbox Pattern

If an event is committed while an email/payment has not yet executed, restarting workers may replay it. Use idempotency keys.

### 35.4. Pausing Jobs per Plan

Some maintenance windows require pausing heavy or sensitive batch jobs, though not every consumer needs to stop by default. Assess queue lag and SLAs.

### 35.5. Resuming After Database Readiness

Do not re-enable side-effecting jobs until the primary database meets consistency and readiness gates.

## 36. Controlling Active Backups and Snapshots

If a snapshot or backup is running:

- Verify whether node restarts are allowed per service documentation.
- Assess snapshot consistency under active writes.
- Check backup source and retention.
- Never abort a backup solely to shorten maintenance without decision-owner approval.
- Record any affected backup windows.

### 36.1. Can Backups Overlap Maintenance?

It depends on the mechanism. Some can coexist safely, while others must be avoided to reduce load or preserve consistency.

### 36.2. Do Not Equate Untested Snapshots with Verified Recovery

For high-risk changes, evidence from a restore drill/backup validation carries far more weight than a freshly reported success flag.

## 37. Stages of a Planned Maintenance Runbook

### Phase A — PREPARE

1. Communicate change ID, objective, and timing.
2. Assign owner, incident commander, and rollback approver.
3. Lock scope, node order, and dependencies.
4. Capture baseline metrics and expected error budget.
5. Verify backup/restore readiness.
6. Review compatibility and config diffs.
7. Verify primary, quorum, and lag.
8. Prepare smoke tests and alert dashboards.
9. Confirm stop/go criteria.

### Phase B — EXECUTE

1. Revalidate topology before each node.
2. Drain traffic or throttle workload in a controlled way.
3. Step down primary when required and preconditions are met.
4. Gracefully stop the exact target.
5. Apply the change per change script.
6. Start via the same manager/orchestrator.
7. Wait for role, replication, and index readiness.
8. Run database and application smoke tests.
9. Compare error rates/metrics against baseline.
10. Proceed only if all checks pass.

### Phase C — VERIFY

1. All members healthy.
2. Primary/majority stable.
3. Replication lag within thresholds.
4. Required reads/writes working.
5. API error rate and p95 back within SLO.
6. Change streams and jobs recovered.
7. Backups, search, and file references unaffected.
8. Balancer/router states restored to baseline where applicable.

### Phase D — CLOSE

1. Record start, end, election, and cutover timestamps.
2. Update the change record.
3. Archive logs/evidence stripped of secrets/PII.
4. Document deviations and incidents.
5. Open follow-up actions.
6. Exit maintenance mode and notify stakeholders.

## 38. Step-by-Step Gate Table

| Gate | Before Stop | After Start |
| --- | --- | --- |
| Exact cluster/host | Mandatory | Re-verified |
| Sufficient quorum | Mandatory | Mandatory |
| Secondary caught up | With election plan | Mandatory before next node |
| Disk free and mounts | Mandatory | Mandatory |
| TLS/auth | Baseline recorded | Re-tested |
| Service running | Healthy | Running |
| MongoDB role | Recorded | Stable |
| Application error rate | Within limit | Returned to baseline |
| Write/read probes | Baseline pass | Pass |
| Backup restore path | Available | Still available |
| Rollback | Ready | Used only if criteria met |

### 38.1. What If a Gate Fails?

Do not proceed automatically. Halt rollout, assess impact, and recover the member or roll back per runbook.

### 38.2. Timeouts

Set reasonable timeouts for startup, replication catch-up, and elections based on topology. A timeout is never an excuse to bypass checks and force success.

## 39. Abort Criteria and Rollback

A plan must define stop signals upfront:

- A member fails to start.
- Quorum is at risk.
- Primary election exceeds allowed time.
- Replication lag keeps growing.
- API error rate exceeds threshold.
- p95 latency breaches SLO continuously.
- Backup/restore safety conditions are lost.
- Data inconsistencies appear.
- Storage corruption or severe auth/TLS errors occur.
- Unexpected schema/FCV change occurs.

### 39.1. Config Rollback

If a config option change prevents a node from starting, you can revert to the verified config, provided the change has not introduced incompatible on-disk data state.

### 39.2. Binary Rollback

Downgrade only if **supported by MongoDB version documentation** and allowed by FCV/data feature constraints. Never install an older binary and restart arbitrarily.

### 39.3. Never Force Reconfig to "Rescue Quorum" Without Assessment

Forced reconfig raises the risk of data loss or split-brain. It is a specialized incident recovery operation requiring an owner and dedicated runbook.

### 39.4. Backup Restore Differs from Fast Rollback

A full data restore takes time and can lose writes after the recovery point. Choosing a recovery path must weigh RPO, RTO, and business impact.

## 40. Maintenance Under High Application Load

### 40.1. Choosing the Maintenance Window

Base timing on:

- Hourly traffic patterns.
- Batch jobs and billing cycles.
- Backup windows.
- Customer SLAs.
- Campaigns/peak events.
- Cross-region timezones.
- Sudden workload shifts.

### 40.2. Rate Limiting and Draining

Throttle batch workloads, pause application migrations, or shift load balancers, while avoiding unplanned changes to unrelated knobs.

### 40.3. Maintenance Does Not Always Mean Full Downtime

Replica sets and sharded clusters can be maintained via rolling strategies, yet brief transient errors can still occur. Never promise "zero downtime" without verifying driver and topology behavior.

### 40.4. Planned Maintenance vs. Emergency Maintenance

Urgent incidents may shorten approval chains, yet minimum safety gates still apply: right target, quorum, backup/recovery capability, coordinator, and logs.

## 41. Handling a mongod That Fails to Start

Diagnostic runbook:

1. Check process/service exit code.
2. Read the most recent logs.
3. Verify config path and syntax.
4. Check `dbPath`, volume mounts, and permissions.
5. Check ports and bind addresses.
6. Check TLS/keyfiles and certificates.
7. Check disk free space and inodes.
8. Check MongoDB binary/FCV compatibility.
9. Check for storage recovery errors.
10. Verify no other member or process is using the same data directory.
11. Halt rollout if quorum is impacted.
12. Escalate before modifying data files or running reconfig.

### 41.1. Never Delete WiredTiger/Journal Files Without Guidance

Deleting storage files arbitrarily can destroy recoverability.

### 41.2. Never Run mongod --repair Arbitrarily in Production

Repair has specific uses and risks—not a routine restart step. Have backups and follow a supported procedure.

### 41.3. Startup Recovery Can Take Time

Starting after an abrupt shutdown can require recovery; logs distinguish active progress from a true hang.

### 41.4. Kubernetes CrashLoopBackOff

Never simply raise liveness timeouts to mask disk, auth, or config errors. Inspect actual process logs and volume state.

## 42. When There Is No Primary

Investigate in order:

- Is there a healthy voting majority?
- Network partition or DNS/TLS failure?
- What state is each member in?
- Which secondaries are electable?
- What are replication lag and sync states?
- Is an upgrade or reconfig underway?
- Is the application connecting to the right replica set endpoints?

### 42.1. Do Not Just Restart All Nodes

Simultaneous restarts make behavior unpredictable, prolong recovery, and destroy diagnostic evidence.

### 42.2. Do Not Force Election/Reconfig by Default

If majority is lost, restore the failed members/network or execute an approved disaster-recovery procedure—never force potential data loss without assessment.

### 42.3. Capture Election Logs

Heartbeat timeouts, auth mismatches, quorum loss, and replication lag help pinpoint the root cause.

## 43. After Maintenance: Application Returns Connection Errors

Possible causes:

- Primary changed and the driver has not yet discovered it.
- Connection URI omits replica set hosts.
- Service account credentials changed.
- TLS CA/cert mismatch.
- Wrong DNS/hostnames.
- Different network allowlist.
- Stale connection pool.
- Incompatible driver.
- Drained `mongos` router not returned to service.

### 43.1. Never Fix by Disabling Authorization/TLS

Fix auth/TLS errors via proper credentials, certs, and configs—never weaken security "to start faster".

### 43.2. Inspect Driver Logs and SDAM Events

Driver Server Discovery and Monitoring (SDAM) events reveal primary transitions, network failures, and server selection timeouts.

### 43.3. Client Retry Behavior

Distinguish retryable failures, non-retryable failures, and operations with side effects outside MongoDB.

## 44. Java Application: Basic Readiness Probe

Example using the Java Sync Driver to run `ping` via `MongoClient`:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import org.bson.Document;

public class MongoReadinessProbe {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing MONGODB_URI"
            );
        }

        try (MongoClient client = MongoClients.create(uri)) {
            Document reply = client
                    .getDatabase("admin")
                    .runCommand(new Document("ping", 1));

            System.out.println(reply.toJson());
        }
    }
}
~~~

### 44.1. This Is Only a Connectivity Probe

`ping` does not verify a writable primary, majority, indexes, or business rules.

### 44.2. Do Not Create a New MongoClient per HTTP Request

`MongoClient` should normally be kept and reused across the application lifecycle to benefit from connection pooling and server discovery.

### 44.3. Least Privilege

Health probes do not need admin write privileges; grant appropriate minimal access for `ping` and readiness checks by design.

### 44.4. Do Not Log MONGODB_URI

Connection strings can contain credentials; never print them verbatim to logs.

## 45. Java Application: Business-Level Smoke Test

After a restart, the application can use an authorized test collection/tenant to verify a round trip:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.ReplaceOptions;
import org.bson.Document;

import java.util.Date;

public class MongoSmokeTest {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing MONGODB_URI"
            );
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> coll =
                    client.getDatabase("ops_smoke")
                          .getCollection("validation");

            String id = "maintenance-smoke-001";

            coll.replaceOne(
                    Filters.eq("_id", id),
                    new Document("_id", id)
                            .append("checkedAt", new Date())
                            .append("purpose", "maintenance"),
                    new ReplaceOptions().upsert(true)
            );

            Document readback = coll.find(
                    Filters.eq("_id", id)
            ).first();

            if (readback == null) {
                throw new IllegalStateException(
                        "Write/read smoke test failed"
                );
            }

            coll.deleteOne(Filters.eq("_id", id));

            System.out.println("PASS");
        }
    }
}
~~~

### 45.1. Run Only with Valid Privileges and Scope

This test writes and deletes data. Run it only in authorized environments where change streams/triggers will not cause unwanted side effects.

### 45.2. Do Not Test Only with Admin Credentials

Use the application account and matching write/read concerns to catch permission or execution issues.

### 45.3. Running After Failover

The application may need connection/operation retries per driver semantics. Never add unbounded retries without timeouts and idempotency.

## 46. Checking Indexes and Query Performance After Maintenance

A normal restart is not meant to alter index definitions, yet upgrades, config changes, or index maintenance can affect query behavior.

Example:

~~~javascript
db.orders.getIndexes();
~~~

Sample query:

~~~javascript
db.orders.find({
  tenantId: "tenant-a",
  status: "confirmed"
}).sort({
  createdAt: -1
}).limit(20).explain("executionStats");
~~~

### 46.1. Inspecting executionStats

- Is the expected index used?
- Any unplanned `COLLSCAN`?
- Any blocking `SORT`?
- What are `totalDocsExamined` and `totalKeysExamined`?
- How does execution time vary?

### 46.2. Cold Cache

The first queries after a restart may be slower because the WiredTiger cache is cold. Compare under equivalent warmed conditions.

### 46.3. Search / Vector Search

If the application relies on non-BSON indexes such as Atlas Search, test their readiness and sample queries separately. Never equate CRUD readiness with Search readiness.

## 47. Rehearsing Planned Maintenance in a Test Environment

An exercise can model a replica set with three data-bearing nodes:

~~~text
A: PRIMARY
B: SECONDARY
C: SECONDARY
~~~

Execute in an authorized lab:

1. Record current primary, member states, and baseline lag.
2. Create a test record.
3. Gracefully stop C via its service manager.
4. Observe majority and application behavior.
5. Start C.
6. Wait for C to return to `SECONDARY`/caught up.
7. Verify the test record exists.
8. Repeat for B.
9. Prepare primary stepdown per plan.
10. Verify the new primary and application writes.
11. Restart the old primary once preconditions hold.
12. Finish with all members healthy.
13. Record election duration, API errors, and observed lag.
14. Compare against SLOs.

### 47.1. Do Not Equate Lab with Production

Production differs in network, workload, index/data sizes, backups, and dependencies. Document simulation limits.

### 47.2. Observe Instead of Just Running Commands

The deliverable of a rehearsal is evidence of health transitions and pass/fail conditions, not merely a command list.

## 48. Minimal Maintenance Report

An illustrative template:

~~~yaml
maintenanceId: "MONGO-MAINT-2026-11-14-01"
environment: "staging"
cluster: "mongodb-rs-example"
changeType: "rolling-service-restart"
windowUtc:
  start: "2026-11-14T02:00:00Z"
  end: "2026-11-14T03:00:00Z"
preflight:
  majorityHealthy: true
  secondariesCaughtUp: true
  backupAvailable: true
  applicationSmokeBaseline: "PASS"
steps:
  - member: "mongo-c"
    beforeRole: "SECONDARY"
    afterRole: "SECONDARY"
    result: "PASS"
  - member: "mongo-b"
    result: "PASS"
  - member: "mongo-a"
    result: "PASS"
postflight:
  primaryElected: true
  replicationLagWithinLimit: true
  applicationReadWriteSmoke: "PASS"
  p95LatencyWithinSlo: true
decision: "COMPLETED"
issues: []
~~~

All values are illustrative.

### 48.1. Evidence to Archive

- Change/ticket ID and owner.
- Before/after topology snapshots.
- Backup/recovery evidence.
- Logs from starts, stops, and elections.
- Node versions and config changes.
- Replication lag and metrics timeline.
- Application smoke outputs.
- Abort/rollback decisions if any.

### 48.2. Strip Secrets and PII

Never attach passwords, private keys, raw connection URIs, or unnecessary user data.

### 48.3. Follow-Up Actions

Any slow recovery or latency spike must have an owner, deadline, and concrete follow-up action.

## 49. Common Operational Mistakes

| Mistake | Consequence |
| --- | --- |
| Treating an active service as ready | Misses election, auth, or data errors |
| Running only `ping` before maintenance | Ignores quorum and lag |
| Restarting all members together | Loses majority / causes downtime |
| Maintaining the next secondary before the previous one catches up | Shrinks failure budget |
| Stopping primary without checking electable secondaries | Election fails |
| Forcing stepdown/reconfig without assessment | Loses availability or data |
| Skipping backup verification | No reliable recovery path |
| Treating replication as backup | Cannot recover accidental deletions |
| Ignoring oplog window | Secondary requires initial sync |
| Not verifying target cluster | Modifies production by mistake |
| Running `mongod` twice on the same `dbPath` | File locking / corruption risk |
| Deleting journal/storage files on startup error | Destroys recoverability |
| Using `kill -9` instead of graceful stop | Slow recovery, higher risk |
| Running `systemctl restart` on primary without a plan | Write interruption |
| `docker stop` timeout too short | Forced termination |
| Deleting PVC when restarting a Pod | Loses persistent data |
| Overly aggressive liveness probe | `CrashLoop` |
| Assuming PDB guarantees Mongo quorum | Fails to verify votes and data health |
| Stopping all `mongos` simultaneously | Application loses all routers |
| Overlooking config server majority | Sharded cluster operations fail |
| Disabling balancer and forgetting to re-enable | Shard imbalance |
| Changing FCV together with restart | Downgrade is no longer simple |
| Not verifying driver retries | Transient errors escalate to outage |
| Retrying non-idempotent side effects | Duplicate payments/emails |
| Not monitoring change streams | Event loss or duplication |
| Not warming/checking indexes | Prolonged API p95 increase |
| Smoke-testing only with admin user | Misses app permission bugs |
| Ignoring errors because the service looks online | Lacks business readiness |
| Arbitrarily rolling back binaries | Incompatibility/corruption risk |
| Missing stop/go criteria | Rollout continues despite instability |
| Not recording timelines/evidence | Hard to audit and improve |

## 50. Readiness Exercises

### Exercise 1 — Process vs. Database Readiness

A `mongod` service is active, yet `rs.status()` shows no `PRIMARY`. Can the application be marked writable? What must be checked?

### Exercise 2 — Ping Success

`mongosh` `ping` returns `ok:1`, yet the booking creation API times out. List at least six causes not detected by `ping` alone.

### Exercise 3 — Four-Layer Readiness

Design four signals—liveness, database readiness, application readiness, and maintenance readiness—for a three-voter replica set.

### Exercise 4 — Secondary Lag

Secondary B is lagging by 10 minutes. Should you step down primary A for immediate maintenance? Why or why not?

### Exercise 5 — Oplog

Node C stays offline longer than the oplog window. What can happen upon return, and how does it affect maintenance duration?

### Exercise 6 — Health Thresholds

Select thresholds for p95 latency, error rate, replication lag, and free disk for a demanding application; explain why thresholds depend on baseline/SLOs rather than one universal number.

## 51. Quorum and Replica Set Exercises

### Exercise 7 — Majority

Calculate the majority for replica sets with 1, 2, 3, 4, 5, and 7 voting members.

### Exercise 8 — Three Voters

A/B/C are healthy. You stop C, and then B fails before C returns. What happens to majority and writes?

### Exercise 9 — Arbiter

A replica set consists of a primary, a secondary, and an arbiter. Why does an arbiter help with voting yet fail to replace a data-bearing secondary for durability?

### Exercise 10 — Rolling Restart

Write a runbook for A `PRIMARY`, B/C `SECONDARY`; specify gates after each node and the stepdown plan for A.

### Exercise 11 — Node Roles Change

After restarting B, A is no longer `PRIMARY`. Why must you not continue restarting nodes based on the role list captured at the start?

### Exercise 12 — Force Stepdown

A primary refuses to step down because no eligible secondary exists. Why should you not default to forcing it?

## 52. Deployment Environment Exercises

### Exercise 13 — systemd

In a lab, use `systemctl status/start/stop` and `journalctl` to inspect `mongod`. What must be verified beyond `active` status?

### Exercise 14 — Windows

A MongoDB Windows service fails to start because the service account cannot read the keyfile. What are the verification and corrective steps?

### Exercise 15 — Docker

A container is deleted/recreated and data disappears. What volume design issue could cause this?

### Exercise 16 — Kubernetes

A StatefulSet Pod is performing initial sync, yet the liveness probe keeps restarting it. Improve startup/liveness/readiness and termination settings.

### Exercise 17 — Atlas

Why should you not apply `systemctl` or `mongod --config` directly to an Atlas-managed cluster? What should you monitor during a maintenance window?

### Exercise 18 — Single mongos

A sharded cluster has three healthy shards but only one `mongos`. If this router is stopped, what errors does the application face?

## 53. Sharded Cluster Maintenance Exercises

### Exercise 19 — Config Server Majority

A Config Server Replica Set has three members. One is already down; the team wants to restart a second member. Analyze the risk and Go/No-Go decision.

### Exercise 20 — Balancer

A runbook requires pausing the balancer. What must be recorded before and after to avoid leaving it disabled or disrupting migrations?

### Exercise 21 — Shard Restart

Is it safe to maintain shard A's secondary and shard B's secondary at the same time to save time? Which quorum domains must be considered?

### Exercise 22 — mongos Rolling

Design a router drain/restart/verify workflow for a cluster with four `mongos` instances behind a load balancer.

### Exercise 23 — Upgrade and FCV

Why do binary upgrades and `setFeatureCompatibilityVersion` need separate planning? What are the rollback limitations?

## 54. Application and Failure Recovery Exercises

### Exercise 24 — Retry Storm

A primary election causes 200 API instances to retry simultaneously. What retry limits, backoff, and idempotency measures apply?

### Exercise 25 — Transaction Abort

A booking transaction is aborted during primary stepdown. Design error handling and retries so two orders or duplicate payments are never created.

### Exercise 26 — Change Stream

A consumer fails to resume after prolonged maintenance. Propose a checkpoint, resync, and deduplication workflow.

### Exercise 27 — CrashLoop

`mongod` fails to start after a restart. Write a checklist of log, config, storage, and TLS checks before touching any data files.

### Exercise 28 — No Primary

A replica set loses its primary after restarting one member. Why should you not restart all nodes? What signals must be investigated?

### Exercise 29 — Smoke Test

Write a Java Sync Driver `ping` check and a read/write smoke test against a staging dataset; explain the limits of each test.

### Exercise 30 — Abort

Maintenance on the first node succeeds, yet replication lag climbs steadily and API p95 breaches SLO. What is the next decision and why?

## 55. Concise Operational Checklist

### Before Change

1. Confirm environment, cluster, host, and member identity.
2. Confirm maintenance window and change approval.
3. Record topology, versions, and role inventory.
4. Confirm healthy quorum/majority.
5. Confirm electable/caught-up secondary if stepdown is needed.
6. Verify lag, oplog window, and disk headroom meet criteria.
7. Verify backup/PITR and restore procedures are available.
8. Confirm driver/application retry behavior.
9. Prepare monitoring, alerts, and smoke tests.
10. Clarify abort/rollback approvers and stop conditions.

### During Change

11. Drain traffic/workloads as needed.
12. Stop gracefully via the appropriate manager/orchestrator.
13. Never stop too many voters or routers simultaneously.
14. Never modify storage/journal files directly.
15. Never force elections or reconfigs without approval.
16. Wait for the member to return to a healthy role and catch up.
17. Verify majority reads/writes and application smoke tests.
18. Record timestamps and events before advancing.

### After Change

19. Primary and majority are stable.
20. Replication lag is back within thresholds.
21. All members match expected roles and versions.
22. Authentication/TLS and application permissions work.
23. API latency, error rate, and throughput meet SLOs.
24. Change streams, queues, and jobs have recovered.
25. `mongos`, balancer, and search indexes are in their required states.
26. Backups and alerts remain enabled.
27. Log, metric, and smoke-test evidence is archived.
28. Follow-up actions have owners and deadlines.

## 56. Maintenance Runbook Template

~~~text
CHANGE:
  Mongod controlled rolling maintenance

ENVIRONMENT:
  Approved cluster and nodes

OWNER:
  DBA/Platform lead

PRECHECK:
  Cluster identity confirmed
  Backup verified
  Voting majority healthy
  Secondary lag within threshold
  Disk/network healthy
  Application retry/drain ready

EXECUTION:
  Revalidate topology per member
  Drain affected traffic
  Graceful stop
  Apply approved change
  Start through service manager/operator
  Wait for SECONDARY/PRIMARY stable state
  Verify replication catch-up
  Run database and application smoke
  Continue only after pass

ABORT IF:
  No healthy primary beyond limit
  Quorum at risk
  Lag or API error above threshold
  Node cannot start
  Unplanned data/security change

POSTCHECK:
  All members healthy
  Required indexes/search ready
  Majority writes and critical reads pass
  API p95 and error rate back within SLO
  CDC/background jobs reconnected
  Backup, balancer, alerts restored

CLOSE:
  Record timestamps and logs
  Document changes and deviations
  Notify stakeholders
  Create corrective actions
~~~

## 57. Conclusion

Starting, stopping, and maintaining MongoDB **must never be treated as a single-process operation**. The true objective is keeping the system available within defined RPO, RTO, and SLO boundaries.

Key principles:

- **Distinguish liveness from readiness**: an active process and successful `ping` do not prove business read/write capability.
- **Verify majority, replication lag, and electability** before stopping any replica set member.
- **Prefer rolling maintenance**, waiting for each node to return healthy and caught up before advancing to the next.
- **Stop gracefully** via service manager, orchestrator, or supported commands; never use forced kills as routine practice.
- **Perform controlled primary stepdowns** and plan for transient errors during elections.
- **For sharded clusters**, manage config servers, shards, `mongos`, and the balancer distinctly, following the official version upgrade sequence.
- **For Atlas/Kubernetes**, use the control plane or Operator rather than manual commands that bypass lifecycle management.
- **Never change binaries, FCV, schemas, and network settings all at once without a plan**.
- **After every start, validate both database and application**: roles, TLS, writes, query performance, CDC, and business smoke tests.
- **Maintain abort/rollback gates and operational evidence**, never continuing a rollout solely because the previous command exited with 0.

**A maintenance cycle is complete when the system returns to verified readiness—not when the final restart command finishes.**

## References

- [MongoDB Manual — Administration](https://www.mongodb.com/docs/manual/administration/)
- [MongoDB Manual — Replica Set Deployment and Maintenance](https://www.mongodb.com/docs/manual/replication/)
- [MongoDB Manual — Replica Set Elections](https://www.mongodb.com/docs/manual/core/replica-set-elections/)
- [MongoDB Manual — rs.status](https://www.mongodb.com/docs/manual/reference/method/rs.status/)
- [MongoDB Manual — rs.stepDown](https://www.mongodb.com/docs/manual/reference/method/rs.stepDown/)
- [MongoDB Manual — shutdown](https://www.mongodb.com/docs/manual/reference/command/shutdown/)
- [MongoDB Manual — ServerStatus](https://www.mongodb.com/docs/manual/reference/command/serverStatus/)
- [MongoDB Manual — Sharding](https://www.mongodb.com/docs/manual/sharding/)
- [MongoDB Manual — Upgrade Procedures](https://www.mongodb.com/docs/manual/release-notes/)
- [MongoDB Manual — Backup and Restore](https://www.mongodb.com/docs/manual/core/backups/)
- [MongoDB Atlas — Cluster Maintenance](https://www.mongodb.com/docs/atlas/)
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/)
