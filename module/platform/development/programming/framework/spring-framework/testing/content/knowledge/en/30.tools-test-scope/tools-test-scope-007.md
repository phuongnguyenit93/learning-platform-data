# Testcontainers Adds Real Infrastructure Management

A Spring application rarely runs in isolation. It may need PostgreSQL, Redis, Kafka, RabbitMQ, Elasticsearch, a cloud emulator, or several other infrastructure components. In production, these components have their own versions, protocols, configurations, and lifecycles. If tests only replace them with mocks or substitute databases, the test suite can miss integration bugs.

Testcontainers is a Java library that lets tests manage those services as containers. A test declares the image, configuration, ports, network, and readiness condition; Testcontainers creates the container, provides dynamic endpoints to the application, and cleans up resources according to the chosen lifecycle. As a result, tests can use real infrastructure on a small, reproducible scale without depending on a shared server.

In Spring Framework Testing, Testcontainers adds infrastructure management to Spring Test. Spring still manages the `ApplicationContext`, beans, transactions, and dependency injection; Testcontainers manages the external services those beans connect to. The two parts combine to verify real integration paths.

## 1. What Does Testcontainers Manage?

Testcontainers drives a Docker-compatible container runtime. Instead of writing custom scripts to install and start PostgreSQL or Kafka on a developer's machine, the test declares a Java object describing the needed service.

```text
JUnit test
    |
    v
Testcontainers API
    |
    | create / start / wait / stop
    v
Container runtime
    |
    +--------------------+--------------------+
    |                    |                    |
    v                    v                    v
PostgreSQL           Redis                 RabbitMQ
    |                    |                    |
    +--------------------+--------------------+
                         |
                         v
                Spring ApplicationContext
                         |
                         v
                 Integration assertions
```

Testcontainers can manage:

- Containers with dedicated modules such as PostgreSQL, MySQL, Kafka, RabbitMQ, or Redis.
- Custom images, internal services, or programs that can only run inside a container.
- Networks across multiple containers so they communicate using aliases and internal ports.
- Ports published to the test process so the application running on the host can connect.
- Environment variables, commands, configuration files, volumes, and initialization data.
- Readiness conditions, timeouts, logs, and cleanup.

Testcontainers does not replace the Spring IoC container. It does not decide which beans are injected, which transactions are committed, or which HTTP endpoints are called. It provides out-of-process infrastructure; Spring is configured to connect to that infrastructure.

## 2. Why Is Real Infrastructure Important in Integration Tests?

A mock can verify that a service called `repository.save(...)`, yet cannot verify that the database executes the SQL statement. H2 may run fast, yet does not guarantee equivalence with PostgreSQL regarding JSONB, sequences, collations, locking, or migration syntax. Mocking `KafkaTemplate` can verify a publish call, yet does not test the broker, serializer, or consumer group.

Container testing establishes a real integration boundary:

| Component | What tests can verify |
|---|---|
| Database | Driver, SQL, migrations, constraints, transactions, indexes, and isolation |
| Cache | Protocol, serialization, TTL, eviction, and client configuration |
| Message broker | Connectivity, publish/consume, routing, acknowledgements, topics/queues, and serializers |
| Search engine | Mappings, query DSL, analyzers, and index lifecycle |
| Cloud emulator | SDK configuration, endpoints, request signing, and emulator operations |
| Internal service | Protocol, health checks, configuration, and inter-component communication |

Container testing does not mean running every service in every test. Pick the exact services that the integration contract depends on. Unit tests remain appropriate for pure logic; container tests focus on where the application interacts with external technology.

## 3. Core Concepts

A Testcontainers container is typically described by the following properties:

| Property | Meaning |
|---|---|
| Image | Image and version of the service to run |
| Exposed port | Internal port the service listens on |
| Mapped port | Host port mapped by the runtime for the test process to connect |
| Environment | Environment variables to configure the image |
| Command | Startup command or arguments |
| Volume/bind mount | Data or files shared with the container |
| Network | Network for containers to communicate with one another |
| Wait strategy | Condition determining when the service is ready |
| Lifecycle | When the container is created, started, stopped, and cleaned up |

An important distinction is between internal ports and host ports. For example, PostgreSQL listens on port `5432` inside the container, while Testcontainers may map it to `32781` on the host. Tests must obtain the dynamic port from the container rather than assuming the two ports are identical.

## 4. Adding Dependencies and Managing Versions

Testcontainers is split into modules. A project usually needs the JUnit Jupiter module and the module matching the service. Example following the Testcontainers 1.x module layout:

```groovy
dependencies {
    testImplementation(platform("org.testcontainers:testcontainers-bom:1.20.6"))
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:postgresql")
    testImplementation("org.testcontainers:rabbitmq")
}
```

With Maven, use the BOM in `dependencyManagement` so all Testcontainers modules share the same version:

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
</dependencies>
```

The coordinates above illustrate the 1.x line. When a project uses a different major version, follow the BOM and module names of that major version; do not mix modules from different major versions. JDBC drivers, Spring Data, Spring AMQP, or Spring Kafka remain application dependencies and are not replaced by Testcontainers.

## 5. Using Dedicated Modules When Available

For popular technologies, Testcontainers provides helper classes to configure the image, ports, and readiness. Example for PostgreSQL:

```java
import org.testcontainers.containers.PostgreSQLContainer;

PostgreSQLContainer<?> postgres = new PostgreSQLContainer<>("postgres:16-alpine")
        .withDatabaseName("orders")
        .withUsername("test")
        .withPassword("test");
```

Dedicated modules reduce manual setup and usually include a wait strategy tailored to that service. Connection detail APIs are also clearer, such as `getJdbcUrl()`, `getUsername()`, and `getPassword()`.

Example for RabbitMQ:

```java
import org.testcontainers.containers.RabbitMQContainer;

RabbitMQContainer rabbit = new RabbitMQContainer("rabbitmq:3.13-management-alpine")
        .withUser("test", "test", "/")
        .withPermission("/", "test", ".*", ".*", ".*");
```

Example for Redis:

```java
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.utility.DockerImageName;

GenericContainer<?> redis = new GenericContainer<>(
        DockerImageName.parse("redis:7.4-alpine"))
        .withExposedPorts(6379);
```

When a dedicated module is available, prefer it because it encapsulates service-specific details. `GenericContainer` fits when an image has no dedicated module or when a test needs custom image configuration.

## 6. GenericContainer for Custom Services

`GenericContainer` lets you run nearly any image runnable in a container runtime. The test explicitly declares ports, environment variables, commands, and readiness.

```java
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.wait.strategy.Wait;
import org.testcontainers.utility.DockerImageName;

GenericContainer<?> fakeIdentity = new GenericContainer<>(
        DockerImageName.parse("ghcr.io/example/identity-test:2.1.0"))
        .withExposedPorts(8080)
        .withEnv("ADMIN_USER", "test-admin")
        .withEnv("ADMIN_PASSWORD", "test-password")
        .waitingFor(Wait.forHttp("/health").forStatusCode(200));
```

After starting, obtain the access address from the test process:

```java
fakeIdentity.start();
String host = fakeIdentity.getHost();
int port = fakeIdentity.getMappedPort(8080);
String baseUrl = "http://" + host + ":" + port;
```

`getMappedPort(8080)` returns the host port mapped to port `8080` inside the container. Do not hardcode `localhost:8080` because the runtime can map to another port or the host may not be `localhost` in some environments.

If the image needs a configuration file, you can copy the file into the container before starting or mount a test directory. Keep configuration files in test resources and avoid baking production secrets into images or logs.

## 7. Managing Lifecycle with JUnit Jupiter

Testcontainers integrates with JUnit 5 via `@Testcontainers` and `@Container`:

```java
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
class RedisIntegrationTests {

    @Container
    static final GenericContainer<?> REDIS = new GenericContainer<>("redis:7.4-alpine")
            .withExposedPorts(6379);

    @Test
    void startsRedisForTheTestClass() {
        assertThat(REDIS.isRunning()).isTrue();
    }
}
```

The JUnit extension manages starting and stopping fields annotated with `@Container`.

| Declaration | Lifecycle |
|---|---|
| `static @Container` | Starts once for the test class; stops after the class |
| Instance `@Container` | Starts before each test method; stops after each method |
| Manually started container | Test code is responsible for stopping and cleanup |

Use a static container when test methods can share the same service and manage their own data. Use an instance container when each method needs a completely fresh service state, keeping in mind that startup time can increase significantly.

Example of manual management:

```java
GenericContainer<?> redis = new GenericContainer<>("redis:7.4-alpine")
        .withExposedPorts(6379);

try {
    redis.start();
    // Create client and run tests.
}
finally {
    redis.stop();
}
```

In JUnit tests, the extension is usually easier to read. Manual management is useful when containers are created dynamically in helpers, when coordinating multiple containers, or when the test framework does not use JUnit Jupiter.

## 8. Connecting Spring Boot to Containers

Testcontainers starts the service, while Spring needs the endpoint to create client beans. Two common mechanisms exist: `@ServiceConnection` and `@DynamicPropertySource`.

### `@ServiceConnection`

Spring Boot 3.1 and later supports service connections for recognized container types. Example for PostgreSQL:

```java
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.boot.test.context.SpringBootTest;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest
@Testcontainers
class RepositoryIntegrationTests {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>("postgres:16-alpine");
}
```

Spring Boot creates `ConnectionDetails` for services it supports and uses that information during auto-configuration. The `spring-boot-testcontainers` dependency must be on the test classpath.

### `@DynamicPropertySource`

When you need to map specific properties or a container has no service connection factory, use `@DynamicPropertySource`:

```java
@DynamicPropertySource
static void properties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
    registry.add("spring.datasource.username", POSTGRES::getUsername);
    registry.add("spring.datasource.password", POSTGRES::getPassword);
}
```

This works with any property the application needs, including internal service URLs, mocked API endpoints, or custom brokers. It also lets tests preserve the production client configuration, swapping only the endpoint to the container.

## 9. Distinguishing Host Ports from Container Networks

When the test process runs on the host and connects to a container, use the host and mapped port:

```java
String host = redis.getHost();
int mappedPort = redis.getMappedPort(6379);
```

When one container needs to connect to another container on the same Docker network, use the network alias and internal port. Do not use mapped host ports for container-to-container communication.

```java
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.Network;
import org.testcontainers.containers.wait.strategy.Wait;

Network network = Network.newNetwork();

GenericContainer<?> redis = new GenericContainer<>("redis:7.4-alpine")
        .withNetwork(network)
        .withNetworkAliases("cache")
        .withExposedPorts(6379)
        .waitingFor(Wait.forListeningPort());

GenericContainer<?> worker = new GenericContainer<>("example/worker:1.0.0")
        .withNetwork(network)
        .withEnv("REDIS_HOST", "cache")
        .withEnv("REDIS_PORT", "6379");
```

In this example, `worker` connects to host `cache` and port `6379` on the same network. The `cache` alias is resolved by Docker DNS. If the test process needs to connect to Redis, it still uses `redis.getHost()` and `redis.getMappedPort(6379)`.

When creating a `Network` manually, close the network after tests finish. If containers are managed by the JUnit extension, use an explicit helper/lifecycle to avoid leaving networks around after tests.

## 10. Managing Dependencies Between Multiple Containers

A test system may require multiple services: database, broker, cache, and auxiliary applications. Make dependencies and readiness explicit:

```text
PostgreSQL ----+
               |
Redis ---------+----> Spring application test
               |
RabbitMQ ------+
```

Containers can share a network to communicate directly. For each service:

1. Start foundational containers.
2. Wait for the readiness condition of each service.
3. Pass host/port or network alias to dependent services.
4. Start dependent containers.
5. Wait for dependent applications to become ready.
6. Run tests and clean up in reverse order.

Some APIs let you declare dependencies via `dependsOn(...)` or wait strategies depending on container types. However, starting in order alone is not enough; you must wait until the service actually accepts connections. When there are multiple containers, centralize declarations in a fixture or test configuration rather than repeating setup in every test method.

## 11. Readiness: Running Does Not Mean Ready

The container runtime may report a container as running while the database is still initializing schemas or the broker has not opened its listener yet. Testcontainers uses wait strategies to determine when tests can connect.

Common readiness types:

| Wait strategy | Condition |
|---|---|
| `Wait.forListeningPort()` | Service port starts listening |
| `Wait.forHttp("/health")` | Health endpoint returns the expected status |
| `Wait.forLogMessage(...)` | Logs contain a readiness message |
| Custom wait strategy | A service-specific condition |

Example:

```java
GenericContainer<?> service = new GenericContainer<>("example/service:1.0.0")
        .withExposedPorts(8080)
        .waitingFor(Wait.forHttp("/health")
                .forStatusCode(200)
                .withStartupTimeout(Duration.ofMinutes(2)));
```

Do not use `Thread.sleep(5000)` to guess whether a service is ready. Sleep can be too short on CI or waste time when the service starts quickly. Wait strategies check a meaningful condition with an explicit timeout.

## 12. Using Docker Compose for a Service Cluster

When infrastructure consists of multiple interrelated containers, Docker Compose can describe them in a YAML file: services, images, environment, volumes, networks, and dependencies. Testcontainers provides Compose integration to start the service cluster from that configuration.

A minimal Compose file:

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: orders
      POSTGRES_USER: test
      POSTGRES_PASSWORD: test
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U test -d orders"]
      interval: 2s
      timeout: 2s
      retries: 20

  redis:
    image: redis:7.4-alpine
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 2s
      timeout: 2s
      retries: 20
```

Compose is useful when developers want the same service cluster for local runs and tests. However, do not let tests rely on a Compose stack started manually beforehand without version and lifecycle control. Let Testcontainers manage starting/stopping the stack or declare containers directly in tests.

Testcontainers' Compose API has evolved across versions. Use the module and declaration style matching the Testcontainers version managed by your project; the key principle is that tests explicitly control the Compose file, project name, published ports, readiness, and cleanup.

## 13. Building Custom Test Images or Services

Not every service has a suitable official image. You can build an image from a test-dedicated Dockerfile or use a published internal image.

Example using `ImageFromDockerfile`:

```java
import org.testcontainers.images.builder.ImageFromDockerfile;

ImageFromDockerfile image = new ImageFromDockerfile()
        .withFileFromClasspath("Dockerfile", "test-service/Dockerfile")
        .withFileFromClasspath("app.jar", "test-service/app.jar");

GenericContainer<?> service = new GenericContainer<>(image)
        .withExposedPorts(8080)
        .waitingFor(Wait.forHttp("/health").forStatusCode(200));
```

Building images lets tests run an internal service alongside repository source code. For stable builds, control the Dockerfile, base image, and dependencies. If building the image takes too long or many tests share the same image, consider building once in the pipeline and pulling an image with an immutable tag.

## 14. Data, Volumes, and Cleanup

Dedicated containers isolate processes, yet data can still persist throughout the container's lifecycle. If multiple test methods share a database container, rows or queues from an earlier test can affect a later one.

Common strategies:

| Strategy | Impact | When to use |
|---|---|---|
| Fresh container per method | Strong isolation, higher startup cost | Tests requiring a completely clean service state |
| Shared container per class | Faster, requires data reset | Multiple tests sharing the same schema and image |
| Dedicated schema/database per test | Data isolation, shared server | Parallel tests or separate migrations |
| Delete fixtures after tests | Keeps container long-lived | Data that can be cleaned safely via transactions or SQL |
| Use unique keys | Reduces collisions between tests | Concurrent tests or asynchronous data |

`@Transactional` and rollback apply only to transactions managed by Spring Test. Messages sent to a broker, transactions on other threads, or async work can survive rollback. With brokers, create separate queues/topics or purge messages/state per test.

Volumes can persist data across container lifecycles. This is helpful when reusing data or supplying config files, but shared volumes also increase the risk of tests depending on stale state. Enable persistence only when that is what needs testing.

## 15. Container Lifecycle and Spring TestContext Cache

The Spring TestContext Framework can cache `ApplicationContext` across multiple test classes. If a bean in the context holds a connection to a container stopped by the JUnit extension after the first class, the next class may reuse the cached context while the endpoint is no longer alive.

Therefore, container lifecycle must align with context lifecycle:

- For a standalone test class, static `@Container` is usually the simplest option.
- For multiple test classes sharing a context, the container must outlive the cached context.
- If using a self-managed singleton container, the test suite must clearly define who starts and stops it.
- Do not stop a container in one class's `@AfterAll` if Spring might reuse that context in another class.
- When dynamic endpoints change, Spring may create new contexts because dynamic properties differ; this can affect caching and runtime.

The singleton pattern can reduce startup time but requires handling cleanup at the end of the test suite. Do not mix self-managed singletons with the `@Container` extension on the same container, as the two mechanisms can fight over lifecycle ownership.

## 16. Container Reuse: Faster, but State Persists

Testcontainers supports container reuse in certain development environments. Reuse can save time when heavy databases or brokers are involved, yet containers are not stopped after each run and state can persist across executions.

Reuse fits when:

- Developers repeatedly run the same group of tests locally.
- Explicit reset mechanisms exist for databases, queues, topics, and caches.
- Tests do not require always starting from a fresh image state.

Reuse does not fit when:

- CI requires a clean environment and reproducible results.
- Tests depend on a fresh schema or fresh seed data.
- Multiple branches or test suites might write into the same container.
- No reliable state-reset procedure exists.

Do not enable reuse just to make tests turn green faster. First, measure startup times and optimize image caching, parallelism, lifecycle, or test grouping. If enabling reuse, treat it as an intentional local environment choice.

## 17. Diagnosing Container Startup Failures

When a test fails before assertions, the cause may lie in the runtime, image pull, readiness, or container configuration. Categorize the failure:

| Symptom | Possible cause | What to check |
|---|---|---|
| Docker environment not found | Docker daemon/socket unreachable | Check the runtime and permissions of the test process |
| Image pull fails | Registry unreachable, wrong tag, or missing credentials | Check image name, tag, and registry credentials |
| Container exits immediately after start | Wrong environment or command | Inspect container logs and exit code |
| Readiness wait times out | Wrong health endpoint/port/log or service failed on startup | Check wait strategy and startup logs |
| Spring cannot connect | Wrong host/port used or properties not loaded | Check mapped port, `getHost()`, and dynamic properties |
| Subsequent test class fails | Container stopped while context was cached | Check lifecycle coordination between JUnit and Spring |

You can capture container logs in tests or on failure:

```java
String logs = container.getLogs();
System.out.println(logs);
```

In CI, preserve container logs when tests fail to see where the service stopped. Avoid printing secrets or sensitive data that might appear in logs.

## 18. Running Testcontainers in CI

Testcontainers requires a Docker-compatible runtime accessible by the test process. CI runners must expose a Docker daemon/socket or a supported remote runtime configuration.

Pipelines must address:

- Runtime availability before invoking Gradle/Maven.
- Access permissions to the Docker socket/daemon granted to the right user.
- Reachable image registries and reasonable image caching.
- Sufficient CPU, RAM, and disk on the runner to run databases/brokers.
- Job timeouts large enough for image pulls and service startup.
- Test parallelism within actual resource limits.
- Container cleanup after the job finishes or is cancelled.

If the runner lacks a container runtime, Testcontainers cannot operate normally. You can use CI-provided service containers, a dedicated test infrastructure environment, or runners with Docker support. Do not silently skip critical integration tests; make explicit which test groups require a runtime.

## 19. Testcontainers Compared with Alternatives

| Tool | Where infrastructure is managed | Best suited for |
|---|---|---|
| Mockito/fakes | Inside the test process | Unit tests and interaction verification |
| Embedded database/broker | In-process or embedded runtime | Fast tests when behavior is close enough to production |
| `MockRestServiceServer` | Spring request factory layer | Verifying HTTP client contracts without sockets |
| Testcontainers | Local/remote container runtime | Integrating with real services and real protocols |
| Manually run Docker Compose | External to tests | Developer stacks or separately managed test environments |
| Shared services in test env | Central infrastructure | System testing or long-lived integration environments |

Testcontainers is not the only option and does not need to appear in every test. Its value is providing near-production infrastructure with test-controlled lifecycles, reducing reliance on shared services and manual local setup on developer machines.

## 20. Workflow for Selecting and Managing Infrastructure with Testcontainers

1. Identify which external services directly affect the contract under test.
2. Choose a dedicated Testcontainers module if available; otherwise use `GenericContainer` or a custom test image.
3. Pin image versions and manage modules with the corresponding BOM.
4. Decide whether containers live per method, class, or test suite.
5. Declare ports, environment, volumes, networks, and readiness.
6. Connect Spring using `@ServiceConnection` or `@DynamicPropertySource`.
7. Isolate data, queues/topics, and caches between tests.
8. Align container lifecycle with Spring context caching.
9. Capture logs and diagnose startup failures clearly.
10. Ensure CI has the required runtime, permissions, and resources.
11. Use reuse only when state can be reset and gains have been measured.

## 21. References

- [Testcontainers for Java — Documentation](https://java.testcontainers.org/): API, modules, lifecycle, networks, wait strategies, and CI.
- [Testcontainers — JUnit 5 Quickstart](https://java.testcontainers.org/quickstart/junit_5_quickstart/): `@Testcontainers` and `@Container` integration.
- [Testcontainers — Generic Container](https://java.testcontainers.org/features/creating_container/): configuring images, ports, environment, and commands.
- [Testcontainers — Networking](https://java.testcontainers.org/features/networking/): mapped ports, hosts, and container networks.
- [Testcontainers — Reusable Containers](https://java.testcontainers.org/features/reuse/): conditions and limits of container reuse.
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): `@ServiceConnection` and Spring Boot integration.
- [Spring Framework — DynamicPropertySource](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html): configuring dynamic properties in Spring TestContext.

Testcontainers adds real infrastructure management to Spring tests: starting the right services, providing dynamic endpoints, waiting for readiness, connecting Spring, and cleaning up resources under an intentional lifecycle. Choose a container scope just sufficient for the integration contract to verify, manage state across tests, and keep configuration reproducible on both developer machines and CI.
