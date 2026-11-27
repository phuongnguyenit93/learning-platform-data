# Data Guard: Primary, Physical Standby, and Redo Transport/Apply

Oracle Data Guard is a suite of technologies that maintains one or more standby databases to protect a primary database against hardware failures, storage failures, data center outages, or certain operational errors. With a **physical standby**, the standby database maintains a physical copy of the primary by receiving and applying redo. Redo transport transfers redo from the primary to the standby; redo apply uses that redo to update data blocks on the standby.

Three core concepts:

- **Primary database**: the database serving the main workload and generating redo for changes.
- **Physical standby database**: a physical copy maintained by applying redo from the primary.
- **Redo transport and redo apply**: transport delivers redo to the standby; apply applies redo to standby datafiles to keep data synchronized.

General flow:

~~~text
Application writes data
       |
       v
Primary database
       |
       +--> LGWR writes online redo log
       |
       +--> Redo transport services
                    |
                    v
             Network / Oracle Net
                    |
                    v
             Standby RFS process
                    |
                    v
          Standby Redo Log (SRL)
                    |
                    v
             Redo Apply (MRP)
                    |
                    v
          Physical standby datafiles
~~~

Data Guard is not simply scheduled file copying. Redo transport and apply can operate continuously or near-continuously, under synchronous or asynchronous configurations. Lag, fault tolerance, and data-loss exposure depend on protection mode, transport mode, network, standby redo logs, apply speed, and operational practices.

This lesson focuses on primary/physical standby, the redo transport/apply pipeline, basic configuration, protection modes, lag monitoring, resolving archive gaps, Data Guard Broker, and switchover/failover operations.

## 1. How Does Data Guard Protect a Database?

Data Guard maintains one or more standby databases so roles can be transitioned when the primary fails or during planned maintenance.

### 1.1. Primary Database

The primary is the database accepting main write connections. When a transaction modifies data:

1. Oracle generates redo describing the changes required for recovery.
2. LGWR writes redo from the redo log buffer to the online redo log.
3. Redo transport ships redo to configured standby destinations.
4. The primary continues operating according to the transport/protection mode semantics.

Redo is the information needed to reconstruct changes; it is not a direct copy of each datafile block at the time of transmission.

### 1.2. Physical Standby Database

A physical standby has a file structure and block contents corresponding to the primary. Redo apply uses the received redo to update standby datafiles.

A physical standby can operate in different states:

- MOUNTED with managed recovery running.
- OPEN READ ONLY without applying redo.
- OPEN READ ONLY with concurrent apply in a supported and properly licensed Active Data Guard configuration.
- Apply paused for maintenance or troubleshooting per runbook.

Do not confuse a physical standby with a logical standby. A physical standby applies redo at the physical/block level; a logical standby transforms redo into logical/SQL changes and has distinct compatibility limitations.

### 1.3. A Primary Can Have Multiple Standbys

Data Guard can maintain multiple standby databases. Each standby has its own DB_UNIQUE_NAME, its own network service, its own transport destination on the primary, its own transport/apply state, and its own storage/archive policy.

Do not assume all standbys have the same lag or role-transition readiness. One standby may be synchronized while another lags due to network, storage, or apply throughput.

### 1.4. Data Guard Does Not Replace Backups

A standby protects against certain primary failures, but replicated logical errors can also propagate to the standby. For instance, accidental user deletions or erroneous DDL can be replayed by redo apply.

Independent backups remain necessary to recover logically deleted or corrupted data, restore to a point before an erroneous operation, recover when both primary and standby are affected, and satisfy retention/audit requirements.

## 2. Components in the Redo Transport/Apply Pipeline

Understanding each process's role helps isolate whether an issue lies on the primary, network, standby, or apply side.

### 2.1. LGWR on the Primary

LGWR writes redo from the redo log buffer to the online redo log. In transport configurations sourcing redo from LGWR, redo transport reads from this stream to ship to the standby.

LGWR remains responsible for local redo writes. Data Guard does not replace the primary's online redo logs.

### 2.2. Redo Transport Services

Redo transport services transmit redo from the primary to standbys. Configuration is typically declared via LOG_ARCHIVE_DEST_n with SERVICE, VALID_FOR, DB_UNIQUE_NAME, and transport attributes.

Exact processes and paths can vary by Oracle release, transport mode, and configuration. In LGWR transport streams, LNS processes participate in shipping redo; ARCn can participate in shipping archived redo or handling archive/fallback streams depending on configuration.

### 2.3. Network

Redo is transmitted over Oracle Net to the standby's service. Influencing factors:

- Network latency and bandwidth.
- Packet loss/retransmission.
- Listener/service availability.
- DNS/TNS resolution.
- Firewalls/ports.
- Encryption/compression.
- Number of standbys receiving redo concurrently.
- Workload concurrency.

With SYNC transport, network round-trip time can directly affect commit latency. With ASYNC, the primary does not wait for standby acknowledgment per commit in the same way, but the standby can fall behind if the network or receiver cannot keep up.

### 2.4. RFS on the Standby

The Remote File Server (RFS) receives redo from the primary. When standby redo logs are configured, RFS writes redo into the Standby Redo Log (SRL). Redo can subsequently be archived and fed into the apply process.

RFS is key when investigating:
- Is the standby receiving redo?
- Is the SRL being written?
- Is the network connection stable?
- Are archive logs missing or failing to be created?

### 2.5. Standby Redo Log (SRL)

The SRL is a set of redo log groups dedicated to a standby. It enables the standby to receive redo directly while the primary writes its online redo log, supporting real-time apply and protection modes requiring standby redo confirmation.

SRLs differ from online redo logs:

- Online redo logs serve redo generation on a database acting as primary.
- Standby redo logs receive transported redo on a database acting as standby.
- A database generally needs both types because after a switchover, it can change roles.

### 2.6. MRP and Redo Apply

The Managed Recovery Process (MRP) applies redo on a physical standby. The process name is commonly seen as MRP0. MRP reads redo from standby redo logs or archived redo logs depending on state and configuration, updating standby datafiles.

If transport is healthy yet apply is slow, redo reaches the standby without being applied promptly. If apply stops, the standby accumulates a backlog even with a healthy network.

## 3. Transport Lag and Apply Lag

These two lags measure two different segments of the pipeline.

### 3.1. Transport Lag

Transport lag reflects the delay between redo generated on the primary and redo received at the standby. Rising lag may stem from slow/disconnected networks, unavailable standby listeners/services, RFS unable to receive or write fast enough, SRL/archive destination issues, or the primary generating redo faster than the standby can receive it.

### 3.2. Apply Lag

Apply lag reflects the delay between redo generated on the primary and redo applied to standby datafiles.

Apply lag can increase when MRP is stopped, apply throughput falls below the redo generation rate, standby CPU/I/O is insufficient, the recovery process competes with read workloads, or an archive gap exists.

### 3.3. Reading Both Lags Together

| Transport Lag | Apply Lag | Initial Interpretation |
| --- | --- | --- |
| Low | Low | Both transport and apply are keeping up |
| High | High | Redo has not fully reached the standby; apply is delayed accordingly |
| Low | High | Redo has arrived, but apply cannot keep up or apply is stopped |
| High | Low/stale | Check metric freshness, MRP state, and lag computation timestamp |

A low lag value at a single instant does not guarantee absence of spikes. Track sample series, computation timestamps, and process states.

### 3.4. Lag Is Not Directly the Number of Bytes Lost

Transport lag and apply lag typically express time-based delays according to Data Guard statistics. They do not directly state the exact unreceived bytes or number of transactions at risk. To assess exposure, inspect sequences/SCNs, redo generation rates, transport state, and protection mode.

## 4. Standby Redo Logs: Configuration and Principles

SRLs are critical for real-time apply and synchronous configurations.

### 4.1. SRL Size

SRL size should be equal to or larger than the largest online redo log on the primary so it can receive full redo from the corresponding log.

For example, if the primary's largest online redo log is 1 GB, each SRL should be at least 1 GB. If threads have differing sizes, size based on the largest log that can be shipped to the standby.

### 4.2. Number of SRLs

A standard rule of thumb is to create at least one more SRL group than the number of online redo log groups per redo thread. Apply this per thread in RAC.

For example, if the primary has 3 online redo log groups for thread 1, the standby should have at least 4 SRL groups for thread 1. This is a configuration baseline; more may be required depending on active groups, transport concurrency, and version guidance.

### 4.3. Creating SRLs with ASM/OMF

Example using Oracle Managed Files:

~~~sql
ALTER DATABASE ADD STANDBY LOGFILE THREAD 1 SIZE 1G;
ALTER DATABASE ADD STANDBY LOGFILE THREAD 1 SIZE 1G;
ALTER DATABASE ADD STANDBY LOGFILE THREAD 1 SIZE 1G;
ALTER DATABASE ADD STANDBY LOGFILE THREAD 1 SIZE 1G;
~~~

Filenames are managed by Oracle if OMF destinations are configured. Actual syntax depends on storage layout and version.

Example specifying explicit group/member on a filesystem:

~~~sql
ALTER DATABASE ADD STANDBY LOGFILE
  THREAD 1 GROUP 11
  ('/u03/oradata/standby/srl11.log') SIZE 1G;
~~~

This is an illustrative path. Never reuse filenames belonging to online redo logs or existing files.

### 4.4. Inspecting SRLs

~~~sql
SELECT group#,
       thread#,
       sequence#,
       bytes / 1024 / 1024 AS size_mb,
       archived,
       status
FROM v$standby_log
ORDER BY thread#, group#;
~~~

Check online redo logs to compare sizes and threads:

~~~sql
SELECT group#,
       thread#,
       bytes / 1024 / 1024 AS size_mb,
       status
FROM v$log
ORDER BY thread#, group#;
~~~

### 4.5. Configuring SRLs on Both Sites

After a switchover, the standby becomes primary and the former primary becomes standby. Therefore, each database should have SRLs sized for the online redo logs it may receive when acting as standby.

Do not create SRLs only on the current standby and forget the primary. Verify SRLs across every member of the Data Guard configuration.

## 5. Protection Modes

Protection modes determine the priority between guaranteeing zero data loss and maintaining primary availability.

### 5.1. Maximum Protection

Aims to guarantee zero data loss for committed transactions within supported failure models and configurations. The primary requires redo acknowledgment from a synchronous standby according to the protection mode. If no eligible standby remains to protect redo, the primary can shut itself down rather than commit while violating protection guarantees.

Characteristics:
- Prioritizes maximum data protection.
- Requires at least one eligible synchronously configured standby.
- Can impact availability if standbys/networks become unavailable.
- Requires well-designed network, storage, and standby redundancy.

### 5.2. Maximum Availability

Aims for zero data loss while a synchronous standby is available, yet prioritizes keeping the primary running if the standby temporarily disconnects. When no synchronous standby is reachable, protection temporarily drops to a level equivalent to Maximum Performance; when the standby returns, protection resumes per configuration rules.

Characteristics:
- Balances availability and data protection.
- Typically uses SYNC transport.
- Commit latency depends on network and AFFIRM/NOAFFIRM settings.
- Requires monitoring how long the primary operates in a degraded protection state.

### 5.3. Maximum Performance

Prioritizes primary performance and availability. Redo is typically sent asynchronously (ASYNC), so the primary does not wait for standby redo acknowledgment on each commit as SYNC does.

Characteristics:
- Minimal network latency impact on the commit path.
- Standby can experience transport lag.
- Sudden primary loss can lose transactions not yet transported to the standby.
- Requires measuring redo generation rate, network throughput, and lag to understand data-loss exposure.

### 5.4. Comparison

| Mode | Objective | Typical Transport | Primary Risk |
| --- | --- | --- | --- |
| Maximum Protection | Highest data protection | SYNC with appropriate confirmation | Primary may halt if synchronous standby is lost |
| Maximum Availability | Zero data loss when synchronous standby is ready; prioritizes primary availability | SYNC | May temporarily drop protection if standby disconnects |
| Maximum Performance | Optimize primary performance | ASYNC | May lose untransported redo if primary fails |

Exact modes and transport attributes must be checked against Oracle release, configuration, and RPO/RTO requirements. Do not choose a protection mode solely because its name sounds safer; evaluate latency, network topology, and disconnect behavior.

## 6. SYNC, ASYNC, AFFIRM, and NOAFFIRM

Transport attributes govern when the primary receives standby confirmation and how the standby confirms redo has been written.

### 6.1. SYNC

SYNC requires the primary to synchronize with the standby per transport protocol. In the commit path, the primary waits for a response according to transport semantics to ensure redo has reached the standby as configured.

SYNC suits strict data-protection requirements, but network round-trip time and standby I/O can affect commit latency.

### 6.2. ASYNC

ASYNC sends redo without waiting for standby acknowledgment on every commit as SYNC does. The primary continues processing transactions while redo is transported in the background.

ASYNC reduces network latency impact on commits, though the standby can fall behind during high redo generation, low network throughput, receiver bottlenecks, or SRL/storage contention.

### 6.3. AFFIRM

AFFIRM requires the standby to acknowledge only after redo has been durably written to the standby redo log per Oracle semantics. This strengthens the guarantee that data is persisted on the standby before the primary receives acknowledgment, though it can add I/O latency to the commit path.

### 6.4. NOAFFIRM

NOAFFIRM allows the standby to send acknowledgment before redo is durably flushed to the SRL in the manner AFFIRM requires. It can reduce latency while altering protection guarantees under simultaneous failure scenarios.

Do not treat NOAFFIRM as equivalent to AFFIRM. Assess risk according to protection mode, failure model, and release-specific Oracle documentation.

### 6.5. General Selection Table

| Transport Attribute | Primary Waits Synchronously? | Standby Confirms Durable Write? | Primary Impact |
| --- | --- | --- | --- |
| SYNC AFFIRM | Yes | Yes | High protection; latency sensitive to network and I/O |
| SYNC NOAFFIRM | Yes | Does not wait for AFFIRM durable write | Can reduce latency; must understand failure exposure |
| ASYNC AFFIRM | Does not wait per commit | Standby uses AFFIRM when confirming receipt | Commits less sensitive to RTT; transport can still lag |
| ASYNC NOAFFIRM | Does not wait per commit | Does not wait for AFFIRM durable write | Better throughput in many cases; exposure depends on lag |

Allowed combinations and usage depend on version, protection mode, and configuration. Fast Sync is a NOAFFIRM variant supported in certain Maximum Availability configurations; it does not make every failure scenario equivalent to SYNC AFFIRM. Consult Oracle documentation for your exact release before deploying.

## 7. Basic Primary/Physical Standby Configuration

Production configurations must be designed around DB_UNIQUE_NAME, networking, storage, file naming, and database roles. The examples below illustrate core parameters, not copy-paste scripts suitable for every system.

### 7.1. Prerequisites

Before configuring:
- Primary database is operational and has a valid backup.
- DB_NAME matches between primary and physical standby.
- DB_UNIQUE_NAME is distinct for each database.
- Bidirectional Oracle Net service connectivity meets operational requirements.
- Matching password files and appropriate SYSDBA privileges.
- Storage ready for datafiles, online redo logs, SRLs, archives, and FRA.
- ARCHIVELOG mode enabled.
- FORCE LOGGING enabled or policies ensuring all necessary changes generate redo.
- Standby has sufficient memory/process configuration for apply workload.
- Stable time synchronization and DNS/networking.

### 7.2. Enabling ARCHIVELOG and FORCE LOGGING

Check log mode:

~~~sql
SELECT log_mode,
       force_logging
FROM v$database;
~~~

If ARCHIVELOG needs to be enabled, the database must be MOUNTED:

~~~sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
ALTER DATABASE ARCHIVELOG;
ALTER DATABASE FORCE LOGGING;
ALTER DATABASE OPEN;
~~~

Plan backups and archive destinations before enabling ARCHIVELOG. FORCE LOGGING ensures normally unlogged operations still generate redo needed by the standby, though performance impacts and edge cases should be evaluated per Oracle documentation.

### 7.3. Database Identification Parameters

Example on primary:

~~~sql
ALTER SYSTEM SET db_unique_name='PROD_PRI' SCOPE=SPFILE;
ALTER SYSTEM SET log_archive_config='DG_CONFIG=(PROD_PRI,PROD_STBY)' SCOPE=BOTH;
~~~

Example on standby:

~~~sql
ALTER SYSTEM SET db_unique_name='PROD_STBY' SCOPE=SPFILE;
ALTER SYSTEM SET log_archive_config='DG_CONFIG=(PROD_PRI,PROD_STBY)' SCOPE=BOTH;
~~~

DB_NAME typically matches because the standby shares the same logical database identity; DB_UNIQUE_NAME distinguishes each member. Changing DB_UNIQUE_NAME in the SPFILE may require a restart depending on parameters and configuration.

### 7.4. Configuring Local Archive Destination

Example:

~~~sql
ALTER SYSTEM SET log_archive_dest_1=
 'LOCATION=USE_DB_RECOVERY_FILE_DEST
  VALID_FOR=(ALL_LOGFILES,ALL_ROLES)
  DB_UNIQUE_NAME=PROD_PRI'
 SCOPE=BOTH;
~~~

On the standby, DB_UNIQUE_NAME in the local destination must match the standby's own unique name. Use FRA or a filesystem location aligned with your design.

### 7.5. Configuring Remote Redo Transport

Example of the primary sending redo asynchronously to a physical standby:

~~~sql
ALTER SYSTEM SET log_archive_dest_2=
 'SERVICE=PROD_STBY
  ASYNC NOAFFIRM
  VALID_FOR=(ONLINE_LOGFILES,PRIMARY_ROLE)
  DB_UNIQUE_NAME=PROD_STBY'
 SCOPE=BOTH;

ALTER SYSTEM SET log_archive_dest_state_2=ENABLE SCOPE=BOTH;
~~~

PROD_STBY is an Oracle Net service name resolving to the standby. Test tnsnames/listener and SYSDBA connectivity from primary to standby. Do not store passwords in scripts or logs.

### 7.6. Common Standby Parameters

~~~sql
ALTER SYSTEM SET standby_file_management=AUTO SCOPE=BOTH;
ALTER SYSTEM SET fal_server='PROD_PRI' SCOPE=BOTH;
~~~

STANDBY_FILE_MANAGEMENT=AUTO lets the standby automatically handle certain redo-recorded file operations, such as adding datafiles, per supported semantics. FAL_SERVER identifies the source from which the standby requests missing archived logs in traditional setups; Data Guard Broker can manage parts of this configuration.

If file paths differ between primary and standby, configure DB_FILE_NAME_CONVERT or use OMF/DB_CREATE_FILE_DEST appropriately. With OMF, avoid adding unnecessary path conversions.

### 7.7. Inspecting Destinations

~~~sql
SELECT dest_id,
       status,
       target,
       destination,
       error,
       valid_now
FROM v$archive_dest
WHERE dest_id <= 10
ORDER BY dest_id;
~~~

V$ARCHIVE_DEST_STATUS provides more detailed runtime state. When errors occur, examine ERROR, STATUS, DESTINATION, and alert logs on both primary and standby.

## 8. Creating a Physical Standby

A physical standby can be created from backups or via RMAN duplicate from active database. Exact steps depend on database size, network, release, and backup strategy.

### 8.1. Preparing the Standby Instance

- Install compatible Oracle software.
- Create an appropriate password file.
- Create a PFILE/SPFILE with DB_NAME, DB_UNIQUE_NAME, and required parameters.
- Prepare storage locations.
- Configure Oracle Net/listener.
- Ensure the primary is reachable from the standby.
- Prepare backup media or active duplicate connectivity.

### 8.2. RMAN Duplicate from Active Database

Illustrative template:

~~~text
RMAN> CONNECT TARGET sys@PROD_PRI;
RMAN> CONNECT AUXILIARY sys@PROD_STBY;

RMAN> DUPLICATE TARGET DATABASE
       FOR STANDBY
       FROM ACTIVE DATABASE
       DORECOVER
       SPFILE
       SET DB_UNIQUE_NAME='PROD_STBY';
~~~

This is an illustrative skeleton. Adjust password file handling, channels, section size, file name conversion, OMF, encryption, network compression, DB_FILE_NAME_CONVERT, and other parameters per release/storage. Execute in a prepared environment with proper privileges.

### 8.3. Creating from Backup

You can restore a primary backup on the standby host and recover to an appropriate state. Ensure backups, control file, and archived redo are sufficient to build the standby. Follow a tested RMAN duplicate/restore procedure.

### 8.4. Verifying Database Role

On the standby:

~~~sql
SELECT db_unique_name,
       database_role,
       open_mode,
       controlfile_type
FROM v$database;
~~~

Expected DATABASE_ROLE is PHYSICAL STANDBY. If the role differs, stop and verify before starting apply.

## 9. Starting Redo Apply on a Physical Standby

Once the standby is MOUNTED and SRLs are configured, managed recovery can start.

### 9.1. Managed Recovery in MOUNT Mode

~~~sql
ALTER DATABASE RECOVER MANAGED STANDBY DATABASE
DISCONNECT FROM SESSION;
~~~

Oracle runs the managed recovery process in the background. On a physical standby, MRP typically appears in V$DATAGUARD_PROCESS or V$MANAGED_STANDBY depending on the version.

### 9.2. Real-Time Apply

When SRLs are configured and transport writes redo into SRLs, real-time apply allows the standby to apply redo from SRLs before an archived log completes, reducing apply lag.

In older releases, syntax sometimes used USING CURRENT LOGFILE:

~~~sql
ALTER DATABASE RECOVER MANAGED STANDBY DATABASE
USING CURRENT LOGFILE
DISCONNECT FROM SESSION;
~~~

Real-time apply syntax and defaults have evolved across releases; in modern versions, USING CURRENT LOGFILE is generally no longer required. Check release documentation instead of copying legacy syntax.

### 9.3. Stopping Redo Apply

~~~sql
ALTER DATABASE RECOVER MANAGED STANDBY DATABASE CANCEL;
~~~

Stop apply only for clear operational purposes such as opening read-only without Active Data Guard, maintenance, or incident handling. While apply is stopped, backlog grows and the standby falls behind.

### 9.4. Opening a Physical Standby READ ONLY

Without Active Data Guard, a physical standby can be opened READ ONLY while managed recovery is stopped in the traditional model:

~~~sql
ALTER DATABASE RECOVER MANAGED STANDBY DATABASE CANCEL;
ALTER DATABASE OPEN READ ONLY;
~~~

To resume apply under a supported Active Data Guard configuration:

~~~sql
ALTER DATABASE RECOVER MANAGED STANDBY DATABASE
DISCONNECT FROM SESSION;
~~~

Opening read-only concurrently with apply is an Active Data Guard feature; confirm licensing and version/configuration prerequisites. Do not confuse plain READ ONLY open with Active Data Guard.

## 10. Monitoring Transport and Apply

Monitoring must inspect both primary and standby. A single query is insufficient to evaluate the entire pipeline.

### 10.1. Database Status and Protection

~~~sql
SELECT db_unique_name,
       database_role,
       open_mode,
       protection_mode,
       protection_level,
       switchover_status,
       force_logging
FROM v$database;
~~~

Verify:
- DATABASE_ROLE: PRIMARY or PHYSICAL STANDBY.
- OPEN_MODE: READ WRITE, MOUNTED, READ ONLY, or specialized modes.
- PROTECTION_MODE/LEVEL: configured mode versus actual protection level.
- SWITCHOVER_STATUS: readiness indicators for role transition.
- FORCE_LOGGING: force logging state.

### 10.2. Transport Lag and Apply Lag

~~~sql
SELECT name,
       value,
       unit,
       time_computed,
       datum_time
FROM v$dataguard_stats
WHERE name IN ('transport lag', 'apply lag', 'apply finish time');
~~~

TIME_COMPUTED and DATUM_TIME help evaluate metric freshness. If datum time stops advancing, a low lag number may reflect stale data rather than current health.

### 10.3. Data Guard Processes

~~~sql
SELECT name,
       role,
       action,
       thread#,
       sequence#,
       block#
FROM v$dataguard_process
ORDER BY name;
~~~

V$DATAGUARD_PROCESS is available on supported releases. In older versions/tools, DBAs often queried V$MANAGED_STANDBY:

~~~sql
SELECT process,
       status,
       thread#,
       sequence#,
       block#
FROM v$managed_standby
ORDER BY process;
~~~

V$MANAGED_STANDBY has been superseded/deprecated in some releases; prefer the view recommended for your running release.

### 10.4. Archive Destination Status

On the primary:

~~~sql
SELECT dest_id,
       status,
       target,
       destination,
       error,
       archived_thread#,
       archived_seq#
FROM v$archive_dest_status
WHERE status <> 'INACTIVE'
ORDER BY dest_id;
~~~

Check whether standby destinations report any ERROR, the latest archived/transported sequence, and update timestamps.

### 10.5. Standby Redo Log Status

~~~sql
SELECT group#,
       thread#,
       sequence#,
       status,
       archived,
       bytes
FROM v$standby_log
ORDER BY thread#, group#;
~~~

Verify that RFS writes to SRLs and that SRLs transition appropriately after log switches.

## 11. Archive Gaps and FAL

An archive gap is a range of archived redo sequences missing on the standby. If redo is missing, MRP stalls at the point where it cannot continue applying.

### 11.1. Detecting Gaps

On the physical standby:

~~~sql
SELECT thread#,
       low_sequence#,
       high_sequence#
FROM v$archive_gap;
~~~

V$ARCHIVE_GAP shows the gap currently blocking recovery. After resolving one gap, another gap may appear; repeat checks until no gaps remain.

### 11.2. FAL (Fetch Archive Log)

FAL is the mechanism by which a standby requests missing archived redo from an eligible source. FAL_SERVER is typically configured on the standby to identify the source service.

If FAL fails to resolve gaps, check:
- TNS aliases and listeners.
- Password file/SYS authentication.
- FAL_SERVER.
- LOG_ARCHIVE_CONFIG.
- DB_UNIQUE_NAME.
- Whether archive logs still exist on the primary/FRA.
- Network ACLs/firewalls and service registration.

### 11.3. Manually Copying Archived Logs

If logs can no longer be fetched automatically, DBAs may need to retrieve archived logs from backups or the primary and register them on the standby per recovery procedures. Example:

~~~sql
ALTER DATABASE REGISTER LOGFILE
  '/u04/arch/1_12345_987654321.arc';
~~~

This is strictly an illustrative example. Verify the exact thread, sequence, resetlogs ID, and file integrity before registering. Never register a file with a matching sequence number belonging to a different incarnation.

### 11.4. Do Not Delete Archives Needed by Standbys

Archived logs may still be needed by an unreachable standby, a standby that has received but not yet applied them, FAL gap resolution, backup/recovery policies, or downstream standbys.

Deletion policies must account for every standby requiring protection, not just the nearest one.

## 12. Evaluating Redo Generation and Apply Capacity

A standby keeps up only if its receive and apply capacity exceeds the primary's redo generation rate.

### 12.1. Redo Generation Rate

Compute the delta of the `redo size` statistic from V$SYSSTAT on the primary to estimate bytes/second:

\[
RedoRate = \frac{\Delta redo\_size}{ElapsedSeconds}
\]

Use the same instance and counter lifecycle. In RAC, measure per instance/thread individually and aggregate carefully.

### 12.2. Transport Throughput

Monitor:
- Redo generation rate.
- Network throughput between primary and standby.
- Transport lag.
- Archive destination errors.
- RFS activity.
- Standby redo log writes.

If redo generation persistently exceeds network throughput, the backlog will grow.

### 12.3. Apply Throughput

Monitor:
- Apply lag and apply rate.
- MRP process state.
- Standby CPU.
- Datafile I/O latency.
- Parallel recovery configuration.
- Standby query workload if open read-only.
- Storage contention.

If transport lag is low while apply lag rises, investigate apply throughput rather than blindly increasing network bandwidth.

### 12.4. Peaks and Backlog Catch-Up Time

Do not measure only average redo rates. A batch job can generate many times normal redo. Estimate catch-up time:

\[
CatchUpTime \approx \frac{RedoBacklog}{ApplyRate - IncomingRedoRate}
\]

This formula only makes sense when ApplyRate exceeds IncomingRedoRate and both values share consistent units. If apply rate does not exceed incoming rate, the standby will not catch up while the workload continues.

## 13. Data Guard Broker

Data Guard Broker provides a centralized management layer for configuration and role transitions. Broker manages database members, transport/apply state, switchover/failover, and monitoring.

### 13.1. Enabling Broker

Broker is typically enabled via:

~~~sql
ALTER SYSTEM SET dg_broker_start=TRUE SCOPE=BOTH;
~~~

Enable on database members according to design. Verify listeners, broker configuration files, and network connectivity.

### 13.2. Connecting to DGMGRL

~~~text
DGMGRL> CONNECT sys@PROD_PRI;
~~~

Illustrative configuration creation:

~~~text
DGMGRL> CREATE CONFIGURATION 'PROD_DG'
         AS PRIMARY DATABASE IS 'PROD_PRI'
         CONNECT IDENTIFIER IS PROD_PRI;

DGMGRL> ADD DATABASE 'PROD_STBY'
         AS CONNECT IDENTIFIER IS PROD_STBY
         MAINTAINED AS PHYSICAL;

DGMGRL> ENABLE CONFIGURATION;
~~~

This is a skeleton. Database names and connect identifiers must match configured DB_UNIQUE_NAME/services. Verify syntax with DGMGRL help and release documentation.

### 13.3. Inspecting Broker Configuration

~~~text
DGMGRL> SHOW CONFIGURATION;
DGMGRL> SHOW DATABASE VERBOSE 'PROD_PRI';
DGMGRL> SHOW DATABASE VERBOSE 'PROD_STBY';
DGMGRL> VALIDATE DATABASE 'PROD_STBY';
~~~

Broker reports WARNING/ERROR when transport/apply lag exceeds thresholds or configuration drifts out of sync. Read status and error details before modifying properties.

### 13.4. Broker Properties

Commonly managed properties:
- LogXptMode.
- ApplyLagThreshold.
- TransportLagThreshold.
- NetTimeout.
- ReopenSecs.
- StandbyFileManagement.
- PreferredApplyInstance in RAC depending on configuration.

Property names, values, and support depend on release. Use SHOW DATABASE VERBOSE and EDIT DATABASE per documentation, avoiding unverified settings.

## 14. Switchover: Planned Role Transition

Switchover is a planned reversal of primary and standby roles. It is commonly used for primary maintenance or DR drills. The goal is a controlled transition with zero data loss when the standby is fully synchronized.

### 14.1. Preconditions Before Switchover

- Both primary and standby are healthy.
- Transport/apply lag is 0 or meets acceptable conditions.
- No archive gaps exist.
- Standby has applied all required redo.
- Suitable SRLs and transport configurations exist on both sites.
- Network and listeners are stable.
- Services, client routing, and monitoring transition plans are ready.
- Backup/recovery state confirmed.
- Approved change window and designated owner.

### 14.2. Switchover with Broker

Example:

~~~text
DGMGRL> SHOW CONFIGURATION;
DGMGRL> VALIDATE DATABASE 'PROD_STBY';
DGMGRL> SWITCHOVER TO 'PROD_STBY';
~~~

Broker orchestrates the role transition according to configuration. Afterward, verify the former primary has become a physical standby and redo transport/apply operates in the reverse direction.

### 14.3. Manual Switchover

Manual commands vary by release and state. In supported versions, `ALTER DATABASE SWITCHOVER TO ...` with the VERIFY option may be available. Do not reuse one legacy command sequence across all versions.

Broker generally reduces the risk of missed steps and should be favored when deployed. If performing manually, follow the exact runbook for your Oracle release.

### 14.4. After Switchover

Verify:
- DATABASE_ROLE on both sites.
- OPEN_MODE.
- LOG_ARCHIVE_DEST_STATUS.
- MRP running on the new standby.
- Transport/apply lag back within target.
- Application services pointing to the new primary.
- Backups, monitoring, and alert routing updated for the new roles.
- Required PDBs/services opened and registered.

Database-level switchover completion does not guarantee the entire application stack has finished transitioning.

## 15. Failover: Role Transition When the Primary Fails

Failover transitions a standby to primary when the former primary can no longer serve. It is an emergency operation that can incur data loss depending on protection mode and untransported/unapplied redo.

### 15.1. Before Failover

Verify:
- The primary genuinely cannot be recovered within the allowed timeframe.
- There is no risk of the old primary continuing independent writes causing split-brain.
- Which standby holds the most recent redo.
- Transport/apply lag and archive gaps.
- Whether unshipped redo logs can still be retrieved from the former primary.
- Acceptable RPO and authorized failover decision-maker.

Do not fail over merely because an application cannot connect to the primary; the fault could be a listener, service, network, or transient host issue. First verify the primary's true state and the risk of dual-write split-brain.

### 15.2. Failover with Broker

Illustrative example:

~~~text
DGMGRL> SHOW CONFIGURATION;
DGMGRL> FAILOVER TO 'PROD_STBY';
~~~

Syntax depends on standby state and release; Broker supports different failover types. Execute only under incident runbooks and proper authorization.

### 15.3. Complete vs. Immediate Failover

Some procedures distinguish a failover that attempts to apply all retrievable redo from an immediate failover that bypasses remaining apply steps. Option names and syntax depend on release and Broker/manual mode.

- Attempting to complete apply minimizes data loss but takes longer.
- Immediate failover restores service faster while accepting higher risk of losing unapplied redo.

Do not choose an option based on speed alone. Weigh RTO/RPO and recoverable redo.

### 15.4. Handling the Former Primary After Failover

Once the standby becomes primary:
- Prevent the former primary from opening READ WRITE and accepting traffic.
- Isolate or shut down the former primary to avoid split-brain.
- Determine whether it can be reinstated via Flashback Database and Broker or must be rebuilt.
- Reconfigure transport from the new primary.
- Check any remaining standbys.
- Back up the new primary per procedure.
- Update client services/DNS/load balancers.
- Record any data-loss window.

If Flashback Database was enabled and prerequisites are met, Broker supports REINSTATE DATABASE to turn the former primary back into a standby. If sufficient flashback logs are lacking or incarnations diverge, the standby must be rebuilt.

## 16. Role Transitions and Applications

Data Guard transitions database roles, but applications must also be coordinated.

### 16.1. Services

Design database services so applications connect only to the appropriate role. In RAC, use Clusterware-managed services; in Data Guard, role-based services can automatically start on the designated database role per configuration.

### 16.2. Connection Pools

During switchover/failover:
- Old connections may drop.
- Pools must reconnect to the new primary's service.
- Retries must use backoff.
- In-flight transactions may roll back or need application-level retries.
- Never blindly retry non-idempotent operations.

### 16.3. Client Failover

Use Oracle Net/SCAN/services and appropriate client failover settings. Transparent Application Failover, Application Continuity, and Transaction Guard have distinct capabilities and prerequisites; do not assume applications automatically switch connections without configuration.

### 16.4. Periodic Testing

A DR plan is trustworthy only after testing:
- Planned switchover.
- Scripted failover scenarios.
- Client reconnection.
- Role-based service start/stop.
- Backups after role transition.
- Standby reinstatement or rebuild.
- Measuring actual RTO/RPO.

## 17. Real-Time Apply and Active Data Guard

### 17.1. Real-Time Apply

Real-time apply allows MRP to apply redo directly from SRLs while the primary is still writing to online redo logs. This reduces latency compared to waiting for archived redo logs to complete before applying.

Typical requirements include:
- Properly configured SRLs.
- Operational redo transport to the standby.
- Running managed recovery.
- Sufficient standby storage and apply capacity.

### 17.2. Active Data Guard

Active Data Guard allows a physical standby to be open READ ONLY while redo apply continues running, depending on version and configuration. It enables offloading read workloads such as reporting and analytics.

Requirements:
- Confirm Active Data Guard licensing.
- Evaluate whether read workloads impact apply.
- Monitor apply lag.
- Ensure queries do not overload the standby.
- Understand limitations of an open read-only standby.

Do not confuse basic Data Guard MOUNT + apply capability with concurrent READ ONLY + apply under Active Data Guard.

### 17.3. Standby Reporting Can Impact DR Readiness

If a standby serves heavy queries, CPU/I/O is shared with redo apply. This increases apply lag. Implement resource plans, workload limits, and lag thresholds aligned with RPO.

## 18. Data Guard with RAC

RAC and Data Guard address two distinct availability layers:
- RAC allows multiple instances to access one database within a cluster.
- Data Guard maintains a standby database at another site/cluster to protect against database/storage/site failures.

### 18.1. Redo Threads

Each RAC instance has its own redo thread. The standby must have appropriate SRLs for every thread capable of sending redo.

~~~sql
SELECT thread#,
       group#,
       bytes,
       status
FROM v$log
ORDER BY thread#, group#;
~~~

In RAC, use GV$LOG to inspect per-instance/thread details where appropriate.

### 18.2. SRLs per Thread

Create sufficient SRL groups for every thread. Do not create SRLs solely for thread 1 when a RAC primary has multiple threads.

### 18.3. Apply Instance

Depending on configuration and release, managed recovery may run on one instance or leverage RAC-aware apply capabilities. Data Guard Broker provides properties to control the preferred apply instance in certain environments. Verify specific configuration and process status via GV$ views.

### 18.4. Checking All Instances

Use GV$DATABASE, GV$INSTANCE, GV$ARCHIVE_DEST_STATUS, and GV$DATAGUARD_PROCESS where supported. Retain INST_ID to avoid conflating cluster members.

## 19. End-to-End Monitoring

An effective Data Guard dashboard should display the health of both sites and the entire pipeline.

### 19.1. On the Primary

Monitor:
- DATABASE_ROLE and PROTECTION_LEVEL.
- LOG_ARCHIVE_DEST_n status/errors.
- Redo generation rate.
- Archive log switch rate.
- Network destination states.
- Broker configuration status.
- Primary alert log.

### 19.2. On the Standby

Monitor:
- DATABASE_ROLE and OPEN_MODE.
- MRP/RFS processes.
- Transport lag and apply lag.
- Archive gaps.
- SRL usage.
- Apply throughput.
- FRA/archive destinations.
- Datafile/storage health.
- Standby alert log.

### 19.3. Lag Thresholds

Thresholds should align with RPO and workload:
- Warning when lag exceeds normal budgets.
- Critical when lag approaches RPO or climbs steadily.
- Emergency when transport/apply stops or an archive gap cannot self-resolve.

Do not apply the same second threshold to every database. An RPO 0 system has very different requirements from one tolerating several minutes of data loss.

### 19.4. Metric Freshness

V$DATAGUARD_STATS includes TIME_COMPUTED and DATUM_TIME. Inspect both timestamps to ensure metrics are updating. A stale low lag figure is not evidence that transport/apply is currently healthy.

### 19.5. Alerting

Use Enterprise Manager, Data Guard Broker health checks, or external monitoring systems. Alerts should include DB_UNIQUE_NAME, role, INST_ID, transport/apply lag, last datum time, archive destination errors, MRP/RFS state, archive gaps, and runbook links.

## 20. Troubleshooting Rising Transport Lag or Apply Lag

### 20.1. Rising Transport Lag

Investigate in order:
1. On the primary, check LOG_ARCHIVE_DEST_STATUS and ERROR.
2. Check Oracle Net services, listeners, and network routes.
3. Check the standby listener/service.
4. Check the RFS process.
5. Check SRLs and archive destination storage.
6. Compare redo generation rate against network throughput.
7. Check alert logs on both sides.
8. Check for archive gaps or DEFERred destinations.

If a network outage occurred, restore connectivity and confirm transport resumes. Never delete archives to "reset" lag.

### 20.2. Rising Apply Lag With Low Transport Lag

Investigate:
- Is MRP running?
- Is MRP waiting on a gap or actively applying?
- Is standby CPU saturated?
- Has datafile I/O latency risen?
- Is the standby running heavy reports/queries?
- Is recovery parallelism appropriately configured?
- Are there corruption errors or datafiles needing recovery?

You may need to throttle read workloads, add standby resources, or clear a recovery backlog.

### 20.3. MRP Stopped

Check V$DATAGUARD_PROCESS/V$MANAGED_STANDBY, V$DATAGUARD_STATUS, alert logs, archive gaps, and file/storage errors. After fixing the root cause, restart managed recovery per database state and runbook. Avoid repeatedly issuing START/STOP apply commands without checking current process state.

### 20.4. Unresolved Archive Gaps

- Identify missing thread and sequence numbers.
- Check if logs remain on primary/FRA/backups.
- Check FAL/network/password files.
- Fetch or restore the exact archived logs.
- Register them if required by procedure.
- Confirm MRP resumes and subsequent gaps clear.

## 21. Common Data Guard Errors

| Error / Situation | Possible Causes | What to Check |
| --- | --- | --- |
| ORA-16047 | DB_UNIQUE_NAME mismatch with destination | LOG_ARCHIVE_DEST_n, DB_UNIQUE_NAME, LOG_ARCHIVE_CONFIG |
| ORA-12514 | Listener does not recognize service | TNS alias, listener services, service registration |
| ORA-12541 | No listener at endpoint | Listener, host, port, network |
| ORA-12154 | Could not resolve connect identifier | tnsnames.ora, naming method, service alias |
| ORA-16055 | FAL request rejected | FAL source, archive availability, role/config |
| ORA-00279/ORA-00289 | Recovery requires archived log | Thread/sequence, archive location, gaps |
| ORA-00308 | Cannot open archived log | File path, permissions, storage, archive integrity |
| ORA-01153 | Recovery already running or conflicting recovery | MRP state and recovery commands |
| ORA-01157/ORA-01110 | Cannot identify/open datafile | Datafile path, storage, control file, file state |
| ORA-19809 | FRA limit exceeded | FRA usage, archive/backup retention |
| MRP not running | Apply stopped, file/gap error, or misconfiguration | Broker, alert log, V$DATAGUARD_PROCESS |
| Rising transport lag | Network, RFS, destination, or redo rate | Destination status, network, RFS, SRL |
| Rising apply lag | MRP/CPU/I/O unable to keep up | Apply process, storage latency, standby workload |
| Invalid switchover | Standby unsynchronized or missing prerequisite | Broker validate, lag, role/status, alert log |

Error codes and behavior may differ by release and state. Always read the full error stack and alert logs rather than relying solely on an error code.

## 22. Securing and Operating Data Guard Connectivity

Redo transport relies on Oracle Net connections and authentication between databases. Security configuration should be treated as part of DR design.

- Keep password files synchronized as required and manage credentials securely.
- Never hardcode passwords in scripts, shell history, or logs.
- Restrict SYSDBA privileges and host access.
- Use network encryption/TLS per policy.
- Restrict network routes and firewall rules to required endpoints.
- Track certificate/wallet changes when using TLS.
- Protect backups, archived redo, and standby storage.
- Verify ASM/filesystem read/write permissions.
- Synchronize system clocks for reliable log correlation.

A healthy Data Guard configuration with unprotected credentials or networks remains a severe security risk.

## 23. Daily Data Guard Health Check Runbook

### 23.1. On the Primary

~~~sql
SELECT db_unique_name,
       database_role,
       open_mode,
       protection_mode,
       protection_level
FROM v$database;
~~~

~~~sql
SELECT dest_id,
       status,
       error,
       destination
FROM v$archive_dest_status
WHERE status <> 'INACTIVE';
~~~

### 23.2. On the Standby

~~~sql
SELECT db_unique_name,
       database_role,
       open_mode
FROM v$database;
~~~

~~~sql
SELECT name,
       value,
       unit,
       time_computed,
       datum_time
FROM v$dataguard_stats
WHERE name IN ('transport lag', 'apply lag');
~~~

~~~sql
SELECT process,
       status,
       thread#,
       sequence#
FROM v$managed_standby;
~~~

If your release prefers V$DATAGUARD_PROCESS, query that view instead of V$MANAGED_STANDBY.

### 23.3. Checking Gaps and Broker

~~~sql
SELECT thread#,
       low_sequence#,
       high_sequence#
FROM v$archive_gap;
~~~

~~~text
DGMGRL> SHOW CONFIGURATION;
DGMGRL> SHOW DATABASE VERBOSE 'PROD_PRI';
DGMGRL> SHOW DATABASE VERBOSE 'PROD_STBY';
~~~

### 23.4. Recording Results

Daily checks should log timestamps, role/open mode of each member, transport/apply lag, last received/applied sequence or SCN, destination errors, MRP/RFS states, archive gaps, FRA/storage headroom, Broker status, and any changes since the prior check.

## 24. Designing RPO/RTO for Data Guard

Data Guard must align with business objectives.

### 24.1. RPO

Recovery Point Objective is the maximum data loss an organization tolerates during an incident. With ASYNC, untransported redo creates data-loss exposure. With properly configured synchronous protection, zero data loss can be targeted within the corresponding failure model.

RPO depends not only on protection mode, but also on whether the standby is actually synchronized, network and standby availability, SRL/AFFIRM semantics, archive gaps, and incident type.

### 24.2. RTO

Recovery Time Objective is the maximum time allowed to restore service. RTO includes:
- Incident detection.
- Failover decision.
- Executing role transition.
- Opening database/services.
- Client reconnection.
- Health checks and application verification.

A synchronized standby without runbooks, service routing, and on-call staff may still fail to meet RTO.

### 24.3. Testing RPO/RTO

Measure during DR exercises:
- Detection time.
- Decision time.
- Failover/switchover duration.
- Application reconnection time.
- Last applied SCN/transaction.
- Data loss, if any.
- Time to reinstate/rebuild the former primary.

Do not record merely Data Guard status SUCCESS; measure recovery at the application level.

## 25. Common Misconceptions

**A physical standby replaces backups.** Incorrect. Standbys can receive deletions and logical errors; independent backups remain mandatory.

**Transport lag and apply lag are the same.** Incorrect. Transport lag measures unreceived redo; apply lag measures redo not yet applied to datafiles.

**Standby receiving archived redo means apply is complete.** Incorrect. Receiving and applying are two separate stages.

**Standby Redo Logs are unnecessary if online redo logs exist.** Incorrect. SRLs are where standbys receive live redo directly and enable real-time apply/transport protection.

**SRLs are only needed on the current standby.** Incorrect. Databases can swap roles; prepare SRLs on all members that could become a standby.

**ASYNC guarantees zero data loss.** Incorrect. Untransported redo can be lost if the primary fails.

**SYNC never impacts latency.** Incorrect. The commit path can be sensitive to network RTT and standby I/O.

**NOAFFIRM is identical to AFFIRM.** Incorrect. Acknowledgment and durable-write semantics differ.

**Zero lag at one snapshot guarantees the standby is always synchronized.** Incorrect. Check freshness and trends across multiple samples.

**MRP running means the standby is keeping up.** Incorrect. MRP can run while its apply rate lags behind the incoming redo rate.

**FAL replaces backups.** Incorrect. FAL fetches available archived redo; it cannot recreate logs lost from all sources.

**Old archived redo can be deleted directly via OS commands.** Incorrect. Doing so can break recovery chains or standbys; use RMAN policies.

**Switchover and failover are the same.** Incorrect. Switchover is a planned role transition; failover is an emergency response when the primary cannot continue serving.

**The former primary can be opened READ WRITE after failover.** Never do so carelessly. Isolate and reinstate/rebuild it to prevent split-brain.

**CDB OPEN means all PDBs/services are ready.** Incorrect. Verify PDBs and services individually.

**Active Data Guard is just another name for physical standby.** Incorrect. Capabilities such as concurrent read-only open during apply belong to Active Data Guard and carry separate licensing requirements.

## 26. Self-Practice Exercises

1. Explain the roles of primary and physical standby.
2. Distinguish physical standby from logical standby.
3. Diagram the pipeline from LGWR to RFS, SRL, and MRP.
4. What are the roles of LNS and ARCn in redo transport?
5. Why do standby redo logs differ from online redo logs?
6. State the sizing principle for SRLs.
7. State the count principle for SRLs per redo thread.
8. Why should SRLs be created on both database members?
9. Distinguish redo transport from redo apply.
10. Distinguish transport lag from apply lag.
11. List causes of increasing transport lag.
12. List causes of increasing apply lag.
13. Compare Maximum Protection, Maximum Availability, and Maximum Performance.
14. Distinguish SYNC from ASYNC.
15. Distinguish AFFIRM from NOAFFIRM.
16. Why can SYNC increase commit latency?
17. Explain the roles of DB_NAME and DB_UNIQUE_NAME.
18. Why is LOG_ARCHIVE_CONFIG DG_CONFIG needed?
19. Explain VALID_FOR in LOG_ARCHIVE_DEST_n.
20. What is the role of STANDBY_FILE_MANAGEMENT=AUTO?
21. What problem does FAL_SERVER solve?
22. Write a query to inspect V$DATAGUARD_STATS.
23. Write a query to inspect V$ARCHIVE_DEST_STATUS.
24. Write a query to detect archive gaps.
25. How do you handle situations where FAL cannot fetch an archived log?
26. Distinguish real-time apply from applying from archived logs.
27. Which operations does Data Guard Broker assist with?
28. Distinguish switchover from failover.
29. Why must the former primary be isolated after failover?
30. Design a DR runbook covering RPO/RTO, lag checks, role transition, client reconnection, and reinstatement/rebuild.

**Data Guard keeps a physical standby synchronized with the primary through two distinct stages: redo transport delivers redo to the standby, and redo apply uses that redo to update datafiles.** Properly configure DB_UNIQUE_NAME, networking, archive destinations, and standby redo logs; select protection/transport modes based on RPO, RTO, and latency; and monitor both transport lag and apply lag alongside metric freshness. When transitioning roles, distinguish planned switchover from emergency failover, isolate the former primary, and test both the database and applications after transition.
