# Switchover, Failover, Reinstate, and Drill Planning

Oracle Data Guard maintains one or more standby databases to protect the primary database against failures and support role transitions when needed. Three key operational procedures are **switchover**, **failover**, and **reinstate**. They serve different purposes and preconditions:

- **Switchover:** a planned role reversal. The primary becomes a standby, and the selected standby becomes the primary. This is the standard procedure for maintenance, upgrades, or shifting workload to another data center. When executed properly per Data Guard procedures, switchover guarantees zero data loss.
- **Failover:** promoting a standby to primary when the primary fails and cannot be recovered in time. Data loss may occur depending on protection mode, redo transport, transport lag, and the redo received by the standby.
- **Reinstate:** restoring the former primary as a standby of the new primary after a failover. Data Guard Broker can perform this using Flashback Database if prerequisites are satisfied.

A role transition is complete only when database roles, redo transport, redo apply, application services, and application connections all operate properly. A successful DGMGRL command confirms only the database role transition; DBAs must still verify that applications are serving transactions on the new primary and that the new standby continues receiving and applying redo.

This lesson belongs to the **High Availability** group of Database Engine Relational Oracle. It focuses on switchover, failover, reinstate, and building a repeatable drill plan with measurable RTO/RPO and fallback options.

After completing this lesson, you will be able to:

- Distinguish planned switchover, manual failover, and fast-start failover.
- Understand primary and standby readiness preconditions before transitioning roles.
- Select a target standby based on apply lag, transport lag, and standby type.
- Use Data Guard Broker via DGMGRL to inspect, validate, and transition roles.
- Execute a switchover and verify primary/standby afterward.
- Distinguish complete failover from immediate failover.
- Recognize split-brain risk and how to fence the former primary.
- Understand the impact of Maximum Protection, Maximum Availability, and Maximum Performance.
- Reinstate a former primary using Flashback Database and DGMGRL.
- Identify when a standby must be rebuilt instead of reinstated.
- Recover bystander standbys disabled after a failover.
- Verify role-based services, listeners, application pools, and workloads.
- Build a drill plan covering switchover, failover, reinstate, and failback.
- Measure RTO/RPO, capture evidence, and refine runbooks after each drill.

> **Example Scope:** Examples use Oracle Database 19c and Data Guard Broker. Database names are illustrative: PROD_SITE is the initial primary, DR_SITE is the physical standby, and REPORT_SITE is a secondary standby. Replace them with your actual DB_UNIQUE_NAME, service names, and configuration. Never execute role-transition commands in production without change approval, a runbook, and an assigned coordinator.

## 1. Data Guard Model and Database Roles

Data Guard maintains one or more standby copies of a primary database. Redo generated on the primary is shipped to standbys via redo transport services and applied using Redo Apply or SQL Apply depending on standby type.

### 1.1. Primary Database

The primary database handles the application's read/write transactions. Modifications are recorded in redo. Redo transport services ship redo to configured standbys.

### 1.2. Physical Standby

A physical standby maintains a physical copy of the primary by applying redo. With a physical standby, Redo Apply can run in real-time apply mode when appropriate standby redo logs exist.

A physical standby is generally the preferred target for switchover/failover because it holds a complete physical copy of the database and fits a wide range of role-transition scenarios.

### 1.3. Logical Standby

A logical standby applies redo using SQL Apply. It may differ structurally or in data from the primary within supported boundaries. Certain objects or operations may not be processed by SQL Apply identically to a physical standby.

Switchover/failover to a logical standby has additional consequences for other physical/snapshot standbys. Physical and snapshot standbys in the configuration may be disabled by Broker and require recreation from the new primary before resuming standby operation.

### 1.4. Snapshot Standby

A snapshot standby is opened read/write for testing or temporary work. Redo received from the primary is retained to be applied once the snapshot standby converts back to a physical standby.

A snapshot standby cannot be the target of a switchover or fast-start failover. For a manual failover, Broker can convert the snapshot standby back to a physical standby and apply accumulated redo before failing over.

### 1.5. Bystander Standby

A bystander standby is a standby not directly involved as the target of a role transition. After a switchover, bystander standbys typically continue operating and begin receiving redo from the new primary. After a failover, some bystander standbys may become disabled if they have already applied redo beyond the point possessed by the new primary.

### 1.6. Far Sync and Observer

- A Far Sync instance receives redo from the primary and forwards it to standbys; it is not a database and cannot become primary.
- An Observer is a monitoring process used in Fast-Start Failover. The Observer monitors primary and target standby to decide when to trigger automatic failover per configured conditions.

## 2. How Switchover, Failover, and Reinstate Differ

| Criterion | Switchover | Failover | Reinstate |
| --- | --- | --- | --- |
| Objective | Planned role reversal | Promote standby to primary on primary failure | Return former primary as a standby |
| Former primary state | Operational and coordinating transition | Unreachable or halted | Repaired and able to start in MOUNT |
| Data | Zero data loss on proper procedural switchover | Possible data loss | Resynchronizes with new primary |
| Timing | Planned maintenance, migration, testing | Disaster or primary outage | Post-failover |
| Broker command | SWITCHOVER TO | FAILOVER TO | REINSTATE DATABASE |
| Key prerequisite | Healthy primary/standby, low redo lag | Good target selection, former primary fenced | Sufficient flashback logs and connectivity to new primary |

### 2.1. Switchover Is Not a Controlled Failover

Switchover is a coordinated role reversal between two cooperating databases. The former primary transitions to standby and the target standby becomes primary. Broker coordinates both sides, updates configuration, and manages appropriate services.

Failover is an incident recovery decision. The former primary may be unable to participate. The standby becomes primary based on redo already received and applied. Bringing the former primary back afterward is a separate procedure.

### 2.2. Reinstate Is Not Switchback

Reinstate returns the former primary as a standby of the new primary. Once the former primary is reinstated, another switchover can be executed to move the workload back to the original site. That second reversal is switchback/failback.

The proper post-failover sequence is typically:

~~~text
Initial primary fails
          |
          v
Selected standby fails over
          |
          v
Standby becomes new primary
          |
          v
Repair and reinstate former primary
          |
          v
Former primary runs again as standby
          |
          v
Synchronize redo and verify configuration
          |
          v
Planned switchover if switchback is desired
~~~

## 3. Role of Data Guard Broker

Data Guard Broker centralizes Data Guard configuration management and orchestrates role transitions. DGMGRL is the command-line interface for managing Broker.

### 3.1. Benefits

Broker helps:

- Check overall configuration status.
- Display transport lag and apply lag.
- Validate databases before role transitions.
- Coordinate switchover/failover across multiple databases.
- Start redo transport and Redo Apply after role changes.
- Coordinate with Oracle Clusterware and Global Data Services for service management.
- Automate database reinstatement when Flashback Database prerequisites are met.

### 3.2. Checking Broker

Connect to DGMGRL using an account with appropriate SYSDBA or SYSDG privileges:

~~~text
$ dgmgrl
DGMGRL> CONNECT sys@PROD_SITE;
DGMGRL> SHOW CONFIGURATION;
~~~

Inspect an individual database:

~~~text
DGMGRL> SHOW DATABASE VERBOSE 'PROD_SITE';
DGMGRL> SHOW DATABASE VERBOSE 'DR_SITE';
~~~

Check lag:

~~~text
DGMGRL> SHOW CONFIGURATION LAG;
~~~

Interpret results alongside database state and broker errors. Configuration status SUCCESS is a good sign, yet specific targets must still be validated before transitioning roles.

### 3.3. Key States

| State | Operational Meaning |
| --- | --- |
| TRANSPORT-ON | Primary is shipping redo per Broker state |
| APPLY-ON | Standby is running apply services per Broker state |
| APPLY-OFF | Redo Apply is stopped |
| SUCCESS | Broker reports no errors within configuration scope |
| WARNING | Warnings present that must be read and evaluated |
| ERROR | Errors requiring resolution prior to role transition |

For switchover, Broker requires the primary to be enabled and in TRANSPORT-ON state, and the target standby to be enabled and in APPLY-ON state.

### 3.4. Do Not Mix Broker with Manual SQL Operations

When Broker manages a configuration, use DGMGRL for role transitions. Do not manually run `ALTER DATABASE` role-transition statements on a database while Broker coordinates operations. Manual interventions can leave Broker metadata out of sync with actual roles.

If an environment does not use Broker, manual SQL procedures follow distinct syntax and ordering by standby type, Oracle release, and architecture. Follow the exact Data Guard Concepts and Administration chapter for that release and never mix the two runbooks.

## 4. Protection Modes, Redo Transport, and RPO

Data loss exposure during failover depends on how redo is transmitted and acknowledged.

### 4.1. Maximum Protection

Maximum Protection targets zero data loss. The primary requires at least one synchronized standby receiving redo via appropriate synchronous transport. If the primary cannot ship redo to a required standby, the primary shuts down rather than continuing transactions without configured protection.

### 4.2. Maximum Availability

Maximum Availability uses synchronous redo transport to target zero data loss while a synchronous standby is available. If the standby temporarily cannot acknowledge redo, the primary continues in a degraded protection state per protection mode mechanics.

### 4.3. Maximum Performance

Maximum Performance typically uses asynchronous redo transport to minimize impact on primary performance. If the primary fails, the standby may not have received the latest redo, creating potential data loss.

### 4.4. Comparison

| Protection Mode | Objective | Risk When Standby Stops Receiving Redo |
| --- | --- | --- |
| Maximum Protection | Prioritizes zero data loss | Primary may halt to uphold protection guarantee |
| Maximum Availability | Zero data loss when sync available; prioritizes availability | May run in degraded state during standby disconnect |
| Maximum Performance | Prioritizes primary performance | Untransported redo may be lost on failover |

Never assume zero data loss for a specific failover merely from the protection mode name. Verify transport mode, destination attributes, shipped redo, received redo, and applied redo.

### 4.5. Transport Lag and Apply Lag

- Transport lag: redo delay from primary to standby.
- Apply lag: apply delay on the standby relative to the primary.

A standby with low transport lag but high apply lag may still need time to apply received redo. For switchover, pick the standby with the least unapplied redo to shorten transition duration. For failover, prioritize the standby with the lowest transport lag to minimize potential data loss.

Check in the database:

~~~sql
SELECT
    name,
    value,
    unit,
    time_computed,
    datum_time
FROM v$dataguard_stats
WHERE name IN ('transport lag', 'apply lag', 'apply finish time');
~~~

If `datum_time` is stale or lag stops updating, do not rely on that figure as real-time state. Check networking, redo transport, and broker logs.

### 4.6. RPO Is More Than Displayed Transport Lag

RPO is the amount of data an organization accepts losing from the time of failure. Transport lag is an important operational indicator, yet actual RPO also depends on:

- When transactions committed on the primary.
- Redo transmitted and durably written at the standby.
- Whether redo is applied or resides in standby redo logs/archive logs.
- Primary and network state at failover time.
- The type of failover executed.

Never report RPO using a stale lag value without recording measurement timestamps.

## 5. Preconditions Before Switchover

Switchover is a planned change. Thorough preparation prevents situations where the former primary fails to run as a standby after role reversal.

### 5.1. Check Configuration Health

~~~text
DGMGRL> SHOW CONFIGURATION;
DGMGRL> SHOW CONFIGURATION LAG;
DGMGRL> SHOW DATABASE VERBOSE 'PROD_SITE';
DGMGRL> SHOW DATABASE VERBOSE 'DR_SITE';
~~~

Resolve any ERRORs and evaluate every WARNING. Do not inspect only overall configuration status; verify both the primary and the target standby explicitly.

### 5.2. Validate the Target

~~~text
DGMGRL> VALIDATE DATABASE 'DR_SITE';
~~~

Output indicates:

- Database role.
- Current primary database.
- Ready for Switchover.
- Ready for Failover.
- Warnings about standbys or settings that may become disabled after role transition.

Use VERBOSE for deeper check details:

~~~text
DGMGRL> VALIDATE DATABASE VERBOSE 'DR_SITE';
~~~

### 5.3. Redo Lag Must Be Low

Check:

~~~text
DGMGRL> SHOW CONFIGURATION LAG;
DGMGRL> SHOW DATABASE 'DR_SITE';
~~~

Choose a physical standby with the lowest unapplied redo whenever possible. Never start a switchover while apply lag is climbing steadily or redo transport is failing.

### 5.4. Standby Redo Logs

The former primary becomes a standby after switchover. Therefore, prepare the primary as if it were a standby:

- Standby redo logs matching online redo log counts and sizes.
- Properly configured redo transport properties.
- Destinations capable of shipping redo after role reversal.
- Required files and paths present.

Do not inspect only the current standby. Both databases must be ready for their reversed roles.

### 5.5. Check Broker Properties

Properties that affect redo transport and apply:

- LogXptMode.
- NetTimeout.
- StandbyArchiveLocation.
- StandbyAlternateLocation.
- RedoRoutes.
- DelayMins.

Broker disallows switchover to a standby with a non-zero apply delay. If DelayMins is used operationally, schedule removing the delay per runbook before switchover.

### 5.6. Temporary Files

Ensure tempfiles corresponding to temporary tablespaces exist on the target standby. Verify tempfiles on both sides since roles will reverse.

### 5.7. Services and Application Connectivity

Verify:

- Role-based services configured for PRIMARY/STANDBY.
- Oracle Clusterware or Oracle Restart managing services properly.
- Listeners, SCAN, DNS, and connect descriptors pointing correctly.
- Application pools able to detect closed sessions and reconnect.
- Job schedulers and batch processes prevented from continuing writes to the old site.

### 5.8. Fast-Start Failover Enabled

If FSFO is enabled:

- Switchover may only target the preconfigured target standby.
- Target must be synchronized or within the lag limit per protection mode.
- Inspect the Observer and FSFO conditions prior to role transition.

### 5.9. Confirm the Change Window

Before starting:

- Approved change ticket and assigned coordinator.
- Application owners notified.
- Appropriate maintenance window secured.
- Abort/rollback criteria defined.
- Access verified for both sites.
- Sufficient DBA, systems, network, and application staff engaged.

## 6. Executing Switchover with DGMGRL

Assume:

- PROD_SITE is the initial primary.
- DR_SITE is the target physical standby.
- After transition, DR_SITE becomes primary and PROD_SITE becomes physical standby.

### 6.1. Pre-Transition Checks

~~~text
DGMGRL> CONNECT sys@PROD_SITE;
DGMGRL> SHOW CONFIGURATION;
DGMGRL> SHOW CONFIGURATION LAG;
DGMGRL> SHOW DATABASE VERBOSE 'PROD_SITE';
DGMGRL> SHOW DATABASE VERBOSE 'DR_SITE';
DGMGRL> VALIDATE DATABASE 'PROD_SITE';
DGMGRL> VALIDATE DATABASE 'DR_SITE';
~~~

Confirm primary is TRANSPORT-ON, standby is APPLY-ON, and target reports `Ready for Switchover: Yes`.

### 6.2. Execute Switchover

~~~text
DGMGRL> SWITCHOVER TO 'DR_SITE';
~~~

Broker coordinates:

1. Checking primary and target standby states.
2. Transitioning the former primary to standby role.
3. Updating Broker configuration.
4. Restarting the former primary if converting to a physical standby.
5. Opening the new primary in READ WRITE mode.
6. Starting redo transport from the new primary.
7. Starting Redo Apply on the new standby.
8. Verifying role-transition status.

The new primary does not require a restart like the former primary when converting to physical standby.

### 6.3. Post-Switchover Verification

~~~text
DGMGRL> SHOW CONFIGURATION;
DGMGRL> SHOW DATABASE VERBOSE 'DR_SITE';
DGMGRL> SHOW DATABASE VERBOSE 'PROD_SITE';
~~~

Expected state:

- DR_SITE has role PRIMARY.
- PROD_SITE has role PHYSICAL STANDBY.
- Configuration reports zero errors.
- Redo transport from DR_SITE to PROD_SITE is active.
- Redo Apply on PROD_SITE is running.

Verify directly in each database:

~~~sql
SELECT
    db_unique_name,
    database_role,
    open_mode,
    protection_mode,
    switchover_status
FROM v$database;
~~~

On the new primary, expect `DATABASE_ROLE = PRIMARY` and `OPEN_MODE = READ WRITE`. On the physical standby, expect `DATABASE_ROLE = PHYSICAL STANDBY` and an open state matching configuration, such as MOUNTED or READ ONLY WITH APPLY.

### 6.4. Verify Application Services

Do not check only database roles. Also:

1. Confirm transactional services run on the new primary.
2. Connect applications using production connect descriptors.
3. Execute a controlled write test transaction.
4. Read back the committed data.
5. Verify redo is shipped and applied on the new standby.
6. Check batch jobs, schedulers, monitoring, and backup jobs.

### 6.5. Planned Switchback

Once DR_SITE is primary and PROD_SITE runs cleanly as standby, you can transition back:

~~~text
DGMGRL> VALIDATE DATABASE 'PROD_SITE';
DGMGRL> SWITCHOVER TO 'PROD_SITE';
DGMGRL> SHOW CONFIGURATION;
~~~

Switch back only when both databases are synchronized, stable, and within an approved change window. Do not rush a switchback merely because the new primary sits at the DR site.

## 7. Failover: When Must a Standby Become Primary?

Failover is used when the primary database fails and cannot be recovered within an acceptable timeframe.

Examples:

- Prolonged power outage at the primary site.
- Primary storage failure.
- Severe corruption on the primary database.
- Primary infrastructure cannot be restored within RTO.
- Primary database cannot be opened or recovered in time.

Never fail over merely because an application session timed out or a single RAC node failed if the database continues serving. Scope the outage before changing roles.

### 7.1. Split-Brain Risk

Split-brain occurs when both the former primary and the new primary open READ WRITE and accept independent transactions. The two databases then diverge into incompatible transaction histories that cannot simply be merged.

Before manual failover:

- If the former primary is still reachable, shut down the database per procedure.
- If unreachable, fence it at the infrastructure layer: power, cluster, network, or storage per design.
- Confirm applications cannot write to the former primary.
- Only after ensuring the former primary cannot accept further transactions should failover proceed.

Never treat a standby's inability to reach the primary as proof the primary is dead. A network partition can leave both sites running independently.

### 7.2. Selecting the Target Standby

When multiple standbys exist:

- Prioritize the standby with the lowest transport lag.
- Check apply lag and Redo Apply state.
- Prefer a physical standby where appropriate.
- Check for apply errors, corruption, or archive gaps.
- Verify CPU, memory, storage, and network capacity at the site about to become primary.

Never pick a target solely because it is closer to operators or labeled DR.

### 7.3. Validating Failover Readiness

~~~text
DGMGRL> SHOW CONFIGURATION;
DGMGRL> SHOW DATABASE VERBOSE 'DR_SITE';
DGMGRL> VALIDATE DATABASE 'DR_SITE';
~~~

VALIDATE DATABASE may report Ready for Failover and emit warnings if the primary is still running. During failover, assess the former primary's actual state and split-brain risk.

## 8. Complete Failover vs. Immediate Failover

Data Guard Broker supports two manual failover modes.

### 8.1. Complete Failover

Complete failover is the default and Oracle-recommended choice. Broker waits for the standby to apply remaining usable unapplied redo before transitioning the database to primary.

Command:

~~~text
DGMGRL> FAILOVER TO 'DR_SITE';
~~~

General steps:

1. Confirm the target standby is enabled.
2. Wait to apply remaining available redo.
3. Stop Redo Apply/SQL Apply.
4. Transition the standby to primary.
5. Open the new primary READ WRITE.
6. Start redo transport to remaining eligible standbys.
7. Evaluate whether bystander standbys can continue or require reinstatement/re-creation.

Complete failover strives to recover the maximum possible redo. It may achieve zero data loss if redo transport already shipped all redo, though it does not guarantee zero data loss across all protection/transport configurations.

### 8.2. Immediate Failover

Immediate failover does not wait to apply remaining redo. Broker stops Redo Apply/SQL Apply immediately and promotes the standby to primary.

Command:

~~~text
DGMGRL> FAILOVER TO 'DR_SITE' IMMEDIATE;
~~~

This carries higher data-loss risk. Oracle recommends using it only when complete failover cannot succeed or in specific documented error scenarios, such as ORA-752 or ORA-600 [3020] caused by confirmed lost writes.

Immediate failover also disables other databases in the configuration; they must be reinstated or re-created before resuming standby duty for the new primary.

### 8.3. Comparison

| Criterion | Complete | Immediate |
| --- | --- | --- |
| Applies remaining redo | Yes, if available and applicable | Does not wait for additional apply |
| Duration | May take longer due to apply backlog | Faster |
| Data loss | Potentially zero depending on redo transport | Commonly incurs data loss risk |
| Bystander standbys | Broker evaluates continued viability | All other databases become disabled |
| Choice | Default, preferred | Use only with clear technical justification |

Never use IMMEDIATE merely to save a few minutes if complete failover can finish.

## 9. Executing Manual Failover with DGMGRL

Assume PROD_SITE has failed and DR_SITE is the chosen physical standby.

### 9.1. Confirm Former Primary Is Fenced

This is a mandatory runbook step. If the former primary is still running, ensure it can no longer accept transactions before promoting DR_SITE to primary.

### 9.2. Connect to Target Standby

Oracle instructs connecting DGMGRL to the chosen target standby to execute failover:

~~~text
$ dgmgrl
DGMGRL> CONNECT sys@DR_SITE;
DGMGRL> SHOW CONFIGURATION;
DGMGRL> VALIDATE DATABASE 'DR_SITE';
~~~

### 9.3. Execute Complete Failover

~~~text
DGMGRL> FAILOVER TO 'DR_SITE';
~~~

Only when complete failover cannot succeed and conditions are verified should you consider:

~~~text
DGMGRL> FAILOVER TO 'DR_SITE' IMMEDIATE;
~~~

### 9.4. Verify the New Primary

~~~text
DGMGRL> SHOW CONFIGURATION;
DGMGRL> SHOW DATABASE VERBOSE 'DR_SITE';
~~~

SQL:

~~~sql
SELECT
    db_unique_name,
    database_role,
    open_mode,
    protection_mode
FROM v$database;
~~~

Expect DR_SITE to report `DATABASE_ROLE = PRIMARY` and `OPEN_MODE = READ WRITE`.

### 9.5. Verify Post-Failover Data Protection

After manual failover, if the previous protection mode was Maximum Protection, Broker downgrades protection mode to Maximum Performance. DBAs must check the new mode and plan restoring protection levels once standbys are re-established.

Do not assume the new primary has full disaster protection immediately after failover. If remaining standbys are disabled or unsynchronized, the configuration operates in degraded protection.

### 9.6. Transition Application Services

Once the new database opens READ WRITE:

- Start role-based services on the new primary.
- Ensure listeners and connect descriptors route to the new site.
- Allow application pools to establish fresh connections.
- Verify read and write requests.
- Confirm schedulers, batch processes, and jobs are not concurrently running on the old primary.
- Record the timestamp when the application resumes service.

## 10. Reinstating the Former Primary

After failover, the former primary cannot simply start READ WRITE and rejoin the configuration. It may reside on a different redo branch from the new primary.

Reinstatement brings the former database back into a state suitable to act as standby for the new primary.

### 10.1. Reinstatement Prerequisites

For Broker reinstatement to succeed:

- Flashback Database was enabled on the database to be reinstated prior to failover.
- Sufficient flashback logs exist to flash back to the required point.
- The former database can start in MOUNT state.
- The former database has network connectivity to the new primary.
- Broker configuration still recognizes the database and can coordinate the operation.

Oracle recommends enabling Flashback Database on all databases so standbys disabled after role transitions can be recovered quickly.

### 10.2. ORA-16661 State

If a database is eligible for reinstatement, Broker may report:

~~~text
ORA-16661: the standby database needs to be reinstated
~~~

This indicates the database must be reinstated before it can resume operating as a managed standby.

### 10.3. Bring the Former Database to MOUNT

On the former primary's host, after confirming no READ WRITE instance remains active:

~~~sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
~~~

In RAC environments, follow Clusterware/SRVCTL procedures and ensure all old instances are handled properly. Never start the former primary READ WRITE after failover.

### 10.4. Run REINSTATE DATABASE

Connect DGMGRL to a database in the configuration other than the one being reinstated:

~~~text
DGMGRL> CONNECT sys@DR_SITE;
DGMGRL> REINSTATE DATABASE 'PROD_SITE';
~~~

Broker uses Flashback Database to return PROD_SITE to a compatible state and configure it as a standby of DR_SITE. Broker automatically enables the database upon successful reinstatement.

### 10.5. Post-Reinstate Verification

~~~text
DGMGRL> SHOW CONFIGURATION;
DGMGRL> SHOW DATABASE VERBOSE 'PROD_SITE';
DGMGRL> SHOW DATABASE VERBOSE 'DR_SITE';
~~~

Expected state:

- DR_SITE remains PRIMARY.
- PROD_SITE becomes PHYSICAL STANDBY (if the pre-failover standby was physical).
- Broker resumes managing PROD_SITE.
- Redo transport from DR_SITE to PROD_SITE operates.
- Redo Apply on PROD_SITE runs and lag decreases.

### 10.6. Reinstate Does Not Always Succeed

If Flashback Database was disabled prior to failover or flashback logs are insufficient, Broker cannot reinstate the database. The database may transition to:

~~~text
ORA-16795: the standby database needs to be re-created
~~~

Rebuild the standby from a copy of the new primary and re-enable it in the Broker configuration.

### 10.7. Cases Where Reinstatement Is Prohibited

Do not attempt to reinstate the former primary if the failover target encountered ORA-752 or ORA-600 [3020] related to lost writes. Per Oracle guidance, the former database must be re-created as a standby from the new primary.

Additionally, if multiple role changes occurred before restarting the former database, it may no longer qualify for reinstatement and must be rebuilt.

## 11. Rebuilding the Standby When Reinstatement Is Not Possible

When flashback logs are insufficient or the databases have diverged, rebuild the standby from the new primary.

### 11.1. Why Rebuild from the New Primary?

After failover, the new primary is the authoritative data source. The former primary may contain transactions committed before failover that do not exist on the new primary, or sit on an incompatible redo branch.

Rebuilding from the new primary realigns the entire database to the current primary's timeline.

### 11.2. Rebuild Options

Depending on the environment, DBAs can:

- Use `RMAN DUPLICATE FOR STANDBY`.
- Restore a backup of the new primary and recover.
- Use a physical standby creation method suited to Oracle version and storage.
- Reconfigure redo transport and Broker properties.

Never manually copy a handful of datafiles and open the database as a standby. Ensure control files, incarnation, redo threads, password files, parameter files, standby redo logs, and archive destinations are properly aligned.

### 11.3. Re-Enabling in Broker

Once the standby is rebuilt and its role is verified:

~~~text
DGMGRL> ENABLE DATABASE 'PROD_SITE';
DGMGRL> SHOW DATABASE VERBOSE 'PROD_SITE';
DGMGRL> SHOW CONFIGURATION;
~~~

Enable only after the database is properly configured as a standby of the new primary. If Broker still reports ORA-16795, complete the full re-creation procedure per documentation rather than repeatedly running ENABLE.

## 12. Bystander Standbys After Failover

Failover impacts not only the former primary and target standby. Other standbys in the configuration can also become disabled.

### 12.1. Why Bystanders Become Disabled

A bystander standby may have applied redo ahead of the point applied by the target standby before becoming the new primary. It then cannot continue receiving redo from the new primary along the same timeline.

Broker disables that database to prevent applying redo on a diverged branch.

### 12.2. States Requiring Action

- ORA-16661: requires reinstatement.
- ORA-16795: requires standby re-creation.

### 12.3. Reinstating Bystanders

If Flashback Database is enabled with sufficient logs, reinstate the bystander via Broker:

~~~text
DGMGRL> REINSTATE DATABASE 'REPORT_SITE';
~~~

If reinstatement fails, rebuild the standby from the new primary and re-enable it in Broker.

### 12.4. Verifying the Entire Configuration

~~~text
DGMGRL> SHOW CONFIGURATION;
DGMGRL> SHOW DATABASE VERBOSE 'PROD_SITE';
DGMGRL> SHOW DATABASE VERBOSE 'REPORT_SITE';
~~~

Never treat failover as DR-complete merely because the new primary is open READ WRITE. Restore at least one healthy standby and verify redo apply.

## 13. Fast-Start Failover

Fast-Start Failover (FSFO) automatically promotes a standby to primary when the Observer and Broker detect configured failover conditions.

### 13.1. Components

- Primary database.
- Preconfigured target standby database.
- Data Guard Broker.
- Observer process.
- Network connectivity among components.

### 13.2. Differences from Manual Failover

Manual failover is decided and invoked by a DBA via `DGMGRL FAILOVER`. FSFO is triggered automatically by the Observer based on thresholds, protection mode, lag limits, and configured conditions.

### 13.3. Inspecting FSFO

~~~text
DGMGRL> SHOW FAST_START FAILOVER;
DGMGRL> SHOW CONFIGURATION;
~~~

Check readiness via SQL:

~~~sql
SELECT
    database_role,
    fs_failover_status,
    fs_failover_current_target,
    fs_failover_observer_present
FROM v$database;
~~~

Column names can vary by release; consult the V$DATABASE reference for your actual database.

### 13.4. Observe-Only Mode

FSFO provides an observe-only mode to monitor failover triggers without performing a role change:

~~~text
DGMGRL> ENABLE FAST_START FAILOVER OBSERVE ONLY;
~~~

In this mode, Broker/Observer logs whenever failover conditions are met and records what action would have been taken. It does not change roles or alter application workloads.

This is useful for rehearsing and validating Observer detection before enabling live FSFO. However, observe-only does not replace an actual failover test in an approved environment.

### 13.5. Auto Reinstate

FSFO can automatically reinstate the former primary under certain conditions if Flashback Database and configuration allow. The `FastStartFailoverAutoReinstate` property controls this behavior.

Do not assume every FSFO automatically reinstates. User-defined conditions, Observer disconnects, multiple role changes, or missing flashback logs can prevent automatic reinstatement.

## 14. Application Services After Role Transition

Transitioning database roles does not automatically ensure applications connect to the right place.

### 14.1. Role-Based Services

Transactional services are normally configured to run only when the database holds the PRIMARY role. Read-only reporting services may run on primary or standby depending on design.

After switchover/failover, Oracle Clusterware and Broker coordinate starting services matching the new roles.

### 14.2. Listeners and Connect Descriptors

Verify:

- Service names remain intact.
- DNS or SCAN resolves to the new site.
- Listeners register services properly.
- Application TNS aliases do not hardcode old site addresses.
- Firewalls and network routes permit connections.

### 14.3. Connection Pools

Sessions connected to the old primary may drop during role transition. Applications must:

- Detect connection failures.
- Open new connections to the primary service.
- Retry with bounded limits.
- Never blindly retry non-idempotent DML.
- Handle indeterminate transaction outcomes.

### 14.4. Application Continuity and TAF

Application Continuity, Transparent Application Failover, and Fast Application Notification can aid session recovery or reconnection depending on architecture, drivers, service configuration, and transaction types.

Never assume every transaction replays safely. Applications still require idempotency, transaction identifiers, and handling for cases where the client does not know whether a commit succeeded.

### 14.5. Post-Transition Service Verification

At minimum, perform:

1. Connect via the production service.
2. Read data.
3. Write a controlled test transaction.
4. Confirm commit succeeded.
5. Verify redo shipped to the new standby.
6. Verify standby applied redo.
7. Check job schedulers and batch ownership.

## 15. Data Guard Drill Planning

A thorough drill plan tests databases, networks, applications, and human operators. The goal is not merely proving DGMGRL commands run, but proving service actually recovers within RTO/RPO.

### 15.1. Drill Objectives

- Verify switchover completes with zero data loss.
- Verify failover promotes the standby within target RTO.
- Measure potential data loss under each protection/transport mode.
- Verify application services shift to the new site.
- Verify the former primary can be reinstated.
- Verify bystander standbys resume or are rebuilt properly.
- Test communication across DBA, systems, network, and application teams.
- Update runbooks based on actual measured results.

### 15.2. Defining Scope

Before a drill, specify:

- Which databases and services are in scope.
- Which site is primary and which is DR.
- Which physical/logical/snapshot standbys participate.
- Whether RAC, Far Sync, or FSFO are involved.
- Which applications will be affected.
- Which jobs/batches must be paused or rescheduled.
- Whether the drill exercises planned switchover, manual failover, or FSFO.

### 15.3. Drill Roles

| Role | Responsibilities |
| --- | --- |
| Incident/Exercise Commander | Coordinates, makes go/no-go calls, maintains timeline |
| DBA Lead | Checks Broker, executes role transitions, verifies databases |
| Infrastructure Lead | Networking, hosts, storage, cluster, fencing |
| Application Lead | Services, connection pools, transaction validation |
| Observer/Recorder | Logs timestamps, outputs, errors, and RTO/RPO metrics |
| Business Owner | Confirms disruption tolerance and business data integrity |

### 15.4. Defining Success Criteria

Examples:

| Metric | Sample Criterion |
| --- | --- |
| Switchover | Completes within change window with zero data loss |
| Failover RTO | Application resumes serving within 5 minutes |
| Failover RPO | No more than 30 seconds of committed transactions lost |
| Reinstate | Former primary returns as standby within 60 minutes |
| Apply lag | Returns within target threshold within 10 minutes post-transition |
| Application health | Read/write tests succeed on new service |
| Broker | Configuration returns to SUCCESS state |

These numbers are examples only. Business owners must approve real RTO/RPO targets for each application.

## 16. Switchover Drills

Switchover drills carry lower risk than failover drills because both databases cooperate and roles can be reversed back cleanly.

### 16.1. Before the Drill

- Pick a low-traffic date/time.
- Notify application owners.
- Check configuration and lag.
- Validate primary and standby.
- Check standby redo logs on both databases.
- Check services and client routing.
- Capture baseline application latency/throughput.
- Record an SCN or transaction marker to verify zero data loss.

### 16.2. Execution

~~~text
DGMGRL> SHOW CONFIGURATION;
DGMGRL> SHOW CONFIGURATION LAG;
DGMGRL> VALIDATE DATABASE 'DR_SITE';
DGMGRL> SWITCHOVER TO 'DR_SITE';
~~~

### 16.3. Verification

- DR_SITE is PRIMARY.
- PROD_SITE is PHYSICAL STANDBY.
- Redo transport and apply are running.
- Application services run on DR_SITE.
- Read/write test transactions succeed.
- Zero test data missing.

### 16.4. Switchback

Once verified:

~~~text
DGMGRL> VALIDATE DATABASE 'PROD_SITE';
DGMGRL> SWITCHOVER TO 'PROD_SITE';
DGMGRL> SHOW CONFIGURATION;
~~~

Confirm the primary returns to the original site and the standby continues applying redo.

## 17. Failover Drills

Failover drills carry higher impact because they simulate primary loss and create a new primary. Execute only in lab/staging environments or during approved production exercises with an explicit fencing plan.

### 17.1. Preparation

- Identify the target standby.
- Check transport lag and apply lag.
- Verify Flashback Database across members.
- Check Observer/FSFO state if applicable.
- Record transaction markers.
- Record start timestamp.
- Prepare primary fencing commands.
- Define service and DNS cutover steps.
- Designate failover decision authority.

### 17.2. Simulating Failure

In a lab, simulate site/network loss under controlled scripts. In production, never induce network partitions or power off hosts without formal approval and split-brain prevention mechanisms.

### 17.3. Fencing the Former Primary

Ensure the former primary cannot accept writes. If the database remains reachable, shut it down per procedure. Otherwise, apply infrastructure/network/cluster fencing.

### 17.4. Failover

~~~text
DGMGRL> CONNECT sys@DR_SITE;
DGMGRL> VALIDATE DATABASE 'DR_SITE';
DGMGRL> FAILOVER TO 'DR_SITE';
~~~

Use IMMEDIATE only if complete failover is unfeasible and the technical decision is approved:

~~~text
DGMGRL> FAILOVER TO 'DR_SITE' IMMEDIATE;
~~~

### 17.5. Verifying the New Primary

- DATABASE_ROLE = PRIMARY.
- OPEN_MODE = READ WRITE.
- Application services ready.
- Read/write tests succeed.
- Transaction markers and committed data verified.
- Record last present transaction to estimate RPO.

### 17.6. Restoring DR

- Check whether PROD_SITE can be reinstated.
- With sufficient flashback logs, run REINSTATE DATABASE.
- Otherwise, rebuild the standby from DR_SITE.
- Recover bystander standbys.
- Check transport/apply lag.
- Restore protection mode once configuration prerequisites are satisfied.

### 17.7. Concluding the Drill

Never conclude a drill immediately when the application runs on DR_SITE. Verify the configuration has a healthy standby and data protection is restored; otherwise, the organization is running on an unprotected single primary.

## 18. Drill Scenarios and Verification Criteria

| Scenario | Simulated Impact | Expected Outcome |
| --- | --- | --- |
| Planned switchover | Planned move from primary to standby | Role reversal, application reconnect, zero data loss |
| Primary host failure | Loss of primary host | Failover to chosen standby, application resumes |
| Network isolation | Loss of cross-site connectivity | Proper fencing, zero split-brain |
| Redo transport lag | Elevated transport lag | DBA picks right target and assesses RPO |
| Apply lag | Standby receives redo but applies slowly | Assess apply catch-up time before switchover |
| Immediate failover | Complete failover infeasible in lab | Measure data loss and handle bystander standbys |
| Former primary recovery | Former primary returns after failover | Properly reinstated or re-created |
| Observer outage | Observer disconnects | FSFO behaves per design |
| Application pool stale connections | Old sessions drop on role change | Pool reconnects and resolves transaction outcomes |
| Standby rebuild | Insufficient flashback logs | Re-create standby from new primary |

## 19. Measuring RTO and RPO

### 19.1. RTO

Recovery Time Objective is the maximum time the business tolerates to restore service.

Measure RTO by timestamps:

1. T0: failure begins.
2. T1: incident detected.
3. T2: failover decision approved.
4. T3: failover command finishes.
5. T4: new primary opens READ WRITE.
6. T5: application services ready.
7. T6: business transaction succeeds.

Service RTO is typically `T6 - T0`, not merely the duration of the `FAILOVER` command.

### 19.2. RPO

Recovery Point Objective is the amount of data the business accepts losing upon recovery.

To measure:

- Record timestamped/sequenced transaction markers before the drill.
- Record the last transaction committed on the old primary.
- After failover, locate the last transaction marker present on the new primary.
- Compare the missing time window or transaction count.
- Correlate with transport lag and redo state logged prior to failover.

Do not use SCN directly as a wall-clock timer. SCN helps determine ordering and recovery points, whereas time-based RPO reporting requires correlation with timestamps and transaction markers.

### 19.3. Result Tracking Table

| Milestone | Timestamp | Notes |
| --- | --- | --- |
| Primary outage |  |  |
| Incident detected |  |  |
| Failover approved |  |  |
| Failover started |  |  |
| New primary open |  |  |
| Application service ready |  |  |
| First successful write |  |  |
| Old primary reinstated |  |  |
| Standby apply caught up |  |  |

### 19.4. Additional Metrics

- Pre-incident transport lag.
- Pre-incident apply lag.
- Redo generation rate.
- Apply rate.
- Database startup duration.
- Service transition duration.
- Application pool reconnection time.
- Transaction retry count.
- Lost or indeterminate transactions.
- Reinstatement/re-creation duration.

## 20. Sample Drill Runbook

### Phase A — Pre-Check

~~~text
DGMGRL> SHOW CONFIGURATION;
DGMGRL> SHOW CONFIGURATION LAG;
DGMGRL> SHOW DATABASE VERBOSE 'PROD_SITE';
DGMGRL> SHOW DATABASE VERBOSE 'DR_SITE';
DGMGRL> VALIDATE DATABASE 'PROD_SITE';
DGMGRL> VALIDATE DATABASE 'DR_SITE';
~~~

SQL:

~~~sql
SELECT
    db_unique_name,
    database_role,
    open_mode,
    protection_mode
FROM v$database;

SELECT
    name,
    value,
    unit,
    time_computed,
    datum_time
FROM v$dataguard_stats
WHERE name IN ('transport lag', 'apply lag');
~~~

### Phase B — Planned Switchover

~~~text
DGMGRL> SWITCHOVER TO 'DR_SITE';
DGMGRL> SHOW CONFIGURATION;
~~~

### Phase C — Application Validation

- Connect via production service.
- Read data.
- Write transaction marker.
- Confirm commit.
- Confirm redo apply on the standby.

### Phase D — Switchback

~~~text
DGMGRL> VALIDATE DATABASE 'PROD_SITE';
DGMGRL> SWITCHOVER TO 'PROD_SITE';
DGMGRL> SHOW CONFIGURATION;
~~~

### Phase E — Standalone Failover Drill

In an approved failover drill environment:

1. Fence primary.
2. Connect to target standby.
3. Validate target.
4. Run complete failover.
5. Verify new primary.
6. Transition application services.
7. Measure RTO/RPO.
8. Reinstate former primary or re-create standby.
9. Check bystander standbys.
10. Confirm configuration has a healthy standby again.

Do not combine a switchover drill and a failover drill into a single run when their objectives, impacts, and approval criteria differ.

## 21. Troubleshooting

| Symptom | Possible Cause | Remediation |
| --- | --- | --- |
| VALIDATE DATABASE reports not ready for switchover | Transport/apply inactive or lag/errors | Check Broker status, archive gaps, redo transport, and apply |
| SWITCHOVER rejected | Primary not TRANSPORT-ON or target not APPLY-ON | Check ENABLED status and intended states |
| High standby apply lag | Redo backlog or insufficient apply resources | Wait for catch-up, check I/O/CPU and archive gaps |
| Non-zero DelayMins | Standby has an apply delay | Clear delay per plan before switchover |
| Former primary fails to start as standby | Missing SRLs, redo routes, or tempfiles | Check new-role settings and alert log |
| Complete FAILOVER fails | Apply error, lost-write error, or invalid target | Read alert/broker logs; do not blindly switch to IMMEDIATE |
| Immediate failover causes data loss | Unapplied redo skipped | Reconcile transaction markers and report RPO |
| ORA-16661 | Database needs reinstatement | Startup MOUNT and run REINSTATE DATABASE |
| ORA-16795 | Database needs re-creation | Re-create standby from new primary |
| REINSTATE fails | Flashback disabled/insufficient logs/network | Check flashback logs and connectivity; re-create if needed |
| Former primary remains open READ WRITE | Split-brain risk | Fence immediately and block application writes |
| Bystander standby disabled | Applied past new primary or due to immediate/logical failover | Reinstate or re-create |
| Configuration status WARNING | Warning present or member unsynchronized | Run SHOW DATABASE VERBOSE and read alert/broker logs |
| Application still connects to old site | DNS/service/pool not transitioned | Check role-based services, listeners, connect descriptors, and pools |
| Post-failover protection mode downgraded | Maximum Protection reset to Maximum Performance | Restore standby and re-raise protection mode once eligible |

## 22. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| Switchover and failover are identical | Switchover is planned role reversal; failover handles primary failure |
| Failover always loses data | Can be lossless if standby received all redo; depends on transport/protection |
| Complete failover is always zero data loss | It applies available received redo; it cannot apply untransmitted redo |
| Immediate failover is just a faster complete failover | It skips unapplied redo and can cause data loss |
| Reinstate means reopening the old primary | Reinstate turns the former primary into a standby of the new primary |
| Enabling Flashback Database guarantees reinstatement | Requires sufficient flashback logs, network, and Broker preconditions |
| ORA-16661 means the database is corrupted | It indicates the database needs reinstatement |
| ORA-16795 can be fixed immediately with ENABLE DATABASE | The database must be re-created first |
| Former primary can open READ WRITE after failover | Risks split-brain and diverged redo branches |
| Broker SUCCESS means the application works | Must verify services and actual transactions |
| Zero transport lag means zero lost transactions | Must account for commit timing, redo durability, and transaction outcomes |
| Completing failover restores DR | Standby protection and redo transport must still be restored |
| Switchover to a snapshot standby is supported | Must convert snapshot back to physical standby first |
| Any standby can be picked as failover target | Pick based on lag, type, health, and site capacity |

## 23. Pre-, During-, and Post-Transition Checklists

### Before Switchover

- [ ] Broker configuration healthy.
- [ ] Primary TRANSPORT-ON.
- [ ] Target standby APPLY-ON.
- [ ] Transport/apply lag within limits.
- [ ] VALIDATE DATABASE reports Ready for Switchover.
- [ ] Standby redo logs ready on both databases.
- [ ] DelayMins addressed.
- [ ] Tempfiles and redo routes verified.
- [ ] Service and client routing transition planned.
- [ ] Change window and coordinator confirmed.

### Before Failover

- [ ] Confirmed primary cannot recover in time.
- [ ] Former primary shut down or fenced.
- [ ] Target chosen with lowest eligible transport lag.
- [ ] Apply lag and redo backlog evaluated.
- [ ] Expected RPO assessed.
- [ ] Broker and alert logs inspected.
- [ ] Complete failover chosen by default.
- [ ] Immediate failover chosen only with approved technical justification.
- [ ] Application services and network routing ready.

### After Failover

- [ ] Target holds PRIMARY role and OPEN READ WRITE.
- [ ] Application services active on new primary.
- [ ] Test transaction succeeded.
- [ ] RTO/RPO recorded.
- [ ] Former primary state verified.
- [ ] Former primary reinstated or re-created.
- [ ] Bystander standbys handled.
- [ ] Redo transport and apply operating.
- [ ] Protection mode evaluated and restored per plan.
- [ ] Broker configuration back to healthy state.

## 24. Self-Check Questions

1. How does switchover differ from failover?
2. What problem does reinstate solve after a failover?
3. Why does switchover require both primary and standby to be healthy?
4. Why does the former primary need standby redo logs?
5. What do TRANSPORT-ON and APPLY-ON signify?
6. How does VALIDATE DATABASE help before a role transition?
7. Why choose a standby with low apply lag for switchover?
8. Why choose a standby with low transport lag for failover?
9. How do Maximum Protection, Maximum Availability, and Maximum Performance differ?
10. What does complete failover do with unapplied redo?
11. What risks does immediate failover carry?
12. Why must the former primary be fenced?
13. What does ORA-16661 mean?
14. What does ORA-16795 mean?
15. What are the key prerequisites for REINSTATE DATABASE to succeed?
16. When must a standby be re-created?
17. Why can a bystander standby become disabled after failover?
18. Why can manual failover switch Maximum Protection to Maximum Performance?
19. How does FSFO differ from manual failover?
20. What role does the Observer play?
21. Does observe-only mode perform an actual failover?
22. Why is a successful database role transition insufficient to declare the application recovered?
23. What role do role-based services play?
24. What must connection pools handle after failover?
25. From which point to which point is RTO measured?
26. How is RPO determined?
27. Why are transaction markers needed in failover drills?
28. Why must reinstatement be rehearsed?
29. After a failover, when is switchback safe?
30. What evidence should be preserved after a drill?

**Answer Hints:**

1. Switchover is planned role reversal; failover promotes a standby to primary due to primary failure.
2. Returns the former primary as a standby of the new primary.
3. Broker coordinates both databases to reverse roles without data loss.
4. Because the former primary becomes a standby and must receive redo.
5. Primary is shipping redo; standby is applying redo.
6. Verifies readiness, lag, errors, and role-transition prerequisites.
7. Minimizes time spent applying remaining redo before reversing roles.
8. Minimizes potential redo loss at the moment of primary failure.
9. They differ in priority between zero data loss and availability/performance.
10. Waits for and applies remaining usable received redo.
11. Skips unapplied redo, risks data loss, and disables other databases.
12. Prevents two primaries accepting transactions and causing split-brain.
13. Database needs to be reinstated.
14. Database needs to be re-created.
15. Flashback enabled prior to failover, sufficient logs, database in MOUNT, and network connectivity to new primary.
16. When flashback logs are insufficient, specific lost-write errors occurred, or reinstatement fails.
17. They may have applied redo past the new primary's point.
18. Broker resets protection mode after manual failover so the new primary can keep running.
19. Manual is decided by DBAs; FSFO is triggered automatically by Observer/Broker.
20. Monitors primary and target standby to trigger automatic failover.
21. No, it only logs conditions and intended actions.
22. Applications still require services, listeners, pools, and working transactions.
23. Automatically start services on the database holding the matching role.
24. Evict stale sessions, reconnect, and resolve indeterminate transaction outcomes.
25. From service disruption onset until business transactions succeed again.
26. Compare the last committed transaction against the last transaction present on the new primary.
27. To accurately measure retained vs. lost data.
28. Because the former primary must become a standby to restore DR protection.
29. Once the former primary is reinstated, the standby is synchronized, and the runbook permits.
30. DGMGRL outputs, alert/broker logs, timestamps, transaction markers, RTO/RPO, application tests, and errors.

## Oracle Documentation References

- [Oracle Database 19c Data Guard Broker — Switchover and Failover Operations](https://docs.oracle.com/en/database/oracle/oracle-database/19/dgbkr/using-data-guard-broker-to-manage-switchovers-failovers.html): concepts, prerequisites, switchover, complete/immediate failover, and reinstate.
- [Oracle Database 19c Data Guard Broker — Scenarios Using DGMGRL](https://docs.oracle.com/en/database/oracle/oracle-database/19/dgbkr/examples-using-data-guard-broker-DGMGRL-utility.html): operational examples of switchover and manual failover.
- [Oracle Database 19c Data Guard Broker — Troubleshooting](https://docs.oracle.com/en/database/oracle/oracle-database/19/dgbkr/troubleshooting-oracle-data-guard-broker.html): troubleshooting Broker and role-transition errors.
- [Oracle Database 19c Data Guard Concepts and Administration — Data Protection Modes](https://docs.oracle.com/en/database/oracle/oracle-database/19/sbydb/introduction-to-oracle-data-guard-concepts.html): protection modes, redo transport, and data protection capabilities.
- [Oracle Database 19c Data Guard Scenarios — Converting a Failed Primary into a Standby](https://docs.oracle.com/en/database/oracle/oracle-database/19/sbydb/examples-of-using-oracle-data-guard.html): Flashback Database and converting a failed primary into a standby.
- [Oracle Database 19c Database Reference — V$DATAGUARD_STATS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-DATAGUARD_STATS.html): transport lag and apply lag.
- [Oracle Database 19c Database Reference — V$DATABASE](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-DATABASE.html): database role, open mode, protection mode, and switchover status.

**Key Principle:** Switchover is a planned role reversal; failover is a recovery decision when the primary cannot continue; reinstate returns the former primary as a standby. Complete failover is the default because it applies remaining usable received redo; immediate failover skips unapplied redo and can cause data loss. Always fence the former primary before manual failover to prevent split-brain. Reinstate requires Flashback Database enabled prior to failover and sufficient flashback logs; otherwise, rebuild the standby from the new primary. A drill succeeds only when database roles, redo transport/apply, application services, RTO/RPO, and restored DR protection are all verified.
