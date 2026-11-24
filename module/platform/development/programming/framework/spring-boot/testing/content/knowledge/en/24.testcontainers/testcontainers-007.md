# Distinguishing Shared Containers from Shared Data

A Spring Boot testing team wants their suite to run faster, so they use **one PostgreSQL Testcontainer across multiple test methods or test classes**. That decision can make sense: starting a database takes time, and JUnit and Spring TestContext provide mechanisms to reuse resources. However, after sharing a container, a `findAll()` test starts returning two records instead of one, a duplicate-key test fails because of a leftover record, or parallel tests delete each other's data.

**Root cause:** *sharing a container* is an **infrastructure lifecycle** decision; *sharing data* is a **state and data ownership** decision. The two are not synonymous. You can share a single PostgreSQL, Kafka, or Redis container while keeping every test's data independent, provided you design databases/schemas/namespaces, fixtures, transactions, and cleanup properly. Conversely, each test getting a fresh Java object or a fresh Spring `ApplicationContext` does not guarantee that external data is clean.

This Knowledge article belongs to the **Testcontainers** group of the **Spring Boot – testing** module. The hands-on example uses **Java 17+, Spring Boot 3.5.x, Testcontainers 1.21.x, JUnit Jupiter 5, Spring JDBC, and PostgreSQL 16**. It intentionally lets **two test classes share the same container bean configuration** without depending on each other's data: each method generates its own `owner_token`, every query filters by owner, and cleanup deletes only rows owned by that method.

> **Rule to remember:** **Share infrastructure resources to cut cost; isolate test state to preserve assertion meaning.** When a test fails, you must know whether it is a bug in the code under test or leaked data from another test.

## 1. Learning outcomes

After this lesson, you will be able to:

- Define precisely "shared container," "shared database," "shared schema," "shared collection/topic/index," "shared data," and "shared Spring context."
- Distinguish static `@Container`, instance `@Container`, Spring-managed container beans, singleton containers, and experimental reusable containers.
- Understand that **a living container does not mean reset data**; context caching is not a database reset tool.
- Choose among **per-row/owner, per-schema, per-database, and per-container** isolation based on risk.
- Write JDBC tests on a PostgreSQL Testcontainer using `owner_token` and a composite unique constraint.
- Create independent fixtures per test, assert through owner-filtered queries, and run verified cleanup.
- Explain why `TRUNCATE`, `DROP SCHEMA`, `FLUSHDB`, and deleting shared topics/indexes can break other tests when infrastructure is shared.
- Know when `@Transactional` rollback isolates writes and when it **does not roll back** writes from HTTP server threads or non-transactional systems.
- Recognize the error of a cached Spring context connecting to a static Testcontainer already stopped by JUnit.
- Design parallel-test strategies, resource locks, Docker/CI isolation, and crash-resilient cleanup.
- Use a decision matrix to balance startup time, test fidelity, risk, parallelism, and debuggability.

## 2. Two questions to separate right from the start

**Question A — How is infrastructure managed and reused?**

- Who starts the container: the JUnit extension, a Spring bean, a manual singleton, or shared infrastructure?
- When is it started/stopped: per method, per class, per `ApplicationContext`, per JVM, or per CI job?
- Who supplies host/port/credentials: `@ServiceConnection`, `@DynamicPropertySource`, or a manual JDBC URL?
- Do one or many test classes connect to that service instance?

**Question B — How is each test's state protected?**

- Which rows/keys/documents/topics belong to a specific test?
- Do tests query the entire table/collection/keyspace or always filter by namespace?
- Do fixtures collide on `UNIQUE` constraints, idempotency keys, consumer groups, offsets, or cache keys?
- When a test fails/times out or runs in parallel, how is data cleaned up?
- Are there asynchronous side effects running after the method finishes?

Question A is mostly about **lifecycle/performance**; Question B is about **correctness/isolation**. A good answer to A does not automatically solve B.

## 3. Model of the "shared" layers

```text
JVM / Gradle test worker process
  |
  +-- Spring TestContext cache
  |     +-- ApplicationContext A
  |     |     +-- DataSource / connection pool
  |     |     +-- Spring-managed PostgreSQLContainer
  |     +-- ApplicationContext B (may be separate if config differs)
  |
  +-- Test class A
  |     +-- method A1: owner_token = run-A1
  |     +-- method A2: owner_token = run-A2
  |
  +-- Test class B
        +-- method B1: owner_token = run-B1

Docker daemon
  |
  +-- PostgreSQL container (one DB process)
        +-- database test_db
              +-- schema public
                    +-- table ledger_entries
                          +-- rows belonging to run-A1
                          +-- rows belonging to run-A2
                          +-- rows belonging to run-B1

One PostgreSQL process can hold multiple independent data groups.
```

In the diagram, two test classes *can* share an `ApplicationContext` and container if Spring TestContext cache considers them the same configuration. However, **never rely on having the same container ID/host port as a data assertion**. Even if two classes spin up two separate contexts with their own containers, the data isolation design remains valid.

### 3.1. Table of things commonly mislabeled as "shared"

| What is shared | What is actually shared | What does **not** happen automatically |
|---|---|---|
| Docker image cache | Image layers on the host | Does not share runtime data across running containers |
| Docker daemon | API/runtime creating containers | Does not mean all tests hit the same service instance |
| One container | Service process and storage inside | Does not mean all tests share one fixture/owner |
| One database inside a container | Tables, schemas, transactions | Does not automatically filter queries per test |
| One Spring `ApplicationContext` | Beans/caches/connection pool | Does not reset the database between methods |
| One Java test class instance | Fields on the instance | Does not isolate external state |
| One JUnit static field | Reference inside the JVM | Does not automatically reset rows/keys |
| One Redis instance | Keyspace and TTL | Does not prevent key collisions between two tests |
| One Kafka broker | Topics/partitions/offset storage | Does not prevent shared consumer group contention |
| One reusable container | Process across multiple test runs | Does not erase data between executions |

## 4. Contamination example: one container, two tests touching the same data

Test A:

```java
// COUNTEREXAMPLE: data written without scope or cleanup.
jdbc.update(
        "INSERT INTO accounts(external_id, balance) VALUES (?, ?)",
        "CUST-001", 100);
```

Test B:

```java
// COUNTEREXAMPLE: assumes the database is always empty.
assertEquals(0L, jdbc.queryForObject(
        "SELECT COUNT(*) FROM accounts", Long.class));
```

If A and B share one PostgreSQL container and database, B depends on execution order. If both use the same `external_id`, the database `UNIQUE` constraint can raise a duplicate-key error. If A and B run in parallel, a table-wide cleanup can delete rows right before the other method's assertion.

**Do not "fix" this with `@TestMethodOrder`** so "B always runs before A." Test ordering is not data isolation. A strong test should express:

- Its own data.
- The initial state of that scope.
- Queries scoped to that data.
- Postconditions and cleanup for that scope.
- Clear failure when DB or code breaks an invariant.

## 5. JUnit static `@Container`: shared **within one test class**

With Testcontainers **1.x**, the JUnit 5 extension works as follows:

```java
@Testcontainers
class OrderJdbcTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Test
    void first() { /* ... */ }

    @Test
    void second() { /* ... */ }
}
```

This is a snippet, not a complete runnable file.

- `@Testcontainers` activates the Jupiter extension.
- Static `@Container` is started before test methods and stopped after the class.
- Both methods access **the same running PostgreSQL instance**.
- **Rows, sequences, tables, and cached database state do not automatically reset** between methods.
- If A inserts and commits, B can see that row until it is deleted.
- JUnit creating a new test object per method by default **does not create a new database**.

**Trap:** the `@Testcontainers` extension is documented as tested only for sequential execution; running tests in parallel through this extension is unsupported and can cause unexpected side effects. If parallelism is desired, design lifecycle/isolation explicitly and validate thoroughly.

## 6. JUnit instance `@Container`: different cost, still requires DB understanding

With a **non-static** field:

```java
@Testcontainers
class ExpensivePerMethodTest {

    @Container
    final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Test
    void first() { /* ... */ }

    @Test
    void second() { /* ... */ }
}
```

Under JUnit Jupiter's default `PER_METHOD` test-instance lifecycle, the extension starts/stops the container around each method. This generally isolates storage since each method gets a fresh container, but:

- Startup is noticeably slower than a static container.
- If the test class uses `@TestInstance(PER_CLASS)` or a custom lifecycle, verify extension behavior accordingly.
- A cached Spring context can retain a `DataSource` pointing to a stopped container if configurations mismatch.
- Container-per-method does not protect side effects **outside** that container, such as an HTTP sandbox, filesystem, or shared bucket.
- If experimental reusable containers are enabled, "stop" semantics differ from ephemeral containers.

**Do not choose an instance container simply thinking it is "100% safe."** It is an isolation choice with a cost, and data ownership still needs to be understood.

## 7. Spring-managed container bean and context cache

Spring Boot 3.5 enables:

```java
@TestConfiguration(proxyBeanMethods = false)
class PostgresTestConfig {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgresContainer() {
        return new PostgreSQLContainer<>("postgres:16-alpine");
    }
}
```

The snippet above requires imports for `TestConfiguration`, `Bean`, `ServiceConnection`, and `PostgreSQLContainer`. When the container is managed as a **Spring bean**, Boot starts the container before dependent beans and stops it after context teardown, aligning its lifecycle with connection pools/`DataSource`s that need it.

**Important:**

1. The bean is created once per matching `ApplicationContext`, not necessarily once per JVM.
2. Spring TestContext **caches** contexts; multiple test classes with the same configuration key can reuse it.
3. When a context is reused, its container stays alive with the context.
4. Context caching does not run `DELETE FROM` or reset business fixtures between test methods.
5. If contexts differ due to profiles, properties, or bean overrides, another container can be created.

This is a **lifecycle** choice, not a **data isolation** strategy. Row/schema/database scopes or cleanup are still required.

### 7.1. Does `@ServiceConnection` keep data clean?

No. It supplies `JdbcConnectionDetails`/connection info to Spring auto-configuration; it does not delete rows. With a typed PostgreSQL container, Boot detects the service and connects via the dynamic host/port. If you choose `@DynamicPropertySource` instead, you register JDBC URL/username/password manually and ensure the container has started; that mechanism does not reset data either.

### 7.2. Static container + cached context bug

Test class A uses a static `@Container`; JUnit stops the container after class A. Yet the Spring `ApplicationContext` may remain in cache and be reused by class B with the same context config. The `DataSource` still points to the port of the stopped container; class B gets `Connection refused`. This is a **lifecycle bug**, not data contamination. Spring Boot recommends container beans or `@ImportTestcontainers` when the lifecycle must match the cached context.

## 8. Singleton containers vs reusable containers: two different concepts

### 8.1. Singleton within one JVM

A base class with a static field manually starts the container once and shares it across subclasses:

```java
// Do not put @Container and use the JUnit extension on this snippet
// if you intend to manage the singleton lifecycle manually.
abstract class SharedPostgresBase {

    static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>("postgres:16-alpine");

    static {
        POSTGRES.start();
    }
}
```

This pattern can reduce startups across test classes, but requires careful management of lifecycle, data isolation, and context caching. **Never combine `@Container`/`@Testcontainers` with a manual singleton**: the JUnit extension will stop it when the first class finishes.

### 8.2. Reusable containers across multiple test runs

Testcontainers has an experimental `withReuse(true)` feature, opted into via separate host config. The container can stay running across **multiple JVM/test executions** instead of stopping after the suite.

This is completely different from static `@Container` or Spring context caching.

| Reuse type | Typical scope | Keeps data into the next run? |
|---|---|---|
| Static `@Container` | Methods within the same class | While the container stays alive |
| Spring bean container | Tests sharing the cached context | While the cached context/container stays alive |
| Manual singleton | Multiple classes within one JVM | Within the singleton's lifetime |
| `withReuse(true)` experimental | Potentially across multiple processes/test runs | **Possibly**, requires deliberate reset |
| Image layer cache | Multiple image pulls/startups | Not container runtime data |

Testcontainers documentation states reusable containers are **not suitable for CI** due to cleanup/networking limitations. Do not enable this experimental feature as a blanket CI speedup. When local development allows reuse, treat leftover data as a real possibility, enforce namespaces/resets, and never put production credentials into reusable containers.

## 9. Shared container does not mean a single shared dataset

There are multiple isolation strategies on one container:

```text
PostgreSQL container A
  ├── database class_one
  │     └── schema public
  │           └── rows of test group one
  ├── database class_two
  │     └── schema public
  │           └── rows of test group two
  └── database shared_test_db
        ├── schema it_a (test class A)
        ├── schema it_b (test class B)
        └── schema public
              └── ledger_entries
                    ├── owner_token a-...
                    └── owner_token b-...
```

One container process **can separate databases, schemas, or rows**. You do not have to pick one strategy for the entire repository:

- Repository tests can often use transaction rollback or row-level data scoping.
- Migration tests need a fresh database/schema to protect DDL.
- Concurrency/locking tests sometimes **intentionally** share a table to observe real contention.
- Tenant-isolation tests need multiple tenants in the same backend while asserting strict separation.
- Chaos/restart tests may need an independent container so they do not drop connections for other suites.

## 10. Four levels of data isolation on one backend

| Level | Example | Pros | Limitations |
|---|---|---|---|
| **Per-row/test owner** | `owner_token`/`test_run_id` in every row | Cheap, supports many tests in one DB | Every read/write must be scoped; global DDL/truncate remains dangerous |
| **Per-schema** | `it_a.ledger_entries`, `it_b.ledger_entries` | Isolates tables/sequences and many schema objects | Configuring `search_path`, migrations, permissions, and pools is complex |
| **Per-database** | `db_test_a`, `db_test_b` in one Postgres container | Stronger catalog/schema/user separation | Must create DBs, migrate, and manage separate DataSources; still shares CPU/process |
| **Per-container** | Each class/method gets its own `PostgreSQLContainer` | Best isolation of service process/storage | Higher startup/RAM/disk/CI cost |

There is no absolute best level. **Use the cheapest level that still detects the target risk**, without trading determinism for a few seconds of startup time.

### 10.1. When row-level scope alone works

Appropriate when:

- Tables/migrations are identical across all tests.
- Business queries have a clear tenant/owner key.
- Destructive schema changes are not being tested.
- Tests can delete the exact rows they created.
- No background task runs without owner filtering.
- Tests do not require a globally empty database.

**Unsuitable** if tests intentionally create/drop tables, alter indexes/roles/schemas, or run destructive migrations; those affect the entire schema and cannot be isolated with `owner_token`.

## 11. Row-level scope: filter across reads, writes, and cleanup

Give each test method a token:

```java
String owner = "it-" + UUID.randomUUID();
```

Then in the repository:

```sql
INSERT INTO ledger_entries(owner_token, business_key, amount_minor)
VALUES (?, ?, ?);

SELECT COUNT(*) FROM ledger_entries
WHERE owner_token = ?;

DELETE FROM ledger_entries
WHERE owner_token = ?;
```

**Why isn't a random ID enough?** A test could still run `SELECT COUNT(*) FROM ledger_entries` or `findAll()` and expect 1. Random primary keys avoid ID collisions, **they do not exclude other tests' data from whole-table queries**.

A production multi-tenant repository must enforce tenancy at real boundaries, not merely via test helpers. The demo intentionally takes `owner_token` as a parameter for visibility. If a production app gets tenant IDs from JWT/identity, test injection/authorization and prevent clients from passing arbitrary tokens to access another tenant's data.

### 11.1. Composite uniqueness

Instead of table-wide `UNIQUE(business_key)`, when business rules allow the same key across independent tenants:

```sql
CONSTRAINT uq_owner_business UNIQUE (owner_token, business_key)
```

The same `ORDER-1` from two different tests/tenants will not collide. However, **never weaken a production unique constraint just to make tests easier**. If the business key must be globally unique, generate unique keys per test method or use DB/schema isolation.

### 11.2. The token is test data, not a security boundary

`owner_token` is a tool to assign fixture ownership. It does not replace authentication or PostgreSQL Row-Level Security. Broken SQL missing a `WHERE` clause could still read other rows; a test passing with a matching owner token does not by itself prove production API authorization.

## 12. Per-schema isolation in PostgreSQL

You can create a fresh schema:

```sql
CREATE SCHEMA it_run_a;
CREATE TABLE it_run_a.ledger_entries (...);
```

and point connections/test contexts to the right `search_path`, Hibernate `default_schema`, or fully qualified table names.

**However:**

- DataSource connection pools reuse sessions; manually changing `SET search_path` in one test without resetting can leak schemas to another test.
- Spring Boot `spring.sql.init.*`, Flyway/Liquibase, and JPA defaults must target the right schema.
- Foreign keys, sequences, extensions, and DB roles may live in another schema and are not automatically copied.
- `DROP SCHEMA ... CASCADE` is destructive; only run it on test-owned schemas after closing connections/jobs referencing it.

A reliable strategy is creating a **schema per test class/run before building the context**, configuring connection initialization, and dropping the schema once no active users remain. Do not share one DataSource while individual methods mutate `search_path` on a global connection pool without strict controls.

## 13. Per-database isolation inside one container

One PostgreSQL process can serve multiple databases:

```sql
CREATE DATABASE it_run_a;
CREATE DATABASE it_run_b;
```

Each database has independent catalogs, schemas, and tables. Creating databases must happen on an administrative/test-only connection, cannot run inside a regular PostgreSQL transaction, and requires proper privileges. Spring Boot's `DataSource` must point to the right DB before auto-config/migrations run.

**Pros:** two test classes can share one Postgres container while each gets its own DB and independent schema migrations. **Cost:** creating DBs, running migrations, and managing separate connection pools; the Postgres process/RAM/CPU remain shared.

With Testcontainers `PostgreSQLContainer.withDatabaseName("name")`, you are normally configuring **one database for that container**. Do not assume calling `withDatabaseName` differently on the same Java object after startup creates a second database. Multiple databases in one container require deliberate SQL/configuration setup.

## 14. Per-container isolation: when is it worth the cost?

Dedicated containers suit:

- Tests modifying database roles, cluster settings, or extensions.
- Destructive migrations.
- Database restart/failure injection.
- Replication or network partition scenarios.
- Tests with global state hard to clean within a narrow scope.
- Different PostgreSQL versions or driver behaviors.
- Cases where a shared backend cannot guarantee deterministic data.

Use one container per **class** when methods in a class share the same engine/version and clean up independently. Use one container per **method** when each method genuinely needs a fresh process/storage. **Do not use per-method containers for 100 tests checking pure Java business logic**, as the suite will become very slow.

### 14.1. Some data lives outside PostgreSQL

If a service writes to PostgreSQL while also storing Redis keys or publishing Kafka events, a dedicated PostgreSQL container **does not reset Redis or Kafka**. Isolation is needed for every involved backend. "Each test gets a new Postgres container" does not equal a completely fresh end-to-end environment.

## 15. Resetting via `DELETE`, `TRUNCATE`, transaction rollback, or migrate?

| Approach | What is reset | Pros | Risk in a shared container |
|---|---|---|---|
| `DELETE ... WHERE owner_token=?` | Rows matching owner | Safe for other tests, readable | Must track all related tables/foreign keys |
| `DELETE FROM table` | All rows in table | Simple in a dedicated DB | Deletes other tests' data |
| `TRUNCATE table` | Whole table, can reset identity | Fast for dedicated DBs | Breaks concurrent tests; lock/schema effects |
| `@Transactional` JUnit rollback | Writes in test-managed transaction | Fast for repository tests | Does not cover HTTP/async/other services |
| `@Sql` setup/cleanup | Script-defined data | Explicit fixtures | Overly broad scripts or wrong transaction phase |
| `DROP SCHEMA/DATABASE` | Schema/DB + metadata | Deep reset | Safe only with exclusive namespace |
| Fresh container | Entire service storage | Strong fidelity/isolation | Startup/resource cost |
| New random key/namespace | Objects owned by test | Better parallelism support | Orphans on test kill if no teardown |

**Do not choose `TRUNCATE ... RESTART IDENTITY CASCADE` simply because a test expects count=0.** It touches multiple objects and can block or wipe data belonging to other tests in a shared database. If a database belongs exclusively to a class/run with no concurrent users, `TRUNCATE` can be reasonable under a verified ownership policy.

## 16. Does `@Transactional` keep data clean automatically?

Spring TestContext by default rolls back a test method annotated with test-managed `@Transactional` when the method completes, provided a matching transaction manager exists.

Example:

```java
// Snippet: JDBC test runs inside the test-managed transaction.
@Test
@Transactional
void repositoryWritesAreRolledBack() {
    repository.insert(...);
    assertEquals(1L, repository.count(...));
}
```

**Critical limitations:**

1. Test-managed rollback does not clean data committed during setup outside the transaction or by background tasks.
2. With `@SpringBootTest(webEnvironment=RANDOM_PORT)`, HTTP requests run on server threads/transactions; JUnit's client transaction **does not roll back** writes committed by the server.
3. Code using `REQUIRES_NEW` commits independently; the test transaction does not roll back an already-committed inner transaction.
4. Redis, Kafka, HTTP gateways, filesystems, and emails do not participate in JDBC transactions.
5. Sequences/identity values can advance even across rollbacks; never assert contiguous IDs.
6. Test methods asserting only "DB is empty after test" do not prove the service has proper `@Transactional` behavior: JUnit itself may have rolled back.

**Use rollback when it matches the boundary**, and use cleanup/namespaces when it does not.

## 17. Spring `@DirtiesContext` is not a general data reset

`@DirtiesContext` marks an `ApplicationContext` as ineligible for caching, triggering teardown/rebuild as needed. It helps when **context/beans** themselves were mutated beyond safe reset, not as a database wipe command.

- If the PostgreSQL container is a Spring bean and the context closes, that container usually stops; ephemeral container data disappears with its lifecycle.
- If the DB lives on an external instance, manual singleton, or reusable container, `@DirtiesContext` **does not** delete rows.
- If another context shares/uses a bean container, teardown can disrupt running tests.
- Continual context rebuilds inflate startup time and can mask broken cleanup.

**Ask the right question:** What became dirty — Spring beans, database rows, static Java state, or the container process? Reset that exact thing instead of slapping `@DirtiesContext` on every test hopefully.

## 18. Parallel tests: isolation does not appear automatically from UUIDs

Using `UUID.randomUUID()` as an owner avoids ID collisions, yet global operations still clash:

- `DELETE FROM ledger_entries` without `WHERE`.
- `TRUNCATE ledger_entries` or `DROP TABLE`.
- Index creation/deletion, schema migrations, role changes.
- Kafka topic deletion, Redis `FLUSHDB`, Elasticsearch index deletion.
- Shared filesystem paths, shared test clocks, or static singletons.
- Background consumers/jobs not filtering by owner.
- `@DirtiesContext` closing a context while another test still uses it.

Spring TestContext explicitly cautions against running tests in parallel when they mutate **shared services**; the JUnit Testcontainers extension likewise makes no general parallel-execution guarantee.

### 18.1. Three options to control concurrency

1. **Per-method resource scope**: rows/keys/queues have exclusive namespaces.
2. **JUnit resource locks or sequential execution** for tests touching schemas or global state.
3. **Per-container/per-schema sandboxes** for tests needing destructive operations.

Snippet locking a shared resource:

```java
// Snippet requiring JUnit resource-locking imports:
@ResourceLock("postgres-schema-public")
class MigrationContractTest {
    // Tests creating/dropping indexes or running ALTER TABLE must not run concurrently.
}
```

**Note:** `@ResourceLock` coordinates only tests within the JUnit engine/JVM sharing that resource name; it **does not lock another CI job** or another JVM. If multiple CI jobs share a DB, separate namespaces/instances or external coordination are required.

## 19. Runnable example set: shared infrastructure, independent data

We will build **a small Spring Boot project** demonstrating how to share a container safely. The domain table `ledger_entries` has fields:

- `id`: identity key generated by PostgreSQL.
- `owner_token`: per-test fixture identifier.
- `business_key`: business key that may match across different owners.
- `amount_minor`: positive integer.

Constraints:

```sql
UNIQUE(owner_token, business_key)
CHECK(amount_minor > 0)
```

The composite `UNIQUE` constraint models a **namespace-scoped key contract**. If the real product requires `business_key` to be globally unique, **never alter the constraint just to make tests pass**: instead generate unique business keys per method or use schema/database isolation.

**Two test classes** share the same Spring configuration `SharedPostgresTestConfig`. Each method creates its own owner and cleans up by owner. They do not need to assert having the same **container ID** to prove data isolation; they prove that **even when infrastructure is shared, queries and cleanup never mix data**.

### 19.1. Directory tree

```text
shared-container-isolated-data/
  settings.gradle
  build.gradle
  src/main/java/com/example/isolation/
    IsolationApplication.java
    LedgerRepository.java
  src/main/resources/
    schema.sql
  src/test/java/com/example/isolation/
    SharedPostgresTestConfig.java
    OwnedRowsSupport.java
    SharedContainerIsolationATest.java
    SharedContainerIsolationBTest.java
```

All Java files share the package `com.example.isolation`. Complete file code blocks appear in Sections 20–25; snippets outside that range are not standalone runnable files.

## 20. Gradle: Spring Boot 3.5 + Testcontainers 1.x

**`settings.gradle`**

```groovy
rootProject.name = 'shared-container-isolated-data'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:postgresql'
    testRuntimeOnly 'org.postgresql:postgresql'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Key point:** With a **Spring bean container**, this code **does not need** `org.testcontainers:junit-jupiter` because it **does not use `@Testcontainers`/`@Container`**. If switching to the JUnit extension as in Section 5, add `testImplementation 'org.testcontainers:junit-jupiter'`.

Spring Boot 3.5 BOM manages Testcontainers 1.x dependencies; the `org.testcontainers:postgresql` coordinates and `org.testcontainers.containers.PostgreSQLContainer` package belong to this branch. Testcontainers 2.x changes coordinates/module packages; do not mix 2.x coordinates with 1.x source imports. `spring-boot-testcontainers` provides `@ServiceConnection` and the lifecycle bridge.

This demo does not include a PostgreSQL runtime driver for `bootRun` outside tests; it targets **integration tests in Gradle**. A production application must add the runtime driver dependency and database configuration per deployment policy.

## 21. Application and database schema

**`src/main/java/com/example/isolation/IsolationApplication.java`**

```java
package com.example.isolation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class IsolationApplication {
    public static void main(String[] args) {
        SpringApplication.run(IsolationApplication.class, args);
    }
}
```

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE ledger_entries (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    owner_token VARCHAR(80) NOT NULL,
    business_key VARCHAR(80) NOT NULL,
    amount_minor BIGINT NOT NULL,
    CONSTRAINT ck_amount_positive CHECK (amount_minor > 0),
    CONSTRAINT uq_owner_business UNIQUE (owner_token, business_key)
);

CREATE INDEX idx_ledger_owner ON ledger_entries(owner_token);
```

Tests set `spring.sql.init.mode=always` so Spring Boot executes the script on the external PostgreSQL container. Each new context/container in the demo gets a fresh database created on startup, so `CREATE TABLE` omits `IF NOT EXISTS`; schema init should fail loudly if the table unexpectedly already exists. If a project uses Flyway/Liquibase, run **real migrations** instead of maintaining `schema.sql` alongside them.

**Do not reset identity in tests** and do not assert that IDs start at 1. Sequences/identities can leave gaps after rollbacks or failed inserts.

## 22. Repository: filter by owner on every query

**`src/main/java/com/example/isolation/LedgerRepository.java`**

```java
package com.example.isolation;

import java.sql.PreparedStatement;
import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Repository;

@Repository
public class LedgerRepository {

    private final JdbcTemplate jdbc;

    public LedgerRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public long create(
            String ownerToken,
            String businessKey,
            long amountMinor) {

        KeyHolder holder = new GeneratedKeyHolder();

        int changed = jdbc.update(connection -> {
            PreparedStatement statement =
                    connection.prepareStatement(
                            """
                            INSERT INTO ledger_entries
                                (owner_token, business_key, amount_minor)
                            VALUES (?, ?, ?)
                            """,
                            new String[] {"id"});
            statement.setString(1, ownerToken);
            statement.setString(2, businessKey);
            statement.setLong(3, amountMinor);
            return statement;
        }, holder);

        if (changed != 1) {
            throw new IllegalStateException(
                    "Expected exactly one inserted row");
        }

        Number key = holder.getKey();
        if (key == null) {
            throw new IllegalStateException(
                    "Database did not return generated key");
        }
        return key.longValue();
    }

    public long countByOwner(String ownerToken) {
        Long result = jdbc.queryForObject(
                """
                SELECT COUNT(*) FROM ledger_entries
                WHERE owner_token = ?
                """,
                Long.class, ownerToken);

        if (result == null) {
            throw new IllegalStateException(
                    "COUNT unexpectedly returned null");
        }
        return result;
    }

    public List<String> businessKeysByOwner(
            String ownerToken) {

        return jdbc.queryForList(
                """
                SELECT business_key FROM ledger_entries
                WHERE owner_token = ?
                ORDER BY business_key
                """,
                String.class, ownerToken);
    }

    public long totalAmountByOwner(String ownerToken) {
        Long value = jdbc.queryForObject(
                """
                SELECT COALESCE(SUM(amount_minor), 0)
                FROM ledger_entries
                WHERE owner_token = ?
                """,
                Long.class, ownerToken);

        if (value == null) {
            throw new IllegalStateException(
                    "SUM unexpectedly returned null");
        }
        return value;
    }

    public int deleteByOwner(String ownerToken) {
        return jdbc.update(
                """
                DELETE FROM ledger_entries
                WHERE owner_token = ?
                """,
                ownerToken);
    }
}
```

**Lessons from this repository:**

- SQL values use `PreparedStatement`/bind parameters, never concatenating inputs into SQL.
- `owner_token` appears in every SELECT/DELETE touching fixture data.
- `businessKeysByOwner` sorts explicitly so assertions do not rely on natural database order.
- `COUNT`/`SUM` compute strictly within the owner's scope, not across the entire table.
- `deleteByOwner` avoids `TRUNCATE`, `DELETE FROM ...` without `WHERE`, or dropping tables.
- The repository serves multiple test methods safely even while `DataSource` and container are reused.
- `GeneratedKeyHolder` reads the real ID instead of assuming identity starts at 1.

In a multi-tenant production application, requiring callers to pass `ownerToken` manually is not sufficient security; you may need policy/auth contexts, Row-Level Security, and query reviews. Here `owner_token` is a **test isolation mechanism**.

## 23. Container test config: one bean per context

**`src/test/java/com/example/isolation/SharedPostgresTestConfig.java`**

```java
package com.example.isolation;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.containers.PostgreSQLContainer;

@TestConfiguration(proxyBeanMethods = false)
public class SharedPostgresTestConfig {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgresContainer() {
        return new PostgreSQLContainer<>("postgres:16-alpine")
                .withDatabaseName("isolation_demo")
                .withUsername("test")
                .withPassword("test");
    }
}
```

**Why put it in a separate class?**

- Both test classes use `@Import(SharedPostgresTestConfig.class)`, keeping context configuration consistent and giving Spring **the opportunity to cache/reuse the same context/container**.
- Boot applies `@ServiceConnection` from the typed `PostgreSQLContainer<?>` and wires the `DataSource`.
- Container lifecycle is managed by Spring Boot alongside `ApplicationContext`.
- JUnit `@Container` is not mixed onto this bean; JUnit will not stop the container when one test class finishes while the context may remain cached.
- Database `isolation_demo` belongs only to the ephemeral test container and never points to production.
- If intentionally testing PostgreSQL 15/17 or two parallel databases, create a separate config and re-evaluate context keys/resource ownership.

**Do not assert start count == 1 across the whole suite**: a cache miss, forked JVM, differing profile, or context eviction can create another context and container. Tests should remain valid whether infrastructure is reused **or** each context gets its own service.

## 24. Fixture helper: assigning ownership per method

**`src/test/java/com/example/isolation/OwnedRowsSupport.java`**

```java
package com.example.isolation;

import java.util.HashSet;
import java.util.Set;
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.springframework.beans.factory.annotation.Autowired;

import static org.junit.jupiter.api.Assertions.assertEquals;

public abstract class OwnedRowsSupport {

    @Autowired
    protected LedgerRepository ledger;

    // JUnit Jupiter creates a new test class instance per method by default.
    private final Set<String> ownedTokens = new HashSet<>();

    protected String newOwner() {
        String token = "it-" + UUID.randomUUID();
        ownedTokens.add(token);
        return token;
    }

    @AfterEach
    void deleteOnlyThisMethodData() {
        for (String owner : ownedTokens) {
            ledger.deleteByOwner(owner);
            assertEquals(0L, ledger.countByOwner(owner));
        }
    }
}
```

**Why this cleanup is sound:**

1. The owner is **recorded in the tracked set before inserting**, so if INSERT succeeds and an assertion later fails, teardown still knows what scope to clean.
2. If a test creates multiple owners, the helper cleans each one.
3. `DELETE` always uses `WHERE owner_token = ?`.
4. `assertEquals(0L, countByOwner)` verifies cleanup actually removed the owner's data.
5. If the database fails during cleanup, `@AfterEach` does not swallow the exception; the test run reports a failure.
6. There is no static `ownedTokens` shared across classes; JUnit's default `PER_METHOD` creates a fresh set for every test method.

**Limitations:** a JVM kill or CI timeout can prevent `@AfterEach` from running. Ephemeral container teardown, per-run database ownership, and janitors/TTLs provide extra defense layers. If a background job continues writing to the same owner after cleanup, stop/await the job before deleting; the demo has no async tasks.

## 25. Test class A: one container, two independent owners

**`src/test/java/com/example/isolation/SharedContainerIsolationATest.java`**

```java
package com.example.isolation;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DuplicateKeyException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = IsolationApplication.class,
        properties = "spring.sql.init.mode=always")
@Import(SharedPostgresTestConfig.class)
class SharedContainerIsolationATest extends OwnedRowsSupport {

    @Test
    void identicalBusinessKeyCanExistForDifferentOwners() {
        String a = newOwner();
        String b = newOwner();

        long idA = ledger.create(a, "ORDER-1", 10_000L);
        long idB = ledger.create(b, "ORDER-1", 20_000L);

        assertTrue(idA > 0);
        assertTrue(idB > 0);
        assertEquals(1L, ledger.countByOwner(a));
        assertEquals(1L, ledger.countByOwner(b));
        assertEquals(10_000L, ledger.totalAmountByOwner(a));
        assertEquals(20_000L, ledger.totalAmountByOwner(b));
        assertEquals(List.of("ORDER-1"),
                ledger.businessKeysByOwner(a));
        assertEquals(List.of("ORDER-1"),
                ledger.businessKeysByOwner(b));
    }

    @Test
    void duplicateBusinessKeyWithinOneOwnerIsRejected() {
        String owner = newOwner();

        ledger.create(owner, "ORDER-2", 5_000L);

        assertThrows(DuplicateKeyException.class,
                () -> ledger.create(owner, "ORDER-2", 7_000L));

        assertEquals(1L, ledger.countByOwner(owner));
        assertEquals(5_000L,
                ledger.totalAmountByOwner(owner));
    }
}
```

**Why is Test A helpful?**

- Two owners share the string `ORDER-1`, yet the composite `UNIQUE` constraint protects them separately per owner.
- No need to reset identity or guess IDs.
- Duplicate test **within the same owner** must fail per the real DB constraint.
- `countByOwner` and `totalAmountByOwner` never see data from Test B or another method.
- Teardown deletes rows of **`a` and `b`** without touching other owners.
- Does not claim both tests always run concurrently; they are designed to be order-independent.

**One caveat:** If the product requires `ORDER-1` to be globally unique across the entire system, this composite unique constraint **does not match the business contract**. This lesson demonstrates namespaced data, not loosening product schemas just to avoid test collisions.

## 26. Test class B: continues using the same config without needing A's data

**`src/test/java/com/example/isolation/SharedContainerIsolationBTest.java`**

```java
package com.example.isolation;

import java.sql.Connection;
import java.util.List;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = IsolationApplication.class,
        properties = "spring.sql.init.mode=always")
@Import(SharedPostgresTestConfig.class)
class SharedContainerIsolationBTest extends OwnedRowsSupport {

    @Autowired
    DataSource dataSource;

    @Test
    void freshOwnerStartsEmptyEvenWhenContainerIsRetained() {
        String owner = newOwner();

        // Do not assert the entire table = 0;
        // assert only that the namespace owned by this method is empty.
        assertEquals(0L, ledger.countByOwner(owner));

        ledger.create(owner, "ORDER-1", 30_000L);

        assertEquals(1L, ledger.countByOwner(owner));
        assertEquals(List.of("ORDER-1"),
                ledger.businessKeysByOwner(owner));
    }

    @Test
    void deletingOneOwnerDoesNotDeleteAnotherOwner() {
        String first = newOwner();
        String second = newOwner();

        ledger.create(first, "X", 100L);
        ledger.create(second, "X", 200L);

        int deleted = ledger.deleteByOwner(first);

        assertEquals(1, deleted);
        assertEquals(0L, ledger.countByOwner(first));
        assertEquals(1L, ledger.countByOwner(second));
        assertEquals(200L,
                ledger.totalAmountByOwner(second));

        // @AfterEach will delete remaining data for second;
        // cleaning first again is idempotent and does not delete other owners.
    }

    @Test
    void datasourceReallyUsesPostgres() throws Exception {
        try (Connection connection =
                     dataSource.getConnection()) {
            assertEquals("PostgreSQL",
                    connection.getMetaData()
                            .getDatabaseProductName());
        }
    }
}
```

**Protections in place:**

- B can run before A, after A, or alone; it never reads A's fixtures to pass.
- `freshOwnerStartsEmpty...` does not claim the global database is empty; it proves **this method's owner** is empty.
- `deletingOneOwnerDoesNotDeleteAnotherOwner` proves cleanup is **scoped** instead of wiping the whole table.
- `datasourceReallyUsesPostgres` confirms the DB engine is PostgreSQL, not silently replaced by H2.
- Both A and B share equivalent context configurations; Spring TestContext **can** reuse the context/container, yet test correctness does not depend on reuse occurring.

**Do not add `@DirtiesContext` or `@TestMethodOrder` to force outcomes.** When observing reuse for performance tuning, use controlled startup metrics/logs; never turn container start count into a business data condition.

## 27. How to run and expected results

After setting up the project and a compatible Docker Engine:

```bash
docker version
docker info

./gradlew test --tests com.example.isolation.SharedContainerIsolationATest --tests com.example.isolation.SharedContainerIsolationBTest
```

In PowerShell:

```powershell
docker version
docker info

.\gradlew.bat test --tests com.example.isolation.SharedContainerIsolationATest --tests com.example.isolation.SharedContainerIsolationBTest
```

Expected results:

| Class | Number of `@Test` | What it verifies |
|---|---:|---|
| `SharedContainerIsolationATest` | 2 | Two owners sharing a key; duplicate rejected within one owner |
| `SharedContainerIsolationBTest` | 3 | Fresh namespace is empty; scoped cleanup; PostgreSQL driver |
| **Total** | **5** | Shared infrastructure without depending on other tests' data |

Gradle is expected to report `BUILD SUCCESSFUL` when code, versions, Docker runtime, and image repository are ready. **This is the expected result after reviewing the code, not a claim that Docker/Gradle were run in your workspace.**

There is no fixed business stdout. Docker container IDs, mapped ports, sequence values, and startup logs can vary. JUnit reports usually appear in `build/reports/tests/test/index.html` and XML in the module's `build/test-results/test/`.

**Run each class individually, then together as a suite:** assertions must hold in both cases. If a single class passes while running both classes fails, investigate **shared state, context caching, and startup/teardown ordering** before adding test ordering.

## 28. Why does this code avoid `@Transactional` on tests?

We want to demonstrate **explicit cleanup by `owner_token`**, even when rows are committed. Adding `@Transactional` to every test method causes Spring TestContext to roll back rows after the method, making ownership and cleanup behavior harder to observe.

This does not mean test transactions are bad. In a `@JdbcTest` repository suite, default rollback is often fast and convenient. However, distinguish:

- A test **borrowing a JUnit transaction to clean up data**.
- A real service having **the right `@Transactional` boundary**.
- An HTTP server/broker on another thread/process having its own transaction.
- Redis/Kafka/Elasticsearch not rolling back with a JDBC test transaction.

In the example, `LedgerRepository.create(...)` acquires connections from the Spring `DataSource`; outside a test-managed transaction, each JDBC call can commit under auto-commit. `@AfterEach` deletes data by owner. This keeps isolation behavior explicit and independent of implicit rollback.

### 28.1. When you want to test real transaction rollback

Write a test on a `@Transactional` service, invoke the service through the Spring proxy, trigger an exception after the first write, and query the DB after the exception **outside any test-managed transaction**. Never assume an empty table after a `@JdbcTest` proves service rollback, because JUnit's own rollback can mask service bugs.

## 29. Parallel execution: what this example handles and what else is needed

Row-level tokens let two test methods write to the same table with fewer collisions, yet **do not by themselves make a suite parallel-safe**:

- Global SQL DDL/cleanup must not run concurrently.
- Every query must carry an owner filter; other repository methods must not use `findAll` for scoped assertions.
- If there are table-wide unique constraints (beyond the owner key), random tokens alone are not enough.
- Async/background workers in tests must propagate owner context or use isolated queues/jobs.
- Container lifecycle must stay alive until all active tasks finish.
- JUnit/Spring/DB clients may have parallel-specific settings requiring review.
- Do not enable parallel execution on the JUnit Testcontainers extension blindly — Testcontainers docs state the extension makes no general guarantee for parallel execution.

**Choose parallelism deliberately:** read-only tests or simple owner-scoped writes may run in parallel once global state is ruled out. Tests with migrations, truncates, broker topic deletions, context dirtying, or shared locks should run sequentially or get dedicated sandboxes.

## 30. Data isolation in MongoDB, Redis, Kafka, and Elasticsearch

Shared containers vs shared data is not just a PostgreSQL concern.

### 30.1. MongoDB

**Sharing a `MongoDBContainer`** supports multiple databases or collections:

- Per-test database or collection name.
- Documents carrying `testRunId`/`ownerId`, with scoped queries and deletes.
- `dropCollection` removes collection indexes; if `UNIQUE`/TTL indexes are needed, ensure them again.
- Cleaning via `remove(Query...)` preserves indexes; never run `dropDatabase()` on a shared DB.
- Mongo transactions require a replica set/matching config and **do not roll back alongside a Spring JDBC transaction**.

### 30.2. Redis

**Sharing a Redis instance** requires key namespacing:

```text
it:orders:<run-id>:<test-id>:ORDER-1
it:orders:<run-id>:<test-id>:ORDER-2
```

- Track created keys and `DEL`/`UNLINK` only those keys.
- `SCAN` within your namespace when keys are generated dynamically; remember `SCAN` is not an atomic snapshot.
- Never run `FLUSHDB`/`FLUSHALL` on a shared instance.
- TTL limits leftover orphans, **it does not replace teardown**.
- Spring Cache key generators, background jobs, and streams/consumer groups can create state beyond simple keys.

### 30.3. Kafka

**Sharing a Kafka broker** does not mean sharing consumer groups:

- Test topics/consumer groups should use unique names whenever offsets or retention can interfere.
- A shared consumer group balances partitions across consumers, causing tests to steal messages from each other.
- `auto.offset.reset` applies when a group has no committed offset yet; it is not a broker-wide reset command.
- Creating/deleting test topics on a shared broker needs clear ownership; deleting shared topics is unsafe.
- Leftover messages after a test or async producers can emit events into topics after cleanup.
- Retry/idempotency/transaction semantics require integration tests matching the real Kafka version/config.

### 30.4. Elasticsearch/OpenSearch

- Use separate index names per run/test; do not delete overly broad `orders-*` wildcards.
- Aliases and mappings are shared metadata and need a reset plan.
- Search is near-real-time: use explicit refresh or eventual assertions instead of arbitrary `Thread.sleep`.
- Deleting documents is not equivalent to deleting an index + mapping.
- Index templates/ILM can automatically generate additional resources; inventory and clean them up per owner.

### 30.5. Object storage and filesystem

A separate container does not help if tests write into a shared S3 bucket or local `/tmp/output.json`. Use prefixes/paths containing a run/test ID, delete exact objects/versions when versioning is enabled, and never use production accounts. If multiple tests write to the same file, JVM object isolation offers zero protection.

**In short:** "Shared infrastructure, isolated state" is a **cross-backend principle**, not a single Testcontainers annotation.

## 31. Spring context caching: understanding what controls sharing

Spring TestContext's cache key is built from many elements, including:

- Configuration classes/locations.
- Context initializers, customizers, and imported configs.
- Active profiles and test properties.
- Dynamic property sources.
- Bean overrides/mocks and framework-specific customizers.
- Web context resource paths and other context configuration attributes.

When two test classes share the same key, the context can be reused **within the same JVM/test suite**. When running Gradle forked test processes, caches are not shared across processes. When cache eviction occurs, contexts can be closed and rebuilt. A test with `@DirtiesContext` can also evict a context.

**Therefore, never build correctness on getting a context cache hit.** It is an optimization and lifecycle mechanism. Test data must be clean even on a brand-new context, and independent even when the context is retained from an earlier class.

### 31.1. Another test class still pointing to an old container?

When one class uses a static JUnit `@Container` and the context is cached, after JUnit stops the container, another class can receive a `DataSource` pointing to the old URL and hit connection refused. Using a Spring bean container aligns container lifetime with the context. Still, **do not scatter `@DirtiesContext` everywhere** to fix every issue; choose clear ownership and lifecycles instead.

## 32. Cleanup when tests fail, the JVM crashes, or CI is canceled

`@AfterEach` is part of normal JUnit execution, but cannot run if:

- The JVM receives `kill -9`, loses power, or the runner is canceled.
- The Docker daemon/network drops right during teardown.
- A test hangs/times out and the process stops responding.
- Another cleanup callback throws an exception and aborts the teardown chain.

Defense in depth:

1. **Per-test owner tokens** to identify orphaned data.
2. **Per-run databases/containers** so the whole scope can be disposed.
3. **Container resource reaper** and ephemeral CI runner lifecycles per policy.
4. TTL/retention on auxiliary keys/data where appropriate.
5. Janitor jobs using an allowlist to delete only expired test namespaces.
6. Log cleanup failures clearly instead of swallowing exceptions.
7. Never delete active tests' data with overly broad cleanup.

**Never run `docker system prune -af` or drop an entire cluster when a test fails.** Identify the exact Docker objects/DB resources belonging to the run. And test-only least-privilege service credentials remain a critical guardrail if a wrong connection string is ever used accidentally.

## 33. When is a "shared fixture" intentional?

Sometimes many tests need the same large **read-only fixture**, such as a static product catalog or reference exchange rates. It can be seeded once into the shared container to save startup time.

**Acceptable when:**

- The data is treated as **immutable** across tests.
- No test mutates or deletes the shared fixture.
- Versioning/schema/checksum clearly verifies the fixture is valid.
- Test methods still write their own data under dedicated owner namespaces.
- Seeding before reads has a lifecycle/ordering independent of test execution order.

**Unacceptable when:**

- Test A "sets up" and Test B must run afterward to consume A's data.
- A test deletes or modifies the suite's read-only fixture.
- The fixture is mutated automatically from actual responses on each run.
- Source data contains PII or production secrets.
- A global counter/ID causes tests to fight over ownership.

With a shared immutable fixture, both **container sharing and intentional data sharing** can coexist. What must be avoided is **shared mutable state lacking an explicit owner or contract**.

## 34. Anti-patterns to eliminate

| Anti-pattern | Why it is wrong | Replace with |
|---|---|---|
| Static `@Container` means the DB is automatically clean | Static keeps the container across methods | Transaction/row/schema cleanup |
| New JUnit test instance = new DB | Test instance is just a Java object | Per-test owner or backend isolation |
| `@DirtiesContext` to wipe Redis/Postgres | Context does not reset external shared state | Scoped delete or dedicated DB |
| `TRUNCATE` after every method in a shared DB | Wipes rows from other methods | `DELETE WHERE owner_token=?` |
| `findAll()` asserting `size==1` in a shared DB | Counts other tests' data | Query filtered by owner |
| `UUID` on ID without scoping queries | Does not stop full-table reads | Owner predicate on every operation |
| Fixed global unique keys | Collisions across runs | Unique test keys or dedicated DB |
| Experimental container reuse on CI | State persists and cleanup is unreliable | Ephemeral containers in CI |
| JUnit stops container while Spring cache keeps using it | Lifecycle mismatch | Spring-managed container bean |
| Putting `@Transactional` on HTTP test trusting server rollback | HTTP server runs on a different thread/transaction | Explicit cleanup + assertions after server call |
| Assuming transaction rollback cleans Kafka/Redis | They do not share the JDBC transaction | Backend-specific cleanup |
| Enabling parallel mode and "fixing" with sleep | Races remain | Namespaces/resource locks/per-container |
| Deleting topics/indexes by broad prefix | Wipes other tests' resources | Exact owner-scoped names |
| Asserting container start count == 1 for test pass | Different caches/forks can still satisfy data contracts | Measure metrics separately; keep correctness independent |
| Cleaning up data while ignoring exceptions | Contamination leaks to later tests | Cleanup failures must fail the test |
| Test DB using production credentials | Risk of corrupting real data | Docker/test-only accounts and networks |

## 35. Troubleshooting: separating lifecycle bugs from state bugs

| Symptom | Error class | How to investigate |
|---|---|---|
| Passes alone, fails in suite with extra rows | Data contamination | Which query is missing an owner filter? |
| Duplicate key appears only on second run | Fixture/key collision | Unique constraints, cleanup, run IDs |
| Connection refused after class A finishes | Lifecycle/context cache | Was a static JUnit container stopped? |
| Spring context startup repeats many times | Context cache miss | Profiles/properties/imports/bean overrides |
| DataSource uses H2 instead of PostgreSQL | Auto-config | `@ServiceConnection` and JDBC driver |
| `relation does not exist` | Migration/init | `spring.sql.init.mode=always`, schema config |
| B deletes data while A is asserting | Shared destructive cleanup | `TRUNCATE`/unfiltered `DELETE`/resource locks |
| Identity sequence increases across rollbacks | DB sequence behavior | Never assert contiguous IDs |
| Parallel CI fails while sequential local passes | Concurrency/state | Shared DB/topic/index/async writers |
| Kafka test misses events | Consumer group/offsets | Group ID, topic, committed offsets |
| Unexpected Redis cache hit | Shared key namespace | Key generator/prefix/TTL |
| Search document not visible yet | Eventual consistency | Refresh/eventual assertion |
| Container still running after tests end | Reuse/manual lifecycle | `withReuse`/resource reaper policy |
| Test deletes from the wrong database | Misconfigured connection | Test-only credentials, DB product, guardrails |
| `@AfterEach` does not clean up when process dies | Crash/lifecycle | Ephemeral disposal, janitor |
| Tests slow due to per-method containers | Performance | Per-class/context container + scoped data |

### 35.1. Ordered debugging procedure

1. **Identify the real backend:** check `DatabaseMetaData.getDatabaseProductName()` and database name without printing credentials.
2. **Identify container lifecycle:** JUnit static, instance, bean, or manual singleton?
3. **Identify context cache:** do tests share the same cache key, and is the context still alive?
4. **Identify ownership:** which method/run owns each record/queue/key?
5. **Inspect queries and cleanup:** where is a `WHERE`/namespace filter missing?
6. **Inspect transactions:** does JUnit rollback actually cover the executed code path?
7. **Check parallel/background tasks:** are writers still running after the method ends?
8. **Check migrations/indexes:** is global DDL impacting all tests?
9. **Run the whole class/suite instead of one method:** if behavior differs, suspect shared state.
10. **Fix isolation**, rather than adding test ordering, sleeps, or bigger timeouts.

## 36. Hands-on exercises

### Exercise A — one container for an entire test class

A test class has a static `@Container PostgreSQLContainer`, and two methods both insert `external_id="ORDER-1"`. The second test throws duplicate key. Why? Give three fixes that do not turn the suite into an ordered integration scenario.

**Suggested answer:** The static container retains the DB across methods. Use per-test keys/owner tokens, transaction rollback, or separate databases/schemas; clean up within the proper scope.

### Exercise B — Spring context cache

Class A loads `@SpringBootTest` with a static `@Container`. After A, JUnit stops the container. Class B uses the cached context and gets connection refused. Is this a "shared data" or "shared lifecycle" bug?

**Answer:** Lifecycle mismatch. Use a Spring-managed container bean or `@ImportTestcontainers` when the context must outlive class A.

### Exercise C — two tenants, one table

Tenants A and B both have `business_key=ORDER-1`. If the domain contract allows duplicates across tenants, what `UNIQUE` constraint makes sense? If the business key must be globally unique, may you relax the DB constraint just to make tests pass?

**Answer:** Composite unique `(tenant_id, business_key)` if the domain permits it. If globally unique, keep the constraint and generate distinct test keys or isolate per schema/database.

### Exercise D — `TRUNCATE` cleanup

Two tests run in parallel on the same Postgres container. Test A just inserted a row; Test B runs `TRUNCATE ledger_entries` in `@AfterEach`. What can happen?

**Answer:** B wipes A's data; A can fail or block on locks. Use per-owner deletes, resource locks, or separate backends.

### Exercise E — does a fresh context fix contamination?

A test uses `@DirtiesContext` against a shared external PostgreSQL instance. Does a new context mean all old rows were deleted?

**Answer:** No. Restarting the context does not wipe an external DB. Scoped cleanup or an exclusive DB/schema is required.

### Exercise F — HTTP tests and `@Transactional`

A JUnit client test annotated `@Transactional` sends `POST /api/orders` to a Spring Boot `RANDOM_PORT` server. After the method, the row still exists. Is Spring rollback broken?

**Answer:** Not necessarily. The server request runs on its own thread and transaction; the JUnit test transaction does not cover response-side writes.

### Exercise G — shared Redis

One Redis container is shared across multiple classes. Test A calls `FLUSHDB` to reset, and Test B loses its session key. Propose a key namespace and teardown strategy.

**Answer:** Prefix keys by run/test, track owned keys, `DEL` the exact list or `SCAN` within the private namespace; avoid `FLUSHDB`/`FLUSHALL`.

### Exercise H — Kafka offsets

Two tests share a topic and `group.id=integration` while running concurrently. One test misses events. What is the cause and how do you isolate them?

**Answer:** Consumers in the same group split partitions/offset state. Use distinct group IDs/topics, manage offsets and producer lifecycles, and never delete a shared topic while another test uses it.

### Exercise I — reusable container across two Gradle runs

A developer enables `withReuse(true)`, and the next day an assertion expecting count=0 fails even though code did not change. Why? Should reuse be enabled on CI?

**Answer:** Reusable containers can retain data across runs. Testcontainers docs state experimental reuse is unsuitable for CI; locally it requires explicit resets/namespaces.

### Exercise J — fair cost evaluation

A team has 500 repository tests. Per-method Postgres containers take too long; a shared context/container is fast yet suffers contamination. Propose an architecture combining slices, transaction rollback, owner scopes, and a few per-container migration tests. Which metrics will you track to prove improvement?

**Hints:** Startup duration, total suite runtime, flaky failure rate, false positives, resource consumption, context cache hit rate, and data isolation violations.

## 37. End-of-lesson checklist

- [ ] I distinguish **sharing a container** from **sharing mutable data**.
- [ ] I know who starts/stops the container: JUnit, Spring bean, manual singleton, or experimental reuse.
- [ ] With a static `@Container`, I understand DB rows do not reset between methods.
- [ ] With a Spring-managed container, I understand its lifetime matches `ApplicationContext`.
- [ ] When contexts are cached, I do not rely on context restarts to reset the database.
- [ ] No `DataSource` points to a JUnit container that was already stopped.
- [ ] Spring Boot `@ServiceConnection` wires connections; it does not clean up data.
- [ ] Each test has an independent namespace/owner/fixture.
- [ ] Every query and cleanup carries the right owner predicate when sharing tables.
- [ ] `UNIQUE` constraints reflect the business domain, never relaxed just for tests.
- [ ] I do not assert DB-wide row counts when the DB may contain data from other tests.
- [ ] I do not rely on IDs/sequences starting at 1 or being contiguous.
- [ ] Cleanup deletes only test-owned resources and verifies postconditions.
- [ ] Cleanup errors fail the test run rather than being ignored.
- [ ] Per-schema/per-database/per-container isolation is chosen for DDL/destructive operations.
- [ ] Test transactions are used only for writes genuinely within the rollback boundary.
- [ ] HTTP `RANDOM_PORT`/async/Redis/Kafka writes have dedicated cleanup strategies.
- [ ] Tests run independently without relying on `@TestMethodOrder`.
- [ ] Parallel execution enforces explicit resource ownership/locks.
- [ ] Experimental reusable containers are not blindly enabled on CI.
- [ ] CI/Docker runners have safe quotas, permissions, and cleanup policies.
- [ ] I know how single-JVM vs forked-JVM execution affects Spring context caching.
- [ ] When tests use Mongo/Redis/Kafka/search, I also isolate collection/key/topic/index metadata properly.
- [ ] No broad `TRUNCATE`/`FLUSHDB`/`DROP SCHEMA` runs on shared backends.
- [ ] Tests use credentials and endpoints belonging solely to the test environment.
- [ ] Test conclusions rest on business/DB assertions, not how many times a container started.

**Conclusion:** **A container is an infrastructure unit; test data is a state and ownership unit.** Testcontainers can share one PostgreSQL/Redis/Kafka process to save startup time, yet every test must still identify its own fixtures, scope queries, manage transactions, and clean up safely. Spring context caching, static `@Container`, singletons, and reusable containers are distinct **lifecycle mechanisms**, not magic data-reset switches. Pick row/schema/database/container isolation according to risk, and never let one test corrupt another test's environment.

### Official references

- Spring Boot 3.5 — Testcontainers, Spring-managed container beans, JUnit extension, service connections, and lifecycle: https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html
- Testcontainers — JUnit Jupiter static/instance `@Container` and parallel execution limits: https://java.testcontainers.org/test_framework_integration/junit_5/
- Testcontainers — Manual container lifecycle and singleton pattern: https://java.testcontainers.org/test_framework_integration/manual_lifecycle_control/
- Testcontainers — Reusable Containers (experimental, unsuitable for CI): https://java.testcontainers.org/features/reuse/
- Spring Framework — TestContext caching and context cache keys: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html
- Spring Framework — Parallel Test Execution guidelines: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/parallel-test-execution.html
- Spring Framework — Test-managed transactions/rollback rules: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html
- Testcontainers — PostgreSQL module: https://java.testcontainers.org/modules/databases/postgres/
- PostgreSQL — Schemas: https://www.postgresql.org/docs/current/ddl-schemas.html
- PostgreSQL — Transaction Isolation: https://www.postgresql.org/docs/current/transaction-iso.html
