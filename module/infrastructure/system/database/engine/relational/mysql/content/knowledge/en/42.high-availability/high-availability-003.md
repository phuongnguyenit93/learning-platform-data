# Single-Primary/Multi-Primary and Write Model Limitations

MySQL Group Replication provides two primary write modes: **single-primary**, where only one member accepts write transactions at a time, and **multi-primary**, where multiple members can accept writes concurrently. Both modes share the same Group Replication synchronization and certification engine, but differ in write routing, conflict handling, and operational complexity.

Choosing the right mode is a decision about consistency and business flow, not merely enabling additional write endpoints. Multi-primary does not partition data across nodes, nor does it linearly scale write throughput with node count. Every member still maintains a copy of the same dataset; competing transactions must be checked to preserve a consistent state.

This lesson belongs to the **High Availability** chapter of the `DATABASE_MYSQL` module. The module covers table design, data types, keys, queries, indexes, transactions, concurrency control, tuning, privileges, backups, and relational database operations. The material focuses on MySQL Group Replication and InnoDB Cluster on MySQL 8.0; exact command names and limits should be verified against your deployed version.

After this lesson, you will be able to:

- Distinguish single-primary and multi-primary modes in Group Replication.
- Describe the write path and transaction certification mechanism.
- Identify write conflicts and limitations of the multi-primary model.
- Select a mode based on workload, application placement, and availability requirements.
- Switch modes using MySQL Shell AdminAPI under appropriate conditions.
- Design routing, retries, monitoring, and failover drills.

## 1. Scope: Group Replication and InnoDB Cluster

Single-primary and multi-primary are the two operating modes of **MySQL Group Replication**. InnoDB Cluster uses Group Replication to maintain data members, MySQL Shell AdminAPI to administer the cluster, and MySQL Router to route application connections.

Distinguish the components clearly:

| Component | Role |
|---|---|
| Group Replication | The group protocol enabling members to exchange transactions, establish order, and verify commit eligibility. |
| Single-primary | One member acts as the primary accepting writes; the remaining members act as secondaries and typically serve only reads. |
| Multi-primary | All eligible members can accept writes; transactions are certified across the group. |
| InnoDB Cluster | Cluster management solution built on Group Replication, integrating AdminAPI and typically MySQL Router. |
| MySQL Router | Connection entry point for applications; routes to the primary or read members using cluster metadata. |

Group Replication maintains copies of the same database across members. It is not sharding: each node does not hold a separate data partition. If you need to split data by tenant or geographic region, that is a partitioning/sharding problem at a different architectural layer.

Group Replication is often described as *virtually synchronous*: transactions are exchanged and certified across the group before commit is confirmed according to the consistency policy, while applying changes on other members can occur afterward. Do not interpret this as meaning every node always reads the exact same state at every instant. Read-after-write behavior still depends on consistency settings, routing, and member state.

## 2. Shared mechanism: write sets and certification

Group Replication uses an optimistic concurrency approach. A transaction runs on the receiving member; at commit time, its write set is exchanged with the group and checked for conflicts against the global order.

A write set describes the rows modified by a transaction, based on row key information. Members check whether the transaction conflicts with other already-certified transactions. If there is no conflict, the transaction commits and is applied on the remaining members. If a conflict exists, the transaction is rejected during certification and the client must handle the error.

Example of two applications sending statements to two different primaries in multi-primary mode:

~~~sql
-- Transaction A on node 1
START TRANSACTION;
UPDATE inventory
SET available = available - 1
WHERE product_id = 42;
COMMIT;

-- Transaction B on node 2, at the same time
START TRANSACTION;
UPDATE inventory
SET available = available - 2
WHERE product_id = 42;
COMMIT;
~~~

Both transactions may initially execute locally. When their write sets undergo certification, both touch the row keyed by `product_id = 42`. The group can only accept one compatible ordering; the other transaction can be rolled back due to a certification conflict. The application must detect the error, re-read the state, and decide whether to retry.

Key takeaways:

- Certification does not automatically merge concurrent writes on the same row into a single addition.
- A transaction rolled back due to conflict is never partially committed.
- Clients must handle commit errors and retry the entire transaction when business logic permits.
- Retries need attempt limits, backoff, and safe repeatable business semantics.
- Members must share compatible schemas and configurations to interpret write sets identically.

Stable primary keys enable efficient row identification and conflict detection. Design InnoDB tables with explicit primary keys; avoid relying on tables without unique keys when workloads require reliable replication and conflict detection.

## 3. Single-primary: a single write coordinator

In single-primary mode, one member is elected as primary. Applications send writes to the primary; secondaries receive and apply transactions from the group and are typically configured read-only for applications.

General flow:

~~~text
                 Application
                      |
                MySQL Router
                      |
               Current Primary
                 /    |    \
                /     |     \
         Secondary  Secondary  Secondary
           read       read       read
~~~

Characteristics:

- Only the primary accepts normal write transactions.
- Secondaries can serve read queries if routing and consistency policies allow.
- Group Replication maintains transaction state across members.
- When the primary fails or leaves the group, remaining members can elect a new primary if quorum and operational conditions are met.
- Applications must reconnect or be routed by Router to the new primary after failover.

### 3.1. Advantages

Single-primary provides a clear write coordination point. Transactions updating the same row are handled on one primary, avoiding scenarios where two nodes concurrently run competing transactions on the same data.

This model fits most OLTP applications with complex relational schemas, multiple foreign keys, multi-table transactions, and business logic needing predictable write ordering. Replicas can offload part of the read workload depending on consistency requirements and apply lag.

Operations are also simpler to reason about: identify the current primary, monitor primary write load, track replica lag, and let Router redirect writes when the primary role changes.

### 3.2. Limitations

Because the primary centralizes all writes, it can become a throughput bottleneck. Adding secondaries does not automatically increase write capacity because transactions still must be certified and applied across the group.

Secondaries may lag behind the primary at query time. If an application writes and immediately reads from a secondary, it may not see the newly committed transaction unless an appropriate read-after-write mechanism is used.

During primary failover, there is a brief transition window for role election and reconnection. The cluster requires quorum to continue; Router only handles routing and cannot automatically recover a cluster that has lost quorum or repair inconsistent data.

## 4. Multi-primary: multiple write-capable members

In multi-primary mode, all eligible members can accept write transactions. Each node can accept client writes while exchanging and applying transactions from other members.

~~~text
                 Application
                      |
          Router / app-level routing
                /            \
               /              \
           Node 1  <------>  Node 2
              ^    Group       ^
              |  Replication   |
              v                v
           Node 3  <------>  Node 4

      Nodes can accept writes; transactions
      still go through group certification.
~~~

This can be useful when applications are distributed across network zones and need to write to a node near the request origin. However, multi-node writing is beneficial only when workloads have low contention and clear data-ownership boundaries.

### 4.1. Advantages

- Multiple write entry points can reduce network distance between an application and the receiving node.
- Write workloads can be distributed by tenant, region, or transaction type if data and business workflows are designed accordingly.
- When one member fails, remaining members can continue accepting writes if quorum holds and routing updates cleanly.
- Avoids concentrating all write connections on a single machine in certain distributed topologies.

### 4.2. Limitations

Multi-primary is not a simple way to multiply write throughput. Every transaction still must broadcast its write set, pass certification, and apply across all members. When multiple nodes write to the same data, conflicts and retries can reduce throughput instead of increasing it.

If the application does not control which node receives writes, the same tenant or row can be updated from multiple places. High-latency WAN links also increase transaction exchange and confirmation times.

Transactions touching multiple rows, multiple tables, or multi-step workflows can hit overlapping key sets from different nodes. When that happens, certification conflict rates climb and applications must handle more retries.

## 5. Comparing single-primary and multi-primary

| Criterion | Single-primary | Multi-primary |
|---|---|---|
| Write nodes | One primary at a time | Multiple members |
| Write coordination | Centralized at primary | Distributed across nodes |
| Same-row conflicts | Typically serialized at primary | Detected at certification and rolled back |
| Application routing | Writes go to primary; reads may go to secondaries | Writes can go to multiple nodes |
| Write scaling | Limited by primary and replication overhead | Non-linear; depends on conflict rate and group overhead |
| Suitable workload | OLTP with complex transactions and hot contention points | Low-conflict workloads partitioned by tenant/region |
| Operations | Easy to identify write target | More complex routing, retry, and conflict analysis |
| Failover | Requires electing a new primary | Requires maintaining quorum and routing to live members |
| Primary risks | Primary overload or failover disruption | Conflicts, retries, cross-node latency, unpartitioned writes |

Choose single-primary as the default for most transactional applications unless you have evidence that multi-primary solves a real problem. Switch to multi-primary only after measuring the workload, analyzing write conflicts, and testing client routing.

## 6. Limitations to evaluate in multi-primary

### 6.1. Concurrent writes to the same row

This is the most critical limitation. If two nodes update the same row in overlapping transactions, certification can reject one of them. High conflict rates cause rollbacks, retries, and lower effective throughput.

Tables with "hot" rows—such as account balances, best-selling product inventory, global counters, or order status—easily become contention hotspots. Sending the same workload uniformly to every node can make matters worse.

### 6.2. Key design and transaction scope

Write sets rely on row keys. Tables should have unique, stable primary keys; transactions should update only the necessary rows and stay short-lived.

For example, instead of updating hot rows from multiple nodes, assign each tenant or key group to a designated primary write node. This is an application-layer routing convention, not automatic sharding: data is still replicated to all other members.

Avoid global counters as shared write targets when per-tenant or partitioned counters can be used. If a global sequence is strictly required, design an appropriate allocation mechanism and recognize that it can become a coordination bottleneck.

### 6.3. Local locks and coordination operations

Never assume a lock held on one node locks the same resource on all nodes. Local locks, named locks, or table locks do not replace Group Replication consensus. Check your version's documentation to see which locking statements, isolation levels, and features are supported in multi-primary mode.

For workflows requiring strict serialization, design transactions and routing so the same entity is handled through one designated node. Do not treat `GET_LOCK()` or an in-memory application lock as a cluster-wide distributed lock without a proper coordination service.

### 6.4. Foreign keys and cascading actions

Multi-primary has limitations with tables using cascading foreign keys such as `ON DELETE CASCADE` or `ON UPDATE CASCADE`. Cascading actions can modify multiple rows in ways that are not compatible with multi-primary conflict detection.

If a schema relies heavily on cascading foreign keys, stay on single-primary or redesign the workflow to perform explicit changes and verify against Group Replication limits for your exact version. Never remove data integrity constraints just to force multi-primary to run.

### 6.5. DDL and schema changes

DDL statements are structural changes, unlike normal DML transactions. When multiple applications are writing and migrations run concurrently, schema changes can cause compatibility errors between application queries, in-flight transactions, and member states.

A safe process uses a single coordinated migration pipeline, maintains backward compatibility during rollout, and checks cluster health before and after changes. Never let individual nodes run migrations independently.

### 6.6. Retries must be business-safe

Certification conflicts can cause transactions to roll back. Applications must recognize retryable errors, start a fresh transaction, re-read current state, and replay the entire business operation within bounded retry limits.

Never blindly retry non-idempotent actions. For instance, if a request sent an email or called an external payment gateway before the transaction rolled back, re-running the entire function could email or charge the customer twice. Use idempotency keys, the transactional outbox pattern, or equivalent coordination mechanisms to control side effects.

## 7. Which workload fits which mode?

### 7.1. Start with single-primary when

- Many transactions update a shared set of tables or hot rows.
- Transactions update multiple tables linked by foreign keys.
- Business logic requires clear serialization, such as reservations, inventory deductions, or balance updates.
- The application can route writes to a single stable endpoint.
- The operations team wants to minimize retry and conflict complexity.

### 7.2. Consider multi-primary when

- The application is geographically distributed and latency to a central primary is significant.
- Workloads partition naturally by tenant or key group.
- Cross-node write conflicts are low and verified via real testing.
- Clients support consistent write routing and safe transaction retries.
- Schemas and SQL operations comply with your version's multi-primary limitations.
- Operations can monitor certification conflicts, rollbacks, network latency, and quorum.

Multi-primary is not appropriate simply because user counts are growing. If all nodes write to the same inventory table and hot keys, adding write nodes can increase contention without increasing completed work.

## 8. Write and read routing

In single-primary mode, applications should use the write endpoint exposed by MySQL Router or an equivalent service discovery mechanism. Router reads InnoDB Cluster metadata and directs connections to the current primary. Read connections can be routed to secondaries if the application tolerates lag and uses an appropriate consistency policy.

In multi-primary mode, applications can connect to multiple members for writes. However, routing should be deliberate:

- Pin a tenant or dataset to a preferred node to minimize contention.
- Maintain node affinity within a workflow when consecutive reads and writes occur.
- Do not randomly round-robin requests for the same entity across nodes.
- When a node leaves the group, reroute requests to healthy members and handle in-flight transaction failures.
- Monitor latency between the application and each node, not just connection counts.

A simple strategy is routing by a hash of tenant ID so the same tenant usually lands on the same write node. This is an application or proxy routing policy; it does not change the fact that every member stores the same data and still replicates transactions.

### 8.1. Read-after-write

After a write succeeds on the primary, an immediate subsequent read sent to a secondary may see stale state briefly. You can keep the session or route reads to the primary, or use an appropriate Group Replication consistency setting when waiting for transaction application is required.

In multi-primary mode, the same issue occurs if a client writes on node A and immediately reads from node B. Never assume all nodes have applied a transaction the instant the client receives commit confirmation. Test the application's read-after-write needs against your chosen consistency setting.

## 9. Quorum, membership, and failover

Group Replication requires a majority of active members to keep the group operational. With three members, at least two communicating members are needed for quorum. If majority is lost, the group stops accepting writes to prevent two network partitions from operating independently and diverging.

Quorum is a group property, not a choice between single-primary and multi-primary. Both modes require valid membership and quorum.

Operational principles:

- Align member count with failure domains; three members on separate hosts or zones survive a single failure better than three instances on one host.
- Keep inter-member networking stable, with latency and packet loss within design thresholds.
- Monitor `ONLINE`, `RECOVERING`, `ERROR`, and expelled-member states.
- Have a recovery plan for multi-member failures causing quorum loss; never force one partition active without verifying data state.
- Practice primary failover, member restarts, network partitions, and post-disconnect recovery.

In single-primary mode, when the primary fails, remaining members elect a new primary. In multi-primary mode, remaining members can keep accepting writes if quorum holds, though applications still must route away from the failed node and resolve transactions with uncertain outcomes at disconnect time.

## 10. Switching modes with MySQL Shell AdminAPI

For InnoDB Cluster, MySQL Shell AdminAPI provides methods to switch modes. Before running them, confirm version support, verify all members are healthy, ensure configurations are compatible, confirm no critical transactions or migrations are in flight, and verify the application is ready for the target mode.

Connect MySQL Shell with a cluster admin account, then retrieve the cluster object:

~~~javascript
var cluster = dba.getCluster();
cluster.status({extended: 1});
~~~

Switch to single-primary:

~~~javascript
cluster.switchToSinglePrimaryMode();
cluster.status({extended: 1});
~~~

Switch to multi-primary:

~~~javascript
cluster.switchToMultiPrimaryMode();
cluster.status({extended: 1});
~~~

These are AdminAPI operations, not SQL statements run in the `mysql` client. Execute them inside a controlled change window. If switching to single-primary and you need to designate a specific instance as primary, pass the instance argument per your version's AdminAPI syntax.

After switching modes:

1. Verify cluster status and member roles.
2. Check `read_only`/`super_read_only` according to each node's role and state.
3. Confirm Router metadata and application endpoints route accurately.
4. Run read/write smoke tests using application credentials.
5. Check replication errors, certification conflicts, and latency.
6. Monitor load closely following the transition.

Never switch modes on a live production cluster just to experiment. Rehearse on staging with compatible data and versions.

## 11. Observability and diagnostics

Several Performance Schema tables and administrative commands help monitor Group Replication:

~~~sql
-- Members and status in the group
SELECT *
FROM performance_schema.replication_group_members;

-- Basic Group Replication configuration
SHOW VARIABLES LIKE 'group_replication%';

-- Replica status
SHOW REPLICA STATUS\G
~~~

The `performance_schema.replication_group_members` table shows member ID, host, port, state, and role for each member depending on version. Exact columns may vary across MySQL releases.

In MySQL Shell:

~~~javascript
var cluster = dba.getCluster();
cluster.status({extended: 1});
~~~

When investigating multi-primary, track:

- Transactions rolled back due to certification conflicts.
- Commit rates and latency per node.
- Open transaction duration and write-set size.
- CPU, I/O, and network load across members.
- Membership, quorum, and recovery states.
- Client retry, timeout, and disconnect errors.
- Write workload skew across tenants/nodes.

When investigating single-primary, additionally track:

- CPU, I/O, connections, and lock waits on the primary.
- Replica apply lag and read-serving capacity.
- Failure detection time, primary election time, and routing recovery time.
- Failed write request rate during the failover window.

Do not measure only SQL queries per second. Measure successful transaction commits, rollback rates, p95/p99 latency, and retry volume; those metrics reflect real useful throughput.

## 12. Design example for an e-commerce system

Suppose an application has the following business workflows:

- Product and catalog lookups.
- Order creation and status updates.
- Inventory deduction and payment recording.
- Revenue reporting.

The `orders`, `order_items`, `inventory`, and `payments` tables are linked by foreign keys. Many requests may buy the same product simultaneously, turning inventory rows into hotspots.

Single-primary is usually the logical starting choice:

- Order, inventory, and payment writes go through the primary.
- Secondaries serve reporting queries if read lag is acceptable.
- Business transactions wrap related changes inside one InnoDB transaction.
- Router directs write connections to the current primary.

If you want to evaluate multi-primary, analyze these questions first:

1. Can tenants or data regions be assigned cleanly to minimize overlapping writes?
2. Will popular products still become hot rows across all nodes?
3. Will inventory and order updates touch the same keys from multiple nodes?
4. Are locking behaviors and foreign keys compatible with multi-primary limits?
5. Can clients retry entire transactions without duplicating payments or side effects?
6. Will inter-zone network latency inflate certification times?

If you cannot reduce conflicts or make retries safe, multi-primary will add complexity without proportional benefits.

## 13. Common design mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Choosing multi-primary just because there are multiple nodes | False expectations of write scaling | Measure commits, conflicts, and latency before choosing a mode. |
| Routing the same tenant randomly to multiple nodes | Increased contention on hot rows | Use routing affinity by tenant or key group. |
| Missing stable primary keys | Hard to identify rows and handle conflicts reliably | Define unique primary keys on business tables. |
| Retrying full requests without idempotency | External side effects can execute twice | Use idempotency keys, outbox pattern, and bounded retries. |
| Treating local locks as distributed locks | Other nodes are not coordinated as expected | Use proper distributed coordination or single-primary for serialized workflows. |
| Keeping cascading foreign keys in multi-primary without checking | May violate Group Replication support limits | Check schema and version limits; use single-primary if cascades are required. |
| Reading from a secondary immediately after writing | Results may be stale | Use read-after-write routing or appropriate consistency settings. |
| Checking only Router during failover | Confusing healthy routing with a healthy cluster | Verify quorum, member state, applier, and data integrity. |
| Switching modes during an active migration | Higher risk of schema and client errors | Coordinate migrations, verify cluster state, and switch modes in a change window. |

## 14. Practice exercises

### Exercise 1: Choosing a mode for a workload

An application has 80% reads and 20% writes. Writes concentrate on 20 top-selling products and update the same inventory table. Choose single-primary or multi-primary, explain the risks, and identify which node should receive writes.

### Exercise 2: Analyzing certification conflicts

Use two sessions connected to two different members in a test multi-primary environment. Update the same row in two overlapping transactions. Observe which transaction commits, which rolls back, and what error the client receives. Repeat with two independent rows for comparison.

### Exercise 3: Designing tenant-based routing

Suppose there are 12 tenants and 3 write-capable members. Propose a routing rule so each tenant normally hits the same member. Explain how to fail a tenant over to another member when a node fails and how to handle in-flight transactions during the switch.

### Exercise 4: Mode-switching drill

On a test InnoDB Cluster:

1. Check member status and versions.
2. Switch from single-primary to multi-primary using AdminAPI.
3. Inspect cluster roles and status.
4. Run write transactions on two members and observe the results.
5. Switch back to single-primary.
6. Verify Router and application behavior after each switch.

Record transition times, client errors, and commit/rollback metrics.

### Exercise 5: Evaluating safe retries

A transaction both updates an order and calls an external payment service. If commit is rejected due to a conflict, explain why retrying the whole function could charge the customer twice. Propose an idempotency key or transactional outbox to separate side effects from transaction retries.

## 15. Production readiness checklist for the write model

- [ ] Group Replication mode (single-primary or multi-primary) is explicitly decided.
- [ ] Read/write ratio, hot rows, transaction sizes, and latency are measured.
- [ ] Business tables have stable primary keys.
- [ ] Foreign keys, cascading actions, and locking statements are verified against version limits.
- [ ] Applications recognize certification errors and retry whole transactions with bounded backoff.
- [ ] External side effects have idempotency or outbox protection.
- [ ] Read/write routing aligns with the chosen mode and read-after-write requirements.
- [ ] Router metadata and application endpoints are tested.
- [ ] Quorum and failure domains are designed and monitored.
- [ ] Member failure, primary failover, network partition, and recovery drills are complete.
- [ ] Dashboards track commit latency, conflicts, rollbacks, retries, and replication health.
- [ ] DDL migrations and mode switches follow a coordinated workflow.
- [ ] Runbooks exist for quorum loss or a member unable to rejoin.

Single-primary provides a controllable write stream well suited to OLTP workloads with contention. Multi-primary opens additional write entry points, yet every transaction still passes through certification and replication; gains appear only when workloads partition cleanly with low conflict. Choose your mode from measured data, build routing and retries from day one, and validate through failover drills in a matching environment.
