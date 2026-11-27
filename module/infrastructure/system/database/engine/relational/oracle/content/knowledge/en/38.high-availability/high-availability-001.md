# Distinguishing High Availability, Disaster Recovery, and Scalability

> **Topic:** Database Engine Relational Oracle  
> **Chapter:** High Availability  
> **Objective:** Distinguish High Availability (HA), Disaster Recovery (DR), and Scalability; understand failure domains and RTO/RPO objectives; select Oracle architectures such as RAC, Data Guard, and RMAN; design services, client failover, load balancing, and resource scaling; combine protection layers into an appropriate architecture; test and operate against realistic failure scenarios.

## 1. Three Frequently Confused Objectives

A database system may require three capabilities simultaneously:

- **High Availability (HA):** maintaining or rapidly restoring service when a component fails, with minimal downtime.
- **Disaster Recovery (DR):** restoring service and data when a major failure domain is lost, such as an entire site, storage subsystem, or infrastructure zone.
- **Scalability:** increasing serving capacity as the number of users, requests, data volume, or workload grows.

These three objectives are related but not synonymous:

| Objective | Primary Question | Example Oracle Solutions |
|---|---|---|
| HA | If a node or instance fails, how does the service continue? | Oracle RAC, Oracle Clusterware, service failover, Application Continuity |
| DR | If the entire site or primary database is lost, where is it recovered and how much data is lost? | Oracle Data Guard, RMAN backup/restore, standby site |
| Scalability | As load increases, how do we handle more requests or data? | Scale-up, RAC scale-out, sharding, partitioning, connection/service design |

A RAC cluster can increase node fault tolerance and scale workload within the same cluster, but it does not by itself protect against the loss of an entire site. A Data Guard standby can protect the database at another site, but it does not by itself increase primary write throughput. Adding CPU or nodes can increase capacity, but it does not automatically create data copies for disaster recovery.

**Good design typically combines all three objectives along with backup/recovery.**

## 2. Define Failure Domains Before Choosing Technology

A failure domain is the scope of components that can be affected together by a single failure. An HA/DR architecture must clearly define which failures it needs to withstand.

Examples of progressively larger failure domains:

1. A failing process or session.
2. An unavailable database service.
3. A crashed Oracle instance.
4. A lost host/node.
5. A failed rack, network switch, or storage array.
6. A disconnected availability zone or data center.
7. A region/site experiencing a disaster.
8. Logic errors or human actions corrupting/deleting data across multiple copies.

Different technologies address different scopes:

- Session recovery, retries, and application connection management handle failures at the request/session level.
- RAC and Clusterware handle certain instance/node failures within a cluster.
- Data Guard maintains another database to transition roles when the primary/site fails.
- RMAN backup and recovery protect recoverability when data is corrupted, accidentally deleted, or online copies are no longer trustworthy.
- Immutable/offsite backups help protect against certain malware deletion scenarios or compromise of the entire production environment.

### 2.1. Do Not Place Two Copies in the Same Failure Domain

Two RAC nodes in the same rack can lose power together. Two databases on the same storage array can lose data together if the array fails. Primary and standby databases in the same data center can both be affected by floods, fires, or wide-area network outages.

When designing DR, genuinely separate failure domains:

- Host and rack.
- Power and cooling.
- Storage.
- Network path.
- Data center/availability zone.
- Region.
- Identity/credential and backup administration domain.

Geographic separation while sharing a single identity system, administrative account, or storage control plane may still leave a common point of failure.

### 2.2. Classifying Failures by Scope

| Failure | Can HA help? | May DR be needed? | May backup/recovery be needed? |
|---|---|---|---|
| Process/session failure | Yes, typically retry/reconnect | Usually no | Usually no |
| One RAC instance failure | Yes, if cluster/service is configured properly | Not necessarily | Not necessarily |
| One node failure | RAC can continue on remaining nodes | Yes if the entire cluster/site is lost | Yes if data is corrupted |
| Primary storage failure | Redundancy depends on storage design | Data Guard can fail over to standby | RMAN may be needed for recovery |
| Loss of entire site | Intra-site HA is insufficient | Yes | Backup may be the recovery option |
| Accidental data deletion and error replicated | HA does not solve this | Standby may also receive the change | PITR/backup or logical recovery |
| Ransomware deletes all online copies | HA/replication may be affected | Online DR may be affected | Immutable/offline backup is critical |

## 3. RTO, RPO, Availability, and Operational Metrics

Before selecting RAC, Data Guard, or a backup strategy, business objectives must be established.

### 3.1. RTO — Recovery Time Objective

RTO is the maximum amount of time a service is permitted to be unavailable before it must resume operation.

Examples:

- 30-second RTO: requires very fast detection and redirection mechanisms, and clients must reconnect/replay appropriately.
- 15-minute RTO: may allow a failover procedure with some automated steps and checks.
- 4-hour RTO: restore/recovery from backup may meet the target if measured and rehearsed.

RTO must account for the entire duration from the moment the incident begins until users can actually use the service again, not merely the time until the database reports OPEN.

Components of RTO:

- Detection time.
- Decision/approval time.
- Failover or restore time.
- Database open/recovery time.
- Service/listener/client reconnection.
- Application validation.
- Business reconciliation.

### 3.2. RPO — Recovery Point Objective

RPO is the maximum amount of data loss tolerated, typically expressed in time or transaction points.

Examples:

- RPO 0 in a business sense requires zero loss of committed transactions within the defined failure model.
- 1-minute RPO allows losing up to approximately one minute of data under the defined scenario.
- 24-hour RPO may be suitable for less critical data with daily backups.

RPO depends on how redo/data is protected:

- Synchronous redo transport can reduce or eliminate committed data loss under appropriate failure assumptions.
- Asynchronous transport can experience transport lag and lose redo that has not reached the standby.
- Scheduled backups may result in an RPO larger than the backup interval if archived logs are not adequately protected.

Do not promise RPO 0 simply because a standby exists. You must define protection mode, commit semantics, network failure behavior, and failure scenarios.

### 3.3. Availability and Downtime Budget

Availability is typically expressed as the percentage of time the service is available:

\[
Availability = \frac{Uptime}{Uptime + Downtime}
\]

Theoretical downtime examples in a 365-day year:

| Availability | Approximate Downtime per Year |
|---:|---:|
| 99% | 3 days 15 hours 36 minutes |
| 99.9% | 8 hours 45 minutes 36 seconds |
| 99.95% | 4 hours 22 minutes 48 seconds |
| 99.99% | 52 minutes 34 seconds |
| 99.999% | 5 minutes 15 seconds |

These are theoretical conversions. An actual SLO must define maintenance windows, planned/unplanned downtime, how request success is measured, and service scope.

### 3.4. MTTR and MTBF

- **MTTR (Mean Time To Repair/Recover):** the average time to recover after an incident, depending on how the organization defines it.
- **MTBF (Mean Time Between Failures):** the average time between incidents.

HA typically reduces downtime when component failures occur. DR reduces downtime and data loss when a large failure domain is affected. Good monitoring, automation, and runbooks help reduce detection time and MTTR.

## 4. High Availability with Oracle RAC

Oracle Real Application Clusters (RAC) allows multiple instances on multiple nodes to concurrently access a single database using shared storage in a supported cluster architecture.

Conceptual model:

~~~text
             Application clients
                     |
             Oracle Services
                     |
          +----------+----------+
          |                     |
       Node 1                Node 2
     +---------+           +---------+
     | Instance|           | Instance|
     | RAC1    |           | RAC2    |
     +----+----+           +----+----+
          |                     |
          +----------+----------+
                     |
              Shared storage
               Database files
~~~

If one instance/node fails, the remaining instances can continue serving the workload according to their configuration and remaining capacity.

### 4.1. Which Failures Does RAC Handle?

RAC can improve fault tolerance for:

- A crashed instance.
- Loss of a node.
- Certain process/service failures.
- Node maintenance using supported rolling procedures.
- Distributing workload across instances.

RAC does not by itself protect against every failure:

- Loss of entire shared storage without appropriate redundancy.
- Loss of the entire data center.
- Logic errors or erroneous DML written to the database.
- Accidental table drops.
- Ransomware or administrative privilege compromise.
- Application bugs causing all nodes to receive abnormal workload.

### 4.2. Cache Fusion and the Interconnect

RAC instances maintain separate buffer caches while sharing access to the database. Cache Fusion uses the cluster interconnect to transfer blocks between instances when needed.

Interconnect latency, packet loss, bandwidth, and node membership directly impact RAC performance and stability.

Workloads with high block contention or hot blocks can increase global cache waits. RAC does not make every SQL statement faster; the application and data access patterns must be designed to minimize cross-instance contention.

### 4.3. Services as the Unit of Application Connection

Applications should connect through a managed database service rather than hardcoding a specific instance.

A service can define:

- Preferred/available instances.
- Workload role.
- Failover behavior.
- Connection load balancing.
- Runtime load balancing.
- PDB/service association.

In RAC, services route workload to appropriate instances and support relocating services when a node fails.

Inspecting services:

~~~sql
SELECT inst_id,
       name,
       network_name,
       con_id
FROM gv$services
ORDER BY name, inst_id;
~~~

Clusterware commands to check service status, depending on the architecture:

~~~text
srvctl status service -db <db_unique_name>
srvctl status database -db <db_unique_name>
~~~

### 4.4. Connection Load Balancing and Runtime Load Balancing

Connection load balancing distributes new connections across configured instances/services. Runtime load balancing uses workload/performance information to direct requests to suitable instances when supported by the driver and service configuration.

Distinguish between:

- Connection balancing: decides placement of initial connections.
- Runtime balancing: routes active workload/requests or connections based on runtime metrics.
- Failover: handles situations when an instance/service is no longer available.

Do not assume every JDBC/OCI client automatically has all of these capabilities. The driver, connect descriptor, service goal, and pool configuration must be compatible.

### 4.5. FAN, FCF, and Application Continuity

Oracle provides client-side HA mechanisms:

- **Fast Application Notification (FAN):** notifies clients or connection pools of service/instance events.
- **Fast Connection Failover (FCF):** enables pools to discard dead connections and react to FAN events when configured and supported.
- **Application Continuity:** can replay certain requests/database calls after failures under supported conditions.
- **Transparent Application Continuity:** extends replay capabilities in certain configurations/drivers/services.

These features depend on Oracle release, driver, pool, service, and relevant licenses/options. Not every transaction can be safely replayed. Applications must design idempotency, transaction boundaries, and handling of external side effects outside the database.

### 4.6. RAC Is Not DR

RAC typically uses shared database storage within a single cluster/site. If the site is completely lost or data suffers logical corruption, all RAC nodes may go down together or see the same corrupted data.

Therefore, RAC does not replace Data Guard or RMAN backups. A system requiring intra-site HA and cross-site DR typically uses RAC at the primary and Data Guard to another site.

## 5. Disaster Recovery with Oracle Data Guard

Oracle Data Guard maintains one or more standby databases from a primary database via redo transport and redo apply.

Model:

~~~text
                Application
                    |
               Primary service
                    |
             +--------------+
             | Primary DB   |
             | READ WRITE   |
             +------+-------+
                    |
              Redo transport
                    |
          WAN / DR network
                    |
             +------+-------+
             | Standby DB   |
             | MOUNTED or   |
             | READ ONLY*   |
             +--------------+

* Open mode depends on standby type, configuration, and licensed options.
~~~

The primary generates redo; redo is transmitted to the standby and applied to update datafiles. When the primary/site fails, the standby can be transitioned to become the primary via switchover/failover procedures.

### 5.1. Physical Standby

A physical standby maintains a physical copy of the primary through redo apply. It is suitable for many database-level DR scenarios.

Characteristics:

- Datafiles and database structure are maintained via redo.
- Redo Apply updates the standby.
- Can use MRP (Managed Recovery Process) depending on mode.
- Standby is typically MOUNTED or READ ONLY WITH APPLY in supported configurations.
- Role transitions occur via switchover/failover under applicable conditions.

Physical standby is typically the most common choice for Oracle DR.

### 5.2. Logical Standby

A logical standby applies equivalent SQL derived from redo to an open database, allowing certain structural differences and read/write operations within supported limits.

It has restrictions on data types, objects, and DDL/DML operations compared to a physical standby. Do not assume all schemas/objects are supported. Check supported data types, SQL Apply restrictions, and release notes.

### 5.3. Snapshot Standby

A snapshot standby transitions a physical standby into a read/write open state for testing or validation over a period of time; redo from the primary is received and stored but not applied as in a normal physical standby. When converted back, local changes are discarded and accumulated redo is applied.

A snapshot standby is useful for testing with near-production data, but it is not a DR standby ready for immediate failover while in snapshot mode. It requires storage space and a plan for converting back.

### 5.4. Redo Transport and Apply

Two stages must be monitored separately:

- **Transport:** the primary sends redo to the standby.
- **Apply:** the standby applies redo to datafiles.

Transport lag and apply lag have different meanings. A standby may receive redo quickly but apply slowly; or redo may not reach the standby due to network/destination errors.

Inspection query:

~~~sql
SELECT name,
       value,
       unit,
       time_computed,
       datum_time
FROM v$dataguard_stats
WHERE name IN (
    'transport lag',
    'apply lag',
    'apply finish time'
);
~~~

Check destinations:

~~~sql
SELECT dest_id,
       status,
       error,
       destination
FROM v$archive_dest_status
WHERE status <> 'INACTIVE'
ORDER BY dest_id;
~~~

Lag values should be read alongside TIME_COMPUTED and DATUM_TIME. A stale value is not a reliable real-time measurement.

### 5.5. Protection Modes

Data Guard has main protection modes:

- **Maximum Protection:** prioritizes zero committed data loss within failure assumptions; requires synchronous redo transport and can affect availability if redo cannot be protected as required.
- **Maximum Availability:** prioritizes zero data loss when the standby can satisfy requirements; upon connection failures per its designed mechanism, the primary may continue at a lower protection level depending on the situation.
- **Maximum Performance:** typically uses asynchronous transport to minimize latency impact on the primary; redo not yet transmitted to the standby may be lost during a failure.

Selection depends on RPO, network latency, site distance, bandwidth, and tolerance for downtime. Synchronous transport over long distances can increase commit latency.

Do not choose a mode based solely on the word "maximum". Check the actual protection level:

~~~sql
SELECT protection_mode,
       protection_level,
       database_role,
       switchover_status
FROM v$database;
~~~

### 5.6. Switchover and Failover

- **Switchover:** a planned role transition, typically with zero data loss when executed under proper conditions with a synchronized standby.
- **Failover:** transitioning a standby to primary when the primary can no longer continue serving; data loss may occur depending on transport/protection state.

Switchover is suited for maintenance, DR drills, and controlled transitions. Failover is an emergency action when the primary cannot be recovered within an acceptable timeframe.

Do not trigger failover simply because a transient probe fails. Verify that the primary is genuinely unable to serve, prevent split-brain, and ensure only a single primary is allowed to accept writes.

### 5.7. Data Guard Broker

Broker manages the Data Guard configuration and assists with monitoring and role transitions.

Observation commands:

~~~text
DGMGRL> SHOW CONFIGURATION;
DGMGRL> SHOW DATABASE VERBOSE '<db_unique_name>';
DGMGRL> VALIDATE DATABASE VERBOSE '<db_unique_name>';
~~~

Syntax and output depend on the release. Broker does not replace monitoring of storage, network, application services, and backups.

### 5.8. Active Data Guard and Read-Only Standby

A standby can be opened read-only in supported configurations. Opening a standby read-only while simultaneously applying redo in real time (Active Data Guard) is a feature requiring a separate option/license under Oracle contracts.

Do not assume that simply opening a standby READ ONLY makes all query-while-apply capabilities available. Verify licensing, version, and apply status.

Read workloads on a standby can offload the primary, but require evaluating:

- Apply lag and data freshness.
- Query workloads competing for I/O/CPU with redo apply.
- Service routing and read-only enforcement.
- Transaction semantics and read-after-write consistency.
- Licensing and feature restrictions.

## 6. Backup and Recovery with RMAN: An Independent Protection Layer

RMAN backup/restore addresses a different objective than RAC and Data Guard.

- RAC helps maintain operations when some nodes/instances fail.
- Data Guard helps transition to another database when the primary/site fails.
- RMAN helps restore a database/datafile/control file or a point-in-time state when needed.

A Data Guard standby can receive accidental deletions or logically corrupted data if redo is applied. Therefore, a standby is not an independent backup.

### 6.1. Backup Strategy

A backup strategy must define:

- Full/incremental backup schedule.
- Archived redo log backup frequency.
- Control file/SPFILE autobackup.
- Retention policy.
- Offsite/immutable copies.
- Encryption and key management.
- Restore validation and testing.
- Realistic RPO/RTO.

Example inventory checks:

~~~text
RMAN> SHOW ALL;
RMAN> LIST BACKUP SUMMARY;
RMAN> REPORT NEED BACKUP;
~~~

### 6.2. Restore Validation

~~~text
RMAN> RESTORE DATABASE VALIDATE;
~~~

Validation checks the readability of required backups within the scope of the command. It does not replace a complete restore test to a separate environment.

To know the true RTO, you must perform restore/recover tests and measure:

- Host/storage preparation time.
- Restoring datafiles.
- Applying archived logs.
- Opening the database.
- Starting services.
- Application validation.
- Business reconciliation.

### 6.3. Logical Corruption and Human Error

If a user accidentally deletes data, Data Guard typically replicates that operation. RAC also shares access to the modified database. You need to use:

- Flashback Query/Flashback Table if sufficient undo and appropriate conditions exist.
- Flashback Database if flashback logs and appropriate restore points/retention exist.
- RMAN point-in-time recovery.
- Export/backup or application-level logical recovery.

Do not use standby failover as a way to recover accidentally deleted data.

### 6.4. Immutable and Isolated Backups

To protect against ransomware or administrative privilege compromise:

- Keep backup copies in a separate failure domain.
- Use immutable/object lock or offline media per policy.
- Separate backup credentials from production credentials.
- Restrict permissions to delete backups.
- Protect the recovery catalog and encryption keys.
- Rehearse restores from offsite copies.

## 7. Scalability: Expanding Processing Capacity

Scalability answers the question: as workload increases, can the system handle more work at an acceptable cost and latency?

### 7.1. Vertical Scaling — Scale-Up

Scale-up increases the resources of a single server/database:

- Adding CPU cores.
- Increasing RAM.
- Increasing storage IOPS/throughput.
- Increasing network bandwidth.
- Upgrading CPU/storage generations.

Advantages:

- Simpler architecture.
- No need to distribute data or requests across multiple nodes at the application tier.
- Some workloads benefit immediately if bottlenecked on the exact resource being added.

Limitations:

- Hardware has physical ceilings.
- Costs rise steeply at high-end configurations.
- Can create a large single failure domain.
- Does not solve site failures or logical corruption.
- Workload may be bottlenecked by locks, SQL plans, or serialization rather than CPU/RAM.

### 7.2. Horizontal Scaling — Scale-Out

Scale-out adds nodes/instances/services to process workload in parallel.

In Oracle, common models include:

- RAC with multiple instances on a single database.
- Sharding across multiple databases by shard key.
- Read replicas/standbys for read workloads in supported configurations.
- Multiple application servers/connection pools.
- Partitioning to manage and access large datasets more efficiently.

Scale-out introduces additional overhead:

- Network/interconnect.
- Coordination and distributed transactions.
- Data placement and routing.
- Consistency and failover logic.
- Operational complexity.
- Monitoring and capacity balancing.

Adding nodes does not guarantee linear throughput scaling. If the bottleneck is a hot block, storage array, sequence contention, or an inefficient SQL statement, adding nodes may not resolve it.

### 7.3. RAC Supports Both HA and Potential Scale-Out

RAC can distribute workload across multiple instances and increase processing capacity when the workload can execute concurrently across nodes.

However, RAC scale-out depends on:

- Whether the workload is sufficiently independent across sessions/transactions.
- Global cache traffic.
- Interconnect bandwidth/latency.
- Shared storage throughput.
- Service placement and load balancing.
- Per-node CPU/memory capacity.
- Hot blocks and sequence/index contention.
- Licensing and deployment configuration.

A workload with heavy concurrent access to the same blocks or rows may experience worse contention when adding instances.

### 7.4. Sharding

Oracle Sharding distributes data across multiple database shards by a shard key to scale capacity and distributed workloads.

Advantages:

- Each shard manages a subset of data.
- Can scale out by adding shards.
- Workloads specifying the shard key can be routed directly to the database holding the data.
- Can alleviate certain centralized bottlenecks.

Challenges:

- Selecting a shard key and data distribution.
- Hot shards/skew.
- Cross-shard queries and transactions.
- Rebalancing.
- Global uniqueness and sequence strategy.
- Backup/DR per shard and for the catalog/configuration.
- Application routing and failure handling.

Sharding does not automatically make every query faster. Queries lacking a shard key may have to fan out across multiple shards.

### 7.5. Partitioning Is Not Sharding

Partitioning divides tables/indexes within a single database into partitions for more efficient management, pruning, maintenance, and certain access patterns.

Sharding distributes data across multiple independent databases.

| Partitioning | Sharding |
|---|---|
| Divides objects within a database | Distributes data across multiple databases |
| Single database identity/transaction domain | Multiple shards/databases |
| Supports partition pruning and maintenance | Supports capacity distribution |
| Does not inherently remove single-database limits | Can scale across multiple databases |
| Does not inherently provide DR | Requires HA/DR design for each shard and metadata |

## 8. Read Scaling and Write Scaling

Not all workloads scale in the same way.

### 8.1. Read Scaling

Common approaches:

- SQL and index tuning.
- Caching appropriate results or data.
- Using read-only standbys when configuration and licensing allow.
- Separating reporting workloads.
- Using materialized views/summary tables.
- Partitioning and pruning.
- Sharding aligned with data/query patterns.

Read scaling requires considering consistency. An asynchronous standby may return stale data compared to the primary. If a user writes and immediately reads back, route to the primary or implement a mechanism to guarantee read-after-write consistency.

### 8.2. Write Scaling

Write scaling is harder because writes generally require transaction coordination and uniqueness enforcement.

Approaches:

- Reducing transaction duration and lock contention.
- Optimizing indexes and redo generation.
- Partitioning to reduce contention/maintenance where appropriate.
- RAC when the workload fits and cross-instance contention is acceptable.
- Sharding to distribute writes by shard key.
- Queuing/batching to absorb bursts.
- Designing idempotent operations and asynchronous processing.

Adding read replicas does not increase commit write capacity on the primary. A system with strong read scaling can still suffer a write bottleneck.

## 9. Load Balancing Is Not Failover

Load balancing distributes workload among active instances/services/nodes. Failover shifts workload away from a component that is no longer functioning.

| Concept | Objective | Example |
|---|---|---|
| Load balancing | Avoid overloading one node while others have capacity | RAC service connection balancing |
| Failover | Continue operating after a failure | Service relocate, Data Guard role transition |
| Retry | Re-execute a request upon transient error | Application retry with backoff |
| Replay | Recover an in-flight request/database interaction via supported mechanisms | Application Continuity |
| Scaling | Increase total processing capacity | Adding CPUs, RAC nodes, shards |

A load balancer may continue sending traffic to an unhealthy node if health checks or service registration are misconfigured. Failover does not guarantee in-flight requests will complete; transactions may roll back or clients may need to handle indeterminate outcomes.

### 9.1. Retries and Idempotency

When a connection drops during COMMIT, the client may not know whether the transaction committed. Blind retries can create duplicate transactions.

Applications need:

- Idempotency keys for appropriate business operations.
- Unique constraints or deduplication.
- Determining transaction outcomes upon reconnecting.
- Bounded retries with exponential backoff.
- Classification of retryable vs. non-retryable errors.
- Avoiding retries on operations with external side effects without deduplication mechanisms.

### 9.2. Connection Pools

Connection pools need to handle:

- Dead connection detection.
- FAN/FCF where supported.
- Connection validation.
- Reconnect storms.
- Pool sizing and database session capacity.
- Timeouts, retries, and backoff.
- Service role/instance preferences.

An oversized pool can overload the database; an undersized pool can cause queuing at the application tier. Measure connection wait times alongside active database sessions.

## 10. Combining HA, DR, and Scalability

An enterprise architecture can combine layers:

~~~text
                    Applications
                         |
                 Database service
                         |
              Primary RAC cluster
             +-----------+-----------+
             |                       |
          Node A                  Node B
         Instance                Instance
             |                       |
             +----------+------------+
                        |
                  Primary storage
                        |
                 Redo transport
                        |
                Separate DR site
                        |
              Standby database
              (Data Guard)
                        |
                Standby storage

         Independent RMAN backup copies
              /                  \
       Local backup         Offsite/immutable
       repository             repository
~~~

Roles:

- RAC: node/instance fault tolerance and workload distribution within the primary site.
- Data Guard: maintains a standby in another failure domain and supports role transitions.
- RMAN: provides backup/recovery for media failure, logical errors, and PITR.
- Application services: route connections and respond to failover.
- Monitoring/runbooks: detect, decide, execute, and verify recovery.

### 10.1. Not Every System Needs RAC

A single-instance database can achieve appropriate HA via Oracle Restart, storage redundancy, service monitoring, and Data Guard to another site, depending on RTO/RPO. RAC increases licensing, infrastructure, and operational costs.

Choose based on failure models and business objectives, not merely because a technology is available.

### 10.2. Can a Data Guard Standby Also Use RAC?

Primary and standby databases can have different topologies in Oracle-supported configurations. For example, a RAC primary and single-instance standby, or RAC on both sides. Verify the support matrix, failover capacity, and licensing.

If the standby only has a single small server, failing over the full production workload may fail to meet SLAs. The DR site must be sized for the workload it needs to recover, not merely for receiving redo.

### 10.3. Independent Backups Remain Essential

A RAC + Data Guard architecture still requires RMAN backups and isolated copies. RAC and Data Guard protect availability/replication; they do not guarantee the ability to revert to a state prior to a replicated accidental deletion.

## 11. Selecting Architecture by Requirement

| Requirement | Architectural Direction to Evaluate |
|---|---|
| Tolerate instance/node failure within a site | RAC or an HA approach suited to the workload |
| Tolerate loss of an entire site | Data Guard to another site |
| Recover from accidental deletion/corruption | RMAN PITR, Flashback, or appropriate logical recovery |
| Low RPO | Appropriate Data Guard protection mode/transport, archived log backups |
| Very low RTO | Failover automation, service/client failover, drills |
| Heavy read workload | SQL tuning, caching, reporting standby, or sharding |
| Growing write workload | Transaction optimization, partitioning, appropriate RAC, or sharding |
| Very large data growth | Partitioning, archival, sharding, or data lifecycle management |
| Ransomware resilience | Immutable/offline backups, credential separation, recovery testing |
| Maintenance without long downtime | Rolling maintenance/RAC/Data Guard per support and runbooks |

### 11.1. Selection Examples

**System A: internal application, moderate load, tolerates 4-hour RTO and 24-hour RPO**

Can use a single-instance database, scheduled RMAN backups, archived log backups as needed, and restore testing. RAC may be unnecessary if the downtime budget and costs do not justify it.

**System B: mission-critical transactions, requires minutes-level RTO, low RPO**

Can evaluate RAC at the primary site, Data Guard to a DR site with an appropriate protection mode, application service failover, and independent backups. Must rehearse both node failures and site loss.

**System C: rapidly growing read workload, moderate writes**

Can tune SQL/indexes first, separate reporting, use a read-only standby where supported/licensed, or use caching/materialized views. Control lag and read-after-write consistency.

**System D: write throughput scaling across many independent tenants**

Can evaluate sharding by tenant key if queries and transactions stay mostly within a single tenant. Must account for cross-tenant reporting, global uniqueness, rebalancing, and per-shard DR.

## 12. Measuring Capacity and Scalability

Scalability must be proven through load testing and capacity testing, not merely inferred from CPU/node counts.

### 12.1. Metrics to Monitor

- Transactions/sec and requests/sec.
- p50/p95/p99 latency.
- CPU utilization and CPU time per transaction.
- Active sessions and connection pool wait time.
- Buffer gets per transaction.
- Physical I/O latency, IOPS, and throughput.
- Redo bytes/sec and log file sync.
- Global cache waits in RAC.
- Interconnect throughput/latency.
- Data Guard transport/apply lag.
- TEMP/PGA/UNDO usage.
- Error, timeout, retry, and deadlock rates.

### 12.2. Throughput Saturation

As concurrency increases, throughput usually rises up to a point and then flattens or degrades due to contention/resource saturation.

Signs of saturation:

- Sustained near-maximum CPU usage.
- Rapidly rising p95/p99 latency.
- Growing connection pool queues.
- Increasing lock/latch/global cache waits.
- Rising I/O latency.
- Throughput failing to grow despite increased concurrency.
- Increasing error/timeout/retry rates.

Adding nodes only helps if the bottleneck is distributable. If the bottleneck is a hot row, a sequence, a storage array, or an external dependency, scale-out may be ineffective.

### 12.3. Headroom and N+1 Capacity

An HA cluster must retain sufficient capacity when a node is lost. If two nodes normally run at 90% CPU, losing one node can overload the surviving node.

Capacity planning should evaluate:

- Normal load.
- Peak load.
- Load when one node/site is lost.
- Concurrent batch/reporting workloads.
- Growth over the forecast period.
- Maintenance windows.
- Failover/recovery overhead.

N+1 is a capacity principle: after losing one component, the system retains enough resources to serve the required load. Not every system requires strict N+1, but degradation modes must be understood.

### 12.4. Benchmarking Scale-Out

A process for testing RAC or scale-out:

1. Run a baseline on a single node/instance or current configuration.
2. Record workload mix and concurrency.
3. Add nodes/instances in a test environment.
4. Keep data volume, SQL, bind profiles, and client behavior comparable.
5. Measure throughput, latency, CPU, I/O, and interconnect.
6. Observe global cache waits and hot blocks.
7. Test the workload with one node unavailable.
8. Compare normal performance against degraded mode.

Do not measure aggregate throughput only when all nodes are healthy. An HA architecture must also be measured when a node is lost.

## 13. Testing HA and DR

An architecture is only considered ready once failover procedures have been tested under controlled conditions.

### 13.1. HA Testing

Scenarios that can be rehearsed in an approved environment:

- Killing a test process in a lab.
- Stopping/restarting an instance per runbook.
- Simulating loss of a node.
- Planned service relocation.
- Verifying connection pool detection and eviction of dead connections.
- Verifying application retry/replay.
- Measuring request recovery time.
- Checking in-flight transactions and transaction outcomes.

Do not induce node failures or shut down production instances solely for testing without change approval and an impact plan.

### 13.2. DR Testing

- Planned switchover.
- Failover simulation per runbook in a test environment.
- Loss of network transport.
- Standby apply lag.
- Archive gaps.
- Primary unavailable.
- Client reconnection to standby services after role transition.
- Reinstating/rebuilding the former primary.
- Backup restore when neither primary nor standby is usable.

Measure actual RTO/RPO and record evidence. A single successful switchover does not prove all failure scenarios are handled.

### 13.3. Backup Recovery Testing

- Restoring the database from backup.
- Recovering to an SCN/point in time.
- Restoring the control file when needed.
- Recovering the encryption wallet/key.
- Restoring from offsite/immutable copies.
- Verifying business data and application startup.

Backup job success alone is insufficient. Restorability must be verified in a separate failure domain.

### 13.4. Scalability Testing

- Stepping up request rates.
- Increasing concurrency.
- Testing peaks/bursts.
- Testing with one node down.
- Testing standby lag/read routing.
- Checking connection pool behavior.
- Measuring saturation points and headroom.
- Verifying data and business outcomes.

## 14. Key Trade-Offs

### 14.1. Synchronous Transport and Latency

Synchronous redo transport can reduce data loss but increases sensitivity to network latency. Site distance and network quality affect commit latency.

Placing a DR site too far away can make synchronous protection unfeasible for latency SLAs. Choose modes based on business requirements and measure over real networks.

### 14.2. Asynchronous Transport and Data Loss Exposure

Asynchronous transport reduces commit latency impact but can leave unshipped redo when the primary fails abruptly. Transport lag is part of RPO exposure.

Monitoring, sufficient network capacity, and lag-handling runbooks are required.

### 14.3. RAC and Shared Storage/Interconnect

RAC improves node fault tolerance but creates dependencies on the cluster interconnect, shared storage, voting/cluster infrastructure, and clusterware. These components require dedicated redundancy and monitoring.

### 14.4. Standby Read Workloads and Apply Lag

Heavy read queries on a standby can contend for resources with redo apply. If standby lag grows, applications read staler data.

Resource limits/reporting windows, dedicated workload services, and primary-routing policies for read-after-write are needed.

### 14.5. Scale-Out and Distributed Complexity

Sharding can increase capacity but complicates queries, transactions, backups, schema changes, monitoring, and incident response. Operational costs must be factored into total cost of ownership.

## 15. Common Observation Queries

### 15.1. Database Role and Open Mode

~~~sql
SELECT name,
       db_unique_name,
       database_role,
       open_mode,
       protection_mode,
       protection_level,
       switchover_status
FROM v$database;
~~~

### 15.2. Instance Status

~~~sql
SELECT inst_id,
       instance_name,
       host_name,
       status,
       startup_time
FROM gv$instance
ORDER BY inst_id;
~~~

In single-instance environments, V$INSTANCE can be used.

### 15.3. RAC Services

~~~sql
SELECT inst_id,
       name,
       network_name,
       con_id
FROM gv$services
ORDER BY name, inst_id;
~~~

### 15.4. Data Guard Lag

~~~sql
SELECT name,
       value,
       unit,
       time_computed,
       datum_time
FROM v$dataguard_stats
WHERE name IN ('transport lag', 'apply lag');
~~~

### 15.5. Resource Utilization

~~~sql
SELECT resource_name,
       current_utilization,
       max_utilization,
       limit_value
FROM v$resource_limit
WHERE resource_name IN ('processes', 'sessions', 'transactions')
ORDER BY resource_name;
~~~

### 15.6. Top SQL

~~~sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       ROUND(elapsed_time / 1e6, 2) AS elapsed_seconds,
       ROUND(cpu_time / 1e6, 2) AS cpu_seconds,
       buffer_gets,
       disk_reads,
       rows_processed
FROM v$sql
WHERE executions > 0
ORDER BY elapsed_time DESC
FETCH FIRST 20 ROWS ONLY;
~~~

V$SQL counters typically accumulate per child cursor; use snapshots/deltas or execution-level tools to evaluate a single execution. For RAC, use GV$ when viewing across all instances.

## 16. Role Transition and Service Recovery Runbook

Each organization needs detailed runbooks tailored to its topology, Oracle release, Broker setup, client drivers, and approval policies. The steps below form a procedural framework, not direct production failover commands.

### 16.1. Precheck

- Confirm primary DB_UNIQUE_NAME, DBID, and role.
- Confirm standby identity, role, and open mode.
- Confirm transport/apply lag, archive gaps, and protection level.
- Confirm the primary is genuinely unable to serve if performing a failover.
- Determine whether there is any risk of the old primary still accepting writes.
- Confirm approver and incident/change record.
- Confirm service/client routing and DNS/network state.
- Record SCN/sequence numbers and pre-operation state.
- Confirm backup/recovery options if the role transition fails.

### 16.2. Choosing Switchover vs. Failover

- Switchover when the primary is operational and can coordinate the role transition.
- Failover when the primary cannot continue and waiting exceeds business thresholds.
- Do not use failover to handle an isolated application error if the primary database is healthy.
- Never allow both the old primary and the new primary to accept writes simultaneously.

### 16.3. Postcheck

- The new standby/primary assumes the correct role/open mode (the former standby is now primary).
- Database services are started/registered in the right locations.
- Application reconnection and read/write smoke tests succeed.
- Actual RPO is recorded.
- Error rate, latency, and throughput return to acceptable levels.
- Monitoring, backups, and redo transport are re-established.
- Former primary is reinstated/rebuilt per procedure.
- Incident timeline and root cause are documented.

## 17. Selection Matrix by Objective

| Requirement | HA | DR | Scalability |
|---|---|---|---|
| One instance fails | RAC/service failover | Not necessarily | Not the primary goal |
| Loss of a node | RAC can continue | Not necessarily | RAC can distribute load |
| Loss of entire site | Insufficient if intra-site only | Data Guard or restore at another site | Does not solve |
| Accidental data deletion | Does not solve | Standby may replicate the error | Does not solve |
| Increased read requests | Load balancing/caching/standby reads | Standby can support reads in suitable configs | Read scaling |
| Increased write requests | HA aids continuity, does not inherently increase write capacity | DR does not increase primary write capacity | Suitable RAC or sharding/scale-up |
| Need PITR | No | Standby does not replace backups | No |
| Need reduced latency | Service routing and tuning | Standby distance can increase latency | Scale resources/architecture per bottleneck |

## 18. Practice Exercises

Perform in a lab or approved environment.

### Exercise 1 — Identify Failure Domains

Diagram the current topology: applications, services, nodes, instances, storage, sites, standbys, backups, and network. Highlight shared components that could cause simultaneous failures.

### Exercise 2 — Define RTO/RPO

Select an application, define its RTO/RPO, and calculate the corresponding downtime budget. Specify the failure scenarios to which the commitment applies.

### Exercise 3 — RAC Services

In a RAC lab, inspect service placement and status. Perform a planned service relocation per release documentation and measure client reconnection.

### Exercise 4 — Instance Failure

In a lab, simulate an instance becoming unavailable. Observe services, surviving instances, active sessions, and application behavior.

### Exercise 5 — Data Guard Lag

Generate redo workload in a lab. Monitor transport lag and apply lag. Distinguish slow transport from slow apply scenarios.

### Exercise 6 — Switchover

Perform a planned switchover per the lab runbook. Measure role transition time, service startup, and application recovery.

### Exercise 7 — Failover

In an isolated lab, simulate primary unavailability and execute failover per documentation. Record unapplied redo, actual RPO, and reinstate/rebuild steps.

### Exercise 8 — RMAN Restore

Restore a database to a test host/schema from backups and archived logs. Measure restore/recover/open/validation duration.

### Exercise 9 — Logical Error

Simulate an accidental deletion in a lab. Compare standby behavior against Flashback/PITR to understand why replication does not replace backups.

### Exercise 10 — Scale-Up

Increase CPU/memory/storage resources in a test environment. Run the same workload before and after and measure throughput, p95 latency, CPU, and I/O.

### Exercise 11 — RAC Scale-Out

Compare a workload on one node versus multiple nodes. Monitor global cache waits, interconnect, hot blocks, and throughput.

### Exercise 12 — Read Scaling

If the environment has a suitable read-only standby, run a reporting workload and measure apply lag, query latency, primary load, and read consistency.

### Exercise 13 — Shard Key

Design a shard key for a tenant-based orders table. Identify local queries, cross-shard queries, uniqueness, rebalancing, and DR.

### Exercise 14 — Failure Test Report

For each test, record:
- Failure scenario.
- Expected behavior.
- Actual behavior.
- Detection time.
- Decision time.
- Recovery/failover time.
- Actual RTO/RPO.
- Application validation.
- Data correctness.
- Follow-up actions.

## 19. Design and Operations Checklist

### HA

- [ ] Define failure domains to tolerate.
- [ ] Evaluate RAC or an appropriate HA approach.
- [ ] Redundant network, storage, and cluster infrastructure.
- [ ] Services configured for appropriate workloads.
- [ ] Client drivers/pools support required failover behavior.
- [ ] Retry/replay has idempotency and transaction contracts.
- [ ] Sufficient remaining capacity when one node is lost.
- [ ] Rehearse instance/node failures.

### DR

- [ ] Independent site/failure domain.
- [ ] Select Data Guard or backup/restore based on RTO/RPO.
- [ ] Select protection mode based on data loss tolerance and network latency.
- [ ] Monitor transport lag, apply lag, gaps, and datum freshness.
- [ ] Runbooks for switchover/failover/reinstate.
- [ ] Service/client routing tested after role transitions.
- [ ] Independent RMAN backups, offsite/immutable where required.
- [ ] Actual restore tests and measured RTO/RPO.
- [ ] Protect control files, SPFILE, wallet/keystore, and recovery catalog.

### Scalability

- [ ] Identify bottlenecks before scaling.
- [ ] Evaluate scale-up versus scale-out.
- [ ] Load test by concurrency and workload mix.
- [ ] Monitor throughput, p95/p99, CPU, I/O, and waits.
- [ ] For RAC, monitor global cache/interconnect/hot blocks.
- [ ] For sharding, verify shard keys, skew, and cross-shard queries.
- [ ] Evaluate read-after-write and standby lag when scaling reads.
- [ ] Verify N+1 capacity and degraded mode.
- [ ] Evaluate licensing, infrastructure, and operational costs.

### Testing and Governance

- [ ] RTO/RPO and SLOs approved by business owners.
- [ ] Failure scenarios and expected behaviors defined.
- [ ] Change/incident approvals for disruptive testing.
- [ ] Telemetry across application, database, OS, and network.
- [ ] Evidence and timelines recorded after each drill.
- [ ] Owners assigned for follow-up actions and runbooks.
- [ ] Reviews after patches, topology changes, and major incidents.

## 20. Key Takeaways

- HA maintains service when some components fail; DR restores service/data after a major failure domain is lost; scalability increases capacity as workload grows.
- RAC primarily supports instance/node-level HA and can scale out within a cluster; it does not replace DR or backups.
- Data Guard maintains a standby via redo transport/apply and supports role transitions; it does not protect against replicated logic errors.
- RMAN backup/restore provides independent recoverability, including media recovery and point-in-time recovery.
- RTO is the maximum time to restore service; RPO is the maximum tolerable data loss.
- RTO must include detection, decision, failover/restore, service/client reconnection, and application validation.
- Synchronous redo transport can reduce data loss but is sensitive to network latency; asynchronous transport can leave unshipped redo.
- Switchover is a planned role transition; failover is an emergency role transition when the primary cannot continue.
- Load balancing distributes load; failover shifts load away from failed components; retry/replay requires transaction semantics and idempotency.
- Scale-up increases resources of one system; scale-out distributes workload across multiple nodes/databases; neither automatically fixes inefficient SQL or hot blocks.
- RAC scale-out depends on Cache Fusion, interconnect, shared storage, and workload distribution.
- Sharding can scale writes/reads across multiple databases but increases routing, transaction, and operational complexity.
- Partitioning divides objects within one database; sharding distributes data across multiple databases.
- Standby read workloads may be constrained by apply lag and licensing; read-after-write consistency must be designed.
- HA/DR does not replace immutable/offsite backups; replication can replicate accidental deletions or logical corruption.
- Design must measure both normal mode and degraded mode when losing a node/site.
- Choose technology based on failure domains, RTO/RPO, workload, capacity, licensing, and operational capability; rehearse before relying on commitments.

### Oracle Documentation References

- [Oracle Real Application Clusters Administration and Deployment Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/racad/) — RAC architecture, services, Cache Fusion, Clusterware and operations.
- [Oracle Data Guard Concepts and Administration](https://docs.oracle.com/en/database/oracle/oracle-database/19/sbydb/) — Physical/logical standby, redo transport/apply, protection modes, switchover and failover.
- [Oracle Database Backup and Recovery User's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/) — RMAN backup, restore, recovery and validation.
- [Oracle Database High Availability Overview](https://docs.oracle.com/en/database/oracle/oracle-database/19/haovw/) — Oracle HA architecture and solution selection.
- [Oracle Database Sharding Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/shard/) — Shard architecture, shard keys, routing and scaling.
- [Oracle Database Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/) — V$DATABASE, V$INSTANCE, V$DATAGUARD_STATS, GV$ services and performance views.
- [Oracle Database Licensing Information User Manual](https://docs.oracle.com/en/database/oracle/oracle-database/19/dblic/) — RAC, Active Data Guard and other option/feature licensing.

Supported topology, failover behavior, driver capabilities and licensing vary by Oracle release and contract. Confirm the deployed version, platform support matrix and license entitlement; test instance failure, site failover, client reconnect, backup restore and degraded-mode capacity in a representative non-production environment.
