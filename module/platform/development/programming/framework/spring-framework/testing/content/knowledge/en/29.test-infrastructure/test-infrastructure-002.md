# Test Containers for Databases and Brokers

When testing a Spring application that uses a database or message broker, in-memory H2 and mock repositories often fail to faithfully reproduce the real runtime environment. PostgreSQL has its own data types, transactions, constraints, and SQL syntax; Kafka, RabbitMQ, or Redis also have their own protocols, acknowledgements, consumer groups, and connection management. A test relying solely on mocks can miss configuration errors or behavioral differences in those components.

Testcontainers solves this problem by starting real services inside containers dedicated to testing. The Spring application connects to the container through dynamically mapped ports, executes migrations, queries the database, or sends/receives messages just as in production. When the test completes, the container is stopped according to the lifecycle declared by the test.

Test containers sit between unit tests and full deployment testing: the underlying service is real, yet the test retains control over images, configuration, data, and lifecycle. This is a valuable way to verify that repositories, transactions, migrations, message publishers, and consumers work together with the technologies the application actually uses.

## 1. When Should You Use Test Containers?

A test using a mock repository can verify that a service calls `save(...)`, but it does not prove that the generated SQL is valid, migrations execute cleanly, or a unique constraint in PostgreSQL behaves as expected. Similarly, mocking `KafkaTemplate` can verify that the application calls `send(...)`, but it does not prove that the broker accepts the message, serializers are compatible, or a consumer receives the message.

Test containers provide real services for the application to communicate with:

```text
JUnit / Spring Test
       |
       v
Spring ApplicationContext
       |
       +---------------------------+
       |                           |
       v                           v
DataSource / JPA              KafkaTemplate / RabbitTemplate
       |                           |
       | JDBC                      | AMQP / Kafka protocol
       v                           v
PostgreSQL container          Broker container
       |                           |
       +-------------+-------------+
                     |
                     v
              Assertions in test
```

Consider Testcontainers when you need to verify:

- Repositories and queries against the actual production database type.
- Schema migrations using Flyway or Liquibase.
- Transactions, isolation, constraints, indexes, and locking.
- Serialization, publish/consume, routing keys, topics, partitions, or acknowledgements.
- Configuration of connection pools, drivers, broker clients, and authentication.
- Behavior when a service starts slowly, is temporarily unavailable, or returns errors.

Unit tests remain appropriate for testing pure business rules. Container tests should focus on integration boundaries with databases or brokers, where behavior depends on the real product.

## 2. How Does Testcontainers Work?

Testcontainers is a Java library that controls a container runtime. In a test, you declare the required image, ports, environment variables, volumes, commands, and readiness conditions. The library creates the container, waits for the service to become ready, and exposes the mapped address and port to the application.

The typical lifecycle looks like this:

1. The test declares the container and image.
2. Testcontainers asks a Docker-compatible runtime to start the container.
3. The container launches the database or broker and exposes service ports.
4. The test retrieves the dynamic host/port from the container and configures Spring.
5. Spring creates the connection pool or broker client and runs migrations if configured.
6. The test exercises application behavior and runs assertions on real data/messages.
7. Testcontainers stops and cleans up the container according to the chosen lifecycle.

Never assume a service is always at `localhost:5432`, `localhost:5672`, or `localhost:9092`. Testcontainers normally maps the container port to an available ephemeral port on the host. Always obtain addresses from the container API, such as `getJdbcUrl()`, `getAmqpPort()`, or `getBootstrapServers()`.

## 3. Dependencies for JUnit and Databases

The following example uses Gradle. Managing Testcontainers versions centrally with a BOM ensures all modules share the same version:

```groovy
dependencies {
    testImplementation(platform("org.testcontainers:testcontainers-bom:1.20.6"))
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:postgresql")

    testRuntimeOnly("org.postgresql:postgresql")
}
```

If the project uses Maven, import the BOM in `dependencyManagement` and declare the modules with test scope:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>testcontainers-bom</artifactId>
            <version>1.20.6</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
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
</dependencies>
```

The versions above illustrate a compatible set of dependencies; projects should choose a supported Testcontainers version and manage it consistently. The `junit-jupiter` module provides annotation integration with JUnit 5. The `postgresql` module provides `PostgreSQLContainer`; the JDBC driver remains a separate application dependency.

## 4. Starting a PostgreSQL Container with JUnit 5

`@Testcontainers` enables the JUnit Jupiter extension. `@Container` marks a container managed by the extension. A `static` field is started once for the entire test class and stopped after the class; an instance field is started and stopped for each test method.

```java
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
class PostgreSqlContainerTests {

    @Container
    static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("orders")
                    .withUsername("test")
                    .withPassword("test");

    @Test
    void containerExposesJdbcConnectionDetails() {
        assertThat(POSTGRES.isRunning()).isTrue();
        assertThat(POSTGRES.getJdbcUrl()).contains("jdbc:postgresql:");
        assertThat(POSTGRES.getUsername()).isEqualTo("test");
    }
}
```

`PostgreSQLContainer` knows how to configure the PostgreSQL image, database, username/password, and wait until the database is ready. Tests do not need custom shell scripts to start the database.

Pin a specific image tag, such as `postgres:16-alpine`, instead of using `latest`. If the tag changes unexpectedly, tests may receive a different database version than production and yield unstable results.

## 5. Connecting Spring Boot to a Container via DynamicPropertySource

With Spring Boot, `@DynamicPropertySource` registers dynamic properties before the application context is created. This approach works with many container types and does not depend on whether Spring Boot has a built-in service connection factory for that service.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest
@Testcontainers
class OrderRepositoryIntegrationTests {

    @Container
    static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("orders")
                    .withUsername("test")
                    .withPassword("test");

    @Autowired
    OrderRepository orderRepository;

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username", POSTGRES::getUsername);
        registry.add("spring.datasource.password", POSTGRES::getPassword);
    }

    @Test
    void savesAndLoadsOrderUsingPostgres() {
        OrderEntity saved = orderRepository.save(
                new OrderEntity("ORD-100", "CREATED"));

        OrderEntity loaded = orderRepository.findById(saved.getId())
                .orElseThrow();

        assertThat(loaded.getOrderNumber()).isEqualTo("ORD-100");
        assertThat(loaded.getStatus()).isEqualTo("CREATED");
    }
}
```

The example assumes the application has `OrderRepository`, `OrderEntity`, and an appropriate schema. `spring.datasource.url` receives the JDBC URL with the dynamic port exposed by the container. Username and password are also retrieved directly from the container.

When Spring creates the `DataSource`, Flyway or Liquibase can run migrations just as at application startup. As a result, the test also confirms that migrations can be applied to the actual database engine. When using `@SpringBootTest`, ensure the test context scans the application's repository, entity, and migration configurations.

## 6. Using @ServiceConnection in Spring Boot

Spring Boot 3.1 and later provides `@ServiceConnection` to automatically create `ConnectionDetails` from supported container types. This reduces the need to declare individual properties with `@DynamicPropertySource`.

Add the Spring Boot Testcontainers module:

```groovy
dependencies {
    testImplementation("org.springframework.boot:spring-boot-testcontainers")
}
```

Then annotate the container:

```java
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;

@SpringBootTest
@Testcontainers
class OrderRepositoryServiceConnectionTests {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>("postgres:16-alpine");
}
```

Spring Boot recognizes the container type and provides connection details for the corresponding auto-configuration. You do not need to manually declare `spring.datasource.url`, username, and password if a matching service connection factory is loaded.

`@ServiceConnection` only works for service types for which Spring Boot provides connection details support. For custom containers or application-specific properties, `@DynamicPropertySource` remains a flexible option. Both approaches can be combined: use service connection for the datasource, and dynamic properties for an endpoint or broker without a matching factory.

## 7. Testing Migrations and Database-Specific Features

A key benefit of containers is running migrations on the same engine used in production. For example, Flyway may use PostgreSQL syntax that H2 does not support or handles differently.

With Spring Boot, if migrations are configured in the application, initializing the context typically runs Flyway before test methods execute. A test can inspect the schema after migration:

```java
import org.springframework.jdbc.core.JdbcTemplate;

@Autowired
JdbcTemplate jdbcTemplate;

@Test
void migrationCreatesExpectedIndex() {
    Integer count = jdbcTemplate.queryForObject("""
            select count(*)
            from pg_indexes
            where schemaname = 'public'
              and indexname = 'idx_orders_order_number'
            """, Integer.class);

    assertThat(count).isEqualTo(1);
}
```

The example queries the PostgreSQL-specific `pg_indexes` catalog. This is something H2 cannot prove equivalently. However, you should not write every repository test using internal SQL catalogs; use them only when the goal is to verify a specific migration or database structure.

Containers are also useful for testing unique constraints, foreign keys, JSONB, sequences, collation, timezones, locking, and isolation. Choose assertions tied to real application risks rather than repeating tests for every database feature.

## 8. Isolating Data Between Tests

A dedicated container does not automatically guarantee clean data between tests if multiple methods share a single static container. The database will retain rows created by earlier tests.

Several ways to manage data:

| Approach | Scope | When appropriate |
|---|---|---|
| `@Transactional` with rollback after test | Test transaction | Repository/service tests running inside a Spring transaction that do not need a commit for other components to read |
| Deleting data in `@BeforeEach` | Specific tables or datasets | Tests needing explicit fixture control |
| Creating a separate schema/database per test | A group of tests or tenant | Migration tests or parallel test execution |
| Container instance per test method | Dedicated container per method | High isolation needs where longer startup time is acceptable |
| Using unique data keys | Each test | Parallel tests or tests that need to preserve committed data |

`@Transactional` can automatically roll back a test-managed transaction, though it is not always enough. If the application opens a separate transaction on another thread, uses `REQUIRES_NEW`, publishes messages after commit, or performs async processing, the test transaction may not roll back those changes. Tests that need to verify real commit behavior should manage transactions explicitly rather than relying on default rollback.

With Flyway or Liquibase, avoid re-running migrations in every method unless necessary. Typically, the container starts once per class, migrations run when the Spring context is created, and each test manages its own data.

## 9. Container Lifecycle and the Spring Context Cache

The JUnit lifecycle and the Spring `ApplicationContext` lifecycle are two separate mechanisms. Spring Test can cache a context for reuse across multiple test classes. If a cached context holds a `DataSource` or broker client pointing to a container that was stopped after the first class, subsequent test classes will fail when reusing that old context.

Key principles:

- Use a static `@Container` when the container should live for the duration of the test class.
- Avoid shutting down a container while a cached Spring context referencing it is still in use.
- If multiple classes share the same context, consider a singleton container with a lifecycle compatible with the entire test suite, or use the same test configuration so Spring recognizes identical contexts.
- Do not share response queues or broker state across parallel tests without isolation.
- Do not create a new container for every method unless startup cost is justified; doing so can slow down the test suite significantly.

You can use the singleton container pattern via a static field in a base class or test utility. However, this pattern must be designed carefully because the JUnit `@Container` extension manages lifecycles per class. If you start a container manually in a static initializer or `@BeforeAll`, the test code itself is responsible for stopping the container at the appropriate time.

## 10. Containers for RabbitMQ

For AMQP brokers such as RabbitMQ, Testcontainers provides a dedicated module:

```groovy
dependencies {
    testImplementation("org.testcontainers:rabbitmq")
}
```

The container can create a dedicated test user and expose the AMQP port:

```java
import org.testcontainers.containers.RabbitMQContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class RabbitMessagingIntegrationTests {

    @Container
    static final RabbitMQContainer RABBIT =
            new RabbitMQContainer("rabbitmq:3.13-management-alpine")
                    .withUser("test", "test", "/")
                    .withPermission("/", "test", ".*", ".*", ".*");

    @DynamicPropertySource
    static void rabbitProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.rabbitmq.host", RABBIT::getHost);
        registry.add("spring.rabbitmq.port", RABBIT::getAmqpPort);
        registry.add("spring.rabbitmq.username", () -> "test");
        registry.add("spring.rabbitmq.password", () -> "test");
    }
}
```

`RabbitMQContainer` waits for the broker to be ready and exposes the host and mapped AMQP port. Using a dedicated user avoids relying on the default `guest` account, which is often restricted from connecting outside the container host.

Suppose the application has an `orders.events` queue and `RabbitTemplate` is auto-configured:

```java
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class RabbitTestConfiguration {

    @Bean
    Queue ordersQueue() {
        return new Queue("orders.events", false);
    }
}
```

A test can publish a message and read it back from the broker:

```java
import java.time.Duration;

import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.RabbitMQContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
@SpringBootTest
class RabbitTemplateIntegrationTests {

    @Container
    static final RabbitMQContainer RABBIT =
            new RabbitMQContainer("rabbitmq:3.13-management-alpine")
                    .withUser("test", "test", "/")
                    .withPermission("/", "test", ".*", ".*", ".*");

    @Autowired
    RabbitTemplate rabbitTemplate;

    @DynamicPropertySource
    static void rabbitProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.rabbitmq.host", RABBIT::getHost);
        registry.add("spring.rabbitmq.port", RABBIT::getAmqpPort);
        registry.add("spring.rabbitmq.username", () -> "test");
        registry.add("spring.rabbitmq.password", () -> "test");
    }

    @Test
    void publishesMessageToRabbitQueue() {
        rabbitTemplate.convertAndSend("orders.events", "order-42");

        String received = awaitMessage();
        assertThat(received).isEqualTo("order-42");
    }

    private String awaitMessage() {
        long deadline = System.nanoTime() + Duration.ofSeconds(5).toNanos();
        while (System.nanoTime() < deadline) {
            Object message = rabbitTemplate.receiveAndConvert("orders.events");
            if (message != null) {
                return message.toString();
            }
            try {
                Thread.sleep(50);
            }
            catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new AssertionError("Interrupted while waiting for message", ex);
            }
        }
        throw new AssertionError("No message arrived in orders.events");
    }
}
```

This example verifies publishing and consuming through a real broker. The queue must be declared before sending; you can use a `Queue` bean as configured above or declare the topology through application configuration. The loop uses a bounded deadline to wait for the message instead of relying on scheduling timing. For tests waiting on an asynchronous listener to process a message, use Awaitility or a synchronization latch/condition rather than polling the queue directly.

## 11. Containers for Kafka

Kafka requires a bootstrap server accessible to producers and consumers. The Testcontainers Kafka module provides a dedicated container:

```groovy
dependencies {
    testImplementation("org.testcontainers:kafka")
}
```

Example using the Apache Kafka image:

```java
import org.testcontainers.kafka.KafkaContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@SpringBootTest
class KafkaIntegrationTests {

    @Container
    static final KafkaContainer KAFKA = new KafkaContainer(
            DockerImageName.parse("apache/kafka-native:3.8.0"));

    @DynamicPropertySource
    static void kafkaProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.kafka.bootstrap-servers",
                KAFKA::getBootstrapServers);
    }
}
```

`getBootstrapServers()` returns the address the test process can use to connect to the broker. Do not construct `localhost:9092` manually, because Testcontainers may map the broker to a different port and advertised listener configuration depends on the container.

With Spring Kafka, `KafkaTemplate` and listener containers can be created from `spring.kafka.bootstrap-servers`. A publisher test can send a message:

```java
@Autowired
KafkaTemplate<String, String> kafkaTemplate;

@Test
void publishesOrderEvent() throws Exception {
    kafkaTemplate.send("orders", "order-42", "CREATED")
            .get(10, TimeUnit.SECONDS);
}
```

This snippet confirms the producer completed sending according to the future, but to prove the broker stored the message and a consumer can read it, you need a test consumer or verification of an application listener. The consumer needs its own group ID, `auto.offset.reset=earliest` if it needs to read messages published before partition assignment, and proper cleanup after the test.

When testing an asynchronous listener, do not check only that `KafkaTemplate.send(...)` completed. The broker receiving the record and the listener processing the record are two distinct events. Use a latch, Awaitility, or an observable state in the database to wait for the listener outcome with a finite timeout.

## 12. Using a Database and Broker in the Same Test

Many business flows both write to a database and publish a message. Containers allow integration testing across both boundaries:

```java
@Testcontainers
@SpringBootTest
class OrderPublicationIntegrationTests {

    @Container
    static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Container
    static final RabbitMQContainer RABBIT =
            new RabbitMQContainer("rabbitmq:3.13-management-alpine")
                    .withUser("test", "test", "/")
                    .withPermission("/", "test", ".*", ".*", ".*");

    @DynamicPropertySource
    static void infrastructureProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username", POSTGRES::getUsername);
        registry.add("spring.datasource.password", POSTGRES::getPassword);
        registry.add("spring.rabbitmq.host", RABBIT::getHost);
        registry.add("spring.rabbitmq.port", RABBIT::getAmqpPort);
        registry.add("spring.rabbitmq.username", () -> "test");
        registry.add("spring.rabbitmq.password", () -> "test");
    }

    // Inject OrderService, OrderRepository and a message consumer/observer.
}
```

The test invokes the order creation use case, then asserts that the row was persisted in PostgreSQL and the corresponding event appeared in RabbitMQ or was processed by a consumer. If the application uses a transactional outbox, the test should verify that the outbox record is written in the same transaction, then check that the publisher converts that record into a message via the actual mechanism.

Regarding transactions between a database and a broker, do not assume the two systems automatically commit atomically together. If the application uses `@TransactionalEventListener`, outbox, retries, or publisher confirms, the test must verify that specific mechanism. Container tests help observe real integration behavior, but they do not provide distributed transactions on their own.

## 13. Waiting for Service Readiness and Configuring Readiness Checks

A container in the `running` state does not guarantee the application inside is ready to accept requests. Specialized Testcontainers modules already define appropriate wait strategies, such as waiting on a port or a database startup log message.

With `GenericContainer`, declare readiness explicitly:

```java
GenericContainer<?> service = new GenericContainer<>("some-service:1.2.3")
        .withExposedPorts(8080)
        .waitingFor(Wait.forHttp("/health").forStatusCode(200));
```

You can use `Wait.forListeningPort()` or `Wait.forLogMessage(...)` depending on the service. Avoid using `Thread.sleep(5000)` to guess when a container is ready. A wait strategy has explicit timeouts and conditions, so tests report clearer errors when a service fails to start.

If an image has a long bootstrap time, inspect the container logs and configure the wait strategy accordingly. Do not increase timeouts indefinitely to mask startup failures or misconfigurations.

## 14. Pinning Images, Data, and Configuration for Repeatable Tests

Container tests can still become flaky if images, data, or configurations change arbitrarily.

**Pin image versions.** Use specific tags, or better yet image digests in pipelines requiring strict reproducibility. Avoid `latest`.

**Use explicit initialization data.** Create schemas via migrations and fixture data via builders or test SQL. Do not rely on leftover data from previous runs.

**Separate test credentials.** Use dedicated usernames/passwords for containers; never place production secrets in tests.

**Set timezone and locale intentionally.** If logic depends on timezone, explicitly configure both the database and JVM so tests do not vary across developer machines or CI.

**Control resources.** Set timeout limits and avoid running too many heavy containers concurrently on runners with limited CPU/RAM.

## 15. Running Testcontainers in CI

The test machine must have a Docker-compatible container runtime accessible to Testcontainers. On developer machines, Docker Desktop or Docker Engine typically provides that environment. In CI, runners need access to the Docker daemon/socket or a supported remote runtime configuration.

Items to prepare in the pipeline:

- Ensure the container runtime is active before running tests.
- Grant daemon access permissions to the process running Gradle/Maven.
- Allow pulling images or configure an appropriate registry mirror/cache.
- Allocate sufficient CPU, RAM, and disk for database/broker images.
- Use CI timeouts aligned with image pull and service bootstrap times.
- Collect container logs when tests fail to diagnose readiness or configuration errors.
- Clean up containers after the job, even if the test run is canceled.

If CI does not permit Docker or a container runtime, Testcontainers cannot start services in the usual way. In that case, you can use CI-provided service containers, a managed shared test environment, or run container tests in a dedicated job/runner. Do not silently skip important integration tests simply because a runner lacks a runtime; represent that test group explicitly in the pipeline.

## 16. Using Container Reuse and Singletons Thoughtfully

Starting PostgreSQL or Kafka can take noticeable time. Testcontainers supports container reuse in some development environments, but reuse is not suitable by default for CI because data and state can persist across runs.

If reuse is enabled, tests themselves must ensure database schemas, queues/topics, and data are properly reset. Never rely on test order or assume a container is fresh. In CI, test-managed lifecycles are generally more reproducible.

Singleton containers can reduce startup overhead when many test classes use the same service. However, they increase the risk of shared state and interactions with the Spring context cache. Use them only when justified by measured savings and backed by clear isolation conventions.

## 17. When to Use @ServiceConnection, DynamicPropertySource, or Custom Configuration?

| Configuration approach | Advantages | Limitations |
|---|---|---|
| `@ServiceConnection` | Less boilerplate; Spring Boot automatically generates connection details | Only applies to container/service types supported by Boot |
| `@DynamicPropertySource` | Flexible; can map any property from a container | Requires manually declaring property names and getters |
| `ApplicationContextInitializer` | Can alter environment before context refresh | More code; usually unnecessary for simple cases |
| Dedicated test property file | Readable for static values | Unsuitable for dynamic ports assigned by containers |

For common databases in Spring Boot, `@ServiceConnection` is usually the cleanest option. For brokers, custom services, or multiple specialized properties, `@DynamicPropertySource` is explicit and easy to control.

## 18. Common Mistakes When Using Test Containers

| Practice | Problem | Better approach |
|---|---|---|
| Hardcoding ports like `5432` or `9092` | Host port may be mapped differently or already in use | Retrieve JDBC URL, AMQP port, or bootstrap servers from the container |
| Using H2 instead of PostgreSQL and treating them as equivalent | SQL, data types, transactions, and constraints can differ | Run integration tests on the production engine |
| Only mocking repositories or KafkaTemplate | Does not test drivers, protocols, serializers, or the broker | Use containers for tests at the integration boundary |
| Using the `latest` image | Tests can change behavior when the image updates | Pin tags or digests |
| Not cleaning data between methods | Tests depend on execution order or stale data | Transaction rollback, fixture cleanup, or separate schemas |
| Stopping a container while the Spring context is still cached | Beans retain URLs pointing to a stopped service | Align container lifecycle with context lifecycle |
| Only checking that the producer future completed | Does not prove the consumer processed the message | Wait for and verify the outcome at the consumer |
| Using `Thread.sleep` to wait for startup | Slow and flaky tests | Use wait strategies, Awaitility, or latches |
| Running too many brokers/databases in parallel | CI runs out of CPU/RAM and tests slow down abnormally | Limit parallelism or split test groups |
| Using reuse without resetting state | Results depend on the previous run | Disable reuse in CI or manage resets explicitly |

## 19. Workflow for Building Integration Tests with Databases and Brokers

1. Identify the real technology the application uses: PostgreSQL, MySQL, Kafka, RabbitMQ, or another service.
2. Choose the matching Testcontainers module and pin the image version.
3. Declare the container with `@Container`, choosing static or instance scope based on required isolation.
4. Configure Spring via `@ServiceConnection` or `@DynamicPropertySource`.
5. Allow migrations and relevant production configuration to load in the test context.
6. Prepare repeatable data/queue/topic fixtures.
7. Execute the use case through application beans rather than calling driver or broker APIs directly if the goal is testing the integration layer.
8. Assert outcomes in the database or observe messages from the broker/consumer.
9. For async messaging, wait on completion conditions with a finite timeout.
10. Clean up data and stop containers in a lifecycle compatible with the Spring context cache.
11. Ensure CI has a container runtime, sufficient resources, and image pull permissions.

## 20. References

- [Testcontainers for Java — Documentation](https://java.testcontainers.org/): concepts, lifecycle, JUnit Jupiter integration, and service modules.
- [Testcontainers — PostgreSQL Module](https://java.testcontainers.org/modules/databases/postgres/): `PostgreSQLContainer` configuration and JDBC connection details.
- [Testcontainers — RabbitMQ Module](https://java.testcontainers.org/modules/rabbitmq/): RabbitMQ container configuration.
- [Testcontainers — Kafka Module](https://java.testcontainers.org/modules/kafka/): Kafka container and bootstrap servers.
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): Testcontainers integration and `@ServiceConnection`.
- [Spring Framework — DynamicPropertySource](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html): registering dynamic properties for test contexts.

Test containers enable a Spring application to work with real databases and brokers in a reproducible local environment. Use the right image and version, obtain addresses from the container, wire Spring with service connections or dynamic properties, and test behavior at the integration boundary. Manage lifecycle and data explicitly so tests can run independently on both developer machines and CI.
