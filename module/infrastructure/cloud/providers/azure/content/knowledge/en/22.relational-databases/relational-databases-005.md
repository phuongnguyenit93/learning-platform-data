# SQL Server on Azure Virtual Machines

An enterprise operates an accounting system on **Microsoft SQL Server**, with stored procedures, SQL Server Agent jobs, linked servers, OS version control requirements, and Java/.NET applications accessing over a private network. The team wants to move the database to Azure without immediately changing instance-level features or traditional operational processes. **SQL Server on Azure Virtual Machines (SQL Server on Azure VMs)** moves SQL Server onto Azure virtual machines under the **Infrastructure as a Service (IaaS)** model, preserving high control over Windows/Linux, the SQL Server instance, storage configuration, connectivity, and high availability mechanisms.

The benefit is leveraging existing SQL Server expertise and many instance-level features. The trade-off: **Azure manages the physical infrastructure**, while the operations team remains significantly responsible for installation, databases, backups, security configuration, patching, performance, HA/DR, and licensing costs. Spinning up a VM running SQL Server **does not mean you have a production-ready database system**.

This lesson belongs to the **Relational Databases** chapter of the **CLOUD_PROVIDERS_AZURE** module: exploring Azure from subscriptions, resource groups, and Microsoft Entra ID to virtual networking, compute, storage, data protection, monitoring, and cost management. The lesson focuses on architecture selection, deployment, and operations for SQL Server on Azure VMs; examples use common Windows Server/SQL Server patterns, though many principles also apply to SQL Server on Linux where features are supported.

> **Technical scope:** Azure and SQL Server update frequently. Combinations of SQL Server version, Windows/Linux, VM SKU, disk SKU, Availability Zones, Azure Backup, SQL IaaS Agent extension, and HA features have specific support limits. Illustrative commands are not complete production deployment scripts: before running, verify subscription, permissions, region, edition, licensing, compatibility matrices, and current documentation for the chosen configuration.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish SQL Server on Azure VM from **Azure SQL Database** and **Azure SQL Managed Instance**.
2. Explain the **IaaS** responsibility boundary between Azure and the SQL administration team.
3. Choose images, editions, versions, CPU/RAM, licenses, and the SQL IaaS Agent extension.
4. Design managed disks for **data, transaction logs, tempdb, backups**, IOPS, throughput, and latency.
5. Design private networking, DNS, NSGs, identities, and encryption to reduce unauthorized access risks.
6. Plan backups/restores, RPO/RTO, and real recovery testing.
7. Compare **Always On Availability Groups**, **Failover Cluster Instances**, Availability Zones, and disaster recovery.
8. Use Azure CLI and T-SQL/DMVs to verify state, performance, and configuration.
9. Establish monitoring, alerts, maintenance runbooks, patching, and cost optimization.
10. Evaluate migration workflows and criteria indicating when PaaS is preferable to VMs.

## 2. Positioning SQL Server on Azure VM in the Azure Ecosystem

Three major options:

| Criterion | SQL Server on Azure VM | Azure SQL Managed Instance | Azure SQL Database |
|---|---|---|---|
| Model | **IaaS** with customer-managed SQL Server | **PaaS** compatible with many SQL Server instance traits | **PaaS** optimized per database |
| OS control | High: VM, OS, and SQL configuration | No direct OS management | No OS/instance management |
| SQL Server Agent / instance scope | Used per edition and supported config | Many instance-level features, with differences | Not equivalent to traditional SQL Server Agent |
| OS/SQL patching | Customer plans, executes, and tests, with Azure tooling support | Platform manages substantial portion | Platform manages substantial portion |
| Backup/restore | Customer designs and tests, with supporting services | Built-in backups per service policy | Built-in backups per service policy |
| High availability | Customer designs AG/FCI or suitable mechanism | Service-managed HA per SLA | Service-managed HA per SLA |
| Instance-level dependencies | Higher compatibility with self-managed SQL Server | Must verify feature gaps | Significant instance-level differences |
| Cost unit | VM + disks + network + SQL license + operations | PaaS compute/storage model | PaaS compute/storage model |

**Choose VM** when OS requirements, SQL Server engine/edition, integrated software, SQL Server instance features, or migration compatibility do not fit PaaS options. **Choose PaaS** when the application can adapt and you want to reduce OS/SQL patching and backup/HA responsibilities.

Never decide simply because "an Azure VM looks like the old server": the team must compare **total cost of ownership (TCO)**, security, recovery workflows, maintenance downtime, and operational capacity.

## 3. Reference Architecture for a SQL Server VM

~~~mermaid
flowchart TD
  C["Java / .NET API on AKS, VM, or Container Apps"] --> DNS["Private DNS / SQL listener FQDN"]
  DNS --> SQL["SQL Server on Azure VM (private IP)"]
  SQL --> DAT["Managed disks: data files"]
  SQL --> LOG["Managed disks: transaction logs"]
  SQL --> TMP["tempdb: suitable disk"]
  SQL --> BK["Backup to vault / Blob per strategy"]
  SQL --> OBS["Azure Monitor + SQL telemetry"]
  OPS["Admin via Bastion / management network"] --> SQL
  ID["AD / Entra and appropriate SQL permissions"] -.-> SQL
~~~

A single-VM model helps teach the components, **not HA design**. If the VM fails or an Availability Zone goes down, the application may lose the database until the VM or backup is recovered. Critical production systems typically need at least two SQL replicas/instances, DNS/listeners, data protection, and failover capability.

### Boundaries to Distinguish

- **VM:** compute instance with CPU/RAM, NIC, and operating system.
- **Managed disk:** block storage resource attached to the VM; not an Azure Blob container.
- **SQL Server:** database service running on the VM managing files, logs, memory, and connections.
- **SQL virtual machine resource:** an Azure management resource linking a VM running SQL Server to specialized management capabilities via the SQL IaaS Agent extension when supported; not a second VM.
- **Azure SQL Database:** a different PaaS service; do not use PaaS firewall/Private Endpoint guides to replace SQL-on-VM configurations.

## 4. Shared Responsibility Model

| Component | Primary Responsibility |
|---|---|
| Datacenter, physical hardware, underlying hypervisor | Azure |
| Choosing region, zone, VM SKU, disk SKU, and availability | Customer designs; Azure provides service capabilities |
| Guest OS, hardening, accounts, patching/reboots | Customer, with Azure tooling support |
| SQL Server version, setup, edition, options, agent jobs | Customer |
| Database schema, indexes, logins, query tuning | Customer |
| Backup policies, retention, restore testing | Customer decides and tests; Azure provides execution services |
| HA/DR, RPO/RTO, failover procedures | Customer designs and tests |
| VNet, NSGs, DNS, private access, TLS | Customer configures on Azure platform |
| Monitoring, alerts, audit logs, security response | Customer configures and operates, with Azure telemetry services |

A VM built from an Azure Marketplace SQL Server image comes with SQL pre-installed. This **does not transfer database management and backup responsibilities to Azure SQL Database**.

## 5. Choosing a SQL Server Image and Deployment Method

Three common approaches:

1. **Marketplace SQL Server image:** select an image bundling Windows Server and a supplied SQL Server version/edition; suitable for quick setup aligned with licensing models and SQL VM integration.
2. **Self-install SQL Server on Azure VM:** create the OS VM first, then install SQL Server using authorized media/licenses; register/manage as a SQL VM where applicable.
3. **Migrate an existing VM or database:** use Azure Migrate, backup/restore, log shipping, AG seeding, or suitable transfer methods; evaluate licenses, drivers, and version compatibility.

**Do not pick the "latest" VM image by instinct.** Verify the SQL Server version supported by your application, database compatibility level, OS lifecycle, licensing, SQL features, and patching plan.

### Windows vs. Linux

SQL Server on Linux supports many core features, yet administration, scripts, HA, authentication, and extensions differ from Windows. If an application relies on Windows authentication, COM, SSIS, or Windows-only software, verify compatibility instead of assuming Linux is a drop-in replacement.

### Two Azure Resource Types

For example, you may see:

~~~text
Microsoft.Compute/virtualMachines          vm-sql-prod-01
Microsoft.SqlVirtualMachine/sqlVirtualMachines  vm-sql-prod-01
~~~

The SQL VM resource adds Azure-level management via the SQL IaaS Agent extension and registration per current support. It **does not replace the SQL Server process** and does not turn the setup into Managed Instance. When managing VMs with IaC, track both the VM resource and the SQL VM registration.

## 6. SQL IaaS Agent Extension and SQL VM Management

The **SQL IaaS Agent extension** enables Azure VM SQL Server management capabilities such as SQL VM registration, inventory/status, license management, and automated management features depending on OS/SQL version and deployment mode.

Capabilities can include:

- Declaring/converting license types within eligible bounds.
- Configuring certain storage/SQL VM management features when supported.
- Automated backups or patching in compatible configurations.
- Integrating SQL Server metadata visibility into the Azure Portal.
- Supporting specialized SQL Server VM management tasks.

**Do not assume every SQL Server version, OS, and extension mode supports every feature.** Automated backup in the SQL IaaS extension differs from a backup policy managed by Azure Backup for SQL Server in Azure VM; choose one clear mechanism to avoid overlapping backup schedules, competing for bandwidth, or breaking backup chains.

### Checking Registration

Read-only example commands, assuming the resource exists and Azure CLI has the SQL VM command group available:

~~~bash
RG="rg-sql-lab"
VM="vm-sql-lab-01"

az vm show \
  --resource-group "$RG" \
  --name "$VM" \
  --query "{id:id,name:name,location:location,vmSize:hardwareProfile.vmSize}" \
  --output json

az sql vm show \
  --resource-group "$RG" \
  --name "$VM" \
  --output json
~~~

If the second command finds nothing, that is **insufficient grounds** to conclude SQL Server is not installed on the VM: the VM might not be registered as a SQL VM resource, the CLI extension might not be ready, or the account lacks permission. Verify through governance processes without creating new resources before confirming licensing and permissions.

## 7. SQL Server Licensing on Azure VM

SQL Server licensing is a major part of TCO. Two common paths:

| Path | Meaning | What to Verify |
|---|---|---|
| **Pay-as-you-go (PAYG)** | SQL Server license cost billed through the appropriate image/SQL VM model | Edition, license meter, vCPU count, VM size, resource config |
| **Azure Hybrid Benefit (AHB)** | Apply eligible SQL Server licenses under Microsoft policy to reduce Azure license costs | Entitlement, Software Assurance/subscription, usage rights, core counts, and compliance |

Additional licensing models may exist under specific agreements and conditions. **Never switch `licenseType` to AHB unless the organization holds valid entitlement**, and never assume checking one VM tag satisfies full compliance.

Windows Server licensing, SQL Server licensing, VM compute, and managed disks may appear under distinct billing meters; estimates must check actual pricing by region, OS, VM SKU, and license.

### Optimizing Licensing and Compute

- Pick an edition sufficient for HA, performance, and feature needs.
- Select VM vCPU/RAM ratios matching load; avoid over-provisioning vCPUs just to get memory if a memory-optimized SKU fits better.
- For core-based SQL Server licenses and specific VM models, verify core minimums and contract rules before resizing VMs.
- Verify entitlements for passive HA replicas, disaster recovery replicas, and standby states; free/discounted rights are **conditional**, not automatic for every topology.
- Review total cost before adopting multi-node Always On topologies.

## 8. Choosing a VM SKU: CPU, Memory, and Network

### CPU

SQL Server bears load from query execution, parallelism, compression, index maintenance, and encryption. Insufficient CPU raises latency, while excess CPU inflates compute and license costs.

Evaluate:

- Peak CPU and how long CPU stays elevated.
- Query concurrency, parallelism settings, and waits.
- ETL, maintenance, and batch jobs overlapping transaction hours.
- VM series and SKU disk/network throughput limits.
- Whether the VM SKU supports accelerated networking, zones, and Ultra/Premium SSD v2.

### Memory

SQL Server uses RAM for the buffer pool, plan cache, and engine components. Size the VM for the **database working set**, not just total data file size.

Reserve RAM for:

- Guest OS and agents: Defender, backups, Azure Monitor.
- SQL Server non-buffer-pool memory, CLR/linked servers if used.
- Auxiliary services or drivers running on the same VM.
- Peak queries and maintenance jobs.

**`max server memory (MB)`** bounds a large share of SQL Server memory, but does not replace monitoring total memory. Never let SQL Server claim 100% of VM RAM; leave headroom so the OS and agents avoid paging/OOM.

### Network

SQL Server can consume substantial bandwidth for AG replication, backup to URL, client queries, and ETL. Check the **VM SKU network bandwidth**, cross-zone/cross-region latency, and egress policies. A SQL VM with fast disks can still bottleneck on low VM network/storage throughput caps.

## 9. Designing Managed Disks for SQL Server

A database typically exhibits distinct I/O profiles:

| Component | Typical I/O Pattern | Design Guidance |
|---|---|---|
| **Data files (.mdf/.ndf)** | Random reads, checkpoint/page writes | Disk/pool providing low latency and adequate IOPS |
| **Transaction log (.ldf)** | Sequential writes, highly latency-sensitive | Dedicated disk or layout prioritizing write latency; host caching per guidance |
| **tempdb** | Temporary I/O, sorts/hashes/version store | Fast storage; consider local temporary disk if SKU supports it and recreation is safe |
| **Backup files** | Large sequential reads/writes | Blob/backup service with suited bandwidth, retention, and security |
| **OS disk** | OS, agents, system files | Avoid placing production data/logs on the OS disk due to unpredictable contention |

### Disk SKUs and Throughput

Storage tiers may include Standard SSD, Premium SSD, Premium SSD v2, Ultra Disk, or other suitable options. **IOPS/throughput provisioning, caching, zone support, snapshots, resizing, and VM size compatibility vary by SKU/region**.

Do not select Ultra solely for its "high-end" label. Measure workload **IOPS, MB/s, and latency** and compare against each disk/VM SKU's capabilities.

### Four Concurrent Limits

Actual I/O speed cannot exceed the lowest limit along the path:

~~~text
Application/SQL workload
    -> SQL engine + file layout
    -> Guest filesystem / storage stack
    -> Azure managed disk IOPS + throughput
    -> VM-level disk IOPS + throughput caps
~~~

If disks provision 40,000 IOPS but the VM only delivers 20,000 IOPS for that workload type, effective performance is capped by the VM. With 64 KiB requests, 10,000 IOPS theoretically corresponds to roughly 625 MiB/s; a lower throughput cap will throttle the result.

### Host Caching

For disk/VM configs supporting it and aligned with SQL Server best practices:

- Data disks sometimes use **ReadOnly host caching** if workload fits.
- Transaction logs typically use **None** (no host caching) to avoid unsafe behavior for log writes.
- **Premium SSD v2/Ultra Disk do not support host caching identically to standard Premium SSD**; check SKU limits.
- Never enable caching out of habit across all disks, especially with shared disks/HA.

Changing production disk caching or storage layouts may require reboots/downtime; test first and execute in a change window.

## 10. Data/Log Separation, File Layout, and tempdb

### Why Separate Data and Logs?

Transaction logs are written sequentially for durability/recovery; data files generate heavy random I/O. Sharing one disk lets data read bursts or index maintenance degrade log write latency.

Common layout:

~~~text
C:  OS, SQL binaries
F:  SQL data files
G:  SQL transaction log files
T:  tempdb (suitable disk, potentially temporary local)
Backup -> Azure Backup / Blob per design
~~~

Drive letters are illustrative only, not a mandatory convention.

### Multiple Disks and Storage Spaces

When a single managed disk lacks enough IOPS/throughput, multiple disks can be striped into a storage pool/volume as supported on Windows or Linux. Striping requires tracking:

- Disk count, size, performance tier, and VM-level limits.
- Stripe/interleave and filesystem allocation unit size suited to the workload.
- Whole-volume snapshot/backup/recovery capabilities.
- Disk mount/recovery order during failover or restore.
- Shared disk compatibility if using FCI.

**Never stripe multiple disks just to get more drive letters.** Rely on real I/O testing, latency monitoring, and verified recovery workflows.

### tempdb on Local Temporary Storage

Some Azure VM SKUs include high-speed **temporary/local SSD or NVMe**. `tempdb` can be placed there in supported environments since `tempdb` is recreated when SQL Server starts.

However, local temporary disks **are not persistent** across events like deallocate/redeploy/host maintenance. Therefore:

1. Never place **user database data/log files or sole backups** on temporary disks.
2. Ensure the `tempdb` directory, ACLs, and mount path are recreated before SQL Server starts.
3. Verify the SKU actually provides a temporary disk of adequate size.
4. Test upgrade/stop/start conditions so SQL Server doesn't fail to start if the `tempdb` path disappears.
5. If workload/version/VM SKU does not support it, use an appropriate persistent managed disk.

### tempdb Tuning

The number of `tempdb` data files, initial size, and autogrowth depend on concurrency, version, and contention. Never blindly apply "one `tempdb` file per CPU" on VMs with dozens of cores. Measure `PAGELATCH`/metadata contention and follow guidance for your SQL Server version.

## 11. Designing VNet, NSGs, and DNS

SQL Server on VM should generally use a **private IP in an Azure VNet**, allowing access only from authorized applications and admin groups.

~~~mermaid
flowchart LR
  APP["Application - subnet-app"] --> NSG["NSG / Firewall policy"]
  NSG --> SQL["SQL VM private IP: SQL TCP endpoint"]
  SQL --> DISK["Managed disks"]
  OPS["VPN / ExpressRoute / Bastion"] --> ADMIN["VM Administration"]
  ADMIN --> SQL
  SQL --> BK["Backup / Azure services per outbound rules"]
~~~

### Never Expose SQL Ports to the Internet

TCP port **1433** is commonly used for the default instance **when configured to listen on that port**. Named instances may use dynamic or alternate ports; SQL Browser/UDP 1434 plays a specific role. Do not assume every SQL VM listens on TCP 1433.

Recommendations:

- Do not attach a public IP directly to a SQL VM without an approved exceptional need.
- Restrict NSGs so only **application subnets, jump subnets, or specific sources** reach the SQL port.
- Never use an inbound rule `0.0.0.0/0:1433`.
- Administer Windows via **Azure Bastion**, VPN/ExpressRoute, or approved admin paths; restrict RDP 3389.
- Use Azure Firewall/NVA when inspection/central egress and logging are needed.
- Check the guest OS firewall, not just NSGs.
- With AG listeners/FCI, clients use the **listener DNS name**, not pinned node private IPs.

### Do Not Confuse with Azure SQL Database Private Endpoint

SQL Server on a VM has a **VM NIC/private IP** or listener/ILB depending on topology. It **does not automatically use Azure SQL Database Private Endpoint** simply because both engines speak SQL. Private Endpoints may be used for Storage, Key Vault, and supported Azure PaaS services that the SQL VM calls.

### DNS and Connection Strings

Application connections should reference a stable DNS name:

~~~text
sql-orders.internal.example:1433
~~~

For multi-subnet AGs, supported JDBC/drivers and topologies may need options like `multiSubnetFailover=true` to speed failover connectivity. Verify listener, DNS TTL, IP, driver version, and actual network behavior. Do not blindly add `multiSubnetFailover` if the app does not use a multi-subnet listener.

## 12. Authentication, Authorization, and TLS

### Authentication Methods

Depending on SQL Server version, Windows/Linux, and enterprise environment:

- **Windows/Active Directory authentication** via domain and appropriate service accounts.
- **SQL Server authentication** with login/password governed by policy and rotation.
- **Microsoft Entra authentication** with SQL Server on VM in supported versions/configurations; do not assume every SQL Server version uses Entra identically to Azure SQL Database.

A **managed identity on a VM** lets apps or tasks interact with Entra-supported Azure services, but **does not automatically become a valid SQL Server login** across all SQL Server versions. SQL database authentication must still be designed and configured explicitly.

### Least Privilege

- Separate accounts for DBAs, SQL Server Agent, applications, and backups.
- Grant applications only required database/schema permissions.
- Avoid `sa`, `sysadmin`, or `db_owner` in API connection strings.
- Store secrets in Key Vault or approved secret managers; avoid source code, images, Terraform state/logs, or unprotected config files.
- Audit permission changes, unusual logins, schema edits, and sensitive data access.

### TLS on Connections

Enforce TLS with valid certificates and matching FQDNs. Example JDBC URL when SQL listens on a static port with a trusted certificate:

~~~properties
spring.datasource.url=jdbc:sqlserver://sql-orders.internal.example:1433;databaseName=Orders;encrypt=true;trustServerCertificate=false;loginTimeout=30
~~~

This URL configuration **contains no password**; configure username/password or authentication mechanisms separately per app policy. `trustServerCertificate=false` enforces certificate validation; never flip it to `true` just to bypass a production certificate error. With newer drivers, `encrypt` defaults and hostname validation vary by version; verify directly.

## 13. Encryption at Rest and Key Management

Distinguish three layers:

| Layer | Purpose | What Must Be Managed |
|---|---|---|
| Azure managed disk encryption | Protects data at the Azure storage layer per platform mechanisms | Platform-managed keys or customer-managed keys per needs/features |
| SQL Server TDE | Encrypts database files and transaction logs at the SQL layer | Certificates/asymmetric keys, key backups, rotation, and restores |
| TLS | Encrypts data when clients connect to SQL Server | Certificates, trust chains, hostnames, and expiration |

**Azure disk encryption does not replace TDE if SQL-level encryption is required**; conversely, TDE does not control who can connect and query decrypted data inside the engine.

### TDE Backup/Restore

A TDE-enabled database requires the **matching certificate/key and private key** to restore onto another instance, per TDE configuration. Back up these keys securely via formal procedures, stored separately from database backups, and test recovery. Never ship a TDE backup to another environment only to discover the certificate is missing.

### Key Vault

Azure Key Vault can manage secrets/keys where configuration, version, and integration fit. Never hard-code secrets or keys into IaC SQL scripts. Enforce RBAC, private networking/DNS, auditing, and key rotation plans.

## 14. Backups Are Not Just Snapshots

Backups must restore a **consistent database**, not merely copy disk blocks.

| Mechanism | Used For | Limits to Understand |
|---|---|---|
| **Native SQL BACKUP DATABASE/LOG** | Full, differential, log backups per recovery model | Customer schedules, retains, verifies checksums, and tests restores |
| **Azure Backup for SQL Server in Azure VM** | Workload-aware backup/restore per service policy and supported config | Requires instance registration/protection, policy, vault, permissions, and recovery verification |
| **SQL VM automated backup** | Capability via SQL IaaS Agent extension in supported cases | Not available for all SQL/OS types; avoid overlapping backup policies |
| **Managed disk snapshots** | Disk-level protection, certain VM/storage goals | Not inherently SQL-consistent backups or point-in-time restore |
| **Availability Group replica** | High availability/disaster recovery replica | **Not a backup**; accidental data deletion replicates |

An isolated disk snapshot taken while SQL Server is writing **does not guarantee consistency across multiple data/log disks**. Using VM snapshots/backups for SQL requires app-consistent/VSS mechanisms or a guaranteed, tested solution. **Never replace a log backup chain with snapshots** when point-in-time recovery is required.

## 15. Recovery Models, Log Backups, and RPO

The SQL Server recovery model governs the recovery strategy.

| Recovery Model | Purpose | Limitations |
|---|---|---|
| **FULL** | Supports log backups and point-in-time restore with a valid backup chain | Must **actually run log backups**; switching to FULL alone creates no backups |
| **SIMPLE** | Reuses log space per engine rules; fits when log backups/PITR aren't needed | Does not support transaction log backup chains for PITR like FULL |
| **BULK_LOGGED** | Can reduce log volume for certain bulk operations | Restricts PITR on log backups containing minimally logged operations |

### Full, Differential, and Transaction Logs

Illustrative policy:

~~~text
Full backup:          Sunday 01:00
Differential backup:  Daily 01:00
Log backup:           Every 10 minutes
Retention:            Per RPO/RTO, compliance, cost
Restore drill:        Per approved schedule
~~~

If the database fails at 14:07 and the latest log backup was at 14:00 without an available tail-log backup, the latest restore point may be 14:00; data loss RPO **could be ~7 minutes or more**, depending on backup success and tail-log availability. This is an illustration, not a guarantee of 10-minute RPO in every failure.

**Log backups must remain continuous and recoverable.** Any gap, deleted file, expired credential, or unreachable storage can break point-in-time restore.

### RPO and RTO Differ

- **RPO:** maximum acceptable data loss relative to an incident.
- **RTO:** maximum time from disruption until service is restored.

Backups every 10 minutes may partially satisfy RPO, yet do not guarantee a 10-minute RTO if restoring terabytes takes hours. Measure **full backup-chain restore time, new VM creation, DNS cutover, and application reconnect**.

## 16. T-SQL Examples for Backup/Restore — Controlled Illustration

Check database recovery models:

~~~sql
SELECT name, recovery_model_desc, state_desc, compatibility_level
FROM sys.databases
WHERE name NOT IN ('master', 'model', 'msdb', 'tempdb')
ORDER BY name;
~~~

Illustrative **native backup to URL** syntax for a lab database with proper credentials/authorization for SQL Server to write to Blob:

~~~sql
BACKUP DATABASE [OrdersLab]
TO URL = 'https://<STORAGE_ACCOUNT>.blob.core.windows.net/sql-backups/OrdersLab_full_001.bak'
WITH COPY_ONLY, COMPRESSION, CHECKSUM, STATS = 10;
~~~

This snippet **cannot run as-is** without replacing placeholders, configuring credentials/SAS or an auth method supported by the SQL Server version, SQL permissions, and network reachability to Blob. **COPY_ONLY** avoids disrupting the differential base in certain full backup flows; production policies must define whether to use it.

Verifying backup structure is one step:

~~~sql
RESTORE VERIFYONLY
FROM URL = 'https://<STORAGE_ACCOUNT>.blob.core.windows.net/sql-backups/OrdersLab_full_001.bak'
WITH CHECKSUM;
~~~

**`RESTORE VERIFYONLY` is not a complete restore drill.** Periodically restore onto an independent instance, confirm the database comes online, check consistency, and run business queries. With TDE, the corresponding key/certificate is required. Never overwrite a production database just to test a backup.

### Retention and Immutability

Backups supporting ransomware recovery require independent permissions, retention, and deletion/modification protection per policy. Consider vault protections, soft delete, immutability, or service-supported storage controls; evaluate cost and legal retention periods. Never keep the sole backup on the same VM/data disk as the database.

## 17. High Availability: Availability Zones Are Insufficient with a Single VM

Availability Zones distribute compute/storage across independent physical fault zones within a supported Azure region. **A single SQL VM in one zone** remains a single point of failure without replicas or failover mechanisms.

### Always On Availability Groups (AG)

An AG typically includes:

- **Primary replica:** accepts reads/writes for databases in the availability group.
- **Secondary replicas:** receive data synchronously or asynchronously per configuration, optionally serving read-only/backups under valid conditions.
- **Windows Server Failover Cluster (WSFC)** for many Windows AG topologies.
- **Listener:** logical connection name routing apps to the active primary.
- **Quorum/witness:** split-brain prevention mechanism per cluster topology.

~~~mermaid
flowchart LR
  APP["Application via listener DNS"] --> L["AG listener"]
  L --> P["SQL VM A - Zone 1 - Primary"]
  P -->|Synchronous commit (when appropriate)| S["SQL VM B - Zone 2 - Secondary"]
  P -->|Async commit for DR (example)| DR["SQL VM C - Other region"]
  W["Cluster quorum / witness"] -.-> P
  W -.-> S
~~~

This diagram is conceptual; real topologies must verify zone/region support, edition, networking, endpoints, WSFC, listeners, quorum, and failover behavior.

### Synchronous vs. Asynchronous

- **Synchronous commit** reduces data loss during failover when replicas are healthy and properly configured, with a **cross-zone latency trade-off**.
- **Asynchronous commit** avoids commit-time latency dependency, fitting certain DR topologies, with **potential loss of unsent/unredone transactions** on failover.
- **Automatic failover** is supported only in specific combinations of availability mode, failover mode, health, and quorum; do not assume every secondary automatically promotes to primary.

Even a healthy AG does not replace database backups: application bugs, accidental DELETE statements, or ransomware replicate.

## 18. Failover Cluster Instance (FCI) and Shared Storage

**SQL Server Failover Cluster Instance (FCI)** provides HA at the SQL Server instance level rather than grouping user databases like AG. A typical FCI includes:

- Multiple Windows/SQL Server nodes per supported configuration.
- Failover cluster resources.
- Shared storage or equivalent storage solution supported by SQL Server/Windows/Azure.
- Stable SQL instance name/endpoint.
- Quorum, witness, and failover rules.

Azure supports FCI setups using **Azure shared disks or other supported solutions**, yet not every managed disk SKU, zone/region topology, or clustering mode is compatible. Check the **official matrix for SQL Server FCI on Azure VMs, disk types, host caching, multi-writer support, and witnesses** before designing.

### AG or FCI?

| Criterion | Always On AG | FCI |
|---|---|---|
| HA scope | Group of databases joined to the AG | Entire SQL instance per FCI design |
| Data mechanism | Replicas maintain independent database copies | Requires shared/clustered storage |
| Readable secondary | Supported in certain editions/configs | No independent secondary database copy in traditional FCI |
| Storage failure considerations | Each replica has separate storage | Must evaluate shared storage failure domain |
| Configuration | AG endpoints, listener, replicas, quorum | Cluster disks/resources, instance failover, quorum |
| Migration/operations | Logins/jobs outside AG may need syncing | Instance-level failover, though dependencies still require checks |

Do not choose AG or FCI based purely on VM count. Evaluate edition/version features, RPO/RTO, DBA runbooks, licensing, and whether apps handle post-failover reconnects.

## 19. Quorum, Witness, and Listeners in Azure

### Quorum

WSFC requires quorum to decide which cluster partition retains resource authority and to avoid split-brain. With two SQL nodes, design an appropriate **witness** (e.g., cloud witness where supported), managing identity/secrets/networking and fault domains.

A failed witness does not necessarily halt SQL databases immediately, but can block automatic failover on the next node failure. Monitor quorum health operationally, not just whether the SQL Server service is running.

### Listener

An AG listener can use a private virtual IP configured with an **Azure Internal Load Balancer** in some topologies, or DNS/DNN listener methods supported by SQL Server/Windows and the environment. Configuration differs across single-subnet, multi-subnet, AG/FCI, and SQL versions.

If using an Internal Load Balancer:

- Ensure health probes, backend pools, NSGs, and ports match topology guidance.
- Never use a public LB to expose SQL Server without an approved specialized design.
- Verify the listener IP does not conflict within the VNet.
- Test failover: existing connections break and app pools must reconnect; surviving TCP sessions are not guaranteed.

If the application uses JDBC:

~~~properties
jdbc:sqlserver://sql-ag-listener.internal.example:1433;databaseName=Orders;encrypt=true;trustServerCertificate=false;multiSubnetFailover=true;loginTimeout=30
~~~

This applies **when a multi-subnet listener/driver is supported and properly configured**. Test the exact SQL Server JDBC driver version and set appropriate connection pool validation/retries rather than assuming one property handles all of failover.

## 20. Disaster Recovery: Region Failures Differ from Node Failures

Single-region HA reduces downtime during VM or zone faults, but may not meet targets during a **full region outage**.

Choose a DR strategy aligned with data requirements and budget:

- Asynchronous AG replica in a secondary region where topology/edition permit.
- Log shipping or backup/restore to another region in suitable models.
- Cross-region backup replication per Azure Backup/storage policy capabilities.
- Tested specialized replication or migration tools.
- Application/DNS traffic cutover and connection strings in the standby region.

### RPO/RTO Must Be Measured

| Scenario | Expected HA/DR | Risks |
|---|---|---|
| SQL Server process restart | Self-recovery or HA failover | Connection resets, in-flight transactions |
| VM/node failure | AG/FCI or restore | Failover delay, quorum/storage |
| Availability Zone outage | Replica in another zone | Capacity, cross-zone sync latency |
| Region outage | DR region | Async data loss, DNS/app cutover |
| Database corruption/ransomware | Safe backup/restore | Corruption can replicate to secondaries |
| Human error: DROP/DELETE | Point-in-time restore via backup chain | Recovery point, restore duration, dependencies |

A **failover drill** is more than switching primary: verify app endpoints, DNS, TLS, logins, Agent jobs, linked servers, backup policies, data consistency, and failback capability. Establish runbooks and emergency permissions before an incident hits.

## 21. Performance Tuning: Measure SQL Server Before Resizing the VM

When an API slows down, a common wrong reflex is **immediately scaling up the VM size**. Instead, classify the bottleneck:

- CPU-bound: query plans, excessive parallelism, scalar computations.
- I/O-bound: data disk read/write latency, log write stalls, `tempdb` contention.
- Memory pressure: buffer churn, paging, excessive memory grants.
- Locking/blocking: long transactions, missing indexes, or isolation levels.
- Network/connections: DNS/TLS, connection pool exhaustion, packet loss.
- Application: N+1 queries, lack of batching, retry loops, or ORM bugs.
- HA/replication: synchronous commit waits, secondary lag.

### Indexes and Query Store

**Query Store** tracks query plan/runtime history when enabled and supported by version. Use it to spot post-deploy regressions, compare execution plans, and guide tuning. Avoid creating dozens of indexes for one slow query; weigh write overhead, storage cost, and plan stability.

### max server memory and MAXDOP

Set `max server memory` based on physical RAM, leaving room for the OS, agents, and other workloads. Configure `MAXDOP`, cost threshold for parallelism, and `tempdb` based on SQL version, NUMA, core count, and query patterns; never copy one static "optimal" value onto every VM.

## 22. T-SQL: Checking Version, Databases, and File Layout

Run in SQL Server Management Studio, Azure Data Studio (if still supported in your environment), or an approved SQL client using an account with required privileges.

### Version and Edition

~~~sql
SELECT
    @@SERVERNAME AS SqlInstance,
    SERVERPROPERTY('ProductVersion') AS ProductVersion,
    SERVERPROPERTY('ProductLevel') AS ProductLevel,
    SERVERPROPERTY('Edition') AS Edition,
    SERVERPROPERTY('EngineEdition') AS EngineEdition;
~~~

Results verify patch level, edition, and supported features. Edition name alone does not prove license entitlement is valid.

### Database Health

~~~sql
SELECT
    name,
    state_desc,
    recovery_model_desc,
    compatibility_level,
    is_read_only
FROM sys.databases
ORDER BY name;
~~~

### Data/Log Files

~~~sql
SELECT
    DB_NAME(database_id) AS DatabaseName,
    name AS LogicalFileName,
    type_desc,
    physical_name,
    size * 8.0 / 1024 AS SizeMiB,
    growth,
    is_percent_growth
FROM sys.master_files
ORDER BY database_id, file_id;
~~~

`size` is measured in 8 KiB pages; `growth` means different units depending on `is_percent_growth`. Drive letters/paths verify whether data and logs are separated as designed. Check actual free space and policies before changing production autogrowth.

### I/O Latency from DMVs

~~~sql
SELECT
    DB_NAME(v.database_id) AS DatabaseName,
    mf.name AS LogicalFileName,
    mf.type_desc AS FileType,
    v.num_of_reads,
    v.num_of_writes,
    CASE WHEN v.num_of_reads > 0
         THEN 1.0 * v.io_stall_read_ms / v.num_of_reads END AS AvgReadMs,
    CASE WHEN v.num_of_writes > 0
         THEN 1.0 * v.io_stall_write_ms / v.num_of_writes END AS AvgWriteMs
FROM sys.dm_io_virtual_file_stats(NULL, NULL) AS v
JOIN sys.master_files AS mf
  ON mf.database_id = v.database_id
 AND mf.file_id = v.file_id
ORDER BY DatabaseName, LogicalFileName;
~~~

**DMVs are cumulative counters** since SQL Server/object startup per DMV semantics; never inspect one lifetime value and claim it reflects the last 5 minutes' latency. Take two samples and compute deltas over a defined window. DMV access may require server-state/performance-state permissions that vary across SQL Server versions.

## 23. T-SQL: Wait Statistics and Blocking

### Top Waits

~~~sql
SELECT TOP (15)
    wait_type,
    waiting_tasks_count,
    wait_time_ms,
    signal_wait_time_ms
FROM sys.dm_os_wait_stats
ORDER BY wait_time_ms DESC;
~~~

This is merely a **cumulative wait time** list. Some waits are benign/background and do not directly indicate a bottleneck. Analyze wait categories, query plans, file latencies, time windows, and transaction counts before tuning. Never "fix" a wait just because it tops the list.

### Active Requests

~~~sql
SELECT
    session_id,
    status,
    command,
    blocking_session_id,
    wait_type,
    wait_time,
    total_elapsed_time,
    cpu_time
FROM sys.dm_exec_requests
WHERE session_id <> @@SPID
ORDER BY total_elapsed_time DESC;
~~~

`blocking_session_id` helps initiate lock contention investigations; never automatically `KILL` a production session just because a transaction runs long. Verify owner, commit duration, lock scope, and rollback impact.

### tempdb, Transaction Logs, and Free Space

Beyond DMVs, monitor log reuse wait, log size, SQL error logs, and PerfMon counters per version. Key alerts:

- Transaction log nearly full / broken backup chain.
- Storage volume running out of space.
- Continuous `tempdb` autogrowth.
- Deadlocks or long blocking chains.
- Failed SQL Agent backup jobs.
- High AG replication send/redo queue lag.
- Database corruption/CHECKDB errors.

## 24. Monitoring with Azure Monitor and SQL Telemetry

### Azure VM Level

Azure Monitor collects baseline platform metrics such as:

- CPU Percentage.
- VM disk read/write operations and bytes per metric capabilities.
- Network in/out.
- VM availability/health and published platform events.

These metrics help, yet **cannot tell whether a SQL query is deadlocked**. Supplement with guest OS counters, SQL DMVs, Query Store, SQL Server error logs, and appropriate diagnostic/monitoring integrations.

### Guest OS Level

Use Azure Monitor Agent (AMA) with Data Collection Rules (DCR) or an approved pipeline to collect Windows Event Logs, PerfMon counters, or Linux syslog/performance as required.

Commonly needed signals:

| Signal | Objective |
|---|---|
| CPU and runnable tasks | Is compute saturated? |
| Available memory and paging | Is the OS under memory pressure? |
| Disk avg sec/read/write, queue length | Is I/O latency exceeding baseline? |
| SQL batch requests/sec | Is workload growing/shrinking? |
| SQL user connections | Is the connection pool behaving abnormally? |
| Page life expectancy / buffer metrics | Is there memory pressure? Correlate multiple signals |
| Log flush waits/latency | Is the log disk throttling commits? |
| Backup success + last log backup age | Is the recovery objective protected? |
| AG health/send/redo queue | Are replicas keeping up and ready to fail over? |

Counter names, ingestion methods, and visibility vary by Windows/SQL version and agent. Never build alerts on counters that do not exist in your workspace.

### Application Level

Application Insights/OpenTelemetry in Java/.NET links **API latency** to SQL dependencies. Example trace:

~~~text
POST /checkout (3.2s)
  -> SQL query CreateOrder (2.7s)
     -> wait: WRITELOG / lock? must verify via SQL telemetry
  -> HTTP return (0.2s)
~~~

A slow dependency trace is a starting point, not an automatic engine diagnosis. Correlate SQL DMVs, Query Store, I/O latency, and change timelines.

## 25. Azure CLI: Inspecting VM, Disks, and Platform Metrics

The read-only commands below fit Azure Cloud Shell Bash when authorized to view the resources. Replace placeholders before running:

~~~bash
az account show \
  --query "{subscription:name,id:id,tenant:tenantId}" \
  --output table

RG="rg-sql-lab"
VM="vm-sql-lab-01"

VM_ID=$(az vm show \
  --resource-group "$RG" \
  --name "$VM" \
  --query id --output tsv)

az vm show \
  --resource-group "$RG" \
  --name "$VM" \
  --query "{name:name,size:hardwareProfile.vmSize,location:location,storage:storageProfile}" \
  --output json
~~~

List data disk IDs/LUNs:

~~~bash
az vm show \
  --resource-group "$RG" \
  --name "$VM" \
  --query "storageProfile.dataDisks[].{name:name,lun:lun,diskId:managedDisk.id}" \
  --output table
~~~

Check platform CPU metric:

~~~bash
az monitor metrics list \
  --resource "$VM_ID" \
  --metric "Percentage CPU" \
  --interval PT5M \
  --output json
~~~

If the metric command returns no data, check the time range, permissions, VM state, metric definitions, and resource ID. Never infer CPU=0 from missing telemetry.

Inspect diagnostic settings:

~~~bash
az monitor diagnostic-settings list \
  --resource "$VM_ID" \
  --output json
~~~

**Diagnostic settings on a VM resource do not replace AMA/DCR** for collecting guest logs or SQL-specific metrics. Also, `az vm show` displays disk attachments rather than full filesystem layouts/SQL file mappings; cross-check with T-SQL from earlier sections.

## 26. Maintenance Schedules, Patching, and Controlled Changes

A production SQL VM needs a **maintenance plan** for the OS, SQL cumulative updates/security fixes, drivers, SQL IaaS Agent extension, backup agents, and antimalware.

Runbook:

1. Record current VM/SQL versions, AG/FCI topology, health, and restore points.
2. Check release notes, application compatibility, SQL features, and drivers.
3. Confirm latest backups, log chain, and most recent restore drill.
4. Check AZ/region capacity, quotas, disk space, and secondary health.
5. Test on staging or secondary nodes first.
6. With HA, plan failover/rolling maintenance per supported configurations.
7. Execute approved patching/SQL service restarts; expect brief downtime or connection resets.
8. Verify SQL service, databases ONLINE, AG sync, listener, and Agent jobs.
9. Run application smoke tests; verify query latency, error rates, and backups.
10. Document results, rollback/forward-fix plans, and post-change notes.

**Azure Update Manager** or Azure/SQL VM patching features aid orchestration, yet cannot automatically understand all business constraints, DB failovers, and applications. Never enable arbitrary auto-reboots on a production SQL primary without an HA/cutover plan.

### SQL Agent Jobs

Inventory backup, ETL, cleanup, statistics/index maintenance, and external integration jobs. With AGs, instance-level objects such as **logins, SQL Agent jobs, and linked servers** do not automatically sync via database replication. Establish a mechanism to manage them on secondaries after failover and ensure run-once logic prevents duplicate job execution.

## 27. Cost Optimization and Resource Governance

SQL Server on Azure VM costs typically comprise:

~~~text
VM compute
+ Windows / SQL licensing per applied model
+ managed disks (capacity / performance)
+ backup vault / Blob capacity / operations
+ network transfer, Load Balancer, Firewall, Bastion
+ monitoring/log retention
+ HA/DR replicas and replication data
+ operations / support / compliance effort
~~~

### High-Impact Cost Drivers

- Edition/license and vCPU count.
- VM instance size and running hours.
- Premium SSD/Ultra/Premium SSD v2 IOPS/throughput provisioning.
- Number of AG/FCI/DR replicas and region/zone placement.
- Backup retention and immutable copies.
- Log Analytics ingestion/retention.
- Dedicated networking and cross-zone/cross-region transfer.

### Rightsizing

Never resize a production VM based solely on average CPU. Check:

- Peak CPU during transaction windows.
- Memory pressure/working set.
- Disk latency/IOPS/throughput and new caps.
- VM network limits.
- Core-based licensing costs.
- Downtime and HA impact during SKU changes.
- Whether the new SKU supports existing disks/features and zones.

### Reserved Instances, Savings Plans, and Licensing

Compute and licensing discounts depend on SKU, contract, region, and policy. Verify which costs are discounted, commitment terms, usage rights, and flexibility before purchasing. **Never conclude Reserved Instances include SQL Server licensing in all cases.**

### Cleaning Up Lab Environments

Stopping a VM does not automatically delete disks, snapshots, backup vaults, NICs/Public IPs, or SQL VM resources. **Deallocating** stops certain compute charges, yet disks/storage and other resources keep billing. When cleaning up a lab, list only resources belonging to the lab and confirm shared infrastructure is untouched.

## 28. Migration Workflow from On-Premises SQL Server

### Discovery

Collect:

- SQL Server version/edition/patch level and feature inventory.
- Database sizes, filegroups, transaction log growth.
- Hourly and peak CPU/RAM/IOPS/latency.
- Logins, SQL Agent jobs, linked servers, SSIS/SSRS/SSAS dependencies.
- Collations, compatibility levels, encryption/TDE certificates.
- Network dependencies, IP allowlists, TLS/driver versions.
- RPO/RTO, maintenance windows, current HA/DR.
- License entitlements and compliance.

### Choosing a Data Transfer Method

| Option | When Suitable | Trade-Offs |
|---|---|---|
| Backup/restore | Database can go offline during maintenance window | Downtime depends on backup/transfer/restore speed |
| Full + differential + log chain | Minimize data delta at cutover | Requires managing log chain and cutover timing |
| AG/log shipping migration | Pre-syncing data to reduce downtime | Requires compatible versions/topologies and runbooks |
| VM rehost | Software heavily tied to OS/instance | Still requires sizing, networking, performance, licensing review |
| PaaS migration after assessment | Reduce IaaS ops when compatible | Must address feature gaps and app changes |

### Cutover Checklist

1. Migration runbook and rollback decision point established.
2. Backup/restore rehearsed on a staging Azure VM.
3. Logins, jobs, certificates, and dependencies migrated per procedure.
4. App connectivity/TLS/DNS, query plans, and performance verified.
5. Remaining data delta synced and consistency checked.
6. Source writes fenced/coordinated at cutover per chosen method.
7. Connection strings/DNS switched and traffic opened in a controlled manner.
8. Real business transactions verified, not just `SELECT 1`.
9. Monitoring, backup/DR policies, and new alerts checked.
10. Viable rollback/failback kept ready before decommissioning the old environment.

Avoid upgrading major SQL versions, changing database compatibility, altering collations, migrating data, and moving to Kubernetes all at once without comprehensive testing: simultaneous changes obscure root causes.

## 29. Symptom-Based Troubleshooting for SQL VMs

| Symptom | Possible Cause | Checks |
|---|---|---|
| Client timeout/connection failure | NSG/Windows Firewall, TCP port, DNS, TLS, listener, service down | Private path, listener, SQL service, error log |
| Login failed | SQL/Windows/Entra auth, disabled login, password, Kerberos/SPN | SQL error number, auth mode, identity |
| JDBC certificate error | Wrong FQDN, CA trust, expired certificate | SQL TLS config, server cert, driver |
| Slow transactions | Log write latency, blocking, CPU, lock escalation | DMV waits, file latency, Query Store |
| High read I/O | Table scans/missing indexes, RAM pressure, disk cap | Plans, buffer pool, storage metrics |
| `tempdb` full | Query spills, version store, undersized volume | `tempdb` files, waits, active transactions |
| SQL log full | Failing log backups, long transaction, AG/replication lag | Log reuse wait, backup jobs, log capacity |
| Low VM CPU but slow API | SQL waits, locks, network, or downstream | Dependency trace + SQL DMVs |
| AG failover fails | Quorum, replica state, endpoint/network, listener | WSFC/quorum logs, AG health, DNS/LB |
| Secondary falling behind | Network latency, log send/redo queue, disk I/O | AG DMVs, network/IO telemetry |
| Green backup but restore fails | Missing TDE key, broken backup chain, corruption, or permissions | Restore drill, CHECKSUM, certificates |
| Storage out of space | Unchecked growth, log/`tempdb`/indexes | Filesystem, SQL files, retention |
| App fails after patching | Driver/compatibility, TLS change, login, SQL plan regression | Version/change logs, Query Store, smoke tests |
| Sudden cost spike | VM/SQL licenses, provisioned disks, DR/backups/logging | Cost Management breakdown, tags |

### Investigation Order

1. Identify **which applications and business flows are impacted**: latency, 500/503, timeouts, or data corruption.
2. Identify **timing and recent changes**: patches, deployments, failovers, storage resizes.
3. Check VM/SQL service/network before blaming a database query.
4. Inspect SQL error logs, backup status, DMVs, waits, and Query Store.
5. Inspect Azure platform metrics, disk caps, subnets/NSGs/firewalls.
6. If HA, check replica health, quorum, listener, and failover events.
7. Choose a reversible mitigation: tune queries, cap concurrency, shift traffic, or fail over per runbook.
8. Confirm recovery via **business success**, not just VM `Running` status.

Never experiment with `KILL`, data-repairing `DBCC`, full-DB index rebuilds, or altering AG quorum in production just to "see if the error clears."

## 30. Case Study: Order System Migrating to Azure

### Context

A company has SQL Server 2019, a 1.2 TiB Orders database, and a Java API stack. Workload profile:

- Roughly 1,000 transactions/s at peak (planning assumption, not an Azure benchmark).
- OLTP queries with heavy random reads and continuous transaction log writes.
- Nightly reporting creating I/O bursts.
- App currently relies on SQL Agent jobs and Windows authentication.
- Desired RPO max 15 minutes; RTO under 1 hour.
- Currently runs daily full backups with no recent restore drill.

### Option Evaluation

**PaaS:** check whether Azure SQL Managed Instance supports all Agent jobs, linked servers, authentication, and compatibility needs. If yes, PaaS can reduce patching/HA overhead. If not, or if the migration deadline is tight, SQL Server on Azure VM is a sensible transitional step.

**Sizing:** measure CPU, memory, Query Store, and disk latency at the source; pick a VM with peak headroom and suitable storage IOPS/throughput. Never size a VM solely by database size.

**Storage:** separate data and logs; fast `tempdb` disk with lifecycle control; independent backups to vault/Blob.

**Network:** SQL VM on a private subnet, Java API connecting over DNS and TLS; allow only required ports from the app subnet. DBAs connect via Bastion/VPN.

**Backups:** FULL recovery + log backups; rehearse restoring 1.2 TiB to prove RTO. If restore is too slow, add HA/DR or revise business targets.

**HA:** with a 1-hour RTO and resilience against VM faults, consider AG replicas across zones with listener/quorum and failover drills. Weigh extra VM/license costs against expected revenue loss.

**Operations:** Azure Monitor, SQL DMVs, Query Store, alerts for backup age, disk latency, AG health, and Cost Management.

### Node Failure Scenario

~~~mermaid
flowchart TD
  A["Alert: SQL endpoint unavailable"] --> B["Check VM / SQL service / network"]
  B --> C{"AG/FCI retains quorum, secondary healthy?"}
  C -->|Yes| D["Fail over per policy/runbook"]
  C -->|No| E["Evaluate backup restore/DR"]
  D --> F["Verify listener DNS, app reconnect"]
  E --> F
  F --> G["Test transactions and data consistency"]
  G --> H["Reconcile RPO/RTO, file incident report"]
~~~

Failover does not preserve every connection and in-flight transaction; clients must reconnect/retry **idempotently** per business logic. If the AG is asynchronous, quantify potential data loss before triggering DR.

## 31. Guided Hands-On Exercise

> **Safety:** execute only in an authorized lab resource group/VM with budget approval. Creating VMs, installing SQL, backing up, resizing disks, and setting up HA can incur costs or cause downtime. This lesson does not require running commands that alter production.

### Part A — Architecture Design

Model a Java API requiring SQL Server:

1. Justify why SQL VM is needed over Azure SQL Database/Managed Instance.
2. Select Windows/Linux, SQL version/edition, and licensing per real entitlements.
3. Draw the VNet: app subnet, SQL VM private subnet, admin access, Storage/Key Vault connectivity.
4. Select VM size from peak CPU/RAM, VM-level I/O caps, and HA targets.
5. Separate data/log/`tempdb` and choose disk performance tiers.
6. Design a backup policy with RPO/RTO, retention, and a restore drill schedule.
7. Select required HA/DR, listener/quorum, and fault domains.
8. Define monitoring alerts, ownership, and cost tags.

### Part B — Inspect an Existing Azure VM

1. Run `az account show` to confirm the subscription.
2. Run `az vm show` to inspect VM size, location, and storage profile.
3. Run `az sql vm show` to inspect SQL VM registration if present.
4. Check NSGs and private networking using Portal/CLI tools permitted by your organization.
5. Check VM CPU metrics and ensure no secrets appear in output.
6. Check disk SKUs, LUNs, host caching, and disk capacities with read-only permissions.
7. Check active automated backup/Azure Backup protection policies.

### Part C — Inspect Using T-SQL

1. Check SQL version/edition, database list, and recovery models.
2. List data/log files and physical paths.
3. Run the I/O latency DMV twice to calculate a delta.
4. Inspect wait stats over an appropriate window; distinguish log waits, CPU, and blocking.
5. Inspect Query Store or execution plans for a slow lab query.
6. Verify logins/application permissions and TLS certificates per policy.
7. Inspect backup history and last successful full/diff/log backups.
8. Run restore verification/a restore drill on an independent lab instance if authorized.

### Part D — Failure Simulation

In a non-production lab:

1. Intentionally misconfigure a client app port/hostname to distinguish DNS from auth failures.
2. Test a query missing an index and measure latency; inspect the plan before adding the index.
3. Simulate a failed backup job; observe alerts and recovery gaps.
4. If an HA lab cluster exists, execute a failover per runbook and measure downtime/reconnect.
5. Test TDE certificate/backup dependencies in a test environment if using TDE.
6. Compare VM/disk costs against estimates and clean up the lab as authorized.

### Self-Check Questions

**Q1.** What is the biggest operational responsibility difference between SQL Server on Azure VM and Azure SQL Managed Instance?

**Q2.** Are the SQL IaaS Agent extension and SQL virtual machine resource a second SQL Server instance?

**Q3.** Why can a VM SKU IOPS cap throttle performance even when a managed disk is provisioned with very high IOPS?

**Q4.** Why do transaction logs typically need low disk latency and merit separating from data files?

**Q5.** Should user databases and sole backups be placed on temporary local SSDs? Why or why not?

**Q6.** Is a SQL VM with a private VNet IP automatically protected if the application account uses `sysadmin`?

**Q7.** What is the difference between Azure managed disk encryption, SQL TDE, and TLS?

**Q8.** Does setting the FULL recovery model automatically create log backups and guarantee point-in-time restore?

**Q9.** Why is `RESTORE VERIFYONLY` insufficient to prove RTO and complete post-restore data integrity?

**Q10.** How does an Availability Zone differ from a two-replica SQL Always On Availability Group?

**Q11.** How do AG and FCI differ in storage and failover scope?

**Q12.** When an AG fails over, what non-database objects (logins, jobs, linked servers, app DNS) must be checked?

**Q13.** Does an async AG replica guarantee RPO=0 if the primary region fails?

**Q14.** Why must SQL Server file I/O DMVs be read using deltas rather than comparing a single cumulative value?

**Q15.** VM CPU is low, yet the SQL API is slow; what categories of causes could explain this?

**Q16.** Why must Azure Hybrid Benefit be verified against actual entitlements rather than toggling tags/`licenseType` at will?

**Q17.** A SQL VM using TLS with `trustServerCertificate=false` throws a certificate error; what is the proper fix?

**Q18.** A system requires a 10-minute RTO, but database backup restore takes 90 minutes; what solutions must be evaluated?

**Q19.** Which charges continue accruing after deallocating a lab VM?

**Q20.** When should you recommend migrating from a SQL VM to Azure SQL Managed Instance/Database?

**Completion criteria:** learners can make an IaaS/PaaS decision, diagram a SQL VM with proper storage/networking/identity, build backup-restore/HA runbooks, inspect systems using Azure CLI + T-SQL, understand performance/licensing limits, and evaluate security/costs.

## Conclusion

**SQL Server on Azure Virtual Machines** is the right IaaS option when you need **control over the SQL Server instance and OS**, compatibility with legacy systems, or a phased migration. It lets you leverage Azure VMs, managed disks, Availability Zones, private networking, Azure Monitor, Azure Backup, and eligible licensing models.

However, SQL Server on an Azure VM still demands an **actively responsible operations team** handling sizing, data/log layout, SQL patching, identity/TLS/TDE, backups and restore drills, Always On/FCI, DR, I/O and SQL wait monitoring, incident response, and total cost optimization. A trustworthy platform is built on **measured RPO/RTO, defense in depth, tested failovers/restores, and monitoring tied to business outcomes**—not merely a `Running` VM status in the Azure Portal.