# Promotion and Ensuring a Single Writer Server in PostgreSQL

In PostgreSQL high availability (HA), **promotion** is the process of transitioning a standby server in recovery mode into a primary capable of accepting writes. Promotion allows the service to continue operating when the current primary fails or when a DBA proactively transfers roles between two servers.

Promotion by itself does not guarantee that there is only one primary. If the old primary is still running and still accepting writes while a new standby is promoted, both can accept transactions simultaneously. This is a **split-brain** situation: two independent data branches are both treated as authoritative, making reconciliation difficult and potentially causing data loss.

To guarantee a single writer server, the system must coordinate three things:

1. **Select one node authorized to be primary** using a quorum-based coordination mechanism or an authoritative decision source.
2. **Fence the old primary** so it cannot continue accepting writes.
3. **Promote the selected standby and switch routing** to the new primary after safety state is confirmed.

This lesson, **"Promotion and Ensuring a Single Writer Server in PostgreSQL"**, belongs to the **High Availability** chapter of the **Database Engine Relational PostgreSQL** module. It explains the promotion mechanism, timelines, failover and switchover, synchronous/asynchronous replication, quorum, fencing/STONITH, endpoint management, rejoining the old node, monitoring, and incident response procedures.

> **Core Principle:** PostgreSQL can promote a standby, but PostgreSQL streaming replication does not provide a complete leader election and fencing system on its own. To achieve a single-writer guarantee, you must ensure the old primary has lost the ability to write before the new primary is allowed to accept writes.

---

## 1. Primary and Standby in HA

A basic physical streaming replication topology has one primary and one or more standbys:

~~~text
                    Application
                       |
                       v
                 Write endpoint
                       |
                       v
                 Primary node
                  /         \
                 / WAL       \ WAL
                v             v
          Standby A       Standby B
          (recovery)      (recovery)
~~~

- **Primary:** accepts SQL writes and generates WAL.
- **Standby:** receives WAL from the primary, replays WAL, and maintains a copy of the data.
- **Promotion:** transitions a standby into a new primary.
- **Failover:** transfers service to a standby when the primary fails.
- **Switchover:** planned transfer of the primary role, typically for maintenance or infrastructure migration.

PostgreSQL physical replication is a one-way WAL transfer mechanism. A normal standby runs in recovery mode and does not accept application writes.

## 2. What Is Promotion?

Promotion ends recovery on a standby and transitions the server to normal operating mode.

When promotion completes:

- The server is no longer in standby recovery mode.
- The server can accept writes.
- The server begins writing WAL on a new timeline.
- Other standbys need to follow the new timeline and connect to the new primary per HA configuration.
- The old primary, if still alive, must be prevented from accepting writes and later rejoined according to procedure.

Promotion does not copy data backward to the old primary and does not automatically fix application routing.

## 3. Promotion Is Not the Same as Leader Election

PostgreSQL provides a mechanism to instruct a standby to promote. It does not decide all distributed questions on its own:

- Is the old primary truly dead or only disconnected?
- Is any node holding leader authority?
- Which standby has the newest WAL?
- Which node is permitted to accept writes?
- Who has authority to fence the old primary?
- When should the endpoint be updated?
- How will the old node be rejoined?

This is the responsibility of an HA manager/orchestrator or a control plane designed for that purpose.

HA management systems can coordinate PostgreSQL with a distributed configuration store, quorum, health checks, fencing, and routing. Whichever tool is used, you must understand its exact guarantees and failure modes.

## 4. Logical Steps of Promotion

At a conceptual level:

1. The HA manager detects that the primary is no longer healthy.
2. The system determines whether this is a real failure or a network partition.
3. The old primary is fenced or proven unable to accept writes.
4. A control plane with quorum selects a standby as the candidate.
5. The candidate is instructed to promote.
6. PostgreSQL completes recovery up to available WAL and starts a new timeline.
7. Health checks confirm the candidate is the new primary.
8. The write endpoint is moved to the new node.
9. Remaining standbys are reconfigured to follow the new primary.
10. The old primary is kept isolated until it can be safely rejoined.

~~~text
Primary failure suspected
          |
          v
   Verify failure / quorum
          |
          v
  Fence old primary
          |
          v
  Select one standby
          |
          v
      Promote
          |
          v
  Verify new primary
          |
          v
  Move write endpoint
          |
          v
  Rejoin other nodes
~~~

The ordering of fencing and promotion is critical. Two nodes must never both hold write authority during the transition window.

## 5. What Is Split-Brain?

**Split-brain** occurs when two or more PostgreSQL nodes simultaneously act as primary and accept writes for one logical database service.

Example:

- Primary A is severed from the HA manager's network.
- A still has connectivity to one group of applications.
- The HA manager cannot see A and promotes standby B.
- One application group writes to A while the other writes to B.

~~~text
           Network partition
        +----------------------+
        |                      |
        v                      v
   Primary A               Standby B
   (still accepting writes) (promoted)
        ^                      ^
        |                      |
    App group 1             App group 2

          Both branches accepting writes
                 SPLIT BRAIN
~~~

Both nodes may return `false` for `pg_is_in_recovery()`. PostgreSQL does not automatically merge transactions from two independent timelines into a single shared history.

## 6. Why Is Split-Brain Dangerous?

Once two primaries accept writes independently:

- The same primary key can be created with two different values.
- A row can be `UPDATE`d on both branches in two directions.
- A `DELETE` on one branch does not automatically appear on the other.
- Sequence values can collide or diverge.
- Business transactions can be executed twice.
- The two WAL branches have different histories.
- There is no general-purpose merge operation safe for all schemas and business rules.

It may be necessary to pick one branch as authoritative, extract data from the remaining branch, and reconcile manually. This is complex work, not a simple failback command.

## 7. Single-Writer Guarantee Requires Multiple Layers

An HA design should include these layers:

| Layer | Responsibility |
|---|---|
| Replication | Keep standbys with data close to the primary |
| Leader election/quorum | Decide which node has authority to be leader |
| Fencing | Prevent the old primary from continuing to write |
| Promotion control | Promote exactly one candidate |
| Routing | Direct applications to the confirmed primary |
| Monitoring | Detect lag, split-brain, and abnormal states |
| Rejoin procedure | Return the old node as a standby |

Routing and fencing are two different things. Switching the load balancer to B does not automatically prevent applications or administrators from connecting directly to A.

## 8. What Is Fencing?

**Fencing** is the action of isolating a node from being able to affect shared systems or accept writes.

The goal is to ensure the old node cannot continue operating as primary after leader authority has transferred to the new node.

Fencing methods can include:

- Powering off the old node via hardware/cloud control plane (STONITH).
- Cutting network access to the database service and client networks.
- Revoking access to shared storage in shared-storage topologies.
- Using a watchdog or reliable self-fencing mechanism when a node loses its lease.
- Combining multiple fencing layers to avoid any remaining access path.

Specific measures depend on infrastructure. You must verify that fencing truly blocks writes, not merely makes health checks fail.

## 9. STONITH

STONITH is commonly understood as "Shoot The Other Node In The Head": a mechanism to forcibly power off or isolate the old node via an independent management channel.

Infrastructure examples may include:

- Cloud instance stop/terminate.
- IPMI/iLO/iDRAC power control.
- Hypervisor VM power-off.
- Storage fencing.
- Network switch/SDN isolation.

The management channel must operate independently of the partitioned network path. If a fencing command cannot confirm status, do not assume the old node has been powered off.

### 9.1. Fencing Must Have a Verified Result

An automation script calling an instance stop API that receives a timeout does not know whether the node has powered off. It must verify the final state from an independent control plane or the corresponding fencing mechanism.

If you cannot verify that the old primary has been fenced, promoting can create split-brain. The system must have a clear policy: wait, retry fencing, or sacrifice availability to preserve single-writer safety.

## 10. Network Isolation Is Not Always Enough

Disabling an interface or changing DNS may not block every write path:

- Applications may connect by direct IP.
- Old connection pools may still exist.
- Jobs, DBAs, or backup tools may connect directly.
- The old primary may still accept writes from another internal network.
- A node partitioned from the control plane may still reach storage or the client network.

Fencing must account for all possible write paths. DNS/load balancers are only a routing layer, not a replacement for fencing.

## 11. Quorum and Leader Election

In distributed systems, quorum is the minimum number of votes required to make an authoritative decision.

For example, a control plane has three voting members. The majority is two votes. When one node loses contact with the rest:

- The group with a majority can continue coordinating.
- The minority group must not claim leader authority.
- A candidate is only promoted if the control plane grants authority per policy.

~~~text
Control plane: 3 voters

Healthy:
  Voter A + Voter B + Voter C
  Majority = 2

Partition:
  Group 1: A + B  -> has quorum
  Group 2: C      -> no quorum

Only the group with quorum is allowed to make leader decisions.
~~~

Control-plane quorum does not automatically fence PostgreSQL. It helps unify decisions; fencing or self-fencing must prevent the node without quorum from continuing to accept writes.

## 12. Leases and the Risk of Stale Leases

Some HA managers use time-bounded leases to grant leader authority.

A node may only act as leader while holding a valid lease. When the lease expires, the node must stop accepting writes on its own or be fenced.

Leases are only safe when:

- Clock and timeout assumptions are properly designed.
- The old node cannot continue writing after the lease expires.
- The control plane has proper consensus/quorum.
- The new node is not promoted too early while the old lease is still valid.
- Network partitions do not cause the old node to skip self-fencing.

Simply storing a lease timestamp in a file or using a basic heartbeat does not constitute a safe distributed lease.

## 13. PostgreSQL Does Not Fence the Old Primary on Its Own

PostgreSQL streaming replication has no built-in mechanism for an old primary to know on its own that another standby has just been promoted elsewhere across arbitrary network partitions.

Therefore:

- `pg_promote()` does not shut down the old primary.
- `pg_ctl promote` does not switch endpoints.
- `pg_is_in_recovery()` only describes the node's local state.
- `pg_stat_replication` is not a quorum service.
- Synchronous replication does not perform STONITH on its own.

An HA manager must coordinate these pieces.

## 14. Failover and Switchover

| Criterion | Failover | Switchover |
|---|---|---|
| Cause | Primary failed/no longer safe | Planned transition |
| Old primary | May be unresponsive | Controllable |
| Writes | May be interrupted abruptly | Usually quiesced beforehand |
| Candidate WAL | May be missing some async commits | Can wait for candidate to catch up |
| Fencing | Critical | Still must confirm old primary no longer accepts writes |
| RPO | Depends on replication mode and candidate | Can be near or equal to 0 with proper sync workflow |
| RTO | Depends on detection, fencing, promote, routing | Depends on maintenance window and preparation |

Switchover generally carries lower data risk because writes can be controlled and you can wait for the standby to catch up. However, you still must prevent the old primary from accepting writes after roles change.

## 15. Manual Promotion With pg_promote

On a standby, promotion can be requested via SQL:

~~~sql
SELECT pg_promote();
~~~

The function has optional parameters to wait for promotion to complete:

~~~sql
SELECT pg_promote(wait => true, wait_seconds => 60);
~~~

Exact parameter names and signatures should be checked against your PostgreSQL version. When `wait` is enabled, the function waits until promotion completes or the timeout expires. The return value indicates whether the promotion request succeeded according to the function's semantics.

This is an operation on the targeted node. It does not check cluster-wide quorum, does not fence the old primary, and does not update application routing.

**Only run manual promotion after confirming the candidate and old-primary fencing per runbook.**

## 16. Promotion With pg_ctl

You can request a promote from the administrative host:

~~~bash
pg_ctl promote -D /var/lib/postgresql/data
~~~

Timeout/wait options for `pg_ctl` depend on version. Verify server status and logs after running the command.

`pg_ctl promote` sends a request to the corresponding PostgreSQL instance. It does not replace an HA manager or fencing.

## 17. How Does Promotion Work With Recovery?

A standby continuously replays WAL in recovery mode. Upon receiving a promotion request:

- Recovery is instructed to end.
- PostgreSQL advances as far as recovery can reach with available WAL.
- The server transitions to normal operating state.
- A new timeline is created.
- The server starts serving the primary role.

Transactions committed on the old primary whose WAL has not reached the candidate may be lost in asynchronous replication. Promotion cannot reconstruct WAL that the standby never received.

## 18. Timelines After Promotion

PostgreSQL uses timelines to distinguish branches of WAL history.

~~~text
Timeline 1 (old primary)
       |
       +---- WAL ---- WAL ---- WAL
                              |
                              | promote standby
                              v
                        Timeline 2
                              |
                              +---- WAL ---- WAL
~~~

After promotion, the new primary writes WAL on the new timeline. A timeline history file describes where the new timeline branched from the previous history.

Timelines help PostgreSQL manage WAL history, but they do not automatically resolve which branch is authoritative if two primaries accepted writes concurrently.

## 19. RPO Depends on Replication Mode

**RPO (Recovery Point Objective)** is the maximum amount of data the business accepts losing during a failover.

### 19.1. Asynchronous Replication

In asynchronous replication, the primary can acknowledge `COMMIT` before the standby receives/flushes the corresponding WAL.

If the primary is lost suddenly:

- The standby may be missing WAL for recently committed transactions.
- Promoting the standby can lose those commits.
- RPO depends on lag, network, WAL generation, and the moment of failure.

Asynchronous replication usually has lower latency but does not guarantee zero data loss.

### 19.2. Synchronous Replication

Synchronous replication can require the primary to wait for standby WAL confirmation before returning `COMMIT` success.

Illustrative configuration example:

~~~text
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
synchronous_commit = on
~~~

With this policy, the primary waits for the synchronous standby chosen per configuration to satisfy the acknowledgement requirement. You must understand precisely which standby is considered synchronous and which candidate holds the acknowledged commits.

Synchronous replication can significantly reduce RPO, but does not automatically guarantee that every failover candidate has all commits if the topology/policy allows different standbys to receive acknowledgements.

## 20. synchronous_commit Levels

Common levels:

| Setting | Wait condition |
|---|---|
| `local` | Local WAL flush |
| `remote_write` | Standby writes WAL to OS |
| `on` | Standby flushes WAL durably per synchronous policy |
| `remote_apply` | Standby replays/applies transaction |
| `off` | May return COMMIT before local WAL flush |

`remote_apply` may be needed when applications require the transaction to be applied on the synchronous standby before the primary returns `COMMIT`. It typically increases commit latency.

### 20.1. Synchronous Does Not Automatically Mean Zero Data Loss on Every Failover

Consider:

- `synchronous_standby_names`.
- `FIRST` vs. `ANY` quorum mode.
- Which standby acknowledged a specific transaction.
- Which candidate is chosen for promotion.
- Whether WAL was flushed or only written/applied.
- Whether fencing and leader election are properly implemented.

In `ANY N` quorum, a transaction is acknowledged by any N standbys in the group. You cannot infer that every standby candidate received that transaction. The HA manager must choose a candidate with appropriate WAL or have a policy that accepts the corresponding RPO.

## 21. Quorum Synchronous Replication

Quorum configuration can take the form:

~~~text
synchronous_standby_names = 'ANY 2 (standby_a, standby_b, standby_c)'
~~~

This means commit waits for acknowledgement from any two standbys in the list according to synchronous replication semantics.

This improves commit availability when one standby fails, but during failover you must know which nodes hold the acknowledged WAL. Quorum commit does not mean all nodes are identical at every moment.

Quorum design must account for the number of voting/replication nodes, failure domains, candidate selection, network partitions, latency, and RPO/RTO objectives.

## 22. WAL Positions for Candidate Selection

On the primary, standby progress can be observed:

~~~sql
SELECT
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication
ORDER BY application_name;
~~~

- `sent_lsn`: WAL sent.
- `write_lsn`: WAL written by the standby at the write level.
- `flush_lsn`: WAL flushed on the standby.
- `replay_lsn`: WAL replayed on the standby.

The candidate with the highest flush/replay LSN typically has the smallest WAL gap, though the decision must factor in timeline, sync policy, WAL receiver state, and when the metrics were captured.

Do not select a candidate based solely on ping latency or a green health check.

## 23. Monitoring Standby Receive and Replay

On a standby:

~~~sql
SELECT
    pg_is_in_recovery() AS in_recovery,
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_xact_replay_timestamp() AS last_replay_time;
~~~

You can inspect the WAL receiver:

~~~sql
SELECT *
FROM pg_stat_wal_receiver;
~~~

- Receive LSN indicates WAL received.
- Replay LSN indicates WAL applied.
- The gap between the two reflects the WAL backlog on the standby.
- If `pg_stat_wal_receiver` has no rows, the standby may be disconnected or pulling WAL from an archive.

`pg_last_xact_replay_timestamp()` can appear stale when the primary is idle. Do not use this timestamp alone to determine lag.

## 24. pg_is_in_recovery Does Not Prove a Node Is the Sole Leader

~~~sql
SELECT pg_is_in_recovery();
~~~

- `true`: the node is in recovery mode, typically a standby.
- `false`: the node is no longer in recovery mode, typically a primary after startup/promotion.

If split-brain has occurred, both the old primary and the new primary can return `false`.

Therefore, this function only answers "is this node in recovery?", not "is this node the sole primary authorized to accept writes?".

It must be combined with authoritative leader state from the HA manager, fencing status, and routing policy.

## 25. Write Endpoint and Connection Routing

Applications commonly connect through:

- HAProxy.
- PgBouncer combined with health checks/endpoints.
- Virtual IP.
- DNS/service discovery.
- Cloud database endpoints.
- Kubernetes Services or operator-managed endpoints.

The endpoint should point to the confirmed primary. Health checks must distinguish primary/standby and verify leader authority from the control plane whenever possible.

### 25.1. Routing Is Not Fencing

If the endpoint switches from A to B:

- Old connection pools may still hold connections to A.
- A job may use A's direct IP.
- A DBA may have a direct session open to A.
- A may still have its port open and accept writes.

Old write paths must be closed/severed via fencing and/or database/network-side policy, not just DNS changes.

## 26. Client Reconnect After Promotion

When the primary changes:

- Old TCP connections typically break or error out.
- Applications need retry logic with backoff.
- Connection pools need to discard stale connections.
- In-flight transactions may have an unknown outcome to the client if the connection drops before receiving the `COMMIT` response.
- Non-idempotent requests risk being resent and executed twice.

Application retry design requires transaction idempotency or request keys for sensitive workflows. Do not blindly retry every transaction after connection loss without evaluating the commit outcome.

## 27. DNS TTL and Virtual IP

DNS failover can be affected by client DNS caches, runtime resolver caches, connection pools, TTLs, proxy/service discovery caches, and network route convergence.

A Virtual IP or load balancer can switch faster, yet is still only routing. You must still confirm the old primary is fenced.

Use centrally managed endpoints and avoid hardcoding the primary address across multiple services.

## 28. Planned Switchover

A general switchover procedure:

1. Select the standby candidate.
2. Confirm the standby is healthy and has sufficient WAL capacity.
3. Stop or quiesce application writes on the primary.
4. Wait for in-flight transactions to complete or handle them per policy.
5. Capture the primary's final LSN.
6. Wait for the candidate to receive and replay up to that boundary.
7. Confirm the candidate has caught up.
8. Stop/demote the old primary and verify it no longer accepts writes.
9. Promote the candidate.
10. Verify timeline, recovery state, and write capability.
11. Switch the write endpoint.
12. Configure the old primary as a standby of the new primary.
13. Rejoin and verify replication.

Command details depend on the HA manager and topology. A controlled procedure generally yields lower RPO than an unexpected failover because you can wait for full replay before promoting.

## 29. Unplanned Failover

When the primary is lost:

1. Health checks detect the failure.
2. The control plane verifies quorum and node status.
3. Fence the old primary.
4. Select a standby based on WAL progress and synchronous policy.
5. Promote the candidate.
6. Verify the new primary.
7. Update routing.
8. Verify applications reconnect.
9. Rebuild/rejoin other standbys.
10. Record actual RPO and investigate the root cause.

Do not promote multiple standbys simultaneously. Only one candidate is granted leader authority.

## 30. The Old Primary Returns

After failover, the old primary may restart with an older WAL history.

Do not allow that node to accept writes or be exposed on the write endpoint.

If the old node has diverged from the new primary, it must be brought onto the same history. Options:

- `pg_rewind` if prerequisites are met.
- Recreate the standby from a base backup of the new primary.
- Restore using a supported physical recovery procedure.

Never simply start the old primary as an independent primary and reconnect applications.

## 31. pg_rewind

`pg_rewind` can synchronize a diverged data directory with a source cluster by identifying and copying blocks modified since the point of divergence.

Conceptual example:

~~~bash
pg_rewind --target-pgdata=/var/lib/postgresql/old-primary \
          --source-server="host=new-primary.example dbname=postgres user=rewind_user"
~~~

Key prerequisites typically include:

- Data checksums enabled at `initdb` or `wal_log_hints=on`.
- `full_page_writes=on`.
- Target cluster cleanly shut down as required by `pg_rewind`.
- Source server is the new authoritative cluster.
- Sufficient WAL exists from the point needed to determine divergence; archive access may be required depending on configuration.
- Version and permissions satisfy tool requirements.

Read the documentation for your exact major version before running. `pg_rewind` modifies the target data directory; back up/retain a copy and verify the exact target path before executing.

## 32. Rejoining the Old Primary as a Standby

After rewind or rebuild:

1. Ensure the old primary remains fenced during the operation.
2. Configure `standby.signal` and connection to the new primary per version.
3. Configure `primary_conninfo` and appropriate slot if used.
4. Start the node as a standby.
5. Confirm `pg_is_in_recovery()` returns `true`.
6. Verify the WAL receiver connects to the new primary.
7. Monitor receive/replay LSN.
8. Only return the node to the candidate pool once replication is stable.

Do not return a node to the HA candidate pool merely because the PostgreSQL process is running.

## 33. Timelines and History After Failover

After promotion, the new primary writes on a new timeline. Other standbys must learn the new timeline and fetch WAL from the correct branch.

Inspect timeline/control information using the appropriate tool:

~~~bash
pg_controldata /var/lib/postgresql/data
~~~

Timeline history files in the WAL archive help determine the relationship between old and new timelines.

If the archive is missing a history file or WAL segment, a standby may be unable to follow the intended branch.

## 34. Fencing When the Primary Is Partitioned

This is the most dangerous scenario:

- Primary A loses connectivity to the HA manager.
- A still has network connectivity to some clients.
- The HA manager has quorum and selects B.
- B is about to be promoted.

Before B accepts writes, you must ensure A cannot continue writing. Options include hardware/cloud power fencing, verified storage/network isolation, or reliable lease/watchdog-based self-fencing.

If there is no way to verify A has been disabled, the system must have a policy not to promote in order to protect single-writer safety. This is the trade-off between availability and consistency.

## 35. Quorum Control Plane Must Be Independent From the PostgreSQL Data Plane

An HA manager typically stores leader state in a distributed store/consensus system.

The data plane consists of PostgreSQL nodes and replication connections. The control plane is where who becomes leader is decided.

If the control plane loses quorum:

- Two groups must not independently elect leaders.
- The old node must self-fence when it no longer holds leader authority if the design is lease-based.
- A new candidate must not promote simply because it cannot ping the primary.
- Fail-safe policies must be followed.

A distributed store with three members all residing on one host or one failure domain does not provide true fault tolerance.

## 36. Health Checks Must Distinguish States

A health check can verify:

- TCP connection to PostgreSQL.
- `SELECT 1` query.
- `pg_is_in_recovery()`.
- Replication lag.
- WAL receiver state.
- Disk capacity.
- Control-plane leader state.
- Fencing status.

`SELECT 1` only proves the database accepts queries. It does not prove the node is authorized to accept writes.

A node can be process-healthy yet not be the leader. Health checks for the write endpoint must verify role and leader authorization per the HA design.

## 37. Write Controls as an Additional Defense Layer

Beyond fencing, writes can be restricted via:

- Granting application write credentials only on the coordinated primary.
- Separating read/write endpoints.
- Blocking client networks from reaching standbys/the old primary.
- Using role-checking proxies.
- Restricting administrative privileges and direct connections.
- Monitoring for writes outside the standard application path.

These measures are defense in depth. If the old primary still has superuser/local access or another connection path, ACLs alone do not replace fencing.

## 38. Synchronous Standby and Candidate Selection

If low RPO is required, you must ensure the standby selected for promotion has WAL containing the commits acknowledged by the primary.

With one fixed synchronous standby, candidate coordination can be simpler, though state must still be monitored.

With multiple synchronous standbys or `ANY` quorum, the manager needs to know which node flushed the WAL. Do not look only at the list of sync candidates or current `sync_state` and assume every candidate has identical WAL.

You can follow a procedure:

1. Retrieve the commit policy and synchronous standby list.
2. Track flush/replay LSN.
3. On failover, select a node with appropriate WAL progress.
4. Fence the old primary.
5. Promote the candidate.
6. Verify actual RPO.

## 39. Asynchronous Failover and Potential Data Loss

If the standby candidate is missing some transactions committed on the old primary, those transactions are absent from the new primary's history.

After failover, do not attempt to replay writes from the old primary by arbitrarily splicing two timelines. Evaluate the remaining data on the old primary, establish the authoritative history, and perform controlled business reconciliation if needed.

Record the candidate's replay LSN at promotion time, the primary's last known WAL/commit position, estimated lag, transactions with unknown commit outcomes in applications, and business records requiring reconciliation.

## 40. Do Not Use Two Primaries as "Redundancy"

A standby kept in recovery mode is the backup replica. A second primary accepting writes independently is not an HA standby.

If multiple writers are desired, you need an explicitly designed multi-writer solution with conflict handling, key allocation, consistency semantics, and application support. PostgreSQL physical streaming replication does not provide that.

## 41. Patroni, repmgr, and HA Managers

PostgreSQL HA management tools can automate:

- Health checks.
- Leader election.
- Quorum/Distributed Configuration Store.
- Promotion.
- Fencing/watchdog integration.
- Reconfiguration of standbys.
- Endpoint/routing hooks.
- Rejoin/rewind workflows.

Examples in the PostgreSQL ecosystem include Patroni and repmgr. They have different models, configurations, and guarantees; you must read the documentation for the deployed version.

Do not equate installing an HA manager with having safe fencing. Explicitly verify the DCS/consensus topology, lease/TTL semantics, watchdog/fencing configuration, behavior on quorum loss, candidate selection policy, synchronous mode handling, routing update hooks, and recovery after split-brain.

## 42. Kubernetes and Container Environments

In Kubernetes, Pod readiness or Service endpoint updates are not complete fencing.

An old Pod can continue running and accepting connections if another network path exists. The operator must manage leader state, storage, Pod lifecycle, and failover.

Determine:

- Is the PersistentVolume attached exclusively?
- Node partition behavior.
- Is Pod termination confirmed?
- Does the Service remove the old primary from endpoints?
- Can the old node continue accepting writes via another address?
- Does the operator have proper quorum/leader election and fencing?

Do not manually promote a Pod with a SQL command merely because Kubernetes reports the primary Pod unhealthy.

## 43. Backups Do Not Replace HA

HA keeps the service running when a node fails. Backups/PITR enable recovery when data is deleted/corrupted or all replicas contain a logical mistake.

Replication also replicates logical mistakes such as `DROP TABLE` or a bad `UPDATE`.

A production system needs base backups, WAL archiving, restore tests, standbys, fencing/failover, monitoring, and runbooks.

Do not treat a standby as an independent backup.

## 44. RTO and Failover Time

**RTO (Recovery Time Objective)** is the target time for the service to resume operation.

~~~text
Detection
   + Quorum/election
   + Fencing
   + Promotion
   + Routing convergence
   + Client reconnect
   + Application recovery
~~~

Optimizing promotion time while skipping fencing reduces RTO on paper but creates split-brain risk. Time each step in the lab and choose timeouts aligned with failure detection, networking, and application retries.

## 45. Monitoring for Single-Writer Safety

Signals to monitor:

| Metric/state | Meaning |
|---|---|
| Authoritative leader ID | Node currently granted leader authority by the control plane |
| Quorum status | Whether the control plane still holds majority |
| Fencing result | Whether the old primary has been isolated |
| `pg_is_in_recovery()` | Local role of the PostgreSQL node |
| Timeline ID | Current WAL branch |
| Standby flush/replay LSN | Replication progress |
| Logical/physical slot health | WAL retention state |
| Write endpoint target | Where applications are being routed |
| Connection count | Whether clients remain connected to the old node |
| Disk/WAL capacity | Ability to continue receiving WAL |
| Failover events | History of promotions/demotions |

Alert when more than one node reports the primary role or when the write endpoint does not match the authoritative leader.

## 46. Detecting Two Primaries

You can collect from every node:

~~~sql
SELECT
    inet_server_addr() AS server_address,
    inet_server_port() AS server_port,
    pg_is_in_recovery() AS in_recovery;
~~~

Combine with timeline and HA manager state.

If two nodes both return `in_recovery=false`, that is a signal requiring immediate investigation. However, a single node returning `false` does not prove it holds leader authority; cross-check the authoritative leader and fencing state.

Automation should not automatically drop/rewind a node based on a single query.

## 47. Incident Response When Split-Brain Is Suspected

1. Stop or restrict writes at the application layer per incident policy.
2. Identify the authoritative leader from the control plane/quorum.
3. Fence the unselected node.
4. Confirm only one node continues accepting writes.
5. Record timelines, LSNs, logs, and promotion timestamps.
6. Assess whether the two branches generated independent writes.
7. Choose the authoritative history per policy.
8. Extract and reconcile required data from the remaining branch.
9. Rewind/rebuild the old node as a standby.
10. Reopen writes only after single-writer state is confirmed.

Do not attempt to "merge WAL" from two primaries using unplanned manual operations. WAL timelines are not a business merge tool.

## 48. Lab: Manual Standby Promotion

Perform in two PostgreSQL lab instances, never in production.

1. Set up a primary and a physical standby.
2. Confirm the standby is in recovery.
3. Stop writes on the lab primary.
4. Stop/isolate the lab primary so it cannot accept writes.
5. Request the standby to promote:

~~~sql
SELECT pg_promote(wait => true, wait_seconds => 60);
~~~

6. Verify:

~~~sql
SELECT pg_is_in_recovery();
~~~

7. Check the timeline using `pg_controldata` and server logs.
8. Perform a write test on the new primary.

The goal is to observe promotion and role transition after the old primary has been isolated.

## 49. Lab: Simulating Network Partition and Fencing

In an isolated VM/network lab environment:

1. Create primary A and standby B.
2. Set up a test control plane with quorum.
3. Simulate A losing connectivity to the control plane while remaining reachable from a test client.
4. Do not promote B while A still accepts writes.
5. Fence A using the VM/network test mechanism.
6. Verify A no longer accepts connections/writes.
7. Promote B.
8. Switch the client endpoint to B.
9. Confirm only B accepts writes.

This lab demonstrates why a network partition and process health are insufficient to conclude the old primary is dead.

## 50. Lab: Asynchronous Replication and RPO

In the lab:

1. Configure asynchronous streaming replication.
2. Generate a write workload.
3. Observe primary/standby LSNs.
4. Stop the standby or throttle the network.
5. Generate additional transactions on the primary.
6. Stop/fence the primary.
7. Promote the standby.
8. Compare previously committed data with data on the standby.

The result shows that the standby may be missing commits near the time of failure.

## 51. Lab: Synchronous Replication

In a separate lab:

1. Configure a synchronous standby.
2. Set `synchronous_standby_names` appropriately.
3. Choose `synchronous_commit=on`.
4. Write transactions and observe commit behavior.
5. Monitor `pg_stat_replication` flush LSN.
6. Stop the standby and observe the impact on writes per policy.
7. Test `remote_apply` and compare latency.

Do not use the lab to generalize that every synchronous topology has RPO=0. Candidate selection and fencing must still be verified separately.

## 52. Lab: Planned Switchover

In a test environment:

1. Select a candidate.
2. Temporarily block application writes.
3. Wait for the candidate to replay up to the LSN boundary.
4. Cleanly stop the old primary or fence per runbook.
5. Promote the candidate.
6. Verify primary state and timeline.
7. Switch the endpoint.
8. Rewind/rebuild the old primary as a standby.
9. Verify stable replication before concluding the lab.

Record RTO and client reconnect duration.

## 53. Common Mistakes

### 53.1. Promoting a Standby Completes HA

False. Fencing, leader election, routing, and rejoining are still required.

### 53.2. An Unpingable Primary Means It Is Dead

False. It may be network-partitioned while still accepting writes from other clients.

### 53.3. Changing DNS Is Enough to Prevent Split-Brain

False. Clients may use direct IPs or existing connections; the old primary is still running.

### 53.4. pg_is_in_recovery=false Proves the Node Is the Sole Primary

False. It only describes local state; two nodes can both return `false` after split-brain.

### 53.5. Synchronous Replication Automatically Selects a Safe Candidate

False. You must select a candidate with appropriate WAL and coordinate with fencing/the manager.

### 53.6. Every Synchronous Standby Has Every Commit

False with `ANY` quorum and many synchronous configurations; you must understand per-transaction acknowledgements.

### 53.7. Promote a New Primary and Let the Old Primary Reconnect on Its Own

False. The old primary may have diverged and must be rewound/rebuilt as a standby.

### 53.8. pg_rewind Always Works

False. It has prerequisites regarding checksums/`wal_log_hints`, `full_page_writes`, shutdown state, and WAL availability.

### 53.9. Two Timelines Can Merge Automatically

False. If both primaries accepted writes, you must select an authoritative history and perform business reconciliation.

### 53.10. A Standby Is a Backup

False. A standby also receives replicated erroneous changes; separate backups and PITR are required.

## 54. Single-Writer HA Design Checklist

**Topology and replication**

1. Is there at least one suitable standby?
2. Are WAL level/slots/senders sufficient?
3. Are replication mode and RPO defined?
4. Can the standby candidate catch up?
5. Are archives/WAL backups complete?

**Control plane**

6. Does leader election use quorum/consensus?
7. Does the control plane have independent failure domains?
8. Are lease/TTL semantics clear?
9. Does a node losing quorum self-fence?
10. Is there a watchdog/STONITH or fencing mechanism?

**Promotion**

11. Is candidate selection based on WAL progress?
12. Is the old primary fenced before opening writes?
13. Is only one candidate promoted?
14. Is the promotion result verified?
15. Is the new timeline recognized?

**Routing and applications**

16. Does the write endpoint point to the right leader?
17. Are direct connections to the old primary blocked?
18. Do connection pools reconnect?
19. Do retries have idempotency?
20. Do health checks distinguish role and leader authorization?

**Rejoin and recovery**

21. Is the old primary kept isolated?
22. Is there a `pg_rewind` or rebuild procedure?
23. Are sufficient WAL/history files available?
24. Are slots and standby config recreated?
25. Have restore/failover/split-brain drills been executed?

## 55. Failover Operations Checklist

When the primary experiences an incident:

- Record timestamp and symptoms.
- Check quorum/control plane.
- Distinguish crash from network partition.
- Determine fencing method and confirm result.
- Select the standby with appropriate WAL progress.
- Promote exactly one candidate.
- Check `pg_is_in_recovery()` and timeline.
- Switch the write endpoint.
- Verify application reconnect and commit outcomes.
- Check remaining standbys.
- Rejoin the old primary via rewind/rebuild.
- Record actual RPO/RTO and incident root cause.

If fencing cannot be confirmed, keep writes closed per policy until single-writer safety is guaranteed.

## 56. Important Commands and Views

~~~sql
-- Local role of the node.
SELECT pg_is_in_recovery();

-- Promote standby once runbook confirms fencing.
SELECT pg_promote(wait => true, wait_seconds => 60);

-- Primary: standby progress.
SELECT
    application_name,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;

-- Standby: receive/replay progress.
SELECT
    pg_last_wal_receive_lsn(),
    pg_last_wal_replay_lsn(),
    pg_last_xact_replay_timestamp();

-- Standby: WAL receiver.
SELECT * FROM pg_stat_wal_receiver;

-- Replication configuration.
SHOW synchronous_standby_names;
SHOW synchronous_commit;
SHOW wal_level;
SHOW max_wal_senders;
SHOW max_replication_slots;
~~~

These commands observe or control the local PostgreSQL instance. They do not replace quorum, fencing, endpoint management, and incident policy.

## 57. Frequently Asked Questions

### Does promotion automatically shut down the old primary?

No. Promotion acts on the standby being promoted. The old primary must be fenced/stopped separately.

### Why must we fence before promoting?

To prevent the old primary from continuing to accept writes while the new primary begins accepting writes. This is a critical requirement to avoid split-brain.

### Does pg_promote check quorum?

No. It instructs the local PostgreSQL instance to end recovery. Quorum and candidate selection belong to the HA manager/control plane.

### Does pg_is_in_recovery=false mean the node is the sole leader?

No. It only indicates that the local node is not in recovery mode.

### Does synchronous replication guarantee zero data loss?

It can guarantee commit acknowledgement on a synchronous standby per policy, but safe failover also depends on candidate selection, quorum mode, fencing, and WAL state.

### How does remote_apply differ from on?

`on` waits for the synchronous standby to flush WAL; `remote_apply` waits for the transaction to be replayed/applied on the selected synchronous standby.

### Does ANY quorum mean every standby has the commit?

No. The commit is acknowledged by any subset of standbys meeting the quorum requirement. The candidate must be chosen based on actual WAL received/flushed.

### Is switching the load balancer enough for a single-writer guarantee?

No. It only changes routing; the old primary may still receive direct connections or hold old connections.

### Can pg_rewind be used for every old primary?

No. Prerequisites and WAL availability must be met. Otherwise, rebuild from a base backup.

### Can data from two primaries be merged after split-brain?

There is no general WAL merge operation. You must select an authoritative history and perform business reconciliation.

### Can an async standby lose transactions?

Yes. If the primary acknowledges a commit before the standby receives/flushes WAL and the primary is lost, the candidate may lack that transaction.

### When should switchover be used?

When you can control writes, wait for the standby to catch up, stop the old primary, and transfer roles in a planned manner.

### Should you promote when the control plane loses quorum?

Not automatically. The system must prevent a minority group from claiming leadership. Lease/fencing policy must be followed to preserve single-writer safety.

### Do backups replace standbys?

No. Standbys serve HA; backups/WAL archives serve data recovery and PITR.

## 58. Summary

Promotion is the step that transitions a standby into a new primary. To have only a single server accepting writes, an authoritative workflow is required:

1. Detect and classify the primary failure.
2. Use quorum/control plane to select exactly one candidate.
3. Fence the old primary and confirm it cannot accept writes.
4. Evaluate candidate WAL progress/RPO.
5. Promote the candidate.
6. Verify role and timeline.
7. Switch the write endpoint.
8. Verify applications reconnect and write only to the new primary.
9. Rewind/rebuild the old primary as a standby.
10. Monitor replication and inspect the entire HA topology.

Key principles to remember:

- `pg_promote()` and `pg_ctl promote` only request promotion on a single node.
- PostgreSQL streaming replication does not provide complete leader election/fencing on its own.
- Split-brain occurs when two primaries accept writes simultaneously.
- Fencing/STONITH prevents the old primary from continuing to make changes.
- Quorum helps the control plane agree on decisions; quorum alone does not fence the data plane.
- Leases are only safe if a node losing its lease self-fences or is fenced externally.
- Changing DNS/load balancers does not replace fencing.
- `pg_is_in_recovery()` only describes the local role, not proof of sole leadership.
- Synchronous replication reduces RPO per acknowledgement policy, but does not select candidates or fence the old primary on its own.
- `ANY N` quorum does not mean every standby contains every commit.
- Asynchronous failover can lose transactions already committed on the old primary.
- Promotion creates a new timeline; never automatically merge two WAL histories.
- The old primary must be kept isolated and rejoined using `pg_rewind` or a rebuild.
- Backups and WAL archiving remain essential alongside standbys.
- Failover drills must test network partitions, fencing, routing, and client reconnect.

Single-writer diagram:

~~~text
              Primary failure suspected
                         |
                         v
               Control plane / quorum
                         |
                         v
              Select one candidate
                         |
                         v
               Fence old primary
                         |
                 Fencing confirmed?
                    /       \
                  No         Yes
                  |            |
                  v            v
            Keep writes     Promote candidate
            closed / wait         |
                                  v
                         Verify new timeline
                                  |
                                  v
                         Update write endpoint
                                  |
                                  v
                         Client reconnect
                                  |
                                  v
                         Single writer active
                                  |
                                  v
                         Rejoin old primary
                         as a standby
~~~

**Conclusion:** Promotion allows PostgreSQL to continue serving when the primary changes, but single-writer safety comes from the entire orchestration workflow. The system must **elect a leader via quorum, fence the old primary, promote exactly one standby, update routing after verification, and rejoin the old node as a standby**. If you cannot prove the old primary has lost write authority, you must not open writes on a new primary.
