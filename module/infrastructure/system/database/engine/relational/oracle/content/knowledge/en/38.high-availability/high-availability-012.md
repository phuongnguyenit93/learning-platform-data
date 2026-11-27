# Comparing RAC, Data Guard, and Active Data Guard Against Oracle Editions and Licensing

Oracle RAC, Oracle Data Guard, and Oracle Active Data Guard all support high availability, yet they solve different problems. RAC lets multiple instances access a single shared database to maintain service when an instance or node fails. Data Guard maintains one or more separate standby databases receiving and applying redo from the primary to recover when a site or primary database fails. Active Data Guard adds the ability to open a physical standby for read-only queries while Redo Apply continues running, providing both DR protection and read workload offloading.

These technologies do not fully replace one another. RAC does not fully protect against shared storage/site loss or erroneous logical operations committed to the shared database; Data Guard provides a copy in a separate failure domain. Active Data Guard adds standby querying, but carries a separate license option requirement. An architecture can combine RAC at the primary with Data Guard/Active Data Guard at the standby site.

When selecting an architecture, answer three separate questions:

1. **Which failure domains require protection?** Instance, node, storage, database, site, or logical errors?
2. **Which workloads must be served?** Read/write transactions, read-only queries on standby, reporting, or disaster recovery?
3. **Which edition and entitlements cover the deployment?** Oracle Database edition, RAC option, Active Data Guard option, Processor/Named User Plus metrics, standby/failover rights, and specific contract terms.

Never conclude that because a feature is technically supported, the organization holds commercial rights to use it. Usage rights depend on release, edition, options, license metrics, hardware, node/server counts, standby usage, and active ordering documents/contracts. Before deploying to production, verify against the Oracle Licensing Information User Manual for your exact release, Oracle price lists/contracts, and confirm with License Management/Oracle whenever anything is unclear.

This lesson belongs to the **High Availability** topic of *Database Engine Relational Oracle*. It focuses on:

- Architecture and failure domains of RAC, Data Guard, and Active Data Guard.
- Comparing HA, DR, RPO/RTO, read scaling, and limitations of each solution.
- Basic Data Guard vs. Active Data Guard real-time query.
- Editions and options: Enterprise Edition, Standard Edition 2, RAC option, Active Data Guard option.
- Processor and Named User Plus license metrics.
- Rights governing standbys, failover, RAC nodes, and DR sites.
- Combined RAC + Data Guard scenarios.
- Selection matrix by business requirement.
- Entitlement verification, monitoring, drills, and common deployment mistakes.

## 1. Distinguishing HA, DR, and Read Scaling

### High Availability (HA)

High Availability aims to minimize service unavailability when a component fails. HA designs use redundancy, clustering, failover, connection retries, and monitoring to shift workloads to surviving components.

Examples:

- One Oracle instance crashes while another instance continues serving the same database.
- A database node fails and services relocate to a surviving node.
- Sessions reconnect/replay per application and driver capabilities.

HA does not mean every in-flight transaction continues undisturbed. Sessions can drop, uncommitted transactions roll back, and clients must retry with idempotency guarantees.

### Disaster Recovery (DR)

DR aims to restore service after major incidents such as losing a site, storage subsystem, database, or faults rendering the primary unusable. DR typically requires a data copy in an independent failure domain, failover procedures, DNS/service routing, and a failback plan.

Key questions:

- How far has the standby received redo?
- Is zero RPO required or is some data loss acceptable?
- Is failover automatic or does it require manual approval?
- How long does total RTO take, including detection, failover decision, mount/open, and connection rerouting?
- Is there a failback/switchover path back to the primary site?

### Read Scaling

Read scaling distributes read workloads across multiple resources to offload the primary or boost query capacity. RAC serves workloads across multiple instances on one database; Active Data Guard offloads read-only queries to a physical standby while redo apply continues.

Read scaling must consider data consistency and lag. Reports on a standby can read older data than the primary whenever apply lag is non-zero. Do not route workflows requiring immediate read-after-write consistency to a read-only standby without an appropriate consistency mechanism.

### RPO and RTO

- **RPO (Recovery Point Objective):** maximum data loss tolerated by the organization, typically expressed in time or transaction points.
- **RTO (Recovery Time Objective):** maximum allowed time to restore service after an incident.

RAC typically reduces downtime from instance/node failures within the same cluster while database files remain intact on shared storage. Data Guard protects against broader failure domains using a separate standby database. Active Data Guard adds standby querying while apply runs.

Actual RPO/RTO depend on architecture, transport mode, apply lag, automation, detection, application reconnection, and rehearsal. No product guarantees RPO/RTO merely by being installed.

## 2. What Is Oracle RAC?

Oracle Real Application Clusters (RAC) allows multiple database instances on separate nodes to concurrently access one shared database. Instances maintain separate buffer caches while sharing datafiles, control files, and online redo in a supported cluster/storage architecture.

### Conceptual Architecture

~~~text
             Applications / Services
                /             \
               /               \
        RAC Node 1            RAC Node 2
        Instance 1            Instance 2
        SGA / Buffer Cache    SGA / Buffer Cache
               \               /
                \             /
             Shared Database Storage
       Datafiles / Control Files / Redo / ASM
~~~

Oracle Clusterware manages cluster resources, membership, voting/OCR, and database services per configuration. ASM commonly manages storage, though exact architectures vary by environment.

### What Does RAC Protect Against?

- Instance failures: surviving instances continue serving configured services.
- Node failures: workloads shift to healthy nodes.
- Node maintenance: many operations support rolling procedures if architecture/release allow.
- Scale-out: multiple instances increase capacity for suitable parallelizable workloads.

### What Does RAC Not Protect Against by Itself?

- Loss of entire shared storage or a shared failure domain.
- Logical data corruption from erroneous `DELETE`/`UPDATE` committed to the shared database.
- Corruption propagating across the shared database or storage.
- Loss of the entire site without a copy at another site.
- Applications failing to handle session loss, transaction rollbacks, or retries.

RAC is one database with multiple instances, not two independent databases. Therefore, committed data changes on one instance are seen across the shared database by other instances.

### Services and Client Failover

RAC uses database services to distribute connections. Applications must connect by service name with drivers/configurations supporting appropriate failover/reconnection. Features such as Fast Application Notification (FAN), Fast Connection Failover (FCF), Application Continuity, or Transparent Application Continuity depend on drivers, editions/options, and configuration; never assume they work automatically just because RAC is installed.

### RAC and Transactions

When a node fails:

- Sessions attached to that node may drop.
- Uncommitted transactions require rollback/recovery.
- Surviving instances perform cache/instance recovery per cluster architecture.
- Clients must reconnect/retry per application logic.

RAC improves availability, yet does not guarantee zero disruption for every active request.

## 3. What Is Oracle Data Guard?

Oracle Data Guard maintains one or more standby databases to protect a primary database. The primary ships redo to standbys; standbys receive and apply redo to keep data synchronized.

### Basic Architecture

~~~text
          Primary Database
             LGWR/ARCH
                 |
           Redo Transport
                 |
        Network / WAN / Site link
                 |
           Standby Database
        Standby Redo Logs (SRL)
                 |
             Redo Apply
                 |
          Standby Datafiles
~~~

### Physical Standby

A physical standby maintains a block-level copy of the primary via redo apply. Physical datafile structure fundamentally mirrors the primary. This is the most common DR choice and the foundation for Active Data Guard real-time query.

### Logical Standby

A logical standby applies equivalent SQL derived from redo instead of maintaining an identical block-level copy. It permits certain structural differences and local workloads on the standby, subject to data type/object restrictions and compatibility testing. Not all schemas/objects are equally supported.

### Snapshot Standby

A snapshot standby temporarily converts a physical standby into a read/write database for testing. Redo apply pauses during snapshot mode; when converted back to physical standby, local changes are discarded and accumulated redo is applied per procedure. Snapshot standby is not intended for long-term production write workloads.

### Redo Transport and Apply

- Redo transport ships redo from primary to standby.
- Standby redo logs (SRL) receive redo when properly configured.
- Redo Apply applies redo onto the physical standby.
- Archive logs and transport/apply services preserve the synchronization chain.

Monitor transport lag and apply lag to know how far behind a standby sits. A standby that exists without properly receiving and applying redo fails DR objectives.

### Switchover and Failover

- **Switchover:** planned role reversal, typically zero data loss when synchronization preconditions hold.
- **Failover:** promoting a standby to primary when the primary cannot continue; potential data loss depends on protection mode and received redo.
- **Reinstate:** returning the former primary as a standby when conditions and tools support it.

Data Guard Broker simplifies configuration management, switchover/failover, and monitoring. Fast-Start Failover (FSFO) automates failover via Observer/Broker rules; quorum, observer placement, thresholds, and fencing must still be designed to prevent split-brain.

## 4. What Is Active Data Guard?

Active Data Guard is an option extending Data Guard. Its most cited capability is **real-time query**: opening a physical standby in read-only mode while Redo Apply keeps running. Consequently, the standby stays synchronized with redo while serving read/reporting queries.

### Basic Data Guard vs. Active Data Guard

| Capability | Basic Data Guard | Active Data Guard |
| --- | --- | --- |
| Physical standby receives redo | Yes | Yes |
| Redo Apply on standby | Yes | Yes |
| Open physical standby read-only while apply runs | Not a real-time query entitlement in Basic Data Guard | Yes, via Active Data Guard real-time query |
| Stop apply then open read-only for inspection | Possible per procedure, but apply must stop | Yes; also supports read-only queries while apply continues |
| Offload near-real-time reporting | Limited because apply stops during basic read-only open | Yes, depending on apply lag, workload, and config |

The key distinction is concurrency. With Basic Data Guard, a physical standby can open read-only in certain procedures, yet Redo Apply does not run concurrently as in the Active Data Guard model. Active Data Guard allows read-only queries while apply continues running.

### Real-Time Query

A physical standby can serve read-only queries while receiving and applying redo. Queries see data consistent with standby read-consistency; if apply lag is non-zero, results trail the primary.

Applications must know:

- Whether queries run on the standby or primary.
- Current standby apply lag and transport lag.
- Whether eventual/near-real-time data is acceptable.
- Whether immediate read-after-write after primary transactions is required.
- Whether queries contend for CPU/I/O with redo apply.

### Other Capabilities of Active Data Guard

The Active Data Guard option may include additional advanced capabilities depending on release, such as automatic block repair, Far Sync, and related protection/availability features. Do not extrapolate feature lists from one release to another; check the Oracle Licensing Information User Manual and feature matrix for your exact version.

### Active Data Guard Is Not RAC

Active Data Guard real-time queries run against a separate standby database, usually at another site or failure domain. It does not turn the standby into a second read/write instance on the same shared database like RAC. The physical standby continues applying redo via Data Guard and restricts direct writes.

## 5. Data Guard Protection Modes and RPO

Data Guard provides protection modes defining how the primary waits for redo delivery to standbys. Choosing a mode trades off data protection, latency, and transaction continuity during standby/network outages.

| Protection Mode | Typical Redo Transport | Objective | Trade-Off |
| --- | --- | --- | --- |
| Maximum Protection | Synchronous transport with redo write acknowledgment per protection setup | Zero committed data loss while configured protection holds | If no synchronized standby remains eligible, primary may halt to avoid data loss |
| Maximum Availability | Synchronous transport; primary keeps running if standby conditions temporarily fail per mode rules | Zero data loss when synchronous standby is ready; prioritizes availability when standby disconnects | May drop to lower protection during failures depending on state |
| Maximum Performance | Typically asynchronous transport | Prioritizes primary performance; RPO depends on unshipped redo | Unreceived redo may be lost if primary/site fails abruptly |

Exact transport attribute names, SYNC/ASYNC, AFFIRM/NOAFFIRM, and behaviors depend on configuration and release. Design strictly per Oracle documentation and test failure scenarios.

### SYNC and ASYNC

- SYNC requires the primary to wait for standby acknowledgment per configured mode before completing certain commit paths; transaction latency reflects network/storage latency.
- ASYNC ships redo asynchronously, insulating primary latency while risking redo gaps if the primary fails before redo ships.

Do not inspect only protection mode in `V$DATABASE`. Verify transport destination attributes, standby redo logs, networking, apply processes, and actual protection level.

### Checking Protection Mode and Level

~~~sql
SELECT protection_mode,
       protection_level,
       database_role,
       switchover_status
FROM v$database;
~~~

`PROTECTION_MODE` is the configured mode; `PROTECTION_LEVEL` reflects the level currently achieved at observation time. They diverge if standbys/destinations fail to meet requirements.

### Transport Lag and Apply Lag

~~~sql
SELECT name, value, unit, time_computed, datum_time
FROM v$dataguard_stats
WHERE name IN ('transport lag', 'apply lag', 'apply finish time');
~~~

Monitor lag continuously rather than only during drills. A small lag reading at one moment does not guarantee the standby continuously meets RPO.

## 6. Comparing RAC, Data Guard, and Active Data Guard

| Criterion | RAC | Basic Data Guard | Active Data Guard |
| --- | --- | --- | --- |
| Architecture | Multiple instances sharing one database | Separate primary and standby databases | Separate primary and physical standby |
| Failure domain | Instance/node within cluster | Database/site/storage per standby topology | Same as Data Guard |
| Storage | Typically shared storage/ASM for the database | Independent storage for standby | Independent storage for standby |
| Primary read/write | Yes across configured instances | Yes on primary | Yes on primary |
| Standby read-only while redo apply runs | Not applicable | Not under basic entitlement | Yes |
| Protection against site loss | Not provided natively | Yes when standby is at another site | Yes when standby is at another site |
| Offload reporting | Distributes workload across instances on same database | Read-only standby limited to paused apply | Offloads near-real-time read-only queries |
| RPO | No redo shipping to separate database; crash recovery uses shared database | Depends on sync/async and redo gaps | Depends on Data Guard transport/apply like Data Guard |
| RTO | Typically fast for instance/node failover while cluster is healthy | Depends on detection, role transition, mount/open, and app reconnect | Same as Data Guard |
| Committed logical errors | Shared across common database | Redo also propagates to standby; requires logical protection/restore points | Same as Data Guard |
| Primary license | RAC option or SE2 rights within version limits | Enterprise Edition Data Guard entitlement per release | Enterprise Edition + Active Data Guard option per entitlement |

### Conclusions by Failure Domain

- Need to keep serving when an instance/node fails within one site: RAC fits.
- Need an independent standby to recover when primary/site fails: Data Guard fits.
- Need to run reports on a physical standby while apply continues: Active Data Guard fits if licensed.
- Need both local HA and cross-site DR: combine RAC on primary/standby with Data Guard.

### Coexisting in One Architecture

~~~text
       Primary Site                         DR Site
   +------------------+                +------------------+
   | RAC Node 1       |                | RAC Node 3       |
   | RAC Node 2       | -- Redo -----> | RAC Node 4       |
   | Primary Database |                | Physical Standby |
   +------------------+                +------------------+
        |                                      |
   App Services                         Read-only reports
                                        (Active DG option)
~~~

RAC protects nodes/instances inside each site; Data Guard protects across databases/sites; Active Data Guard enables standby read workloads during redo apply. Each layer carries distinct licensing, infrastructure, monitoring, and operational procedures.

## 7. Editions and Options: Which Layers Must Be Distinguished?

Oracle Database software comprises editions, options, and management packs. These are distinct entitlement layers:

- **Edition** defines the base feature set of the database product, such as Standard Edition 2 or Enterprise Edition.
- **Database option** is an add-on feature licensed separately atop a supported edition, such as the Oracle RAC option or Active Data Guard option.
- **Management pack** is a separately entitled administration/monitoring suite, such as Diagnostics Pack and Tuning Pack.
- **License metric** defines how required license counts are calculated, such as Processor or Named User Plus.
- **Contract/ordering documents** establish the organization's exact usage rights, discounts, metrics, quantities, sites, and special terms.

A feature appearing in software binaries or dictionary views does not prove commercial entitlement to use it. Conversely, purchased editions/options must be deployed within exact version and contractual bounds.

## 8. Enterprise Edition, Standard Edition 2, and RAC

### Enterprise Edition (EE)

Enterprise Edition is the foundation for advanced HA/DR architectures. However, purchasing EE does not automatically include every option:

- Oracle RAC on Enterprise Edition is a separately licensed option under Oracle's licensing model.
- Active Data Guard is a separately licensed option.
- Basic Data Guard entitlement accompanies Enterprise Edition in common release licensing docs; still verify exact release and contract.
- Other capabilities like Partitioning, Advanced Compression, Diagnostics Pack, Tuning Pack, and additional options carry separate entitlements.

### Standard Edition 2 (SE2)

SE2 carries different technical and licensing limits from EE. In popular SE2 releases (notably 12.1.0.2/12.2/18c/19c), Oracle RAC was included with SE2 subject to socket/CPU thread and cluster node limits. Exact rules vary across releases/platforms and must be checked in the corresponding Licensing Information User Manual.

Common limits documented for earlier SE2 releases:

- Maximum of two CPU sockets per server as defined by Oracle.
- Cap on CPU threads usable per database instance.
- Cluster node limit for RAC (commonly max two nodes in referenced releases).

Do not carry numbers from an older release blindly to newer releases. Verify licensing docs for your exact version and server hardware.

### Data Guard with SE2

Do not assume SE2 includes Data Guard entitlement like Enterprise Edition. Oracle Data Guard availability/entitlement is tied to Enterprise Edition in standard licensing guides; Standard Edition 2 should not be assumed to include Data Guard merely because other replication mechanisms can be configured.

If DR is needed on SE2, evaluate solutions supported and properly licensed for your release, such as backup/restore, storage replication, or separately licensed replication technologies. Never call storage replication "Data Guard" when Data Guard is not licensed or running.

### Checking Edition from the Database

~~~sql
SELECT banner
FROM v$version;

SELECT parameter, value
FROM v$option
WHERE parameter IN ('Real Application Clusters');
~~~

`V$OPTION` shows whether features are enabled in binaries/configuration, not commercial license ownership. Verify edition across banners, software inventory, and contracts. Never cite `V$OPTION` as legal proof of entitlement.

## 9. Oracle RAC Option and License Metrics

### RAC on Enterprise Edition

The Oracle RAC option generally must be licensed on all servers/processors where RAC is installed or used per licensing rules. In multi-node clusters, do not count only nodes actively hosting workload at audit time; evaluate installation scope, failover configurations, and contractual terms.

### RAC in SE2

RAC may be included under SE2 within release-specific limits. Exceeding socket/thread/node caps or using EE-only features requires upgrading editions/architecture and licensing appropriately. Do not assume every two-node RAC cluster is compliant based solely on node count; hardware and version restrictions also apply.

### Processor Metric

The Processor metric typically multiplies Oracle-defined processor cores by the Core Factor Table, plus contract minimums/terms. Calculations differ across CPU architectures, platforms, and agreements.

Illustrative general formula for Processor licensing:

\[
\text{Processor licenses}
=
\text{Cores} \times \text{Core Factor}
\]

This is merely an illustrative model. Always apply the current official Core Factor Table and exact contract terms; never assume a default factor.

### Named User Plus (NUP)

NUP counts human users and non-human devices authorized to access the software per contract definitions, subject to Processor-based minimums and specific rules. With connection pools, application accounts, or indirect users, never equate database accounts with NUP counts. Count all direct and indirect users/devices per licensing rules.

### Where Must RAC Be Licensed?

RAC can expand license footprint because the option must be licensed across servers/processors within scope of option usage. In a cluster, evaluate every node where the RAC option is installed/enabled/used per contractual rules, not just the primary or active service node.

## 10. Basic Data Guard vs. Active Data Guard Option

### Basic Data Guard

Basic Data Guard ships with Enterprise Edition per licensing documentation across many releases, rather than being a separate paid option like Active Data Guard. Still, standby server rights, failover usage, standby counts, hardware, and operational usage must be verified in license agreements/ordering documents.

Never interpret "Data Guard included with EE" to mean "all standby servers and standby features are free." Database software on standbys, failover limits, usage restrictions, and other options may carry separate license obligations.

### Active Data Guard Option

Active Data Guard is a separately licensed option atop Enterprise Edition. Whenever option features are used—especially real-time query on a physical standby while Redo Apply continues running—appropriate entitlement is mandatory.

Depending on release, the Active Data Guard option may bundle extra capabilities such as automatic block repair, Far Sync, and features listed in the Licensing Information User Manual. Confirm feature lists and licensing conditions per version.

### Licensing Primary and Standby

Never assume Active Data Guard needs licensing only on the standby or only on the primary. Option licensing depends on how features are deployed/used, servers running the database/option, metrics, and Oracle terms governing standbys/DR. Check the exact licensing guide and organizational contracts before finalizing quantities.

### Read-Only Standby Does Not Automatically Mean Active Data Guard

A physical standby can open read-only in certain Basic Data Guard workflows once Redo Apply is stopped. That behavior differs from real-time query concurrent with apply. Simply seeing `READ ONLY` does not prove Active Data Guard usage; active apply state and utilized features determine option usage.

## 11. Standbys, Failover, and License Entitlements

Standby licensing is one of the most frequently misunderstood areas. Scenarios include:

- Physical standby continuously receiving/applying redo.
- Standby dedicated strictly to DR with zero read workloads.
- Standby opened read-only for reporting.
- Standby used for backups or testing.
- Standby activated as primary during failover.
- Former primary reinstated as standby.
- Multi-node/multi-instance clusters at both sites.

Each scenario can affect license requirements differently.

### Failover Rules Are Not Blank Checks

Oracle includes failover server policies in certain license agreements/guides, typically framed around annual failover-day limits and matching failover node rules. Exact conditions depend on applicable documents and contracts; never assume every Data Guard standby runs license-free.

### Active Data Guard and Standby Usage

Whenever a standby serves real-time queries, reporting, or Active Data Guard features, verify option licenses for all involved servers. Never argue a standby is "just DR" if it actively serves read workloads or option features.

### Backups on Standby

Offloading RMAN backups to a standby can carry different rules/conditions from running Active Data Guard real-time queries. Do not assume backup offload automatically requires or exempts the Active Data Guard option. Verify the release feature matrix and licensing guide.

### Test and Development

A standby used for testing, QA, UAT, or reporting may cease to qualify as passive failover infrastructure. Document usage purpose, duration, user access, enabled options, and license metrics. Disaster recovery terms do not automatically cover test environments.

## 12. Calculating License Footprint for HA/DR Architectures

To assess entitlement, build an inventory per database, server, and site rather than simply counting database instances.

### Information to Collect

- Oracle Database release, edition, and patch level.
- Oracle Homes, installed/used options, and database services.
- Hostnames, physical/virtual servers, CPU sockets, cores, and Core Factors.
- Contractual Processor or NUP metrics.
- RAC node counts and instances per node.
- Primary/standby roles and standby locations.
- Usage of Active Data Guard real-time query, Far Sync, or other option features.
- Backup, reporting, test, and batch workloads running on standbys.
- Failover policies, standby usage days, and DR terms.
- Any other enabled or utilized options and management packs.

### Illustrative Inventory Table

| Site | Server | Role | Edition | RAC | Data Guard | Active DG Usage | Metric / Quantity |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Primary | db01 | Primary node 1 | EE | RAC | Primary | No | Per contract |
| Primary | db02 | Primary node 2 | EE | RAC | Primary | No | Per contract |
| DR | db03 | Physical standby | EE | RAC/Single | Standby | Read-only query | Per contract |
| DR | db04 | Physical standby node 2 | EE | RAC/Single | Standby | Read-only query | Per contract |

This is merely an inventory template, not a determination of how many licenses each server requires. Populate metrics, option usage, and failover rights strictly per contract.

### Processor Metric and Core Factors

When contracts use Processor metrics, count cores in scope of Oracle software per Oracle rules and apply the appropriate Core Factor Table. Factors to verify:

- CPU model and cores per socket.
- Whether hyper-threading counts as cores under current metrics.
- Virtualization/hard partitioning policies and Oracle-recognized partitioning technologies.
- Core Factor Table version.
- Minimums and special contractual clauses.
- Whether standby/failover nodes qualify for exceptions/reductions under specific terms.

Never use VM vCPU counts as final license quantities without confirming Oracle partitioning policies. Soft partitioning rarely caps license footprints in the way many organizations assume.

### Named User Plus

For NUP, inventories must count authorized users and devices, including indirect access via applications, middleware, batch jobs, or service accounts per NUP rules. NUP carries Processor-based minimums and cannot be determined merely by counting rows in `DBA_USERS`.

### Option Licenses Bound to Servers/Processors

Options like RAC or Active Data Guard can require separate entitlement per server/processor where installed or used. Never assume buying EE on the primary automatically grants RAC or Active Data Guard across all DR servers.

### Virtualization, Cloud, and Engineered Systems

Licensing rules vary across VMware, Hyper-V, cloud IaaS, OCI, Exadata, and engineered systems. In particular, the scope of hosts/clusters Oracle deems capable of running the software affects Processor calculations. Apply Oracle's policy for your exact environment and contract rather than applying bare-metal assumptions to VMs or cloud.

## 13. Technical Checks Do Not Replace License Audits

DBAs can query which edition/options are configured and which features show usage. These queries aid technical inventorying, yet do not establish commercial entitlement.

### Checking Version and Edition

~~~sql
SELECT banner
FROM v$version;

SELECT product, version, status
FROM product_component_version;
~~~

### Checking Option Enablement

~~~sql
SELECT parameter, value
FROM v$option
ORDER BY parameter;
~~~

`V$OPTION` only shows whether options are enabled in binaries/configuration as reflected by the view. An option can be enabled without a license, or licensed without currently being enabled in a specific database.

### Checking RAC Runtime

~~~sql
SELECT instance_name,
       host_name,
       thread#,
       status,
       parallel
FROM gv$instance
ORDER BY inst_id;

SELECT name, value
FROM v$parameter
WHERE name IN ('cluster_database', 'cluster_database_instances');
~~~

In RAC, `GV$` views return data from cluster instances accessible to the query.

### Checking Data Guard Role and Mode

~~~sql
SELECT name,
       db_unique_name,
       database_role,
       open_mode,
       protection_mode,
       protection_level,
       switchover_status
FROM v$database;
~~~

### Checking Data Guard Lag

~~~sql
SELECT name, value, unit, time_computed, datum_time
FROM v$dataguard_stats
ORDER BY name;
~~~

### Checking Standby Open Mode

~~~sql
SELECT database_role, open_mode
FROM v$database;

SELECT process, status, thread#, sequence#
FROM v$managed_standby;
~~~

`V$MANAGED_STANDBY` is deprecated in newer releases; use `V$DATAGUARD_PROCESS` per release documentation when applicable. `READ ONLY WITH APPLY` is a technical indicator of Active Data Guard real-time query, though licensing must still be verified separately.

### Checking Feature Usage

`DBA_FEATURE_USAGE_STATISTICS` and feature-usage views help inventory certain features. However, feature-usage statistics are not license contracts, follow Oracle's internal sampling/lag mechanics, and do not cover every feature completely. Combine audits, configuration reviews, workload checks, and contract reviews.

## 14. Combined RAC and Data Guard Architectures

A system requiring both local HA and site-level DR can deploy RAC at the primary site and either RAC or a single-instance standby at the DR site.

### RAC Primary + Single-Instance Physical Standby

Advantages:

- Primary has HA across RAC nodes.
- DR site holds an independent database.
- RAC option cost may focus on the primary cluster if the standby does not run RAC, depending on license terms.

Trade-offs:

- DR failover may run with lower capacity than primary.
- On failover, verify services, instance resources, and connection routing.
- Standby and option licenses must still be verified against contracts.

### RAC Primary + RAC Standby

Advantages:

- Both primary and DR sites have intra-site HA.
- Hardware/topology parity simplifies failover performance expectations.
- Can distribute read workloads if Active Data Guard is licensed.

Trade-offs:

- Greater complexity across infrastructure, storage, networking, Clusterware, and operations.
- RAC option/SE2 limits and Active Data Guard options must be assessed at both sites.
- Role transitions, services, and node failure drills are more complex.

### Single-Instance Primary + RAC Standby

Can be used when DR requires different capacity/availability from primary, though not the default choice. Evaluate role transitions, parameter compatibility, redo transport, services, and RAC licensing on the standby.

### Data Guard with Multiple Standbys

Data Guard supports multiple standbys per architecture and release limits. Each standby serves a distinct purpose: DR, reporting, regional recovery, or testing. Extra standbys add network/storage/monitoring load and can expand license footprints; never assume a second standby is free.

## 15. Choosing Technology by Requirement

| Requirement | Solution to Evaluate | Why |
| --- | --- | --- |
| Single node/instance failure while shared storage stays healthy | RAC | Surviving instances on the shared database continue serving. |
| Loss of entire site or shared storage | Data Guard | Independent standby database in another failure domain. |
| Reporting on standby while redo apply continues | Active Data Guard | Real-time query on a physical standby. |
| Scale read capacity within same site on same database | RAC/service distribution or caching/reporting tier | Distributes workload while sharing the same database. |
| Scale read capacity at DR site | Active Data Guard | Offloads read-only queries to the standby. |
| Zero-data-loss DR | Data Guard Maximum Protection/Maximum Availability with SYNC and suitable infrastructure | Protects commits under configured conditions, latency, and availability. |
| Tolerable RPO of seconds/minutes | Data Guard ASYNC with monitoring/lag policy | Cuts primary latency while accepting redo gaps in certain failures. |
| Backup/restore suffices with longer RTO | RMAN + backup strategy | Sufficient when continuous standby availability is unnecessary. |
| Protection against logic errors / accidental deletes | Backups, Flashback, restore points, logical protection, and DR controls | RAC/Data Guard propagate erroneous committed changes. |

### Design Question Matrix

Before deciding, have architects/DBAs answer:

1. Are instance or node failures the main outage scope to mitigate?
2. Can shared storage or the entire site fail simultaneously?
3. Is RPO zero or is losing unshipped redo acceptable?
4. Is RTO measured from fault detection or from failover approval?
5. Must the standby open read-only while apply runs?
6. How much apply lag can queries tolerate?
7. Do primary and standby require identical node counts/capacity?
8. Do applications handle reconnection, retries, and idempotency?
9. Are licenses sufficient for edition, RAC/Active DG options, metrics, and nodes?
10. Are teams rehearsing switchover/failover and restores regularly?

## 16. Pre-Production License Review Checklist

Before purchasing, expanding a cluster, enabling Active Data Guard, or routing reporting to a standby, compile an entitlement dossier.

### Step 1: Identify Release and Edition

- Record exact Oracle Database release, Release Update, and platform.
- Identify Standard Edition 2 vs. Enterprise Edition.
- Identify related Oracle Homes, Grid Infrastructure, and database homes.
- Check edition technical limits in the exact release's licensing guide.

### Step 2: Inventory Actual Features

- RAC instances/nodes and RAC services.
- Data Guard primary/standby configurations.
- Physical, logical, or snapshot standbys.
- Active Data Guard real-time query.
- Far Sync, automatic block repair, or other option features.
- Diagnostics/Tuning Packs and other utilized options.
- Backup, reporting, test, and batch workloads on standbys.

### Step 3: Build Server and Metric Inventory

Record hostnames, CPU models, sockets, cores, VMs/hypervisors, cloud/engineered systems, Oracle Homes, node roles, and Processor/NUP metrics. When using virtualization, document CPU partitioning and applicable Oracle partitioning policies.

### Step 4: Review Licensing Documentation

Cross-check at minimum:

- Oracle Database Licensing Information User Manual for your exact release.
- Current Oracle Database Licensing Guide / price list.
- Current Core Factor Table if using Processor metrics.
- Organizational ordering documents, license certificates, contracts, and amendments.
- Terms for standby, failover, disaster recovery, test/development, and cloud.

Document titles and phrasing evolve across releases. Reference official documents matching your running software and purchase dates.

### Step 5: Map Features to Entitlements

| Feature / Usage | Base Edition | Option / Entitlement to Verify |
| --- | --- | --- |
| RAC on EE | Enterprise Edition | Oracle RAC option |
| RAC on SE2 | Standard Edition 2 | SE2 release RAC rights and hardware/node limits |
| Basic Data Guard | Enterprise Edition per standard licensing guides | Confirm Data Guard and standby/failover terms in contract |
| Active Data Guard real-time query | Enterprise Edition | Active Data Guard option |
| ASM / Clusterware | Per Oracle Grid Infrastructure / database architecture | Applicable product rights and conditions |
| AWR / ASH / SQL Tuning Advisor / Real-Time SQL Monitoring | Supported edition | Diagnostics Pack / Tuning Pack where features belong to packs |

This table is directional guidance, not a license quote. Feature entitlements can vary by release or contract.

### Step 6: Verify Standby/Failover Rights

Ask specific questions:

- Is the standby strictly passive or running read-only workloads?
- Does redo apply run continuously during queries?
- Is the standby used for backups?
- Does the standby run RAC?
- How many failover days/events are permitted under contract terms?
- After failover, may the former primary serve as standby and for how long?
- Are test/QA clones permitted under existing agreements?

Request written confirmation from License Management or Oracle whenever terms are ambiguous.

### Step 7: Archive Evidence

Retain inventories, query outputs, architecture diagrams, licensing guide versions, contract references, approvals, and review dates. Whenever adding nodes or enabling features, update the dossier prior to production rollout.

## 17. Operating and Monitoring RAC/Data Guard

Licensing is only one piece. An HA/DR architecture must be operated and tested to prove RPO/RTO.

### RAC Monitoring

Monitor:

- Clusterware node membership and resource status.
- Database instances and services.
- Interconnect latency and packet loss.
- Cache fusion traffic and global cache waits.
- ASM disk groups, rebalance operations, and storage health.
- Node evictions, instance recovery, and service relocation.
- Application reconnection, transaction retries, and connection pools.

Examples:

~~~sql
SELECT inst_id, instance_name, host_name, status
FROM gv$instance
ORDER BY inst_id;

SELECT inst_id, name, open_mode, database_role
FROM gv$database
ORDER BY inst_id;
~~~

Detailed cluster state typically requires Grid Infrastructure tools/views such as `CRSCTL`/`SRVCTL` and ASM views. Use the proper Oracle Home and OS privileges.

### Data Guard Monitoring

Monitor:

- Transport lag and apply lag.
- Redo transport destination status/errors.
- Standby redo log availability.
- Managed recovery process.
- Archive gaps and sequence gaps.
- Broker configuration/status.
- Protection mode and protection level.
- Observer status if using FSFO.

Examples:

~~~sql
SELECT name, value, unit, time_computed, datum_time
FROM v$dataguard_stats
WHERE name IN ('transport lag', 'apply lag');

SELECT dest_id, status, error, destination
FROM v$archive_dest_status
ORDER BY dest_id;
~~~

Some views/columns vary by release and database role. With Data Guard Broker, run `DGMGRL` `SHOW CONFIGURATION`, `SHOW DATABASE VERBOSE`, and `VALIDATE DATABASE` per version.

### Active Data Guard Monitoring

In addition to Data Guard metrics, monitor:

- Whether standby open mode is `READ ONLY WITH APPLY`.
- Query workloads and resource usage on the standby.
- Apply lag during reporting hours.
- Application query consistency and lag tolerance.
- Resource Manager plans and reporting workload limits.
- Licensing/feature usage aligned with entitlement.

### Drills

Rehearse regularly:

- Node/instance failure in RAC.
- Service relocation and application reconnection.
- Planned Data Guard switchover.
- Failover when the primary site is lost.
- Reinstating the former primary.
- Network/redo transport loss.
- Apply lag breaching thresholds.
- Standby read-only workloads impacting apply.

Record measured RTO/RPO rather than merely citing documented target RTO/RPO.

## 18. Sample Design Scenarios

### Internal OLTP App Needing Single-Site HA

If the primary need is staying online when a node/instance fails while shared storage and the site remain healthy, RAC can fit. Ensure matching database edition/options, cluster networking/storage, services, and client failover. Add Data Guard if site DR is required.

### Payment System Needing DR with Very Low RPO

Evaluate Data Guard synchronous transport and an appropriate protection mode. Measure network round-trip times and standby redo write latency. Maximum Protection can halt the primary if no eligible standby remains; Maximum Availability behaves differently when a standby drops. Select based on availability vs. data-loss tolerance, then rehearse.

### Heavy Reporting Workload on Standby

If reports must run while redo apply continues, evaluate Active Data Guard. Verify queries are strictly read-only, check apply lag, workload contention, and option licensing. If batch reports suffice and apply can pause during a dedicated window, Basic Data Guard may suffice per procedure.

### Small System Using SE2

If RAC is needed, verify exact SE2 release and server hardware limits. If Data Guard or Active Data Guard requirements exceed SE2 entitlements, evaluate EE with required options or an alternative licensed DR mechanism. Never design an architecture exceeding edition limits and defer license checks until later.

### Two Sites Needing Both HA and DR

RAC at the primary with Data Guard to DR is a classic pattern. RAC may also run on the standby if equivalent capacity/HA is needed. Active Data Guard is evaluated when the standby must serve read-only queries while applying redo. Every node, site, and option must appear in the license inventory.

## 19. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| RAC and Data Guard are two names for clustering | RAC runs multiple instances on one database; Data Guard maintains separate primary and standby databases. |
| RAC protects against losing an entire site | RAC does not automatically create a database copy at another site. |
| Data Guard always guarantees zero data loss | RPO depends on SYNC/ASYNC, protection mode, network, and standby state. |
| Basic Data Guard permits queries while apply runs | Real-time query on a physical standby while Redo Apply continues is an Active Data Guard capability. |
| Active Data Guard is just opening the standby READ ONLY | The distinction is concurrent read-only querying with active apply; read-only with paused apply is different. |
| Buying Enterprise Edition includes RAC | The RAC option for EE normally requires separate licensing. |
| SE2 allows any RAC configuration | SE2 RAC enforces release-specific limits on sockets, CPU threads, and nodes. |
| Data Guard standbys are always free of licensing | Standby/failover rights carry conditions; Active Data Guard and standby workloads require separate verification. |
| `V$OPTION = TRUE` proves an option was purchased | `V$OPTION` reflects technical state only, not commercial entitlement. |
| A standby can run reporting because it is for DR | Reporting can change licensing/option obligations and classification. |
| RAC fixes accidental `DELETE` errors | Committed logical changes propagate across all RAC instances and standbys via redo. |
| Failover never loses in-flight transactions | Active sessions/transactions can drop; applications must handle retries and idempotency. |
| One standby meets every DR goal | Must evaluate failure domains, RTO/RPO, independent backups, and simultaneous primary/standby loss. |

## 20. Practice Exercise: Building an Architecture and License Matrix

This lab does not require installing RAC/Data Guard or enabling licensed options. The objective is building an inventory from a hypothetical architecture and identifying documents to verify prior to deployment.

### Step 1: Describe Requirements

Assume an application requires:

- HA when a database node fails.
- DR at a second site.
- Target RPO under 5 seconds.
- Target RTO under 15 minutes.
- Reports tolerating up to 30 seconds of data lag.
- Primary handling OLTP read/write workload; standby serving read-only reporting.

### Step 2: Diagram the Architecture

~~~text
Primary Site                         DR Site
-------------                        --------
RAC Node A                           Standby Node C
RAC Node B  ---- Redo Transport ---> Physical Standby
Primary DB                           Redo Apply
Application services                 Read-only reporting
                                     (evaluate Active DG)
~~~

### Step 3: Select Technologies

- RAC handles node/instance failures at the primary site.
- Data Guard provides an independent standby at the DR site.
- If reporting must run while apply continues active, evaluate the Active Data Guard option.
- If reporting tolerates paused apply / batch windows, evaluate Basic Data Guard and operational schedules.

### Step 4: Document Assumptions to Verify

| Assumption | Verification Method |
| --- | --- |
| Edition supports planned RAC layout | Release-specific licensing guide and hardware inventory |
| RAC option has been purchased | Contracts/ordering documents and license inventory |
| Data Guard is supported/entitled | Edition matrix and contract |
| Active Data Guard option required | Confirm real-time query/apply behavior and feature list |
| Standby/failover servers are properly licensed | Standby/failover clauses and usage days |
| Processor/NUP counts sufficient | CPU/socket/core/virtualization or user/device inventory |
| RPO < 5 seconds achievable | Transport/apply testing under representative load |
| RTO < 15 minutes achievable | End-to-end failover drill measurement |
| Reporting lag < 30 seconds | Apply lag monitoring and query testing |

### Step 5: Collect Technical Data

On existing databases, run appropriate queries:

~~~sql
SELECT banner FROM v$version;

SELECT parameter, value
FROM v$option
WHERE parameter = 'Real Application Clusters';

SELECT name, db_unique_name, database_role,
       open_mode, protection_mode, protection_level
FROM v$database;

SELECT name, value, unit
FROM v$dataguard_stats
WHERE name IN ('transport lag', 'apply lag');
~~~

This forms the technical inventory; archive outputs alongside host/CPU inventories and license documents.

### Step 6: Build the Entitlement Table

Complete per contract:

| Server / Node | Edition | RAC Option | Active DG Option | Metric | Entitled Quantity | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| Primary A | ... | ... | ... | ... | ... | ... |
| Primary B | ... | ... | ... | ... | ... | ... |
| DR C | ... | ... | ... | ... | ... | ... |

Never populate quantity directly from CPU counts without applying Core Factor and virtualization rules.

### Step 7: Document Conditional Decision

Write a conditional architectural decision:

- Which architecture satisfies failure domains?
- Which options are required by utilized features?
- Which licenses must be purchased or adjusted?
- Which standby/failover terms require confirmation?
- Which assumptions must be tested before production?
- What actual RPO/RTO were measured after drills?

## 21. Self-Check Questions

1. **What problem does RAC solve?** Instance/node-level HA and scale-out when multiple instances access one database.
2. **What problem does Data Guard solve?** DR/availability using separate primary and standby databases synchronized via redo.
3. **How does Active Data Guard differ from Basic Data Guard?** Real-time query on a physical standby while Redo Apply continues running.
4. **Does RAC replace backups?** No; RAC does not protect against logic errors, corruption, or total shared storage loss.
5. **Does Data Guard always guarantee zero data loss?** No; depends on transport mode, protection mode, network, and received redo.
6. **What is RPO?** Maximum data loss tolerated under recovery objectives.
7. **What is RTO?** Maximum time allowed to restore service.
8. **What is a physical standby?** A standby copy applying redo at the physical block level.
9. **How does a logical standby differ from a physical standby?** Applies equivalent SQL and can allow structural differences within supported limits.
10. **Does a snapshot standby continue applying redo?** Not while in snapshot standby mode; apply resumes after converting back to physical standby per procedure.
11. **Does Basic Data Guard provide real-time query concurrent with apply?** Not under Basic Data Guard entitlement; that belongs to Active Data Guard.
12. **Does RAC on EE require a separate option license?** Yes, the RAC option is generally licensed separately.
13. **Does SE2 include RAC?** Popular SE2 releases include RAC rights with specific limits; verify exact release and hardware.
14. **Does SE2 automatically include Data Guard?** Never assume so; Data Guard entitlement aligns with EE in standard licensing guides.
15. **Does Active Data Guard require a separate license?** Yes, it is a separate option atop Enterprise Edition per entitlement.
16. **Does `V$OPTION = TRUE` prove a license was purchased?** No.
17. **Are standbys always license-exempt?** No; verify standby/failover terms, workloads, and option usage.
18. **How is the Processor metric calculated?** By cores/sockets and the applicable Core Factor Table/contract.
19. **Can NUP count only database users?** No; count authorized users/devices per NUP rules, including indirect access.
20. **Can RAC and Data Guard be combined?** Yes; RAC provides intra-site HA while Data Guard provides cross-site DR.
21. **Can Active Data Guard offload reporting?** Yes, via read-only queries on a physical standby while apply continues and licensing permits.
22. **Is read-after-write on a standby always instantaneous?** No; account for apply lag and consistency mechanisms.
23. **Are AWR/ASH/SQL Monitor always included in EE?** No; Diagnostics/Tuning Packs carry separate entitlements per feature/release.
24. **What proves entitlement?** Official license contracts/ordering documents and formal licensing policies, not SQL outputs alone.
25. **Why must failover be rehearsed?** To measure real RTO/RPO and validate applications, networking, services, redo, and operations teams.

RAC, Data Guard, and Active Data Guard address distinct needs. RAC keeps services running when instances/nodes fail on the same database; Data Guard maintains an independent standby for DR; Active Data Guard adds real-time read-only querying while redo apply continues. Proper selection starts from failure domains, RPO/RTO, and workloads, then cross-checks editions, options, metrics, and standby/failover rights in Oracle documentation and organizational contracts. Technical checks using `V$` views assist only with inventorying; they never replace license verification. Combine RAC with Data Guard when both local HA and site DR are required, and rehearse periodically to prove the architecture meets its goals.
