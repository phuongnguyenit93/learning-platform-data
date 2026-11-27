# High Availability

## Switchover, Failover, Fencing, and Verifying the Writable Server

In a highly available (HA) MySQL system, transferring the primary role is a change that directly affects data integrity and service availability. **Switchover** is a planned role transfer while the current primary is still healthy; **failover** is an unplanned transfer after the primary suffers an outage. Both must guarantee that only one server is permitted to accept writes at any given time.

The decisive step of a safe transition is fencing: isolating or disabling the old primary's ability to accept writes before enabling writes on the new primary. If you merely see the old server stop responding from one network path and open writes on another server, the system can enter split-brain: two independent primaries accepting transactions concurrently. Once connectivity returns, reconciling the data can be extremely difficult or impossible to automate.

In the `DATABASE_MYSQL` module, you learn to master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, and concurrency control. You also practice reading execution plans, query tuning, privilege management, backups, and troubleshooting relational database operations. These skills form the foundation for HA transitions: you must understand in-flight transactions, replication lag, GTIDs, backups, write privileges, and how applications connect before switching server roles.

This lesson covers switchover, failover, fencing, and single-writer verification procedures for primary/replica topologies. SQL examples use `SOURCE`/`REPLICA` syntax from MySQL 8.0.22 and newer; MySQL 5.7 and earlier use `MASTER`/`SLAVE`. Verify your version, topology, and orchestration tooling before executing in production.

### 1. Objectives and terminology

An HA transition workflow must satisfy four goals:

1. **No dual writers:** at all times only one primary is permitted to accept application writes.
2. **Bounded data loss:** pick the replica closest to the primary and know explicitly which transactions could be lost.
3. **Accurate redirection:** proxies, routers, VIPs, DNS, and connection pools must direct applications to the new primary.
4. **Verifiability:** server states, GTIDs, write privileges, replication streams, and application operations are all verified post-transition.

| Term | Meaning |
|---|---|
| Primary / source | Server currently accepting writes and shipping binary logs to replicas |
| Replica | Server receiving and applying changes from the source; typically read-only |
| Switchover | Planned primary change, usually allowing transaction synchronization before role transfer |
| Failover | Primary change when the current primary is unavailable or deemed unsafe |
| Fencing | Disabling write capability or resource access on the old primary to prevent it from acting as a writer |
| Split-brain | Two or more nodes both believing they are primary and accepting writes simultaneously |
| RPO | Maximum tolerable data loss, measured in time or transactions |
| RTO | Target duration to restore service |

Asynchronous replication does not automatically guarantee zero data loss. A replica may not have received or applied the newest transactions when the primary fails. A planned switchover can normally achieve RPO = 0 if writes are paused, synchronization completes, and checks pass. Unplanned failover must evaluate GTIDs and remaining binlogs to identify unprotected transactions.

### 2. Preparing the topology before transitions are needed

You cannot improvise a safe HA procedure in the middle of an incident without a baseline. Before going live, document and verify:

- Primary, replicas, server UUIDs, server IDs, channels, and replication sources for every node.
- Replication model: asynchronous, semi-synchronous, or Group Replication/InnoDB Cluster.
- Write policy: applications write through a single endpoint; replicas enforce `read_only` and `super_read_only` by design.
- Routing mechanism: MySQL Router, proxy, load balancer, VIP, DNS, or orchestration platform.
- Independent fencing mechanism: stopping VMs/instances, power off, network isolation, revoking storage access, or an explicitly designed lease/quorum mechanism.
- RPO/RTO, replica selection criteria, lag thresholds, and sign-off procedures for data loss.
- Backups and binary log archives sufficient to restore or rebuild replicas.
- Admin accounts, replication users, TLS, secrets, and required permissions for role changes.

Verify server identity on each host:

```sql
SELECT
  @@hostname AS hostname,
  @@server_id AS server_id,
  @@server_uuid AS server_uuid,
  @@GLOBAL.read_only AS read_only,
  @@GLOBAL.super_read_only AS super_read_only,
  @@GLOBAL.gtid_mode AS gtid_mode,
  @@GLOBAL.gtid_executed AS gtid_executed,
  @@GLOBAL.gtid_purged AS gtid_purged;
```

Every instance must have a unique `server_id` and `server_uuid` across the topology. When cloning a data directory, follow MySQL's procedure to generate distinct identities; never let two nodes share the same identity. Save baseline output alongside your topology diagram and runbook.

### 3. Switchover: planned transition

Switchover applies when the old primary is still healthy, the application can briefly pause writes, and the target replica is healthy. The goal is transferring every committed transaction from the old primary to the target replica before enabling writes there.

Assume `db-primary` is the current source and `db-replica-1` is the replica selected to become the new primary.

#### 3.1. Pre-transition checks

On both the primary and replica, capture:

```sql
SELECT VERSION(), @@hostname, @@server_uuid,
       @@GLOBAL.gtid_executed,
       @@GLOBAL.gtid_purged,
       @@GLOBAL.read_only,
       @@GLOBAL.super_read_only;

SHOW REPLICA STATUS\G
```

Confirm both receiver and applier are running with no I/O or SQL errors, no abnormal backlog, ample disk space, and no errant local transactions on the replica. Reconcile schemas, replication filters, event scheduler jobs, and background tasks. If multiple replicas exist, clearly designate which node gets promoted and which will repoint to the new primary.

Never select a replica based solely on `Seconds_Behind_Source`. Inspect `Retrieved_Gtid_Set`, `Executed_Gtid_Set`, `gtid_executed`, and worker errors. If long transactions, parallel appliers, or filters are active, evaluate the real status of transactions.

#### 3.2. Quiesce writes and drain transactions

1. Put the application into maintenance or read-only mode at the application tier so no new write requests arrive.
2. Wait for in-flight transactions to finish or handle them per agreed timeout policy.
3. Check open transactions and write connections; confirm no batch jobs, events, or admin sessions are writing to the primary.
4. Set the old primary to read-only as an additional safeguard:

   ```sql
   SET GLOBAL super_read_only = ON;
   SET GLOBAL read_only = ON;
   ```

5. Record the final GTID set after all write sources have stopped:

   ```sql
   SELECT @@GLOBAL.gtid_executed AS final_source_gtids;
   ```

`super_read_only` and `read_only` act as MySQL-level guards, useful during switchover when the node is reachable. They do not replace independent fencing during failover: a network-partitioned node may still be running and reachable by another client, and privileged accounts can toggle variables. Control applications, accounts, proxies, and nodes together.

#### 3.3. Wait for the replica to apply all transactions

On the chosen replica, wait for the old primary's final GTID set to execute:

```sql
SELECT WAIT_FOR_EXECUTED_GTID_SET(
  'source_uuid:1-123456',
  60
) AS wait_result;
```

Replace the placeholder string with the exact GTID set recorded from the old primary. A result of `0` means the GTID set has been executed; `1` means timeout. Handle any SQL errors per the returned message. If it times out, do not promote: investigate blocked transactions, receiver/applier errors, missing binlogs, or slow workers.

After the wait succeeds, verify with `GTID_SUBSET()`:

```sql
SELECT GTID_SUBSET(
  'source_uuid:1-123456',
  @@GLOBAL.gtid_executed
) AS source_history_is_present;
```

A result of `1` confirms the source's GTID set is a subset of executed GTIDs on the replica. This verifies transaction history; you must still confirm data integrity and absence of unexpected errant transactions.

#### 3.4. Promote the replica and redirect applications

Once the old primary has stopped writes, the target replica has applied all transactions, and fencing/role-transfer policies are satisfied:

1. Stop the replication channel on the node being promoted:

   ```sql
   STOP REPLICA;
   ```

2. Confirm receiver/applier threads are stopped and record the final GTID set.
3. Enable writes on the new node:

   ```sql
   SET GLOBAL super_read_only = OFF;
   SET GLOBAL read_only = OFF;
   ```

4. Update MySQL Router/proxy/VIP or the write endpoint to point to the new primary.
5. Refresh application connection pools; verify new connections land on the expected server UUID.
6. Execute a reconcilable test write transaction, then confirm the GTID increments on the new primary and other replicas receive it.

Never let applications write before the endpoint points to the new node and the old node is locked read-only/fenced. Reconfigure remaining replicas to follow the new primary using `CHANGE REPLICATION SOURCE TO` and GTID auto-positioning per runbook. Never reset channel metadata before saving connection configuration and GTID state.

### 4. Failover: transitioning when the primary fails

Failover is harder than switchover because the old primary may be unresponsive—yet unresponsiveness does not prove it has stopped running. It might merely be network-partitioned from monitoring while still accepting writes from another client subnet. Therefore, the most critical step before promotion is verifying the old node's state and executing fencing.

#### 4.1. Distinguishing a dead primary from an unreachable primary

Gather signals from multiple independent sources:

- MySQL and OS health checks.
- VM/instance or bare-metal status from the control plane/hypervisor.
- Network reachability from multiple monitoring zones, DNS, firewalls, and load balancers.
- Application, proxy, and Router logs plus connection errors.
- Replica status, GTIDs, relay logs, and latest received binary logs.
- Quorum/lease systems if the topology uses an election mechanism.

A failed ping or a single health-check timeout is insufficient proof that the primary is down. Setting failover timeouts too aggressively can cause brief network jitter to trigger false promotions.

#### 4.2. Fencing the old primary

Fencing ensures the old primary cannot continue accepting writes, even if it recovers or keeps running inside a network partition. Depending on infrastructure, use:

| Mechanism | Example | What to verify |
|---|---|---|
| Power fencing | Power off host, stop VM, or terminate instance via control plane | Command completed and node is no longer running |
| Network fencing | Revoke security groups, apply firewall rules, or isolate VLAN | No client can reach the old node's MySQL port or write endpoint |
| Storage fencing | Revoke shared volume write access or enforce SCSI reservations/leases | Old node cannot write to shared storage resources |
| Orchestrator/quorum fencing | HA controller managing leases, quorum, and primary authority | Only one node holds write authority; expired leases are enforced at resource level |
| Database-level read-only | Set `super_read_only=ON` while node is still controllable | Defense-in-depth only; insufficient when node is partitioned and unreachable |

Fencing must be confirmed from the control plane or a mechanism independent of MySQL on the old node. If you cannot verify the old node is fenced, do not open writes on the new node. Keeping the system read-only/paused while investigating is usually far safer than creating two divergent data histories.

#### 4.3. Selecting a replica to promote

After fencing the old primary, evaluate all eligible replicas:

1. Identify nodes whose receiver/applier were healthy prior to the incident with no apply errors.
2. Collect `gtid_executed`, `gtid_purged`, `Retrieved_Gtid_Set`, and per-channel GTID sets.
3. Compare GTID sets to determine which transactions are applied versus missing.
4. Check candidates for errant GTIDs or direct local writes.
5. Cross-check the old primary's binlogs/archives if still reachable or archived externally.
6. Choose the node with the most complete, valid transaction history matching RPO; document potentially lost transactions or time window.

Never assume a replica with `Seconds_Behind_Source = 0` is the best candidate. That metric may miss unapplied transactions, stopped workers, or timing artifacts. GTIDs quantify transaction differences, though they do not prove row contents are identical.

If two candidates have differing GTID sets, use `GTID_SUBTRACT(A, B)` and `GTID_SUBTRACT(B, A)` to inspect each node's unique transactions. Investigate the origin of extra transactions before picking. Never manipulate GTID metadata to force two nodes to look identical.

#### 4.4. Promoting and recovering topology

Once fencing is confirmed and the candidate is selected:

1. Save a snapshot of the candidate's status and GTIDs.
2. Stop receiver/applier on the candidate:

   ```sql
   STOP REPLICA;
   ```

3. Verify the node has no half-applied transactions and data is consistent up to the selected GTID.
4. Set `super_read_only=OFF`, then `read_only=OFF` on the candidate per runbook.
5. Update the write endpoint, Router/proxy, and connection pools.
6. Verify applications connect to the right server UUID; run a test write and observe GTID progression.
7. Repoint remaining replicas to the new primary using GTID auto-positioning or the appropriate file/position procedure.
8. Monitor errors, replication lag, transactions, and business metrics throughout stabilization.

When the old primary returns, keep it isolated or read-only. Never automatically let it accept writes. Inspect its GTIDs and data; if the old node has divergent transactions or compatibility cannot be proven, rebuild it from a backup of the new primary and configure it as a replica. Reintroduce it to the topology only after confirming zero diverged write history.

### 5. Fencing and single-writer verification

A transition is accepted only when you prove which node holds write authority and confirm all other nodes cannot accept application writes.

#### 5.1. MySQL-layer verification

Run the following query across all nodes reachable by traffic:

```sql
SELECT
  @@hostname AS hostname,
  @@server_uuid AS server_uuid,
  @@GLOBAL.read_only AS read_only,
  @@GLOBAL.super_read_only AS super_read_only,
  @@GLOBAL.gtid_executed AS gtid_executed;
```

Expected results in a classic single-primary model:

| Role | `read_only` | `super_read_only` | Accepts app writes |
|---|---:|---:|---|
| Current primary | `0` | `0` | Yes |
| Healthy replica | `1` | `1` | No |
| Demoted old primary | `1` | `1` or stopped/fenced | No |

These values reflect desired database-layer state and do not replace infrastructure fencing checks. Also audit users able to modify global variables, admin accounts, events, scheduled jobs, and which nodes applications can reach directly.

#### 5.2. Infrastructure and application verification

- Control plane confirms the old primary is stopped or isolated per fencing policy.
- Router/proxy/load balancer routes the write endpoint to exactly one server UUID.
- DNS/VIP updates have propagated and stale connection pools are drained or expired.
- Application accounts cannot write directly to replicas or the old primary.
- Write-endpoint health checks validate server identity, not just an open TCP port.
- A test write on the new primary generates a new GTID; replicas receive and apply that GTID.
- Zero new transactions appear on the old node after the fencing timestamp.

Include an automatic write-rejection mechanism if a node loses its lease/quorum or is not confirmed as primary by orchestration. When using leases, enforce the lease where it actually blocks the old node from writing; storing a lease timestamp solely inside the application without resource-level enforcement is not enough to prevent split-brain.

### 6. Differences across HA models

The classic primary/replica procedure above does not replace membership management in Group Replication or InnoDB Cluster.

| Model | Primary selection mechanism | Transition notes |
|---|---|---|
| Asynchronous replication | Operator or orchestrator selects replica | May lose transactions not yet received/applied; must compare GTIDs and fence old source |
| Semi-synchronous replication | Still requires selecting and promoting a replica | ACK proves at least one replica received the event per config; does not prove all candidates applied it or guarantee zero data loss |
| Group Replication single-primary | Group members and group primary election | Check quorum, member states, certification, and current primary; avoid altering membership without understanding group state |
| InnoDB Cluster | Group Replication paired with MySQL Shell AdminAPI and MySQL Router | Use cluster/metadata status and AdminAPI failover procedures; verify Router and client routing post-transition |

In Group Replication, quorum is critical for keeping group consensus consistent. A minority partition must never be forced into primary unilaterally. Forcing quorum or setting `group_replication_force_members` raises split-brain risk if excluded members remain active in another partition. Use only per your exact version's Group Replication recovery procedure after verifying every member's state.

Semi-synchronous replication narrows the data-loss window in certain failure scenarios, yet does not guarantee the chosen candidate has applied the last transaction. On timeout, the system can fall back to asynchronous mode per configuration. Check the actual runtime mode and each replica's GTIDs rather than treating a "semi-sync" label as a zero-data-loss guarantee.

### 7. Common errors during HA transitions

| Symptom | Possible cause | Resolution |
|---|---|---|
| Two nodes accepting writes | Promoted before fencing old primary or routing still hits old node | Halt writes, fence old node, assess diverged histories, and run verified reconciliation/re-seed |
| Promoted node missing transactions | Replica had not applied all GTIDs or async failover left unshipped commits | Quantify missing GTIDs, inspect old primary binlogs/archives, and report actual RPO |
| `WAIT_FOR_EXECUTED_GTID_SET` times out | Applier error, missing relay logs, huge transaction, or wrong GTID set | Inspect worker status, source GTIDs, and binlogs; never promote just to bypass timeout |
| Apps still writing to old primary | Connection pools holding sockets, stale DNS/VIP, or direct connection paths | Fence old node, revoke old endpoint, flush pools, and verify server UUID in app |
| New replica has extra GTIDs | Direct writes, multiple sources, or leftover data from prior restores | Trace origin and affected data; never erase GTIDs via arbitrary metadata edits |
| Old primary cannot rejoin | Divergent transactions, stale source config, or incompatible GTIDs | Keep node read-only/fenced, reconcile history, and re-seed from new primary if needed |
| Router reports wrong primary | Stale metadata or unrefreshed health checks | Inspect cluster/metadata status, endpoints, and identity; open traffic only once routing verifies |

### 8. Switchover and failover runbooks

Runbooks must name the decision-maker, executor, data sources, abort conditions, and rollback path. Use the following templates as baselines.

**Planned switchover**

1. Announce maintenance window and switch applications to non-writing mode.
2. Confirm source/replicas are healthy, pick candidate, and capture baseline state/GTIDs.
3. Drain transactions, stop write jobs, and set `super_read_only=ON` on the old source.
4. Capture final source GTIDs; wait for candidate via `WAIT_FOR_EXECUTED_GTID_SET`.
5. Verify GTID subset, zero apply errors, and data validation criteria.
6. Stop replication on candidate and enable writes on candidate.
7. Redirect write endpoint, flush connection pools, and verify server UUID.
8. Reconfigure old source as a replica of the new primary; verify single-writer and monitor.

**Incident failover**

1. Confirm outage via multiple independent monitoring signals and assess partition risk.
2. Block write traffic and fence the old primary using an independent mechanism.
3. Gather remaining GTIDs/binlogs from archives and replicas; evaluate RPO.
4. Select candidate with the most complete valid transaction history; check for errant GTIDs.
5. Stop replication on candidate, promote, and update endpoints once fencing is confirmed.
6. Verify apps write to the right server UUID, GTIDs advance, and other replicas follow the new primary.
7. Keep the old primary fenced/read-only on recovery; decide between rejoin and re-seed.
8. Record potentially lost transactions, actual RTO, decisions, and sign-off evidence.

**Abort conditions**

- Cannot confirm the old primary is fenced.
- Cannot identify a candidate with valid data history.
- GTIDs or schemas show unexplained diverged transactions.
- Cannot control the write endpoint or accounts bypassing the proxy.
- Projected RPO exceeds approved limits without explicit owner sign-off.

### 9. Practice exercise

A MySQL system has `db-primary`, `db-replica-a`, and `db-replica-b` using GTID-based asynchronous replication. Applications write through a proxy. The primary loses connectivity from the main monitoring region, yet the control plane still reports the VM as running. The two replicas have different `gtid_executed` sets: replica A has fewer GTIDs than replica B, while B has some GTIDs absent on A.

1. Why is losing monitoring connectivity insufficient to promote immediately?
2. How must you fence the primary, and where do you obtain confirmation evidence?
3. Use `GTID_SUBTRACT` to analyze missing/extra GTIDs between the two replicas. Why can you not simply pick the node with the highest transaction count?
4. How do you determine whether the primary's final transaction was received and applied by a replica?
5. If you cannot retrieve binary logs from the primary, how do you assess RPO and communicate potential data loss?
6. After promotion, what must you check across MySQL, proxy, connection pools, and applications to prove single-writer operation?
7. When the old primary recovers, what conditions allow configuring it as a replica? When is re-seeding required?

### 10. Single-writer acceptance checklist

- [ ] HA model, version, topology, source UUID, and candidate clearly identified.
- [ ] Replication state, GTID sets, worker errors, and backups/binlogs saved before transition.
- [ ] For switchover, applications paused writes and transactions drained.
- [ ] For failover, old primary fenced via independent mechanism with completion evidence.
- [ ] Candidate applied all required GTIDs or RPO loss assessed/approved.
- [ ] Zero unexplained errant transactions on the candidate.
- [ ] Only the new primary has `read_only=OFF` and `super_read_only=OFF` per design.
- [ ] Replicas and old primary accept zero app writes; old primary remains fenced/read-only upon recovery.
- [ ] Router/proxy/VIP/DNS and connection pools point to the exact new server UUID.
- [ ] Test write succeeds on new primary and new GTID replicates/applies on replicas.
- [ ] Business data, replication lag, errors, and background jobs verified.
- [ ] Runbook, transition timestamps, actual RPO/RTO, and operational decisions logged.

### 11. Operational principles

Switchover requires draining transactions and synchronizing replicas before switching roles. Failover requires determining whether the old primary truly lost write capability or merely lost connectivity to one network zone. Fencing prevents split-brain; `read_only` and `super_read_only` are MySQL-level safeguards that do not replace independent fencing. Select candidates using GTIDs and data evidence, then verify MySQL, infrastructure, and application connection paths. Complete a transition only once you prove a single writer, replicas follow the new primary, and data loss falls within approved RPO.
