# Spanner and Choosing a Distributed Relational Database

An e-commerce platform runs Java services on Cloud Run, GKE, and Compute Engine. With a single region and moderate transaction volume, Cloud SQL or AlloyDB can serve it well. However, when the application requires **a consistent relational database, concurrent writes across multiple servers, horizontal scalability, and availability across multiple geographic regions**, the team must consider **Google Cloud Spanner**.

**Spanner** is a managed distributed database service that combines **tables/SQL, ACID transactions, and strong consistency** with data distribution and replication across multiple machines. It is not "Cloud SQL with a few extra read replicas": its primary key model, transactions, replica geography, SQL compatibility, latency, and cost are all different.

This lesson belongs to the **Spanner** chapter of the `CLOUD_PROVIDERS_GCP` module, connecting storage decisions with project/IAM/VPC governance, application deployment, release automation, reliability monitoring, and cost control. Examples use the **GoogleSQL dialect**, Java 21, and a lab project; places where the PostgreSQL dialect is used will be noted explicitly.

## Learning Objectives

After this lesson, you will be able to:

1. Explain Spanner as a **distributed relational database** and distinguish it from Cloud SQL/AlloyDB.
2. Describe instances, databases, splits, replicas, leaders, and **regional/dual-region/multi-region** configurations.
3. Understand **ACID, serializable/external consistency**, strong reads, stale reads, and aborted transactions.
4. Choose primary keys that avoid hotspots, and organize relationships and secondary indexes appropriately.
5. Distinguish between the **GoogleSQL** and **PostgreSQL dialects**, including compatibility limitations.
6. Determine when to choose Spanner, Cloud SQL, AlloyDB, Firestore, or Bigtable based on the workload.
7. Create a lab database with `gcloud`, run SQL, and understand a Java transaction example.
8. Evaluate IAM, capacity, performance, security, backups, and cost before going to production.

## 1. From Traditional Relational Databases to Spanner

A typical RDBMS has tables, primary keys, indexes, joins, and transactions. As data grows rapidly, teams often have to **scale up machine specs, add read replicas, or shard manually**. Manual sharding pushes routing, cross-shard transactions, rebalancing, and failure recovery onto the application layer.

Spanner distributes data by **key ranges (splits)**, automatically manages multiple replicas, and provides SQL/transactions through a unified service.

~~~mermaid
flowchart LR
    API["Java services<br/>Cloud Run / GKE / VM"] --> CLIENT["Spanner client library<br/>sessions / RPC"]
    CLIENT --> DB["Spanner database<br/>Orders, Customers, Payments"]
    DB --> S1["Split: key range A"]
    DB --> S2["Split: key range B"]
    DB --> S3["Split: key range C"]
    S1 --> R["Replicated storage + consensus"]
    S2 --> R
    S3 --> R
~~~

| Concept | Meaning |
| --- | --- |
| **Instance** | Geographic configuration, edition, compute capacity; contains multiple databases |
| **Database** | Tables, indexes, schemas, and data; choose **one SQL dialect** at creation |
| **Split** | A contiguous key-ordered range of data that can automatically split/move to balance load |
| **Replica** | A copy of data in a location belonging to the instance configuration |
| **Leader** | The component coordinating writes and consensus for the corresponding data |
| **Processing units (PU)** | Unit of compute allocation; **1 node = 1,000 PU** |
| **GoogleSQL/PostgreSQL dialect** | Two SQL syntaxes supported by Spanner, not two independent storage engines |

**Key point:** Spanner solves many data distribution problems at the service layer, **but poor schemas and queries still cause hotspots, transaction aborts, or high costs**.

## 2. Distributed Architecture and Availability

Spanner automatically replicates data synchronously according to the instance topology. With a **basic regional configuration**, data is replicated across **three read-write replicas in different zones within the same region**. When one zone is lost, the remaining replicas can maintain service subject to quorum/availability conditions.

~~~mermaid
flowchart TD
    APP["Application / Spanner API"] --> SP["Spanner instance: regional-asia-southeast1"]
    SP --> A["Replica A<br/>Zone 1"]
    SP --> B["Replica B<br/>Zone 2"]
    SP --> C["Replica C<br/>Zone 3"]
    A <-->|"Consensus/replication"| B
    B <-->|"Consensus/replication"| C
~~~

In a **multi-region** configuration, Spanner distributes replicas across multiple regions and uses a consensus mechanism to maintain consistency. Write transactions must coordinate across replicas, so **write latency can increase** when the leader/quorum is far from the application; remote strong reads also incur some network/latency overhead.

### 2.1. Three Deployment Scopes

| Configuration | Geographic Scope | Choices / Trade-offs |
| --- | --- | --- |
| **Regional** | Multiple zones in **one region** | Usually offers the lowest write latency when the application is nearby; does not protect against all region-wide outages |
| **Dual-region** | **Two regions within the same country**, per supported configurations | Cross-region availability with higher latency/cost; requires **Enterprise Plus** |
| **Multi-region** | Multiple regions per available topologies | Suitable for geographically wide apps / high HA; requires **Enterprise Plus**, leader selection, and write latency consideration |

**Do not assume multi-region means every data row always has an independent primary in every region.** Topology determines replica/leader placement and transaction paths. If you require placing **specific groups of data in separate regions**, Spanner offers **geo-partitioning** in Enterprise Plus under specific feature states/support; it requires dedicated schema design and compliance configuration, and is not enabled automatically just by choosing multi-region.

### 2.2. Availability Does Not Mean Zero Outage

Spanner offers SLAs depending on **edition and configuration**: Standard/Enterprise regional configurations publish **99.99%**, while Enterprise Plus multi-region can reach **up to 99.999%** when conditions are met. This is a **conditional SLA**, not a guarantee that every query is error-free. Applications still need timeouts, retry/backoff, latency monitoring, and recovery runbooks.

## 3. Why Is Spanner Still a Relational Database?

Spanner provides:

- **Typed schemas** and **primary keys**.
- SQL for `SELECT`, `JOIN`, aggregations, filtering, and sorting.
- **Indexes** and relationships via **foreign keys/interleaved tables** depending on dialect/features.
- **ACID transactions**, including modifying multiple rows/tables within a database.
- **Strong reads**, snapshot read-only transactions, and **stale reads** when allowed by the application.

Do not call Spanner a NoSQL database just because its data is sharded. The difference from traditional relational systems lies in **how data is distributed and how transactions are coordinated**.

### 3.1. A Transaction Can Span Multiple Splits

Suppose two accounts exist in the `Accounts` table and you need to transfer 100,000 VND from A to B. With a Spanner read-write transaction, both updates can commit **atomically** even if the rows reside on different splits. The application does not need to implement its own two-phase commit across sharded databases.

**Limitation:** if the transaction also calls external systems (Pub/Sub publish, sending email, payment API), that side effect **is not part of the same Spanner transaction**. Use a transactional outbox, idempotency key, or reconciliation when cross-system consistency is needed.

## 4. Strong Consistency, Serializability, and External Consistency

Spanner uses **serializable isolation** by default for read-write transactions, ensuring committed transactions appear as if executed in a valid serial order. With **external consistency**, the commit order also respects real-time ordering: if transaction A completes before B begins, B cannot observe a nonsensical reversed order.

Spanner coordinates **TrueTime**, commit timestamps, and consensus to provide this property. This is why the service can support distributed transactions while maintaining strong consistency.

| Access Type | When to Use |
| --- | --- |
| **Read-write transaction** | Money transfers, inventory reservations, state changes across multiple rows/tables requiring atomicity |
| **Strong read** | Reading the latest consistent data per consistency guarantees after writes complete |
| **Read-only transaction** | Reading multiple tables on the **same consistent snapshot**, without write locks |
| **Stale read** | Reports/cached views accepting older data to optimize latency/capacity as appropriate |
| **Repeatable read isolation** | Supported with distinct semantics; do not assume it is equivalent to the default serializable isolation |

**Do not use stale reads** to verify whether an account balance is sufficient for payment or to check current inventory when business logic requires the latest data.

### 4.1. Transaction ABORTED and Automatic Retry

Two concurrent transactions modifying the same data can conflict. Spanner may abort a transaction; the client library typically **reruns the callback** inside the transaction runner.

~~~mermaid
sequenceDiagram
    participant C as Java client
    participant S as Spanner
    C->>S: Transaction callback attempt 1
    S-->>C: ABORTED (conflict)
    C->>S: Client library retry callback
    S-->>C: COMMIT succeeded
~~~

Because the callback **may run multiple times**, **do not send emails, process payments, or publish to Pub/Sub directly inside the callback** without idempotency. Keep transactions short and perform external side effects after commit via an outbox/reliable relay.

## 5. Choosing GoogleSQL or PostgreSQL Dialect?

**The dialect is chosen when creating the database**, and changing the dialect cannot be treated as a routine `ALTER DATABASE` statement.

| Criterion | GoogleSQL | PostgreSQL Dialect |
| --- | --- | --- |
| Language | Spanner's GoogleSQL syntax | A PostgreSQL-compatible subset/semantics supported by Spanner |
| Java integration | Spanner Java client, GoogleSQL DDL/SQL | Spanner Java client or PGAdapter/JDBC tools where supported |
| Data types / syntax | `STRING`, `INT64`, `PRIMARY KEY (...)` DDL outside table definition | `varchar/text`, `bigint`, more familiar SQL types |
| Suitable applications | Teams comfortable with Spanner-native syntax | Teams familiar with PostgreSQL looking to reduce syntax learning curve |
| PostgreSQL engine compatibility | **No** | **Not a full PostgreSQL server** |

**PostgreSQL dialect ≠ Cloud SQL for PostgreSQL**. Spanner does not automatically support every PostgreSQL extension, stored procedure, trigger, catalog, driver, or engine administration behavior. **PGAdapter** allows certain PostgreSQL tools to connect over the wire protocol, but you must still check the **compatibility matrix, DDL, and query semantics** before migrating.

Both dialects share the same Spanner core for transactions, replication, and scalability. **Do not choose the PostgreSQL dialect merely expecting to lift-and-shift a PostgreSQL workload without modifying SQL/schema.**

## 6. Primary Key Design Determines Scalability

Spanner orders data by **primary key** and partitions it into key ranges. If all inserts hit the "tail" of a monotonically increasing key sequence, they can pile onto a single split, creating a **hotspot** even when the overall instance still has spare compute.

### 6.1. Poor Example

~~~sql
-- GoogleSQL. Not recommended for tables with very high inserts per second.
CREATE TABLE Events (
  CreatedAt TIMESTAMP NOT NULL,
  EventId STRING(36) NOT NULL,
  Payload STRING(MAX)
) PRIMARY KEY (CreatedAt, EventId);
~~~

Ascending timestamps at the start of the key create a **hot range**. Similarly, an ascending sequence leading `OrderId` can also cause a bottleneck.

### 6.2. Better Example for Orders

~~~sql
-- GoogleSQL, assuming OrderId is a string UUID v4.
CREATE TABLE Orders (
  OrderId STRING(36) NOT NULL,
  CustomerId STRING(36) NOT NULL,
  TotalCents INT64 NOT NULL,
  Status STRING(20) NOT NULL
) PRIMARY KEY (OrderId);
~~~

A **well-distributed UUID v4** `OrderId` helps spread inserts more evenly. For multi-tenant workloads, `(TenantId, OrderId)` can improve locality, **however** an extremely large tenant can cause a hotspot; analyze access patterns and consider adding a hash/shard prefix if needed.

| Key Strategy | Benefit | Trade-off |
| --- | --- | --- |
| UUID v4 / random keys | Prevents all inserts from landing in one key range | Time-based reads require another index/query |
| Hash prefix / shard ID | Proactively distributes write load | Querying across all shards is more complex |
| Composite key by tenant | Locality for queries within a tenant | Large tenants can become too hot |
| Ascending timestamp as prefix | Easy to scan by time | High risk of **hotspot** with continuous writes |

### 6.3. Secondary Indexes Can Also Hotspot

An index whose key starts with a monotonically increasing timestamp can also concentrate writes at the end of the index, even if the **base table** uses UUID v4. Only create indexes for queries that genuinely need them; evaluate **write amplification, storage**, and key ordering.

~~~sql
-- Index for filtering orders by customer.
CREATE INDEX OrdersByCustomer
ON Orders(CustomerId)
STORING (Status, TotalCents);
~~~

A secondary index incurs **write and storage overhead**; `STORING` increases index data size to reduce lookups back to the base table. Do not create dozens of indexes based on guesswork.

## 7. Data Relationships, Foreign Keys, and Interleaving

Spanner provides **foreign keys** to enforce referential integrity and **interleaved tables** to store child rows physically near parent rows when the schema makes sense.

For example, `Customers` and `Orders`:

- **Foreign key:** ensures `Orders.CustomerId` points to a valid customer (per schema).
- **Interleaving:** the child primary key includes the parent key prefix to co-locate parent/child rows, suitable when they are frequently read together.

**Do not confuse them:** a foreign key **does not automatically mean colocated data**, whereas interleaving is a **physical/locality** decision. Consider massive one-to-many relationships, write volume to a single parent, and row sizes before using interleaving.

## 8. Choosing a Database: Decision Matrix

| Criterion | Cloud SQL | AlloyDB | Spanner | Firestore | Bigtable |
| --- | --- | --- | --- | --- | --- |
| Primary model | Managed MySQL/PostgreSQL/SQL Server | PostgreSQL-compatible OLTP/analytics | Distributed relational SQL | Document | Wide-column/key-value |
| Relations, joins, SQL | Yes | Yes, PostgreSQL ecosystem | Yes, GoogleSQL/PostgreSQL dialect | Not based on relational joins | Not general-purpose SQL OLTP |
| Distributed ACID across data splits | Not the primary scale goal | Not a global goal | **Core strength** | Transactions with document semantics | Row-level semantics; unlike multi-row RDBMS |
| Horizontal write scaling | Limited by single-primary architecture | Write primary per AlloyDB architecture | **Yes**, depends on schema/capacity | Yes, based on document/query patterns | Yes, for suitable key-range workloads |
| Multi-region strong consistency | DR/replicas have different semantics | DR/replicas per product design | **Yes** with appropriate topology/edition | Per Firestore region design and consistency | Different replication semantics |
| PostgreSQL ecosystem | Cloud SQL PostgreSQL | **Very close to PostgreSQL** | Partial dialect, requires verification | No | No |
| Suitable workload | Small/medium apps, fast RDBMS migration | Heavy, high-performance PostgreSQL | Large-scale distributed relational transactions | Mobile/web document apps | High-throughput time-series/key-value |
| Cost / complexity | Usually easy to start | Requires cluster sizing | Requires key/transaction design and capacity planning | Per operations/storage | Per nodes/storage/throughput |

**BigQuery** is a separate choice for **data warehouse/analytics**, not an OLTP database for committing individual orders. Conversely, Spanner has SQL aggregation and analytics capabilities, but **not every large BI query should run on the primary Spanner OLTP database**; consider exporting/streaming to BigQuery.

### 8.1. When Should You Choose Spanner?

Consider Spanner if several of the following criteria are true simultaneously:

1. Data is **relational**, requiring joins/constraints/ACID.
2. Reads/writes are at **large scale**, and manual sharding in a traditional RDBMS creates operational burden.
3. You are ready to invest in designing keys, indexes, and transaction patterns suited for distribution.
4. You need **strong consistency** across distributed data and, with the appropriate edition/topology, multiple regions.
5. Availability SLOs and growth demands justify the **compute/replication costs**.

### 8.2. When Should You Not Choose It Yet?

- A Java CRUD app with a single primary DB, moderate scale requirements, and reliance on PostgreSQL extensions/stored procedures: **Cloud SQL PostgreSQL or AlloyDB** may be more economical.
- Only need document storage for mobile/web: consider **Firestore**.
- Extremely high key-value/time-series throughput without needing joins or general multi-row relational transactions: consider **Bigtable**.
- Majority of workload is multi-TB/PB data aggregation: prefer **BigQuery** for analytics.
- Only need single-region HA: evaluate **Cloud SQL HA/AlloyDB HA** before choosing Spanner multi-region.

**Do not choose Spanner just because of the label "globally scalable"; you must have measurable requirements.**

## 9. RTO, RPO, Latency, and User Location

| Factor | Questions to Ask |
| --- | --- |
| Application region | Where are Cloud Run/GKE running? Where are DB leaders/replicas located? |
| Read freshness | Are stale reads acceptable on dashboards? |
| Write latency | How far must a transaction coordinate to commit? |
| Availability | Is losing one zone or an entire region the scenario to protect against? |
| Data residency | Are there regulations requiring data storage in a specific country/region? |
| DR | Are backup, restore, PITR, failover, and RTO/RPO drills required? |
| Business invariants | If an API retries, could it create duplicate orders/payments? |

Spanner replication reduces the risk of data loss from infrastructure failures, **but it cannot undo an accidental `DELETE` or committed logic bug**. You still need backups, PITR, safeguards, application-level idempotency, and disaster-recovery testing.

**A multi-region instance does not automatically make every write faster than a regional one**: quorum/leader placement has an impact. Benchmark from **actual application regions**, rather than just running `SELECT 1` locally.

## 10. Editions and Compute Capacity

Spanner currently offers three editions:

| Edition | Highlights |
| --- | --- |
| **Standard** | Core relational/key-value features, **regional configuration** |
| **Enterprise** | Adds multi-model/search, enhanced operations such as **managed autoscaling**, regional + supported read-only replica options |
| **Enterprise Plus** | Adds **dual-region/multi-region**, higher HA capabilities, geo-partitioning per feature availability |

Compute capacity is provisioned in **nodes** or **processing units**, with **1 node = 1,000 PU**. Increasing compute handles more requests, but **does not fix hotspots caused by schema design**. With Enterprise/Enterprise Plus, you can configure **managed autoscaling** based on CPU/storage targets and appropriate min/max capacity.

**Capacity belongs to the instance's compute, not a number of VMs you manage directly.** An instance holds multiple databases sharing capacity; size according to total workload and replication topology.

### 10.1. Resources and Costs

Spanner may bill for:

- **Compute capacity**: edition, instance configuration, nodes/PU, number/type of replicas, and duration.
- **Database storage**: data, indexes, and replicas per the pricing model.
- **Backup/PITR** and data retention.
- **Network egress / replication-related transfer** depending on configuration.
- **Data Boost** if using independent read compute for compatible workloads.
- **Cloud Logging/Monitoring**, client service resources, and related services.

Costs depend on region, edition, and resource usage; **do not quote a hardcoded "cost per transaction" figure** without basing it on billing SKUs. Spanner offers a **90-day free trial instance** subject to specific terms and limits; it is not a permanent free-tier production environment. Alert-based billing budgets **do not automatically cap spending**.

## 11. Read-Only Lab: Evaluating Deployment Readiness

**First, create nothing**—only verify the project, region, and supported configurations:

~~~bash
gcloud auth list
gcloud config get-value project

# Supported instance configurations in the project:
gcloud spanner instance-configs list --project=PROJECT_ID

# Existing instances, does not modify state:
gcloud spanner instances list --project=PROJECT_ID
~~~

Assuming the lab uses `regional-asia-southeast1` and an instance named `spanner-choice-lab`. Before running mutating commands, confirm that this configuration appears in the output, the project has Billing/Spanner API enabled, and the operator has appropriate permissions.

### 11.1. IAM for Learners and Applications

- A lab deployer/admin has permissions to create instances/databases/schemas, scoped down per environment.
- The Java application only needs **Spanner Database User** (`roles/spanner.databaseUser`) on the target database, adding narrow roles only for special tasks.
- Locally, use **Application Default Credentials (ADC)**; on Cloud Run/GKE/Compute Engine, use the runtime service account / Workload Identity Federation for GKE.
- Do not create service account JSON keys, and do not grant `roles/spanner.admin` to the runtime just to make permission errors go away.

## 12. Mutating Lab: Creating an Instance and GoogleSQL Database

**Warning:** the commands below create resources that may incur continuous charges. Run only in an **approved lab project with a budget**, and do not collide with names used by other teams.

~~~bash
gcloud services enable spanner.googleapis.com \
  --project=PROJECT_ID

# Example small regional Standard instance; verify quota and pricing.
gcloud spanner instances create spanner-choice-lab \
  --config=regional-asia-southeast1 \
  --description="Spanner relational lab" \
  --edition=STANDARD \
  --processing-units=100 \
  --project=PROJECT_ID

# Creates a database with the GoogleSQL dialect by default.
gcloud spanner databases create orders-db \
  --instance=spanner-choice-lab \
  --project=PROJECT_ID
~~~

`100 PU` is a small compute example suitable for a lab under supported configurations, **not a production recommendation**. When an eligible free trial instance is available, you can follow the dedicated trial flow per documentation; do not blindly apply provisioned-instance flags to a trial.

### 12.1. Creating Tables and Indexes

~~~bash
gcloud spanner databases ddl update orders-db \
  --instance=spanner-choice-lab \
  --project=PROJECT_ID \
  --ddl='CREATE TABLE Orders (OrderId STRING(36) NOT NULL, CustomerId STRING(36) NOT NULL, TotalCents INT64 NOT NULL, Status STRING(20) NOT NULL) PRIMARY KEY (OrderId)'

gcloud spanner databases ddl update orders-db \
  --instance=spanner-choice-lab \
  --project=PROJECT_ID \
  --ddl='CREATE INDEX OrdersByCustomer ON Orders(CustomerId) STORING (Status, TotalCents)'
~~~

DDL operations are **long-running operations** and can take time; wait for the operation to complete before inserting/querying. In multi-user projects, do not run production schema changes without a migration plan.

### 12.2. Insert and Query

~~~bash
gcloud spanner databases execute-sql orders-db \
  --instance=spanner-choice-lab \
  --project=PROJECT_ID \
  --sql="INSERT INTO Orders (OrderId, CustomerId, TotalCents, Status) VALUES ('aa9dc1b4-2ef1-4afb-931c-6c912833dd70', 'customer-01', 150000, 'NEW')"

gcloud spanner databases execute-sql orders-db \
  --instance=spanner-choice-lab \
  --project=PROJECT_ID \
  --sql="SELECT OrderId, CustomerId, TotalCents, Status FROM Orders WHERE CustomerId = 'customer-01'"
~~~

**Expected result:** the query returns one row with `TotalCents=150000`. This is a **basic read/write exercise**; it does not measure throughput or prove "infinite scale." If you need to analyze the query plan, use **Spanner Studio/EXPLAIN** according to your SQL dialect version.

### 12.3. Cleaning Up Resources

After verifying **no data or other users depend on them**:

~~~bash
# PERMANENT DELETE: the database and lab data will be lost.
gcloud spanner databases delete orders-db \
  --instance=spanner-choice-lab \
  --project=PROJECT_ID

# PERMANENT DELETE: only after deleting/verifying all remaining databases.
gcloud spanner instances delete spanner-choice-lab \
  --project=PROJECT_ID
~~~

Deleting an instance deletes **all databases** inside it and cannot be easily undone. If deletion protection is enabled, follow the proper procedure. Check Billing Reports after cleanup; **do not assume disabling the Spanner API stops all charges**.

## 13. Java: Writing a Record with a Read-Write Transaction

The following snippet uses the **Spanner Java client** and the **GoogleSQL database** from section 12. Maven artifact: `com.google.cloud:google-cloud-spanner`, managed via an updated/vetted **Google Cloud Libraries BOM**; the code requires Java 17+ or a target supported by the client version.

~~~java
import com.google.cloud.spanner.DatabaseClient;
import com.google.cloud.spanner.DatabaseId;
import com.google.cloud.spanner.Key;
import com.google.cloud.spanner.Mutation;
import com.google.cloud.spanner.Spanner;
import com.google.cloud.spanner.SpannerOptions;
import com.google.cloud.spanner.Struct;
import java.util.List;

public class SpannerOrderExample {
    public static void main(String[] args) {
        String projectId = "PROJECT_ID";
        String instanceId = "spanner-choice-lab";
        String databaseId = "orders-db";
        String orderId = "aa9dc1b4-2ef1-4afb-931c-6c912833dd70";

        try (Spanner spanner = SpannerOptions.newBuilder()
                .setProjectId(projectId).build().getService()) {
            DatabaseClient db = spanner.getDatabaseClient(
                DatabaseId.of(projectId, instanceId, databaseId));

            String result = db.readWriteTransaction().run(tx -> {
                Struct existing =
                    tx.readRow("Orders", Key.of(orderId), List.of("OrderId"));
                if (existing != null) {
                    return "ALREADY_EXISTS";
                }

                tx.buffer(Mutation.newInsertBuilder("Orders")
                    .set("OrderId").to(orderId)
                    .set("CustomerId").to("customer-01")
                    .set("TotalCents").to(150000L)
                    .set("Status").to("NEW")
                    .build());
                return "CREATED";
            });

            System.out.println(result);
        }
    }
}
~~~

**Explanation:**

- `DatabaseClient` operates on a specific database; it does not automatically create instances/databases.
- `readWriteTransaction().run(...)` may **rerun the callback** when Spanner returns `ABORTED` due to contention; the callback should only read and write via `tx`.
- `tx.readRow` checks if the key exists; the mutation is buffered and then committed by the client library when the callback finishes.
- Two concurrent requests with the same `orderId` may result in abort/retry or one write being rejected due to a unique key; the app must handle the response and business idempotency.
- **Do not call Pub/Sub/email/payment APIs inside the callback**: the callback may execute multiple times. When you need to publish an event after commit, use an **outbox table in the same Spanner transaction** and a reliable relay.

The example already has the row created by the lab `INSERT` in section 12, so the output will be `ALREADY_EXISTS`. To observe `CREATED`, switch to a **new UUID v4** and run twice; the first run prints created, the second prints already exists. Never generate new IDs for retries of **the same business request**.

## 14. Spanner in Java Services: Connectivity and Security

| Application Source | Method | What to Verify |
| --- | --- | --- |
| Cloud Run | Spanner Java client via Google Cloud API, runtime service account | IAM Database User, deadlines, max instances, and sessions |
| GKE | Workload Identity Federation for GKE, client library | Namespace/KSA identity mapping, networking |
| Compute Engine | VM service account + client library | IAM and connectivity to Google APIs |
| Local developer | ADC `gcloud auth application-default login` | Quota project, least-privilege DB permissions |
| PostgreSQL tools | PGAdapter if dialect/driver are compatible | Feature support, connection config, and PostgreSQL differences |

**Spanner is not a PostgreSQL instance accepting TCP connections on default port 5432.** The Spanner Java client works over APIs; using certain PostgreSQL clients requires PGAdapter. Do not open a VPC firewall rule for the PostgreSQL port and assume Spanner is configured.

Consider **Private Google Access, VPC egress, and Private Service Connect for Google APIs** if your organization restricts network paths; do not model Spanner connectivity after public IPs of VMs or Cloud SQL databases.

## 15. Monitoring Spanner and Investigating Bottlenecks

Monitor **Cloud Monitoring** and Spanner observability tools:

| Signal | Interpretation |
| --- | --- |
| High-priority CPU utilization | Insufficient compute capacity or workload spike? |
| Storage utilization | Growing data/index size? |
| Read/write latency | DB latency and distance to leader/region |
| Transaction abort count | Contention, long transactions, hot keys |
| Session count, RPC errors, deadline exceeded | Client resources/pool, network/IAM |
| Query statistics/plan | Missing index, scanning many rows, expensive joins |
| **Key Visualizer** | Hotspots by key range, key/index ordering |
| Locks/transaction statistics | Transactions holding locks too long or experiencing contention |
| Billing SKU | Compute, storage, backup, network, Data Boost |

Google Cloud provides guidance on monitoring **high-priority CPU**: recommended maximums are **65% for regional** and **45% per region for dual-/multi-region** to leave headroom if an availability zone is impacted. These are **operational guidelines**, not hard limits for every workload.

### 15.1. When CPU Is High but Throughput Is Low

Do not just increase PUs/nodes. Check:

1. **Key range hotspots** caused by sequential timestamp primary keys/indexes.
2. Overly long transactions or contention on a hot row.
3. Queries scanning too much data, missing indexes, or choosing inefficient joins.
4. Apps deployed in a distant region making too many RPC calls per request.
5. Heavy read-only reports competing for CPU with OLTP; consider stale reads/Data Boost/BigQuery exports.

**Adding capacity does not naturally disperse a hot key range**; you must fix the schema/query pattern when a hotspot is the root cause.

## 16. Migration and Operational Trade-offs

Migrating from Cloud SQL/AlloyDB to Spanner is more than changing a JDBC URL:

- Evaluate **SQL dialect**, data types, and incompatible extensions/procedures/triggers.
- Redesign **primary keys, indexes, and transaction boundaries** for splits.
- Migrate data using documented migration tools/Dataflow, preserving **write consistency** during dual-write/cutover.
- Define handling for `ABORTED` errors, retry policies, idempotency, and session/pool management.
- Test cross-region query latency as well as backup/PITR/restore.
- Run load tests with **realistic traffic and realistic key distributions**, not just a handful of rows.

**Choosing the PostgreSQL dialect does not eliminate these steps.** Conversely, if the application relies heavily on PostgreSQL extensions and can meet its SLO within a single region, AlloyDB or Cloud SQL may be a simpler, more economical choice.

## 17. Decision Scenario: Global Orders

**Context:** the Commerce team currently runs Java on Cloud Run in Singapore and Tokyo, with a Cloud SQL PostgreSQL database in Singapore. Orders are growing rapidly, peak hours handle heavy write volumes, and there is a requirement for consistent reads/writes across multiple geographic regions.

| Question | If Answered "Yes" | Direction to Consider |
| --- | --- | --- |
| Are there tight relationships among orders, payments, and inventory? | Needs ACID/foreign keys/joins | Spanner / relational DB |
| Has a single primary database become a write bottleneck? | Scale-up/replicas are insufficient | Spanner, with a distributed schema |
| Need cross-region writes with strong consistency? | Latency/failover scenarios are complex | Enterprise Plus multi-region, choose leader carefully |
| Heavy use of PostgreSQL-specific extensions? | Migration is expensive | Evaluate AlloyDB/Cloud SQL first |
| Workload is mostly BI reporting? | Large query scans, batch | BigQuery rather than an OLTP DB |
| Budget available for multi-replica compute? | High replication/capacity costs | Compare TCO by workload |

**Selection process:**

1. Measure current Cloud SQL: QPS, write latency, CPU, storage, replica lag, downtime, and cost.
2. Define **RTO/RPO**, data residency requirements, and read/write ratios by region.
3. Benchmark an optimized Cloud SQL/AlloyDB setup **against** a Spanner PoC using realistic key distributions.
4. Test order placement transactions, concurrent inventory updates, idempotency, and network failures.
5. Measure p95/p99, abort rate, capacity, cross-region latency, and cost.
6. Migrate only when HA/scale benefits outweigh complexity/cost; prepare cutover and rollback plans.

**Scenario conclusion:** Spanner is well worth considering if write bottlenecks and multi-region strong consistency requirements are real. If a single region suffices and throughput is not yet saturated, **Cloud SQL HA/AlloyDB** is usually a more sensible starting point.

## 18. Exercises and Self-Check Questions

**Exercise 1 — Database Selection.** An internal Java app serves 200 requests/second, requires PostgreSQL extensions, and runs in one region. What should you choose?

*Suggested answer:* Cloud SQL PostgreSQL/AlloyDB first; Spanner is not optimal by default due to migration/compatibility/cost.

**Exercise 2 — Topology Selection.** A multi-region payment system requires cross-region consistency and availability. What configuration should you choose?

*Answer:* Evaluate Spanner Enterprise Plus dual-/multi-region, measure write latency, residency, cost, SLA, and DR.

**Exercise 3 — Finding a Hotspot.** A table has `PRIMARY KEY (CreatedAt, EventId)`; write rate increases while total CPU still has headroom. How do you fix it?

*Answer:* Use UUID v4/hash/shard prefix or an appropriate distributed key; check secondary indexes and Key Visualizer as well.

**Exercise 4 — Lab Practice.** Create a GoogleSQL instance/database, insert a row, run `SELECT` by `CustomerId`, and inspect the index.

*Pass criteria:* Data is accurate, query returns results; record configuration/PU/cost, and clean up the instance after the lab.

**Question 5.** Can Spanner use foreign keys/joins and ACID across multiple splits?

*Answer:* Yes, per supported features/dialect; this is a core distributed relational strength.

**Question 6.** Is Spanner's PostgreSQL dialect 100% equivalent to Cloud SQL PostgreSQL?

*Answer:* No. The SQL subset and ecosystem/extensions/drivers must be verified.

**Question 7.** How do strong reads and stale reads differ?

*Answer:* Strong reads require the latest consistent data per guarantee; stale reads accept an older snapshot as requested.

**Question 8.** When a Java transaction callback is retried, is it safe to call a payment API directly inside the callback?

*Answer:* No. The callback can execute multiple times; use an outbox/idempotency/reconciliation.

**Question 9.** Can regional Spanner survive a region-wide outage without another topology?

*Answer:* Not guaranteed; regional distributes across zones within one region, so cross-region DR requires a different plan.

**Question 10.** Why might adding nodes fail to help if a timestamp-based index is a hot range?

*Answer:* The hotspot still concentrates on one part of the key space/index; the key/index layout must be fixed.

**Question 11.** Is multi-region Spanner always faster for writes than regional?

*Answer:* No. Cross-region consensus/quorum can increase write latency.

**Question 12.** How many processing units equal 1 node?

*Answer:* 1,000 PU, though sizing also depends on edition/topology and workload.

**Question 13.** Does Spanner replace backups/PITR because it has synchronous replication?

*Answer:* No. Logic bugs and accidental deletes are replicated; backups/restore are still required.

**Question 14.** When should Bigtable be preferred over Spanner?

*Answer:* High-throughput key-value/wide-column workloads that do not require relational joins or general multi-row ACID.

## 19. Production Checklist

- [ ] Measurable requirements exist for **scale-out writes, strong consistency, HA/DR**.
- [ ] Compared against Cloud SQL/AlloyDB/Firestore/Bigtable for the exact use case.
- [ ] Selected **region/dual-region/multi-region** and edition matching feature/SLA needs.
- [ ] Ensured data residency, leader placement, and application proximity to data.
- [ ] Primary keys/indexes avoid hotspots; benchmarked using realistic key distributions.
- [ ] SQL dialect/compatibility/drivers/migration verified.
- [ ] Short transactions, `ABORTED` retries, and no external DB side effects in callbacks.
- [ ] Business idempotency and outbox are clearly designed.
- [ ] Least-privilege IAM `databaseUser`, ADC/WIF, and network controls configured appropriately.
- [ ] Compute PU/nodes, CPU utilization, storage/index growth, and autoscaler sized properly.
- [ ] Cloud Monitoring, Query stats, Key Visualizer, and SLO alerts active.
- [ ] Backup/PITR, restore drills, deletion protection, and DR runbooks approved.
- [ ] Billing budget alerts configured; compute, replicas, storage, backup, and egress estimated.
- [ ] Cutover, rollback, and audit plans in place when replacing a production database.

## 20. Conclusion

**Spanner is a true distributed relational database**, combining SQL, ACID transactions, strong consistency, and horizontal scalability through data partitioning, replication, and consensus. That power only pays off when **keys are well distributed, transactions are well designed, regions/editions are chosen properly, and costs are measured**.

Choose **Spanner** when relational/consistency/scale/availability requirements genuinely demand a distributed architecture. Choose **Cloud SQL or AlloyDB** when PostgreSQL/MySQL applications need higher compatibility and simpler operations. Every decision should rest on a **PoC with realistic load, SLOs, data residency, migration cost, and total cost of ownership**.

## Official References

- [Spanner documentation overview](https://cloud.google.com/spanner/docs)
- [Spanner instances](https://cloud.google.com/spanner/docs/instances)
- [Regional, dual-region, multi-region configurations](https://cloud.google.com/spanner/docs/instance-configurations)
- [Spanner editions](https://cloud.google.com/spanner/docs/editions-overview)
- [Spanner transactions](https://cloud.google.com/spanner/docs/transactions)
- [Schema and data model](https://cloud.google.com/spanner/docs/schema-and-data-model)
- [Schema design best practices](https://cloud.google.com/spanner/docs/schema-design)
- [Choose GoogleSQL or PostgreSQL dialect](https://cloud.google.com/spanner/docs/choose-googlesql-or-postgres)
- [Create and query database by gcloud](https://cloud.google.com/spanner/docs/getting-started/gcloud)
- [Getting started with Spanner in Java](https://cloud.google.com/spanner/docs/getting-started/java)
- [Spanner Java read-write transaction sample](https://cloud.google.com/spanner/docs/samples/spanner-read-write-transaction)
- [Spanner CPU utilization](https://cloud.google.com/spanner/docs/cpu-utilization)
- [Spanner pricing](https://cloud.google.com/spanner/pricing)
