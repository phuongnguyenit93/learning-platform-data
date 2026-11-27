# Data Guard Broker, Observer, and Automatic Failover Conditions

Oracle Data Guard maintains one or more standby databases to protect data and improve availability when the primary database fails. Data Guard Broker provides a centralized management layer to configure, monitor, and coordinate databases within a Data Guard configuration. Combining Broker with **Fast-Start Failover (FSFO)** and an **observer** process allows Oracle to automatically transition an eligible standby to primary without requiring a DBA to issue a failover command manually.

The three components play distinct roles:

- **Data Guard Broker:** manages the configuration, redo transport, Redo Apply, database states, and role transitions.
- **Observer:** a process outside the database that monitors connectivity and health of both primary and target standby; the master observer decides when to initiate FSFO.
- **Fast-Start Failover:** the Broker-coordinated mechanism that automatically transitions the target standby to primary when configured conditions are met.

Automatic failover does not simply promote a standby the moment a ping to the primary drops. Broker must confirm the primary is genuinely unavailable per configured criteria, the observer and standby must agree on state, the target standby must be sufficiently synchronized, and the configuration must guard against two sites acting as primary simultaneously.

This lesson focuses on Broker/observer architecture, preconditions enabling FSFO, choosing thresholds and lag limits, failover trigger conditions, status verification, and limitations to consider when deploying automatic failover in production.

## 1. What Is Data Guard Broker?

Data Guard Broker is the management framework for Oracle Data Guard environments. Broker stores configuration metadata and coordinates members such as the primary database, physical standbys, logical standbys, and far sync instances.

Broker offers two primary management interfaces:

- **DGMGRL:** a command-line interface to create, modify, validate, and operate the configuration.
- **Oracle Enterprise Manager Cloud Control:** a graphical management interface for supported operations and monitoring.

Broker uses the DMON process on member databases to manage the configuration. Databases must be configured for Broker operation, typically via the parameter:

~~~sql
ALTER SYSTEM SET DG_BROKER_START = TRUE SCOPE = BOTH;
~~~

This parameter must be set on databases participating in Broker according to environment requirements. Before enabling, inspect existing Data Guard parameters and connections to avoid disrupting a running configuration.

### 1.1 What Does Broker Manage?

Broker manages and monitors:

- The list of databases in the configuration and their current roles.
- Redo transport from primary to standbys.
- Redo Apply on physical standbys.
- Overall configuration protection mode.
- Transport lag and apply lag.
- Database-level and configuration-level properties.
- Switchover, manual failover, and Fast-Start Failover.
- Observer and automatic failover readiness status.
- Reinstatement of the former primary after FSFO when prerequisites are met.

Broker makes role transitions more consistent by orchestrating multiple steps across redo transport, apply services, and remaining standbys. However, Broker does not automatically resolve external application-tier components such as DNS, load balancers, connection pools, caches, or message queues. Those components must be designed to handle database role changes.

### 1.2 Broker Configuration and Database Members

A Broker configuration has a configuration name and one or more database members. Each database has a distinct DB_UNIQUE_NAME. DB_NAME may match between primary and physical standby, whereas DB_UNIQUE_NAME identifies each member uniquely.

Example topology:

~~~text
                  +----------------------+
                  |      Observer        |
                  |  DGMGRL process      |
                  +----------+-----------+
                             |
                   monitors both sites
                             |
           +-----------------+-----------------+
           |                                   |
+----------v-----------+            +----------v-----------+
| Primary database     |  redo      | Target standby       |
| DB_UNIQUE_NAME=PRD   +----------->+ DB_UNIQUE_NAME=STB   |
| ROLE=PRIMARY         | transport  | ROLE=PHYSICAL STANDBY|
+----------------------+            +----------------------+
           |                                   |
           +--------------- Broker ------------+
~~~

In real environments, members can reside in different data centers, availability zones, or geographic regions. The observer runs on a separate host and connects to databases over Oracle Net.

### 1.3 DGMGRL Basics

Connect to DGMGRL using an account with appropriate SYSDBA or SYSDG privileges per security policy:

~~~text
dgmgrl
DGMGRL> CONNECT sysdg@PRD_DG;
DGMGRL> SHOW CONFIGURATION;
DGMGRL> SHOW DATABASE VERBOSE 'PRD';
DGMGRL> SHOW DATABASE VERBOSE 'STB';
~~~

Service names in examples represent configured Oracle Net aliases. Never put plaintext passwords in scripts or shell history. Use Secure External Password Store or an appropriate credential mechanism for automated connections.

Once Broker manages members, use DGMGRL to inspect states and adjust Broker properties. Avoid manually altering redo transport parameters while Broker manages the same attributes without understanding how Broker configuration and runtime parameters synchronize.

## 2. Switchover, Manual Failover, and Fast-Start Failover

These three role transitions serve different purposes.

| Operation | Event Type | Who Initiates? | Characteristics |
|---|---|---|---|
| Switchover | Planned role transition | DBA or maintenance workflow | Swaps primary and standby roles; guarantees zero data loss when preconditions are met |
| Manual failover | Unplanned role transition | DBA | DBA chooses a standby and issues failover after primary failure |
| Fast-Start Failover | Unplanned automatic role transition | Observer coordinating with Broker | Automatically transitions to target standby when FSFO conditions are satisfied |

### 2.1 Switchover

Switchover is used for planned maintenance, such as OS patching or primary server upgrades. Both primary and standby remain reachable; Broker synchronizes redo and coordinates the role reversal.

Example:

~~~text
DGMGRL> SWITCHOVER TO 'STB';
~~~

After switchover:

- The chosen standby becomes primary.
- The former primary becomes standby.
- Broker reconfigures redo transport and apply services for the new roles.
- Other standbys continue or adjust to receive redo from the new primary.

Switchover is not an incident-recovery mechanism when the primary has completely lost connectivity. It requires cooperation from both sides.

### 2.2 Manual Failover

Manual failover is initiated by a DBA when the primary stops operating or cannot recover in time. The DBA picks a standby as the new primary and executes failover via DGMGRL.

General example:

~~~text
DGMGRL> FAILOVER TO 'STB';
~~~

Data-loss exposure depends on protection mode and redo received/applied at the standby. After manual failover, the former primary must typically be inspected, flashed back, or rebuilt as a standby depending on its state.

### 2.3 Fast-Start Failover

FSFO automates the failover decision within a preconfigured Broker setup. The observer monitors the primary and target standby. When the primary becomes unreachable per criteria and the target standby is eligible, the observer instructs Broker to execute failover.

FSFO does not run automatically just because Data Guard Broker is installed. You must configure the target standby, protection mode, redo transport, thresholds, observer, network connectivity, and a consistent Broker state.

## 3. What Is the Observer?

The observer is a continuously running process from the DGMGRL client-side component. It is not a database instance, stores no datafiles, and applies no redo. Its sole job is monitoring connectivity and health of the primary and target standby, then coordinating with Broker when FSFO is required.

The observer usually runs on a separate host from both primary and standby. Placement is critical: if the observer shares a failure domain with the primary, a single site outage can take out both primary and observer, leaving automatic failover unable to decide.

### 3.1 What Does the Observer Monitor?

The observer maintains connections and exchanges state with:

- The primary database.
- The target standby database.
- The Broker configuration through database members.

The observer must be able to reach both the primary and the target standby. It must confirm the target standby is in a valid state to assume the primary role.

When the observer loses connectivity to the primary, it does not fail over immediately. It starts tracking outage duration against `FastStartFailoverThreshold`, attempts to reconnect, and verifies target standby state.

### 3.2 Master Observer and Backup Observers

In releases supporting multiple observers, one observer acts as the **master observer**. The master observer coordinates FSFO. Remaining observers act as backup observers that can assume the master role if the active observer fails per Broker mechanics.

The maximum number of observers varies by Oracle version. Oracle Database 19c documentation specifies up to three observers per configuration; newer releases may support different limits. Consult documentation for your exact deployed release and Release Update.

Running multiple observers does not mean multiple observers issue independent failover commands. Broker designates a single master observer to prevent conflicting role-transition decisions.

### 3.3 Where Should the Observer Be Placed?

A sound topology separates all three components:

- Primary in site A.
- Target standby in site B.
- Observer in site C or an independent failure domain.

Example:

~~~text
+-------------------+      +-------------------+
| Site A            |      | Site B            |
| Primary database  |----->| Standby database  |
+-------------------+ redo +-------------------+
          \                       /
           \                     /
            \                   /
             +-----------------+
             | Site C           |
             | Observer host    |
             +------------------+
~~~

If only two sites exist, evaluate which site hosts the observer and whether network paths are sufficiently independent. No observer placement completely eliminates network partition risk. The goal is enabling the observer to distinguish a site outage from an isolated link failure as reliably as possible.

### 3.4 Observer Requires Oracle Net and Credentials

The observer host requires:

- Oracle Client or Oracle Home with compatible DGMGRL.
- `TNSNAMES.ORA` or corresponding naming method.
- Connect identifier to the primary.
- Connect identifier to the target standby.
- Credentials with Broker management privileges.
- Working network routes, firewall rules, and DNS.
- Write permissions for observer logs and state files.
- A supervision mechanism to restart the observer process if the host reboots.

With RAC, connect identifiers must allow the observer to reach eligible instances without depending on a single node. Configure `ObserverConnectIdentifier` if the observer should use a separate connect string from the `DGConnectIdentifier` used for redo transport.

## 4. Foundational Prerequisites Before Enabling FSFO

Broker allows enabling Fast-Start Failover only when essential prerequisites are satisfied. A healthy running Data Guard setup is not automatically ready for FSFO.

Key prerequisite groups:

1. Primary and target standby belong to the same Broker configuration.
2. Broker is enabled and the configuration is healthy.
3. Protection mode and redo transport are compatible.
4. Target standby receives redo from the primary per supported configuration.
5. Standby redo logs are properly configured.
6. Observer can connect to both primary and target standby.
7. Connect identifiers, listeners, and static services have been verified.
8. Target standby is synchronized or within lag limits.
9. FSFO is enabled.
10. Observer is running and recognized by Broker.

### 4.1 Broker Configuration Must Be Active

Check:

~~~text
DGMGRL> SHOW CONFIGURATION;
DGMGRL> SHOW CONFIGURATION VERBOSE;
~~~

If the Broker configuration is disabled, inconsistent, or reporting transport/apply errors, resolve them before enabling FSFO.

On database members, check:

~~~sql
SHOW PARAMETER dg_broker_start;
~~~

To enable if needed:

~~~sql
ALTER SYSTEM SET DG_BROKER_START = TRUE SCOPE = BOTH;
~~~

Verify Broker manages the members and databases communicate via their connect identifiers.

### 4.2 Primary and Target Standby Must Be Reachable

When enabling FSFO, both primary and target standby must be running, connected, and meeting prerequisites. The observer must also reach both.

Validate Broker network configuration:

~~~text
DGMGRL> VALIDATE NETWORK CONFIGURATION FOR ALL;
~~~

Command availability depends on release. If this validate command is absent in your release, validate each database with supported `VALIDATE` commands and test live connections from the observer host.

### 4.3 Target Standby Must Be Eligible to Assume the Role

A far sync instance only forwards redo; it is not a database and cannot become primary. A target standby may receive redo through far sync in supported setups, but the standby database itself is the failover target.

A snapshot standby is not a valid target for switchover or FSFO as documented for Oracle 19c. Convert it back to a physical standby and meet prerequisites before selecting it as an FSFO target.

A physical standby is the most common choice because it maintains a complete physical copy and can keep protecting the new primary after role transitions.

## 5. Protection Modes and Potential Data Loss

Protection mode determines data-protection behavior when the primary fails before the standby receives or applies all redo.

| Protection Mode | Typical Redo Transport | Objective | FSFO Behavior |
|---|---|---|---|
| Maximum Protection | SYNC | Guarantees zero data loss; primary may halt if redo cannot be protected | Target must be synchronized per mode rules |
| Maximum Availability | SYNC or FASTSYNC per config | Prioritizes zero data loss when standby is available while preserving availability | Target must be synchronized at failover |
| Maximum Performance | ASYNC | Prioritizes primary performance; untransported/unapplied redo may be lost | Target must be within FastStartFailoverLagLimit |

Specific configurations must be checked against release, standby type, far sync, and redo transport mode. This table is a conceptual overview, not a replacement for actual Oracle configuration rules.

### 5.1 Maximum Protection

Maximum Protection prioritizes zero data loss. The primary continues processing transactions only while required redo is protected per mode rules. If no eligible synchronized standby remains, the primary may shut down rather than run without the selected protection guarantee.

FSFO can operate under an eligible protection mode, provided the target satisfies synchronization requirements. Under Maximum Protection, redo transport requires SYNC and excludes far sync per certain Oracle configuration restrictions.

### 5.2 Maximum Availability

Maximum Availability is commonly selected when prioritizing zero data loss while a synchronous standby is available, yet keeping the primary running if the standby temporarily disconnects per mode behavior.

For FSFO to achieve zero data loss, the configuration must use compatible redo transport—typically SYNC or FASTSYNC per Oracle guidelines—and the target must be SYNCHRONIZED when the primary fails.

Never infer zero data loss solely from the protection mode name. Verify actual synchronization state and Broker properties.

### 5.3 Maximum Performance

Maximum Performance uses ASYNC to minimize redo transport overhead on the primary. When the primary fails, the target standby may not have received or applied all redo.

`FastStartFailoverLagLimit` sets the maximum apply lag (in seconds) tolerated for FSFO to proceed. If the target exceeds this limit, Broker blocks automatic failover because data loss could breach policy.

Configuration example:

~~~text
DGMGRL> EDIT DATABASE 'PRD' SET PROPERTY LogXptMode = ASYNC;
DGMGRL> EDIT DATABASE 'STB' SET PROPERTY LogXptMode = ASYNC;
DGMGRL> EDIT CONFIGURATION SET PROTECTION MODE AS MaxPerformance;
DGMGRL> EDIT CONFIGURATION SET PROPERTY FastStartFailoverLagLimit = 30;
~~~

The 30-second example is purely illustrative. Choose a lag limit aligned with business-approved RPO and the standby's ability to sustain apply.

### 5.4 Zero Data Loss and Lag Limit

In Maximum Availability configured for zero data loss, the target must be confirmed synchronized by Broker. Broker documentation may display Lag Limit as 0 in zero-data-loss mode.

In Maximum Performance, `FastStartFailoverLagLimit` represents acceptable data-loss exposure. Oracle 19c documentation cites a default of 30 seconds and a minimum of 5 seconds for this mode.

Do not apply the same lag limit across all protection modes. Evaluate mode, redo transport, target state, and exact release.

## 6. Choosing the Target Standby for Fast-Start Failover

The target standby is the database Broker prepares in advance to assume the primary role when FSFO triggers.

If a configuration has only one standby, explicitly setting the target property may not be required per some Broker guidelines. With multiple standbys, specify the target or candidate list using `FastStartFailoverTarget` on the current primary.

Example:

~~~text
DGMGRL> EDIT DATABASE 'PRD' SET PROPERTY FastStartFailoverTarget = 'STB';
~~~

When multiple targets are specified, Broker evaluates them in the order listed in the property. Verify list syntax and delimiters for your running release.

### 6.1 Target Selection Criteria

Evaluate:

- Transport lag and apply lag.
- Protection mode and data-loss exposure.
- Network latency from primary to standby.
- Redo transport bandwidth.
- Standby CPU, memory, storage, and I/O capacity.
- Capacity to carry full production workload post-failover.
- Reachability from applications and clients.
- Service, listener, wallet, and dependency configurations.
- Ability to continue protecting the new primary via remaining standbys post-transition.

Among standbys of the same type, lower transport lag generally reduces data loss. For FSFO, the target must also meet synchronized or within-lag states.

### 6.2 A Target Needs More Than Just Data

A standby may receive all redo yet lack the hardware capacity to carry production load. After failover, the database opens as primary while the application slows down or misses SLAs.

Size the standby for real production workload: CPU, memory, storage throughput, connection limits, licensing, backups, monitoring, and operational staffing.

## 7. FastStartFailoverThreshold

`FastStartFailoverThreshold` is the time (in seconds) the master observer waits and attempts to reconnect to the primary before initiating FSFO due to primary disconnect.

In Oracle Database 19c:

- Default value is 30 seconds.
- Minimum value is 6 seconds.
- Higher values reduce false failovers from brief network glitches.
- With a RAC primary, factor in instance failure detection and Clusterware reconfiguration time before choosing a threshold.

Example:

~~~text
DGMGRL> EDIT CONFIGURATION SET PROPERTY FastStartFailoverThreshold = 45;
~~~

45 seconds is illustrative, not a universal recommendation.

### 7.1 Threshold Too Low

If the threshold is too low:

- Brief network jitter may be mistaken for a primary failure.
- The observer lacks time to distinguish transient glitches from real outages.
- A RAC node undergoing Clusterware recovery may not finish recovering in time.
- Unwanted failovers disrupt applications and incur role-transition overhead.

### 7.2 Threshold Too High

If the threshold is too high:

- Applications wait longer before the database transitions roles.
- RTO increases.
- A genuinely dead primary leaves the service unavailable longer than necessary.

Set the threshold from observed network behavior and recovery times, not merely by picking a small number for fast failover.

### 7.3 Using the Observer Histogram

Oracle provides `V$FS_OBSERVER_HISTOGRAM` in supported releases to inspect statistics on successful pings between the observer and primary over time intervals.

This helps calibrate thresholds against real network latency and jitter. Combine histogram data with observer logs, broker logs, and network monitoring metrics.

## 8. FastStartFailoverLagLimit

`FastStartFailoverLagLimit` sets the maximum apply lag permitted on the standby for FSFO to trigger under Maximum Performance mode.

Example:

~~~text
DGMGRL> EDIT CONFIGURATION SET PROPERTY FastStartFailoverLagLimit = 20;
~~~

If the target standby's apply point trails the primary's redo generation point beyond this limit, FSFO is blocked.

The lag limit reflects acceptable data loss, not failover speed. A lower lag limit cuts potential data loss but can make the standby ineligible for failover during heavy load spikes or slow network periods.

### 8.1 Transport Lag vs. Apply Lag

Distinguish:

- **Transport lag:** redo generated on the primary not yet delivered to the standby.
- **Apply lag:** redo received by the standby not yet applied to standby datafiles.

A standby with low transport lag but high apply lag may still be ineligible. FSFO evaluates apply/lag readiness per Broker rules rather than looking at a single transport lag figure.

### 8.2 Do Not Use Lag Limit to Mask Apply Issues

If the standby frequently breaches the lag limit, find the root cause:

- Insufficient network bandwidth.
- Spikes in redo generation rate.
- Standby CPU or I/O bottlenecks.
- Suboptimal recovery parallelism.
- Configured apply delay.
- Standby contention or capacity exhaustion.
- Redo transport errors or interruptions.

Raising the lag limit solely so Broker always allows failover risks violating business data-loss policies.

## 9. Connectivity Conditions and Detecting Primary Failure

In standard disconnect scenarios, FSFO relies on signals from both the observer and the target standby.

Default model:

1. Primary loses connectivity to the observer.
2. Primary also loses connectivity to the target standby.
3. Observer starts the threshold timer and attempts to reconnect to the primary.
4. Target standby checks its state and synchronization level.
5. If the threshold expires while the primary remains unreachable, the target standby is eligible, and Broker configuration is consistent, the observer initiates failover.

This prevents a lone observer from declaring the primary dead while the standby still communicates normally with the primary.

### 9.1 Why Must Both Observer and Standby Confirm?

Suppose the network link between observer and primary breaks while the primary continues communicating normally with the standby. If the observer decided to fail over unilaterally, two databases could simultaneously believe they are primary.

Requiring standby confirmation lowers split-brain risk. Broker verifies whether the target standby can still reach the primary and allows failover only when conditions align.

### 9.2 ObserverOverride

`ObserverOverride` is a property allowing the observer to trigger failover upon losing contact with the primary, even if the standby still has a healthy connection to the primary.

The default in Oracle Database 19c documentation is `FALSE`.

~~~text
DGMGRL> EDIT CONFIGURATION SET PROPERTY ObserverOverride = TRUE;
~~~

Enabling `ObserverOverride` addresses specific network partition scenarios, but alters split-brain protections. If the standby still sees the primary active, failing over risks leaving both old and new primaries able to serve clients.

Never enable `ObserverOverride` merely to shave failover time. Consider it only when network architecture, fencing, primary shutdown, and partition scenarios have been thoroughly designed, tested, and approved.

## 10. Primary Shutdown to Mitigate Split-Brain

`FastStartFailoverPmyShutdown` controls whether the primary shuts itself down under certain FSFO conditions.

In Oracle Database 19c, the default is `TRUE`. When FSFO is enabled and the primary's `FS_FAILOVER_STATUS` remains `STALLED` past `FastStartFailoverThreshold`, the primary can shut down to prevent an isolated primary from continuing to serve queries.

Example checking properties:

~~~text
DGMGRL> SHOW CONFIGURATION VERBOSE;
DGMGRL> SHOW FAST_START FAILOVER;
~~~

This property is especially important when the primary is isolated from both observer and target standby. Once failover promotes the standby, the former primary must stop accepting application writes.

Primary self-shutdown does not replace network fencing and service routing design. Applications must avoid routing writes back to the old site after role transition.

## 11. Health Conditions That Can Trigger FSFO

Besides threshold-based disconnects, Broker lets you configure specific health conditions so FSFO triggers immediately upon detecting severe faults.

In Oracle Database 19c documentation, conditions include:

| Health Condition | Meaning | Default per 19c Docs |
|---|---|---|
| Datafile Write Errors | Write errors on datafiles, including certain system, undo, and temp files | YES |
| Corrupted Dictionary | Severe data dictionary corruption | YES |
| Corrupted Controlfile | Permanent control file corruption due to media error | YES |
| Inaccessible Logfile | LGWR cannot write to any member of a log group due to I/O error | NO |
| Stuck Archiver | Archiver cannot archive redo because destination is full or unavailable | NO |

Defaults and condition sets can vary by release. Use DGMGRL to inspect actual configuration.

### 11.1 Enabling an Additional Condition

Example syntax:

~~~text
DGMGRL> ENABLE FAST_START FAILOVER CONDITION 'Inaccessible Logfile';
~~~

Disable:

~~~text
DGMGRL> DISABLE FAST_START FAILOVER CONDITION 'Inaccessible Logfile';
~~~

Verify exact condition names for your release. These conditions can trigger failover without waiting for `FastStartFailoverThreshold`.

### 11.2 Why Not Enable Every Condition?

Some errors may affect only a single instance in Oracle RAC. Failing over the entire database to another site for a single-instance issue that Clusterware could recover locally can actually reduce availability.

Specifically, Oracle advises carefully evaluating `Inaccessible Logfile` and `Stuck Archiver` in RAC because they can trigger at a single-instance scope and bypass Oracle Clusterware's local recovery benefits.

Enable extra health conditions only when the organization confirms those faults cannot be resolved locally and warrant role transition.

## 12. Normal Shutdown Does Not Trigger FSFO

An important operational rule is that FSFO does not automatically fail over when the primary or standby undergoes a clean shutdown.

Clean shutdown modes include:

- `SHUTDOWN NORMAL`.
- `SHUTDOWN IMMEDIATE`.
- `SHUTDOWN TRANSACTIONAL`.

In these cases, Broker does not treat the event as a primary crash requiring automatic failover. FSFO will not trigger until primary and standby reconnect and exchange state as required.

Conversely, `SHUTDOWN ABORT` or failure of all primary instances can trigger FSFO if remaining preconditions are met.

This matters when scheduling maintenance. If a DBA intentionally shuts down the primary, use a planned switchover when a role transfer is desired rather than expecting FSFO to take over.

## 13. Target Standby Readiness Conditions

The observer detecting a disconnected primary is not enough. The target standby must also be ready to become primary.

Conditions that prevent FSFO from occurring:

- FSFO is disabled.
- Master observer is not running.
- Observer cannot connect to the target standby.
- Observer and target standby have inconsistent Broker configuration states.
- Target standby lost connectivity to the observer.
- Target standby is not synchronized under Maximum Availability or Maximum Protection.
- Target standby exceeds `FastStartFailoverLagLimit` under Maximum Performance.
- Target standby still communicates with the primary while `ObserverOverride` is `FALSE`.
- Target standby's `FS_FAILOVER_STATUS` indicates a blocking reason.
- A manual failover is already underway.
- Primary was shut down cleanly rather than via `ABORT`.

### 13.1 Checking Target State

On the target standby:

~~~sql
SELECT database_role,
       open_mode,
       switchover_status,
       fs_failover_status,
       fs_failover_observer_present
FROM v$database;
~~~

These columns verify role, open mode, and FSFO readiness. Column names and values may vary by release.

Under Maximum Availability, readiness typically appears as `SYNCHRONIZED`. Under Maximum Performance, status may appear as `TARGET UNDER LAG LIMIT` when within bounds.

### 13.2 Checking via DGMGRL

~~~text
DGMGRL> SHOW FAST_START FAILOVER;
DGMGRL> SHOW DATABASE VERBOSE 'STB';
DGMGRL> SHOW CONFIGURATION VERBOSE;
~~~

`SHOW FAST_START FAILOVER` output reveals:

- Whether FSFO is enabled or disabled.
- Protection mode.
- Lag limit.
- Threshold.
- Active target and potential targets.
- Current observer.
- Shutdown Primary setting.
- Auto-reinstate setting.
- Observer reconnect and override settings.
- Enabled health conditions.

Never check only the `Enabled` line. Verify the target is valid, the observer is recognized, and the database is eligible for failover.

## 14. Step-by-Step Procedure to Enable Fast-Start Failover

This section outlines a configuration framework for a primary and physical standby already managed by Data Guard Broker. Replace database names, services, and values with your actual environment details.

### Step 1: Verify Broker Configuration

~~~text
DGMGRL> SHOW CONFIGURATION;
DGMGRL> SHOW DATABASE VERBOSE 'PRD';
DGMGRL> SHOW DATABASE VERBOSE 'STB';
~~~

Confirm both primary and standby are enabled with no unresolved transport/apply errors.

### Step 2: Verify Redo Transport and Standby Redo Logs

Check that `LogXptMode` matches your protection mode. Both primary and target standby need standby redo logs properly sized, counted, and assigned per thread for their respective roles.

In RAC environments, verify every thread. An SRL layout sufficient for a single instance can fail during role transitions or multi-thread activity.

### Step 3: Set Target Standby

If multiple standbys exist, set `FastStartFailoverTarget` on the primary:

~~~text
DGMGRL> EDIT DATABASE 'PRD' SET PROPERTY FastStartFailoverTarget = 'STB';
~~~

Change targets following Broker procedures; in many releases you must disable FSFO, update the target, and re-enable FSFO.

### Step 4: Set Protection Mode

Example for Maximum Availability:

~~~text
DGMGRL> EDIT DATABASE 'PRD' SET PROPERTY LogXptMode = SYNC;
DGMGRL> EDIT DATABASE 'STB' SET PROPERTY LogXptMode = SYNC;
DGMGRL> EDIT CONFIGURATION SET PROTECTION MODE AS MaxAvailability;
~~~

If using FASTSYNC or far sync, verify your architecture and release support that exact setup. For Maximum Performance, configure ASYNC and set a lag limit matching RPO.

### Step 5: Set Threshold

~~~text
DGMGRL> EDIT CONFIGURATION SET PROPERTY FastStartFailoverThreshold = 30;
~~~

30 seconds is the default in Oracle 19c documentation. In production, base it on network latency, RAC failover times, and the observer histogram.

### Step 6: Review Related Properties

~~~text
DGMGRL> SHOW CONFIGURATION VERBOSE;
DGMGRL> SHOW FAST_START FAILOVER;
~~~

Inspect properties such as `FastStartFailoverPmyShutdown`, `FastStartFailoverAutoReinstate`, `FastStartFailoverLagLimit`, `ObserverOverride`, and `ObserverReconnect`.

### Step 7: Verify Connectivity from the Observer Host

From the observer host, verify Oracle Net connects to both primary and target standby using the exact connect identifiers. Do not test only from a DBA laptop or the primary host.

If not using Oracle Clusterware or Oracle Restart, configure static services so Broker can restart databases during reinstatement. Use `VALIDATE STATIC CONNECT IDENTIFIER` per release to verify.

### Step 8: Enable FSFO

~~~text
DGMGRL> ENABLE FAST_START FAILOVER;
~~~

This authorizes Broker to perform automatic failover if trigger conditions occur. It does not trigger an immediate failover upon enabling.

### Step 9: Start the Observer

On the observer host, connect DGMGRL to the configuration and run:

~~~text
DGMGRL> START OBSERVER IN BACKGROUND;
~~~

You can run it in the foreground via `START OBSERVER`, though the prompt will not return until the observer is stopped from another DGMGRL session. Running in the background is usually more practical operationally.

### Step 10: Verify Final State

~~~text
DGMGRL> SHOW FAST_START FAILOVER;
DGMGRL> SHOW CONFIGURATION VERBOSE;
DGMGRL> SHOW DATABASE VERBOSE 'STB';
~~~

Confirm the observer appears, target is valid, FSFO is enabled, and protection mode and lag match RPO.

## 15. Observe-Only Mode: Rehearsing Before Allowing Real Failover

Observe-only mode lets you observe conditions FSFO would act upon without executing an actual role transition.

Enable:

~~~text
DGMGRL> ENABLE FAST_START FAILOVER OBSERVE ONLY;
~~~

In this mode, Broker/observer logs whether failover conditions are met and what action would be taken. No automatic role change occurs.

Observe-only mode is useful for:

- Measuring detection times for primary unavailability.
- Testing networking between the observer and databases.
- Verifying whether the target standby maintains synchronized/within-lag state.
- Checking observer and broker logs.
- Detecting false positives caused by network jitter.
- Evaluating thresholds before enabling live automatic role transitions.

Note: Observe-only does not enforce the exact same checks as live FSFO. Certain preconditions may be bypassed in observe mode, so do not treat a single observe-only run as proof that real failover will succeed.

## 16. How Does the Observer Operate When the Primary Fails?

Typical flow:

~~~text
Primary is active
        |
        v
Observer and standby monitor primary
        |
        v
Primary loses connectivity
        |
        v
Observer starts FastStartFailoverThreshold
        |
        +---- Primary reconnects before timeout? ---- Yes ----> Abort failover attempt
        |
        No
        |
        v
Observer checks target standby
        |
        +---- Target ineligible? ---- Yes ----> Do not failover yet; continue monitoring
        |
        No
        |
        v
Broker transitions target standby to primary
        |
        v
Former primary is shut down/fenced per configuration
        |
        v
Applications connect to services on new primary
        |
        v
Former primary is reinstated as standby when eligible
~~~

This is a logical model. Actual timing also depends on threshold, detection time, apply backlog, recovery, database open, service startup, and application reconnection times.

### 16.1 Primary Loses Connectivity to Both Observer and Standby

This is the classic default scenario. Both observer and target standby confirm loss of contact with the primary. Once the threshold expires and the target qualifies, FSFO executes.

### 16.2 Only the Observer Loses Connectivity to Primary

If the target standby still communicates with the primary, Broker blocks failover by default to prevent split-brain. `ObserverOverride` alters this behavior, but requires rigorous risk evaluation.

### 16.3 Observer Stops

Without an active master observer, FSFO cannot execute normally. A backup observer can take over if configured and running per release mechanics.

The observer is a critical component of the availability architecture. Monitor its process, host, logs, network, and restart policy like any production service.

### 16.4 RAC Primary Loses One Instance

With a RAC primary, FSFO should not fail over merely because one instance fails while surviving instances continue operating. The observer checks remaining instances; failover triggers only when all primary instances are deemed failed or unreachable per Broker logic.

This is why the threshold must be large enough to cover Clusterware instance failure detection and recovery time, avoiding cross-site failover for a single transient node failure.

## 17. FastStartFailoverAutoReinstate

After FSFO succeeds, the former primary can be brought back into the configuration as a new standby. The `FastStartFailoverAutoReinstate` property controls automatic reinstatement in supported scenarios.

In Oracle Database 19c, the default is `TRUE`.

However, auto-reinstate does not always occur. Typical prerequisites include:

- Flashback Database enabled on the database needing reinstatement and target/new primary per Oracle requirements.
- Sufficient flashback logs retained to flash back the former primary to the required SCN.
- Observer able to reconnect to the former primary.
- Former primary and new primary able to communicate.
- Broker configuration still has FSFO enabled and remaining preconditions satisfied.
- Failover did not originate from user-configurable conditions or `DBMS_DG.INITIATE_FS_FAILOVER` calls in cases where Oracle skips automatic reinstatement.

### 17.1 Checking Flashback Database

On relevant databases:

~~~sql
SELECT name, flashback_on
FROM v$database;
~~~

If auto-reinstate is required, size FRA and flashback retention to keep flashback logs long enough. Simply having `FLASHBACK_ON` does not guarantee sufficient logs remain when an outage happens after an extended period.

### 17.2 Manual Reinstatement

If auto-reinstate does not execute, DBAs can resolve the blocker and use Broker to reinstate:

~~~text
DGMGRL> REINSTATE DATABASE 'PRD';
~~~

Run this only when the database satisfies reinstatement prerequisites. If flashback logs are insufficient or the former primary cannot flash back to the required point, rebuild the standby from the new primary using the appropriate procedure.

## 18. Application Connectivity After Failover

Data Guard Broker transitions database roles, yet applications must know how to find the new primary.

Prepare:

- Services configured to run only when the database holds the `PRIMARY` role.
- Proper listeners and service registration at both sites.
- TNS connect descriptors capable of reaching the new site.
- DNS or load balancers updated per design.
- Connection pools able to purge stale connections and establish fresh ones.
- FAN, TAF, or Application Continuity if supported by your application and Oracle stack.
- Post-transition verification of jobs, schedulers, integration endpoints, and database links.

### 18.1 Role-Based Services

A service can be configured to run only when the database is in the `PRIMARY` role via Oracle Clusterware or Oracle Restart. When a role transition occurs, the service starts automatically on the new primary per configuration.

Never allow write services to run concurrently on both the former primary and the new primary. Verify role settings, preferred/available instances, and service management before deploying FSFO.

### 18.2 Client Retries and Transaction Outcomes

If a connection breaks during a commit, the application may not know whether the transaction committed. This is a transaction outcome problem, not just reconnection.

Applications should implement idempotency keys, bounded retry logic, and reconciliation workflows for critical writes. Application Continuity can help replay eligible requests, though driver, service, and transaction support must be verified.

## 19. Monitoring FSFO Status

Do not wait for a failure to check the observer. Continuously monitor Broker and target standby health.

### 19.1 DGMGRL

Common commands:

~~~text
DGMGRL> SHOW CONFIGURATION VERBOSE;
DGMGRL> SHOW FAST_START FAILOVER;
DGMGRL> SHOW DATABASE VERBOSE 'PRD';
DGMGRL> SHOW DATABASE VERBOSE 'STB';
DGMGRL> VALIDATE DATABASE VERBOSE 'STB';
DGMGRL> VALIDATE NETWORK CONFIGURATION FOR ALL;
~~~

`VALIDATE` commands reveal warnings or issues to fix prior to role transitions. Exact syntax varies by release.

### 19.2 V$DATABASE

~~~sql
SELECT name,
       database_role,
       open_mode,
       fs_failover_status,
       fs_failover_observer_present,
       fs_failover_current_target,
       fs_failover_threshold
FROM v$database;
~~~

FSFO columns show failover readiness, observer presence, target, and threshold. Verify supported columns for your exact version in the Oracle Database Reference.

### 19.3 Fast-Start Failover Statistics

`V$FS_FAILOVER_STATS` provides statistics on past FSFO events. Example:

~~~sql
SELECT last_failover_time,
       last_failover_reason
FROM v$fs_failover_stats;
~~~

`V$FS_OBSERVER_HISTOGRAM` helps calibrate thresholds via ping latency statistics. Alongside database views, collect observer logs, broker logs, and alert logs across sites.

### 19.4 Metrics to Alert On

- Observer process stopped or unrecognized by Broker.
- FSFO disabled.
- Target standby invalid.
- `FS_FAILOVER_STATUS` not in a ready state.
- Apply lag exceeding threshold.
- Redo transport errors.
- Broker configuration inconsistent.
- FRA or flashback log space running low.
- Observer disconnected from either database.
- Primary in `STALLED` state.
- Primary-role service not running after role transition.

Alerts must route through channels independent of the primary site. If the alerting system resides solely on the primary, a primary outage can silence notifications.

## 20. Common Troubleshooting

| Symptom | Possible Cause | Remediation |
|---|---|---|
| FSFO enable fails | Unmet prerequisites, invalid target, or incompatible protection mode | Read DGMGRL error, validate primary/standby, redo transport, and Broker state |
| ORA-16819 or observer warning | FSFO enabled but observer not running or unrecognized | Check observer host, DGMGRL, TNS, and logs |
| Target invalid | Apply lag, transport error, Broker inconsistent, or unsupported target | Run SHOW DATABASE VERBOSE, check FS_FAILOVER_STATUS and redo apply |
| Observer cannot reach standby | TNS alias, listener, firewall, DNS, or credentials | Test connectivity directly from the observer host |
| Primary is STALLED | No acknowledgment from observer/standby per protection policy | Check network, observer, and standby; inspect alert/broker logs |
| Failover did not trigger after primary crash | Observer stopped, target not synchronized/within lag, or FSFO disabled | Inspect all conditions, not just threshold |
| Failover triggered prematurely | Low threshold, network jitter, or enabled health condition | Review observer logs, histogram, and configurable conditions |
| Former primary did not auto-reinstate | Flashback disabled/insufficient logs, network, or unmet reinstatement rules | Check FRA, flashback logs, broker status, and run REINSTATE manually when eligible |
| Applications fail to reach new primary | Service/listener/client connect descriptor not updated for role | Check role-based services, DNS, pools, and retries |
| Standby frequently exceeds lag limit | Network, apply throughput, or standby load | Investigate transport/apply bottlenecks; do not arbitrarily raise the limit |

### 20.1 Observer Not Recognized

Check:

- Is the observer process still running?
- Is the observer connected to the correct Broker configuration?
- Does the observer host have valid TNS aliases and credentials?
- Do primary and target standby recognize the observer?
- Was the observer state/log file deleted or unwritable?
- Are multiple observers running with master election in progress?

Restart the observer per release guidelines and operational runbooks, avoiding uncontrolled duplicate observers or deleting state files needed for recovery.

### 20.2 FSFO Disabled Yet Observer Still Running

Disabling FSFO does not necessarily stop the observer process. The observer may remain running while prohibited from initiating automatic failover.

Check state with:

~~~text
DGMGRL> SHOW FAST_START FAILOVER;
~~~

To stop the observer, issue `STOP OBSERVER` from an appropriate DGMGRL session. Do not confuse disabling FSFO with stopping the observer.

### 20.3 Caution with DISABLE FAST_START FAILOVER FORCE

During a network partition, the `FORCE` option may fail to propagate the disabled state to every database member. Disabling FSFO only on the primary while the target standby retains FSFO enabled can still allow the observer to fail over, creating a risk of two databases claiming the primary role.

Oracle warns to handle the target standby carefully during disconnect scenarios. Never treat `FORCE` as a blanket fix. Before using it, locate the observer, primary, and target standby, determine which database has transitioned roles, and ensure split-brain is prevented.

## 21. Designing the Observer and Network Against False Failovers

The observer needs stable network paths to monitor both primary and target. A solid design evaluates:

- Networking between observer and primary.
- Networking between observer and standby.
- Redo transport networking between primary and standby.
- DNS and Oracle Net name resolution.
- Firewall idle timeouts and session timeouts.
- Network routing when a site is isolated.
- Peak-hour latency and jitter.
- Observer host reboots, patching, and process supervision.
- Credential expiration and wallet availability.

### 21.1 Failure Domain Independence

If the observer and primary depend on the same router, power domain, or data center, a shared fault can blind the observer's visibility.

Give the observer as independent an access path as possible. With three sites, placing primary, standby, and observer in three distinct failure domains yields the clearest failure reasoning.

### 21.2 Calibrate Thresholds with Real Data

Do not pick a threshold just because a tutorial uses 30 seconds. Measure ping round-trips, network failover times, RAC reconfiguration, and observer reconnection under realistic load.

Set the threshold high enough to prevent false failovers, yet low enough to meet RTO. Test node losses, network outages, listener failures, and site outages.

### 21.3 Backup Observers

If your release supports multiple observers, deploy a backup observer on a separate host. Verify observer registration, master/backup status, networking, and credential policies.

A backup observer does not replace monitoring. If a shared configuration error or expired credential impacts all observers simultaneously, automatic failover still fails.

## 22. Controlled Failover Testing

Never test FSFO for the first time during a real production outage. Build a test environment matching production protection mode, redo transport, observer topology, and network behavior.

A test plan can include:

1. Verify Broker configuration and target standby.
2. Confirm the observer is running and recognized.
3. Enable observe-only mode to monitor triggers.
4. Inject a controlled network interruption in the test environment.
5. Measure observer detection time.
6. Confirm the target standby maintains synchronized/within-lag state.
7. Review observer and broker logs.
8. Once behavior is understood, enable live FSFO in the test environment.
9. Execute an approved failure injection.
10. Verify role transition, service startup, and client reconnection.
11. Confirm the former primary reinstates or is rebuilt as standby.
12. Back up and re-verify configuration post-failover.

Never induce `SHUTDOWN ABORT` or sever production networks solely to test without a formal plan and approved maintenance window.

### 22.1 Scenarios to Test

- Single-instance primary crash.
- One RAC primary instance crashes while surviving instances stay up.
- Total RAC primary outage.
- Observer disconnects while standby still reaches primary.
- Standby loses connection to observer.
- Redo transport link drops between primary and standby.
- Apply lag exceeds `FastStartFailoverLagLimit`.
- Observer host reboots.
- Network partition across three sites.
- Clean primary shutdown.
- Primary `SHUTDOWN ABORT`.
- Triggering a configured health condition.

Record whether failover occurred, exact timestamps, reasons, potential data loss, application reconnection behavior, and former primary recovery.

## 23. RPO, RTO, and Automatic Failover Expectations

FSFO improves RTO by automating the failover decision. It does not guarantee instant service recovery.

Actual RTO comprises multiple intervals:

- Failure detection time.
- `FastStartFailoverThreshold`.
- Broker role-transition duration.
- Database recovery/open duration.
- Service startup duration.
- Client dead-connection detection and reconnection time.
- Application transaction outcome verification time.

RPO depends on protection mode and redo state at failure time:

- Maximum Availability / Maximum Protection with a synchronized target can achieve zero data loss per configured conditions.
- Maximum Performance permits data loss up to the configured limit while the target remains within the lag limit.
- If the target exceeds the lag limit, FSFO blocks failover rather than accepting policy-breaking data loss.

Never commit to an RTO/RPO number based solely on the threshold setting. Measure the entire end-to-end application recovery during drills.

## 24. Limitations to Understand

FSFO cannot solve every failure type:

- Does not protect against erroneous logical data replicated to the standby.
- Does not replace backups and recovery.
- Does not automatically repair all corruptions propagated to the standby.
- Cannot fail over if the target standby is insufficiently synchronized.
- Cannot fail over if observer and target lose connectivity to each other.
- Does not automatically solve client retries or indeterminate transaction outcomes.
- Does not guarantee external systems outside the database switch roles simultaneously.
- Does not replace RAC for local instance failures.
- Does not replace Clusterware for local instance recovery.
- Does not eliminate split-brain risk if network partitions and observer override are carelessly configured.

Data Guard protects a remote copy; backups protect historical recoverability; RAC protects intra-cluster availability; Clusterware manages resources and instances; applications must handle reconnection and transaction semantics. These layers complement one another.

## 25. End-to-End Illustrative Configuration Example

Assume:

- Primary has `DB_UNIQUE_NAME` `PRD`.
- Physical standby has `DB_UNIQUE_NAME` `STB`.
- Observer runs on host `OBS01`.
- Broker already manages `PRD` and `STB`.
- Target protection mode is Maximum Availability.
- Observer can connect to both databases.

On primary and standby, verify Broker is running:

~~~sql
SHOW PARAMETER dg_broker_start;
~~~

In DGMGRL:

~~~text
DGMGRL> SHOW CONFIGURATION;
DGMGRL> SHOW DATABASE VERBOSE 'PRD';
DGMGRL> SHOW DATABASE VERBOSE 'STB';
~~~

Configure redo transport and protection mode per design:

~~~text
DGMGRL> EDIT DATABASE 'PRD' SET PROPERTY LogXptMode = SYNC;
DGMGRL> EDIT DATABASE 'STB' SET PROPERTY LogXptMode = SYNC;
DGMGRL> EDIT CONFIGURATION SET PROTECTION MODE AS MaxAvailability;
~~~

Set target and threshold:

~~~text
DGMGRL> EDIT DATABASE 'PRD' SET PROPERTY FastStartFailoverTarget = 'STB';
DGMGRL> EDIT CONFIGURATION SET PROPERTY FastStartFailoverThreshold = 30;
~~~

Validate connectivity and database readiness:

~~~text
DGMGRL> VALIDATE DATABASE VERBOSE 'STB';
DGMGRL> VALIDATE NETWORK CONFIGURATION FOR ALL;
~~~

Enable FSFO and start the observer:

~~~text
DGMGRL> ENABLE FAST_START FAILOVER;
DGMGRL> START OBSERVER IN BACKGROUND;
~~~

Verify:

~~~text
DGMGRL> SHOW FAST_START FAILOVER;
DGMGRL> SHOW CONFIGURATION VERBOSE;
DGMGRL> SHOW DATABASE VERBOSE 'STB';
~~~

In a test environment, run observe-only mode before enabling live failover. Once testing succeeds, finalize service roles, client connectivity, monitoring, backups, and reinstatement procedures.

The commands above are educational examples. Verify syntax, properties, and prerequisites for your running Oracle Database release before applying in production.

## 26. Data Guard Broker and Observer Operational Checklist

### Before Enabling FSFO

- [ ] Primary and standby belong to the Broker configuration.
- [ ] `DG_BROKER_START` enabled on all members.
- [ ] `SHOW CONFIGURATION` reports zero unresolved errors.
- [ ] Target standby selected and eligible for the primary role.
- [ ] `FastStartFailoverTarget` configured properly when multiple standbys exist.
- [ ] Protection mode and `LogXptMode` aligned with RPO.
- [ ] Standby redo logs configured properly for primary/standby and RAC threads.
- [ ] Redo transport and apply operating smoothly.
- [ ] Target has no unintended apply delay.
- [ ] Observer has DGMGRL, Oracle Net, and valid credentials.
- [ ] Observer reaches both primary and target.
- [ ] Static connect identifiers validated if needed.
- [ ] Threshold and lag limit calibrated with measured data.
- [ ] Application service configured for `PRIMARY` role and client reconnection tested.
- [ ] Flashback Database enabled if auto-reinstate is desired.

### While FSFO Is Running

- [ ] Observer process is active.
- [ ] Broker recognizes the observer/master observer.
- [ ] FSFO status is Enabled.
- [ ] Target standby is valid.
- [ ] `FS_FAILOVER_STATUS` indicates synchronized/within-lag per protection mode.
- [ ] Redo transport is error-free.
- [ ] Apply lag stays within limits.
- [ ] FRA and flashback log space remain adequate.
- [ ] Observer, broker, and alert logs are monitored.
- [ ] Alerts route through infrastructure independent of the primary site.

### After a Failover

- [ ] Confirm new database has `DATABASE_ROLE = PRIMARY`.
- [ ] Confirm old database is blocked from accepting writes as primary.
- [ ] Verify services and listeners at the new site.
- [ ] Verify application reconnection and transaction outcomes.
- [ ] Check remaining standbys and new redo transport.
- [ ] Reinstate former primary or rebuild standby.
- [ ] Verify flashback and backups.
- [ ] Back up the database after role transition per procedure.
- [ ] Document root cause, timeline, RPO/RTO, and follow-up actions.

## 27. Conclusion

Data Guard Broker manages configuration and coordinates role transitions; the observer monitors primary and target standby; Fast-Start Failover automatically transitions an eligible target to primary when configured criteria are met.

For FSFO to operate reliably, choose an appropriate target, align protection mode and redo transport with RPO, calibrate thresholds and lag limits from empirical data, run an independent observer, monitor Broker health, and prepare services and clients for role changes. By default, both the observer and target standby must agree the primary is unreachable, and the target must be synchronized or within the lag limit. `ObserverOverride` and health conditions alter failover behavior and require careful evaluation to prevent false failovers and split-brain.

Automatic failover is only one part of high availability. Backups, recovery, flashback, networking, Clusterware, service management, application resilience, and regular drills must all work together so the new primary truly keeps serving the business.
