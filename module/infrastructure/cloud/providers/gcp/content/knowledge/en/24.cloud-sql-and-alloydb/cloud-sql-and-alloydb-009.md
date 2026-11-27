# Connection Pooling and Application Connection Limits

> **Chapter:** Cloud SQL and AlloyDB  
> **Module:** CLOUD_PROVIDERS_GCP

A Java order-management API runs on **Cloud Run**, backed by **Cloud SQL for PostgreSQL** or **AlloyDB for PostgreSQL**. During normal hours, a few containers handle all traffic. During a promotion, Cloud Run scales out by dozens of instances, each opening a batch of PostgreSQL connections. The database begins throwing `too many connections` even though CPU is not exhausted. The root cause is usually the **total number of connections opened by the application and how they are reused**, not necessarily query compute capacity.

This lesson belongs to the **Cloud SQL and AlloyDB** chapter of the **CLOUD_PROVIDERS_GCP** module: after covering project/IAM/VPC organization, Compute Engine, GKE, Cloud Run, storage, and databases, you need to know how to deploy apps safely, automate releases, and monitor reliability and cost. The lesson uses **PostgreSQL** throughout. MySQL and SQL Server have different drivers, connection models, and managed pooling behavior — do not apply PostgreSQL commands to them verbatim.

**Learning Outcomes:**

1. Distinguish **client connections**, **server connections**, **in-app pools**, **database-side poolers**, and **Cloud SQL Auth Proxy**.
2. Inspect `max_connections` and compute a **connection budget** across Cloud Run instances/GKE Pods and other database consumers.
3. Configure **HikariCP** for Java with pool bounds, timeouts, connection lifetimes, and proper resource closing.
4. Choose Managed Connection Pooling appropriately for **Cloud SQL for PostgreSQL Enterprise Plus** or **AlloyDB**, understanding prerequisites and ports.
5. Distinguish **transaction pooling** from **session pooling**, and recognize incompatible PostgreSQL features.
6. Monitor active/idle/waiting clients, saturation causes, failovers, connection leaks, and costs.
7. Complete a load-testing and configuration rollback lab without touching production databases.

## 1. Why More Connections Do Not Guarantee Better Speed

PostgreSQL typically spawns one **backend process** per server connection. Each connection consumes memory, tracking structures, and authentication/TLS handshake time. When an application repeatedly opens and closes connections, overhead can dominate request latency. Opening too many connections triggers CPU/memory contention or causes the database to reject new sessions.

A **connection pool** keeps a set of established connections so requests borrow and return them rather than opening a fresh connection per query.

~~~mermaid
flowchart LR
  REQ["HTTP requests"] --> API["Cloud Run instance\nJava orders-api"]
  API --> H["HikariCP\nMax pool = 5"]
  H -->|"Borrow / return"| DB["Cloud SQL / AlloyDB\nPostgreSQL server"]
  API2["Another Cloud Run instance"] --> H2["HikariCP\nMax pool = 5"]
  H2 --> DB
  DB --> M["DB max_connections\nGlobal ceiling"]
~~~

### 1.1. Metrics That Are Not Equivalent

| Concept | Meaning | Example |
| --- | --- | --- |
| **HTTP concurrency** | Simultaneous requests one instance can accept | Cloud Run concurrency = 40 |
| **Pool size** | **Max** database connections **in one pool** | Hikari `maximumPoolSize` = 5 |
| **Active connections** | Connections currently borrowed and in use | 3/5 |
| **Idle connections** | Unborrowed connections kept warm by the pool for reuse | 2/5 |
| **Pending/waiting borrowers** | Threads/requests waiting for a connection from the pool | 8 threads waiting |
| **Server connections** | Active PostgreSQL backend sessions | 130 connections on primary |
| **`max_connections`** | PostgreSQL configuration limit, not free slots reserved for one app | 300 (illustrative) |

An instance receiving 40 concurrent HTTP requests **does not automatically need 40 database connections**: some requests process JSON or hit caches without touching the DB, and one connection can serve multiple queries **sequentially**. Conversely, a request holding a transaction open for seconds ties up a connection and builds a queue.

### 1.2. Lifecycle of a Pool

~~~text
Request → pool.getConnection()
    ├── Idle connection available? → borrow immediately
    ├── Below maxPoolSize?         → open a new connection
    └── Pool full?                 → wait up to connectionTimeout
                                        └── Expired → SQLException/timeout

Execute query/transaction
    ↓
connection.close()  # In a JDBC pool: RETURNS TO POOL, usually does not close TCP socket
    ↓
Connection ready to be borrowed again
~~~

**Never create a new pool per HTTP request.** Scope the pool to the process/container lifecycle (usually a singleton via DI/Spring Boot), and use `try-with-resources` for `Connection`, `PreparedStatement`, and `ResultSet`. A pool will not fix slow SQL queries, long-held locks, or database memory exhaustion.

## 2. Three Limit Layers to Calculate Separately

~~~mermaid
flowchart TD
    RUN["Cloud Run/GKE\nN instances × P pool size"] --> A["Total potential client connections"]
    A --> R{"Managed pooler?"}
    R -- "No" --> DB["DB server sessions\nmax_connections"]
    R -- "Yes" --> MP["Pooler client connections\nmax_client_connections"]
    MP --> S["Pooler server connections\npool_mode + max_pool_size"]
    S --> DB
    O["Other apps, replicas,\nadmin, maintenance"] --> DB
~~~

### 2.1. Budget Without a Server-Side Pooler

Estimating the ceiling from one application:

\[
C_{\text{app,max}} \approx \sum_{r=1}^{R} N_r \times P_r + C_{\text{jobs}} + C_{\text{other-processes}}
\]

Where:

- `R`: number of concurrently live revisions/deployments (including canary/rollback windows).
- `N_r`: maximum instances or Pods for revision `r`.
- `P_r`: connection limit **per process/pool**.
- `C_jobs`: connections opened by background workers, migration jobs, batch jobs, and secondary pools.
- This sum is a **scenario ceiling**, not a steady-state number or a guarantee the autoscaler will never spike past expectations.

The application's share must stay below the database budget:

\[
B_{\text{app}} = C_{\text{DB usable}} - C_{\text{other services}} - C_{\text{headroom}}
\]

**Never allocate 100% of `max_connections` to one service.** Reserve slots for admin access, replication, maintenance, other apps, and failover/scale-out spikes. When tuning `max_connections`, account for RAM and engine/tier limits; raising the number does not create CPU or RAM.

### 2.2. Working Backward Example

Suppose `max_connections=400`; after operational and headroom reserves, DBAs allocate **240 connections** to `orders-api`. Configuration:

| Component | Assumed Value |
| --- | ---: |
| New Cloud Run revision max | 16 instances |
| Old revision still serving during rollout | 8 instances |
| Total instances in design | 24 |
| HikariCP `maximumPoolSize` | 8 |
| Configured max demand | 24 × 8 = **192** |
| Headroom within app budget | 240 − 192 = **48** |

Raising the pool from 8 to 15 without changing instance counts pushes the ceiling to **360**, blowing past the 240 budget. To serve more concurrent requests, measure **DB connection hold time** and adjust concurrency, instance caps, query efficiency, or server-side pooling.

**Rule of thumb:** Design for peak instances **across all active revisions, jobs, and consumers**, not just steady-state instance counts.

### 2.3. Relating RPS to Active Connection Demand

Little's Law estimate in steady state:

\[
C_{\text{active,average}} \approx \text{DB transactions/s} \times \text{average connection hold time (s)}
\]

With 200 transactions/s and an average hold time of 40 ms, average concurrency is roughly **8 connections** (200 × 0.04). This is **not** your required pool size: bursts, p95/p99 query times, locks, transaction queuing, and cache misses push demand higher. Pair this with dashboards and load tests, then add margin.

## 3. Cloud SQL PostgreSQL and Cloud Run Limits

### 3.1. PostgreSQL `max_connections`

**Read-only** SQL commands run by an authorized user:

~~~sql
SHOW max_connections;

SELECT name, setting, unit, source
FROM pg_settings
WHERE name IN ('max_connections', 'superuser_reserved_connections',
               'reserved_connections');

SELECT current_setting('max_connections')::int AS configured_limit,
       count(*) AS visible_sessions
FROM pg_stat_activity;
~~~

`reserved_connections` may not exist on older PostgreSQL versions; if `pg_settings` omits it, that is normal. `pg_stat_activity` may hide details of other users' sessions depending on privileges, though total session counts remain useful. Cross-check with Metrics Explorer/Database Insights.

Cloud SQL sets a default based on machine tier and edition memory. On PostgreSQL, you can tune `max_connections` **within supported flag bounds and DB memory**; changing the flag may require a restart. Never copy a value from a 32 GiB RAM machine onto a small instance.

### 3.2. Scope of Cloud Run's 100-Connections-Per-Instance Limit

Cloud SQL documentation states that **Cloud Run's built-in Cloud SQL integration** enforces a limit of **100 connections per Cloud SQL database per container instance**. That limit **does not apply identically** to:

- Cloud SQL **Language Connectors**.
- A Cloud SQL Auth Proxy **sidecar**.
- **Direct TCP connections to the instance IP**.

Still, every method consumes **database connections** and counts toward `max_connections`. The 100 limit is **not a HikariCP default** and not a deployment-wide cap: 30 instances using the built-in integration with 20 connections/instance can still request ~600 database connections without server-side pooling.

### 3.3. App Engine, GKE, and Workers

| Runtime | Source of High Connection Counts | What to Calculate |
| --- | --- | --- |
| Cloud Run services | Autoscaling and overlapping revisions serving traffic | `Instances × pools`, concurrency, `max_instances` |
| Cloud Run jobs | Parallel tasks / job execution retries | `Tasks × pools` + app services |
| GKE | ReplicaSets/HPA, multiple JVMs per Pod, rolling updates | `Replicas (including surge) × pools` |
| Compute Engine | Multiple VMs/processes and sidecar workers | `Instances × processes × pools` |
| App Engine Standard | Autoscaling and platform quotas | `Connections/instance` + service scaling |

One database is often shared by **multiple workload types**. Per-service dashboards help identify which caller caused a connection spike.

## 4. In-App Pooling: Java HikariCP

Examples below assume you have the PostgreSQL JDBC driver, HikariCP, and a database endpoint configured with **proper networking, TLS, and IAM**. With Cloud SQL or AlloyDB, the path may go through **Auth Proxy, a Language Connector, or private IP**; those transport choices are **not** the pool itself.

### 4.1. Creating a Reusable DataSource

~~~java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

public final class DataSourceFactory {
    private DataSourceFactory() {}

    public static HikariDataSource create() {
        var cfg = new HikariConfig();

        // URL supplied via secure config:
        // jdbc:postgresql://DB_HOST:DB_PORT/orders
        // Needs TLS/trust + DNS/hostname matching the connection method.
        cfg.setJdbcUrl(System.getenv("DB_JDBC_URL"));
        cfg.setUsername(System.getenv("DB_USER"));
        cfg.setPassword(System.getenv("DB_PASSWORD"));

        cfg.setPoolName("orders-pool");
        cfg.setMaximumPoolSize(5);
        cfg.setMinimumIdle(0);
        cfg.setConnectionTimeout(10_000);  // Wait <= 10 s to borrow a connection
        cfg.setValidationTimeout(5_000);
        cfg.setIdleTimeout(600_000);       // Applies only to surplus idle connections
        cfg.setMaxLifetime(1_800_000);     // Keep shorter than backend/proxy timeouts

        return new HikariDataSource(cfg);
    }
}
~~~

**This is a sample config**, not a complete production JDBC setup. Set `DB_JDBC_URL` for your real connectivity path, verify TLS/server identity or use a supported Auth Proxy/Language Connector, and retrieve `DB_PASSWORD` from Secret Manager/credential providers. Never place passwords in source code or logs.

**Parameter guide:**

| HikariCP Setting | Meaning | Notes |
| --- | --- | --- |
| `maximumPoolSize` | Max connections per pool | Calculate DB budget first |
| `minimumIdle` | Minimum idle connections kept | `0` often suits serverless; load-test it |
| `connectionTimeout` | Max wait to **borrow from the pool** | Distinct from TCP connect timeout and SQL query timeout |
| `validationTimeout` | Max wait to validate a connection | Must not exceed `connectionTimeout` |
| `idleTimeout` | Time surplus connections sit idle before eviction | Not guaranteed down to the exact millisecond |
| `maxLifetime` | Max lifetime of a connection before retirement | Set shorter than server/proxy timeouts to avoid stale sockets |
| `leakDetectionThreshold` | Logs warnings when a connection is held too long | Diagnostic only; does not forcibly close leaks |

**Do not rely on `maxLifetime` to bound query runtime.** Configure explicit statement/query timeouts per workload along with PostgreSQL `statement_timeout` and `lock_timeout` where appropriate.

### 4.2. Borrow, Return to Pool, and Close Promptly

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public class OrderHealthQuery {
    private final DataSource dataSource; // Shared singleton pool

    public OrderHealthQuery(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public boolean ping() throws SQLException {
        try (Connection connection = dataSource.getConnection();
             PreparedStatement sql = connection.prepareStatement("SELECT 1");
             ResultSet rs = sql.executeQuery()) {
            return rs.next() && rs.getInt(1) == 1;
        }
    }
}
~~~

With `try-with-resources`, HikariCP reclaims the connection when `close()` runs. In Spring Boot, the pool is created and managed **once per application context** — never instantiate a datasource per request. Close `HikariDataSource` on process shutdown, never at the end of an individual request.

### 4.3. Separating Timeouts During Investigation

~~~text
HTTP request deadline
  ├── Pool borrow: Hikari connectionTimeout
  ├── Establish new JDBC/TCP/Cloud SQL Connector connection timeout
  ├── Execute SQL: statement_timeout / query timeout
  ├── Acquire database lock: lock_timeout
  └── Commit/response network timeout
~~~

HikariCP `connectionTimeout=10s` only caps how long a thread **waits for an available connection in the pool**. A query on a borrowed connection can still run much longer without SQL timeouts. Align deadlines with your SLO so waits and retries do not exceed Cloud Run/API Gateway request timeouts.

## 5. Tuning for Cloud Run and GKE

### 5.1. Cloud Run Autoscaling

As requests rise, Cloud Run adds instances. Each JVM instance normally runs its own pool: **pool of 5 × 30 instances = 150 connections** at the ceiling. During rollouts, old and new revisions overlap, so account for both.

- `--concurrency` caps concurrent HTTP requests per **container instance**, **not** DB sessions directly.
- `--max-instances` caps scale-out per configuration; verify whether limits are set at **service vs. revision level**.
- `--min-instances` keeps warm capacity, which can also hold idle database connections open.
- Low `minimumIdle` cuts idle sessions; overly tiny pools cause queuing when traffic truly hits the DB.
- If the database is already saturated, raising `max-instances` or `maximumPoolSize` makes things worse.

Read-only inspection commands:

~~~bash
gcloud run services describe orders-api \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID

gcloud sql instances describe orders-db \
  --project=LAB_PROJECT_ID
~~~

Approved test adjustment example:

~~~bash
# CREATES REVISION / CHANGES autoscaling; never run carelessly on production
gcloud run services update orders-api \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID \
  --concurrency=20 \
  --max-instances=12
~~~

**Serverless pitfall:** Under request-based billing, Cloud Run throttles CPU when an instance is idle, stalling background pool maintenance threads. When the next request arrives, an idle connection already closed by the DB/proxy may fail on first use. Use connection validation/reconnects, appropriate `minimumIdle`, and lazy connector refresh with Cloud SQL Java Connector; consider **instance-based billing** only if continuous background pool maintenance justifies the extra cost.

### 5.2. GKE Rolling Updates and HPA

Suppose a Deployment has `replicas=10`, `maxSurge=3`, and HikariCP `maximumPoolSize=10`. During a rolling update, **13 Pods** can run simultaneously — **130** DB sessions from this workload despite a baseline of 100. HPA can also scale replicas up during the same window.

When budgeting, calculate:

~~~text
Max DB connections ≈
  (baseline replicas + surge Pods) × JVMs/Pod × pools/JVM
  + job/consumer connections
  + other applications
~~~

Lowering `maxSurge` trims peak connections at the cost of slower rollouts; balance against availability/SLO. On GKE, monitor pool metrics per Pod and deployment rather than relying solely on `kubectl get pods`.

## 6. Cloud SQL Auth Proxy Is Not a Connection Pool

**Cloud SQL Auth Proxy** provides IAM-authorized, encrypted connectivity to a Cloud SQL instance; **it does not multiplex many PostgreSQL sessions onto fewer server connections**. Opening 100 JDBC connections through a standard Auth Proxy still opens roughly 100 sessions on the database. You can **pair** Auth Proxy with HikariCP or supported Managed Connection Pooling.

| Tool | Primary Role | Multiplexes Multiple DB Clients? |
| --- | --- | --- |
| Cloud SQL Auth Proxy | Auth/encrypted tunnel and connection management | **No**, when used alone |
| Cloud SQL Java Connector | IAM auth, TLS, and address resolution | **No**, not a pool by itself |
| HikariCP | Reuses connections **inside one JVM** | Caps per-JVM clients; does not share across instances |
| Self-managed PgBouncer | Server-side pooler (transaction/session modes) | **Yes**, depending on pool mode |
| Cloud SQL PostgreSQL **Managed Connection Pooling** | Managed poolers sharing backend server sessions | **Yes**, when prerequisites are met |
| AlloyDB **Managed Connection Pooling** | Managed poolers on an AlloyDB instance | **Yes**, when prerequisites are met |

**Networking, IAM, and DB authentication are distinct layers:** direct PostgreSQL TCP over private IP requires networking/TLS/auth; Auth Proxy/Language Connectors add IAM permissions (such as `roles/cloudsql.client` for Cloud SQL); yet PostgreSQL `CONNECT`, schema/table privileges, and DB credentials/IAM DB auth are still required. `roles/cloudsql.client` never grants table `SELECT/INSERT`.

## 7. Cloud SQL for PostgreSQL Managed Connection Pooling

**Cloud SQL Managed Connection Pooling (MCP)** is a Google-managed server-side pooler. Unlike an in-JVM pool, many client connections can **share a bounded number of server connections** per user/database pair in transaction or session mode. This feature targets **Cloud SQL for PostgreSQL Enterprise Plus**, and is **not** available by default on every Cloud SQL instance.

### 7.1. Mandatory Prerequisites

Per current documentation, verify all of these before enabling MCP:

- **Edition:** Cloud SQL **Enterprise Plus** for PostgreSQL.
- **Network architecture:** instance uses the **new Cloud SQL network architecture** and connects via Private Services Access, public IP, or Private Service Connect per support terms.
- **Maintenance version:** at least `POSTGRES_$version.R20250727.00_14` (replace `$version` with your major version); do not check only the PostgreSQL major number.
- **Client connectivity:** MCP works with **direct connections** or **Cloud SQL Auth Proxy** (Proxy v**2.15.2+**). Do not assume every Language Connector supports MCP identically.
- **Admin permissions:** the operator updating the instance needs appropriate Cloud SQL permissions; the app user only needs connection/database privileges for the chosen path.
- **Impact on running instances:** enabling MCP on an existing instance **restarts the database**; schedule a maintenance window, HA/failover plan, and reconnect tests.

**Never enable MCP via an ad-hoc production patch assuming it is "zero downtime."** Double-check network architecture and maintenance version first.

### 7.2. Connection Ports and How to Choose

| Case | Port | Meaning |
| --- | --- | --- |
| Direct PostgreSQL | TCP `5432` | Connects directly to the DB server, **bypassing MCP** |
| Direct Managed Connection Pooling | TCP `6432` | Connects to the MCP pooler over a supported network path |
| Cloud SQL Auth Proxy to MCP | Cloud SQL target uses TCP `3307` | Auth Proxy selects the MCP endpoint per Proxy flags; **local app port** may differ |
| Standard Cloud SQL Auth Proxy | Cloud SQL Proxy target also uses `3307` | Does not automatically use MCP unless enabled and selected |

**Do not change the JDBC URL from 5432 to 3307 when the app talks to a local Auth Proxy.** `3307` is the **Cloud SQL service port used by the Proxy**. To route through MCP via Auth Proxy, pass the documented Proxy flags on a supported version and point your app at the **local listener**.

### 7.3. Pooler Count and Pool Size Are Two Separate Tiers

Cloud SQL provisions roughly **1 connection pooler per 4 vCPUs**, minimum one. Each pooler maintains a **separate pool per database and user pair**.

For example, an 8-vCPU instance runs 2 poolers. With `max_pool_size=50`, **one user/database pair** can receive up to 50 server connections **per pooler** — theoretically up to **100** total for that pair, **not 50 across the entire instance**. With multiple database users, total server sessions climb even higher. Ultimately, PostgreSQL `max_connections` remains the hard ceiling.

Key default parameters:

| MCP Setting | Documented Default | Scope |
| --- | ---: | --- |
| `pool_mode` | `transaction` | Server connection hold scope |
| `max_pool_size` | 50 | **Per user / database / pooler** |
| `min_pool_size` | 0 | Per pool |
| `max_client_connections` | 5,000 | **Per pooler** |
| `query_wait_timeout` | 120 s | Client wait time for a server connection |
| `max_prepared_statements` | 0 | Enables protocol-level named prepared statements when configured |

**5,000 client connections does not mean the database can execute 5,000 concurrent transactions.** When the server pool fills up, clients **queue**; latency climbs and requests can time out. A pooler reduces connection overhead — it does not turn the database into infinite compute.

### 7.4. Inspecting and Enabling via gcloud

~~~bash
# READ-ONLY: substitute real instance and project before running
gcloud sql instances describe orders-db \
  --project=LAB_PROJECT_ID \
  --format="yaml(name,region,databaseVersion,settings.edition,settings.tier,settings.connectionPoolConfig)"

# READ-ONLY: check whether MCP is enabled
gcloud sql instances describe orders-db \
  --project=LAB_PROJECT_ID \
  --format="value(settings.connectionPoolConfig.connectionPoolingEnabled)"
~~~

Once all prerequisites are verified in a **lab project**, an administrator can enable it:

~~~bash
# MODIFIES INSTANCE and TRIGGERS DATABASE RESTART:
# use only on eligible Cloud SQL PostgreSQL Enterprise Plus instances.
gcloud sql instances patch orders-db \
  --project=LAB_PROJECT_ID \
  --enable-connection-pooling
~~~

Example updating pool settings **after enabling**:

~~~bash
# MODIFIES pool configuration; requires load and maintenance testing
gcloud sql instances patch orders-db \
  --project=LAB_PROJECT_ID \
  --connection-pool-flags=pool_mode=transaction,max_pool_size=30
~~~

Pass flags using a **supported gcloud CLI version** (docs require gcloud 515.0.0+). Never apply arbitrary pool values in production before checking pooler count, database users, `max_connections`, and active session impact.

## 8. AlloyDB Managed Connection Pooling

**AlloyDB for PostgreSQL** also offers **Managed Connection Pooling**, multiplexing client connections across a pool of server connections; it supports both **primary** and **read pool instances**. The feature is **disabled by default** and configured independently per AlloyDB instance.

### 8.1. Enabling and Checking

~~~bash
# READ-ONLY
gcloud alloydb instances describe primary-instance \
  --project=LAB_PROJECT_ID \
  --region=asia-southeast1 \
  --cluster=orders-cluster \
  --format="value(connectionPoolConfig.enabled)"
~~~

~~~bash
# MODIFIES instance: run only in an authorized lab
gcloud alloydb instances update primary-instance \
  --project=LAB_PROJECT_ID \
  --region=asia-southeast1 \
  --cluster=orders-cluster \
  --enable-connection-pooling
~~~

**Plan a change window:** For AlloyDB instances created **before November 2024**, enabling MCP may trigger a one-time network update causing a brief VPC connection drop (docs cite typically under 15 seconds); do not promise zero impact for every instance or assume in-flight transactions survive.

### 8.2. Connecting to the Pooler on Port 6432

- Direct PostgreSQL on AlloyDB typically uses **5432**.
- MCP listens on **TCP 6432** over supported private/PSC endpoints.
- Managed pooler **does not support public IP connections**.
- **AlloyDB Auth Proxy or AlloyDB Language Connectors** can be used per supported docs; Auth Proxy pooler connections use a separate group from direct pooler connections.
- DB credentials/IAM DB auth and SSL/mTLS must match the connection method. Having private IP does not mean certificates are automatically verified.

Example **solely to illustrate the connection path** — never pass passwords on the command line:

~~~bash
# Run from a host inside the VPC with proper network/TLS/auth.
# DB_HOST is a valid DNS/private IP; sslmode/certs may be required by policy.
psql "host=DB_HOST port=6432 dbname=orders user=orders_app sslmode=require"
~~~

**Never use literal `DB_HOST` as a real address.** With AlloyDB direct connections, TLS/verification options differ from Auth Proxy/Language Connectors; configure verification for your chosen architecture.

### 8.3. Tuning Transaction/Session Modes

~~~bash
# MODIFIES pooler config in lab; check CLI version and IAM
gcloud alloydb instances update primary-instance \
  --project=LAB_PROJECT_ID \
  --region=asia-southeast1 \
  --cluster=orders-cluster \
  --connection-pooling-pool-mode=transaction \
  --connection-pooling-max-pool-size=30 \
  --connection-pooling-max-client-connections=1000
~~~

`max_pool_size` caps server connections per user/database pair per pooler; `max_client_connections` caps client connections, **not** database `max_connections`. Measure `waiting clients` and query wait times after tuning rather than cranking limits indefinitely.

### 8.4. AlloyDB Stats Console and Metrics

AlloyDB exposes pooler metrics:

| Metrics Explorer | Meaning |
| --- | --- |
| `/database/conn_pool/client_connections` | Client connections by active/waiting |
| `/database/conn_pool/server_connections` | Server connections by active/idle |
| `/database/conn_pool/client_connections_avg_wait_time` | Client wait time for a server connection |
| `/database/conn_pool/num_pools` | Number of pools per database |

When explicitly authorized, operators can connect to the **stats console** over a private endpoint and run PgBouncer-compatible commands `SHOW POOLS;`, `SHOW CLIENTS;`, and `SHOW STATS;`. The stats database name looks like `alloydb_mcp_stats_1` for the standard pooler; stats users must be allowlisted beforehand. **Never grant broad stats/credential visibility** to routine application accounts.

## 9. Transaction Pooling vs. Session Pooling

This is an **application compatibility** decision, not merely a performance toggle.

~~~mermaid
flowchart LR
  A["Client A\nPooler"] --> P["Transaction pool"]
  B["Client B\nPooler"] --> P
  P -->|"Tx A: server #1\nCOMMIT → return server"| S1["PostgreSQL server #1"]
  P -->|"Tx B: reuse server #1"| S1
  P2["Session pool"] -->|"Client C holds server #2\nfor entire session"| S2["PostgreSQL server #2"]
~~~

| Criterion | **Transaction mode** | **Session mode** |
| --- | --- | --- |
| Backend connection hold time | For **one transaction**; returned after commit/rollback | For the **entire session** until client disconnect |
| Sharing efficiency | High for short transactions | Lower when clients stay connected idle |
| Session state | **Cannot assume state persists** across transactions | Preserves session state on the assigned server connection |
| Best fit | Stateless REST APIs, short transactions | Apps relying on session state or session protocol features |
| When server pool is full | Clients wait / time out | Other clients wait until a session disconnects |

### 9.1. Features Often Incompatible with Transaction Mode

Per Cloud SQL and AlloyDB MCP transaction mode limits, audit for:

- `SET/RESET` mutating session state across transactions.
- Long-lived `LISTEN/NOTIFY` listeners holding sessions open.
- Session-level advisory locks (`pg_advisory_lock`).
- Temporary tables using `ON COMMIT PRESERVE ROWS` or session scope.
- `WITH HOLD` cursors.
- SQL-level `PREPARE/DEALLOCATE` and session-bound prepared statements.
- **Protocol-level named prepared statements** by default; some setups allow non-zero `max_prepared_statements`, requiring driver/pooler testing.

**Failure example:** A Hibernate/PostgreSQL JDBC driver caches server-side prepared statements across transactions. If the backend server connection swaps between transactions, a named prepared statement may not exist on the new backend or may collide in name. Test the driver's `prepareThreshold` and MCP `max_prepared_statements`; never disable all prepared statements blindly without measuring performance and reading version docs.

**Choose session mode** if the app strictly requires session state, understanding that client sessions will closely track server connections with much less multiplexing efficiency. If an app needs `LISTEN` or a migration runner, give that component a **dedicated direct 5432 connection** while short-transaction APIs use the 6432 transaction pooler.

### 9.2. Can a Pooler and HikariCP Be Used Together?

**Yes.** HikariCP bounds how many client connections each JVM opens to the pooler; the pooler multiplexes many client sessions onto a smaller set of server connections. However, **two queuing layers** can increase tail latency:

1. Request waits to borrow a HikariCP connection.
2. Client connection reaches MCP and waits for a free server connection.

Monitor both **Hikari pending/wait time** and **MCP waiting/query wait time**, not just total connections. For short transactional workloads, keep the JVM pool small, use transaction pooling, and scale the app within backend capacity. Always verify SQL compatibility first.

## 10. Choosing a Pooling Strategy by System

| Scenario | Recommendation | What to Avoid |
| --- | --- | --- |
| Cloud SQL PostgreSQL Enterprise (not Plus) | HikariCP/driver pool; consider self-managed PgBouncer if needed | Assuming Google-managed MCP is available |
| Eligible Cloud SQL PostgreSQL Enterprise Plus | HikariCP + **Cloud SQL MCP** when benefits are clear | Enabling MCP without planning for restart and transaction compatibility |
| AlloyDB read/write with client spikes | HikariCP + **AlloyDB MCP** | Connecting to 6432 over unsupported public IP |
| App relying on long session state | HikariCP or **session mode** / direct 5432 | Unvalidated transaction mode |
| Java on GKE with hundreds of Pods | Size `pooled connections × replicas/surge`; MCP if supported | Simply raising database `max_connections` |
| Cloud Run with many instances, bursty traffic | Cap pool/instance, `max_instances`, idle validation; consider MCP | Opening a new connection/pool per HTTP request |
| PostgreSQL admin / migrations / replication | **Direct** connection per policy | Routing `REPLICATION` or stateful DDL/migrations through a transaction pooler |
| Cloud SQL MySQL / SQL Server | Study each engine's specific pooling model | Copying PostgreSQL process/multiplexing assumptions |

**Distinguish Cloud SQL MySQL Managed Connection Pooling:** on MySQL, the newer mechanism uses **thread pooling**, which still keeps separate client sessions and still counts toward `max_connections`; do not infer from this PostgreSQL lesson that MySQL collapses server sessions like PgBouncer.

## 11. Observing Connections and Finding Bottlenecks

### 11.1. Safe SQL for Cloud SQL PostgreSQL / AlloyDB

Run using a DB user **authorized to view stats**, and avoid pasting full user query texts into tickets/logs:

~~~sql
-- Configured limit:
SHOW max_connections;

-- Aggregate sessions by database, user, and state:
SELECT datname, usename, COALESCE(state, 'unknown') AS state,
       count(*) AS sessions
FROM pg_stat_activity
GROUP BY datname, usename, state
ORDER BY sessions DESC;

-- Total connections and active session breakdown:
SELECT
    count(*) AS all_sessions,
    count(*) FILTER (WHERE state = 'active') AS active_sessions,
    count(*) FILTER (WHERE state = 'idle') AS idle_sessions,
    count(*) FILTER (WHERE state = 'idle in transaction') AS idle_in_transaction
FROM pg_stat_activity;
~~~

**Counting server sessions is not the same as counting MCP clients.** With a transaction pooler, hundreds or thousands of client connections can sit in front of a small set of backend connections. Inspect **pooler metrics** rather than `pg_stat_activity` alone to see waiting clients. High `idle in transaction` counts often indicate code holding transactions/locks open too long.

### 11.2. Metrics to Correlate Over the Same Time Window

| Layer | Signal | Meaning |
| --- | --- | --- |
| Cloud Run/GKE | Instance/Pod count, concurrent HTTP, restarts, p95 | How the app is scaling |
| HikariCP | `active`, `idle`, `pending`, `total`, borrow time | Queuing inside the JVM |
| Cloud SQL/AlloyDB | Server connections, CPU, memory, active transactions | Database saturation |
| MCP | Waiting clients, active/idle server connections, wait time | Queuing at the pooler? |
| Query | Lock waits, slow queries/p95, execution time | Is the pool held up simply because SQL is slow? |
| Network | Connection errors, TLS failures, latency | Not every failure is a pool issue |
| Platform | DB failover/restarts, maintenance, max-connection errors | Separate transient events from misconfiguration |

**Starting question:** Did 5xx rise because threads **could not borrow from HikariCP**, because **MCP waited for a backend server**, or because **SQL execution was slow**? Each cause has a different fix.

### 11.3. Suggested Alerts

- Sustained Hikari `pending > 0`, or p95 borrow time approaching `connectionTimeout`.
- Database connections approaching approved budget, or `too many connections` errors.
- Rising MCP waiting clients / query wait times while server pools are saturated.
- Rising `idle in transaction` counts or overly long transactions.
- DB CPU, lock waits, or IOPS spiking while the app pool still has free slots: tune SQL, do not add connections.
- Cloud Run instance/revision overlap pushing total pool capacity past projections.
- Reconnect failures after failover, maintenance, or Secret Manager/password rotation.

Metric names and labels vary by version; verify in Metrics Explorer and app instrumentation (Micrometer/JMX, Cloud Monitoring) rather than hardcoding non-existent metric names.

## 12. Runbook When Connection Pools Saturate

~~~mermaid
flowchart TD
  FAIL["HTTP 5xx / DB timeout"] --> GET{"Can borrow from HikariCP?"}
  GET -- "No" --> H["Pending, leaks, pool size,\ntransaction hold time"]
  GET -- "Yes" --> MCP{"Managed pooler in use?"}
  MCP -- "Yes" --> WAIT{"Pooler waiting rising?"}
  WAIT -- "Yes" --> P["Check max_pool_size,\nquery wait, server saturation"]
  WAIT -- "No" --> SQL["SQL/locks/network/DB failover"]
  MCP -- "No" --> LIMIT{"Near max_connections?"}
  LIMIT -- "Yes" --> S["App × instances budget,\nidle sessions, other consumers"]
  LIMIT -- "No" --> SQL
  H --> LOAD["Correlate metrics, logs, and load tests"]
  P --> LOAD
  S --> LOAD
  SQL --> LOAD
~~~

### 12.1. Triage Order — Do Not "Turn Up Numbers Until Errors Stop"

1. **Confirm scope:** Cloud SQL or AlloyDB; primary or read pool; port **5432/6432**; direct, Auth Proxy, or Language Connector; which project and region.
2. **Classify the timeout:** Hikari borrow timeout, TCP connect timeout, pooler query wait timeout, or SQL `statement_timeout`.
3. **Count all callers:** Cloud Run revisions, Cloud Run jobs, GKE replicas, migrations/cron jobs, and other services.
4. **Inspect the DB:** `max_connections`, active/idle sessions, CPU/memory, long transactions, locks, and slow queries.
5. **Inspect the pooler (if used):** waiting clients, active/idle server connections, `pool_mode`, `max_pool_size`, and per-user/database bounds.
6. **Prioritize shortening connection hold times:** close JDBC resources cleanly, optimize queries, keep transactions short, and never make external HTTP calls while holding a transaction open.
7. **Apply backpressure:** cap max instances/Pod replicas, queue concurrency, bounded waits, and fail fast with 429/503 per contract instead of opening unbounded DB sessions.
8. **Increase pool/capacity only with evidence:** ensure DB CPU/RAM/IOPS and `max_connections` actually have headroom.
9. **Canary changes:** update one revision or test environment, watch p95, error budget, and connection counts, and roll back if metrics regress.

### 12.2. Retries and Failover

During HA failover or maintenance, existing connections may drop. Apps should detect broken connections, evict them from the pool, open fresh ones, and **retry with bounded limits** using exponential backoff + jitter. If a failure strikes **mid-transaction**, the commit outcome may be ambiguous; retry from the start only when the operation uses an **idempotency key** or state check to prevent double writes.

**Never raise Hikari `minimumIdle` to a large number across hundreds of instances** hoping for faster HA recovery. Hundreds of idle sessions slamming the primary simultaneously can exhaust resources the moment it comes back up.

### 12.3. Managing Risky Changes

| Change | Impact to Prepare For |
| --- | --- |
| Raising app `maximumPoolSize` | Each instance can open more sessions; total scales with autoscaling |
| Raising Cloud Run `max_instances` | More JVM pools, higher DB connection ceiling |
| Raising PostgreSQL `max_connections` | Consumes RAM; check restarts and Cloud SQL/AlloyDB limits |
| Enabling Cloud SQL MCP on an existing instance | **Triggers a restart** and changes the app connection path to the pooler |
| Enabling AlloyDB MCP on older instances | May trigger a one-time network update and brief VPC drop |
| Switching session → transaction pooling | Can break session state, prepared statements, and advisory locks |
| Disabling AlloyDB MCP | **Drops active client connections using the pooler** |
| Switching endpoint 5432 → 6432 | Verify firewalls/TLS/drivers, metrics, and rollback path |

Every change needs a **change owner, observation window, load test, rollback plan, and stakeholder notice**. Never adjust these settings directly in production just to practice this lesson.

## 13. Common Failure Matrix

| Symptom | Common Cause | Remediation |
| --- | --- | --- |
| `FATAL: sorry, too many clients already` | DB near `max_connections`, no slots left for user | Inspect active sessions, other callers, and budget |
| `FATAL: remaining connection slots are reserved` | Remaining slots reserved for admin roles | Never run apps as admin roles; reduce connections |
| Hikari `Connection is not available, request timed out` | Pool exhausted or slow connection creation | Check Hikari active/pending, long queries, timeouts |
| High PostgreSQL `idle in transaction` | App opens transactions without committing/rolling back | Measure transaction durations and fix lifecycle |
| Rising MCP `waiting clients` | Server pool saturated, slow queries | Tune SQL, measure wait times, review `max_pool_size` |
| MCP transaction mode prepared statement errors | Driver/session feature mismatch | Test `max_prepared_statements` or use session/direct |
| `SET` changes lost across requests | Transaction pooling clears session state | Refactor app; use `SET LOCAL` inside transactions where appropriate |
| Switching to `:6432` gets connection refused | MCP disabled, wrong network/port/firewall | Check instance MCP status and routing |
| Cloud SQL MCP fails to enable | Missing Enterprise Plus, new network, or maintenance version | Verify all prerequisites before patching |
| AlloyDB MCP fails over public IP | Public endpoints unsupported by AlloyDB MCP | Use private/PSC and documented auth |
| Cloud Run hits stale connections right after idle | CPU throttling, server timeout, deferred pool cleanup | Enable validation/reconnect, lazy refresh, evaluate billing mode |
| Blocked at 100 connections/instance | Built-in Cloud Run–Cloud SQL integration limit | Bound pool size; review connection method |
| `permission denied` before reaching DB | IAM/connector/auth proxy permissions | Check runtime SA, resource scope, Admin API |
| `password authentication failed` | Wrong user/secret/database auth | Verify credentials/rotation; never grant Owner |
| Server `too many connections` after rollout | Overlapping revisions or Pod surge | Budget pools across rollouts; reduce surge/scale |
| DB CPU/IOPS 100% yet app pool has idle slots | Slow SQL, lock contention, missing index, or I/O bottleneck | Query Insights, plans/indexes, shorten transactions |
| Retries worsen outage | Retry storm lacking jitter or backpressure | Bounded exponential backoff and circuit breakers |
| Writes fail on read pool | App connected to read-only replica/pool endpoint | Separate write and read datasources by use case |

**Keep this clear:** auth and network errors never go away by raising pool size. When a handful of requests fail because a pooler or server is recovering from failover, retries must stay bounded and never duplicate write transactions.

## 14. Case Study: Java Ordering on Cloud Run, Cloud SQL to AlloyDB

### 14.1. Problem Statement

A team operates a retail API:

- Spring Boot Java on Cloud Run with canary revisions.
- PostgreSQL primary; each request runs 1–3 small, mostly short queries.
- Promotional traffic spikes drive aggressive instance scale-out.
- The team wants zero connection-exhaustion outages; they may be on Cloud SQL Enterprise Plus or evaluating AlloyDB.

**Analysis:** Check **`instances × Hikari pool size`** and **connection hold time** first — do not jump straight to "migrating to AlloyDB will make the errors vanish."

### 14.2. Initial Testable Baseline

| Parameter | Test Target | Rationale |
| --- | ---: | --- |
| DB budget for `orders-api` | 240 sessions | Leaves capacity for system tasks and other services |
| Max Cloud Run instances across both revisions | 24 | Accounts for rollout overlap |
| Hikari max pool/instance | 8 | Ceiling of 192 connections, keeping headroom |
| Hikari `minIdle` | 0 | Avoids holding idle sessions during scale-out |
| Borrow timeout | 10 s | Must stay below request deadline leaving room for SQL/logic |
| Query/transaction timeouts | Per SLO | Prevents connections from being held indefinitely |
| DB CPU/memory headroom | Per load test | Never size from session count alone |

**Test A:** Run 24 instances × pool 8 and measure throughput and latency. If Hikari pending is high while DB CPU/IOPS remain idle, inspect held connections and tune pool sizing. If DB CPU is already saturated, **adding connections only increases contention**.

**Test B:** On eligible Cloud SQL PostgreSQL Enterprise Plus or AlloyDB, enable managed pooling in staging and route one canary via **port 6432** or the supported proxy option. Compare MCP waiting clients, server connections, Hikari pending, application p95, and behavior of the SQL features listed earlier.

**Test C:** Verify whether the app uses `SET search_path` or JDBC prepared statements cleanly under **transaction mode**. If not, consider session mode or direct connections for stateful components.

**Decision:** Enable MCP in production only when metrics prove clear gains and **restart impact, transaction compatibility, and rollback have been verified**. Never force every workload through a pooler just because one API sends many short-lived connections.

## 15. Guided Hands-On Lab

**Goal:** Calculate a budget, configure a pool, and diagnose saturation in a **dedicated lab project/instance**. If you lack Cloud SQL/AlloyDB access or budget, complete the math and modeling exercises — **there is no need to create billable managed databases**.

### Part A — Read-Only Inspection

~~~bash
# Read-only; target your dedicated lab project
gcloud config get-value project

gcloud sql instances describe orders-db \
  --project=LAB_PROJECT_ID \
  --format="yaml(name,databaseVersion,settings.edition,settings.tier,settings.connectionPoolConfig)"

gcloud alloydb instances describe primary-instance \
  --cluster=orders-cluster \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID \
  --format="yaml(name,instanceType,connectionPoolConfig)"
~~~

These last two commands represent **two database options**: both do not have to exist in your lab. If one is absent, record "NOT PRESENT" rather than creating a production-sized instance just to check it off.

If you have a real PostgreSQL endpoint with an authorized DB user, run the **read-only** SQL queries from Sections 3 and 11. Never dump passwords, connection URIs with credentials, or sensitive SQL payloads into reports.

### Part B — Budget Math Table

Given:

- Cloud SQL `max_connections` = 320 (assumed).
- Slots reserved for admin, reporting, migrations, and headroom = 120.
- 20 concurrent Cloud Run instances and 4 GKE Pods writing to the database.
- Each JVM runs **one** Hikari pool, and workloads share one user/database pair.

**Prompt:** Remaining budget is **200**; if Hikari max pool is 10, the ceiling is 24 × 10 = **240** (fails). Propose a pool size of 6 or 8 and evaluate against app p95 and DB saturation in a load test. At 8, 24 × 8 = **192**, leaving only 8 connections of headroom — too tight if instances or jobs grow. Choosing 6 yields **144** for safer margin, then measure pool borrow wait times.

### Part C — Layer-by-Layer Testing

1. Set Hikari max pool 5, `minIdle` 0, `connectionTimeout` 10 s; capture a baseline.
2. Ramp load gradually against a **read-only endpoint on a test DB**; avoid destructive queries or heavy writes.
3. Collect active/idle/pending metrics, DB sessions, CPU, p95, and request failures.
4. When pending borrowers appear, measure how long queries/transactions hold connections before touching pool size.
5. In a prepared MCP sandbox, test via **5432 direct** and then **6432 pooler** (or supported Auth Proxy mode); record differences in client count, server sessions, and wait times.
6. Test a stateful SQL feature on lab data to compare transaction vs. session mode; never flip all apps to transaction mode before testing your driver.
7. Model rollouts mathematically across two overlapping revisions instead of forcing scale spikes in production.
8. Propose a final configuration backed by **metrics and safety margins**, never from a single magic formula.

### Part D — Submission Evidence

| Evidence | Required Details |
| --- | --- |
| Database type/edition/region | Cloud SQL Enterprise/Enterprise Plus or AlloyDB |
| `max_connections` and reserved budget | Configured and observed values |
| Instances, Pods, Jobs | Peak and rollout overlap counts |
| HikariCP config | `maximumPoolSize`/`minimumIdle`, timeouts, lifetimes |
| Metrics | Active/idle/pending/borrow time and DB server sessions |
| MCP (if applicable) | Pool mode, 5432/6432, waiting clients / server connections |
| Compatibility | Driver, prepared statements, session state |
| Error/failover | Error types, bounded retries, and recovery time |
| Tuning decision | Bottleneck identified and effect on p95/5xx |
| Rollback plan | Reverting endpoint/config without deleting the DB |

## 16. Review Questions and Answers

1. **How many clients at most does HikariCP pool 5 across 20 Cloud Run instances create?** Roughly **100** database connections from that app assuming one pool per instance, excluding overlapping revisions/jobs.
2. **Does HTTP concurrency 80 mean you need 80 DB connections per instance?** No. Connection demand depends on DB hold time and how many requests actually hit the DB.
3. **Is `max_connections` the full budget available to your app?** No; reserve capacity for headroom and other workloads.
4. **Does Cloud SQL Auth Proxy pool connections itself?** No; it provides secure connectivity and can be paired with client or managed pooling.
5. **Does Cloud Run's built-in 100 connections/instance limit apply identically to all Language Connectors?** No.
6. **Which Cloud SQL PostgreSQL edition provides Google-managed MCP?** **Enterprise Plus** meeting network and maintenance prerequisites.
7. **Does enabling Cloud SQL MCP on an existing instance cause a restart?** Yes; plan a maintenance and change window.
8. **What are the usual ports for direct PostgreSQL and the managed pooler?** Typically **5432** and **6432**.
9. **Does MCP `max_pool_size=50` cap the entire instance at 50 sessions?** No; it caps per user/database **per pooler**.
10. **Is AlloyDB MCP enabled by default?** No; it must be enabled and configured.
11. **Does AlloyDB MCP support public IP connections?** No.
12. **When does transaction mode return a server connection?** Once the transaction ends; session mode holds it until the client disconnects.
13. **Should an app using long-lived `LISTEN` choose transaction mode?** No; use session mode or direct connections for stateful features.
14. **Is Hikari's `Connection is not available` always caused by `max_connections`?** No; the app pool can fill up simply because queries or transactions run slowly.
15. **Can raising Cloud Run `max_instances` cause more DB errors?** Yes, because it multiplies total pools.
16. **Why shouldn't you blindly retry a write transaction after a timeout?** The transaction may have committed; use idempotency keys and reconciliation.
17. **Does a pooler turn slow queries into fast ones?** No; it optimizes connection reuse, while SQL/I/O/locks still need tuning.
18. **When using two-tier pooling, which metrics do you need?** Hikari pending/borrow times and MCP waiting/server connections alongside DB and query metrics.

## 17. Production Checklist and Official Documentation

- [ ] Identified PostgreSQL Cloud SQL edition or AlloyDB instance; verified region, network, maintenance, and version.
- [ ] Checked `max_connections` and reserved slots for admin, other services, migrations, and headroom.
- [ ] Calculated **`instances/Pods/jobs/revisions × pools`** for both peak and rollout overlap.
- [ ] Java uses a singleton HikariCP pool, `try-with-resources`, and never holds transactions across external HTTP calls.
- [ ] `maximumPoolSize`/`minimumIdle`, timeouts, and `maxLifetime` tested under p95 load.
- [ ] Handled Cloud Run request-based CPU throttling and stale connections.
- [ ] Separated Auth Proxy/Language Connector roles from pooling, IAM, TLS, and networking.
- [ ] If using Cloud SQL MCP: verified Enterprise Plus, new network architecture, maintenance version, and restart window.
- [ ] If using AlloyDB MCP: verified private endpoint/port 6432, auth, and pooler stats.
- [ ] Tested transaction/session pool mode with prepared statements, `SET`, `LISTEN`, temp tables, and locks.
- [ ] Accounted for MCP client vs. server connection limits per user/database/pooler, not just per instance.
- [ ] Monitored pending borrowers, waiting clients, query wait/locks, CPU/memory/IOPS.
- [ ] Verified bounded retries, idempotent writes, failover, and secret rotation runbooks.
- [ ] Prepared canary, load test, rollback plan, and approval for any restart-inducing changes.
- [ ] Tracked Billing across DB tier/edition, Cloud Run/GKE scaling, logging/monitoring, and networking.
- [ ] Excluded DB passwords, IAM tokens, and sensitive SQL payloads from logs and docs.

**Official Google Cloud Sources:**

- [Cloud SQL PostgreSQL: Manage database connections](https://docs.cloud.google.com/sql/docs/postgres/manage-connections) — pooling, timeouts, retry/backoff.
- [Cloud SQL PostgreSQL: Managed Connection Pooling overview](https://docs.cloud.google.com/sql/docs/postgres/managed-connection-pooling) — prerequisites, poolers, modes, ports.
- [Cloud SQL PostgreSQL: Configure MCP](https://docs.cloud.google.com/sql/docs/postgres/configure-mcp) — enabling, flags, restarts, and monitoring.
- [Cloud SQL PostgreSQL: Quotas and limits](https://docs.cloud.google.com/sql/docs/postgres/quotas) — max connections and Cloud Run built-in limits.
- [Cloud SQL PostgreSQL: Connect from Cloud Run](https://docs.cloud.google.com/sql/docs/postgres/connect-run) — CPU throttling, connection management.
- [Cloud SQL PostgreSQL: Cloud SQL Auth Proxy](https://docs.cloud.google.com/sql/docs/postgres/sql-proxy) — encrypted/IAM tunnel, not a pooler.
- [AlloyDB: Connection overview](https://docs.cloud.google.com/alloydb/docs/connection-overview) — client pools, server-side MCP, tuning.
- [AlloyDB: Configure managed connection pooling](https://docs.cloud.google.com/alloydb/docs/configure-managed-connection-pooling) — port 6432, flags, transaction/session modes, metrics.
- [AlloyDB: Choose connectivity](https://docs.cloud.google.com/alloydb/docs/choose-alloydb-connectivity) — direct/Auth Proxy/connectors and TLS.
- [Cloud Run: Concurrency](https://docs.cloud.google.com/run/docs/about-concurrency) — request concurrency and autoscaling.
- [Cloud SQL MySQL: Managed Connection Pooling](https://docs.cloud.google.com/sql/docs/mysql/managed-connection-pooling) — thread pool distinct from PostgreSQL.
- [Cloud SQL pricing](https://cloud.google.com/sql/pricing) and [AlloyDB pricing](https://cloud.google.com/alloydb/pricing) — editions, compute, storage, and cost.

**Conclusion:** **Keep enough connections to serve load, never so many that you starve the database.** In-app pools cap connections per process, managed poolers share backend sessions where supported, and PostgreSQL `max_connections` plus CPU/memory/IO still define the real ceiling. **Budget system-wide, measure active/waiting/latency, validate transaction/session compatibility, and roll out with a clean rollback path.**
