# Choosing Azure SQL and Managed Relational Databases

An e-commerce application with orders, inventory, customers, and payments requires consistent data, rollbackable transactions, SQL queries, and a recovery plan when the system encounters failures. When moving an application to Microsoft Azure, the question is not just "where to run SQL," but **choosing the right database engine, managed service level, performance architecture, security, HA/DR, and cost**.

Azure offers several services for relational data: **Azure SQL Database**, **Azure SQL Managed Instance**, **SQL Server on Azure Virtual Machines**, **Azure Database for PostgreSQL – Flexible Server**, and **Azure Database for MySQL – Flexible Server**. They all support structured data, but do not share the same engine, compatibility, billing model, or administrative responsibilities.

This lesson belongs to the **Relational Databases** chapter of the **CLOUD_PROVIDERS_AZURE** module. The knowledge connects with Azure subscriptions, resource groups, Microsoft Entra ID, VNet, Private Endpoint, App Service, Azure Functions, AKS, Azure Monitor, security, and cost control for an application on Azure.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Identify relational workloads suited for SQL, transactions, foreign keys, and ACID.
2. Distinguish between PaaS databases and SQL Server on Azure VM (IaaS), including maintenance/backup responsibilities.
3. Compare Azure SQL Database single database, elastic pool, serverless, and Hyperscale.
4. Determine when to use Azure SQL Managed Instance to migrate existing SQL Server workloads.
5. Recognize requirements that necessitate choosing SQL Server on a VM.
6. Choose PostgreSQL/MySQL Flexible Server when the application uses the corresponding engine.
7. Compare service tiers: DTU/vCore, General Purpose, Business Critical, and Hyperscale.
8. Design requirements for backups, PITR, LTR, zone redundancy, geo-replication, and RPO/RTO.
9. Understand Microsoft Entra authentication, managed identity, SQL database permissions, and private networking.
10. Practice inspecting/creating an Azure SQL Database and running sample T-SQL statements.
11. Plan migration, benchmarking, operations, monitoring, and TCO optimization.
12. Make well-founded decisions using a requirements matrix, real-world scenarios, and a production checklist.

**Note:** service tier names, regions, SKUs, limits, and capabilities change over time. Azure CLI/SQL examples are only for authorized labs; do not execute them blindly. Before going to production, verify the capabilities of the supported engine version, Azure region, and pricing model.

## 2. Why Relational Databases Matter

### 2.1. Data with Cross-Table Constraints

~~~mermaid
erDiagram
    CUSTOMERS ||--o{ ORDERS : places
    ORDERS ||--|{ ORDER_ITEMS : contains
    CUSTOMERS {
        uniqueidentifier customer_id PK
        string name
    }
    ORDERS {
        uniqueidentifier order_id PK
        uniqueidentifier customer_id FK
        string status
    }
    ORDER_ITEMS {
        uniqueidentifier order_id FK
        string sku
        int quantity
    }
~~~

Relational database management systems support:

- **Schema:** tables, data types, constraints.
- **Primary keys and foreign keys:** ensure referenced records are valid.
- **Indexes:** accelerate queries based on access predicates.
- **SQL:** filtering, joins, aggregations, updates, and transactions.
- **Transactions:** multiple changes are committed or rolled back according to engine guarantees.
- **Concurrency control:** isolation levels, locking, or MVCC depending on the DBMS.

An ordering system must prevent situations where an order is created without existing line items or inventory counts are updated inconsistently.

### 2.2. What Does ACID Solve?

| Property | Meaning | Illustration |
|---|---|---|
| Atomicity | Operations within a transaction commit/rollback as a single unit | Creating Order and OrderItem commits together |
| Consistency | Data obeys constraints and rules enforced by the design | A foreign key cannot point to a non-existent customer |
| Isolation | Concurrent transactions do not observe invalid intermediate states per the isolation level | Two users ordering the last item |
| Durability | Committed data is persisted according to the service/engine guarantee | Committed data does not reside only in process memory |

ACID **does not automatically fix business logic bugs**, does not guarantee no deadlocks will occur, and does not mean an asynchronous geo-secondary will lose zero transactions if an entire region fails.

### 2.3. OLTP, Analytics, and Mixed Workloads

- **OLTP:** many short transactions, indexed queries, requiring good p95 latency.
- **Analytics/OLAP:** reading/scanning large datasets, grouping/aggregating, reporting.
- **Mixed:** the same database serving transactional APIs and heavy reporting.

Do not select a tier based solely on storage size in GB. A 20 GB database with thousands of TPS may require more compute than a rarely accessed 1 TB database. If reporting causes bottlenecks for transactions, you may need read replicas, ETL/warehousing, or a dedicated analytics architecture.

## 3. Shared Responsibility: How PaaS and IaaS Differ

### 3.1. Layers Managed by the Customer vs. Azure

~~~mermaid
flowchart LR
    U["Application / API"] --> P["Managed SQL PaaS"]
    U --> V["SQL Server on Azure VM"]
    P --> M["Azure manages OS/engine infrastructure, patching, backups per service"]
    V --> O["Customer manages OS, SQL instance, backups, HA"]
    M --> D["Customer remains responsible for data, schema, permissions, queries"]
    O --> D
~~~

**PaaS does not mean no DBA is needed.** Azure handles much of the infrastructure, but the customer still manages schema, database permissions, queries, application connection pooling, compliance, business data recovery, and HA/DR choices.

### 3.2. Responsibility Matrix

| Task | Azure SQL Database | Azure SQL Managed Instance | SQL Server VM |
|---|---|---|---|
| OS and underlying DB infrastructure | Azure | Azure | Primarily customer |
| SQL engine servicing/patching | Azure service | Azure service | Customer coordinates deployment |
| Automated backups | Managed by service per policy | Managed by service per policy | Customer designs or uses supporting tools |
| Base service HA | Per service tier | Per service tier | Must be designed/administered |
| Backup retention and DR objectives | Customer decides | Customer decides | Customer decides |
| Index/query/schema | Customer | Customer | Customer |
| SQL data permissions | Customer | Customer | Customer |
| OS access | No | No | Yes |
| Licensing responsibility | Per PaaS model | Per PaaS model | Per VM/SQL licensing |

A backup created by the service **does not replace restore testing** and data reconciliation. An automatically patched PaaS **does not replace managing drivers and preventing SQL injection in the application**.

## 4. Overview of Options on Azure

| Service | Engine | Management Model | Typically Suited For |
|---|---|---|---|
| **Azure SQL Database** | Microsoft SQL/T-SQL at database level | PaaS | Cloud-native apps, microservices, SaaS DB-per-tenant |
| **Azure SQL Managed Instance** | SQL Server-compatible at instance level | PaaS | SQL Server migrations requiring many instance-level features |
| **SQL Server on Azure VM** | Customer-managed SQL Server | IaaS | Legacy workloads, vendor requirements, OS/full instance control |
| **PostgreSQL Flexible Server** | PostgreSQL | PaaS | PostgreSQL apps, JSONB, supported ecosystem/extensions |
| **MySQL Flexible Server** | MySQL | PaaS | MySQL apps, web/CMS/e-commerce |

### 4.1. Initial Decision Tree

~~~mermaid
flowchart TD
    Q["Current or chosen engine?"] --> E{"Engine already chosen?"}
    E -->|PostgreSQL| PG["Azure Database for PostgreSQL Flexible Server"]
    E -->|MySQL| MY["Azure Database for MySQL Flexible Server"]
    E -->|SQL Server/T-SQL| S{"Need instance-level features?"}
    E -->|Not yet| X["Evaluate ecosystem, SQL features, skills, TCO"]
    X --> E
    S -->|No| DB["Azure SQL Database"]
    S -->|Yes, MI supported| MI["Azure SQL Managed Instance"]
    S -->|Need OS/full control| VM["SQL Server Azure VM"]
    DB --> C{"Multiple DBs with staggered load?"}
    C -->|Yes| EP["Elastic pool"]
    C -->|No| SD["Single DB / suitable tier"]
~~~

This is only a **filter**, not an architectural conclusion. Mandatory requirements regarding compliance, latency, licensing, HA/DR, and migration compatibility must be verified before deciding.

### 4.2. Azure SQL Is Not a Generic Name for Every SQL Engine

An application using PostgreSQL extensions, PL/pgSQL, PostGIS, or JSONB cannot run on Azure SQL Database simply by changing the connection string. The same applies to a MySQL application relying on specific charsets, storage engines, or stored programs. Likewise, SQL Server Agent jobs and T-SQL stored procedures do not run natively on MySQL/PostgreSQL.

## 5. Azure SQL Database: Database-Level PaaS Service

### 5.1. Logical Server Is Not a SQL Server VM

~~~mermaid
flowchart LR
    A["App Service / Functions / AKS"] --> L["Azure SQL logical server endpoint"]
    L --> D1["Database orders"]
    L --> D2["Database inventory"]
    L --> D3["Database payments"]
    D1 --> B["Automated backups / PaaS HA"]
    D2 --> B
    D3 --> B
~~~

A **logical server** is a management resource that houses SQL databases and certain networking/authentication configurations. It is not a VM that users can RDP into for SQL Server OS access. Compute/scaling for a database or elastic pool is managed according to the chosen model.

### 5.2. Single Database

Suitable when an application has one database or a few DBs with independent workloads:

- Want billing and performance sizing per individual DB.
- Do not need SQL Server Agent, OS-level control, or unsupported instance features.
- Want to reduce OS/engine operations.
- Want autoscale or to choose a service tier matching product capabilities.

For example, an Orders API on App Service connects to a SQL Database `ordersdb` via Microsoft Entra identity and Private Endpoint.

### 5.3. Elastic Pool

An elastic pool allows multiple Azure SQL databases to share a pool of compute resources appropriately. For example, a SaaS with 100 customers, each with its own DB, where peak usage occurs at different hours.

~~~text
09:00 Tenants A, B have heavy transactions.
12:00 Tenants C, D have heavy transactions.
18:00 Tenant E runs batch processing.
The remaining databases have low load.
~~~

Instead of over-provisioning resources for each single DB, an elastic pool can provide cost efficiency. However, if tenants peak simultaneously or one tenant consumes heavy I/O, the pool can still experience bottlenecks. You must examine:

- Total and peak CPU/IO/log throughput.
- Per-database min/max limits per tier.
- Peak concurrency across tenants.
- Storage and data growth rate.
- Ability to isolate tenants with special requirements.
- Pool cost compared to the actual set of single databases.

**An elastic pool is not auto-sharding** and does not provide proper schema/data isolation in place of the application; each tenant DB still requires security, backups, and operations.

### 5.4. Serverless Compute

In supported Azure SQL Database tier/compute combinations, serverless can:

- Automatically scale compute within configured min/max limits.
- Auto-pause/auto-resume when specific conditions are met.
- Still incur storage and other charges even when compute is paused.
- Exhibit resume latency when the application reconnects.
- Fail to auto-pause if persistent connections or background tasks prevent pausing.

**Serverless is not always cheaper than provisioned.** For 24/7 applications or SLAs requiring immediate response after idle periods, you must measure actual costs and cold-resume latency. Certain tiers/hardware/regions have differing limits and capabilities.

### 5.5. Hyperscale

Hyperscale is an Azure SQL Database service tier using a different storage/compute architecture from standard tiers, suitable when:

- The database is large or growing rapidly.
- Hyperscale's backup/restore and scaling/storage capabilities are needed.
- Read workloads fit supported replica options.
- Performance and total cost have been benchmarked.

Do not assume Hyperscale is always the fastest or best option. You must verify supported features, service limits, region availability, zone redundancy capabilities, compute models, and migration/rollback requirements.

### 5.6. Limitations Compared to Traditional SQL Server

Azure SQL Database does not support every SQL Server instance-level feature identically to a SQL Server VM. During migration, check:

- SQL Server Agent and job scheduling.
- Linked servers/instance-level objects.
- Cross-database queries/transactions.
- SQL CLR and extended server features.
- File-system/OS integration.
- Server-level settings and security model.
- T-SQL syntax and compatibility level.
- Third-party driver/extension requirements.

If the application cannot replace instance-level features, continue evaluating Managed Instance or SQL Server VM.

## 6. Azure SQL Managed Instance

### 6.1. Product Goal

Azure SQL Managed Instance (MI) serves SQL Server workloads needing broad **instance-level** compatibility compared to SQL Database while having Azure manage most of the infrastructure. For example, a legacy ERP system with SQL Agent jobs, multiple databases, and complex stored procedures.

### 6.2. Key Highlights

- A managed instance hosts and manages multiple databases.
- Supports more SQL Server instance features than Azure SQL Database.
- Provides service tiers/capacity options and PaaS HA/backups per configuration.
- Has a specific network, subnet, and DNS model.
- Can reduce code modifications in certain SQL Server migrations compared to SQL Database.
- **Still has unsupported features/differences** compared to SQL Server on VM.

Managed Instance **does not grant RDP access to the OS**, nor does it allow arbitrary installation of OS-level drivers, agents, or SQL Server binaries. Such dependencies must be evaluated separately.

### 6.3. VNet and Subnet for MI

MI deploys into a VNet-integrated network configuration with its own specific model. Requirements for subnet delegation, CIDR, routes, NSGs, hybrid connectivity, and DNS must be prepared according to MI documentation before provisioning.

Do not take Azure SQL Database Private Endpoint guides and apply every step directly to MI. The network model, endpoints, ports, and security controls are not identical.

### 6.4. When Is MI Not Needed?

- Only a single new DB with no need for instance features.
- Want serverless compute suited for intermittent load at the DB level.
- Want an elastic pool for many tenant databases.
- The application uses PostgreSQL/MySQL.
- Provisioned MI cost does not fit a small workload.
- Require OS access/full SQL binaries unavailable on MI.

**A migration compatibility assessment is still mandatory**, even if the source application runs Microsoft SQL Server.

## 7. SQL Server on Azure Virtual Machines

### 7.1. When Full Control Is Required

SQL Server on Azure VM is suitable if:

- A vendor only certifies SQL Server running on a specific Windows/Linux/VM setup.
- OS-level access, specific SQL Server versions, drivers, or agents are needed.
- SQL Server features not yet available on SQL Database/MI are required.
- Lifting and shifting a legacy system that cannot yet be rewritten.
- There is a DBA/SRE team capable of operating patching, backups, and HA/DR.

### 7.2. Associated Responsibilities

| Item | Required Actions |
|---|---|
| OS | Patching/hardening, disk encryption, EDR, firewall |
| SQL Server | Instance/version/CU, engine configuration |
| Disk I/O | Data/log/tempdb layout, IOPS/throughput/caching |
| Backup | Schedule, retention, encryption, offsite backups, restore testing |
| HA | Availability Groups/replicas, listener/quorum per design |
| DR | Secondary region, failover/failback runbook |
| Monitoring | OS and SQL metrics, deadlocks, query waits |
| Capacity | VM CPU/RAM, disks, peak/auto-scaling strategy |
| Licensing | SQL Server license and Azure Hybrid Benefit if eligible |

Azure provides tools/extensions to assist SQL VMs and Azure Backup in supported scenarios, but they do not turn a VM into SQL PaaS.

### 7.3. VMs Are Not Necessarily Cheaper Than PaaS

When comparing costs, include licenses, disks, backups, HA replicas, secondary region, DBA on-call, patching, and incident handling time. Comparing only one VM/hour against one database vCore/hour is usually an unfair comparison.

## 8. PostgreSQL and MySQL Flexible Server

### 8.1. PostgreSQL Flexible Server

Suitable when the application is built on PostgreSQL:

- psycopg/Npgsql/PostgreSQL JDBC drivers.
- PostgreSQL SQL dialect, PL/pgSQL, JSON/JSONB.
- Extensions supported by Azure per version and region.
- Workloads needing a PostgreSQL-compatible relational engine.
- Wanting Azure to manage most OS/engine servicing/backups.

If the application depends on PostGIS or other extensions, check the **specific extension** and version supported by Flexible Server, rather than just looking at the PostgreSQL product name.

### 8.2. MySQL Flexible Server

Suitable when the application runs MySQL:

- Websites, CMS platforms, and transactional applications using MySQL drivers.
- MySQL schemas, InnoDB, stored programs, and collations.
- Need PaaS HA, backups, and compute/storage management per service capabilities.

Verify exact engine versions, charsets, collations, SQL modes, plugins, and migration support.

### 8.3. Do Not Mix the Three SQL Dialects

| Item | Azure SQL / SQL Server | PostgreSQL | MySQL |
|---|---|---|---|
| SQL dialect | T-SQL | PostgreSQL SQL, PL/pgSQL | MySQL SQL |
| Common SDKs/drivers | Microsoft.Data.SqlClient, JDBC SQL Server | Npgsql, psycopg, JDBC PG | MySQL Connector/J |
| JSON | JSON features per SQL engine version | JSON/JSONB | JSON per MySQL version |
| Stored procedures | T-SQL and feature matrix | PL/pgSQL / languages | MySQL stored programs |
| Engine-specific extensions | SQL Server features | Supported PostgreSQL extensions | Supported MySQL plugins/features |

Changing engines requires schema conversion, rewriting SQL/stored code, and data testing. You cannot simply swap the connection string.

### 8.4. Networking and HA Differ from Azure SQL

PostgreSQL/MySQL Flexible Server has options for private/public connectivity, VNet integration/Private Link, backups, HA, and read replicas depending on engine, tier, region, and server creation mode. Some network mode transitions have constraints; **networking must be decided during design**, not after migration is complete.

## 9. Service Tiers and Compute Purchasing Models

### 9.1. DTU and vCore

**DTU-based** represents bundled CPU/memory/I/O resources within defined service objectives. **vCore-based** provides compute selection by vCores, hardware family, storage, and tier.

There is no exact `1 DTU = X vCore` conversion formula for every workload. When changing pricing models, you must benchmark CPU, memory, read/write I/O, log rate, transaction latency, and cost.

### 9.2. General Purpose, Business Critical, and Hyperscale

| Tier | Intended Use | What to Measure |
|---|---|---|
| General Purpose | Balanced price/performance for many workloads | CPU, latency, log rate, I/O limits |
| Business Critical | OLTP needing higher latency/availability characteristics per configuration | Compute/storage overhead, cost, replica support |
| Hyperscale | Very large databases, scalable storage/compute architecture | Growth, backup/restore, supported features |
| DTU Basic/Standard/Premium | Tiers based on DTU service objectives | DTU usage, limits, and cost |

Zone redundancy, read replicas, serverless compute, failover, or hardware families **are not identical across all tiers**. Check the feature matrix by SKU and region before assuming a capability is available.

### 9.3. Sizing Capacity from Metrics

Collect:

1. Average/peak CPU by hour, week, and month-end.
2. Memory working set and cache behavior.
3. Data size, growth rate, and storage constraints.
4. Reads/writes, IOPS, latency, and log generation rate.
5. Transactions/second, concurrent users/connections.
6. p95/p99 query durations and service latency.
7. Query execution plans, expensive queries, deadlocks.
8. Backup/restore times, HA/DR requirements.
9. Expected peak after App Service/AKS/Functions scale-out.
10. Budget and headroom.

**Upgrading a tier will not fix an application with N+1 queries**, missing/wrong indexes, or transactions holding locks too long.

### 9.4. Provisioned or Serverless?

| Criterion | Serverless (if supported) | Provisioned |
|---|---|---|
| Intermittent load | Potentially cost-effective | Idle compute still incurs cost |
| Steady 24/7 load | Not guaranteed to save money | Predictable budgeting |
| Auto-pause/resume | Conditional | Generally not the same model |
| Resume latency | Must be tested | No auto-resume from pause |
| Compute config | Min/max per model | Select provisioned capacity |
| Storage cost | Still billed | Still billed |

Do not assume a DB with periodic jobs, monitoring, or open connection pools will pause on schedule. Decide only after observing idle periods and benchmarking.

## 10. High Availability, Backup, and Disaster Recovery

### 10.1. Distinguishing Mechanisms

| Mechanism | Solves | Does Not Automatically Solve |
|---|---|---|
| Service HA | Node/infrastructure failures within service tier scope | Full region outage in all cases |
| Zone redundancy | Certain Availability Zone failures | Accidental data deletion |
| Automated backups | Data recovery per retention | Instant RTO |
| PITR (point-in-time restore) | Restore to a supported point in time | Automated production rollback in one command |
| LTR (long-term retention) | Storing long-term backups per policy | Unlimited default retention |
| Geo-replication / failover groups | Cross-region DR per configuration | RPO=0 in every failure |
| App retry/reconnect | Transient failover errors | Fixing flawed transaction logic |

Azure SQL Database/MI provides service-managed automated backups. Customers must manage retention, geo-backup strategy, restoration processes, and meeting business requirements.

### 10.2. RPO and RTO

- **RPO:** maximum acceptable data loss in an incident, measured in time.
- **RTO:** maximum target time to restore service.

For example, a business defines targets:

~~~text
RPO <= 5 minutes
RTO <= 60 minutes
~~~

These are **internal targets**, not a guarantee that every Azure SQL tier automatically meets them. Geo-replication can be asynchronous, so the secondary has replication lag. Failover also depends on DNS/listener, drivers, app reconnection, and data verification.

### 10.3. Point-in-Time Restore

Procedure for restoring a database after accidental record deletion:

1. Find the last timestamp when the data was still valid.
2. Confirm the database's PITR retention.
3. Restore to a valid point in time; in SQL Database scenarios this typically creates a **new restored database**.
4. Verify data/permissions and integrity.
5. Reconcile transactions created after the restore timestamp.
6. Choose how to merge data or cut over the application with approval.
7. Monitor post-recovery and save UTC evidence.

**Do not assume restore is equivalent to safely undoing all transactions after time X.** Valid orders may have been created after the restore point.

### 10.4. LTR and Backup Policy

When compliance requires retaining backups long-term:

- Define weekly/monthly/yearly retention per product capabilities.
- Select an appropriate region and data residency.
- Check storage encryption/CMK if required.
- Drill restoring from an LTR backup and measure actual RTO.
- Calculate backup storage and network costs.
- Manage permissions for policy deletion and data destruction.
- Document owner/legal/privacy requirements.

Do not arbitrarily set multi-year LTR "just in case"; balance legal obligations, data deletion rights, and cost.

### 10.5. Geo-Replication and Failover

For supported products/tiers:

- Evaluate primary/secondary topology and replication lag.
- Define automatic/manual failover per policy.
- Check read-write/read-only listeners and application routing.
- Verify DNS, firewall, Private Endpoint, and identity in the secondary region.
- Test reconnect/retry after failover; pooled connections may need refreshing.
- Measure RPO/RTO and plan failback.
- Account for data loss if failover happens before the secondary receives all transaction logs.

**A read replica is not a backup against logic errors**: accidental data deletion can be replicated.

### 10.6. Flexible Server Has Its Own Mechanisms

PostgreSQL/MySQL Flexible Server supports backups, PITR, and HA/read replicas depending on engine and configuration. Do not apply a SQL Database failover group diagram to PostgreSQL/MySQL without verifying service-specific HA/DR behavior.

## 11. Networking: Connecting to Databases Securely

### 11.1. Conceptual Architecture

~~~mermaid
flowchart LR
    C["Clients"] --> API["APIM / Front Door"]
    API --> APP["App Service / Azure Functions / AKS"]
    APP --> V["VNet integration / AKS network"]
    V --> DNS["Private DNS"]
    DNS --> PE["Private connectivity"]
    PE --> SQL["Managed relational database"]
    APP --> ID["Managed Identity / Entra token"]
    ID -. "Auth token" .-> SQL
    APP --> MON["Application Insights"]
    SQL --> MON
~~~

A private network does not automatically grant SELECT permissions. You need **DNS, route/TCP, TLS, authentication, and database authorization**.

### 11.2. Azure SQL Database Connectivity

Available models may include:

- Public endpoint with firewall/IP rules.
- VNet service endpoint rules in supported configurations.
- **Private Endpoint / Azure Private Link**.
- Disabling public network access once the private path is tested.

An example SQL logical server hostname:

~~~text
sqlorderslab.database.windows.net
~~~

When using Private Endpoint, clients usually continue using the canonical SQL hostname in the driver; DNS via the associated **privatelink.database.windows.net** zone resolves to the private IP when properly configured.

**Do not hard-code private IPs** to "fix DNS": this risks breaking certificate hostname verification, failover, and endpoint changes. Check DNS directly from the workload runtime:

~~~bash
nslookup sqlorderslab.database.windows.net
~~~

Results on a laptop do not prove an AKS Pod or Azure Function has the same route/DNS.

### 11.3. Do Not Over-Open the Network

The Azure SQL option "Allow Azure services and resources to access this server" has a broader scope than a single application. Do not enable it just to resolve a connection timeout without understanding the security boundary. Instead, define subnets, VNet integration, Private Endpoint, DNS resolver, firewall, and NSGs by design.

### 11.4. Managed Instance and Flexible Server

- **Managed Instance:** requires subnet/VNet networking and MI-specific conditions; check ports, delegation, routes, and private/hybrid access per documentation.
- **PostgreSQL/MySQL Flexible Server:** has networking models different from SQL Database; choosing private/public mode during provisioning can affect future transition options.
- **SQL Server VM:** uses VM NICs, NSGs, routes, and SQL listener/ports per instance configuration; the customer directly hardens the network and OS.

### 11.5. Layered Connection Troubleshooting

1. **DNS:** does the server hostname resolve?
2. **TCP/network:** does traffic reach the right port, subnet, and endpoint?
3. **TLS:** does the driver verify the certificate/hostname?
4. **Authentication:** is the SQL login/Entra token valid?
5. **Authorization:** does the principal have CONNECT/SELECT/EXECUTE on the right DB/schema?
6. **Query/runtime:** are there timeouts, deadlocks, or throttling?

Do not grant `db_owner` to fix a DNS issue; do not open a public firewall just because SQL permissions are missing.

## 12. Identity, SQL Permissions, and Security

### 12.1. Management Plane Differs from Data Plane

| Layer | Example | Control |
|---|---|---|
| Azure RBAC | Reader/Contributor on Azure SQL resource | Create/modify/delete resources, management operations |
| Microsoft Entra ID | User/group/managed identity | Login/token identity |
| SQL data-plane rights | CONNECT, SELECT, INSERT, EXECUTE, GRANT | Operations inside the database |
| Network | Firewall/Private Endpoint/VNet | Connection path |
| Application authorization | Which orders User A can view | Business permissions |

An Azure Contributor on a resource group **does not default to having SQL SELECT**. An Azure Function with managed identity enabled **does not automatically have a database user**.

### 12.2. Microsoft Entra and Managed Identity

~~~mermaid
sequenceDiagram
    participant A as App Service / Function
    participant M as Managed Identity Endpoint
    participant E as Microsoft Entra ID
    participant S as Azure SQL Database
    A->>M: Request token for SQL
    M->>E: Authenticate platform identity
    E-->>M: Access token
    M-->>A: Token
    A->>S: Connect over TLS with token
    S->>S: Verify DB user and permissions
    S-->>A: Result or permission error
~~~

Managed identity reduces the need to store SQL passwords, but you must still create the database principal and grant permissions per engine. Separate runtime app identities, migration identities, and DBA/break-glass identities.

### 12.3. T-SQL Example for Least Privilege

Once a Microsoft Entra admin is configured and logged into the **correct database** with a privileged principal, for example:

~~~sql
-- Principal name must match the corresponding Microsoft Entra identity.
CREATE USER [mi-orders-api] FROM EXTERNAL PROVIDER;

-- Read-only access to the existing sales schema.
GRANT SELECT ON SCHEMA::sales TO [mi-orders-api];
~~~

Display names can collide; verify the Entra principal/object ID and supported product syntax. Do not assume an arbitrary name always resolves to the right object. For apps needing write access, grant specific permissions only for required tables/schemas/procedures; avoid standing `db_owner`.

### 12.4. Sample .NET Connection String

With a Microsoft.Data.SqlClient version supporting Active Directory Default:

~~~text
Server=tcp:sqlorderslab.database.windows.net,1433;
Database=ordersdb;
Encrypt=True;
TrustServerCertificate=False;
Authentication=Active Directory Default;
~~~

This is a multi-line display example. Verify the driver, credential selection, and Entra permissions. For user-assigned identities, specify the client ID per the corresponding SDK/driver guide; **client ID differs from principal/object ID**.

### 12.5. SQL Authentication When Required

If a legacy application uses SQL username/password:

- Never put real passwords in source code, Dockerfiles, plain-text IaC, or logs.
- Use an approved Key Vault/secret manager.
- Rotate secrets on schedule and after any exposure.
- Restrict SQL user permissions.
- Separate credentials per environment.
- Use TLS and certificate verification.
- Plan a transition to Entra identity when feasible.

### 12.6. Encryption and Auditing

- **TLS:** encryption in transit.
- **TDE:** encryption at rest supported by the service; does not prevent a user with valid SELECT from reading plaintext.
- **Customer-managed key:** used when key control is required, with Key Vault/HSM, rotation, and recovery.
- **Always Encrypted:** client-side encryption for specific columns per engine/driver support, affecting queries.
- **Auditing:** records events per policy, protecting logs and retention.
- **Defender for SQL/Defender for Cloud:** detects posture/threats per enabled tier.
- **Data classification/masking:** supports governance; does not replace database authorization.

Runtime identities should not have DDL/database admin rights. An injection vulnerability paired with DROP/ALTER rights can destroy far more data than an account with only business-required SELECT/INSERT. Use parameterized queries and secure coding independently of DB permissions.

## 13. Performance: Choosing a Tier After Understanding the Application

### 13.1. Why Are Queries Slow?

A slow SQL query can result from:

- No index matching the filter predicates or joins.
- Execution plans using suboptimal scan or join strategies.
- Query returning too many rows/columns; unnecessary `SELECT *`.
- ORM generating N+1 queries and excessive network round trips.
- Transactions holding locks too long, contention, or deadlocks.
- CPU, memory, log throughput, or I/O hitting tier limits.
- Connection pool exhaustion; opening a connection per HTTP request.
- Stale statistics, parameter-sensitive plans, or index fragmentation in relevant cases.
- Schema/optimization changes causing regressions.
- Database/network located in a different region from the application causing latency.

**Upgrading compute vCores does not automatically fix N+1 queries**, long transaction locks, or SQL injection. Measure and address the actual bottleneck.

### 13.2. Metrics to Watch

| Metric | Question | Possible Action |
|---|---|---|
| CPU utilization | Is DB compute hitting limits? | Optimize queries then consider scaling |
| Data I/O | Excessive reading/writing of data pages? | Index/query, tier/storage assessment |
| Log write rate | Are transaction log writes the bottleneck? | Reduce batch/transaction overhead, size capacity |
| Memory pressure | Is working set/plan cache sufficient? | Index/query/memory tier |
| Sessions/connections | Connection leak or burst? | Pooling and app-side concurrency |
| Query duration p95/p99 | Impacting user experience? | Compare against baseline, Query Store |
| Deadlocks | Lock contention from design? | Lock ordering, transaction scope, retry |
| Storage usage | Rate of data/index growth? | Capacity forecast and retention |
| Replication lag | Does DR/replica have stale data? | Check topology and RPO |
| Failed connections | Network/auth/capacity errors? | Investigate layer by layer |

Query Store and Azure SQL performance insights tools help observe queries/plans and regressions per engine capabilities. Do not enable automatic tuning unintentionally if the environment requires approval for schema/index changes.

### 13.3. Connection Pooling Is Especially Critical with Cloud Autoscaling

Suppose Azure Functions scales out to 80 instances, each configured with a SQL connection pool max of 40 connections. If all use the maximum simultaneously, theoretically there could be **3,200 connections**. This is an illustrative multiplication; in practice drivers/instances might not open the full pool, but the risk of a connection storm is real.

A sound strategy:

1. Open connections close to query execution and close/return them to the pool properly.
2. Never hold a transaction open while awaiting an external HTTP API.
3. Use parameterized SQL and avoid N+1 queries.
4. Cap pool size and concurrency according to SKU/DB limits.
5. Monitor p95 DB dependency latency as HPA/Functions scale.
6. Use transient retries with backoff and clear timeouts.
7. Do not retry an entire transaction with side effects without guaranteeing idempotency.
8. Consider Queue/Service Bus as a buffer during workload bursts.

### 13.4. Read Replicas and Reporting Workloads

Read replica/read-only routing options vary by SQL service tier or Flexible Server engine. When using them:

- Verify supported replica features and requirements.
- Offload reporting queries from primary OLTP if beneficial.
- Understand replication lag, consistency, and read-after-write behavior.
- Do not route business queries requiring freshly committed data to a stale replica.
- Measure replica cost/throughput.
- Do not treat a replica as a backup against accidental business data deletion.

## 14. Hands-On: Azure SQL Database and Relational Schema

### 14.1. Lab Scope

In this exercise, assume the Azure SQL **logical server already exists**, created and configured by the infrastructure team under security policy. We create a new database and run sample T-SQL.

~~~text
Subscription: <SUBSCRIPTION_ID>
Resource group: rg-sql-lab
Logical SQL server: sqlorderslab
Database: ordersdb
Region: per existing server
Compute: supported General Purpose vCore objective
~~~

Do not run database creation commands in production unapproved. Provisioning databases incurs cost, and the example logical server name may not exist.

### 14.2. Identify Subscription and Read Server Configuration

~~~bash
az account show --output table
az account set --subscription "<SUBSCRIPTION_ID>"

az sql server show \
  --resource-group rg-sql-lab \
  --name sqlorderslab \
  --query "{name:name,location:location,fullyQualifiedDomainName:fullyQualifiedDomainName}" \
  --output json
~~~

If the logical server does not exist yet, it must be provisioned via Portal or IaC following the organization's identity/networking/admin workflow. This guide avoids passing real SQL administrator passwords via command line to prevent exposure in shell history, process inspection, or CI logs.

### 14.3. Create a Database

Assuming the SKU/hardware in the region permits the illustrative service objective:

~~~bash
az sql db create \
  --resource-group rg-sql-lab \
  --server sqlorderslab \
  --name ordersdb \
  --service-objective GP_Gen5_2
~~~

**GP_Gen5_2 is only an example service objective**. Check SKU availability, storage limits, tier, and region before running. Do not assume this is the optimal configuration for production.

Verify after creation:

~~~bash
az sql db show \
  --resource-group rg-sql-lab \
  --server sqlorderslab \
  --name ordersdb \
  --query "{name:name,status:status,edition:edition,sku:sku,location:location}" \
  --output json

az sql db list \
  --resource-group rg-sql-lab \
  --server sqlorderslab \
  --output table
~~~

These commands use the **Azure management plane**; they do not prove SQL login/data-plane permissions are working.

### 14.4. Connect with Microsoft Entra Authentication

Before querying:

1. A DBA has configured Entra admin/permissions for the SQL logical server and database.
2. The machine has proper routing, firewall/Private Endpoint, DNS, and TLS.
3. The user running the query has SQL CONNECT and table permissions.
4. The SQL client/driver supports the intended Entra authentication type.

Example with a `sqlcmd` version supporting the Entra authentication option:

~~~bash
sqlcmd \
  -S sqlorderslab.database.windows.net \
  -d ordersdb \
  -G \
  -Q "SELECT DB_NAME() AS CurrentDatabase;"
~~~

Different `sqlcmd`/ODBC versions configure TLS/auth differently; check `sqlcmd --help` and actual driver documentation. Do not enable `TrustServerCertificate` or disable TLS hostname verification to work around connection errors.

### 14.5. Create Tables and Constraints

Run T-SQL in **ordersdb** using a principal with DDL rights in the lab:

~~~sql
CREATE SCHEMA sales;
GO

CREATE TABLE sales.Customers
(
    CustomerId uniqueidentifier NOT NULL
        CONSTRAINT PK_Customers PRIMARY KEY,
    DisplayName nvarchar(200) NOT NULL,
    CreatedAtUtc datetime2(3) NOT NULL
        CONSTRAINT DF_Customers_CreatedAtUtc DEFAULT SYSUTCDATETIME()
);
GO

CREATE TABLE sales.Orders
(
    OrderId uniqueidentifier NOT NULL
        CONSTRAINT PK_Orders PRIMARY KEY,
    CustomerId uniqueidentifier NOT NULL,
    Amount decimal(18, 2) NOT NULL,
    Status varchar(20) NOT NULL,
    CreatedAtUtc datetime2(3) NOT NULL
        CONSTRAINT DF_Orders_CreatedAtUtc DEFAULT SYSUTCDATETIME(),

    CONSTRAINT FK_Orders_Customers
        FOREIGN KEY (CustomerId)
        REFERENCES sales.Customers(CustomerId),

    CONSTRAINT CK_Orders_Amount
        CHECK (Amount >= 0),

    CONSTRAINT CK_Orders_Status
        CHECK (Status IN ('pending', 'paid', 'canceled'))
);
GO

CREATE INDEX IX_Orders_CustomerId_CreatedAtUtc
    ON sales.Orders(CustomerId, CreatedAtUtc DESC);
GO
~~~

Explanation:

- **uniqueidentifier** is an illustrative ID choice, not automatically best for every table/index.
- **decimal(18,2)** is better suited than float for many fixed currency values, though currency/tax/rounding rules must be defined.
- The foreign key prevents creating Orders with a non-existent CustomerId.
- CHECK constraints prevent negative amounts and statuses outside the illustrative set.
- The index on CustomerId and CreatedAtUtc supports a specific query group while carrying storage/write overhead.

### 14.6. Transaction Commit or Rollback

~~~sql
DECLARE @CustomerId uniqueidentifier = NEWID();
DECLARE @OrderId uniqueidentifier = NEWID();

BEGIN TRY
    BEGIN TRANSACTION;

    INSERT INTO sales.Customers (CustomerId, DisplayName)
    VALUES (@CustomerId, N'Test Customer');

    INSERT INTO sales.Orders (OrderId, CustomerId, Amount, Status)
    VALUES (@OrderId, @CustomerId, 150000.00, 'pending');

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0
        ROLLBACK TRANSACTION;
    THROW;
END CATCH;
GO
~~~

This is T-SQL, **not PostgreSQL/MySQL syntax**. In a real application, each Order must reference an existing customer if business rules require it; creating a new Customer in the same transaction is solely to illustrate atomicity.

Query:

~~~sql
SELECT TOP (10)
    o.OrderId,
    c.DisplayName,
    o.Amount,
    o.Status,
    o.CreatedAtUtc
FROM sales.Orders AS o
JOIN sales.Customers AS c
  ON c.CustomerId = o.CustomerId
ORDER BY o.CreatedAtUtc DESC;
GO
~~~

### 14.7. Testing Least Privilege

In the database, you can create a read-only principal for the application's Entra managed identity:

~~~sql
-- Run only after Entra admin, principal, and schema are prepared.
CREATE USER [mi-orders-reader] FROM EXTERNAL PROVIDER;
GRANT SELECT ON SCHEMA::sales TO [mi-orders-reader];
GO
~~~

Some environments require configuring identity mapping or checking specific permissions; do not assume a display name always maps uniquely. Verify using **the app identity itself**, not a DBA login. A reader does not need ALTER/DROP/CONTROL permissions.

### 14.8. Ending the Lab and Costs

A provisioned Azure SQL Database can continue incurring charges. Only delete lab resources confirmed to be no longer in use or without needed data. Do not run commands to delete a SQL server holding multiple databases just to clean up one lesson; monitor Azure Cost Management and budgets.

## 15. Connecting Cloud-Native Applications to Databases

### 15.1. Reference Architecture

~~~mermaid
flowchart LR
    C["Client"] --> F["Front Door / API Management"]
    F --> APP["App Service / Azure Functions"]
    APP --> VN["VNet integration"]
    VN --> PE["Private Endpoint + Private DNS"]
    PE --> DB["Azure SQL Database"]
    APP --> MI["Managed Identity / Entra ID"]
    MI -. "Token" .-> DB
    APP --> MON["Application Insights"]
    DB --> MON
~~~

In this model:

- API ingress/gateway handles requests and does not carry the database admin password.
- Managed identity enables the app to acquire SQL tokens.
- Private Endpoint restricts the network path.
- The SQL principal has least-privilege data permissions.
- Backup/PITR and DR are designed per business SLA.
- Monitoring tracks both application and database.

### 15.2. Azure Functions and Database Scaling

Azure Functions can scale out suddenly. If each Function instance opens multiple SQL connections, the DB can suffer a connection storm:

- Set pool and concurrency limits.
- Use async I/O appropriately with the driver.
- Do not keep transactions open while calling external APIs.
- Load test with bursts and cold starts.
- Do not rely on SQL serverless auto-resume when the SLA requires very low latency.
- Use a queue to buffer and throttle write rates.
- Test transient retries and idempotency.

### 15.3. AKS and Databases

An AKS deployment with 30 Pods, where each Pod has multiple workers and connection pools, requires calculating total capacity, not just Pod count. Private connectivity requires VNet DNS/routing; Microsoft Entra Workload ID can provide identities to Pods via supported mechanisms.

**Kubernetes RBAC is not database SQL permissions.** A ServiceAccount with Pod read permissions does not thereby get SELECT access on the Orders table.

## 16. Migrating Data to Azure: Assessment Before Cutover

### 16.1. Choosing a Landing Zone by Compatibility

~~~mermaid
flowchart TD
    S["Existing SQL Server"] --> A["Inventory + Assessment"]
    A --> Q{"Instance-level / OS dependencies?"}
    Q -->|No| DB["Candidate: Azure SQL Database"]
    Q -->|Yes, MI supported| MI["Candidate: SQL Managed Instance"]
    Q -->|Need OS/full SQL control| VM["Candidate: SQL Server VM"]
    DB --> T["Migration pilot + performance tests"]
    MI --> T
    VM --> T
    T --> C["Cutover + validation + fallback"]
~~~

When the source database is PostgreSQL/MySQL, an engine-specific assessment and migration plan must be used. Do not use a SQL Server migration tool for all relational databases.

### 16.2. Pre-Migration Inventory

Record:

- Engine/version/edition and end-of-support status.
- Number of databases, size, growth rate, file layout.
- Stored procedures, triggers, functions, views.
- SQL Agent, linked servers, integration services, cross-database queries.
- SQL CLR, custom plugins, OS dependencies.
- Collation, case sensitivity, timezone, encoding.
- Logins/users, permissions, Entra integration, encryption.
- Throughput, CPU, memory, I/O, connections, query latency.
- Backup schedule, restore testing, RPO/RTO.
- Application dependencies, drivers, configs, hard-coded hostnames.
- Downtime budget, data residency, cutover window.

### 16.3. Tools and Methods

You can evaluate Microsoft-supported migration/assessment solutions such as Azure Database Migration Service, Azure SQL migration guidance/tools, backup/restore, schema conversion, and replication matching the **exact source/target/version**.

Online migration and offline migration involve trade-offs:

| Approach | Advantages | Risks |
|---|---|---|
| Offline/downtime cutover | Simpler workflow | Requires downtime based on size and speed |
| Online/replication | Reduces downtime when supported | Replication lag, cutover complexity, data validation |
| Lift-and-shift VM | Fewer initial engine/OS changes | Retains operational overhead |
| Replatform MI | PaaS with broader SQL Server compatibility | Feature/network/sizing assessment |
| Modernize SQL Database | Cloud-native database-level architecture | Code/instance feature changes may be large |
| Re-engine (switch engine) | Standardize on PostgreSQL/MySQL or others | High schema/code conversion cost and risk |

Support matrices change; do not promise "zero downtime" online migration for every engine or database size.

### 16.4. 12-Step Process

1. **Discover:** list databases and dependencies.
2. **Assess:** analyze unsupported features.
3. **Design:** select engine/tier/network/identity/HA/DR.
4. **Provision:** create target via IaC, tags, monitoring, and security.
5. **Prepare:** migration tooling, backups, and rollback plan.
6. **Convert:** adjust schemas/SQL/features if needed.
7. **Pilot:** migrate a subset, test queries and data.
8. **Benchmark:** compare latency, throughput, CPU, lock behavior.
9. **Rehearse:** practice cutover/failback and data reconciliation.
10. **Cutover:** freeze writes or coordinate per migration mechanism.
11. **Validate:** row counts, checksums, business invariants, end-to-end tests.
12. **Monitor/decommission:** monitor and decommission the old source only after sign-off.

Changing the connection string **is not the entire migration**. You must verify SQL users, network, TLS, collation, application retries, jobs, data correctness, and backup policy.

### 16.5. Post-Migration Data

An aggregate checksum can help detect discrepancies, but it is not sufficient to guarantee all business invariants. For example:

- Total OrderItems count must match.
- Orders must have no invalid customer references.
- Total order amount over a period is reconciled.
- Payment/fulfillment states are consistent.
- Row changes during the cutover window are captured.
- No duplicate or missing transactions.

Test data must be anonymized and compliant with policy; never copy production PII into uncontrolled lab environments.

## 17. Cost and Total Cost of Ownership

### 17.1. Cost Components

~~~text
TCO =
  Compute / database service capacity
+ Data storage / log / IOPS per product model
+ Backup retention / LTR / geo-backup
+ HA, read replicas, geo-secondary / DR
+ Network/private connectivity/egress
+ Monitoring, audits, Defender
+ Licensing / Azure Hybrid Benefit if eligible
+ DBA/SRE operations, patching, migration, testing
+ Risk buffer for peak workload and incident recovery
~~~

This formula is an analytical framework, not a unified pricing formula across all SKUs. Each tier/region/service bills differently.

### 17.2. Cost-Saving Levers

- Choose the right engine from the start to avoid wasteful rewrites.
- Choose single DB for independent applications.
- Consider elastic pools for multiple databases with staggered peaks.
- Consider serverless for genuinely idle periods and SLAs tolerant of resume latency.
- Right-size vCores/storage based on metrics and benchmarks.
- Evaluate Reserved capacity/Azure Hybrid Benefit if eligible.
- Retain backups/LTR/geo-replicas per business requirements, not excessively.
- Manage Log Analytics retention and sampling while keeping essential audits.
- Set budgets/tags for dev/test/production environments.
- Test releases/rollbacks via checklists to reduce incident costs.

### 17.3. Example Where Elastic Pool Can Save Cost

A SaaS has 20 tenants, each using a separate database. For most of the day, only 2–3 DBs have high load; the rest are very low. An elastic pool can improve resource sharing efficiency.

However, you must check **concurrent peaks**, not just daily averages. If all 20 tenants run month-end closing simultaneously, the pool can hit CPU/log I/O limits. A solid plan:

1. Collect per-DB metrics across a business cycle.
2. Build aggregate concurrent load over short intervals.
3. Define per-DB and pool limits.
4. Load test month-end/campaign events.
5. Compare costs and SLAs between pool and single DBs.
6. Isolate large tenants from the pool when they cause noisy-neighbor effects.

### 17.4. Do Not Ignore Operations Cost of SQL VM

SQL Server VM can meet technical constraints, but total cost also includes OS patching, SQL licensing, disk tuning, monitoring, backup infrastructure, HA secondaries, DBA on-call, and DR drills. Do not compare VM compute price directly against PaaS price while omitting those items.

## 18. Case Studies: Choosing a Service by Problem

### 18.1. New Order API

**Scenario:** .NET API on App Service, familiar SQL/T-SQL, single DB, OLTP transactions, small team.

**First candidate:** Azure SQL Database single database.

**Rationale:** PaaS reduces engine operations, includes managed backups, and supports Entra identity/private connectivity by design. Choose General Purpose or another tier after load testing; do not default to Business Critical.

**Must verify:** p95 latency, query plans, connection pooling, PITR, HA/DR, and cost.

### 18.2. 500-Tenant SaaS

**Scenario:** one database per tenant, mostly low load, staggered peak hours.

**Candidate:** Azure SQL Database elastic pool for small/medium groups, dedicated single databases for large tenants or those needing special isolation.

**Must verify:** pool peak, per-tenant metrics, noisy neighbor, backup/tenant lifecycle, security boundary, and auto-provisioning.

### 18.3. 15-Year-Old SQL Server ERP

**Scenario:** multiple databases, SQL Agent, stored procedures, limited migration downtime, desire to reduce OS management.

**Candidate:** Azure SQL Managed Instance after feature assessment.

If dependent on an OS driver/feature unavailable on MI, use SQL Server on Azure VM as a transitional choice.

### 18.4. Vendor App Requiring a Windows-Level Agent

**Scenario:** vendor only certifies SQL Server installed on Windows Server with a custom agent.

**Candidate:** SQL Server on Azure VM.

**Conditions:** DBA/SRE staff, licenses, HA/backups, patching, and DR runbook. Do not assume the VM automatically gets PaaS backups.

### 18.5. GIS Application Using PostgreSQL/PostGIS

**Scenario:** PostgreSQL drivers, JSONB, PostGIS.

**Candidate:** Azure Database for PostgreSQL Flexible Server if the extension/engine version is supported.

### 18.6. CMS Website Using MySQL

**Scenario:** web application currently running MySQL and its corresponding plugin ecosystem.

**Candidate:** Azure Database for MySQL Flexible Server; verify charset, SQL mode, engine version, backups, private networking, and pricing.

**Case study conclusion:** six relational workloads should not necessarily choose the same Azure database service.

## 19. Weighted Decision Matrix

An architecture team may choose an example matrix:

| Criterion | Illustrative Weight | Question |
|---|---:|---|
| Engine/feature compatibility | 30% | Do SQL dialect, features, and extensions run properly? |
| HA/DR/availability | 20% | Does it meet RPO/RTO and regional requirements? |
| Operations/skills | 15% | Can the team manage the OS/DB engine? |
| Performance/scalability | 15% | TPS, connections, I/O, data growth, latency? |
| Security/network/compliance | 10% | Entra, VNet, audit, data residency? |
| TCO | 10% | Compute, storage, backups, licenses, DBA cost? |

Weights are only a methodology, **not a mandatory Azure best practice**. If there is a hard constraint such as data needing to stay in a specific region or requiring PostGIS/SQL Server Agent, eliminate non-compliant services before calculating total scores.

### 19.1. Architecture Decision Record (ADR)

~~~text
Decision: Azure SQL Database - single database
Context: .NET OLTP app, one database, no SQL Agent dependency
Alternatives: SQL Managed Instance, SQL Server VM, PostgreSQL
Rationale:
  - SQL Server-compatible data model
  - PaaS operations match team capacity
  - Entra identity + private networking
  - Backup/HA/DR plan meets validated requirements
Risks:
  - Connection storm during Functions scale-out
  - Uncertain peak sizing
Mitigations:
  - Connection pooling and cap concurrency
  - Load test p95 latency and log throughput
  - Practice PITR restore and failover
Review trigger:
  - SQL instance-level features required
  - Unexpected data growth or latency regression
  - Region/compliance requirement changes
~~~

An ADR records assumptions and rationale; it does not replace testing or security reviews.

## 20. Monitoring and Operations

### 20.1. Telemetry Sources

- **Azure Monitor metrics:** CPU, memory/IO/log utilization, storage, connections per service.
- **Query Store/SQL performance tooling:** slow queries, execution plans, regressions.
- **Database auditing:** data activities and privileged events per configuration.
- **Azure Activity Log:** resource changes, firewall, SKU, identities.
- **Application Insights:** SQL dependency latency/errors from the application.
- **Defender for Cloud/SQL:** security assessments/alerts if enabled.
- **Azure Cost Management:** compute, storage, backups, replicas, log costs.
- **Business metrics:** checkout success, orders/minute, payment consistency.

**Azure Activity Log does not record every SELECT/INSERT**; to audit the data plane, enable the appropriate log source.

### 20.2. Illustrative KQL

If the Application Insights workspace sends dependency data to `AppDependencies`:

~~~kusto
AppDependencies
| where TimeGenerated > ago(1h)
| where Type has "SQL"
| summarize Requests=count(),
            Failed=countif(Success == false),
            P95ms=percentile(DurationMs, 95)
    by bin(TimeGenerated, 5m), Target
| order by TimeGenerated asc
~~~

Table/column names vary by telemetry schema and ingestion. An empty query result does not prove the DB has no errors if instrumentation/logging is not enabled.

### 20.3. Alerts to Design

| Alert | Situation |
|---|---|
| Sustained high CPU/log I/O | May be approaching limits |
| Storage nearly full | Risk of write disruption |
| p95 SQL dependency increase | SLA impact |
| Connection timeout increase | Network/pooling/capacity |
| Deadlock increase | Transaction conflict/regression |
| Abnormal failover/restart | Availability issue |
| Backup/retention policy change | Recovery risk |
| SQL firewall/public access change | Security change |
| Privileged role/user change | Risk of data abuse |
| Replication lag exceeds RPO | DR risk |
| Cost exceeds baseline | Over-provisioning/abnormal load |

Do not create alerts without owners. Every alert should include a runbook, baseline, and severity level.

## 21. Troubleshooting

| Symptom | Possible Cause | Remediation |
|---|---|---|
| Hostname does not resolve | Private DNS/custom resolver | Check zone/link and DNS path |
| TCP timeout | Route/NSG/firewall/private endpoint | Test from the actual app runtime |
| TLS certificate error | Hostname, driver, trust chain | Use canonical hostname, verify CA |
| SQL login failed | Wrong Entra identity/token or SQL auth | Verify principal and tenant |
| Permission denied SELECT | Insufficient SQL GRANT | Review schema/role/data permissions |
| Azure Contributor cannot read data | Confusing Azure RBAC with DB SQL rights | Create DB user/appropriate GRANT |
| High CPU | Heavy queries/under-provisioning | Query Store, plans/indexes, sizing |
| Saturated data/log I/O | Storage limits or write pattern | Metrics and tier |
| Too many connections | Pool leak/burst | Cap pool × replicas |
| Deadlocks | Transaction locking/concurrency | Lock ordering, shorten transaction scope |
| Slow queries after migration | Different collation, plans, stats, features | Benchmark and SQL assessment |
| Auto-pause not happening | Workload/background activities | Check serverless eligibility |
| High resume latency | Serverless cold resume | Choose compute model per SLA |
| App fails after failover | Pool reconnect/DNS/listener | Driver retries and routing |
| Wrong PITR timestamp | UTC/retention or data reconciliation | Restore runbook |
| Geo-secondary stale | Asynchronous replication lag | Check lag, RPO policy |
| Cost over budget | Over-provisioning/replicas/backups/logs | Azure Cost Management |
| Missing feature after migration | Unsupported SQL feature | Evaluate MI/VM or refactor |

### 21.1. Layered Diagnostic Process

1. Identify the actual service and engine (SQL DB, MI, VM, PostgreSQL, MySQL).
2. Verify subscription, resource, region, UTC timestamps.
3. Verify DNS/network/TLS from the **actual workload**.
4. Confirm identity and SQL data-plane permissions.
5. Review resource utilization, Query Store, wait stats/slow queries.
6. Correlate application dependency logs and correlation IDs.
7. Check recent changes: code, schema, indexes, roles, firewall, tier.
8. Assess data safety and backup/restore if data loss risk exists.
9. Apply approved rollback/recovery.
10. Document root cause and preventive actions.

**Do not fix DNS errors with `db_owner`. Do not fix SQL 403 by opening public networks. Do not fix N+1 queries with the most expensive tier without measuring.**

## 22. Pre-Production Checklist

### Product Selection

- [ ] List of source engine version and features exists.
- [ ] T-SQL, SQL Agent, cross-database, and extensions have been evaluated.
- [ ] PaaS or IaaS chosen according to operational responsibilities.
- [ ] Hard requirements and migration compatibility assessment completed.
- [ ] Proof of concept/load test completed, not relying solely on pricing spreadsheets.
- [ ] ADR, risks, and review triggers documented.

### Networking and Identity

- [ ] Subscription/resource group/region and tags are correct.
- [ ] Private Endpoint/VNet/DNS and egress verified.
- [ ] Public network not opened beyond requirements.
- [ ] Microsoft Entra identity, SQL users/GRANT follow least privilege.
- [ ] DBA/migration identities separated from runtime identity.
- [ ] Remaining secrets protected in Key Vault.
- [ ] TLS encryption and certificate verification enabled.

### Data, Backup, and DR

- [ ] Schema/constraints/indexes reviewed.
- [ ] PITR and retention meet business policy.
- [ ] Backup/LTR configured if required by compliance.
- [ ] Restore rehearsed, actual measured RTO known.
- [ ] Geo-DR/failover aligns with RPO/RTO targets.
- [ ] Replication lag and data residency considered.
- [ ] Schema migration and rollback compatible with application versions.
- [ ] Audit/security logs have retention and an owner.

### Performance and Cost

- [ ] DB resources sized from CPU, I/O, log rate, latency, concurrency.
- [ ] Connection pools and retries load tested.
- [ ] Functions/AKS scale does not exceed DB capacity.
- [ ] Elastic pool/serverless justified by actual load.
- [ ] App Insights, Query Store, and alerts aligned with SLA.
- [ ] Compute/storage/backup/secondary/license/ops estimated.
- [ ] Budgets/tags/Cost Management configured.

### Operations

- [ ] DBA/SRE owner and on-call assigned.
- [ ] Runbooks for DNS/network/auth/deadlock/restore/failover exist.
- [ ] Change approval process in place for firewall, tier, roles, database schema.
- [ ] Process for deprecation and end-of-support engine versions exists.
- [ ] Migration cutover, reconciliation, and decommission plans exist.
- [ ] Next DR drill scheduled.

## 23. Self-Check Questions

1. **When is relational data a good choice?** When SQL joins, schemas, constraints, and consistent transactions are needed.
2. **Is Azure SQL Database a SQL Server VM?** No; it is a PaaS database.
3. **Does a managed database replace DBA/query tuning?** No.
4. **When is a Single DB appropriate?** Applications with an independent DB and few instance-level dependencies.
5. **When is an Elastic pool appropriate?** Multiple DBs with staggered loads that can share compute efficiently.
6. **Does an Elastic pool automatically shard tenant data?** No.
7. **Is Serverless completely free when paused?** No, storage and other charges still apply.
8. **Why might Serverless fail to auto-pause?** Persistent connections, background activity, or unsupported features.
9. **Is Hyperscale automatically the cheapest/fastest tier?** No.
10. **What kind of SQL Server migration does Managed Instance help with?** Workloads needing instance features and broader compatibility than SQL Database.
11. **Does MI allow users to RDP into the OS?** No.
12. **When does SQL Server VM make sense?** When OS/full SQL control is required or due to vendor/feature constraints.
13. **Can PostgreSQL run on Azure SQL DB just by changing the connection string?** No.
14. **Why must PostgreSQL extensions be checked?** Flexible Server only supports specific extensions/versions.
15. **Which service should a MySQL source evaluate first?** MySQL Flexible Server if requirements align.
16. **Can DTU be converted exactly into vCore via a single factor?** No.
17. **How do General Purpose and Business Critical differ?** Performance/availability/storage orientation per service tier.
18. **What does RPO mean?** Maximum acceptable data loss, measured in time.
19. **What does RTO mean?** Target recovery time objective.
20. **Does HA replace PITR when data is accidentally deleted?** No.
21. **Does geo-replication guarantee zero data loss?** Not when replication is asynchronous.
22. **Does Private Endpoint automatically grant SQL SELECT?** No.
23. **Does Azure Contributor automatically grant database SELECT?** No.
24. **Does a Managed identity need database permissions?** Yes.
25. **Why shouldn't Private Endpoint IPs be hard-coded?** TLS hostname/DNS/failover can break.
26. **Does TDE prevent someone with SELECT from reading plaintext?** No.
27. **Why is connection pooling important during AKS scale-out?** To prevent a DB connection storm.
28. **Will upgrading tiers fix N+1 queries?** Not necessarily; code/queries must be optimized.
29. **What can go wrong in a migration even after all data is copied?** SQL features, jobs, permissions, collation, DNS, drivers, performance.
30. **What does TCO include besides compute?** Storage, backups, replicas/DR, licenses, network, monitoring, and staffing.
31. **When to choose MI over VM?** When MI satisfies feature requirements and the team wants to reduce OS/engine ops.
32. **How must a good database choice be proven?** Compatibility, network/security, performance tests, restore/DR exercises, and total cost.

## 24. References

- [Azure SQL documentation](https://learn.microsoft.com/azure/azure-sql/) — Azure SQL product family and deployment models.
- [Azure SQL Database overview](https://learn.microsoft.com/azure/azure-sql/database/sql-database-paas-overview) — PaaS database.
- [Azure SQL Managed Instance overview](https://learn.microsoft.com/azure/azure-sql/managed-instance/sql-managed-instance-paas-overview) — instance features and compatibility.
- [SQL Server on Azure VMs](https://learn.microsoft.com/azure/azure-sql/virtual-machines/) — SQL Server IaaS.
- [Azure SQL service tiers](https://learn.microsoft.com/azure/azure-sql/database/service-tiers-sql-database-vcore) — vCore, General Purpose, Business Critical, Hyperscale.
- [DTU-based service tiers](https://learn.microsoft.com/azure/azure-sql/database/service-tiers-dtu) — DTU objectives.
- [Azure SQL elastic pools](https://learn.microsoft.com/azure/azure-sql/database/elastic-pool-overview) — shared compute for DBs.
- [Azure SQL serverless](https://learn.microsoft.com/azure/azure-sql/database/serverless-tier-overview) — compute scaling and pause.
- [Azure SQL Hyperscale](https://learn.microsoft.com/azure/azure-sql/database/service-tier-hyperscale) — storage/compute architecture.
- [Azure SQL security](https://learn.microsoft.com/azure/azure-sql/database/security-overview) — identity, auditing, and encryption.
- [Azure SQL Private Endpoint](https://learn.microsoft.com/azure/azure-sql/database/private-endpoint-overview) — networking and DNS.
- [Azure SQL automated backups](https://learn.microsoft.com/azure/azure-sql/database/automated-backups-overview) — PITR and LTR.
- [Active geo-replication](https://learn.microsoft.com/azure/azure-sql/database/active-geo-replication-overview) — geo-secondary.
- [Azure SQL failover groups](https://learn.microsoft.com/azure/azure-sql/database/failover-group-sql-db) — DR and failover.
- [PostgreSQL Flexible Server overview](https://learn.microsoft.com/azure/postgresql/flexible-server/overview) — PostgreSQL PaaS.
- [MySQL Flexible Server overview](https://learn.microsoft.com/azure/mysql/flexible-server/overview) — MySQL PaaS.
- [Azure Database Migration Service](https://learn.microsoft.com/azure/dms/dms-overview) — migration scenarios.
- [Monitoring and performance tuning in Azure SQL](https://learn.microsoft.com/azure/azure-sql/database/monitoring-tuning-index) — metrics/Query Store.
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) — estimation by SKU/region.
- [Azure Cost Management](https://learn.microsoft.com/azure/cost-management-billing/costs/) — budgets, tags, and cost analysis.

**Conclusion:** choosing a relational database on Azure must begin with **engine/feature compatibility**, followed by **management level**, **workload pattern/tier**, **private networking and identity**, **backup/HA/DR**, and **total cost of ownership**. Azure SQL Database suits many SQL Server-compatible cloud-native apps; Managed Instance supports many migration scenarios with instance-level dependencies; SQL Server on Azure VM fits when OS/full engine control is needed; PostgreSQL/MySQL Flexible Server serve their respective ecosystems. Only finalize an option after testing feature compatibility, measuring performance, rehearsing recovery, and establishing clear operational ownership.

