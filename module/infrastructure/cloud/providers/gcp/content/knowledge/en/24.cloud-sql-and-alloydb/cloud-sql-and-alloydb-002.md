# Cloud SQL for PostgreSQL, MySQL, and SQL Server

## Learning Objectives

After this lesson, you will be able to:

1. Explain **Cloud SQL** as a managed relational database service, distinguishing instances, databases, users, HA standbys, read replicas, and backups.
2. Compare **Cloud SQL for PostgreSQL**, **MySQL**, and **SQL Server** across ecosystems, versions, authentication, licensing, scalability, and administrative limits.
3. Choose **Enterprise/Enterprise Plus**, region, machine size, storage, availability, and connectivity options (**public IP/private IP/Cloud SQL connectors**).
4. Create and configure instances using **gcloud**, and connect securely from Java/Spring Boot on Cloud Run, GKE, or a developer workstation.
5. Separate **Google Cloud IAM**, **database users/roles**, and **service identity**; apply Secret Manager and IAM database authentication where supported.
6. Design backups, **point-in-time recovery (PITR)**, high availability, read replicas, migrations, monitoring, rollbacks, and cost controls; complete exercises with worked answers.

## 1. What Does Cloud SQL Solve?

**Cloud SQL** is a managed relational database server service on Google Cloud. Instead of operating PostgreSQL, MySQL, or Microsoft SQL Server yourself on Compute Engine, you offload infrastructure tasks such as provisioning, patching, backups, availability monitoring, and part of replication to Google Cloud. **The application remains responsible** for schemas, indexes, queries, users, data, connections, costs, and recovery procedures.

In the **CLOUD_PROVIDERS_GCP** module, this is the link connecting project/IAM/VPC organization with Java workloads running on **Compute Engine, GKE, and Cloud Run**, as well as security, release automation, reliability monitoring, and budgeting strategies.

### Running Example

A retail company deploys:

- **orders-api** (Spring Boot/Java) on Cloud Run, requiring transactional order processing.
- **payment-adapter** on GKE, needing to read payment statuses.
- **reporting-job** aggregating data at the end of the day.
- Production database located in **asia-southeast1**, with backups retained according to recovery policy.

~~~mermaid
flowchart LR
    U["Users"] --> LB["Cloud Run orders-api<br/>Java + HikariCP"]
    LB --> CONN["Cloud SQL Java Connector<br/>or Auth Proxy"]
    CONN --> DB["Cloud SQL primary<br/>orders-db"]
    DB --> HA["HA standby<br/>different zone, same region"]
    DB -. "asynchronous replication" .-> RR["Read replica<br/>reporting"]
    DB --> BK["Backups + transaction logs<br/>PITR"]
    GKE["GKE payment worker"] --> CONN
    IAM["IAM + Secret Manager"] -. "Manages identities/credentials" .-> CONN
~~~

**Diagram boundaries:** the HA standby is not a read replica for reporting; backup/PITR is not a live query-serving copy; and **replication does not replace backups**.

## 2. Resource Hierarchy and Core Concepts

~~~text
Google Cloud project: shop-dev-001
└── Cloud SQL instance: orders-pg
    ├── Engine: PostgreSQL 18
    ├── Region: asia-southeast1
    ├── Databases: ordersdb, app_test
    ├── Users/roles: app_user, readonly_user
    ├── HA standby (if regional availability is chosen)
    ├── Read replica (separate instance resource, if created)
    └── Backups / transaction logs (if configured)
~~~

| Concept | Meaning | Example |
|---|---|---|
| **Instance** | Managed DB server with engine/version, vCPU/RAM/storage/network | orders-pg |
| **Database** | Logical database residing inside an instance | ordersdb |
| **Database user/role** | SQL identity and privileges, separate from Cloud IAM | app_user can only CRUD one schema |
| **Instance connection name** | Identifier used by Cloud SQL Auth Proxy/Language Connectors | shop-dev-001:asia-southeast1:orders-pg |
| **Primary** | Instance handling writes and most transactions | orders-pg |
| **HA standby** | Internally managed standby in another zone for failover | Not queried directly by applications |
| **Read replica** | Instance receiving data asynchronously from primary to scale reads | orders-pg-replica |
| **Backup / PITR** | Restoring data to a point in time or retention window | Recovering before an accidental DELETE |

**Cloud SQL is not a self-managed database server**: you do not have root access on the VM running the engine and cannot arbitrarily install every extension, plugin, or OS feature. Always check **engine-specific feature compatibility** before migrating legacy applications.

## 3. PostgreSQL, MySQL, or SQL Server?

| Criterion | PostgreSQL | MySQL | Microsoft SQL Server |
|---|---|---|---|
| Ecosystem | Standard SQL, Cloud SQL-supported extensions, JSON/JSONB types, GIS via PostGIS | Web/LAMP apps and many ORMs, MySQL ecosystem | .NET/Windows/SQL Server apps, T-SQL, Microsoft ecosystem |
| Engine-specific syntax | PL/pgSQL, JSONB, PostgreSQL functions | MySQL dialect, InnoDB, collations | T-SQL, stored procedures, SQL Server data types |
| Common JDBC driver | **org.postgresql:postgresql** | **com.mysql:mysql-connector-j** | **com.microsoft.sqlserver:mssql-jdbc** |
| Default TCP port | **5432** | **3306** | **1433** |
| Database authentication | Built-in user/password; **IAM database authentication** | Built-in user/password; **IAM database authentication** | SQL logins/password, Active Directory/Entra ID per config; **no IAM database authentication** |
| Licensing | Open-source PostgreSQL component included in service price | MySQL component included in service price | Includes SQL Server license costs per edition |
| Notes | Extensions/superuser privileges are restricted | Flags, charsets/collations, binary logs need review | SQL Server Agent/AD/linked servers/features have service limits |

**Do not choose by engine name alone:** base your decision on compatibility with existing schemas/queries, team skills, HA/DR requirements, empirical performance, licensing, and operational cost.

### 3.1. Database Versions Are Not Immutable Defaults

Per documentation updated in 2026, Cloud SQL supports modern releases such as:

- **PostgreSQL 18**; older major versions are also supported under **regular/extended support** schedules.
- **MySQL 8.4** and releases listed in the supported versions table; older releases may incur **extended support charges**.
- **SQL Server 2022/2025** with eligible editions; certain 2017/2019 versions follow Microsoft's respective support lifecycles.

Do not rely on console/gcloud defaults; **explicitly specify database-version** and check **support/EOL**, major version upgrade paths, and JDBC compatibility before creation. A version listed as "supported" might be in **extended support with extra fees**, which does not mean you should pick it for a new project.

## 4. Editions, Machine Sizing, and Availability

Cloud SQL offers two editions across all three engines:

| Edition | Characteristics | When to Choose |
|---|---|---|
| **Enterprise** | Core managed DB capabilities, standard machine series, and baseline HA/observability | Small-to-medium apps, dev/staging, moderate budget/latency requirements |
| **Enterprise Plus** | Enhanced performance, data protection, availability/maintenance/observability options | Production workloads requiring advanced SLA/latency/throughput and supported features |

**Pricing, machine series, and features vary by engine, database version, and region.** SQL Server Enterprise Plus is not available for every SQL Server edition: current documentation lists eligible combinations of **SQL Server Enterprise 2019/2022/2025**. PostgreSQL 16+ and MySQL 8.4+ also have **default edition** rules that differ from older versions when created via gcloud/API. Therefore, always specify **--edition** explicitly to avoid billing surprises.

### 4.1. What Must Be Decided Before Creating an Instance?

1. **Engine/version/edition**: affects SQL compatibility, extensions, pricing, and lifecycle.
2. **Region**: place near applications and data dependencies; evaluate residency and egress.
3. **CPU/RAM/storage**: size based on measured workload; Cloud SQL does not autoscale CPU/RAM per HTTP request like Cloud Run.
4. **Availability**: **Zonal** or **Regional HA**; critical production workloads should consider HA.
5. **Connection path**: private IP, public IP + connector, or Private Service Connect depending on topology.
6. **Data protection**: backup option, retention, PITR, encryption/CMEK, and failover runbooks.
7. **Network/IAM**: who manages instances, who connects, and who receives SQL GRANTs.
8. **Maintenance**: maintenance windows, upgrade schedules, and application retry/reconnect behavior.

### 4.2. HA Is Not DR

**Regional HA** places a primary and a standby in **two zones within the same region**. Data is replicated synchronously for HA; when a zone or instance fails, Cloud SQL can **fail over** to the standby using the managed endpoint/IP mechanism. In PostgreSQL documentation, failover typically causes downtime of **around one minute**, though it varies by configuration and incident. **Active connections must reconnect/retry**.

**Zonal/standalone** uses fewer resources but does not automatically recover from an entire zone outage like HA. **HA does not protect against** accidental DELETEs, bad application writes, prolonged logic bugs, or full-region outages. Those risks require tested **PITR, backups, and cross-region DR**.

### 4.3. Read Replicas Do Not Replace Standbys

A read replica receives changes **asynchronously**, serving SELECT/analytics/reporting queries to offload the primary; **replication lag** means it may return stale data. Queries requiring **read-after-write consistency** (such as checking a payment just recorded) should read from the primary or use an appropriate consistency mechanism.

A read replica has its own **connection endpoint, instance cost, and monitoring**. For SQL Server, Cloud SQL now also supports read replicas, though limits/eligibility by edition and version must be verified. Failing over to a replica or cross-region DR is a **different process from automatic HA standby failover**.

## 5. Hands-On A — Creating a PostgreSQL Lab Instance

Assume the following values:

| Attribute | Example Value |
|---|---|
| Project | **shop-dev-001** |
| Region | **asia-southeast1** |
| Instance | **orders-pg** |
| Engine | **PostgreSQL 16**, Enterprise |
| Database | **ordersdb** |
| App runtime | **orders-api** service account |

**These are example commands**, not already-executed commands. Creating a Cloud SQL instance incurs charges for vCPU/RAM, storage, and backups. Run only in an authorized lab project; before creating production instances, review sizing, IAM, and networking.

### 5.1. Preflight

~~~bash
gcloud config get-value project
gcloud auth list
gcloud sql instances list --project=shop-dev-001

# Only run if you have permission to enable APIs for the lab project.
gcloud services enable sqladmin.googleapis.com \
  --project=shop-dev-001
~~~

### 5.2. Creating a Zonal Instance for Learning (Not a Production HA Template)

~~~bash
gcloud sql instances create orders-pg \
  --project=shop-dev-001 \
  --region=asia-southeast1 \
  --database-version=POSTGRES_16 \
  --edition=ENTERPRISE \
  --cpu=2 \
  --memory=7680MB \
  --storage-size=20GB \
  --availability-type=ZONAL \
  --backup-start-time=02:00
~~~

**Specify the edition explicitly**: PostgreSQL 16 may default to Enterprise Plus if no edition is provided. The 2 vCPU/7.5 GiB and 20 GB sizing is for lab use only, not a recommendation for all applications.

The command above defaults to a **public IP network model if private IP is not specified**, subject to current defaults/organization policies. **Do not open authorized networks to 0.0.0.0/0** just to test connectivity. For production, design private connectivity from the start.

### 5.3. Creating a Database and Inspecting Details

~~~bash
gcloud sql databases create ordersdb \
  --instance=orders-pg \
  --project=shop-dev-001

gcloud sql instances describe orders-pg \
  --project=shop-dev-001 \
  --format="yaml(name,connectionName,databaseVersion,region,settings,ipAddresses)"

gcloud sql databases list \
  --instance=orders-pg \
  --project=shop-dev-001
~~~

An **instance** is not the same as a **database**: a single instance can host multiple databases. The **databases create** command does not automatically grant SQL permissions to the Java runtime.

### 5.4. Choosing Production HA

Reference pattern (do not run on the lab instance unless needed):

~~~bash
gcloud sql instances patch orders-pg \
  --project=shop-dev-001 \
  --availability-type=REGIONAL

gcloud sql instances describe orders-pg \
  --project=shop-dev-001 \
  --format="yaml(settings.availabilityType,gceZone,secondaryGceZone)"
~~~

**Changing availability type** can trigger a restart/failover or significant provisioning time and increases cost. Production systems should choose **REGIONAL at creation time** when high availability is needed, review backups/PITR, and test reconnect behavior.

## 6. MySQL and SQL Server: Similar Operations, Not Identical

### 6.1. Creating a MySQL Enterprise Instance

~~~bash
gcloud sql instances create orders-mysql \
  --project=shop-dev-001 \
  --region=asia-southeast1 \
  --database-version=MYSQL_8_0 \
  --edition=ENTERPRISE \
  --cpu=2 \
  --memory=7680MB \
  --storage-size=20GB \
  --backup-start-time=02:00
~~~

**MySQL 8.0** is used here to illustrate stable syntax; for new applications, evaluate **MySQL 8.4** and currently supported versions along with matching editions, regions, and machine series. MySQL requires **binary logging** to be configured for certain replication/PITR workflows; check the appropriate options for your version and backup settings.

### 6.2. Creating SQL Server: Differences in Editions and SQL Credentials

A gcloud example **with placeholders — do not run verbatim**:

~~~bash
gcloud sql instances create orders-sqlserver \
  --project=shop-dev-001 \
  --region=asia-southeast1 \
  --database-version=SQLSERVER_2022_STANDARD \
  --edition=ENTERPRISE \
  --cpu=2 \
  --memory=7680MB \
  --root-password=REPLACE_WITH_TEST_PASSWORD
~~~

SQL Server uses **sa/password logins or supported AD/Entra ID options**, not IAM database authentication. Passing **--root-password** on the command line risks exposing it in shell history, process lists, or CI logs. For real environments, **set passwords via an approved secure administrative channel** (such as the console or dedicated secret workflows), never hardcoded in scripts or pushed to Git.

**SQL Server editions** (Standard/Enterprise/Express/Web) and **Cloud SQL editions** (Enterprise/Enterprise Plus) are **two separate classifications**. For example, `SQLSERVER_2022_STANDARD` can run under **Cloud SQL Enterprise edition** — it is not a SQL Server Enterprise license. SQL Server pricing includes separate licensing components.

### 6.3. Differences in SQL Dialects

~~~sql
-- PostgreSQL
CREATE TABLE orders (
  order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  amount NUMERIC(12, 2) NOT NULL
);

-- MySQL
CREATE TABLE orders (
  order_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  amount DECIMAL(12, 2) NOT NULL
);

-- SQL Server
CREATE TABLE orders (
  order_id BIGINT IDENTITY(1,1) PRIMARY KEY,
  amount DECIMAL(12, 2) NOT NULL
);
~~~

These three snippets are **mutually exclusive alternatives**, not statements to run sequentially on the same database. When migrating, review **data types, sequences/identity, transaction isolation, collations, timestamps/time zones, JSON, stored procedures, and indexes**, not just the JDBC URL.

## 7. Connecting to Cloud SQL: Public IP, Private IP, or Connector?

**Having a network path** and **having database access permissions** are two separate requirements. Choose the network path first, then set up IAM, TLS, and SQL credentials.

| Connection Type | When to Use | Requirements and Risks |
|---|---|---|
| **Private IP + direct TCP** | Cloud Run/GKE/VMs with VPC connectivity to Cloud SQL | Private Services Access or appropriate private IP architecture; manage VPC/firewalls/TLS |
| **Public IP + direct TCP** | Clients with fixed IPs where a public endpoint is justified | Authorized networks + TLS/certificates; never open 0.0.0.0/0 |
| **Cloud SQL Auth Proxy** | Developers, GKE sidecars, or workloads needing a proxy | ADC/IAM + Cloud SQL Admin API, appropriate Proxy version; no public authorized networks needed |
| **Cloud SQL Java/Python/Go connector** | Applications managing connections in-process | Library dependency, ADC, pool management, IP selection |
| **Private Service Connect (PSC)** | Multi-VPC/multi-project service networking topologies where eligible | DNS, service attachments/endpoints, specific quotas and limits |

**Recommendation:** for workloads inside Google Cloud, prefer **private IP** unless constrained otherwise; use **Cloud SQL connectors** when you want automatic IAM authentication and TLS encryption. A **connector does not create a VPC route to a private IP**: if using private IP, Cloud Run/GKE/VMs must still have a valid network path.

### 7.1. Rules for Public IP

- When **connecting directly over public IP**, configure **authorized networks** with narrow CIDRs and enforce TLS.
- When using **Cloud SQL Auth Proxy/Language Connectors over public IP**, you do not need to add client IPs to authorized networks because the connector authenticates through Cloud SQL's control plane.
- Never run **gcloud sql instances patch --authorized-networks=...** in production without reading the existing list first: the command can **overwrite the entire allowlist** and lock out other clients.
- A public network path does not bypass DB authentication; the SQL account must still authenticate properly.

### 7.2. Rules for Private IP

With a private IP model using **Private Services Access**, allocate an IP range and create a service networking connection on the VPC before assigning a private IP to the instance. Choose a CIDR/org policy sizing with enough capacity for services; this network configuration affects shared resources and requires platform team review.

For **Cloud Run**, use **Direct VPC egress** or a **Serverless VPC Access connector** pointing to the VPC that can reach Cloud SQL's private IP. For **GKE**, cluster networking and routing must reach the database; never assume two resources in the same project automatically have network connectivity.

**Default ports:** PostgreSQL **5432**, MySQL **3306**, SQL Server **1433**. The Java client must use the matching driver, port, and SQL dialect. With Cloud SQL Auth Proxy, the application connects to **localhost/Unix socket** on the port the Proxy listens on, which does not have to match the DB engine port.

### 7.3. Instance Connection Name

~~~bash
gcloud sql instances describe orders-pg \
  --project=shop-dev-001 \
  --format="value(connectionName)"

# Example output:
# shop-dev-001:asia-southeast1:orders-pg
~~~

The **connection name** is used by Cloud SQL connectors, not as a DNS hostname or database name. Do not confuse it with **ordersdb** or the instance IP address.

## 8. Hands-On B — Cloud SQL Auth Proxy and Java

### 8.1. Accounts and IAM Permissions

Cloud SQL Auth Proxy/Java connector uses **Google Cloud credentials** to verify that a principal is allowed to connect to the instance; typically this requires:

- **roles/cloudsql.client**, or a custom role with **cloudsql.instances.connect**, granted at the appropriate scope.
- **Cloud SQL Admin API** enabled on the project containing the instance (and related projects for cross-project connections).
- Valid **ADC**: the Cloud Run/GKE/Compute Engine service account, or a developer logged into ADC in a lab environment.
- Separate **database user/password**, unless **IAM database authentication** is configured on a supported engine.

**Important:** **roles/cloudsql.client does not grant SELECT/INSERT** on SQL schemas. It only permits passing through the Cloud SQL connector layer. The application still needs a database login and corresponding **GRANT** privileges.

### 8.2. Running the Proxy on a Controlled Development Machine

After installing **Cloud SQL Auth Proxy v2** following Google Cloud instructions, run:

~~~bash
# This command uses existing ADC; NO JSON key download required.
cloud-sql-proxy \
  --port=5432 \
  shop-dev-001:asia-southeast1:orders-pg
~~~

Open another terminal to connect:

~~~bash
# Example for PostgreSQL only; enter password at the secure prompt.
psql -h 127.0.0.1 -p 5432 -U app_user -d ordersdb
~~~

By default, the Proxy listens on **127.0.0.1**. **Do not bind 0.0.0.0** to share the Proxy with others; anyone able to reach that socket can use the connection tunnel opened by the Proxy. If the instance only has a **private IP** or you want to force the private path, the Proxy needs **--private-ip** and the machine running the Proxy must have a valid VPC route (VPN/VM/VPC).

**Local practice note:** do not run `cloud-sql-proxy` on the same port as another local PostgreSQL server; pick a different local port if there is a conflict.

### 8.3. Java JDBC Without Hardcoded Passwords

Java 21 example with the **PostgreSQL JDBC driver**. The code connects to the Proxy on localhost; **DB_USER/DB_PASSWORD** must be injected via an approved secrets mechanism:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class CloudSqlCheck {
    private CloudSqlCheck() {}

    public static void main(String[] args) throws SQLException {
        String url = "jdbc:postgresql://127.0.0.1:5432/ordersdb";
        String username = System.getenv("DB_USER");
        String password = System.getenv("DB_PASSWORD");

        if (username == null || password == null) {
            throw new IllegalStateException("Missing DB credentials");
        }

        try (Connection conn = DriverManager.getConnection(url, username, password);
             PreparedStatement stmt = conn.prepareStatement("SELECT 1");
             ResultSet rs = stmt.executeQuery()) {
            if (rs.next()) {
                System.out.println("Database connection OK"); // Do not print secrets.
            }
        }
    }
}
~~~

**For real applications**, never open a new connection per HTTP request; use **HikariCP**, configure **max pool size**, connection timeout, idle timeout, and retries with jitter. The PostgreSQL JDBC driver above is specific to that engine. When switching to MySQL/SQL Server, update the **JDBC driver, URL, port, SQL syntax, and DB authentication**.

~~~text
PostgreSQL : jdbc:postgresql://127.0.0.1:5432/ordersdb
MySQL      : jdbc:mysql://127.0.0.1:3306/ordersdb
SQL Server : jdbc:sqlserver://127.0.0.1:1433;databaseName=ordersdb;encrypt=true
~~~

For SQL Server, TLS verification across the driver and Proxy must be validated together; **encrypt=true** alone does not guarantee proper endpoint validation if `trustServerCertificate` disables certificate checking. Use Google-supported driver/connector configurations rather than setting **trustServerCertificate=true** as a quick fix.

### 8.4. Attaching Cloud SQL to Cloud Run

If **orders-api** is already deployed on Cloud Run and uses the built-in integration:

~~~bash
gcloud run services update orders-api \
  --project=shop-dev-001 \
  --region=asia-southeast1 \
  --add-cloudsql-instances=shop-dev-001:asia-southeast1:orders-pg
~~~

Updating Cloud Run creates a **new revision**; the service identity needs **Cloud SQL Client**, and the app still needs **database login/credentials**. For **private IP/direct TCP**, Cloud Run needs dedicated VPC egress configuration; do not assume **--add-cloudsql-instances** solves all private networking requirements.

### 8.5. GKE and Sidecar Connections

On GKE, a common pattern is **Java Pod + Cloud SQL Auth Proxy sidecar**, granting **Cloud SQL Client** to the KSA via **Workload Identity Federation for GKE**. Both containers in the same Pod share a network namespace, so Java can connect to **127.0.0.1** on the Proxy port. Pin the Proxy image by version/digest, set CPU/memory limits, configure health checks, and restrict secret exposure.

**Do not place JSON service account keys inside Pods** unless there is an approved exception. WIF + IAM provides short-lived credentials for the Proxy to call Cloud SQL APIs; it does not replace database username/password or IAM database login.

## 9. Permissions: Google IAM Does Not Equal SQL GRANT

### 9.1. Two Gates to Pass Through

~~~mermaid
flowchart LR
    APP["Java app / service account"] --> NET{"VPC/Public IP/Proxy"}
    NET --> IAM{"Cloud SQL IAM<br/>if via connector"}
    IAM --> LOGIN{"Database login<br/>password or IAM DB auth"}
    LOGIN --> GRANT{"SQL privileges<br/>GRANT/roles"}
    GRANT --> QUERY["SELECT/INSERT/UPDATE"]
~~~

| Permission | Purpose | Does Not Replace |
|---|---|---|
| **roles/cloudsql.client** | Allows Cloud SQL connectors/Proxy to connect | DB login and SQL GRANTs |
| **roles/cloudsql.instanceUser** | Grants **cloudsql.instances.login** for IAM database authentication | Cloud SQL Client (if using connector), SQL GRANTs |
| **Cloud SQL Admin** | Manages instances/operations via IAM | Full DBA privileges inside every database |
| **Database user / SQL roles** | Reads/writes schemas, tables, stored procedures | Project IAM for managing instances |

**PostgreSQL and MySQL** support database login via **IAM database authentication** once the instance is configured and IAM DB users/groups are properly created. **SQL Server does not support IAM database authentication**: use SQL logins/passwords, Active Directory, or Microsoft Entra ID per available features. Never claim that all three engines "support IAM login."

### 9.2. PostgreSQL and MySQL: IAM Database Authentication

To log in with IAM automatically:

1. Enable **IAM database authentication** on the Cloud SQL instance (this alters DB flags and may require a restart).
2. Add the IAM user, service account, or group in the format supported by Cloud SQL.
3. Grant **roles/cloudsql.instanceUser** to the IAM principal; if using Proxy/Language Connector, also grant **roles/cloudsql.client**.
4. Configure **Cloud SQL Auth Proxy/Java Connector** with **automatic IAM database authentication** mode.
5. Inside the database, still execute **GRANT SELECT/INSERT/EXECUTE** per business needs; IAM login does not automatically confer CRUD permissions.

**Access tokens are short-lived**, so automatic refresh via a connector is much safer than manually managing tokens inside a connection pool. When running on Cloud Run, the ADC principal must match the identity configured for IAM DB auth and the corresponding SQL user.

### 9.3. SQL Server: SQL Logins and Directory Auth

Cloud SQL for SQL Server supports database authentication via **built-in SQL authentication**, **managed/customer-managed Active Directory**, and **Microsoft Entra ID** where eligible. **IAM only controls instance/backup operations, not SQL query logins**. For Java apps:

- Use a **Microsoft JDBC driver** compatible with the server version.
- Create least-privilege SQL logins and store passwords in **Secret Manager** when using SQL auth.
- Manage credential rotation and connection pooling; never write the `sa` password into `app.yaml`, Dockerfiles, or GitHub Actions logs.
- Never run day-to-day application traffic using the **sa** login; create dedicated users/roles restricted to the required database.

### 9.4. Least Privilege Inside the Database

PostgreSQL example run after logging in as an **authorized DBA**:

~~~sql
-- Illustrative only; app_user was created via a secure provisioning workflow.
GRANT CONNECT ON DATABASE ordersdb TO app_user;
GRANT USAGE ON SCHEMA public TO app_user;
GRANT SELECT, INSERT, UPDATE ON TABLE public.orders TO app_user;
-- If using identity/sequences or other objects, verify corresponding GRANTs.
~~~

Do not default to **GRANT ALL PRIVILEGES ON DATABASE** for runtime accounts. MySQL uses **GRANT SELECT, INSERT, UPDATE ON ordersdb.orders ...**; SQL Server uses **GRANT ... ON OBJECT::dbo.orders TO app_user**. Syntax and schema/role models **differ across the three engines**.

## 10. Network, Data, and Secrets Security

### 10.1. Security Checklist

| Layer | Control |
|---|---|
| **Resource IAM** | Separate deployer, DB operator, and runtime SAs; least-privilege roles |
| **Network** | Private IP/PSC where appropriate; tightly scoped public authorized networks; VPC firewalls/TLS |
| **DB authentication** | IAM DB auth where supported, minimal SQL users, AD/Entra where applicable |
| **Secrets** | Secret Manager, no password logging; rotate with dual-credential overlap where possible |
| **At-rest encryption** | Google-managed encryption by default; evaluate **CMEK** per compliance requirements |
| **Backups** | Encryption, retention, storage location, restore testing; do not treat same-region copies as DR |
| **Audit** | Cloud Audit Logs for control plane, engine database audit/logs as needed |
| **App** | Prepared statements, query timeouts, connection pooling, migration reviews, SQL injection prevention |

### 10.2. CMEK Is Not a SQL Permission

Cloud SQL encrypts data at rest by default. If you choose a **customer-managed encryption key (CMEK)**, create the Cloud KMS key in a supported location and grant required permissions to the **Cloud SQL service agent**; plan key rotation and availability before creating the instance. **Do not grant KMS CryptoKey Decrypter to every SQL application user** — the Cloud SQL service itself performs storage encryption.

If the key is disabled or service agent permissions are revoked, instances, backups, and restarts can be disrupted. Never disable a production key to test behavior; use a lab project with a runbook and verify DR impacts.

### 10.3. Encryption in Transit

- **Cloud SQL Auth Proxy/Connectors** establish an encrypted channel to Cloud SQL and authenticate the principal, reducing direct management of server/client certificates.
- With **direct TCP**, configure **SSL/TLS** per requirements and verify server certificates; private IP **does not automatically mean encrypted traffic**.
- The path from Java to the local Proxy TCP port on the same host/Pod is a trusted boundary; **never expose the Proxy port on a public interface**.

## 11. Managing Connection Pools When Cloud Run/GKE Scales

**Cloud SQL instances have connection and resource limits**. Cloud Run can scale up by dozens of instances during traffic spikes; if each instance opens an oversized pool, the DB gets overwhelmed even while app CPU looks healthy.

Suppose there are **40 Cloud Run instances**, each with a maximum pool of **10 connections**:

\[
\text{Max application connections} \approx 40 \times 10 = 400.
\]

This is just the configured upper bound (excluding migrations, reporting, DBAs, and background jobs). On a DB with a lower `max_connections` limit, errors such as **too many connections**, rising latency, or timeouts can appear right after scale-out.

### 11.1. Pool Design

1. Calculate **concurrent requests × fraction of requests that actually hit the DB**; do not size pools equal to total requests if many requests do not query the DB.
2. Cap **HikariCP maximumPoolSize**, set `connectionTimeout`, and set `maxLifetime` shorter than any infrastructure connection idle cutoff; test under real peak load.
3. Align Cloud Run **max instances/concurrency** with DB capacity; on GKE, verify HPA replica caps.
4. Use **retries for transient/failover errors** with exponential backoff and jitter; avoid retrying within non-idempotent flows that could create duplicate orders.
5. Consider **read replicas** for long-running reports, application caching, and query optimization before scaling up vCPU.
6. Measure **active/idle connections**, pool wait times, SQL latency, and error rates from both the app and Cloud SQL.

### 11.2. Idempotency After Failover

When the DB drops between submitting a write transaction and receiving the response, the application may **not know whether the transaction committed**. Never blindly retry a **CREATE ORDER** command; use an **idempotency key** or unique business constraint to prevent duplicate orders.

**HA helps the system recover faster; it does not make JDBC connections immortal**. Java/Spring Boot still requires reconnect logic, timeouts, and health checks.

## 12. Backups, PITR, and Disaster Recovery

### 12.1. Three Distinct Capabilities: HA, Backups, and PITR

| Mechanism | Protects Against | Does Not Protect Against |
|---|---|---|
| **Regional HA** | Single zone/instance failure, enabling fast failover | Accidental DELETEs, ransomware/bad logic, full-region outage |
| **Read replica** | Heavy read load and certain DR scenarios via promotion | Zero data loss guarantees; replacing backups |
| **Automated/on-demand backup** | Data loss or needing to restore an earlier state | Serving live traffic; zero restore time |
| **PITR** | Restoring close to a moment right before a bad transaction | Works only within the **retained log window**, must be enabled beforehand |
| **Cross-region backup/replica** | Out-of-region DR support | Automatic switching of DNS, app/DB credentials, and traffic |

### 12.2. Standard Backups vs. Enhanced Backups

Cloud SQL currently provides two **backup options**:

- **Standard backups:** configured directly on the instance, stored and managed by Cloud SQL in the same project. Automated schedules are typically **daily**; automated backup retention depends on configuration and edition. On-demand backups have separate retention rules.
- **Enhanced backups:** integrated with **Backup and DR Service**, using **backup vaults/backup plans** that can be managed centrally in another project, with **hourly/daily/weekly/monthly/yearly** schedules, longer retention, and safeguards such as retention locks.

The two options **cannot run simultaneously on the same instance**. Per documentation, Standard automated backups can be kept for up to roughly **1 year**, while Enhanced can reach **10 years**, though specific limits and features depend on engine, edition, backup plan, and whether backups are retained after instance deletion.

**Warning:** backup storage location can differ from the DB region. Changing the backup location **does not automatically move old backups**. Check data residency, Cloud KMS key location, storage charges, and network egress before choosing.

### 12.3. Hands-On C — Creating and Listing Backups

~~~bash
# Create an on-demand backup on the lab instance; incurs storage charges.
gcloud sql backups create \
  --instance=orders-pg \
  --project=shop-dev-001 \
  --description="Pre-migration lab backup"

gcloud sql backups list \
  --instance=orders-pg \
  --project=shop-dev-001

gcloud sql instances describe orders-pg \
  --project=shop-dev-001 \
  --format="yaml(settings.backupConfiguration)"
~~~

To verify that **backups actually restore**, test **restoring to an isolated instance**, run SQL integrity checks, and confirm the application can read and write. A **SUCCESS** status on a backup job does not prove RTO/RPO targets are met.

### 12.4. Point-in-Time Recovery

**PITR** combines backups with **transaction logs**: PostgreSQL uses WAL, MySQL uses binary logs, and SQL Server uses log backups depending on capability/edition. PITR requires supported settings to be enabled, transaction logs within the retention window, and a valid timestamp.

**PITR creates a new instance** — it is not an in-place UNDO on the primary. Example command for **standard backups** after confirming PITR is enabled:

~~~bash
# REPLACE timestamp with an actual UTC time WITHIN the PITR window.
# Do not run placeholder verbatim.
gcloud sql instances clone orders-pg orders-pg-restore-test \
  --project=shop-dev-001 \
  --point-in-time="YYYY-MM-DDTHH:MM:SSZ"
~~~

If the instance uses **Enhanced backups**, restoring from a **backup vault/data source** may use **gcloud sql instances point-in-time-restore** with different parameters. **Do not copy the standard clone command for a vault backup and assume it works**. Always verify the active backup option before choosing a recovery workflow.

**Safe recovery drill:**

1. Create test data and record a UTC timestamp.
2. Take an on-demand backup and confirm PITR is active.
3. Simulate an accidental DELETE on the **lab database**, then pick a restore timestamp right before the DELETE.
4. Restore to a **new instance**, verify row counts, constraints, and application connectivity.
5. Measure **RTO** (recovery duration) and **RPO** (potential data loss window) against your targets.
6. Delete the cloned instance once testing is done and no forensic/rollback need remains, avoiding ongoing charges.

**Do not assume** backups/PITR will cover every regional failure; check transaction log placement, backup locality, and cross-region restore capabilities in the engine/backup option documentation.

### 12.5. Backup Lifecycle, Keys, and Deletion Permissions

Backups are sensitive resources containing production data. Restrict IAM permissions for restore/export/delete; use Cloud KMS where appropriate, set explicit retention, and monitor audit logs. With **CMEK**, never disable or destroy key versions still needed to decrypt backups. If an instance is deleted, whether backups persist depends on the backup option and **retained/final backup configuration**.

## 13. Migrations, Upgrades, and Schema Changes

### 13.1. Moving Data from Legacy Environments to Cloud SQL

| Source | Typical Migration Path | What to Verify |
|---|---|---|
| Self-managed PostgreSQL | **Database Migration Service (DMS)** or dump/restore | Versions/extensions, roles, large objects, replication permissions |
| Self-managed MySQL | DMS or logical dump/import | Binary logs, GTID, collations, stored procedures |
| On-prem/VM SQL Server | DMS (where supported) or native **.bak** export/import | T-SQL, logins, jobs, Active Directory, SQL Server edition/features |
| Between Cloud SQL instances | Engine-specific replication, backup/restore, export/import, or migration tools | Engine/version, region, downtime, RPO, compatibility |

**There is no "one-click engine converter"** that turns T-SQL into PL/pgSQL. Migrating from SQL Server to PostgreSQL/MySQL requires rewriting schemas, data types, stored procedures, query behavior, integrations, and running business tests. Even major version upgrades within the same engine can incur downtime or require specific procedures.

### 13.2. Safe Migration Workflow

1. **Inventory:** database size, extensions/flags, connections, users, collations, SQL dialect, peak transactions.
2. **Prepare:** create the target instance with the right engine/version/edition, networking/IAM/backups, and monitoring.
3. **Transfer:** dump/restore or DMS/replication per engine capabilities; measure lag and throughput.
4. **Validate:** checksums/row counts, database constraints, query compatibility, timezones, and encoding.
5. **Cutover:** stop/throttle writes per runbook, complete final sync, switch connection routing/secrets, run smoke tests.
6. **Rollback:** define the point of return and how new data is synced back; avoid split-brain where two databases accept uncoordinated writes.
7. **Observe:** watch slow queries, errors, connection counts, storage, and cost; decommission the source only after the retention/rollback window expires.

### 13.3. Schema Migrations with Java

With Spring Boot, use **Flyway** or **Liquibase** inside CI/CD to version-control schemas. During rolling deployments where multiple Java versions run concurrently, prefer **expand/contract**:

~~~text
1. Expand : add columns/tables/indexes compatible with existing code
2. Deploy : Java v2 starts using the new schema
3. Migrate: backfill data, monitor performance and errors
4. Contract: drop old columns/constraints once no code depends on them
~~~

Never deploy breaking schema changes before confirming that a **Java v1 rollback** will still function. Some DDL statements cause heavy locks or table rewrites; test on production-sized datasets and measure SLO impact.

## 14. Monitoring, Query Insights, and Cost Optimization

### 14.1. Every Symptom Needs Visibility on Both Sides

| Symptom | Cloud SQL Metrics | Java/App Metrics |
|---|---|---|
| API p99 latency spikes | CPU/IO utilization, DB query latency, locks | Hikari pool wait, JDBC calls, request traces |
| Connection errors under load | Connections, max connections, CPU/memory | Cloud Run instance count, max pool size |
| Slow queries after release | Slow queries/Query Insights, index usage | Deployed version, SQL statement shape |
| Rapid storage growth | Disk utilization, storage growth, transaction log retention | Batch jobs, message retries, large blobs |
| Read replica returns stale data | Replication lag, replica health | Client routing, read-after-write behavior |
| Failover/maintenance | Cloud SQL operations/events, availability | Reconnect errors, retry rate, readiness |
| Restore misses RTO | Backup size, operation duration | Traffic cutover/recovery workflow |

Use **Cloud SQL System Insights**, **Cloud Monitoring**, **Cloud Logging**, and **Query Insights** where supported by engine/version. On PostgreSQL, analyze **pg_stat_statements** or slow queries/locks per configuration; MySQL offers slow query logs/`performance_schema`; SQL Server offers **DMVs/Query Store** per service support.

### 14.2. Illustrative Alerts

| Alert | Sample Threshold | Suggested Response |
|---|---|---|
| CPU utilization | Above **85%** for **15 minutes** | Find hot queries, missing indexes, check capacity |
| Disk utilization | Above **80%**, growing rapidly | Review storage autosize, retention, growth |
| Connections | Above **80%** of limit | Inspect pool × app instances, connection leaks |
| Replica lag | Above **30 seconds** for **10 minutes** | Look for long transactions, I/O bottlenecks, SQL load |
| Backup failure | Any critical job fails | Page owner, check backup window/quotas |
| API DB errors | Spike after failover | Check reconnects, IAM/network, DB logins, and pools |

**These numbers are illustrative**, not default Cloud SQL SLOs. A strict OLTP database workload may tolerate far less lag; choose thresholds based on baselines, error budgets, and data criticality.

### 14.3. Cost Components

| Component | Main Drivers |
|---|---|
| **CPU/RAM** | Edition, machine series, instance count, uptime |
| **Storage/IO** | SSD/HDD per edition, provisioned storage, autosize, throughput |
| **HA** | Primary + standby resources, region, infrastructure overhead |
| **Replicas** | Replica compute/storage, replication network traffic |
| **Backups/PITR** | Backup option, size, retention, transaction logs, restores |
| **SQL Server** | License/engine edition + Cloud SQL compute/storage |
| **Network** | Inter-region transfer, VPC/PSC/egress, out-of-region clients |
| **Monitoring/logs** | Cloud Logging ingestion/retention, Monitoring, billable Query Insights features |

**Budget alerts do not automatically stop instances**. Enabling HA, one replica, and long backup retention on a production DB creates multiple separate billing lines. Estimate with the **Google Cloud Pricing Calculator**, check pricing by **engine/edition/region**, and review Billing reports after deployment.

### 14.4. First Optimizations to Try

1. **Find slow queries and missing indexes** before upsizing the machine when p95 rises.
2. Fix ORM **N+1 queries** and reduce JDBC round trips.
3. Use **bounded connection pools** and align Cloud Run/GKE autoscaling limits.
4. Add a **read replica** only when reads are the real bottleneck and freshness requirements allow lag.
5. Size storage growth and backup retention with justification; never slash backups just to save money when RPO/RTO matter.
6. Clean up lab resources and backup artifacts on schedule, while preserving versions/instances needed for rollback or audit.

## 15. Troubleshooting: Layer-by-Layer Diagnosis

| Symptom | Common Causes | First Check |
|---|---|---|
| **gcloud sql instances create** fails | API disabled, missing IAM, invalid quota/region/edition/version | Cloud SQL Admin API, org policies, create operation error |
| **PERMISSION_DENIED** from Auth Proxy/connector | Wrong ADC principal or missing Cloud SQL Client | Service identity, effective IAM policy, instance connection name |
| **Connection refused / timeout** | Missing VPC route, wrong IP/port, firewall, Proxy not running | Network path, `127.0.0.1:port`, private IP/PSC DNS |
| **no pg_hba.conf entry / access denied** | DB login/TLS/user/host rejected | Authentication mode, SQL user, engine logs |
| **Invalid password / Login failed for user** | Wrong username/password or SQL Server AD config | Secret version, DB user status, rotation, grants |
| **IAM DB authentication not working on SQL Server** | Unsupported feature | Use SQL auth/AD/Entra; IAM only manages instances/backups |
| **IAM DB login gets 403 on PostgreSQL/MySQL** | Missing `instanceUser`, `client`, or IAM DB user not created | IAM grants, instance flag, user mapping, automatic refresh |
| **Cloud Run v2 fails to reach private IP** | Missing Direct VPC egress/connector or wrong network | VPC egress, network/subnet, routes |
| **Direct public IP connect fails** | Client IP missing from authorized networks or TLS mismatch | CIDR allowlist, SSL settings |
| **Cloud SQL Proxy running but Java fails to connect** | Wrong JDBC URL/port or missing DB credentials | Local listener, socket, dbname, JDBC exception |
| **Too many connections** | Hikari pool too large × too many app instances | Cloud SQL connections, autoscale cap, pool leaks |
| **High p99 SQL latency** | Queries/indexes/locks, GC/app timeouts, I/O/CPU | Query Insights, slow queries/locks, Cloud Monitoring |
| **Read replica sees stale data** | Asynchronous replication, rising lag | Replica lag, is the app routing reads to the replica? |
| **App fails during failover** | Old JDBC connections dropped without reconnect | Connection timeout, retries, health probes |
| **PITR cannot find timestamp** | PITR not enabled beforehand, outside retention, missing logs | Backup option, transaction-log retention, recovery window |
| **Restore finished but Java sees wrong data** | App still points to old primary, different DB users/secrets/config | Instance connection name, endpoints, schema, validation |
| **Cost spikes after enabling HA** | Standby/edition/storage and backup charges | Billing breakdown, edition, machine, replicas |

### 15.1. Non-Destructive Inspection Commands

~~~bash
gcloud sql instances list --project=shop-dev-001
gcloud sql instances describe orders-pg --project=shop-dev-001
gcloud sql databases list --instance=orders-pg --project=shop-dev-001
gcloud sql users list --instance=orders-pg --project=shop-dev-001
gcloud sql backups list --instance=orders-pg --project=shop-dev-001
gcloud sql operations list --instance=orders-pg --project=shop-dev-001
~~~

Combine these with **Cloud SQL System Insights, Query Insights, Cloud Monitoring, Cloud Logging**, and Java/GKE/Cloud Run logs. Never print passwords, SQL results containing customer data, or full JDBC connection strings with secrets into tickets or logs.

### 15.2. An Effective Investigation Workflow

1. **Identify the resource:** project/instance/database/region, engine, edition, maintenance state.
2. **Isolate the failure layer:** resource provisioning, network, connector IAM, DB login, SQL privileges, query/connection pool, or data recovery.
3. **Fix only the failing layer:** a 403 does not mean grant Cloud SQL Admin; SQL GRANT does not fix a missing VPC route.
4. **Reduce production risk:** check recent changes; if canarying and the new app fails, roll back app traffic after verifying schema compatibility.
5. **Re-measure:** connection success, 5xx rates, p95/p99, DB locks/connections, replica lag, and transaction correctness.

## 16. Synthesis Scenario: Java Orders, Reporting, and Data Boundaries

**Minh Phuc** company plans to migrate self-managed PostgreSQL on Compute Engine to Cloud SQL. Requirements:

- Java **orders-api** on Cloud Run must write orders securely without exposing passwords.
- GKE reporting workers can read aggregated data and tolerate a few seconds of lag, but must never write orders.
- The service must survive a single-zone failure; accidental data deletion must be recoverable within a 7-day window.
- Production is in **asia-southeast1**, with an out-of-region DR plan and cost tracking.

### 16.1. Initial Design

| Decision | Choice | Rationale |
|---|---|---|
| Engine | **Cloud SQL for PostgreSQL** matching tested major version | Minimizes SQL differences during migration |
| Edition | Enterprise or Enterprise Plus based on SLO/baseline | Avoid choosing an edition by name alone |
| Availability | **REGIONAL HA** | Protects against single-zone/instance failures |
| Networking | Private IP + Cloud Run VPC egress; GKE on same VPC/route | Restricts public DB exposure |
| App authentication | Separate runtime service accounts; IAM DB auth or minimal SQL user | Decouples cloud connectivity from SQL grants |
| Java | Bounded HikariCP pool, prepared statements, idempotency keys | Prevents connection storms and duplicate orders |
| Reporting | Read replica if measured load warrants it | Offloads primary, tolerates lag |
| Backups | Standard/Enhanced per retention & compliance + PITR enabled | Recovers from accidental DELETEs |
| Observability | System Insights, SQL metrics, Cloud Run/GKE logs, alerts | Early detection and RTO/RPO measurement |

### 16.2. Release and DR Flow

~~~mermaid
flowchart TD
    OLD["Self-managed PostgreSQL"] --> MIG["Migration rehearsal + DMS/dump"]
    MIG --> TEST["Validate data, IAM, latency, backup/restore"]
    TEST --> CUT["Cutover Java connections"]
    CUT --> PROD["Cloud SQL primary HA"]
    PROD --> RR["Read replica if needed"]
    PROD --> BAK["Backups + PITR"]
    PROD --> MON["Cloud Monitoring + alerts"]
    MON --> FAIL{"Incident?"}
    FAIL -->|"Zone failure"| HA["HA automatic failover + app reconnect"]
    FAIL -->|"Accidental DELETE"| PITR["PITR to new instance + validation"]
    FAIL -->|"Region outage"| DR["DR runbook: restore/promote, app routing"]
~~~

### 16.3. Pre-Production Acceptance Tests

| Scenario | Expected Outcome |
|---|---|
| Deploy Java with read-only DB user | INSERT is denied while SELECT succeeds where granted |
| Runtime service account lacks Cloud SQL Client | Auth Proxy is blocked from connecting |
| Java uses SQL Server with only IAM DB auth configured | Docs/runbook catch lack of support and switch to supported auth |
| Cloud Run scales from 2 to 40 instances | Total DB connections remain within pool limits |
| Read replica lags by 15 seconds | Orders API reads from primary when consistency is required |
| Simulated DB disconnect in lab | App reconnects and retries idempotently; zero duplicate orders |
| Backup/PITR drill | Restores to new instance; row counts and RTO verified |
| SQL migration changes schema | Previous Java version still works within rollback window |
| Credential rotation test | Secret version/connection pool updates without exceeding SLO downtime |
| End of testing | Clean up instances, replicas, backups, and billable resources per policy |

## 17. Practice Exercises with Answers

### Exercise A — Choosing an Engine

The existing app relies on **T-SQL stored procedures** and SQL Server Agent jobs. The team wants a quick migration to PostgreSQL to lower licensing fees.

**Answer:** Do not assume an engine swap is lift-and-shift. Consider **Cloud SQL for SQL Server** first to preserve compatibility, or scope a **dedicated migration project** to port stored procedures, schemas, and integrations if long-term benefits justify it. Verify how much of your SQL Server feature set Cloud SQL supports.

### Exercise B — IAM or SQL GRANT?

The Cloud Run runtime has **roles/cloudsql.client**, the Proxy connects, yet JDBC throws **permission denied for table orders**.

**Answer:** Cloud IAM connector permissions are sufficient; SQL privileges are missing. A DBA must run **GRANT SELECT/INSERT...** on the right schema/table for the DB user — do not grant Cloud SQL Admin to fix this.

### Exercise C — Authentication Across the Three Engines

**Question:** Does IAM database authentication work the same way for PostgreSQL, MySQL, and SQL Server?

**Answer:** No. PostgreSQL/MySQL support IAM DB auth after configuring the instance, IAM roles, and DB users. SQL Server does not support IAM DB auth for queries; use SQL auth, Active Directory, or Entra ID per available features.

### Exercise D — Public or Private IP?

Cloud Run `orders-api` needs to connect to Cloud SQL's private IP. The team granted SQL Client, yet connections time out.

**Answer:** An IAM role does not create a network route. Check **Direct VPC egress or Serverless VPC Access**, subnet/VPC, Private Services Access/PSC, and firewall rules. Also verify the app is not using the wrong IP or port.

### Exercise E — Connection Limits

Cloud Run can scale up to **60 instances**, each with a HikariCP max pool of **8 connections**. Excluding other sources, what is the maximum number of DB connections?

**Answer:** **480 connections**. This excludes DBAs/reporting/jobs; compare against Cloud SQL `max_connections` and tune pool sizes and `max_instances` accordingly.

### Exercise F — HA or Backups?

Due to a script bug, the app deleted 100,000 rows at 10:15. The instance has regional HA enabled, but PITR is disabled.

**Answer:** HA **replicates the DELETE** to the standby as well and cannot undo it. You must restore from an **available backup**, accepting an RPO up to that backup timestamp and potentially losing recent writes. Enable PITR before an incident to support point-in-time recovery.

### Exercise G — Read Replicas and Consistency

A user just completed payment; 100 ms later the API queries a read replica to display payment status and receives stale state.

**Answer:** Asynchronous replicas have **replication lag**. Flows requiring read-after-write consistency should query the **primary**, or use appropriate synchronization/wait mechanisms.

### Exercise H — PITR and Backup Options

A Cloud SQL instance uses **Enhanced backups** and needs to be restored to a timestamp from yesterday.

**Answer:** Identify the **backup vault/data source** and PITR window, and use **point-in-time-restore** following Enhanced backups documentation. Restore to a **new instance**; do not treat it as an in-place fix on the primary or blindly reuse the Standard backup clone workflow.

### Exercise I — Editions and SQL Server Licensing

Someone claims: **Cloud SQL Enterprise Plus** means **SQL Server Enterprise** is selected for every database.

**Answer:** False. Cloud SQL edition is the **cloud service tier**, whereas SQL Server edition is the **engine license/feature tier**. For SQL Server, supported version/edition combinations vary; choose both explicitly and account for licensing costs.

### Exercise J — Security and Cost

A Java service stores its SQL password in a Dockerfile `ENV`, Cloud SQL allows **0.0.0.0/0** on public IP, and backup retention is 1 day despite a 30-day policy.

**Answer:** Move the password to Secret Manager or IAM DB auth where supported and rotate the exposed credential; remove the wide-open public allowlist and prefer private IP/connector; configure backup options/retention for **30 days** and test restores; review IAM, logs, CMEK, and budgets. **Do not assume merely removing ENV in a new image revokes the password** — revoke/rotate it in the DB.

## 18. Operational Checklist and Summary

### Before Deployment

1. Confirm **engine/version/edition/region** and support lifecycle.
2. Size vCPU/RAM/storage and configure **REGIONAL HA** per RTO/SLO; plan cross-region DR.
3. Finalize public/private/PSC and connectors, TLS, service identity, DB users/roles, and secrets.
4. Enable backups and PITR under the right backup option, run restore rehearsals, and check key/location placement.
5. Test query latency, connection pools, and Java backend scaling behavior.
6. Set up dashboards, error alerts, backup alerts, billing budgets, and on-call ownership.

### During an Incident

1. Isolate network/IAM/DB login/SQL GRANT/query/HA/backup layers instead of changing everything at once.
2. For Java deployment issues, roll back traffic/schema per compatibility guidelines.
3. For data corruption/loss, **halt harmful writes**, preserve logs, and restore to a new instance for comparison.
4. For failover, allow controlled connection reconnects and verify **idempotent** transactions.
5. Document actual RTO/RPO, costs, and follow-up actions.

**Remember:** Cloud SQL makes operating PostgreSQL, MySQL, and SQL Server easier, but **does not eliminate DBA discipline**. Choosing the right engine and edition, scoping IAM and SQL privileges, securing connectivity, controlling JDBC pools, enabling backups/PITR, and practicing restores form the foundation for resilient Java applications.

## 19. Official Google Cloud Documentation

1. [Cloud SQL FAQ](https://docs.cloud.google.com/sql/faq) — overview of all three engines and limits.
2. [Database versions and version policies](https://docs.cloud.google.com/sql/docs/db-versions) — version support/EOL and extended support.
3. [Cloud SQL PostgreSQL editions](https://docs.cloud.google.com/sql/docs/postgres/editions-intro) — Enterprise/Enterprise Plus.
4. [Cloud SQL MySQL editions](https://docs.cloud.google.com/sql/docs/mysql/editions-intro) — edition configurations and capabilities.
5. [Cloud SQL SQL Server editions](https://docs.cloud.google.com/sql/docs/sqlserver/editions-intro) — Cloud SQL editions and SQL Server licensing/versions.
6. [Create PostgreSQL instances](https://docs.cloud.google.com/sql/docs/postgres/create-instance) — gcloud flags, editions, CPU/RAM.
7. [Create MySQL instances](https://docs.cloud.google.com/sql/docs/mysql/create-instance) — versions and machine shapes.
8. [Create SQL Server instances](https://docs.cloud.google.com/sql/docs/sqlserver/create-instance) — passwords and license options.
9. [Choose connection options](https://docs.cloud.google.com/sql/docs/postgres/connection-options) — private/public IP, connectors.
10. [Cloud SQL Auth Proxy](https://docs.cloud.google.com/sql/docs/postgres/connect-auth-proxy) — ADC, TLS, and sidecars.
11. [Connect Cloud Run to Cloud SQL](https://docs.cloud.google.com/sql/docs/postgres/connect-run) — networking/Cloud Run integration.
12. [PostgreSQL IAM database authentication](https://docs.cloud.google.com/sql/docs/postgres/iam-logins) — instanceUser, Client, and SQL GRANTs.
13. [MySQL IAM database authentication](https://docs.cloud.google.com/sql/docs/mysql/iam-logins) — IAM DB users/groups.
14. [SQL Server IAM authentication limitations](https://docs.cloud.google.com/sql/docs/sqlserver/iam-authentication) — IAM DB login not supported.
15. [Cloud SQL high availability](https://docs.cloud.google.com/sql/docs/postgres/high-availability) — regional HA and failover.
16. [SQL Server replication](https://docs.cloud.google.com/sql/docs/sqlserver/replication) — read replicas.
17. [Choose backup options](https://docs.cloud.google.com/sql/docs/postgres/backup-recovery/backup-options) — Standard vs. Enhanced.
18. [Point-in-time recovery](https://docs.cloud.google.com/sql/docs/postgres/backup-recovery/pitr) — Standard/Enhanced recovery workflows.
19. [Monitor instances](https://docs.cloud.google.com/sql/docs/postgres/monitor-instance) — System Insights and Monitoring.
