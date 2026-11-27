# Azure SQL Database and Data Deployment Models

A Java application running on Azure App Service, Azure Kubernetes Service, or Azure Functions typically needs to store customers, orders, payments, and transaction states. This data has relationships, integrity constraints, and consistent transaction requirements. If managing SQL servers manually, the operations team must handle OS installation, SQL Server patching, high availability setup, backups, and storage provisioning. **Azure SQL Database** provides a relational database under the **Platform as a Service (PaaS)** model, allowing greater focus on schema design, queries, connectivity, and data quality.

However, choosing Azure SQL Database is not just creating a database in the Portal. You must also decide on **single database vs. elastic pool, database-per-tenant vs. shared, compute and storage levels, redundancy models, migration approach, network/identity access permissions, and cost**. Mistakes in these decisions can cause the system to slow down under load, make customer isolation difficult, hinder data recovery, or prevent safe rollbacks.

This lesson belongs to the **Relational Databases** chapter in the **CLOUD_PROVIDERS_AZURE** module. The module explores Microsoft Azure from subscriptions, resource groups, and Microsoft Entra ID to virtual networks, compute, storage, and data; teaching how to deploy, monitor, protect, and control costs for an application architecture. Here, Azure SQL Database is placed within a real-world application architecture and data deployment workflow from development to production.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish between **Azure SQL Database**, **Azure SQL Managed Instance**, and **SQL Server on Azure VM**.
- Explain **logical server**, single database, elastic pool, database replicas, and connectivity.
- Compare **DTU/vCore**, General Purpose, Business Critical, Hyperscale, provisioned, and serverless compute according to support conditions.
- Choose a data model for a single application, multiple applications, and **multi-tenant SaaS**.
- Design relational tables, primary/foreign keys, unique constraints, indexes, and transactions.
- Connect Java to Azure SQL using **Microsoft Entra ID/managed identity** or an appropriate method.
- Design **Private Endpoint, DNS, firewall, TLS, RBAC, database permissions, auditing**, and data protection.
- Distinguish between **zone redundancy**, backup/PITR, geo-replication, and failover groups.
- Implement **schema migrations** using versioned mechanisms, testing, and rollback plans.
- Monitor performance/cost, troubleshoot connection errors, deadlocks, throttling, and recovery.

## 2. What Is Azure SQL Database?

**Azure SQL Database** is an Azure-managed relational database service built on SQL Server technology, featuring the **T-SQL** query language, transactions, indexes, data constraints, and extensive security/availability capabilities. Azure handles many infrastructure operations such as the OS, service patching, high availability components, and service-managed automated backups.

~~~text
Client / Java API
       |
       | TDS over TLS, port 1433 via appropriate network path
       v
Azure SQL logical server endpoint
<SERVER_NAME>.database.windows.net
       |
       +-- Database: orders-dev
       |
       +-- Database: orders-staging
       |
       +-- Database: orders-prod
       |
       +-- Elastic pool (if used)
             +-- tenant-a-db
             +-- tenant-b-db
~~~

The diagram illustrates only **logical addresses and organization**, not physical machines or a recommendation to place dev/staging/prod on the same logical server. For strict isolation requirements, separate logical servers, resource groups, subscriptions, identities, and networks.

### What Azure Manages vs. What You Still Manage

| Managed by Azure per Service Model | Managed by Application/Operations Team |
|---|---|
| PaaS database infrastructure, most platform patching | Schema, constraints, indexes, and migration plans |
| Many provided HA/backup mechanisms | Choosing tier/region/zone redundancy and DR objectives |
| SQL service connectivity at logical endpoint | Firewall, Private Endpoint, DNS, network egress |
| Default encryption at rest per feature | Data authorization, additional key management, auditing |
| Telemetry/monitoring capabilities | Alerts, query optimization, capacity, and budgets |
| Service tier scaling options | Connection pooling, retries, workload isolation |

**PaaS does not mean Azure is responsible for fixing slow queries, application-deleted data, leaked passwords, or breaking migrations.** These remain your design and operational responsibilities.

## 3. Choosing Azure SQL Database, Managed Instance, or SQL Server VM?

All three services share a SQL Server foundation, but differ in management level and compatibility.

| Criterion | Azure SQL Database | Azure SQL Managed Instance | SQL Server on Azure VM |
|---|---|---|---|
| Model | Database-level PaaS | Near instance-level SQL Server PaaS | IaaS, self-managing more of SQL Server/OS |
| Best suited for | Cloud apps, independent DBs, multi-DB SaaS | Migrated workloads needing broad instance-level capabilities | Requiring OS/SQL instance control or specialized features |
| Operational effort | Lighter at the server layer | Removes much of the infrastructure layer management | Heavy responsibility for patching, backups, HA, licensing |
| Instance-level features | Some features limited/different from full SQL Server | Broad instance compatibility, still has differences | Maximum configuration control per edition |
| Networking | Logical server + endpoints, private/public per config | Dedicated MI network design | VM NIC, NSG, SQL listener, HA/network |
| Schema changes | Managed by app/DBA | Managed by app/DBA | Managed by app/DBA |

Choose **Azure SQL Database** when the application is designed cloud-friendly, mainly uses database-level objects, and aims to minimize infrastructure operations. Choose **Managed Instance** if a migrating system requires substantial instance-level compatibility. Choose **SQL Server on VM** when server, OS, or integration controls are required that PaaS models cannot satisfy.

**Do not assume every T-SQL feature or SQL Server Agent job on-premises works identically on Azure SQL Database.** Before migrating, create a compatibility comparison matrix and check cross-database features, jobs, authentication, and extensions.

## 4. A Logical Server Is Not a SQL VM

When creating an Azure SQL Database, you usually create or select an **Azure SQL logical server**. The logical server provides a **DNS name/management point**, a scope for firewall/authentication configurations, and a container to organize databases.

~~~text
Subscription
   |
   +-- Resource group: rg-orders-prod
          |
          +-- Logical server: sql-orders-prod
          |     FQDN: sql-orders-prod.database.windows.net
          |     |
          |     +-- orders-db  (single database)
          |     +-- reports-db
          |
          +-- App Service / AKS workloads
          +-- Private Endpoint / Private DNS
          +-- Azure Monitor diagnostics
~~~

**A logical server is not a VM you SSH/RDP into to install SQL Server.** There is no OS-level administrative access in this model. Configurations for backup retention, availability, and compute/storage can be set per **database/service tier** rather than defaulting to a single setting for the entire logical server.

### Connection Name

Example endpoint:

~~~text
sql-orders-prod.database.windows.net
~~~

For most direct TCP connections, clients use **port 1433** per network configuration. However, a successful connection also depends on DNS, firewall, connection policy, TLS, user/token, and database name. Do not assume opening NSG port 1433 alone is enough to connect to a private Azure SQL Database.

### Management Environment

Distinguish three layers:

1. **Azure RBAC (management plane):** who can create/modify the logical server, databases, Private Endpoint, auditing?
2. **SQL authentication/database permissions (data plane):** which users can SELECT/INSERT/ALTER?
3. **Network restrictions:** which VNet/IP clients can reach the endpoint?

Having **Contributor** on the resource group does not mean having SELECT permissions on all tables. Having a valid database user does not guarantee getting past the firewall.

## 5. The Single Database Model

A **single database** is a database with compute/storage resources and a service objective selected independently per tier, fitting a single workload or clear administrative unit.

~~~text
Orders Java API
      |
      v
Azure SQL Database: orders-prod
  +-- Customers
  +-- Orders
  +-- OrderItems
  +-- Payments
~~~

Benefits:

- Easy lifecycle, schema, restore, and permission management per database.
- Compute/tier can be scaled independently for the database.
- Easy to tie monitoring and ownership to a single application.
- Ideal for microservices with clear data ownership or an internal product.

Limitations:

- If placing multiple tenants in one database, **isolation logic** must be enforced on every query.
- If there are many databases, compute can be wasted when DBs are mostly idle.
- Not all cross-database SQL operations work as on a SQL Server VM.
- Read/write scale and latency requirements may force a different tier/scale design.

### When to Start with a Single Database

An orders API with moderate data volume, relatively predictable traffic, and one team owning the schema typically starts well with a **single database** at an appropriate tier. Only after gathering CPU, I/O, memory, connections, latency, and cost metrics should you decide to scale compute, add read replicas, or partition data.

## 6. Elastic Pool: Multiple Databases Sharing Resources

An **elastic pool** lets multiple Azure SQL databases share a pool of compute resources under a tier-supported model. It is useful when multiple databases have **non-simultaneous usage patterns**, such as dozens of tenants active at different hours.

~~~text
Azure SQL Elastic Pool
  Shared compute capacity
        |
        +-- tenant-a-db -> morning peak
        +-- tenant-b-db -> afternoon peak
        +-- tenant-c-db -> rarely accessed
        +-- tenant-d-db -> occasional reporting
~~~

### When a Pool Is Beneficial

- Many databases have uneven activity.
- Combined concurrent capacity is typically lower than the sum of individual DB peaks.
- You want to manage cost/capacity at the pool level while tracking per-database usage.
- SaaS using database-per-tenant needing cost optimization.

### When a Pool Is Not Beneficial

- A few DBs consistently consume high CPU/I/O at the same time.
- One tenant runs heavy queries causing resource contention in the pool.
- Performance isolation requirements are too strict, requiring dedicated capacity.
- Some DBs need service tiers/regions/features incompatible with the chosen pool.

**An elastic pool does not merge database data into a single schema.** Databases remain logically separate units; sharing occurs mainly at the pool resource layer. Overcrowding a pool can create **noisy-neighbor performance effects**, requiring pool utilization monitoring and setting per-database min/max limits where supported.

### Quick Comparison

| Aspect | Single DB | Elastic Pool |
|---|---|---|
| Capacity | Allocated per DB | Shared across the pool |
| Idle resources | Potentially wasted on low-load DBs | Can be utilized across DBs |
| Impact from other workloads | Minimal direct resource sharing | Possible contention within pool |
| Operations | Simple for a few DBs | Good for many DBs, requires monitoring |
| Use case | Critical API/application | Multi-tenant SaaS/small databases |

## 7. DTU and vCore Resource Models

Azure SQL Database offers resource purchasing models such as **DTU-based** and **vCore-based** depending on tier/offer. You must inspect the selected service objective, not just the database name.

### DTU

**Database Transaction Unit (DTU)** is a blended unit of CPU, memory, and I/O for a service objective. Historical tiers include Basic, Standard, and Premium, each with different limits.

- Easy to start when preferring a single bundled resource level.
- Difficult to map directly to exact core/memory needs of specialized workloads.
- Newer tiers/features and compute options tend to favor vCore.

### vCore

The **vCore** model exposes explicit choices for virtual cores, hardware generation, service tier, and storage parameters. It can suit workload-driven sizing and Azure-supported license savings mechanisms.

| Decision | Questions to Answer |
|---|---|
| Service tier | General Purpose, Business Critical, or Hyperscale? |
| Compute | How many vCores, which hardware type is available? |
| Provisioning | Provisioned or serverless where supported? |
| Storage | Size, growth, I/O latency, backup storage |
| Availability | Zone redundancy, replicas, and geo-DR |
| Billing | Compute, storage, backups, network, and eligible license benefits |

**Do not convert DTU to vCore using an absolute one-to-one formula.** You must measure throughput, p95 latency, CPU, I/O, log write pressure, and load test after changing the service objective.

## 8. General Purpose, Business Critical, and Hyperscale

In the vCore model, three service tiers are commonly evaluated:

| Tier | General Architectural Characteristics | Best Suited For |
|---|---|---|
| **General Purpose** | Compute and storage architected for balanced price/performance | Standard enterprise APIs with non-extreme latency needs |
| **Business Critical** | Designed for lower I/O latency and HA using replicas per tier capabilities | Latency-sensitive OLTP requiring high I/O and HA |
| **Hyperscale** | Decoupled scalable storage/serving architecture for large DBs and tier scaling | Large datasets, rapid growth, specialized backup/restore/scale needs |

Each tier has limits on size, service objectives, read scale, replica topology, and zone/geo settings. **Do not assume every tier supports every combination of serverless, read replicas, or zone redundancy in all regions.**

### Identifying Trade-Offs

- **General Purpose:** usually a good starting point if measurements do not demand ultra-low I/O latency.
- **Business Critical:** pays higher cost in exchange for latency/I/O/HA advantages; must be justified by the workload.
- **Hyperscale:** helpful when DB size/backup/scale exceeds standard designs; not automatically faster or cheaper for small DBs.

A database of just a few GiB with low transactions placed on high-end Business Critical can be an unnecessary expense. Conversely, a financial workload needing low p99 write latency should not pick a tier solely for low price without testing.

## 9. Provisioned Compute and Serverless Compute

**Provisioned compute** reserves the selected capacity for the provisioned duration; suited for steady, continuous workloads needing predictable startup latency.

**Serverless compute** in Azure SQL Database can **auto-scale compute within a min/max range** and, on supported configurations, **auto-pause/auto-resume** when the database genuinely meets idle conditions.

~~~text
Workload over time

00h ---- 06h ---- 09h ---- 15h ---- 20h ---- 24h
        idle     burst    light     burst

Provisioned:
  capacity remains provisioned at configured level

Serverless:
  scales within min/max bounds;
  may auto-pause when conditions are met;
  resume can increase latency on the first request
~~~

### When Serverless Is Suitable

- Dev/test, proof of concept, workloads with long inactive periods.
- Infrequently used APIs that tolerate delay when the database resumes.
- Highly variable loads where auto-scaling is beneficial.

### When Not to Assume Savings

- Applications with health checks, monitoring, or connection pools **constantly keeping the DB active**.
- Background jobs, CDC, or other features preventing auto-pause per service rules.
- SLAs that cannot tolerate cold-resume latency.
- The workload's tier/region/features do not support the desired serverless/auto-pause configuration.

**Serverless does not mean the database is free when there are no queries.** Storage and other components may still incur charges, and auto-pause does not always trigger. Review service tier conditions/limits and calculate based on actual usage.

## 10. Data Deployment Models by Application and Tenant

A foundational decision is **where customer/tenant data lives**. Three main models:

~~~text
(A) Shared database, shared schema
    orders-shared
      Customers(TenantId,...)
      Orders(TenantId,...)

(B) Shared database, separate schemas
    orders-shared
      tenant_a.Orders
      tenant_b.Orders

(C) Database per tenant
    tenant-a-db / tenant-b-db / tenant-c-db
~~~

| Model | Isolation Method | Advantages | Risks/Costs |
|---|---|---|---|
| **Shared DB + shared schema** | TenantId and application/RLS | Resource-efficient, simpler operations when differences are few | Data leaks if tenant filter is missed, noisy neighbor, shared migrations |
| **Shared DB + separate schemas** | Schema and in-DB permissions | Organizes objects per tenant, moderate flexibility | Many schemas cause drift, no per-tenant compute/backup isolation |
| **Database per tenant** | One DB per tenant with matching identity/connection | Independent restore, tier changes, ownership | Many DBs, bulk migrations, higher cost/ops complexity |
| **Sharded databases** | Data split across DBs by shard key | Data scaling and load distribution | Routing, resharding, cross-shard joins/transactions are hard |

No single model fits every SaaS. You must weigh tenant count, data volume, SLAs, sensitive data, per-tenant backup/restore, residency requirements, and cost.

### Decision Examples

- Small SaaS, 20 tenants, a few GiB of data: shared schema with verified tenant isolation may fit.
- 500-tenant SaaS with staggered traffic: database-per-tenant combined with an elastic pool can be advantageous.
- A few very large tenants: place them into dedicated single DBs/high-capacity pools or dedicated shards.
- Customers requiring contractual restore/isolation: separate DBs may be easier to govern than a shared schema.

**Multi-tenant isolation is not just adding a TenantId column.** You must audit every query, join, unique key, cache key, background job, export/backup, and authorization check.

## 11. Designing a Relational Schema for an Ordering Application

Suppose the **Orders API** application has customers and orders. Requirements:

- Every order belongs to one customer and one tenant.
- Email is unique within the tenant per chosen collation/business rules.
- Retrying a request with the same **ExternalOrderId** must not create two orders.
- Total amount is non-negative, and status belongs only to the allowed set.
- An index exists for querying recent orders by tenant.

### Illustrative DDL

~~~sql
CREATE TABLE dbo.Customers (
    TenantId UNIQUEIDENTIFIER NOT NULL,
    CustomerId BIGINT IDENTITY(1,1) NOT NULL,
    Email NVARCHAR(320) NOT NULL,
    CreatedAt DATETIME2(3) NOT NULL
        CONSTRAINT DF_Customers_CreatedAt DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_Customers
        PRIMARY KEY (TenantId, CustomerId),
    CONSTRAINT UQ_Customers_Tenant_Email
        UNIQUE (TenantId, Email)
);

CREATE TABLE dbo.Orders (
    TenantId UNIQUEIDENTIFIER NOT NULL,
    OrderId BIGINT IDENTITY(1,1) NOT NULL,
    CustomerId BIGINT NOT NULL,
    ExternalOrderId NVARCHAR(80) NOT NULL,
    Status VARCHAR(20) NOT NULL
        CONSTRAINT DF_Orders_Status DEFAULT 'PENDING',
    TotalAmount DECIMAL(18,2) NOT NULL,
    CreatedAt DATETIME2(3) NOT NULL
        CONSTRAINT DF_Orders_CreatedAt DEFAULT SYSUTCDATETIME(),
    RowVer ROWVERSION NOT NULL,
    CONSTRAINT PK_Orders PRIMARY KEY (TenantId, OrderId),
    CONSTRAINT FK_Orders_Customers
        FOREIGN KEY (TenantId, CustomerId)
        REFERENCES dbo.Customers(TenantId, CustomerId),
    CONSTRAINT UQ_Orders_Tenant_ExternalOrder
        UNIQUE (TenantId, ExternalOrderId),
    CONSTRAINT CK_Orders_TotalAmount CHECK (TotalAmount >= 0),
    CONSTRAINT CK_Orders_Status
        CHECK (Status IN ('PENDING', 'CONFIRMED', 'CANCELLED'))
);

CREATE INDEX IX_Orders_Tenant_CreatedAt
    ON dbo.Orders (TenantId, CreatedAt DESC)
    INCLUDE (Status, TotalAmount);
~~~

**Run DDL only on an empty, authorized lab database.** The example uses two tables to teach relationships and constraints; a real ordering system may also include OrderItems, Payments, Currency, Taxes, an event outbox, auditing, retention, and data policies.

### Why Use a Composite Key Including TenantId?

The foreign key **(TenantId, CustomerId)** prevents linking an order of tenant A to a customer of tenant B, provided all operations use the schema properly. The unique constraint **(TenantId, ExternalOrderId)** supports idempotent handling per tenant. Both are a **data integrity** layer, not a substitute for user authentication or tenant authorization.

**IDENTITY** generates sequential numbers for identification, without guaranteeing gapless continuity or strict chronological ordering. **ROWVERSION** is a binary token for change detection, **not a date/time**; use explicit CreatedAt/UpdatedAt columns for timestamps.

### Choosing Proper Data Types

- **DECIMAL(18,2)** for monetary amounts if scale fits; never use FLOAT for exact financial calculations.
- **DATETIME2** and **UTC** for timestamps; convert time zones in the presentation layer.
- **NVARCHAR** when Unicode is required.
- **BIGINT/UNIQUEIDENTIFIER** based on identification strategy and data scale.
- **VARCHAR** for status enums when values are bounded by CHECK constraints or lookup tables.
- **NULL/NOT NULL** and defaults clearly reflecting the data contract.

For currencies, **DECIMAL(18,2)** is not sufficient for every currency or business rule; add **CurrencyCode**, rounding rules, and product-specific precision.

## 12. Relationships, Normalization, and Safe Queries

Relational databases rely on:

- **Primary key:** uniquely identifies a record within the chosen scope.
- **Foreign key:** referential constraint preventing orphan relationships.
- **Unique constraint:** protects uniqueness such as external order IDs.
- **Check constraint:** prevents invalid statuses/amounts.
- **Index:** speeds up searches/joins/ordering while adding write and storage overhead.
- **Transaction:** groups changes requiring atomicity.

### Querying Orders by Tenant

~~~sql
SELECT TOP (20)
    o.OrderId,
    o.ExternalOrderId,
    o.Status,
    o.TotalAmount,
    o.CreatedAt,
    c.Email
FROM dbo.Orders AS o
INNER JOIN dbo.Customers AS c
    ON c.TenantId = o.TenantId
   AND c.CustomerId = o.CustomerId
WHERE o.TenantId = @TenantId
ORDER BY o.CreatedAt DESC, o.OrderId DESC;
~~~

Here **@TenantId** is a parameter supplied by the API from **verified principal/tenant authorization**, not an arbitrary query parameter set by the client. Use **parameterized queries/prepared statements**; never concatenate SQL strings with user input.

If the Orders table has millions of rows, indexes must be designed around query patterns, selectivity, execution plans, and actual record counts. **Having an index does not guarantee every query uses it**, and adding indexes can slow down INSERT/UPDATE operations.

### N+1 Queries from ORMs

In Java Spring Data/JPA, an API fetching 100 orders and then executing 100 separate queries to fetch customers can create an **N+1 problem** and inflate DB round trips. Possible solutions include:

- Joins/fetches aligned with the access pattern.
- Batch fetching with sensible limits.
- Projections retrieving only needed fields.
- Controlled caching without sacrificing business consistency.

Avoid blindly eager-loading every relationship on every endpoint, as it can produce bloated joins. Verify using query plans/metrics first.

## 13. ACID Transactions and Optimistic Concurrency

An application creating orders and deducting inventory must maintain valid state even if requests are retried or two users update concurrently.

**ACID** in an RDBMS comprises:

- **Atomicity:** all changes in a transaction commit or roll back together.
- **Consistency:** constraints and data rules are upheld.
- **Isolation:** concurrent transactions are isolated according to the isolation level.
- **Durability:** committed data is durably stored per service guarantees.

### Single-Database Transaction

Example in a parameterized stored procedure:

~~~sql
CREATE OR ALTER PROCEDURE dbo.ConfirmOrder
    @TenantId UNIQUEIDENTIFIER,
    @OrderId BIGINT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    BEGIN TRY
        BEGIN TRANSACTION;

        UPDATE dbo.Orders
           SET Status = 'CONFIRMED'
         WHERE TenantId = @TenantId
           AND OrderId = @OrderId
           AND Status = 'PENDING';

        IF @@ROWCOUNT <> 1
            THROW 50001, 'Order not found or not pending', 1;

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF XACT_STATE() <> 0
            ROLLBACK TRANSACTION;
        THROW;
    END CATCH;
END;
~~~

This example demonstrates **a conditional state transition**. It **does not** yet check user permissions, inventory, payment authorization, event notifications, or end-to-end idempotency. Run this DDL only in your lab; every stored procedure requires a security review before production.

### Optimistic Concurrency with Rowversion

Two clients read the same order; one updates it first. The second client must detect that the value changed:

~~~sql
UPDATE dbo.Orders
SET Status = 'CANCELLED'
WHERE TenantId = @TenantId
  AND OrderId = @OrderId
  AND RowVer = @ExpectedRowVersion
  AND Status = 'PENDING';
~~~

If **@@ROWCOUNT = 0**, the order may not exist, its status may have changed, or its rowversion changed. The API can return **409 Conflict** after verifying the cause per contract. The **@...** parameters are bound by the application/stored procedure; do not run directly without declaring them.

### Retries Must Respect Idempotency

With network errors, the client might not know whether a transaction committed. Blindly retrying an **INSERT** can create duplicate records. An idempotency key like **(TenantId, ExternalOrderId)** and logic handling unique violations per the API contract are required.

**Do not treat retrying every SQL error as safe**: deadlocks, connection resets, and timeouts have different handling mechanisms; distinguish transient errors from non-recoverable data/constraint/authorization errors.

## 14. Isolation Levels, Blocking, and Deadlocks

Azure SQL Database supports SQL Server transaction isolation mechanisms per service/database configuration. **READ COMMITTED** with row versioning in appropriate configurations can reduce many reader/writer blocking scenarios; however, locks and update conflicts must still be understood.

| Phenomenon | Example | Remediation |
|---|---|---|
| **Blocking** | Transaction A holds a lock, B waits | Shorten transaction duration, add indexes, batch work |
| **Deadlock** | A/B lock resources in opposite order and wait on each other | Enforce consistent update ordering, bounded retries |
| **Optimistic conflict** | Rowversion no longer matches | Re-read and return conflict/business retry |
| **Long-running transaction** | Batch updating millions of rows | Process in batches, monitor logs and locking |
| **Stale reads** | Async replica lacks newest records | Choose read target/consistency per requirement |

A banking transaction has different consistency needs than an analytics dashboard. Do not enable the strictest isolation level for all queries without evaluating throughput/lock contention.

## 15. Row-Level Security and the Shared Database Model

With multiple tenants sharing one database, SQL Database **Row-Level Security (RLS)** can help enforce data filtering at the database layer.

~~~text
API validates user/tenant claims
          |
          v
Open pooled DB connection
          |
          v
Set verified tenant context safely
          |
          v
Execute parameterized SQL
          |
          v
RLS security policy filters TenantId rows
~~~

### RLS Is Defense in Depth, Not Magic

A design pattern may use **SESSION_CONTEXT** to pass a verified TenantId, then apply a predicate function in RLS. However:

- The application must set/validate context on **every request and every connection checkout**.
- Connection pools reuse sessions: reset/control context so request B never inherits request A's tenant context.
- Never grant end users direct SQL access or permission to alter security policies.
- Design a trustworthy tenant passing mechanism; **SESSION_CONTEXT itself does not validate JWTs**.
- Test SELECT/UPDATE/DELETE queries, stored procedures, background jobs, and migrations across multiple tenants.

If the backend shares a privileged DB login and has a SQL injection flaw, RLS relying solely on app-set context can be bypassed. Combine **least-privilege SQL permissions, query parameters, application authorization, RLS, and negative tests**.

### Minimum Verification Matrix

| Test | Expected Result |
|---|---|
| Tenant A reads Order A | Succeeds |
| Tenant A reads Order B | Returns no data |
| Tenant A updates Order B | Modifies no data |
| Tenant B reuses pooled connection after A | No leaked context from A |
| Background job without tenant context | Explicitly controlled by role/design |
| Low-privilege SQL principal | Cannot disable RLS/security policy |

Do not treat a single SELECT with `WHERE TenantId` as proof that **the entire API** is protected.

## 16. Sharding and Coordinating Multiple Databases

When data volume or transaction load exceeds the capacity or isolation target of a single database, it can be split into **shards**. Each shard is a database holding a subset of data per shard key.

~~~text
API / Tenant routing service
            |
    shard map (tenant -> database)
        /        |         \
       v         v          v
  sql-db-01  sql-db-02   sql-db-03
  tenants A-E tenants F-J tenants K-N
~~~

### Choosing a Shard Key

For example, **TenantId**:

- A tenant routes consistently to a specific database.
- Easy to isolate/move a tenant if data is primarily tenant-scoped.
- Avoids cross-shard joins/transactions for same-tenant operations.

However, if one tenant grows massive, sharding by tenant cannot split that single tenant further. Choosing **OrderId** or a hash key may force queries for all of a tenant's data to fan out across multiple shards.

### Added Operational Tasks

1. Store and protect the **shard map/routing metadata**.
2. Verify consistent schema versions across all shards.
3. Reshard/move tenants with checkpoints, data verification, and rollback.
4. Monitor individual database health so no single shard exceeds capacity.
5. Handle cross-shard analytics queries with appropriate read/batch solutions.
6. Avoid expecting distributed cross-database transactions/foreign keys to behave like a single database.

**Sharding is not a default starting choice.** Prove actual bottlenecks, optimize schema/indexes/tiers/pools first, and then evaluate the operational cost of sharding.

## 17. Java Applications Connecting to Azure SQL Database

For Java/Spring Boot applications, use the **Microsoft JDBC Driver for SQL Server** with a connection pool like HikariCP. In Azure environments, prefer **Microsoft Entra authentication/managed identity** per supported JDBC version and platform; avoid storing SQL usernames/passwords in Git.

### JDBC Configuration Using Entra ID

Example connection string (replace placeholders with provisioned details):

~~~properties
spring.datasource.url=jdbc:sqlserver://<SERVER_NAME>.database.windows.net:1433;databaseName=<DATABASE_NAME>;encrypt=true;trustServerCertificate=false;hostNameInCertificate=*.database.windows.net;loginTimeout=30;authentication=ActiveDirectoryDefault
spring.datasource.driver-class-name=com.microsoft.sqlserver.jdbc.SQLServerDriver
spring.datasource.hikari.maximum-pool-size=10
spring.datasource.hikari.minimum-idle=2
spring.datasource.hikari.connection-timeout=30000
~~~

**ActiveDirectoryDefault** is a mode supported by the Microsoft JDBC driver in compatible versions, leveraging the Azure identity chain (managed identity in Azure, developer credentials locally) when required libraries are installed. Verify **Microsoft JDBC driver version, azure-identity dependencies, Java version, hostname, and authentication support** before applying. This is an illustrative configuration snippet, not a configuration tested against a live subscription.

### Maven Dependencies to Prepare

~~~xml
<dependencies>
    <dependency>
        <groupId>com.microsoft.sqlserver</groupId>
        <artifactId>mssql-jdbc</artifactId>
        <version>VERIFIED_DRIVER_VERSION</version>
    </dependency>
    <dependency>
        <groupId>com.azure</groupId>
        <artifactId>azure-identity</artifactId>
        <version>VERIFIED_AZURE_IDENTITY_VERSION</version>
    </dependency>
</dependencies>
~~~

This is a **snippet**; replace versions with officially supported BOM/release versions and add framework dependencies. Placeholders cannot build as-is. With user-assigned managed identities, configure the client ID/identity selection method per driver/SDK rather than assuming the chain always picks the right principal.

### SQL Steps Required for Managed Identity

A Function App/App Service/AKS workload with a managed identity **does not automatically have a database user**. An authorized Azure SQL administrator must:

1. Configure the **Microsoft Entra administrator** or supported server identity/Entra auth mechanism.
2. Create a database user for the verified identity.
3. Grant **least-privilege database permissions**.
4. Ensure network connectivity from the workload to SQL works.
5. Test connectivity under the workload's own identity.

Illustrative T-SQL executed by an authorized principal:

~~~sql
CREATE USER [orders-api-mi] FROM EXTERNAL PROVIDER;
-- Depending on the workload, grant permissions on exact tables/schemas:
GRANT SELECT, INSERT, UPDATE ON OBJECT::dbo.Orders TO [orders-api-mi];
GRANT SELECT ON OBJECT::dbo.Customers TO [orders-api-mi];
~~~

The **principal name** must match the actual managed identity/Entra object, and permissions on these two tables are illustrative only. If the workload uses stored procedures, grant EXECUTE instead of direct DML. **Never grant `db_owner` or server admin** just to fix a login error. In some Entra/SQL setups, `CREATE USER` has directory permission prerequisites/limits; do not work around this by putting a SQL admin password in the pipeline.

### Connection Pools and Concurrency

If 50 AKS pods × 20 connections/pod, the system can open up to **1,000 database connections** before counting batch jobs. Azure SQL tiers have worker/session/concurrent workload limits; size accordingly:

~~~text
Potential total connections
= Instance count * maximumPoolSize
+ other clients/queues/migrations
~~~

- Size pools based on concurrency/query latency, not mechanically by CPU core count.
- Configure timeouts/retries with jitter for transient errors; do not retry credential or SQL constraint errors.
- Close ResultSet/Statement/Connection using patterns that reliably return connections to the pool.
- When scaling out the app, inspect database capacity, DTU/vCore utilization, workers, and connection limits.
- For burst-scaling Azure Functions, avoid opening a new connection **per invocation** if the runtime/SDK supports an appropriate pooling model.

## 18. Authentication and Authorization: Azure RBAC Differs from SQL Permissions

A user authorized to create databases in the Azure Portal does not necessarily have permission to read data in `dbo.Orders`. These are distinct permission planes:

| Plane | Subject | Example |
|---|---|---|
| **Azure management plane** | IAM on subscription/resource group/server/database | Azure SQL DB Contributor can manage resources per role definition |
| **SQL data plane** | Contained database user/SQL login/Entra principal | SELECT/INSERT/EXECUTE, roles such as `db_datareader` when appropriate |
| **Network layer** | IP/VNet/Private Endpoint/Firewall | Client has a TCP/TLS path to the logical server |

### Prefer Entra ID with Managed Identity

- Reduces static secrets in deployments.
- Simplifies auditing principals/roles per workload.
- Separates application permissions from migration runners.
- Supports revoking access following the identity lifecycle.

SQL authentication still has supported use cases; if used, store credentials in a secret manager, rotate them, and never embed passwords in committed JDBC URLs.

### Separate Runtime and Migration Permissions

| Identity | Recommended Permissions |
|---|---|
| **Java API runtime** | SELECT/INSERT/UPDATE/EXECUTE on required schemas/tables |
| **Schema migration runner** | Controlled DDL permissions during deployment windows |
| **Read-only reporter** | SELECT on permitted data; may use a separate read endpoint |
| **DB administrator** | Approved configuration changes, recovery, and troubleshooting |

Do not grant **ALTER TABLE/DROP** to the API runtime just because Flyway needs to run. Run migrations in a pipeline using a separate audited identity.

## 19. Public Network, SQL Firewall, and Private Endpoint

An Azure SQL logical server offers network access options depending on configuration:

- **Public endpoint** with firewall rules and public network access policy.
- **Private Endpoint (Private Link)** inside a VNet/subnet with a private IP.
- Additional controls like VNet rules/service endpoints per service capabilities and model used.

**An open firewall does not grant data permissions.** A client still needs valid authentication and SQL GRANT permissions.

### Private Network Architecture

~~~text
AKS / App Service / Functions
     |
     | VNet Integration / AKS node network
     v
Private VNet/subnet + DNS Resolver
     |
     | Private Endpoint IP
     v
Azure SQL logical server
  <SERVER>.database.windows.net
     |
     +-- Azure SQL database
~~~

A Private Endpoint is a network interface inside a VNet, **not a database replica**. To connect, clients still use the designed SQL server hostname; DNS is configured to resolve to the private path.

### Private DNS

Private Link for Azure SQL typically involves the DNS zone:

~~~text
privatelink.database.windows.net
~~~

When using Private Endpoint, configure the Private DNS zone/records, zone links, or DNS forwarding properly so **<SERVER>.database.windows.net** resolves to the private IP via Azure mechanisms. **Do not hard-code private IPs into connection strings** bypassing DNS/TLS hostname verification; IPs can change if endpoints are recreated.

### Networking Traps

1. AKS has a VNet, but the Private DNS zone is not linked to the node VNet.
2. App Service/Functions lack proper **VNet Integration/egress** configuration.
3. Firewalls/NSGs/DNS resolvers block traffic on the actual path.
4. SQL public access is disabled before preparing a private path for the migration runner.
5. DNS works, but the Entra token/SQL user lacks granted permissions.

**Disable public network access only after** testing the app, migrations, monitoring, emergency admin path, and DR region over approved private paths. Locking down the network prematurely can take down the entire service.

## 20. Data Protection: TLS, TDE, Always Encrypted, Auditing

Azure SQL Database supports multiple protection layers with distinct goals:

| Mechanism | Protects | What It Does Not Replace |
|---|---|---|
| **TLS/encrypted connection** | Data in transit between client and service | SQL user permissions |
| **Transparent Data Encryption (TDE)** | Encryption at rest at the database/storage layer per service mechanism | Protecting columns from principals with SELECT rights |
| **Customer-managed key** | TDE key control needs per supported services | Query-level authorization, rotation plans |
| **Always Encrypted** | Sensitive columns with client-side key management per configuration | Query flexibility, app auth, or networking |
| **Dynamic data masking** | Masked display in appropriate contexts | A security boundary for actual underlying data |
| **Auditing/Defender** | Activity visibility, anomaly/vulnerability protection per features | Automatically preventing all SQL injection |
| **RLS** | Row filtering via security predicates | Tenant authentication and full authorization |

### Sensitive Data and Privacy

- Store only data genuinely required for business operations.
- Encrypt/mask PII per classification, retention, and organizational legal rules.
- Never log JDBC connection strings containing passwords or access tokens.
- Configure audit sinks, retention, RBAC, and alerts on permission/schema changes.
- Verify the impact of key rotation, backup restores, and encrypted columns.

**Always Encrypted** requires driver design, encryption metadata, and client-side key management; it is not a checkbox you can enable on every column without affecting the application. Do not confuse Always Encrypted with TDE.

## 21. High Availability Within a Region

Azure SQL Database provides managed high availability per service tier, handling various hardware/software faults without manually installing SQL Server Always On on VMs.

However, **HA does not mean zero interruption ever**. During in-region failovers, open TCP connections can drop; applications must handle transient errors, reconnect, perform controlled retries, and recover transactions idempotently.

### Zone Redundancy

In supported service tiers/regions, **zone-redundant configuration** distributes HA components across multiple **Availability Zones** in a region to reduce single-zone dependency.

| Scenario | Default/Tier HA | Zone Redundancy |
|---|---|---|
| SQL process/node failure | Supported by managed failover | Supported per configuration |
| One Availability Zone outage | Not resilient in all configurations by default | Helps mitigate risk per supported design |
| Entire region outage | Insufficient | Insufficient |
| App fails to reconnect | Not fixed by DB HA | Must fix app retry/connection handling |

**Do not enable zone redundancy solely based on a name in documentation**: check specific region, tier, SKU, quota, availability, and cost. Zone redundancy capabilities vary by service objective/hardware.

### Health Checks and Connection Pools

After an in-region failover, a Java JDBC pool may hold stale/broken connections. Pool validation, retry policies, and transaction boundaries must be tested. Never configure infinite retries on all write statements; this can cause duplicate actions when commit outcomes are uncertain.

## 22. Automated Backups, PITR, and Long-Term Retention

Azure SQL Database provides **automated backups** and **point-in-time restore (PITR)** based on service tier retention. The service manages the backup chain; operators choose retention/backup storage redundancy according to available features and compliance needs.

Key concepts:

| Mechanism | Objective | Limits to Understand |
|---|---|---|
| **PITR** | Restore a database to a point in time within the retention window | Usually creates a new database, not a simple single-table undo button |
| **Long-term retention (LTR)** | Retain backups on a weekly/monthly/yearly schedule for compliance | Policies/ranges/pricing and restore steps depend on configuration |
| **Geo-restore** | Restore from geo-redundant backups when the primary region is unavailable | RTO/RPO depend on backup replication and restore time, not instant failover |
| **Active geo-replication** | Maintain a readable secondary via async replication | Does not replace PITR after logic errors/accidental deletion |
| **Failover group** | Coordinate failover for database groups and endpoints | Does not replace separate backup/archive/restore procedures |

### A Valid PITR Scenario

At 13:20, a faulty migration erroneously updated 80,000 orders. The issue is detected at 13:30. You can restore the database to a timestamp **before the error**, then compare data/restore valid state per runbook.

**PITR typically restores to a separate database**, requiring time and resources; do not trigger a restore directly over production without understanding consequences. If production kept writing valid data from 13:20 to 13:30, switching wholesale to the restored copy would lose valid transactions from that window. You may need **reconciliation**, partial data export, or a verified rename/cutover procedure.

### Backup Retention and Data Laws

- Choose PITR retention based on RPO, recoverability, and cost.
- Configure LTR when long-term retention is required.
- Verify backup storage redundancy, storage region, and data residency.
- Rehearse restores periodically in an isolated environment, measuring time and verifying data.
- Restrict restore/export permissions, as a database copy contains full sensitive data.

**Backup existence does not mean restore has been successfully tested.** A DR plan requires hands-on proof covering permissions, networking, encryption keys, and the application.

## 23. Active Geo-Replication and Failover Groups

Azure SQL Database supports **active geo-replication** to create a secondary database in another region under supported models. Cross-region replication is **asynchronous**, meaning there can be **replication lag and risk of losing recent transactions near the time of an outage**.

~~~text
Azure Region A                          Azure Region B
  App A                                   App B / Standby
    |                                        |
    v                                        v
  Primary Azure SQL Database -----> Readable secondary
                        async replication
~~~

### Active Geo-Replication Is Not Multi-Primary

In the standard architecture, **the primary handles writes**; the secondary typically serves reads and promotion capability. **Do not assume the secondary automatically accepts concurrent business writes to the same data.** If the application requires strict read-after-write consistency, reading from a newly replicated geo-secondary may return stale data.

### Failover Groups

A **failover group** manages a set of databases and a geo-failover strategy between logical servers per service capabilities. It provides logical endpoints (listeners) to avoid hard-coding the primary server name in the application.

~~~text
Java API connection config
     |
     | Failover group read-write listener
     v
Current primary region
     |
     | Async replication
     v
Secondary region

After failover:
  Listener is updated to point to the new primary
  App reopens connections and handles retries
~~~

**Listener DNS does not seamlessly migrate open connections without interruption.** The application must reconnect and respect DNS TTL, driver behavior, and the failover runbook. Some setups also provide a read-only listener; distinguish write endpoints from read-only/read-scale endpoints per documentation.

### Failover Groups Do Not Replicate Everything

When failing over an application to Region B, you must still prepare:

- Secondary logical server, administrative rights, and compatible server-level settings.
- Private Endpoint, Private DNS, VNet integration, firewall rules in the standby region.
- Managed identity/Entra admin and SQL database users per supported model.
- Backend services, APIs, secrets, monitoring, Key Vault, CI runners, and app configs.
- DR data for **non-SQL services** such as Blob, Redis, and messaging.
- Write fencing mechanisms and split-brain prevention per scenario.

If Region A is completely lost, **geo-failover can lose un-replicated data**. Never claim RPO=0 just because a secondary exists. Base RTO/RPO on actual measurements and service commitments.

## 24. RTO/RPO and DR Architecture Decisions

**Recovery Time Objective (RTO):** acceptable duration to restore service operations. **Recovery Point Objective (RPO):** maximum time-measured volume of data that can be lost after an incident.

Example ordering system:

~~~text
Full region outage begins at 10:00
Secondary confirms data up to 09:59:45
Application resumes serving traffic at 10:18

Illustrative measured RPO: 15 seconds of data potentially missing on secondary
Illustrative measured RTO: 18 minutes
~~~

These figures are **illustrative only**, not an Azure SQL SLO or guarantee. RPO analysis must include unsynchronized transactions, non-Azure SQL DBs, and side effects like payments/emails.

### Option Selection Table

| Objective | Capabilities/Configurations to Consider |
|---|---|
| Node fault or intra-region failover | Managed HA + retries/JDBC pool |
| Availability Zone outage | Zone redundancy if supported by region/tier |
| Accidental data deletion/update | PITR/LTR + reconciliation |
| Full region outage | Geo-replication/failover group or geo-restore per RTO/RPO |
| Reading data in another region | Geo-secondary/read routing, accepting replica lag |
| Protection from stolen credentials | Identity/RBAC, networking, auditing, key rotation |

**One measure does not replace all others.** Geo-replication can replicate an accidental DELETE to the secondary; PITR and auditing remain essential.

## 25. Schema Deployment: Migrations Differ from App Deployment

A Java application can be released as a container image/JAR, but the database schema is **persistent state**. Schema changes must be versioned and evaluated for compatibility with running application versions.

Common tools:

| Tool/Approach | Model | What to Manage |
|---|---|---|
| **Flyway** | Versioned SQL migrations in repository | Migration history, ordering, checksums, rollback strategy |
| **Liquibase** | Changelogs and changesets | Labels/contexts, reviews, rollback where supported |
| **SQL Database Projects / DACPAC / SqlPackage** | State-based schema deployment with diff and deployment plan | Drift, schema compare, destructive change reviews |
| **Governed manual T-SQL scripts** | Necessary in certain systems | Approval, idempotency, auditing, and repeatability |
| **Data migration tools** | Moving data from legacy systems | Cutover, consistency, validation, and networking |

**Do not run automatic Hibernate `ddl-auto=update` in production and treat it as a migration strategy.** It undermines code reviews, rollbacks, data governance, and multi-environment consistency.

### Versioned SQL Migrations Pattern

~~~text
db/migration/
  V001__create_customers.sql
  V002__create_orders.sql
  V003__add_order_note.sql
  V004__index_orders_by_created_at.sql
~~~

When Flyway/Liquibase runs under a migration identity, the tool maintains schema history per its capabilities. **The application runtime must not hold ALTER/DROP table rights** just because the pipeline needs DDL.

### Managing Schema Versions in Multi-Tenant Databases

With **database-per-tenant**, a release might need to update hundreds of DBs:

- Use per-database schema version tracking.
- Deploy in waves/rings (canary tenants → small batches → all).
- Cap migration concurrency to avoid vCore/I/O spikes.
- Halt rollout on failure and track which tenant is on which version.
- Support the app running while some databases temporarily remain on the prior version per compatibility policy.

**Do not assume all tenants have migrated just because the pipeline finished the first resource group.**

## 26. Expand-and-Contract for Low-Disruption Deployments

The **expand → migrate/backfill → switch → contract** pattern allows old and new code to run concurrently during rolling updates.

### Step 1: Expand

The app needs an order note field. Instead of dropping or altering an existing column's type, add a nullable column:

~~~sql
ALTER TABLE dbo.Orders
ADD CustomerNote NVARCHAR(500) NULL;
~~~

Old code that does not use the new column continues working. Migrations must be tested against production-like data/volume while checking locking, execution time, and tier capacity.

### Step 2: Deploy Compatible Code

Deploy Java API v2 capable of reading/writing `CustomerNote`, while still handling records with NULL from older code. During rolling updates or multi-region deployments, v1 and v2 may run simultaneously.

### Step 3: Safe Backfill

If populating default values for existing rows, run **in checkpointed batches** while monitoring logs/locks. Never run a massive full-table UPDATE during peak hours without measuring I/O, log generation, and lock duration.

### Step 4: Switch Traffic/Feature

After verifying v2 behavior, enable the feature flag and observe errors/latency. Application v1 can still run or be rolled back until contract-breaking changes occur.

### Step 5: Contract

Only after confirming no consumers remain on the old schema, consider:

- Changing NULL → NOT NULL once data is fully populated.
- Dropping deprecated columns/objects.
- Cleaning up compatibility code and redundant indexes.

**Contract is a breaking-change step and may not be reversible with a simple command.** It requires backups/PITR, review, and an appropriate execution window. In multi-service systems, keep the compatibility window open long enough for every consumer, including batch jobs.

## 27. Executing Data Migration from Legacy SQL Server

If a system already runs on SQL Server on-premises/VM, moving to Azure SQL Database is not just exporting and importing a BACPAC.

### Preflight Questions

1. Are SQL Server features used by the app (Agent, CLR, cross-database queries, linked servers, etc.) compatible with Azure SQL Database?
2. What are the database size, throughput, peak writes, and latency requirements?
3. Is near-zero downtime required, or is a maintenance window available?
4. How much data loss is tolerable during cutover?
5. Will authentication/connection strings switch to Entra/managed identity?
6. What is the network path from the migration worker to source and target?
7. Which migration mechanism fits: bulk copy/BACPAC, Azure Database Migration Service, Data Factory, replication, or supported tools?
8. Who signs off on application-level data correctness after cutover?

### Phases

~~~text
Inventory + compatibility assessment
          |
          v
Target SQL Database sizing/security
          |
          v
Initial schema + data load
          |
          v
Validation: row counts, checksums,
constraints, indexes, sample business workflows
          |
          v
Incremental synchronization (if needed)
          |
          v
Maintenance/cutover with write fencing
          |
          v
Application connection switch + smoke tests
          |
          v
Monitor, rollback window, decommission later
~~~

**BACPAC** is a schema-and-data export/import package suitable for certain scenarios, **not an online HA/DR mechanism or a way to preserve all instance-level state**. For large databases or strict uptime, evaluate a more detailed migration pipeline/cutover.

### Post-Migration Data Verification

- Record counts per table/tenant.
- Primary/foreign keys and unique constraints.
- Decimals, datetimes, collations, and Unicode.
- Indexes, stored procedures, functions, and permissions.
- Business invariants such as order totals/statuses.
- Critical queries and p95 latency.
- No applications still writing to the old source outside of design.

Never delete the source immediately after a matching `SELECT COUNT(*)`. Cutover requires clear ownership and a tested rollback strategy.

## 28. Creating and Inspecting SQL Database in the Azure Portal

With a lab subscription authorized for resource creation and an approved budget:

1. Open [Azure Portal](https://portal.azure.com), select **Azure SQL** or **SQL databases**.
2. Select **Create SQL database**, the right subscription/resource group, and a database name.
3. Choose an existing **logical server** or create a new one. The server name must follow naming rules and be service-wide unique.
4. Select a region matching workload/residency needs.
5. Select **compute + storage tier**, service objective, storage size, and provisioned/serverless (if supported).
6. Configure backup storage redundancy, zone redundancy, and related features per policy/SKU.
7. Choose authentication, preferring Entra ID with proper governance; if using lab SQL auth, manage credentials securely.
8. Under Networking, choose public endpoint/firewall or **Private Endpoint** per topology.
9. Review auditing, Defender/monitoring, and tags.
10. Review estimated pricing/configuration before creating.

**Creating a SQL Database can incur charges immediately upon provisioning**, even without data. If you do not have a lab subscription, practice read-only on an administrator-provided sample database or design on paper.

### Avoiding Common Creation Mistakes

- Do not choose an oversized Business Critical/Hyperscale tier solely because of a GUI default.
- Do not enable **Allow Azure services and resources to access this server** unthinkingly: depending on the mechanism, it can open public access to far more Azure resources than intended.
- Do not record server admin usernames/passwords in shared documents.
- Do not disable public access before the migration runner/application has a working private path.
- Do not use a production database to test DDL changes.
- Do not share secrets or admin identities across dev/staging/prod.

## 29. Azure CLI: Safe Configuration Inspection

The commands below use **Azure CLI in Bash/Azure Cloud Shell**, primarily reading metadata. Replace placeholders with resources you are authorized to access:

~~~bash
az login
az account list --output table
az account set --subscription "<LAB_SUBSCRIPTION_ID>"
az account show --output table

RG="<SQL_RESOURCE_GROUP>"
SERVER="<AZURE_SQL_LOGICAL_SERVER_NAME>"
DB="<DATABASE_NAME>"

az sql server show \
  --resource-group "$RG" \
  --name "$SERVER" \
  --query "{name:name,location:location,publicNetworkAccess:publicNetworkAccess}" \
  --output json

az sql db show \
  --resource-group "$RG" \
  --server "$SERVER" \
  --name "$DB" \
  --query "{name:name,status:status,sku:sku.name,tier:sku.tier,capacity:sku.capacity,zoneRedundant:zoneRedundant}" \
  --output json
~~~

List databases on a logical server:

~~~bash
az sql db list \
  --resource-group "$RG" \
  --server "$SERVER" \
  --query "[].{name:name,status:status,sku:sku.name}" \
  --output table
~~~

Inspect firewall rules:

~~~bash
az sql server firewall-rule list \
  --resource-group "$RG" \
  --server "$SERVER" \
  --output table
~~~

These **show/list** commands do not prove a Java client can connect or a user has SELECT rights. Nor do they replace testing Private Endpoint, DNS, Entra tokens, and SQL permissions.

### Do Not Modify Shared Server Configurations for Practice

Commands like `az sql db create/update/delete`, `az sql server firewall-rule create`, changing `public-network-access`, or triggering failover can incur costs or cause outages. Before executing, you must:

1. Verify resource names, subscription, and environment.
2. Read `az sql db create --help` and check regional compatibility of the service objective.
3. Have approval, budget, and a rollback plan.
4. Test in a lab first.

Example **database creation command** in a lab on an existing logical server:

~~~bash
az sql db create \
  --resource-group "$RG" \
  --server "$SERVER" \
  --name "orders-sandbox" \
  --service-objective "S0"
~~~

The command uses **S0**, a traditional Standard DTU service objective, to illustrate the CLI. Availability, quotas, and pricing must be verified beforehand; **do not treat S0 as a default recommendation for production apps**. If the exercise targets vCore/GP/BC/Hyperscale, choose the SKU via the Portal or CLI parameters verified for the actual region/tier.

## 30. Connecting and Running T-SQL in the Lab

Once you have a test database and an authorized principal, use SSMS, VS Code/appropriate SQL tooling, JDBC, or **sqlcmd** supporting your authentication method.

### Read-Only Verification

~~~sql
SELECT
    DB_NAME() AS DatabaseName,
    SUSER_SNAME() AS CurrentLogin,
    ORIGINAL_LOGIN() AS OriginalLogin,
    SYSUTCDATETIME() AS CheckedAtUtc;
~~~

Check the service objective in the database context via the DMV schema your account is permitted to view:

~~~sql
SELECT
    edition,
    service_objective,
    elastic_pool_name
FROM sys.database_service_objectives;
~~~

Depending on role/engine compatibility, some metadata/DMVs require specific permissions or have differing column names across versions. When a query fails, verify schema documentation and permissions instead of immediately granting `db_owner`.

### Querying Recent Resource Usage

Azure SQL Database provides DMVs/resource statistics like **sys.dm_db_resource_stats** to observe CPU, I/O, and worker/resource usage per service capabilities:

~~~sql
SELECT TOP (20)
    end_time,
    avg_cpu_percent,
    avg_data_io_percent,
    avg_log_write_percent
FROM sys.dm_db_resource_stats
ORDER BY end_time DESC;
~~~

The numbers represent **percentages relative to the tier/database resource limits** per metric, not percentages of an entire physical machine. Check timeframes, available data, and combine with Azure Monitor metrics for a complete picture.

### Analyzing Slow Queries

- Enable/inspect **Query Store** per service configuration and retention.
- Review top queries by duration, CPU, logical reads, and regressions.
- Inspect actual/estimated execution plans in an authorized environment.
- Check parameter sniffing, statistics, blocking, and missing/unused indexes.
- Assess query impact on other tenants.

Do not blindly create indexes for every "missing index" suggestion without measuring write overhead, index overlap, and workload.

## 31. Health Monitoring and Performance Optimization

A production database needs monitoring for both **SQL-level** and **application-level** signals.

| Group | Signal | Question to Answer |
|---|---|---|
| Compute | CPU %, DTU/vCore utilization | Is the DB saturating compute? |
| I/O | Data IO %, log write %, storage latency | Are queries or log writes bottlenecked? |
| Storage | Data size, allocated space, growth | When will quota be hit, is retention needed? |
| Concurrency | Sessions, workers, blocking, deadlocks | Is app scaling creating too many connections? |
| Queries | Query Store duration, CPU, plan regressions | Which schema/code release caused slowdowns? |
| Application | Connection pool, p95/p99 DB calls, retry count | How are users affected? |
| DR | Replica lag, failover state, backup status | Are RPO/RTO targets met? |
| Security | Login failures, audit anomalies, access changes | Are credentials/permissions being abused? |
| Cost | Compute, storage, backups, networking | Is the DB right-sized for cost? |

### Actionable Alerting

Examples:

- CPU or data I/O near thresholds for several minutes **and** p95 latency rises.
- Free storage/allocated capacity approaching limits.
- Sudden spike in deadlock rate or error retries.
- Replication lag exceeds target RPO.
- Zero successful connections or business transactions over an unusual window.

**Do not alert solely on `CPU > 70%`** without knowing the recipient, response runbook, and application impact. In serverless, CPU/resume patterns differ from provisioned; thresholds should reflect compute type.

### Performance Tuning Before Scale-Up

1. Identify slow SQL statements and execution plans.
2. Check indexes, TenantId filters, statistics, and pagination.
3. Reduce N+1 queries or excessive round trips.
4. Check transaction duration, lock contention, and DB connection pools.
5. Optimize queries before adding vCores when the bottleneck is in design.
6. If the issue is genuinely capacity, change tier/vCores or partition workloads to fit the problem.

**Scaling up a database may not fix deadlocks or a table-scan query missing a tenant filter.** After changing the service objective, re-measure latency, throughput, and cost.

## 32. Cost Management for Azure SQL Database

SQL PaaS cost is more than just the database count.

| Component | Potential Cost Drivers |
|---|---|
| **Compute** | DTU/vCore, provisioned or serverless usage per tier |
| **Storage** | Database data storage, allocated/provisioned space |
| **Backups** | PITR exceeding allowance, LTR, redundancy per pricing model |
| **Replicas** | Geo-secondary/read replicas, service tier, and region |
| **Network** | Private Endpoint, DNS resolver, NAT, egress, data transfer |
| **Monitoring/security** | Azure Monitor logs, auditing storage, Defender plans |
| **App/CI** | AKS/App Service/Functions, migration runners |
| **License savings** | Azure Hybrid Benefit/reserved capacity where eligible |

Never lock in a fixed price without knowing the **region, tier, vCore/DTU, storage, compute model, and uptime**. Use Azure Pricing Calculator, Cost Management, Azure Advisor, and resource usage dashboards.

### Cost-Based Decision Examples

Three dev/test databases are usually idle from 20:00–08:00. Serverless auto-pause **can save money** if they actually meet pause conditions, but background jobs/health probes may prevent pausing. Do not assume 50% compute savings without measuring auto-pause status and billing.

An elastic pool can reduce costs for 100 mostly idle tenant databases, but if all tenants run reports at 9:00 simultaneously, the pool will need large capacity or scheduling/isolation controls.

### Tags, Budgets, and Cleanup

- Apply **environment**, **owner**, **application**, and **costCenter** tags per policy.
- Set budget alerts at the resource group/subscription level.
- Review tiers monthly; change tiers deliberately and performance test.
- Delete unneeded lab databases after exporting/backing up data per policy.
- **Never delete a shared logical server/resource group** just to finish a practice exercise.

**A budget alert does not stop billing automatically.** A provisioned DB continues incurring charges even with zero requests.

## 33. Common Errors and Diagnostic Approach

| Symptom | Possible Cause | Diagnostic Step |
|---|---|---|
| Client timeout, cannot connect to SQL | DNS, Private Endpoint, firewall, route/proxy, SQL unavailable | DNS from app VNet, network policy, SQL health |
| Login failed / 18456 | Wrong principal/token/password, DB user not created | Entra principal, DB user, auth configuration |
| **Cannot open server** due to firewall | Public endpoint missing allowed IP or public network disabled | Firewall rules, actual egress, private DNS |
| **403** from Key Vault when fetching DB connection secret | Wrong identity/Key Vault RBAC/network | Managed identity, vault logs, reference status |
| **40613/40197** or transient disconnections | DB/service unavailable/failover, transient faults | Azure status, retry/backoff, failover events |
| **40501** or resource limit errors | Service busy/compute limits hit | Metrics, concurrency, service objective |
| **1205 deadlock** | Transactions updating resources in conflicting order | Deadlock graphs, transaction design, bounded retries |
| **2627/2601** duplicate key | Unique/idempotency conflict | Unique constraints, external request ID, client behavior |
| **547** foreign key conflict | Data violates referential integrity | FK design, transaction ordering |
| **Query timeout** | Slow query, blocking, network, or low threshold | Query Store, execution plan, pool timeout |
| High CPU with low requests | Query scans, background batches, missing indexes | Query Store, DMVs, regressions |
| Elastic pool slow at peak hours | Multiple DBs competing for shared resources | Pool metrics, split workload, min/max limits |
| Geo-secondary reads missing recent data | Async replication lag | Read routing, lag metrics, consistency expectations |
| Function/AKS scale-out overloads DB | Connection pools multiplying with instances | Max pool sizes, worker/session limits |
| Migrations hang | DDL locks, large table scans, long transactions | Blocking sessions, batch plan, maintenance |
| App still fails after restore | Different DNS/identity/config/DB name | Connection string, SQL user, schema, permissions |

Do not use the **SQL admin account** to work around every login or firewall error. Separate issues along **network → authentication → authorization → query/runtime** using targeted checks.

## 34. Scenario A: Java API Fails to Connect After Disabling Public Access

**Context:** Orders API on App Service runs normally over the SQL public endpoint. The security team disables public network access after creating a Private Endpoint. Immediately afterward, the API returns 500 errors and JDBC timeouts.

### Analysis

Having a Private Endpoint does not mean App Service is routing through it. App Service may lack VNet Integration, have incorrect subnet/DNS settings, or still route egress to the public endpoint.

### Runbook

1. Identify affected app instances/region and time of change.
2. Inspect App Service VNet Integration/AKS VNet, routing, and DNS resolver.
3. Resolve **<SERVER>.database.windows.net** from inside the workload's actual network.
4. Verify private IP/Private DNS zone link, NSGs, and connection policy.
5. Check managed identity/SQL user once network connectivity is confirmed.
6. Test connectivity using the workload's identity and target database, not an admin from a laptop.
7. Restore network configuration per change record if the outage persists; do not blindly enable Allow all Azure services.
8. Document the RCA and add positive/negative connectivity tests to infrastructure CI/CD.

### Lesson Learned

Before locking down public networks, verify connectivity from **the app, CI migration runner, monitoring, and DR location**. Private Endpoint is one piece of the architecture, not a complete network migration by itself.

## 35. Scenario B: Java Scale-Out Saturates the Elastic Pool

**Context:** A SaaS app has 50 tenants in an elastic pool. During a batch invoice run, 20 AKS pods scale to 60 pods while DB CPU/log I/O hits limits; many requests time out.

### Diagnosis

1. Inspect **pool-level and per-database metrics** to pinpoint the load-generating tenant.
2. Calculate potential connections: **60 pods × pool size**.
3. Check Query Store top consumers/lock waits and batch schedules.
4. Check whether retries are triggering a retry storm and amplifying load.
5. Inspect HPA/app scaling: adding more pods can worsen a database bottleneck.

### Remediation

- Cap concurrency and pool sizes appropriately.
- Batch work in bounded sizes, avoiding long transactions.
- Optimize queries/indexes and implement retries with jitter.
- Move heavy reporting out of peak hours, or isolate large tenant databases.
- Increase pool capacity only when measurements prove it is needed.
- Set workload-aware alerts for CPU, log write %, latency, and timeouts.

**Do not reflexively increase vCores/replicas.** If the code issues N+1 queries or holds long locks, failures can continue even on higher tiers.

## 36. Scenario C: Migration Dropping a Column Breaks the Old API

**Context:** Pipeline v2 drops column **LegacyCode** before AKS v1 pods finish their rolling update. Requests served by older pods fail because their SQL queries still reference that column.

### Root Cause

Migrations ran **contract-before-expand** without accounting for v1/v2 application coexistence. Rolling back code to v1 may also fail because the column is already gone.

### Runbook

1. Halt rollout to prevent further data changes if possible and assess impact.
2. Use a compatible migration or hotfix to restore the data contract per verified design; avoid guessing the old column's type/structure.
3. If data was lost, evaluate PITR restore to a separate DB and a reconciliation plan.
4. Audit all consumers: API pods, background jobs, reporting, Functions, and queues.
5. Re-run smoke/business tests before reopening full traffic.
6. Refactor the pipeline to follow **expand → deploy compatible code → backfill → contract** across separate releases.

**Restoring schema does not restore data from a dropped column.** Certain incidents require backup restore/data recovery rather than just `CREATE/ALTER TABLE`.

## 37. Scenario D: Regional Failover and Risk of Lost Transactions

**Context:** Primary Azure SQL in Region A experiences an outage. Secondary Region B is online with replication lag. Operations plans to promote B immediately to restore the Orders API.

### Coordination Procedure

1. Confirm the outage and assess app/DB/geo-replication status.
2. Evaluate **realistic RPO** and potentially un-replicated transactions.
3. If possible, fence off old writes and control how the old primary returns to prevent two conflicting write endpoints.
4. Execute failover per approved configuration/authorization.
5. Verify listener DNS, Private Endpoint, SQL auth/permissions, and app connections in B.
6. Run non-destructive smoke tests; reconcile orders/payments/message backlogs.
7. Alert business stakeholders if orders near the outage timestamp may be missing.
8. Plan controlled failback after A recovers.

**RPO=0 is not guaranteed with async geo-replication.** Transactions acknowledged to clients but not yet replicated may require reconciliation from event logs/outboxes/payment processors if the platform is designed for it.

## 38. Safe Hands-On Exercise: Designing Azure SQL for Orders API

### Context

A SaaS Java API running on AKS/App Service has:

- 40 tenants, ranging from hundreds to millions of orders each.
- Two large tenants generating 60% of traffic.
- Order creation transactions requiring consistency and idempotency keys.
- Production in Region A, requiring a DR plan in Region B.
- SQL access restricted to the app network/private migration runner.
- Dev/staging/prod environments; no real sensitive data used in the lab.

### Part A: Model Selection

Compare three options:

1. One **shared database + TenantId + RLS**.
2. **Database per tenant + elastic pool**.
3. Hybrid model: large tenants on dedicated DBs, small tenants in a pool.

Build a table:

| Criterion | Shared DB | DB per Tenant/Pool | Hybrid |
|---|---|---|---|
| Cost at small scale | Often favorable | More DBs to manage | Flexible |
| Per-tenant restore isolation | Harder | Easier on dedicated DBs | Per tenant |
| Performance isolation | Noisy-neighbor risk | Pool still has contention | Can dedicate compute |
| Schema migrations | One DB | Dozens of DBs | Two lifecycles |
| Authorization | TenantId/RLS critical | DB principal/routing | Both |
| Scaling large tenants | Can create hot spots | Can move individually | Easy to isolate |
| Operational complexity | Lower initially | Grows with DB count | Highest |

Choose one option and justify it using SLO, RPO/RTO, scale, residency, and operational capability. Do not pick a solution based solely on tier names.

### Part B: Metadata Inspection (Read-Only)

If provided a lab Azure SQL logical server/database:

~~~bash
az login
az account set --subscription "<LAB_SUBSCRIPTION_ID>"

RG="<LAB_RESOURCE_GROUP>"
SERVER="<LAB_SQL_SERVER>"
DB="<LAB_SQL_DATABASE>"

az sql server show \
  --resource-group "$RG" \
  --name "$SERVER" \
  --query "{name:name,location:location,publicNetworkAccess:publicNetworkAccess}" \
  --output json

az sql db show \
  --resource-group "$RG" \
  --server "$SERVER" \
  --name "$DB" \
  --query "{name:name,sku:sku.name,status:status,zoneRedundant:zoneRedundant}" \
  --output json
~~~

Do not create a new DB or open firewall rules if you only hold Reader rights. Record **service tier, compute, network mode, backup policy, and identity approach** based on visible metadata.

### Part C: SQL Schema in an Isolated Sandbox Database

If the DBA permits object creation in a sandbox:

1. Create **Customers**, **Orders**, and the index from Section 11.
2. Insert at least two tenants with synthetic data.
3. Test FK/unique constraints: an order cannot reference another tenant's customer.
4. Verify duplicate `ExternalOrderId` within the same tenant is blocked by the unique constraint.
5. Run the query from Section 12 with a specified `TenantId` parameter.
6. Compare execution plans before/after adding the index if data volume suffices to observe a difference.
7. Simulate optimistic concurrency using `RowVer` with two clients.

**Never run DDL on production**, and never store real emails/PII in exercises.

### Part D: Java Connectivity Design

Write a JDBC configuration using:

- Logical server FQDN.
- Environment-appropriate database name.
- TLS with certificate validation.
- Managed identity/Entra authentication where supported by runtime/driver.
- A SQL user with only required permissions.
- Connection pool bounded relative to replica count.

Verify the Private Endpoint/Private DNS architecture on paper if no lab network path exists. Never hard-code admin passwords in `application.properties` and commit them.

### Part E: Simulating Schema v2 Deployment

1. Add nullable `CustomerNote` via a versioned migration.
2. Verify v1 code still reads data normally.
3. Deploy v2 understanding the new column and run integration tests.
4. Backfill in batches if required.
5. Contract only in a later release after all consumers have transitioned.
6. Write a rollback plan in case the migration corrupts data.

### Part F: HA/DR Plan

Define illustrative business RTO/RPO targets and choose:

- Zone redundancy in Region A if supported by tier/region.
- PITR retention/LTR per requirements.
- Failover group or geo-restore for Region B matching RTO/RPO.
- App/network/Entra/private DNS/CI runner in B.
- Reconciliation workflow for potentially un-replicated transactions.

**Never simulate incidents by failing over production or deleting real DBs.** Use tabletop exercises/runbooks and sandbox restores when approved.

### Evidence Submission Table

| Item | Evidence |
|---|---|
| Azure SQL selection | Logical server, single DB/elastic pool, tier, and compute model |
| Data model | DDL, PK/FK/unique/check, indexes, and rationale |
| Multi-tenancy | Shared vs. DB-per-tenant vs. hybrid decision |
| Java | JDBC auth/TLS, connection pool, and least privilege |
| Networking | Public firewall or Private Endpoint/DNS |
| Schema migration | Expand-contract plan, versioning, and negative tests |
| Resilience | HA/zone, PITR, geo-DR, RTO/RPO |
| Observability | Queries, CPU/I/O/latency/connection metrics |
| Cost | Tier/storage/backup/replica estimates and cleanup |
| Security | No real secrets/data in documentation |

## 39. Production Deployment Checklist

- [ ] Azure SQL Database chosen after evaluating MI/SQL Server VM and compatibility.
- [ ] Logical server, region, resource group, and data residency clearly defined.
- [ ] Single DB/elastic pool/tenant model justified by capacity, isolation, and cost.
- [ ] DTU/vCore, GP/BC/Hyperscale, provisioned/serverless selected from measured workload.
- [ ] Schema has PK/FK/unique/check constraints, indexes, and appropriate retention policy.
- [ ] Tenant authorization/RLS/pooling tested across multiple users/tenants.
- [ ] T-SQL uses parameterized queries and proper transaction/optimistic concurrency handling.
- [ ] Java JDBC uses TLS, secure authentication, and bounded pool sizes.
- [ ] SQL users/managed identities follow least privilege; migration identity separated from runtime.
- [ ] Public firewall/Private Endpoint/DNS tested from app, runner, and DR region.
- [ ] TDE/auditing/defender/key policies meet data requirements.
- [ ] Query Store, Azure Monitor/alerts, and logging do not expose secrets.
- [ ] Appropriate PITR/LTR configured and restore drilled into an isolated DB.
- [ ] HA/zone redundancy verified per SKU/region.
- [ ] Geo-DR/failover group has RTO/RPO scenarios and standby app/network readiness.
- [ ] Migrations are versioned, using expand-contract and compatibility tests.
- [ ] Multi-DB/tenant migrations use canary/ring rollouts and tracking.
- [ ] Runbooks exist for transient errors, deadlocks, throttling, and schema failures.
- [ ] Cost Management/budgets/tags and regular tier review processes established.
- [ ] Load testing, DR tabletop, and negative access testing completed.

## 40. Self-Check Questions

1. How does Azure SQL Database differ from Managed Instance and SQL Server VM in operational responsibility?
2. Is a logical server a VM containing the databases?
3. Why doesn't Azure RBAC Contributor automatically grant SQL SELECT permissions?
4. When is a single database better than an elastic pool?
5. How does an elastic pool isolate tenant data and CPU?
6. How do DTU and vCore differ in sizing and billing?
7. What distinct needs do General Purpose, Business Critical, and Hyperscale address?
8. When does serverless auto-pause fail to trigger and potentially become disadvantageous?
9. What risks does a shared database/shared schema carry if a TenantId filter is omitted?
10. What are the pros and cons of database-per-tenant with 1,000 tenants?
11. What kind of data error does a composite FK `(TenantId, CustomerId)` prevent?
12. Why does `UNIQUE (TenantId, ExternalOrderId)` support idempotency?
13. How does `rowversion` differ from a timestamp and where is it used?
14. Does RLS authenticate JWTs/tenants on its own? What risks does connection pooling introduce?
15. How does sharding increase query and transaction complexity?
16. Why should Java runtime identity and database migration identity be separate?
17. If Private Endpoint exists but the app cannot connect, which layers must be checked?
18. How do TLS, TDE, and Always Encrypted protect against different threats?
19. How does zone redundancy differ from geo-replication and PITR backups?
20. Which transactions might a geo-secondary lose after a region outage?
21. What does a failover group DNS listener help with, and what does it not solve?
22. Does restoring a PITR database automatically recover valid writes after the restore timestamp?
23. Why is expand-and-contract schema migration safer than a direct DROP?
24. How do Flyway/Liquibase differ from the DACPAC approach to schema management?
25. What must a 500-database SaaS do to control schema rollouts?
26. What issues do Query Store and `sys.dm_db_resource_stats` help diagnose?
27. When AKS HPA increases replicas, how can database connections grow?
28. Why isn't high CPU always fixed by adding vCores?
29. Does having an existing backup mean a DR plan meets RTO/RPO?
30. When picking the cheapest tier, what SLO and cost risks must be considered?

## 41. References

- [Azure SQL Database overview](https://learn.microsoft.com/azure/azure-sql/database/sql-database-paas-overview) — PaaS nature and Azure SQL models.
- [Choose between Azure SQL products](https://learn.microsoft.com/azure/azure-sql/azure-sql-iaas-vs-paas-what-is-overview) — SQL Database, Managed Instance, SQL Server VM.
- [Azure SQL Database purchasing models](https://learn.microsoft.com/azure/azure-sql/database/purchasing-models) — DTU and vCore.
- [Service tiers in the vCore model](https://learn.microsoft.com/azure/azure-sql/database/service-tiers-sql-database-vcore) — General Purpose, Business Critical, Hyperscale.
- [Azure SQL Database serverless](https://learn.microsoft.com/azure/azure-sql/database/serverless-tier-overview) — auto-scaling, auto-pause, and limits.
- [Elastic pools](https://learn.microsoft.com/azure/azure-sql/database/elastic-pool-overview) — sharing compute across databases.
- [Multi-tenant SaaS tenancy patterns](https://learn.microsoft.com/azure/azure-sql/database/saas-tenancy-app-design-patterns) — shared DB, DB per tenant, and sharding.
- [Connect and query Azure SQL Database](https://learn.microsoft.com/azure/azure-sql/database/connect-query-content-reference-guide) — tools and connectivity.
- [Microsoft Entra authentication to Azure SQL](https://learn.microsoft.com/azure/azure-sql/database/authentication-aad-overview) — identities and SQL users.
- [Private Link for Azure SQL](https://learn.microsoft.com/azure/azure-sql/database/private-endpoint-overview) — Private Endpoint/DNS.
- [SQL Database security overview](https://learn.microsoft.com/azure/azure-sql/database/security-overview) — firewall, encryption, auditing, and data protection.
- [Automated backups in Azure SQL Database](https://learn.microsoft.com/azure/azure-sql/database/automated-backups-overview) — PITR/LTR and retention.
- [Active geo-replication for Azure SQL Database](https://learn.microsoft.com/azure/azure-sql/database/active-geo-replication-overview) — asynchronous secondary.
- [Failover groups for Azure SQL Database](https://learn.microsoft.com/azure/azure-sql/database/failover-group-sql-db) — geo-failover and listeners.
- [Query Store](https://learn.microsoft.com/sql/relational-databases/performance/monitoring-performance-by-using-the-query-store) — query tuning and regressions.
- [Microsoft JDBC Driver for SQL Server](https://learn.microsoft.com/sql/connect/jdbc/microsoft-jdbc-driver-for-sql-server) — Java JDBC/TLS/authentication.
- [Azure SQL database migration guidance](https://learn.microsoft.com/azure/azure-sql/migration-guides/database/sql-server-to-sql-database-overview) — assessment and migration.
- [Azure CLI: az sql db](https://learn.microsoft.com/cli/azure/sql/db) — creating, viewing, and configuring databases.
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) — cost estimation.

**Conclusion:** Azure SQL Database reduces SQL Server infrastructure operations, yet a safe data architecture still demands deliberate decisions on **single database vs. elastic pool, tenant and schema models, DTU/vCore and service tiers, network and identity security, backup/HA/DR, migrations, and query performance**. Design data around transactions and ownership, deploy schemas with versioning and backward compatibility, test restores and failovers, monitor from SQL up to the Java application, and tune costs using real metrics rather than guesswork.