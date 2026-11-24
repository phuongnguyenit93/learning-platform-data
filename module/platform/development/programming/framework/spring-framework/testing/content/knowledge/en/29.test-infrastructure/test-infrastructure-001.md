# Choosing Real Resources, Embedded Services, or Mocked Services

A Spring test often requires multiple resources external to the application: databases, HTTP APIs, message brokers, file storage systems, caches, or authentication services. When running tests, we must decide whether to connect to a real service, use an embedded (in-memory) implementation, or replace the dependency with a mock, stub, or fake.

There is no single right choice for every test. Real services provide high fidelity, but they are often slow, costly, and hard to control. Embedded implementations make tests fast, self-contained, and easy to isolate, but they can differ from production behavior. Mocks and fakes allow testing logic within a narrow scope, but they do not prove that the application communicates properly with external systems.

The goal is to choose the resource appropriate for the behavior being verified, and then manage test lifecycle and test data so that results are stable and repeatable.

## 1. Three Ways to Provide Resources for Tests

### Using Real Services

The test connects to a real instance of the service the application uses, such as PostgreSQL, Kafka, Redis, or an HTTP API in a test environment.

"Real" can mean a production-compatible service running locally in a container, a dedicated instance in CI, or a sandbox provided by a service vendor. It does not necessarily mean calling production. For databases or brokers, Testcontainers often spins up a real instance inside a dedicated test container.

Advantages:

- Verifies the actual protocol, dialect, constraints, and behavior of the technology.
- Surfaces differences between application libraries and the systems used in production.
- Allows testing migrations, transactions, locking, broker acknowledgments, or service-specific features.

In return, tests must start and clean up resources, can take more time, require Docker or a suitable CI environment, and may fail due to infrastructure factors.

### Using Embedded or In-Memory Implementations

An embedded implementation provides a lightweight version that runs in the same process or starts automatically with the test. Common examples are in-memory H2 for databases, embedded Kafka for messaging tests, or a mock HTTP server running on loopback.

Advantages:

- Tests start on their own without depending on a shared instance.
- Execution is usually fast and data is easy to clean up.
- Well-suited for frequent integration tests in the development feedback loop.

The disadvantage is that embedded implementations may not fully reproduce the dialect, concurrency, security configuration, or features of the production service. Passing tests on H2 do not guarantee that migrations will run correctly on PostgreSQL if the two database engines have relevant differences.

### Using Mocked Services or Test Doubles

A mock, stub, or fake replaces a real dependency with an object controlled by the test. For example, mocking a `PaymentGateway`, using a fake repository that stores data in a map, or configuring `MockRestServiceServer` to return predefined HTTP responses.

Advantages:

- Tests are fast, deterministic, and independent of the network or external services.
- Easy to simulate rare scenarios such as timeouts, authentication errors, invalid data, or unexpected responses.
- Well-suited for testing business rules and how the application reacts to dependency outcomes.

The disadvantage is that the test only verifies behavior against the test double. If you mock too deeply or misrepresent the contract, tests may pass while the application fails against the real service.

## 2. Choosing Based on the Question the Test Needs to Answer

Before choosing a resource, identify what the test is trying to prove:

| Question to answer | Usually suitable choice |
| --- | --- |
| How do business rules handle data and errors? | Mock or fake at the application boundary. |
| Does the repository generate the right SQL, mapping, constraints, and transactions? | Embedded database for speed; production-equivalent database to confirm compatibility. |
| Do migrations run on the actual production database engine? | Real database of the same type, typically via Testcontainers or a dedicated environment. |
| Does the HTTP adapter send the right method, URL, headers, and body? | Mock HTTP server combined with the real HTTP client. |
| Does the application interact properly with a partner API in a sandbox environment? | Sandbox or real integration environment, usually for a controlled subset of tests. |
| Do consumer and producer exchange messages properly with the broker? | Embedded broker for fast tests; real broker in a container for production-specific features. |
| Are files created, read, and deleted properly on the filesystem? | Temporary directory on the real filesystem via `@TempDir`. |

A system typically needs multiple levels of testing. Unit tests use mocks/fakes to check logic; integration tests use embedded services or containers to verify wiring; a smaller set of end-to-end tests use real services to confirm system-wide contracts.

## 3. Databases: H2, Real Databases, and Testcontainers

Databases are a classic example of the difference between embedded implementations and production services. `@DataJpaTest` typically configures a test slice for JPA and can automatically replace the datasource with an embedded database if a suitable dependency is on the classpath.

Example test using in-memory H2:

```java
@DataJpaTest
class PersonRepositoryTest {

    @Autowired
    PersonRepository repository;

    @Test
    void shouldFindPersonByEmail() {
        repository.save(new Person("Lan", "lan@example.test"));

        assertThat(repository.findByEmail("lan@example.test"))
                .isPresent();
    }
}
```

This test is fast and self-contained. H2 works well for testing many standard repository operations, but you should not assume it is equivalent to PostgreSQL, MySQL, or SQL Server. Differences can appear in:

- SQL syntax, data types, sequences, and key generation strategies.
- Collation, string comparison, timezones, and timestamp precision.
- Constraints, indexes, locking, and transaction isolation.
- Stored procedures, functions, triggers, or engine-specific extensions.
- Behavior of migration tools when running against a specific dialect.

If the production application uses PostgreSQL and relies on PostgreSQL-specific characteristics, run integration tests against real PostgreSQL. Testcontainers can start a PostgreSQL container for the test:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class PersonRepositoryPostgresTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("app_test")
                    .withUsername("test")
                    .withPassword("test");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    PersonRepository repository;

    @Test
    void shouldPersistPersonInPostgres() {
        Person saved = repository.saveAndFlush(
                new Person("Lan", "lan@example.test")
        );

        assertThat(repository.findById(saved.getId())).isPresent();
    }
}
```

`@Container` marks a container managed by the JUnit Jupiter extension. `@DynamicPropertySource` registers connection properties retrieved from the container after it starts. `SpringBootTest` loads the application context and uses the datasource configured from those dynamic properties.

With Spring Boot versions that support Testcontainers service connections, you can use `@ServiceConnection` so Boot infers connection details from the container instead of registering each property manually with `@DynamicPropertySource`:

```java
@Testcontainers
@SpringBootTest
class PersonRepositoryPostgresTest {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");
}
```

`@ServiceConnection` belongs to Spring Boot, not Spring Framework core. It requires the corresponding Testcontainers dependency and the service connection module compatible with the Boot version in use. Without this auto-configuration, the `@DynamicPropertySource` approach remains an explicit option.

### When to Keep H2 and When to Use a Production-Compatible Database?

| Test type | Recommended database | Reason |
| --- | --- | --- |
| Simple CRUD repository tests run frequently | H2 or embedded DB | Speed and isolation. |
| Custom SQL, native query, or migration tests | Production-equivalent database | Verify real dialect and syntax. |
| Locking, isolation, complex constraint tests | Production-equivalent database | Transaction behavior depends on the engine. |
| Standard JPA mapping tests | H2 for fast feedback, plus periodic container tests | Balance speed and fidelity. |

You do not have to run every test against a container if that makes the feedback loop too slow. You can keep a fast suite with H2 and add a group of integration tests running on a production-compatible database in CI.

## 4. External HTTP APIs: Mock Server, Sandbox, or Real Service

When an application calls an HTTP API, there are three common levels of testing.

### Mocking Request/Response at the Client Layer

For `RestClient` or `RestTemplate`, Spring Test provides `MockRestServiceServer`. The test uses the application's real HTTP client, intercepts the request at the request factory, verifies the method/URL/headers/body, and returns a mocked response.

```java
RestClient.Builder builder = RestClient.builder()
        .baseUrl("https://inventory.example");

MockRestServiceServer server = MockRestServiceServer
        .bindTo(builder)
        .build();

InventoryHttpAdapter adapter = new InventoryHttpAdapter(builder.build());

server.expect(requestTo("https://inventory.example/api/items/SKU-1"))
        .andExpect(method(HttpMethod.GET))
        .andRespond(withSuccess(
                """
                {"sku":"SKU-1","quantity":12}
                """,
                MediaType.APPLICATION_JSON
        ));

assertThat(adapter.findBySku("SKU-1"))
        .isEqualTo(new InventoryItem("SKU-1", 12));
server.verify();
```

This is a good choice for verifying that the adapter builds the right request and parses the response properly. It does not call an external service and does not verify that the partner server is up.

With `WebClient`, MockWebServer or WireMock is commonly used to start a local HTTP server, and `WebClient` is configured to call that address. This approach allows testing requests through the actual HTTP connector.

### Using a Vendor Sandbox

A sandbox is a testing environment operated by the API provider. It is appropriate when you need to verify real contracts, request signatures, OAuth, multi-step workflows, or behaviors that a mock server cannot reliably emulate.

Sandbox tests require managing credentials, test data, quotas, response latency, and potential service downtime. You should not make every unit test depend on a sandbox, as the suite will become slow and flaky due to factors outside the application. Typically, only a subset of integration/contract tests run on a schedule or in an appropriate pipeline stage.

### Calling a Real Service

Some systems require testing against a real service, such as verifying payment integration in a staging environment. Use only dedicated test accounts and test data, establish cleanup procedures, and avoid impacting production users or data. Tests need timeouts, reasonable retries, and sufficient logging to diagnose environment failures.

## 5. Message Brokers: Embedded Brokers vs. Real Brokers

For applications using Kafka, RabbitMQ, or ActiveMQ, tests must verify that producers send the right messages and consumers handle payloads, headers, keys, or acknowledgments properly.

Some Spring Kafka projects use an embedded Kafka broker for testing:

```java
@SpringBootTest
@EmbeddedKafka(
        topics = "orders-test",
        partitions = 1,
        bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class OrderEventIntegrationTest {

    @Autowired
    KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    @Test
    void shouldPublishOrderCreatedEvent() {
        kafkaTemplate.send(
                "orders-test",
                "order-42",
                new OrderCreatedEvent(42L)
        );
        // Consumer/test listener verifies that the message was received.
    }
}
```

`@EmbeddedKafka` is provided by Spring Kafka test support, not Spring Framework core. It starts an embedded broker for tests. You need to add a `spring-kafka-test` dependency compatible with your Spring Kafka version and configure a consumer/test listener to confirm that the message is actually processed.

An embedded broker is useful for fast tests covering serialization, listeners, routing, and consumer groups at an appropriate level. When the application relies on production-specific broker features, security configuration, transactions, replication, or a specific broker version, supplement tests with a real broker in a container or integration environment.

With RabbitMQ, you can run a RabbitMQ container via Testcontainers to verify exchanges, queues, bindings, acknowledgments, and dead-letter configurations on a real broker. A mock `RabbitTemplate` is suitable for testing publisher invocation logic in unit tests, but it does not confirm that the topology is created properly on the broker.

## 6. Filesystem and Local Resources

Not every resource requires a network service. For code that reads/writes files, using a temporary directory managed by JUnit is usually better than mocking every `Files` operation:

```java
class ReportWriterTest {

    @TempDir
    Path tempDirectory;

    @Test
    void shouldWriteReport() throws IOException {
        Path report = tempDirectory.resolve("report.txt");

        new ReportWriter().write(report, "Quarterly report");

        assertThat(Files.readString(report))
                .isEqualTo("Quarterly report");
    }
}
```

`@TempDir` provides a temporary directory that JUnit cleans up according to the test lifecycle. This test uses the real filesystem of the test machine while isolating data in a dedicated directory. It verifies real file creation and reading behavior better than deeply mocking static methods of `Files`.

If the application uses S3, Azure Blob Storage, or another object storage service, you can use a fake/local emulator such as LocalStack or MinIO in integration tests, depending on the target service. Mocking the storage interface works for business-logic unit tests; emulators/containers help verify requests, metadata, and API compatibility; sandbox accounts or real environments are suitable for a final set of contract tests.

## 7. How Do Fakes, Stubs, Mocks, and Embedded Services Differ?

These terms are often used interchangeably, but they have distinct meanings:

| Test double type | Characteristics | Example |
| --- | --- | --- |
| Dummy | Object passed only to fill a parameter slot, never used. | A `Clock` or collaborator not invoked in a specific test. |
| Stub | Returns predefined data to control execution branches. | `when(gateway.find()).thenReturn(item)`. |
| Mock | Records and verifies expected interactions. | `verify(gateway).publish(event)`. |
| Fake | Simple implementation with working behavior. | An in-memory repository using a `Map` to store entities. |
| Embedded service | A lightweight real service implementation running in the test environment. | H2 or embedded Kafka. |
| Mock server | Server simulating a protocol so the client sends real requests to it. | MockRestServiceServer, MockWebServer, WireMock. |

Fakes and embedded services are not the same as mocks. A fake repository can execute queries in memory, while an embedded database executes SQL and transactions according to its engine. A mock server accepts HTTP requests via the real client, while responses are controlled by the test.

Choose the replacement type based on the behavior to be verified. Do not use a mock in place of persistence testing when the goal is to verify SQL; do not spin up a database container for a unit test that only needs to check a simple business branch.

## 8. Configuring Resources with Spring Test

Spring Test provides several mechanisms for supplying endpoints, credentials, and connection details to the test application context.

### `@TestPropertySource`

Declare test-specific properties:

```java
@SpringJUnitConfig(AppConfig.class)
@TestPropertySource(properties = {
        "inventory.base-url=http://localhost:9090",
        "feature.audit.enabled=false"
})
class InventoryAdapterTest {
}
```

These properties are added to the `Environment` of the test context. You can also load dedicated properties files via the `locations` attribute.

### `@DynamicPropertySource`

When a resource address is only known after starting a container, register properties dynamically:

```java
@DynamicPropertySource
static void properties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
```

The method must be `static` and accept `DynamicPropertyRegistry`. Suppliers are only evaluated when the property needs to be resolved. This mechanism fits random URLs/ports assigned by containers or mock servers.

### `@TestConfiguration`

You can declare test-only beans using `@TestConfiguration`, such as a fake adapter or a replacement bean. Ensure the test configuration is imported or loaded appropriately; avoid silently replacing dependencies in ways that make tests appear to use the real service.

### Profiles

`@ActiveProfiles("test")` can select a test profile. Profiles help separate configuration by environment, but they do not automatically provision a database, broker, or HTTP service. You still need to provide the corresponding resources and make clear which implementation the test is using.

## 9. Managing Lifecycle, Data, and Isolation

A test may pass in isolation yet fail across the full suite if resources or data are shared. Whether using real services, embedded implementations, or mock servers, manage lifecycles explicitly.

### Starting and Stopping Resources

- Use JUnit lifecycle methods (`@BeforeAll`, `@BeforeEach`, `@AfterEach`, `@AfterAll`) or dedicated extensions to create and stop resources.
- With Testcontainers, use the JUnit Jupiter extension or a lifecycle mechanism appropriate for your version.
- With MockWebServer/WireMock, start before requests and stop after the test or class.
- Avoid leaving servers or containers alive beyond the test lifecycle unless sharing is intentional.

### Data Isolation

- Give each test its own keys, topic names, or directories whenever possible.
- Clean up data after tests or use a fresh database/container at the appropriate scope.
- Do not let tests depend on execution order or data created by a previous test.
- When sharing a container across multiple tests, still isolate schemas, tables, topics, or keys.

### Transaction Rollback

`@Transactional` on tests can roll back database changes after a test, but it does not automatically roll back side effects outside the database. Messages already sent to a broker, HTTP requests made to external services, or files written to disk may still remain. Clean up those resources separately.

### Timeouts and Retries

Tests using real services need finite timeouts to avoid hanging the suite. Retries should only be used when failures are transient and retrying reflects the application's actual behavior. Retrying tests indiscriminately can mask race conditions or configuration bugs.

## 10. Avoiding Production Resources in Regular Tests

Connecting tests to production databases, brokers, or APIs can alter real data, consume quotas, send notifications to users, or incur costs. Regular tests should use accounts and resources dedicated strictly to testing.

If testing against a production-like system is unavoidable, use a staging/sandbox environment, dedicated credentials, clearly identifiable test data, and a cleanup procedure. Avoid putting secrets in source code or logs; retrieve connection details from environment configuration or a managed secret store.

Avoid using a shared instance where all developers and pipelines write to the same tables or topics without isolation. Tests running in parallel can overwrite each other's data or consume each other's messages.

## 11. Practical Selection Matrix

| Resource | Fast, isolated tests | High-fidelity integration tests | Contract / end-to-end tests |
| --- | --- | --- | --- |
| Database | H2 or fake repository depending on goal | Testcontainers with production-equivalent DB | Staging or dedicated DB with production-like config |
| HTTP outbound | Mock business interface | MockRestServiceServer, MockWebServer, or WireMock | Sandbox or real service instance |
| Kafka/RabbitMQ | Mock publisher or fake event bus | Embedded broker or broker container | Staging broker and related services |
| Filesystem | `@TempDir` on real filesystem | Filesystem/container mirroring target environment | Storage integration environment |
| Object storage | Mock storage port | LocalStack/MinIO or suitable emulator | Dedicated sandbox/tenant storage |
| Identity/OAuth | Stub token provider or mock port | Mock identity server or container | Identity sandbox with real flows |

This matrix is only a starting point. If a feature depends on engine-specific or provider-specific behavior, raise test fidelity in that specific area. You do not need real services for every test.

## 12. A Multi-Layered Strategy for a Spring Project

A Spring project can organize tests into the following groups:

```text
Unit tests
  - Mock/fake application ports
  - Verify business rules
  - Fast, run frequently

Integration tests
  - Embedded services or Testcontainers
  - Verify repositories, HTTP adapters, messaging, serialization
  - Run in CI

Contract / end-to-end tests
  - Sandbox or real services in a dedicated environment
  - Verify interactions between systems
  - Run selectively, usually less frequently
```

For example, in an order creation flow:

1. Unit tests for `OrderService` mock `InventoryGateway` to verify stock availability rules.
2. Tests for `InventoryHttpAdapter` use `MockRestServiceServer` to verify URLs, headers, JSON, and error mapping.
3. Repository tests use a PostgreSQL container to verify transactions and schemas.
4. Final integration tests call the inventory system's sandbox to confirm the real contract if business risk warrants it.

Each group answers a distinct question. Layering gives the suite a large base of fast, deterministic tests while still providing sufficient evidence of integration with real infrastructure.

## 13. Common Mistakes

**Using H2 and concluding the application is compatible with PostgreSQL.**

H2 and PostgreSQL can differ in SQL, data types, constraints, and transactions. Run additional tests on the actual database engine when those characteristics matter.

**Mocking the repository in a test and calling it a persistence integration test.**

A mock repository does not execute SQL or transactions. Use a real or embedded database when the goal is to test persistence.

**Calling a real partner API in every unit test.**

This slows down the suite, risks hitting quota limits, and introduces network dependency. Mock interfaces for business logic, use a mock HTTP server for adapters, and reserve sandboxes for contract tests.

**Using an embedded broker while ignoring differences from the production broker.**

An embedded broker may not reproduce security configuration, replication, or broker-specific features. Add tests with a production-equivalent broker when needed.

**Assuming transaction rollback cleans up all side effects.**

Database rollback does not unpublish messages, undo sent HTTP requests, or delete created files. Separate cleanup is required.

**Sharing data and resources between tests running in parallel.**

Tests can overwrite data or read each other's messages. Use dedicated resource namespaces, unique keys, or proper isolation mechanisms.

**Mocking too deeply into framework APIs.**

Mocking fluent chains often couples tests to specific method call sequences. Mock application interfaces or use a mock server at the protocol boundary.

## 14. Decision and Implementation Workflow

When adding an external dependency to tests, you can follow this sequence:

1. Identify the behavior to test: business logic, persistence, protocol, configuration, or end-to-end integration.
2. Identify service characteristics that affect that behavior: dialect, protocol, transaction, serialization, concurrency, or security.
3. Choose the minimum fidelity level sufficient to verify the behavior: mock/fake, embedded, container, or sandbox/real service.
4. Configure endpoints and credentials via Spring Test properties or dynamic properties; never hard-code secrets.
5. Manage startup/shutdown and cleanup explicitly.
6. Isolate data so tests run independently and can execute in parallel.
7. Add higher-fidelity tests when mocks or embedded services cannot verify critical characteristics.
8. Run fast test groups frequently and real-infrastructure test groups in CI on an appropriate schedule or stage.

## Conclusion

Choosing real services, embedded implementations, or mocked services depends on the behavior the test needs to verify. Mocks and fakes suit business logic; embedded services support fast integration checks; Testcontainers and mock HTTP servers provide higher fidelity at data and protocol boundaries; sandboxes or real services fit a targeted set of contract and end-to-end tests.

No single resource type can replace all other test levels. A sound Spring Testing strategy combines multiple layers, manages lifecycles and data explicitly, and uses the real production engine or protocol whenever those differences materially affect application behavior.
