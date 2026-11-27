# InnoDB ReplicaSet and How It Differs from InnoDB Cluster

In the **DATABASE_MYSQL** module, high availability keeps applications able to access data when a MySQL server fails or needs maintenance. MySQL offers two topologies managed through MySQL Shell AdminAPI: **InnoDB ReplicaSet** and **InnoDB Cluster**. Both can pair with MySQL Router to route application connections, yet their data synchronization mechanisms and failure handling differ significantly.

This lesson explains the architecture, operational workflows, and use cases for each model. The focus is on choosing the right topology for your RPO/RTO targets, understanding failover boundaries, and preventing two servers from accepting writes simultaneously after a primary transition.

Within DATABASE_MYSQL, this topic complements mastering table design, data types, keys, SQL queries, indexes, transactions, and concurrency control; it also connects directly to execution plan reading, query tuning, privilege management, backups, and relational database troubleshooting.

## 1. Objectives and concepts

After this lesson, you will be able to:

- Describe the architectures of InnoDB ReplicaSet and InnoDB Cluster.
- Distinguish asynchronous replication from Group Replication.
- Explain primary, replica, member, quorum, and metadata.
- Create, inspect, and modify topologies using MySQL Shell AdminAPI.
- Perform planned switchovers and handle failovers when the primary fails.
- Assess data-loss risk from replication lag and split-brain risk.
- Select the right model for your application's high-availability requirements.

A topology has a **primary** accepting writes and one or more **replicas** receiving data from the primary. Applications generally send write queries to the primary; read queries can be routed to replicas if the application tolerates synchronization lag. With multi-component systems, clearly define the responsibilities of MySQL Server, MySQL Shell, MySQL Router, and monitoring tools.

Two models to distinguish:

- **InnoDB ReplicaSet:** manages a primary and replicas using GTID-based asynchronous replication.
- **InnoDB Cluster:** manages members using Group Replication; supports single-primary or multi-primary mode. In single-primary mode, Group Replication automatically elects a new primary when the current primary fails and the group retains quorum.

For business data requiring transactional consistency, InnoDB is the proper engine; Group Replication requires replicated tables to use InnoDB. Choosing a model is not merely picking a tool; it determines how the system confirms transactions, handles failed members, and recovers from network disruptions.

## 2. InnoDB ReplicaSet

### 2.1. Architecture

InnoDB ReplicaSet is an asynchronous replication topology managed by MySQL Shell AdminAPI. It consists of one primary and one or more replicas:

- The primary accepts write transactions from applications.
- Replicas receive binary logs from the primary and apply changes via asynchronous replication.
- Each replica can experience lag behind the primary.
- Replicas are typically placed in read-only mode to prevent independent writes from diverging data.
- Administrators control primary transitions via AdminAPI.

Conceptual diagram:

~~~mermaid
flowchart LR
    APP[Application] --> ROUTER[MySQL Router]
    ROUTER -->|Writes| P[Primary]
    ROUTER -->|Reads per policy| R1[Replica 1]
    ROUTER -->|Reads per policy| R2[Replica 2]
    P -->|Binary log / async replication| R1
    P -->|Binary log / async replication| R2
    SHELL[MySQL Shell AdminAPI] -. manages .-> P
    SHELL -. manages .-> R1
    SHELL -. manages .-> R2
~~~

ReplicaSet fits applications needing a single write primary and read/standby replicas while accepting asynchronous replication and administrator-driven failover.

### 2.2. Asynchronous replication and lag

In asynchronous replication, the primary does not wait for replicas to apply a transaction before confirming commit to the client. The primary writes the transaction to its binary log; replicas retrieve and apply events afterward.

Consequences:

- A replica may not yet see a transaction just committed on the primary.
- Heavy load, slow networks, or applier stalls can increase replication lag.
- If the primary crashes abruptly, transactions already acknowledged on the primary may not have reached the replica selected for promotion.
- Reading from a replica can return older data than the primary.

GTIDs identify transactions and track received or applied transaction sets. GTIDs do not turn asynchronous replication into synchronous replication and do not eliminate the risk of losing transactions not yet shipped to a replica.

If the application needs to read just-written data, read from the primary or implement a wait for the replica to catch up to the relevant GTID/position. Never assume a replica read immediately sees the same user's preceding write.

### 2.3. Creating and managing a ReplicaSet with AdminAPI

Illustrative examples use MySQL Shell in JavaScript mode. Before creating the topology, verify versions, network connectivity, server identities, GTID settings, and AdminAPI prerequisites on all instances.

Check instance configuration:

~~~javascript
dba.checkInstanceConfiguration('admin@db-primary:3306');
dba.checkInstanceConfiguration('admin@db-replica1:3306');
~~~

If AdminAPI recommends configuration changes, review and apply them per administrative procedure. On fresh servers, `dba.configureInstance()` can configure required settings:

~~~javascript
dba.configureInstance('admin@db-primary:3306');
dba.configureInstance('admin@db-replica1:3306');
~~~

Some configuration changes require restarting MySQL Server. Complete restarts inside a maintenance window, then re-run configuration checks before creating the topology. Never treat a successful configure command alone as complete proof the instance is ready.

Connect to the instance that will become primary:

~~~javascript
var rs = dba.createReplicaSet('ordersReplicaSet');
~~~

Add replicas. Depending on data size and initial state, pick an appropriate recovery method; for example, `clone` requires Clone Plugin prerequisites and replaces data on the recipient instance:

~~~javascript
rs.addInstance('admin@db-replica1:3306', {
  recoveryMethod: 'clone'
});
~~~

Check status:

~~~javascript
rs.status();
rs.status({extended: 1});
~~~

Inspect each instance's status, role, replication connections, applier errors, and lag where provided. An instance appearing in metadata does not guarantee it is syncing cleanly or ready for reads.

Common administrative operations:

~~~javascript
// Inspect topology and status
rs.status();

// Planned switchover to a synchronized replica
rs.setPrimaryInstance('admin@db-replica1:3306');

// Rejoin a repaired instance back into the topology
rs.rejoinInstance('admin@db-replica2:3306');

// Remove an unused instance from the topology
rs.removeInstance('admin@db-replica2:3306');
~~~

Hostnames, accounts, ports, and ReplicaSet names here are illustrative. Verify the exact target instance before any topology change. `removeInstance()` updates topology metadata; it does not delete business data from storage everywhere.

### 2.4. Planned switchover

When primary maintenance is needed, execute a planned primary switch:

1. Check ReplicaSet status and confirm the target replica is connected cleanly.
2. Confirm the target replica has applied all required transactions from the primary.
3. Verify applications, Router connections, and traffic shift plans.
4. Call `rs.setPrimaryInstance()` so AdminAPI executes the role transfer.
5. Verify the new primary accepts writes, remaining replicas follow the new primary, and the application operates normally.
6. Begin maintenance on the old primary only after confirming it no longer accepts writes.

Example:

~~~javascript
rs.setPrimaryInstance('admin@db-replica1:3306');
rs.status();
~~~

This is a planned switchover: the old primary still participates in the transition. Run it once the target replica has caught up to avoid losing committed transactions.

### 2.5. Failover when the primary is down

If the primary loses connectivity or fails, a ReplicaSet does not automatically promote a replica. An administrator must evaluate surviving replicas, choose the one with the latest data, and execute a controlled failover using `forcePrimaryInstance()`.

Illustrative example:

~~~javascript
var rs = dba.getReplicaSet();
rs.status();
rs.forcePrimaryInstance('admin@db-replica1:3306');
rs.status();
~~~

`forcePrimaryInstance()` is for cases where the current primary cannot participate in a normal switchover. Before running it:

- Confirm the old primary is fenced: shut down, network-isolated, or write-blocked so it cannot keep accepting transactions.
- Check which GTIDs the chosen replica has received/applied; compare GTID sets across surviving replicas.
- Estimate potential transaction loss from asynchronous replication.
- Document the chosen replica and accepted data cutoff.
- After promotion, reopen write traffic to the new primary only after confirming no independent old primary remains active.

Never let an old primary automatically resume accepting writes once the ReplicaSet has a new primary. Put it through rejoin/recovery to resynchronize from the authoritative source. If two instances accept writes concurrently, data diverges and manual reconciliation is highly risky.

## 3. InnoDB Cluster

### 3.1. Architecture

InnoDB Cluster is a high-availability solution built on Group Replication, managed by MySQL Shell AdminAPI, and commonly paired with MySQL Router.

Components:

- **Group Replication:** maintains member group, distributes and certifies transactions, tracks membership and quorum.
- **MySQL Shell AdminAPI:** creates clusters, adds/removes members, checks status, and runs administrative actions.
- **MySQL Router:** provides application connection endpoints and routes to appropriate members via topology metadata.

Single-primary diagram:

~~~mermaid
flowchart LR
    APP[Application] --> ROUTER[MySQL Router]
    ROUTER -->|Read / Write| P[Primary]
    ROUTER -->|Read only| S1[Secondary 1]
    ROUTER -->|Read only| S2[Secondary 2]
    P <-->|Group Replication| S1
    P <-->|Group Replication| S2
    S1 <-->|Membership / transaction| S2
    SHELL[MySQL Shell AdminAPI] -. manages .-> P
    SHELL -. manages .-> S1
    SHELL -. manages .-> S2
~~~

In single-primary mode, only the primary accepts normal write transactions; secondaries receive and apply transactions via Group Replication. When the primary fails, remaining members can elect a new primary if the group retains quorum.

### 3.2. Group Replication, certification, and quorum

Group Replication distributes transactions across members and uses certification to detect write conflicts based on write sets. In single-primary mode, write transactions concentrate on the primary, minimizing multi-node write conflicts.

**Quorum** is the majority of voting members required for the group to continue operating. It prevents both sides of a network partition from simultaneously claiming transaction coordination authority.

Example with three voting members:

- All three active: group has quorum.
- One member disconnected: the remaining two still form a majority and can continue.
- Only one of three remaining: group lacks majority and cannot continue as a healthy group.

Thus, three members is the standard configuration to tolerate one member failure. Two members do not provide single-node fault tolerance: if one node disconnects, the survivor lacks a majority. Design member count, placement, and networking around real failure domains.

Quorum does not replace backups. It keeps the group operating through certain member failures, yet offers no protection against accidental deletes, valid commits of bad data, or incidents corrupting data across all members.

### 3.3. Single-primary and multi-primary

| Mode | Write handling | Advantages | Considerations |
|---|---|---|---|
| Single-primary | One primary accepts writes; others are secondaries | Familiar application model, fewer concurrent write hotspots | Brief interruption while electing a new primary |
| Multi-primary | Multiple members can accept writes | Can distribute write points per application design | Certification conflicts, operation limits, and higher app complexity |

Single-primary is the common choice for standard OLTP applications. Choose multi-primary only when the application is engineered to handle conflicts and Group Replication limits; do not enable it merely to have multiple writable nodes.

### 3.4. Creating a Cluster with AdminAPI

Connect MySQL Shell to the first instance, check and configure instances per AdminAPI requirements, then create the cluster:

~~~javascript
var cluster = dba.createCluster('ordersCluster');
~~~

Add members:

~~~javascript
cluster.addInstance('admin@db-node2:3306');
cluster.addInstance('admin@db-node3:3306');
~~~

Check status:

~~~javascript
cluster.status();
cluster.status({extended: 1});
~~~

Inspect status output to verify members joined, synchronization state, and current roles. If any member is unhealthy, fix the root cause before opening application traffic.

Planned primary switch in single-primary mode:

~~~javascript
cluster.setPrimaryInstance('admin@db-node2:3306');
cluster.status();
~~~

During a member failure, Group Replication can automatically elect a new primary if quorum remains. AdminAPI helps inspect and manage topology after the event; automatic primary election is built into Group Replication rather than requiring a manual `forcePrimaryInstance()` as in ReplicaSet.

### 3.5. Recovering a failed member

When a member leaves the group, diagnose why before rejoining it:

- Did the server or MySQL process stop?
- Is inter-member networking unstable or is a port blocked?
- Did the member's GTIDs diverge from the group?
- Was there an applier error or conflicting data?
- Is the instance running an incompatible configuration or version?

After fixing the cause, use AdminAPI to inspect and rejoin the member via supported workflows. If the member's data is no longer compatible, clone or incremental recovery may be required depending on state and AdminAPI options.

Never manually copy a data directory from another member without checking the recovery method. Use AdminAPI recovery mechanisms to ensure GTIDs, metadata, and data align with the topology.

## 4. Comparing ReplicaSet and Cluster

| Criterion | InnoDB ReplicaSet | InnoDB Cluster |
|---|---|---|
| Replication engine | Asynchronous replication | Group Replication |
| Write topology | One primary | Single-primary or multi-primary |
| Failover | Administrator-executed; no auto-promotion | Single-primary auto-elects a new primary while quorum holds |
| Group quorum | No Group Replication quorum | Majority of voting members |
| Replication lag | Can be noticeable due to asynchronicity | Group Replication coordinates group transactions; individual members can still lag or degrade |
| Data-loss risk on primary failure | Can lose transactions not yet sent to chosen replica | Reduced via Group Replication, though consistency, quorum, and transaction state still need evaluation |
| Complexity | Generally simpler | Higher due to Group Replication and network/quorum requirements |
| Best fit | One primary, read/standby replicas, manual failover acceptable | HA and automated failover required in a quorum topology |
| Administration | MySQL Shell AdminAPI | MySQL Shell AdminAPI |
| Application routing | Can pair with MySQL Router | Typically paired with MySQL Router |

Do not interpret this comparison as a zero-RPO promise for Cluster. Transactional consistency and failure behavior depend on Group Replication settings, consistency mode, quorum, network partitions, member state, and how applications handle commit errors. Test realistic failure scenarios to measure achievable RPO/RTO.

## 5. MySQL Router and application connection flow

MySQL Router is the connection routing layer between applications and the topology. It frees applications from manual endpoint reconfiguration on every primary transition.

In a Router-enabled topology:

- Applications configure connections to Router endpoints.
- Router reads topology metadata and picks a backend matching connection intent.
- The write endpoint routes to the current primary.
- The read endpoint routes to eligible members per configuration and policy.
- When topology changes, Router updates routing according to observed metadata and state.

Router does not replace replication and cannot repair diverged data. For ReplicaSet, Router never promotes a replica on behalf of an administrator. For Cluster, primary election happens inside Group Replication; Router updates connection paths to match the new topology.

Existing connections can drop during failover or role changes. Applications need bounded retries, backoff, handling for unknown-outcome transactions, and connection pool recovery. Never automatically retry every write without evaluating idempotency, since a client may lose its connection after the server already committed.

## 6. Choosing a model for system requirements

### 6.1. When ReplicaSet fits

Choose ReplicaSet when:

- The application has one clear write primary.
- Asynchronous replication and lag monitoring are acceptable.
- Manual runbook-driven failover meets your RTO.
- You want to manage an existing primary/replica topology with MySQL Shell AdminAPI.
- Operational overhead and complexity should stay lower than Group Replication.

Example: an internal reporting platform with one write primary, one reporting read replica, and one standby replica. If the primary fails, operations identifies the most caught-up replica and promotes it following an approved runbook.

### 6.2. When Cluster fits

Choose InnoDB Cluster when:

- The service needs automated failover within quorum bounds.
- Enough members and stable inter-node networking can be deployed.
- The application tolerates brief connection drops during primary election.
- Operations can monitor Group Replication, quorum, and member states.
- You want an HA topology managed via AdminAPI and routed through Router.

Example: an online transactional system needing rapid primary failover on single-node loss, deployed with three members across separate failure domains and continuous topology health monitoring.

### 6.3. Decision matrix

| Question | If Yes | Direction to consider |
|---|---|---|
| Can you accept replica lag and operator-triggered failover? | Yes | ReplicaSet |
| Need automatic primary election when a member fails while quorum remains? | Yes | Single-primary InnoDB Cluster |
| Does the app need multiple nodes accepting writes concurrently? | Yes | Evaluate multi-primary carefully; inspect conflicts and limits |
| Cannot guarantee stable network links between members? | Yes | Re-evaluate Cluster design and failure domains before deploying |
| Very strict RPO/RTO targets? | Yes | Benchmark both models, measure lag/failover/restore; never pick by product name alone |

Define explicit targets:

- **RPO:** maximum acceptable data loss. For async ReplicaSet, account for transactions not yet received by replicas. For Cluster, measure real behavior across configurations and failure modes.
- **RTO:** service recovery duration. ReplicaSet requires detection, decision, and manual promotion time; Cluster auto-elects primary with quorum, yet applications still need time to reconnect.

## 7. Pre-deployment preparation and controls

Before creating a ReplicaSet or Cluster, prepare:

1. Compatible MySQL Server and MySQL Shell versions.
2. Stable hostname resolution across nodes; avoid addresses that change unpredictably.
3. Unique `server_id` per instance and proper binary logging settings.
4. GTIDs enabled and configured consistently per AdminAPI requirements.
5. InnoDB for replicated business tables.
6. Topology admin accounts with appropriate privileges and secure secret storage.
7. Firewalls permitting required client, replication, and Group Replication ports.
8. Time synchronization and monitoring for lag, network errors, disk capacity, CPU, and I/O.
9. Independent backups before adding, cloning, or changing instance roles.
10. Runbooks for planned switchover, unplanned failover, rejoin, and rollback.

For Group Replication, prerequisites typically include binary logging, GTIDs, row-based logging, GTID consistency, and required replication settings. Each instance needs a unique `server_id`; nodes must resolve hostnames consistently and communicate over Group Replication ports. Let AdminAPI check and configure settings for your running version rather than copying legacy parameter sets.

Never copy a configuration list from another environment without running AdminAPI checks. MySQL version, OS, network stack, and security settings can alter exact requirements.

Common configuration and status inspection commands:

~~~sql
SHOW VARIABLES LIKE 'server_id';
SHOW VARIABLES LIKE 'gtid_mode';
SHOW VARIABLES LIKE 'enforce_gtid_consistency';
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'binlog_format';
SHOW REPLICA STATUS;
~~~

`SHOW REPLICA STATUS` inspects asynchronous replication status on modern MySQL versions; older versions use `SHOW SLAVE STATUS`. For InnoDB Cluster, alongside server variables, use `cluster.status()` to inspect Group Replication and member state.

## 8. Operations and monitoring

An HA topology only helps if failures are detected early and runbooks are executed properly. Monitor at least:

- Primary and replica/member status.
- Replication lag, queued transactions awaiting apply, and applier errors.
- Inter-node network connectivity and Cluster quorum status.
- CPU, memory, disk I/O, relay log, and binary log disk usage.
- Connection counts, connection errors, and query latency.
- MySQL Router health, metadata cache, and application endpoints.
- Failover, switchover, rejoin, clone, and configuration-change events.

For ReplicaSet, alert when replica lag exceeds business thresholds or a replica stops applying logs. Never blindly promote a heavily lagging replica simply because the current primary failed; evaluate acceptable data loss first.

For Cluster, alert when a member leaves, the group loses quorum, a member turns unhealthy, or primary election stalls. Never try to force a no-quorum group back up by randomly restarting nodes; follow the Group Replication runbook to avoid creating two independent groups.

## 9. Incident drills

Run drills in non-production environments. A minimal drill plan should cover:

| Scenario | ReplicaSet | InnoDB Cluster |
|---|---|---|
| Planned primary stop | Use `setPrimaryInstance()` after replica catches up | Use `cluster.setPrimaryInstance()` in single-primary |
| Sudden primary crash | Fence old primary, evaluate GTIDs, then force promote replica | Check quorum and let Group Replication elect a new primary |
| Replica/member network loss | Check lag, fix network, rejoin | Check membership, quorum, and rejoin |
| Node returning after failover | Prevent old node from accepting writes; rejoin/recover from new primary | Verify member state and recovery before serving traffic |
| Multi-node outage | Pick best replica, assess lost transactions | Determine if quorum holds; recover group per runbook |

Record incident start time, detection time, promotion/election time, Router endpoint switch time, application recovery time, and final confirmed GTID. Use these to compute actual RPO/RTO.

Drills must include clients disconnecting immediately after sending `COMMIT`. The application may not know whether the transaction committed. Design idempotency keys or transaction-status lookup mechanisms to prevent duplicate writes during retries.

## 10. Common issues and troubleshooting

| Symptom | Possible cause | Investigation path |
|---|---|---|
| ReplicaSet replica falling behind | Slow network, heavy write load, applier bottleneck | Check replication status, lag, relay log, CPU, and I/O |
| Unable to switch primary | Target replica out of sync or topology error | Check `rs.status()`, find missing GTIDs, and fix errors first |
| Force promote risks data loss | Target replica missing transactions from old primary | Compare GTIDs, pick the best instance, and document RPO impact |
| Old primary returns after failover | Missing fencing or improper rejoin | Block writes on old node, inspect data, then rejoin/recover |
| Cluster loses quorum | Too many failed members or network partition | Inspect member states and networking; restore quorum per runbook |
| Member cannot join Cluster | Incompatible config, GTIDs, plugins, version, or network | Run AdminAPI checks, read error logs, and resolve recovery |
| Router routes incorrectly or fails connections | Stale metadata, Router cannot reach members, or stale connections | Inspect Router logs, metadata cache, endpoints, and topology status |
| Application writes duplicates after failover | Retried non-idempotent transaction with uncertain `COMMIT` outcome | Use request IDs/idempotency keys and check state before resubmitting |

During incidents, collect topology status, MySQL Server error logs, MySQL Shell/Router logs, GTIDs, replication lag, and event timestamps. Avoid issuing forced commands across multiple nodes simultaneously without confirming which node currently holds write authority.

## 11. Self-check

**Scenario 1:** A ReplicaSet system has a primary and two replicas. The primary crashes; one replica has applied newer GTIDs than the other. What must be done before promoting?

**Hint:** Confirm the old primary is fenced, compare GTID sets, and choose the replica with the most complete data. Assess potential lost transactions before running `forcePrimaryInstance()`.

**Scenario 2:** A three-member Cluster loses network connectivity to one member. Can the remaining two members continue?

**Hint:** Two out of three is a majority, so the group retains quorum—provided the two remaining members are healthy and can communicate with each other.

**Scenario 3:** A Cluster has only two members. When one member stops, the remaining member cannot continue as a healthy group. Why?

**Hint:** One out of two is not a majority. Quorum prevents both sides of a network partition from claiming coordination authority.

**Scenario 4:** An application connects via MySQL Router. Does Router automatically promote a ReplicaSet replica when the primary fails?

**Hint:** No. ReplicaSet failover requires administrator control through AdminAPI. Router updates routes from topology metadata after roles change.

**Scenario 5:** A system requires automated failover and has three nodes in independent failure domains. Which model should you evaluate?

**Hint:** Single-primary InnoDB Cluster fits well because Group Replication can elect a new primary while quorum remains. Run drills to measure RTO and verify application behavior.

## 12. Key takeaways

- InnoDB ReplicaSet uses asynchronous replication with one primary and replicas; failover requires administrator execution.
- InnoDB Cluster uses Group Replication; single-primary auto-elects a new primary while quorum holds.
- GTIDs help track transactions but do not convert ReplicaSet into synchronous replication.
- When force-promoting in ReplicaSet, fence the old primary and assess potential transaction loss.
- Quorum requires a majority of members; three members tolerate one node failure, whereas two members cannot lose one node and retain majority.
- MySQL Router routes connections according to topology; it does not replace replication or ReplicaSet promotion decisions.
- Applications must handle dropped connections, bounded retries, and transactions with unknown `COMMIT` outcomes.
- Choose topologies based on RPO/RTO, failure domains, operational readiness, and real drill outcomes.

## References

- [MySQL Shell 8.4 Reference: InnoDB ReplicaSet](https://dev.mysql.com/doc/mysql-shell/8.4/en/mysql-innodb-replicaset.html) — architecture, creating, and managing ReplicaSets.
- [MySQL Shell 8.4 Reference: InnoDB Cluster](https://dev.mysql.com/doc/mysql-shell/8.4/en/mysql-innodb-cluster.html) — Cluster architecture and AdminAPI operations.
- [MySQL 8.4 Reference Manual: Group Replication](https://dev.mysql.com/doc/refman/8.4/en/group-replication.html) — members, quorum, single-primary, and multi-primary.
- [MySQL Router 8.4 Reference](https://dev.mysql.com/doc/mysql-router/8.4/en/) — bootstrapping, metadata cache, and connection routing.
