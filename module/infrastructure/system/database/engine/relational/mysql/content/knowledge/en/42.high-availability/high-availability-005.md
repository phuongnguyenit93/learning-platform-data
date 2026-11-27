# Distributed Recovery, Clone, and Member Join Conditions

When a new server joins MySQL Group Replication or a previous member returns after an interruption, it must receive all transactions the group committed during its absence. This state synchronization process is called **distributed recovery**. Group Replication automatically selects a data-providing member (the donor) and transfers missing transactions to the joining member (the joiner).

Group Replication has two main state-transfer methods. If the donor still retains the required transactions in its binary logs and the gap is small enough, the joiner receives the missing transactions via the `group_replication_recovery` channel. If the gap is large or donors no longer retain sufficient binary logs, Group Replication can use the Clone plugin to copy data from a donor and then fetch transactions generated while cloning was in progress. A member reaches `ONLINE` only after applying all group transactions.

This lesson uses MySQL 8.4 and current Group Replication syntax. It focuses on native Group Replication, the foundation of InnoDB Cluster; administrative actions through MySQL Shell automate several similar configuration steps.

## Objectives

After this lesson, you will be able to:

- Describe the stages of distributed recovery and the roles of donor and joiner.
- Distinguish binary-log state transfer from remote cloning.
- Understand how `group_replication_clone_threshold` determines when cloning is selected.
- Prepare the Clone plugin, recovery account, and compatibility prerequisites.
- Verify GTID, configuration, data, and network prerequisites before adding a member.
- Monitor `RECOVERING`, `ONLINE`, donor failures, and scenarios that cannot auto-recover.

## 1. What is distributed recovery?

Group Replication maintains a group of servers sharing a common history of certified, committed transactions. When a new member joins or an existing member returns after disconnecting, it may lack transactions already applied by other members. The joiner must catch up to that history before participating in normal transaction processing.

Two roles in this process:

| Role | Responsibility |
|---|---|
| Donor | An `ONLINE` member providing transactions from binary logs or physical data via the Clone plugin. |
| Joiner | A server joining or rejoining the group; receives and applies missing state. |

Distributed recovery uses a dedicated channel named `group_replication_recovery`. This is a direct replication connection between the joiner and the donor, separate from the group communication connection used to exchange membership messages, transaction certification, and view changes.

### 1.1. Recovery stages

General workflow:

```text
START GROUP_REPLICATION on joiner
              |
              v
Check group_replication_applier relay log
              |
              v
Select an eligible ONLINE donor
              |
              v
Choose state transfer method
       /                      \
      v                        v
Fetch transactions from    Clone data from donor
donor binary logs          then restart joiner
      |                        |
      |                 Fetch transactions generated
      |                 during clone from binlog
       \                      /
        v                    v
Apply missing and buffered transactions
              |
              v
Caught up with group history
              |
              v
            ONLINE
```

Before connecting to a donor, the joiner checks the `group_replication_applier` channel's relay log. If the server was previously in the group and received but had not yet applied some transactions, it applies those pending transactions first. A brand-new server typically has no work here.

Next, the joiner connects to an active donor to retrieve state. While state transfer runs, the group may keep committing new transactions. The joiner continues receiving or buffering these new transactions and applies them after the initial state transfer completes. Only once all required transactions are applied does Group Replication transition the joiner to `ONLINE`.

## 2. State transfer from binary logs

This is the foundational mechanism of distributed recovery. The joiner connects to a donor via the `group_replication_recovery` channel, operating much like an asynchronous replica. The donor sends transactions the joiner lacks; the replication applier applies them in the proper order.

A critical prerequisite is that at least one eligible donor's binary logs must still contain every transaction the joiner needs. Group Replication uses GTID sets to identify missing history and verify whether those transactions remain available in binary logs or have been purged.

Example:

- The group has executed GTIDs `...:1-1500`.
- The joiner already has `...:1-1450`.
- If a donor still has binary logs containing transactions `1451` through `1500`, the joiner can retrieve the delta via binary-log state transfer.
- If the needed transactions have been purged from every donor, this method cannot finish.

These GTID numbers are illustrative only. In practice, GTID sets can include multiple SIDs and multiple transaction intervals; never infer missing gaps by simply subtracting two final numbers.

### 2.1. Why must binary logs be retained long enough?

Binary logs on group members are the source for incremental recovery. If a member stays offline too long and the transactions it needs are purged from all donors, it cannot catch up using binary logs alone.

Binary log retention must account for:

- How long a member might remain offline.
- Time to detect the incident and prepare the server to return.
- Time to connect, transfer, and apply transactions.
- Volume of transactions generated while recovery runs.

Check GTID state and binary log retention on each server:

```sql
SELECT @@GLOBAL.gtid_executed,
       @@GLOBAL.gtid_purged;

SHOW BINARY LOGS;
SHOW BINARY LOG STATUS;
```

`gtid_executed` shows the GTID set executed on the instance; `gtid_purged` shows GTIDs that were executed but are no longer present in the current binary logs. If transactions needed by the joiner are in `gtid_purged` on every eligible donor, binary-log state transfer can no longer supply them.

### 2.2. When is binary log recovery insufficient?

Two common situations occur:

1. The joiner is missing a huge number of transactions, making per-transaction transfer from binary logs slow and heavy on the donor.
2. Required transactions are no longer present in any donor's binary logs.

In the second case, the Clone plugin can automatically provision full state. If cloning is not installed, no compatible donor exists, or cloning fails across all donors, the joiner cannot complete distributed recovery automatically. An administrator must re-provision data from a valid snapshot source or resolve why cloning cannot run.

## 3. Clone plugin in distributed recovery

The Clone plugin enables Group Replication to copy physical data from a donor to a joiner. Group Replication manages cloning automatically when members are configured to support it. Operators simply prepare the plugin, recovery account, and clone threshold before the joiner begins joining.

Cloning is typically appropriate when:

- The joiner is a fresh server with no group data yet.
- The joiner was offline for a long period and is missing a large transaction volume.
- Donor binary logs no longer hold the transactions the joiner needs.
- You want to avoid the time spent transferring and applying a massive backlog of individual transactions.

### 3.1. Installation requirements

At least one existing member capable of acting as donor and the joiner must be prepared for remote cloning. For broader donor choices and higher resilience, install and activate the Clone plugin on all current members and future candidate joiners.

Check plugins on each server:

```sql
SELECT PLUGIN_NAME, PLUGIN_STATUS
FROM INFORMATION_SCHEMA.PLUGINS
WHERE PLUGIN_NAME IN ('clone', 'group_replication');
```

If the plugin is not yet installed, on Linux install it with:

```sql
INSTALL PLUGIN clone SONAME 'mysql_clone.so';
```

Both the Clone plugin and the Group Replication plugin must be installed and active on the donor and joiner. If the donor uses other plugins—such as a keyring plugin for encryption key management—the corresponding plugin must also be installed and active on the joiner so data can be decrypted correctly after cloning.

### 3.2. Compatibility between donor and joiner

For cloning in Group Replication, donor and joiner must meet these conditions:

- Run on the same operating system.
- Belong to the same MySQL Server release series (e.g., no direct cloning between 8.0 and 8.4 series).
- Have both the Clone plugin and Group Replication plugin installed and active on both machines.
- Have required plugins on the donor, such as keyring plugins, also present on the joiner.
- Satisfy clone donor selection rules; in MySQL 8.4, the clone donor is selected from members with the same patch version as the joiner.
- Have matching TLS configuration and certificates if distributed recovery uses SSL.

Cloning replaces the data and data dictionary on the joiner. Remote cloning removes user-created tablespaces and existing data on the joiner before transferring data from the donor. If aborted mid-way, the joiner may be left with partial or no user data. Group Replication retries with another donor when possible, but the server must remain excluded from application traffic until recovery completes.

### 3.3. Accounts and privileges for Clone

During distributed recovery, Group Replication uses the replication recovery account itself as the clone user on the donor. Therefore, this account needs `BACKUP_ADMIN` on members supporting cloning, including the joiner once it joins and may act as a donor later.

Required privileges on the recovery account in MySQL 8.4:

| Privilege | Purpose |
|---|---|
| `REPLICATION SLAVE` | Establishes the recovery connection and reads transactions from the donor. |
| `CONNECTION_ADMIN` | Keeps Group Replication connections operational in certain situations when an instance enters offline mode. |
| `BACKUP_ADMIN` | Allows the recovery account to act as the clone user on the donor when using the Clone plugin. |
| `GROUP_REPLICATION_STREAM` | Required when the group uses the MySQL communication stack. |

Create the same recovery account on existing members and the joiner. Example:

```sql
CREATE USER 'rpl_user'@'10.20.30.%'
IDENTIFIED BY 'replace_with_secret';

GRANT REPLICATION SLAVE ON *.*
TO 'rpl_user'@'10.20.30.%';

GRANT CONNECTION_ADMIN ON *.*
TO 'rpl_user'@'10.20.30.%';

-- Required when using the Clone plugin for distributed recovery.
GRANT BACKUP_ADMIN ON *.*
TO 'rpl_user'@'10.20.30.%';

-- Grant only when the group communication stack is MYSQL.
GRANT GROUP_REPLICATION_STREAM ON *.*
TO 'rpl_user'@'10.20.30.%';
```

If the group uses the XCom communication stack, `GROUP_REPLICATION_STREAM` is not needed for this purpose. Restrict the host pattern to your actual management subnet and use a dedicated password. The exact same recovery account and credentials must be configured consistently across every member.

In Group Replication, the joiner uses the internal `mysql.session` account with `CLONE_ADMIN` to initiate cloning on the recipient side. Group Replication automatically sets `clone_valid_donor_list` according to the selected donor. You do not need to grant `CLONE_ADMIN` to the recovery account or manually manage the clone allowlist for this process.

### 3.4. Configuring the clone threshold

The `group_replication_clone_threshold` variable sets the transaction gap between donor and joiner (measured in transactions) beyond which Group Replication prefers remote cloning when cloning is feasible.

```sql
SHOW VARIABLES LIKE 'group_replication_clone_threshold';
```

In MySQL 8.4, the default is `9223372036854775807`, effectively disabling threshold-based cloning whenever binary-log recovery is still possible. When you want Group Replication to choose cloning for large gaps, set a threshold tailored to your dataset size and group transaction rate.

Illustrative example setting a threshold of 100,000 transactions:

```sql
SET PERSIST group_replication_clone_threshold = 100000;
```

This value is only an example; measure actual clone duration and transaction rate before choosing a production threshold. The variable can be updated while Group Replication is running, but takes effect only after stopping and restarting Group Replication on that member. Configure it before the joiner begins recovery.

Do not set the threshold too low in a high-throughput group. If the group generates more transactions than the threshold while cloning is underway, upon restarting the joiner may exceed the threshold again and trigger another clone—creating a continuous clone loop. Choose a threshold comfortably higher than expected transaction volume over the duration of a full clone.

Even if the threshold is not exceeded, Group Replication still uses cloning if required transactions are missing from every donor's binary logs and cloning is possible. In that case, the threshold cannot disable cloning because cloning is the only automatic fallback short of manual re-provisioning.

### 3.5. Clone completion and joiner restart

Once cloning completes, the joiner restarts. If `group_replication_start_on_boot=ON` and the required settings were saved in the configuration file or via `SET PERSIST`, Group Replication can resume automatically after server startup. Cloning also copies the replication metadata repositories needed to resume replication; thus credentials stored in metadata on the donor may be transferred to the joiner.

If `group_replication_start_on_boot=OFF`, an administrator must run `START GROUP_REPLICATION` again after the post-clone restart. If credentials were passed only inline via `START GROUP_REPLICATION USER=..., PASSWORD=...`, you must supply `USER` and `PASSWORD` again after restart because inline credentials are held only in memory. If credentials were saved with `CHANGE REPLICATION SOURCE TO` for the recovery channel, `START GROUP_REPLICATION` can use the metadata repository.

Cloning transfers data state and metadata needed to resume, but does not replace all donor binary logs and relay logs. After restart, the joiner still needs to connect to a donor to fetch transactions committed while cloning took place. Therefore, the donor must still retain those transactions in its binary logs.

## 4. Prerequisites for a new member to join the group

Distributed recovery begins only after the server passes initial compatibility checks. A server may appear in `OFFLINE` or `ERROR` while configuration checks fail; `RECOVERING` indicates it is receiving and applying data. Prerequisites must be prepared before running `START GROUP_REPLICATION`.

### 4.1. Server configuration prerequisites

Group Replication members need the following foundational settings:

| Setting | Requirement |
|---|---|
| `server_id` | Unique positive integer across the entire replication topology. |
| `server_uuid` | Unique across instances; never copy a data directory that duplicates UUIDs. |
| `log_bin` | Enable binary logging. |
| `log_replica_updates` | Enable to record transactions received from donors and applied from the group. |
| `binlog_format` | Use `ROW`. |
| `gtid_mode` | Set `ON`. |
| `enforce_gtid_consistency` | Set `ON`. |
| `group_replication_group_name` | Identical valid UUID across all members. |
| `group_replication_local_address` | Dedicated, unique group communication address reachable by other members. |
| `group_replication_group_seeds` | List of member addresses used to discover the group. |
| `group_replication_bootstrap_group` | `OFF` on joiners; only enabled temporarily when creating/bootstrapping a group per dedicated procedure. |

In MySQL 8.4, binary logging, `binlog_format=ROW`, and `log_replica_updates=ON` are common defaults, though you should still verify the active configuration. GTIDs and `enforce_gtid_consistency` must be enabled for Group Replication to run.

Minimal illustrative configuration for a joiner:

```ini
[mysqld]
server_id=103
log_bin=binlog
log_replica_updates=ON
binlog_format=ROW
gtid_mode=ON
enforce_gtid_consistency=ON

group_replication_group_name="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
group_replication_local_address="db3.example.internal:33061"
group_replication_group_seeds="db1.example.internal:33061,db2.example.internal:33061"
group_replication_bootstrap_group=OFF
group_replication_start_on_boot=OFF
```

These hostnames, UUID, ports, and `server_id` are examples. Use the exact `group_replication_group_name` of the existing group; `group_replication_local_address` must be the joiner's own address. With the XCom communication stack, groups typically use a dedicated group communication port such as `33061`; do not confuse this port with the SQL port donors use for recovery and cloning.

`group_replication_bootstrap_group` must always be `OFF` when a regular member joins a running group. Enabling it at the wrong time can create a separate independent group with the same name instead of joining the existing group.

### 4.2. Data and schema prerequisites

Group Replication requires data to be managed by InnoDB. Replicated tables must have a primary key or an equivalent unique key over `NOT NULL` columns so rows are uniquely identified during transaction conflict checking.

Before joining:

- Convert MyISAM, MEMORY, or unsupported storage engine tables to InnoDB.
- Ensure every application table has a primary key or valid `NOT NULL` unique key.
- Reconcile schemas and application versions against active members.
- Align `lower_case_table_names` across members.
- Align `default_table_encryption` across members.

You can configure the server to block creating tables with unsupported engines:

```ini
disabled_storage_engines="MyISAM,BLACKHOLE,FEDERATED,ARCHIVE,MEMORY"
```

This is an extra safeguard; evaluate your application before applying it because it blocks `CREATE TABLE` statements using the listed engines.

### 4.3. GTID history prerequisites

The joiner's GTID set must be compatible with the group's transaction history. A joiner may be missing transactions (which distributed recovery supplies), but it must not contain extra local transactions absent from existing members.

Extra transactions commonly appear when an administrator runs writes on a server while Group Replication is stopped. Those writes create GTIDs outside the shared history. If a joiner has extra transactions:

- Cloning erases those transactions and corresponding data when replacing the data directory.
- Binary-log state transfer can conflict with those local transactions.
- Group Replication refuses to complete recovery to avoid losing or mixing data histories.

Check GTIDs on the joiner and existing members:

```sql
SELECT @@GLOBAL.gtid_executed,
       @@GLOBAL.gtid_purged;
```

If you must perform local administrative actions on a member while Group Replication is stopped without generating errant GTIDs, disable binary logging for the admin session:

```sql
SET SESSION sql_log_bin = 0;

-- Perform required administrative operations here.

SET SESSION sql_log_bin = 1;
```

Do this only when you fully understand the impact. Changes not written to the binary log will not replicate to other members; never use this technique to create application data the group expects to synchronize.

If a joiner already has extra transactions, inspect its binary logs to identify their content and choose a safe resynchronization path—typically cloning from an active group member. Never manually edit `gtid_purged` or delete GTID history just to bypass join checks.

### 4.4. Network and donor prerequisites

Members need continuous bidirectional connectivity over the group communication network. Before joining, verify:

- The joiner can reach the addresses in `group_replication_group_seeds`.
- Existing members can reach back to the joiner's `group_replication_local_address`.
- Firewalls permit both the group communication port and the SQL port used for distributed recovery.
- Group Replication's IP allowlist permits peer addresses when using XCom.
- DNS resolves consistently; configured hostnames must resolve to addresses actually reachable by members.
- The recovery account exists with the proper privileges on donors.
- TLS and certificates match the security configuration of group communication and distributed recovery.

The donor must be `ONLINE` and able to serve the joiner. For binary-log state transfer, the donor must retain the needed transactions. For cloning, the donor must satisfy OS, release series, plugin, and patch-version compatibility rules. Group Replication picks a donor at random from eligible `ONLINE` members; operators do not pin a fixed donor per join. In MySQL 8.4, a donor for binary-log recovery must have a patch version lower than or equal to the joiner; a donor for remote cloning must have the exact same patch version as the joiner.

### 4.5. Version compatibility prerequisites

Members must run a version combination supported by Group Replication. During upgrades, a group may temporarily run mixed versions under rolling-upgrade procedures and compatible communication protocol versions. Never add an arbitrary version into a running group; verify MySQL's version compatibility policy and communication protocol version before joining.

For cloning specifically, requirements are stricter: donor and joiner must share the same OS and release series. Donor selection rules for binary-log recovery versus cloning also differ on patch versions. If cloning is ineligible due to version or platform differences, Group Replication can still attempt binary-log state transfer if the required transactions remain available.

## 5. Configuring the recovery user and starting the joiner

Once server and data prerequisites are set, prepare credentials for the `group_replication_recovery` channel.

### 5.1. Storing credentials in replication metadata

Example on the joiner:

```sql
CHANGE REPLICATION SOURCE TO
  SOURCE_USER = 'rpl_user',
  SOURCE_PASSWORD = 'replace_with_secret'
FOR CHANNEL 'group_replication_recovery';

START GROUP_REPLICATION;
```

Credentials configured via `CHANGE REPLICATION SOURCE TO` are stored in plain text in the replication metadata repository. Restrict read permissions on metadata files and consider stronger credential-management practices per your security policy.

### 5.2. Supplying credentials at startup

Credentials can be passed inline in the start statement:

```sql
START GROUP_REPLICATION
  USER = 'rpl_user',
  PASSWORD = 'replace_with_secret';
```

Credentials passed this way live only in memory and are cleared upon `STOP GROUP_REPLICATION` or server restart. If using this approach, set `group_replication_start_on_boot=OFF` and establish a procedure to run `START GROUP_REPLICATION` again after cloning or restarting. Do not mix both approaches without clearing old credentials from the metadata repository, since saved credentials could be picked up on auto-start.

Note when using the Clone plugin: if credentials were previously stored via `CHANGE REPLICATION SOURCE TO` and you switch to passing them in `START GROUP_REPLICATION`, clear the old credentials from the metadata repository following MySQL's secure distributed recovery guidelines before cloning. Otherwise, stale credentials may be copied from donor to joiner and start the recovery channel unexpectedly.

## 6. How Group Replication chooses IST vs. Clone

Group Replication automatically picks the method after `START GROUP_REPLICATION` runs on the joiner. Selection depends on:

1. Available donors and which are eligible to serve the joiner.
2. Transaction gap between the joiner's and donor's GTID sets.
3. Whether required transactions still exist in donor binary logs.
4. Whether the Clone plugin is configured on both donor and joiner.

| Scenario | Method typically chosen |
|---|---|
| Small transaction gap; donor retains needed binary logs | Binary-log state transfer. |
| Transaction gap exceeds `group_replication_clone_threshold`; clone eligible | Remote clone, followed by state transfer for transactions generated during clone. |
| Required transactions purged from all donors; clone eligible | Remote clone regardless of threshold. |
| Clone not installed or incompatible; binary logs available | Binary-log state transfer. |
| Required binary logs unavailable and clone impossible | Recovery fails; re-provision data or fix clone prerequisites. |

The clone threshold measures transaction count gap, not data size in GB or offline duration. A member offline for a day on a low-traffic group may lack few GTIDs; a member offline for minutes on a busy group may lack huge numbers of transactions.

### 6.1. Donor errors and retry behavior

Group Replication can automatically select another donor and retry on connection errors, receiver/applier errors, clone failures, or if a donor leaves mid-transfer. The `replication_applier_status_by_worker` table can reveal the latest error triggering a retry.

Recovery cannot complete if:

- Required transactions were purged from all donors and cloning is unavailable.
- The joiner has extra transactions absent from the group.
- All eligible donors have been tried and neither cloning nor binary-log transfer succeeded.
- Reconnection attempts exceed `group_replication_recovery_retry_count`.
- The joiner leaves the group or an administrator stops Group Replication mid-recovery.

When no options remain, the joiner exits the group and executes the action set in `group_replication_exit_state_action`. Inspect the error log and worker status before retrying; never loop start commands without fixing the root cause.

## 7. Monitoring the join process

### 7.1. Checking member state

Query from an active member:

```sql
SELECT MEMBER_ID,
       MEMBER_HOST,
       MEMBER_PORT,
       MEMBER_STATE,
       MEMBER_ROLE,
       MEMBER_VERSION
FROM performance_schema.replication_group_members;
```

Common states:

| State | Meaning |
|---|---|
| `OFFLINE` | Plugin is loaded, but the member has not joined the group. |
| `RECOVERING` | Member is receiving and applying data during distributed recovery. |
| `ONLINE` | Member is fully synchronized and participating normally. |
| `ERROR` | Member hit an error during configuration checks, recovery, or transaction apply. |
| `UNREACHABLE` | Failure detector suspects this member cannot be contacted. |

Consider the join complete only when the state is `ONLINE`. `RECOVERING` does not mean ready for application traffic; `ERROR` requires investigation before trying to rejoin.

### 7.2. Checking recovery and applier channels

```sql
SELECT CHANNEL_NAME,
       SERVICE_STATE,
       LAST_ERROR_NUMBER,
       LAST_ERROR_MESSAGE
FROM performance_schema.replication_connection_status
WHERE CHANNEL_NAME = 'group_replication_recovery';

SELECT CHANNEL_NAME,
       WORKER_ID,
       SERVICE_STATE,
       LAST_ERROR_NUMBER,
       LAST_ERROR_MESSAGE
FROM performance_schema.replication_applier_status_by_worker
WHERE CHANNEL_NAME = 'group_replication_applier';
```

The `group_replication_recovery` channel reports connection and transfer status from the donor. The `group_replication_applier` channel applies group transactions. If the receiver has fetched data while the applier is stopped, inspect worker errors and the failing transaction rather than checking only network connectivity.

### 7.3. Monitoring the Clone plugin

While remote cloning is running, check:

```sql
SELECT *
FROM performance_schema.clone_status\G

SELECT *
FROM performance_schema.clone_progress;
```

`clone_status` shows the status of the latest clone operation; `clone_progress` shows progress per stage. Combine this with the error log to determine whether cloning is running, completed, or failed. After cloning, the joiner still needs binary-log state transfer and to apply new transactions before turning `ONLINE`.

### 7.4. Reconciling GTIDs

```sql
SELECT @@GLOBAL.gtid_executed,
       @@GLOBAL.gtid_purged;
```

Once recovery finishes, the joiner's transaction history must match the group. Do not rely solely on `Seconds_Behind_Source` or received transaction counts; Group Replication tracks history via GTID sets and you must confirm the member reaches `ONLINE`.

## 8. Common errors and troubleshooting

| Symptom | Possible cause | Resolution |
|---|---|---|
| Joiner stuck in `RECOVERING` for a long time | Large transaction gap or slow donor transfer | Check GTID gap, binlog volume, donor load, and network throughput; consider cloning. |
| Required transactions not found | Binary logs purged on all donors | Check `gtid_purged`; prepare cloning or re-provision from a valid snapshot. |
| Clone not selected | Plugin inactive, missing `BACKUP_ADMIN`, threshold too high, or incompatible donor | Check plugins, recovery privileges, threshold, and release series/platform. |
| Repeated clone loops | Threshold too low relative to transaction rate during clone duration | Raise threshold above expected writes per clone cycle; stop/start Group Replication to apply. |
| Clone fails due to keyring | Key management plugin on donor missing or inactive on joiner | Install and configure matching keyring plugin on joiner before cloning. |
| Recovery authentication error | Recovery user missing on donor or wrong password/host | Align user and privileges across members; check TLS and auth plugin. |
| Joiner rejected for extra transactions | Joiner holds GTIDs absent from the group | Inspect joiner's binlogs and resync from a valid donor; never arbitrarily alter GTID sets. |
| Joiner fails configuration checks | Wrong group name, duplicate `server_id`, local address, or incompatible settings | Diff joiner config against `ONLINE` members. |
| Joiner cannot reach donor | Firewall, DNS, allowlist, or wrong SQL/group communication port | Verify bidirectional connectivity and logs on both donor and joiner. |
| Clone finished but not `ONLINE` yet | Joiner still fetching/applying transactions generated during clone | Monitor recovery channel and applier workers; wait for state transfer to finish. |

If cloning is interrupted, the recipient may retain partial data. Never route application writes to that instance. Let Group Replication try another donor or re-prepare the joiner from a valid backup after resolving the error.

## 9. Practical walkthrough: adding a member to a group

Suppose a group currently has `db1` and `db2` in `ONLINE` state. Server `db3` is the joiner. The group runs MySQL 8.4, the XCom communication stack, and the Clone plugin to assist recovery.

### Step 1: Inspect the existing group

On an active member:

```sql
SELECT MEMBER_HOST, MEMBER_PORT, MEMBER_STATE, MEMBER_ROLE
FROM performance_schema.replication_group_members;

SHOW VARIABLES LIKE 'group_replication_group_name';
SHOW VARIABLES LIKE 'group_replication_clone_threshold';
SHOW BINARY LOGS;
```

Confirm the group has quorum, at least one donor is `ONLINE`, donors retain needed binary logs or support cloning, and no unresolved recovery errors exist.

### Step 2: Prepare db3

Set unique `server_id` and `server_uuid`. Configure GTIDs, binary logging, `ROW` format, InnoDB, primary keys, group name, local address, seeds, and `group_replication_bootstrap_group=OFF`. Align `lower_case_table_names` and `default_table_encryption` with the group.

### Step 3: Install plugins and recovery account

Install and enable `group_replication` and `clone` on `db3` and prospective donors. Create the recovery account on all members and the joiner, granting `REPLICATION SLAVE`, `CONNECTION_ADMIN`, and `BACKUP_ADMIN`. For the MySQL communication stack, also grant `GROUP_REPLICATION_STREAM`.

### Step 4: Configure credentials and clone threshold

On `db3`, configure credentials for the `group_replication_recovery` channel. Choose `group_replication_clone_threshold` based on expected transactions generated during a clone; avoid values that are too low. If changing the threshold on an instance already running Group Replication, stop and restart the plugin for the value to take effect.

### Step 5: Start joining

On `db3`:

```sql
START GROUP_REPLICATION;
```

Group Replication validates the joiner, picks a donor, and performs binary-log recovery or cloning as conditions dictate. Do not manually run `CLONE INSTANCE` for this automated distributed recovery flow.

### Step 6: Monitor until ONLINE

Watch `replication_group_members`, the recovery channel, applier workers, and clone status. If cloning ran, wait for `db3` to restart; if `group_replication_start_on_boot=OFF`, run `START GROUP_REPLICATION` again after restart. Route application traffic to `db3` only once its state is `ONLINE` and GTID history has caught up.

### Step 7: Verify future donor readiness

Confirm `db3` has the Clone plugin active, the recovery account holds `BACKUP_ADMIN`, and required network/TLS settings are in place. This allows `db3` to serve as a donor for future recoveries.

## 10. Operational principles

1. **Retain binary logs long enough.** Binary-log recovery depends on donors still holding the transactions a joiner needs.
2. **Prepare cloning before incidents.** Install plugins and grant privileges across members ahead of time to maximize donor options.
3. **Size the clone threshold to real workload.** Account for transactions generated throughout the duration of a clone.
4. **Keep GTID history clean.** Avoid local writes on a member while Group Replication is stopped unless they belong to shared history.
5. **Align critical configurations.** Group name, GTID, InnoDB, primary keys, encryption, and lower-case table settings must satisfy group rules.
6. **Verify recovery privileges.** The same recovery account needs identical required privileges on every donor and joiner.
7. **Secure connections.** Restrict hosts, enable TLS, and protect access to binary logs.
8. **Monitor all the way to ONLINE.** `RECOVERING` means state transfer is incomplete; keep joiners out of traffic until synchronized.
9. **Never ignore GTID errors.** Extra transactions or purged transactions require controlled resynchronization.

## 11. Self-check exercises

1. When a joiner is missing only a few transactions still held in a donor's binary logs, which mechanism does Group Replication use to recover?
2. Why might a joiner missing many transactions be cloned instead of fetching individual transactions from binary logs?
3. If needed transactions have been purged from every donor, what condition allows recovery to proceed?
4. Why can setting `group_replication_clone_threshold` too low cause a clone loop?
5. Which privileges does the recovery account need to both read binary logs and act as clone user on a donor?
6. Why does Group Replication reject a joiner with extra transactions?
7. Which state confirms a joiner has caught up with the group and can participate normally?
8. Why must a joiner set `group_replication_bootstrap_group=OFF` when joining an active group?

**Answer hints:** (1) Binary-log state transfer via the `group_replication_recovery` channel. (2) Cloning copies physical data state faster than transferring and applying huge numbers of individual transactions. (3) The Clone plugin must be installed and an eligible donor must be available; otherwise manual re-provisioning is required. (4) New transactions during cloning can exceed the threshold again; after restarting, the joiner triggers another clone, looping repeatedly. (5) `REPLICATION SLAVE`, `CONNECTION_ADMIN`, and `BACKUP_ADMIN`; plus `GROUP_REPLICATION_STREAM` when using the MySQL communication stack. (6) Cloning would overwrite them, and binary-log recovery could conflict with group history. (7) `ONLINE`. (8) Enabling bootstrap on a joiner risks creating an independent group instead of joining the existing one.

## References

- [MySQL 8.4 Reference Manual: Distributed Recovery](https://dev.mysql.com/doc/refman/8.4/en/group-replication-distributed-recovery.html)
- [MySQL 8.4 Reference Manual: Cloning for Distributed Recovery](https://dev.mysql.com/doc/refman/8.4/en/group-replication-cloning.html)
- [MySQL 8.4 Reference Manual: Configuring Distributed Recovery](https://dev.mysql.com/doc/refman/8.4/en/group-replication-tuning-recovery.html)
- [MySQL 8.4 Reference Manual: Fault Tolerance for Distributed Recovery](https://dev.mysql.com/doc/refman/8.4/en/group-replication-distributed-recovery-fault.html)
- [MySQL 8.4 Reference Manual: Group Replication Requirements](https://dev.mysql.com/doc/refman/8.4/en/group-replication-requirements.html)
- [MySQL 8.4 Reference Manual: User Credentials for Distributed Recovery](https://dev.mysql.com/doc/refman/8.4/en/group-replication-user-credentials.html)
- [MySQL 8.4 Reference Manual: Group Replication Server States](https://dev.mysql.com/doc/refman/8.4/en/group-replication-server-states.html)
