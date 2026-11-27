# Quorum, Network Partitions, and Split-Brain Prevention

A multi-node MySQL system is only truly highly available when nodes can determine who is authorized to accept writes after a failure. When a network partitions, two groups of servers can each believe the other side is dead. If both groups accept writes, data diverges and becomes very difficult to reconcile. This phenomenon is called **split-brain**.

Quorum is a mechanism requiring a group of nodes to hold enough votes to make collective decisions. In MySQL Group Replication, quorum allows members to determine which partition retains the right to continue operating. With traditional asynchronous replication, MySQL does not provide built-in quorum-based primary election; an external orchestration layer must select a node, prevent the old primary from accepting writes, and update application endpoints.

This lesson belongs to relational MySQL operations: understanding quorum, identifying network disconnections, distinguishing node failures from network failures, and building failover procedures with fencing. Examples use MySQL 8.0, where `SOURCE`/`REPLICA` syntax is used starting in MySQL 8.0.23. Specific variable names or behavior may vary by version and deployment.

## Learning objectives

After this lesson, you will be able to:

- Explain quorum and calculate the minimum votes required for a group to keep operating.
- Distinguish Group Replication quorum from asynchronous and semi-synchronous replication.
- Describe how network partitions create split-brain risk.
- Inspect membership and member states in Group Replication.
- Build procedures for handling quorum loss, recovering nodes, and safely promoting replicas.
- Explain the roles of fencing, `read_only`, `super_read_only`, and write endpoints.

## 1. What is quorum?

Quorum is the minimum number of votes a group needs to continue an operation requiring consensus. For a system with `N` voting members, majority quorum is calculated as:

\[
Q = \left\lfloor \frac{N}{2} \right\rfloor + 1
\]

Examples:

| Members | Quorum | Members that can be lost while retaining quorum |
|---:|---:|---:|
| 1 | 1 | 0 |
| 2 | 2 | 0 |
| 3 | 2 | 1 |
| 4 | 3 | 1 |
| 5 | 3 | 2 |
| 7 | 4 | 3 |

Majority quorum prevents two independent partitions from simultaneously holding a majority of votes within the same membership view. For example, with three nodes, only one partition can contain two nodes; the remaining node lacks enough votes to unilaterally continue as an independent group.

In practice, you cannot just count running machines. You must know which nodes belong to the current membership view, which have been expelled, which are `RECOVERING`, and which mechanism determines valid votes. A server with a running `mysqld` process that is no longer part of the group does not automatically retain write authority.

### 1.1. Why are odd node counts preferred?

With majority quorum, three nodes require two votes and tolerate one failed node. Four nodes require three votes and still tolerate only one failed node. Five nodes require three votes and tolerate two failed nodes. Therefore, odd node counts generally provide better fault tolerance per added node.

For example, a three-node cluster placed across three independent failure domains can continue when one zone fails, provided the other two zones can still communicate. If all three nodes sit in the same rack or depend on the same switch, a shared infrastructure failure can wipe out quorum.

Quorum does not replace infrastructure redundancy. Distribute nodes across failure domains, ensure network connectivity between zones, and account for latency, bandwidth, power, storage, and coordination services.

## 2. Quorum in MySQL Group Replication

MySQL Group Replication uses group communication and membership mechanisms so members agree on the set of participating nodes. A group requires a majority of members in the membership view to continue processing transactions under group consistency guarantees. When a partition loses contact with the majority, that partition loses quorum and cannot continue committing transactions as an independent group.

Group Replication has two main modes:

- **Single-primary mode:** only one member is elected primary to accept writes; remaining members typically serve reads and apply transactions. When the primary fails, a group with quorum can elect a new primary.
- **Multi-primary mode:** multiple members can accept writes. Certification checks for conflicts between transactions before commit. This mode requires careful application design because concurrent updates to the same data can be rejected due to conflicts.

Quorum protects the group's authority to keep operating. It does not guarantee that every transaction a client ever sent was committed, does not replace backups, and does not automatically fix data written outside the group. In multi-primary mode, quorum also does not eliminate business-level data conflicts.

### 2.1. Three-member cluster example

Suppose a group has `db-1`, `db-2`, `db-3` and quorum is two:

| Scenario | Membership/connectivity | Expected outcome |
|---|---|---|
| `db-1` crashes; `db-2` and `db-3` communicate | Remaining two nodes hold majority | Group can continue; single-primary can elect a new primary |
| `db-1` is isolated; `db-2` and `db-3` communicate | Two-node partition holds majority | Majority partition continues; isolated node must not assume write authority |
| `db-1` and `db-2` lose contact with `db-3` but reach each other | Two-node partition holds majority | The two nodes can continue under valid membership |
| All three nodes cannot form a communicating majority | No partition holds quorum | Group cannot continue normal commits until quorum is restored or controlled recovery runs |

In a two-node cluster, quorum is two. When one node loses connectivity, the remaining node lacks majority and cannot continue as a fault-tolerant cluster. You can add a third voting member in another failure domain; MySQL Router is not a voting member of Group Replication.

### 2.2. Failure detection and member expulsion

Group Replication monitors messages between members to detect unresponsive nodes. If a node is deemed unreachable, the group can expel it from membership after a configured wait period. Variables such as `group_replication_member_expel_timeout` and `group_replication_autorejoin_tries` govern detection/expulsion and auto-rejoin behavior in supported versions.

Failure detection timeouts are an operational trade-off. Too short, and nodes get expelled during brief network blips; too long, and the system stays degraded longer. Measure network latency between failure domains, review Group Replication logs, and verify actual variables rather than copying sample values.

A node can be expelled due to network issues even while MySQL is still running and disk data remains intact. Once connectivity returns, the node can rejoin and receive missing transactions via distributed recovery or incremental state transfer if required binary logs are still available. If it cannot catch up via logs, re-provision it from a consistent data source.

## 3. Distinguishing node failures from network partitions

Two scenarios look nearly identical from a client's viewpoint yet require different responses:

| Scenario | Symptoms | Questions to verify |
|---|---|---|
| MySQL process stopped | Connections to the node fail; error log may record crash/shutdown | Can the node restart safely? Are data and binary logs recoverable? |
| Server or storage failure | Node unresponsive; OS or volume inaccessible | Can the instance be recovered or must the node be replaced? Is a consistent backup/clone available? |
| Network partition | Nodes still run but some pairs cannot communicate | Which partition has quorum? Are any nodes still accepting direct client writes? |
| Network latency or packet loss | Nodes repeatedly time out, membership flaps or rejoins | Are timeout thresholds appropriate? Is there congestion, MTU mismatch, firewall rule, or routing issue? |
| DNS/proxy/service discovery failure | Nodes communicate internally, but clients hit the wrong endpoint | Does the write endpoint point to the current primary? Are DNS caches or routes stale? |

Never conclude a node is dead merely because the application cannot connect. A node isolated from the group might still be reachable from certain client subnets. If clients continue writing directly to that node, split-brain can occur even while the rest of the cluster holds quorum.

## 4. How does split-brain happen?

Split-brain occurs when two nodes or two partitions both accept writes as though each were the authoritative primary. A classic scenario with asynchronous replication:

```text
                 Application
                    |
               Proxy / DNS
                    |
          Old primary: db-a
             /          \
            / replication \
           v               v
       Replica db-b    Replica db-c

     Network between db-a and db-b/db-c is partitioned

       db-a still receives writes from old clients
       db-b is promoted and also receives writes

       Two data histories begin to diverge
```

Asynchronous replication transfers transactions only after the primary commits. If the old primary loses contact with replicas, it can still keep operating independently. A failover procedure that only flips DNS or a proxy to a replica without fencing the old primary leaves a second write path open.

Group Replication uses quorum to prevent a minority partition from committing as a valid group; a member without quorum cannot commit group transactions. Applications connecting directly to that node may still open TCP sessions, but write operations will fail once the node loses quorum. Split-brain risk arises if an administrator forces membership improperly, bootstraps a new group while the old one is still active, or lets the old node accept writes after switching to an independent replication/primary setup.

### 4.1. Impact of split-brain

- The same primary key can be inserted or updated differently on both branches.
- Both branches can generate conflicting GTID transactions; GTIDs do not merge data automatically.
- When reconnecting replication, the applier can hit duplicate key errors, missing rows, or business conflicts.
- Transactions confirmed on one branch may not exist on the branch chosen as the final primary.
- Manual reconciliation may require data comparison, business replay, or restoring from backup.

No single `RESET REPLICA` or `CHANGE REPLICATION SOURCE` command can automatically reconcile two independent write histories. Before reconnecting, determine which branch is the source of truth and handle the divergent transactions from the other branch.

## 5. Standard replication and quorum are different mechanisms

MySQL offers multiple replication architectures; not all of them include built-in quorum.

| Mechanism | How transactions transfer | Built-in membership quorum? | Required failover actions |
|---|---|---|---|
| Asynchronous replication | Source commits first; replica receives and applies later | No | Use orchestrator/HA manager, compare GTIDs, and fence old source |
| Semi-synchronous replication | Source waits for at least one replica to acknowledge receiving and logging the event per config | Not a primary-election quorum | Still need candidate selection, transaction inspection, and fencing of old source |
| Group Replication | Members exchange and certify transactions according to group membership | Yes | Restore quorum, monitor election, and ensure clients write only to the valid primary |
| InnoDB Cluster | Uses Group Replication with metadata and MySQL Router/AdminAPI | Yes, via Group Replication | Use AdminAPI/Router per cluster state and verify write endpoints |

Semi-synchronous replication can reduce transaction loss risk compared to asynchronous replication under certain failure modes, but a log-receipt ACK does not mean the replica has applied the transaction. It also does not provide majority election or stop an old primary from accepting writes.

With asynchronous replication, an HA manager can use GTIDs to find the most up-to-date candidate. However, GTID sets only show history received/committed by a node; you must also check received-but-unapplied relay logs, transactions remaining in the source's binlogs, and acceptable RPO.

## 6. Inspecting Group Replication state

On MySQL Group Replication, inspect membership via Performance Schema:

```sql
SELECT
  MEMBER_ID,
  MEMBER_HOST,
  MEMBER_PORT,
  MEMBER_STATE,
  MEMBER_ROLE
FROM performance_schema.replication_group_members;
```

Common states include `ONLINE`, `RECOVERING`, `OFFLINE`, `ERROR`, and `UNREACHABLE`. Interpret states alongside the membership view and each member's logs. `RECOVERING` means the node is synchronizing data; do not put a node into read/write service simply because `mysqld` is running.

Inspect additional group and primary status:

```sql
SHOW GLOBAL STATUS LIKE 'group_replication%';
```

In single-primary mode, you can check the current primary via status variable:

```sql
SHOW GLOBAL STATUS LIKE 'group_replication_primary_member';
```

If using MySQL Shell InnoDB Cluster, `cluster.status({extended: 1})` provides additional details on topology, instance states, and warnings detected by AdminAPI. Always run the command against the right cluster object and cross-check against each MySQL instance's actual state.

Inspect variables related to quorum, timeouts, and read-only mode:

```sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
  'group_replication_member_expel_timeout',
  'group_replication_autorejoin_tries',
  'group_replication_unreachable_majority_timeout',
  'group_replication_exit_state_action',
  'group_replication_single_primary_mode',
  'read_only',
  'super_read_only'
);
```

Some variables do not exist in older versions or have different dynamic change constraints. If a statement omits a variable, check the documentation for your exact release and plugin status.

Also monitor:

- Counts of `ONLINE`, `RECOVERING`, `UNREACHABLE` members and membership change frequency.
- Rejoin duration, distributed recovery time, and data transfer volume.
- Certification errors, transaction conflicts, and apply queues.
- Inter-node network latency, packet loss, and storage response times.
- Replica lag, GTID sets, and endpoints currently used by applications.

## 7. Preventing split-brain with fencing

**Fencing** ensures an old node can no longer cause mutations once write authority has moved to another node. It is a critical safeguard during failover, especially with asynchronous replication.

Fencing methods can be combined:

| Mechanism | Example | What to verify |
|---|---|---|
| Power fencing | Shut down or isolate VM/instance via control plane | Is completion confirmed and prevented from auto-restarting? |
| Network fencing | Block client, replication, and admin paths to the old node via firewall/security group | Are any secondary network paths or direct connections still open? |
| Storage fencing | Revoke write access to shared volumes or use SCSI/storage reservations | Does any node still hold cached or volume write leases? |
| Proxy/service fencing | Remove old node from writer endpoint; revoke routes and write credentials | Can applications bypass the proxy and connect directly? |
| MySQL read-only guard | Enable `read_only=ON` and `super_read_only=ON` on old node | Can admin accounts or automation disable the guard? |

`read_only` and `super_read_only` are useful defense-in-depth guards inside MySQL, but they do not replace infrastructure fencing if an administrator can reopen the old node or if connections reach it via another path. In automated failover, fencing must return explicit confirmation before enabling writes on the candidate.

### 7.1. The write endpoint must have a single owner

Applications typically connect via MySQL Router, a proxy, or a service DNS name. When the primary changes, the write endpoint must update to point to the new primary. However, changing Router's route does not automatically block direct connections to the old primary.

Good design requires:

- Network restrictions so applications can connect only through the managed endpoint.
- Avoiding distributing physical primary addresses into individual service configurations.
- Health checks that distinguish a running node from a node authorized to accept writes.
- Updating the writer endpoint only after the candidate is verified and the old primary is fenced.
- Checking connection pools, DNS caches, and background jobs to ensure old connections are dropped.

## 8. Handling quorum loss in Group Replication

When a group loses quorum, do not try to force isolated nodes to continue accepting writes. First determine membership and which partition can still communicate.

### 8.1. Handling procedure

1. **Determine failure scope:** check which nodes are alive, which network paths are broken, and whether storage or process errors occurred.
2. **Read membership from reachable nodes:** compare `replication_group_members`, status variables, error logs, and cluster status in MySQL Shell.
3. **Identify the majority partition:** confirm which nodes still hold valid membership and quorum. Never infer this from a single health check.
4. **Protect the writer:** ensure nodes outside the majority partition cannot receive application writes. Check direct connections and admin privileges.
5. **Restore networking or nodes:** fix routing, firewalls, packet loss, storage, or the MySQL process. Monitor nodes rejoining and running distributed recovery.
6. **Confirm group stability:** verify all members are present, `ONLINE`, the primary is correct, and no replication errors exist before reopening full traffic.
7. **Reconcile data and backups:** verify critical transactions, GTID sets, binary log retention, and recoverability.

If the entire group has stopped, identify which member has the most complete data history before restarting the group. With InnoDB Cluster, use the AdminAPI recovery workflow suited to the outage state; never bootstrap a new group without proving the old group has completely stopped.

### 8.2. Caution with forcing quorum

MySQL Group Replication provides the advanced variable `group_replication_force_members` allowing operators to force a new membership view in certain quorum-loss situations. This is a high-risk recovery measure. `group_replication_exit_state_action` also determines what a member does upon leaving the group; depending on version and configuration, the member may enter read-only or offline mode. Check its current value to understand how a node reacts when expelled.

Consider forcing membership only after:

- Identifying the exact members to include in the new membership.
- Proving other partitions cannot continue operating or accepting writes.
- Fencing nodes excluded from the selected group.
- Stopping or isolating excluded nodes so they cannot keep operating under the old membership.
- Comparing GTIDs and evaluating any data that might be left behind on another partition.
- Preparing a plan to recover excluded nodes and reconcile data.

If two partitions are both forced into independent groups, split-brain can occur. Never use `group_replication_force_members` as a routine fix for timeouts or as an experiment to see if the group restarts.

Similarly, `group_replication_bootstrap_group=ON` must only be used under controlled conditions when initializing a brand-new group per procedure. Only one node may bootstrap the group at a time, and the flag must be turned off immediately afterward. Never enable bootstrap on multiple nodes simultaneously.

## 9. Failover with asynchronous replication

With traditional replication, an HA manager must execute explicit steps to prevent two primaries from accepting writes. A reference procedure:

1. Detect primary failure using multiple signals: MySQL connectivity, application health checks, host, and network checks.
2. Determine whether the old primary might still accept writes. If you cannot prove it has stopped, execute fencing.
3. Collect `gtid_executed`, `Retrieved_Gtid_Set`, `Executed_Gtid_Set`, and receiver/applier status from surviving replicas.
4. Select the candidate with the most complete transaction history aligned with GTIDs and RPO. Do not pick solely by lowest `Seconds_Behind_Source`.
5. If relay logs contain received-but-unapplied transactions, wait for or process them per tested runbook before promoting. Do not skip transactions just to shave seconds off failover time.
6. Verify the candidate has no unexplained errant transactions.
7. Promote the candidate per administrative procedure, enable writes, and update the writer endpoint after the old primary is fenced.
8. Repoint remaining replicas to the new primary using GTID auto-positioning if the topology qualifies.
9. Verify data, error logs, replication status, backups, and PITR capability post-failover.

If the old primary was merely network-partitioned and later reappears, keep it blocked from accepting writes. Compare its GTID set against the new primary, resolve divergent transactions on each branch, and only allow it to rejoin once data is consistent.

## 10. Illustrative scenarios

A Group Replication cluster has three nodes across three zones:

```text
Region A: db-a  <---->  Region B: db-b
                  \       /
                   \     /
                   Region C: db-c
```

Connectivity from `db-a` to `db-b` and `db-c` is interrupted, while `db-b` and `db-c` can still communicate. The two-node group holds majority. `db-a` is not allowed to continue committing as an independent group. When the network recovers, `db-a` must rejoin and apply missing transactions.

In another asynchronous topology, `db-a` is primary and `db-b`, `db-c` are replicas. Network connectivity from `db-a` to the application still works, but replication to both replicas breaks. An HA manager observes the replicas falling behind and chooses to promote `db-b`. Without fencing `db-a`, applications holding old connection pools can still write to `db-a` while new requests write to `db-b`. That is split-brain even though `db-b` was promoted cleanly.

Both examples show identical connectivity-loss symptoms, yet their safety mechanisms differ: Group Replication relies on membership quorum; asynchronous replication requires an HA manager, candidate selection, and fencing.

## 11. Practice exercise

A MySQL system has three nodes `mysql-1`, `mysql-2`, `mysql-3` and applications connect via a proxy. The system uses Group Replication single-primary mode. After a network incident:

- `mysql-1` loses contact with the other two nodes but still accepts connections from a legacy application subnet.
- `mysql-2` and `mysql-3` communicate with each other and report the group has quorum.
- The proxy has switched the writer endpoint to the new primary in the group.
- A batch job still connects directly to `mysql-1`'s IP address.

Design a response plan:

1. Why does the fact that `mysql-1` is running and accepting TCP connections not prove it has write authority?
2. Which statements would you use to check membership, the current primary, and node states?
3. What steps are needed to stop the batch job from continuing to write to `mysql-1`? Why is switching the proxy insufficient?
4. When the network recovers, what conditions must be verified before `mysql-1` rejoins?
5. If `mysql-1` has GTIDs not present on the new primary, how would you investigate?
6. If all three nodes lose quorum, why must you never enable bootstrap or force quorum on multiple nodes simultaneously?
7. Propose node placement, network monitoring, and failover drills to reduce recurrence risk.

Your plan must clearly define the authoritative write node, fencing actions, rejoin prerequisites, and post-incident data verification.

## 12. Common operational mistakes

- **Equating quorum with reachable pings:** quorum is based on membership and voting rules, not ICMP or TCP health checks.
- **Assuming two nodes in a two-node cluster can survive one failure:** quorum of a two-node cluster is two, so losing one node loses quorum.
- **Treating MySQL Router as a fencing mechanism:** Router directs connections; it does not block clients connecting directly to the old server.
- **Promoting a replica before fencing the primary:** the old primary can keep accepting writes from stale connection pools or unmigrated jobs.
- **Forcing quorum without knowing the other partition's state:** can create two independent groups both accepting writes.
- **Checking only `Seconds_Behind_Source`:** this metric does not replace comparing GTIDs, inspecting relay logs, or verifying committed transactions.
- **Sending traffic immediately to a rejoining node:** the node may still be `RECOVERING` or catching up; confirm state and data first.
- **Never drilling network partitions:** untested failover can fail due to DNS caching, missing permissions, firewalls, or automation bugs.

## Conclusion

Quorum lets a group of nodes decide whether enough members remain to keep operating after a failure. MySQL Group Replication uses membership and quorum to prevent minority partitions from committing; asynchronous and semi-synchronous replication require external HA tooling to elect a primary and fence the old node. Preventing split-brain requires a single authoritative writer, managed endpoints, verified fencing, GTID comparison, and clear rejoin procedures. Drill both node failures and network partitions, because the two can look alike to applications while posing very different risks to data.
