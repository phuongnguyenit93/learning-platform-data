# Upgrade Order for Source/Replica or Cluster Members

This lesson belongs to the **DATABASE_MYSQL** module. When upgrading MySQL in a system using replication or running InnoDB Cluster, upgrade order directly affects service continuity, replication stream compatibility, and rollback capability. A standalone server can be upgraded within a single maintenance window; a multi-server topology must be upgraded in a defined sequence so active nodes continue exchanging data and maintaining quorum.

For standard asynchronous replication, the common deployment principle is **upgrade replicas first, source last**. For Group Replication/InnoDB Cluster in single-primary mode, typically secondaries are upgraded one by one and the primary is upgraded last. In both models, verify the compatibility matrix for the exact version pair, keep replication/quorum healthy, and confirm each node operates stably before moving to the next node.

## 1. Why Does Upgrade Order Matter?

In a MySQL topology, nodes can perform multiple roles:

- **Source/primary:** accepts write transactions and emits binary logs.
- **Replica/secondary:** receives events from the source or participates in Group Replication to maintain a copy of the data.
- **Router/proxy:** routes application connections to the primary or secondaries.
- **MySQL Shell/AdminAPI:** tool for managing and inspecting cluster configuration.

Upgrading in the wrong order can cause the source to emit events that an older replica cannot understand, halting log application; or cause a cluster to lose quorum if multiple members go offline simultaneously. An upgrade can also update the data dictionary and internal data directory format, making it unsafe to revert to old binaries.

Goals when planning the sequence:

1. Keep the topology in a compatible state throughout the entire mixed-version phase.
2. Take only one node out of service at a time, if the architecture and procedure support rolling upgrades.
3. Maintain enough replicas or members to satisfy RPO, availability, and quorum.
4. Ensure data has been fully received and applied before switching roles or upgrading the source.
5. Have backups and recovery paths suited to the pre-upgrade version.

## 2. Version Compatibility Rules

Before choosing an order, identify the exact source and target versions. Not every pair of MySQL versions supports replication or Group Replication while running mixed versions.

For asynchronous replication across supported version combinations, the general rule is that the source must be the same version or older than the replica. Do not design a replication stream from a newer source to an older replica and assume it will work. Beyond this general rule, check restrictions by release series, patch version, binlog event format, features in use, and the target version's upgrade path documentation.

| Topology State | Assessment |
|---|---|
| Older source, newer replica within a supported version pair | Can be used as an intermediate state when upgrading replicas before the source |
| Source and replica on the same version | Normal state after the upgrade is complete |
| Newer source, older replica | Do not use as a target replication state; this direction is unsupported under standard compatibility rules |
| Skipping multiple release series | Perform only if the official upgrade path permits it; may require upgrading through an intermediate version |
| Group Replication with mixed-version members | Maintain only during a documented rolling upgrade window; never treat mixed-version as a long-term operating state |

Do not compare version numbers alone. Check edition/distribution, plugins, authentication, TLS, binlog configuration, GTID, and features used by the application. If an upgrade changes SQL behavior or removes a feature, applications can still fail even while replication keeps running.

## 3. General Pre-Upgrade Preparation

### 3.1. Documenting Topology and Roles

Map out all nodes, versions, roles, replication streams, application endpoints, Routers/proxies, and deployment locations. For chained replication, clearly document which node is the source for which node.

On each server, record version and identity:

```sql
SELECT VERSION() AS mysql_version,
       @@version_comment AS distribution,
       @@hostname AS host_name,
       @@server_id AS server_id,
       @@server_uuid AS server_uuid;
```

For asynchronous replication, check replica status using version-appropriate syntax. MySQL 8.0.22 and later use:

```sql
SHOW REPLICA STATUS\G
```

Older versions may use the command name `SHOW SLAVE STATUS`. Check at minimum:

- Receiver/IO thread and applier/SQL thread are running.
- Zero errors in receiving or applying transactions.
- Replication lag is within acceptable thresholds.
- Received and executed GTIDs align with the source.
- Required binary logs remain within retention and cover the entire upgrade window.

For Group Replication, inspect member status:

```sql
SELECT MEMBER_ID, MEMBER_HOST, MEMBER_PORT,
       MEMBER_STATE, MEMBER_ROLE
FROM performance_schema.replication_group_members;
```

Before starting, members should be in the expected state, typically `ONLINE`, with exactly one primary in single-primary mode and the group maintaining quorum. If any node is `RECOVERING`, `ERROR`, `UNREACHABLE`, or leaving the group, resolve that before upgrading.

### 3.2. Backups and Recoverability Verification

Create a consistent backup before upgrading. For critical systems, maintain an appropriate backup for the source and a plan to rebuild replicas. Backups must be stored outside the data directory and protected from the upgrade operation or local storage failures.

Verify:

1. Backup completed with required checksums/metadata.
2. Tested restoring onto an independent host running the matching version.
3. Required binary logs/GTIDs exist to recover to the target point.
4. Saved configurations, TLS certificates, keyrings, plugins, and secrets needed for startup.
5. Clear procedure to rebuild a replica if upgrading a node fails.

Do not treat a data directory snapshot as a usable backup unless you have verified the restore procedure and compatibility with the corresponding MySQL version.

### 3.3. Checking Compatibility and Operational Readiness

- Read release notes, upgrade paths, and compatibility matrices for the target version.
- Run upgrade/configuration check tools supported by your version, such as MySQL Shell AdminAPI for InnoDB Cluster instances.
- Verify compatible versions for plugins/components, authentication plugins, audit, keyring, and TLS.
- Check free disk space for packages, temporary files, redo/undo logs, binary logs, and backups.
- Check for long-running transactions, metadata locks, active DDL, and large batch jobs.
- Confirm `server_id` and `server_uuid` are unique across all nodes.
- Verify application compatibility with both old and new versions during the transition phase.
- Establish the maintenance window, abort criteria, accountable owners, and communication plan.

Do not deploy schemas or SQL statements exclusive to the new version while older nodes still need to read or apply those changes.

## 4. Asynchronous Source/Replica Upgrade Order

### 4.1. Why Upgrade Replicas First?

Suppose a topology has one source on an older MySQL version and three replicas. Within an upgrade path that allows an older source to stream binlogs to a newer replica, you can upgrade each replica first. The source remains on the old version while replicas are upgraded and continues accepting transactions.

Once all replicas run the target version and operate stably, upgrade the source last. This ensures the source never sends new-version binlogs to an older-version replica. That is the core reason for the replica-first, source-last order.

```text
Before upgrade:
                 Source vA
                /    |    \
               v     v     v
          Replica vA vA   Replica vA

During replica upgrade phase:
                 Source vA
                /    |    \
               v     v     v
          Replica vB vA   Replica vA

After all replicas are upgraded:
                 Source vA
                /    |    \
               v     v     v
          Replica vB vB   Replica vB

Finally upgrade source:
                 Source vB
                /    |    \
               v     v     v
          Replica vB vB   Replica vB
```

The diagram illustrates the sequence; perform this only if the vA/vB version pair is supported for replication during the upgrade.

### 4.2. Chained Replication Topologies

In a source A → replica B → replica C topology, upgrade from leaf nodes back toward the root: C first, B next, A last. When upgrading B, C is already on the new version; B still receives binlogs from the older A and can relay logs to the newer C within verified compatibility limits.

If there are multiple branches, upgrade replicas at the same tier independently node by node, then work up toward the root source. Always verify compatibility at every source→replica edge, not just between the two outermost nodes.

### 4.3. Procedure for Upgrading Each Replica

1. **Select a replica:** prioritize a node with minimal read-traffic impact that is not the sole failover candidate.
2. **Verify catch-up:** confirm the replica has applied all required transactions and has zero replication errors.
3. **Drain or shift read traffic:** if the replica serves queries, shift traffic to other nodes per plan.
4. **Stop replication and MySQL cleanly:** use version-appropriate replica stop and shutdown procedures; never delete relay logs or data files manually.
5. **Upgrade software and data:** execute the tested in-place upgrade or restore/rebuild procedure for the target version.
6. **Start and inspect:** review error logs, server status, plugins, configuration, data dictionary, and warnings.
7. **Reconnect replication:** configure the source/replication channel and GTID or file/position per runbook.
8. **Wait for catch-up:** confirm receiver/applier are running, error-free, and lag returns to acceptable levels.
9. **Restore read traffic:** return the node to the serving pool only after testing queries and performance.
10. **Proceed to the next replica:** only once the newly upgraded node is stable.

Do not upgrade multiple replicas simultaneously if doing so eliminates redundancy or leaves the source without a sufficiently caught-up replica. With one source and a single replica, explicitly account for the zero-redundancy window, acceptable RPO, and how to rebuild the replica if it fails.

### 4.4. Upgrading the Source Last

Once every replica runs the target version:

1. Confirm all replicas are healthy, caught up, and have consistent GTIDs/positions.
2. Stop or lock application write streams per the cutover plan.
3. Confirm no active or long-running transactions remain to obstruct shutdown.
4. Record the final watermark and create required backups/snapshots.
5. Stop the source cleanly and upgrade the server following the upgrade path.
6. Start the source and inspect error logs, data dictionary, plugins, and configuration.
7. Confirm binary logging and GTID operate as designed.
8. Verify replicas reconnect and resume applying transactions.
9. Run smoke tests, reopen writes, and monitor replication lag.

If the source fails to start or replication fails after upgrading, keep the system in maintenance and execute the recovery runbook. Do not hastily promote another node while leaving the old source able to accept writes.

## 5. Group Replication and InnoDB Cluster Upgrade Order

InnoDB Cluster uses Group Replication to maintain group membership and MySQL Router to route connections. In single-primary mode, one node is the primary accepting writes while the remaining nodes are secondaries.

### 5.1. Rolling Upgrade Principles

Within an upgrade path supporting mixed-version Group Replication, the standard sequence is:

1. Upgrade one secondary.
2. Wait for the secondary to start, rejoin the group, and return to `ONLINE` state.
3. Confirm the group retains quorum, the primary remains active, and transactions synchronize.
4. Upgrade the next secondary.
5. After all secondaries are upgraded and stable, perform a planned switchover if needed so the current primary becomes a secondary.
6. Upgrade the former primary node last.
7. Confirm all members run the target version, the group is healthy, and the primary is properly designated.

Do not stop multiple members at once. In a three-node group, when one node goes offline, the remaining two maintain a majority; if a second node is stopped, the group can lose quorum and stop accepting writes. Calculate quorum based on actual member states and failure detection settings, not just the initial node count.

### 5.2. Secondary-First, Primary-Last Order

Example three-node single-primary cluster:

```text
Initial:
       Node A (PRIMARY, vA)
       Node B (SECONDARY, vA)
       Node C (SECONDARY, vA)

Upgrade B, wait for ONLINE:
       Node A (PRIMARY, vA)
       Node B (SECONDARY, vB)
       Node C (SECONDARY, vA)

Upgrade C, wait for ONLINE:
       Node A (PRIMARY, vA)
       Node B (SECONDARY, vB)
       Node C (SECONDARY, vB)

Switch primary to an upgraded node if required by runbook:
       Node A (SECONDARY, vA)
       Node B (PRIMARY, vB)
       Node C (SECONDARY, vB)

Upgrade A:
       Node A (SECONDARY, vB)
       Node B (PRIMARY, vB)
       Node C (SECONDARY, vB)
```

This diagram shows only role progression. In practice, Group Replication may elect a primary based on group configuration and state; use MySQL Shell/AdminAPI switchover operations or a verified runbook. Do not edit cluster metadata manually.

### 5.3. Multi-Primary Mode

In multi-primary mode, multiple members can accept writes. There is no single primary left to upgrade last. You must:

- Confirm the target version supports rolling upgrades with the current version across the whole group.
- Consider switching to single-primary mode before upgrading if procedures and applications allow.
- Drain write traffic from one node at a time, upgrade it, and wait for it to return `ONLINE` before continuing.
- Maintain quorum and watch certification failures, retries, and active transactions.
- Prevent two versions from concurrently processing workloads that use differing SQL features during the transition.

If the versions or topology do not support mixed-version rolling upgrades, use an offline upgrade procedure or provision a new parallel cluster and migrate applications per plan. Do not force a rolling upgrade solely to avoid downtime.

### 5.4. Checking Group Status After Each Node

After a member rejoins, verify:

```sql
SELECT MEMBER_HOST, MEMBER_PORT, MEMBER_STATE, MEMBER_ROLE
FROM performance_schema.replication_group_members;
```

Proceed to the next node only when the newly upgraded member is `ONLINE`, has zero recovery errors, and the group holds quorum. Also check Group Replication logs, transaction certification, flow control, and the replication applier. `ONLINE` is a necessary condition, though you must still test applications and real load.

## 6. Router, MySQL Shell, and Auxiliary Components

The database server is not the only component requiring upgrades. InnoDB Cluster also includes MySQL Router, MySQL Shell/AdminAPI, plugins, and monitoring tools.

A safe management sequence is typically:

1. Check whether current Router and Shell versions are compatible with both pre-upgrade and post-upgrade cluster versions.
2. Keep Router running during the rolling upgrade if that version supports connecting to mixed-version nodes.
3. Upgrade Router instances one by one, keeping at least one healthy Router active if applications use multiple instances.
4. Once cluster servers are upgraded and stable, upgrade administrative/monitoring tools per the compatibility matrix.
5. Re-verify routing to primary and secondaries, TLS, cluster metadata, and health checks.

Do not assume Router, Shell, or plugins work across all server versions. Check separate release notes and compatibility matrices for each component. If InnoDB Cluster metadata needs upgrading, perform it via AdminAPI at the version and stage specified by documentation; never edit metadata tables manually.

## 7. Things to Avoid During the Mixed-Version Phase

While nodes are running two different versions:

- Do not use syntax or features exclusive to the new version if older nodes still have to parse or apply those statements.
- Avoid large schema changes alongside server upgrades; separate the two activities to simplify fault isolation.
- Do not change `binlog_format`, GTID mode, authentication plugins, or TLS policies outside the upgrade plan.
- Do not purge binlogs still needed by replicas; retention must cover offline node upgrades and catch-up.
- Do not copy `auto.cnf` or clone `server_uuid` onto a new node.
- Do not allow applications to write directly to a replica/secondary while roles are transitioning.
- Do not upgrade additional nodes while the previously upgraded node is not yet `ONLINE` or replication has not caught up.
- Do not treat a clean service startup as proof that data and replication are healthy.

Changes in the data dictionary, SQL mode, collation, optimizer, authentication, and plugins can affect applications. Test representative workloads on the new version before upgrading the entire topology.

## 8. Rollback Plans and Recovering Failed Nodes

Upgrading MySQL can update internal data formats. Especially for major upgrades, never assume that reinstalling old binaries will open a data directory already upgraded by a newer version.

### 8.1. A Replica Upgrade Fails

If a replica fails to start or fails to rejoin:

1. Keep the source and remaining replicas operating stably.
2. Read the error log to identify package, plugin, configuration, data dictionary, or replication errors.
3. Do not continue upgrading other replicas if doing so reduces redundancy below acceptable levels.
4. Restore the replica from its matching backup/snapshot or rebuild it from the source using a tested procedure.
5. Verify GTID/position, replication, and catch-up status before returning the node to the pool.

### 8.2. Source or Primary Upgrade Fails

If the source fails to start after upgrading, keep application writes halted. Determine whether the issue can be fixed on the target version or requires restoring the pre-upgrade backup. If returning to the old version, use a data directory/backup compatible with the old version and replay logs to the target point.

With Group Replication, if the primary cannot return, execute failover or group bootstrap strictly according to a verified runbook. Avoid bootstrapping a new group while other members may still be operating, as that can create two independent data groups.

### 8.3. Do Not Rely on Downgrade as the Default Rollback

Major version downgrades are often restricted or unsupported directly. Safe fallback options are typically:

- Restore the pre-upgrade backup using the exact old version.
- Replay required binary logs/GTIDs to bring data to the chosen point.
- Or rebuild a replica from a source still running the old version during the transition phase.

If new transactions occurred on the target version, determine how to preserve them before reverting. Never switch endpoints back to an old source and ignore data written on the new node.

## 9. Post-Upgrade Verification

After each node and after the entire topology is upgraded, verify across these categories:

| Category | Verification Scope |
|---|---|
| Version | `SELECT VERSION()`, edition, plugins, and packages match target |
| Startup | Clean error log, no upgrade failures, crash loops, or critical warnings |
| Data | Schemas, tables, indexes, constraints, row counts, and critical business queries |
| Replication | Receiver/applier running, zero errors, GTID/position advancing, and lag within threshold |
| Group Replication | Members `ONLINE`, correct primary, quorum intact, and no expelled nodes |
| Security | Users/roles, authentication plugins, TLS, keyring, and audit functioning |
| Application | Connectivity, reads/writes, transactions, background jobs, events, and reports |
| Performance | Query latency, CPU, I/O, buffer pool, connections, lock waits, and replication lag |
| Backup | Fresh backup succeeds and restore test passes on the new version |

Common general check commands:

```sql
SELECT VERSION();
SHOW GLOBAL STATUS LIKE 'Uptime';
SHOW GLOBAL VARIABLES LIKE 'log_bin';
SHOW GLOBAL VARIABLES LIKE 'gtid_mode';
SHOW GLOBAL VARIABLES LIKE 'server_id';
```

For asynchronous replication, continue checking with `SHOW REPLICA STATUS\G` or the version-appropriate command. For Group Replication, inspect `performance_schema.replication_group_members` and plugin logs. Compare states before and after the change rather than inspecting a single value in isolation.

## 10. Example Source/Replica Upgrade Plan

Assume one source and two replicas, all on version A. The goal is to upgrade to version B, and the official upgrade path allows A to act as a source for B during the transition.

| Stage | Source | Replica 1 | Replica 2 | Gate to Proceed |
|---|---|---|---|---|
| Initial | A | A | A | Healthy replication, valid backups |
| Step 1 | A | B | A | Replica 1 caught up, zero errors |
| Step 2 | A | B | B | Both replicas `Yes/Yes`, lag within threshold |
| Step 3 | B | B | B | Source starts stably, replication resumes |
| Complete | B | B | B | Data, applications, security, and backups verified |

In this example, the source remains on version A until both replicas are upgraded. If the second replica fails, you can pause the process and remediate that node while the source stays on version A, provided the first replica and source meet availability/RPO requirements. Never upgrade the source simply because a single replica succeeded.

## 11. Upgrade Order Checklist

- [ ] Recorded versions, roles, and topology of all nodes.
- [ ] Checked upgrade paths and compatibility matrices for the exact version pair.
- [ ] Confirmed source/replica or Group Replication is currently healthy.
- [ ] Created backups and tested restores using matching versions.
- [ ] Checked plugins, TLS, keyrings, authentication, and OS configuration.
- [ ] Defined order: leaf replicas → intermediate replicas → root source for chained replication.
- [ ] Defined secondary-first, primary-last order if single-primary Group Replication supports rolling upgrades.
- [ ] Calculated quorum and capped the number of nodes permitted offline simultaneously.
- [ ] Prepared read/write traffic shifting and write-freeze plans for the source/primary upgrade.
- [ ] Ensured binlog retention covers offline upgrades and catch-up.
- [ ] Defined abort criteria: node fails to start, replication errors, quorum loss, or excessive lag.
- [ ] Prepared node restore/rebuild and topology-wide rollback plans.
- [ ] Verified each node before upgrading the next node.
- [ ] Executed smoke tests, performance checks, and created fresh backups post-upgrade.

## 12. Self-Check

1. Why are replicas typically upgraded before the source in asynchronous replication?
2. In an A → B → C topology, why should C be upgraded before B, and B before A?
3. What can happen if the source is upgraded to a new version while replicas remain on an older version?
4. In single-primary InnoDB Cluster, why must secondaries be upgraded one by one before the primary?
5. Why must you wait for a member to return `ONLINE` before stopping the next member?
6. How is quorum affected if two nodes in a three-member cluster go offline simultaneously?
7. When is a planned primary switchover required before upgrading the old primary node?
8. Why can you not assume you can downgrade by reinstalling old binaries?
9. Which metrics prove a replica has caught up after an upgrade?
10. Draft an upgrade sequence for a topology with one source, two replicas, and one Router; list the verification checks after each step.

Upgrade order must follow the topology's replication direction, version compatibility rules, and quorum mechanics. Upgrading node by node and verifying actual state before proceeding catches errors early, preserves recoverability, and reduces the risk of turning maintenance into a widespread data incident.
