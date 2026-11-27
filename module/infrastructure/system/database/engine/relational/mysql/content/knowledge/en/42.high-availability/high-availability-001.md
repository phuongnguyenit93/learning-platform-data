# Distinguishing High Availability, Disaster Recovery, and Scalability

This lesson belongs to the **DATABASE_MYSQL** module. When operating MySQL for real-world applications, the system must continue serving when a component fails, recover after a major incident, and handle increasing load over time. These three goals are related but not identical: **High Availability (HA)** reduces service disruption, **Disaster Recovery (DR)** restores the system after a severe failure, and **scalability** handles more requests or larger data volumes.

A multi-server cluster does not automatically guarantee good HA; a replica is not a backup; and adding a read replica does not directly increase write capacity. To choose the right architecture, you need to identify the types of failures to tolerate, acceptable data loss, recovery time, read/write workload characteristics, and how the application connects to MySQL.

## 1. Three goals: HA, DR, and scalability

### 1.1. High Availability (HA)

HA is a design that enables a service to continue operating or quickly resume operation when a component fails. For MySQL, that component may be the `mysqld` process, a physical/virtual server, disk, network, proxy, or a cluster member.

HA typically relies on redundant components, failure detection mechanisms, role switching (failover), connection routing, and automated or semi-automated recovery procedures. The goal is to minimize downtime within the scope of anticipated failures.

Example: the MySQL source stops working, and an up-to-date replica is promoted to become the new primary. A proxy or MySQL Router redirects write connections to the new primary so the application can keep working.

### 1.2. Disaster Recovery (DR)

DR is the ability to restore services and data after a large-scale incident, such as losing an entire data center, a cloud region outage, shared storage failure, destructive attacks, or administrative mistakes that destroy data across multiple servers.

DR typically requires an independent location or failure domain, isolated backups, binary logs stored outside the source system, configuration data and encryption keys, along with recovery runbooks. DR can take longer than HA because you must provision or activate the standby environment, verify data integrity, and switch the application over.

Example: the entire cloud region hosting the primary and its replicas goes down. The operations team activates a cluster in another region, restores the latest backup, replays binary logs stored outside the failed region, and points the application to the new endpoint.

### 1.3. Scalability

Scalability is the ability to increase processing capacity as the number of users, queries, or data volume grows. Two fundamental approaches:

- **Vertical scaling (scale up):** increasing CPU, RAM, IOPS, or storage capacity on the existing MySQL server.
- **Horizontal scaling (scale out):** distributing load across multiple servers, such as read replicas for read queries or sharding to partition data and write load.

HA focuses on fault tolerance and service continuity. Scalability focuses on processing capacity. A read replica can serve both as a failover candidate and as a read-query target, but the two roles can compete for resources and must be designed explicitly.

### 1.4. Comparison table

| Criterion | HA | DR | Scalability |
|---|---|---|---|
| Goal | Minimize disruption when a component fails | Recover after a major disaster | Handle growing load or data volume |
| Failure scope | Process, host, node, or a small failure domain | Site/region outage, data destruction, wide-area failure | CPU, I/O, connection overload, or architectural limits |
| Typical mechanisms | Replicas, quorum, failover, routing | Independent backups, binlog archive, standby site | Scale up, read replicas, cache, sharding |
| Key metrics | Availability, failover time, RTO/RPO | Post-disaster RTO/RPO | Throughput, latency, capacity |
| Testing | Node failure, network partition, switchover | Restore and site failover drills | Load test, capacity test, benchmark |

A production architecture usually needs all three goals, but you should not assume a single mechanism solves all of them.

## 2. Measuring availability and recovery objectives

### 2.1. Availability and downtime

Availability is commonly expressed as the percentage of time a service is operational over an observation window:

\[
Availability = \frac{Uptime}{Total\ observation\ time} \times 100\%
\]

Common availability levels correspond to the following theoretical maximum downtime:

| Availability level | Approximate max downtime per 365-day year |
|---|---:|
| 99% | 3 days 15 hours 36 minutes |
| 99.9% | 8 hours 45 minutes 36 seconds |
| 99.95% | 4 hours 22 minutes 48 seconds |
| 99.99% | 52 minutes 34 seconds |
| 99.999% | 5 minutes 15 seconds |

This is a mathematical conversion and does not account for how an SLA contract defines maintenance windows, exclusions, or rounding rules. Database availability also does not automatically equal application availability: if the application, DNS, proxy, or network is down, users still cannot access data.

You should measure availability using checks from the application's perspective, such as connecting, executing a representative transaction, and receiving the correct result. Checking only whether the `mysqld` process is alive is not enough.

### 2.2. RTO and RPO

Two key metrics when designing HA and DR:

- **RTO (Recovery Time Objective):** the maximum acceptable downtime an organization can tolerate before the service is restored.
- **RPO (Recovery Point Objective):** the maximum acceptable data loss, usually measured as the time interval between the recovery point and the time of failure.

For example, an RTO of 10 minutes and an RPO of 30 seconds mean the target is to restore the service within 10 minutes while tolerating the loss of at most roughly 30 seconds of the most recent data. These are design targets, not automatic guarantees from MySQL. They must be measured through drills and validated with system owners.

HA and DR can have different RTO/RPO targets. An HA cluster within the same region might promote a new primary in tens of seconds, whereas DR in another region might need tens of minutes to rebuild data and switch the application. If business requirements demand the same RPO/RTO for both, cost and complexity increase significantly.

## 3. Identifying failure domains before choosing an architecture

HA/DR design requires identifying what can fail together at the same time. Common failure domains include:

| Failure domain | Example | Mitigation |
|---|---|---|
| Process | `mysqld` crash, plugin failure | Controlled restart, monitoring, standby node |
| Server | Host, VM, or instance unreachable | Replica on a different host, failover |
| Storage | Volume failure, out of space, corruption | Storage redundancy, independent backups, restore verification |
| Rack/AZ | Power, network, or infrastructure outage in one zone | Place nodes across separate failure zones |
| Region/site | Loss of an entire region or data center | DR cluster in an independent region, off-site backups |
| Human/software error | Accidental `DROP TABLE`, faulty migration, bug writing corrupt data | Backups, binlogs, change control, PITR |
| Security | Ransomware, credential leak, sabotage | Isolated accounts, least privilege, immutable backups with separated permissions |

Placing three MySQL instances on the same physical host provides no redundancy against host failure. Placing replicas on the same storage or network domain can also cause them to fail together. Redundancy only helps when components do not share a single point of failure.

An HA system must also eliminate **single points of failure (SPOF)** at other layers: a single proxy, non-redundant DNS, an unreachable secret store, a single network path, or a failover procedure that only one person knows how to execute.

## 4. Common HA models for MySQL

### 4.1. One primary and one or more asynchronous replicas

This is the classic source/replica model. The application writes to the primary; replicas receive the binary log and apply transactions afterward. When the primary fails, a sufficiently up-to-date replica can be promoted to become the new primary.

```text
                      +------------------+
Application writes -->| Primary MySQL    |
                      | Binary log       |
                      +------------------+
                         |           |
               async     |           | async
                         v           v
                  +----------+  +----------+
                  | Replica A|  | Replica B|
                  +----------+  +----------+
                         |
                 application reads
```

Advantages:

- Simpler to deploy than synchronous/quorum clusters.
- Replicas can serve read queries.
- A replica can be promoted when the primary fails.
- Supports backups and PITR from binary logs.

Limitations:

- Asynchronous replication introduces lag; a replica may not have received or applied the latest transactions when the primary fails.
- Failover requires identifying the replica with the most complete data, preventing the old primary from accepting writes, and updating endpoints.
- If the application writes directly to a replica or there are multiple write paths, the risk of data divergence increases.
- A mistaken operation or corrupted data can be replicated to replicas.

This model fits when a certain RPO is acceptable, a clear failover runbook exists, and read scaling is needed. Using GTIDs makes it easier to identify executed transactions and reconfigure replication after role changes.

### 4.2. Semi-synchronous replication

Semi-synchronous replication adds replica acknowledgment to the source's commit path. Depending on the plugin and configuration, the source waits for at least one replica to acknowledge that it has received and written the event to its relay log before completing the commit under semi-sync mode.

Key nuance: acknowledging log receipt does not mean the replica has already applied the transaction to its data tables. Semi-sync narrows the data-loss window in certain scenarios, but it does not automatically guarantee zero data loss across all failures. If no replica acknowledges within the configured timeout, the mechanism can time out and fall back to asynchronous behavior according to configuration.

Therefore, semi-sync is a way to improve RPO within a source/replica topology; it is not equivalent to a quorum-based consensus cluster and does not replace backups or DR.

### 4.3. InnoDB Cluster and Group Replication

**MySQL InnoDB Cluster** combines Group Replication, MySQL Shell, and MySQL Router to build a MySQL cluster with built-in membership management and connection routing. Group Replication uses group messaging and consensus so members agree on the order of accepted transactions.

Two main operating modes:

- **Single-primary:** one member accepts writes; the remaining members act as secondaries. When the primary fails and the cluster retains quorum, an eligible secondary can be elected as the new primary.
- **Multi-primary:** multiple members can accept writes. Group Replication checks for transaction conflicts; conflicting transactions can be rejected and the application must handle retries. This mode demands more careful data and application design.

Single-primary is generally easier to operate and more predictable for most OLTP applications. Multi-primary does not mean all write transactions run in parallel without conflict; transactions modifying the same data can hit certification failures or rollbacks.

In a three-member cluster, the majority is two members. If one member fails, the remaining two can maintain quorum. If the network partitions into one member on one side and two on the other, the majority side can continue while the minority side must not independently accept writes. In a five-member cluster, three votes are needed for a majority.

Quorum is essential to prevent both sides of a network partition from operating as independent primaries. Therefore, avoid designing a cluster with a member count or placement where a common network incident causes loss of majority.

### 4.4. Role of MySQL Router

MySQL Router provides endpoints so applications connect based on cluster roles. Instead of hardcoding a static primary IP in the application, Router routes connections to the primary or secondaries according to cluster metadata and routing configuration.

Router does not store data and does not replace Group Replication's consensus mechanism. It must be deployed redundantly, monitored, and placed close to the application in alignment with the topology. Applications still need to handle connection errors, reconnects, and transactions with unknown outcomes during primary transitions.

### 4.5. Single-primary InnoDB Cluster diagram

```text
                       +------------------+
Application ---------->| MySQL Router     |
                       | R/W endpoints    |
                       +------------------+
                                |
                    +-----------+-----------+
                    |           |           |
                    v           v           v
               +---------+ +---------+ +---------+
               | Node 1  | | Node 2  | | Node 3  |
               | Primary | |Secondary| |Secondary|
               +---------+ +---------+ +---------+
                    Group Replication / quorum
```

This is a logical diagram. In real deployments, Router should run with multiple instances and nodes should be distributed across appropriate failure domains. Placing three nodes across three AZs improves AZ fault tolerance, but network latency and quorum requirements must be evaluated.

## 5. Failover and switchover

Two operations that are often confused:

- **Failover:** an unplanned switch to another server because the current primary has failed or is no longer safe to serve traffic.
- **Switchover:** a planned role transfer, such as for primary maintenance, upgrades, or shifting the active region.

### 5.1. Failover procedure for source/replica

A failover runbook should include these steps:

1. **Detect and confirm failure:** check application health checks, `mysqld` status, network, storage, and reachability of the primary.
2. **Fence the old primary:** prevent the old server from accepting further writes. This may require network isolation, stopping the service, or infrastructure-level fencing. Simply removing the endpoint from a load balancer may not stop other clients from writing directly.
3. **Select a replica:** compare retrieved/executed GTIDs or binlog coordinates to identify the replica with the most recent data matching the RPO target.
4. **Finish applying logs:** if the old primary is still reachable, collect remaining transactions per the runbook. Never assume every committed transaction is present on an asynchronous replica.
5. **Promote:** configure the chosen replica as the new primary, enable writes according to policy, and verify data.
6. **Redirect connections:** update Router, proxy, service discovery, or application endpoints.
7. **Reconfigure remaining replicas:** point the other replicas to the new primary, which is typically much simpler when GTIDs are enabled.
8. **Post-failover monitoring:** monitor application errors, transaction retries, replication lag, data integrity, and disk capacity.

Never promote a replica before preventing the old primary from accepting writes. If both accept writes simultaneously, the system can enter **split-brain**: two independent data branches are both treated as authoritative. Reconciling the data afterward can be very difficult or impossible to automate.

### 5.2. Planned switchover

A safe switchover typically includes:

1. Choosing a low-traffic window and announcing the maintenance window.
2. Stopping or locking new writes to the old primary per application procedure.
3. Waiting for the target replica to receive and apply all required transactions.
4. Verifying data, GTIDs, or replication coordinates are synchronized.
5. Switching primary/replica roles and connection endpoints.
6. Re-enabling writes, verifying the new replication stream, and monitoring the application.

Switchover can achieve an RPO of 0 for synchronized transactions under proper procedural control, though specific topology conditions must be verified. Do not claim "zero data loss" unless commit behavior, fencing, and replica state under failure conditions have been proven.

## 6. DR: designing an independent recovery environment

HA typically handles component failures within a cluster or region. DR prepares for cases where the entire active region becomes unusable or primary data is corrupted/destroyed.

### 6.1. Components of a DR solution

- **Standby site/region:** a MySQL instance or cluster in an independent failure domain with sufficient resources to recover critical workloads.
- **Independent backups:** full and incremental backups stored outside the primary site, with retention policies and deletion protection.
- **Binary log archive:** continuous shipment of binlogs to independent storage to support recovery to a chosen point in time.
- **Configuration and secrets:** secure storage of MySQL configuration, TLS certificates, keyrings, encryption keys, service accounts, and routing information.
- **Runbook:** instructions for restoring, replaying binlogs, verifying data, switching endpoints, and failing back to the primary site.
- **Drills:** periodic recovery exercises in the DR environment to measure actual RTO/RPO.

A replica in another region can reduce recovery time when the primary site fails, but relying solely on a replica means accidental deletions or corrupted data can still be replicated. Immutable backups and an independent binlog archive remain essential.

### 6.2. Site-level active-passive and active-active

| Model | How it works | Advantages | Limitations |
|---|---|---|---|
| Active-passive | One site accepts writes; DR site syncs data and waits for activation | Simple write path, easier conflict control | Requires switching applications and resources during DR; replica may lag |
| Active-active | Multiple sites serve traffic concurrently | Can distribute load and shorten cutover time in some architectures | Complex write conflict handling, routing, consistency, and operations |

Cross-site replication does not automatically produce safe active-active operation. If two sites write to the same data concurrently, you need explicit data partitioning or conflict resolution. For most transactional MySQL systems, active-passive is far easier to control.

### 6.3. DR sequence when the primary site is lost

1. Confirm the scope of the disaster and decide to activate DR according to pre-approved authorization.
2. Isolate the old site if there is any risk it could come back online and accept parallel writes.
3. Identify the latest good backup and the contiguous binlog archive.
4. Initialize or verify the cluster at the DR site; restore the backup and replay logs to the selected recovery point.
5. Verify databases, objects, privileges, keyring, business data, and application behavior.
6. Switch DNS, Router, proxy, or service discovery configuration to the DR site.
7. Monitor traffic, latency, connection errors, and consistency after opening the service.
8. Plan failback to the primary site after it is repaired and safely resynchronized.

Failback is another full cutover, not simply turning the old server back on. You must establish which site is authoritative, synchronize data in a controlled single direction, verify synchronization points, and only then switch roles.

## 7. Scaling MySQL

### 7.1. Scale up

Adding CPU, RAM, storage, or IOPS can improve performance when the server is resource-bound. This is usually the simplest way to increase a primary's capacity, but it faces hardware limits, cost constraints, and change windows. Scaling up does not create extra data copies and does not protect against single-server failure.

Before upgrading hardware, measure CPU, memory pressure, buffer pool hit ratio, disk latency, IOPS, connection count, lock waits, transaction duration, and query latency. If the bottleneck is missing indexes or long-running transactions holding locks, adding CPU/RAM may only help partially.

### 7.2. Scaling reads with replicas

Read replicas can serve read queries to offload the primary. The application or a proxy layer classifies queries and routes eligible reads to replicas.

Important considerations:

- Asynchronous replicas can lag, so reading immediately after a write might not reflect recently committed data.
- Read-after-write workflows must read from the primary or wait for the replica to catch up to the relevant GTID/position.
- Heavy queries on a replica can slow down the applier and increase replication lag.
- Do not blindly offload reads if the replica is also needed as a failover candidate; excessive read load can prevent it from keeping up.
- Limit connections and balance load; each replica carries its own CPU, RAM, storage, and operational cost.

Read scaling increases read capacity. It does not directly distribute write transactions; the primary can still be a bottleneck for write-heavy workloads.

### 7.3. Scaling writes with sharding

When a single primary cannot handle the write load, data can be partitioned into multiple shards. Each shard is a subset of data managed by its own server or cluster; the application routes operations to the shard holding the corresponding data.

For example, customer data can be range-partitioned by `customer_id`:

```text
customer_id 0..999999       -> Shard A
customer_id 1000000..1999999 -> Shard B
customer_id 2000000..2999999 -> Shard C
```

This is only an example of range partitioning. Choosing a shard key requires evaluating data distribution, growth patterns, common query patterns, and shard mobility. If most queries need to join data across multiple shards, complexity and network overhead rise sharply.

Sharding distributes write load and storage capacity, but introduces:

- Query routing and shard metadata management.
- Difficulty performing cross-shard transactions and guaranteeing consistency.
- Difficulty with global joins, sorting, aggregations, and reporting.
- Need for shard rebalancing, splitting/merging, and handling skewed shards.
- Each shard still needs its own HA, backups, PITR, and DR.

Do not shard before measuring and optimizing schema, indexes, queries, connection pooling, transactions, and server configuration. Table partitioning inside a single MySQL instance is also not equivalent to sharding: partitioning organizes data within one table/instance and does not create separate servers or independent failure domains.

### 7.4. Caching and connection pooling

Caching can reduce repetitive queries to MySQL, especially for read-heavy, infrequently changing data. Design TTLs, invalidation, and cache-failure fallback carefully to prevent stale data or turning the cache into a new failure point.

Connection pools reuse connections, cap connection counts, and reduce the overhead of frequent connection creation. During failover, the pool must evict stale connections, reconnect using backoff, and avoid a thundering herd of simultaneous reconnects overwhelming the new primary.

## 8. Choosing an architecture based on requirements

| Requirement | Candidate model | What to validate |
|---|---|---|
| Small system, longer downtime acceptable | Single MySQL + backups/PITR | Restore duration, actual RPO/RTO |
| Basic failover and read scaling | Primary + async replicas | Lag, promotion, fencing, routing |
| Smaller data-loss window on source/replica | Semi-sync replication | Timeout, number of acking replicas, behavior on disconnect |
| Quorum management and automatic primary election | InnoDB Cluster / Group Replication | Member count, quorum, latency, Router, and runbook |
| Region-wide fault tolerance | DR cluster or replica in another region + backup/binlog archive | Cross-region latency, RPO/RTO, failover/failback |
| Higher read throughput | Read replicas, cache | Read-after-write, lag, applier load |
| Write load exceeding a single primary | Sharding or partitioned data architecture | Shard key, cross-shard transactions, rebalancing |

Selection should start from business requirements: how critical the service is, how much downtime is tolerable, how much data can be lost, read/write workload profile, and operational budget. Only then should you choose the topology and tooling.

## 9. Applications must be built to survive failover

A database may fail over cleanly while the application still errors out if connections and transactions are not handled properly.

### 9.1. Controlled reconnection

- Use a stable endpoint via Router, proxy, or service discovery instead of hardcoding the primary IP.
- Configure connection timeouts and retries with exponential backoff and jitter.
- On failover, drain/reset the connection pool to drop connections to the old primary.
- Cap retry counts and total retry duration to avoid overloading a recovering database.

### 9.2. Transactions with uncertain outcomes

If a connection drops during `COMMIT`, the application may not know whether the server committed the transaction. Blindly retrying the transaction can create duplicate actions if the operation is not idempotent.

For critical workflows like payments or order creation, implement idempotency keys, unique constraints, or reconciliation mechanisms so a request is processed at most once at the business level. Never assume a connection error means the transaction rolled back.

### 9.3. Read consistency on replicas

If a user updates data and immediately reads it back, the application must guarantee read-after-write consistency. A simple approach is reading from the primary for a short window after a write. For stricter requirements, wait for the replica to apply up to a known GTID or binlog position if supported by the version and topology.

Do not send all read queries to replicas without considering semantics. Reports may tolerate a few seconds of lag; payment confirmation pages typically must show the latest state immediately.

## 10. Monitoring and drills

An HA/DR system must monitor health and recoverability, not just CPU and RAM.

### 10.1. Metrics to track

- **Availability:** synthetic connections and transactions from the application's perspective.
- **Replication:** receiver/applier state, replication lag, retrieved/executed GTIDs, relay log growth, and replication errors.
- **Group Replication:** member status, current primary, quorum, member state, and group communication errors.
- **Database:** connection saturation, query latency, lock waits, deadlocks, long-running transactions, CPU, memory, disk latency, and disk space.
- **Backup/DR:** timestamp of last successful backup, binlog archive age, checksums, storage capacity, restore drill results, and measured RTO/RPO.
- **Routing:** Router/proxy health, primary endpoint, DNS errors, and routing update latency.

Set alert thresholds tied to business targets. For example, replication lag should trigger an alert before exceeding RPO or before a replica falls too far behind to catch up before binlogs expire.

### 10.2. Controlled drills

At a minimum, drill the following scenarios:

1. Stop the MySQL process on the primary and measure detection time, failover time, and application reconnection time.
2. Break network connectivity between members to verify quorum behavior and split-brain prevention.
3. Simulate high replica lag or a stopped applier to verify alerts and runbooks.
4. Simulate losing an entire AZ/site to execute the DR procedure.
5. Accidentally delete data in a test environment to verify backups and PITR.
6. Perform failback after the primary site recovers to verify data integrity and safe role transition.

Record start time, detection time, database ready time, application healthy time, data loss amount, and manual steps taken. Only these measurements prove your actual RTO/RPO.

## 11. Common misconceptions to avoid

1. **Having a replica means having a backup:** false. Replicas can replicate accidental deletions or corrupted data. Independent backups and PITR are required.
2. **Having three nodes means zero downtime:** false. Loss of quorum, network, storage, Router, or application issues can still cause service disruption.
3. **Failover is always lossless:** false for asynchronous replication; replicas can miss the latest transactions.
4. **Adding read replicas speeds up writes:** false. They mainly offload reads; the primary still processes the write stream.
5. **Semi-sync equals quorum synchronization:** false. Acknowledgment conditions and timeout fallbacks differ from Group Replication.
6. **Automatic failover is always safer than manual:** not necessarily. False failure detection or missing fencing on the old primary can cause split-brain.
7. **DR only needs a replica in another region:** false. You need independent backups, binlogs, configurations, keys, endpoints, and recovery drills.
8. **Partitioning is sharding:** false. Partitioning does not automatically distribute workloads across independent instances.

## 12. HA/DR and scaling design checklist

- [ ] Read/write workload, availability target, RTO, and RPO are defined.
- [ ] Failure domains and SPOFs across database, network, routing, storage, and application are mapped.
- [ ] Replicas or cluster members are distributed across appropriate failure domains.
- [ ] Synchronization mode (async, semi-sync, or Group Replication) is chosen with clear understanding of data guarantees.
- [ ] Fencing is in place so the old primary cannot accept writes after failover.
- [ ] A stable endpoint is chosen and connection pooling behavior is tested across primary transitions.
- [ ] Independent backups, binlog archiving, retention, encryption, and key protection are designed.
- [ ] Procedures exist for restore, PITR, failover, switchover, DR, and failback.
- [ ] Replication lag, quorum, transaction latency, connections, and disk capacity are monitored.
- [ ] Read load on replicas is tested and a read-after-write policy is defined.
- [ ] Shard keys are evaluated if write load exceeds a single primary's capacity.
- [ ] Drills have been executed and actual RTO/RPO recorded.

## 13. Self-check

1. How does HA differ from DR in failure scope and recovery objectives?
2. Why might an asynchronous replica not contain the last transaction when the primary fails?
3. What does semi-synchronous replication acknowledge, and why does that not mean the transaction has already been applied on the replica?
4. What role does quorum play in Group Replication during a network partition?
5. Why must the old primary be fenced before promoting a replica?
6. What part of the InnoDB Cluster architecture does MySQL Router solve, and what components does it not replace?
7. Why do read replicas help scale reads without solving write bottlenecks on their own?
8. What benefits does sharding bring, and what challenges does it introduce for transactions, joins, and operations?
9. Why do transactions disconnected during `COMMIT` require idempotency or reconciliation?
10. Propose an architecture for an application requiring an RTO of 10 minutes, RPO of 1 minute, a DR site, and high read load; describe how you would test it to prove the targets.

When designing MySQL for production, connect business requirements with failure domains, synchronization mechanisms, application endpoints, backups, and runbooks. An architecture is only trustworthy once tested under representative failure scenarios with measured results meeting agreed targets.
