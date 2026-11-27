# Azure Database for MySQL Flexible Server

## 1. Why Choose Managed MySQL on Azure?

Java applications can run on Azure App Service, Azure Functions, Azure Kubernetes Service (AKS), or VMs. Applications storing orders, accounts, inventory, and transactions typically need a relational database providing **SQL, transactions, indexes, and data constraints**.

There are two approaches to running MySQL:

- **Self-installing MySQL on Azure VM:** the operations team manages the OS, MySQL process, backups, patches, replication, HA, and monitoring.
- **Azure Database for MySQL Flexible Server:** Azure provides a managed MySQL service; the application team focuses on schemas, queries, permissions, connectivity, performance, backup/restore policies, and business recoverability.

This lesson belongs to the **Relational Databases** chapter of the module exploring the Microsoft Azure ecosystem, connecting subscriptions, resource groups, Microsoft Entra ID, virtual networks, compute services, security, monitoring, and cost into a MySQL-backed application architecture.

**Managed MySQL does not mean the application can skip database design.** A query missing an index can still be slow, a flawed transaction can still corrupt data, and an unencrypted connection still creates security risk.

### End-to-End Scenario

Suppose an e-commerce system includes:

- **orders-api**: a Java API writing and looking up orders.
- **catalog-api**: serving product details.
- **orders-worker**: processing events from Azure Service Bus.
- **Azure Database for MySQL Flexible Server**: storing orders, products, and relational data.
- **Azure Monitor**: tracking performance and incidents.
- **Azure Key Vault/identity**: managing credentials or supported authentication methods.

The objective is choosing the right MySQL configuration, not merely provisioning a server.

## 2. Learning Objectives

After this lesson, you will be able to:

1. Explain Azure Database for MySQL Flexible Server and customer responsibilities.
2. Compare Flexible Server with Azure SQL, managed PostgreSQL, and self-managed MySQL.
3. Select compute tier, vCores, memory, storage, and IOPS.
4. Distinguish same-zone/zone-redundant HA, PITR, and read replicas.
5. Design backups, RPO/RTO, and recovery drills.
6. Choose public firewalls or private networking and configure DNS properly.
7. Use TLS and distinguish Azure RBAC from MySQL authentication/authorization.
8. Design least-privilege MySQL permissions and Java JDBC/HikariCP connectivity.
9. Create schemas, transactions, indexes, and analyze `EXPLAIN`.
10. Monitor performance, connections, slow queries, and storage.
11. Plan maintenance, upgrades, migrations, and DR.
12. Complete a cost-bounded lab and safe cleanup procedure.

## 3. Flexible Server Architecture

Flexible Server is an **Azure resource** providing a MySQL database endpoint with Azure-managed compute and storage. Users configure engine version, compute tier, storage, networking, authentication, and backup/HA options.

~~~mermaid
flowchart TB
    APP[Java API on AKS / App Service] --> NET[VNet / Firewall / Private DNS / TLS]
    NET --> DNS[MySQL Flexible Server FQDN]
    subgraph FLEX[Managed MySQL Flexible Server]
        P[(Primary MySQL)]
        DISK[(Managed storage)]
        HA[(Optional HA standby)]
        BK[(Automated backup / PITR)]
        P --> DISK
        P -. HA replication .-> HA
        P --> BK
    end
    DNS --> P
    P -. Async read replication .-> REP[(Optional read replica)]
    REPORT[Reporting worker] --> REP
    MON[Azure Monitor] --- FLEX
~~~

This diagram illustrates only logical components. HA standby and read replicas differ in purpose, access, and replication model.

### 3.1. Resource and SQL Databases

Example:

~~~text
Resource group: rg-shop-prod
└── MySQL Flexible Server: mysql-shop-prod
    ├── database: shopdb
    ├── database: reportingdb
    └── MySQL users / privileges
~~~

A server can host multiple databases; schema names, permissions, and resource consumption must still be governed clearly.

### 3.2. No OS Root Access

You cannot SSH into the database host to edit arbitrary MySQL files or manage the OS as with MySQL on a VM. Permitted server parameters are adjusted through the managed service; other underlying boundaries remain Azure's responsibility.

## 4. Shared Responsibility

| Component | Primarily Managed by Azure | Managed by Application Team |
|---|---|---|
| Host infrastructure | Provisioning, OS/service infrastructure | Region, SKU, scaling |
| Database runtime | Service-managed patching/maintenance | Version compatibility, upgrade validation |
| Storage | Storage platform | Capacity, IOPS, schemas/indexes |
| HA | HA feature per configuration | HA mode, app reconnect, failover testing |
| Backup | Automated backups per policy | Retention, PITR drills, RPO/RTO |
| Networking | Azure network integration | Firewalls, VNet, DNS, TLS |
| Identity | Supported auth features | Users/grants, secrets/tokens, least privilege |
| SQL/data | MySQL engine | Schemas, migrations, transactions, indexes |
| Monitoring | Metrics/logging interfaces | Alerting, on-call, query tuning |
| Cost | Billing/metering | Resource sizing, budgets, and optimization |

**Azure RBAC managing the server resource does not automatically grant SELECT/INSERT inside MySQL.**

## 5. When to Choose Flexible Server Over Other Services?

| Service | Suitable Scenario | Notes |
|---|---|---|
| **Azure Database for MySQL Flexible Server** | Apps requiring MySQL and wanting a managed service | Managed MySQL feature/parameter limits |
| **Azure Database for PostgreSQL Flexible Server** | PostgreSQL ecosystem, extensions, and data model | SQL dialect/drivers are not drop-in replacements for MySQL |
| **Azure SQL Database** | Apps suited for SQL Server/T-SQL | Engine/auth/queries differ from MySQL |
| **MySQL on Azure VM** | Need full OS/database control or managed-unsupported configs | Self-manage HA, backups, patching, and DR |
| **NoSQL database** | Document/key-value models and matching access patterns | Does not directly replace relational constraints/joins |

If an app already uses MySQL with stored procedures, triggers, and engine-specific features, perform a compatibility assessment before switching platforms.

## 6. Choices When Creating a Server

A Flexible Server requires evaluating simultaneously:

1. Subscription and resource group.
2. Region and data residency.
3. Supported MySQL engine version.
4. Compute tier and VM/SKU.
5. vCores and memory.
6. Storage size, storage growth, IOPS.
7. HA mode if needed.
8. Backup retention and geo options where supported.
9. Networking mode, firewall/VNet/private DNS.
10. Authentication, SQL administrator, and app runtime users.
11. Maintenance window and monitoring.
12. Budgets, tags, and backup/cleanup workflows.

**Do not copy dev/lab configs to production** when SLOs, data, and compliance differ.

## 7. Compute Tiers: Burstable, General Purpose, Memory Optimized

| Tier | Characteristics | Best Suited For |
|---|---|---|
| **Burstable** | Compute capable of bursting per SKU profile, suited for low/variable load | Labs, dev/test, and measured small workloads |
| **General Purpose** | Balanced compute and memory | CRUD APIs, enterprise apps |
| **Memory Optimized** | More RAM per vCore per SKU family | Large working sets, cache/read-heavy workloads |

SKU names, vCore ranges, HA availability, quotas, and pricing vary by region, version, and time. Never rely on hard-coded numbers from an outdated price sheet.

### 7.1. When Not to Use Burstable

- Consistently high CPU usage.
- Long batch jobs or large reports.
- Production latency highly sensitive to CPU starvation.
- HA/capacity features unavailable on the chosen SKU.

### 7.2. When Is Memory Optimized Worth the Cost?

When the frequently read working set is large enough that a bigger InnoDB buffer pool meaningfully cuts disk reads. If queries scan tables due to missing indexes or lock contention, more RAM is rarely the optimal fix.

## 8. Sizing vCores and Memory by Measurement

Factors to investigate:

- Peak queries/second and concurrent transactions.
- Read/write ratio.
- CPU, memory, active connections.
- Query p95/p99 and slow query samples.
- InnoDB buffer pool and disk reads.
- Batch jobs, reporting, and maintenance windows.
- Data growth over 3–12 months.
- Scaling/restart impact and SLOs.

For example, `orders-api` peaks at 300 HTTP requests/second. You cannot deduce MySQL vCores directly from that, because one request might run 1 indexed SELECT or 30 unindexed queries.

**Benchmark with a workload/dataset close to production** before finalizing configurations.

## 9. Storage, IOPS, Throughput, and Autogrow

| Metric | Role | Bottleneck Signal |
|---|---|---|
| Provisioned storage | Space for data and related components | Capacity nearing full |
| IOPS | Read/write operations per second | Many queries waiting on I/O |
| Throughput | Data read/written per second | Slow full scans/batch I/O |
| Read/write latency | Storage operation latency | Prolonged transactions |
| Autogrow | Auto-expands storage per supported feature | Helps avoid running out of capacity at thresholds |

### 9.1. Autogrow Does Not Replace Capacity Planning

Forecast capacity, monitor growth, and track costs. **Do not assume provisioned storage can be shrunk directly after deleting rows**; many configurations only scale up, requiring migration/creating a new server to shrink provisioned size.

### 9.2. Optimize Before Increasing IOPS

If `SELECT` scans full tables instead of using indexes, raising IOPS burns money without fixing the root cause. Inspect `EXPLAIN`, schemas, and the buffer pool.

## 10. High Availability in Flexible Server

Flexible Server provides HA options depending on supported features/regions/SKUs:

- **Same-zone HA:** primary and standby placed within one Availability Zone per model.
- **Zone-redundant HA:** primary/standby placed in separate Availability Zones within the same region where available.

~~~mermaid
flowchart LR
    API[Java app] --> DNS[MySQL FQDN]
    subgraph REGION[Azure region]
        subgraph ZONEA[Zone A]
            P[(Primary)]
        end
        subgraph ZONEB[Zone B]
            S[(HA standby)]
        end
        P -. Managed HA replication .-> S
    end
    DNS --> P
    S -. Failover .-> DNS
~~~

### 10.1. Can the Standby Serve Reads?

**An HA standby is not a read replica for reporting.** Its primary purpose is resilience when the primary or underlying infrastructure fails.

### 10.2. Failover Does Not Mean Zero Downtime

Connections can drop and in-flight transactions can fail, requiring retries/reconnects and commit-status verification. Always use the DNS endpoint rather than hard-coding IPs.

### 10.3. HA Does Not Undo Accidental Deletes

If a valid SQL statement mistakenly deletes orders, the wrong state replicates to both primary and standby. PITR or another backup mechanism is required to recover historical data.

## 11. Automated Backups and Point-in-Time Restore

Flexible Server provides automated backups and **Point-in-Time Restore (PITR)** according to supported retention/settings.

Key concepts:

- **Retention:** historical window eligible for recovery per service limits.
- **PITR:** choosing a timestamp prior to an error to reconstruct that data state.
- **Restore target:** PITR typically creates **a new server** rather than overwriting the live server in place.
- **Geo-redundant backup/restore:** varies by region/tier/configuration; check eligibility and cross-region recovery capabilities.

Example:

~~~text
09:00:00 Data normal
09:20:00 Faulty batch UPDATE runs
09:21:00 Issue detected
09:23:00 Stop job and avoid new writes complicating recovery
09:30:00 Restore to a new server before 09:20
         Verify data, then decide whether to cut over or extract records
~~~

**Never blindly point the app to the restored server simply because it finished provisioning.** Verify schemas, data, users, networking, DNS, and transactions occurring after the restore timestamp.

## 12. RPO and RTO: Write Targets Before Enabling Features

- **RPO**: maximum acceptable time-measured data loss.
- **RTO**: maximum acceptable time to restore service.

Suppose an app requires a 15-minute RPO and 60-minute RTO. Merely enabling backups does not prove you meet those targets, since restoring requires provisioning/copying time, data validation, and cutover.

### 12.1. PITR Runbook

1. Who is authorized to declare an incident?
2. How are writes halted or fenced?
3. Which logs identify the exact restore timestamp?
4. Where is the restored server placed?
5. Are MySQL users/permissions and networking configured properly?
6. How are row counts, transactions, and business invariants verified?
7. How is the application updated to point to the new endpoint?
8. Is there a rollback if cutover fails validation?
9. Who signs off on data integrity and closes the incident?

**A backup that has never been restore-tested is insufficient proof of recoverability.**

## 13. How HA, Read Replicas, Backups, and DR Differ

| Mechanism | Objective | Does Not Replace |
|---|---|---|
| HA | Survive certain instance/zone faults within a region | Historical backups |
| PITR | Recover data to a specific point in time | Instant auto-failover |
| Read replica | Scale SELECT capacity, some DR scenarios | Backups, default automated HA |
| Geo-restore/DR topology | Recover from regional disasters | RPO=0 or fully automatic operation |
| App-level export/backup | Store data for custom requirements | Transaction consistency if misconfigured |

Critical systems usually combine HA + tested backup/restore + a DR plan aligned with RPO/RTO.

## 14. Read Replicas for Read Scaling

A read replica is a secondary server receiving replicated data from the primary—typically **asynchronously**—to serve read queries that tolerate lag.

~~~mermaid
flowchart LR
    API[Orders API] --> PRIMARY[(Primary: reads + writes)]
    PRIMARY -. Async replication .-> REPLICA[(Read replica)]
    REPORT[Reporting worker] --> REPLICA
~~~

### 14.1. Advantages

- Offloads reporting from the primary.
- Scales system read throughput.
- Prevents heavy `SELECT`s from competing for primary compute.

### 14.2. Limitations

- Replicas can return stale state due to **replication lag**.
- Never route normal writes to a read replica.
- Does not solve write bottlenecks.
- Cannot serve as historical PITR backups.
- Do not treat as an auto-failover solution unless explicitly designed and supported.

### 14.3. Read-After-Write

After a user updates an order, the immediate next request needing the freshly written status should consider reading from the primary. Reporting dashboards can tolerate lag when SLOs explicitly permit it.

## 15. Networking: Public Access and Private Topologies

Networking mode is a foundational choice when creating a Flexible Server.

### 15.1. Public Access with Firewall

The server exposes a public endpoint per config, while Azure firewall rules restrict permitted source IPs.

~~~text
Developer workstation
        |
  Firewall allowlist + TLS
        |
mysql-lab.mysql.database.azure.com
~~~

Fits certain labs or approved setups. Never open the entire Internet just to connect quickly.

### 15.2. Private Access / VNet Integration

In supported topologies, Flexible Server integrates into a private network via a delegated subnet and private DNS.

~~~text
AKS / App Service with VNet connectivity
             |
          Azure VNet
             |
         Private DNS
             |
       MySQL Flexible Server
~~~

Verify:

- VNet/subnet/delegation.
- IP space.
- Private DNS zone and VNet links.
- NSGs/routes/firewalls.
- VPN/ExpressRoute if on-premises access is needed.
- Where CI/CD, DBAs, and migration tools connect from.

### 15.3. Private Endpoint Differs from VNet Integration

**Private Link/Private Endpoint** support depends on Flexible Server deployment mode and current features. Do not assume a server in any networking mode can switch to a private endpoint with a single toggle.

### 15.4. Never Hard-Code IPs

Always use the MySQL server hostname. Failover/maintenance can re-route the endpoint to different underlying infrastructure.

## 16. DNS and Connecting from Azure Workloads

Example endpoint:

~~~text
mysql-shop-prod.mysql.database.azure.com
~~~

From an authorized machine or Pod:

~~~bash
nslookup mysql-shop-prod.mysql.database.azure.com
~~~

Test the port:

~~~bash
nc -vz mysql-shop-prod.mysql.database.azure.com 3306
~~~

`nslookup` verifies only DNS resolution. `nc` tests only TCP connectivity, not TLS, authentication, or database permissions.

### 16.1. When Private DNS Fails

- AKS Pod resolves the wrong IP.
- A machine in VNet A connects, VNet B does not.
- On-premises has routing, but DNS forwarding is missing.
- App Service lacks VNet integration or proper outbound routing.

Verify DNS zone links, routing, and private endpoint/delegated topology before altering firewalls or disabling TLS.

## 17. TLS: Encryption and Verifying the MySQL Server

Production should require TLS and **verify the server's certificate identity**.

- **No TLS:** lacks proper transport encryption.
- **TLS encryption only:** encrypts the channel, without necessarily verifying full hostname/certificate identity.
- **VERIFY_IDENTITY:** checks both the certificate chain and hostname when the client/truststore is properly configured.

MySQL CLI example:

~~~bash
mysql \
  --host=mysql-shop-prod.mysql.database.azure.com \
  --port=3306 \
  --user=app_reader \
  --password \
  --ssl-mode=VERIFY_IDENTITY \
  --ssl-ca=/secure/path/to/ca-bundle.pem \
  shopdb
~~~

`/secure/path/to/ca-bundle.pem` is a placeholder. Pick a trust bundle accepted by Azure/MySQL clients and update it when certificate chains rotate. In labs some clients may use `REQUIRED` for encryption, yet production should verify server identity per policy.

### 17.1. Certificate Rotation

Never pin a single leaf certificate permanently when the service rotates certificates. Maintain truststores/JDK/Connector-J versions and test before certificate changes take effect.

## 18. MySQL Authentication and Microsoft Entra ID

Supported authentication methods may include:

- **Native MySQL users/passwords:** traditional mechanism.
- **Microsoft Entra authentication:** when supported by version, server configuration, and client flow.

Using Entra authentication enables passwordless designs in certain setups, but requires configuring the server administrator, Entra principal mapping, token acquisition/refresh, and proper SQL grants.

**An AKS/App Service managed identity does not automatically create a MySQL user or grant SELECT.** Azure Resource Manager roles and SQL database authentication are separate.

### 18.1. Secret Management

When using native MySQL passwords:

- Store secrets in Azure Key Vault or an approved secret store.
- Never save in Git, container images, logs, or query strings.
- Rotate per policy.
- Use dedicated accounts per workload/environment.
- Never use the MySQL administrator account for application runtime.

## 19. Azure RBAC vs. MySQL Permissions

| Scope | Example | Meaning |
|---|---|---|
| Azure resource management | Reader, Contributor on Flexible Server | Manage metadata/resource configuration |
| MySQL login | user/password or Entra principal mapping | Authenticate to the database engine |
| MySQL grants | SELECT, INSERT, UPDATE, DELETE on `shopdb` | Privileges on tables/schemas |

An engineer holding **Azure Reader** cannot automatically run `SELECT` on `shopdb`; conversely, an app holding a SQL account cannot resize the server SKU without Azure RBAC.

### 19.1. Least Privilege

Separate **app_reader**, **app_writer**, and admin. Never grant `DROP DATABASE`, `CREATE USER`, or global privileges to app runtime accounts just to bypass permission errors.

## 20. Sample SQL: Creating Schema and Indexes

MySQL 8.x example in a lab database:

~~~sql
CREATE DATABASE IF NOT EXISTS shopdb
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

USE shopdb;

CREATE TABLE IF NOT EXISTS orders (
    order_id     VARCHAR(40) NOT NULL,
    customer_id  VARCHAR(40) NOT NULL,
    amount       DECIMAL(12,2) NOT NULL,
    status       VARCHAR(20) NOT NULL,
    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP NOT NULL
                 DEFAULT CURRENT_TIMESTAMP
                 ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (order_id),
    INDEX idx_customer_created (customer_id, created_at)
) ENGINE=InnoDB;
~~~

`utf8mb4_0900_ai_ci` is an illustrative collation depending on supported MySQL version; verify your engine version before applying. If incompatible, pick a suitable `utf8mb4` collation.

### 20.1. DECIMAL for Monetary Values

Use `DECIMAL` for currency and exact arithmetic within defined precision, instead of `FLOAT`/`DOUBLE` which suffer binary rounding errors.

### 20.2. InnoDB

InnoDB supports transactions, row-level locking, and foreign keys in MySQL, fitting most transactional applications.

### 20.3. Indexes Are Not Free

Indexes speed up reads matching query patterns, but consume storage and add work to every `INSERT`/`UPDATE`/`DELETE`.

## 21. Creating MySQL Users Following Least Privilege

The example below is illustrative SQL to be run by an authorized SQL administrator:

~~~sql
CREATE USER 'shop_reader'@'%'
  IDENTIFIED BY 'REPLACE_WITH_SECURE_SECRET';

GRANT SELECT ON shopdb.*
  TO 'shop_reader'@'%';

CREATE USER 'shop_writer'@'%'
  IDENTIFIED BY 'REPLACE_WITH_ANOTHER_SECRET';

GRANT SELECT, INSERT, UPDATE, DELETE ON shopdb.*
  TO 'shop_writer'@'%';

SHOW GRANTS FOR 'shop_reader'@'%';
SHOW GRANTS FOR 'shop_writer'@'%';
~~~

**Never use placeholders as real passwords and never commit SQL scripts with secrets into Git.** When automating account creation, pull credentials from an approved secret manager and keep them out of logs.

### 21.1. Host Wildcard and Azure Firewall

`'user'@'%'` is a MySQL account host pattern. It does not replace Azure firewall/VNet controls. Likewise, a wildcard is not a tight network control at the SQL layer.

### 21.2. Never Use Admin for Java Applications

Application accounts rarely need `CREATE USER`, `GRANT`, `DROP DATABASE`, or global privileges. Separate migration accounts, runtime writers, and reporting readers by purpose.

## 22. Transactions and Concurrency

Suppose `orders-api` must insert an order and decrement inventory. In MySQL InnoDB, both operations belong in one transaction when data and business logic demand atomicity.

~~~sql
START TRANSACTION;

INSERT INTO orders (order_id, customer_id, amount, status)
VALUES ('ORD-1001', 'C-20', 125000.00, 'CREATED');

UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 'P-100'
  AND quantity > 0;

-- Application must check affected rows;
-- COMMIT only when all steps succeed, otherwise ROLLBACK.
COMMIT;
~~~

**Note:** the SQL above illustrates logic; the `inventory` table was not created earlier. In real code, create the table and verify affected rows from `UPDATE`; never `COMMIT` unconditionally if inventory is zero.

### 22.1. ACID Does Not Eliminate Deadlocks

Concurrent transactions can cause deadlocks, lock waits, and retries. Design indexes, consistent update ordering, and short transactions to minimize lock duration.

### 22.2. Optimistic Concurrency

When a table has a `version` column:

~~~sql
UPDATE products
SET price = 150000,
    version = version + 1
WHERE product_id = 'P-100'
  AND version = 7;
~~~

If affected rows equal 0, the record changed concurrently. The application must handle the conflict rather than blindly overwriting.

### 22.3. Retry Only When Idempotent

If the connection drops right after `COMMIT` before the response returns, the client cannot tell whether the transaction succeeded. Retrying the exact `INSERT` with a fixed business key and unique constraint is safer than generating a new `orderId` on every retry.

## 23. EXPLAIN and Indexes: Optimize Before Adding Compute

An API frequently runs:

~~~sql
SELECT order_id, amount, status, created_at
FROM orders
WHERE customer_id = 'C-20'
ORDER BY created_at DESC
LIMIT 20;
~~~

Index `(customer_id, created_at)` is worth evaluating because the query filters by customer and sorts by `created_at`.

~~~sql
EXPLAIN
SELECT order_id, amount, status, created_at
FROM orders
WHERE customer_id = 'C-20'
ORDER BY created_at DESC
LIMIT 20;
~~~

Observe:

- Access method and key chosen.
- Optimizer's estimated row count.
- Presence of full scans or filesort (`Extra`).
- Whether the query returns excessive columns/data.
- Whether index selectivity fits real data.

### 23.1. Indexes Do Not Always Improve Every Query

Indexes consume storage and force `INSERT`/`UPDATE` to maintain structures. On tiny tables or low-selectivity filters, the optimizer may ignore an index.

### 23.2. Avoid N+1

If an API fetches 100 orders and issues 100 separate `SELECT`s for customers, total latency climbs even if each query is fast. Inspect query counts, JOINs/batch fetching, and controlled caching.

### 23.3. Do Not Run EXPLAIN ANALYZE Recklessly in Production

Certain analysis modes execute the query and add overhead. For data-modifying statements, understand the impact thoroughly before running.

## 24. Connecting Java with MySQL Connector/J and HikariCP

Java applications use JDBC and a connection pool to reuse connections. A well-tuned pool avoids establishing a new TLS handshake and MySQL session on every HTTP request.

Typical dependencies:

- **MySQL Connector/J** compatible with your MySQL and JDK versions.
- **HikariCP** or a framework-compatible pool.
- Logging/metrics to detect pool exhaustion.

### 24.1. JDBC URL Over TLS

Example environment config:

~~~text
DB_URL=jdbc:mysql://mysql-shop-prod.mysql.database.azure.com:3306/shopdb?sslMode=VERIFY_IDENTITY
DB_USER=shop_writer
DB_PASSWORD=<secret-provided-at-runtime>
~~~

`DB_URL` must point to the actual hostname; `VERIFY_IDENTITY` requires a matching Java truststore and certificate chain. The password is a placeholder, never stored in source code.

### 24.2. Java JDBC Sample

~~~java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public final class OrdersRepository implements AutoCloseable {
    private final HikariDataSource pool;

    public OrdersRepository() {
        HikariConfig config = new HikariConfig();

        config.setJdbcUrl(requireEnv("DB_URL"));
        config.setUsername(requireEnv("DB_USER"));
        config.setPassword(requireEnv("DB_PASSWORD"));

        config.setMaximumPoolSize(5);
        config.setMinimumIdle(0);
        config.setConnectionTimeout(5000);
        config.setPoolName("orders-db-pool");

        pool = new HikariDataSource(config);
    }

    public void createOrder(String orderId,
                            String customerId,
                            BigDecimal amount)
            throws SQLException {
        String sql =
            "INSERT INTO orders " +
            "(order_id, customer_id, amount, status) " +
            "VALUES (?, ?, ?, ?)";

        try (Connection conn = pool.getConnection();
             PreparedStatement statement =
                 conn.prepareStatement(sql)) {
            statement.setString(1, orderId);
            statement.setString(2, customerId);
            statement.setBigDecimal(3, amount);
            statement.setString(4, "CREATED");
            statement.executeUpdate();
        }
    }

    private static String requireEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing setting: " + key);
        }
        return value;
    }

    @Override
    public void close() {
        pool.close();
    }
}
~~~

This is a minimal example; production requires error classification, proper transactions, idempotency, input validation, and pool usage metrics.

### 24.3. PreparedStatement

`PreparedStatement` avoids concatenating user input directly into SQL, reducing SQL injection risk when used properly. Never concatenate `userInput` directly into a `WHERE` clause string.

### 24.4. Closing Connections vs. Closing the Pool

Exiting `try-with-resources` on a connection obtained from Hikari **returns the connection to the pool**. Close `HikariDataSource` on application shutdown—never close the entire pool after every request.

## 25. Connection Pools and Too Many Connections Errors

Suppose there are 20 AKS Pods, each allowing up to 50 JDBC connections:

\[
20 \times 50 = 1{,}000\ \text{potential open connections}
\]

This total can exceed MySQL limits or consume substantial memory.

### 25.1. Practical Pool Sizing

1. Count peak Pods/instances.
2. Measure concurrent queries and query durations.
3. Choose an adequate `maximumPoolSize`.
4. Set connection acquisition timeouts.
5. Monitor active/idle/waiting connections.
6. Configure connection validation and post-failover retries.
7. Prevent connection leaks and long-running transactions.
8. Avoid keeping too many idle connections open.

### 25.2. Failover Can Cause a Connection Storm

When the primary switches roles, existing connections drop. If hundreds of Pods retry simultaneously, the database can get overwhelmed. Use backoff, jitter, and a bounded retry budget.

### 25.3. Raising max_connections Doesn't Fix Every Error

If the cause is a pool leak or oversized pool configuration, raising server limits will not fix the root issue. Measure actual connections, waiters, and how long each connection is held.

## 26. Spring Boot and External Configuration

In Spring Boot, use environment variables to supply settings without putting passwords in source control.

Example environment variables:

~~~text
SPRING_DATASOURCE_URL=jdbc:mysql://mysql-shop-prod.mysql.database.azure.com:3306/shopdb?sslMode=VERIFY_IDENTITY
SPRING_DATASOURCE_USERNAME=shop_writer
SPRING_DATASOURCE_PASSWORD=<secret-from-approved-store>
SPRING_DATASOURCE_HIKARI_MAXIMUM_POOL_SIZE=5
~~~

Spring Boot binds settings from environment variables according to its version's relaxed-binding rules. Verify active settings to confirm the pool size is actually applied.

### 26.1. Never Let ORMs Alter Production Schemas Arbitrarily

In production, use Flyway/Liquibase or a reviewed, versioned migration workflow instead of letting the app `DROP`/`CREATE` schemas uncontrolled.

### 26.2. Readiness and Liveness

If MySQL is briefly unavailable, readiness probes can signal the app shouldn't receive traffic yet. Never tie liveness probes directly to the database in a way that causes all Pods to restart in a loop whenever the DB slows down.

### 26.3. Passwordless Requires Dedicated Configuration

If using Microsoft Entra authentication for MySQL Flexible Server, the client must acquire/refresh tokens via the proper flow and the server must have matching principals/grants. Do not just enable managed identity and expect Connector/J to pick up tokens automatically.

## 27. Azure Monitor and Performance Signals

A useful MySQL dashboard covers:

| Layer | Metrics | Purpose |
|---|---|---|
| Compute | CPU utilization, memory pressure | Identify CPU/RAM bottlenecks |
| Connections | Active/failed connections | Detect pool limits/leaks |
| Storage | Used storage, growth | Forecast capacity exhaustion |
| I/O | IOPS, read/write latency | Identify storage bottlenecks |
| Query | Slow queries, p95/p99 query latency | Pinpoint SQL needing tuning |
| Transactions | Lock waits, deadlocks | Assess contention |
| HA | Failover/availability events | Track connection disruptions |
| Replicas | Replication lag/health | Detect stale reads |
| Backup/DR | Restore rehearsal outcomes | Prove recoverability |
| Billing | Compute, backups, storage, logs | Stay within budget |

Not every value is a built-in Azure Monitor metric on every SKU. Metrics like JDBC pool wait or business query p99 typically require **application instrumentation**.

### 27.1. End-to-End Tracing

~~~text
HTTP request
  -> Java application
  -> Wait for Hikari pool
  -> Send SQL
  -> MySQL processing
  -> Transaction commit
  -> HTTP response
~~~

If HTTP p99 rises, compare pool wait time, query duration, network latency, and MySQL CPU/I/O instead of blaming the database blindly.

### 27.2. Logs Containing Sensitive Data

Slow query logs and query traces can contain SQL values or IDs. Enforce appropriate retention/sampling, masking, and role-based access.

## 28. MySQL Server Parameters and Slow Query Logs

Flexible Server lets you adjust many MySQL parameters via Azure interfaces within supported bounds. Some changes are dynamic; others require a restart.

Key groups to know:

- Character set/collation and SQL mode.
- Connection timeouts/limits.
- Slow query logging.
- InnoDB/optimizer-related parameters within allowed ranges.
- Binary logging/replication-related behavior.
- Timezone and session settings where supported.

### 28.1. Parameter Change Workflow

1. Quantify the problem with metrics.
2. Check default and current values.
3. Cross-check MySQL version and Azure support.
4. Determine whether the change triggers a restart.
5. Test in staging.
6. Schedule a maintenance window if needed.
7. Change a small batch at a time.
8. Re-measure p95/p99, errors, CPU/memory.
9. Prepare a rollback if performance worsens.

### 28.2. Reading Parameters via Azure CLI

~~~bash
az mysql flexible-server parameter list \
  --resource-group rg-shop-lab \
  --server-name mysql-shop-lab-unique \
  --output table
~~~

This illustrates CLI usage for a lab environment; verify syntax/flags against your Azure CLI version.

## 29. Query Tuning Before Upgrading SKUs

Workflow:

1. Receive CPU or latency alert.
2. Identify slow query patterns.
3. Measure rows examined and execution frequency.
4. Run `EXPLAIN` in an authorized environment.
5. Check indexes, join order, and filters.
6. Hunt down ORM N+1 queries.
7. Optimize transactions and locking.
8. Re-run load tests.
9. Upgrade SKU only if compute/I/O remains insufficient.

### 29.1. Batch Queries and Caching

Batching queries reduces round trips. Caching cuts read load, yet requires invalidation/TTL and must never serve stale data when business logic demands fresh state.

### 29.2. Avoid Excessive Query Logging

Logging every query adds overhead, cost, and PII exposure risks. Enable slow-query logging targeted to investigations with bounded retention.

## 30. Maintenance, Patching, and Major Upgrades

Azure performs platform maintenance, though applications may see connection resets, restarts, or failovers.

### 30.1. Maintenance Windows

Pick low-traffic hours where customizable. Avoid overlapping database maintenance with schema migrations, batch settlements, and major deployments.

### 30.2. Upgrading MySQL Versions

Major upgrades can impact:

- Reserved keywords/SQL syntax.
- Authentication plugins.
- Charsets/collations.
- Query optimizer behavior.
- Stored procedures/triggers.
- JDBC driver compatibility.
- Deprecated server parameters.
- Data migration and rollback paths.

**Do not assume Flexible Server supports direct downgrades after a major upgrade.** Check currently supported versions and service upgrade procedures at deployment time.

### 30.3. Upgrade Checklist

1. Inventory schemas, apps, and drivers.
2. Review breaking changes.
3. Rehearse backup/restore.
4. Build a production-like staging environment.
5. Test CRUD, transactions, migrations, and performance.
6. Prepare a cutover/rollback plan.
7. Schedule a maintenance window.
8. Monitor application errors post-upgrade.

## 31. Scaling Compute, Storage, and Reads

Three main axes:

- **Compute scale:** adjust vCores and memory per SKU.
- **Storage/IOPS scale:** adjust capacity or storage performance per feature support.
- **Read replicas:** offload `SELECT` queries that tolerate stale data.

### 31.1. Scaling Compute Can Be Disruptive

Changing SKUs or scaling compute may require a restart or failover depending on context. Apps need reconnect, retry, and idempotency handling.

### 31.2. Storage Does Not Shrink Easily

Do not grow storage recklessly assuming you can shrink it right after dropping tables. Forecast long-term costs.

### 31.3. Read Replicas Do Not Fix Write Locks

If `UPDATE inventory` causes contention, adding read replicas will not ease lock contention on the primary.

## 32. Disaster Recovery and Cross-Region Incidents

RPO/RTO dictate the DR strategy.

| Incident | Mechanism to Consider | What to Test |
|---|---|---|
| Primary instance failure | HA failover | Reconnect and recovery duration |
| Zone failure | Zone-redundant HA if supported by config | Whether apps and networking remain available |
| Accidental table drop | PITR restore | Data, RPO/RTO, cutover |
| Region outage | Supported geo-restore/DR architecture | Target region, data loss, networking |
| Reporting overload | Read replica | Lag and fallback |
| Connection storm | Pool limits/backoff | Peak scaling and failover |

### 32.1. In-Region HA Does Not Equal Multi-Region DR

Zone-redundant HA protects against single-zone faults within a region, not a full region outage.

### 32.2. Verify Geo Options First

Geo-redundant backups, cross-region replicas, and geo-restores depend on tier, region, time, and configuration. Never promise RPO=0 or automatic cross-region failover without a verified, working solution.

## 33. Migrating from Self-Managed MySQL

Migration should start with an **assessment**, not the first copy command.

### 33.1. Details to Verify

- MySQL engine/version/edition.
- DB/table sizes and growth.
- Charset/collation and timezone.
- Storage engine.
- Stored procedures, triggers, events.
- Users, grants, authentication plugins.
- Required server parameters.
- Queries relying on OS privileges or the filesystem.
- Downtime window and data change rate.
- Network/firewall/latency to Azure.
- Binary logs/replication prerequisites if migrating online.

### 33.2. Offline vs. Online?

| Approach | Advantages | Risks |
|---|---|---|
| Offline dump/restore | Easy to explain and control for small datasets | Downtime proportional to dump/restore time |
| Online/continuous replication migration | Shrinks cutover downtime | Consistency, log/replication, and final-sync complexity |
| Application dual-write | Allows gradual workload migration | Data divergence risk without strict protocols |

Azure migration tools support specific source/target combinations. Confirm exact engine/version/topology compatibility rather than assuming every tool works universally.

## 34. Cutover Runbook to Flexible Server

1. Freeze schema changes ahead of the window.
2. Verify source backups and rehearse restore.
3. Provision target server; verify networking/DNS/TLS.
4. Create users/roles per procedure.
5. Run migration and track progress.
6. Compare row counts/checksums/business invariants.
7. Stop source writes if required by the plan.
8. Wait for target data to catch up to the cutover point.
9. Update application secrets/connection configs.
10. Run smoke tests covering CRUD, transactions, and query latency.
11. Monitor error rates, slow queries, and connection counts.
12. Define rollback criteria and know when rollback ceases to be safe.
13. Retain the source during a reconciliation window before approved deletion.

**Never delete the source database just because the API returns HTTP 200**; verify data and critical transactions thoroughly.

## 35. Creating a Lab Flexible Server in the Azure Portal

**Create resources only in an authorized subscription/resource group with approved budget.** Using the Portal displays live region/SKU options directly rather than relying on version-specific CLI flags.

### 35.1. Preparation

- Dedicated resource group like `rg-shop-lab`.
- Suitable region supporting MySQL Flexible Server.
- Securely generated/stored MySQL admin password.
- Fixed source IP or VNet with private access.
- Budget and cleanup plan.

### 35.2. Steps

1. Azure Portal → Create a resource.
2. Search for **Azure Database for MySQL flexible server**.
3. Select subscription and resource group.
4. Pick a unique server name and region.
5. Select a supported MySQL engine version.
6. Pick Burstable/small compute suited for labs if supported.
7. Select modest storage; review IOPS/autogrow.
8. For labs not needing HA, consider leaving HA off to save cost; never apply that default to production.
9. Set appropriate lab backup retention.
10. Choose networking:
    - Public access allowlisting only the lab machine IP; or
    - Private topology when VNet/subnet/DNS are ready.
11. Configure administrator and secret.
12. Review TLS policy, monitoring, and tags.
13. Review + Create.
14. Record FQDN, tier, storage, network mode, and projected cost.

**Never open the firewall to the entire Internet**, and do not enable allow-all Azure services without understanding its scope.

### 35.3. Private Access Requires Upfront Preparation

Some private integration models require a delegated subnet/private DNS and restrict switching modes after creation. Check current Flexible Server capabilities before choosing.

## 36. Azure CLI: Inspecting the Lab Server

These read-only commands never put SQL passwords on the command line:

~~~bash
az login
az account set --subscription "<subscription-id>"

az mysql flexible-server show \
  --resource-group rg-shop-lab \
  --name mysql-shop-lab-unique \
  --output json

az mysql flexible-server list \
  --resource-group rg-shop-lab \
  --output table
~~~

Inspect parameters:

~~~bash
az mysql flexible-server parameter list \
  --resource-group rg-shop-lab \
  --server-name mysql-shop-lab-unique \
  --output table
~~~

For public-access labs with firewalls:

~~~bash
az mysql flexible-server firewall-rule list \
  --resource-group rg-shop-lab \
  --name mysql-shop-lab-unique \
  --output table
~~~

**`mysql-shop-lab-unique`** is a placeholder, not a real resource. CLI syntax, options, and output schemas can change; check current CLI help to verify.

### 36.1. Why Not Put Passwords in CLI Create Examples?

Passwords on the command line leak into shell history, process listings, and CI logs. Provision via the Portal, secure prompts, or approved secret/automation mechanisms.

## 37. Connecting with MySQL CLI and Verifying the Session

Once the server, database, SQL account, and certificate trust are configured:

~~~bash
mysql \
  --host=mysql-shop-lab-unique.mysql.database.azure.com \
  --port=3306 \
  --user=shop_writer \
  --password \
  --ssl-mode=VERIFY_IDENTITY \
  --ssl-ca=/secure/path/to/ca-bundle.pem \
  shopdb
~~~

If login succeeds:

~~~sql
SELECT VERSION();
SELECT DATABASE();
SELECT CURRENT_USER();
SHOW VARIABLES LIKE 'require_secure_transport';
SHOW STATUS LIKE 'Ssl_cipher';
~~~

**Run verification commands only on your created lab server.** Replace the CA path with the valid trust bundle. Parameters and output vary slightly across MySQL versions/clients.

### 37.1. Verify Four Layers

1. DNS resolution.
2. TCP/routing/firewall.
3. TLS/hostname/certificate.
4. MySQL authentication and grants.

If a connection fails, isolate the exact layer instead of disabling TLS or widening firewalls.

## 38. SQL Hands-On: Schema, Transactions, Indexes

Inside the lab **shopdb** database:

~~~sql
CREATE TABLE IF NOT EXISTS products (
  product_id VARCHAR(40) NOT NULL,
  name VARCHAR(200) NOT NULL,
  price DECIMAL(12,2) NOT NULL,
  quantity INT NOT NULL,
  version INT NOT NULL DEFAULT 1,
  PRIMARY KEY (product_id),
  CHECK (quantity >= 0)
) ENGINE=InnoDB;

INSERT INTO products (product_id, name, price, quantity)
VALUES ('P-100', 'Demo product', 125000.00, 10);

INSERT INTO orders (order_id, customer_id, amount, status)
VALUES ('ORD-1001', 'C-20', 125000.00, 'CREATED');

EXPLAIN
SELECT order_id, amount
FROM orders
WHERE customer_id='C-20'
ORDER BY created_at DESC
LIMIT 10;
~~~

Re-running `INSERT` with the same primary key triggers a duplicate-key error; this is expected behavior, not a service bug.

### 38.1. Transaction Demo

~~~sql
START TRANSACTION;

UPDATE products
SET quantity = quantity - 1,
    version = version + 1
WHERE product_id = 'P-100'
  AND quantity > 0;

SELECT ROW_COUNT() AS affected_rows;

-- COMMIT only if affected_rows=1 and all other checks pass.
-- Otherwise, ROLLBACK.
COMMIT;
~~~

In real application code, **inspect `affected_rows` and programmatically drive `COMMIT`/`ROLLBACK`**, rather than unconditionally executing `COMMIT` after a comment.

## 39. Lab Planning for HA, PITR, and Read Replicas

HA/replica/geo-backup features can incur significant cost. Complete the design exercise first, provisioning extras only with budget/approval.

### Part A — HA

1. Check whether the SKU/region supports same-zone or zone-redundant HA.
2. Diagram primary and standby.
3. Describe which connections break during failover.
4. Write a retry/backoff and idempotency policy.
5. Never test failover in production.

### Part B — PITR

1. Create a sample table in the lab server.
2. Record a timestamp before altering data.
3. Confirm retention covers that timestamp.
4. If budget permits, restore **to a new server**.
5. Verify row counts and business invariants.
6. Measure actual RTO.
7. Delete the restored server per workflow when finished.

### Part C — Read Replica

1. Determine whether reports tolerate stale reads.
2. Check read replica eligibility for your SKU/region.
3. Estimate replica compute/storage cost.
4. Plan replication lag monitoring.
5. Design app routing: writes/critical reads to primary, reporting reads optionally to replica.
6. Never enable a replica solely to "have a backup."

## 40. Troubleshooting by Error Category

### 40.1. DNS Fails to Resolve

Check exact hostname, private DNS zone, VNet links, DNS forwarding, and endpoint topology.

### 40.2. TCP Timeout on Port 3306

Check firewall IPs, NSGs/routes, subnets, private endpoint/VNet integration, client outbound routing, and VPN/ExpressRoute.

### 40.3. TLS/Certificate Failure

Check Java truststore, CA chain, TLS mode, hostname, and certificate rotation. Never bypass by disabling certificate verification in production.

### 40.4. Access Denied for User

Check MySQL account host mapping, password/token, SQL grants, and authentication mode. Azure RBAC Contributor does not replace SELECT grants.

### 40.5. Too Many Connections

Check pool size × Pod count, connection leaks, idle sessions, app retry storms, and `max_connections`. Never blindly raise server limits alone.

### 40.6. High CPU

Analyze slow queries, missing indexes, table scans, N+1 queries, reporting load, and lock contention before scaling up.

### 40.7. Storage Nearly Full

Measure used storage, growth, autogrow, quotas, and temp files/logging. Deleting rows does not shrink provisioned capacity.

### 40.8. Read Replica Lag

Inspect primary write volume, replica workload, long transactions, and replication status. Avoid stale reads for data needing strong consistency.

### 40.9. Failover Triggers API 5xx

Check pool invalid connections, reconnect/backoff, uncertain transaction outcomes, and application readiness.

### 40.10. New PITR Server Cannot Connect

Check VNet/firewall, DNS/FQDN, SQL users/grants, secrets, engine version, and whether the app still points to the old connection string.

## 41. Flexible Server Costs

| Item | Cost Drivers |
|---|---|
| Compute | Tier, vCores/SKU, running hours |
| Storage | Provisioned capacity, growth |
| IOPS/throughput | Performance configuration per feature and pricing model |
| HA | Standby capacity and HA mode |
| Read replicas | Compute/storage for each replica |
| Backups | Retention and storage volume per pricing policy |
| Networking | Private Link/egress/connectivity resources |
| Monitoring | Logs/metrics ingestion, retention |
| DR | Geo backups/replication/restore drills |

Never cite a fixed unit price without specifying region, SKU, currency, and timeframe.

### 41.1. Cost Optimization

- Pick a tier matching measured workloads.
- Fix SQL/indexes before raising compute/IOPS.
- Cap pool limits to avoid excess connections.
- Monitor storage growth and backup retention.
- Do not create read replicas without an actual read workload to offload.
- Set budgets/tags in Azure Cost Management.
- Clean up lab resources when finished.

### 41.2. Does Stopping a Lab Server Eliminate All Charges?

Supported stop/start features can reduce compute charges under certain conditions, yet do not eliminate all storage/backup costs; stop duration limits/conditions also apply. Always monitor resources and actual billing.

## 42. Reference Production Java Application Architecture

~~~mermaid
flowchart TB
    USER[Users] --> GW[Ingress / API Gateway]
    GW --> API[AKS orders-api Java]
    GW --> CAT[AKS catalog-api]
    API --> PRI[(MySQL primary)]
    CAT --> PRI
    PRI -. Async replication .-> READ[(Optional read replica)]
    REPORT[Reporting worker] --> READ
    API --> SEC[Key Vault / Identity integration]
    PRI --- HA[(Optional HA standby)]
    PRI --- BK[(Backup / PITR)]
    MON[Azure Monitor] --- PRI
    MON --- API
~~~

### Key Decisions

- Use private networking per company policy where appropriate.
- Never hard-code IPs or SQL passwords in containers.
- Size pools relative to total Pods.
- Use read replicas only for lag-tolerant reads.
- Align HA/backups/DR with RPO/RTO.
- Monitor connection errors, slow queries, and storage.
- Manage schema migrations through approved CI/CD.

### MySQL + Service Bus Outbox

When an app writes to MySQL and publishes a message to Service Bus, the two actions are not automatically wrapped in a cross-service ACID transaction. **Transactional outbox** is a pattern that reduces the risk of DB commit succeeding while event delivery is lost.

## 43. Comprehensive Hands-On Lab

### A. Preparation

1. Authorized lab subscription/resource group with budget.
2. Choose engine version/tier/storage/networking.
3. Configure dedicated firewall IP or private VNet access.
4. Store secrets safely and configure TLS.
5. Define cleanup criteria.

### B. Provisioning

1. Create MySQL Flexible Server via the Portal.
2. Record FQDN, tier, vCores, storage, and backup retention.
3. Verify DNS and TCP connectivity.
4. Connect with MySQL CLI over TLS.
5. Record TLS/authentication status.

### C. Database and Security

1. Create `shopdb` and the `orders` table.
2. Create least-privilege read-only and writer roles/users.
3. Inspect `SHOW GRANTS`.
4. Run sample `INSERT`/`SELECT` statements.
5. Keep credentials out of Git.

### D. Java JDBC

1. Configure MySQL Connector/J.
2. Use a small HikariCP pool.
3. Run `PreparedStatement` to insert an order.
4. Test duplicate-key behavior.
5. Measure active/waiting pool connections.

### E. Optimization

1. Run `EXPLAIN` on the customer query.
2. Compare with an appropriate index.
3. Monitor CPU/I/O/query duration.
4. Do not upgrade SKUs without evidence.

### F. Recovery

1. Write an accidental data-deletion scenario.
2. Identify a PITR timestamp before the mistake.
3. If budget permits, restore to a new server.
4. Verify data and measure recovery duration.
5. Never cut over automatically without verifying accuracy.

### G. Cleanup

1. Save a secret-free report.
2. Stop lab applications.
3. Confirm the server holds no shared data/resources.
4. Delete lab resources per authorization and policy.
5. Check Azure Cost Management.

**The lab is complete when you can justify tier/network choices, connect securely, execute proper SQL/JDBC, and show evidence of a tested recovery plan.**

## 44. Production Readiness Checklist for Flexible Server

- [ ] MySQL version is supported and compatible with the application.
- [ ] Workloads measured to choose tier/vCores/memory.
- [ ] Storage/IOPS/growth forecasted with alerts.
- [ ] HA mode fits SLO and is supported in region/SKU.
- [ ] Backup retention satisfies business requirements.
- [ ] PITR restore rehearsed with measured actual RTO.
- [ ] Regional-outage DR plan prepared if required.
- [ ] Read replicas never used as a backup substitute.
- [ ] Replication lag monitored if replicas exist.
- [ ] Firewall not opened too broadly to the Internet.
- [ ] VNet/private DNS tested from actual workloads.
- [ ] TLS with certificate verification properly configured.
- [ ] Secrets kept out of source code/Git/logs.
- [ ] SQL users/grants follow least privilege.
- [ ] Azure RBAC and MySQL data-plane rights separated.
- [ ] JDBC driver/HikariCP configured with limits/timeouts.
- [ ] App handles reconnects/failover and enforces idempotency.
- [ ] Schema migrations reviewed and versioned.
- [ ] Core queries verified with `EXPLAIN`/appropriate indexes.
- [ ] Slow query monitoring and log retention controlled.
- [ ] Metrics configured for CPU, storage, connections, and error rates.
- [ ] Maintenance window and upgrade compatibility tests established.
- [ ] Migration cutover includes rollback and validation plans.
- [ ] Cost budget includes HA, replicas, storage, and monitoring.
- [ ] Incident runbooks and accountable owners assigned.
- [ ] SQL administrator never used as the runtime application account.
- [ ] Recovery tested against accidental data deletion.

## 45. Self-Check Questions

1. Which MySQL operational tasks does Flexible Server offload from the operations team?
2. Which workloads fit Burstable, General Purpose, and Memory Optimized?
3. Why doesn't high CPU always warrant increasing vCores?
4. Does storage autogrow let you shrink storage after deleting data?
5. How do same-zone HA and zone-redundant HA differ in failure domains?
6. Is an HA standby a read replica for reporting?
7. Can HA recover from an accidental `DELETE`?
8. How does PITR typically create the restored server?
9. How do RPO and RTO differ?
10. Is a read replica instantaneously consistent with the primary?
11. Why might a request right after a write need to read from the primary?
12. How does public access/firewall differ from private VNet integration?
13. Why must private DNS and routing be designed together?
14. How does TLS `REQUIRED` differ from `VERIFY_IDENTITY`?
15. Does Azure Contributor automatically grant `SELECT` on `shopdb`?
16. Does a managed identity automatically create a MySQL user?
17. Why should `app_writer` only hold CRUD rights on a specific schema?
18. How does `PreparedStatement` mitigate SQL injection risk?
19. What risk does a 50-connection pool across 20 Pods introduce?
20. Why shouldn't an admin database account be used at runtime?
21. What does `EXPLAIN` help analyze?
22. Why do indexes simultaneously speed up reads and add write overhead?
23. What sensitive data can slow query logs contain?
24. What SQL/driver/charset items must a major upgrade test?
25. Does zone-redundant HA replace multi-region DR?
26. How must an online migration validate consistency and cutover?
27. Why might a newly provisioned restored server still reject application connections?
28. Does stopping a lab server halt all charges?
29. Why is a restore drill more important than merely seeing backups enabled?
30. How does transactional outbox help when writing to MySQL and sending a Service Bus event?

## 46. Summary

**Azure Database for MySQL Flexible Server** is a managed MySQL service on Azure that reduces infrastructure effort without replacing schema design, security, performance tuning, backup/restore planning, and application governance.

A sound setup balances **compute tier/vCores, memory, storage/IOPS, HA, automated backups/PITR, read replicas, networking, TLS, and authentication**. Clearly separate roles: **HA** handles certain infrastructure faults; **PITR** recovers data to a point in time; **read replicas** serve lag-tolerant reads; and **DR** addresses regional outages.

For Java applications, use **MySQL Connector/J, `PreparedStatement`, bounded connection pooling, proper secrets/identity, and idempotent retries**. Optimize with **`EXPLAIN`, indexes, transaction design, and Azure Monitor** before raising compute or IOPS. A well-run database must be **recoverable, data-protected, consistent, performant, and cost-controlled on Azure**.

