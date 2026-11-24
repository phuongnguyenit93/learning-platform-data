# Dedicated Schemas, Databases, or Namespaces per Test Group in Spring Boot

> **Module:** Spring Boot – testing  
> **Knowledge Group:** Test Data  
> **Topic:** Dedicated schemas, databases, or namespaces per test group  
> **Goal:** Design data isolation across test groups (billing, shipping, search, cache, etc.), especially under parallel execution; pick the right isolation unit for SQL/NoSQL/brokers/object storage; configure Spring Boot test contexts, migrations, cleanup, and Testcontainers safely; distinguish data isolation, transactions, and access control. The runnable example uses Java 17, Maven, Spring Boot 3.5, two separate H2 databases for two test groups, plus unit tests verifying namespace keys.

## 1. Why Does Each Test Group Need Its Own Data Space?

Suppose a system has two test groups:

- **Billing tests** insert an invoice with reference `INV-001`.
- **Shipping tests** insert a shipment also with reference `INV-001`.

If both share a `records` table in one common test database, several failures occur:

1. Billing inserts first; Shipping inserts the same unique key and fails even though Shipping logic is right.
2. Shipping runs `DELETE FROM records` in `@BeforeEach`, wiping Billing's data mid-assertion.
3. A test reads leftover rows from an earlier test and unexpectedly passes or fails depending on run order.
4. CI enables parallel execution; two groups simultaneously create/drop schemas or truncate tables.
5. One group's Flyway/Liquibase migrations alter the schema another group is querying.
6. A test worker runs Redis `FLUSHDB` or Elasticsearch `DELETE index-*`, wiping data owned by other groups.
7. A test accidentally connects to a shared development/staging database, risking data loss or polluted reads.
8. A test passes only when run alone (`mvn -Dtest=...`) yet fails in the full suite (`mvn test`).

The culprit is not JUnit, Spring Boot, or an “unstable” database; it is **unscoped shared mutable state**.

The solution is giving every **test group** data resources with explicit ownership: a SQL database, SQL schema, MongoDB database, Redis key prefix, Elasticsearch index, Kafka topic/consumer group, S3 bucket/prefix, or service-appropriate mechanism. Then define who creates it, who uses it, when it is cleaned up, and what scope can safely run in parallel.

### 1.1. Guarantees to Prove

A sound isolation strategy must guarantee at least:

- **No cross-reads:** Group A never sees B's data unintentionally.
- **No cross-writes:** A never modifies or deletes resources owned by B.
- **No naming collisions:** Business keys, sequences, index names, topics, and cache keys never collide.
- **Order independence:** Tests pass whether A runs before B, B before A, or in parallel (where supported).
- **Ownership-scoped cleanup:** Cleanup touches only objects and resources owned by that group.
- **Reproducibility:** Local and CI environments build the exact same logical environment from configuration/migrations.
- **Safety:** Never use production credentials or destructive cleanup on resources not proven to be test-only.

**Note:** Data isolation does not automatically equal authorization. Two schemas inside the same PostgreSQL database can still access each other if a role has privileges; two Redis key prefixes in the same database do not stop a privileged client from reading another prefix. For security isolation, add roles/ACLs/IAM policies and matching tests.

## 2. Choosing the Isolation Unit: Test Method, Class, Group, Suite, or CI Job?

A “test group” is not necessarily one JUnit class. It may be a module, bounded context, pipeline job, infrastructure integration slice, or set of tests sharing a lifecycle.

| Scope | Example | Benefit | Cost |
| --- | --- | --- | --- |
| Per test method | Separate DB/schema for every `@Test` | Maximum isolation, virtually zero bleed | Heavy setup and migration overhead |
| Per test class | One DB for `BillingRepositoryTest` | Clear, parallelizable across classes | Per-class DB setup |
| Per group/feature | `billing` and `shipping` own separate resources | Balances speed and isolation | Tests within the group still need cleanup/transactions |
| Per suite/module | One DB for the whole integration suite | Fewer containers, faster | Classes are not automatically isolated from each other |
| Per CI job/shard | `run_942_shard_2` | Zero interference across concurrent jobs | Requires naming, provisioning, and teardown per job |
| Per environment | Local/dev/CI/staging | Blocks cross-environment leaks | Does not stop collisions within the same environment |

**Scope by risk**, rather than spinning up a separate container for every test method. Read-only tests that never mutate state can share immutable fixtures. Tests writing data, running migrations, creating/dropping indexes, or testing concurrency need tighter boundaries.

### 2.1. Expressing an Ownership Model as a Contract

```text
Test run: ci_942
  |
  +-- group: billing
  |     SQL database:   it_ci942_billing
  |     Redis prefix:   it:ci942:billing:
  |     Mongo database: it_ci942_billing
  |     ES index:       it-ci942-billing-orders
  |     Kafka topic:    it.ci942.billing.events
  |
  +-- group: shipping
        SQL database:   it_ci942_shipping
        Redis prefix:   it:ci942:shipping:
        Mongo database: it_ci942_shipping
        ES index:       it-ci942-shipping-orders
        Kafka topic:    it.ci942.shipping.events
```

Illustrative names are kept short and free of sensitive data. When the same group spans **multiple concurrent CI shards**, include a shard ID or process ID in the name. If fixed read-only data is shared, document clearly who provisions it and prevent any test from mutating it.

### 2.2. Separate Database, Separate Schema, or Prefix Only?

No single choice fits every engine:

- A dedicated SQL database isolates object names and many configuration settings more strongly than a schema, at a higher creation cost.
- A dedicated SQL schema fits when multiple groups share one PostgreSQL server/database while keeping separate table, index, and sequence names.
- A Redis key prefix is naming partitioning—not an isolated Redis database, and it will not stop full-DB flushes.
- A dedicated MongoDB database separates collections and index names, while server resources and admin privileges remain shared.
- A dedicated Elasticsearch index separates mappings and documents, while cluster settings, quotas, and nodes remain shared.
- A dedicated Kafka topic isolates messages; a dedicated consumer-group ID isolates offsets—the two are not interchangeable.

## 3. Distinguishing SQL Databases from SQL Schemas Precisely

### 3.1. Dedicated Database

In PostgreSQL, a database contains schemas, tables, indexes, and other objects; JDBC clients connect to **one database** via the connection URL.

```text
PostgreSQL server/container
   ├── database it_ci942_billing
   │       ├── schema public
   │       └── schema billing
   └── database it_ci942_shipping
           ├── schema public
           └── schema shipping
```

Pros: prevents table and sequence name collisions, simplifies per-database migration history, and cleans up cleanly by dropping **that test-only database** after closing connections.

Cons: creating databases, connection pools, and running migrations takes time; CPU, memory, and roles are still shared on the same instance. Separating databases is no proof of network or security isolation if shared credentials hold broad privileges.

### 3.2. Dedicated Schema

In PostgreSQL, multiple schemas can live inside **the same database**:

```sql
CREATE SCHEMA test_billing;
CREATE SCHEMA test_shipping;

CREATE TABLE test_billing.outbox_events (
    id BIGINT PRIMARY KEY,
    payload TEXT NOT NULL
);

CREATE TABLE test_shipping.outbox_events (
    id BIGINT PRIMARY KEY,
    payload TEXT NOT NULL
);
```

Both tables share the name `outbox_events` without colliding because they live in separate schemas. However, SQL relies on schema qualification and `search_path`:

```sql
SELECT * FROM test_billing.outbox_events;
SELECT * FROM test_shipping.outbox_events;

SHOW search_path;
SELECT current_schema();
```

When a query executes `SELECT * FROM outbox_events`, PostgreSQL resolves the table using the **current connection's** `search_path`. Therefore, schema settings must be applied consistently across every pooled connection, JPA query, and migration.

### 3.3. `search_path` Is Not a Security Boundary

`SET search_path TO test_billing` changes resolution order for **unqualified** object names. It does not forbid a sufficiently privileged client from running `SELECT * FROM test_shipping.outbox_events`. Nor does it affect native queries explicitly referencing `public.some_table`.

Therefore:

- Never treat schema naming as your sole multi-tenant security mechanism.
- Where security isolation is required, configure PostgreSQL roles, `GRANT`/`REVOKE`, and least privilege.
- Never place an untrusted schema ahead on a privileged role's `search_path`; untrusted objects on the search path pose a security risk.
- Never concatenate schema names from request headers or user input directly into SQL.
- With connection pools, never alter session `search_path` ad hoc without restoring it before returning the connection to the pool.

### 3.4. Schemas Are Not Table Prefixes

These two approaches differ:

```sql
CREATE TABLE test_billing.orders (...);
CREATE TABLE test_shipping.orders (...);
```

versus

```sql
CREATE TABLE billing_orders (...);
CREATE TABLE shipping_orders (...);
```

The first is **schema isolation**; the second is merely **prefixing table names within the same schema**. Prefixes prevent name collisions yet do not separate migration history, privileges, or search paths the way distinct schemas do.

## 4. Database/Schema Isolation Differs from Transaction Rollback

`@DataJpaTest` makes test methods transactional and rolls back by default at method end. This keeps fixture DML from lingering **inside the test transaction**, yet does not replace database or schema separation.

Example:

```java
@DataJpaTest
class OrdersRepositoryTest {
    @Test
    void createsOrder() {
        // Normally the method's transaction rolls back.
    }
}
```

This snippet illustrates annotations only, not a full test class.

Limits of rollback:

- DDL and migrations do not necessarily roll back like DML.
- Sequences/identity counters may keep incrementing despite DML rollback.
- `@SpringBootTest(RANDOM_PORT)` over real HTTP executes business transactions on a server thread; the test thread's rollback does not wrap server commits.
- `@Async`, scheduled jobs, message consumers, and connections on other threads commit independently.
- MongoDB, Redis, Kafka, and Elasticsearch do not join `@DataJpaTest` transaction rollbacks.
- Tests disabling `@Transactional` or invoking `REQUIRES_NEW` can leave persisted rows behind.
- Two test classes running migrations or dropping objects concurrently can collide even if every test method rolls back.

**Conclusion:** Transaction rollback is **one cleanup layer**, whereas dedicated databases, schemas, and namespaces define **ownership and naming boundaries**. Both work well together.

## 5. Choosing Safe, Collision-Free Namespace Names

### 5.1. Components to Include in Names

Test resource names typically need:

1. A clear `it`/`test` marker so operators immediately recognize them.
2. A CI run ID or opaque random ID, free of emails or secrets.
3. A group ID (`billing`, `shipping`).
4. A shard/process ID when multiple workers run concurrently.
5. Resource type if needed (`orders`, `sessions`, `events`).

Example:

```text
SQL database:     it_942_billing_1
PostgreSQL schema: it_billing_1
Mongo database:   it_942_billing_1
Redis prefix:     it:942:billing:1:
ES index:         it-942-billing-1-orders
Kafka topic:      it.942.billing.1.events
S3 prefix:        it/942/billing/1/
```

Avoid putting raw user input, real tenant IDs, secrets, emails, or access tokens into resource names. PostgreSQL limits identifiers to 63 bytes by default, so bound component lengths and use short hashes when necessary. Elasticsearch index names have their own rules (e.g., lowercase), and Kafka topics restrict allowed characters. Build provider-specific naming functions rather than forcing one arbitrary string everywhere.

### 5.2. Determinism and Uniqueness Rules

- **Deterministic within one run:** all classes in Group A derive the same Group A database name.
- **Unique across runs:** Run A and Run B never share namespaces when running concurrently.
- **Idempotent setup:** provisioning a schema for a run never accidentally wipes data used by another active test.
- **Scoped cleanup:** remove only resources tagged with that run/group's ownership.
- **Leases/TTLs where possible:** reap orphaned resources left after canceled or crashed CI jobs.
- **Never run global wipes:** avoid unconditional `DROP DATABASE`, `FLUSHALL`, `DELETE /*`, or deleting a bucket root.

### 5.3. Separate Names Do Not Prevent Resource-Level Contention

If groups use separate schemas on the same PostgreSQL server, they still share CPU, connection pools, locks on system catalogs, and disk I/O. If two groups use distinct Redis prefixes on an instance with `maxmemory` eviction, Group A's memory pressure can still evict Group B's keys. Distinct Elasticsearch indices on one cluster still share shards, indexing throughput, and refresh load.

When tests are sensitive to latency, concurrency, or failover, move to stronger isolation such as dedicated containers or clusters in a stable performance environment.

## 6. Runnable Spring Boot Project: Two Groups Using Two H2 Databases

This core example uses **Java 17, Maven, Spring Boot 3.5.0**. It defines two test groups:

- `BillingDataTest` uses H2 database `billing_group`.
- `ShippingDataTest` uses H2 database `shipping_group`.

Both use the **exact same entity/repository and the exact same unique business key** to show keys never collide across separate databases. It also includes `NamespaceKeysTest` testing a pure Java helper that builds per-run, per-group Redis key prefixes (no Redis server required).

**Important:** this H2 example proves isolation only at the JDBC database URL and JPA persistence level within H2. It **does not** prove PostgreSQL dialects, Flyway migrations, Redis TTLs, or security ACLs. Sections 9–12 discuss scaling up to real environments.

### 6.1. Directory Structure

```text
isolated-test-data-lab/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/isolation/
    │       ├── IsolationLabApplication.java
    │       ├── AuditRecord.java
    │       ├── AuditRecordRepository.java
    │       └── NamespaceKeys.java
    └── test/
        └── java/com/example/isolation/
            ├── BillingDataTest.java
            ├── ShippingDataTest.java
            └── NamespaceKeysTest.java
```

Every `public` class/interface sits in its matching file under `com.example.isolation`. No HTTP server or external database is required. H2 creates named databases automatically when each test context boots.

### 6.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>isolated-test-data-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

The Spring Boot parent manages compatible Hibernate, H2, and JUnit versions. H2 stays in `test` scope; no production database credentials appear in the project. Each test class specifies its exact JDBC URL and instructs Spring Boot **not** to replace it with another embedded DB.

### 6.3. `IsolationLabApplication.java`

```java
// src/main/java/com/example/isolation/IsolationLabApplication.java
package com.example.isolation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class IsolationLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(IsolationLabApplication.class, args);
    }
}
```

No `@RestController` or `@Service` is required because this lesson focuses on test data isolation and JPA slices.

### 6.4. `AuditRecord.java`

```java
// src/main/java/com/example/isolation/AuditRecord.java
package com.example.isolation;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "audit_records")
public class AuditRecord {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "reference_code",
            nullable = false,
            unique = true,
            length = 64)
    private String referenceCode;

    @Column(name = "owner_group",
            nullable = false,
            length = 32)
    private String ownerGroup;

    protected AuditRecord() {
    }

    public AuditRecord(
            String referenceCode,
            String ownerGroup) {
        this.referenceCode = referenceCode;
        this.ownerGroup = ownerGroup;
    }

    public Long getId() {
        return id;
    }

    public String getReferenceCode() {
        return referenceCode;
    }

    public String getOwnerGroup() {
        return ownerGroup;
    }
}
```

`reference_code` is unique **per database**, not globally across the server. Two isolated databases can each store `shared-ref` with zero conflict.

### 6.5. `AuditRecordRepository.java`

```java
// src/main/java/com/example/isolation/AuditRecordRepository.java
package com.example.isolation;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AuditRecordRepository
        extends JpaRepository<AuditRecord, Long> {

    Optional<AuditRecord> findByReferenceCode(
            String referenceCode);
}
```

The repository knows nothing about group or database names; the Spring test context's `DataSource` determines where SQL executes. That is why tests must verify **connection metadata**, not just assert business rows.

## 7. Two JPA Test Classes: Isolated DB Configurations

### 7.1. `BillingDataTest.java`

```java
// src/test/java/com/example/isolation/BillingDataTest.java
package com.example.isolation;

import java.sql.Connection;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest(properties = {
        "spring.datasource.url=jdbc:h2:mem:billing_group;DB_CLOSE_DELAY=-1",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.datasource.username=sa",
        "spring.datasource.password=",
        "spring.jpa.hibernate.ddl-auto=create-drop"
})
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
class BillingDataTest {

    @Autowired
    DataSource dataSource;

    @Autowired
    AuditRecordRepository repository;

    @Test
    void usesBillingDatabaseAndSavesReference() throws Exception {
        try (Connection connection = dataSource.getConnection()) {
            assertThat(connection.getMetaData().getURL())
                    .contains("mem:billing_group");
        }

        assertThat(repository.count()).isZero();

        AuditRecord saved = repository.saveAndFlush(
                new AuditRecord("shared-ref", "billing"));

        assertThat(saved.getId()).isNotNull();
        assertThat(repository.findByReferenceCode("shared-ref")
                .orElseThrow().getOwnerGroup())
                .isEqualTo("billing");
    }

    @Test
    void billingFixtureIsScopedToCurrentTransaction() {
        assertThat(repository.count()).isZero();

        repository.saveAndFlush(
                new AuditRecord("bill-only", "billing"));

        assertThat(repository.count()).isEqualTo(1L);
    }
}
```

**Why is each setting needed?**

- `jdbc:h2:mem:billing_group` creates a uniquely named in-memory H2 database.
- `DB_CLOSE_DELAY=-1` keeps the DB alive in the JVM after closing the last connection, preventing the database from vanishing between pool checkouts—though it **requires explicit isolation/cleanup** in long suites because the DB persists across test contexts.
- `@AutoConfigureTestDatabase(replace=NONE)` preserves the configured `DataSource`; if replaced with a random embedded DB, the group database name would be lost.
- `@DataJpaTest` loads the JPA slice and rolls back DML after each test method by default.
- `ddl-auto=create-drop` generates the schema in **this DB** when the context bootstraps; it does not test Flyway migrations.
- Asserting JDBC metadata proves the test actually connects to `billing_group`, rather than guessing from the class name.
- In both methods, repository count starts at 0 per this example's rollback and context behavior.

### 7.2. `ShippingDataTest.java`

```java
// src/test/java/com/example/isolation/ShippingDataTest.java
package com.example.isolation;

import java.sql.Connection;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest(properties = {
        "spring.datasource.url=jdbc:h2:mem:shipping_group;DB_CLOSE_DELAY=-1",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.datasource.username=sa",
        "spring.datasource.password=",
        "spring.jpa.hibernate.ddl-auto=create-drop"
})
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
class ShippingDataTest {

    @Autowired
    DataSource dataSource;

    @Autowired
    AuditRecordRepository repository;

    @Test
    void usesShippingDatabaseAndSameBusinessKey() throws Exception {
        try (Connection connection = dataSource.getConnection()) {
            assertThat(connection.getMetaData().getURL())
                    .contains("mem:shipping_group");
        }

        assertThat(repository.count()).isZero();

        repository.saveAndFlush(
                new AuditRecord("shared-ref", "shipping"));

        assertThat(repository.findByReferenceCode("shared-ref")
                .orElseThrow().getOwnerGroup())
                .isEqualTo("shipping");
    }

    @Test
    void shippingDataDoesNotDependOnBillingFixture() {
        assertThat(repository.count()).isZero();

        repository.saveAndFlush(
                new AuditRecord("ship-only", "shipping"));

        assertThat(repository.count()).isEqualTo(1L);
    }
}
```

Both classes use `shared-ref`, yet connect to distinct database URLs. This shows that **identical business keys do not conflict across isolated DBs**. Tests also confirm each row reads back with the owner group belonging to that connection.

**Limitation of this check:** Because `@DataJpaTest` rolls back after each method by default, `count() == 0` alone **is not enough** to prove database separation; inspecting the JDBC URL provides direct proof. To verify data persisted across transactions or threads, build an integration test without default rollback using explicit setup and cleanup.

### 7.3. Could Test Context Caching Mix Up the Two Databases?

Spring TestContext caches `ApplicationContext` instances when test configurations match. Here, the two classes declare **different `@DataJpaTest(properties=...)`**, giving each a distinct context key. Never mutate an external static `currentDatabaseName` variable assuming Spring will rebuild the context or `DataSource`.

With `@DynamicPropertySource`, values supplied by lambdas can change while a context remains cached, especially across a base test class and subclasses. If a cached context holds a `DataSource` pointing at Group A while Test B attempts to swap the dynamic URL to B, isolate the context configuration or use `@DirtiesContext` intentionally to force a rebuild—never rely on global mutable variables.

## 8. NamespaceKeys: Key-Prefix Isolation for Redis and Caches

In a shared Redis server or cache, you rarely spin up a fresh server per unit test. Using a deterministic `run + group + resource` prefix prevents key collisions. Still, prefixes **do not protect against `FLUSHDB`/`FLUSHALL` and provide no ACL isolation**.

### 8.1. `NamespaceKeys.java`

```java
// src/main/java/com/example/isolation/NamespaceKeys.java
package com.example.isolation;

import java.util.regex.Pattern;

public final class NamespaceKeys {

    private static final Pattern PART =
            Pattern.compile("[a-z][a-z0-9_-]{0,31}");

    private static final Pattern ID =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");

    private NamespaceKeys() {
    }

    public static String session(
            String run, String group, String subject) {
        if (run == null || !PART.matcher(run).matches()
                || group == null
                || !PART.matcher(group).matches()
                || subject == null
                || !ID.matcher(subject).matches()) {
            throw new IllegalArgumentException(
                    "Invalid namespace token");
        }

        return "it:" + run + ":" + group
                + ":session:" + subject;
    }
}
```

This is a **pure Java naming helper** without any Redis connection. It validates tokens against an allowlist and builds a run+group-scoped key. If an app accepts arbitrary user IDs containing special characters, encode or hash them safely and deterministically rather than loosening the allowlist indefinitely.

### 8.2. `NamespaceKeysTest.java`

```java
// src/test/java/com/example/isolation/NamespaceKeysTest.java
package com.example.isolation;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class NamespaceKeysTest {

    @Test
    void createsDeterministicKeyForOneGroup() {
        assertThat(NamespaceKeys.session(
                "run42", "billing", "user_1"))
                .isEqualTo(
                        "it:run42:billing:session:user_1");
    }

    @Test
    void changesWhenRunOrGroupChanges() {
        String billing = NamespaceKeys.session(
                "run42", "billing", "user_1");
        String shipping = NamespaceKeys.session(
                "run42", "shipping", "user_1");
        String nextRun = NamespaceKeys.session(
                "run43", "billing", "user_1");

        assertThat(billing).isNotEqualTo(shipping);
        assertThat(billing).isNotEqualTo(nextRun);
    }

    @Test
    void rejectsUnsafeNamespaceComponent() {
        assertThatThrownBy(() ->
                NamespaceKeys.session(
                        "run42", "billing:other", "user_1"))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("Invalid namespace token");
    }
}
```

**Limits of these three tests:** They verify **key naming logic**, not whether a real Redis server sets TTLs, preserves raw JSON bytes, executes atomic `SET NX`, evicts keys, or enforces ACLs. Those guarantees require real Redis integration tests.

### 8.3. Running the Complete Sample Project

```bash
java -version
mvn -version

# Run both database groups and the namespace utility:
mvn test

# Run a single test group:
mvn -Dtest=BillingDataTest test
mvn -Dtest=ShippingDataTest test

# Unit test without JPA context:
mvn -Dtest=NamespaceKeysTest test
```

The project contains **7 JUnit `@Test` methods**: 2 in `BillingDataTest`, 2 in `ShippingDataTest`, and 3 in `NamespaceKeysTest`. The JPA tests use in-JVM H2; Redis is not launched. Exact Maven/Surefire output varies by environment, so no fixed stdout is claimed here. No build was executed while authoring this guide; `mvn test` is the command to run after creating the files.

### 8.4. Why Not Use One H2 Database and Drop Tables Between Groups?

When test classes run sequentially, wiping tables before each group can *look* like isolation. Under parallel execution, Group A can lose rows mid-assertion while Group B cleans up. Two distinct JDBC database names eliminate that interference at the **database resource level**.

Furthermore, a single H2 `mem:db` within one JVM does not isolate schema migrations or index names across groups connecting to it. Even when using H2 for integration tests, assign explicit owner/group names and lifecycles just like any real database.

## 9. Scaling Up to PostgreSQL Testcontainers: Real Databases per Group

H2 illustrates the principle. When production runs PostgreSQL and tests must verify native SQL, schema migrations, locks, row types, or JDBC semantics, run a real PostgreSQL engine in a container.

### 9.1. Adding Optional Dependencies

To add PostgreSQL Testcontainers integration tests to Section 6's project, declare these dependencies (without duplicating existing entries):

```xml
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-testcontainers</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
```

The Spring Boot parent manages compatible versions. `test` scope for the PostgreSQL driver suffices for a test-only variant; if production uses PostgreSQL, move the driver to appropriate runtime dependencies instead of `test` scope only.

### 9.2. Class-Specific PostgreSQL Container — Optional Complete Example

Create `src/test/java/com/example/isolation/BillingPostgresTest.java` **only after** adding the dependencies and ensuring Docker is available. This class runs on its own PostgreSQL container:

```java
// src/test/java/com/example/isolation/BillingPostgresTest.java
package com.example.isolation;

import java.sql.Connection;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.test.annotation.DirtiesContext;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest(properties = {
        "spring.jpa.hibernate.ddl-auto=create-drop",
        "test.group=pg-billing"
})
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
@Testcontainers
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class BillingPostgresTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("billing_group");

    @Autowired
    DataSource dataSource;

    @Autowired
    AuditRecordRepository repository;

    @Test
    void reallyUsesPostgresAndOwnDatabase() throws Exception {
        try (Connection connection = dataSource.getConnection()) {
            assertThat(connection.getMetaData()
                    .getDatabaseProductName())
                    .isEqualTo("PostgreSQL");
            assertThat(connection.getCatalog())
                    .isEqualTo("billing_group");
        }

        repository.saveAndFlush(
                new AuditRecord("pg-shared-ref", "billing"));

        assertThat(repository
                .findByReferenceCode("pg-shared-ref")
                .orElseThrow().getOwnerGroup())
                .isEqualTo("billing");
    }
}
```

**Important technical note:** The right import for `@DirtiesContext` is `org.springframework.test.annotation.DirtiesContext` from Spring Test. The class above uses the matching import.

**How it works:**

- `PostgreSQLContainer` boots real PostgreSQL; `withDatabaseName("billing_group")` creates the named test database inside the container.
- `@ServiceConnection` supplies the container's JDBC connection details without touching production URLs.
- `replace=NONE` keeps the container `DataSource` instead of letting the JPA slice swap in H2.
- `getDatabaseProductName()` and `getCatalog()` confirm the connection targets the expected engine and database.
- `@DirtiesContext(AFTER_CLASS)` prevents a cached Spring context from pointing at a stopped container when later test classes run. It is a clear option for class-scoped containers, though it carries rebuild cost and is not needed in every test design.
- A `ShippingPostgresTest` needing a separate database can use its own container with `withDatabaseName("shipping_group")` and distinct configuration properties, though that consumes more resources than schema-per-group on one server.

**Special caution on caching and containers:** A JUnit `static @Container` has class-scoped lifetime, whereas Spring TestContext may cache an `ApplicationContext` beyond the class and reuse it after the container stops. Never pair a per-class static container with a shared cached Spring context without an explicit lifecycle strategy. Depending on your suite, prefer Spring-bean-managed containers, suite-wide singleton containers, or `@DirtiesContext` where appropriate.

### 9.3. Testcontainers Is a Real Resource, Not Total Isolation

A separate container per group isolates the DB server, yet does not make tests parallel-safe if they share external Redis, Kafka, files, or ports. If one class calls global `System.setProperty` or mutates shared static state, DB isolation cannot prevent that interference.

Meanwhile, the standard Testcontainers JUnit 5 extension is generally validated for **sequential test execution**; when enabling JUnit parallelism, consult Testcontainers documentation and adopt appropriate lifecycle coordination. Never rely on test-class execution order to keep a container alive.

## 10. PostgreSQL Schema-per-Group When Sharing One Server

This is more resource-efficient than one PostgreSQL container per group, though it demands strict schema provisioning, connection-pool setup, and migration coordination.

### 10.1. Creating Schemas Before Spring Context / JPA Startup

Suppose a **single test-only PostgreSQL database** named `it_suite` runs:

```sql
CREATE SCHEMA IF NOT EXISTS test_billing;
CREATE SCHEMA IF NOT EXISTS test_shipping;
```

These statements must run **before** Hibernate validation or Flyway migrations needing those schemas. You can use Testcontainers `withInitScript` pointing to a SQL resource in `src/test/resources`, or a bootstrap step executing schema creation via a test-only admin connection.

**Wrong lifecycle:** Creating the schema inside `@BeforeEach` after Flyway/JPA has already tried to bootstrap causes bean creation to fail immediately. Tie schema provisioning to container/DB initialization before the Spring application context boots.

### 10.2. Connecting to the Right Schema in JDBC and Hibernate

With the PostgreSQL JDBC driver, `currentSchema` sets the connection's search path. **Illustrative example without production credentials**:

```properties
# Illustrative values only; replace with a TEST-ONLY DB host/port.
spring.datasource.url=jdbc:postgresql://127.0.0.1:5432/it_suite?currentSchema=test_billing
spring.jpa.properties.hibernate.default_schema=test_billing
spring.flyway.schemas=test_billing
spring.flyway.default-schema=test_billing
spring.jpa.hibernate.ddl-auto=validate
```

For the shipping group, consistently change `test_billing` to `test_shipping`. Supply the driver, Testcontainers connection details, and project configuration as needed. Never mix runtime container URLs with hardcoded localhost assumptions in CI.

- `currentSchema` controls lookup of unqualified SQL identifiers on the JDBC connection.
- `hibernate.default_schema` helps Hibernate qualify SQL/table mappings when appropriate.
- `spring.flyway.schemas`/`default-schema` control Flyway target schemas and history table placement when Flyway is enabled.
- `ddl-auto=validate` checks mappings against migration-created schemas without generating tables itself.
- For native SQL explicitly specifying `public.table`, the search path **does not redirect** the query. Audit native queries in code and tests.

### 10.3. Verifying the Active Schema with Real SQL

```sql
SELECT current_database();
SELECT current_schema();
SHOW search_path;

SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema IN ('test_billing', 'test_shipping')
ORDER BY table_schema, table_name;
```

Each group should report database `it_suite` and its own `current_schema`. Never assert only property strings; a `DataSource` wrapper or pool can point elsewhere. With multiple `DataSource`s, check each live bean.

### 10.4. Flyway/Liquibase and Schema History

Each group should keep its own migration history or explicit migration configuration. If Billing and Shipping both write Flyway history into `public.flyway_schema_history` for identically named tables in different schemas, they can collide or think another group's migrations already ran.

Rules:

1. Create schemas first.
2. Assign migration locations and history table scope per group.
3. Run migrations per group and version.
4. Assert tables, indexes, and constraints reside in the intended schema.
5. Validate Hibernate mappings against the matching `DataSource`/schema.
6. Drop a schema **only when no active group still uses it**.

Liquibase also supports default schemas and tracking tables, though property names and APIs differ. Never copy Flyway properties directly for Liquibase.

### 10.5. Never Concatenate Raw Group Input into `CREATE SCHEMA`

SQL identifiers cannot use `?` JDBC parameters like values do. If a provisioning helper builds dynamic schema names, derive names from a trusted allowlist/slug/hash, quote identifiers with a proper API/procedure, and restrict the test role's permissions. Never interpolate an arbitrary `X-Tenant` header directly into `DROP SCHEMA ... CASCADE`.

## 11. Isolation in NoSQL and Other Services

Services lacking SQL schemas still have **namespace** concepts at various layers. Pick boundaries that match each provider's actual guarantees.

### 11.1. MongoDB: Separate Databases or Collections

Example:

```properties
spring.data.mongodb.database=it_ci942_billing
```

The shipping group uses a different MongoDB database name. This works well because MongoDB collections, indexes, and validators live inside a database. `@DataMongoTest` must confirm the instance/URI is test-only via Testcontainers `@ServiceConnection` or explicit properties.

Warnings:

- `@DataMongoTest` does not roll back writes by default like `@DataJpaTest`. Use explicit fixture cleanup or isolated databases.
- `dropDatabase()` is safe only when the database **is verified to belong to the current run**; never run it on shared/dev DBs.
- Index setup/migrations may execute on context startup; establish database/collection scope beforehand.
- MongoDB transactions/sessions require matching topology (e.g., a replica set for multi-document transactions).
- Two MongoDB databases still share server resources, and admin users can still access both.

To conserve databases, prefix collection names by group. Ensure test queries and repositories point to the prefixed collection and manage index definitions separately.

### 11.2. Redis: Key Prefixes, Never Indiscriminate `FLUSHDB`

Keys:

```text
it:run42:billing:session:user_1
it:run42:shipping:session:user_1
```

do not collide. In Spring Cache, configure cache name or key prefixes; with `RedisTemplate`, use deterministic key builders/serializers. **Every operation**—`get`, `set`, `delete`, `scan`, pipelines, Lua scripts, and background cleanup—must honor the prefix; adding it in only one code path is insufficient.

Warnings:

- `FLUSHALL` wipes the entire server; `FLUSHDB` wipes the entire logical DB. Never run them on a shared Redis instance.
- Redis Cluster does not support logical database separation via `SELECT n` like standalone Redis; do not rely on database indexes as portable isolation.
- Key prefixes do not provide ACL isolation. For Redis Enterprise or vendor namespaces, check the exact contract.
- TTLs and evictions share the memory budget; Group A's keys can trigger eviction of Group B's keys.
- Prefix-based cleanup should be bounded and run **after the group finishes**, typically via `SCAN` with a controlled pattern; avoid `KEYS *` on large shared instances.
- If using Redis Cluster hash tags, avoid accidentally routing all test load onto a single hot hash slot.

### 11.3. Elasticsearch/OpenSearch: Index/Alias per Group

Example:

```text
it-ci942-billing-orders
it-ci942-shipping-orders
```

Each index holds independent mappings and settings; avoid fixed names like `products-test` when multiple jobs run concurrently.

Checklist:

- Test setup creates the intended mappings, analyzers, and aliases.
- Queries target the group's index rather than overly broad `it-*` wildcards.
- Cleanup deletes **only the exact indices created**, never another job's test indices.
- Elasticsearch is near-real-time: newly indexed documents are not guaranteed searchable until refresh; use explicit refresh policies or bounded awaits.
- Separate indices do not isolate cluster CPU, shard limits, security roles, or quotas; performance/failover tests need stronger isolation.
- When using aliases, verify each alias points strictly to indices owned by that group.

### 11.4. Kafka: Topics and Consumer Group IDs Are Two Separate Layers

A distinct Kafka consumer group ID isolates **offset bookkeeping**, not message storage. If two test groups subscribe to the same topic, both still receive each other's messages depending on filters, subscriptions, and offsets. Ensure:

- Dedicated topics per group or unique run/shard suffixes where appropriate.
- Dedicated consumer group IDs per group/subscription.
- Controlled topic auto-creation, partition counts, retention, and cleanup.
- Assertions on event keys, correlation IDs, schema versions, and consumption offsets.
- Never delete a shared topic just to reset test data.

Example:

```text
Billing topic:   it.ci942.billing.events
Billing group:   it.ci942.billing.consumer

Shipping topic:  it.ci942.shipping.events
Shipping group:  it.ci942.shipping.consumer
```

**Shared topic + distinct group ID does not isolate messages.** If architecture forces a shared topic, filter by correlation/test-run ID on consumers, while keeping in mind shared retention, races, and cleanup.

### 11.5. RabbitMQ, S3/MinIO, and Filesystems

- RabbitMQ supports virtual hosts: separate vhosts isolate queues and exchanges by namespace, though users, roles, and server resources still require management.
- Object storage can use dedicated buckets or prefixes like `it/run/group/`. When using prefixes, ensure all list/delete operations restrict to the prefix and never delete the bucket root.
- Local filesystem: create isolated temporary directories per test method/class using JUnit `@TempDir`; never share a fixed path like `./tmp/test-output.json` across workers.
- Database rows are not the only shared state: environment variables, static caches, `System.setProperty`, clocks, ports, and files can also cause cross-test interference.

## 12. Setup/Cleanup Lifecycle and Preventing “One Test Wiping Another”

An ownership-driven workflow:

```text
CI job starts
   │
   ├─ allocate run id (unique)
   │
   ├─ provision namespace per group
   │    ├─ DB/schema/collection/index/topic/key prefix
   │    └─ run schema/index migrations
   │
   ├─ start Spring test context with fixed group config
   │
   ├─ execute tests (parallel only when supported)
   │
   ├─ stop producers/consumers/background workers
   │
   ├─ cleanup only resources owned by group
   │
   └─ final cleanup/lease for orphaned resources
```

### 12.1. Cleanup Must Verify Ownership

Commands like this are **destructive**:

```sql
DROP SCHEMA test_billing CASCADE;
```

Run it only against a verified test-only database once no tests still use that schema. Never execute it automatically from a JVM sharing a PostgreSQL server with development or staging.

For MongoDB, `dropDatabase()` is safe only when both the connection string and database name are confirmed test-only; for Redis, avoid `FLUSHDB`; for Elasticsearch, delete named indices; for S3, delete strictly within the owned bucket/prefix.

### 12.2. Enforce Single Ownership

If Test Group A provisions a schema/index while Group B also tries to “ensure exists” or “clean up” the same resource, parallel jobs will race. Assign lifecycle management to one provisioning layer while test methods create only scoped data within that boundary.

A robust workflow tracks:

- **owner-run-id**
- **resource-name**
- **creation-time**
- **group/shard**
- **cleanup-policy**
- **TTL/lease**
- **environment marker (test-only)**

Store this metadata in CI artifacts or a test-resource registry rather than mixing it into business tables.

### 12.3. Never Use Fixed Sleeps to “Wait for Cleanup”

`Thread.sleep(1000)` does not guarantee a Kafka consumer stopped, Elasticsearch refreshed, or PostgreSQL released connections. Use bounded waits driven by real conditions: container readiness, connection health, index status, consumer assignment, observable event counts, or drained queues, with explicit timeouts and clear failure diagnostics.

## 13. Spring Boot TestContext Cache, `@DynamicPropertySource`, and `@DirtiesContext`

Spring TestContext caches `ApplicationContext` instances to accelerate suites. When two classes share identical configuration, they reuse the same context; that optimization is safe unless URLs or namespaces change in mutable state outside the context cache key.

### 13.1. Never Mutate a Global Namespace Field in `@BeforeEach`

Anti-pattern:

```java
static String currentGroup = "billing";

@BeforeEach
void setGroup() {
    currentGroup = "shipping";
}
```

If `DataSource`, Flyway, or `RedisTemplate` already bootstrapped before `@BeforeEach`, changing `currentGroup` will not rebuild beans; tests will still hit the old namespace. This is an illustrative snippet only—never use it in real projects.

### 13.2. `@DynamicPropertySource` Timing and Cache Semantics

`@DynamicPropertySource` registers dynamic properties such as a PostgreSQL container's JDBC URL:

```java
@DynamicPropertySource
static void configure(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
}
```

This snippet requires a `static postgres` container and imports, not a standalone test class. Spring Framework documentation warns that if a base class defines an inherited dynamic property method whose returned values differ across subclasses, context caching can reuse the wrong context; `@DirtiesContext` or distinct configurations prevent that mismatch.

**Separate contexts by resource identity** (URL/schema/group), not just the displayed test class name. When multiple tests in a group share a context, keep the container/namespace alive **at least** as long as the context can be reused.

### 13.3. `@DirtiesContext` Is Not Default Data Cleanup

`@DirtiesContext` marks the Spring `ApplicationContext` as dirty so it closes and rebuilds per class/method mode; it does not drop MongoDB collections, delete Redis prefixes, or remove Kafka topics. Use it when bean definitions or context configuration change; use SQL cleanup, transactions, or isolated DBs for data.

Putting `@DirtiesContext` on every test slows down suites and hides poor ownership design. Prefer explicit group configuration and controlled context caching.

### 13.4. How Testcontainers Lifecycles Interact with Spring Caching

A JUnit `static @Container` has class-scoped lifetime, whereas Spring's context cache can outlive the class and reuse a `DataSource` or client pointing at a stopped container.

Options:

- Per-class container + `@DirtiesContext(AFTER_CLASS)` to close the context on time.
- Container managed as a Spring bean so it shares the context's lifetime when supported.
- Suite-wide singleton container (explicitly managing start/stop without misusing per-class `@Container`).
- Distinct test configuration identities per resource so contexts are never mis-reused.
- For parallel execution, verify Testcontainers/JUnit version support; never assume the static-container pattern is automatically parallel-safe.

## 14. Parallel Execution: Isolation Must Cover Every Shared Resource

JUnit 5 can run test methods or classes concurrently. When enabled, audit these hazards:

- Two classes sharing a PostgreSQL schema and running `TRUNCATE` on tables.
- Two groups running Flyway migrations concurrently on one schema.
- Redis key prefixes missing the CI run ID, causing concurrent jobs to overwrite each other.
- Fixed Kafka topic names and consumer `group.id`s causing rebalances and offset collisions.
- Fixed Elasticsearch index names where Test A deletes the index Test B is querying.
- Static mutable test fixtures, fixed temp files, and shared ports.
- A static Testcontainers field stopping while another group's Spring context still holds references to it.
- Same-named in-memory H2 databases in **one JVM**, allowing separate contexts to share the same named database.

### 14.1. When Is Parallel Execution Safe?

Once resources are partitioned by ownership with zero problematic global mutable state, running classes or groups in parallel becomes viable. Within a single group sharing one database, run methods sequentially or isolate fixture keys and transactions cleanly.

Never claim “parallel-safe” solely because tests use `@Transactional`. SQL cleanup scripts, async consumers, and out-of-transaction writes can still collide.

### 14.2. Verify Parallel Safety Empirically

A practical QA check is running the full suite repeatedly with randomized ordering and your intended CI parallelism flags. Runs should pass regardless of execution order, not just by luck once. On failure, log run ID, group ID, resource name, and relevant SQL/consumer operations for diagnosis, **without logging secrets or PII**.

## 15. Do Migrations, Index Creation, and Schema History Share the Same Scope?

Creating a namespace is not enough if migration tools still point to default schemas or global metadata.

### 15.1. SQL Schema-per-Group

With Flyway, verify `schemas`, `default-schema`, `locations`, and the history table location. With Liquibase, verify default schemas and tracking tables. With Hibernate, check `default_schema` and DDL auto mode.

A test targeting schema A while Flyway migrates into `public` can appear green if Hibernate also reads `public`, secretly causing Group B to share the same tables. Always assert `current_schema()`, the SQL catalog, and migration history placement.

### 15.2. MongoDB Indexes per Group

When Groups A and B use separate MongoDB databases or collections, ensure indexes are created on each target collection. Annotations like `@CompoundIndex` describe mappings while auto-index creation depends on configuration; never assume one global index initialization covers all databases.

### 15.3. Elasticsearch Mappings per Index

Each dedicated index must be created with expected settings, analyzers, and mappings. Changing only the index name in queries without provisioning mappings lets dynamic mapping alter the schema and invalidate production parity.

### 15.4. Kafka Schema Registry and Topics

Topic-per-group does not separate Schema Registry subjects if the subject naming strategy uses a fixed name. When testing serializers and Schema Registry, verify per-group subject names/versions and cleanup policies, or use isolated registry instances where required.

## 16. Test Assertions That Prove Isolation Better Than `count == 0`

`repository.count() == 0` can pass simply because of an earlier transaction rollback or an overly broad cleanup wiping another group's rows. To genuinely prove isolation, combine:

1. **Identity:** verify the live JDBC URL, `current_database`, `current_schema`, Mongo database, Redis prefix, index, or topic.
2. **Positive own data:** Group A writes and reads its own rows via real repositories/clients.
3. **Negative foreign data:** Group B never sees Group A's data (even on a shared server with separate namespaces); avoid global wildcard queries.
4. **Same business key:** A and B can insert identical keys concurrently when designed to be independent.
5. **Non-destructive cleanup:** deleting A's data leaves B's data intact, verified in a controlled integration scenario.
6. **Order independence:** run groups in reverse order and under supported CI parallelism.
7. **Scoped migrations:** verify schemas, indexes, and constraints exist in the intended scope.
8. **No production access:** datasource/connection metadata matches test-only settings with restricted credentials.

In our H2 project, asserting URL metadata and reusing `shared-ref` verifies **connection-identity isolation**. To prove cross-schema cleanup safety in PostgreSQL, provision both scopes in a limited-privilege integration test, clean up A, and assert B's rows remain—running this extended destructive check strictly against an ephemeral DB.

## 17. Troubleshooting: Common Failures

### Issue A. Two Test Classes Share `jdbc:h2:mem:testdb`

**Symptom:** Order-dependent tests or duplicate unique keys across classes.  
**Fix:** Assign distinct DB names per group/run and verify the JDBC URL from the live `DataSource`. `DB_CLOSE_DELAY=-1` keeps named databases alive inside the JVM, making distinct names even more essential.

### Issue B. `@DataJpaTest` Replaces the PostgreSQL DataSource with H2

**Symptom:** “Postgres” tests pass even though native JSONB queries never actually ran.  
**Fix:** When using a test-only PostgreSQL container, set `@AutoConfigureTestDatabase(replace=NONE)` and assert `DatabaseMetaData.getDatabaseProductName()`/`current_database()`.

### Issue C. Test B Still Connects to Test A's DB

**Symptom:** `DataSource` metadata does not match Group B.  
**Fix:** Never mutate static variables after context bootstrap; separate context configurations, inspect `@DynamicPropertySource` inheritance/caching, and use `@DirtiesContext` where genuinely required.

### Issue D. Spring Context Connects to a Stopped Container

**Symptom:** Initial tests pass, then later test classes fail with connection refused.  
**Fix:** Align Testcontainers lifecycles with the Spring context cache via context-managed beans, suite singletons, or `@DirtiesContext(AFTER_CLASS)` on class-scoped containers.

### Issue E. Flyway Migrates into `public` Despite Wanting `test_billing`

**Symptom:** Tables land in the wrong schema or migration history collides.  
**Fix:** Provision schemas before context startup; align JDBC `currentSchema`, Hibernate `default_schema`, and Flyway `schemas`/`default-schema`; verify against the real PostgreSQL catalog.

### Issue F. `@BeforeEach` Creates the Schema Too Late

**Symptom:** JPA bootstrap/validation fails before any test method executes.  
**Fix:** Create schemas in container init scripts, database bootstrap hooks, or Spring initialization before Flyway/Hibernate runs.

### Issue G. Running `TRUNCATE` or `DROP SCHEMA CASCADE` on Another Group

**Symptom:** Flaky random failures in parallel runs.  
**Fix:** Give every group ownership metadata and clean up only owned resources; restrict destructive operations strictly to test-only DBs.

### Issue H. Redis `FLUSHDB` Wipes Keys Across All Groups

**Symptom:** Cache tests fail whenever another suite cleans up.  
**Fix:** Prefix keys per group/run and clean up by prefix or TTL; never flush a shared DB. If a full flush is needed, provision a dedicated Redis instance.

### Issue I. Kafka Consumer Group ID Is Unique, Yet Topic Is Shared

**Symptom:** Tests consume messages published by other groups.  
**Fix:** Use per-group topics or strict correlation/filtering; unique `group.id` values isolate offsets only, not message storage.

### Issue J. MongoDB Tests Leak Data Across Methods

**Symptom:** Unique index violations or order-dependent failures.  
**Fix:** `@DataMongoTest` does not roll back automatically; isolate databases/collections and add explicit cleanup.

### Issue K. Wildcard Elasticsearch Delete Wipes Another Job's Index

**Symptom:** Search tests fail abruptly with index-not-found errors.  
**Fix:** Include run/group/shard in index names and delete **only the exact indices created**, never system-wide wildcards.

### Issue L. Tests Pass Alone but Fail in Parallel

**Symptom:** Missing rows, duplicate keys, or stale static caches.  
**Fix:** Audit every shared resource, decide which groups can run concurrently, enforce unique namespaces, use bounded waits, and keep tests order-independent.

### Issue M. Schemas Are Separate, Yet Roles Read Every Schema

**Symptom:** Security tests falsely conclude “Tenant B cannot read Tenant A.”  
**Fix:** Naming isolation is not authorization; verify `GRANT`/`REVOKE` permissions and principal/tenant policies.

### Issue N. Test Cleanup Corrupts Staging Data

**Symptom:** `DROP DATABASE` or `deleteAll` hits an unintended environment.  
**Fix:** Enforce test-only connection strings, restricted roles, explicit environment markers, and allowlisted resource names; **never** execute destructive cleanup on shared staging or production.

## 18. Test Data Isolation Strategy Review Checklist

- [ ] Is “test group” clearly defined (class/module/job/shard)?
- [ ] Does every group have explicit resource ownership names with run/shard suffixes when parallelized?
- [ ] Do tests verify the actual engine and JDBC URL/schema/namespace?
- [ ] Are production URLs and secrets absent from test code and CI configs?
- [ ] Does `@DataJpaTest` avoid silently replacing the intended `DataSource` with an embedded DB?
- [ ] Do Spring TestContext caching and dynamic properties keep group configs separate?
- [ ] Do Testcontainers lifecycles match Spring context lifecycles?
- [ ] Are SQL migrations, indexes, and history placed in the right schema/database?
- [ ] For PostgreSQL schemas, are `currentSchema`, `search_path`, Hibernate, and Flyway settings aligned?
- [ ] Are SQL schema names never mistaken for authorization boundaries?
- [ ] Is test rollback never treated as cleanup for async, HTTP, NoSQL, or broker writes?
- [ ] Are MongoDB databases/collections separated and cleaned within scope?
- [ ] Do all Redis key paths enforce prefixes without calling `FLUSHDB` on shared servers?
- [ ] Do Elasticsearch indices/aliases have unique names and proper mappings?
- [ ] Are both Kafka topics **and** consumer groups scoped properly?
- [ ] Are S3 buckets/prefixes and temp directories safe from cross-deletion?
- [ ] Are resource names sanitized/hashed without leaking PII or permitting SQL identifier injection?
- [ ] Does setup finish before schema-dependent Spring beans boot, and teardown wait for background tasks to stop?
- [ ] Have parallel tests been validated with full-suite runs and randomized ordering?
- [ ] Does cleanup verify `owner-run-id` and operate strictly on test-only resources?

## 19. Exercises and Applied Scenarios

### Exercise 1. Same Business Key, Different Databases

Run `BillingDataTest` and `ShippingDataTest`. Both write `shared-ref` with different `ownerGroup` values. Observe the JDBC metadata assertions proving they target two named H2 databases, and explain why `count() == 0` alone is insufficient.

### Exercise 2. Intentionally Sharing One H2 Database

On an isolated practice branch, change both classes to `jdbc:h2:mem:shared_group` and disable rollback if you want to observe leftover state. Design safe test-only cleanup without production data. Explain how class-level context caching, `create-drop`, and rollback can mask collisions during a simple run.

### Exercise 3. Separating Schemas in PostgreSQL

In a test-only PostgreSQL container, create `test_billing` and `test_shipping` before context startup; configure `currentSchema`/Flyway/Hibernate per group. Insert the same reference into both schemas, verify `current_schema()` and `information_schema.tables`, then clean up schema A and assert schema B retains its data.

### Exercise 4. Per-CI-Run Redis Prefixes

Implement a key builder from run ID + group + subject; write tests verifying identical user IDs never collide between `run42`/`run43` or `billing`/`shipping`. Then run against a Redis container to verify `GET`/`SET`/`TTL` on prefixed keys.

### Exercise 5. MongoDB per Database

Using MongoDB Testcontainers, configure two separate database names. Seed a document with the same `_id` in both; assert each group's repository/template sees only its own document. Never call `dropDatabase()` unless the URL/database is verified test-only.

### Exercise 6. Kafka Topic Isolation

Create two topics with unique CI run/group suffixes and two consumer group IDs, publishing the same event key. Assert consumers receive only their topic's messages. Then demonstrate that changing **only** `group.id` on a shared topic fails to isolate messages.

### Exercise 7. Parallelism and TestContext Cache

Enable JUnit/Testcontainers parallelism as supported, run the suite repeatedly, and log `DataSource` URLs and group names. If context reuse leaks state, fix lifecycles or scoping rather than adding `Thread.sleep` or global wipes.

## 20. Self-Check Questions

**Question 1.** Why is a dedicated database stronger than table prefixes alone?

**Answer:** A database establishes a catalog and connection boundary; table prefixes only rename objects inside the same schema/database. Still, a dedicated database does not automatically enforce security if shared privileged credentials are used.

**Question 2.** Does PostgreSQL `search_path` block a user from querying another schema?

**Answer:** No. It only affects unqualified object name resolution; access restrictions require `GRANT`/`REVOKE`, roles, and explicit security policies.

**Question 3.** If two `@DataJpaTest` classes both roll back, do they still need resource isolation?

**Answer:** Often yes—for migrations/DDL, sequences, shared cleanup scripts, async operations, or tests running outside the same transaction. Rollback does not replace ownership isolation.

**Question 4.** Why is `@BeforeEach` the wrong place to create a PostgreSQL schema needed for Hibernate validation?

**Answer:** Spring `ApplicationContext`, JPA, and Flyway usually initialize before test method lifecycle hooks run; schemas must be provisioned prior to that stage.

**Question 5.** Is adding `@AutoConfigureTestDatabase(replace=NONE)` always safe?

**Answer:** No. If the configured `DataSource` points to production, it will not be replaced. Use it only alongside verified test-only configurations like explicit test H2 URLs or Testcontainers.

**Question 6.** If two groups use distinct Redis key prefixes, can one group safely call `FLUSHDB`?

**Answer:** No. `FLUSHDB` wipes the entire logical database regardless of prefix; use prefix-scoped cleanup or a dedicated Redis instance.

**Question 7.** Does sharing a Kafka topic with distinct consumer group IDs isolate messages?

**Answer:** No. Consumer groups separate offsets and processing coordination; both groups still read from the same topic stream.

**Question 8.** How can Spring context caching conflict with a static Testcontainers `@Container`?

**Answer:** The container stops after its test class finishes while the cached Spring context remains reused by later classes, leaving the `DataSource` pointing at a dead server. Align lifecycles properly.

**Question 9.** Does `@DataMongoTest` automatically roll back every write after each method?

**Answer:** No, not by default like JPA transactional tests; isolate databases/collections or perform explicit cleanup.

**Question 10.** To prove Test Group A never deletes Group B's data, what should you assert?

**Answer:** Resource identity/ownership, controlled pre- and post-cleanup assertions across both scopes, and absence of unscoped destructive operations—tested strictly in a test-only environment.

## 21. Official References

- [Spring Boot 3.5 – Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@DataJpaTest`, test databases, transactions, and test slices.
- [Spring Boot 3.5 – Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): `@ServiceConnection`, container lifecycles, and Spring context caching.
- [Spring Framework – Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): test `ApplicationContext` reuse.
- [Spring Framework – `@DynamicPropertySource`](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-dynamicpropertysource.html): dynamic properties and inheritance.
- [Testcontainers – JUnit Jupiter](https://java.testcontainers.org/test_framework_integration/junit_5/): static `@Container`, lifecycle, and parallel support notes.
- [Testcontainers – Container Lifecycle and Spring](https://testcontainers.com/guides/testcontainers-container-lifecycle/): per-class container and Spring context cache caveats.
- [PostgreSQL – Schemas](https://www.postgresql.org/docs/current/ddl-schemas.html): namespaces, schema qualification, `search_path`, and security.
- [pgJDBC – Connection Parameters](https://jdbc.postgresql.org/documentation/use/): `currentSchema` JDBC option.
- [Flyway – Schemas and Default Schema](https://documentation.red-gate.com/fd/flyway-schemas-setting-277579234.html): migration scope and history.
- [Spring Data MongoDB – Testing/Mapping](https://docs.spring.io/spring-data/mongodb/reference/): repositories, converters, collection names, and index management.
- [Redis – Key Naming and SCAN](https://redis.io/docs/latest/commands/scan/): key traversal and cleanup considerations.
- [Elasticsearch – Index Management](https://www.elastic.co/guide/en/elasticsearch/reference/current/index-mgmt.html): indices, aliases, and mappings.
- [Apache Kafka – Consumer Configs](https://kafka.apache.org/documentation/#consumerconfigs): `group.id` and consumer group behavior.

**Conclusion:** Proper test data isolation requires aligning **scope, resource identity, startup, migrations, transactions, context caching, cleanup, and access safety**. Use dedicated databases or schemas for SQL groups, provider-native namespaces/collections/indices/topics for other stores, include run/group/shard identifiers in names, and strictly avoid global destructive commands. A test is truly independent only when it cannot read, modify, or delete another group's resources within its declared isolation boundary.
