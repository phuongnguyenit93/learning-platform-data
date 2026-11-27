# GoogleSQL and the PostgreSQL Interface in Spanner

## Learning Objectives

After this lesson, learners can:

1. Distinguish Spanner's **GoogleSQL dialect** and **PostgreSQL dialect/interface** from a PostgreSQL server on Cloud SQL.
2. Choose the right dialect based on SQL syntax, Java tooling, portability, and application features.
3. Write DDL/DML for the same data model in both dialects; properly use **primary keys**, data types, parameterized queries, and transactions.
4. Connect via **Spanner client/JDBC** or **PostgreSQL JDBC → PGAdapter**, understanding IAM/ADC mechanics and protocol limitations.
5. Create a lab database, inspect schemas, identify incompatibilities when migrating from PostgreSQL, and evaluate performance, reliability, security, and cost.

## 1. Context: Two SQL Languages, One Spanner Platform

In the **CLOUD_PROVIDERS_GCP** module, Java applications may run on Compute Engine, GKE, or Cloud Run and require a durable database. **Spanner** is a managed distributed database supporting relational transactions with horizontal scalability and regional/multi-region configurations. Spanner uses **the same storage and transaction engine** for both dialects:

- **GoogleSQL**: an SQL language tightly integrated with Spanner and the Google Cloud ecosystem.
- **PostgreSQL dialect/interface**: a compatible subset of PostgreSQL grammar, data types, and wire protocol, with Spanner-specific extensions.

For example, a retail company builds **orders-api** on Cloud Run to read/write order data transactionally; a worker on GKE processes Pub/Sub events; the analytics team uses BigQuery. The development team already knows PostgreSQL but wants Spanner's scalability. The question is not just "which SQL statements run?", but **which Java library, which migration path, which transaction semantics, and which dialect fit long-term goals?**

~~~mermaid
flowchart TB
    APP["Java orders-api / GKE worker"] --> CHOOSE{"Client choice"}
    CHOOSE --> NATIVE["Spanner Java Client / JDBC<br/>gRPC, ADC"]
    CHOOSE --> PGJDBC["PostgreSQL JDBC / psql"]
    PGJDBC --> PGAD["PGAdapter<br/>PostgreSQL wire protocol → Spanner gRPC"]
    NATIVE --> ENGINE["Spanner distributed engine"]
    PGAD --> ENGINE
    ENGINE --> GSQL["Database A<br/>GoogleSQL dialect"]
    ENGINE --> PSQL["Database B<br/>PostgreSQL dialect"]
~~~

**Note:** one **Spanner instance can contain multiple databases**, each selecting its dialect at creation time. **The dialect belongs to the database**, not the entire instance, though you cannot arbitrarily mix syntax from both dialects inside the same database. Changing the dialect of an existing database means **creating a new database and migrating**, not flipping a minor setting.

## 2. Choosing a Dialect Based on Application Requirements

| Criterion | **GoogleSQL** | **PostgreSQL Interface** |
|---|---|---|
| Familiar syntax | GoogleSQL, partially similar to BigQuery | PostgreSQL SQL, data types, and many PostgreSQL clients |
| Available drivers | Spanner Java Client / Spanner JDBC | Spanner Java Client / Spanner JDBC; or PostgreSQL JDBC via PGAdapter |
| Admin tooling | Spanner Studio, gcloud, Spanner APIs | Same control plane; plus psql/supported ORMs via PGAdapter |
| Migration from PostgreSQL | Usually requires updating DDL, queries, and data types | May require fewer SQL edits, but **not a drop-in replacement** |
| Portability to another PostgreSQL | Usually requires syntax conversion | Better if avoiding Spanner-specific extensions |
| Spanner distributed features | Accessed via supported SQL/APIs | Accessed via PostgreSQL syntax or Spanner-specific extensions |
| Underlying performance/reliability | Same Spanner engine | **Same** Spanner engine; not inherently faster or slower due to dialect |

**Selection rules:**

1. If the team already uses **Spanner Java APIs and GoogleSQL** and wants tight Google Cloud integration: consider GoogleSQL.
2. If the app/team uses **PostgreSQL JDBC, Hibernate, or psql** and prioritizes SQL portability: consider the PostgreSQL dialect.
3. If the app relies on **triggers, extensions, custom UDFs/procedures, fine-grained PostgreSQL locks, or transactional DDL**: inventory them first. These features are not automatically supported by the PostgreSQL interface.
4. If the scale is small and does not need distributed Spanner, Cloud SQL for PostgreSQL may require fewer app changes. Choose Spanner based on **SLOs, load, data, and cost**, not because of the "PostgreSQL" name.

## 3. Compatibility Boundaries: Spanner Does Not Run a PostgreSQL Server

**The PostgreSQL interface consists of two layers:**

- **SQL dialect**: a subset of PostgreSQL DQL/DML/DDL and types/functions, plus Spanner extensions.
- **PostgreSQL wire protocol**: uses **PGAdapter** as a proxy translating client PostgreSQL protocol traffic into **Spanner gRPC APIs**; PGAdapter **does not contain a PostgreSQL engine**.

| Component | What It Can Do | What Not to Assume |
|---|---|---|
| **PGAdapter** | Lets PostgreSQL JDBC, psql, and many ORMs connect to Spanner PostgreSQL dialect | Does not turn Spanner into a full PostgreSQL server |
| **Spanner JDBC** | Connects directly to both dialects via the Spanner endpoint | Does not mean it uses the PostgreSQL JDBC wire protocol |
| **Spanner Studio** | Runs SQL/DDL/DML and views schemas according to database dialect | Not pgAdmin or a PostgreSQL system administrator |
| **PostgreSQL-compatible schema** | Many CREATE TABLE, SELECT, JOIN, and INSERT statements | Does not automatically support every extension, function, catalog, lock, or PostgreSQL DDL |
| **Cloud IAM/FGAC** | Identifies principals and permissions on Spanner | Has no self-managed PostgreSQL login/password or superuser model |

### Limitations to Check Before Migration

- Arbitrary **PostgreSQL extensions, user-defined types/functions/operators, triggers, foreign data wrappers, and transactional DDL** are not supported.
- **SAVEPOINT**, certain fine-grained concurrency/locking constructs, and **pg_catalog** coverage are incomplete compared to upstream PostgreSQL.
- **Serial/identity:** do not assume every legacy **SERIAL** statement retains identical semantics. Current docs support **serial aliases** when **spanner.default_sequence_kind=bit_reversed_positive** is set; Spanner sequences/identities have their own semantics and do not guarantee strictly contiguous sequential IDs like traditional sequences.
- **Data type differences:** in Spanner PostgreSQL dialect, **int** is an alias for int8 (64-bit), **timestamp without time zone** is unsupported, and **numeric(18,2)** may work in expressions but **cannot be used as a type modifier in DDL**. Do not assume every PostgreSQL type maps 1:1.
- **PostgreSQL administrative utilities:** do not use pgAdmin to provision/manage Spanner like a regular PostgreSQL server; use Spanner console, gcloud, and APIs.

Never equate "a SQL syntax is supported" with "all runtime/transaction/optimizer behavior matches PostgreSQL." Test the app, ORM migrations, performance, and actual error codes.

## 4. Comparing Data Types and DDL on the Same Model

Suppose an **orders** table contains: order ID, customer ID, total amount, creation timestamp, and status. Choose a **well-distributed primary key** rather than a monotonically auto-incrementing number for a write-heavy table.

### 4.1. Corresponding Data Types

| Need | **GoogleSQL** | **PostgreSQL Dialect** |
|---|---|---|
| 64-bit integer | **INT64** | **BIGINT / INT8** |
| String | **STRING(128)** | **VARCHAR(128) / TEXT** |
| Bytes | **BYTES(MAX)** | **BYTEA** |
| Boolean | **BOOL** | **BOOL / BOOLEAN** |
| Absolute point in time | **TIMESTAMP** | **TIMESTAMPTZ** |
| Calendar date | **DATE** | **DATE** |
| Exact decimal | **NUMERIC** | **NUMERIC / DECIMAL**; DDL omits precision/scale modifiers |
| JSON | **JSON** | **JSONB** |
| Array | `ARRAY<T>` | `T[]`, multidimensional arrays unsupported |
| UUID | **UUID** per current GoogleSQL support | **UUID** |

Inspect type limitations carefully, especially **NUMERIC**, **JSON/JSONB**, timezones/collations, and indexes. For example, `timestamp without time zone` is valid in standard PostgreSQL but **cannot** be used directly in a Spanner PostgreSQL schema.

### 4.2. GoogleSQL: PRIMARY KEY Placed After Column List

~~~sql
CREATE TABLE Orders (
  OrderId STRING(36) NOT NULL,
  CustomerId STRING(36) NOT NULL,
  Amount NUMERIC NOT NULL,
  CreatedAt TIMESTAMP NOT NULL,
  Status STRING(32) NOT NULL
) PRIMARY KEY (OrderId);

CREATE INDEX OrdersByCustomer ON Orders (CustomerId);
~~~

### 4.3. PostgreSQL: PRIMARY KEY Inside CREATE TABLE Parentheses

~~~sql
CREATE TABLE orders (
  order_id VARCHAR(36) PRIMARY KEY,
  customer_id VARCHAR(36) NOT NULL,
  amount NUMERIC NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  status VARCHAR(32) NOT NULL
);

CREATE INDEX orders_by_customer ON orders (customer_id);
~~~

**The two snippets above are alternatives in two separate databases**—do not run both on the same database. The example uses app-generated UUID strings for syntax clarity; for new apps, consider the UUID type and supported key-generation features. Both dialects require a **primary key**, which Spanner uses to sort and partition data.

### 4.4. Primary Keys Determine Scalability

Spanner partitions key ranges into **splits**. If a primary key increases sequentially, such as `OrderId = 1, 2, 3...`, heavy writes can crowd into the **beginning/end of a key range**, creating a **hotspot** even after adding processing units.

Prefer **distributed UUIDs**, hashed/distributed keys, or **bit-reversed sequences/identities** when appropriate. When using **interleaved tables** (parent/child by key), consider locality, transaction load, and parent keys; do not confuse interleaving with PostgreSQL table inheritance/partitioning.

~~~mermaid
flowchart LR
  SEQ["Monotonic sequential key<br/>1,2,3,..."] --> HOT["Writes concentrated in one key range<br/>hotspot"]
  UUID["UUID/distributed key"] --> SPLITS["Writes spread across multiple splits"]
~~~

**Exception:** randomly generated UUIDs will not solve every hotspot if **secondary indexes** still lead with a monotonically increasing key such as a timestamp. Review the entire schema, indexes, and transaction access patterns.

## 5. DML, Query Parameters, Transactions, and Spanner Syntax

### 5.1. Insert and Select: Two Ways to Write Them

On the **GoogleSQL** database with table **Orders**:

~~~sql
INSERT INTO Orders (OrderId, CustomerId, Amount, CreatedAt, Status)
VALUES ('ord-a1', 'cust-7', 350000, CURRENT_TIMESTAMP(), 'CREATED');

SELECT OrderId, Amount, Status
FROM Orders
WHERE CustomerId = 'cust-7'
ORDER BY OrderId;
~~~

On the **PostgreSQL** database with table **orders**:

~~~sql
INSERT INTO orders (order_id, customer_id, amount, created_at, status)
VALUES ('ord-a1', 'cust-7', 350000, CURRENT_TIMESTAMP, 'CREATED');

SELECT order_id, amount, status
FROM orders
WHERE customer_id = 'cust-7'
ORDER BY order_id;
~~~

These are lab commands on two **different** databases. In production, use **prepared statements/parameters** and never concatenate client input directly into SQL strings.

### 5.2. Query Parameters

| Access Method | Common Placeholder | Notes |
|---|---|---|
| **GoogleSQL via Spanner API** | **@customer_id** | Spanner client bind parameters |
| **PostgreSQL SQL/wire protocol** | **$1, $2...** | Positional parameters for PostgreSQL protocol |
| **Java JDBC PreparedStatement** | **?** | Bound by the JDBC driver; applies to both Spanner JDBC and PostgreSQL JDBC |

Plain SQL examples:

~~~sql
-- GoogleSQL, executed via Spanner API with bind parameter @customer_id
SELECT OrderId FROM Orders WHERE CustomerId = @customer_id;

-- PostgreSQL SQL, bind $1 using a PostgreSQL client
SELECT order_id FROM orders WHERE customer_id = $1;
~~~

Do not paste **@customer_id** into psql expecting psql to bind it, and do not pass **$1** to `gcloud execute-sql` without a corresponding binding mechanism. The `gcloud` examples below use lab literals; Java safely uses `JDBC PreparedStatement`.

### 5.3. Transaction Semantics Are Not Default PostgreSQL

Spanner provides **ACID read-write transactions** with **serializable isolation/external consistency** per transaction configuration. Spanner also supports other modes/isolation levels documented by Google Cloud, but **does not automatically replicate all PostgreSQL MVCC/locking semantics** into the PostgreSQL interface.

A read-write transaction can be **ABORTED** due to contention or transient events. Spanner client libraries and drivers provide retry mechanisms, however:

1. **Code inside a transaction callback can execute again**; never call payment APIs or send non-idempotent emails directly from a retried callback.
2. Use an **idempotency key** and the outbox pattern when publishing events to Pub/Sub after commit.
3. Keep transactions short; avoid overly broad scans or locking the same hot key.
4. Test retries under contending traffic, monitoring transaction abort and commit counts.

Spanner does not support **transactional DDL** like standard PostgreSQL. When applying DDL via `gcloud`/Spanner Studio, check the long-running schema operation and wait for completion before running schema-dependent data migrations.

### 5.4. Query Hints and the Optimizer

The two dialects write hints differently:

~~~sql
-- GoogleSQL hint syntax (illustrative form)
SELECT * FROM Orders@{FORCE_INDEX=OrdersByCustomer}
WHERE CustomerId = 'cust-7';

-- PostgreSQL dialect uses Spanner comment-style hints
SELECT * FROM orders /*@ FORCE_INDEX=orders_by_customer */
WHERE customer_id = 'cust-7';
~~~

Do not apply hints unconditionally; inspect **EXPLAIN/query plans/Query Insights**, indexes, and statistics to verify whether a hint actually improves latency/cost. Every new index also consumes storage and increases write cost.

## 6. Lab A — Creating an Instance and Two Databases

The commands below **can create billable resources**; run only in an authorized lab project. Example values:

| Property | Value |
|---|---|
| Project | **shop-dev-001** |
| Instance | **spanner-sql-lab** |
| Config | **regional-asia-southeast1** (Singapore) |
| GoogleSQL Database | **orders-google** |
| PostgreSQL Database | **orders-pg** |
| Compute | **100 processing units** for the lab; billed by resource usage |

### 6.1. Preflight and Instance Creation

~~~bash
gcloud config get-value project
gcloud auth list
gcloud services list --enabled --project=shop-dev-001
gcloud spanner instance-configs list --project=shop-dev-001
gcloud spanner instances list --project=shop-dev-001

# Operate only on an authorized lab project.
gcloud services enable spanner.googleapis.com \
  --project=shop-dev-001

gcloud spanner instances create spanner-sql-lab \
  --project=shop-dev-001 \
  --config=regional-asia-southeast1 \
  --description="SQL dialect learning lab" \
  --edition=STANDARD \
  --processing-units=100
~~~

**Do not use a lab instance for production**: 100 processing units is a small configuration. Check **instance configuration, edition/quotas, pricing**, and regional availability beforehand; do not create another instance if one already exists.

### 6.2. Creating Two Databases on the Same Instance

~~~bash
# GoogleSQL is default, but specified explicitly for easier review.
gcloud spanner databases create orders-google \
  --project=shop-dev-001 \
  --instance=spanner-sql-lab \
  --database-dialect=GOOGLE_STANDARD_SQL

gcloud spanner databases create orders-pg \
  --project=shop-dev-001 \
  --instance=spanner-sql-lab \
  --database-dialect=POSTGRESQL

gcloud spanner databases list \
  --project=shop-dev-001 \
  --instance=spanner-sql-lab
~~~

**Important:** when **creating a PostgreSQL-dialect database**, `gcloud` **does not support `--ddl` or `--ddl-file` inside the create command**. You must **create an empty database first, then run `ddl update`**. GoogleSQL accepts DDL at creation time or afterward. Choosing the wrong dialect at creation requires a migration, not an in-place modification on the same database.

### 6.3. Applying Schemas per Dialect

~~~bash
# GoogleSQL: PRIMARY KEY clause sits outside the parentheses.
gcloud spanner databases ddl update orders-google \
  --project=shop-dev-001 \
  --instance=spanner-sql-lab \
  --ddl='CREATE TABLE Orders (OrderId STRING(36) NOT NULL, CustomerId STRING(36) NOT NULL, Amount NUMERIC NOT NULL, CreatedAt TIMESTAMP NOT NULL, Status STRING(32) NOT NULL) PRIMARY KEY (OrderId)'

# PostgreSQL: PRIMARY KEY sits inside CREATE TABLE.
gcloud spanner databases ddl update orders-pg \
  --project=shop-dev-001 \
  --instance=spanner-sql-lab \
  --ddl='CREATE TABLE orders (order_id VARCHAR(36) PRIMARY KEY, customer_id VARCHAR(36) NOT NULL, amount NUMERIC NOT NULL, created_at TIMESTAMPTZ NOT NULL, status VARCHAR(32) NOT NULL)'
~~~

For large tables/migrations, use reviewed DDL files and a CI/CD workflow to avoid shell-quoting mistakes. The example commands **do not create indexes** here; to run the `FORCE_INDEX` queries from section 5.4, create the corresponding indexes from section 4 first.

### 6.4. DML and Reading Back with gcloud

~~~bash
gcloud spanner databases execute-sql orders-google \
  --project=shop-dev-001 --instance=spanner-sql-lab \
  --sql="INSERT INTO Orders (OrderId,CustomerId,Amount,CreatedAt,Status) VALUES ('ord-a1','cust-7',350000,CURRENT_TIMESTAMP(),'CREATED')"

gcloud spanner databases execute-sql orders-google \
  --project=shop-dev-001 --instance=spanner-sql-lab \
  --sql="SELECT OrderId, Status FROM Orders WHERE CustomerId='cust-7'"

gcloud spanner databases execute-sql orders-pg \
  --project=shop-dev-001 --instance=spanner-sql-lab \
  --sql="INSERT INTO orders (order_id,customer_id,amount,created_at,status) VALUES ('ord-a1','cust-7',350000,CURRENT_TIMESTAMP,'CREATED')"

gcloud spanner databases execute-sql orders-pg \
  --project=shop-dev-001 --instance=spanner-sql-lab \
  --sql="SELECT order_id,status FROM orders WHERE customer_id='cust-7'"
~~~

If you repeat an INSERT with the same key, an **`ALREADY_EXISTS`/unique key error** is expected. Do not delete production data just to "re-run the lab"; change lab IDs cleanly.

### 6.5. Inspecting Schemas and Cleaning Up Resources

~~~bash
gcloud spanner databases ddl describe orders-google \
  --project=shop-dev-001 --instance=spanner-sql-lab
gcloud spanner databases ddl describe orders-pg \
  --project=shop-dev-001 --instance=spanner-sql-lab
~~~

After finishing and confirming no data needs to be kept, delete **the lab databases/instance** following an approved procedure. **Deleting a database is destructive**, so check backups/deletion protection and billing before proceeding; never embed delete commands into unattended scripts.

## 7. Connecting to the PostgreSQL Interface via PGAdapter and psql

**PGAdapter** can run as a standalone process, a Cloud Run/GKE sidecar, or **in-process inside the JVM**. It listens for the PostgreSQL wire protocol on localhost and forwards calls to Spanner gRPC using the process's IAM/ADC principal.

~~~mermaid
sequenceDiagram
  participant J as PostgreSQL JDBC / psql
  participant P as PGAdapter localhost:5432
  participant S as Spanner API
  J->>P: PostgreSQL protocol request
  P->>S: Authenticated Spanner gRPC request (ADC)
  S-->>P: SQL results
  P-->>J: PostgreSQL protocol response
~~~

### 7.1. Running Locally in a Lab with ADC

Download the PGAdapter JAR per the official **Start PGAdapter** documentation; ensure a Java runtime is installed. Once the user authenticates ADC for the lab:

~~~bash
# For development machines only; do not download JSON service account keys.
gcloud auth application-default login

# Assumes pgadapter.jar was downloaded per documentation into the current directory.
java -jar pgadapter.jar \
  -p shop-dev-001 \
  -i spanner-sql-lab \
  -d orders-pg \
  -s 5432
~~~

In another terminal:

~~~bash
psql -h 127.0.0.1 -p 5432 -d orders-pg \
  -c "SELECT order_id, status FROM orders ORDER BY order_id"
~~~

**Security boundary:** PGAdapter listens only on localhost by default. **Do not add `-x` or bind a public interface** to expose the proxy to the Internet; any client able to reach that local socket can exercise the PGAdapter process's IAM permissions. PostgreSQL username/password values at the PGAdapter endpoint **do not correspond to PostgreSQL server users**: Spanner authorization is governed by PGAdapter's **IAM principal**, optionally scoped further with fine-grained access control database roles.

### 7.2. PGAdapter Limitations

- Does not support the entire PostgreSQL wire protocol or all **psql meta** commands; apps/tools relying on server admin features must be tested.
- **Transactional DDL** is not supported like a PostgreSQL server; do not wrap schema migrations in `BEGIN`/`ROLLBACK` assuming atomicity.
- Client → PGAdapter connections in this example use **localhost**, not end-to-end TLS to a PostgreSQL server. PGAdapter → Spanner uses protected gRPC; do not expose PGAdapter outside the trusted boundary.
- Verify compatibility versions for **PostgreSQL JDBC 42.x**, psql/ORM/Hibernate, and PGAdapter; never enable a feature just because a tool reports "PostgreSQL 14."

### 7.3. Deploying on Cloud Run and GKE

On **Cloud Run**, run PGAdapter as a **sidecar** in the same instance or in-process in Java; containers in the same instance share the network namespace and the app connects to localhost. On **GKE**, run PGAdapter as a sidecar in the same Pod, configured with **Workload Identity Federation for GKE** and IAM. In both cases:

- Attach a least-privilege runtime service account/identity with access to the Spanner database.
- Never place service account JSON keys inside images, Kubernetes Secrets, or environment variables when Workload Identity/ADC is available.
- Pin the PGAdapter version/digest; configure startup/health checks, resource limits, and monitoring.
- Size the JDBC pool sensibly and test transaction retries and concurrent connections.

## 8. Lab B — Java JDBC via Two Connection Paths

For Java, there are **two valid JDBC paths**:

| Driver | Sample JDBC URL | Connects To |
|---|---|---|
| **com.google.cloud:google-cloud-spanner-jdbc** | jdbc:cloudspanner:/projects/shop-dev-001/instances/spanner-sql-lab/databases/orders-google | Spanner gRPC/API directly using ADC |
| **org.postgresql:postgresql** | jdbc:postgresql://127.0.0.1:5432/orders-pg | PGAdapter process/sidecar, then Spanner API |

**Spanner JDBC** also supports **orders-pg** if you change the database name in the URL, without needing PGAdapter; this is especially useful when Java code does not require PostgreSQL-compatible ORMs or tooling.

### 8.1. Java Snippet Using PreparedStatement

This example uses Java 21, assuming the corresponding driver dependency is configured in Maven/Gradle and the account has appropriate IAM permissions. Pass **`pgwire`** or **`native`** as the argument:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class SpannerDialectQuery {
    private SpannerDialectQuery() {}

    public static void main(String[] args) throws SQLException {
        boolean viaPgAdapter =
            args.length > 0 && "pgwire".equalsIgnoreCase(args[0]);

        String url = viaPgAdapter
            ? "jdbc:postgresql://127.0.0.1:5432/orders-pg"
            : "jdbc:cloudspanner:/projects/shop-dev-001"
              + "/instances/spanner-sql-lab/databases/orders-google";

        String sql = viaPgAdapter
            ? "SELECT order_id, status FROM orders WHERE customer_id = ?"
            : "SELECT OrderId, Status FROM Orders WHERE CustomerId = ?";

        try (Connection connection = DriverManager.getConnection(url);
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setString(1, "cust-7");
            try (ResultSet rows = statement.executeQuery()) {
                while (rows.next()) {
                    System.out.printf("%s : %s%n",
                        rows.getString(1), rows.getString(2));
                }
            }
        }
    }
}
~~~

This is a **standalone class once the proper JDBC drivers are installed**. It assumes the Spanner lab holds the data from section 6 and PGAdapter is running for **pgwire**. With **native**, Spanner JDBC uses ADC directly without needing a PostgreSQL username/password.

### 8.2. Key Java Considerations

1. **`PreparedStatement` uses `?`** in both drivers—much safer than concatenating user input strings.
2. Use **connection/session pools** per driver guidance; never spawn a new PGAdapter process or Spanner client per HTTP request.
3. Configure **deadlines, transaction retries, and backoff**, avoiding retrying a payment outside a re-executable transaction callback.
4. With Cloud Run auto-scaling / GKE HPA, size sessions and pools based on instance counts; do not hardcode 400 sessions just because of an old example.
5. When using Hibernate/Spring Data, choose dialect/driver versions verified in the **Spanner PostgreSQL drivers and ORMs compatibility matrix**. Do not assume the native PostgreSQL Hibernate dialect runs every migration.
6. Log request/transaction tags and query latency **without logging PII or sensitive full query parameters**.

### 8.3. Spring Boot: Distinguishing Datasource Configurations

~~~properties
# Example A: Native Spanner JDBC
spring.datasource.url=jdbc:cloudspanner:/projects/shop-dev-001/instances/spanner-sql-lab/databases/orders-google

# Example B: PostgreSQL JDBC to PGAdapter (replaces the line above)
# spring.datasource.url=jdbc:postgresql://127.0.0.1:5432/orders-pg
~~~

This is only the **connection URL**, not a complete Spring Boot configuration. You still need the driver on the classpath, pooling, access permissions, health checks, schema migrations, and tests. Do not put a real PostgreSQL password in properties: **PGAdapter uses the process's IAM principal/ADC**, not a Cloud SQL `postgres`/superuser role.

## 9. IAM, Authentication, and Access Control

For both dialects, Spanner uses **Google Cloud IAM** for resource management and caller authentication. With the PostgreSQL wire protocol, **PGAdapter uses the process's ADC/service account** to send requests. The PostgreSQL username in a JDBC string is not an execution identity on Spanner.

| Identity / Role | Responsibility | Warning |
|---|---|---|
| **Deployer/DB operator** | Create instances/databases and update DDL | Never grant `roles/spanner.admin` to the runtime |
| **orders-runtime@...** | Access Spanner database from Cloud Run | Grant only appropriate database permissions |
| **PGAdapter service identity** | Uses ADC to call Spanner gRPC | Any client reaching PGAdapter can leverage this process's permissions |
| **Fine-grained database role** | `SELECT`/`INSERT`/`UPDATE` on specific tables | Requires FGAC IAM role and permission to assume the role |
| **Auditor/SRE** | View metrics/logs and query statistics | Does not need DDL edit rights or sensitive data read access |

### 9.1. Resource IAM vs. FGAC

The **`roles/spanner.databaseUser`** role allows reads/writes and **can also update DDL**; it is not read-only. If an application only needs `SELECT` on a few tables, use **fine-grained access control (FGAC)**:

1. Create a **database role** and explicit SQL `GRANT` statements in your active dialect.
2. Grant **`roles/spanner.fineGrainedAccessUser`** along with **`roles/spanner.databaseRoleUser`** using IAM Conditions specifying the role.
3. Specify the database role when the client/PGAdapter connects.
4. Test with the application identity: verify allowed reads plus negative tests against schema/DDL/other tables.

If no database role is specified, permissions are evaluated against the IAM principal (role-based restrictions are not applied automatically). Do not grant a broad resource-level role to the runtime and expect a narrow database role to restrict it.

### 9.2. Broad Lab IAM Example (Not a Production Default)

~~~bash
# Run only in an authorized lab project; databaseUser is quite broad.
gcloud spanner databases add-iam-policy-binding orders-google \
  --project=shop-dev-001 \
  --instance=spanner-sql-lab \
  --member="serviceAccount:orders-runtime@shop-dev-001.iam.gserviceaccount.com" \
  --role="roles/spanner.databaseUser"

gcloud spanner databases get-iam-policy orders-google \
  --project=shop-dev-001 \
  --instance=spanner-sql-lab
~~~

**Risk:** `databaseUser` includes DDL update permissions; production should evaluate FGAC or supported custom IAM roles. If moving from **Cloud SQL for PostgreSQL**, PostgreSQL-internal **`GRANT` syntax** differs from Spanner's IAM/FGAC model.

### 9.3. Security at the Client Boundary

- Cloud Run and GKE should use **service identity / Workload Identity Federation**, avoiding static JSON service account keys.
- Run **PGAdapter on localhost** or inside a trusted Pod/instance; never expose port 5432 to the Internet.
- Spanner client API connections use TLS and IAM; the PGAdapter local socket is a separate boundary to protect. If a remote PGAdapter is unavoidable, review networking and explicit authentication mechanisms rather than assuming PostgreSQL TLS/mTLS is automatic.
- Monitor IAM changes, service account impersonation, **Database Audit Logs**, and CMEK if required.
- Never include credentials/tokens or order payloads in query tags, logs, or debug output.

## 10. Migrating a PostgreSQL Application to the Spanner PostgreSQL Interface

**Syntax compatibility is a starting point, not a guarantee that you can "just swap the connection string."** Migrating from Cloud SQL PostgreSQL or self-managed PostgreSQL should follow these stages:

| Stage | Work | What to Verify |
|---|---|---|
| **Inventory** | Extensions, stored procedures, triggers, views, sequences, types, indexes, schema migration tools | Unsupported features and semantic differences |
| **DDL translation** | Convert data types, PRIMARY KEYs, constraints, and identity columns | Mandatory PKs, non-hotspot keys, numeric modifiers, timestamps |
| **Data migration** | Export/copy/ingest data with supported tools | Types/encoding, duplicates, foreign keys, row counts |
| **Client migration** | PG JDBC + PGAdapter or Spanner JDBC/client | IAM auth, connection URLs, pools, transaction retries |
| **Behavioral tests** | CRUD, transactions, ordering, time zones, JSON, locking | Semantics, not just syntax |
| **Load tests** | Queries, index plans, hotspots, CPU/sessions | p95/p99 latency, throughput, and cost |
| **Cutover/rollback** | Sync writes, switch traffic, retain source per policy | Schema compatibility, RPO/RTO, no blind dual-write |

### 10.1. Examples of Differences to Fix

| Upstream PostgreSQL | How to Handle in Spanner PostgreSQL |
|---|---|
| Sequential `SERIAL`/Sequence IDs | Consider UUID or bit-reversed sequence; for `SERIAL` aliases, set the database option first |
| `NUMERIC(12,2)` in `CREATE TABLE` | Use `NUMERIC`, enforce precision/scale validation in the app or supported `CHECK` constraints |
| `TIMESTAMP WITHOUT TIME ZONE` | Use `TIMESTAMPTZ` and normalize UTC/zone in the app |
| Triggers updating audit fields | Move logic into app/transactions or supported Spanner features |
| User-defined PL/pgSQL functions | Refactor to app SQL/client logic; inspect supported system procedures |
| `psql` admin commands / `pg_dump` extensions | Use Spanner DDL APIs and supported PGAdapter import/export flows |
| Advisory locks / `SAVEPOINT` | Redesign transactions/idempotency without relying on PostgreSQL-style locking |

### 10.2. Testing on a Fresh Clone Database

Never migrate production directly with an unreviewed import command. Lab approach:

1. Extract the original PostgreSQL DDL schema and list unsupported constructs.
2. Create an empty **Spanner PostgreSQL-dialect database** and normalize the DDL.
3. Load a test dataset containing Vietnamese diacritics, NULLs, JSONB, timestamps, and representative business keys.
4. Run integration tests with **PostgreSQL JDBC + PGAdapter**, then try **Spanner JDBC** if you want to remove the proxy layer.
5. Measure query plans, hotspots, transaction aborts, and cost; fix schemas/keys before migrating real data.
6. Plan cutover/rollback: write-freeze window, data verification, cutover timing, and protecting in-flight transactions.

### 10.3. Migrating Back to PostgreSQL

The PostgreSQL interface improves **portability**, but **Spanner-specific extensions** (interleaving, hints, TTL, identities, or proprietary features) must still be replaced or removed. When moving back to a PostgreSQL server, export dialect DDL and data and refactor Spanner-specific elements. Portability does not equal 100% drop-in portability.

## 11. Performance, Reliability, and Cost Depend on Spanner Design

### 11.1. Do Not Optimize by Dialect Before Measuring

Because both dialects share **the same Spanner engine**, there is no blanket rule that "PostgreSQL is slower than GoogleSQL." Latency depends on:

- **Key distributions and hotspots**: PK/sequential index writes, high-contention rows.
- **Indexes and query plans**: filter columns, `ORDER BY`, join patterns, large scans.
- **Transaction size/duration**: read/write scope, contention, `ABORTED`/retries.
- **Instance config/leader locality**: regional/dual/multi-region, client distance to leader and write quorum.
- **Capacity**: processing units/nodes, autoscaling, CPU/storage, session counts.
- **Client**: JDBC/PGAdapter sidecar topology, pooling, gRPC deadlines, and retries.

**Processing units** measure capacity: **1 node = 1,000 processing units**. A node is a logical capacity unit distributed across infrastructure, **not a physical machine**. Adding capacity can raise throughput, **but will not automatically fix a primary key hotspot**.

### 11.2. Even a Regional Instance Replicates Across Zones

Spanner **regional** uses multiple replicas in **different zones of the same region** and quorum to serve transactions; you do not create a Cloud SQL-style "read replica" manually for basic high availability. **Multi-region** raises availability and geographic spread at the cost of extra replica/quorum latency and billing. Both dialects benefit from the same topology.

**Multi-region does not mean no backups needed:** data loss from SQL bugs or accidental deletes is replicated everywhere. Design **backups/PITR, deletion protection, restore drills**, and separate IAM.

### 11.3. System Insights, Query Insights, and Key Visualizer

| Signal | Where to Look | Hypothesis |
|---|---|---|
| Sustained high-priority CPU | Spanner **System Insights** / Cloud Monitoring | Under-provisioning, large query scans |
| One key range receiving abnormal writes | **Key Visualizer** | PK/secondary index hotspot |
| High query p99 | **Query Insights**, query plans | Missing index, excessive rows scanned, lock contention |
| Rising `ABORTED` retries | Transaction metrics and application logs | Transaction contention, accessing the same hot rows |
| Surging sessions | Session metrics, Cloud Run/GKE instance count | Client/pool created per request or scale-out |
| Queries stable yet bill rising | Cloud Billing + Spanner compute/storage/backups | Overprovisioned PUs, storage/index/backup growth |
| Errors only on the pgwire path | PGAdapter logs, JDBC errors, resource usage | Proxy issue, driver/ORM incompatibility |

When comparing **GoogleSQL vs. PostgreSQL dialect**, benchmark the **exact target schema, data distribution, service locations, and workload**. Test both **direct Spanner JDBC** and PG JDBC/PGAdapter if the client path is a key variable.

### 11.4. Controlling Lab and Production Costs

Costs can include **instance compute capacity, data/index storage, backups, network/data transfer, Data Boost when used**, plus application/observability systems. **Regional** is usually less expensive than multi-region, though selection must follow data residency and SLOs.

Do not create multiple instances/dialects just to view DDL if one shared instance suffices. After the lab, **clean up both databases and the instance** with approval; **budget alerts do not shut down resources automatically**. Pricing/quotas vary by edition, instance configuration, and region—check Google Cloud pricing/quotas at deployment time.

## 12. Troubleshooting: Diagnosing the Right Layer

| Symptom | Possible Cause | First Check |
|---|---|---|
| PostgreSQL JDBC cannot connect to **localhost:5432** | PGAdapter not running, wrong port, startup error | Process/sidecar logs, local listener |
| PostgreSQL JDBC connects but SQL fails | Unsupported DDL/type/function/extension | PostgreSQL language reference, schema, ORM SQL |
| **`PERMISSION_DENIED`** via PGAdapter | ADC identity lacks Spanner IAM/role | Runtime service account, PGAdapter credentials, FGAC role |
| **`PERMISSION_DENIED`** running DDL | Role lacks **`spanner.databases.updateDdl`** | Effective IAM permissions and DDL operation |
| Changing PostgreSQL username still grants access | PGAdapter uses the process's service account/ADC | Check IAM; don't confuse with PostgreSQL server logins |
| ORM migration fails on savepoint/trigger | PostgreSQL compatibility covers a subset | Refactor migration, remove unsupported constructs |
| PostgreSQL `CREATE TABLE` fails on `numeric(12,2)` | Precision/scale modifiers unsupported in DDL | Switch to `NUMERIC`, add validation |
| `CREATE TABLE` missing `PRIMARY KEY` | Spanner requires a PK | Choose a well-distributed key |
| Slow writes with ascending IDs | Hotspot at end of key range | Key Visualizer, key strategy, secondary indexes |
| High query p99 despite moderate CPU | Lock contention, scans, or network locality | Query Insights, transaction metrics, leader region |
| **`ABORTED`** in transaction | Contention/transient conflict, faulty retry | Retry policy, short transactions, app side effects |
| Schema DDL sent yet queries still fail | Schema update still running or invalid | Spanner operations, DDL describe |
| Uppercase SQL identifiers folded to lowercase | PostgreSQL folds unquoted identifiers | Use consistent lowercase or explicit quoted identifiers |
| `gcloud` PostgreSQL create with `--ddl` fails | `--ddl` unsupported when creating PG database | Create empty DB first, then `ddl update` |
| SQL works on Cloud SQL PG but fails on Spanner | PostgreSQL engine semantics differ | Compare supported language and transaction behavior |
| 0% traffic still incurs charges | Spanner instance capacity stays provisioned | Instance billing/capacity; controlled cleanup |

### 12.1. Minimal Verification Sequence

~~~bash
# Read configuration without modifying data:
gcloud spanner instances describe spanner-sql-lab \
  --project=shop-dev-001

gcloud spanner databases list \
  --instance=spanner-sql-lab \
  --project=shop-dev-001

gcloud spanner databases ddl describe orders-pg \
  --instance=spanner-sql-lab \
  --project=shop-dev-001

gcloud spanner databases get-iam-policy orders-pg \
  --instance=spanner-sql-lab \
  --project=shop-dev-001
~~~

**Workflow:** verify exact project/instance/database/dialect → identify client path → check IAM → check syntax/DDL/schema → measure sessions/CPU/queries/indexes/transactions → tune and run negative tests.

## 13. Integrated Scenario: Migrating an Order Service from Cloud SQL

**An Phat** currently runs Java Spring Boot on Cloud Run, storing orders in Cloud SQL for PostgreSQL. Traffic is growing, requiring higher scalability and consistent transactions across a large dataset. The team wants to adopt Spanner while keeping Hibernate and existing PostgreSQL syntax.

### 13.1. Design Decisions

| Question | Choice and Rationale |
|---|---|
| Which dialect? | **PostgreSQL interface** if the compatibility audit passes and portability matters |
| How to run JDBC? | Start with **PG JDBC + PGAdapter** to minimize client changes; benchmark **direct Spanner JDBC** |
| Primary key? | **UUID or distributed key** for orders; review indexes and join patterns |
| SQL schema? | Remove triggers/unsupported types, convert `NUMERIC` modifiers and transactional DDL |
| Auth? | Cloud Run runtime identity + Spanner IAM/FGAC; never reuse PostgreSQL superuser/password |
| Transactions? | Short read-write transactions, idempotency keys, proper `ABORTED` handling |
| Availability? | Pick Spanner instance config by users/SLO/data residency; include backups and restore tests |
| Monitoring? | p95/p99, transaction aborts, CPU, Key Visualizer, PGAdapter logs |

### 13.2. Cutover and Rollback Flow

~~~mermaid
flowchart TD
    INVENTORY["Audit extensions/SQL/queries"] --> DDL["Convert schema + choose PK"]
    DDL --> LAB["Create Spanner PostgreSQL lab"]
    LAB --> TEST["Integration + load + retry tests"]
    TEST --> CHECK{"Compatible and SLO met?"}
    CHECK -->|No| FIX["Adjust schema/ORM/client, retest"]
    CHECK -->|Yes| SYNC["Sync data + validation"]
    SYNC --> CUT["Cutover traffic per runbook"]
    CUT --> OBS["Monitor errors/latency/consistency"]
    OBS --> DR["Keep source per rollback window"]
~~~

**Likely failure scenario:** the legacy model uses a monotonically increasing `SERIAL` primary key, an audit-updating trigger, and Hibernate migrations using `SAVEPOINT`. The app **cannot simply change the JDBC URL and deploy to production**. You must adopt distributed key generation, move trigger logic to the app/a Spanner-supported mechanism, and adjust transaction/migration logic.

### 13.3. Acceptance Criteria

1. All CRUD, joins, order constraints, and transaction rollbacks tested.
2. Zero remaining unsupported functions/schema constructs required at runtime.
3. p95/p99 and transaction-abort rates meet target SLOs.
4. App runs with least-privilege service identity; negative IAM/FGAC tests pass.
5. Migration confirms row counts/checksums with no lost order events; recovery and rollback runbooks exist.
6. Capacity/cost controlled using actual workload measurements rather than guessing a "node count."

## 14. Exercises with Answers

### Exercise A — Two Dialects and One Instance

**Question:** Can you create one Spanner instance containing one GoogleSQL database and one PostgreSQL database? Can you convert an existing database's dialect with an `ALTER` command?

**Answer:** **Yes** to two databases with different dialects inside the same instance; **no** to switching an existing database's dialect via a simple flag. Changing dialects requires creating a new target database and migrating schema/data/app.

### Exercise B — Is the PostgreSQL Interface Complete PostgreSQL?

An application relies on the PostGIS extension, triggers, PL/pgSQL functions, and pgAdmin management.

**Answer:** Not a drop-in fit. Check compatibility; many extensions/triggers/UDFs and traditional server admin tools **are unsupported**. Consider refactoring or staying on **Cloud SQL PostgreSQL** if those features are mandatory.

### Exercise C — Writing DDL

**Task:** Create a `products(id, name)` table with a PK using both GoogleSQL and the PostgreSQL dialect.

**Answer:**

~~~sql
-- GoogleSQL:
CREATE TABLE Products (ProductId INT64 NOT NULL, Name STRING(120))
PRIMARY KEY (ProductId);

-- PostgreSQL dialect (separate DB):
CREATE TABLE products (product_id BIGINT PRIMARY KEY, name VARCHAR(120));
~~~

### Exercise D — DDL Failure on NUMERIC(12,2)

A Spanner PostgreSQL database returns an error when creating **`price NUMERIC(12,2)`**.

**Answer:** Precision/scale modifiers on `NUMERIC` **are not supported in `CREATE TABLE` DDL**. Use **`NUMERIC`** and add appropriate validation/constraints; test how JDBC handles numeric types and precision before migration.

### Exercise E — Hotspot

A system doing 10,000 writes/s uses an ascending `OrderId`; CPU and latency spike despite abundant processing units.

**Answer:** Writes are likely concentrating at the tail of a key range. Inspect **Key Visualizer**, design UUID/distributed/bit-reversed IDs, and check timestamp-based secondary indexes and contention.

### Exercise F — JDBC and PGAdapter

A Java service connects to a Spanner PostgreSQL database using PostgreSQL JDBC via PGAdapter. When PGAdapter stops, the app cannot connect.

**Answer:** PGAdapter is a **required component** of the PostgreSQL wire path; restart the sidecar/process or evaluate switching to **direct Spanner JDBC** if the app/ORM fits. Never point PostgreSQL JDBC at the Spanner gRPC port assuming wire compatibility.

### Exercise G — IAM and Database Roles

The runtime holds **`roles/spanner.databaseUser`** even though it only needs `SELECT` on one table. Is this least privilege?

**Answer:** **No**; `databaseUser` grants broad rights including DDL changes. Design an **FGAC database role** with the needed `SELECT` plus IAM roles/conditions scoped to that role; test denial on other tables.

### Exercise H — Transaction Retry

Inside a read-write transaction callback, the app deducts a balance and calls an external payment API. Spanner returns **`ABORTED`**, and the client retries the callback.

**Answer:** The payment API may be called twice. Avoid external side effects inside auto-retried callbacks; use **idempotency keys, outbox tables, and post-commit actions**, and test retry paths.

### Exercise I — Performance Comparison

You observe PG JDBC + PGAdapter p95 = 80 ms, while direct Spanner JDBC p95 = 65 ms.

**Answer:** You cannot conclude "the PostgreSQL dialect is slower." You must benchmark the exact same database/query/indexes, payload, client location, pool settings, load, PGAdapter resources, and transaction mode; both dialects run on **the same engine**.

## 15. Summary and References

**Six principles:**

1. **GoogleSQL** and the **PostgreSQL interface** are two dialects on **the same Spanner engine**, chosen **per database**.
2. **The PostgreSQL interface is a subset with extensions**, not a PostgreSQL server; PGAdapter translates the wire protocol to Spanner.
3. **DDL, types, and parameter syntax differ**: `PRIMARY KEY` placement varies, and JSON/NUMERIC/time types require testing.
4. **PK/index design and transaction retries** govern scalability and correctness far more than the dialect name.
5. **Direct Spanner JDBC/client** fits native Spanner access, while **PostgreSQL JDBC + PGAdapter** lets you leverage PostgreSQL tooling.
6. Always account for **IAM/FGAC, region/leader, latency, monitoring, backups, and cost**—never assume portability eliminates migration effort.

**Official Google Cloud Documentation:**

1. [Choose GoogleSQL or PostgreSQL dialect](https://docs.cloud.google.com/spanner/docs/choose-googlesql-or-postgres).
2. [PostgreSQL interface overview and limitations](https://docs.cloud.google.com/spanner/docs/postgresql-interface).
3. [PostgreSQL language support](https://docs.cloud.google.com/spanner/docs/reference/postgresql/overview).
4. [PostgreSQL DDL reference](https://docs.cloud.google.com/spanner/docs/reference/postgresql/data-definition-language).
5. [PostgreSQL data types](https://docs.cloud.google.com/spanner/docs/reference/postgresql/data-types).
6. [GoogleSQL DDL reference](https://docs.cloud.google.com/spanner/docs/reference/standard-sql/data-definition-language).
7. [Create a database via gcloud](https://docs.cloud.google.com/spanner/docs/getting-started/gcloud).
8. [PGAdapter overview](https://docs.cloud.google.com/spanner/docs/pgadapter).
9. [Start PGAdapter](https://docs.cloud.google.com/spanner/docs/pgadapter-start).
10. [Spanner JDBC quickstart](https://docs.cloud.google.com/spanner/docs/getting-started/jdbc).
11. [Transactions](https://docs.cloud.google.com/spanner/docs/transactions).
12. [IAM roles and permissions](https://docs.cloud.google.com/iam/docs/roles-permissions/spanner).
13. [Fine-grained access control](https://docs.cloud.google.com/spanner/docs/configure-fgac).
14. [Regional/multi-region configurations](https://docs.cloud.google.com/spanner/docs/instance-configurations).
15. [System insights/monitoring](https://docs.cloud.google.com/spanner/docs/monitoring-console).
16. [Migrate PostgreSQL to Spanner](https://docs.cloud.google.com/spanner/docs/migrating-postgres-spanner).
