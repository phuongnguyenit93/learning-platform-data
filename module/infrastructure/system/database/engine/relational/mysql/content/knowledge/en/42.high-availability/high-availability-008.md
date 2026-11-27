# InnoDB Cluster, MySQL Shell AdminAPI, and Boundaries with Group Replication

InnoDB Cluster is MySQL's solution for building highly available database clusters. It combines Group Replication to synchronize transactions across members, MySQL Shell AdminAPI to create and manage clusters, and MySQL Router to route application connections. Group Replication is the data communication and consensus layer; AdminAPI is the lifecycle management layer; Router is the client connection layer. Understanding these three roles helps you design clusters properly, handle failures safely, and avoid false expectations about data protection.

This lesson belongs to the **High Availability** chapter of the **DATABASE_MYSQL** module. Along the path to mastering MySQL—from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, execution plans, query tuning, privileges, and backups—InnoDB Cluster keeps services running when a member fails. An HA cluster still requires separate backups, PITR, monitoring, and a disaster recovery plan.

## 1. What components make up InnoDB Cluster?

A standard InnoDB Cluster consists of three components:

- **Group Replication:** the MySQL plugin coordinating group membership, exchanging transactions, checking conflicts, and keeping cluster state consistent.
- **MySQL Shell AdminAPI:** the administrative API for checking instance configuration, creating clusters, adding or removing members, inspecting topology, and changing the primary.
- **MySQL Router:** a proxy accepting application connections and routing them to the appropriate member using cluster metadata.

High-level architecture:

~~~text
                 Application
                      |
                      v
                MySQL Router
                 /        \
          read/write      read-only
               |              |
               v              v
          Primary node    Secondary nodes
               \              /
                \            /
                 Group Replication
              (membership + certification)

        MySQL Shell AdminAPI
           |      |      |
           +---- administers ----+
              cluster members
~~~

In single-primary mode, one member is the primary accepting writes; the remaining members are secondaries and typically serve reads. Router exposes stable endpoints so applications do not need to track primary hostnames after every failover.

AdminAPI is not a replication engine. When you call `dba.createCluster()`, Shell configures Group Replication and writes InnoDB Cluster management metadata. Once the cluster is running, transactions are exchanged and applied by Group Replication. Router also does not participate in transaction consensus; it only routes connections.

## 2. How does Group Replication work?

Group Replication is a group-based replication mechanism. Members exchange transaction data over group communication, check for conflicts, and coordinate apply order. Transactions undergo certification before being accepted into the group. If two concurrent transactions modify the same data in a conflicting way, one transaction can be rejected and the application must retry.

Group Replication provides a **virtually synchronous replication** model: members coordinate via the group protocol before a transaction is confirmed per the commit policy. This prevents a single member from unilaterally accepting changes not agreed upon by the group. However, this should not be interpreted as meaning every transaction is durably flushed to disk on all replicas before the client gets a response. Durability still depends on durability settings, storage, and individual member states.

Key characteristics:

- Each member has a unique `server_id` and proper replication configuration.
- Transactions are written to the binary log; Group Replication uses GTIDs to identify transactions.
- Members maintain group membership and exchange cluster state.
- Conflicting transactions can hit certification failures; applications need a safe retry strategy.
- Members can leave, lose connectivity, or rejoin through distributed recovery.

Group Replication is not a global table-locking mechanism. It uses certification and group communication to coordinate transactions among members. Therefore, applications must still keep transactions short, define explicit primary keys, and handle commit/retry errors properly.

## 3. Single-primary and multi-primary

### Single-primary

Single-primary is the default mode and usually the right fit for most applications. Only the primary accepts write transactions; secondaries maintain copies and can serve read queries depending on routing policies.

Advantages:

- Centralized, easier-to-predict write flow.
- Fewer write conflicts across members.
- Easier integration with applications expecting a single write endpoint.
- When the primary fails, the group can elect a new primary if quorum holds.

Example creating a cluster in default mode:

~~~javascript
var cluster = dba.createCluster("ordersCluster");
~~~

When the primary fails, Group Replication selects a new primary via group election. Applications connecting through Router can continue using the write endpoint once Router detects the new topology and connections are re-established.

### Multi-primary

Multi-primary allows multiple members to accept writes. Every transaction still goes through certification and group coordination. If two clients modify the same row on different members, one transaction can be rejected due to conflict.

Create a multi-primary cluster in MySQL Shell using the option:

~~~javascript
var cluster = dba.createCluster("ordersCluster", {
  multiPrimary: true
});
~~~

Or switch modes via the corresponding API when supported by your Shell version:

~~~javascript
cluster.switchToMultiPrimaryMode();
cluster.switchToSinglePrimaryMode();
~~~

Multi-primary does not automatically make all applications write faster. It is better suited when workloads partition cleanly or most transactions update independent rows. You must evaluate limitations around foreign keys, unique keys, multi-row transactions, write ordering, and failover behavior. For applications with frequent updates to the same entities, single-primary is much easier to operate.

| Criterion | Single-primary | Multi-primary |
|---|---|---|
| Write-capable members | One primary | Multiple members |
| Write conflicts | Fewer, serialized on primary | Can arise across primaries |
| Failover | Elects a new primary | Group retains multiple write endpoints while eligible members remain |
| Application logic | Simpler | Must handle retries and conflicts carefully |
| Best fit | Standard OLTP workloads | Well-partitioned workloads with low write contention |

## 4. Quorum and fault tolerance

Group Replication requires a majority of active members to make group decisions. For a group of N members, standard quorum is `Q = floor(N / 2) + 1`.

Examples:

| Members | Quorum | Members that can be lost while retaining majority |
|---:|---:|---:|
| 1 | 1 | 0 |
| 2 | 2 | 0 |
| 3 | 2 | 1 |
| 4 | 3 | 1 |
| 5 | 3 | 2 |

Thus, a three-member cluster spread across three independent servers tolerates one failed member while retaining majority. A two-member cluster cannot continue operating normally if one member fails, because the lone survivor lacks quorum. Adding an arbitrator is not Group Replication's default substitute for a MySQL member; design member counts and failure domains appropriately.

Quorum protects membership consistency, not physical infrastructure redundancy. If all three members run on the same physical host, a host outage still takes down the entire cluster. Distribute members across hosts, racks, zones, or failure domains matching your availability goals.

When a group loses majority, remaining members stop accepting writes in a no-quorum state. Never unilaterally force one partition active without confirming other members are completely isolated. Forcing quorum incorrectly can cause split-brain or two data branches accepting writes simultaneously.

## 5. Prerequisites before creating an InnoDB Cluster

Before using AdminAPI, prepare MySQL instances on compatible versions meeting Group Replication requirements. Checks include:

- Each instance has a unique `server_id`.
- GTIDs are enabled and consistent; `enforce_gtid_consistency=ON`.
- Binary logging is enabled in the required format; Group Replication requires `binlog_format=ROW` and `log_replica_updates=ON`.
- Business tables use InnoDB and have primary keys or non-nullable unique keys. Tables without unique identifiers increase risk and face replication restrictions.
- Cluster admin accounts have the privileges needed to configure replication, metadata, and Group Replication.
- Servers resolve hostnames, synchronize clocks, and communicate over required SQL and group communication ports.
- MySQL Shell, Server, and Router versions are mutually compatible.
- Instances hold consistent data state before joining; avoid adding an instance with divergent data without choosing an explicit recovery method.

Settings such as `binlog_format`, `gtid_mode`, `log_replica_updates`, `server_id`, and Group Replication parameters can be inspected or configured by AdminAPI depending on version. Do not blindly copy a sample configuration file across every MySQL version. Use AdminAPI preflight checks to see what an instance is missing.

## 6. Creating a cluster with MySQL Shell AdminAPI

MySQL Shell supports JavaScript and Python modes. The examples below use JavaScript mode. First, connect to the prospective seed instance:

~~~text
mysqlsh --uri icadmin@db1.example.internal:3306
~~~

Inside Shell, verify the instance:

~~~javascript
dba.checkInstanceConfiguration("icadmin@db1.example.internal:3306");
~~~

If the instance does not yet meet requirements, configure it via AdminAPI:

~~~javascript
dba.configureInstance("icadmin@db1.example.internal:3306");
~~~

The command may prompt for confirmation or admin credentials. Afterward, restart MySQL if Shell reports a restart is needed, then reconnect and verify status.

Create the cluster:

~~~javascript
var cluster = dba.createCluster("ordersCluster");
~~~

Add prepared instances:

~~~javascript
cluster.addInstance("icadmin@db2.example.internal:3306");
cluster.addInstance("icadmin@db3.example.internal:3306");
~~~

When adding an instance, AdminAPI brings the new instance's data in sync with the cluster. You can choose the appropriate distributed recovery method, such as incremental recovery or clone:

~~~javascript
cluster.addInstance(
  "icadmin@db2.example.internal:3306",
  { recoveryMethod: "clone" }
);
~~~

Clone copies data from a donor to the new instance and replaces existing data on the recipient. Verify the target instance carefully before choosing clone; never run clone on a server holding data you need to keep. Incremental recovery uses binary logs to transfer missing transactions, so a donor must still retain all needed logs.

## 7. Checking status and administering topology

After creating the cluster, inspect topology:

~~~javascript
cluster.status();
cluster.status({ extended: 1 });
cluster.describe();
~~~

What to inspect:

- Cluster name and single-primary/multi-primary mode.
- Which member is primary and which are secondaries.
- Member states such as `ONLINE`, `RECOVERING`, `UNREACHABLE`, or `ERROR`.
- Received and applied transactions.
- Quorum health and configuration warnings.
- Distributed recovery lag or backlog.

`ONLINE` indicates the member is active in the group at the moment of inspection. It does not prove backups exist or business data is verified. A `RECOVERING` member is still synchronizing data; do not route critical read traffic to it until it becomes `ONLINE`.

Retrieve the cluster object when opening a fresh Shell session:

~~~javascript
var cluster = dba.getCluster("ordersCluster");
~~~

If the primary needs maintenance or is degraded while the cluster still holds quorum, proactively switch primary:

~~~javascript
cluster.setPrimaryInstance("db2.example.internal:3306");
~~~

To bring back a member that left the group, investigate the failure cause first, then run the appropriate method:

~~~javascript
cluster.rejoinInstance("icadmin@db3.example.internal:3306");
~~~

If a member is no longer needed in the topology, remove it cleanly:

~~~javascript
cluster.removeInstance("db3.example.internal:3306");
~~~

Use `cluster.dissolve()` only when intentionally dismantling the entire InnoDB Cluster. It is a major topology change; verify applications, Router, and transition plans beforehand.

## 8. MySQL Router and application routing

MySQL Router provides stable endpoints for clients. In single-primary mode, Router directs write connections to the primary and read connections to secondaries based on the configured routing strategy. When the primary changes, Router reads updated metadata and routes new connections accordingly.

Bootstrapping Router typically connects to an InnoDB Cluster member using an account with Router management privileges:

~~~bash
mysqlrouter --bootstrap icadmin@db1.example.internal:3306
~~~

This command may prompt for a password and generate Router configuration files. Protect the configuration files because they hold connection metadata and potentially credentials. In production, run Router under a dedicated OS user with proper secret management.

Applications should use Router endpoints instead of hardcoding a specific member. Still, understand these caveats:

- Router does not migrate an in-flight transaction from an old node to a new node.
- On failover, active connections can drop; connection pools must reconnect and applications must safely retry transactions.
- Read paths can return data slightly behind the primary if replication apply has not finished.
- Router needs access to cluster metadata and target nodes; Router itself must be deployed redundantly.
- Do not let applications write directly to secondaries in single-primary mode.

Deploy multiple Router instances on application hosts or a dedicated proxy tier to avoid making a single Router a single point of failure.

## 9. Distributed recovery: incremental and clone

When a new member joins or returns after being offline, it must synchronize missing transactions.

**Incremental recovery** pulls transactions from a donor's binary logs and applies them on the recipient. This uses less bandwidth when the recipient is missing only a small transaction delta. The donor must retain complete binlogs from the GTID where the recipient stopped.

**Clone recovery** copies physical data state from donor to recipient using the MySQL Clone Plugin. It fits when the recipient is missing too many transactions or required binlogs have been purged. Clone overwrites existing data on the recipient, so confirm the target host and preserve any needed data first.

AdminAPI selects a recovery method automatically by default or lets you specify one explicitly:

~~~javascript
cluster.addInstance(
  "icadmin@db3.example.internal:3306",
  { recoveryMethod: "incremental" }
);
~~~

If incremental recovery fails due to missing binlogs, do not wipe state or reset replication blindly. Inspect GTID sets, binlog retention, donors, and recipient data; then decide between cloning or rebuilding the instance from a valid backup.

## 10. Incident handling and recovery boundaries

### Loss of one member

If a three-member cluster loses one member, the remaining two normally retain quorum. Check `cluster.status({extended: 1})`, MySQL logs, and network connectivity. Fix the root cause, then call `rejoinInstance()` if the member is eligible to rejoin.

### Loss of quorum

If remaining nodes lack majority, the cluster stops accepting transactions. Before restoring quorum, identify which partition has the newest data and isolate all other partitions. AdminAPI provides a method to force quorum from one partition, but use it only after proving members outside that partition are stopped or fenced. Misuse can lose changes on excluded partitions and trigger split-brain.

Example API for controlled recovery:

~~~javascript
cluster.forceQuorumUsingPartitionOf("db1.example.internal:3306");
~~~

Run this command only after confirming the chosen member belongs to the sole partition authorized to proceed and other partitions cannot accept writes. Record pre-recovery state and re-verify the entire topology immediately after quorum is restored.

### Primary failure

In single-primary mode, if quorum holds, the group elects a new primary. Router updates routes for new connections; applications must handle connection resets and retries. Check for transactions that might have committed on the server when the client lost the response; retries need idempotency keys or duplicate-write guards.

### Certification failure

If a transaction is rejected due to conflict, inspect the error message, identify conflicting keys/rows, and retry at the application layer when appropriate. Never infinitely retry a transaction guaranteed to conflict. Keeping transactions short, targeting clear row sets, and avoiding concurrent writes to the same entity reduces errors.

## 11. Boundaries between Group Replication and InnoDB Cluster

Group Replication is a plugin that can be configured and operated directly without InnoDB Cluster. InnoDB Cluster builds on Group Replication and adds metadata, AdminAPI, and standardized management workflows.

| Feature/capability | Standalone Group Replication | InnoDB Cluster |
|---|---|---|
| Group transaction sync | Yes | Yes, via Group Replication |
| Membership and certification | Yes | Yes |
| AdminAPI management | Not required | Primary management interface |
| InnoDB Cluster topology metadata | Not fully built-in | Yes |
| MySQL Router integration | Configured manually | Supported via metadata and bootstrap |
| Cluster lifecycle management | Operator manages many steps manually | AdminAPI provides standardized APIs |

Standalone Group Replication fits organizations needing custom configuration and integration workflows. InnoDB Cluster fits teams wanting AdminAPI automation and supported MySQL Router integration.

Also distinguish InnoDB Cluster from **InnoDB ClusterSet**. ClusterSet links multiple InnoDB Clusters for cross-cluster disaster recovery, typically with one primary cluster and standby replica clusters. Replication between clusters is asynchronous, so failing over to a standby cluster can lose transactions not yet shipped there. A single InnoDB Cluster does not automatically provide cross-region disaster recovery. Nor should you stretch members of a single Group Replication group across high-latency WAN links without evaluating network requirements and topology limits.

## 12. HA does not replace backups and data controls

Group Replication maintains service when members fail, yet valid replicated mutations still propagate to every member. If someone runs an accidental `DELETE`, an application writes bad data, or ransomware uses valid credentials to corrupt records, the cluster replicates those changes very quickly.

Therefore, an operational design still needs:

- Full and incremental backups aligned with RPO/RTO.
- Retained binary logs for PITR.
- Regular restore drills in an isolated environment.
- Monitoring for quorum, member state, replication apply, and Router.
- Dedicated accounts, least privilege, and secret management.
- Testing for failover, member recovery, and primary changes.
- Off-cluster DR planning when region or site fault tolerance is required.

Never treat the count of `ONLINE` members as sole proof of recoverability. Periodically drill node outages, network partitions, full disks, donor failures, and Router outages to see how the system actually behaves.

## 13. Deployment and verification workflow

A practical deployment workflow can follow this order:

1. Define RTO/RPO, member count, failure domains, and single-primary vs. multi-primary.
2. Provision instances on compatible versions with unique `server_id`, GTIDs, and binary logs.
3. Verify InnoDB tables, primary keys, admin privileges, hostnames, and firewalls.
4. Install MySQL Shell and run `dba.checkInstanceConfiguration()` and `dba.configureInstance()` on each instance.
5. Create the cluster on the seed node using `dba.createCluster()`.
6. Add remaining instances via `cluster.addInstance()`, choosing `incremental` or `clone` per data state.
7. Inspect `cluster.status({extended: 1})` until all expected members are `ONLINE`.
8. Bootstrap at least two MySQL Router instances across failure domains and point applications to Router endpoints.
9. Test primary switches, single-member failures, member recovery, and application reconnection.
10. Set up backups/PITR, monitoring, and incident drill schedules.

Validation must confirm not only that the cluster elects a primary, but also that applications reconnect, transactions retry safely, secondaries catch up, and Router routes traffic accurately.

## 14. Key takeaways

- InnoDB Cluster combines Group Replication, MySQL Shell AdminAPI, and MySQL Router.
- Group Replication synchronizes transactions and handles membership/certification; AdminAPI manages lifecycle; Router routes clients.
- Single-primary is usually easier to operate; multi-primary requires low-conflict workloads and careful retry logic.
- Quorum requires a majority of members; three members tolerate one member failure while connectivity and resources remain.
- AdminAPI checks instances, creates clusters, adds/removes members, switches primaries, and reports status.
- Incremental recovery requires intact binlogs; clone recovery overwrites recipient data.
- Router does not preserve active in-flight connections across failover; applications must reconnect and retry safely.
- Group Replication does not replace backups, PITR, or DR.
- Never force quorum before isolating remaining partitions.

Good HA design begins by clearly separating replication, topology management, and application routing. Once quorum, recovery, Router, backups, and failover procedures are all verified, InnoDB Cluster becomes a reliable high-availability foundation.

## References

- [MySQL 8.0 Reference Manual: InnoDB Cluster](https://dev.mysql.com/doc/mysql-shell/8.0/en/mysql-innodb-cluster.html)
- [MySQL Shell 8.0: AdminAPI](https://dev.mysql.com/doc/mysql-shell/8.0/en/admin-api.html)
- [MySQL 8.0 Reference Manual: Group Replication](https://dev.mysql.com/doc/refman/8.0/en/group-replication.html)
- [MySQL Router 8.0 Reference Manual](https://dev.mysql.com/doc/mysql-router/8.0/en/)
