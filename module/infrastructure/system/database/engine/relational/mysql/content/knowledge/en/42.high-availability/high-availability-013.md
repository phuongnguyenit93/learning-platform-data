# Topology Changes, Member Maintenance, and Quorum Loss Conditions

MySQL InnoDB Cluster uses Group Replication to maintain a group of servers sharing a consistent history of committed transactions under a group protocol. Whenever you add or remove members, switch between single-primary and multi-primary modes, or take a server down for maintenance, group membership changes. Those changes directly impact quorum, transaction commit capability, and fault tolerance.

Quorum is the condition allowing a group of members to agree on a membership view and keep processing transactions under the Group Replication protocol. If a network partition no longer holds a majority of the current view's members, that partition loses quorum and cannot continue committing transactions as a normal active group. Consequently, topology changes must be scheduled around healthy member counts, verified after every step, and paired with recovery plans for quorum loss.

This lesson belongs to mastering MySQL from data design, transactions, and concurrency control through replication and high-availability operations. Examples focus on MySQL Group Replication and InnoDB Cluster managed via MySQL Shell AdminAPI.

## 1. Membership view and quorum

Group Replication maintains a list of participating members called the membership view. When a member joins, leaves, or is expelled after losing connectivity, the group updates the view. Members must agree on the view to coordinate transaction ordering and group state.

Quorum requires the number of communicating, agreeing members to exceed half the members in the view. For a group of N members, minimum votes needed are:

\[
Q = \left\lfloor \frac{N}{2} \right\rfloor + 1
\]

The number of member losses the group can tolerate while keeping a majority is:

\[
F = \left\lfloor \frac{N-1}{2} \right\rfloor
\]

Illustrative configurations:

| Members in view | Required quorum | Member failures tolerated |
|---:|---:|---:|
| 1 | 1 | 0 |
| 2 | 2 | 0 |
| 3 | 2 | 1 |
| 4 | 3 | 1 |
| 5 | 3 | 2 |
| 6 | 4 | 2 |

A three-member group tolerates one failed member. If two members can still communicate, they form a majority. When only one member remains in a three-node view, that member cannot make decisions on behalf of the group.

A four-member group still tolerates only one failure, the same as a three-member group, because three votes are needed for a majority. Therefore, adding a fourth node to a three-node group does not automatically increase tolerated failures. To survive two independent failures, you need at least five members in the group.

### 1.1. Network partitions and the majority side

Suppose a three-member group A, B, and C splits into two partitions: A and B can still communicate with each other, while C is isolated.

~~~mermaid
flowchart TB
    subgraph Majority["Majority partition: 2/3"]
      A["A - ONLINE"]
      B["B - ONLINE"]
      A --- B
      W["Has quorum"]
    end
    subgraph Minority["Minority partition: 1/3"]
      C["C - UNREACHABLE"]
      X["Lost quorum"]
    end
~~~

The two-member partition retains majority and can continue processing per group state. The single isolated member in the other partition is not allowed to continue committing as an independent group. When the network recovers, the isolated member must resynchronize with the valid group's membership view and transaction history.

Crucially, quorum is calculated against the group's membership view, not against how many servers an operator sees powered on. A member not yet expelled from the view still counts toward the votes needed. During the failure-detection and expulsion window, behavior can differ from after the new view forms.

### 1.2. Quorum differs from primary

Quorum is a condition on member majority; primary is the write role in single-primary mode. The two concepts are related but distinct:

- Group has quorum and an active primary: the group processes writes normally if all other requirements are met.
- Primary fails while group retains quorum: a single-primary group can elect a new primary.
- Primary is running but isolated from the majority: that primary cannot keep accepting writes as if the group were healthy.
- Group loses quorum: members cannot keep committing transactions under the group protocol, even though MySQL processes remain running on individual hosts.

Never resolve quorum loss by arbitrarily opening write access on a minority member. Doing so creates two diverged data branches and leads to split-brain.

## 2. How single-primary and multi-primary affect topology

InnoDB Cluster typically runs in single-primary mode. One member holds the `PRIMARY` role and accepts write transactions; remaining members act as `SECONDARY`, usually read-only. When the primary fails, a group with quorum elects a new primary.

In multi-primary mode, multiple members can accept writes. Group Replication checks transaction conflicts through certification; conflicting transactions may roll back on one or more members. Multi-primary does not mean every workload scales writes linearly.

| Criterion | Single-primary | Multi-primary |
|---|---|---|
| Write entry points | One primary at a time | Multiple members can accept writes |
| Role switching | Elects a new primary when primary fails and quorum remains | No need to elect a single primary |
| Write conflicts | Centralizing writes minimizes cross-node conflicts | Certification conflicts can occur when multiple nodes edit the same data |
| Application routing | Writes go to primary; reads can go to secondaries if lag is tolerable | Applications can write to multiple nodes but must design to avoid conflicts |
| Use cases | Fits most standard transactional applications | Fits only when workloads and schemas are designed to limit conflicts |

With multi-primary, design cluster-wide unique primary keys, partition data ownership, or route record groups to dedicated nodes. Evaluate impacts on auto-increment, transaction order, DDL, and long transactions. If multiple nodes frequently update the same row, conflict rollback rates climb and throughput drops.

Modes can be switched via MySQL Shell AdminAPI. Run these commands in MySQL Shell JavaScript mode against a cluster object retrieved from metadata:

~~~javascript
var cluster = dba.getCluster();

cluster.switchToSinglePrimaryMode();
cluster.status({extended: 1});
~~~

Or switch to multi-primary once applications are ready:

~~~javascript
cluster.switchToMultiPrimaryMode();
cluster.status({extended: 1});
~~~

Before switching modes, verify versions, member states, and workload compatibility. Never tweak internal Group Replication variables directly in place of AdminAPI. After switching, verify primary/secondary roles, `read_only` states, and how MySQL Router or applications route writes.

## 3. Adding and removing members in the group

Adding members can increase read capacity and fault tolerance when sized properly. Removing members may be required when replacing servers, upgrading OSes, changing deployment zones, or retiring an unsafe instance.

With InnoDB Cluster, use MySQL Shell AdminAPI to update membership and metadata. Adding an instance generally involves:

1. Preparing the new server with a compatible MySQL version, network configuration, and TLS.
2. Assigning a unique `server_id` and configuring Group Replication per AdminAPI requirements.
3. Checking disk capacity, admin accounts, recovery accounts, and required privileges.
4. Choosing an appropriate recovery method: incremental from binary logs or clone from a donor member.
5. Adding the instance via AdminAPI and monitoring until it reaches `ONLINE`.

Example in MySQL Shell:

~~~javascript
var cluster = dba.getCluster();

cluster.addInstance("icadmin@db4.internal:3306", {
  recoveryMethod: "clone"
});

cluster.status({extended: 1});
~~~

The connection string is illustrative and omits passwords. Cloning replaces existing data on the new instance, so confirm the target host and ensure it holds no data that must be kept. If choosing incremental recovery, a source/donor must still retain all binary logs needed by the new member.

When removing an instance intentionally, verify beforehand that the group retains quorum and enough healthy members afterward. Example:

~~~javascript
cluster.removeInstance("icadmin@db3.internal:3306");
cluster.status({extended: 1});
~~~

After removal, confirm the member is gone from the membership view and cluster metadata reflects the updated topology. When bringing a maintained instance back, inspect its data and configuration first, then use `addInstance` or `rejoinInstance` according to its actual state.

Never remove a member without confirming whether it is primary or secondary, whether it serves application traffic, and how the remaining count affects quorum. If a member is unreachable, forced removal must be evaluated carefully; never use force as the default response to an undiagnosed connectivity error.

## 4. Planning rolling maintenance per member

Rolling maintenance applies changes one member at a time so the group stays online—for example, OS upgrades, disk replacements, MySQL patching, or network changes on a three-node cluster.

~~~mermaid
flowchart TD
    S["Verify cluster is healthy"] --> P["Select a secondary"]
    P --> D["Drain traffic and perform maintenance"]
    D --> R["Restart and rejoin"]
    R --> V{"Member ONLINE and caught up?"}
    V -->|Yes| N["Select next member"]
    V -->|No| H["Halt rollout, investigate"]
    N --> C{"More members need maintenance?"}
    C -->|Yes| P
    C -->|No| F["Verify whole cluster and finish"]
~~~

Recommended workflow:

1. **Pre-maintenance check:** run `cluster.status({extended: 1})`, confirm all expected active members are `ONLINE`, with no stalled recovery, certification errors, or abnormal lag.
2. **Assess failure budget:** compute quorum from the membership view and verify whether one additional failure during maintenance would break quorum.
3. **Select a node:** start with secondaries in single-primary mode to minimize write disruption. When maintaining the primary, switch primary cleanly first and confirm the new primary is healthy.
4. **Drain traffic:** shift read queries off the node, inspect open connections, and confirm applications no longer depend on the instance under maintenance.
5. **Remove from group if needed:** for lengthy maintenance or major config changes, use AdminAPI `removeInstance` before shutting the host down.
6. **Perform maintenance:** upgrade, replace hardware, or apply config changes on that one node.
7. **Restart and reintroduce:** verify config, TLS, `server_id`, networking, and recovery; use `addInstance` or `rejoinInstance` as appropriate.
8. **Verify:** wait for the member to reach `ONLINE`, check GTIDs, transaction queues, and application health before moving to the next node.

Example cluster check in MySQL Shell:

~~~javascript
var cluster = dba.getCluster();
cluster.status({extended: 1});
~~~

On a MySQL server, inspect membership via Performance Schema:

~~~sql
SELECT
  MEMBER_ID,
  MEMBER_HOST,
  MEMBER_PORT,
  MEMBER_STATE,
  MEMBER_ROLE
FROM performance_schema.replication_group_members;
~~~

Common states include `ONLINE`, `RECOVERING`, `OFFLINE`, `ERROR`, and `UNREACHABLE`. Only place a member back into application pools once it is `ONLINE` and data has caught up to workload requirements. `RECOVERING` means the member is synchronizing data; do not treat it as ready to serve reads.

In a three-node cluster, once one node is removed or expelled from the view, the remaining two nodes form a two-member group that can tolerate zero additional failures. Therefore, never begin maintenance on a second node before the first has returned healthy or the topology has been expanded appropriately.

## 5. Changing topology without losing quorum

Every add or remove operation alters the vote count of the membership view. Evaluate quorum before, during, and after every change.

Three-member cluster example:

| Phase | Members in view | Quorum | Notes |
|---|---:|---:|---|
| Initial | 3 | 2 | Tolerates one failure |
| Remove one node for maintenance | 2 | 2 | Tolerates zero additional failures |
| Maintained node rejoins and turns `ONLINE` | 3 | 2 | Single-failure tolerance restored |

Five-member cluster example:

| Phase | Members in view | Quorum | Notes |
|---|---:|---:|---|
| Initial | 5 | 3 | Tolerates two failures |
| Remove one node for maintenance | 4 | 3 | Still tolerates one failure |
| Remove another node | 3 | 2 | Tolerates one failure only |
| Remove one more node | 2 | 2 | Tolerates zero additional failures |

When designing topologies, plan for unexpected failures occurring mid-maintenance. If the system must still survive one unexpected failure during maintenance, provision enough nodes and failure domains. Five nodes sharing one power zone or network domain do not provide equivalent infrastructure fault tolerance; distribute failure domains.

Do not just count nodes. Verify:

- Are members placed across independent hosts, racks, availability zones, or failure domains?
- Do network latency and stability satisfy Group Replication requirements?
- Do remaining members have enough CPU, RAM, IOPS, and disk to absorb extra load while one node is in maintenance?
- Do donors have sufficient binary logs or capacity to clone/recover returning nodes?
- Do MySQL Router and applications route accurately as members leave and rejoin?

## 6. Quorum loss conditions and symptoms

A group loses quorum when communicating members no longer form a majority of the membership view. Common causes:

- Multiple members suffer hardware failures, power outages, or stopped services simultaneously.
- A network partition prevents nodes from forming a majority component.
- Simultaneous maintenance on multiple nodes exceeds the topology's failure budget.
- Timeouts or network issues expel members from the view.
- Partial cluster restarts after an incident without a consistent bootstrap/reboot plan.

Upon losing quorum, members stop committing transactions under the group protocol. Applications receive write errors or lose connections to the primary. Depending on `exit_state_action` and instance state, servers may switch to read-only, offline mode, or shut down. Check actual configuration and runtime state rather than assuming every version reacts identically.

Inspect membership and group status with:

~~~sql
SELECT
  MEMBER_HOST,
  MEMBER_PORT,
  MEMBER_STATE,
  MEMBER_ROLE
FROM performance_schema.replication_group_members;

SHOW STATUS LIKE 'group_replication%';
~~~

In MySQL Shell, `cluster.status({extended: 1})` gives a cluster-wide view including instance states and warnings. Collect MySQL logs, network logs, and per-node state before deciding how to recover.

### 6.1. Quorum loss does not immediately equal data loss

Losing quorum prevents the group from committing new transactions under Group Replication consistency guarantees. Previously committed transactions remain intact on members that applied them. However, nodes may hold differing GTID sets if an outage hit mid-flight or transactions were still applying. Identify the member with the most complete history before recovering.

Never assume a node is newest based solely on OS timestamps or hostname. Compare executed GTIDs, received transactions, logs, and recovery status. In multi-channel topologies or if errant transactions exist, have an experienced operator evaluate candidate selection.

## 7. Recovering from quorum loss

Recovery must avoid creating two groups accepting writes simultaneously. Two distinct scenarios apply:

**A majority partition still exists:** prioritize restoring network connectivity or bringing the needed members back into the majority partition. Never force a minority partition to form a new group while the old majority can still operate.

**The entire cluster stopped or no recoverable majority exists:** verify all nodes are stopped or fenced, identify the member with the most complete transaction history, and follow the complete-outage reboot procedure.

For InnoDB Cluster, MySQL Shell provides AdminAPI for complete-outage recovery:

~~~javascript
dba.rebootClusterFromCompleteOutage();
~~~

Run this only when the cluster is genuinely in complete outage and instances have been evaluated. If you must specify the seed instance, choose the host with the most complete GTID history per recovery procedure. After the cluster restarts, verify every member and rejoin/recover remaining nodes according to their state.

Never use `dba.rebootClusterFromCompleteOutage()` as a shortcut around a network partition where a majority partition is still running. Before rebooting, prevent old nodes from starting up automatically and accepting unplanned writes.

### 7.1. `group_replication_force_members` is an emergency-only measure

MySQL provides `group_replication_force_members` to manually override membership during special quorum-loss emergencies. It is high-risk because it forces a subset of members into a new view outside normal consensus.

Consider it only when:

1. Every group member and its connectivity state are accurately identified.
2. No other majority partition remains active anywhere.
3. Nodes outside the forced set are isolated or fenced and cannot accept writes.
4. The selected member set's data and transaction history have been evaluated.
5. An approved runbook, recovery plan, and clear owner are in place.

If you force a minority partition active while the old majority is still running, both groups can accept writes—causing split-brain and hard-to-repair data divergence. Never use this variable as a routine way to adjust quorum, never enter arbitrary addresses, and never use it in place of GTID checks.

### 7.2. Group bootstrap is only for creating a new group

`group_replication_bootstrap_group` initializes a brand-new group. It is not a generic recovery switch to enable across nodes when a cluster loses quorum. Enabling bootstrap on multiple members simultaneously creates independent groups and causes split-brain.

With InnoDB Cluster, prefer AdminAPI and the complete-outage reboot runbook. If performing manual bootstrap in a non-AdminAPI Group Replication deployment, run it on exactly one chosen member and turn the option off immediately afterward following version-specific documentation.

## 8. Maintenance, upgrades, and configuration changes

Certain changes impact compatibility or group membership:

| Change | How to prepare |
|---|---|
| MySQL upgrade | Check supported upgrade paths, intra-group version compatibility, and upgrade one node at a time in the order allowed by version docs |
| IP or hostname change | Update DNS, allowlists, local addresses, and connection configs; confirm all members communicate |
| TLS certificate rotation | Install compatible certs and CAs across nodes, check expiration, and verify before reload/restart |
| Hardware or storage change | Confirm backups, recovery capacity, and headroom on remaining nodes |
| Member count change | Recalculate quorum and failure budget before adding/removing |
| Switching single-primary/multi-primary | Evaluate conflicts, app behavior, auto-increment, and routing before changing mode |

For rolling upgrades, upgrade one node at a time and wait for it to return `ONLINE` and catch up on transactions before continuing. Never arbitrarily mix MySQL versions outside your target release's Group Replication compatibility matrix.

After configuration changes, verify Group Replication variables, TLS, network addresses, group name, and recovery channel settings. Back up configurations before changing them and know how to roll back if a node fails to rejoin.

## 9. Pre- and post-maintenance verification runbook

Before starting:

1. Capture cluster status via MySQL Shell and save the output.
2. Verify membership view, `ONLINE` member count, and `PRIMARY`/`SECONDARY` roles.
3. Confirm current quorum and calculate maximum tolerable node losses during maintenance.
4. Check GTIDs, applier queues, replication errors, and backup status.
5. Identify the node to maintain, application traffic to drain, and how it will rejoin.
6. Confirm operators can access remaining nodes if the maintained node fails to boot.

After each node:

1. Confirm the node starts with the right `server_id` and address.
2. Verify Group Replication joined the right group.
3. Wait for member state to reach `ONLINE`.
4. Confirm transaction queues and GTIDs have caught up.
5. Run test read queries and verify Router and application health.
6. Proceed to the next node only once all checks pass.

Completion:

- Confirm expected member count and quorum match final topology.
- Verify the primary role is correct and only authorized write endpoints are active.
- Check MySQL Router, connection pools, and alerts.
- Document versions, configurations, maintenance timestamps, and test results.
- Update topology diagrams, member inventories, and runbooks if anything changed.

## 10. Practical scenario

An InnoDB Cluster has three members: `db-a`, `db-b`, and `db-c`. `db-a` is currently primary. Operations needs to upgrade the OS on `db-c`, then `db-b`. While `db-c` is removed from the group for maintenance, networking to `db-b` fails.

Analyze:

1. After `db-c` is removed from the membership view, how many members remain and how many votes does quorum require?
2. If `db-a` and `db-b` cannot communicate, can `db-a` continue accepting writes as a lone member?
3. Why must you not force `db-a` into a one-node group without confirming `db-b` is fenced?
4. Should you restore `db-a`/`db-b` connectivity or reboot the cluster from complete outage here?
5. What conditions must be met before continuing maintenance on `db-b`?

With only `db-a` and `db-b` in the membership view, quorum is two. If they lose connectivity, neither holds a majority. Since `db-c` is outside the group for maintenance, the cluster has no majority component. The priority is restoring communication between `db-a` and `db-b`, verifying membership and primary status, and waiting for `db-c` to rejoin. Never force a single isolated node into a new group while the other node might still be running and accepting writes.

## 11. Self-check questions

1. How is quorum calculated for three-, four-, and five-member groups?
2. Why does a four-member group not tolerate more failures than a three-member group?
3. How do quorum and primary differ in single-primary mode?
4. Why must you wait for a member to become `ONLINE` and catch up before maintaining the next node?
5. In a 2/1 network partition of a three-node group, which side can continue processing transactions?
6. When should you use `dba.rebootClusterFromCompleteOutage()`?
7. What is the risk of using `group_replication_force_members` while the old majority partition is still active?
8. Why must `group_replication_bootstrap_group` never be enabled on multiple nodes simultaneously?

Topology changes and member maintenance are exercises in managing a cluster's failure budget. You must know the current membership view, votes needed for quorum, primary role, data synchronization status, and application routing state. When quorum is lost, restore the majority component or follow a tested complete-outage runbook; never create a new group from an un-isolated partition.
