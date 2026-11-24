# Verifying Compatibility Using the Same Infrastructure Type as the Runtime Environment

A Spring application can work properly against mocks or embedded services in tests yet still fail in a real runtime environment. The cause often lies in differences between test infrastructure and production infrastructure: H2 instead of PostgreSQL, a fake broker instead of Kafka, an in-memory cache instead of Redis, or the local filesystem instead of object storage. These systems may expose similar APIs while differing in SQL dialect, transaction isolation, serialization, retries, expiry, locking, collation, protocols, and error handling.

To verify compatibility, run integration tests against the same type of service the application uses in deployment. You can use Testcontainers to start databases, message brokers, caches, or auxiliary services inside dedicated test containers. The goal is to reproduce infrastructure characteristics that affect application behavior while keeping data, accounts, and resource lifecycles isolated.

## What Does "Same Type of Infrastructure" Mean?

You do not necessarily need to build a full production replica. You need the same technology family and the characteristics capable of altering the behavior the test aims to confirm.

For example, if production uses PostgreSQL, SQL compatibility tests should run on PostgreSQL rather than relying solely on H2 in compatibility mode. If production uses Kafka, tests for critical publish/consume flows should use real Kafka or a Kafka-compatible environment instead of only mocking `KafkaTemplate`. If production stores files on S3, tests must verify storage protocols and behavior with S3 or a compatible implementation.

| Production infrastructure | Representative test infrastructure | Differences to care about |
|---|---|---|
| PostgreSQL | PostgreSQL container with matching major/minor version | SQL dialect, JSONB, sequences, constraints, collation, isolation, extensions |
| MySQL | MySQL container with matching version and relevant settings | SQL mode, collation, timezones, indexes, transaction engine |
| Kafka | Kafka container or compatible test broker | Partitions, offsets, consumer groups, ordering, acknowledgements, retries |
| RabbitMQ | RabbitMQ container | Exchanges, routing keys, queue durability, acknowledgements, dead-lettering |
| Redis | Redis container | TTL, eviction, serialization, atomic operations, Lua scripts |
| Elasticsearch/OpenSearch | Same engine family and compatible version | Mappings, analyzers, query DSL, index lifecycle, refresh behavior |
| S3-compatible storage | S3 or compatible service such as MinIO | Bucket policies, metadata, multipart uploads, path-style/virtual-host addressing |
| Filesystem | Filesystem of the matching OS/container | Case sensitivity, permissions, atomic renames, path separators |

"Same type" should be interpreted through compatibility risk. A test checking only that a service calls a repository can use a mock. However, a test verifying native queries, migrations, locking, or transactions needs a real database engine. Similarly, a test checking event mapping logic can be a unit test, whereas a test verifying consumer groups, acknowledgements, and retries needs a real broker.

## Choosing the Necessary Level of Similarity

Not every test needs to reproduce every production detail. Identify which infrastructure traits influence the outcome:

1. **Service type:** database, broker, cache, search engine, object storage, or filesystem.
2. **Engine and version:** use the same engine and a version compatible with the runtime environment; avoid the `latest` tag because test behavior can shift unexpectedly.
3. **Critical settings:** encoding, collation, timezone, SQL mode, extensions, transaction isolation, retention, TTL, partitions, or policies.
4. **Drivers and protocols:** use the same driver/client type and configuration close to the production application.
5. **Security:** if production relies on TLS, authentication, authorization, or credential rotation, include tests verifying those pieces at an appropriate layer.
6. **Lifecycle and failure modes:** confirm the application handles timeouts, unavailable services, retries, reconnects, and shutdown as required.

A container running the same engine with settings different from production can still miss bugs. For example, a test PostgreSQL instance missing an extension used in production will not prove migrations or extension-dependent queries work. Conversely, you do not need to copy production data volumes when the goal is simply verifying query syntax and schema constraints.

## Why H2 or Mocks May Not Be Enough

H2 is very useful for fast tests and simple repository checks. However, H2 is not PostgreSQL or MySQL. Even with compatibility modes, it cannot guarantee that all differences in parsers, data types, SQL functions, constraints, indexes, locking, and transaction semantics are modeled accurately.

For instance, the following query uses PostgreSQL-specific syntax:

```sql
select payload ->> 'customerId'
from event_log
where payload @> '{"status":"READY"}'::jsonb
```

This query uses PostgreSQL JSONB operators and casting. A test running only on H2 may fail to execute the query or force replacing it with another implementation, leaving the actual production SQL untested.

Mock repositories have an even bigger limitation: mocks only return programmed results. They do not test SQL, constraints, transactions, isolation, migrations, indexes, or real mappings. Mocks fit service unit tests, where the goal is verifying business rules and collaborator coordination. They do not replace integration tests meant to confirm database compatibility.

A practical strategy can use all three levels:

| Test type | Infrastructure | What is verified |
|---|---|---|
| Unit test | Mock dependencies | Business logic and execution branches |
| Fast integration test | Embedded or lightweight service | Basic mappings/config, when semantics are compatible enough for the goal |
| Compatibility integration test | Production-equivalent engine/protocol | SQL, transactions, migrations, serialization, and real service behavior |

You do not need to remove H2 from every test. Simply avoid concluding from H2 results that the application is compatible with PostgreSQL when production actually runs PostgreSQL.

## Using Testcontainers to Start Real Infrastructure

Testcontainers provides a Java API to run containers for testing and automatically manage container lifecycles. Tests can start a database or broker at the beginning, retrieve the dynamic endpoint, run the application against that endpoint, and stop the container when tests finish.

With Maven, a PostgreSQL dependency example:

```xml
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
</dependency>
```

Use a BOM or your project's dependency management to align Testcontainers and driver versions. This example assumes the application already has Spring Boot Test and the corresponding Spring Data/JDBC/JPA dependencies.

### PostgreSQL Matching the Production Type

The following example runs a PostgreSQL container and injects the dynamic URL, username, and password into the Spring context via `@DynamicPropertySource`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
@SpringBootTest
class OrderRepositoryCompatibilityTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16.4-alpine")
                    .withDatabaseName("store_test")
                    .withUsername("test_user")
                    .withPassword("test_password");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void persistsAndReadsOrderUsingPostgres() {
        Order saved = orderRepository.save(new Order("PO-349"));

        Order loaded = orderRepository.findById(saved.getId()).orElseThrow();

        assertThat(loaded.getReference()).isEqualTo("PO-349");
    }
}
```

`@Testcontainers` integrates Testcontainers with JUnit Jupiter. `@Container` on a `static` field creates a container shared across the test class; the container starts before the class's tests run and stops after the class completes. `@DynamicPropertySource` registers values available only after the container starts. Spring reads these suppliers when constructing the context.

Image tags should be pinned to the version used in production or specified in a compatibility matrix. If production runs PostgreSQL 16.x, do not let tests silently shift to another major version just because `latest` updated.

### Preventing Spring Boot from Replacing the Test Database with an Embedded Database

With `@DataJpaTest`, Spring Boot can automatically replace the datasource with an embedded database if a matching dependency is found. When the goal is testing a PostgreSQL container, disable that replacement behavior:

```java
@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@Testcontainers
class OrderRepositorySliceTest {
    // PostgreSQLContainer and DynamicPropertySource as in the example above.
}
```

`replace = NONE` keeps the datasource configured from the container. If a test accidentally runs against H2, the test might pass while no longer proving the SQL runs on the production engine.

## Using @ServiceConnection in Spring Boot

With Spring Boot 3.1 and later, `@ServiceConnection` can automatically generate connection details for Boot-supported Testcontainers types. This reduces manual registration of datasource properties:

```java
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class OrderDatabaseTest {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16.4-alpine");
}
```

To use this annotation, the project needs the matching Spring Boot Testcontainers module (`spring-boot-testcontainers`) alongside the Testcontainers PostgreSQL module. `@ServiceConnection` only auto-configures service types for which Spring Boot provides a connection details factory; for custom services or settings, `@DynamicPropertySource` remains a flexible option.

Do not mix multiple configuration mechanisms for the same endpoint unnecessarily. Make the final property source clear so container URLs are not overridden by `application-test.yml` or environment variables.

## Running Real Migrations Against the Test Database

Compatibility tests should create schemas using the same migrations the application runs on deployment. If production uses Flyway or Liquibase, let the test context run migrations on the container database:

```properties
spring.flyway.enabled=true
spring.jpa.hibernate.ddl-auto=validate
```

With this setup, Flyway builds the schema from migration scripts while Hibernate validates that entity mappings match the resulting schema. In tests, avoid letting Hibernate auto-generate the schema in place of migrations when the goal is verifying that production migrations work.

A test can confirm data is stored after migrations run:

```java
@Test
void migrationCreatesExpectedColumnAndConstraint() {
    Integer count = jdbcTemplate.queryForObject(
            "select count(*) from information_schema.columns " +
            "where table_name = 'orders' and column_name = 'reference'",
            Integer.class);

    assertThat(count).isEqualTo(1);
}
```

Metadata queries can differ across engines; the example above suits PostgreSQL with the appropriate schema/search path. Write assertions against the production database's catalog, especially when checking indexes, constraints, extensions, or migration history.

Migration tests should start from an empty database or freshly created schema so the entire migration chain executes in order. A database already holding schemas from a previous run can mask missing or non-idempotent migrations.

## Verifying Brokers and Message Semantics

Mocking `KafkaTemplate` can confirm that a service calls `send()` with the expected topic and payload, but it does not verify that the broker accepts the message, serializers work, partitions are selected, or consumer groups commit offsets and retry. When those behaviors matter, run a matching broker in integration tests.

A broker test should verify the flow end to end:

1. Start the broker and create required topics/queues.
2. Configure Spring producers/consumers with the container endpoint.
3. Send a message using the real producer.
4. Wait for the consumer to process it using a bounded-timeout signal, such as a latch or a state written to the database.
5. Assert payload, headers, keys, routing, or resulting side effects.
6. Clean up topics/queues or use dedicated topics/consumer groups per test.

Never use `Thread.sleep()` to guess when a consumer has received a message. Use Awaitility, `CountDownLatch`, `CompletableFuture`, or condition-based polling with a timeout. Broker tests should enforce finite timeouts and log topic, partition, offset, or correlation ID details on failure.

For Kafka, key characteristics can include partition count, key-based ordering, consumer groups, offset commits, acknowledgements, retries, and dead-letter topics. For RabbitMQ, test exchanges, bindings, routing keys, durable queues, acknowledgements, redelivery, and dead-letter exchanges. Mocks can test message mapping; real brokers test messaging system semantics.

## Verifying Caches, Search, and Object Storage

An in-memory cache like `ConcurrentHashMap` is not automatically equivalent to Redis. It can differ in TTL, eviction, serialization, atomic operations, distributed locking, and behavior across node restarts. If the application uses Redis, compatibility tests should run a Redis container for features relying on those semantics.

Search engines also differ across implementations. If production uses Elasticsearch or OpenSearch, verify the engine/version, mappings, analyzers, query DSL, refresh behavior, and bulk operations. A mock HTTP server can verify outgoing JSON requests, but it does not prove the engine interprets those mappings or queries as in production.

For object storage, use S3 or a compatible service runnable in a container/test environment. Verify uploads/downloads, metadata, content types, multipart uploads, bucket policies, path-style addressing, and missing-object handling. An in-memory byte-array fake only suits testing logic that calls the storage interface.

| Feature | Unit test with mocks | Compatibility test with matching infrastructure |
|---|---|---|
| Redis cache key | Verify service builds the right key | Verify serialization, TTL, and atomic operations |
| Kafka event | Verify producer targets the right topic/key | Verify broker acceptance, partitioning, and consumer handling |
| Search query | Verify request/query object construction | Verify mappings/analyzers/queries execute on the engine |
| S3 upload | Verify service invokes the storage port | Verify endpoint accepts objects, metadata, and policies |

You do not need to run all of these tests for every change. Focus on adapters and behaviors where development and production environments risk diverging.

## Configuring Test Environments Explicitly

Tests should use a dedicated profile, but the profile must not change the infrastructure type the test intends to verify. For example, `application-test.yml` can hold test-appropriate logging, timeouts, and feature flags while the datasource URL is supplied by Testcontainers:

```yaml
spring:
  jpa:
    open-in-view: false
    hibernate:
      ddl-auto: validate
  flyway:
    enabled: true
  datasource:
    hikari:
      maximum-pool-size: 4
      connection-timeout: 5000
```

```java
@SpringBootTest
@ActiveProfiles("test")
class OrderInfrastructureTest {
}
```

Supply URLs, usernames, and passwords dynamically from the container; never commit production credentials into test resources. If production enforces TLS or authentication, add dedicated configuration tests confirming clients connect properly with those mechanisms. A container without TLS enabled cannot prove production TLS configuration works.

When a test needs to verify pool settings or connection lifecycles, keep the application's real connection pool (such as HikariCP) and point its endpoint to the container. Do not replace the entire datasource with a mock, as doing so bypasses pooling, drivers, connection validation, and the transaction manager.

## Aligning Versions and Configuration with Production

Store test infrastructure versions in one place where they can be reviewed and upgraded deliberately:

```properties
# test-infrastructure.properties
test.postgres.image=postgres:16.4-alpine
```

You can use this property to configure containers or place pinned tags directly in test sources. What matters is preventing CI from silently pulling the newest image without a reviewed change.

A compatibility matrix can state explicitly:

| Component | Production | Test | Similarity to maintain |
|---|---|---|---|
| PostgreSQL | 16.x | 16.4 | Same major version; pin patch version in CI |
| JDBC driver | PostgreSQL JDBC 42.x | Same driver line | Same driver and pool settings |
| Kafka | 3.x | Same broker version or certified version | Protocol and consumer/producer semantics |
| Redis | 7.x | 7.x | Same version, plus persistence/eviction if relevant |
| S3 | Managed S3 | S3 test service | APIs and features used by the application |

If production runs a managed service with proprietary extensions or policies, a basic container only verifies the underlying engine/API. Supplement it with contract tests or staging tests to verify provider-specific features.

## Data Isolation and Cleanup

Using the same type of infrastructure does not mean sharing production data. Each test needs deterministic data and must not affect other tests.

Common strategies:

- A dedicated container per test class or test suite.
- A dedicated database/schema per test class or parallel worker.
- Namespaced topic, queue, bucket, or key names per test.
- Explicit fixture seeding and cleanup after tests.
- Transaction rollback when all operations occur in the same transaction/thread; never assume rollback covers HTTP server threads, async executors, or message consumers.

For databases, `@Transactional` can roll back test-managed transactions in tests calling repositories directly. However, when requests go through `RANDOM_PORT`, the server executes on another thread with its own transaction. Data committed by the server does not automatically roll back with the test transaction. Delete data via a cleanup transaction, create separate schemas/databases, or reset the container.

For brokers, use dedicated topics or queues per test so stale messages cannot cause later tests to pass falsely. For Redis, prefix keys and set appropriate TTLs. For object storage, use dedicated buckets/prefixes and delete objects after tests. Under parallel execution, namespaces should include test or worker IDs to prevent collisions.

Never use raw production data directly. If realistic data shapes are needed, generate synthetic fixtures or use anonymized data approved under organizational procedures.

## Container Lifecycle and the Spring Context Cache

A `static @Container` with JUnit Jupiter normally lives for the duration of one test class. Spring TestContext, meanwhile, can cache an `ApplicationContext` and reuse it across multiple classes. If a cached context retains a `DataSource` pointing to a container stopped after the previous class, the next test class may hit connection refused errors despite having an identical configuration.

Several ways to organize this:

1. Scope containers per class and configure contexts so lifecycles align with containers; prevent the context cache from outliving the resources it depends on.
2. Use a suite-scoped singleton container, started once and kept alive for the entire duration contexts use it. With this approach, omit `@Container` so JUnit does not stop it after each class, and manage startup/shutdown explicitly.
3. Use `@DirtiesContext` when a test genuinely needs to close the context before stopping the container, without overusing it since it increases suite duration.

Even when sharing a suite-level container, still isolate databases/schemas, topics, queues, and keys between tests. Sharing a service process does not mean sharing business state.

## Checking Readiness Instead of Fixed Waits

A running container does not guarantee the service inside is ready for requests. Testcontainers provides wait strategies for ports, log messages, HTTP responses, or health checks. Choose readiness conditions suited to the service and image version.

```java
GenericContainer<?> service = new GenericContainer<>(
        DockerImageName.parse("example/service:1.2.3"))
        .withExposedPorts(8080)
        .waitingFor(Wait.forHttp("/health")
                .forStatusCode(200)
                .withStartupTimeout(Duration.ofMinutes(2)));
```

This example shows an HTTP wait strategy for a service exposing a health endpoint. For databases or brokers, prefer their corresponding wait strategies or image health checks. Avoid `Thread.sleep(5000)` after starting a container: fast machines waste time, while slow machines may still not be ready.

If the application has startup logic that retries when a dependency is unavailable, tests should verify that behavior using an observable condition and a finite timeout. Container readiness and application retry policies are two separate behaviors.

## Running the Same Strategy Locally and in CI

Compatibility tests are only useful when repeatable. Developer machines and CI should use the same image versions, migrations, critical settings, and endpoint discovery mechanisms. CI requires a container runtime such as Docker or a compatibly configured Testcontainers environment.

A typical pipeline runs:

1. Prepare the Docker/container runtime.
2. Run the test suite; Testcontainers starts the required services.
3. Wait for readiness, create schemas/topics/buckets, and load fixtures.
4. Run integration tests and collect logs on failure.
5. Stop containers and clean up test resources.

When CI disallows Docker-in-Docker or lacks Testcontainers support, you can use CI-provided service containers or a dedicated ephemeral environment. Keep the same engine/version and relevant settings; change only how endpoints are supplied, never silently swapping to a different database or broker.

## When Additional Tests in a Production-Like Environment Are Needed

Same-type containers cover most engine and protocol behavior, yet some differences cannot be reproduced completely:

- Managed databases with custom extensions, parameter groups, proxies, or failover.
- Multi-node Kafka/RabbitMQ clusters with replication, partition rebalancing, or quorum behavior.
- Cloud IAM, KMS, secret managers, certificate rotation, and network policies.
- Load balancers, reverse proxies, DNS, TLS termination, and network latency.
- Provider storage policies, lifecycle rules, versioning, and quotas.

For these risks, use container-based compatibility integration tests to verify foundational behavior, then add targeted contract/staging tests in a production-like environment. You do not need to turn every unit test into a staging test; place provider-specific dependencies at the appropriate verification tier.

## Common Mistakes

| Symptom | Possible cause | Solution |
|---|---|---|
| Tests pass on H2 but fail on PostgreSQL | Different SQL dialect or semantics | Run query/migration tests on production-equivalent PostgreSQL |
| Spring still connects to H2 | Boot replaced the datasource or container properties were overridden | Use `replace = NONE` on the matching slice and verify the actual datasource URL |
| Container runs but connections fail | Service not yet ready or wrong port mapping | Use wait strategies and retrieve endpoints via the Testcontainers API |
| Subsequent test class gets connection refused | Spring context cache references a stopped container | Align container/context lifecycles or use a suite-level container |
| Messaging test receives stale events | Shared topic/queue was not reset | Namespace or create dedicated topics/queues per test |
| Cache test depends on execution order | Shared keys or unexpired TTL | Use dedicated prefixes, clean keys, and verify TTL explicitly |
| Tests slow or flaky on CI | Using `sleep`, unclear readiness, or unpinned image versions | Use wait strategies with timeouts, pin images, and collect logs |
| Test transaction does not roll back HTTP request data | Request runs on a server thread with its own transaction | Clean up data or isolate schemas/databases |
| API-compatible container lacks production features | Managed service has custom extensions/policies | Add tests on staging or appropriate contract tests |

## Matrix for Choosing Infrastructure by Goal

| Test goal | Recommended infrastructure | Why |
|---|---|---|
| Service logic and business branches | Mock repository/client | Focus on service decisions |
| Native queries, migrations, locking | Same database engine as production | Verify real SQL and transaction semantics |
| Serialization and consumer behavior | Same or compatible broker | Verify protocols, routing, acknowledgements, and retries |
| TTL, atomic operations, distributed locks | Same cache engine | Verify semantics in-memory caches fail to emulate |
| Search mappings/analyzers | Same search engine/version | Verify query and indexing behavior |
| Object upload/download | S3 or compatible implementation | Verify APIs, metadata, multipart, and policies |
| IAM, failover, managed extensions | Staging or production-like environment | These traits are not fully available in basic containers |

Verifying compatibility with the same infrastructure type catches bugs caused by engine, version, protocol, and configuration differences before deployment. Use mocks for unit logic, containers for integration tests needing real services, and staging tests for traits that exist only in managed environments. When versions, settings, readiness, data, and lifecycles are controlled, test outcomes reflect far more reliably how the application behaves in production.
