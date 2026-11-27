# Failover, Switchover, and Trigger Criteria in PostgreSQL

High availability (HA) keeps a PostgreSQL service running when the primary or an infrastructure component fails. In a streaming replication architecture, one or more standbys receive WAL from the primary and can be promoted to become the new primary when needed.

Two common role-transition operations are:

- **Failover**: moving service to a standby because the primary failed or is no longer safe to serve.
- **Switchover**: a planned transition of the primary role, typically for maintenance, upgrades, or shifting load to another node.

Both can end with promoting a standby, but their trigger criteria, level of control, and coordination procedures differ. A wrong promotion decision can cause data loss or create two primaries accepting writes simultaneously (split-brain).

An HA procedure must answer four questions:

1. When do we conclude the primary is truly no longer serving?
2. Which standby is eligible to become primary?
3. How do we guarantee the old primary cannot continue accepting writes?
4. After the role transition, where do applications and remaining nodes connect?

~~~mermaid
flowchart TD
    A["Primary serving"] --> B{"Event occurred?"}
    B -->|"Planned maintenance"| C["Switchover"]
    B -->|"Primary failure / unsafe"| D["Failover"]
    C --> E["Drain writes and sync standby"]
    E --> F["Fence or stop old primary"]
    D --> G["Confirm failure and quorum"]
    G --> H["Fence old primary"]
    F --> I["Promote exactly one standby"]
    H --> I
    I --> J["Verify new primary"]
    J --> K["Switch endpoints / app connections"]
    K --> L["Rejoin old node and monitor"]
~~~

This lesson belongs to the **High Availability** chapter in the **Database Engine Relational PostgreSQL** module. We will analyze trigger criteria, RPO/RTO, replication lag, synchronous/asynchronous replication, fencing, promotion, client routing, rejoining, and HA testing.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish failover, switchover, and failback.
2. Describe the roles of primary, standby, and HA manager.
3. Establish criteria to confirm primary failure.
4. Distinguish database failures, host failures, and network path failures.
5. Evaluate standby candidates based on WAL/LSN and replication state.
6. Explain the impact of synchronous and asynchronous replication on RPO.
7. Understand the relationship among RPO, RTO, and failure detection time.
8. Explain split-brain and the role of fencing.
9. Promote a standby using `pg_ctl` or `pg_promote`.
10. Verify that the new node has exited recovery and can accept writes.
11. Switch endpoints and handle application connection pools.
12. Rejoin the old primary to the topology via `pg_rewind` or a fresh base backup.
13. Execute a controlled switchover while minimizing data loss.
14. Understand quorum, witnesses, and the role of HA orchestration.
15. Monitor replication lag, WAL, timelines, and standby status.
16. Build runbooks for different failure scenarios.
17. Test failover, switchover, and failback periodically.
18. Assess risks across data, connectivity, security, and operations.

## 2. Terms to Distinguish

### Failover

Failover is moving service from a failed primary to an eligible standby. Failover is usually triggered by an unplanned incident such as:

- PostgreSQL primary process stopped.
- Server hardware or storage failure.
- Primary unable to serve write queries.
- Primary isolated from the rest of the system.
- Data center or availability zone outage.

Failover can be automatic or operator-initiated. Automation reduces RTO, but requires quorum, fencing, and strict candidate-selection criteria to avoid accidental promotion.

### Switchover

Switchover is moving the primary role to a standby while the system is still healthy and steps can be coordinated.

Common reasons:

- Hardware or OS maintenance.
- PostgreSQL upgrades or configuration changes.
- Shifting workload to another host.
- Validating standby capability.
- Migrating between infrastructure zones.

Because the old primary can still cooperate, operators can stop writes, wait for the standby to replay up to the final WAL position, stop the old primary, and then promote the standby. A well-prepared switchover can achieve an RPO of 0 for fully synchronized transactions.

### Failback

Failback is transitioning the primary role back to the original node or site after an incident has been resolved. It is also a planned role transition, not simply powering the old machine back on.

The old primary usually remains on an older timeline and may hold transactions divergent from the new primary. It must be converted back into a standby via `pg_rewind` if eligible, or rebuilt from a base backup, before considering a switchover back.

| Term | Timing | Goal | Coordination Level |
| --- | --- | --- | --- |
| Failover | After an incident | Restore service on standby | Usually urgent |
| Switchover | Planned | Safe role transition | Can drain and sync beforehand |
| Failback | After incident resolution | Return old node to topology | Requires verification and planning |

## 3. HA Architecture with Primary and Standby

A simple architecture:

~~~text
                 Application
                      |
              Stable DB endpoint
                      |
                 HA routing
                      |
             Current primary node
                 /          \
            WAL sender     Monitoring
                |
         Streaming replication
                |
          Standby node(s)
~~~

The primary accepts write transactions and generates WAL. Standbys receive WAL, write it to storage, and replay it to update database state.

Operational components typically include:

- PostgreSQL primary.
- One or more physical standbys.
- Dedicated network for replication.
- Replication slots or WAL retention policies.
- HA manager / cluster manager.
- Distributed configuration store or quorum mechanism when required by the architecture.
- Fencing mechanism.
- Load balancer, virtual IP, proxy, or service discovery.
- Monitoring, alerting, and backups/WAL archive.

### PostgreSQL Streaming Replication Alone Does Not Provide Full HA Orchestration

Streaming replication transports WAL and keeps a standby updated. It does not decide on its own that the primary is dead, does not fence the old primary, and does not automatically update endpoints for all applications.

Those capabilities must be implemented via an HA manager, infrastructure tooling, or runbooks. Popular solutions include Patroni, repmgr, `pg_auto_failover`, Pacemaker/Corosync, and cloud-managed PostgreSQL services. Each manages leadership, quorum, fencing, and routing differently and must be operated according to its design.

## 4. Incidents That Can Trigger Failover

Not every connection error means the primary has failed. Incidents must be classified before promoting.

| Incident Type | Symptoms | Assessment Direction |
| --- | --- | --- |
| PostgreSQL process crash | Port unresponsive, process stopped | Check process, logs, and restart viability |
| Host failure | Server power loss or kernel panic | Confirm via infrastructure / out-of-band monitor |
| Storage failure | I/O errors, read-only filesystem, corruption | Assess write capability and integrity |
| Network partition | Some nodes cannot reach primary | Check whether primary still serves clients; quorum/fencing needed |
| Client path failure | App cannot reach primary, yet standby still sees it | Check routing, DNS, firewall, load balancer |
| Database overload | Slow connections, query timeouts | Assess recovery potential; do not equate with dead node |
| High replication lag | Standby falls behind primary | Evaluate RPO and candidates before promoting |
| WAL/archive problem | Standby cannot receive or replay WAL | Determine if WAL exists to continue or rebuild is needed |

### Network Failures and Primary Failures Are Different

If the application network cannot reach the primary while the primary remains alive and accepts writes from other clients, promoting a standby creates split-brain. This is one of the strongest reasons to use multiple health checks and fencing.

A failed ping or a single TCP timeout is insufficient as sole evidence for failover.

## 5. Failover Trigger Criteria

A sound failover policy clearly defines:

- Which health checks must fail.
- How many consecutive checks constitute a failure.
- Which check sources must agree.
- Whether the primary can be fenced.
- Which standby is eligible for promotion.
- Acceptable data loss threshold.
- Which person or system holds decision authority.
- Conditions requiring manual operator approval.

### Criteria Groups

**1. Primary health**

- Is the PostgreSQL process running?
- Can a health-check query succeed?
- Can an appropriate probe transaction commit?
- Is the server hung due to storage or resource exhaustion?

**2. Failure confirmation**

- Do multiple independent probes confirm the failure?
- Does the HA manager hold quorum?
- Is the failure isolated to a single network path?
- Does infrastructure tooling confirm the host is down?

**3. Standby readiness**

- Is the standby in recovery and receiving WAL?
- Is the WAL receiver active?
- Does the standby have sufficient WAL to catch up?
- Are there replay or storage errors?
- Is the candidate's lag within acceptable RPO?

**4. Safety**

- Has the old primary been fenced or proven unable to accept writes?
- Is only one candidate authorized to promote?
- Does the HA manager enforce a single leader?
- Can clients be routed to the new endpoint?

### Sample Criteria

The table below is a design starting point, not default thresholds for every production system.

| Condition | Example Policy | Action |
| --- | --- | --- |
| Primary SQL health check | Consecutive failures across multiple probes | Continue failure verification |
| Host health | Infrastructure confirms node down | Evaluate standby candidates |
| Network partition | No quorum or primary not yet fenced | Do not auto-promote |
| Standby state | Candidate not in stable recovery or has WAL errors | Exclude candidate |
| Replication lag | Exceeds defined RPO | Alert, pick another candidate, or request decision |
| Fencing | Old primary isolated | Permit promotion per policy |
| Candidate quorum | Exactly one candidate selected | Execute promotion |

Never copy timeouts or retry counts blindly from another system. Measure your own environment's startup duration, failover detection, network latency, replication lag, and application reconnect times.

## 6. RPO and RTO Drive Trigger Criteria

Two core HA metrics:

- **RPO (Recovery Point Objective)**: maximum acceptable data loss, typically measured in time or transaction/WAL position.
- **RTO (Recovery Time Objective)**: maximum time allowed to restore service after an incident.

Examples:

- RPO 0: goal of zero loss for committed transactions acknowledged under the synchronous policy.
- RPO 30 seconds: acceptable to lose at most ~30 seconds of data under plan assumptions.
- RTO 2 minutes: target to restore service availability within two minutes.

RPO/RTO must be defined alongside business owners. A payment system requires stricter RPO than a reporting system whose data can be regenerated.

### Components of RTO

\[
RTO = T_{detect} + T_{decide} + T_{fence} + T_{promote} + T_{route} + T_{reconnect}
\]

This is a planning decomposition model. Steps may overlap depending on architecture, but every component should be measured during drills.

### RPO in Asynchronous Replication

With asynchronous streaming replication, the primary does not wait for standby WAL confirmation before returning commit success to the client. If the primary fails suddenly, the standby may lack WAL for recently acknowledged transactions.

Data loss depends on replication lag and the last WAL position the standby received/flushed/replayed. Turning on asynchronous streaming replication alone provides no fixed RPO guarantee.

### RPO in Synchronous Replication

With synchronous replication, commits can wait for standby WAL confirmation per `synchronous_commit` and `synchronous_standby_names`.

This can reduce or eliminate loss of acknowledged transactions, provided the right standby is promoted. With multiple standbys and quorum, not every standby necessarily holds every acknowledged commit.

RPO 0 is a commitment of configuration conditions and candidate selection, not an automatic consequence of setting one parameter.

## 7. Synchronous and Asynchronous Replication

### Asynchronous Replication

This is the common default mode for streaming replication. The primary does not wait for the standby to flush WAL before returning commit to the client.

Advantages:

- Primary is minimally impacted by standby latency.
- Transactions do not wait on a network round-trip to the standby.
- Primary can continue committing when a standby is temporarily slow or disconnected, other conditions permitting.

Trade-offs:

- Standby may lack the final transactions if the primary fails.
- Failover can lose transactions acknowledged to clients that never reached the candidate.
- Requires lag monitoring and defined acceptable RPO.

### Synchronous Replication

The primary waits for acknowledgment from one or more designated synchronous standbys, as configured.

Example:

~~~conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
synchronous_commit = on
~~~

`FIRST 1` selects the first eligible standby in the list by priority order. Quorum mode can also be used:

~~~conf
synchronous_standby_names = 'ANY 1 (standby_a, standby_b, standby_c)'
~~~

`ANY 1` requires at least one standby in the set to acknowledge under synchronous replication.

### `synchronous_commit` Has Different Levels

| Value | General Behavior |
| --- | --- |
| `off` | Does not wait for normal local WAL flush before reporting commit; most recent transactions may be lost on crash |
| `local` | Waits for local WAL flush, does not wait for standby |
| `remote_write` | Waits for standby to write WAL to OS; not equivalent to durable storage flush |
| `on` | Waits for synchronous standby to confirm WAL flush per synchronous replication settings |
| `remote_apply` | Waits for synchronous standby to replay WAL so transaction becomes visible on standby |

`remote_apply` generally adds more commit latency than `on`, but helps when applications need transactions replayed on the standby before commit returns.

### Availability Trade-off

If no synchronous standby satisfies the requirement, transaction commits may block. Synchronous replication increases data safety at the cost of write availability when standbys or networks fail.

The design must answer: does the system prioritize continuing writes or preserving durability guarantees? No single setting fits every workload.

## 8. Selecting a Standby Candidate Using WAL/LSN

Never select a candidate solely by node name, list order, or running state. Evaluate how much WAL the standby has received, flushed, and replayed.

On the primary:

~~~sql
SELECT
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS replay_lag_bytes
FROM pg_stat_replication
ORDER BY replay_lsn DESC NULLS LAST;
~~~

Fields:

- `sent_lsn`: WAL position sent to the standby.
- `write_lsn`: WAL position written by the standby.
- `flush_lsn`: WAL position flushed by the standby.
- `replay_lsn`: WAL position replayed by the standby.
- `sync_state`: synchronous/asynchronous/quorum state per config and version.

### Received, Flushed, and Replayed Are Not the Same

- Sent WAL has not necessarily arrived at the standby.
- Received WAL has not necessarily been flushed to storage.
- Flushed WAL has not necessarily been replayed into query-visible data.
- A standby with small replay lag that has not flushed the latest WAL still requires evaluation against durability goals.

For failover, the durable WAL position on the candidate is critical. For switchover, you normally wait for replay to reach the final target LSN so the new database serves up-to-date queries immediately.

### On the Standby

~~~sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_last_wal_receive_lsn() AS received_lsn,
    pg_last_wal_replay_lsn() AS replayed_lsn,
    pg_last_xact_replay_timestamp() AS last_replayed_transaction_time;
~~~

`pg_last_xact_replay_timestamp()` can look stale when workload is low or no new transactions occur; do not rely solely on this timestamp to judge standby lag. Comparing LSNs and receiver status is more accurate.

## 9. Checking the WAL Receiver on the Standby

Inspect the upstream connection:

~~~sql
SELECT
    status,
    receive_start_lsn,
    written_lsn,
    flushed_lsn,
    received_tli,
    last_msg_send_time,
    last_msg_receipt_time,
    latest_end_lsn,
    latest_end_time,
    sender_host,
    sender_port,
    slot_name
FROM pg_stat_wal_receiver;
~~~

This view contains one row when the WAL receiver is active. An empty result does not prove data directory corruption; the standby may simply be disconnected or the receiver stopped.

Combine with:

~~~sql
SELECT pg_is_in_recovery();
~~~

If `true`, the server is still in recovery/standby mode. After successful promotion, it must return `false`.

## 10. Quorum and Multiple Standbys

With multiple standbys, the HA manager must pick exactly one node to promote. Quorum helps cluster members agree on who is permitted to become leader.

Components may include:

- Primary.
- Two or more standbys.
- Distributed configuration store (DCS).
- Witness or quorum voters.
- Fencing service.
- HA manager.

### Why Is Quorum Needed?

Suppose the primary loses connectivity to standbys while still accepting writes from a subset of applications. If standbys self-promote without a mechanism enforcing a single leader, two nodes could accept writes.

Quorum prevents two groups of nodes from both believing they hold primary authority. In many designs, an odd number of voters provides a clear majority; exact layout depends on the HA manager and failure domains.

### Synchronous Quorum Is Not Automatically HA Quorum

`synchronous_standby_names = 'ANY 1 (...)'` governs how many standbys must acknowledge a commit. That is a durability/commit-acknowledgment mechanism, not a substitute for the HA manager's quorum to elect leaders and prevent split-brain.

The two quorums solve different problems.

## 11. Fencing and Split-Brain

Split-brain occurs when two nodes both act as primary and accept writes simultaneously. Their transaction histories diverge, making merging data very difficult or impossible to automate.

### What Is Fencing?

Fencing guarantees the old primary cannot continue writing or serving as primary once a standby is promoted.

Fencing methods may include:

- Power fencing / STONITH via server out-of-band management.
- Stopping the PostgreSQL service and preventing auto-restart.
- Network-isolating the old node.
- Revoking storage access in compatible shared-storage architectures.
- Using cloud APIs to stop/deallocate the instance.
- HA manager coordinating leases/leader locks alongside fencing.

Fencing must ensure the old node cannot continue accepting writes from clients or across another network partition.

### Do Not Just Update DNS

Changing DNS or load balancer endpoints does not fence the old primary. Clients may keep existing connections, some services may connect by direct IP, or another network segment may still reach the old primary.

Fencing and client routing are two separate steps.

### When the Old Primary Cannot Be Fenced

If isolation of the old primary cannot be confirmed, automatic promotion risks split-brain. The system needs an explicit policy: wait for verification, require operator intervention, or invoke a pre-designed alternate fencing/quorum mechanism.

Never skip safety checks merely to achieve a shorter RTO.

## 12. Failover: General Procedure

A safe failover procedure can be broken into these steps:

1. **Detect**: detect failing primary health checks.
2. **Confirm**: verify the failure using multiple independent signals.
3. **Quorum**: HA manager confirms the cluster holds decision authority.
4. **Fence**: prevent the old primary from accepting further writes.
5. **Select**: pick the standby with the latest data among eligible candidates.
6. **Promote**: bring exactly one standby out of recovery.
7. **Validate**: verify the new primary can accept write queries.
8. **Route**: update endpoints and let applications reconnect.
9. **Rejoin**: return the old node as a standby after resolving timelines.
10. **Observe**: verify replication, backups, WAL, and applications.

~~~mermaid
sequenceDiagram
    participant M as HA Manager
    participant P as Old Primary
    participant S as Selected Standby
    participant A as Application
    M->>P: Health checks fail
    M->>M: Verify quorum and select candidate
    M->>P: Fence old primary
    M->>S: Promote
    S-->>M: Confirm new primary
    M->>A: Switch endpoint
    A->>S: Reconnect and resume workload
    M->>P: Rebuild or rewind into standby
~~~

Not every step can be automated in every architecture. Runbooks must state who executes each step, which commands are used, and what conditions permit advancing.

## 13. Promoting a Standby with `pg_ctl`

On the selected standby, you can run:

~~~bash
pg_ctl promote -D /path/to/data_directory
~~~

In modern PostgreSQL versions, you can use the SQL function:

~~~sql
SELECT pg_promote(true, 60);
~~~

The two arguments in this example instruct PostgreSQL to wait up to 60 seconds for promotion to complete and return a boolean result. Check the exact signature for your version.

Promotion ends recovery and turns the node into a new primary, starting a new timeline. Promotion does not fence the old primary and does not redirect applications to the new node.

### Verifying Promotion

~~~sql
SELECT pg_is_in_recovery();
~~~

A result of `false` indicates the server is no longer in recovery mode.

You can check the timeline and WAL position using version-appropriate functions/views and verify that the server accepts write transactions.

Never run promote commands on multiple standbys simultaneously. The HA manager must lock candidate selection so only one node promotes per failover event.

## 14. Verifying the New Primary After Promotion

After promotion:

- `pg_is_in_recovery()` must return `false`.
- The server must accept SQL connections.
- A write probe transaction can commit in an appropriate schema.
- A new timeline is created.
- WAL senders and replication configuration match remaining standbys.
- Monitoring recognizes the new leader.
- Backups and WAL archiving continue working.

Check:

~~~sql
SELECT
    pg_is_in_recovery() AS in_recovery,
    pg_current_wal_lsn() AS current_wal_lsn;
~~~

A probe write transaction should target a dedicated health-check table/object or use an appropriate read check. Avoid polluting business tables with dummy rows just to verify writability.

## 15. Switching Applications to the New Primary

After promotion, open connections to the old primary will fail. Applications must reconnect to the new endpoint.

Common routing approaches:

- Virtual IP moved to the new node.
- Load balancer backend updated.
- TCP proxy switches primary target.
- DNS record updated.
- Service discovery updates leader address.
- HA-aware driver or middleware locates the primary.

### Why DNS Alone May Be Insufficient

- DNS caches can retain the old address.
- Connection pools keep stale TCP sessions open.
- Applications may cache hostnames or IPs.
- Some clients retry against the old endpoint.
- Other services may connect directly via node IP.

Verify TTLs, connection pool lifecycles, and retry logic. A stable endpoint reduces application coupling to specific nodes.

### Safe Retries

After failover, an application may not know whether its last transaction committed if the connection dropped while the commit response was in flight. For non-idempotent actions, blind retries create duplicate transactions.

Application design should use idempotency keys, unique request identifiers, or transaction outcome verification before retrying critical operations.

## 16. Failover and In-Flight Transactions

When the primary crashes or is fenced:

- Uncommitted transactions are rolled back.
- Committed transactions flushed to the candidate survive.
- Transactions committed on the primary that did not reach an async standby may be lost.
- Clients may see timeouts even though a transaction actually committed.
- Connection pools may remain in an error state until reset/reconnected.

Therefore, failover is not just switching an IP. Applications must handle connection drops, transaction retries, and ambiguous commit outcomes.

For financial transactions or order creation, idempotency is an essential part of HA design.

## 17. When the Old Primary Returns

After failover, the old primary may restart still holding the old timeline. Never allow it to accept writes or reconnect to applications as primary.

Required actions:

1. Keep the old node isolated from client writes.
2. Inspect its timeline and data state.
3. Treat the new node as the source of truth.
4. Evaluate whether `pg_rewind` can be used or a fresh base backup is needed.
5. Configure the old node as a standby following the new primary.
6. Start streaming and verify catch-up.
7. Reintroduce the node into the topology only after checks pass.

Never start the old node as primary simply because the PostgreSQL process boots cleanly. It may contain a transaction branch no longer part of current cluster history.

## 18. Rejoining with `pg_rewind`

`pg_rewind` can resynchronize a diverged data directory back onto the timeline of a source cluster by copying only changed blocks rather than the entire cluster.

Use when:

- The old node was previously primary and diverged.
- The new source is running and holds required WAL/history.
- Both clusters share a compatible common ancestor history.
- Technical preconditions for `pg_rewind` are met.

### Crucial Preconditions

The target must have had data checksums enabled at `initdb` or `wal_log_hints=on` during the relevant period; `full_page_writes` must be enabled. The target must be cleanly shut down before running `pg_rewind`. Source and target must match major version and share compatible WAL/timeline history.

Check `pg_rewind` documentation for your exact version before use; if required WAL is missing or preconditions are unmet, take a fresh base backup.

### Example

Stop the old node, then run on that node's host:

~~~bash
pg_rewind \
  --target-pgdata=/var/lib/postgresql/data \
  --source-server="host=new-primary.example.net port=5432 user=rewind_user dbname=postgres" \
  --progress \
  --write-recovery-conf
~~~

This example assumes appropriate user permissions and securely prepared config/credential files. `--write-recovery-conf` writes the necessary configuration so the target restarts as a standby as supported by your version.

After rewinding, inspect `primary_conninfo`, slots, TLS, `standby.signal`, and other standby settings before starting. Never expose plaintext passwords in command history; use a service file or protected credential mechanism.

### When Is a Fresh Base Backup Needed?

- `pg_rewind` preconditions are not met.
- Required WAL has been deleted or recycled.
- The data directory is damaged or untrusted.
- Major version or timeline mismatch.
- Rewind fails and target consistency cannot be proven.

Rebuilding a standby with `pg_basebackup` from the current primary is often cleaner when time, network, and storage permit.

## 19. Switchover: Planned Procedure

A switchover minimizes data loss because the old primary remains operational to coordinate.

### Step 1: Choose a Standby

Verify the candidate:

- Actively streaming.
- Zero replay errors.
- Adequate disk and WAL.
- Configuration suitable for primary duty.
- No abnormal replication conflicts.
- Capable of accepting writes after promotion.

### Step 2: Stop or Drain Writes

Put the application into maintenance or read-only mode per design. Stop producers, background workers, and other write jobs. Wait for active transactions to finish.

Do not stop only web traffic; identify all writers including batch jobs, ETL, schedulers, and internal services.

### Step 3: Record Target WAL on Old Primary

On the primary:

~~~sql
SELECT pg_current_wal_flush_lsn();
~~~

Record the final LSN after writers have stopped and required transactions have completed.

### Step 4: Wait for Standby to Replay to Target

On the standby:

~~~sql
SELECT pg_last_wal_replay_lsn();
~~~

Wait until the replay LSN equals or exceeds the recorded target LSN. Compare LSNs using PostgreSQL functions or orchestration tools, not lexicographical string comparison.

### Step 5: Stop/Fence Old Primary

Perform a controlled PostgreSQL shutdown or fence the old node so it cannot accept writes. During switchover, a fast shutdown after draining writers works well, followed by verifying the standby received/replayed the final WAL.

### Step 6: Promote Standby

~~~sql
SELECT pg_promote(true, 60);
~~~

Or use `pg_ctl promote` depending on your environment.

### Step 7: Verify and Switch Endpoints

Verify `pg_is_in_recovery()` returns `false`, test a write query, update routing, and re-enable application writes.

### Step 8: Rejoin Old Primary

Convert the old node into a standby via `pg_rewind` or a fresh base backup. Verify streaming and replication lag before ending the maintenance window.

## 20. Does Switchover Guarantee Zero Data Loss?

RPO 0 for committed transactions is achievable if:

- All writers stopped and necessary transactions finished.
- Final LSN on the primary was recorded.
- Standby replayed up to or past that LSN.
- No stray writer generated more WAL afterward.
- Old primary was stopped/fenced before the standby accepted writes.
- No hidden storage errors or changes outside the replication path exist.

Waiting merely until replication lag displays 0 without draining writers and locking a final barrier still allows the primary to generate new WAL right after the check. Switchover therefore requires an explicit barrier between the final write and promotion.

## 21. Failback After Repairing the Old Primary

Failback is simply another switchover. Before switching back:

1. Confirm the old node rejoined as a standby.
2. Confirm stable streaming and replay.
3. Wait for lag to drop within target limits.
4. Assess capacity and health of both nodes.
5. Drain writes.
6. Wait for the old standby to replay to the target LSN.
7. Stop/fence the current primary.
8. Promote the chosen node.
9. Switch endpoints.
10. Rejoin the remaining node.

Do not fail back the moment the old hardware is repaired. The new primary may be running stably while the old node still needs time to catch up or rebuild.

## 22. Role of the HA Manager

An HA manager coordinates decisions and node state. Common capabilities needed:

- Health checks.
- Leader election.
- Quorum/DCS.
- Fencing integration.
- Candidate selection.
- Promotion.
- Replication configuration.
- Service endpoint updates.
- Rejoin/rebuild.
- Monitoring and event logs.

Tools like Patroni, repmgr, `pg_auto_failover`, or Pacemaker vary in deployment models and automation depth. Never install a tool and skip testing DCS, fencing, DNS/VIP, slot management, and network partition behavior.

### HA Manager Does Not Replace Backups

Replication propagates accidental `DROP TABLE` or bad `UPDATE` statements to standbys. A standby is not an independent historical backup. Maintain base backups, WAL archives, retention, and restore tests separately.

## 23. Network Partitions and Promotion Decisions

A network partition is hazardous because the primary may remain alive while part of the cluster cannot see it.

Example:

- Application subnet still reaches the primary.
- Standby subnet cannot reach the primary.
- HA manager loses contact with some voters.
- One group of nodes thinks the primary is dead; another still sees it.

If a standby promotes while the primary continues accepting writes, split-brain occurs.

### Safety Policies

- Use quorum/leader leases per the HA manager.
- Use fencing independent of the failed network path.
- Never rely on a single ping or single monitor.
- Restrict promotion authority to one control plane.
- Ensure endpoints cannot point to two primaries simultaneously.
- Maintain manual overrides and auditing for anomalous events.

In systems lacking reliable fencing, automatic failover can be more dangerous than waiting for operator verification.

## 24. Replication Slots and WAL After Failover

The newly promoted primary may need to serve remaining standbys. Check:

- `max_wal_senders`.
- `max_replication_slots`.
- Physical replication slots.
- Logical replication slots.
- WAL archive.
- `wal_keep_size`.
- `max_slot_wal_keep_size`.
- Standby `primary_slot_name`.
- Slot synchronization/failover support for your PostgreSQL version and HA manager.

Some configurations synchronize or fail over slots depending on version; never assume all slots automatically appear on the new primary. Missing slots can stall consumers or force recreating/reseeding them.

### WAL Retention

If a standby stays disconnected too long while a slot retains WAL, disk space can fill up. Without a slot or if WAL is recycled before the standby returns, the standby may require a full rebuild from base backup.

Failover runbooks must check WAL availability for every consumer, not just primary health.

## 25. Timelines After Promotion

When a standby is promoted, PostgreSQL starts a new timeline. Timelines distinguish divergent WAL history branches.

After failover:

- The new primary writes WAL on the new timeline.
- The old node may have written WAL on the previous timeline.
- Two WAL branches cannot simply be concatenated as one continuous history.
- Rejoining requires rewinding or taking a base backup on the new timeline.
- Archives must preserve timeline history files for recovery and analysis.

Ensure WAL archives include timeline history files and restore procedures can locate the required WAL.

## 26. Backups and PITR After Failover

After promotion:

- Confirm WAL archiving works on the new primary.
- Verify backup schedules.
- Track which backup chain belongs to the current timeline.
- Record the failover timestamp and new timeline.
- Inspect replication slots and archive destination.
- Run a fresh base backup per policy.

Do not delete old backups immediately after failover completes. Backups and WAL from the old timeline may still be needed for investigation or pre-incident recovery points.

If using PITR, verify recovery targets against timeline and WAL history. Logical/physical replication never replaces independent recoverable backups.

## 27. Failover with Synchronous Replication: Picking the Right Node

When synchronous replication is configured, candidates must be evaluated against the standbys that actually acknowledged commits.

Example:

~~~conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
~~~

In `FIRST` mode, one standby may be synchronous while the other is asynchronous. Promoting the lagging standby can lose transactions acknowledged by the synchronous standby.

With quorum:

~~~conf
synchronous_standby_names = 'ANY 2 (standby_a, standby_b, standby_c)'
~~~

Each commit requires two standbys in the set to acknowledge. Not all three nodes necessarily hold every acknowledged transaction. Candidate selection must check actual durable LSN and quorum semantics, not merely similar `sync_state` labels.

For RPO 0 requirements, you must prove the chosen candidate holds every commit acknowledged under the synchronous commit policy. If unprovable, decide based on acceptable RPO and obtain approval as required.

## 28. Failover with Asynchronous Replication: Estimating Potential Data Loss

On the primary, you can monitor:

~~~sql
SELECT
    application_name,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS replay_lag_bytes
FROM pg_stat_replication;
~~~

If the primary is completely lost, this view is no longer queryable on the primary. Use recent monitoring metrics, standby receive/replay positions, and the WAL archive to estimate loss.

### Do Not Convert Byte Lag Directly into Time Lost

One byte of WAL does not map to a fixed duration. Workloads generate WAL at widely varying rates over time. To estimate time-based RPO, combine WAL generation rates with historical replication lag—while explicitly noting it remains an estimate.

The candidate with the highest replay LSN is usually a sensible starting point, provided you also check flushed WAL, storage errors, and shared timeline/ancestor history.

## 29. Endpoint Switching and Connection Pools

A sound HA architecture uses a stable endpoint:

- DNS alias.
- VIP.
- Load balancer.
- TCP proxy.
- Service discovery record.
- Role-aware connection routing layer.

Applications must:

- Reconnect when connections reset.
- Evict pooled connections pointing to the old node.
- Retry with backoff and jitter.
- Handle ambiguous transaction outcomes.
- Never route writes to read-only standbys.
- Verify the new primary before opening traffic.

If read replicas exist, separate read and write routing. After failover, old standbys may not yet be reconfigured to follow the new primary; avoid querying them until topology is verified.

## 30. Health Checks and Readiness Criteria

Health checks can span multiple layers:

| Layer | Check | Meaning |
| --- | --- | --- |
| Process | PostgreSQL process exists | Server process is running |
| Port | TCP connect succeeds | Listener is responding |
| SQL | Health-check query succeeds | Database processes queries |
| Readiness | Role and recovery state check | Node holds the right role for traffic |
| Write readiness | Probe transaction commits | Primary can serve writes |
| Replication | WAL receiver/sender and lag | Standby is keeping up |
| Application | End-to-end request | Service actually works |

A running process does not mean the database is healthy. A successful SQL query on a standby does not mean it can accept writes.

### Health Checks Must Be Role-Aware

Write applications need endpoints pointing strictly to the primary. Health checks can query `pg_is_in_recovery()` to distinguish primary from standby, combined with HA manager state and endpoint routing.

Never allow a load balancer to round-robin write traffic across all PostgreSQL nodes.

## 31. Essential Monitoring for Failover

Key metrics:

- Primary and standby roles.
- PostgreSQL process/SQL health.
- `pg_stat_replication` state.
- `pg_stat_wal_receiver` status.
- Sent/write/flush/replay LSN.
- Replication lag in bytes and time.
- WAL generation rate.
- Replication slot active/inactive state.
- Disk free space and WAL directory size.
- DCS/quorum/leader lease status.
- Fencing status.
- Client connection errors.
- Application transaction errors.
- Failover duration and recovery time.
- Timeline ID and archive health.

### On the Primary

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
FROM pg_stat_replication;
~~~

### On the Standby

~~~sql
SELECT
    status,
    sender_host,
    sender_port,
    written_lsn,
    flushed_lsn,
    latest_end_lsn,
    latest_end_time
FROM pg_stat_wal_receiver;
~~~

### Role Check

~~~sql
SELECT pg_is_in_recovery();
~~~

Adapt queries to your version and monitoring permissions. Record both current values and trends, as a single sample is insufficient to trigger failover.

## 32. Automated Failover Runbook

An automated runbook should define explicit states:

1. HEALTHY: primary serving, standby streaming.
2. SUSPECT: one or more health checks failing.
3. CONFIRMED_FAILURE: sufficient signals confirm primary is down.
4. FENCING: preventing old primary from accepting writes.
5. CANDIDATE_SELECTED: one standby chosen.
6. PROMOTING: promotion executing.
7. PRIMARY_VALIDATED: new node ready to accept writes.
8. ROUTING_UPDATED: client endpoint switched cleanly.
9. REJOINING: old node rewound/rebuilt.
10. STABLE: topology stable and monitoring green.

Every state needs timeouts, retry policies, logging, and stop conditions. If fencing fails, never proceed to promotion as though fencing succeeded.

## 33. Manual Switchover Runbook

A practical checklist:

**Before switching**

- Confirm maintenance window.
- Notify applications and stop writer jobs.
- Verify primary/standby health.
- Check lag and WAL archive.
- Verify latest backup.
- Confirm routing and rollback plan.
- Verify candidate has adequate resources.

**During switching**

- Drain writes.
- Record target LSN.
- Wait for standby to replay target.
- Stop/fence old primary.
- Promote standby.
- Verify `pg_is_in_recovery()` = `false`.
- Switch endpoint.
- Resume writes and monitor errors.

**After switching**

- Rejoin old node.
- Verify replication slots.
- Verify backups/WAL archiving.
- Verify application health.
- Record step durations and actual RTO.

## 34. Specific Scenarios and Decisions

### Primary Process Crashes, Standby Healthy

- Confirm process/server is truly down.
- Check candidates and replication lag.
- Ensure fence/restart policies keep the old node from accepting writes.
- Promote candidate.
- Switch endpoint and monitor.

### Primary Loses Network While Host Remains Alive

- Determine if this is a network partition.
- Check alternate paths to primary.
- Rely on quorum and fencing.
- Do not promote solely because one client subnet lost access.

### Large Standby Lag

- Compare standbys.
- Inspect WAL receive/flush/replay.
- Assess actual RPO.
- If no candidate meets RPO, make a deliberate decision and document potential data loss.

### Primary Storage Corruption

- Stop writing to untrusted storage.
- Fence primary.
- Pick a standby with clean data.
- Promote and verify.
- Preserve the damaged instance for investigation per policy; do not discard evidence prematurely.

### No Standby Available

- Restore primary from backup/WAL per recovery plan.
- No promotion target exists.
- RTO depends on restore/PITR duration.
- After recovery, rebuild standbys and validate HA topology.

### Synchronous Standby Unresponsive

- Commits may block depending on `synchronous_commit`.
- Check `synchronous_standby_names` and node state.
- Alter durability policy only with explicit approval.
- Never silently relax sync policy during an incident without assessing RPO.

## 35. Testing Failover and Switchover

HA is unproven until drilled.

Tests should cover:

- Controlled stop of PostgreSQL primary.
- Killing processes in a test environment.
- Simulating network loss between primary and standby.
- Simulating network loss between application and primary.
- Simulating standby lag.
- Simulating inactive replication slots.
- Simulating WAL disk pressure.
- Testing fencing.
- Testing promotion and endpoint switching.
- Testing client reconnection.
- Testing transaction retry/idempotency.
- Testing rejoin via `pg_rewind`.
- Testing rebuild via `pg_basebackup`.
- Testing switchback once topology stabilizes.

Never perform fault injection in production without an approved change plan, scope, and rollback procedure.

### Measuring Actual Timing

Record:

- Incident start time.
- Alert firing time.
- Failure confirmation time.
- Fencing completion time.
- Promotion completion time.
- Endpoint switch time.
- Time when applications resume normal writes.
- Data/transactions lost or requiring reconciliation.

Use these measurements to calibrate RTO/RPO and alert thresholds.

## 36. Protecting Backups and Change Control

Failover is not a backup. Erroneous operations replicated to a standby will still persist there.

Maintain:

- Physical base backups.
- WAL archives and PITR.
- Logical backups for selective use cases.
- Backups of PostgreSQL and HA manager configs.
- Inventory of certificates/secrets.
- Runbooks and change history.
- Periodic restore tests.

Any change to `synchronous_standby_names`, replication slots, HBA, TLS, routing, or fencing policies affects HA. Place them under change management and test before production.

## 37. Common Mistakes

1. **Promoting a standby merely because applications lost connectivity to the primary**, while the primary still accepts writes elsewhere.
2. **Skipping fencing**, allowing both old and new primaries to run simultaneously.
3. **Selecting a standby by name or list order**, without comparing WAL/LSN and health.
4. **Confusing `sent_lsn` with `replay_lsn`**, misjudging ready data.
5. **Assuming asynchronous replication guarantees RPO 0**, even though the primary does not wait for standby commit confirmation.
6. **Assuming synchronous replication guarantees every standby has the latest transaction**, ignoring `FIRST`/`ANY` selection and quorum semantics.
7. **Misunderstanding `synchronous_commit`**, misinterpreting `remote_write`, `on`, and `remote_apply`.
8. **Using synchronous standbys without evaluating availability trade-offs**, causing commits to block when standbys/networks fail.
9. **Updating DNS without resetting connection pools**, leaving applications pinned to sessions on the old node.
10. **Ignoring ambiguous transaction outcomes**, causing retries to create duplicate transactions.
11. **Restarting the old primary as primary**, creating divergent timelines.
12. **Assuming `pg_rewind` always works**, overlooking missing WAL or unmet preconditions.
13. **Not checking replication slots after promotion**, preventing other standbys from continuing.
14. **Ignoring WAL archive/timeline history**, breaking PITR and rejoining.
15. **Confusing synchronous quorum with HA leader-election quorum**, failing to prevent split-brain.
16. **Triggering automatic failover from a single probe**, causing false failovers on network jitter.
17. **Not verifying endpoint write readiness**, sending writes to a read-only standby.
18. **Never drilling failover**, leaving actual RTO and missing manual steps unknown.
19. **Deleting old backups immediately after promotion**, losing investigative or pre-incident recovery capability.
20. **Failing back too early**, before the old node has rejoined and caught up.
21. **Using replication instead of backups**, leaving no independent recovery point.
22. **Not monitoring WAL disk/slot retention**, filling the new primary's disk after role transition.

## 38. Practice Exercises with Answers

### Exercise 1. What is failover?

**Answer:** Moving service to a standby because the primary suffered an incident or is no longer safe to serve.

### Exercise 2. What is switchover?

**Answer:** A planned primary/standby role transition when both can coordinate and synchronize beforehand.

### Exercise 3. What is failback?

**Answer:** Transitioning the role back to the original node/site after it has been safely rejoined and verified.

### Exercise 4. What does RPO measure?

**Answer:** The acceptable amount of data loss during an incident.

### Exercise 5. What does RTO measure?

**Answer:** The target time to restore service availability.

### Exercise 6. Why is a failed ping insufficient to trigger failover?

**Answer:** Only one network path may be broken while the primary continues accepting writes from other clients.

### Exercise 7. What is the purpose of fencing?

**Answer:** Preventing the old primary from continuing to accept writes after a new standby is promoted.

### Exercise 8. What is split-brain?

**Answer:** Two nodes simultaneously believing they are primary and accepting writes, creating divergent data histories.

### Exercise 9. Which SQL function promotes a standby?

~~~sql
SELECT pg_promote(true, 60);
~~~

**Answer:** `pg_promote` instructs the standby to exit recovery and become primary; the parameters wait up to 60 seconds.

### Exercise 10. How to check if a node is still in recovery?

~~~sql
SELECT pg_is_in_recovery();
~~~

**Answer:** `true` means in recovery/standby; `false` means no longer in recovery.

### Exercise 11. Does asynchronous replication guarantee zero loss of the last transaction?

**Answer:** No. The primary can acknowledge commit before the standby receives or flushes the WAL.

### Exercise 12. What does `synchronous_commit=on` wait for?

**Answer:** Local WAL flush and flush confirmation from the synchronous standby per configured policy.

### Exercise 13. How does `remote_apply` differ from `on`?

**Answer:** `remote_apply` waits for the standby to replay the transaction; `on` waits for the standby to flush WAL.

### Exercise 14. What does `ANY 1` in `synchronous_standby_names` mean?

**Answer:** At least one standby in the quorum set must acknowledge as configured.

### Exercise 15. Does synchronous quorum replace HA manager quorum?

**Answer:** No. One verifies commit durability; the other governs leader election and split-brain prevention.

### Exercise 16. Which view on the primary shows standby LSNs?

**Answer:** `pg_stat_replication`.

### Exercise 17. Which view on the standby shows the WAL receiver?

**Answer:** `pg_stat_wal_receiver`.

### Exercise 18. Why not pick a candidate solely by replay lag timestamp?

**Answer:** Timestamps can look stale during idle workloads; evaluate LSN, flush state, timeline, and health.

### Exercise 19. After promotion, can the old primary restart as primary?

**Answer:** No. It must be fenced and rejoined onto the new timeline using `pg_rewind` or a fresh base backup.

### Exercise 20. What is `pg_rewind` used for?

**Answer:** Resynchronizing a diverged target with a source by copying modified blocks, when preconditions are met.

### Exercise 21. When is a fresh base backup needed instead of `pg_rewind`?

**Answer:** When required WAL is missing, preconditions fail, timelines/versions mismatch, or the data directory is untrusted.

### Exercise 22. Why must switchover drain writes?

**Answer:** To establish a final barrier, preventing the primary from generating extra WAL after verifying standby catch-up.

### Exercise 23. Why is updating DNS alone insufficient?

**Answer:** DNS caches and connection pools can retain stale addresses/sessions; explicit routing and reconnection handling are needed.

### Exercise 24. Does a client timeout during COMMIT mean the transaction rolled back?

**Answer:** Not necessarily. Commit may have succeeded while the response was lost; applications need idempotency or outcome verification.

### Exercise 25. Do logical replication slots automatically follow the new primary?

**Answer:** Never assume so. Verify slot failover/synchronization support for your PostgreSQL version and HA manager.

### Exercise 26. Is a single standby enough for HA?

**Answer:** It provides one candidate, subject to failure domains, quorum, fencing, and readiness; however, zero redundancy remains if that standby also fails.

### Exercise 27. Why must failover check the WAL archive?

**Answer:** To ensure continued standby/recovery viability and PITR on the new timeline.

### Exercise 28. When should automatic promotion be delayed?

**Answer:** When failure is unconfirmed, quorum is absent, the old primary cannot be fenced, or no candidate satisfies safety policies.

### Exercise 29. What must a safe switchover verify before promotion?

**Answer:** Writers drained, target LSN recorded, standby replayed to target, and old primary stopped/fenced.

### Exercise 30. When is failover considered complete?

**Answer:** The new primary is verified writable, endpoints and applications have reconnected, monitoring/backups/replication are restored, and a rejoin plan exists for the old node.

## 39. Failover Decision Checklist

- [ ] Primary failure confirmed by multiple health checks.
- [ ] Primary failure distinguished from client network path failure.
- [ ] HA manager holds quorum or clear leadership decision authority.
- [ ] Old primary fenced.
- [ ] Exactly one standby candidate selected.
- [ ] Candidate healthy and holding sufficient WAL.
- [ ] Received/write/flush/replay LSNs inspected.
- [ ] RPO evaluated against actual sync mode and candidate.
- [ ] Explicit decision made if target RPO cannot be met.
- [ ] Exactly one standby promoted.
- [ ] `pg_is_in_recovery()` = `false` verified.
- [ ] New primary verified able to accept writes.
- [ ] Endpoints switched and connection pools reset.
- [ ] Application handles retries/idempotency.
- [ ] WAL archiving and replication slots verified.
- [ ] Rejoin plan scheduled for old node.
- [ ] Monitoring and alerts verified post-transition.
- [ ] Timeline, timestamps, and potential data loss recorded.

## 40. Switchover Checklist

- [ ] Maintenance window and rollback plan approved.
- [ ] Healthy standby with sufficient capacity selected.
- [ ] Replication lag and WAL availability checked.
- [ ] All writers and background jobs stopped/drained.
- [ ] In-flight transactions completed.
- [ ] Final primary flush LSN recorded.
- [ ] Standby replayed up to target LSN.
- [ ] Old primary stopped or fenced.
- [ ] Standby promoted.
- [ ] Role and write readiness verified.
- [ ] Endpoints switched.
- [ ] Writers resumed and application monitored.
- [ ] Old primary rejoined via rewind/rebuild.
- [ ] Backups, slots, WAL, and replication verified.
- [ ] Actual RTO and drill results documented.

## 41. Official PostgreSQL Documentation

Consult documentation matching your deployed major version:

- [Warm Standby and Streaming Replication](https://www.postgresql.org/docs/current/warm-standby.html) — physical standbys, streaming, and promotion.
- [Failover](https://www.postgresql.org/docs/current/warm-standby-failover.html) — promoting a standby and failover considerations.
- [Synchronous Replication](https://www.postgresql.org/docs/current/warm-standby.html#SYNCHRONOUS-REPLICATION) — `synchronous_standby_names` and commit behavior.
- [pg_ctl](https://www.postgresql.org/docs/current/app-pg-ctl.html) — promote, stop, and server control.
- [pg_promote](https://www.postgresql.org/docs/current/functions-admin.html) — SQL function controlling promotion.
- [pg_rewind](https://www.postgresql.org/docs/current/app-pgrewind.html) — bringing a diverged node back onto the current timeline.
- [pg_basebackup](https://www.postgresql.org/docs/current/app-pgbasebackup.html) — creating a standby from a physical base backup.
- [Replication Configuration](https://www.postgresql.org/docs/current/runtime-config-replication.html) — WAL senders, slots, and synchronous replication settings.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — `pg_stat_replication` and `pg_stat_wal_receiver`.
- [Continuous Archiving and PITR](https://www.postgresql.org/docs/current/continuous-archiving.html) — base backups, WAL archives, and timeline recovery.
- [Replication Slots](https://www.postgresql.org/docs/current/warm-standby.html#STREAMING-REPLICATION-SLOTS) — WAL retention and slot lifecycles.

`/current/` URLs point to current PostgreSQL documentation. Promotion, `pg_rewind`, synchronous replication, slot failover, and monitoring details can vary by major version; verify documentation for your exact server/client and HA manager versions before applying.

## 42. Summary

**Failover restores service after an incident; switchover performs a planned role transition; failback returns the original node to the topology after a safe rejoin.** All three require control over data, leader identity, and client routing.

1. **Never trigger failover from a single connectivity loss signal.** Confirm primary failure with multiple checks and quorum.
2. **Fencing is a critical safety requirement.** Never allow the old primary to keep accepting writes after promotion.
3. **Choose candidates by WAL/LSN and health**, not merely node name or lag timestamp.
4. **Asynchronous replication can lose transactions not yet sent to the standby.** RPO depends on lag at failure time.
5. **Synchronous replication reduces risk of losing acknowledged commits**, but requires picking the right sync/quorum candidate and accepting availability trade-offs.
6. **`pg_promote` or `pg_ctl promote` turns a standby into primary**, but neither switches endpoints nor fences the old node.
7. **Applications must handle reconnection and ambiguous transaction outcomes**, especially for non-idempotent operations.
8. **The old primary must rejoin on the new timeline** via `pg_rewind` if eligible or a fresh base backup.
9. **Switchover requires draining writes and waiting for the standby to replay the target LSN** before promotion.
10. **An HA manager, quorum, fencing, and routing complement streaming replication** to form a complete HA system.
11. **Backups and PITR remain essential.** A standby never replaces an independent backup.
12. **Drill and measure actual RPO/RTO** so runbooks work reliably during real incidents.

An HA system is trustworthy only when operations teams know precisely when promotion is permitted, how to stop the old primary from continuing to accept writes, and how to bring the entire application back to stable service.
