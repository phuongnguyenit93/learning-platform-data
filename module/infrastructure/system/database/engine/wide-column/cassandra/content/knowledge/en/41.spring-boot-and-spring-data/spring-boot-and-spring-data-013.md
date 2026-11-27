# Schema Action, Migration, and Separating DDL Changes from Application Startup

> **Chapter:** Spring Boot and Spring Data  
> **Module:** DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA  
> **Scope:** Apache Cassandra — distributed wide-column database, partition-key and query-driven table design, replication/consistency levels, CQL, compaction, repair, error handling, and Java integration.  
> **Focus:** Spring Boot, Spring Data Cassandra, schema action, versioned migrations, and DDL deployment workflows independent of application startup.

## 1. The Problem: Why Should Application Startup Not Modify Schema Simultaneously?

An order service runs 20 Spring Boot instances. During deployment, the 20 new instances start up almost simultaneously. If each instance tries to create or alter Cassandra tables using an automatic mechanism based on Java entities, the following problems can occur:

- Multiple processes concurrently issue **CREATE/ALTER**, causing overlapping schema operations.
- Entities of the new and old versions coexist during a rolling deployment with **two different interpretations of the schema**.
- An incompatible column/UDT change causes startup failure; the container orchestrator keeps restarting instances, issuing even more DDL.
- A destructive schema action can wipe out existing table data.
- Inferred field names or Java types do not **fully** express Cassandra's replication, clustering order, TTL, compaction strategy, or data operational behavior.
- **CREATE/ALTER/DROP** privileges have to be granted to every instance just to start up, widening the security risk surface.

In production, the more common and controllable solution is:

**The schema is managed with versioned CQL migrations executed once in a controlled deployment phase; the Spring Boot application starts with schema action NONE and only executes business logic.**

This does not mean every DDL statement must be written by hand in every environment. In test/lab environments, automatic schema creation can be convenient; however, local convenience should not be confused with production policy.

After this lesson, you will be able to:

1. Distinguish between **Spring Data mapping metadata** and the **actual Cassandra schema**.
2. Understand the meaning, risks, and scope of **SchemaAction** options in Spring Data Cassandra.
3. Configure **spring.cassandra.schema-action: none** in Spring Boot 3.x and recognize configuration differences across Boot generations.
4. Separate DDL migrations into a dedicated job/pipeline with ordering, checksums, ownership, privileges, and verification evidence.
5. Design changes following **expand → migrate/backfill → switch → contract** so rolling deployments do not break older application versions.
6. Verify schema agreement, RF/DC, primary keys, CQL, and Java connectivity before opening traffic.
7. Prepare a failure/rollback runbook for changes that may be irreversible.

> **Version note:** Boot configuration properties, available SchemaAction values, UDT/table creation behavior, migration tool integration, and CQL syntax may vary by specific **Spring Boot/Spring Data Cassandra/Cassandra** versions. The examples target **Spring Boot 3.x + Spring Data Cassandra + Java driver 4.x**. When using Boot 2.x or another Cassandra distribution, consult the exact documentation rather than copying property names or APIs mechanically.

## 2. Three Layers of Responsibility: Entity, Schema, Data

Spring Data Cassandra lets you describe Java entities using annotations such as **@Table**, **@PrimaryKey**, **@PrimaryKeyClass**, **@PrimaryKeyColumn**, and **@Column**. These annotations provide **mapping metadata** so the framework can read and write rows.

Cassandra stores schema and data across the cluster. DDL consists of **CREATE KEYSPACE**, **CREATE TABLE**, **ALTER TABLE**, **CREATE TYPE**, **CREATE INDEX**, and other schema-modifying statements. They affect multiple nodes, not just the Java process that is starting up.

~~~mermaid
flowchart LR
    E["Java Entity + repository"] --> M["Spring Data mapping"]
    M --> D["CQL SELECT/INSERT/UPDATE"]
    D --> C["Cassandra cluster\nschema + data"]
    V["Versioned CQL migration"] --> G["Migration job with DDL privileges"]
    G --> C
    A["Spring Boot application"] --> M
    P["CI/CD gates and approvals"] --> G
~~~

### 2.1. Mapping Is Not the Sole Source of Truth

Suppose an entity has a **status** field of type String. It does not by itself describe critical operational choices:

- Does the keyspace use **NetworkTopologyStrategy**, and what is the RF per DC?
- Should the partition key be bucketed by day? How large is a single partition expected to grow?
- What **DESC/ASC** clustering order is required for the primary query?
- How are the table's TTL, **gc_grace_seconds**, compaction, or compression settings approved?
- In which version do UDTs/indexes exist, and are they understood by older application versions?
- Are DDL privileges permitted? Are **data residency/security** rules applied properly per DC?

These decisions belong to **schema contract + data architecture + cluster operations**. Java mapping must **match** the schema, but it should not by default hold authority to recreate the production schema by inferring from classes.

### 2.2. Differences from Relational Databases

Cassandra is not designed for applications to arbitrarily alter schemas on every startup like a small local database. DDL is distributed and metadata is synchronized across nodes; furthermore, the **PRIMARY KEY determines data placement and organization**. Changing a partition key or clustering key is usually not a minor ALTER statement, but requires a **new table, data migration, and query cutover**.

Cassandra also does not provide multi-step DDL transactions of the form "CREATE/ALTER multiple tables, and if the last statement fails, ROLLBACK everything" for migrations. A partially executed script can leave the cluster in a **partially modified schema state**.

## 3. Spring Data Cassandra SchemaAction

Spring Data Cassandra provides a **SchemaAction** configuration setting to decide what happens to the schema during application context initialization, depending on the framework and version. Common values include:

| Schema action | General meaning | Suitable for multi-instance production? |
|---|---|---|
| **NONE** | Do not automatically create/recreate schema from mapping at startup | **Default choice to set explicitly** when schema is managed by separate migrations |
| **CREATE** | Create schema from mapping using framework logic | Consider only for test environments with controlled lifecycles |
| **CREATE_IF_NOT_EXISTS** | Create objects needed by mapping if they do not exist, using framework logic | Suitable for some labs/tests, **not a safe migration mechanism for all existing schemas** |
| **RECREATE** | Recreate schema using framework logic; may drop data/tables | **Do not use in production** |
| **RECREATE_DROP_UNUSED** | Variant that recreates/drops unused objects according to mapping; destructive | **Do not use in production** |

**Key takeaway:** **CREATE_IF_NOT_EXISTS is not a schema diff or migration engine.** If a table already exists but is missing a new column, has the wrong CQL type, has a changed clustering key, or has incorrect compaction settings, "create if not exists" does not ensure that existing schema is upgraded accurately.

Do not treat **SchemaAction.NONE** as a **schema validator**. NONE only means the framework does not automatically create or modify schema; the application can still fail when repositories prepare CQL statements or query nonexistent columns. Schema validation must be handled by the migration job and dedicated integration tests.

### 3.1. Destructive Values Are Especially Dangerous

A recreating schema action may fit an **ephemeral test cluster with no real data**. In production, if it drops/recreates tables or UDTs, the consequences can include:

- Data loss that cannot be fixed by restarting the application.
- DELETE/TTL/tombstone events and replicas not automatically restoring deleted content according to business state.
- Some app instances still reading/writing the old table during a rolling deployment.
- Backups whose recovery point precedes the action missing subsequent new writes.

**Do not rely on replication factor to consider DROP/RECREATE safe.** Replicas store copies of mutations/schema changes; independent backups and restore drills are what provide a separate fault-domain recovery layer.

### 3.2. Why Not "CREATE_IF_NOT_EXISTS in Production for Convenience"?

- Every instance still needs schema creation privileges, even though runtime only needs DML.
- If multiple app versions start up together, their mappings may differ.
- Migration errors lack clear history, checksums, and approvals.
- An entity change may accidentally depend on an unmigrated column.
- Automatic object-creation logic may not fully manage replication, indexes/UDTs, table options, and ordering of changes.
- A schema that has the right name but the **wrong structure** is not valid merely because it exists.

Therefore, **schema action NONE + independent migrations** is easier to audit and control risk for a live system.

## 4. Spring Boot Configuration: Application Does Not Run DDL Automatically

For Spring Boot **3.x** using Cassandra auto-configuration, an illustrative configuration is:

~~~yaml
spring:
  application:
    name: order-api
  cassandra:
    contact-points:
      - cassandra-1.internal
      - cassandra-2.internal
    port: 9042
    local-datacenter: dc1
    keyspace-name: commerce
    schema-action: none
~~~

Meaning:

- **keyspace-name** selects the keyspace the application uses; it **does not define RF/topology** for the cluster.
- **local-datacenter** must match the actual DC name so the driver routes traffic appropriately.
- **schema-action: none** tells Spring Data not to automatically create schema from entities when the context starts.
- Contact points are only initial addresses for cluster discovery, not a list of all replicas.
- Production requires proper **TLS, authentication, secrets, and network policies**; never put passwords into publicly committed YAML.

**Do not assume configuration properties are identical across Boot generations.** Some Spring Boot 2.x versions use the **spring.data.cassandra...** namespace, whereas 3.x versions use **spring.cassandra...** for connection/schema properties. Verify the documentation and **effective configuration** for your exact version before rollout. A misspelled property name may silently fail to take effect.

### 4.1. Set Schema Action NONE in Every Important Environment

Set **NONE** explicitly for staging and production to validate the migration pipeline. For completely isolated unit/integration tests, schemas can be created via test fixtures or controlled initialization mechanisms.

Do not build logic like:

~~~java
// Illustrative anti-pattern: API startup executes DDL itself.
@Component
class SchemaOnStartup {
    @EventListener(ApplicationReadyEvent.class)
    void init() {
        // cqlSession.execute("ALTER TABLE ...");
    }
}
~~~

The pseudo-code above is **not an acceptable implementation**. It illustrates the risk when every instance executes DDL on AppReady. Replace it with a **migration job** in the pipeline before releasing the app version that requires the new schema.

### 4.2. Runtime Privileges Differ from Migration Privileges

| Actor | Required privileges | Should not routinely hold |
|---|---|---|
| **Spring Boot runtime application** | SELECT, MODIFY on tables/keyspaces needed by features; required metadata/connection privileges | CREATE/ALTER/DROP across the keyspace/cluster |
| **Migration job** | CREATE/ALTER scoped to the keyspace, metadata read privileges for verification | Cluster-wide superuser privileges when unnecessary |
| **DBA/SRE** | Manage replication, nodes, backup/restore, and approve changes | Sharing app credentials for everything |
| **CI/CD orchestrator** | Run a single versioned migration job, record logs/audits, manage approvals | Writing secrets into artifacts, running DDL on every app replica |

Cassandra's privilege model depends on the configured version/authenticator/authorizer; confirm exact **GRANT** syntax and permission targets on your specific cluster. The guiding principle is **least privilege + secret rotation + audit**.

## 5. CQL Schema: Example Query-Driven Design

Suppose an API frequently reads **the list of orders for a customer on a given day, newest first**. We design a partition by **(customer_id, order_day)** and clustering columns.

### 5.1. Keyspace and Replication

**Lab** example with RF 3 in dc1:

~~~sql
-- Run only when dc1 has sufficient nodes/appropriate replica distribution.
CREATE KEYSPACE IF NOT EXISTS commerce
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};
~~~

**In production**, the keyspace/RF must be finalized by DBA/SRE based on topology, DCs, racks, and RPO/RTO. Do not let a Java entity or auto-create utility implicitly decide replication. Changing RF requires a proper operational/repair plan and is not just a one-line edit in application.yml.

### 5.2. Creating a Table Aligned with the Access Pattern

~~~sql
CREATE TABLE IF NOT EXISTS commerce.orders_by_customer_day (
    customer_id uuid,
    order_day date,
    created_at timestamp,
    order_id uuid,
    status text,
    amount decimal,
    PRIMARY KEY ((customer_id, order_day), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
~~~

- **(customer_id, order_day)** is a composite partition key. Queries must bind both components.
- **created_at, order_id** are clustering keys, supporting ordering within the partition.
- **status, amount** are business attributes; another query by order_id may require a **separate query-specific table**.
- A very hot customer can still produce a large daily partition. Measure row counts/bytes and consider smaller buckets/sharding if needed.
- **CREATE TABLE IF NOT EXISTS** makes creation repeatable when the object does not exist yet, but **does not guarantee that the table options/columns of an existing table match the migration**.

### 5.3. Typical CQL Query

~~~sql
SELECT created_at, order_id, status, amount
FROM commerce.orders_by_customer_day
WHERE customer_id = ?
  AND order_day = ?
LIMIT ?;
~~~

This is a query for **PreparedStatement** in Java. Do not use **ALLOW FILTERING** to patch over a missing partition key. If the API needs to inspect multiple days, it must query bounded buckets and merge results according to business ordering.

## 6. Spring Data Cassandra Mapping Matching the Primary Key

Spring Data can map an entity to the table model above. Minimal Java example:

~~~java
import java.io.Serializable;
import java.time.Instant;
import java.time.LocalDate;
import java.util.Objects;
import java.util.UUID;

import org.springframework.data.cassandra.core.cql.PrimaryKeyType;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;

@PrimaryKeyClass
public class OrderEventKey implements Serializable {
    @PrimaryKeyColumn(
        name = "customer_id", ordinal = 0,
        type = PrimaryKeyType.PARTITIONED)
    private UUID customerId;

    @PrimaryKeyColumn(
        name = "order_day", ordinal = 1,
        type = PrimaryKeyType.PARTITIONED)
    private LocalDate orderDay;

    @PrimaryKeyColumn(
        name = "created_at", ordinal = 2,
        type = PrimaryKeyType.CLUSTERED)
    private Instant createdAt;

    @PrimaryKeyColumn(
        name = "order_id", ordinal = 3,
        type = PrimaryKeyType.CLUSTERED)
    private UUID orderId;

    public OrderEventKey() {}

    public OrderEventKey(
            UUID customerId, LocalDate orderDay,
            Instant createdAt, UUID orderId) {
        this.customerId = customerId;
        this.orderDay = orderDay;
        this.createdAt = createdAt;
        this.orderId = orderId;
    }

    public UUID getCustomerId() { return customerId; }
    public LocalDate getOrderDay() { return orderDay; }
    public Instant getCreatedAt() { return createdAt; }
    public UUID getOrderId() { return orderId; }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof OrderEventKey)) return false;
        OrderEventKey that = (OrderEventKey) other;
        return Objects.equals(customerId, that.customerId)
            && Objects.equals(orderDay, that.orderDay)
            && Objects.equals(createdAt, that.createdAt)
            && Objects.equals(orderId, that.orderId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(customerId, orderDay, createdAt, orderId);
    }
}
~~~

Entity:

~~~java
import java.math.BigDecimal;

import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("orders_by_customer_day")
public class OrderEvent {
    @PrimaryKey
    private OrderEventKey key;

    @Column("status")
    private String status;

    @Column("amount")
    private BigDecimal amount;

    public OrderEvent() {}

    public OrderEvent(
            OrderEventKey key, String status, BigDecimal amount) {
        this.key = key;
        this.status = status;
        this.amount = amount;
    }

    public OrderEventKey getKey() { return key; }
    public String getStatus() { return status; }
    public BigDecimal getAmount() { return amount; }
}
~~~

Repository:

~~~java
import java.util.UUID;

import org.springframework.data.cassandra.repository.CassandraRepository;

public interface OrderEventRepository
        extends CassandraRepository<OrderEvent, OrderEventKey> {
    // Declare query methods aligned with the access pattern
    // and verify the generated CQL instead of guessing arbitrary method names.
}
~~~

> **Source code note:** Each class/interface above belongs in its **corresponding Java file** with an appropriate package. In real use, check Spring Data version compatibility, annotations/constructors, and unit tests. This lesson **does not create Java files in the repository**.

**Important point:** The mapping includes both **partition** and **clustering columns**; changing key order or types in an entity does not alter an existing Cassandra primary key. If the Java entity changes while the table has not changed, startup may still succeed, while queries, deserialization, or saves fail.

### 6.1. An Easily Overlooked Mapper Bug

If the CQL schema defines **order_day date** but Java computes the date in the local timezone while another service uses UTC, data can be written into **two different partitions**. This is not a Cassandra DDL bug, but a partition-key derivation rule bug. Migrations should also test data around day boundaries/TTLs and across multiple client versions.

### 6.2. Repositories Do Not Replace Schema Verification

A repository interface compiling successfully does not guarantee:

- The table already exists on the cluster.
- Clustering order and partition key are correct.
- The schema has propagated to every node.
- The runtime role has SELECT/MODIFY privileges.
- The driver is compatible with the CQL/UDT types.
- The consistency level satisfies RF/DC.
- Derived query methods have valid access patterns and do not trigger scans.

Therefore, **integration tests against a representative Cassandra cluster** are required, not just context-load tests or mocked repositories.
## 7. Separating DDL Migrations from the Spring Boot Startup Lifecycle

The deployment model should have two components with distinct privileges, responsibilities, and execution timing:

~~~mermaid
flowchart TD
    A["Commit code + CQL migration"] --> B["Build/test and schema review"]
    B --> C["Approve change"]
    C --> D["One coordinated migration job"]
    D --> E["Cassandra schema updated"]
    E --> F["Verify schema agreement + metadata + smoke test"]
    F --> G{"Gate passed?"}
    G -->|No| H["Halt rollout, investigate/recover"]
    G -->|Yes| I["Deploy Spring Boot vNext"]
    I --> J["App connects with schema-action NONE"]
    J --> K["Observe SLOs and correctness"]
~~~

**The migration lifecycle** belongs to CI/CD or a dedicated operations job. **The application lifecycle** covers process startup, creating sessions, mappers, repositories, and serving requests.

### 7.1. Why Does the Job Run Only Once?

If there are 20 application instances, you do not want 20 startups deciding whether to run migrations. Instead:

- The pipeline has **a single execution owner** per environment/keyspace.
- The migration job is serialized through the orchestrator (deployment lock/change ticket/singleton job).
- Do not use **Cassandra schema metadata** as an implicit mutex across multiple processes.
- When the job fails, prevent the application version depending on the new schema from receiving traffic.
- Each migration version is recorded as complete only after **postcondition verification**.

Running only one process does not suddenly make DDL statements transactional. It reduces races and clarifies accountability when errors occur.

### 7.2. Separate Privileges and Secret Paths

The migration job needs credentials with appropriate privileges to create/alter schema on the **authorized keyspace**. The runtime app should have credentials restricted to **SELECT/MODIFY** on the required tables.

~~~text
CI/CD change approval
       |
       +--> Migration identity (DDL permissions, short-lived)
       |         |
       |         +--> CREATE/ALTER + schema checks
       |
       +--> Application identity (DML permissions)
                 |
                 +--> Spring Boot startup
                 +--> Controlled SELECT/INSERT/UPDATE/DELETE
~~~

Do not commit passwords or CQL auth tokens to the repository. Use a secret manager and auditing; encrypt connections with TLS, verify certificates, and restrict network policies. Do not share one long-lived admin credential across every application pod.

### 7.3. Avoid Startup DDL Disguised as an "Init Helper"

Some projects keep SchemaAction.CREATE disabled yet still include one of the following mechanisms:

- A **CommandLineRunner** or **ApplicationRunner** calling **CqlSession.execute("CREATE TABLE ...")**.
- **@PostConstruct** creating keyspaces/tables.
- **ApplicationReadyEvent** triggering ALTER TABLE.
- A bean creating indexes/UDTs on every context refresh.
- A test fixture accidentally loaded in the production profile.
- A third-party starter or custom Cassandra configuration triggering schema initialization.

**Disabling SchemaAction is only part of the control.** You must audit **custom DDL code paths** and runtime permissions as well. The most practical way to prevent unintended DDL is: **runtime credentials are not granted DDL privileges**, and migrations use a separate identity.

## 8. Versioned CQL Migrations: A Minimal Model

A migration set typically includes **immutable CQL files**, version names, checksums, descriptions, review metadata, and execution order. This example is only a **suggested layout**, not a mandatory format of Spring Data Cassandra:

~~~text
db/cassandra/
  V001__create_orders_by_customer_day.cql
  V002__add_fulfillment_channel.cql
  V003__create_order_lookup_table.cql

manifest:
  version
  filename
  sha256
  reviewed_by
  approved_change
  expected_precondition
  expected_postcondition
~~~

This lesson does not create those illustrative files; they describe how to organize them in a real Java project.

### 8.1. Migration V001: Create Table

~~~sql
-- V001__create_orders_by_customer_day.cql
-- Preconditions:
--   keyspace commerce has been created with approved RF/DC
--   table orders_by_customer_day does not exist yet
-- Postconditions:
--   partition/clustering keys, column types, and options match spec

CREATE TABLE IF NOT EXISTS commerce.orders_by_customer_day (
    customer_id uuid,
    order_day date,
    created_at timestamp,
    order_id uuid,
    status text,
    amount decimal,
    PRIMARY KEY ((customer_id, order_day), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
~~~

**Do not stop verification at "CREATE returned no error."** If the table already existed with different types or structure, **IF NOT EXISTS** may skip the operation; the migration must still compare the **actual schema** against postconditions.

### 8.2. Migration V002: Adding a Column, Preserving Backward Compatibility

~~~sql
-- V002__add_fulfillment_channel.cql
-- Preconditions:
--   V001 achieved, column fulfillment_channel does not exist yet
-- Postconditions:
--   fulfillment_channel has type text, primary key unchanged

ALTER TABLE commerce.orders_by_customer_day
ADD fulfillment_channel text;
~~~

This is an **additive** change. Older rows without a value in the new column are typically read as **null** until backfilled/updated. Older applications that do not reference this column can continue operating, provided other assumptions still hold.

**However**, an additive change can still break applications when:

- The new version's Spring Data mapper expects a **non-null** field while legacy data is still null.
- New queries reference the column before DDL propagates/is applied.
- The new column is created with a different type than the mapping code expects.
- **save** logic inadvertently writes null, creating tombstones for existing fields.
- Queries from older apps use **SELECT * / positional mapping** with fragile assumptions about fixed field counts/order.

Migrations must therefore test **old reader, new reader, old writer, and new writer**.

### 8.3. Migration V003: Adding a Table for a Different Access Pattern

Suppose a new API needs to look up **an order by (customer_id, order_id)** without knowing the date. Instead of scanning every day bucket or enabling ALLOW FILTERING, we create a separate table:

~~~sql
-- V003__create_order_lookup_table.cql

CREATE TABLE IF NOT EXISTS commerce.order_lookup_by_id (
    customer_id uuid,
    order_id uuid,
    order_day date,
    created_at timestamp,
    status text,
    PRIMARY KEY ((customer_id), order_id)
);
~~~

The application needs a business-aligned synchronization mechanism between **orders_by_customer_day** and **order_lookup_by_id** (event-driven, carefully designed dual write, idempotent projection, or reconciliation). **There is no automatic multi-partition ACID transaction** simply from adding a table. Additionally, if a customer accumulates an extremely large number of orders, partitioning by **customer_id** in the lookup table can grow large; evaluate cardinality/load and consider **((customer_id, order_id))** or another bucketing scheme for point lookups.

### 8.4. Distinguishing "Rerun" from "First-Time Completion"

A migration can stop midway: CREATE TABLE succeeds, but postcondition verification or ledger checksum recording fails. On rerun:

- Do not blindly rerun from the initial state.
- Check **actual preconditions and postconditions** on the cluster.
- Mark as complete only when the schema matches expectations.
- If a prior step ran and produced the wrong schema, stop and seek approval for a remediation path.
- Never edit the contents of an already-applied migration while keeping the same version; add a **subsequent migration** with a clear changelog instead.

**IF NOT EXISTS is neither a migration transaction nor a distributed lock.** It reduces "already exists" errors rather than verifying schema compatibility or rolling back failed steps.

## 9. Migration Ledger, Checksums, and Execution Tools

A migration workflow may store history of applied migrations, for example:

~~~sql
-- Illustrative custom ledger if an organization builds its own runner.
CREATE TABLE IF NOT EXISTS commerce.schema_migrations (
    version text PRIMARY KEY,
    checksum text,
    applied_at timestamp,
    description text,
    applied_by text
);
~~~

The ledger only aids **tracking/auditing**; it is not the sole source of truth. You must cross-check **system_schema** and the postconditions of each DDL statement.

### 9.1. Why a Ledger Row Does Not Make DDL Atomic

Suppose a runner does:

~~~text
1. INSERT version='V002' IF NOT EXISTS into ledger
2. ALTER TABLE ... ADD fulfillment_channel
3. Record completion result
~~~

If the process dies between steps 1 and 2, the ledger may indicate the migration was claimed while the DDL never ran. If you reverse the order to **ALTER first, then INSERT ledger**, the process can still die between those two steps. Cassandra does not provide an atomic transaction spanning **schema change + ledger row**.

**A more reliable design:**

1. Serialize the runner using an **orchestrator lock** or approved coordination mechanism.
2. Record **intention/attempt** in a separate audit log without treating it as COMPLETE.
3. Verify preconditions.
4. Execute DDL in a fixed order.
5. Wait for and verify schema agreement per approved criteria.
6. Verify postconditions against metadata and CQL smoke tests.
7. Only upon passing, record **APPLIED** along with checksum/version.
8. If a job dies mid-run, the next runner **reads the cluster schema first** and decides whether to resume or fix, rather than blindly rerunning.

Do not build a DIY distributed lock with LWT and assume that lock protects multi-node DDL execution on its own. Any lock requires lease/fencing/ownership handling for disconnects, stale locks, and dead processes; a **single pipeline executor** is simpler.

### 9.2. Choose Cassandra-Appropriate Tools, Do Not Assume JDBC Migrations

Some ecosystems provide **CQL**-capable migration tools, Liquibase extensions, or custom runners. Support for Cassandra varies by tool/extension version.

**Do not assume standard relational-database JDBC Flyway/Liquibase setups can run directly on Cassandra without proper connectors/extensions and testing.** Verify:

- Compatibility with your Cassandra/driver/JDK versions and authentication/TLS.
- How multi-statement files are executed and how CQL errors are detected.
- How schema agreement waiting and DDL retry semantics behave.
- Checksums, version ordering, auditing, and handling of partially failed migrations.
- Whether it modifies keyspaces/roles out of scope.
- Whether it can run inside a single Kubernetes Job or pipeline step.

If using **cqlsh -f** as a simple runner in a lab, do not rely solely on exit codes while ignoring logs and postconditions. Error reporting and stop-on-error behavior can vary by cqlsh version; production needs a thoroughly tested wrapper/runner.

## 10. Expand–Migrate–Switch–Contract in Rolling Deployments

A production system can rarely shut down all APIs, alter schema, and bring up every new version simultaneously. You must handle **app v1 and v2 coexisting**.

~~~mermaid
flowchart TD
    A["Step 0: app v1 + schema S1"] --> B["EXPAND: run migration creating S2 compatible with v1"]
    B --> C["VERIFY: schema agreement, metadata, smoke tests"]
    C --> D["DEPLOY: app v2 reads both old and new data"]
    D --> E["BACKFILL: bounded supplementary writes and reconciliation"]
    E --> F["SWITCH: move readers/writers to new schema"]
    F --> G["OBSERVE: no v1 consumers remaining"]
    G --> H["CONTRACT: separately approved cleanup/drop"]
~~~

### 10.1. Expand Step: Add First, Do Not Break the Old Schema

- Add **new nullable columns** or **new tables**.
- Do not immediately rename or drop old columns while app v1 still reads them.
- Do not change the partition/clustering key of a table currently in use.
- Wait until the schema is recognized and verify both old readers and old writers.
- When adding UDT fields, check mappers/codecs across all app versions and null handling.

For Cassandra, **changing a primary key** typically requires a new table with different keys rather than an ALTER on the existing table. Because schema is tightly bound to data partitioning, measure token distribution, partition sizes, and consistency for the new table.

### 10.2. Deploy Step: App v2 Tolerates the Transitional State

Example of v2 using **fulfillment_channel**:

~~~java
// Business logic idea in application v2:
String channel = row.getString("fulfillment_channel");
if (channel == null) {
    channel = "LEGACY";
}
~~~

This snippet illustrates handling **legacy rows missing the new column**, not a complete repository implementation. You must ensure DDL has run before queries **reference** the new column; null handling only covers existing rows lacking values, **it does not allow queries to run against a schema that does not yet have the column**.

### 10.3. Backfill: A Data Process Separate from DDL

When populating a new column is needed, run a job with:

- **A verifiable data source** for each row; do not invent values when invariants matter.
- Full partition key and clustering columns when issuing UPDATE.
- **Rate limits/concurrency bounds** to avoid overloading hot partitions.
- Checkpoints, idempotency, and retry budgets.
- Row count checks, sampled fixtures, and invariant reconciliation between old/new tables.
- Monitoring of disk I/O, GC, compaction/tombstones, and repair/streaming.
- A resume strategy from failures and clear distinction between complete and incomplete states.

**Do not treat backfill as an ALTER TABLE statement.** DDL is usually a small statement with metadata impact; backfill is actual data load that can run for hours and affect SLAs.

### 10.4. Switch: Shifting Readers and Writers

Once data is sufficiently populated, you can:

1. Enable **dual read/compare** to reconcile old/new data at controlled ratios.
2. Activate new writers and guarantee idempotency.
3. Gradually shift readers via feature flags.
4. Preserve fallback reading of the legacy path during the compatibility window.
5. Run reconciliation when discrepancies appear.
6. Consider contraction only after all old clients/consumers have stopped.

**Dual write** has its own failure modes: one table write succeeds while the other times out. Design event/outbox patterns, idempotent retries, or reconciliation; do not treat two INSERTs as a distributed transaction.

### 10.5. Contract: A Destructive Step with Its Own Approval Gate

After verifying no legacy consumers remain:

- Unused fields/tables/indexes may be dropped following supported CQL procedures.
- Destructive drop/alter DDL must have a **recovery point, backup/restore drill, retention window, and change approval**.
- Assess tombstones, compaction, and disk space before large operations.
- Do not consider application rollback sufficient once a column/table has been dropped.

A **contract migration** should not run alongside deploying app v2 if app v1 may still exist during rolling rollout or within the rollback window.

## 11. Deployment Order: Migration First, App Next, Cleanup Last

A typical plan:

| Phase | Actor | Entry criteria | Exit criteria |
|---|---|---|---|
| **0. Review** | DBA/SRE + Java owners | CQL diff, version matrix, backup, and KPIs | Change approved |
| **1. Preflight** | Migration runner | Cluster healthy, RF/DC/CL sufficient, valid secrets | Baseline and recovery path ready |
| **2. Apply expand migration** | **One** migration job | No other runner active, schema preconditions met | DDL applied, logs/audits recorded |
| **3. Verify schema** | Job + smoke tests | Schema agreement and system_schema match | CQL old/new fixtures PASS |
| **4. Deploy app** | CD orchestrator | App v2 compatible with both old and new state | Canary/rolling deployment PASS |
| **5. Backfill/switch** | Data job + app team | Sufficient capacity, idempotency/rollback plan | Data reconciled, traffic switched |
| **6. Contract** | Migration runner + DBA | No old readers/writers remaining, recovery approved | Cleanup PASS, backup/restore re-verified |

### 11.1. If the Migration Fails Before Deploy

- **Do not deploy** the version depending on the new column/table.
- Keep app v1 running if it remains compatible with the current schema state.
- Review partially applied DDL; verify metadata object by object.
- Choose a safe fix-forward migration or restore if data loss / one-way mutation occurred, per runbook.
- Clearly record **BLOCKED** status, owner, evidence, and rerun criteria.

### 11.2. If App v2 Fails After the Schema Expanded

In a well-designed additive change, you can usually **roll back the application to v1** while **leaving the unused new column/table in place**. Still, verify:

- Does app v1 read/write normally while the new column exists?
- Has app v2 written new data that v1 does not understand or that altered business state?
- Were feature flags switched or writes sent to a new table? Is reconciliation needed?
- Did any contract/destructive step run beforehand?
- Do RPO/RTO and backups still meet commitments?

**Code rollback does not equal data/schema rollback.** Leaving an additive column temporarily in place is usually safer than rushing to drop it during an incident, though this must be verified for the specific version.
## 12. Schema Agreement and Postconditions: Running the Migration Is Not Enough

Cassandra distributes schema metadata across multiple nodes. After DDL, there can be a window during which nodes do not yet agree on the same schema version. Therefore, a migration should only be marked successful after **both structural correctness and schema agreement meet requirements**.

### 12.1. Checking via CQL Metadata

Check keyspace replication:

~~~sql
SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'commerce';
~~~

Check table existence:

~~~sql
SELECT keyspace_name, table_name
FROM system_schema.tables
WHERE keyspace_name = 'commerce'
  AND table_name = 'orders_by_customer_day';
~~~

Check column names, types, and positions:

~~~sql
SELECT column_name, kind, position, type
FROM system_schema.columns
WHERE keyspace_name = 'commerce'
  AND table_name = 'orders_by_customer_day';
~~~

These SELECT statements inspect **the metadata seen by the connected node**. They do not by themselves prove every node agrees. On a distributed cluster, check **schema agreement** using the version-appropriate API/tooling and cross-check logs/metrics across nodes.

### 12.2. Node-Level Observation Commands

~~~bash
# Node UP/DOWN status and DC/rack distribution.
nodetool status

# Schema agreement/version info according to the tool available in this version.
nodetool describecluster

# Background task info to assess deployment impact.
nodetool tpstats
nodetool compactionstats

# After deploy/queries, inspect the table serving the workload.
nodetool tablestats commerce.orders_by_customer_day
~~~

**nodetool describecluster** can display schema version information depending on the version; do not hardcode brittle output parsing. If nodes disagree or are unreachable, do not declare cluster-wide verification just because one SELECT through a coordinator succeeded.

**If schema disagreement persists:** keep the pipeline PAUSED, inspect node health, gossip/networking, schema logs, and version compatibility. Do not rush to restart the entire cluster or run repair to "fix schema." **Data repair** is not a substitute for resolving schema agreement.

### 12.3. Postconditions Must Include Semantics, Not Just Names

A table can exist yet violate the intended design. For **orders_by_customer_day**, verify:

- Partition key is **customer_id + order_day** in the exact order.
- Clustering key is **created_at + order_id** with DESC/ASC ordering per spec.
- **amount** has type decimal, **status** has type text.
- **fulfillment_channel** has type text after V002.
- The keyspace uses the approved replication strategy and RF/DC.
- Tables/indexes/UDTs and related table options match the migration.
- The runtime role has required privileges and lacks unnecessary DDL privileges.
- Driver and Spring Data mapping can read/write via prepared CQL on at least fixture keys.

Checking only **table_name** lets a table with the wrong partition key slip past the gate, causing query failures or hotspots in production.

## 13. Spring Boot Only Checks Contracts, Never Modifies Schema

After the migration job runs and verifies metadata, the vNext application can perform a **lightweight compatibility check** during deployment/readiness. This is fundamentally different from "auto-creating schema."

Example Spring bean checking required column presence via Java Driver metadata:

~~~java
import com.datastax.oss.driver.api.core.CqlIdentifier;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.metadata.schema.TableMetadata;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public final class CassandraSchemaContractCheck
        implements ApplicationRunner {

    private final CqlSession session;

    public CassandraSchemaContractCheck(CqlSession session) {
        this.session = session;
    }

    @Override
    public void run(ApplicationArguments args) {
        CqlIdentifier commerce =
            CqlIdentifier.fromCql("commerce");
        CqlIdentifier tableName =
            CqlIdentifier.fromCql("orders_by_customer_day");

        TableMetadata table = session.getMetadata()
            .getKeyspace(commerce)
            .flatMap(ks -> ks.getTable(tableName))
            .orElseThrow(() -> new IllegalStateException(
                "Schema contract missing: commerce.orders_by_customer_day"));

        if (!table.getColumns().containsKey(
                CqlIdentifier.fromCql("status"))) {
            throw new IllegalStateException(
                "Missing status column required by schema contract");
        }
    }
}
~~~

**Limitations of the example:**

- This is a **read-only check** through driver metadata and sends no DDL.
- Driver metadata may not immediately reflect newly updated schema if nodes still disagree or the session has not received schema events yet; therefore the migration job still needs a separate schema agreement gate.
- Checking that **status** exists is only a minimal check; production should also check **DataType, primary key, clustering order, keyspace RF/replication**, and critical queries.
- Failing startup can make sense when mandatory baseline schema is missing, but if the migration job has not completed yet, **block rollout in the pipeline** rather than letting hundreds of pods crash-loop.
- If startup checks run heavy queries or hit the server too frequently across every pod, the check itself creates load. Favor thorough verification in the migration job and appropriate readiness probes.
- Each Java class needs valid package/imports in a real project; the code assumes Spring Boot auto-configuration provides a suitable CqlSession bean.

### 13.1. Context Startup Success Is Not Data Verification

A Spring Boot context can open a CqlSession and create repository beans without executing an actual SELECT/INSERT. Several errors appear only when methods are invoked:

- Nonexistent column or mismatched type.
- Query missing the partition key or requiring a different access-pattern table.
- **CodecNotFoundException** for UDT/collection mappings.
- **Unavailable/ReadTimeout** due to RF/CL and replica health.
- Runtime credentials lacking SELECT/MODIFY privileges.
- Legacy null data where new code uses primitives or forbids null via validation.

Therefore, **smoke tests using real prepared CQL** against permitted synthetic data form an important deployment gate.

## 14. Post-Migration CQL and Java Verification Examples

### 14.1. Fixture Query After V002

~~~sql
-- Query a known partition without scanning the full table.
SELECT created_at, order_id, status, amount,
       fulfillment_channel
FROM commerce.orders_by_customer_day
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_day = '2026-11-21'
LIMIT 20;
~~~

Before backfill, **fulfillment_channel** on legacy rows can be null. This **does not indicate migration failure** if the contract permits null during the transitional window.

### 14.2. Java Driver Smoke Test in a Lab Environment

~~~java
import java.time.LocalDate;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class OrderSchemaSmoke {
    private final CqlSession session;

    public OrderSchemaSmoke(CqlSession session) {
        this.session = session;
    }

    public void check() {
        UUID customerId = UUID.fromString(
            "11111111-1111-4111-8111-111111111111");
        LocalDate day = LocalDate.of(2026, 11, 21);

        PreparedStatement query = session.prepare(
            "SELECT order_id, status, fulfillment_channel " +
            "FROM commerce.orders_by_customer_day " +
            "WHERE customer_id = ? AND order_day = ? LIMIT ?");

        for (Row row : session.execute(
                query.bind(customerId, day, 20)
                    .setConsistencyLevel(
                        DefaultConsistencyLevel.LOCAL_QUORUM))) {
            if (row.getUuid("order_id") == null) {
                throw new IllegalStateException(
                    "Schema/data fixture missing order_id");
            }
            // Null is valid prior to backfill.
            String channel = row.getString(
                "fulfillment_channel");
            if (channel != null && channel.isBlank()) {
                throw new IllegalStateException(
                    "Blank fulfillment_channel is invalid");
            }
        }
    }
}
~~~

**Execution conditions:** valid schema after V002, sufficient RF/DC for LOCAL_QUORUM; data fixtures must be seeded in staging if asserting row counts or expected values. The snippet above only checks query/mapping errors and minimal invariants; **it does not prove all data is valid or the whole cluster agrees on schema**.

In a real application, test a **non-empty fixture** with expected order IDs/statuses rather than treating 0 rows as PASS. TLS/auth and secrets must be configured properly for Spring Boot's CqlSession.

### 14.3. Backfilling a Row Using the Full Key

Illustrating only a fixture row verified to exist:

~~~sql
UPDATE commerce.orders_by_customer_day
SET fulfillment_channel = 'LEGACY'
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_day = '2026-11-21'
  AND created_at = '2026-11-21T08:00:00Z'
  AND order_id = 22222222-2222-4222-8222-222222222222;
~~~

**Cassandra UPDATE has upsert semantics.** If the row does not exist, UPDATE can create unintended data. Real migrations/backfills must verify the data source and target rows appropriately, use idempotent event IDs/checkpoints, and avoid unconditional UPDATEs on unverified keys.

Do not run a CQL query **scanning the entire keyspace** and issuing mass UPDATEs inside a DDL migration. Backfill load should be separated from schema migration, rate-limited, and monitored for replicas/disk/compaction.

## 15. Cassandra DDL Changes Requiring Extra Caution

| Change | Can follow expand/contract? | Risks |
|---|---|---|
| **ALTER TABLE ADD** column | Expand | Legacy null rows, new code intolerant of null, schema propagation |
| **CREATE TABLE (new)** by query | Expand | Needs sync/backfill, partition size, dual-write divergence |
| **CREATE/ALTER TYPE** UDT | Expand if compatible | Mappers/codecs across Java client versions may fail |
| **CREATE INDEX** | Conditional expand | Index backfill, resource load; does not fix every access pattern |
| **ALTER TABLE DROP** column | Contract | Column data loss, old apps fail, complex restore/rollback |
| **DROP TABLE** | Destructive | Table/data loss; no automatic recovery from replicas |
| **TRUNCATE** | Destructive | Wipes data at large scale, hard to undo |
| **Change partition/clustering key** | Usually needs a new table | Repartitioning/backfill and query rewrite, not a simple ALTER |
| **Change compaction/TTL options** | Requires separate evaluation | Background load, tombstones, retention, and disk I/O |
| **Change keyspace RF/DC** | Data infrastructure change | Replica placement, repair/streaming/capacity, availability |

This is a **methodology assessment table** and does not claim all DDL is compatible across all versions. In particular, **DROP followed by re-ADDing the same column name** can carry schema-history/tombstone and version risks; do not attempt to "revert" a column by re-adding the old name without specific version guidance.

### 15.1. TTL, Tombstones, and Compaction

If a DDL change sets **default_time_to_live** or alters retention, rows may expire under different policies. Tombstone/compaction behavior and grace periods affect data, disk usage, and repair.

**Do not use ALTER TABLE to mask slow queries** without measuring partition distribution, SSTable counts, tombstones, and I/O. Changing compaction strategy may require dedicated time/capacity and monitoring; do not bundle it with a new Java version deployment without clear justification.

### 15.2. UDTs and Collections

UDTs group structured data while remaining bound to CQL types; modifying UDT fields while multiple Java versions run concurrently can break custom codecs. Large collections or frozen structures cause heavy mutations and compaction pressure; automatic schema actions do not determine business bounds for collections.

### 15.3. Primary Key Is Physical Design, Not a Decorative Annotation

If the app shifts from querying **orders_by_customer_day** to **orders_by_status** across the entire tenant, merely adding a **findByStatus** repository method to the current entity does not magically give Cassandra an optimal index/query path. You must:

1. Determine the access pattern and cardinality.
2. Design a suitable table or index per supported version/features.
3. Run schema-creation migrations.
4. Perform bounded backfill/dual-write/reconciliation.
5. Switch Spring repository/query code once data is ready.

Do not enable ALLOW FILTERING or cluster-wide scans as a shortcut to "avoid migrating" for production workloads.

## 16. Schema Drift: When the Database and Repository Diverge

**Schema drift** occurs when the production schema no longer matches the approved contract/migrations: someone ran a manual ALTER, a job skipped a version, or an older app created a table with a different structure.

### 16.1. Signs of Drift

- Same migration version shows different CQL checksums across two deployments.
- **system_schema.columns** does not match the expected DataTypes/primary keys.
- A datacenter/node still lacks the new schema.
- Staging differs from production due to long-term use of **CREATE_IF_NOT_EXISTS**.
- The new app reports unknown column/invalid query while the old app keeps working.
- Table name matches, but options/RF differ.
- A deployment rolled back code while migrations remained on the newer version.

### 16.2. Handling Drift Safely

1. **Halt new migrations**, snapshot current metadata and node status.
2. Determine whether new business data has already been written under the drifted schema.
3. Compare contracts, checksums, schema versions, and logs from each apply run.
4. Never run RECREATE/DROP on your own to "reset it back."
5. Author a **fix-forward** migration with pre/postconditions, or an isolated restore plan if data loss occurred.
6. Verify old/new apps and data by partition key.
7. Update the migration ledger only after actual state is verified.

Avoid editing **system_schema** or system metadata tables directly as a way to "sync schema." DDL must go through supported Cassandra mechanisms.

## 17. Deployment Scenario with Timeline

Suppose the service runs **app v1**, reading `orders_by_customer_day` with two business columns **status** and **amount**. App v2 requires **fulfillment_channel**. The cluster has three nodes in local dc1, RF = 3, and critical endpoints use **LOCAL_QUORUM**.

| Illustrative time (UTC) | Action | Gate |
|---|---|---|
| 09:00 | Verify backups, RF/DC, schema, and SLO baseline | GO if preflight PASSES |
| 09:10 | Single migration job runs V002 ADD COLUMN | No other runner active |
| 09:12 | Verify metadata, schema agreement, and CQL SELECT | PASS before app v2 |
| 09:20 | Deploy a canary of app v2 | No abnormal unknown column/codec/timeout errors |
| 09:30 | Canary reads legacy rows with null channel using fallback | PASS correctness |
| 09:40 | Continue rolling deploy of app v2 | CL/latency/replicas healthy |
| 10:10 | Run rate-limited backfill | Within resource/error budget |
| 11:00 | Reconcile, enable feature flag to read new channel | PASS on backfilled data |
| Days later | Consider contraction if unused legacy objects remain | Separate approval/backup |

**Timestamps are illustrative**, not a guarantee that DDL/schema agreement always takes only two minutes. A migration must wait on verified real conditions rather than using a fixed sleep as proof.

### 17.1. If the Canary Fails at 09:20

A **CodecNotFoundException** occurs because v2's Spring Data mapping uses an unconfigured custom enum codec.

**Decision:** Halt the v2 rollout; keep the schema with the added column if v1 remains compatible. Fix the codec/dependency and retest, or roll back v2 to v1. **Do not reflexively DROP the new column**, because the schema ADD may not be the root cause and any writes already emitted must be reconciled.

### 17.2. If DDL Times Out at 09:10

The migration runner loses responsiveness after ALTER TABLE; it is unknown which nodes received the schema change.

**Decision:** Pause subsequent steps, inspect **system_schema/metadata/schema agreement** and logs, and do not immediately re-issue ALTER. Once preconditions/postconditions are verified, update the ledger or run an approved **fix-forward migration**.

### 17.3. If Backfill Causes Overload at 10:10

Read/write p99 spikes sharply, pending compactions build up, and the Java service sees ReadTimeout/Overloaded errors.

**Decision:** Pause/throttle backfill; do not silently lower consistency levels or perform bulk retries. Monitor disk/GC/partitions, reduce in-flight requests, and use checkpoints to resume later. Having applied the DDL does not mean the backfill job must finish at all costs.

## 18. Rollback, Downgrade, and Data Recovery

**Application rollback**, **rolling back a CQL migration**, and **data restore** are three distinct operations.

| Scenario | Typically viable option | What to watch out for |
|---|---|---|
| Nullable column added, app v2 broken, v1 still works | Roll back app to v1, keep additive schema | Writes from v2 and new logic may already have changed data |
| Lookup table added, sync incomplete | Disable feature flag reading new table, continue reconciliation | Do not assume lookup is complete |
| Column/table containing data was DROPPED | May require restore/recovery from an independent source | No automatic DDL transaction rollback |
| Primary key changed via new table | Point readers back to old table if still accurate | Dual-writes and new data need reconciliation |
| Compaction/TTL or RF changed | Follow version/topology runbook | Background operations may run long and consume resources |
| Cluster just upgraded Cassandra version and ran new DDL | Consult compatibility/downgrade guide | Older binaries may not understand new SSTables/schemas |

### 18.1. What Makes a Good Restore Point?

Before a destructive step:

- Complete backups/snapshots covering all nodes/tokens and relevant tables/UDTs.
- CQL schema, manifest/checksums, Cassandra version, and decryption keys.
- Clearly documented recovery point/cutoff.
- Backup stored independently of the production fault domain, with read/restore access tested.
- Restore drill executed on an isolated cluster with data reconciled across multiple partitions.
- Handling plan for valid writes after cutoff, with **RPO/RTO** communicated.

Replication does not replace backups. Erroneous DROP/DELETE DDL can propagate across replicas; **repair does not restore data validly deleted according to Cassandra semantics**.

### 18.2. Contraction Should Be Deferred

A safe strategy: only after v2 runs stably and v1's rollback window has expired should dropping old tables/columns be evaluated in a separate change window. Additional retention/audit cycles and checks for non-Spring Boot clients (batch jobs, direct Java driver, BI, CDC) may be needed. **Do not drop an object merely because one Java repository no longer references it.**

## 19. Migration Test Matrix Across Multiple Application Versions

For an **add column** migration, verify each combination:

| App | Schema S1 (before ADD column) | Schema S2 (after ADD column) | Goal |
|---|---|---|---|
| **v1** unaware of new column | Runs properly | **Must keep running properly** | App v2 rollback has a safe path back |
| **v2** references new column | May fail unknown column, **do not deploy** | Runs properly with null/legacy data | Require migration gate before deploy |
| **v2** after backfill | Not applicable | Reads new and old data per contract | Reconcile and confirm readiness |
| **Legacy batch/job** | Runs properly | Must be tested | Do not overlook non-Spring clients |
| **App vNext after contract** | Does not support old schema | Runs only after approved contract | Rollback window must have passed |

**Do not test only app v2 + schema S2.** The hardest case is usually **app v1 + schema S2** during rolling deployments and rollbacks.

### 19.1. Test Layers

**Unit tests:**

- Java type mapping: UUID, LocalDate, Instant, BigDecimal, nullable fields.
- Bucket/partition-key computation rules and null/UNSET semantics.
- Feature flag fallbacks, idempotent projections, and reconciliation.

**Integration tests with lab Cassandra:**

- Run migrations V001 → V002 → V003 on a compatible cluster/version.
- Verify schema metadata, DataTypes, partition/clustering keys, and UDTs if used.
- Read/write via Spring Data repositories and Java Driver prepared statements.
- Both app v1 and v2 against schema S2, including legacy rows missing the new column.
- Test LOCAL_QUORUM under lab RF/DC rather than extrapolating from one node to three replicas.
- Simulate partially failed migrations and reruns with postcondition checks.
- Test privileges: runtime cannot execute DDL, migration identity holds only approved privileges.

**Staging/load tests:**

- Single migration job runs while app v1 serves representative load.
- Schema agreement and health gates before canary deployment.
- Rate-limited backfill without exceeding ReadTimeout/Overloaded/compaction backlog thresholds.
- Monitor latency, repair/streaming, disk, and memory.
- Roll back app v2 to v1 without executing destructive DDL.
- Restore drill for planned contract/destructive changes.

### 19.2. Three Test Types Do Not Substitute for One Another

- A **context-load test** only proves Spring Boot builds beans, not CQL data correctness.
- A **repository save/find** proves one path, not all partitions/tombstones/TTLs/legacy rows.
- A **migration test** on one node does not prove schema agreement and replication in multi-DC production.

Clearly record the **scope of evidence**: server/driver/JDK versions, node/DC counts, RF, CL, dataset, query shapes, duration, outcomes, and untested limitations.

## 20. Common Anti-Patterns

| Anti-pattern | Why it is dangerous | Alternative |
|---|---|---|
| **schema-action: recreate** in production | Can drop/recreate, causing data loss | **none** + independent migrations |
| Treating **create-if-not-exists** as full migration | Does not verify existing schema matches contract | Versioned CQL + postconditions |
| All pods running ALTER at startup | Races and hard-to-manage privileges/history | Single migration job before deploy |
| Migration runner running concurrently in two pipelines | DDL conflicts, ledger races | Serialization/lock with an owner |
| Trusting ledger write alone as "APPLIED" | DDL and ledger are not atomic | Verify metadata and postconditions |
| Editing an applied migration file under same version | Checksum mismatch, untrustworthy history | Add a new fix-forward migration |
| Runtime app holding DROP/ALTER by default | Exposure from bugs/config attacks | Least privilege and separate secrets |
| App v2 referencing column before DDL | Unknown column/prepare errors | Expand migration before deploy |
| DROPPING columns as soon as app v2 canaries | Running app v1 / rollback fails | Contract after compatibility window |
| Changing primary key by editing annotations | Cassandra table does not repartition itself | New table, backfill, switch |
| Backfilling inside a startup bean | Pods duplicate work and overload cluster | Dedicated data job, checkpoint/rate limit |
| Changing RF in application.yml | App config creates no replica plan | DBA/SRE-controlled keyspace topology |
| Using ALLOW FILTERING instead of table migration | Expensive scans, erratic latency | Access-pattern-driven table design |
| Checking only table existence | Table may have wrong types/PK/options | Compare full schema contract |
| Manually editing system_schema on disagreement | Corrupts metadata and operational support | Use official DDL/diagnostic mechanisms |
| Bundling DROP into a rollbackable release | No path back if app v1 resumes | Multi-phase expand-contract |
| Using repair to undo bad DELETE/DDL | Repair syncs replicas without business context | Controlled backup/restore/reconciliation |

## 21. Practice Exercises and Solutions

### Exercise 1 — Which SchemaAction for Production?

A Spring Boot service has 12 pods and Cassandra tables already hold real data. The team wants startup to automatically create and align schemas, proposing **RECREATE** so the environment always matches Java entities.

**Question:** Is this appropriate? What should be configured instead?

**Suggested answer:** No. RECREATE risks destroying data. Configure **schema-action: none** for runtime, manage CQL via a separate migration job, and run tests and approvals before deploying app vNext.

### Exercise 2 — Why Is IF NOT EXISTS Insufficient?

An environment already has the **orders_by_customer_day** table, but **amount** is **text** instead of **decimal**. The migration uses **CREATE TABLE IF NOT EXISTS** with the right schema.

**Question:** Can the migration be reported as successful because the statement produced no errors?

**Suggested answer:** No. The existing table can be left untouched with the wrong type. You must inspect **system_schema.columns**, primary keys/table options, and design a fix-forward or compatible data migration. IF NOT EXISTS does not fix drifted schemas.

### Exercise 3 — App and DDL Deployment Order

App v2 reads **fulfillment_channel**. App v1 is unaware of this field. The team deploys v2 first, waits for all pods to come up, and then runs ALTER TABLE ADD.

**Question:** What is the risk? What is the right order?

**Suggested answer:** v2 can fail while preparing/querying the nonexistent column. Run the **expand migration** first, wait for schema agreement and smoke tests, then canary v2; run backfill/switch separately, and contract last.

### Exercise 4 — Application Rollback After Adding a Column

After V002 ADDs the column and v2 canaries, v2's Spring mapper fails. App v1 has been verified to work normally with schema S2.

**Question:** Do you need to run DROP COLUMN to roll back?

**Suggested answer:** Usually no. You can roll back the **application** to v1 and keep the additive column until the next fix/deploy, avoiding destructive DDL during an incident. You still need to reconcile any writes emitted by v2.

### Exercise 5 — Changing the Partition Key

A table has **PRIMARY KEY ((customer_id, order_day), created_at, order_id)**. A new requirement needs to look up orders by **order_id** without knowing the date. A developer changes the Java annotation to **@PrimaryKey orderId** and sets **schema-action: create-if-not-exists**.

**Question:** Will that make the existing table queryable by orderId?

**Suggested answer:** No. The primary key governs physical partitioning in Cassandra. You must design a new query-driven table, migrate it, backfill/dual-write/reconcile, and cut over the API; do not use ALLOW FILTERING as the default solution.

### Exercise 6 — Two Pipelines Running V002 Concurrently

One job runs ALTER TABLE ADD column successfully but dies before updating the ledger. Another pipeline sees APPLIED is missing and reruns V002.

**Question:** What is the design flaw? What should be done?

**Suggested answer:** The runner was not serialized and relied solely on the ledger; DDL and ledger writes are not atomic. Stop duplicate runners, verify metadata/postconditions, record audit/checksum once the state is verified correct, and use an orchestrator lock/owner next time.

### Exercise 7 — Backfill Causing Overloaded

V002 succeeded. An unthrottled backfill scans/sends millions of UPDATEs, pushing p99 from 120 ms to 1,800 ms and triggering Overloaded errors.

**Question:** Should Spring driver timeouts be raised to 10 seconds?

**Suggested answer:** That is not the primary fix. Stop or throttle the backfill, bound in-flight requests/rates, use key-based checkpoints, and investigate disk/compaction/hot partitions. Do not violate CL commitments to mask overload. Timeouts should only be tuned after understanding SLOs and load.

### Exercise 8 — Application Privileges

The runtime app runs with a role holding cluster-wide CREATE, ALTER, and DROP because migrations used to run inside an ApplicationRunner.

**Question:** What are the risks and how should this be fixed?

**Suggested answer:** Code bugs or credential leaks can have broad blast radius; it is hard to audit who changed the schema. Move DDL to a dedicated job with least privilege per keyspace, restrict runtime roles to DML only, rotate secrets, and enable auditing.

### Exercise 9 — Schema Agreement

Migration V002 returned success from one coordinator, yet app v2 intermittently receives unknown column errors when hitting certain nodes.

**Question:** What are possible causes? Which gate was missing?

**Suggested answer:** Some nodes may not have received the schema yet, or node/driver metadata has not refreshed; check schema agreement, node health, driver/schema events, and logs. The gate cannot be merely "DDL returned success."

### Exercise 10 — Schema and Legacy Data

App v2 adds the Java field **fulfillmentChannel** with non-null validation. Existing rows from v1 all lack this column.

**Question:** Why does it still fail after ALTER ADD succeeded?

**Suggested answer:** Adding a column does not backfill values automatically. Provide fallback/nullable mapping, run a verified backfill, and enforce non-null validation only after data has been reconciled.

### Exercise 11 — Spotting an Incomplete Test

An integration test creates 1 row and succeeds with `repository.findById` on a single-node RF 1 cluster. The team claims they have validated production RF 3, LOCAL_QUORUM, and rolling deployment migrations.

**Question:** What evidence is missing?

**Suggested answer:** Multi-node schema agreement, RF/DC behavior, quorum failures, concurrent app v1/v2 execution, rollback, backfill, TLS/auth, and performance under load. A single-node test only proves a narrow mapping/query path.

### Exercise 12 — Destructive DDL Cannot Be Rolled Back by Code Alone

A contract migration DROPs the old table immediately after deploying v2. Later v2 fails and requires rolling back to app v1, which still reads the old table.

**Question:** Why is code rollback not enough?

**Suggested answer:** The table is gone; app v1 cannot read the data simply by switching container images. You need a backup/restore or another data source, incurring RPO/RTO and downtime. Contraction should be deferred past the rollback window under separate approval.

## 22. Schema and Spring Boot Deployment Checklist

- [ ] Maintain a **schema contract** specifying keyspace, RF/DC, primary key, clustering order, DataTypes, indexes/UDTs, table options, and query rules.
- [ ] Cross-check exact versions of Spring Boot, Spring Data Cassandra, Cassandra, and the Java driver/JDK.
- [ ] In production, set **spring.cassandra.schema-action: none** in the right namespace for your Boot version; inspect effective configuration.
- [ ] Ensure no startup bean/runner executes DDL at runtime.
- [ ] Runtime roles hold no CREATE/ALTER/DROP privileges beyond approved needs.
- [ ] Migration jobs use a separate identity/secret, are serialized, and have an owner.
- [ ] Every migration has a version, checksum, preconditions, postconditions, audit trail, and approval.
- [ ] Never edit already-APPLIED migrations; add a new migration to fix forward.
- [ ] Do not treat **IF NOT EXISTS** as a schema diff or transaction.
- [ ] Verify **schema agreement**, full metadata, and keyspace replication before deployment.
- [ ] Run prepared CQL/Java smoke tests with non-empty fixtures and accurate CL/RF/DC.
- [ ] Entity annotations match composite partition keys, clustering keys, CQL types, and null semantics.
- [ ] Expand migrations do not break app v1 running during rolling deployment.
- [ ] App v2 tolerates legacy data, null fields, and eventual rollout.
- [ ] Backfill/switch are decoupled from DDL, rate-limited, checkpointed, idempotent, and reconciled.
- [ ] Avoid repository derived queries missing partition keys or using ALLOW FILTERING to paper over poor design.
- [ ] Do not bundle DROP/contract with canary while still within the rollback window.
- [ ] Prior to destructive DDL, ensure full backups, manifest/schema/keys, and restore drills exist.
- [ ] Define clear PAUSE/STOP/ROLLBACK APP/FIX-FORWARD/RECOVER triggers and decision owners.
- [ ] Monitor p95/p99 latency, Cassandra node health, errors, disk/GC, tombstones, and compaction/repair during migrations/backfills.
- [ ] Configure TLS/auth/secrets/audits properly and never log real payloads or credentials.
- [ ] Test mid-migration failures, duplicate runner protection, app v1/v2 coexistence, and rollback.
- [ ] Mark APPLIED/GO only when postconditions and smoke tests PASS, not merely on a zero script exit code.

## 23. Summary

**SchemaAction** is Spring Data Cassandra's mechanism for creating or recreating schemas from mappings during application startup. It is useful in certain test environments, but **does not replace versioned CQL migrations** when Cassandra runs in multi-instance production with real data and safe rollback requirements.

Your architecture should separate the **DDL migration job** from the **Spring Boot runtime**: migrations have dedicated privileges and execution timing and verify **schema agreement + postconditions**, while the application uses **schema-action NONE** and minimal DML privileges. For data changes, follow **expand → compatible deploy → backfill/reconciliation → switch → contract** across gated approvals rather than treating DROPs or primary-key changes as simple Java annotation edits.

In Apache Cassandra, the schema is part of the distributed architecture: **partition keys govern routing, replication and consistency levels govern serving conditions, while compaction/repair and tombstones affect load during migrations and backfills**. A sound workflow must prove **data correctness, v1/v2 application compatibility, recoverability, and controlled repeatability**, rather than merely getting the application to start up.
