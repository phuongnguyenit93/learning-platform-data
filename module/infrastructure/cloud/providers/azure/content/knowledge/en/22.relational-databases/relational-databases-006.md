# Azure Database for PostgreSQL Flexible Server

> **Chapter:** Relational Databases  
> **Module:** `CLOUD_PROVIDERS_AZURE` — Explore the Microsoft Azure ecosystem from subscriptions, resource groups, and Entra ID to virtual networks, compute services, storage, and data. Learn how to deploy, monitor, secure, and control costs for an application architecture on Azure.

## Lesson Objectives

After this lesson, you will be able to:

1. Explain what **Azure Database for PostgreSQL Flexible Server** is, along with the responsibilities of Azure and the development/operations teams.
2. Distinguish **Flexible Server**, self-managed PostgreSQL on Azure VM, and other relational database options based on application requirements.
3. Select **compute tier, vCores, storage, IOPS, backup retention, availability zone**, and weigh cost considerations.
4. Design **public/private network access**, VNet integration, Private DNS, firewalls, TLS, and authentication via PostgreSQL or Microsoft Entra ID.
5. Provision and inspect a test server using authorized workflows; connect using **psql** and **Java/JDBC**, creating databases, roles, schemas, and illustrative transactions.
6. Understand **high availability (HA)**, zone-redundant/same-zone standbys, read replicas, backups, **point-in-time restore (PITR)**, and each mechanism's limits.
7. Operate PostgreSQL with metrics, logs, `pg_stat_statements`, index/query tuning, connection pooling, VACUUM, maintenance, and alerting.
8. Diagnose DNS, TLS, firewall, RBAC, `max_connections`, replication lag, storage pressure, and slow query issues.
9. Design a production checklist and hands-on lab covering data protection, performance, high availability, and budgets.

## 1. Context: Needing Managed PostgreSQL While Using Standard SQL

A team builds an ordering application on **Azure App Service** or **AKS**, comprising a Java/Spring Boot API and a relational database:

- `customers`, `orders`, and `order_items` data have relationships and require consistent transactions.
- The API needs to query using **SQL**, indexes, foreign keys, and transactions.
- As the application grows from hundreds to thousands of requests/second, DBAs/SREs must monitor CPU, I/O, connection counts, and slow queries.
- Data requires backups, point-in-time recovery, restricted network access, and credential protection.
- The business wants to minimize OS patching, VM configuration, rebuilding failed servers, and managing an entire PostgreSQL cluster manually.

**Azure Database for PostgreSQL Flexible Server** is an Azure-managed relational PostgreSQL service letting you select compute/storage resources, supported PostgreSQL versions, and connectivity models, alongside built-in backup, HA, and monitoring capabilities.

~~~mermaid
flowchart LR
    U["Users"]
    G["Front Door / App Gateway\nif present"]
    APP["Java Application\nApp Service or AKS"]
    DNS["Private DNS\nprivate network routing"]
    PG["PostgreSQL Flexible Server\nprimary"]
    HA["HA standby\nwhen enabled"]
    B["Automated backups\nPITR"]
    MON["Azure Monitor\nLogs / Alerts"]
    U --> G --> APP
    APP --> DNS --> PG
    PG -.->|"HA replication"| HA
    PG -.-> B
    PG -.-> MON
~~~

The diagram shows a **logical architecture**, without implying every server automatically has an HA standby or private networking. When HA is disabled, no corresponding HA standby exists. Actual paths depend on public/private access, DNS, routing, and network security.

### When Is It Appropriate?

| Requirement | Is Flexible Server Suitable? | Rationale |
| --- | --- | --- |
| Relational app needing standard PostgreSQL | Usually suitable | SQL, transactions, indexes, supported extensions |
| Want Azure to manage backups/patching | Suitable | Reduces self-management of servers and underlying storage |
| Want control over maintenance windows, sizing, HA | Suitable per config/tier/region | More flexible than completely fixed DB models |
| Need full root/OS access and arbitrary custom extensions | Not by default | PaaS restricts superuser, extensions, and filesystem |
| PostgreSQL needing logical replication/CDC | Consider carefully | Must verify version, WAL/slot config, permissions, limits |
| Many short-lived connections from serverless | Potentially suitable with pooling | Requires PgBouncer/connection pooling and connection limits |
| System needing compatibility with an older PostgreSQL version | Must check support matrix | Service only supports versions within its lifecycle |
| Massive analytics workload with heavy table scans | Consider dedicated solutions | Evaluate analytics, replicas, and HTAP/warehouse architecture |

**A managed database does not mean the application is automatically secure, skips backup tests, or cannot suffer outages.** Design HA, connectivity, queries, and recovery around business RTO/RPO.

## 2. Distinguishing Flexible Server from Other PostgreSQL Models

### 2.1. Flexible Server vs. PostgreSQL on Azure VM

| Criterion | PostgreSQL Flexible Server | Self-Installed PostgreSQL on VM |
| --- | --- | --- |
| OS and PostgreSQL patching | Azure manages service layer per schedule/policy | Operations team manages manually |
| Backup/PITR | Built-in per service/tier capabilities | Self-build backup/WAL archiving/restore |
| HA | Service-managed HA options | Self-design replication/quorum/failover |
| PostgreSQL superuser/OS root | Restricted per managed service | Full self-managed control possible |
| Compute/storage | Select available tier/SKU/storage | Select VM, disks, storage stack |
| Network connectivity | Service public/private models | Team-managed VNet, NSGs, OS firewall |
| Extensions | Only Azure-allowed/supported extensions | More flexible, but self-maintained |
| Monitoring | Azure Monitor + PostgreSQL tools | Azure VM metrics + self-integrated PostgreSQL tools |
| Kernel/OS tuning capability | Limited | Broader |
| Operational responsibility | Shared responsibility | Most responsibility sits with operations |

### 2.2. Do Not Confuse Flexible Server with Azure SQL Database

- **Azure SQL Database** provides the SQL Server/T-SQL ecosystem, drivers, and corresponding features.
- **Azure Database for PostgreSQL Flexible Server** runs PostgreSQL, using PostgreSQL SQL, datatypes, extensions, and drivers.
- Their APIs and compatibility differ; you cannot simply swap hostnames and run a T-SQL app on PostgreSQL.

### 2.3. Product Generations

Older docs may mention **Azure Database for PostgreSQL Single Server**. For new systems, focus on the **Flexible Server** model and current product migration paths; do not treat the legacy Single Server configuration as a modern standard.

### 2.4. Shared Responsibility

**Azure manages:** most underlying infrastructure, compute/storage services, service software updates, and backup/HA mechanisms when configured.

**Customer manages:** schema design, indexes, queries, applications, credentials/identities, networking rules, encryption choices, monitoring/alerts, costs, recovery tests, user permissions, and data governance.

~~~mermaid
flowchart TD
    R["PostgreSQL workload"]
    AZ["Azure-managed:\nservice infrastructure, routine maintenance,\nbackup/HA mechanisms by configuration"]
    U["Customer-managed:\nSQL/schema, IAM, firewall, client TLS,\nconnection pooling, restore drill, SLO"]
    R --> AZ
    R --> U
~~~

A slow query caused by a missing index or a long-held transaction lock **is not automatically fixed by Azure** simply because you use PaaS.

## 3. Components of Flexible Server

### 3.1. Server, Database, Schema, Role

~~~text
Azure subscription
  Resource group
    Flexible Server: pg-orders-lab
      PostgreSQL version: 16 (example; verify support)
      Host: pg-orders-lab.postgres.database.azure.com
      Port: 5432
      Databases:
        postgres
        ordersdb
          Schemas:
            public
            sales
          Roles:
            app_owner
            app_runtime
            readonly_analyst
~~~

- **Flexible Server** is the Azure resource managing a PostgreSQL server instance/endpoint.
- **Database** is a logical database inside the server; multiple databases can coexist.
- **Schema** is a namespace containing tables/views/functions inside a database.
- **Role** is a PostgreSQL principal capable of holding login rights or group privileges.
- **PostgreSQL administrator** is for initial setup and **should not be used as the query account for production applications**.
- **PostgreSQL port** is typically **5432**.
- **FQDN** takes the form `<server-name>.postgres.database.azure.com`; use the server's actual hostname.

### 3.2. Compute, Storage, and Backups Are Separate Choices

Flexible Server lets you pick the compute tier/SKU, vCores, SKU-tied RAM, provisioned storage, storage performance, and appropriate availability/backup features.

| Resource | Primary Impact | Sizing Questions |
| --- | --- | --- |
| vCores/CPU | Query processing, parallelism, background tasks | Is CPU saturating? |
| RAM/cache | Buffer cache, sorting, sessions | Do queries spill to disk or miss cache often? |
| Data storage | Data size, indexes, WAL, and growth | Are growth/retention planned? |
| IOPS | I/O operations per second | Is the workload heavy on random reads/writes? |
| Throughput | Bytes/second | Large table scans or bulk loads? |
| Connections | Concurrent connections | What are app instance counts and pool sizing? |
| Backup retention | PITR window | Does it meet recovery/compliance goals? |
| HA | RTO on node/zone failure | Are standby and failover required? |
| Read replica | Scaling reads, isolating workloads | Is replication lag acceptable? |

**Do not equate IOPS with API requests/second.** One request may read multiple pages, trigger multiple I/Os, or be served entirely from RAM cache.

### 3.3. Common Compute Tiers

| Tier | Orientation | Caveats |
| --- | --- | --- |
| **Burstable** | Dev/test, small workloads, or intermittent load | CPU credits/throttling and HA capabilities differ from other tiers |
| **General Purpose** | Majority of production OLTP | Balanced CPU/RAM, cost, and performance |
| **Memory Optimized** | Workloads needing large RAM/cache | Higher cost; must justify with metrics |

**SKUs/tiers/versions and HA, storage, and availability zone support vary by region and over time.** Never treat old VM SKU names as permanent assumptions. Check the available SKU list in your subscription/region at deployment time.

### 3.4. Resource Changes Can Cause Disruptions

Scaling vCores/tiers, changing storage/IOPS, enabling HA, or modifying network/server parameters may require **restarts, failovers, or brief disruptions** depending on the operation. Execute within maintenance windows and runbooks rather than assuming every change is dynamic/zero-downtime.

Provisioned storage scales up per policy/capacity, **but do not assume provisioned storage can be shrunk directly after growing**. Reclaiming space via `VACUUM` also does not automatically reduce provisioned storage or your Azure bill.

## 4. Network Architecture: Public Access and Private Access

### 4.1. Public Access with Firewall Rules

Flexible Server offers a public access model **governed by firewall rules**. The server uses an FQDN; clients outside the VNet can connect when public access is enabled, the source is within allowed ranges, and PostgreSQL authentication/TLS succeed.

~~~mermaid
flowchart LR
    D["Developer laptop / CI"]
    IP["Public client IP"]
    FW["Azure PostgreSQL\nfirewall rule"]
    PG["Flexible Server\npublic endpoint :5432"]
    D --> IP --> FW --> PG
~~~

**A firewall allowlist does not replace authentication.** Never open the entire Internet range just for convenient testing. When clients use NAT/VPN, the IP seen by the service may be a **public egress IP**, differing from the machine's private IP.

Note that an Azure option named similarly to "allow access from Azure services" in some firewall models can open connectivity to **a vast range of Azure sources**, not just your own subscription/resources. Do not enable it indiscriminately when strict security is required.

### 4.2. Private Access via VNet Integration

In the **private access (VNet integration)** model, Flexible Server is created inside a subnet **delegated** to the service, paired with an appropriate Private DNS Zone.

~~~mermaid
flowchart LR
    APP["AKS / App Service\nVNet-integrated"]
    VNET["VNet + routing"]
    DNS["Private DNS Zone\nhostname resolution"]
    SUBNET["Delegated subnet\nMicrosoft.DBforPostgreSQL/flexibleServers"]
    PG["Flexible Server\nprivate access"]
    APP --> VNET --> DNS
    VNET --> SUBNET --> PG
~~~

Key requirements:

- Subnet is properly delegated to `Microsoft.DBforPostgreSQL/flexibleServers` and meets service sizing/rules.
- Private DNS Zone is linked to the appropriate VNet(s).
- Client apps have routing to the server subnet via VNet, peering, or supported hybrid connectivity.
- NSGs/UDRs/firewalls do not block required flows; verify both DNS and platform management traffic if applicable.
- **Private DNS does not grant PostgreSQL login rights.** Valid users/tokens and TLS are still required.
- Do not assume a public server can be converted **in-place** to private VNet integration; choose the network mode at design time and verify supported migration/cutover paths.

### 4.3. Private Endpoint (Private Link) Differs from VNet Integration

Some Flexible Server configurations support **Private Endpoint/Private Link** under the public networking model depending on product conditions and timing. This is a **different private connectivity pattern** from deploying the server directly in a delegated subnet.

Do not conflate the two as "having a Private DNS Zone means private." Identify whether the server uses **VNet-integrated private access** or **public access with Private Endpoint support**, noting combination limits, DNS zones, firewalls, and actual network paths.

### 4.4. Private AKS Does Not Automatically Make PostgreSQL Private

An AKS cluster with a private API server **does not guarantee** all outbound paths to PostgreSQL are private. Conversely, a public API server can still run Pods connecting to PostgreSQL over a VNet/private endpoint. Verify **application data-plane routing and DNS**, rather than inferring from the AKS control-plane mode.

### 4.5. Choosing a Network Model

| Requirement | Selection Guidance |
| --- | --- |
| Dev/test from a laptop with known egress IP | Public access + specific firewall IP + TLS/auth |
| Production API and DB inside corporate network | Supported private access/VNet or Private Link |
| Access from on-premises | VPN/ExpressRoute, DNS forwarding, and private routing |
| Block Internet access to DB | Private-only data path; verify public access is disabled/unused |
| Multi-VNet or multiple consumers | Peering/hub-spoke/DNS/routing scoped to design |
| Deploying PaaS App Service/Functions | Client app **VNet integration** when DB is private |
| Access auditing required | Firewalls, identity, network logs, PostgreSQL auditing/logging |

**Network access is only one layer** of defense in depth: continue enforcing TLS, least-privilege roles, and monitoring.

## 5. Environment Preparation and Lab Safety Boundaries

### 5.1. Prerequisites

- An Azure subscription and resource group **authorized to create/modify billable resources**.
- Azure CLI `az` with a compatible PostgreSQL Flexible Server command group/extension.
- `psql` CLI and PostgreSQL client libraries.
- Verified region, supported PostgreSQL version, and SKU.
- Selected public IP allowlist or private subnet/DNS per requirements.
- App identity/DB roles, TLS root CA, and secret management plan.
- Estimated budget for compute/storage/backups/networking/monitoring.
- Lab cleanup plan; never share a production resource group.

### 5.2. Confirm Azure Context

~~~bash
az login

az account show \
  --query "{subscription:name, subscriptionId:id, tenantId:tenantId}" \
  --output json

# Switch only to your assigned subscription.
az account set --subscription "<SUBSCRIPTION_ID>"

RG="rg-pg-flex-lab"
LOCATION="southeastasia"
PGSERVER="pg-orders-unique-lab"
ADMIN="pgadminlab"

az postgres flexible-server --help
az postgres flexible-server create --help
~~~

Do not use `pg-orders-unique-lab` literally if already taken; public DNS names must be valid and globally unique per service rules.

### 5.3. Protecting Credentials

In labs, if using a PostgreSQL admin password:

- Generate a strong password with a secrets tool and store it in a vault.
- Never embed passwords in Bash history, Git, Dockerfiles, or application code.
- Where possible, use interactive input/secret injection; never put `--admin-password "password123"` in production docs.
- Once the server is created, use a dedicated app role rather than logging in as admin at runtime.
- Never paste connection strings, CA private keys, or outputs containing secrets into public tickets.

**This lesson does not automatically execute commands to create or delete Azure resources.** Every command below applies only in authorized environments and may incur costs.


## 6. Creating a Flexible Server and Reading Back Configuration

### 6.1. Picking the Right Option

Production apps requiring Internet isolation typically fit **private access** in a prepared VNet. For labs from a laptop with a fixed public egress IP, **public access + single-IP firewall** with TLS and dedicated users can work.

Never open `0.0.0.0/0` or allow all Azure services by default. Never spin up a billable server before receiving approval.

### 6.2. Azure CLI: Public Server Example Restricted to Lab IP

~~~bash
az login
az account show --query "{name:name, id:id}" --output json
az account set --subscription "<SUBSCRIPTION_ID>"

RG="rg-pg-flex-lab"
LOCATION="southeastasia"
PGSERVER="pg-orders-unique-lab"
ADMIN="pgadminlab"
CLIENT_IP="<APPROVED_PUBLIC_EGRESS_IP>"

# May incur costs; run only in an approved lab subscription/RG.
az group create --name "$RG" --location "$LOCATION"

# CLI may prompt interactively for password if supported by version.
az postgres flexible-server create \
  --resource-group "$RG" \
  --name "$PGSERVER" \
  --location "$LOCATION" \
  --admin-user "$ADMIN" \
  --tier GeneralPurpose \
  --sku-name Standard_D2s_v3 \
  --version 16 \
  --storage-size 128 \
  --public-access "$CLIENT_IP"
~~~

**Cross-check command template before running:** the server name must be unique; SKU `Standard_D2s_v3` and PostgreSQL 16 only work if supported in your region/subscription. Inspect `az postgres flexible-server create --help` and tier/version/storage limits. If CLI does not prompt for a password, use a secret manager/portal per policy; avoid placing passwords in command-line history.

**Never use the command above to create a private-only production database.** A public firewall allowlist is not a user identity control replacing PostgreSQL authentication.

### 6.3. Creating a Private VNet-Integrated Server

A standard workflow:

1. Create/select a VNet and dedicated subnet for Flexible Server.
2. Delegate the subnet to `Microsoft.DBforPostgreSQL/flexibleServers`; verify IP capacity and ensure no unrelated resources share the subnet.
3. Prepare the Private DNS Zone and link it to the VNet per service requirements.
4. Create Flexible Server in private network mode referencing the proper subnet/DNS.
5. Verify the FQDN resolves to a private IP from an actual client.
6. Verify TCP 5432, auth/TLS, and no unintended public paths remain.

Parameterized example—**do not run before networking is prepared**:

~~~bash
VNET="vnet-app-lab"
DELEGATED_SUBNET="snet-postgres"
PRIVATE_DNS_ZONE="private.postgres.database.azure.com"

az postgres flexible-server create \
  --resource-group "$RG" \
  --name "$PGSERVER" \
  --location "$LOCATION" \
  --admin-user "$ADMIN" \
  --tier GeneralPurpose \
  --sku-name Standard_D2s_v3 \
  --version 16 \
  --vnet "$VNET" \
  --subnet "$DELEGATED_SUBNET" \
  --private-dns-zone "$PRIVATE_DNS_ZONE"
~~~

**This is an alternative**, not a second command run on top of an already created public server. CLI syntax and VNet/Private DNS prerequisites vary across CLI versions. Verify deployment and Private Link/VNet integration behavior beforehand.

### 6.4. Reading Back Server Configuration

~~~bash
az postgres flexible-server show \
  --resource-group "$RG" \
  --name "$PGSERVER" \
  --query "{name:name, location:location, version:version, state:state, sku:sku, storage:storage, backup:backup, highAvailability:highAvailability}" \
  --output json

az postgres flexible-server db list \
  --resource-group "$RG" \
  --server-name "$PGSERVER" \
  --output table
~~~

`show` and `db list` are read-only. Record **resource ID, tier/SKU, region, zone, networking mode, backup window, HA status, owner, and budget** in the runbook; never record passwords.

## 7. Connecting with psql Over TLS

### 7.1. DNS and TCP

~~~bash
PGHOST="${PGSERVER}.postgres.database.azure.com"

nslookup "$PGHOST"
nc -vz "$PGHOST" 5432
~~~

In private mode, run from a machine/VM/Pod with routing and DNS to the private server. **Correct DNS does not mean firewall, TLS, and PostgreSQL roles are valid.**

### 7.2. TLS and Server Verification

- `sslmode=require` enforces TLS encryption, though server identity verification depends on client and CA setup.
- `sslmode=verify-ca` verifies the CA/trust chain.
- `sslmode=verify-full` verifies both the CA/trust chain and the **FQDN hostname**.
- `sslmode=disable` is unfit for production and may be rejected when TLS enforcement is enabled.

With an organization-approved root CA file:

~~~bash
CAFILE="/secure/certs/postgres-root-ca.pem"

# Enter password interactively or via an approved secret provider.
psql "host=$PGHOST port=5432 dbname=postgres user=$ADMIN \
sslmode=verify-full sslrootcert=$CAFILE"
~~~

`/secure/certs/postgres-root-ca.pem` is a placeholder path, not a file pre-created by this lesson. Never switch to `sslmode=disable` to hide CA/SNI errors.

### 7.3. Flexible Server Usernames

With PostgreSQL authentication, the admin username is typically **the plain name you created**, e.g., `pgadminlab`. Do not default to `pgadminlab@server` from older **Single Server** guides. Microsoft Entra authentication uses its own token/role mapping mechanism.

### 7.4. Inspecting the Session

Inside `psql`:

~~~sql
SELECT current_database(), current_user, version();
SHOW ssl;
SHOW max_connections;
SHOW TimeZone;

SELECT pid, usename, client_addr, state
FROM pg_stat_activity
WHERE pid = pg_backend_pid();
~~~

`psql` meta-command:

~~~text
\conninfo
~~~

**Never print all environment variables** to debug, as they may expose secrets.

## 8. PostgreSQL Hands-On: Schema, SQL, and Roles

### 8.1. Creating a Database

Log in as a PostgreSQL admin authorized to create databases:

~~~sql
CREATE DATABASE ordersdb;
~~~

In `psql`, switch databases:

~~~text
\c ordersdb
~~~

Production should deploy schema changes through **Flyway/Liquibase** or a reviewed migration tool, not ad-hoc DDL during peak traffic.

### 8.2. Orders Table and Indexes

~~~sql
CREATE SCHEMA IF NOT EXISTS sales;

CREATE TABLE sales.orders (
    id            bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    external_id   text NOT NULL UNIQUE,
    customer_id   bigint NOT NULL,
    amount_minor  bigint NOT NULL CHECK (amount_minor >= 0),
    currency      char(3) NOT NULL DEFAULT 'VND',
    status        text NOT NULL
                  CHECK (status IN ('NEW', 'PAID', 'CANCELLED')),
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_orders_customer_created
    ON sales.orders (customer_id, created_at DESC);

CREATE INDEX idx_orders_status_created
    ON sales.orders (status, created_at DESC);
~~~

- `external_id UNIQUE` supports **idempotency** when the same order event is reprocessed.
- `timestamptz` suits storing timestamps; apps should standardize on UTC.
- `amount_minor` stores monetary amounts in the **smallest currency unit** per contract; use `numeric(p,s)` when decimal precision is required.
- Indexes accelerate specific queries while consuming storage and write overhead.

### 8.3. Illustrative Transaction

~~~sql
BEGIN;

INSERT INTO sales.orders (
    external_id, customer_id, amount_minor, currency, status
)
VALUES ('ORD-1001', 21, 12500000, 'VND', 'NEW')
ON CONFLICT (external_id) DO NOTHING
RETURNING id;

COMMIT;
~~~

If a retry returns no `id` due to a unique conflict, the code must check business state before treating it as a success. **A PostgreSQL transaction does not cover** external side effects such as Service Bus, Kafka publishing, HTTP payments, or emails. Transactional outbox/idempotent consumers may be needed.

### 8.4. Least-Privilege Runtime Account

Create a dedicated application role; **never use admin in the application**:

~~~sql
CREATE ROLE app_runtime LOGIN;

GRANT CONNECT ON DATABASE ordersdb TO app_runtime;
GRANT USAGE ON SCHEMA sales TO app_runtime;

GRANT SELECT, INSERT, UPDATE, DELETE
ON ALL TABLES IN SCHEMA sales TO app_runtime;

GRANT USAGE, SELECT
ON ALL SEQUENCES IN SCHEMA sales TO app_runtime;
~~~

In `psql`, set the password interactively:

~~~text
\password app_runtime
~~~

To apply grants to future tables/sequences created by **the role running the command**:

~~~sql
ALTER DEFAULT PRIVILEGES IN SCHEMA sales
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_runtime;

ALTER DEFAULT PRIVILEGES IN SCHEMA sales
    GRANT USAGE, SELECT ON SEQUENCES TO app_runtime;
~~~

**`ALTER DEFAULT PRIVILEGES` does not retroactively modify existing objects and does not apply across arbitrary owner roles.** Use an explicit migration owner role, and never grant `CREATEROLE`, `CREATE DATABASE`, or superuser to `app_runtime`.

### 8.5. EXPLAIN and Indexes

~~~sql
SELECT id, external_id, status, amount_minor, created_at
FROM sales.orders
WHERE customer_id = 21
ORDER BY created_at DESC
LIMIT 20;

EXPLAIN
SELECT id, external_id, status, amount_minor, created_at
FROM sales.orders
WHERE customer_id = 21
ORDER BY created_at DESC
LIMIT 20;
~~~

`EXPLAIN (ANALYZE, BUFFERS)` actually executes the query to measure runtime stats. Be careful with write statements or heavy queries in production; never run large load tests unapproved.

## 9. Java/JDBC Connectivity and Connection Pooling

### 9.1. JDBC URL with TLS

~~~text
jdbc:postgresql://pg-orders-unique-lab.postgres.database.azure.com:5432/ordersdb?sslmode=verify-full&sslrootcert=/secure/certs/postgres-root-ca.pem
~~~

The CA path must exist inside the runtime/container and be accepted by the PostgreSQL JDBC driver. If relying on the JVM truststore, verify certificates/driver configuration explicitly rather than assuming every image trusts the server CA.

### 9.2. Spring Boot application.yml

~~~yaml
spring:
  datasource:
    url: ${DB_JDBC_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 10
      minimum-idle: 2
      connection-timeout: 30000
      max-lifetime: 1800000
  jpa:
    open-in-view: false
~~~

`DB_JDBC_URL`, `DB_USERNAME`, and `DB_PASSWORD` must be supplied via environment/configuration/secret managers and kept out of Git/logs. Hikari numbers are **illustrative starting points**, not universal standards.

### 9.3. Java JDBC with PreparedStatement

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

public final class OrdersReader {
    public static void main(String[] args) throws Exception {
        String url = System.getenv("DB_JDBC_URL");
        String username = System.getenv("DB_USERNAME");
        String password = System.getenv("DB_PASSWORD");
        if (url == null || username == null || password == null) {
            throw new IllegalStateException("Missing DB configuration");
        }

        String sql = "SELECT external_id, status, amount_minor " +
                     "FROM sales.orders WHERE customer_id = ? " +
                     "ORDER BY created_at DESC LIMIT ?";

        try (Connection conn =
                 DriverManager.getConnection(url, username, password);
             PreparedStatement stmt = conn.prepareStatement(sql)) {
            stmt.setLong(1, 21L);
            stmt.setInt(2, 20);
            try (ResultSet rows = stmt.executeQuery()) {
                while (rows.next()) {
                    System.out.printf(
                        "%s %s %d%n",
                        rows.getString("external_id"),
                        rows.getString("status"),
                        rows.getLong("amount_minor")
                    );
                }
            }
        }
    }
}
~~~

Requires an `org.postgresql:postgresql` dependency compatible with your Java/driver version. The snippet uses `DriverManager` for demonstration; web applications should use a `DataSource` and connection pooling.

### 9.4. Sizing Pool by Replica Count

~~~text
AKS replicas:              12
Hikari maxPoolSize:        10
Potential app DB sessions: 12 × 10 = 120
~~~

Beyond those 120 sessions, account for workers, admins, migrations, and monitoring. Never size total connections right against `max_connections`; keep headroom for failovers and reconnects.

### 9.5. PgBouncer

**PgBouncer** reduces PostgreSQL backend connections when serving many short-lived clients. Flexible Server provides built-in or supported PgBouncer options in certain tiers/configs, but you must verify **support/ports/versions and permissions** beforehand.

- **Session pooling:** preserves session semantics more closely, with lower multiplexing gains.
- **Transaction pooling:** optimizes short transactions; verify compatibility with session variables, temp tables, advisory locks, and prepared statements depending on driver/config.
- A pooler does not solve slow SQL, missing indexes, deadlocks, or insufficient IOPS.
- Do not switch the JDBC endpoint to the PgBouncer port before testing TLS, identity, and app behavior.


## 10. High Availability: Primary, Standby, and Failover

### 10.1. Why Can a Primary Experience Disruptions?

A Flexible Server primary can be impacted by hardware faults, instance failures, maintenance/restarts, and availability zone outages. Since all writes hit the primary, apps need a plan to reconnect and handle incomplete transactions.

In supported tiers/regions, Azure provides **high availability (HA)** to reduce downtime. HA must be enabled and configured; **do not assume every server automatically has a standby**.

### 10.2. Same-Zone and Zone-Redundant HA

| Configuration | Characteristics | Key Takeaway |
| --- | --- | --- |
| HA disabled | Primary only per base config | Vulnerable to instance/zone faults and maintenance restarts |
| Same-zone HA | Standby in the same zone, where supported | Protects against some instance faults, not a full zone outage |
| Zone-redundant HA | Standby in another zone, where supported | Separates zone failure domains; still within one region |

~~~mermaid
flowchart LR
    APP["Java API + HikariCP"]
    DNS["PostgreSQL server FQDN"]
    P["Primary\nZone 1"]
    S["HA standby\nZone 2 when supported"]
    MON["Azure Monitor"]
    APP --> DNS --> P
    P -.->|"HA replication"| S
    P -.-> MON
    S -.->|"Failover role"| DNS
~~~

HA can use **synchronous replication** per service design to protect committed transactions. However, **RPO/RTO, failover duration, and support levels** must be checked against your SLA/tier/region; never make an unconditional promise that "every outage has RPO=0 and RTO=0."

### 10.3. How Failover Affects the Application

During failover, existing connections may drop. HikariCP must evict broken connections, the app must reconnect via the standard hostname, and handle transient exceptions.

A tricky scenario: the client sends `COMMIT` and loses the connection before receiving the response. **You cannot always tell whether the transaction committed** from the exception alone. Use `external_id UNIQUE` and idempotency keys to retry safely.

Never click **force failover** in production to test. Rehearse in staging with change approval, measuring error rates, recovery duration, connection behavior, DNS, transaction state, and logs.

### 10.4. HA Does Not Automatically Provide Read Scale or Disaster Recovery

An HA standby is dedicated to availability, **not a default read replica for API SELECT queries**. During a **full-region outage**, both primary and HA standby can be lost together. Systems needing cross-region DR require a separate architecture and rehearsed recovery.

## 11. Backups, PITR, and Disaster Recovery

### 11.1. Automated Backups

Flexible Server offers service-managed backups combining base data and WAL logs required for supported restore flows. **Backups and HA serve different goals**:

- **HA:** restores service availability from instance/zone faults per configuration.
- **Backup/PITR:** restores data to a point in time within the supported retention window.
- **DR:** recovers from regional failures or incidents larger than the HA domain.

Backup retention, geo-redundancy, storage costs, and restore limits vary by tier/region/configuration. Never adopt a default day count from an old tutorial as a production standard.

### 11.2. Point-in-Time Restore

Suppose a faulty migration ran at 10:25 UTC while data was healthy until 10:23 UTC. If backup retention/WAL allow, trigger **PITR to 10:23 UTC**.

~~~mermaid
flowchart LR
    BACK["Backup baseline"]
    WAL["Change logs / WAL"]
    POINT["Restore point\n10:23 UTC"]
    NEW["Restored Flexible Server\nnew endpoint"]
    CUT["Validate data\nand cut over"]
    BACK --> WAL --> POINT --> NEW --> CUT
~~~

PITR typically creates a **new server**, rather than rewinding the existing primary in-place. This affects:

- FQDN/connection strings, firewalls/Private DNS.
- Compute/storage of the restored server and added cost.
- Roles/extensions/configurations needing verification.
- Traffic cutover and preventing split writes to both servers.
- Data validation and rollback workflows.

### 11.3. Restore Runbook

1. Stop the faulty process or migration from causing further corruption.
2. Record the UTC failure time and target restore timestamp.
3. Confirm the restore point lies within retention.
4. Provision the restored server via Azure-supported restore into the right network/region.
5. Verify rows, constraints, extensions, users, grants, and application behavior.
6. Run smoke tests without causing production side effects.
7. Cut over database endpoint/secrets/app config within a change window.
8. Monitor 5xx errors, transaction failures, connections, and p95 latency.
9. Clean up the unused old/restored server **only after approval**.

**Never delete the primary hoping backups auto-restore.** For localized data corruption, selective extraction from the restored copy is sometimes better than cutting over the entire application.

### 11.4. Geo-Restore, Cross-Region, and RPO/RTO

Some configurations support geo-redundant backups/geo-restore per tier/region. Cross-region backup/replication can be **asynchronous**, so do not assume zero data loss. RTO also includes provisioning the restored server, updating DNS/connections, and validation.

Design parameters to declare:

- **RPO (Recovery Point Objective):** acceptable time-measured data loss.
- **RTO (Recovery Time Objective):** maximum target outage duration.
- Failure scope: process/VM, zone, or region.
- Data residency and compliance.
- Backup retention and frequency of restore drills.
- Owners and cutover/rollback runbooks.

### 11.5. pg_dump vs. Service Backups

| Backup/Recovery Method | Objective |
| --- | --- |
| Automated backup/PITR | Point-in-time server recovery |
| `pg_dump` + `pg_restore` | Selective schema/data export/import, migrations |
| Read replica | Scaling reads; does not undo accidental deletes |
| HA standby | Failover availability; does not replace PITR |
| Cross-region recovery | Supported DR with its own lag and RPO/RTO |

`pg_dump` does not provide PITR; for large databases, verify version, network, storage, backup/restore duration, and consistency.

## 12. Read Replicas, Replication Lag, and CDC

### 12.1. Read-Only Replicas

A primary handling order writes can get starved of CPU/I/O by analytics reports. **Read replicas** in supported configs offload SELECT/reporting queries to another instance.

~~~mermaid
flowchart LR
    APP["Order write API"]
    P["Primary PostgreSQL\nRead / Write"]
    R1["Read replica\nReports"]
    R2["Read replica\nAnalytics"]
    REP["Reporting API"]
    ANAL["Analytics worker"]
    APP --> P
    P -.->|"Async replication"| R1 --> REP
    P -.->|"Async replication"| R2 --> ANAL
~~~

**A replica is not a second write endpoint.** The app must route writes to the primary and appropriate reads to the read-only replica, planning for replica lag or unavailability.

### 12.2. Read-After-Write Consistency

Right after an `INSERT` on the primary, reading immediately from a replica may not return the new row. This is a natural consequence of **asynchronous replication**, not necessarily an API bug.

How to handle it:

- Requests needing **read-your-writes** read from the primary.
- Reporting/analytics tolerating slight delay can read from replicas.
- Monitor replication lag and define an SLO.
- If falling back to the primary, throttle load so the primary isn't overwhelmed.
- Never split a single consistent transactional flow arbitrarily across primary and replica connections.

### 12.3. Causes of Replica Lag

- Primary generates WAL faster than the replica applies it.
- Replica lacks sufficient CPU, RAM, or IOPS.
- Network/region latency.
- Heavy read queries holding resources/locks on the replica.
- Replication limits, maintenance, or restarts.

Adding more replicas does not fix slow SQL queries. Protect the primary during replica issues with capacity budgets and graceful fallback.

### 12.4. HA Standby Differs from Read Replica

| Property | HA Standby | Read Replica |
| --- | --- | --- |
| Objective | Availability/failover | Scale SELECTs and isolate reporting |
| Replication type | Service HA replication | Typically async |
| App read endpoint | Not by default | Provides read-only endpoint |
| Automatic failover | Per HA mechanism | Requires separate promotion/cutover check |
| Consistency | Per HA SLA | Can be stale per lag |
| Replaces backups? | No | No |

### 12.5. Logical Replication / CDC

PostgreSQL provides **logical replication** and WAL decoding for Change Data Capture. On managed Flexible Server, verify:

- PostgreSQL version/extension allowlist.
- Server parameters for logical replication/WAL.
- Permissions for replication users/publications/slots.
- Storage growth if a replication slot stalls.
- Initial snapshots and schema change handling.

**Logical replication is not a physical read replica or HA.** Never enable a test logical slot and abandon it, as unconsumed WAL accumulates and fills storage.

## 13. Authentication: PostgreSQL Roles, Microsoft Entra ID, and Secrets

### 13.1. Password Authentication

A PostgreSQL account like `app_runtime` derives rights from GRANTs on databases/schemas/tables/sequences. Best practices:

- Separate admin, migration, runtime, and readonly roles.
- Store passwords in Key Vault/secret stores.
- Rotate credentials cleanly with connection pool compatibility.
- Never place secrets in source code, CLI history, Dockerfiles, or logs.
- Avoid logging queries with sensitive literal inputs.

### 13.2. Microsoft Entra Authentication

Flexible Server supports **Microsoft Entra authentication** per service conditions. For Azure apps, managed identity/workload identity reduces long-lived PostgreSQL passwords.

High-level flow:

1. Configure Entra authentication and an Entra administrator per workflow.
2. Map users/groups/principals to PostgreSQL roles per supported method.
3. Grant PostgreSQL privileges on exact schemas/tables.
4. Client acquires an access token with the right audience/scope.
5. Pass the token to the driver per supported auth flow.
6. Implement token refresh for pools/reconnects; never cache expired tokens indefinitely.
7. Independently verify networking, FQDN, and TLS.

**Azure RBAC Contributor on the PostgreSQL Azure resource does not automatically grant SELECT inside PostgreSQL.** The Azure control plane and PostgreSQL data plane are separate authorization domains.

### 13.3. Identity, Networking, and TLS Must All Align

| Layer | Question |
| --- | --- |
| Azure RBAC | Who can create/modify the Azure server or network? |
| Entra/PostgreSQL login | Does the server recognize the principal to log in? |
| PostgreSQL GRANT | Does it have SELECT/INSERT on the right schema/table? |
| DNS/route/firewall | Can the client reach port 5432? |
| TLS certificate | Are hostname and CA verified? |
| Secret lifecycle | Are credentials/tokens rotated/refreshed securely? |

Never fix an authorization failure by widening the firewall or granting an admin role. Classify the root cause first.

## 14. Query Tuning, Indexes, VACUUM, and Statistics

### 14.1. Key PostgreSQL Signals

- CPU, memory, IOPS, storage throughput, and disk space.
- Active/idle connections, pool wait times, connection failures.
- Transactions/sec, lock waits, deadlocks.
- Query p95/p99, temp files, long transactions.
- Table/index bloat, autovacuum/analyze activity.
- Replica lag, WAL retention, and failover events.

A slow server can stem from **SQL plans, locks, CPU, I/O, or a connection storm**; never scale SKUs before inspecting metrics.

### 14.2. Diagnostic Statistics Queries

~~~sql
SELECT datname, numbackends, xact_commit, xact_rollback,
       blks_read, blks_hit
FROM pg_stat_database
WHERE datname = current_database();

SELECT pid, usename, state, wait_event_type, wait_event,
       now() - query_start AS elapsed,
       left(query, 120) AS statement_preview
FROM pg_stat_activity
WHERE datname = current_database()
  AND pid <> pg_backend_pid()
ORDER BY elapsed DESC NULLS LAST
LIMIT 20;
~~~

`pg_stat_activity.query` may contain literal data, so avoid pasting full query text into unsecured tickets. Visibility of stat columns depends on role privileges.

### 14.3. EXPLAIN and Execution Plans

~~~sql
EXPLAIN
SELECT external_id, status
FROM sales.orders
WHERE customer_id = 21
ORDER BY created_at DESC
LIMIT 20;

-- Run only when permitted: actually executes SELECT to measure.
EXPLAIN (ANALYZE, BUFFERS)
SELECT external_id, status
FROM sales.orders
WHERE customer_id = 21
ORDER BY created_at DESC
LIMIT 20;
~~~

Check index vs. sequential scans, estimated vs. actual rows, sorts, temp files, and buffer reads. `EXPLAIN ANALYZE` on write SQL modifies data; never run `EXPLAIN (ANALYZE) UPDATE/DELETE` blindly in production.

### 14.4. pg_stat_statements and Performance Insights

Flexible Server can provide query performance insights and supports `pg_stat_statements` per version/extension allowlist. Before enabling, check preloading, server parameters, permissions, and potential restart requirements.

~~~sql
-- Only when the extension and permissions are supported by the server.
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
~~~

Do not assume `CREATE EXTENSION` succeeds automatically on every server. Query statistics may reveal sensitive data; apply appropriate retention and access controls.

### 14.5. Autovacuum and Table Bloat

PostgreSQL MVCC retains dead tuples after UPDATE/DELETE until vacuum cleans them. If autovacuum falls behind or long-running transactions hold snapshots open, bloat and disk pressure increase.

~~~sql
SELECT schemaname, relname, n_live_tup, n_dead_tup,
       last_autovacuum, last_autoanalyze
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 20;
~~~

Remediation:

- Monitor dead tuples, long transactions, and disk growth.
- Tune autovacuum/analyze within managed server limits.
- Run `VACUUM ANALYZE` appropriately during permitted windows.
- Avoid `VACUUM FULL` outside maintenance windows due to heavy locking and disk space requirements.
- Deleting rows or running `VACUUM` does not automatically shrink provisioned storage or reduce the Azure bill immediately.

### 14.6. N+1, Batching, and Transactions

For Java/Spring Data JPA:

- Avoid **N+1 queries** from misplaced lazy loading.
- Use prepared statements, batch inserts/updates, and short transactions.
- Index based on actual query patterns, not guesswork.
- Set statement timeouts and pool wait timeouts matching SLOs.
- Avoid `SELECT *` on wide tables when only a few columns are needed.
- Evaluate keyset pagination instead of massive `OFFSET` values.
- Use `COPY` for bulk imports after checking resources/permissions.


## 15. Azure Monitor, Logs, Alerts, and SLOs

### 15.1. Two-Layer Monitoring

Azure Monitor reflects the health of **managed resources**: CPU, memory, storage, I/O, connections, availability, replication, and other metrics per feature/tier. PostgreSQL dynamic views/logs reflect **SQL and session context**.

| Source | Signals | Question |
| --- | --- | --- |
| Azure Monitor metrics | CPU, memory, IOPS, storage percentage | Is compute/storage bottlenecked? |
| PostgreSQL connection metrics | Active/succeeded/failed connections | Are app pool sizing and auth healthy? |
| PostgreSQL `pg_stat_activity` | Queries, wait events, states | Which query/lock is blocking? |
| Query insights / `pg_stat_statements` | Query frequency, total time, mean time | Which SQL consumes the most resources? |
| PostgreSQL logs | Authentication errors, errors, slow queries | Is the error at the DB or client? |
| Azure Activity Log | Server/parameter/network changes | Who recently changed Azure config? |
| HA/replica metrics | Failover events, replica lag where available | Are availability/replication meeting SLO? |
| App Service/AKS/App Insights | API p95/p99, pool timeouts | Are errors impacting actual users? |
| Cost Management | Compute/storage/backup/network charges | Is the budget being exceeded? |

Do not assume every metric exists on every tier/version. List **metric definitions** on the actual resource before picking names/dimensions.

### 15.2. Read-Only Azure CLI Commands

~~~bash
PG_RESOURCE_ID=$(az postgres flexible-server show \
  --resource-group "$RG" \
  --name "$PGSERVER" \
  --query id \
  --output tsv)

az monitor metrics list-definitions \
  --resource "$PG_RESOURCE_ID" \
  --output table

az monitor metrics list \
  --resource "$PG_RESOURCE_ID" \
  --output json
~~~

The last command returns metrics using current defaults; in a real dashboard, specify metric name, granularity, timeframe, and dimensions. Never use a single CPU snapshot to justify scaling compute.

### 15.3. Diagnostic Settings and Query Logs

Configure per policy:

- Diagnostic settings streaming supported logs/metrics to Log Analytics, Storage, or Event Hubs.
- PostgreSQL server parameters for logging/slow queries per supported features.
- Retention and workspace access controls.
- Masking/minimizing sensitive data in SQL text.
- Propagating correlation IDs from Java requests through DB connections/tracing where possible.

**Logging all SQL statements** can raise costs, hurt performance, and expose input values; evaluate policy first. Restrict log readers when PII may appear.

### 15.4. Essential Alerts

- CPU/IOPS/throughput or memory sustained near limits.
- Storage usage rising rapidly, nearing provisioned capacity.
- Rising failed connections/auth failures.
- Active connections approaching `max_connections` or rising pool wait time.
- Query p95/p99 exceeding SLO, long transactions, deadlocks.
- Abnormal availability/failover or HA states.
- Replica lag exceeding allowable read staleness.
- Backup/restore failures per supported telemetry.
- Unexpected cost spikes or scaling outside change windows.

Alerts must specify **owner, severity, threshold, sustained duration, and runbook**. A one-minute CPU spike during a known batch may be fine; sustained CPU saturation with API 5xx requires immediate action.

### 15.5. End-to-End SLOs

Illustrative business SLO:

~~~text
POST /orders:
  p95 end-to-end latency < 300 ms
  success rate             >= 99.9% within defined window
  No duplicate orders on retry

GET /orders/{id} from replica:
  p95 latency              < 150 ms
  Read staleness           <= 5 seconds (business target)
~~~

These are **illustrative application targets**, not an Azure-guaranteed SLA. DB availability is one component and cannot guarantee API SLOs amid buggy code, pool exhaustion, or network faults.

## 16. Maintenance, Upgrades, and Server Parameter Governance

### 16.1. Maintenance Windows

Flexible Server performs routine maintenance/patching per schedule and service policy. Some operations trigger restarts/failovers or brief connection drops.

Design:

1. Choose a maintenance window aligned with business hours where permitted.
2. Notify API, SRE, DBA, and workload owner teams.
3. Keep metrics/alerts, recovery runbooks, and escalation paths ready.
4. Verify client retry/idempotency before maintenance.
5. After maintenance, check API latency, failed connections, and replication health.

Do not mistake a maintenance window for a guarantee that **zero incidents happen outside it**; unexpected failovers/incidents can still occur.

### 16.2. PostgreSQL Minor vs. Major Upgrades

- **Minor version/patch:** bug and security fixes within the same major version per support schedule.
- **Major version upgrade:** can alter extension compatibility, planner behavior, SQL behavior, client drivers, and require migration/cutover.

Major upgrade workflow:

1. Check source/target versions and feature eligibility.
2. Audit extensions, server parameters, reserved keywords, queries, and JDBC versions.
3. Prepare backup/PITR plan and a matching staging environment.
4. Test schema migrations, restores, performance regressions, and failover.
5. Evaluate **in-place vs. migration** upgrade paths supported by service/tier.
6. Plan cutover/rollback; note that rolling back a major upgrade is rarely a single parameter flip.
7. Monitor post-upgrade and clean up obsolete configs.

### 16.3. Server Parameters

PostgreSQL exposes parameters such as `max_connections`, `work_mem`, `shared_buffers`, `log_min_duration_statement`, `statement_timeout`, and `autovacuum_*`. On managed Flexible Server:

- Some parameters are **read-only or Azure-managed**.
- Some can be modified via Azure portal/CLI but **require a restart**.
- Some apply only within specific tier limits.
- Raising `work_mem`/`max_connections` increases memory pressure and OOM risk.
- Enabling logical replication changes WAL/slot behavior.

Read-only parameter listing example:

~~~bash
az postgres flexible-server parameter list \
  --resource-group "$RG" \
  --server-name "$PGSERVER" \
  --output table
~~~

Before running `parameter set`, check defaults/limits, restart requirements, and test in staging. Never change 20 parameters at once, or root-causing regressions becomes nearly impossible.

### 16.4. Stop/Start and Lab Cost Savings

Some configurations support **stop/start** to reduce compute charges when a lab is unused. However:

- Stopping does not eliminate all storage/backup/networking fees.
- Stop duration limits and auto-start rules apply per service/tier.
- HA, replicas, compute, or network settings can restrict stopping.
- Never use stop as a production HA strategy.
- Upon restart, verify connectivity, app pools, and scheduled workloads.

Use stop only after confirming server support and authorization; never let scripts accidentally stop production databases.

## 17. Production Security: Data, Network, Roles, and Auditing

### 17.1. Defense in Depth

~~~mermaid
flowchart LR
    APP["Application identity"]
    NET["VNet / Private DNS\nNSG / Firewall"]
    TLS["TLS verify-full"]
    AUTH["PostgreSQL / Entra auth"]
    RBAC["DB GRANT + Row policy"]
    DATA["PostgreSQL tables"]
    LOG["Audit / Monitoring"]
    APP --> NET --> TLS --> AUTH --> RBAC --> DATA
    AUTH -.-> LOG
    DATA -.-> LOG
~~~

Every layer matters:

- **Network:** shrinks attack surface and blocks unauthorized sources.
- **TLS:** encrypts traffic in transit and verifies server identity.
- **Authentication:** verifies the connecting principal.
- **Authorization:** restricts database/schema/table/row actions.
- **Audit/Monitor:** detects misconfigurations and suspicious access.

### 17.2. Encryption Responsibilities

Azure-managed databases provide encryption at rest per platform policy. Some configurations support **customer-managed keys (CMK)** via Key Vault/managed identity per tier/feature eligibility. If CMK is needed:

- Define compliance requirements and Key Vault administration rights.
- Check Key Vault availability, key rotation, soft delete/purge protection per policy.
- Assess consequences if a key is revoked or access expires.
- Test recovery/restore under the matching encryption setup.
- Never assume every server/HA/replica supports switching encryption options in-place.

**Encryption at rest does not replace TLS in transit** and does not enforce SQL data authorization.

### 17.3. Keep PII Out of Connection Logs

Avoid:

- Printing JDBC URLs containing usernames/passwords or tokens.
- Logging full SQL values, credit card numbers, or access tokens.
- Pasting raw `pg_stat_activity.query` into public tickets.
- Storing database dumps in buckets with overly broad access.
- Using admin logins for app runtime.

When auditing is required, choose Azure-supported extensions/logging features and govern retention and read access. Never attempt unauthorized audit extensions on Flexible Server.

### 17.4. Row-Level Security (RLS) for Multi-Tenancy

When a database hosts multiple tenants, PostgreSQL **Row-Level Security** can add row-level access controls, provided:

- Roles, policies, table ownership, and session context are properly designed.
- The app never sets `tenant_id` directly from untrusted user input.
- Under connection pooling/transaction pooling, session state is never assumed to persist cleanly across requests.
- RLS **does not replace** networking, auth, schema reviews, or application authorization.
- Automated tests prove Tenant A cannot read/write Tenant B's rows.

Conceptual policy example—**not a complete production design**:

~~~sql
-- Illustrative only when table has tenant_id and proper roles/policies.
-- ALTER TABLE sales.orders ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY tenant_filter ON sales.orders
-- USING (tenant_id = current_setting('app.tenant_id')::text);
~~~

Do not apply these commented lines verbatim to the lab schema (the table lacks `tenant_id`). Establish a clear trust model and test across distinct PostgreSQL roles before enabling.

### 17.5. Network Security Review

- Periodically audit public firewall rules and remove stale IPs.
- Verify Private DNS Zone links, peering, UDRs, and NSGs.
- Restrict outbound database access from unneeded workloads.
- Scope private endpoints/VNet integration to actual connection sources.
- Separate Dev/Staging/Prod DBs and credentials as required.
- Enforce least privilege for both Azure roles and PostgreSQL roles.
- Ensure backups/restored copies comply with data residency and access policies.

## 18. Cost and Capacity Planning

### 18.1. Cost Components

| Component | Determining Factors |
| --- | --- |
| Compute | Tier, vCores, SKU, HA/standby, and provisioned hours |
| Storage | Provisioned GiB, auto-grow, storage performance/IOPS |
| Backups | Retention, additional storage, redundancy per billing policy |
| Read replicas | Compute/storage per replica and networking |
| Networking | Egress, Private Endpoint, NAT, data transfer |
| Monitoring | Log Analytics ingestion, retention, alerts |
| Key Vault | Access operations/keys per config |
| DR environment | Warm/cold standbys, test restored servers |
| Application | App Service/AKS instances, CPU, connection pools/traffic |

**Prices vary by region/SKU/tier/time and agreements.** Never treat a fixed USD figure as a promise. Use the Azure Pricing Calculator and Cost Management with actual selections.

### 18.2. Sizing by Workload

A system handles 400 API requests/second, each averaging two SQL queries:

~~~text
Request rate       = 400 req/s
SQL per request    = 2
SQL query rate     ≈ 800 queries/s
~~~

Yet 800 queries/s is **insufficient** to size vCores/IOPS. A `SELECT` reading 1 row from cache differs drastically from scanning 10 million rows. Load test and measure:

- p50/p95/p99 query latency.
- CPU/memory, cache hit ratio, IOPS/throughput.
- Index access, locks, temp spills.
- Concurrent transactions and connections.
- Peak traffic, growth forecasts, and retention.
- Downstream/retry behavior during failover.

### 18.3. From Hikari Pool to max_connections

Example:

~~~text
App instances:                    16
Pool max per instance:            12
Potential DB sessions:            192

Background worker sessions:        20
Monitoring/migrations reserve:     10
Total potential:                   222
~~~

If the server's safe connection budget is below 222, shrink pool sizes or introduce pooling architecture rather than blindly raising `max_connections`. Connections consume memory, especially with concurrent queries/`work_mem`.

### 18.4. Protecting Capacity During Failover

Load can spike temporarily after failover as all app instances reconnect/retry simultaneously:

- Use exponential backoff with jitter.
- Configure max retry budgets and circuit breakers.
- Throttle pool creation bursts.
- Store idempotency keys to avoid duplicate transactions.
- Watch `remaining connection slots`/CPU and HTTP 5xx.
- Have a load-shedding plan while the DB cache warms up.

### 18.5. FinOps

- Use General Purpose when SLOs are met instead of defaulting to Memory Optimized.
- Scale using metrics, not intuition.
- Clean up unused replicas/labs/restored servers with change approval.
- Monitor backup retention and growing storage charges.
- Trim log spam while retaining mandatory audits.
- Enable budgets/alerts with clear resource tags and owners.
- Optimize queries/indexes before adding compute/IOPS when SQL is the root cause.


## 19. Flexible Server Diagnostic Runbook: Connectivity, Performance, and Availability

### 19.1. Quick Triage Table

| Symptom | Possible Cause | Diagnostic Step |
| --- | --- | --- |
| `could not translate host name` | Wrong DNS, broken private zone/link | `nslookup` from actual client/network |
| TCP timeout port 5432 | Firewall, NSG/UDR, VPN, routing | `nc -vz host 5432`, network access mode |
| `no pg_hba.conf entry` or similar | Network source/TLS/auth policy rejected | Firewall/network mode/TLS; do not edit OS `pg_hba` |
| `password authentication failed` | Wrong user/password, role, secret rotation | Correct Flexible Server user, credentials, logs |
| Entra token fails to log in | Expired audience/token, unmapped role | Entra config, PostgreSQL role, refresh |
| TLS certificate verify failed | CA trust, SAN/hostname, cert chain | `sslmode=verify-full`, CA/FQDN |
| `too many connections` | App replicas × pool size exceeds budget | `pg_stat_activity`, Hikari active/idle |
| HTTP API 500/timeout, low DB CPU | Pool wait, locks, network, or SQL exception | Hikari metrics, DB logs, query waits |
| Sustained 95% DB CPU | Heavy SQL, burst, undersized tier | Query insights, indexes, concurrency |
| IOPS/storage pressure | Table scans, WAL, bloat, storage growth | Azure metrics, `pg_stat_user_tables` |
| Blocked queries | Long transaction/row locks/deadlocks | `pg_stat_activity` wait events |
| Table exists but role cannot SELECT | Missing grants/schema USAGE | `\dp`/`\dn+` in psql, GRANT |
| App misses recently written row | Reading from lagging async replica | Read from primary or monitor replica lag |
| Disconnect errors during failover | Pool holding stale connections | Reconnect/backoff/idempotency |
| PITR restore missing certain rows | Timestamp picked before commit | Verify UTC/commit/restore point |
| Maintenance causes 5xx | Restart, failover, aggressive retries | Runbook, app traces, DB activity |
| Costs rise despite light dev usage | SKU, HA/replica/restored server, storage | Cost Management, resource inventory |

**Never try to fix every error by opening the firewall to the Internet or adding vCores.** Start with evidence at the right layer.

### 19.2. Step 1 — Identify the Azure Target

Record server name, FQDN, subscription, RG, region, tier, network mode, and UTC timestamp. Read-only commands:

~~~bash
az account show --output json

az postgres flexible-server show \
  --resource-group "$RG" \
  --name "$PGSERVER" \
  --query "{name:name,state:state,version:version,sku:sku,storage:storage,highAvailability:highAvailability}" \
  --output json
~~~

If the app points to a staging FQDN while your environment config points to production, never alter production firewalls/roles to chase symptoms.

### 19.3. Step 2 — DNS and Networking

From the **actual container/VM/runner running the app**:

~~~bash
nslookup "$PGHOST"
nc -vz "$PGHOST" 5432
~~~

If public mode: verify the exact **public egress IP** and firewall rule. If private mode: verify subnet delegation, Private DNS links, peering, client VNet integration, and NSGs/UDRs.

**Never use success from a laptop to conclude an AKS Pod has the same route.** Each source has a distinct DNS/egress path.

### 19.4. Step 3 — TLS and Authentication

From an authorized network:

~~~bash
psql "host=$PGHOST port=5432 dbname=postgres user=$ADMIN \
sslmode=verify-full sslrootcert=$CAFILE"
~~~

Interpret errors:

- Certificate/hostname → verify FQDN, CA chain, and client trust.
- Password → secret, username, role, and rotation.
- Entra token → principal mapping, token lifetime/refresh, and audience.
- Permission denied on table → PostgreSQL grants, not Azure firewall.

Never paste credentials into unapproved tools or use `sslmode=disable` as a workaround.

### 19.5. Step 4 — Connections and Query Waits

~~~sql
SELECT count(*) AS total_connections
FROM pg_stat_activity;

SELECT usename, state, count(*) AS sessions
FROM pg_stat_activity
GROUP BY usename, state
ORDER BY sessions DESC;

SELECT pid, usename, wait_event_type, wait_event,
       now() - xact_start AS transaction_age
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY transaction_age DESC NULLS LAST
LIMIT 20;
~~~

These queries are normally read-only, though detail visibility may be restricted. Never terminate app sessions with `pg_terminate_backend` before confirming the owner and consequences.

If connections are high while queries sit idle, inspect **idle sessions** and `Hikari maximumPoolSize × number of replicas`. For long transactions/locks, trace the code path and query holding the transaction open.

### 19.6. Step 5 — Bottleneck-Specific Performance

- **High CPU + slow queries:** inspect query plans, missing indexes, joins, JPA N+1.
- **High IOPS:** inspect sequential scans, bloat, caching, bulk jobs.
- **Growing storage:** distinguish real data, indexes, temp files, and WAL/replication slots.
- **Rising pool wait with low CPU:** pool limits, connection leaks, networking, or lock waits.
- **Replica lag:** measure primary write rate, replica capacity, and read workload.
- **Rising 5xx after failover:** inspect connection pool recovery and retry storms.

Gather evidence before scaling or changing parameters repeatedly. For load tests, use staging with representative data and explicit approval.

### 19.7. Step 6 — Backup/Restore and Failover Check

If the server is unavailable:

1. Classify single instance vs. zone vs. region incident.
2. Check server/HA status and Azure Monitor health signals.
3. Never force failover or delete resources while consequences remain unclear.
4. Review RTO/RPO and pre-planned fallback options.
5. If PITR is needed, select a valid UTC timestamp and restore to a separate server.
6. Verify data, permissions, networking, and TLS before cutover.
7. Monitor the app post-recovery and record the incident timeline.

### 19.8. Step 7 — Verify the Fix

After changes:

- FQDN/TLS/identity login works properly.
- PostgreSQL role holds only required privileges.
- Connection pools show no exhaustion.
- p95 API/DB latency and error rates meet SLOs.
- Storage/I/O metrics stabilize.
- HA/replica lag are healthy and restore plans remain viable.
- No unintended public access is exposed.
- Costs stay within budget; alerts remain active.

## 20. Comprehensive Hands-On Lab

### 20.1. Problem Statement

A company deploys a Java Order API on AKS, persisting data in PostgreSQL Flexible Server.

Requirements:

- **No public database exposure** to the Internet in production.
- DB reachable from AKS via VNet/private DNS.
- **Zone-redundant HA** where supported by region/tier and approved.
- **PITR** and backup retention meeting company standards.
- Account `app_runtime` restricted to CRUD on schema `sales`.
- App uses JDBC TLS `verify-full` and HikariCP.
- Dashboards for CPU, connections, storage, query latency, and replica lag (if replicas exist).
- Budget and alerts configured.
- Order data must be idempotent across API retries.

### 20.2. Acceptance Checklist

| Step | Action | Evidence |
| --- | --- | --- |
| 1 | Select subscription/RG/region | Verified `az account show` |
| 2 | Estimate tier/HA/storage pricing | Cost estimate sheet |
| 3 | Create/verify VNet + delegated subnet and Private DNS | Valid DNS zone/link, private path |
| 4 | Create private Flexible Server | FQDN routes properly within VNet |
| 5 | Configure backup retention and HA per requirements | Confirmed via server show/portal |
| 6 | Connect via `psql` using TLS `verify-full` | Valid CA/hostname |
| 7 | Create `ordersdb`, schema/tables/indexes | SQL queries succeed |
| 8 | Create `app_runtime`, verify grants | SELECT/INSERT succeed; DDL denied |
| 9 | Deploy Java JDBC/HikariCP | App tests INSERT/SELECT; no secrets logged |
| 10 | Monitor CPU, I/O, connections, and query plans | Azure Monitor + PostgreSQL stats |
| 11 | Rehearse PITR in an authorized environment | Restored server contains expected rows |
| 12 | Rehearse failover in staging with approval | Reconnect and idempotency work |
| 13 | Audit firewall/public exposure | Zero unintended public paths |
| 14 | Configure alerts/budgets and runbooks | Owners, thresholds, and escalation |
| 15 | Clean up lab per approval | Shared resources untouched |

### 20.3. Scenario A — Server Has Private IP, Yet API Times Out

App Service/AKS cannot resolve the PostgreSQL hostname or gets an unroutable private IP.

**Diagnosis:** inspect Private DNS Zone links/forwarding, client VNet integration, VNet peering/UDRs/NSGs, subnet delegation, and TCP 5432. Never open a public firewall just to "avoid fixing DNS."

### 20.4. Scenario B — TLS Connects, Yet Login Is Rejected

`psql` fails with password auth or Entra token error; `nc -vz` succeeds.

**Diagnosis:** networking works; focus on username/password or Entra role/token mapping, grants, and secret rotation. Do not loosen the firewall.

### 20.5. Scenario C — Java API Scales from 4 to 20 Replicas

Each replica configures a Hikari max pool size of 15.

\[
20\times15=300\text{ potential sessions}
\]

If the database's safe connection limit after subtracting admin/headroom is below 300, scaling the API can exhaust DB sessions even while CPU stays low.

**Remediation:** shrink pool sizes, adopt PgBouncer where compatible, inspect Hikari waits/leaks, DB `max_connections`, and transaction concurrency; never raise connection counts blindly without sufficient memory.

### 20.6. Scenario D — Transaction Fails Between COMMIT and Response

The app submits `ORD-1001`, loses connection during failover, and the client retries.

**Remediation:** rely on `external_id UNIQUE`/idempotency key, query to verify business state, and never generate a second order with a new ID. Retries must be bounded with backoff.

### 20.7. Scenario E — Replica Read Misses New Order

The API just inserted `ORD-1001` on the primary; a `GET` via replica misses the row.

**Remediation:** recognize replication lag; route read-your-writes to the primary or wait per consistency policy. Never treat a replica as strictly synchronous.

### 20.8. Scenario F — Migration Deletes Data Erroneously

A migration at 14:05 UTC accidentally drops/truncates table `orders`.

**Remediation:** stop offending writes/migrations, pick a restore point before 14:05, create a restored server via PITR, compare data, and cut over per runbook. Never attempt to "turn back the clock on the primary" or delete the original server immediately.

### 20.9. Scenario G — High CPU Driven by a Single Query

A JPA query loads every customer's orders across multi-table joins; p95 jumps to 4 seconds.

**Remediation:** run controlled `EXPLAIN`/`EXPLAIN ANALYZE`, check N+1, indexes, statistics, pagination, locks, and pools; scale compute only with matching evidence.

### 20.10. Scenario H — Sudden DB Cost Spike

There is an HA server, two read replicas, yesterday's PITR restored server, and surging Log Analytics ingestion.

**Remediation:** inventory resources, identify owners and usage status; remove the restored server only after approval, tune log ingestion/retention, and balance replicas against SLOs. Never turn off HA just to cut cost without reviewing RTO risk.

## 21. Safe Lab Environment Cleanup

### 21.1. Inspect Resources in the RG

~~~bash
az resource list \
  --resource-group "$RG" \
  --output table
~~~

**Never delete an RG containing shared or production resources.** Flexible Servers, backups, and read replicas may still serve multiple apps even if only one team notices.

### 21.2. Delete Only Lab-Dedicated RGs

~~~bash
# DESTRUCTIVE OPERATION.
# Run only after approval and confirming the RG belongs strictly to the lab.
az group delete \
  --name "$RG" \
  --yes
~~~

This command can destroy databases, networking, backups, and dependent resources inside the RG; it is not easily reversible. If VNets/Private DNS are shared, delete only specifically identified lab resources under change approval.

### 21.3. Post-Cleanup Checks

- No lingering lab servers/replicas/restored instances accruing charges.
- Database dumps/log secrets handled per policy.
- Lab role assignments, Private DNS records, and firewall rules reviewed.
- Backup/retention requirements remain intact.
- Azure Cost Management and alerts show no unexpected residual spend.

## 22. Self-Check Questions

**Q1.** How does Flexible Server differ from PostgreSQL installed on a VM?

**Answer:** Azure manages much of the service infrastructure, backups/maintenance/HA per configuration; the customer still manages SQL, schemas, permissions, connectivity, performance, and recovery drills. VMs grant fuller OS control but require self-operating far more components.

**Q2.** Does Flexible Server automatically provision an HA standby upon creation?

**Answer:** Not by default. You must select an HA mode per tier/region and verify the actual configuration.

**Q3.** How do same-zone HA and zone-redundant HA differ?

**Answer:** Same-zone places the standby in the same zone, whereas zone-redundant uses another zone where supported; zone-redundant mitigates single-zone outages but does not replace cross-region DR.

**Q4.** Does a read replica replace PITR backups?

**Answer:** No. Accidental data deletion on the primary replicates to the replica. PITR restores data to a point before the error within the backup window.

**Q5.** Why does a backup restore usually require a new FQDN?

**Answer:** PITR usually creates a separate restored server; the app must validate and cut over per runbook rather than mutating the primary in place.

**Q6.** Is a Private DNS Zone alone enough to keep a database secure?

**Answer:** No. Routing/network policies, TLS, authentication, PostgreSQL grants, and secret controls are all required.

**Q7.** Is `sslmode=require` the same as `sslmode=verify-full`?

**Answer:** No. `verify-full` verifies both the CA chain and server hostname, aligning with production security goals.

**Q8.** Does Azure RBAC Contributor automatically grant SELECT on PostgreSQL tables?

**Answer:** No. Azure resource permissions and PostgreSQL data-plane privileges are distinct.

**Q9.** When an API scales from 10 to 20 replicas, what happens to the connection pool budget?

**Answer:** Potential connections can double if each replica keeps the same pool size, risking `max_connections` exhaustion or RAM starvation on the DB.

**Q10.** Why do applications need idempotency during failover?

**Answer:** Losing a connection after `COMMIT` can leave the client unsure whether the transaction succeeded; retrying without idempotency creates duplicate side effects.

**Q11.** How does `EXPLAIN ANALYZE` differ from `EXPLAIN`?

**Answer:** `EXPLAIN ANALYZE` executes the query to measure actual runtime behavior; avoid running heavy write statements in production without controls.

**Q12.** Should `VACUUM FULL` be run regularly to shrink storage bills?

**Answer:** No. It causes heavy locking/I/O, does not guarantee shrinking Azure provisioned storage, and should only be considered under a runbook.

**Q13.** Why might a GET against a replica miss a recently inserted order?

**Answer:** Because asynchronous replication introduces lag; read-after-write flows must read from the primary or apply a consistency strategy.

**Q14.** Why won't adding vCores fix a SQL deadlock?

**Answer:** Deadlocks stem from transaction/lock ordering across app logic and data; code/transaction logic must be fixed.

**Q15.** What should guide choosing Burstable, General Purpose, or Memory Optimized?

**Answer:** Workload CPU/RAM patterns, SLOs, HA/feature availability, cost, and benchmark results—not merely lowest price.

**Q16.** If a database uses public access and the organization requires private-only, is changing DNS to private enough?

**Answer:** No. You must deploy a service-supported private network model (VNet integration or Private Link depending on server type), DNS, routing/firewall, and a proper migration/cutover process.

**Q17.** Does `pg_stat_statements` work automatically on every Flexible Server right after `CREATE EXTENSION`?

**Answer:** Not guaranteed. Check the extension allowlist, version, preload/server parameters/restarts, and permissions.

**Q18.** When cleaning up a lab, should you delete a resource group with one command without inspecting it?

**Answer:** No. Only delete an RG confirmed to be 100% lab-owned and approved, as deletion is destructive and can impact shared data/resources.

## Key Takeaways

- **Azure Database for PostgreSQL Flexible Server** is a managed relational PostgreSQL service, yet you remain responsible for **SQL, schemas, roles, networking, security, SLOs, and costs**.
- **Compute tier, SKU, storage/IOPS, backups, and HA** must match workload patterns, regional/feature support, and budgets.
- **Public firewall allowlists** and **private VNet/Private Link** are distinct connectivity models; DNS, routing, TLS, and authentication must each be verified independently.
- For PostgreSQL/JDBC clients, aim for **TLS `verify-full`**, least-privilege roles, secret management, and budgeted connection pooling.
- **HA standby** protects availability per model; **read replicas** scale reads with lag; **PITR** supports data recovery and usually creates a new server.
- **Protecting transactions** requires PostgreSQL constraints, short transactions, idempotency, and bounded retries across disconnects/failovers.
- Monitor **Azure Monitor metrics** alongside **PostgreSQL statistics/query plans** to fix the true CPU/I/O/lock/connection bottleneck.
- Promote databases to production only after completing **monitoring, backup restore drills, HA/DR planning, security reviews, cost budgeting, and incident runbooks**.