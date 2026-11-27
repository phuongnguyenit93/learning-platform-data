# IAM Database Authentication and User Management

> **Chapter:** Cloud SQL and AlloyDB  
> **Lesson:** IAM Database Authentication and User Management  
> **Module:** CLOUD_PROVIDERS_GCP

In the **CLOUD_PROVIDERS_GCP** module, learners explore Google Cloud from project, IAM, and VPC organization through Compute Engine, GKE, Cloud Run, storage services, and databases. Through real-world deployments, learners select services, secure resources, automate delivery, observe reliability, and control costs. A critical aspect of Java application security is **defining who can log into the database, under which identity, over which network path, and which data operations they are allowed to perform**.

**IAM database authentication** lets Cloud SQL and AlloyDB use Google Cloud IAM identities with **short-lived OAuth 2.0 access tokens** instead of static database passwords. However, **IAM does not automatically grant `SELECT`, `INSERT`, or `DELETE` privileges inside PostgreSQL/MySQL**. A successful connection must pass **independent layers**: identity/IAM, network/TLS, database account, and SQL privileges.

This lesson focuses on **Cloud SQL for PostgreSQL/MySQL** and **AlloyDB for PostgreSQL**, especially Java workloads on Cloud Run or GKE. **Cloud SQL for SQL Server does not support the IAM database authentication model described here**, even though Google Cloud IAM still manages the instance resource. The commands below that create users, modify IAM, change flags, and run SQL **have real effects** — execute them only in an approved sandbox project.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Distinguish **IAM login permission**, **connection authorization**, **database accounts**, and **SQL privileges**.
2. Compare **built-in password authentication**, **individual IAM authentication**, and **IAM group authentication**.
3. Configure IAM database authentication for **Cloud SQL PostgreSQL/MySQL** and **AlloyDB PostgreSQL** using their respective database flags.
4. Grant the right roles (`roles/cloudsql.instanceUser`, `roles/cloudsql.client`, `roles/alloydb.databaseUser`, and `roles/alloydb.client`) as needed.
5. Log in via **Cloud SQL Auth Proxy/Java Connector** or **AlloyDB Auth Proxy** using automatic IAM authentication.
6. Create database users/groups and apply `GRANT` and `REVOKE` following least privilege.
7. Connect Java JDBC with IAM authentication without storing service account keys or DB passwords in repositories.
8. Manage onboarding/offboarding lifecycles, account naming, group propagation, auditing, and application connection pooling.
9. Isolate IAM 403 errors, database `permission denied` errors, authentication failures, and network errors.
10. Complete exercises and an authorization case study for Orders API, Billing Worker, and an analytics team.

## 2. Four Control Layers Before Reading Any Data

~~~mermaid
flowchart LR
    App["Java Orders API<br/>runtime service account"]
    IAM["Google Cloud IAM<br/>login + connect"]
    Network["VPC / PSC / IP<br/>connector + TLS"]
    DBLogin["Database account<br/>IAM user or group"]
    SQL["PostgreSQL / MySQL<br/>GRANT, role, schema"]
    Data["orders database<br/>tables / views"]
    App --> IAM --> Network --> DBLogin --> SQL --> Data
~~~

| Layer | What Does It Check? | Example |
|---|---|---|
| **Google IAM** | Does the principal have permission to connect and log into the instance? | `cloudsql.instances.login`, `alloydb.users.login` |
| **Network path** | Does the client have routing, TLS/connector, and matching connectivity policy? | Cloud SQL Auth Proxy, VPC private IP, AlloyDB Auth Proxy |
| **Database user** | Is the user/service account/group registered on the instance or cluster? | `dev@example.com`, `orders-api@PROJECT_ID.iam` |
| **SQL authorization** | Which database, schema, and tables can the DB user/role access? | `GRANT CONNECT`, `GRANT USAGE`, `GRANT SELECT` |

Someone holding `roles/cloudsql.admin` on a project does **not automatically** get permission to read order data. Conversely, running `GRANT SELECT` on a PostgreSQL role **does not grant external IAM login permission**. SQL roles and Google Cloud IAM roles are **two separate authorization systems** that must be governed and audited together.

### 2.1. Authentication vs. Authorization

- **Authentication:** verifies who the principal logging in is — via database password or IAM access token.
- **Connection authorization:** permission to use a connector/proxy to open a tunnel, checked by Google Cloud.
- **Database authorization:** after login, PostgreSQL/MySQL checks `GRANT`s, ownership, schemas, and row-level security if applied.
- **Application authorization:** Java code still checks tenant/user boundaries — never rely solely on a SQL account to decide whether customer A may read customer B's orders.

**Do not treat IAM database authentication as an automatic per-tenant data guard.** If a Java API shares one runtime SA and one database account, the DB has no inherent awareness of which HTTP caller made the request; careful domain authorization or RLS context design is still needed.

## 3. Comparing Cloud SQL and AlloyDB

| Topic | Cloud SQL for PostgreSQL | Cloud SQL for MySQL | AlloyDB for PostgreSQL |
|---|---|---|---|
| Engine | PostgreSQL | MySQL | PostgreSQL-compatible |
| Instance IAM flag | `cloudsql.iam_authentication=on` | `cloudsql_iam_authentication=on` | `alloydb.iam_authentication=on` |
| Group IAM flag | Uses the IAM flag above | Uses the IAM flag above | Also requires `alloydb.iam_group_authentication=on` |
| IAM login role | `roles/cloudsql.instanceUser` | `roles/cloudsql.instanceUser` | `roles/alloydb.databaseUser` |
| Connector/proxy role | `roles/cloudsql.client` | `roles/cloudsql.client` | `roles/alloydb.client` |
| Separate from SQL privileges | PostgreSQL `GRANT` | MySQL `GRANT` | PostgreSQL `GRANT` |
| Proxy | Cloud SQL Auth Proxy **v2** | Cloud SQL Auth Proxy **v2** | **AlloyDB Auth Proxy** |
| IAM group | Cloud Identity group; account created on member login | Similar; note MySQL naming | IAM group on cluster; enable both flags |
| User provisioning | Scoped to **instance** | Scoped to **instance** | IAM user created on **cluster** |
| Token | OAuth access token, typically valid ~**1 hour** | Same | Short-lived OAuth access token |
| Built-in users | Can coexist with IAM users | Can coexist | Can coexist |

**Cloud SQL IAM database authentication does not apply to SQL Server.** Seeing `roles/cloudsql.client` or `roles/cloudsql.admin` on a SQL Server instance does not turn a SQL Server account into an IAM database user.

### 3.1. Individual IAM vs. IAM Group vs. Password

| Management Model | Advantages | Trade-offs |
|---|---|---|
| **Built-in username/password** | Compatible with legacy tools, no IAM token needed | Requires password storage/rotation/revocation; easy to share accounts |
| **Individual IAM user / service account** | Explicit identity, short-lived token login, centralized IAM revocation | Must provision each DB account and assign SQL privileges |
| **IAM group** | Role-based group management, easier onboarding/offboarding | Group membership propagation delay; needs migration if individual accounts exist |
| **Workforce Identity Federation** (where supported) | Avoids issuing Google accounts to every external user | Different limits/setup from IAM groups; verify engine and connector support |

For production Java apps, **prefer a dedicated service identity** per workload. For human analytical or troubleshooting access, **IAM groups** usually cut down manual edits and simplify centralized revocation.

## 4. Automatic IAM Authentication vs. Manual Authentication

~~~mermaid
sequenceDiagram
    participant Java as Java / psql
    participant Proxy as Cloud SQL / AlloyDB connector
    participant IAM as Google IAM
    participant DB as Database
    Java->>Proxy: Connect with IAM DB username
    Proxy->>IAM: Fetch/refresh short-lived access token
    IAM-->>Proxy: Token bound to runtime principal
    Proxy->>DB: Establish authenticated, encrypted connection
    DB->>DB: Verify IAM user + SQL privileges
    DB-->>Java: Query result / permission denied
~~~

### 4.1. Automatic IAM Database Authentication

- **Cloud SQL:** supported via Cloud SQL Auth Proxy v2 `--auto-iam-authn` or Cloud SQL Language Connectors (Java/Go/Python).
- **AlloyDB:** supported via AlloyDB Auth Proxy `--auto-iam-authn` or AlloyDB Language Connectors.
- The connector **automatically fetches and refreshes access tokens** for new connections — ideal for Java services using connection pools.
- The principal **running the connector must match the principal registered as the IAM DB user**, unless valid service account impersonation is configured.
- Client-to-local-proxy traffic typically uses loopback; **the proxy encrypts the hop to the database**, so protect the local listener from untrusted users on the host.

**This is the recommended approach** for long-running services. It avoids baking one-hour tokens into `application.properties` or forcing operators to rotate static passwords manually.

### 4.2. Manual IAM Database Authentication

The workflow **fetches an OAuth access token** and passes it as the IAM DB user's password in `psql`/`mysql`; typically used for ad-hoc testing or special tools.

~~~bash
# Cloud SQL PostgreSQL illustration on bash/Cloud Shell.
# Never print tokens or enable shell tracing; SSL connection required.
PGPASSWORD="$(gcloud sql generate-login-token)" \
  psql "hostaddr=DATABASE_IP dbname=orders user=dev@example.com sslmode=require" \
  --no-password
~~~

**Warnings:**

- Tokens expire in about **one hour**; new connections opened after expiry fail, so never use this as a static Java pool config.
- `psql` has length limits for interactive password prompts; pass the token via environment variable per docs and **never paste tokens into consoles, logs, or tickets**.
- Direct access requires network reachability to the instance IP and TLS configuration per policy. `sslmode=require` encrypts traffic, yet production policy may require full certificate/hostname verification.
- Never swap in `gcloud auth print-access-token` carelessly for `gcloud sql generate-login-token` when login-scoped tokens are required.
- Under **Context-Aware Access**, Cloud SQL/AlloyDB connectors with IAM DB auth have specific restrictions; verify supported direct connection paths.

### 4.3. Why Can ADC Cause Confusion?

`gcloud auth login` sets the **gcloud CLI** credential; `gcloud auth application-default login` creates **Application Default Credentials** for local apps and connectors. They are not guaranteed to be the same identity.

If you add DB user `dev@example.com` while the local proxy runs using `ops@example.com` ADC, **automatic IAM authentication cannot arbitrarily log in as `dev@example.com`**. On Cloud Run/GKE, verify the **runtime service account** or Workload Identity Federation for GKE — never infer it from whoever deployed the service.

## 5. Task-Based IAM Roles: Least Privilege

### 5.1. Cloud SQL

| Identity | IAM Role | Scope / Meaning |
|---|---|---|
| IAM DB user or service account | `roles/cloudsql.instanceUser` | Grants `cloudsql.instances.login` for IAM login |
| Identity running Cloud SQL Auth Proxy / Java Connector | `roles/cloudsql.client` | Grants `cloudsql.instances.connect` and connector access |
| Database operator | Required DB/instance admin roles | For operators only — **never grant to Java runtime** |
| SQL data reader | **PostgreSQL/MySQL GRANT**, not a Cloud IAM role | Scoped strictly to tables/schemas needed by the workload |

If the Java connector runs under the **same** runtime service account, that account generally needs **both Instance User and Cloud SQL Client**. IAM bindings apply at the scopes supported by the product; Cloud SQL IAM login is managed via project IAM policy, so bound projects/resources per architecture and org policy.

### 5.2. AlloyDB

| Identity | IAM Role | Meaning |
|---|---|---|
| IAM DB user/group | `roles/alloydb.databaseUser` | Permits database IAM login |
| Principal using AlloyDB Auth Proxy / Language Connector | `roles/alloydb.client` | Permits establishing connections via connector |
| Principal calling API to verify permissions | `roles/serviceusage.serviceUsageConsumer` | Required per IAM/connector documentation |
| Data reader/writer | PostgreSQL `GRANT` | Real SQL authorization — never `roles/alloydb.admin` |

In a Java workload using AlloyDB Auth Proxy and automatic IAM auth, the runtime identity typically needs **Database User + AlloyDB Client + Service Usage Consumer**, plus a **database account on the cluster** and SQL grants.

**Never grant `roles/owner`, `roles/editor`, `roles/cloudsql.admin`, or `roles/alloydb.admin` to a Java app just to clear a 403.** Infrastructure admin roles do not replace SQL authorization.

## 6. Preparing the Cloud SQL PostgreSQL Lab

This lab uses an **existing Cloud SQL PostgreSQL instance** and an `orders` database. Do not spin up new instances just for this exercise, as that incurs unnecessary cost.

| Component | Assumed Value |
|---|---|
| Project | `PROJECT_ID` |
| Region | `asia-southeast1` |
| Cloud SQL instance | `orders-pg` |
| Instance connection name | `PROJECT_ID:asia-southeast1:orders-pg` |
| PostgreSQL database | `orders` |
| IAM human account | `dev@example.com` |
| IAM app SA | `orders-api@PROJECT_ID.iam.gserviceaccount.com` |
| PostgreSQL app username | `orders-api@PROJECT_ID.iam` |
| SQL application role | `orders_reader` |
| Schema/table | `public.orders` |

**Do not use `dev@example.com` or `PROJECT_ID` literally**; replace them with real sandbox values. If the database or table does not exist yet, a DBA creates it via controlled migrations; `GRANT` examples run only after the objects exist.

### 6.1. Non-Destructive Inspection

~~~bash
gcloud auth list
gcloud config get-value project

gcloud sql instances describe orders-pg \
  --project=PROJECT_ID \
  --format="yaml(name,region,connectionName,settings.databaseFlags)"

gcloud sql users list \
  --project=PROJECT_ID \
  --instance=orders-pg

gcloud projects get-iam-policy PROJECT_ID \
  --format="yaml(bindings)"
~~~

Check the existing **`cloudsql.iam_authentication`** flag, networking/IPs, backups, and roles beforehand. The Cloud SQL Admin API must be enabled, with sufficient IAM for read/write steps.

### 6.2. Enabling the IAM Flag: Watch Out for Wiping Other Flags

For Cloud SQL PostgreSQL, enable:

~~~text
cloudsql.iam_authentication=on
~~~

On a **running instance**, use Google Cloud Console → Cloud SQL → instance → Edit → Flags, or `gcloud sql instances patch`. **Critical warning:** `--database-flags` can **overwrite the entire existing flag list**. If you pass only the IAM flag, all other custom flags reset to defaults.

~~~bash
# SYNTAX ILLUSTRATION ONLY; do not run verbatim on production.
# Read all existing flags first and re-include them in the same patch.
gcloud sql instances patch orders-pg \
  --project=PROJECT_ID \
  --database-flags=cloudsql.iam_authentication=on
~~~

The sample command is **unsafe if the instance already has other flags**. Before applying in real environments, record all flags, confirm backups and a change window, preserve existing flags in the patch, and check for restarts/connection impact. On Cloud SQL MySQL, the flag name differs: **`cloudsql_iam_authentication`** (with underscores).

## 7. Hands-On A — Granting IAM Login for Cloud SQL

### 7.1. Step 1: Grant IAM Roles to the Learner

**The following commands alter project IAM** and are strictly for an authorized sandbox:

~~~bash
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="user:dev@example.com" \
  --role="roles/cloudsql.instanceUser"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="user:dev@example.com" \
  --role="roles/cloudsql.client"
~~~

`roles/cloudsql.instanceUser` enables **IAM DB login**; `roles/cloudsql.client` enables **Cloud SQL Auth Proxy/connectors**. Neither role creates a database user or grants `SELECT` on table `orders`.

### 7.2. Step 2: Create the IAM User on the Cloud SQL Instance

~~~bash
gcloud sql users create dev@example.com \
  --project=PROJECT_ID \
  --instance=orders-pg \
  --type=cloud_iam_user

gcloud sql users list \
  --project=PROJECT_ID \
  --instance=orders-pg
~~~

The user appears as **`CLOUD_IAM_USER`** on `orders-pg`. If the database already grants permissions to `PUBLIC`, the user may inherit them; therefore, never claim "zero privileges by default" without auditing `PUBLIC` grants alongside explicit grants.

### 7.3. Step 3: Grant Separate SQL Privileges

Connect **as an authorized DBA role** to run the SQL below — never use a learner account to self-grant:

~~~sql
-- PostgreSQL inside database orders:
CREATE ROLE orders_reader NOLOGIN;

GRANT CONNECT ON DATABASE orders TO orders_reader;
GRANT USAGE ON SCHEMA public TO orders_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO orders_reader;

-- Because IAM usernames contain @ and dots, double-quote the identifier.
GRANT orders_reader TO "dev@example.com";
~~~

**SELECT on all tables** illustrates an analytics role; for the Orders API, scope grants to specific tables/views to minimize data exposure. PostgreSQL `GRANT SELECT ON ALL TABLES` **applies only to existing tables**, not future tables. When needed, DBAs configure default privileges for the **exact table-creating role**:

~~~sql
-- Example only: run by a DBA/privileged role to cover
-- future tables created by role app_owner.
ALTER DEFAULT PRIVILEGES FOR ROLE app_owner IN SCHEMA public
  GRANT SELECT ON TABLES TO orders_reader;
~~~

Verify beforehand that `app_owner` exists and actually creates the tables. Default privileges **do not apply retroactively** to existing tables and **do not cover tables created by other owners**.

### 7.4. Step 4: Connect via Cloud SQL Auth Proxy v2

On an authorized workstation or Cloud Shell, **ADC must belong to `dev@example.com`**:

~~~bash
gcloud auth application-default login

# Run in a dedicated terminal; requires cloud-sql-proxy v2 binary installed.
cloud-sql-proxy --auto-iam-authn \
  PROJECT_ID:asia-southeast1:orders-pg
~~~

In another terminal:

~~~bash
psql -h 127.0.0.1 -p 5432 \
  -U "dev@example.com" \
  --dbname=orders

# Inside psql:
# SELECT current_user, current_database();
# SELECT COUNT(*) FROM public.orders;
~~~

Cloud SQL Auth Proxy listens on loopback by default and needs no database password. **The local client → proxy hop is unencrypted loopback**, while the proxy provides mTLS/encryption to Cloud SQL. On a shared VM or bastion, restrict other users from reaching the proxy port/socket because the connector authenticates as its privileged IAM principal.

**Networking still matters:** Cloud SQL connectors need outbound TCP 443 to Cloud APIs and TCP 3307 to the instance, and will not build a VPC route when using **private IP**. With `--private-ip`, the proxy host must already have a network path to the Cloud SQL instance.

### 7.5. Test Both "Allow" and "Deny"

~~~sql
-- Succeeds when CONNECT, USAGE, and SELECT are granted:
SELECT COUNT(*) FROM public.orders;

-- If orders_reader lacks DELETE, NEVER run the statement below
-- against real data; test only on a scratch table.
-- DELETE FROM public.orders WHERE id = 1;
~~~

**Never use production data to test negative permissions.** Use a scratch table, or use `has_table_privilege` to verify privileges without mutating anything:

~~~sql
SELECT current_user;
SELECT has_table_privilege(current_user, 'public.orders', 'SELECT') AS can_read;
SELECT has_table_privilege(current_user, 'public.orders', 'DELETE') AS can_delete;
~~~

Expect `can_read=true` and `can_delete=false` when the role has only `SELECT` and no extra grants via `PUBLIC` or other roles. If results differ, inspect role memberships, table ownership, and remaining grants.

## 8. Hands-On B — IAM Service Account for the Java Orders API

A Java app on Cloud Run or GKE should never use a developer's personal account. Create a dedicated identity:

~~~bash
gcloud iam service-accounts create orders-api \
  --project=PROJECT_ID \
  --display-name="Orders API database identity"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:orders-api@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/cloudsql.instanceUser"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:orders-api@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/cloudsql.client"
~~~

Register the **shortened name** as the PostgreSQL IAM database user:

~~~bash
gcloud sql users create "orders-api@PROJECT_ID.iam" \
  --project=PROJECT_ID \
  --instance=orders-pg \
  --type=cloud_iam_service_account
~~~

**PostgreSQL IAM naming rule:** `orders-api@PROJECT_ID.iam.gserviceaccount.com` → **`orders-api@PROJECT_ID.iam`**. The shortened name must not exceed **63 characters**. Human user accounts still keep the full email such as `dev@example.com`.

Grant minimal SQL privileges — for example, an Orders API that **only reads** existing orders:

~~~sql
GRANT CONNECT ON DATABASE orders TO orders_reader;
GRANT USAGE ON SCHEMA public TO orders_reader;
GRANT SELECT ON public.orders TO orders_reader;
GRANT orders_reader TO "orders-api@PROJECT_ID.iam";
~~~

For an Orders API that actually writes orders, define a separate role like `orders_writer` with `INSERT/UPDATE` on the exact tables — never grant broad admin roles out of convenience. **The runtime service account must be attached to the Cloud Run revision or GKE KSA/GSA mapping** per your org model; creating the SA in IAM **does not attach it** to a workload automatically.

### 8.1. Java JDBC with Cloud SQL Java Connector and ADC

In your Maven project, pin **compatible versions** for:

- `com.google.cloud.sql:postgres-socket-factory` (Cloud SQL Java Connector).
- `org.postgresql:postgresql` (PostgreSQL JDBC).
- `com.zaxxer:HikariCP` for connection pooling.

Simple Java 17 example verifying IAM login via JDBC; environment variables hold **configuration, not tokens or passwords**:

~~~java
package com.example.orders;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.Properties;

public final class DatabaseCheck {
    public static void main(String[] args) throws SQLException {
        String instance = System.getenv("INSTANCE_CONNECTION_NAME");
        String database = System.getenv("DB_NAME");
        String iamUser = System.getenv("DB_IAM_USER");
        if (instance == null || database == null || iamUser == null) {
            throw new IllegalArgumentException("Missing database configuration");
        }

        Properties p = new Properties();
        p.setProperty("socketFactory",
                "com.google.cloud.sql.postgres.SocketFactory");
        p.setProperty("cloudSqlInstance", instance);
        p.setProperty("enableIamAuth", "true");
        p.setProperty("user", iamUser);
        p.setProperty("password", "ignored-by-IAM-connector");
        p.setProperty("sslmode", "disable");
        p.setProperty("ipTypes", "PRIVATE");
        p.setProperty("cloudSqlRefreshStrategy", "lazy");

        try (Connection c = DriverManager.getConnection(
                     "jdbc:postgresql:///" + database, p);
             Statement stmt = c.createStatement();
             ResultSet rows = stmt.executeQuery(
                     "SELECT current_user, current_database()")) {
            if (rows.next()) {
                System.out.println("Database user=" + rows.getString(1)
                        + ", database=" + rows.getString(2));
            }
        }
    }
}
~~~

Clarifying easily confused properties:

- `enableIamAuth=true`: Java connector automatically acquires an IAM login token via runtime **ADC**.
- `user`: **shortened database IAM username**, here `orders-api@PROJECT_ID.iam`.
- `password`: **placeholder value ignored** by automatic IAM auth, only present so the PostgreSQL JDBC driver passes its non-empty password check; **not a real secret**.
- `sslmode=disable` applies to the **PostgreSQL JDBC driver**, because **Cloud SQL Java Connector manages the encrypted tunnel to the instance itself**. Never copy this setting to a **direct IP connection** without a connector.
- `ipTypes=PRIVATE`: use only when the workload has a VPC/private IP path to Cloud SQL. The connector **never creates network routes**.
- `cloudSqlRefreshStrategy=lazy` suits certain serverless workloads by avoiding background refresh threads.

For production, wrap with **HikariCP**, bounded pool sizes, statement timeouts, compliant secret handling, and monitoring. **Never open a new database connection per HTTP request**; IAM login has per-instance rate limits, and constant connection churn adds latency and DB load.

### 8.2. Cloud SQL Connector vs. Cloud Run "Connection Attachment"

Cloud Run offers built-in Cloud SQL integration via service/instance connection flags. If using **Java JDBC Socket Factory**, the app executes the connector flow in-process; if using **Cloud SQL Auth Proxy**, a local proxy handles transport/auth. Avoid stacking **redundant connector layers** unnecessarily; pick one topology and configure IAM and networking for that choice.

## 9. Hands-On C — IAM Database Authentication on AlloyDB

AlloyDB for PostgreSQL is a separate service: **users are created at the cluster level, flags are set on instances**, and IAM roles and Auth Proxy differ from Cloud SQL.

| Lab Value | Example |
|---|---|
| Region | `asia-southeast1` |
| AlloyDB cluster | `orders-alloy-cluster` |
| Primary instance | `orders-primary` |
| Database | `orders` |
| IAM principal | `dev@example.com` or dedicated runtime SA |
| Cluster user type | `IAM_BASED` or `IAM_GROUP` |
| Auth Proxy binary | `alloydb-auth-proxy` |

### 9.1. Inspect Flags Before Enabling

~~~bash
gcloud alloydb clusters describe orders-alloy-cluster \
  --project=PROJECT_ID \
  --region=asia-southeast1

gcloud alloydb instances describe orders-primary \
  --project=PROJECT_ID \
  --cluster=orders-alloy-cluster \
  --region=asia-southeast1

gcloud alloydb users list \
  --project=PROJECT_ID \
  --cluster=orders-alloy-cluster \
  --region=asia-southeast1
~~~

Enable `alloydb.iam_authentication=on` on the **instance**. If using IAM groups, enable **both**:

~~~text
alloydb.iam_authentication=on
alloydb.iam_group_authentication=on
~~~

**Do not overwrite existing flags:** `gcloud alloydb instances update --database-flags=...` can **reset any omitted flags**. Back up current flags, preserve them in the update, account for maintenance/restarts, and never pass `--update-mode=FORCE_APPLY` in production without controlled justification. AlloyDB IAM authentication is **off by default** on instances per current docs.

### 9.2. Grant AlloyDB IAM Roles and Create the Database User

~~~bash
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="user:dev@example.com" \
  --role="roles/alloydb.databaseUser"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="user:dev@example.com" \
  --role="roles/alloydb.client"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="user:dev@example.com" \
  --role="roles/serviceusage.serviceUsageConsumer"

gcloud alloydb users create dev@example.com \
  --project=PROJECT_ID \
  --cluster=orders-alloy-cluster \
  --region=asia-southeast1 \
  --type=IAM_BASED
~~~

These commands create **login permission**, not SQL table read privileges. A DBA still runs PostgreSQL `GRANT` in database `orders`, just like Section 7:

~~~sql
GRANT CONNECT ON DATABASE orders TO orders_reader;
GRANT USAGE ON SCHEMA public TO orders_reader;
GRANT SELECT ON public.orders TO orders_reader;
GRANT orders_reader TO "dev@example.com";
~~~

### 9.3. Automatic IAM Auth via AlloyDB Auth Proxy

~~~bash
# Requires valid VPC/PSC connectivity and alloydb-auth-proxy binary.
alloydb-auth-proxy --auto-iam-authn \
  projects/PROJECT_ID/locations/asia-southeast1/clusters/orders-alloy-cluster/instances/orders-primary

# Another terminal, when ADC belongs to dev@example.com:
psql -h 127.0.0.1 -p 5432 -U "dev@example.com" --dbname=orders
~~~

AlloyDB Auth Proxy uses an **instance URI** rather than a Cloud SQL connection name. Network/private IP/PSC reachability must be configured properly. Quick gcloud CLI alternative:

~~~bash
# Beta/Preview CLI: for manual testing; verify current support status.
gcloud beta alloydb connect orders-primary \
  --project=PROJECT_ID \
  --cluster=orders-alloy-cluster \
  --region=asia-southeast1 \
  --auto-iam-authn
~~~

This command requires `psql` and proper network reachability. It **does not** create clusters or VPC tunnels automatically; the active gcloud principal must match the IAM database user or use authorized impersonation.

### 9.4. Differences for Java Workloads

- Use **AlloyDB Auth Proxy** or the **AlloyDB Language Connector** supporting automatic IAM auth — **never point Cloud SQL Socket Factory** at AlloyDB.
- The runtime service account needs `roles/alloydb.databaseUser`, `roles/alloydb.client`, and `roles/serviceusage.serviceUsageConsumer` per connection method.
- Create the database user on the **cluster** with the shortened SA name (`orders-api@PROJECT_ID.iam`).
- Run PostgreSQL `GRANT` statements inside the target database.
- Watch the AlloyDB instance **per-minute login quota** and pool sizing; prevent serverless scaling from causing login storms.

## 10. IAM Group Authentication: Team-Based Access

### 10.1. Cloud SQL IAM Groups

If team `db-analysts@example.com` uses Cloud SQL PostgreSQL:

~~~bash
# Cloud Identity group must already exist.
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="group:db-analysts@example.com" \
  --role="roles/cloudsql.instanceUser"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="group:db-analysts@example.com" \
  --role="roles/cloudsql.client"

gcloud sql users create db-analysts@example.com \
  --project=PROJECT_ID \
  --instance=orders-pg \
  --type=cloud_iam_group
~~~

A DBA grants SQL privileges to the **group database role**:

~~~sql
GRANT CONNECT ON DATABASE orders TO "db-analysts@example.com";
GRANT USAGE ON SCHEMA public TO "db-analysts@example.com";
GRANT SELECT ON public.orders TO "db-analysts@example.com";
~~~

Members log in with their **personal IAM identities**, not a shared group password. Cloud SQL creates the corresponding member database account on first login. When Cloud Identity group membership changes, propagation can take **15 minutes or more**, excluding IAM policy propagation.

**Migration trap:** someone who already exists as an individual `CLOUD_IAM_USER` or `CLOUD_IAM_SERVICE_ACCOUNT` **does not automatically inherit SQL grants from a group**. To migrate to an IAM group, plan to **revoke/drop the individual DB account and let them log in via the group**, especially if that account owns active objects/privileges — never drop it in production without transferring ownership first.

### 10.2. AlloyDB IAM Groups

In addition to enabling both database flags, assign IAM roles to the **group** and create the group user on the cluster:

~~~bash
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="group:db-analysts@example.com" \
  --role="roles/alloydb.databaseUser"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="group:db-analysts@example.com" \
  --role="roles/serviceusage.serviceUsageConsumer"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="group:db-analysts@example.com" \
  --role="roles/alloydb.client"

gcloud alloydb users create db-analysts@example.com \
  --project=PROJECT_ID \
  --cluster=orders-alloy-cluster \
  --region=asia-southeast1 \
  --type=IAM_GROUP
~~~

Then execute SQL `GRANT`s for `"db-analysts@example.com"`. Group members still log in with their own individual accounts.

**Current limits to note:** AlloyDB supports up to **200 IAM groups per cluster** and PostgreSQL usernames up to 63 characters. **AlloyDB IAM group authentication is not compatible with managed connection pooling/PgBouncer** per current documentation; do not combine group users with managed pooling without verifying support. Group membership additions/removals also take time to sync.

### 10.3. Does Group Authentication Replace Database Roles?

**No.** IAM/Cloud Identity groups manage **who can log in**, while PostgreSQL SQL `GRANT`s determine **what they can do**. Granting a group `roles/alloydb.databaseUser` or `roles/cloudsql.instanceUser` **does not let members read tables** until SQL `GRANT`s are issued.

## 11. Database Username Rules and Engine Differences

| Principal | Cloud SQL PostgreSQL / AlloyDB PostgreSQL | Cloud SQL MySQL |
|---|---|---|
| User `dev@example.com` | `dev@example.com` | Local username `dev` (strips `@example.com`) |
| SA `orders-api@PROJECT_ID.iam.gserviceaccount.com` | `orders-api@PROJECT_ID.iam` | Local username `orders-api` |
| Max username length | **63 characters** in PostgreSQL identifiers | **32 characters** in MySQL usernames |
| Login | Full email for humans; SA strips `.gserviceaccount.com` | Uses shortened name per engine/cloud connector |
| Database grants | `GRANT ... TO "name@domain"` | `GRANT ... TO 'name'@'host'` per user/host |

**Important MySQL limitation:** two human emails `dev@company-a.com` and `dev@company-b.com` both strip down to username `dev`, so both cannot coexist on the same MySQL instance under this IAM scheme. DBAs must design conflict-free account naming. **Never copy PostgreSQL `GRANT` statements straight into MySQL** — role syntax, grants, and host semantics differ.

### 11.1. Key Practical Differences for Cloud SQL MySQL

- The IAM flag is `cloudsql_iam_authentication=on` (not `cloudsql.iam_authentication`).
- IAM login still requires `roles/cloudsql.instanceUser`; using proxy/connector also requires `roles/cloudsql.client`.
- Add the IAM user/service account/group on the instance, then grant privileges with MySQL `GRANT`.
- IAM accounts use lowercase usernames; MySQL imposes a **32-character** username cap and disallows two IAM emails colliding on the same local name.
- MySQL 5.6 **does not support IAM database authentication**; check the actual engine/version.

## 12. Security, Auditing, and User Lifecycle

### 12.1. Onboarding

1. Identify the principal: developer, BI analyst, Java runtime, or CI migration runner.
2. Choose **individual human, IAM group, or user-managed service account**; never default to Editor.
3. Grant the exact **IAM database login + connector roles** on the project/resources.
4. Create the IAM DB account on the **Cloud SQL instance** or **AlloyDB cluster**.
5. Grant minimal **database roles** and `GRANT`s to required databases/schemas/tables.
6. Verify the network path (private IP/PSC, proxy/TLS) and test login with the target principal.
7. Run positive and negative SQL privilege checks on test data.
8. Record owner, purpose, review date, and audit evidence.

### 12.2. Offboarding

**Revoking IAM login** blocks future sign-ins once effective, yet **do not assume it immediately terminates existing open connections**. During a security incident:

1. Revoke the IAM role or group membership.
2. Inspect active sessions and terminate them per change/incident procedures if needed.
3. Revoke SQL grants/role memberships and reassign dependent object ownership.
4. Drop the DB account/group object per plan — **never carelessly drop data or role owners**.
5. Revoke the runtime SA or redeploy workloads if a service identity was compromised.
6. Audit access and verify the user can no longer log in or query.

**IAM group propagation has latency.** In urgent revocations, do not just wait for group sync and assume you are safe; apply network blocks, SQL revokes, and DB session termination immediately.

### 12.3. Auditing

- Google Cloud Audit Logs capture admin/IAM actions; **Data Access logs** must be configured per product to record login/access events (note many types are off by default).
- PostgreSQL/MySQL engine logs and database audit extensions can log logins and queries per configuration.
- Never assume IAM audit logs automatically record **every SQL statement and returned row**.
- Never log OAuth tokens, credentials, full queries containing PII, database dumps, or secrets into application logs.
- Monitor IAM policy edits, DB account creation/deletion, role grants, failed logins, session spikes, and permission-denied errors.

### 12.4. Connectivity, HA, and Cost

- Never open a new DB connection per HTTP request: use HikariCP/connection pools sized for Cloud Run/GKE concurrency.
- IAM tokens live roughly 1 hour and connectors auto-refresh them for **new connections**; an existing open connection is not dropped simply because the token used at handshake expired.
- IAM database logins have per-instance rate quotas; connection storms can trigger auth failures even when DB CPU is low.
- Failover/read replicas can have separate auth settings; **Cloud SQL read replicas do not always inherit IAM auth enablement from the primary** — check replica flags explicitly.
- Proxies/connectors still consume client CPU/network; Cloud SQL/AlloyDB instances, storage, egress, and Cloud Logging/Monitoring remain usage-billed.
- With **Workload Identity Federation for GKE**, distinguish Kubernetes ServiceAccount mappings from database IAM usernames — never turn a KSA email into a PostgreSQL user unless it is the actual impersonated/authenticated principal.

## 13. Diagnosis: IAM Error, SQL Error, or Network Error?

| Error / Symptom | Likely Cause | What to Check |
|---|---|---|
| Proxy fails with `403 PERMISSION_DENIED` | Missing `roles/cloudsql.client` or `roles/alloydb.client`; wrong identity | ADC/runtime SA, project/instance IAM |
| Database reports login/authentication failed | IAM flag off, user missing, missing InstanceUser/DatabaseUser | Flags, IAM roles, and DB users |
| Cloud SQL IAM login succeeds yet `permission denied for table` | Missing SQL `GRANT` / schema `USAGE` | PostgreSQL `\dp`, role membership/ownership |
| AlloyDB login 403 | Missing DatabaseUser, ServiceUsageConsumer, or Client | IAM/connector logs, cluster user |
| `psql` hangs and times out | No VPC route/private IP/PSC, or proxy not running | Local listener, firewall, ports 443/3307/5433, network path |
| Java app reports user/password mismatch | Connector uses different ADC than `DB_IAM_USER` | Runtime SA, `DB_IAM_USER` |
| Token expires when pool opens new connection | Static manual IAM token | Switch to automatic IAM auth/refresh |
| IAM group member lacks grants | Individual DB account exists or membership hasn't synced | User type, group/DB grants, propagation |
| PostgreSQL role name truncated | Shortened IAM SA exceeds 63 characters | Shorter SA name or appropriate impersonation |
| Cloud SQL MySQL user collision | Stripping domain causes two emails to share local username | Redesign IAM principals/naming |
| Offboarded user still has active session | Revoke blocks new logins only; existing connections remain | Active DB sessions, revoke SQL/network, terminate safely |
| Java opens too many connections | Hikari pool too large, high Cloud Run scale | DB connection count, instance max, auth quota |
| Cloud SQL IAM auth fails on read replica | Replica flag not enabled | Describe replica flags |
| AlloyDB group via managed pool fails | Unsupported group + managed pooling per docs | Use supported direct/pool-free connection or individual accounts |
| Context-Aware Access breaks connector auth | Connector incompatible with IAM DB auth under policy | Review policy and supported direct connectivity |

### 13.1. Six-Step Workflow to Avoid Over-Privilege

1. **Verify the principal**: `gcloud auth list` is not enough — check **ADC/runtime identity**.
2. **Verify the resource**: right project, Cloud SQL connection name or AlloyDB instance URI, region, database.
3. **Verify networking**: VPC/private IP/PSC, proxy listener, TLS, and egress.
4. **Verify Google IAM**: **login** permission and **connect** permission are distinct; check group propagation/role bindings.
5. **Verify DB account / SQL grants**: user exists, shortened name matches, `GRANT`s target the exact schema/table.
6. **Retest with a read-only query** and verify audit/metrics; never test using `Owner`.

### 13.2. Queries to Inspect Roles and Privileges

~~~sql
-- PostgreSQL, executed by a principal permitted to inspect catalogs:
SELECT current_user, session_user;

SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole
FROM pg_roles
WHERE rolname LIKE '%orders%' OR rolname LIKE '%example.com%';

SELECT has_database_privilege(current_user, 'orders', 'CONNECT') AS can_connect;
SELECT has_schema_privilege(current_user, 'public', 'USAGE') AS can_use_schema;
SELECT has_table_privilege(current_user, 'public.orders', 'SELECT') AS can_select;
~~~

Never run a test `DELETE` on a production table just to confirm "delete is denied." The `has_*_privilege` functions check permissions without altering data.

## 14. Case Study: Retail Orders API and Analytics

**Hypothetical scenario:** an enterprise runs `orders-api` on Cloud Run, `billing-worker` on GKE, and an analytics team reading reports. Orders and Billing access Cloud SQL PostgreSQL; the analytics team later moves certain workloads to AlloyDB for higher throughput.

### 14.1. Identity Separation

| Component | IAM Principal | Database Role |
|---|---|---|
| Orders API Cloud Run | `orders-api@PROJECT_ID.iam.gserviceaccount.com` | `orders_writer` on exact Orders tables |
| Billing Worker GKE | `billing-worker@PROJECT_ID.iam.gserviceaccount.com` | `billing_reader`, `billing_writer` per business logic |
| Analytics team | Cloud Identity `db-analysts@example.com` | `orders_reader` or read-only views |
| DBA / migration CI | Dedicated identity with controlled schema upgrade rights | DDL role, never used in HTTP runtime |
| Monitoring | Dedicated identity reading metrics/logs | Needs no DB login if reading Cloud Monitoring only |

### 14.2. Secure Processing Path

~~~mermaid
flowchart LR
    HTTP["HTTP Client"] --> Run["Cloud Run Orders API"]
    SA1["Orders runtime SA"] -. "IAM login + connect" .-> Run
    Run --> Connector["Cloud SQL Java Connector"]
    Connector --> DB["Cloud SQL PostgreSQL"]
    DB --> SQLRole["orders_writer<br/>only required GRANT"]
    Group["Analyst Cloud Identity group"] --> Proxy["Cloud SQL / AlloyDB Proxy"]
    Proxy --> Read["read-only views"]
~~~

Implementation rules:

1. Each workload gets its **own service account** — never developer accounts or default Editor.
2. Bind runtime identities to Cloud Run/GKE, grant IAM login/connect, create DB users, and assign matching SQL roles.
3. Java uses **automatic IAM auth + connection pooling**, storing zero static passwords or tokens.
4. Analysts belong to an **IAM group**, with SQL grants limited to reporting views/schemas.
5. Never share write credentials between Java runtimes and BI tools.
6. Offboard group memberships and runtime SAs under change control; inspect open sessions.
7. Collect IAM + DB audit logs, and regularly review grants, login failures, and costs.

### 14.3. Incident: "Has IAM Yet Cannot Read Table"

After granting `roles/cloudsql.instanceUser` and `roles/cloudsql.client` to `orders-api`, Cloud Run connects, yet SQL queries fail with `permission denied for table orders`.

**Diagnosis:** IAM opened the login/connect gates, but the DB account lacks schema `USAGE` or table `SELECT` via a SQL role. Fix by running `GRANT` on the exact table — **never** grant `roles/cloudsql.admin` or use the `postgres` superuser account for HTTP traffic.

### 14.4. Operational Evidence

| Question | Evidence |
|---|---|
| Which identity runs Java? | Cloud Run revision / GKE workload SA |
| Can the IAM principal log in/connect? | Project IAM bindings / role permissions |
| Is the user/group registered in the DB? | Cloud SQL users list / AlloyDB users list |
| Which objects allow SELECT/INSERT? | `pg_roles`, `\dp`, `has_table_privilege` |
| Are tokens auto-refreshed? | Connector config, auth failure logs, pool metrics |
| Can an offboarded analyst still log in? | Group membership, active sessions, and login test |
| Are DB costs healthy? | Connection counts, CPU, storage, billing, logs |

## 15. Practice Exercises and Self-Assessment

### Exercise 1 — Two Layers: IAM and SQL

A Java SA has `roles/cloudsql.instanceUser` and `roles/cloudsql.client` and is added to the PostgreSQL instance, yet `SELECT * FROM orders` returns `permission denied`.

**Question:** Does adding `roles/cloudsql.admin` fix the root cause? What must change?

**Hint:** No; grant SQL `CONNECT/USAGE/SELECT` on the right database/schema/table or role.

### Exercise 2 — Automatic vs. Manual

A Java service stores an access token in an environment variable without refreshing it for 24 hours. After an hour, new pool connections fail with authentication errors.

**Question:** Why? Which mechanism should replace it?

**Hint:** IAM tokens are short-lived; switch to a Cloud SQL/AlloyDB connector with automatic IAM auth.

### Exercise 3 — PostgreSQL Service Account Name

The service account is `orders-api@retail-prod.iam.gserviceaccount.com`. **What should the IAM database username be in PostgreSQL?** What length limit applies?

**Hint:** `orders-api@retail-prod.iam`; max 63 characters.

### Exercise 4 — MySQL vs. PostgreSQL

Cloud SQL MySQL has two IAM users: `dev@team-a.example` and `dev@team-b.example`.

**Question:** What problem does MySQL's domain stripping cause? Is the MySQL IAM flag spelled like PostgreSQL's?

**Hint:** Both collide on local username `dev`; MySQL's flag uses underscores: `cloudsql_iam_authentication`.

### Exercise 5 — AlloyDB Roles

A user is granted `roles/alloydb.databaseUser` yet gets a 403 connecting via AlloyDB Auth Proxy.

**Question:** Which extra IAM roles, database user/flags, and network components must be checked?

**Hint:** `roles/alloydb.client`, `serviceusage.serviceUsageConsumer`, instance flags, cluster user, VPC/PSC.

### Exercise 6 — Group Does Not Inherit Grants

`dev@example.com` already exists as an individual IAM DB user; the DBA adds the `db-analysts@example.com` group and grants `SELECT` to the group. The developer still lacks access.

**Question:** Why? How do you migrate safely?

**Hint:** Individual IAM accounts do not automatically use group grants; plan to switch DB account type and transfer ownership — never delete carelessly in production.

### Exercise 7 — Database Flags

An engineer runs `gcloud sql instances patch ... --database-flags=cloudsql.iam_authentication=on` on an instance with several existing flags.

**Question:** What is the risk? What must be done before running it?

**Hint:** It can reset omitted flags; read current flags first, preserve the full list, and review change impact.

### Exercise 8 — Cloud Run Using the Wrong ADC

A developer can run `psql` as `dev@example.com` on a laptop, while Cloud Run runs under SA `orders-api`. Java config sets `DB_IAM_USER=dev@example.com` and fails authentication.

**Question:** Which principal should the config match? Which DB user and SQL role must be created?

**Hint:** Use the runtime SA's IAM DB username, not the deployer's; create matching SQL grants.

### Exercise 9 — Offboarding

An employee is removed from the IAM group yet still holds an open PostgreSQL connection.

**Question:** Why might removing group membership alone not block all access immediately? List remediation steps.

**Hint:** Group propagation delay and active DB sessions; audit IAM, revoke SQL grants, and terminate sessions per runbook.

### Exercise 10 — System Security Design

Design IAM database authentication for Java Orders API, Billing Worker, and the BI team on **Cloud SQL PostgreSQL** with an optional move to **AlloyDB**. Specify:

- IAM roles and principal types;
- whether users/groups are created at the instance or cluster level;
- domain-scoped SQL `GRANT`s;
- connectors, networking, and TLS;
- pooling, token refresh, and group propagation;
- logging/auditing, revocation runbook, and cost considerations.

**Hint:** Decouple Cloud IAM resource access from PostgreSQL SQL privileges; never share one admin identity across workloads.

## 16. Production Readiness Checklist

- [ ] Engine confirmed: Cloud SQL PostgreSQL/MySQL or AlloyDB PostgreSQL; never assign IAM DB auth to Cloud SQL SQL Server.
- [ ] Separated IAM login/connect, networking, DB accounts, and SQL privileges.
- [ ] Enabled the exact IAM database flag for **each engine/instance** while preserving existing flags.
- [ ] IAM users/service accounts/groups registered on the **Cloud SQL instance** or **AlloyDB cluster**.
- [ ] Cloud SQL identities hold `roles/cloudsql.instanceUser`; connectors hold `roles/cloudsql.client`.
- [ ] AlloyDB identities hold `roles/alloydb.databaseUser`; connectors hold `roles/alloydb.client` and Service Usage Consumer as needed.
- [ ] SQL roles explicitly created with minimal `GRANT`s on required databases/schemas/tables; `PUBLIC` grants audited.
- [ ] Dedicated Java runtime SA per workload; never default to Developer/Owner/Editor.
- [ ] Automatic IAM authentication via connector/proxy; zero static tokens, passwords, or JSON keys in source.
- [ ] Verified the **connector principal** matches the database IAM user, including when using impersonation.
- [ ] Private IP/PSC, firewalls, TLS, and connector egress configured properly.
- [ ] Shortened PostgreSQL SA usernames verified ≤ 63 characters; MySQL checked for post-strip collisions.
- [ ] IAM groups adopted appropriately, with individual-account migration and propagation accounted for.
- [ ] Avoided combining AlloyDB IAM group auth with unsupported managed pooling.
- [ ] HikariCP/connection pooling sized for Cloud Run/GKE concurrency and database login quotas.
- [ ] Offboarding revokes IAM/SQL and handles **live sessions**, not just group membership removal.
- [ ] IAM and database audit logs enabled, with alerts for login failures, quota/connection storms, and grant changes.
- [ ] Backups/HA/replicas, flag rollbacks, and costs reviewed before configuration changes.
- [ ] Rehearsed positive and negative permission checks in a sandbox without running `DELETE` tests on real data.

## 17. Official Documentation

Limits, flags, connector versions, and IAM group features evolve over time. Verify the docs before implementation:

- [Cloud SQL PostgreSQL — IAM authentication](https://docs.cloud.google.com/sql/docs/postgres/iam-authentication)
- [Cloud SQL PostgreSQL — Configure IAM-enabled instances](https://docs.cloud.google.com/sql/docs/postgres/create-edit-iam-instances)
- [Cloud SQL PostgreSQL — Add/manage IAM users and groups](https://docs.cloud.google.com/sql/docs/postgres/add-manage-iam-users)
- [Cloud SQL PostgreSQL — IAM login and automatic auth](https://docs.cloud.google.com/sql/docs/postgres/iam-logins)
- [Cloud SQL PostgreSQL — Cloud SQL Language Connectors](https://docs.cloud.google.com/sql/docs/postgres/connect-connectors)
- [Cloud SQL MySQL — IAM database authentication](https://docs.cloud.google.com/sql/docs/mysql/iam-authentication)
- [Cloud SQL MySQL — Manage IAM users](https://docs.cloud.google.com/sql/docs/mysql/add-manage-iam-users)
- [AlloyDB — IAM database authentication overview](https://docs.cloud.google.com/alloydb/docs/database-users/iam-authentication)
- [AlloyDB — Manage IAM authentication](https://docs.cloud.google.com/alloydb/docs/database-users/manage-iam-auth)
- [AlloyDB — Connect using IAM](https://docs.cloud.google.com/alloydb/docs/connect-iam)
- [AlloyDB — Auth Proxy](https://docs.cloud.google.com/alloydb/docs/auth-proxy/connect)
- [AlloyDB — IAM roles and permissions](https://docs.cloud.google.com/alloydb/docs/reference/iam-roles-permissions)
- [AlloyDB — Database flags](https://docs.cloud.google.com/alloydb/docs/instance-configure-database-flags)
- [AlloyDB — Connect using gcloud CLI (Preview)](https://docs.cloud.google.com/alloydb/docs/connect-gcloud)
- [Cloud SQL JDBC Socket Factory — IAM auth](https://github.com/GoogleCloudPlatform/cloud-sql-jdbc-socket-factory/blob/main/docs/jdbc.md)
- [PostgreSQL — GRANT](https://www.postgresql.org/docs/current/sql-grant.html)
- [PostgreSQL — Default privileges](https://www.postgresql.org/docs/current/sql-alterdefaultprivileges.html)

**Key takeaway:** **IAM database authentication verifies identity for database login; `GRANT`/`REVOKE` inside PostgreSQL/MySQL still decides what data can be read or written.** Cloud SQL and AlloyDB differ in flags, IAM roles, and user-provisioning scopes; **automatic IAM auth via connectors** lets Java use short-lived tokens without storing static secrets. Secure design combines **dedicated runtime service identities, least-privilege SQL roles, VPC/TLS, connection pooling, lifecycle-managed IAM groups, and end-to-end auditing**.
