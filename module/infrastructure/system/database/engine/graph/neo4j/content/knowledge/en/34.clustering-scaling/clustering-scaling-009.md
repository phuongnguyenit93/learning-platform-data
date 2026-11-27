# Monitoring, Backups, and Failure Drills in a Cluster

## 1. A Multi-Replica Neo4j Cluster Can Still Suffer Incidents

Neo4j lets you deploy graph databases in a **cluster** to improve availability and scale read capacity in supported configurations. Data remains modeled with **nodes, relationships, and properties**, queried with **Cypher**, and accessed by Java applications via the **Neo4j Java Driver** or Spring Data Neo4j.

However, running multiple servers does not solve every failure mode:

- An unresponsive member can cause connections targeting that server to fail.
- Losing enough consensus participants can **prevent the cluster from committing writes** even while several servers stay running.
- Applications may reach the bootstrap endpoint yet receive a routing table containing unreachable hostnames.
- A read query on a lagging replica may miss recently committed changes unless an appropriate consistency mechanism is used.
- An accidental `DELETE` or bad business mutation replicates to the remaining members.
- Incidents hitting an entire storage region, admin account, or shared config can impact the whole cluster.
- Having backups that have never been restore-tested can still fail recovery within deadlines.

Hence three coordinated layers of control are required:

1. **Monitoring:** detect anomalies across the cluster, databases, transactions, and applications.
2. **Backup and restore:** maintain independent backups and verified procedures to rebuild after data loss or corruption.
3. **Failure drills:** proactively verify assumptions around failover, routing, recovery time, data integrity, and on-call ownership.

> **Core principle:** Replication improves availability against certain infrastructure faults; **backups protect data recoverability**; drills prove both mechanisms actually work. Never use any one mechanism as a total substitute for the other two.

Examples in this lesson focus conceptually on Neo4j Enterprise 5.x and newer architectures. **Command names, privileges, backup settings, cluster limits, and server roles vary by version/edition.** Before deploying, verify documentation for your exact running version; never run operational commands in production solely because they appear in a lesson.

## 2. Understanding Cluster Topology and Failure Blast Radius

Across modern Neo4j cluster models, distinguish:

| Component | High-level role | What to observe |
|---|---|---|
| **Server / member** | Neo4j process participating in the deployment | Liveness, CPU, heap, page cache, disk, network |
| **Primary** | Replica participating in data maintenance and write consensus per topology | Availability, consensus health, commit latency |
| **Secondary** | Replica supporting read scaling / availability goals | Data catch-up lag, read queries, resources |
| **Database** | Logical graph database distributed according to topology | Status, read/write capability, replication |
| **Writer / leader** | Point coordinating writes for that database at a given time | Role changes, latency, failover |
| **System database / control plane** | Manages metadata/topology and administrative functions per version | System state, config changes, privileges |
| **Client routing** | Java Driver mechanism discovering and picking endpoints | Routing table, DNS, TLS, read/write connectivity |

Different Neo4j releases may vary terminology, role counts, and database allocation policies. **Never equate `PRIMARY` in a status output with assuming that server is always the current writer for every database.** Writer roles can vary per database and over time.

### 2.1. Quorum and Write Capability

Under majority consensus, a three-member voting group can generally lose one member while retaining a majority **provided all other topology conditions hold**. When only one of three members remains reachable and cannot contact the other two, safe write commits generally cannot continue.

~~~text
Normal state:
    Primary A ----- Primary B ----- Primary C
         \              |              /
            sufficient consensus members

One member lost:
    Primary A ----- Primary B       Primary C (offline)
         |
     can still retain majority, depending on topology

Majority lost:
    Primary A          Primary B (offline)  Primary C (offline)
         |
      no majority left to commit writes safely
~~~

This model illustrates the principle—not a guarantee that every three-server setup fails over identically with the same latency. Write capability also depends on database state, networking, election, topology, and version.

**Secondaries are not an automatic substitute for write quorum.** Even with many read-only replicas, the cluster still requires specific consensus conditions to allow writes.

### 2.2. Failure Blast Radius Must Be Stratified

- **One Neo4j process:** crash, out-of-memory, exhausted file descriptors.
- **One host / VM / Pod:** restart, CPU starvation, full disk.
- **One availability zone:** zone-wide network or storage outage.
- **One subnet / VPC:** DNS, routing, firewall, or network partition.
- **One database:** stopped, failed, missing replicas, or data corruption.
- **Entire cluster:** shared configuration mistake, simultaneously expired certificates, operator error.
- **Integrating systems:** brokers/Java services keep sending requests even when the database loses write capability.

Monitoring and drills should include scenarios for each tier rather than lumping everything into “Neo4j is down.”

## 3. Defining What Counts as a Healthy System

An endpoint returning `200 OK` or a successful `RETURN 1` **does not prove** every database and application path is healthy.

Evaluate health across four layers:

| Layer | Question | Example measurements |
|---|---|---|
| **Infrastructure** | Do servers and networks have sufficient resources? | CPU, memory, free disk, I/O, TCP, DNS |
| **Neo4j / database** | Is the database online with valid topology and processing transactions? | DB status, transaction errors, replication |
| **Driver and application** | Are Java services connecting, routing, and retrying properly? | Routing errors, pool waits, `executeRead`/`executeWrite` |
| **Business** | Are critical operations completing with accurate results? | Order creation, relationship reads, data reconciliation |

A cluster may report every member process “up” while users fail to write due to quorum loss or mis-advertised DNS. Therefore, **process health, database health, and business health are not the same**.

### 3.1. Define SLIs/SLOs Before Creating Alerts

An **SLI** is a measured quantity, such as write transaction success rate or read latency p99. An **SLO** is the target chosen by product/operations teams.

Illustrative example:

~~~text
Service: Graph Order API
SLI-1: ratio of write requests confirmed successful
SLI-2: p95/p99 latency of Order creation
SLI-3: ratio of read queries succeeding after writes
SLI-4: projection update freshness delay
SLO: chosen from product requirements, not arbitrary thresholds
~~~

**Never pick one universal threshold for every Neo4j cluster.** Real-time services, analytical stores, and ingestion pipelines have different SLOs.

## 4. Inspecting Cluster Status with Neo4j Tools

In Neo4j versions supporting the corresponding admin commands, start with:

~~~cypher
SHOW DATABASES;
~~~

This lists databases alongside status/role columns exposed by your version and privileges.

In environments supporting server management via Cypher:

~~~cypher
SHOW SERVERS;
~~~

Requires proper privileges and a supported version/edition. Column schemas can vary across Neo4j versions; when scripting metric collectors, **never hardcode column names from another version**.

Inspect running transactions (with sufficient privileges):

~~~cypher
SHOW TRANSACTIONS;
~~~

This aids investigation of long-running transactions, lock waits, or active queries. **Never paste raw dumps into public tickets** if they contain query text, user details, or sensitive parameters.

### 4.1. States to Distinguish

- Member/DB is online and accepting connections.
- Database is requested online, yet current status is not online.
- One server is offline, while the database remains readable/writable via other servers.
- Application fails to fetch a routing table, or the routing table contains unreachable addresses.
- Reads still succeed while writes fail.
- Writes still commit, yet latency spikes due to contention or a writer switch.
- Backup service is online, yet backup jobs fail due to disk/permissions/networking.

Never rely on a **single** health check on one IP as the health signal for the whole cluster.

### 4.2. Point-in-Time Status Does Not Replace History

`SHOW DATABASES` at time T might show the database online. It does not reveal that the database lost its writer three minutes ago, how many elections happened, or which requests timed out.

Keep time series and event timelines:

~~~text
09:10:00  Member B unresponsive
09:10:05  Driver begins reporting routing/write failures
09:10:18  New writer active and committing
09:10:22  API write success rate returns to target
09:11:00  Reconcile received vs. committed business commands
~~~

Timestamps above are **illustrative**, not standard Neo4j failover timings. Real timings must be measured in drills.

## 5. Monitoring Resources on Every Server

Monitor **each member individually**, not just cluster totals:

| Category | Metrics to watch | Why it matters |
|---|---|---|
| CPU | Utilization, saturation, VM steal time | Queries/GC slow down under CPU contention |
| Heap / JVM | Used heap, GC pauses, GC frequency | Memory pressure causes timeouts/OOM |
| Page cache | Size, hit ratio, evictions | Governs disk I/O during node/relationship traversals |
| OS memory | Available RAM, swap/memory pressure | RAM exhaustion slows the entire server |
| Disk | Free bytes, inodes, IOPS, latency, queue depth | Transaction commits and backups are I/O-sensitive |
| Network | Throughput, errors, packet loss, RTT | Impacts routing and data replication |
| Process | Restarts, open files, thread pools, liveness | Detects crashes or resource limits |
| Backup destination | Free capacity, write errors, upload time | Backup success depends on destination health |
| Container | CPU throttling, memory limits, OOMKilled | cgroup limits may differ from host capacity |

### 5.1. Heap and Page Cache Are Not the Same Thing

Neo4j uses JVM heap for Java structures and **page cache** for graph store data on disk. If latency spikes because page cache is undersized, raising heap alone may not help. Conversely, over-allocating page cache can starve the OS and JVM heap.

When tuning memory, review:

- Counts of nodes, relationships, indexes, and store size.
- How much of the graph typical queries traverse.
- Cache warming behavior after restarts.
- GC pauses and pressure.
- Memory headroom for backups, GDS projections, and ingestion jobs.

Never apply a fixed RAM formula blindly across all workloads.

### 5.2. Disk Exhaustion Is a Top-Priority Alert

Databases and transaction logs require write space. If a member runs out of disk, it suffers write failures, backup failures, recovery failures, or falls behind the cluster.

Alert well before disk hits critical thresholds based on **growth rate**, remaining space, and operational remediation time.

**Never manually delete transaction logs, store files, or internal Neo4j files just to free space.** Those actions can destroy recoverability or consistency. Always use procedures supported by your Neo4j version.

## 6. Monitoring Replication and Write Availability

In a cluster, replication/synchronization metrics must be interpreted per database’s role and topology:

- Are enough members available to meet write conditions?
- Is the writer changing frequently?
- Are replicas **keeping up** with commit state?
- Is one member lagging persistently due to network, CPU, or disk?
- Is a node repeatedly evicted/rejoining, or is a database flapping states?
- Is there divergence between business databases and system/control-plane components?

**Metric names and replication mechanics depend on Neo4j version.** Never assume a single universal counter or unit like “replication lag = X milliseconds” across every version. When wiring exporters, verify each metric’s meaning, server/database scope, and whether it is suitable for paging alerts or only informational context.

### 6.1. Stale Reads Differ from Failed Reads

Example:

~~~text
T1: write "Order O1 = PAID" commits successfully
T2: another read session lands on a lagging server
T3: that session may miss the new data without causal consistency
~~~

If business rules need **read-your-writes** across sessions, the Java Driver offers **bookmarks/causal consistency** depending on API and version; applications should pass bookmarks at the proper scope rather than assuming every subsequent read hits the commit server.

Also distinguish “seeing my own prior write” from “all clients instantaneously seeing the exact same global state.” Causal consistency does not turn the whole cluster into a single synchronous distributed transaction across unrelated tasks.

### 6.2. Monitor the Application for Both Reads and Writes

Track separately:

- `executeRead` success/latency.
- `executeWrite` success/latency.
- Retry / transaction attempt counts.
- Errors acquiring writer/routing endpoints.
- Insufficient-servers or database-unavailable errors.
- Business requests received, succeeded, and deduplicated.

During an incident, **succeeding reads** can keep aggregate dashboards looking green while **writes are completely down**. Splitting read and write SLIs catches this immediately.

## 7. Collecting Metrics, Logs, and Traces Safely

On supported Neo4j Enterprise versions, metrics can be exported to Prometheus or compatible platforms. Setting names and support levels vary by version.

Illustrative **example for Neo4j 5.x settings** (verify against your actual version):

~~~properties
# neo4j.conf — illustrative only, not a complete production config.
server.metrics.enabled=true
server.metrics.prometheus.enabled=true
server.metrics.prometheus.endpoint=127.0.0.1:2004
~~~

`127.0.0.1:2004` binds the metric endpoint strictly to the network namespace loopback. If the monitoring agent lives in another container/Pod, configure a protected internal network path; **never change it arbitrarily to public `0.0.0.0`**.

Before deploying, verify:

1. Exact Neo4j version and edition.
2. Whether the metric settings are supported.
3. Whether metric endpoints require extra network/auth policies.
4. Whether the collector has proper permissions and routes.
5. Whether metric labels include database/member with bounded cardinality.
6. Whether collected metrics actually suffice to compute defined SLIs.

### 7.1. Never Collect Sensitive Data Just for Debugging

Keep metrics aggregated with bounded labels such as `database`, `operation`, and `outcome` per policy. Never put emails, customer IDs, Cypher parameter maps, or request bodies into metric labels, trace spans, or alerts.

For query/transaction logs, verify redaction/parameter-logging policies per version; shared dashboards must never leak data that viewers are unauthorized to read directly in the graph.

### 7.2. Layered Observability

~~~mermaid
flowchart TD
  A["Neo4j members"] --> B["Metrics/Logs Collector"]
  C["Java Driver / Spring Service"] --> B
  D["Proxy / DNS / LB"] --> B
  E["Backup / Restore Jobs"] --> B
  B --> F["Read-write dashboard + RPO/RTO evidence"]
  B --> G["Alerts / Incident process"]
~~~

A proxy routing bug can block application connectivity even when both Neo4j servers and query metrics look normal. Therefore collectors need signals from **both infrastructure and clients**.

## 8. Building a Minimum Viable Operational Dashboard

An on-call dashboard should immediately answer:

| Group | Suggested widgets | Alerts to distinguish |
|---|---|---|
| Topology | Members up, databases online, role statuses | Member down vs. database unmet topology |
| Write availability | Write success/failure per database | Missing writer or lost quorum |
| Read availability | Read success/failure | Unreachable replica/endpoint |
| Latency | p50/p95/p99 by read/write and business endpoint | Rising tail latency |
| Routing / client | DNS/TLS/routing errors, pool waits, retries | Bootstrap works while member endpoints fail |
| Replication | Version-supported data catch-up indicators | Sustained member lag/stall |
| Storage | Free disk, I/O, transaction log growth | Approaching disk exhaustion |
| Backup | Last successful backup, backup age, integrity check | No fresh backup within RPO window |
| Restore drills | Last restore test, duration, verification result | Unverified backup recoverability |
| Business invariants | Processed request reconciliation, orders missing edges | Duplicate writes or state drift after retries |

### 8.1. Every Alert Must Be Actionable

Never configure “CPU above threshold” without specifying who acts and how. A good alert includes:

- Affected database/server.
- Start time and violation duration.
- Related SLI/SLO.
- Priority and impact scope.
- Link to the remediation runbook.
- On-call owner or team.
- Recovery verification signal.

High CPU while request success rate and latency stay within SLO warrants a different urgency than **100% write failures**.

### 8.2. Backup Alerts Must Not Rely Solely on Exit Codes

A backup process can exit 0 even when:

- The backup artifact was never copied to an independent storage zone as planned.
- Destination storage filled up and the latest copy remained on a temporary host.
- Secrets/certificates needed to decrypt the backup were misplaced.
- Files exist, yet restores fail due to missing metadata/permissions.
- The backup repository was corrupted or deleted by the same production admin account.

Dashboards should distinguish **backup job completed**, **artifact verified**, **offsite copy verified**, and **restore drill passed**.

## 9. Replication Is Not a Backup

A cluster with three copies of a database can survive losing one server under defined conditions. Yet replication also **replicates mistakes**:

~~~text
App executes erroneous DELETE
       |
       v
Writer commits DELETE
       |
       v
Transactionally valid change replicates
       |
       v
All replicas now lack the deleted data
~~~

Consistent replicas do not guarantee business-correct data. To return to a point before an erroneous deletion, you need **backups or a pre-designed historical recovery mechanism**.

| Mechanism | Primary protection | Does not solve automatically |
|---|---|---|
| Cluster replication | Certain member/host failures and continuous read/write | Accidental deletes, ransomware, committed logic bugs |
| Independent backups | Restoring data from saved checkpoints | Instant automatic failover |
| Storage snapshots | Platform-level volume snapshots | Application/database consistency if taken improperly |
| Transaction logs / supported recovery | Recovery to supported points/boundaries | Cannot protect all changes if retention/chain breaks |
| Restore drills | Proves a viable recovery path | Does not prevent incidents |
| Outbox / idempotency | Reduces drift from retries/duplicates and integration | Does not restore an entire lost database |

**Never treat VM snapshots, copying a live data directory, or manual PVC clones as consistent Neo4j backups** unless following supported product and storage procedures.

## 10. Setting RPO, RTO, and Recovery Scope Targets

Two targets must be agreed upon with the business before choosing a backup strategy:

- **RPO (Recovery Point Objective):** acceptable data loss after an incident, usually expressed as a time window.
- **RTO (Recovery Time Objective):** allowed time from service disruption until service is restored to acceptable operation.

Illustrative example:

~~~text
Service outage at:        10:00
Latest recoverable
data point:               09:55
Service restored at:      10:17

Data loss window:         ~5 minutes
Outage duration:          ~17 minutes
~~~

This illustrates measurement, **not default Neo4j guarantees**. If additional transactions are replayed from logs after the backup mark or application streams replay, actual recovery points differ. Measure by **verified committed data**, not merely backup file timestamps.

### 10.1. What Must RPO and RTO Include?

RTO should not measure only the restore CLI runtime. Restoring application service also requires:

1. Provisioning compute, networking, volumes, and secrets.
2. Accessing the backup artifact.
3. Restoring the database and checking consistency.
4. Configuring cluster/topology per supported procedures.
5. Restoring DNS/proxy/TLS and application privileges.
6. Verifying reads/writes, indexes, and critical queries.
7. Reconciling confirmed vs. pending transactions.
8. Reopening traffic against acceptance criteria.

Saying “restore took 4 minutes” can hide 40 minutes spent fixing networking or auth afterward.

### 10.2. Business Contracts Drive Targets

An internal document search graph may tolerate rebuilding from source, whereas an orders/rewards graph needs stronger protection for acknowledged commits. Acceptable data loss and downtime must be **signed off by business owners**.

Never promise RPO = 0 without the concrete architecture, budget, authoritative sources, and tested procedures to back it up.

## 11. Designing Backup Policies for Single and Multi-Database Deployments

Before writing backup scripts, inventory:

- Active databases and which ones are authoritative data sources.
- Which databases hold rebuildable data versus irreplaceable data.
- Neo4j version/edition and supported backup mechanisms.
- Backup service addresses and network permissions.
- Store/index/log sizes and growth rates.
- Independent storage, encryption, and secret lifecycles.
- Full/incremental schedules where features and versions permit.
- Retention and copy counts.
- Immutable/offsite storage rules against accidental deletion and ransomware.
- Artifact verification and restore drill procedures.
- Configuration/role/secret metadata requiring separate protection.

### 11.1. Multiple Databases Do Not Automatically Share a Cluster-Wide Consistent Point

A system with `customers` and `orders` databases may back them up at different times. If business invariants span both, restoring independent backups can leave cross-database state **misaligned in time**.

Standard Neo4j transactions are scoped to one database; never assume backing up multiple databases creates a **business-consistent distributed snapshot** across databases or between Neo4j and SQL/Kafka.

Mitigations include:

- Storing version/offset metadata in applications to reconcile after restore.
- Pausing or coordinating writers during backup windows where business rules permit.
- Accepting eventual reconciliation with a documented missing-event replay playbook.
- Clearly defining authoritative sources versus rebuildable projections.

### 11.2. Do You Need to Back Up the `system` Database?

In Neo4j, the **`system` database** and administrative metadata play a vital role in database definitions and privileges. Exact backup/restore scope, commands, and cluster rebuild workflows vary by version.

A complete recovery plan must cover restoring or recreating **database metadata, users/roles, schema, secrets/certificates, topology, and deployment configuration** via version-supported methods. Never back up only business databases and assume everything else magically reappears after total cluster loss.

## 12. Online Backups: Tools and Safety Conditions

Neo4j Enterprise provides backup tooling for supported versions/editions. An illustrative Neo4j 5.x-style command looks like:

~~~bash
# Illustrative for an authorized test environment.
# Check exact syntax/flags and mechanics for your running version.
neo4j-admin database backup \
  --from=10.20.1.11:6362 \
  --to-path=/secure/neo4j-backups \
  neo4j
~~~

This example assumes the backup service at `10.20.1.11:6362` is enabled, reachable from the CLI host, and authorized. **Never assume port 6362 is always open** or online backup is enabled across every image, edition, and configuration.

Some versions configure the backup service via settings such as:

~~~properties
# Illustrative settings; verify against your deployed Neo4j version.
server.backup.enabled=true
server.backup.listen_address=10.20.1.11:6362
~~~

Never expose the backup port to the Internet. It is an operational channel accessing highly sensitive data; enforce network ACLs, access controls, encryption, and artifact governance.

### 12.1. Which Member Should Run Backups?

In principle, you can select a member **eligible to serve backups with sufficient data** per version/topology rules to minimize impact on write traffic. Never claim “backing up a secondary is always safe/fresh enough” unconditionally.

Measure:

- Data freshness on the chosen member.
- I/O, CPU, and network impact on live read/write traffic.
- How the backup tool handles transaction logs and consistency.
- Gap between the recovered data point and backup completion time.
- Whether the backup finishes within its allowed window.

A successful backup from a lagging member can still violate RPO if you fail to verify the **actual recovery point**.

### 12.2. Full and Incremental Backups

A strategy can combine **periodic full backups** with **incremental backups** in between if supported by your Neo4j version and storage target. Incrementals typically depend on the backup chain/transaction history; never delete part of a chain assuming you can still restore to the latest point.

Design retention to keep all components needed for valid reconstruction. When upgrading versions, changing servers, or moving storage, verify incremental chain continuity rather than guessing.

### 12.3. Protecting Backup Artifacts

- Include database, timestamp, version, backup type, and run ID in naming/metadata.
- Encrypt in transit and at rest per policy.
- Restrict accounts allowed to delete or overwrite backups.
- Store copies in a failure domain separate from the cluster.
- Record manifests/checksums where supported.
- Verify artifact listing and readability.
- Record the Neo4j version/window required for compatible restore.
- Run periodic restore tests and track outcomes.

**Checksums prove a file was not unexpectedly altered under that hash check, but do not prove the internal data store can restore cleanly.** A restore test is mandatory.

## 13. Managing Backup Schedules and Recovery-Point Age

A schedule might look like:

~~~text
00:00  Full backup (per policy)
01:00  Incremental or supported supplemental mechanism
02:00  Incremental / verify
...
Daily: check recovery-point age and artifact verification
Weekly/monthly: restore drill in an isolated environment
~~~

This is an illustrative schedule; actual frequency depends on RPO, write rate, transaction log retention, and cost.

### 13.1. When a Backup Job Fails

Never dismiss a failure as “just retry it” without finding root cause. Check:

- Does the destination still have free space?
- Did networking to the backup member fail?
- Is the backup service listening on the expected address/port?
- Is the cluster failing over or is the database offline?
- Did secrets, certificates, or permissions change?
- Are concurrent backup jobs saturating I/O?
- Is the incremental chain still intact?

For tight RPOs, consecutive backup failures must alert on **age of the newest valid recovery point**, not merely failed job count.

### 13.2. Retention and Recovery Windows

Suppose an organization retains hourly backups for one day and daily backups for four weeks. That tiered retention policy does not mean you can recover to **every arbitrary second** across four weeks.

Point-in-time granularity depends on backup format, transaction log/incremental chains, and features supported by your Neo4j version. **Never advertise minute/second point-in-time recovery merely because backup filenames carry timestamps.**

## 14. Restore Drills Must Happen Outside the Live Cluster

A safe restore drill runs in an **isolated environment**, never overwriting production data.

~~~mermaid
flowchart TD
  A["Protected backup artifact"] --> B["Isolated restore environment"]
  B --> C["Restore with matching-version tool"]
  C --> D["Start test database/cluster"]
  D --> E["Check status and run Cypher checks"]
  E --> F["Verify data invariants"]
  F --> G["Measure RTO/RPO and file report"]
~~~

### 14.1. Preparing a Restore

- Confirm the **target database** and compatible version.
- Provision disk/volumes with ample space for restore, logs, and indexes.
- Prepare required secrets, certificates, and roles.
- Ensure the target environment does not reuse production DNS/service names in a way that misroutes live clients.
- Block unnecessary outbound integrations (production email, payments, brokers).
- Record the selected snapshot/artifact and expected recovery point.
- Verify restore tooling, permissions, and failure fallback steps.

**Never run overwrite-destination restores on a live serving production database** during a drill. For real disaster recovery, strictly follow approved change/incident procedures and official version-specific restore instructions.

### 14.2. Restore Is Not Just a Single CLI Command

Neo4j restore tooling includes commands in the family of:

~~~text
neo4j-admin database restore ...
~~~

Exact paths, artifact formats, overwrite flags, database-offline preconditions, and startup sequence must come from **help docs for your specific version**. Avoid blindly running placeholder destructive commands from memory.

After restoring, verify the server starts cleanly and the database reaches an appropriate online state—**never check only the CLI exit code**.

### 14.3. Checking the Graph with Cypher

On a test-restored database, count representative entities:

~~~cypher
MATCH (c:Customer)
RETURN count(c) AS customers;
~~~

~~~cypher
MATCH (o:Order)
RETURN count(o) AS orders;
~~~

~~~cypher
MATCH (:Customer)-[r:PLACED]->(:Order)
RETURN count(r) AS placedRelationships;
~~~

These numbers **must not be guessed**; compare against a pre-recorded manifest, recovery checkpoint, or authoritative source. On massive graphs, full scans carry cost; choose checks suited to graph scale and authorized in the test environment.

### 14.4. Checking Invariants, Not Just Counts

Suppose every Order must have at least one OrderLine:

~~~cypher
MATCH (o:Order)
WHERE NOT EXISTS {
  MATCH (o)-[:HAS_LINE]->(:OrderLine)
}
RETURN o.orderId AS orderId
LIMIT 20;
~~~

Check for OrderLines missing a Product:

~~~cypher
MATCH (l:OrderLine)
WHERE NOT EXISTS {
  MATCH (l)-[:FOR_PRODUCT]->(:Product)
}
RETURN l.lineId AS lineId
LIMIT 20;
~~~

These queries are valid only when the business model enforces those invariants. If the app supports `DRAFT` states or incomplete orders, filter by status before flagging anomalies.

### 14.5. Checking Schema and Privileges

After restore, do not inspect only nodes and relationships:

~~~cypher
SHOW CONSTRAINTS;
~~~

~~~cypher
SHOW INDEXES;
~~~

Verify API-facing schemas, application roles, service accounts, database names, routing, and essential metadata are all restored or recreated accurately.

## 15. Reconciling Application Transactions After Recovery

This step is easily overlooked when systems use retries and multiple services.

Example:

~~~text
Client sends command C-101
    |
    +-- Neo4j commits successfully
    |
    X-- response lost in incident
    |
Client does not know whether C-101 committed
~~~

After a cluster failover or restore, clients may resend the same operation. If creating an Order uses a stable `orderId`, uniqueness constraints prevent two Orders. Yet for an **additive points update**:

~~~cypher
MATCH (a:Account {accountId: $accountId})
SET a.points = coalesce(a.points, 0) + $delta;
~~~

a successful retry adds points a second time. Hence an **idempotency key/receipt** design is mandatory.

### 15.1. Writing a Receipt Alongside the Business Mutation

Illustrative model:

~~~text
(:AppliedCommand {commandId, payloadHash, appliedAt})
           |
       [:APPLIED_TO]
           |
           v
(:Account {accountId, points})
~~~

Constraint:

~~~cypher
CREATE CONSTRAINT applied_command_unique IF NOT EXISTS
FOR (cmd:AppliedCommand)
REQUIRE cmd.commandId IS UNIQUE;
~~~

Write the receipt and update `Account` **in the same Neo4j transaction**. On duplicate requests, look up the receipt by `commandId` and validate payload match before treating it as already processed. **Simply using `MERGE` on Account does not prevent a delta from being added twice.**

### 15.2. Restore Can Lose Receipts After the Recovery Point

If you restore to a backup taken before C-101 committed, C-101’s receipt disappears. Yet external systems may already have received confirmation/notifications for C-101. During replay:

- Event sources must know the right replay offset.
- Messages must carry stable IDs.
- A reconciliation workflow must compare acknowledged commands against the recovery point.
- External side effects must be compensated or coordinated per business rules.

**A successful database restore does not automatically restore point-in-time consistency between Neo4j and payment/Kafka/SQL systems.** RPO and reconciliation must cover the entire end-to-end business process.

### 15.3. Transactional Outbox Helps Coordinate External Systems

If an application emits events after graph writes, write an `OutboxEvent` inside the same Neo4j transaction, then let a dispatcher publish to the broker post-commit. The dispatcher can still duplicate deliveries on crash, so consumers still need idempotency.

During a restore, identify which outbox records already published before the outage, which remain pending, and how to replay without duplicating business effects.

## 16. Single-Member Failure and Failover Drills

A drill typically starts with **intentionally stopping one member** in test/staging.

### 16.1. Scenario

- Cluster built with representative test topology.
- Java app using `neo4j+s://...` routing URI or network-appropriate config.
- Light read/write workload using stable parameters and business IDs.
- Test dataset containing known nodes/relationships for verification.
- On-call operator equipped with dashboards and rollback controls.

### 16.2. Verification Sequence

1. Capture 10–30 minutes of baseline (or environment-appropriate window).
2. Identify the target database’s writer/roles using version-supported tools.
3. Stop **one chosen member in the authorized environment**—never pick a production server randomly.
4. Observe server/database/driver alerts.
5. Track duration of read/write impact and recovery timestamp.
6. Audit counts of committed, failed, retried, and ambiguous requests.
7. Restore the member and observe catch-up and cluster state.
8. Verify business invariants and document findings.

Never declare failover successful simply because surviving servers answer `RETURN 1`. Confirm **business write transactions** and Java-side routing recovery.

### 16.3. Metrics to Record

| Metric | Why it matters |
|---|---|
| Failure detection time | Quality of monitoring/alerting |
| Time from failure to usable new writer | Database failover responsiveness |
| Timeout/failed request count | User impact |
| Driver retry count | Load and stability impact |
| Ambiguous commit count | Reconciliation/idempotency exposure |
| Member recovery/catch-up time | Topology healing speed |
| p95/p99 latency during and after fault | Stability under failover |
| Data drift / duplicates | Business correctness |

## 17. Network Partition and Quorum-Loss Drills

This scenario is critical yet **carries higher risk** than stopping a single process: one misconfigured firewall/network policy can isolate an entire environment.

### 17.1. Drill Objectives

- When member groups cannot reach one another, does the cluster **block unsafe writes** on the non-quorum side?
- Which Java requests succeed, time out, or get rejected?
- Do DNS and proxies keep routing traffic to members unable to serve writes?
- Once networking heals, does the cluster recover?
- After recovery, are there graph anomalies or duplicate writes from app retries?

### 17.2. Logical Model

~~~text
Before fault:
  [A] --- [B] --- [C]

Network partition:
  [A]       [B] --- [C]

Group B,C can retain majority under configured rules.
A must not commit independent writes just because its process is still up.
~~~

In a three-member voting group, two members can retain majority; this is not a universal rule for every cluster/database regardless of member count. Always evaluate against actual topology.

### 17.3. Never Induce Arbitrary Network Partitions in Production

Run partition drills in staging or a topology-matched test environment. Any production test requires an approved change plan, defined blast radius, on-call staff, network rollback, abort criteria, and a maintenance window.

**Never use “delete the data directory to force a resync” as a casual testing step.** Recovery, server replacement, and topology edits must follow official procedures.

## 18. Drilling Other Failure Modes

A solid plan goes beyond “stop one node.”

| Simulated incident | Objective | Key metrics |
|---|---|---|
| Stop one primary/member | Failover, routing, write availability | Time to usable writer, app errors |
| Stop one secondary | Read capacity and load spread | Read latency, replica catch-up |
| Flaky network / packet loss | Retries, timeouts, election stability | Transaction errors, latency |
| Stale DNS IP | Client reconnect/cutover | Routing errors, pool reconnects |
| Nearly expired TLS certificate | Alerting and renewal workflow | Zero connection outage |
| Full disk in test | Detection and storage remediation | Pre-critical alerts, recovery |
| Write overload on hot node | Deadlocks/lock contention | Retries, p99, error rate |
| Backup job failure | RPO alerting | Valid backup age |
| Restore from latest backup | Measure RPO/RTO | Data recovery and reconciliation |
| Entire failure domain loss | Independent DR capability | Time to stand up alternate env |
| Outbox dispatcher crash | Redelivery | Zero duplicate business effects |
| Java app crash post-commit | Ambiguous commits | Receipts/idempotency verification |

Deliberate tests must stay strictly within authorized scopes; omit destructive/partition commands from generic docs to prevent running them against the wrong environment.

### 18.1. Drilling Loss of an Entire Cluster Zone

If all members sit in **one failure domain**, cluster replication offers no protection against losing that zone. An advanced DR drill simulates total primary-zone loss and rebuilds service from **backups stored outside the affected zone**.

Such a drill requires:

- Alternate compute and networking.
- Access to backup artifacts and secrets.
- Infrastructure configuration/manifests.
- DNS/certificate/proxy cutover procedures.
- Verification of database and external data sources.
- Business sign-off before reopening writes.

## 19. Java Driver: Read/Write and Routing Smoke Tests

The Java Driver lets applications use `executeRead` and `executeWrite` for driver-managed transactions alongside version-appropriate routing and retries.

Example **read smoke test**:

~~~java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class ClusterReadSmokeTest {
    public static void main(String[] args) {
        String uri = System.getenv("NEO4J_URI");
        String user = System.getenv("NEO4J_USER");
        String password = System.getenv("NEO4J_PASSWORD");
        String database = System.getenv("NEO4J_DATABASE");

        if (uri == null || user == null ||
                password == null || database == null) {
            throw new IllegalArgumentException(
                "Neo4j configuration is incomplete"
            );
        }

        try (Driver driver = GraphDatabase.driver(
                uri, AuthTokens.basic(user, password))) {
            driver.verifyConnectivity();

            try (Session session = driver.session(
                    SessionConfig.forDatabase(database))) {
                long value = session.executeRead(tx ->
                    tx.run("RETURN 1 AS value")
                      .single()
                      .get("value")
                      .asLong()
                );
                if (value != 1L) {
                    throw new IllegalStateException(
                        "Unexpected Cypher result"
                    );
                }
                System.out.println("Cluster read smoke test PASS");
            }
        }
    }
}
~~~

This code verifies connectivity and a trivial query at the instant it runs. It **does not prove failover, write availability, or business data consistency**.

### 19.1. Write Smoke Tests Must Not Pollute Production

Instead of `CREATE`-ing arbitrary nodes in production:

1. Target an approved **test/canary** database.
2. Use a deterministic identifier per probe.
3. Write inside a transaction with proper uniqueness/idempotency.
4. Read back to verify.
5. Clean up canary data safely per procedure.

Example Cypher for a canary database:

~~~cypher
MERGE (c:ClusterCanary {checkId: $checkId})
ON CREATE SET c.createdAt = datetime()
SET c.lastCheckedAt = datetime()
RETURN c.checkId AS checkId;
~~~

Create a uniqueness constraint on `ClusterCanary.checkId` before multiple workers probe concurrently. Never run this write query against a live business database without authorization; if used for live readiness, avoid creating write pressure or event spam.

### 19.2. Callbacks Can Retry

Never put email sending, payment calls, or broker publishing inside an `executeWrite` callback just to smoke-test business flows. Managed transaction callbacks can re-run on eligible errors. If events must be emitted, use an outbox and idempotency rather than mixing external side effects into transactions.

### 19.3. Routing and Bookmarks

With `neo4j+s://...`, the driver discovers endpoints from the routing table. If a cluster behind a proxy/NAT advertises private hostnames unreachable from Java Pods/clients, bootstrap may succeed while queries fail.

After failover, if business rules require read-your-writes across sessions, use a bookmark manager / causal consistency per your Driver version’s API. Never use fixed sleeps assuming all replicas have caught up.

## 20. Cluster Incident Response Runbook

A concrete runbook shortens decision time under pressure.

### 20.1. Identification Phase

1. Identify the affected **database and business endpoints**.
2. Distinguish read, write, routing, TLS, authentication, or query-latency errors.
3. Review member/DB/driver dashboards and recent changes.
4. Record incident start time to track RTO.
5. Escalate priority and page on-call staff per policy.

### 20.2. Containment / Isolation Phase

- If a server crashed: inspect resources, logs, and peer states.
- If quorum was lost: identify failure domain and connectivity state; never force writes on the minority side.
- If routing failed: inspect DNS/advertised endpoints, proxies, certificates, and firewalls from the Java environment.
- If disk filled up: follow supported cleanup/expansion procedures; never delete DB files arbitrarily.
- If data was corrupted by a bad business command: contain blast radius, halt the bad writer, and evaluate restore/reconciliation before resuming.

### 20.3. Recovery Phase

Priority order by incident type:

1. Protect data from ongoing destructive operations.
2. Restore connectivity or members per version documentation.
3. Verify the database can accept appropriate reads/writes.
4. Reconcile commands with uncertain commit outcomes using receipts/business logs.
5. Verify graph invariants and latencies.
6. Gradually reopen traffic if deployment controls support it.

**Do not treat restore as the knee-jerk first reaction to every server failure.** A downed member can often be replaced/recovered without rolling back all data to an older backup. Choose restore only after evaluating data-loss scope and targets.

### 20.4. Closure Phase

- Document the full timeline.
- Record actual RTO and newest recovered data point.
- Analyze retries, duplicates, pending outbox entries, and events needing replay.
- List improvements for monitoring, backups, runbooks, and topology.
- Schedule verification tests for the fixes.

## 21. Ready-to-Use Drill Plan Template

| Field | Details to fill in |
|---|---|
| Drill ID | `neo4j-drill-staging-001` |
| Environment | Isolated staging/DR |
| Database | Test database name |
| Neo4j version / edition | Specify explicitly |
| Topology | Primary count, secondary count, failure domains |
| Objective | e.g., verify failover when one member stops |
| Dataset | Canary and business invariant set |
| Test load | Low read/write RPS within safe bounds |
| Trigger | Approved simulated fault |
| Operators | Executor and observer |
| Abort criteria | Error threshold, quorum loss, out-of-scope impact |
| Rollback | How to restore member/network |
| SLI / SLO | Contracted metrics |
| Expected RPO / RTO | Business-approved targets |
| Evidence | Dashboards, logs, timeline, Cypher outputs |
| Result | PASS/FAIL/PARTIAL and findings |
| Follow-up actions | Owner, deadline, and remediation plan |

### 21.1. Safe Abort Conditions

Before every drill, confirm:

- No production traffic can accidentally hit the test environment.
- No unauthorized production data or secrets are used.
- Mechanisms exist to halt fault injection and restore networking.
- Necessary backup/restore points exist.
- An accountable decision-maker is present.
- Error or blast-radius thresholds trigger an immediate halt.
- No out-of-scope databases can be deleted or overwritten.

A drill ending in a **well-evidenced FAIL** is still valuable when it uncovers weaknesses early without harming out-of-scope environments.

## 22. Common Design Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Three replicas means backups aren’t needed | Accidental deletes replicate to every member | Independent backups, retention, and restore drills |
| Counting up processes = cluster healthy | Missing writer/quorum goes undetected | Read/write SLIs and database status checks |
| Monitoring only the current leader | Leadership shifts after failover | Monitor all members/databases and routing |
| Backup job exits 0 so it’s fine | Artifact might fail restore | Run test restores and verify data |
| Backups sit on the same volume/zone as cluster | One outage wipes out both | Copy to a separate failure domain and verify access |
| Unspecified RPO/RTO | No basis for backup frequency or drills | Obtain business sign-off upfront |
| Restore directly over production to test | Can destroy live data | Restore in isolation; never overwrite production |
| Measuring only restore CLI duration | Ignores DNS, secrets, routing, and validation | Measure end-to-end RTO |
| Checking only node counts | Missing relationships or broken invariants go unseen | Verify invariants, schema, and reconcile |
| Ignoring system metadata/roles | Database restores yet apps lack access | Plan metadata and config restoration |
| `RETURN 1` works so writes must work | Lost write quorum hides behind read checks | Safe write smoke tests and write SLIs |
| Private IPs in routing for public clients | Bootstrap works while queries fail | Ensure advertised endpoints are reachable |
| Retrying point-addition commands without IDs | Double-applies deltas | Receipts / idempotency keys |
| Sending emails inside retryable callbacks | Duplicate external side effects | Outbox / dispatcher |
| Manually deleting transaction logs when disk fills | Can break recovery | Follow Neo4j-supported procedures |
| Drilling only single-server shutdown | Blind to partitions and zone loss | Multi-tier scenario suite |
| No rollback for network tests | Test escalates into real outage | Abort criteria and pre-approved rollback |
| Capturing sensitive queries/params on dashboards | Leaks customer data | Redaction/allowlists and RBAC |

## 23. Practice Exercises

### Exercise 1 — Replication and Accidental Deletion

A cluster has three healthy members. An erroneous Cypher statement deletes 2,000 nodes, commits, and replicates.

**Question:** Why can you not simply “pull from another cluster member” by default to recover the old data?

**Answer:** Replication applies committed changes; caught-up replicas also lost those 2,000 nodes. You must restore from backups, use historical recovery features if supported, or rebuild from authoritative sources.

### Exercise 2 — Quorum Loss

A database uses a three-member voting group. Two members become unreachable, leaving one active.

**Question:** Should you force the lone survivor to keep accepting writes to avoid downtime?

**Answer:** No. It lacks a majority under consensus rules. Permitting independent writes risks breaking invariants. Restore connectivity/quorum or execute supported DR procedures.

### Exercise 3 — Backup Files Exist but Never Restored

Backup jobs run nightly and dashboards show green. The organization has never performed a test restore.

**Question:** Can you claim RTO is guaranteed?

**Answer:** No. You do not know artifact transfer time, restore duration, database startup, DNS/TLS/roles, data validation, or application cutover times. You must run an end-to-end drill.

### Exercise 4 — Gap Between Backup and Event Sources

A backup captures state as of 09:55. At 10:00 an outage strikes; external systems still hold confirmed orders from the last five minutes.

**Question:** After restoring, is checking that the database is online sufficient?

**Answer:** No. Reconcile/replay confirmed commands/events missing from the recovery point using stable IDs to avoid duplicate processing.

### Exercise 5 — Reads Succeed, Writes Fail

After a network glitch, a read API still returns results while Order creation continuously times out.

**Question:** Which dashboards should you prioritize?

**Answer:** Database writer/quorum status, write SLIs, routing/write errors, and topology. Process health or read SLIs alone are insufficient.

### Exercise 6 — Client Bootstraps but Cannot Run Queries

Through a proxy, the Java Driver bootstraps successfully, yet the routing table returns `neo4j-1.internal:7687`, which the client cannot resolve.

**Question:** Should you increase connection pool size to fix it?

**Answer:** No. Fix DNS, advertised endpoints, and routing reachability—not connection counts.

### Exercise 7 — Backing Up Multiple Databases

An application has `orders` and `customers` databases backed up at different times.

**Question:** Can you assert they form a single consistent business snapshot?

**Answer:** No. You need consistency/reconciliation rules, versioning, or coordination; independent database backups do not form a distributed transaction.

### Exercise 8 — Single-Member Drill

In staging, one primary stops; reads recover fast, yet write retries leave 40 commands with unknown outcomes.

**Question:** Beyond restarting the member, what must you do?

**Answer:** Inspect receipts/`commandId`s, reconcile committed commands, handle retries/duplicates, and measure time to usable writer; never blindly re-run the 40 commands under new IDs.

### Exercise 9 — Backup Port Exposure

An operator opens the backup port to the Internet so an external backup host outside the VPC can reach it.

**Question:** Why must this design change?

**Answer:** Backups access highly sensitive data. Use private channels/VPNs/protected management paths with strict source and privilege restrictions instead of public exposure.

### Exercise 10 — When Does a Drill End?

A restore CLI finishes at 10:10, the database comes online at 10:12, Java APIs connect at 10:17, and the business verifies data integrity at 10:20.

**Question:** Which timestamp best reflects business-service RTO?

**Answer:** Defining RTO as full functional service restoration with valid data makes 10:20 far more accurate than “restore CLI finished.” Agree on the definition before testing.

## 24. Acceptance Checklist for Monitoring and Recovery

### 24.1. Cluster and Applications

- [ ] Topology, edition, version, and failure domains documented per database.
- [ ] Monitoring covers members/databases/writers and write-loss conditions.
- [ ] Distinct SLIs for reads, writes, routing, latency, and business errors.
- [ ] Java Driver uses routing URIs/endpoints aligned with client networking.
- [ ] All advertised endpoints are reachable from applications.
- [ ] Bounded timeouts/retries, idempotency, and external side-effect controls in place.
- [ ] Bookmark/causal consistency policy defined where business rules require it.

### 24.2. Backups and Artifacts

- [ ] RPO/RTO defined and approved.
- [ ] Clear inventory of databases to back up and metadata to protect.
- [ ] Backup tools/formats match Neo4j version support.
- [ ] Backup endpoints and repositories protected by access controls, networking, and encryption.
- [ ] Retention, offsite copies, and accidental-deletion protection configured.
- [ ] Dashboard tracks valid recovery-point age, not just job status.
- [ ] Manifests/artifacts/versions tracked to reproduce restores.
- [ ] Scheduled test restore completed with evidence archived.

### 24.3. DR and Drills

- [ ] Isolated DR/restore environment exists without overwriting production.
- [ ] Runbooks cover member loss, quorum loss, network partitions, and zone loss.
- [ ] Abort criteria, on-call staff, approvers, and rollback plans established.
- [ ] Detection time, write recovery, actual RTO, and recovery point measured.
- [ ] Post-restore verification covers nodes, relationships, schema, privileges, and business invariants.
- [ ] Reconciliation procedure exists for transactions with ambiguous outcomes.
- [ ] Replay/outbox/broker plan covers data generated after the recovery point.
- [ ] Java application verified reading and writing after recovery.
- [ ] Every drill produces a PASS/FAIL/PARTIAL report with improvement actions.

## 25. Key Takeaways

**Neo4j cluster monitoring** cannot rely solely on counting running servers. Track **write capability, per-database status, consensus health, Java Driver routing, data catch-up, query latency, resources, and business operations**. An online server or a passing `RETURN 1` does not prove the cluster meets application requirements.

**Replication does not replace backups**: deleted or corrupted data replicates to every member. Backups must follow policies for **RPO/RTO, retention, security, isolated storage, and restore testing**; recoverability is proven by a **working database, valid graph invariants, and functional Java services**, not merely the existence of a backup file. Finally, rehearsing member loss, quorum loss, network partitions, and backup restores in safe environments uncovers weaknesses in topology, data, DNS, privileges, retries, and incident response before real outages hit.
