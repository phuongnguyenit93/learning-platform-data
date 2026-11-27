# Overview of RAC, Shared-Database Instances, and Cache Fusion

Oracle Real Application Clusters (RAC) enables multiple Oracle Database instances running on multiple servers to access a single database simultaneously. Each instance has its own SGA memory, background processes, and redo thread, while all instances operate on a shared set of database files. Through this architecture, applications can distribute connections and workload across multiple nodes while continuing to serve requests if an instance or node fails, depending on system configuration and redundancy levels.

The core principle of RAC is **multiple instances, one database**. RAC does not create multiple independent database copies that synchronize later. The instances jointly manage a single logical database and coordinate to preserve consistency when multiple nodes read or modify the same data blocks.

That coordination is achieved via cluster services and inter-instance block transfer mechanisms, most notably **Cache Fusion**. Cache Fusion allows an instance to receive needed data blocks directly from another instance's buffer cache over the interconnect, instead of always re-reading the block from storage. This mechanism is the foundation that enables multiple instances to access data consistently.

## 1. Database, Instance, and Node Are Three Distinct Concepts

In Oracle RAC, three components must be distinguished:

- **Database:** the collection of physical files and metadata that make up a database, such as datafiles, control files, online redo log files, and related files.
- **Instance:** the memory structures and background processes used to manage and access a database. An instance has its own SGA, processes, redo thread, and operational state.
- **Node:** a physical or virtual host participating in the cluster and running an instance.

In a typical single-instance system, one instance manages one database at a time. In RAC, multiple instances across multiple nodes open and access one database concurrently.

```text
             Applications / Clients
                    |
             SCAN / Listeners
                    |
          +---------+---------+
          |                   |
     Node 1                Node 2
   +-----------+         +-----------+
   | Instance 1|         | Instance 2|
   | SGA       |         | SGA       |
   | Processes |         | Processes |
   | Redo T1   |         | Redo T2   |
   +-----+-----+         +-----+-----+
          |                     |
          +------ Interconnect -+
                    |
             Shared Storage
       +---------------------------+
       | Datafiles                 |
       | Control files             |
       | Online redo log files     |
       | SPFILE / other files      |
       +---------------------------+
```

The diagram above is a conceptual model. Each node has its own instance and memory; instances coordinate over the interconnect and access the same database files on shared storage. RAC also requires clusterware components, voting files, OCR, and network services to manage membership, resources, and connections.

### 1.1. One Database Can Have Multiple Instances

For example, a database named `SALESDB` running on two nodes:

| Component | Node 1 | Node 2 |
|---|---|---|
| Database | `SALESDB` | `SALESDB` |
| Instance | `salesdb1` | `salesdb2` |
| SGA | Separate | Separate |
| Background processes | Separate | Separate |
| Redo thread | Thread 1 | Thread 2 |
| Datafiles | Same set of files | Same set of files |
| Online redo logs | Groups belonging to thread 1 | Groups belonging to thread 2 |

The instance name is typically configured via `INSTANCE_NAME`; the database name is `DB_NAME`. In RAC, instances can have different instance names while belonging to the same database. Specific configurations also depend on `DB_UNIQUE_NAME`, CDB/PDB environments, and deployment methods.

### 1.2. Shared Database Does Not Mean Shared Memory

Instances do not share a single SGA. Each instance has its own buffer cache, shared pool, large pool, redo buffer, and other memory areas. A block residing in instance 1's buffer cache does not automatically appear in instance 2's buffer cache.

When instance 2 needs a block for which instance 1 holds an appropriate version, RAC can ship the block across the interconnect using Cache Fusion. Therefore, distinguish between:

- Shared storage: instances access the same database files.
- Private instance memory: each instance has its own SGA and processes.
- Global coordination: instances exchange information to determine where a block resides, who holds modification rights, and which version may be used.

This coordination between private caches and shared persistent storage distinguishes RAC from a simple single-instance model.

## 2. Why Use Oracle RAC?

RAC is commonly deployed to meet requirements for high availability, workload distribution, or horizontal processing scalability.

### 2.1. High Availability

If an instance or node stops operating, the remaining instances can continue serving the database. Application services are configured to redirect new connections to surviving instances. Sessions running on the failed node may be disconnected; applications require appropriate reconnection and retry mechanisms.

RAC does not guarantee that every in-flight transaction continues seamlessly when a node fails. Uncommitted transactions on the lost instance generally must be rolled back or recovered according to database rules. Application Continuity, Transparent Application Failover (TAF), or suitable client/service mechanisms can mitigate impact for certain workloads, but require configuration and testing aligned with application behavior.

### 2.2. Scalability

Multiple instances can process workloads concurrently. Adding nodes can increase aggregate CPU capacity and connection handling if the workload can be distributed effectively.

However, adding nodes does not guarantee linear performance scaling. If multiple instances frequently modify the same block, Cache Fusion and global coordination can incur substantial overhead. Workloads with contention on the same index leaf block, sequence hot spots, or centralized tables may scale poorly as instance count increases.

### 2.3. Workload Distribution

Services help classify workloads and direct connections to appropriate instances. For example:

- `OLTP_SERVICE`: prioritizes short transactional workloads, potentially running on OLTP instances.
- `REPORT_SERVICE`: routes reporting queries to a designated group of instances, if architecture and resources allow.
- `BATCH_SERVICE`: runs batch jobs only on a subset of instances or on a schedule to avoid competing with online transactions.

Service placement, preferred/available instances, and service policies must be designed alongside the application. Do not assume every service automatically balances perfectly or that every connection is always routed to the least loaded node.

## 3. Architectural Components of RAC

### 3.1. Oracle Grid Infrastructure and Clusterware

Oracle Grid Infrastructure provides the cluster foundation to manage nodes and resources. Clusterware monitors node, network, storage, and database/service resource states; it coordinates startup, shutdown, and failover according to configuration.

Common concepts:

| Component | Role |
|---|---|
| Cluster membership | Determines which nodes are currently valid members of the cluster |
| Oracle Clusterware | Manages cluster resources such as databases, instances, listeners, services, and VIPs |
| Voting files | Assist in membership/quorum decisions and prevent multiple node subgroups from each claiming to be the valid cluster |
| OCR (Oracle Cluster Registry) | Stores resource configurations and cluster information managed by Clusterware |
| Cluster interconnect | Private or dedicated network configured for internal cluster communication, including Cache Fusion traffic |
| Node VIP | Virtual IP address of a node, assisting connection redirection when a node fails |
| SCAN | Single Client Access Name, a unified access point for RAC clients |

Voting files and OCR serve different purposes. Voting files participate in membership/quorum; OCR stores cluster configuration. They do not replace database datafiles, control files, or redo logs.

### 3.2. Shared Storage

RAC instances must access a shared set of database files. Shared storage can be provided via SAN, NAS, or Oracle Automatic Storage Management (ASM) depending on supported architectures.

ASM is a purpose-built volume manager and file system for Oracle Database. ASM disk groups can store datafiles, control files, online redo logs, archive logs, and related files. ASM can stripe and mirror data according to its redundancy configuration.

Shared storage does not mean instances arbitrarily write to the same data block without coordination. Block access rights and consistency are coordinated by RAC. Both storage and interconnect are essential; fast shared disks paired with a poor interconnect can still slow down RAC when Cache Fusion traffic is high.

### 3.3. Interconnect

The interconnect is the internal network link between nodes. It carries cluster coordination messages and data blocks transferred between instances. For workloads with heavy cross-instance access, interconnect latency and bandwidth directly impact performance.

Interconnect design must consider:

- Sufficient bandwidth for peak Cache Fusion traffic.
- Low and consistent latency.
- Isolation from uncontrolled application or backup traffic causing congestion.
- Redundancy and network failure detection capabilities.
- Proper MTU, bonding, VLAN, and routing configurations per Oracle and OS guidelines.

Do not check only nominal link speed. Measure latency, packet loss, throughput, and relevant RAC statistics under realistic workloads.

### 3.4. Redo Threads and Undo

Each RAC instance has its own redo thread. When an instance modifies data, redo is written to the online redo log groups of that thread. All threads belong to the same database and must be configured to support recovery and archiving.

Each instance also uses an appropriate undo tablespace for its transaction activity. An instance's transactions are tracked within the database and can be accessed by other instances when recovery or coordination is required.

Do not confuse a redo thread with a separate database. All threads belong to one database; archive logs and recovery must account for all relevant threads.

## 4. How Clients Connect to RAC

Clients typically connect via a service name rather than hardcoding a specific instance. Oracle RAC provides SCAN and listeners to locate an appropriate instance serving the service.

### 4.1. SCAN and SCAN Listeners

SCAN is a unified access name for the cluster. DNS or network configuration resolves the SCAN name to one or more SCAN VIPs. A client sends a connection request to a SCAN listener; the listener redirects the client to the local listener of a node running an instance that provides the service.

Simplified model:

```text
Client
  |
  | connect to sales-scan.example.com:1521 / service SALES_APP
  v
SCAN VIP / SCAN Listener
  |
  +----> Node 1 local listener ----> salesdb1
  |
  +----> Node 2 local listener ----> salesdb2
```

SCAN allows clients to use a stable connection name when the number of nodes or service placement changes. It is neither a database nor a load balancer that routes individual SQL statements. The SCAN listener primarily assists with connection routing; session and workload distribution also depend on service configuration and load balancing policies.

### 4.2. Services as Logical Connection Units

A service represents a workload or application group. A database can have multiple services with different placement, goals, and policies.

Example checking services in the database:

```sql
SELECT name,
       network_name,
       goal,
       clb_goal
FROM dba_services
ORDER BY name;
```

Views and columns may vary by version or privileges. In a RAC environment, `GV$ACTIVE_SERVICES` can be used to see which instances are actively running a service:

```sql
SELECT inst_id,
       name,
       network_name
FROM gv$active_services
ORDER BY name, inst_id;
```

A service can be configured to run on preferred instances and fail over to available instances. With policy-managed databases, server pools can determine where services run. Configuration details are managed via SRVCTL or appropriate administrative tools for the version.

### 4.3. Client-Side Load Balancing and Runtime Load Balancing

Two concepts must be distinguished:

- **Connection load balancing:** distributes new connections across instances providing the service.
- **Runtime connection load balancing:** provides information enabling supported clients to select an instance based on workload/service conditions.

Distributing new connections does not mean an already running SQL statement will migrate to another node. A session remains bound to a single instance for the lifetime of the connection, unless an appropriate failover/replay mechanism is in place.

### 4.4. Connection Configuration Examples

A client can use a connect descriptor with a service name:

```text
salesdb_high =
  (DESCRIPTION =
    (ADDRESS =
      (PROTOCOL = TCP)
      (HOST = sales-scan.example.com)
      (PORT = 1521)
    )
    (CONNECT_DATA =
      (SERVICE_NAME = sales_app.example.com)
    )
  )
```

In JDBC, applications typically specify the service name in a URL such as:

```text
jdbc:oracle:thin:@//sales-scan.example.com:1521/sales_app.example.com
```

Applications should connect using the DBA-published service rather than hardcoding `INSTANCE_NAME` if the goal is workload distribution and failover capability in RAC.

## 5. Global Cache and Global Enqueue Services

Because multiple instances access data concurrently, Oracle requires mechanisms to track block states and locks cluster-wide. Two key services are Global Cache Service (GCS) and Global Enqueue Service (GES).

### 5.1. Global Cache Service (GCS)

GCS coordinates the state and location of blocks across instance buffer caches. When an instance needs a block, GCS determines which cache can supply it, its current state, and how access rights must be transferred.

GCS involves concepts such as:

- Global resource directory: coordination metadata about resources/blocks in the cluster.
- Block ownership/mastership: the instance responsible for coordinating a given resource.
- Block mode: current access state, such as shared or exclusive.
- Current/consistent block: the block version appropriate for reading or modifying.

GCS is not merely a single process or an on-disk metadata table. It is a distributed service coordinating across instances.

### 5.2. Global Enqueue Service (GES)

GES manages global enqueues/resources requiring coordination across instances. It handles cluster-wide locks and synchronization resources, covering many resource types beyond buffer blocks.

GCS focuses on cache/block coordination; GES focuses on global enqueue coordination. In practice, both services interact to maintain consistency and coordinate database operations.

### 5.3. Global Resource Directory (GRD)

The Global Resource Directory stores coordination information for resources managed by RAC. Each resource has a master instance responsible for coordinating its metadata. Mastership can shift based on cluster state or resource management policies.

When an instance requests a block, it does not scan the caches of every node. Global resource management locates where a suitable copy resides and executes the transfer according to the protocol.

## 6. What Is Cache Fusion?

Cache Fusion is the mechanism that enables RAC instances to transfer data blocks directly between buffer caches over the interconnect. It allows one instance to obtain a block from another instance when that block is already cached there, reducing the need to re-read from disk in many cases.

For example, instance 1 has read a block containing `ORDERS` rows. Later, a session on instance 2 needs to read or update the same block. Instance 2 requests appropriate access through the global cache mechanism. If instance 1 holds the block, Oracle can ship it across the interconnect in the required state.

```text
       Instance 1                         Instance 2
  +-------------------+              +-------------------+
  | Buffer Cache      |              | Buffer Cache      |
  | Block B (current) |              | Request Block B   |
  +---------+---------+              +---------+---------+
            |                                  |
            +----------- Interconnect --------+
                       Cache Fusion
                              |
                    GCS coordinates access
```

Cache Fusion is not asynchronous replication between two databases. It is a block-transfer mechanism across caches of instances opening the same database, coordinated by GCS/GES and Oracle consistency rules.

## 7. Block States and How Blocks Are Transferred

To understand Cache Fusion, several block state concepts must be distinguished.

### 7.1. Consistent Read (CR) Block

A consistent read block is a block version constructed to satisfy read consistency as of an appropriate SCN. Oracle can apply undo to build a consistent block version for a query.

A query can perform a consistent read of a block without blocking a transaction modifying the data. If another instance's cache holds a suitable block, the block or needed data can be shipped via Cache Fusion; if an older version is needed, Oracle can apply undo under consistent read rules.

A CR block is not necessarily physically identical to the current block at the present instant. It represents a data version consistent with the snapshot required by the query.

### 7.2. Current Block

A current block is the up-to-date version of a block in cache, used for operations requiring current state and data modifications. A block has only one valid current version at a logical point in time, though multiple CR copies can exist across different instances.

When a transaction needs to modify a block, Oracle must grant appropriate exclusive access. If another instance holds rights or copies, RAC coordinates revoking/transferring state according to the protocol.

### 7.3. Shared and Exclusive Modes

Conceptually:

- Shared mode allows multiple instances to hold suitable copies for reading.
- Exclusive mode grants one instance the right to modify a block under cache coherency rules.

Exact internal mode names and states are managed internally by Oracle. Operators typically monitor wait events or global cache statistics rather than manually controlling block modes.

### 7.4. A Block Read Flow via Cache Fusion

Suppose a session on instance 2 needs to read a block currently held by instance 1:

1. Instance 2 detects the block is not in its local buffer cache.
2. Instance 2 requests the block through the global cache mechanism.
3. GCS determines the resource state and which instance holds a suitable block.
4. Instance 1 can send the block over the interconnect to instance 2.
5. Instance 2 places the block into its buffer cache and continues the query.

This is a conceptual description; the actual protocol includes numerous states and optimizations. Not every cache miss produces the exact same wait event or transfer path.

### 7.5. A Block Write Flow from Another Instance

Suppose instance 1 holds a block in shared state and instance 2 wants to update a row in that block:

1. Instance 2 requests appropriate exclusive access.
2. GCS/GES coordinates the state transition and invalidation of incompatible copies.
3. The instance holding the block may send the current block or perform the action required by the protocol.
4. Instance 2 receives access rights and the block needed to apply the change.
5. Redo for the change is generated and written to instance 2's redo thread.
6. Other instances become aware of the new state via cache coherency mechanisms.

A block is never updated independently on two nodes and merged afterward. RAC coordinates access rights prior to modification to prevent conflicting versions.

## 8. Cache Fusion and Disk I/O

Cache Fusion can reduce physical I/O when the needed block already resides in another instance's buffer cache. However, transferring blocks over the interconnect still incurs latency and CPU cost. A block retrieved from a remote cache is not free.

Consider these scenarios:

| Scenario | General Data Retrieval Path | Costs to Examine |
|---|---|---|
| Block is in local cache | Read from local buffer cache | CPU and memory access |
| Block not in local cache but in remote cache | Cache Fusion over interconnect | Interconnect latency, global cache coordination |
| Block has no suitable cached copy | Read from storage into cache | Storage I/O and cache management |
| Block needing write access is held by another instance | Global coordination and block/right transfer | Global cache waits, interconnect, and contention |

Therefore, observing low physical reads does not imply RAC has zero data access cost. A workload can suffer high global cache waits even with minimal disk reads.

## 9. Global Cache Waits and Performance Diagnostics

When RAC waits for a block or access right from another instance, sessions may record global cache wait events. Event names vary across releases and scenarios, but common groups include:

- `gc cr request`: waiting for a consistent-read block from the global cache.
- `gc current request`: waiting for a current block or appropriate current access rights.
- `gc cr block 2-way` / `gc cr block 3-way`: forms of consistent-read block transfer.
- `gc current block 2-way` / `gc current block 3-way`: forms of current block transfer.
- `gc buffer busy acquire` and `gc buffer busy release`: waits related to buffer/global cache contention in certain situations.

Specific names, detailed semantics, and variants depend on the Oracle release. Do not diagnose based on event name alone; correlate wait time, wait counts, involved objects/blocks, source/target instances, and execution plans.

### 9.1. Viewing Global Cache Waits in a Session

Example checking wait events of the current session:

```sql
SELECT event,
       total_waits,
       time_waited_micro
FROM v$session_event
WHERE sid = SYS_CONTEXT('USERENV', 'SID')
  AND event LIKE 'gc%'
ORDER BY time_waited_micro DESC;
```

With RAC, `GV$` views allow observing across instances:

```sql
SELECT inst_id,
       event,
       total_waits,
       time_waited_micro
FROM gv$system_event
WHERE event LIKE 'gc%'
ORDER BY time_waited_micro DESC;
```

System event counters typically accumulate from instance startup. To evaluate a specific time window, capture two snapshots and compute deltas; watch out for instance restarts or counter resets.

### 9.2. Viewing Cache Transfer Statistics

Global cache statistics can be inspected in `GV$SYSSTAT`:

```sql
SELECT inst_id,
       name,
       value
FROM gv$sysstat
WHERE LOWER(name) LIKE '%gc%'
ORDER BY inst_id, name;
```

Statistic names may vary by release. The query above helps discover available counters; select the appropriate counters and compute deltas before drawing conclusions.

### 9.3. Viewing Block Contention by Object

Views such as `GV$SESSION`, `GV$SESSION_WAIT`, `GV$ACTIVE_SESSION_HISTORY` (if authorized and appropriately licensed), and AWR reports help correlate wait events with SQL, objects, and blocks. Some views or historical data require administrative privileges and may involve separately licensed options; adhere to organizational policy.

Example inspecting waiting sessions:

```sql
SELECT inst_id,
       sid,
       serial#,
       username,
       event,
       wait_class,
       seconds_in_wait,
       sql_id,
       blocking_instance,
       blocking_session
FROM gv$session
WHERE wait_class <> 'Idle'
ORDER BY seconds_in_wait DESC;
```

To pinpoint specific objects/blocks, include row-wait columns such as `ROW_WAIT_OBJ#`, `ROW_WAIT_FILE#`, and `ROW_WAIT_BLOCK#` when applicable and map object IDs via the data dictionary. Not all global cache waits populate meaningful row-wait information.

### 9.4. Distinguishing Normal Cache Transfer from Contention

RAC inherently transfers blocks between instances; some global cache waits represent normal operation. High wait counts alone do not prove a problem. Examine:

- Total wait time and its proportion relative to DB time.
- Average wait time and latency distribution.
- Which SQL statements generate the traffic.
- Which blocks or objects are heavily accessed across multiple instances.
- Whether DML concentrates on the same blocks or index leaves.
- Whether the interconnect shows abnormal latency, packet loss, or bandwidth saturation.
- Whether service placement or workload affinity can be adjusted to reduce cross-instance traffic.

## 10. Affinity, Locality, and Reducing Block Pinging

A common RAC performance issue occurs when multiple instances alternately request write access to the same block. Passing the block back and forth generates global cache traffic and waits. Depending on context, this is often called block pinging or block contention.

For example, two services on two nodes concurrently update a concentrated set of rows in a `COUNTERS` table. If many sessions on both instances repeatedly modify the same block, current ownership may bounce back and forth between nodes.

Ways to reduce this overhead:

- **Workload affinity:** route transactions that frequently access the same data subset to the same instance/service where appropriate.
- **Partitioning:** divide data so distinct workloads primarily touch distinct partitions/blocks.
- **Reducing hot blocks:** redesign indexes or write patterns to avoid multiple sessions updating a concentrated block.
- **Batching:** group small modifications into reasonable batches to reduce coordination frequency and round-trips.
- **Sequence caching:** use appropriate cache sizes to reduce sequence management overhead; avoid `ORDER` if the business does not require cluster-wide ordering.
- **SQL optimization:** reduce repeated access to the same blocks and shorten transaction durations.

### 10.1. Index Hot Blocks

An index with sequentially increasing keys can direct concurrent inserts to the rightmost index leaf block. In RAC, if inserts happen concurrently across multiple instances, that hot block can bounce between nodes.

Solutions depend on index type, version, and workload. Options to evaluate include reverse key indexes for certain equality-lookup patterns, hash-partitioned indexes, or other techniques where suitable. Reverse key indexes are not suited for all range scans; partitioning and index design must be evaluated against actual queries.

### 10.2. Sequences in RAC

A sequence generates numeric values, commonly used for surrogate keys. In RAC, sequences can be cached to reduce coordination and dictionary access overhead.

Example:

```sql
CREATE SEQUENCE order_id_seq
    START WITH 1
    INCREMENT BY 1
    CACHE 1000
    NOORDER;
```

`CACHE` allows each instance to pre-allocate a range of values, reducing the overhead of fetching new values. When an instance fails or restarts, cached but unused values may be lost, leaving gaps in the sequence. Sequences do not guarantee gapless numbering.

`ORDER` enforces dispensing values in global request order per sequence rules, which can increase coordination overhead. For most surrogate keys, uniqueness suffices without strict chronological ordering; `NOORDER` is usually more suitable. If the business requires transaction ordering, use timestamps/commit metadata or explicit business logic rather than assuming sequence numbers reflect commit order.

## 11. RAC and Transaction Consistency

Because multiple instances access a single database, Oracle must maintain read consistency and transaction isolation cluster-wide.

### 11.1. Redo and Undo Still Operate per Transaction

When a session modifies data on instance 1, Oracle generates undo for rollback and consistent reads, as well as redo to recover changes. Redo is written to the thread of the instance performing the modification.

Other instances read committed data according to SCNs and consistent read rules. If the current block is in a remote cache, Cache Fusion can supply it; if an older version is needed, Oracle can construct a CR version using undo.

### 11.2. Commit and Redo Durability

When a transaction commits, Oracle ensures the necessary redo is durably persisted according to commit rules before reporting success. RAC does not alter transaction durability principles. Each instance has its own redo thread, yet the single database manages all threads.

### 11.3. Instance Recovery

If an instance fails, surviving instances detect the membership change and the database performs instance recovery for the failed instance's redo/undo per Oracle recovery mechanisms. Recovery may include rolling forward changes recorded in redo and rolling back uncommitted transactions using undo.

Surviving instances can continue serving once recovery and services are appropriately coordinated. Recovery duration depends on redo volume, cache state, cluster configuration, and workload. RAC does not eliminate the need for backups, media recovery, or Data Guard.

## 12. Handling Node/Instance Failures and Application Services

RAC provides the high-availability foundation, but the application experience depends on how services and clients are configured.

### 12.1. When a Node Fails

A general handling flow:

1. Clusterware detects that a node or instance is no longer active.
2. Cluster membership updates; surviving nodes establish valid cluster membership.
3. Resources and services relocate or start on surviving instances according to policy.
4. The database performs necessary recovery for the failed instance's transactions.
5. Clients can reconnect via SCAN/service; previous sessions may need to be re-established.

If the interconnect experiences a network partition, the cluster must prevent multiple node subsets from operating independently as separate clusters against the same shared storage. Membership/quorum and fencing mechanisms protect data integrity. Voting files, network redundancy, and storage fencing must be operated per Oracle guidelines.

### 12.2. TAF and Application Continuity

Client mechanisms can reduce disruption time:

- **Transparent Application Failover (TAF):** supports session failover for certain connection types and query states. The ability to resume fetching or restore session state depends on statement types and configuration.
- **Application Continuity:** can replay certain requests after failures if the application, driver, service, and database are properly configured.
- **Fast Application Notification (FAN):** broadcasts service/instance state changes so client pools react quickly.
- **Fast Connection Failover (FCF):** allows compatible connection pools to receive FAN events and purge broken connections.

Do not claim that RAC automatically makes every request safe to replay. Applications must manage transaction boundaries, idempotency, side effects, and ambiguous commit outcomes. Sending emails, calling external APIs, or writing files cannot automatically be replayed safely.

### 12.3. Failover Testing

A failover test should verify:

- New connections reach the service on surviving nodes.
- Connection pools evict broken connections and establish fresh ones.
- In-flight transactions on the failed instance resolve properly per rollback/recovery rules.
- Retries do not produce duplicate business transactions.
- Recovery time meets the system's RTO target.
- Committed data remains durable per the RPO target.
- Alerts, monitoring, and runbooks detect the node/service failure.

## 13. How Does RAC Differ from Data Guard and Other HA Models?

RAC and Data Guard solve different problems, though they can be combined within the same architecture.

| Criterion | Oracle RAC | Oracle Data Guard |
|---|---|---|
| Primary objective | Multiple instances accessing one database for HA and workload scaling | Maintaining a standby database to protect against and recover from site/database failures |
| Storage | Instances share the same database files | Primary and standby have separate database files on different storage/sites |
| Instances | Multiple instances open the same database | Primary and standby have distinct database roles; standby may be mounted or open in supported modes |
| Data synchronization | Cache Fusion and redo/transaction coordination within one database | Redo transport and apply from primary to standby |
| Node failure | Other instances in the cluster can continue serving | Standby can transition to primary via appropriate failover/switchover |
| Site failure protection | Does not by itself protect against full site or shared storage loss | Can protect against site failure depending on design and distance |

RAC protects against certain instance/node failures and helps distribute workload within a cluster. Data Guard protects against database/site failures and provides a standby copy. A system requiring both local HA and DR can use RAC at the primary site combined with Data Guard to a standby site.

## 14. Common Views and Commands for Monitoring RAC

### 14.1. Viewing Active Instances

```sql
SELECT inst_id,
       instance_name,
       host_name,
       status,
       database_status,
       startup_time
FROM gv$instance
ORDER BY inst_id;
```

`GV$INSTANCE` aggregates instance information from nodes visible to the database. `V$INSTANCE` reflects only the session's current instance.

### 14.2. Viewing Database and Threads

```sql
SELECT dbid,
       name,
       db_unique_name,
       open_mode,
       database_role
FROM v$database;
```

```sql
SELECT thread#,
       status,
       enabled,
       groups
FROM v$thread
ORDER BY thread#;
```

Columns may vary across releases; verify against the data dictionary when writing long-lived scripts.

### 14.3. Viewing Sessions by Instance

```sql
SELECT inst_id,
       username,
       service_name,
       status,
       COUNT(*) AS session_count
FROM gv$session
WHERE type = 'USER'
GROUP BY inst_id, username, service_name, status
ORDER BY inst_id, username, service_name;
```

This query shows how sessions are distributed across instances. Session count does not equal CPU load or DB time; also inspect active sessions, wait events, and service workload.

### 14.4. Viewing Cache Fusion Statistics

```sql
SELECT inst_id,
       event,
       total_waits,
       time_waited_micro
FROM gv$system_event
WHERE event LIKE 'gc%'
ORDER BY inst_id, time_waited_micro DESC;
```

To investigate a specific interval, take before and after snapshots and compute deltas. Do not compare cumulative totals of two instances with different uptimes without normalizing by time or workload.

### 14.5. Viewing Interconnect and Cluster Resources

Cluster network and resource information can be observed via dynamic performance views, Clusterware utilities, and OS tools. Commands such as `crsctl`, `srvctl`, `olsnodes`, and `asmcmd` are commonly used in Grid Infrastructure/ASM administration; exact syntax depends on release and OS/grid owner privileges.

Conceptual inspection commands:

```text
olsnodes -n
crsctl stat res -t
srvctl status database -db SALESDB
srvctl status service -db SALESDB
```

Run administrative commands only per runbooks and authorized privileges. Do not execute start/stop or resource-modifying commands in production outside change control procedures.

## 15. Why RAC Can Still Be Slow Despite Multiple Nodes

Adding instances does not solve every bottleneck. Common causes include:

### 15.1. Block Pinging and Hot Blocks

Multiple instances repeatedly request write access to the same block. This causes current block transfers, increasing global cache waits and interconnect traffic. Identify the objects/indexes/segments and DML patterns causing concentration.

### 15.2. Lack of Workload Locality

Sessions across multiple nodes access the same hot data, even when the workload could be grouped by tenant, customer, or service. Routing workload to preserve locality can reduce cross-instance block transfers.

### 15.3. Interconnect Latency or Congestion

Cache Fusion relies on the interconnect. Slow networking, packet loss, congestion, or misconfiguration can drive up global cache waits even when storage performs well.

### 15.4. Hot Index Leaf Blocks

Sequentially increasing index keys can concentrate inserts into a few leaf blocks. In RAC, multiple instances writing to the same index region can create contention. Evaluate index design, sequence caching, reverse key/hash partitioning, and workload before choosing a fix.

### 15.5. Poor SQL and Execution Plans

SQL processing too many rows, using poor join orders, or performing excessive repeated lookups remains slow on RAC. SQL tuning, statistics, and indexing remain essential; RAC does not replace statement-level tuning.

### 15.6. Suboptimal Service Placement

If every service runs on every node even when workloads have affinity, transactions can increase cross-instance traffic. Grouping services and connection pools by workload can improve locality, while avoiding overloading a single node.

### 15.7. Saturated Shared Storage or CPU

RAC does not infinitely scale storage bandwidth or CPU. If shared storage is the bottleneck, adding instances can intensify contention. Evaluate CPU, I/O, interconnect, and global cache together.

## 16. RAC Design and Operational Principles

A stable RAC system requires end-to-end design from cluster to application:

1. **Node and cluster design:** ensure node, voting files, OCR, network, and storage redundancy per supported architectures.
2. **Shared storage design:** select appropriate ASM/storage, provide redundant access paths, and monitor latency.
3. **Interconnect design:** size bandwidth and latency for expected Cache Fusion traffic.
4. **Service design:** classify workloads, define preferred/available instances, and set connection policies.
5. **Connection pool design:** use service names, support FAN/FCF or appropriate driver mechanisms, and control reconnections.
6. **Transaction design:** keep transactions short, implement idempotent retries, and avoid holding locks during slow external calls.
7. **Data locality design:** avoid multiple instances modifying the same blocks when workloads can be partitioned or routed.
8. **Sequence/index design:** consider caching, hot blocks, and indexing strategies for concurrent inserts.
9. **Cluster-wide monitoring:** observe by `INST_ID`, service, SQL, wait class, global cache, and interconnect.
10. **Failure testing:** test node loss, network interruptions, service failover, and transaction/application behavior.

## 17. Practice Exercise: Monitoring an Application Across Two Instances

Assume database `SALESDB` has two instances `salesdb1` and `salesdb2`. The application connects via service `sales_app`.

### Step 1: Verify Both Instances

```sql
SELECT inst_id,
       instance_name,
       host_name,
       status
FROM gv$instance
ORDER BY inst_id;
```

### Step 2: Check Where the Service Is Running

```sql
SELECT inst_id,
       name,
       network_name
FROM gv$active_services
WHERE name = 'sales_app'
   OR network_name LIKE '%sales_app%'
ORDER BY inst_id;
```

### Step 3: Check Application Connections

```sql
SELECT inst_id,
       service_name,
       COUNT(*) AS sessions
FROM gv$session
WHERE type = 'USER'
GROUP BY inst_id, service_name
ORDER BY inst_id, service_name;
```

### Step 4: Observe Global Cache Waits

```sql
SELECT inst_id,
       event,
       total_waits,
       time_waited_micro
FROM gv$system_event
WHERE event LIKE 'gc%'
ORDER BY inst_id, time_waited_micro DESC;
```

### Step 5: Execute a Representative Workload

Run identical types of transactions across both instances, recording SQL ID, service, wait events, logical reads, and elapsed time. Compare when the workload is spread across instances versus routed with appropriate affinity. Do not generate test load in production without a plan and safety limits.

### Step 6: Evaluate

- Are sessions distributed as expected?
- Do global cache waits increase when two instances modify the same hot dataset?
- Does the interconnect exhibit abnormal latency or throughput?
- Does SQL create excessive block accesses or index hot spots?
- Can service placement improve locality without unbalancing nodes?

## 18. Common Misconceptions to Avoid

| Misconception | Accurate Understanding |
|---|---|
| RAC is multiple databases synchronizing with each other | RAC is multiple instances concurrently opening one database |
| Instances share the same SGA | Each instance has its own SGA and processes |
| Cache Fusion is disk replication | Cache Fusion transfers blocks between buffer caches over the interconnect |
| Having shared storage is enough to run RAC | Requires Grid Infrastructure, cluster membership, interconnect, and global coordination |
| RAC guarantees sessions are never disconnected | Sessions on a failed node may drop; reconnect/replay depends on client/service and application |
| Adding nodes always scales performance linearly | Global cache traffic, hot blocks, CPU, and storage can limit scalability |
| Low physical reads mean RAC has no bottlenecks | Global cache waits can be high even when disk I/O is low |
| SCAN is a load balancer for individual SQL statements | SCAN assists with connection routing; a session stays bound to its connected instance |
| Sequences in RAC always increment in commit order | Sequences dispense values per sequence rules, do not guarantee commit order, and can have gaps |
| RAC replaces Data Guard | RAC handles intra-cluster HA/scaling; Data Guard provides a standby/DR at another database/site |
| Every `gc%` wait is an error | Evaluate latency, total wait time, SQL, objects, and workload before concluding |

Oracle RAC combines multiple instances with a single shared database to improve availability and distribute workloads. Each instance maintains its own memory and processes while coordinating through Clusterware, GCS/GES, and the interconnect. Cache Fusion transfers blocks between buffer caches to maintain consistency without always re-reading from storage. RAC performance depends not only on node count but also on data locality, service design, SQL, indexing, the interconnect, and how applications handle connection failures.
