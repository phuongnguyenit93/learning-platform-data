# Read Replicas and Read/Write Splitting Strategies on Amazon RDS and Aurora

## Learning Objectives

After this lesson, learners will be able to:

- Explain **writer/primary**, **read replica/reader**, **replication lag**, **writer endpoint**, **reader endpoint**, and why read-heavy systems need read–write splitting.
- Distinguish **RDS DB instance read replicas**, **RDS Multi-AZ DB instance standbys**, **RDS Multi-AZ DB cluster readers**, and **Amazon Aurora Replicas**, avoiding confusing high availability with read scaling.
- Identify which flows require **read-after-write/strong consistency** and which tolerate **eventual consistency**, and choose the right endpoints and fallbacks accordingly.
- Understand asynchronous and semisynchronous replication, apply lag, SQL/CPU/I/O impacts, and the limits of adding replicas.
- Design explicit routing for **Java/Spring Boot/JDBC**, manage transactions and connection pools, and avoid mistaking `@Transactional(readOnly=true)` for automatic reader routing.
- Create/inspect an RDS read replica and inspect Aurora cluster endpoints via the AWS CLI, and diagnose lag, query timeouts, and failovers.
- Evaluate **Aurora failover, promotion, Multi-AZ, cross-Region replicas, Global Database, RDS Proxy**, and backups/restores against RTO/RPO.
- Use **VPC, IAM, TLS, AWS KMS, Secrets Manager, CloudWatch, and AWS Budgets** to protect data, monitor performance, and control costs.

**Context:** This lesson belongs to the **RDS and Aurora Databases** chapter of the **CLOUD_PROVIDERS_AWS** module. After learning Regions/AZs, IAM, VPC, compute, storage, databases, integration, and serverless, learners must know how to choose a database architecture that both resolves read bottlenecks and remains **secure, observable, resilient, and within budget**. Read replicas are an important tool, but they do not automatically solve data consistency or system-wide availability.

> **Scope:** Focused on **RDS for PostgreSQL/MySQL** and **Aurora PostgreSQL/MySQL**. Replica support, promotion, cross-Region options, metrics, engine versions, and instance classes vary by product and Region. All names, URLs, account IDs, ARNs, and commands in this lesson are for **lab** use; never modify production databases to test examples.

## 1. Why split reads and writes?

An e-commerce system has APIs for creating orders, managing inventory, and browsing product listings. During peak hours, suppose every second brings:

- 500 write operations for orders/payments;
- 5,000 read queries for catalogs, products, and history;
- several dashboard aggregation queries scanning millions of rows.

If everything hits the same RDS primary instance:

~~~mermaid
flowchart TB
    Web[Web / Mobile] --> API[Java API ECS / Lambda]
    Jobs[BI / Reporting] --> DB[(RDS Primary)]
    API --> DB
    DB --> CPU[CPU, connections, read I/O, locks]
~~~

SELECTs consume CPU, buffer cache, I/O, and connection slots; the writer must compete for resources with reporting queries. Scaling up the primary instance only helps up to a point, hits limits, and raises costs.

Read–write splitting offloads queries that **tolerate slightly stale data** to reader instances:

~~~mermaid
flowchart TB
    Client[Client] --> App[Java Application]
    App --> Rule{Operation / consistency}
    Rule -->|INSERT UPDATE DELETE| W[(Writer / Primary)]
    Rule -->|Reads needing fresh data| W
    Rule -->|Reads tolerating staleness| R1[(Reader A)]
    Rule -->|Reads tolerating staleness| R2[(Reader B)]
    W -. Replication .-> R1
    W -. Replication .-> R2
    R2 --> Report[Reporting workload]
~~~

**Not every SELECT goes to a reader.** Balance checks, inventory checks, authorization checks, in-flight transactions, and freshly written data typically need to read from the writer or a verified strong-consistency mechanism.

## 2. Terminology and three distinct architectural goals

| Concept | Meaning |
| --- | --- |
| **Primary/Writer** | DB instance or cluster member handling primary data mutations |
| **Read replica/Reader** | Read-serving copy updated from the writer via replication |
| **Replication lag** | Delay before a committed change on the writer becomes visible on a reader |
| **Read endpoint** | Address for read connections; on a cluster, selects a reader for new connections |
| **Writer/cluster endpoint** | Address pointing to the current writer, helpful when writer ownership shifts |
| **Instance endpoint** | Endpoint of a specific DB instance, not a permanent role alias |
| **Promotion** | Converting a replica into a standalone writer/DB per product mechanics |
| **Failover** | Switching service to another DB instance to restore availability |
| **RTO/RPO** | Recovery time objective / maximum acceptable data loss measured in time |

Three goals must be designed separately:

1. **Read scaling:** Distributing SELECTs across multiple instances to increase read capacity.
2. **High availability:** Automatically restoring service when a writer/instance/AZ fails.
3. **Data recovery/disaster recovery:** Recovering lost/accidentally deleted/corrupted data, or shifting Regions during a disaster.

**A read replica is not an HA standby, and neither replaces point-in-time recovery or backups.**

## 3. Traditional RDS DB instance read replicas

With an Amazon RDS DB instance read replica, RDS creates an **additional DB instance**, typically initialized from a snapshot of the source, and maintains **asynchronous replication** using the database engine's mechanism.

~~~mermaid
sequenceDiagram
    participant App as Java Application
    participant W as RDS Primary
    participant R as RDS Read Replica
    App->>W: INSERT order + COMMIT
    W-->>App: COMMIT OK
    W-->>R: Replicate asynchronously
    App->>R: SELECT order right after COMMIT
    R-->>App: May not see order yet
    Note over R: Apply changes completes
    App->>R: SELECT order later
    R-->>App: Sees order
~~~

Characteristics:

- The **source** is an eligible RDS DB instance; replicas require matching engine/version/backup prerequisites.
- A replica has its **own compute, storage/I/O, and endpoint**; you can pick a different DB instance class depending on engine/quotas.
- Changes are copied **asynchronously**, causing replica lag.
- Read replicas normally serve **read-only** SQL; some engines support alternative replica modes—check official docs.
- Applications must **explicitly route read queries** to replica endpoints; RDS does not automatically split SELECTs away from the primary.
- Multiple read replicas can be created within quotas, and cross-Region in supported cases.
- RDS does not automatically **scale traditional read replica counts up or down** by QPS by default.
- A replica can be **promoted** to a standalone DB instance where supported, but it does not automatically replace the primary on failure like a Multi-AZ standby.

### Why does lag occur?

- The writer produces WAL/binlog entries faster than the replica can receive/replay them.
- Replica CPU/I/O is underpowered or analytics queries saturate resources.
- Network disruptions occur, especially cross-Region.
- Long transactions, schema changes, large transactions, or insufficient disk/IO capacity.
- Engine replication slots/log retention, permissions, or replication status errors.

**Replication is an asynchronous pipeline:** a writer reporting commit success **does not prove** the reader has applied that record yet.

## 4. RDS Multi-AZ DB instance standby: HA, not read scaling

A common misconception: “Turning on Multi-AZ gives me another database to run SELECTs.”

**False for an RDS Multi-AZ DB instance deployment with one standby.**

~~~text
Primary (AZ A)  --synchronous replication-->  Standby (AZ B)
  Read + write                            Does not serve SQL reads
  Accepts app connections                 Ready for failover
~~~

The standby is managed by RDS to minimize downtime when the primary or AZ fails. **There is no reader endpoint to use that standby as a reporting DB.**

| Property | RDS Multi-AZ DB instance standby | Traditional RDS read replica |
| --- | --- | --- |
| Primary purpose | **High availability** | **Read scaling** and planned DR |
| Serves SELECTs | **No** | **Yes** |
| Replication | Synchronous per engine mechanism | **Asynchronous** |
| Automatic takeover on primary failure | **Yes** | **Not by default** |
| Application connects to | Primary endpoint | Separate replica endpoint |
| Risk of stale reads | Not used for reads | **Yes** |
| Cost | HA standby | Separate replica compute/storage |

You can combine an **RDS Multi-AZ primary instance + additional RDS read replicas** where supported by the engine, gaining both a standby for HA and read offloading for eligible queries.

## 5. RDS Multi-AZ DB cluster: two real readers

AWS also offers the **RDS Multi-AZ DB cluster**, distinct from the Multi-AZ DB instance standby model in Section 4.

Per current AWS documentation, the Multi-AZ DB cluster model is supported for **RDS MySQL/PostgreSQL** in eligible engine versions/Regions; the cluster has:

- **1 writer** and **2 readable reader instances** across three different Availability Zones.
- A **writer endpoint** and a **reader endpoint**.
- **Semisynchronous replication**: a transaction can commit once at least one reader acknowledges per the protocol; **it does not require every reader to have fully applied all records**.
- Automatic failover to an eligible reader if the writer fails.
- Readers both serve SELECTs and act as failover targets.

~~~mermaid
flowchart TB
    App[Java API] --> WE[Writer endpoint]
    App --> RE[Reader endpoint]
    subgraph C["RDS Multi-AZ DB cluster"]
      WE --> W[(Writer AZ A)]
      RE --> R1[(Reader AZ B)]
      RE --> R2[(Reader AZ C)]
      W -. Semisynchronous replication .-> R1
      W -. Semisynchronous replication .-> R2
    end
~~~

**Important:** Semisynchronous acknowledgment does not equal “every reader has applied the latest commit.” Reading from reader C immediately after a commit on writer A **can still see stale data**, depending on apply progress.

**Further distinction:** An additional **DB instance read replica** created off a Multi-AZ DB cluster (where supported) **differs** from the built-in cluster reader members: the external read replica receives changes asynchronously and is not an automatic cluster-member failover target.

## 6. Amazon Aurora Replicas: shared storage volume, still has replication lag

**Amazon Aurora** is a cluster architecture with:

- One **primary/writer DB instance** responsible for writes.
- Up to **15 Aurora Replicas** (readers) in supported configurations.
- Instances sharing a **logical Aurora cluster volume** protected across multiple Availability Zones.
- **Cluster writer endpoint**, **reader endpoint**, **instance endpoints**, and **custom endpoints**.
- Aurora can **promote an Aurora Replica** to writer when the primary fails.

~~~mermaid
flowchart TB
    App[Java API / Lambda] --> WE[Aurora writer endpoint]
    App --> RE[Aurora reader endpoint]
    WE --> W[(Writer AZ A)]
    RE --> R1[(Reader AZ B)]
    RE --> R2[(Reader AZ C)]
    W --> Volume[(Shared Aurora cluster volume across AZs)]
    R1 --> Volume
    R2 --> Volume
    W -. Reader state / log apply .-> R1
    W -. Reader state / log apply .-> R2
~~~

**Aurora Replicas do not maintain independent full copies of storage for each reader** like traditional RDS read replicas. Although they share the volume, each reader has its own compute/cache and must still reflect writer changes in its query state; therefore, **`AuroraReplicaLag` is not strictly zero at every moment**.

Aurora typically exhibits low lag, but heavy write loads, overloaded readers, engine/version factors, or incidents can raise lag. Never treat a marketed “a few milliseconds” figure as a consistency guarantee for payment applications.

### Aurora Replicas and failover priority

When the writer fails, Aurora can promote a reader based on **promotion tier** and actual health. Tiers range from 0 to 15, with **lower numbers prioritized first**. Placing a reader in another AZ improves recovery when an AZ goes down; apps still need reconnects, backoff, and write idempotency.

## 7. Choose the right model before writing routing code

| Goal | Candidate option | Decision point |
| --- | --- | --- |
| RDS primary overloaded by SELECTs | **RDS DB instance read replicas** | App routes to separate reader endpoints; lag applies |
| Want HA standby, no read scaling needed | **RDS Multi-AZ DB instance** | Standby is **non-readable** |
| Want HA and two readable members for MySQL/Postgres | **RDS Multi-AZ DB cluster** | 1 writer + 2 readers, semisync commit |
| Want many readers with shared cluster volume | **Aurora** | Up to 15 readers, cluster endpoints/failover |
| Want data closer to users in another Region | Cross-Region read replica / Aurora Global Database | Replication lag, DR routing, and data transfer fees |
| Analytics reports scanning huge datasets | Reporting replica or **Redshift/S3/Athena** | Keep BI from starving OLTP |
| Need a major increase in **write** TPS | Optimize writer/partitioning/sharding/architecture | Read replicas do not increase writer throughput |

**Before adding replicas:** Inspect slow query logs, indexes, query plans, N+1 queries, pagination, caching, transaction durations, and connection pools. A single unindexed SQL query can overload all 5 readers, not just the primary.

## 8. Endpoints: the connection address decides where traffic goes

### 8.1. Traditional RDS DB instances

Each primary/read replica has its **own DNS endpoint**:

~~~text
Writer:   orders-primary.abc123.ap-southeast-1.rds.amazonaws.com:5432
Reader A: orders-ro-a.def456.ap-southeast-1.rds.amazonaws.com:5432
Reader B: orders-ro-b.ghi789.ap-southeast-1.rds.amazonaws.com:5432
~~~

With ordinary RDS read replicas, **there is no built-in aggregated “reader endpoint” like Aurora**. The app or router must distribute queries by health/lag/weights or dedicate a replica to reporting.

### 8.2. Aurora and RDS Multi-AZ DB clusters

~~~text
Writer endpoint: orders.cluster-abc.ap-southeast-1.rds.amazonaws.com
Reader endpoint: orders.cluster-ro-abc.ap-southeast-1.rds.amazonaws.com
Instance endpoint: orders-reader-a.abc.ap-southeast-1.rds.amazonaws.com
~~~

- **Writer endpoint** points to the current writer; appropriate for DML, transactions, and critical reads.
- **Reader endpoint** typically distributes **new connections** across readers, **not individual SQL statements** on an open connection.
- **Instance endpoint** pins to a specific instance, useful for debugging; hardcoding it long-term prevents the app from following role changes after failover.
- **Aurora custom endpoints** can group readers for BI/reporting vs. OLTP where supported.

### 8.3. An important Aurora reader endpoint edge case

If an Aurora cluster has **no healthy Aurora Replicas**, the reader endpoint **can route connections to the primary**. In that situation, a session could have write capability if the DB user has write privileges. Therefore:

- **Do not treat the `-ro` hostname suffix as a write-protection boundary.**
- Use a **SELECT-only** DB user for read flows where appropriate.
- Send DML exclusively through the writer datasource and back it with integration tests.
- Monitor healthy reader counts and failover state.

### 8.4. DNS and connection reuse

Writer/reader endpoints are DNS names. During failover, the backing instance can change; **old TCP connections do not magically migrate to the new writer**. HikariCP/JDBC must discard failed connections, reopen them, pick up updated DNS, and retry with backoff.

With the reader endpoint, if a pool opens 30 connections at startup, those connections may distribute unevenly across replicas. **Do not assume the reader endpoint load-balances every query round-robin**; measure CPU, connections, and query latency on each instance.

## 9. Replication lag: the immediate post-POST example

~~~text
10:00:00.000  POST /orders → writer COMMIT order ORD-1001
10:00:00.050  GET /orders/ORD-1001 → read replica
10:00:00.050  Replica has not applied yet → 404 or stale status
10:00:00.300  Replica catches up
10:00:00.350  GET again → sees ORD-1001
~~~

This is a **read-after-write violation** in an eventual-read architecture, not necessarily data loss.

### Three consistency tiers to classify

| Requirement | Example | Approach |
| --- | --- | --- |
| Must see the commit just performed | Payments, balances, newly created order | **Read from writer** or a verified consistency mechanism |
| Tolerates up to a few seconds stale | Catalog listings, real-time dashboards | Reader with lag threshold, fallback, or pending state |
| Tolerates long staleness | Historical reports/BI | Reporting replica/warehouse with refresh schedule |

**HTTP GET does not equal eventual read.** A GET checking permissions, inventory, or payment status may require reading the latest state. A SELECT inside a writer transaction must also run on the appropriate database/connection to see required data and locks.

### Measuring lag accurately

- RDS DB instance read replica: CloudWatch metric **`ReplicaLag`**, typically in seconds, with engine-specific definitions.
- RDS Multi-AZ DB cluster: **`ReplicaLag`** reflects the delay applying changes on a reader member per product definition.
- Aurora: monitor **`AuroraReplicaLag`** per reader and corresponding cluster metrics like **`AuroraReplicaLagMaximum`** where supported.
- RDS `ReplicaLag=-1` can mean **lag is undetermined**, not better-than-zero lag.
- When the writer is idle, SQL `now() - pg_last_xact_replay_timestamp()` can grow or return NULL even when data is caught up. Do not use that formula as your sole SLO signal.

**Business requirements matter more than a single metric:** “99.9% of GETs right after payment must see confirmed status” is not guaranteed merely by a CloudWatch lag datapoint reading 0.

## 10. Six read-after-write and bounded staleness strategies

### A. Read from writer for sensitive requests

After a write command, route queries needing immediate visibility to the writer:

~~~text
POST /orders → writer
GET /orders/{id} right after create → writer
GET /catalog → reader
GET /reports/daily → reader
~~~

Pros: clear and easy to verify. Cons: the writer still handles some read load; that is a necessary trade-off for correctness.

### B. Session affinity or sticky writer reads

For a short window after a write, the same user/session is routed to the writer. Useful for UI flows, but **not an absolute guarantee**: replica lag can outlast the sticky window. Never rely solely on a sticky TTL for balances or inventory.

### C. Transaction token/position

Use a version, sequence, LSN, GTID, or commit position per engine to **wait until a replica has replayed up to that point**. Return from the reader only once confirmed; include a timeout and writer fallback.

This approach depends on PostgreSQL/MySQL/Aurora versions and engine APIs; **do not assume WAL LSN and GTID are directly interchangeable concepts**.

### D. Bounded staleness reads

Send queries to a reader only if health/lag meets a business-defined threshold, e.g., staleness ≤2 seconds. When a reader falls behind, critical queries go to the writer; noncritical queries can return cached data or 503.

Note that CloudWatch metrics are sampled and **do not prove individual transactions have replayed**, so metric-based bounded staleness is only a heuristic unless backed by commit-level verification.

### E. Caching with explicit TTL/invalidation

Use ElastiCache, CloudFront, or an application cache for catalog/reference data; monitor stale caches and ensure invalidation. Caching also involves consistency trade-offs and is not a “zero-lag replica.”

### F. Explicit asynchronous workflow

Rather than promising immediate visibility across all read models, the API returns:

~~~json
{
  "orderId": "ORD-1001",
  "status": "PROCESSING",
  "statusUrl": "/orders/ORD-1001"
}
~~~

The frontend displays a processing state and polls status via the writer/command store when needed. Reporting/read models update later via replication or events. This fits **lightweight CQRS**, while still requiring idempotency and clear contracts.

## 11. Read/write routing policy table for an e-commerce app

| Operation | Route | Reason |
| --- | --- | --- |
| `POST /orders`, `PUT /orders/{id}` | Writer | DML and transactions |
| `POST /payments/confirm` | Writer | Consistency-sensitive business decision |
| `GET /orders/{id}` right after POST | Writer | Read-your-writes |
| `GET /products?page=...` | Reader | Tolerates eventual consistency |
| Completed order history page | Reader if SLO permits | Offloads reads |
| Hourly revenue dashboard | Reader/reporting instance | Heavy aggregations |
| Check balance/inventory before UPDATE | Writer transaction | Needs locks/versioning |
| DDL/schema migrations | Writer | Controlled schema changes only |
| End-of-day reconciliation/report | Reader + writer verification | Reporting does not replace business truth |

**Do not route by parsing whether a SQL string starts with SELECT or UPDATE.** Stored procedures, locks, session states, and transactions are more complex than prefix matching. It is far better to **route by use case, service method, or transaction boundary**.

## 12. Java/Spring Boot: two explicit HikariCP pools

To avoid guessing SQL in a router, create two DataSources:

- `writerDataSource` for the writer/cluster endpoint.
- `readerDataSource` for the replica/reader endpoint.

Illustrative code with Java 21, Spring JDBC, HikariCP, and PostgreSQL:

~~~java
package com.example.orders.config;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class DbConfiguration {

    @Bean("writerDataSource")
    public DataSource writerDataSource() {
        return pool("ORDERS_WRITER_JDBC_URL",
                    "ORDERS_WRITER_USER",
                    "ORDERS_WRITER_PASSWORD", "orders-writer-pool");
    }

    @Bean("readerDataSource")
    public DataSource readerDataSource() {
        return pool("ORDERS_READER_JDBC_URL",
                    "ORDERS_READER_USER",
                    "ORDERS_READER_PASSWORD", "orders-reader-pool");
    }

    @Bean("writerJdbc")
    public JdbcTemplate writerJdbc(
        @Qualifier("writerDataSource") DataSource source) {
        return new JdbcTemplate(source);
    }

    @Bean("readerJdbc")
    public JdbcTemplate readerJdbc(
        @Qualifier("readerDataSource") DataSource source) {
        return new JdbcTemplate(source);
    }

    @Bean("writerTxManager")
    public PlatformTransactionManager writerTxManager(
        @Qualifier("writerDataSource") DataSource source) {
        return new DataSourceTransactionManager(source);
    }

    private static DataSource pool(String url, String user,
                                   String pass, String name) {
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl(required(url));
        config.setUsername(required(user));
        config.setPassword(required(pass));
        config.setPoolName(name);
        config.setMaximumPoolSize(10);
        config.setMinimumIdle(0);
        config.setConnectionTimeout(5000);
        return new HikariDataSource(config);
    }

    private static String required(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing env: " + key);
        }
        return value;
    }
}
~~~

Example endpoint config (sample only):

~~~text
ORDERS_WRITER_JDBC_URL=jdbc:postgresql://orders.cluster-abc.ap-southeast-1.rds.amazonaws.com:5432/orders?sslmode=verify-full
ORDERS_READER_JDBC_URL=jdbc:postgresql://orders.cluster-ro-abc.ap-southeast-1.rds.amazonaws.com:5432/orders?sslmode=verify-full
ORDERS_WRITER_USER=orders_rw
ORDERS_READER_USER=orders_ro
ORDERS_WRITER_PASSWORD=(inject-secret-for-lab)
ORDERS_READER_PASSWORD=(inject-secret-for-lab)
~~~

**Configuration notes:**

- On PostgreSQL JDBC, `sslmode=verify-full` requires the proper **RDS CA bundle/trust store**. Never disable hostname verification to “quickly fix” a certificate error.
- Env placeholders only illustrate wiring. Production should integrate **Secrets Manager/secret rotation or IAM DB authentication** per engine and driver; never commit passwords to repos or images.
- `maximumPoolSize(10)` is illustrative. 100 ECS tasks × 2 pools × 10 could require up to **2,000 DB connections**; compare against `max_connections` and reserve headroom for administration and replication.
- If using Spring Data JPA/Hibernate, configure **EntityManagerFactory and transaction managers per datasource**; do not assume a JDBC example solves all JPA mappings.

## 13. Java service: commands use writer, queries use reader

Create the schema on the **writer** via Flyway/Liquibase or approved migrations:

~~~sql
CREATE TABLE orders (
    order_id VARCHAR(64) PRIMARY KEY,
    customer_id VARCHAR(80) NOT NULL,
    status VARCHAR(24) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_orders_customer_created
    ON orders(customer_id, created_at DESC);
~~~

Service separating commands and queries:

~~~java
package com.example.orders.service;

import java.util.List;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private final JdbcTemplate writerJdbc;
    private final JdbcTemplate readerJdbc;

    public OrderService(
            @Qualifier("writerJdbc") JdbcTemplate writerJdbc,
            @Qualifier("readerJdbc") JdbcTemplate readerJdbc) {
        this.writerJdbc = writerJdbc;
        this.readerJdbc = readerJdbc;
    }

    @Transactional(transactionManager = "writerTxManager")
    public void createOrder(String id, String customerId) {
        writerJdbc.update(
            "INSERT INTO orders(order_id, customer_id, status) VALUES (?, ?, ?)",
            id, customerId, "CREATED"
        );
        // Production: business validation, idempotency,
        // transactional outbox, and authorization.
    }

    public OrderView getImmediatelyAfterWrite(String id) {
        // Needs read-your-writes: use the writer.
        return writerJdbc.queryForObject(
            "SELECT order_id, status FROM orders WHERE order_id = ?",
            (rs, n) -> new OrderView(rs.getString(1), rs.getString(2)),
            id
        );
    }

    public List<OrderView> listRecent(String customerId) {
        // This query tolerates eventual reads.
        return readerJdbc.query(
            "SELECT order_id, status FROM orders "
                + "WHERE customer_id = ? ORDER BY created_at DESC LIMIT 50",
            (rs, n) -> new OrderView(rs.getString(1), rs.getString(2)),
            customerId
        );
    }

    public record OrderView(String orderId, String status) {}
}
~~~

**What is right:** DML and critical reads use the writer; list views tolerating staleness use the reader. SQL uses **prepared parameters** instead of string concatenation.

**Still needed for production:** Transactional outbox, retry safety, idempotent creates, tenant authorization, timeouts/circuit breakers, secret rotation, failover handling, schema migrations, and monitoring.

## 14. `@Transactional(readOnly=true)` does not auto-route to a replica

The Spring annotation `@Transactional(readOnly = true)` provides a transaction hint/configuration to the ORM or transaction manager; **it does not automatically select an AWS RDS reader endpoint**.

~~~java
@Transactional(readOnly = true)
public OrderView getOrder(String id) {
    // Still reads from the writer because writerJdbc points to the writer pool.
    return writerJdbc.queryForObject(
        "SELECT order_id, status FROM orders WHERE order_id = ?",
        (rs, n) -> new OrderView(rs.getString(1), rs.getString(2)),
        id
    );
}
~~~

You can implement `AbstractRoutingDataSource` and route via a context such as `READ_EVENTUAL` / `READ_STRONG` / `WRITE`. However, note:

- The routing key must exist **before the JDBC connection is acquired**.
- If the transaction manager acquires a connection too early, `TransactionSynchronizationManager.isCurrentTransactionReadOnly()` may not yet reflect routing intent; `LazyConnectionDataSourceProxy` or custom interceptor design may be required.
- **Self-invocation** within the same class can bypass the Spring AOP proxy, preventing annotations from taking effect.
- **Nested transactions** must not arbitrarily swap physical database connections between writer and reader.
- **Open Session In View**, lazy loading, or JPA `EntityManager` may acquire connections at unexpected times.
- Integration tests are required to prove connections actually hit writer/reader as intended, including during failover.

**Safe way to learn:** Keep two explicit `JdbcTemplate`s/`DataSource`s until you have a strong reason and full test coverage to adopt dynamic routing.

## 15. Transaction consistency: never read a replica to decide a write

Anti-pattern:

~~~text
BEGIN transaction on writer
  SELECT inventory from reader      → sees 10 items
  UPDATE inventory on writer        → actually only 2 items remain
COMMIT
~~~

Reading from a reader happens on a separate database connection, **outside the transaction snapshot and locks** of the writer. Marking a Java method `@Transactional` does not create a distributed transaction across two DataSources.

For payments, inventory, and transfers:

1. Read current state from the **writer** inside the same proper transaction.
2. Use **row locks**, **optimistic versioning**, **conditional updates**, or the required isolation level.
3. Execute DML and commit atomically in the DB.
4. Record an idempotency key/unique constraint for safe retries.
5. Never use an eventually consistent reader to make decisions that could lose money or oversell inventory.

**Transaction isolation** and **replication lag** are two separate axes: isolation coordinates transactions within a database; replication lag measures how far behind the writer a reader is.

## 16. Reader endpoints distribute connections, not individual queries

A reader endpoint can distribute new TCP connections like this:

~~~text
Reader endpoint:
  connection 1 → Reader A
  connection 2 → Reader B
  connection 3 → Reader B
  connection 4 → Reader C

Every SELECT on connection 3 continues running on Reader B
until the connection is closed or replaced.
~~~

Consequences:

- **Too few pool connections:** may underutilize available readers.
- **Too many pool connections:** can exhaust connection slots/memory, especially during Lambda bursts or high ECS task counts.
- **Long-lived connections:** load distribution can skew as readers are added or removed.
- **Hardcoding instance endpoints:** connections fail to follow role changes after failover.
- **Long-running queries:** can saturate one reader even while other readers sit idle.

With Aurora, **custom endpoints** can group instances for BI/reporting where supported. With ordinary RDS replicas, you must build your own health-aware routing/load balancing or use a proxy/router supporting the engine/model.

## 17. Calculating read capacity and scale-out limits

Suppose 12,000 requests/second consist of:

- 20% writes/commands;
- 20% strong-consistency reads;
- 60% eventual-consistency reads.

Then:

\[
Q_{\text{writer}}=12{,}000\times 40\%=4{,}800\text{ req/s}
\]

\[
Q_{\text{readers}}=12{,}000\times 60\%=7{,}200\text{ req/s}
\]

If 3 readers share load roughly evenly:

\[
Q_{\text{per reader}}\approx 7{,}200/3=2{,}400\text{ req/s}
\]

**This is a traffic model, not a database benchmark.** Actual throughput depends on query cost, indexes, CPU, memory, IOPS, buffer cache, locks, and replication apply speed.

### When does adding readers help?

- The writer is bottlenecked on SELECTs/ReadIOPS, while the write path still has headroom.
- SELECTs can be routed to eventual readers.
- Query plans and indexes are reasonably optimized.
- The app has routing, sized connection pools, and real lag monitoring.

### When does adding readers NOT help?

- The writer is bottlenecked on **write latency/WriteIOPS/locks**.
- Most reads require strong consistency and still hit the writer.
- Unindexed SQL causes every reader to run massive scans.
- Business reporting should use an analytics pipeline/warehouse instead of OLTP replicas.
- Reader lag grows due to replication apply bottlenecks.

**To scale writes**, you need different strategies such as transaction/index optimization, partitioning, sharding, appropriate caching, or a different database architecture; read replicas do not become multi-writer merely by adding instances.
## 18. RDS Proxy: managing connections and aiding failover

**Amazon RDS Proxy** is a managed database connection proxy tier, useful when applications exhibit wide swings in connection counts, such as Lambda bursts or traffic-driven ECS scaling.

### What can RDS Proxy help with?

- Pooling/reusing database connections within protocol and transaction constraints.
- Reducing new connections hitting the DB directly when Lambda invocations spike.
- Helping applications reconnect and recover more smoothly during failover in many scenarios.
- Integrating Secrets Manager/IAM authentication where supported by engine/features.
- With **Aurora** and **RDS Multi-AZ DB clusters**, configuring a **read-only proxy endpoint** where supported, alongside the default read/write proxy endpoint.

~~~text
App writer pool → RDS Proxy default read/write endpoint → Writer
App reader pool → RDS Proxy READ_ONLY endpoint → Reader instances
~~~

**Do not assume every RDS Proxy has a read-only endpoint.** Check the engine and deployment type, and distinguish ordinary single RDS DB instances from Aurora/Multi-AZ DB clusters.

### What does RDS Proxy NOT replace?

- It does not update readers to eliminate lag.
- It does not make read-after-write strongly consistent when reading a replica.
- It does not automatically add Aurora Replicas or RDS read replicas as read QPS climbs.
- It does not replace authorization, business transactions, or backups.
- It does not guarantee query-level balancing when connections/sessions are **pinned**; temporary tables, session variables, long transactions, or protocol features can reduce multiplexing.

**Proper design:** Even with a proxy, keep a **writer/reader routing policy**, pool limits, lag alarms, idempotency, and rules for when fallback to the writer is permitted.

## 19. Failover: the app must reconnect and retry properly

### 19.1. Ordinary RDS read replica

When the source primary fails, **a traditional read replica does not automatically become the writer** like a Multi-AZ standby. A DR option is to **promote a read replica** via a controlled procedure, accepting potential un-replicated data loss (non-zero RPO) and switching the app to the new endpoint.

### 19.2. RDS Multi-AZ DB instance

When the primary or AZ fails, RDS can **automatically fail over to the standby**. The app reconnects via the DB endpoint once DNS/network updates; the standby was not previously used as a reader.

### 19.3. RDS Multi-AZ DB cluster

RDS reader members act as **automatic failover candidates**. Writer/reader endpoints help the app follow role changes. **Semisynchronous replication does not eliminate all read lag** on every reader.

### 19.4. Aurora cluster

Aurora can promote an Aurora Replica to writer. The cluster writer endpoint retains its DNS name while the **target instance changes**. The reader endpoint's available readers may also change.

~~~mermaid
sequenceDiagram
    participant App as Java / HikariCP
    participant DNS as Writer endpoint DNS
    participant Old as Old Writer
    participant New as Promoted Aurora Reader
    App->>DNS: Resolve endpoint
    DNS-->>App: Old writer IP
    App->>Old: Transaction COMMIT
    Note over Old: Instance / AZ failure
    Note over New: Aurora promotes reader to writer
    App->>Old: Existing JDBC connection fails
    DNS-->>App: New writer IP after failover
    App->>DNS: Resolve and open new connection
    App->>New: Retry safe operation
~~~

### Retries must not create duplicate writes

A dangerous scenario:

~~~text
Client → INSERT order ORD-501 → writer COMMIT OK
Network → response lost before client receives it
Client → assumes INSERT never happened, retries
~~~

If retries lack an **idempotency key/unique constraint**, you risk creating duplicate orders, sending duplicate emails, or double-charging.

**Mitigations:**

1. Assign a stable `orderId` or `Idempotency-Key` from the client/service.
2. Enforce DB unique constraints/conditional writes or transactional inbox/outbox.
3. Classify SQL errors before retrying, and **never automatically replay non-idempotent DML** when commit outcome is unknown.
4. Tune JDBC connection timeout, socket timeout, and Hikari fail-fast/connection validation for the workload.
5. Configure DNS caching so new connections resolve the updated writer endpoint after failover.
6. Practice real failovers in a lab and measure **RTO**, 5xx rates, pool recovery, and data reconciliation.

**Automatic failover does not mean in-flight requests will not fail.**

## 20. Cross-Region replicas and Aurora Global Database

To reduce read latency for users in other Regions or prepare for disaster recovery:

- RDS supports **cross-Region read replicas** for eligible engines/versions.
- Aurora offers **Aurora Global Database** with one primary Region and secondary Regions where supported.
- Secondary Regions can serve reads, but involve **cross-Region replication lag**, network latency, and dedicated failover/switchover procedures.

~~~mermaid
flowchart LR
    UserA[App Region A] --> Primary[(Writer Region A)]
    Primary -. Cross-Region replication .-> Secondary[(Reader Region B)]
    UserB[App Region B] --> Secondary
    Ops[DR Runbook] --> Fail[Switchover / Failover]
    Fail --> Secondary
~~~

**Do not assume secondaries are strongly consistent by default.** Writing in Region A and immediately reading in Region B can return stale data. Critical queries should route to the primary or use a supported, tested consistency mechanism.

### Write forwarding is a distinct feature

Some Aurora MySQL/PostgreSQL versions offer **local/global write forwarding** with consistency modes like `EVENTUAL`, `SESSION`, and `GLOBAL`, depending on engine and forwarding type. Stricter modes may wait for propagation and increase latency.

**You do not automatically get write forwarding just by using the reader endpoint**, nor should you assume ordinary RDS read replicas have an equivalent feature. Check engine/version parameters and documentation before using.

### DR requires more than a replica

A solid cross-Region plan requires:

- Quantified **RTO/RPO** targets.
- Routing DNS/APIs/clients to the DR Region.
- KMS encryption keys and secrets available in the DR Region as designed.
- Testing restore/failover and **fencing the old writer** so two independent writers never accept transactions simultaneously.
- Reconciling un-replicated data and communicating status to users.
- Budgeting for replication traffic, reader compute/storage, backups, logs, and database networking.

**Do not treat cross-Region replication as a point-in-time backup**; accidental deletes or bad updates can replicate to the other Region.

## 21. Backups, promotion, and data recovery

Read replicas continuously receive **all changes**, including destructive mistakes:

- An admin accidentally deletes orders.
- A migration corrupts data with a bad update.
- A compromised user/app runs unauthorized DML.
- A bug updates millions of rows incorrectly.

These changes propagate to replicas too. You need **automated backups, PITR, AWS Backup/manual snapshots, and restore tests** per policy.

| Mechanism | Primary problem solved | Does not fully solve |
| --- | --- | --- |
| Read replica | Read scaling, certain DR scenarios | Accidental deletes/corruption, read-after-write |
| Multi-AZ standby | HA on instance/AZ failure | SELECT scaling, PITR |
| Aurora readers | Read scaling + failover candidates | Data immutability, default strong reads |
| Automated backups/PITR | Restoring to a supported point in time | Instant failover, every RTO |
| Manual snapshot/AWS Backup | Scheduled/retained backups | Immediate availability |
| Cross-Region copy/Global Database | DR / regional reads | Zero-RPO guarantee across all failures |
| Application logical backup | Partial business-level recovery | Consistency, retention, and integrity management |

### When promoting an RDS read replica

**Execute only with administrative authorization and a DR runbook.**

1. Verify source, Region, engine, reader endpoint, and replication status.
2. Stop/fence write traffic to the old primary or confirm it can no longer accept writes.
3. Check `ReplicaLag` and assess un-replicated data; set RPO expectations.
4. If the source is still running and objectives permit, wait for the replica to catch up before promoting.
5. Check backup retention, instance parameter group, DB subnet group, SGs, and authentication.
6. Promote the replica via the supported API; monitor status until it becomes a standalone DB writer.
7. Update the writer JDBC URL/secret/pool, then test DML/SELECTs and the application.
8. Reconcile un-replicated transactions; never bring the old primary back as a parallel writer.
9. Execute a separate failback/migration plan.

Promotion **is not a command that can be automatically reversed without system impact**. Avoid running it in production just to practice.

## 22. Monitoring CloudWatch, Database Insights, and applications

CloudWatch namespace **`AWS/RDS`** provides metrics varying by engine/instance type.

| Metric | Signal | When to investigate |
| --- | --- | --- |
| **`ReplicaLag`** | Lag for RDS read replicas and some Multi-AZ readers | Exceeds SLO, climbs steadily, or unknown |
| **`AuroraReplicaLag`** | Lag for an Aurora reader instance | Reader applying slowly, stale reads |
| **`AuroraReplicaLagMaximum`** | Highest reader lag in an Aurora cluster where supported | One lagging reader causing instability |
| `CPUUtilization` | Writer/reader CPU pressure | Heavy reader queries or replica apply bottleneck |
| `DatabaseConnections` | Connection count | Oversized pools, nearing limits |
| `ReadIOPS` / `ReadLatency` | I/O serving SELECTs | Table scans, cache misses, or storage bottlenecks |
| `WriteIOPS` / `WriteLatency` | Write I/O | Writer bottleneck, log pressure |
| `FreeableMemory` | Memory pressure | Caches/maintenance/queries |
| `FreeStorageSpace` | Remaining storage per RDS type | WAL/binlog retention or storage full |
| `TransactionLogsDiskUsage` | WAL logs per engine/config | Replication slot retaining logs too long |
| Engine events/replication status | Replica errors/recovery/reconnects | Act early before data/availability loss |

**Note:** Not every metric appears for every engine, version, or instance class. Metric names, dimensions, units, and `-1` values must be checked against the documentation for your deployment model.

### Database performance insights

Depending on engine/Region support and **CloudWatch Database Insights/Performance Insights** features, inspect:

- Top SQL by DB load and query latency.
- Wait events: CPU, locks, I/O.
- Query plans and missing indexes.
- Long transactions and WAL/binlog lag.
- Memory/connection pressure when scaling out tasks.

### Application observability

Measure separately:

- p50/p95/p99 query latency for **writer vs. reader**.
- Ratio of queries routed to writer vs. reader.
- “POST succeeded then GET missed it” incidents.
- Count of writer fallbacks due to unhealthy/lagging readers.
- JDBC SQLSTATE, connection acquire timeouts, pool active/idle/pending counts.
- Business duplicate writes / transaction retries.
- Replication lag during peak traffic or failover.

**A `ReplicaLag=0` metric alone does not prove every GET after POST is always consistent.** Run integration tests for read-after-write to measure business SLOs.

## 23. Lag alerting and fallback without overloading the writer

Reference policy:

~~~text
Reader healthy when:
  DB instance available
  metrics/health probes updating
  lag below business threshold
  CPU and connection errors not persistently high

Reader degraded when:
  lag > 2s across consecutive samples
  or query latency/errors spike
  or reader in maintenance/failover

When degraded:
  critical reads -> writer
  optional reads -> cache/stale response or bounded wait
  reports -> backoff/pause
  monitor writer CPU/DBConnections to avoid crashing the writer
~~~

**This is an application policy, not an automatic RDS configuration setting.** CloudWatch sampling has latency, so real-time routing may need active health checks, circuit breakers, timeouts, and app metrics.

### Never unconditionally fall back all SELECTs

If a reader failure shifts 7,000 read QPS onto a writer already handling heavy writes, the writer can collapse and cause a larger outage. Prioritize by criticality:

- Critical reads → writer, with rate limits.
- Catalog/analytics → serve cache, or 503/429 with retry hints if SLO allows.
- BI jobs → pause temporarily.
- Protect write throughput and transaction availability before allowing additional fallback traffic.

**Graceful degradation matters more than “every request always returns 200.”**

## 24. VPC, IAM, Secrets Manager, KMS, and TLS

### VPC/Network

Production databases typically reside in **private subnets** inside a DB subnet group spanning multiple AZs per the model; applications need matching routes, DNS, and security groups:

- PostgreSQL: **TCP 5432**.
- MySQL: **TCP 3306**.
- RDS SG inbound allowed only from **ECS task SG, EC2 SG, Lambda VPC SG, or RDS Proxy SG**, never open to the Internet.
- NACLs/routes/DNS must allow valid forward and return traffic.
- If apps run on-premises, use VPN/Direct Connect or private networking along with DNS resolution.

### Encryption and authentication

- Enable **encryption at rest** with KMS per security requirements; verify KMS key policies and snapshot restore capability.
- Use **TLS** and verify server certificates/hostnames with the official CA bundle.
- Store passwords in **AWS Secrets Manager**; configure rotation and refresh credentials cleanly on connections.
- Consider **IAM database authentication** where supported by engine/instance/driver, using short-lived tokens; pools must refresh tokens safely.
- Separate DB users `orders_rw` and `orders_ro` with appropriate SQL GRANTs. Never rely solely on the reader endpoint to block DML.
- Scope application IAM permissions tightly: access only the needed secret, `rds-db:connect` if using IAM auth, and required AWS APIs.

| Principal | Permissions to review |
| --- | --- |
| Java ECS task role / Lambda execution role | Secrets Manager, KMS, IAM DB auth where applicable |
| SQL user `orders_rw` | INSERT/UPDATE/DELETE/SELECT needed for transactions |
| SQL user `orders_ro` | SELECT on permitted schemas/tables |
| DBA / schema migration role | DDL/maintenance per change process |
| Infrastructure operator | Describe/CreateReplica/Promote/Modify per change approval |
| KMS key administrators | Key policy/grants per scope and auditing |

**AWS IAM control-plane permissions do not equal database SQL GRANTs.** A task role with `rds:DescribeDBInstances` cannot read table rows; it still needs database authentication and SQL privileges.

## 25. Lab 1 — Create an RDS PostgreSQL read replica via AWS CLI

> **Cost and safety:** Creating a real replica incurs compute, storage, I/O, and backup charges. Only operate in an authorized lab account. Never create, promote, or delete production DBs or use customer data. Examples use Region `ap-southeast-1`, profile `lab`, and an existing source DB instance `orders-primary-lab` with matching engine/version and backup prerequisites.

### 25.1. Inspect the source

~~~bash
aws sts get-caller-identity --profile lab

aws rds describe-db-instances \
  --db-instance-identifier orders-primary-lab \
  --region ap-southeast-1 \
  --profile lab \
  --query 'DBInstances[0].{Id:DBInstanceIdentifier,Engine:Engine,Version:EngineVersion,Status:DBInstanceStatus,MultiAZ:MultiAZ,BackupRetention:BackupRetentionPeriod,Endpoint:Endpoint.Address}'
~~~

Confirm the source:

- Is an **RDS DB instance**, not confused with an Aurora DB cluster.
- Engine/version supports read replicas in the Region.
- Automated backup retention and prerequisites are satisfied.
- Instance class, network/SG, DB subnet group, encryption, and quotas qualify.
- Write workload is steady enough to create a replica without unintended impact.

### 25.2. Create the read replica

~~~bash
aws rds create-db-instance-read-replica \
  --db-instance-identifier orders-reader-lab \
  --source-db-instance-identifier orders-primary-lab \
  --db-instance-class db.t4g.medium \
  --no-publicly-accessible \
  --region ap-southeast-1 \
  --profile lab
~~~

**`db.t4g.medium` is only an example.** Verify engine/version/Region support for this class and that replica resources are sufficient for load and replication apply.

### 25.3. Verify endpoint and status

~~~bash
aws rds describe-db-instances \
  --db-instance-identifier orders-reader-lab \
  --region ap-southeast-1 \
  --profile lab \
  --query 'DBInstances[0].{Status:DBInstanceStatus,Source:ReadReplicaSourceDBInstanceIdentifier,Endpoint:Endpoint.Address,AZ:AvailabilityZone,Class:DBInstanceClass}'
~~~

Once `DBInstanceStatus=available`, inspect replication status and **`ReplicaLag`** in the RDS Console/CloudWatch. **An endpoint appearing does not mean the replica has caught up or is ready for production traffic.**

### 25.4. The application must route explicitly

Creating a read replica does not alter your Java JDBC URL. The app must add a **reader pool**, query routing, and consistency tests. Measure:

- Writer `CPUUtilization` and query latency before/after.
- Reader CPU/IO/connections.
- `ReplicaLag` across varying load states.
- Business GET-after-POST behavior.

## 26. Lab 2 — Inspect Aurora writer and reader endpoints

Assume a lab Aurora PostgreSQL cluster named `orders-aurora-lab` already has a writer and one reader.

### View cluster endpoints

~~~bash
aws rds describe-db-clusters \
  --db-cluster-identifier orders-aurora-lab \
  --region ap-southeast-1 \
  --profile lab \
  --query 'DBClusters[0].{Status:Status,WriterEndpoint:Endpoint,ReaderEndpoint:ReaderEndpoint,Members:DBClusterMembers}'
~~~

The `DBClusterMembers` field shows `IsClusterWriter` to identify the current writer and readers. If the reader endpoint exists while the cluster only has a healthy writer, revisit Section 8 before treating that endpoint as read-only.

### View individual DB instances

~~~bash
aws rds describe-db-instances \
  --region ap-southeast-1 \
  --profile lab \
  --query 'DBInstances[*].{Id:DBInstanceIdentifier,Cluster:DBClusterIdentifier,Status:DBInstanceStatus,AZ:AvailabilityZone,Endpoint:Endpoint.Address,Class:DBInstanceClass}'
~~~

Filter for `DBClusterIdentifier=orders-aurora-lab` in the output. Avoid mixing endpoints across clusters in a shared lab account.

### Create a new reader (if authorized in lab; incurs charges)

~~~bash
aws rds create-db-instance \
  --db-instance-identifier orders-aurora-reader-lab \
  --db-cluster-identifier orders-aurora-lab \
  --engine aurora-postgresql \
  --db-instance-class db.r6g.large \
  --no-publicly-accessible \
  --region ap-southeast-1 \
  --profile lab
~~~

**Check beforehand:** DB ID does not already exist, engine/class/version compatibility, Aurora Serverless vs. provisioned settings, and quotas. An Aurora reader is added by creating a **DB instance attached to the Aurora cluster**; do not confuse with `create-db-instance-read-replica` for ordinary RDS instances.

## 27. Lab 3 — Verify write privileges and data via SQL

### PostgreSQL / Aurora PostgreSQL

Connect separately to writer and reader via JDBC or `psql` and test:

~~~sql
-- PostgreSQL: check server recovery state where applicable.
SELECT pg_is_in_recovery();

-- Check read-only mode of the current transaction.
SHOW transaction_read_only;

-- Query business data:
SELECT order_id, status
FROM orders
WHERE order_id = 'ORD-1001';
~~~

On an RDS PostgreSQL physical replica, `pg_is_in_recovery()` can be useful. However, on Aurora or specialized features, **do not infer full consistency or cluster role from a single SQL function**; cross-check the endpoint, `IsClusterWriter`, and database user permissions.

Run on the **lab writer**:

~~~sql
INSERT INTO orders (order_id, customer_id, status)
VALUES ('ORD-LAB-100', 'C-LAB', 'CREATED');
~~~

Immediately after COMMIT, query the reader:

~~~sql
SELECT order_id, status
FROM orders
WHERE order_id = 'ORD-LAB-100';
~~~

You may see the row immediately or not yet depending on replica lag. **Seeing it once immediately does not prove strong consistency always holds.** Test under varied traffic, measuring lag and failure modes.

### MySQL/MariaDB (compatible engines/versions)

~~~sql
SELECT @@read_only, @@super_read_only;
SHOW REPLICA STATUS;
~~~

Older versions use `SHOW SLAVE STATUS`. This does not imply identical semantics on **Aurora shared storage**; use engine-specific replication monitoring rather than copying one SQL command across all databases.

### Be careful with the PostgreSQL lag formula

`now() - pg_last_xact_replay_timestamp()` can grow when the writer has no new changes even though the reader is caught up; never use a single result as an absolute lag SLO. Use CloudWatch replication metrics, WAL positions where needed, and business read-after-write tests.

## 28. Lab 4 — Testing degraded mode and failover

**Run only in a lab environment with backups; never run force failover on production.**

### A. Read scaling

1. Baseline writer query latency, CPU/IO, and connections.
2. Create a reader and shift part of `GET /products` eventual reads.
3. Run a bounded load test; measure writer/reader p95/p99 latency and `ReplicaLag`.
4. If overloaded, tune SQL/indexes before increasing instance counts.
5. Confirm critical reads still return fresh values via the writer.

### B. Lagging reader

1. Generate moderate write load on the lab writer.
2. Record commit timestamps and when the reader observes the records.
3. Raise alerts or mark the reader degraded when exceeding the SLO.
4. Fall back **critical reads** to the writer; pause heavy reporting.
5. Avoid dumping all read traffic onto the writer if it risks overloading the writer.

### C. Aurora writer failover

1. Record endpoints, `IsClusterWriter`, and app pool metrics beforehand.
2. Send a small transaction with an idempotency key.
3. Use AWS Console/CLI to **fail over only the lab cluster** when authorized.
4. Observe DNS refresh, stale JDBC connections, reconnects, and business retries.
5. Inspect cluster members after failover to verify writer/reader roles.
6. Check order counts and unique keys to verify zero duplicates.
7. Measure actual RTO and update the runbook.

### D. RDS promotion drill

1. Snapshot/back up mock data and note source/replica progress.
2. Stop writes to the source or fence the old primary.
3. Promote the read replica per supported engine, verifying write capability.
4. Switch the app writer pool to the new endpoint.
5. Check RPO/un-replicated data and reconcile.
6. Decommission/fence the old primary to prevent split-brain.

## 29. Architectures for real-world scenarios

### A. Order placement and inventory check API

**Writes and critical reads:** writer inside a transaction; use row locks/optimistic versioning/unique keys to check stock and idempotency. **Catalog and order history:** reader if staleness is acceptable. Include RDS Multi-AZ/Aurora failover + PITR, CloudWatch alerts, and tuned connection pools.

### B. Intraday operational dashboard

Use a reporting reader or dedicated read model. The dashboard tolerates 2–10 seconds of lag per SLA; never use it as the source of truth for billing decisions. For massive analytical scans, use ETL/S3/Athena/Redshift or engine materialized views to offload OLTP.

### C. Lambda bursts + Aurora

Lambda opens many database connections. Use **RDS Proxy** where supported: default proxy endpoint for commands/critical reads and read-only endpoint for eventual queries where supported. Cap concurrency/downstream connections, use secrets/IAM auth/TLS, and safe retries.

### D. Multi-Region application

Use cross-Region replicas or Aurora Global Database to serve eventual reads near users; route writes and read-after-write queries to the primary or a verified consistency mechanism. Maintain a DR/failover policy and never promise RPO=0 just because a secondary Region exists.

### E. Payment/reconciliation queries

Never route financial decision logic to an asynchronous reader. Use writer transactions/locking/unique constraints, backups/PITR, and auditing. Replicas should serve only reporting/historical views without strong consistency requirements.

## 30. Cost and choosing reader counts

### RDS DB instance read replica

Costs may include:

- DB instance-hours by class, engine, and license.
- Separate storage, IOPS/throughput, and backups/snapshots.
- Cross-Region replication/data transfer where applicable.
- RDS Proxy, Secrets Manager, KMS, logs, and Database Insights.
- Networking/VPC endpoints and operational management.

AWS does not charge for **replication data transfer between an RDS source and a read replica in the same AWS Region** where applicable; **do not assume this applies cross-Region**.

### Aurora Replicas

Aurora readers share the **cluster volume**, so you do not multiply full storage copies per Aurora Replica as with ordinary RDS replicas. However, you still incur compute instance/ACU charges plus storage/I/O/backup/network charges per Aurora Standard/I/O-Optimized/Serverless pricing.

| Option | Primary cost | Complexity | When to choose |
| --- | --- | --- | --- |
| Scale up writer instance | Larger instance class | Low | Primary CPU/IO constrained while queries are already tuned |
| Add 1 RDS reader | Reader compute + storage/I/O | Medium | Read-heavy with clear app routing |
| Multiple RDS readers | Multiple compute/storage instances | Higher | Heavy eventual reads with health-aware routing |
| RDS Multi-AZ DB cluster | Writer + 2 readers, cluster storage | Medium | HA + read scaling |
| Aurora + readers | Shared cluster volume + reader compute | Medium | Aurora HA/read scaling |
| Redis/ElastiCache cache | Cache compute/storage | Medium | Repeated catalog/reads where TTL fits |
| Analytics warehouse | ETL + analytics compute/storage | High | Heavy reporting/BI separated from OLTP |

**Do not buy a reader when a query only needs an index.** Measure cost per **1,000 successful read requests under latency/consistency SLOs**, using **AWS Pricing Calculator/Cost Explorer/Budgets** for your actual Region, class, and engine.

## 31. Troubleshooting: symptoms and root causes

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| POST succeeds then GET returns 404 | Reader has not applied commit yet | Route read-after-write to writer; check `ReplicaLag` |
| Slow read replica | Table scan, low CPU/IO, apply lag | EXPLAIN, Top SQL, CloudWatch |
| Writer still overloaded by reads | App not routing properly, too many strong reads | JDBC endpoints, per-pool metrics |
| Reader endpoint allows DML | Aurora has only writer / no healthy readers; broad DB account | Cluster members, read-only SQL user |
| Write fails with read-only error | DML routed to a reader | Service routing, DB endpoint, transaction |
| RDS standby cannot be read | Multi-AZ DB instance standby is HA-only | Check deployment type |
| RDS Multi-AZ DB cluster reader shows stale data | Semisync ACK does not equal apply | `ReplicaLag`, transactions |
| `ReplicaLag=-1` | AWS cannot determine lag | Check replica status/errors; do not treat -1 as healthy |
| `@Transactional(readOnly=true)` still hits writer | No router or connection acquired too early | `RoutingDataSource`, TX timing, `LazyConnectionDataSourceProxy` |
| Uneven CPU across Aurora reader instances | Reader endpoint balances connections, pool pinning | `DBConnections`, Hikari lifetime |
| App still fails after failover | DNS caching, stale TCP/JDBC pool, bad retries | RDS events, connection validation, DNS TTL |
| Retries create duplicate orders | Unknown commit outcome, missing idempotency | Unique keys, transaction/outbox |
| Creating replica fails | Engine/version/class/backup prerequisites or quota | RDS API error, source config |
| Replica enters replication-error | Log retention/WAL/binlog/network, apply error | RDS Events, replica status |
| Cross-Region reader returns stale data | Replication delay | Global/cross-Region lag metrics |
| Lambda floods DB connections | High concurrency, missing pool/proxy | RDS Proxy, `max_connections`, Lambda concurrency |
| Cannot connect | SG/NACL/route/DNS/TLS, DB auth | VPC/Flow Logs, DB endpoint, KMS |
| Snapshot restore insufficient | PITR/backup untested, wrong retention | Backup/restore drills, RTO/RPO |
| Costs climbing | Underused reader instances, cross-Region/proxy/logs | Cost Explorer, tags, reader utilization |

### Layered investigation workflow

~~~text
1. Identify account, Region, engine/version, and deployment type.
2. Distinguish RDS instance replica / Multi-AZ standby / cluster readers / Aurora.
3. Inspect actual writer/reader endpoints, IsClusterWriter, and JDBC URLs/pools.
4. Reproduce read-after-write, logging orderId/eventId and commit timestamps.
5. Compare ReplicaLag/AuroraReplicaLag + CPU/IO/connections per instance.
6. Check query plans/indexes, transaction durations, WAL/binlogs, and locks.
7. If connection errors: check SG/VPC/DNS/TLS/RDS Proxy/Hikari/JVM caching.
8. If failover: check RDS events, DNS, retries/idempotency, and data reconciliation.
9. If DR: check backup/PITR/replication lag, restore/protection, and budget.
10. Fix one root cause at a time, then test happy path + stale/failure paths.
~~~

**Never “fix” issues by:** disabling TLS, opening SGs to the entire Internet, giving the app a DB superuser, skipping backups, or dumping all read QPS onto the writer regardless of capacity.

## 32. Exercises and self-check questions

### Exercise 1 — Multi-AZ without a reader

An RDS PostgreSQL system has **Multi-AZ DB instance** enabled with a standby in AZ B. The dev team wants to shift 5,000 read QPS to the standby.

**Task:** Explain why this is impossible. Propose adding an RDS read replica, switching to a Multi-AZ DB cluster, or Aurora depending on HA/read-scale needs, comparing latency and application changes.

### Exercise 2 — Read-after-write

The frontend POSTs to create ORD-9 (returns 201), then an immediate GET from a replica returns 404 for ~300 ms. Identify the cause and two fixes; distinguish a sticky writer window from a writer guarantee.

### Exercise 3 — Pool connections

There are 80 ECS tasks, each creating a writer pool of up to 12 connections and a reader pool of up to 20 connections.

\[
80\times(12+20)=2{,}560\text{ connections}
\]

If writer capacity is only 400 connections and two readers each support 500, describe potential failures and how to optimize pool sizes, task autoscaling, proxies, and connection lifetimes.

### Exercise 4 — Aurora endpoint failover

Aurora has writer A and readers B/C. B fails, and C is promoted to writer when A fails. Predict how writer/reader endpoints route, what happens to old JDBC connections, and the risk of the reader endpoint pointing to the writer if no healthy readers remain.

### Exercise 5 — Semisynchronous commit

RDS Multi-AZ DB cluster writer A receives acknowledgment from reader B while C has not finished applying. Can stale data be read from C? Why doesn't semisynchronous replication guarantee read-your-writes? Propose routing for financial vs. dashboard flows.

### Exercise 6 — High replica lag

Replica CPU is 95%, p99 SELECT latency is 6 seconds, `ReplicaLag` is 8 seconds, while writer CPU is only 45%.

**Task:** Propose an investigation order covering top SQL/indexes, reader instance class, reporting jobs, connections, and replication apply. If the read service falls back to the writer, how do you avoid overloading the writer?

### Exercise 7 — DR promotion

The source RDS PostgreSQL in Region A fails; the read replica in Region B reports 30 seconds of lag. The team wants to promote it and accept writes.

Describe potential RPO, backups, fencing the old writer/preventing split-brain, cross-Region secrets/KMS, DNS/connection routing, un-replicated data, and reconciliation.

### Exercise 8 — Broken transaction

~~~java
@Transactional
public void approvePayment(long orderId) {
    Order order = readRepository.findById(orderId);
    writeRepository.markPaid(orderId);
}
~~~

If `readRepository` points to a lagging replica, describe the race condition; redesign the writer transaction with versioning/locks and idempotency. Why doesn't Spring `@Transactional` create an atomic transaction across two DataSources?

### Exercise 9 — Cost

You have 1 RDS writer, 4 same-Region replicas, 1 cross-Region DR replica, and 2 RDS Proxies. After caching the catalog, read QPS drops by 70%.

Build a cost model covering compute/storage/I/O/transfer/proxy/cache/backups/monitoring, select which readers can be scaled down without breaking HA/DR, and measure outcomes against latency SLOs.

### Short questions

1. **Is an RDS DB instance read replica synchronous or asynchronous?** Primarily asynchronous.
2. **Can an RDS Multi-AZ DB instance standby serve reads?** No.
3. **How many reader members does an RDS Multi-AZ DB cluster normally have?** Two.
4. **Does an Aurora Replica have its own full storage copy?** No; shared logical cluster volume.
5. **What is the maximum number of Aurora Replicas in a standard model?** 15 per published limits.
6. **Does the Aurora reader endpoint balance per query or per connection?** Per new connection.
7. **Can the Aurora reader endpoint route to the writer?** Yes, if no healthy readers remain.
8. **Does `ReplicaLag=0` guarantee every GET after POST sees data immediately?** Not a transaction-level guarantee.
9. **Does `@Transactional(readOnly=true)` automatically change the JDBC URL?** No.
10. **Should you use a replica to check inventory inside a writer transaction?** No.
11. **Does an ordinary RDS read replica automatically become writer when the source fails?** Not by default.
12. **Does automatic Aurora failover still require client reconnection?** Yes.
13. **Does RDS Proxy eliminate replication lag?** No.
14. **Does adding read replicas directly increase write capacity?** No.
15. **Do replicas replace backups/PITR?** No.
16. **Are cross-Region readers always strongly consistent?** No.
17. **Is a read endpoint an absolute SQL read-only security layer?** No.
18. **What should you measure during failover?** RTO/RPO, error rates, connection recovery, and idempotency/data integrity.

## 33. Pre-production checklist

- [ ] Correctly identified RDS DB instance, Multi-AZ DB instance, Multi-AZ DB cluster, and Aurora cluster.
- [ ] Clearly understood that HA standbys do not serve reads, read replicas have lag, and cluster readers can fail over.
- [ ] Classified each use case by strong / read-after-write / eventual consistency.
- [ ] Routed writes, transaction checks, authorization/inventory/balance checks, and critical reads to the writer.
- [ ] Routed reporting/catalog eventual reads to replicas using the right reader endpoint/instance URL for the model.
- [ ] Did not assume the Aurora reader endpoint performs query-level balancing or always blocks writes.
- [ ] Implemented dedicated health/routing for ordinary RDS replicas instead of assuming a cluster reader endpoint.
- [ ] Integration-tested Java JDBC/Hikari/JPA transaction managers with both pools.
- [ ] Checked connection acquisition timing, proxy order, and `LazyConnectionDataSourceProxy` if routing by annotations/AOP.
- [ ] Implemented idempotency and unique keys for writes in case failover/network timeouts leave commit outcomes unknown.
- [ ] Tracked `ReplicaLag`/`AuroraReplicaLag`, CPU/I/O, `DBConnections`, and p95/p99 SQL/app metrics.
- [ ] Set SLOs for stale reads and rate-limited fallbacks so the writer is not overloaded.
- [ ] Optimized query plans, indexes, pagination, caching, and long transactions before scaling out.
- [ ] Distributed Multi-AZ/Aurora readers across AZs, configured failover promotion tiers, and verified app DNS/reconnects.
- [ ] Configured RDS Proxy per engine/cluster support, using reader proxy endpoints only where supported.
- [ ] Locked down VPC private subnets/SGs/TLS/Secrets Manager/KMS/IAM DB auth.
- [ ] Tested backups/PITR/snapshots and restore drills independently of read replicas.
- [ ] Documented DR/failover/fencing, RTO/RPO, and reconciliation for Cross-Region/Global Database.
- [ ] Built reader health dashboards and runbooks for replication lag, stale reads, and JDBC failover.
- [ ] Enforced IaC/change reviews and tested schema migrations for writer/replica compatibility.
- [ ] Estimated costs for instances/storage/I/O/cross-Region/proxy/cache/logs/backups.
- [ ] Configured AWS Budgets, tags, and safe scale-down/cleanup procedures.
- [ ] Practiced failure drills: reader down, writer failover, stale DNS, high lag, DB restore, and data integrity checks.

## 34. Summary

**Read replicas** increase read capacity by offloading SELECTs that **tolerate brief data staleness** away from the primary. However, effectiveness depends on **application routing, connection pooling, database engine, and replication lag**.

Four models to distinguish:

1. **RDS DB instance read replica:** asynchronous replication, separate endpoint, scales read capacity and supports planned promotion; **not an automatic failover standby**.
2. **RDS Multi-AZ DB instance standby:** HA/failover only; **does not serve SELECTs**.
3. **RDS Multi-AZ DB cluster:** writer + two readable readers, semisynchronous replication, and automatic failover; readers can still experience apply lag.
4. **Amazon Aurora:** writer and up to 15 readers sharing a logical cluster volume, cluster writer/reader endpoints, and automatic failover; **the reader endpoint balances connections, not individual SQL queries**.

In Java, a sound starting point is **two explicit connection pools**: a writer pool for commands, transactions, and critical reads, and a reader pool for eventual reads. Combine **idempotency, transaction isolation, lag/health monitoring, IAM/KMS/VPC/TLS, backups/restores, RDS Proxy where appropriate, and AWS Budgets** to scale reads while safeguarding data.

### Official documentation

- [Working with RDS DB instance read replicas](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_ReadRepl.html)
- [Creating RDS read replicas](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_ReadRepl.Create.html)
- [Monitoring RDS read replication](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_ReadRepl.Monitoring.html)
- [RDS Multi-AZ DB instance deployments](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Concepts.MultiAZSingleStandby.html)
- [RDS Multi-AZ DB cluster deployments](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/multi-az-db-clusters-concepts.html)
- [RDS Multi-AZ DB cluster read replicas](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_MultiAZDBCluster_ReadRepl.html)
- [RDS Multi-AZ DB cluster endpoints](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/multi-az-db-clusters-concepts-connection-management.html)
- [Aurora DB clusters](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Overview.html)
- [Aurora Replication](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Replication.html)
- [Aurora reader endpoints](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Endpoints.Reader.html)
- [Aurora cluster endpoints](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Overview.Endpoints.html)
- [Aurora failover](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-failover.html)
- [Aurora Global Database](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-global-database.html)
- [Aurora write forwarding consistency](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-mysql-write-forwarding-consistency.html)
- [RDS Proxy endpoints for Aurora](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/rds-proxy-endpoints.html)
- [Amazon RDS CloudWatch metrics](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-metrics.html)
- [RDS Pricing](https://aws.amazon.com/rds/pricing/) and [Aurora Pricing](https://aws.amazon.com/rds/aurora/pricing/)
- [AWS CLI RDS command reference](https://docs.aws.amazon.com/cli/latest/reference/rds/)

**Operational note:** Engine/version models, replica limits, endpoint behavior, metrics, quotas, and pricing can change by Region, account, and over time. Cross-check the latest AWS documentation, test consistency against business requirements, and rehearse failovers/restores in a lab before deploying to production.
