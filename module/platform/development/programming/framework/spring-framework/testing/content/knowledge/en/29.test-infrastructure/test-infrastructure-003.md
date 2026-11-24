# External Infrastructure Lifecycle vs. the Context Cache

Integration tests often rely on components outside the Spring application context: PostgreSQL, Redis, Kafka, message brokers, HTTP mock servers, file servers, or services running in Docker. These components have their own lifecycles. Meanwhile, Spring Test can keep and reuse an `ApplicationContext` across multiple test classes to reduce startup time.

These two mechanisms do not synchronize automatically. A cached context may continue holding a datasource, `WebClient`, or other client pointing to a container that has already stopped. Subsequent tests can fail even though context initialization succeeded earlier. Conversely, if each test class starts a new container while Spring reuses the old context, the context may still point to the address of the previous container.

For stable integration tests, you need to design explicitly who owns each resource, how long it lives, when the context is created/closed, and the cleanup order. The key principle is that a dependency's lifetime must span the entire time any context uses that dependency.

## 1. How Does the Spring TestContext Cache Work?

The Spring TestContext Framework manages creating and reusing application contexts for Spring-based tests. When two tests have equivalent configurations, Spring can share an already created context instead of restarting all beans for each class.

Example:

```java
@SpringBootTest
class OrderServiceIntegrationTest {
    // Uses the application's ApplicationContext.
}

@SpringBootTest
class InventoryRepositoryIntegrationTest {
    // Can reuse the same ApplicationContext configuration.
}
```

Caching is not based simply on class names. Spring builds a context key from configuration elements such as:

- Configuration classes and context initializers.
- Context loader and parent context.
- Active profiles.
- Test property sources and inline properties.
- Context customizers, including components registered by Spring Boot test and dynamic property sources.
- Other configuration elements involved in building the context.

If the configuration key matches, the context can be reused across test classes. The cache is an in-process structure within the test JVM, not a global registry shared across JVMs. By default, the cache has a size limit and can evict least-recently-used contexts when the limit is exceeded.

Remember that Spring caches the `ApplicationContext`, not external processes started by tests. Docker containers, mock HTTP servers, temporary files, or auxiliary processes are managed only according to the lifecycle configured by the test, JUnit extension, or Spring beans.

## 2. Two Independent Lifecycles

An integration test typically involves at least two groups of resources:

**Resources inside the Spring context** include datasource beans, `WebClient`, `RestClient`, repositories, services, executors, and beans with lifecycle callbacks. When the context is created, beans are initialized and may connect to external infrastructure. When the context closes, Spring invokes the appropriate bean destruction callbacks.

**Infrastructure outside the context** includes database containers, Redis, Kafka, WireMock servers, MockWebServer, auxiliary processes, or test-created resources. They may live per test method, per test class, for the entire test suite, or be managed by the Spring context.

Example of a configuration that can create a dangerous situation:

```text
Test class A starts
    |
    +--> Start PostgreSQL container A
    |
    +--> Spring creates ApplicationContext C
    |       |
    |       +--> DataSource holds container A's URL
    |
    +--> Test class A finishes
            |
            +--> JUnit stops container A

Test class B starts
    |
    +--> Spring reuses ApplicationContext C from cache
            |
            +--> DataSource still points to stopped container A
```

The context cache does not automatically know container A has stopped. When class B queries the database, connections can fail because the old endpoint is no longer active.

Design rule:

```text
Lifetime of external dependency >= Lifetime of every ApplicationContext using it
```

If a dependency must stop earlier, close/evict the context before the dependency stops, or reconfigure the context so it connects to the new dependency.

## 3. Container Lifecycle with Testcontainers JUnit 5

Testcontainers provides a JUnit Jupiter extension to manage containers via `@Testcontainers` and `@Container`.

```java
@Testcontainers
@SpringBootTest
class OrderRepositoryIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }
}
```

With the JUnit Jupiter Testcontainers extension:

- A container marked `static @Container` starts once for the class's test methods and stops after that class finishes.
- A container marked `@Container` on an instance field starts and stops for each individual test method.
- The extension manages start/stop according to JUnit's class or method lifecycle.

This pattern works when the context and container are only used within that test class, or when the context is guaranteed not to be reused after the container stops. However, the Spring TestContext cache can keep a context alive longer than a single class. Therefore, do not assume `static @Container` lives long enough for every cached context.

Be especially careful when multiple test classes inherit from a shared base class with `@DynamicPropertySource`. The context may be reused while the extension stops the container at the class boundary. If the next class needs the same context, the datasource may hold the endpoint of the stopped container.

## 4. Using a Singleton Container Living Across the Test Suite

If multiple test classes share a single database, a common approach is to manage the container at the suite/JVM scope. The container starts once and is not stopped after each class by the JUnit extension.

Example base class:

```java
abstract class PostgresIntegrationTestBase {

    static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>("postgres:16-alpine");

    static {
        POSTGRES.start();
    }

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username", POSTGRES::getUsername);
        registry.add("spring.datasource.password", POSTGRES::getPassword);
    }
}
```

Test classes extend the base class:

```java
@SpringBootTest
class OrderRepositoryIntegrationTest extends PostgresIntegrationTestBase {
}

@SpringBootTest
class InventoryRepositoryIntegrationTest extends PostgresIntegrationTestBase {
}
```

In this pattern, `@Container` and `@Testcontainers` are omitted so the extension does not stop the container after each class. The container is started manually in a static initializer and stays alive for the lifetime of the test classloader/JVM. Testcontainers still cleans up containers when the process exits; if a project needs explicit lifecycle teardown, stopping can be managed at the appropriate suite level.

The advantage is that the database endpoint remains stable throughout the lifetime of the context cache. The drawback is that database data and state are also shared across classes. Test data must be isolated using unique IDs, appropriate transactions/cleanup, separate schemas, or controlled truncation.

Avoid having each test class wipe the entire database if other tests may run in parallel. Use dedicated namespaces or uniquely keyed fixtures to avoid conflicts.

## 5. Letting Spring Manage the Container as a Bean

Another approach is placing the container inside the Spring `ApplicationContext` so its lifecycle is tied to the context lifecycle. When the context is created, the container bean is initialized; when the context closes, Spring destroys the bean and invokes stop.

With Spring Boot 3.1 and later, `@ServiceConnection` allows Spring Boot to detect connection details from Testcontainers:

```java
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.containers.PostgreSQLContainer;

@TestConfiguration(proxyBeanMethods = false)
class DatabaseContainerConfiguration {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgresContainer() {
        return new PostgreSQLContainer<>("postgres:16-alpine");
    }
}
```

Import the configuration in the integration test:

```java
@SpringBootTest
@Import(DatabaseContainerConfiguration.class)
class OrderRepositoryIntegrationTest {
}
```

Spring Boot generates connection details from the container and applies them to the matching auto-configuration. Because the container is a bean, it is managed alongside the context. When Spring closes the context, the container bean is destroyed and the container stops. If the context is cached and reused, the container remains alive alongside the context.

To use `@ServiceConnection`, the project needs the Spring Boot Testcontainers support dependency, typically:

```groovy
testImplementation 'org.springframework.boot:spring-boot-testcontainers'
```

And the Testcontainers dependency for the corresponding service type. Dependency versions should be managed via Spring Boot dependency management or a compatible BOM.

### Managing Beans with init/destroy Methods

If not using `@ServiceConnection`, you can declare bean lifecycle hooks manually:

```java
@TestConfiguration(proxyBeanMethods = false)
class ExternalServiceConfiguration {

    @Bean(initMethod = "start", destroyMethod = "stop")
    GenericContainer<?> redisContainer() {
        return new GenericContainer<>(DockerImageName.parse("redis:7-alpine"))
                .withExposedPorts(6379);
    }
}
```

Then register the appropriate connection properties using a controlled configuration mechanism. For containers that support service connections, `@ServiceConnection` usually avoids manually writing URLs, ports, and credentials.

Do not declare multiple ownership mechanisms for the same container simultaneously, such as having both a Spring bean call `stop()` and a JUnit extension manage stopping. Each resource should have a single, clear lifecycle owner.

## 6. DynamicPropertySource and Configuration Values in the Context

`@DynamicPropertySource` allows registering properties retrieved from resources started during the test, typically container URLs and credentials:

```java
@DynamicPropertySource
static void redisProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.data.redis.host", redis::getHost);
    registry.add("spring.data.redis.port", redis::getFirstMappedPort);
}
```

Suppliers are registered for properties, allowing values to be read from the running container when properties are resolved. Dynamic properties have higher precedence in the `Environment` than many standard test configuration sources.

However, a dynamic property is not a mechanism that starts or keeps a container alive. It only provides configuration values. If the container stops, the URL and port become unusable even though the property might still return the old string.

The Spring TestContext cache also does not treat every runtime value a supplier might return as an independent context key. If the same `@DynamicPropertySource` method is inherited while the underlying container changes across test classes, a cached context may be reused with beans already built from the previous configuration.

Spring recommends using `@DirtiesContext` if dynamic properties vary across subclasses in a way that requires a fresh context. However, a more durable solution is usually keeping the same container alive for the entire duration the context uses it, or letting Spring manage the container bean.

### Do Not Change Endpoints While the Context Remains Alive

Unsafe example:

```text
Class A:
  container A -> jdbc:postgresql://host:portA/db
  context C creates DataSource pointing to portA

Class A finishes:
  container A stops

Class B:
  container B -> jdbc:postgresql://host:portB/db
  context C is reused
  DataSource in C still points to portA
```

Even if the dynamic property supplier returns `portB` on the next resolution, the `DataSource` bean already created in the context may not be rebuilt. Do not use dynamic properties as a mechanism to swap endpoints on an active singleton bean.

## 7. What `@DirtiesContext` Does and Does Not Do

`@DirtiesContext` marks an `ApplicationContext` as modified or no longer safe to reuse. Spring closes the context and removes it from the cache according to the selected mode. Subsequent tests will require a new context.

Example:

```java
@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class TestThatChangesApplicationContextState {
}
```

Modes can apply at the method or class level, before or after tests depending on the goal. Use this annotation when a test mutates singleton bean state, context configuration, or any state that makes the context unsuitable for other tests.

`@DirtiesContext` is not a general cleanup tool for all external resources. It closes the context and invokes bean lifecycle callbacks inside the context. A container managed by a JUnit extension, a WireMock server created manually in a static field, or a process started by the test may keep running without separate cleanup.

If the container is a bean in the context, closing the context invokes the bean's destroy method and stops the container. If the container is managed by a JUnit extension, the extension still owns stopping it. These two cases must be kept distinct.

Avoid slapping `@DirtiesContext` onto every test to work around lifecycle bugs. Closing and rebuilding contexts can be expensive, and it hides improper lifecycle management of external resources.

## 8. Lifecycle of Mock HTTP Servers and External Processes

The same principle applies to WireMock, MockWebServer, or other mock services.

If a client bean is created in the Spring context with the base URL of a WireMock server, the server must remain alive for at least as long as the context uses that client.

Example of a server managed by a test class:

```java
@SpringBootTest
class PaymentClientIntegrationTest {

    static WireMockServer wireMock = new WireMockServer(options().dynamicPort());

    @BeforeAll
    static void startServer() {
        wireMock.start();
    }

    @AfterAll
    static void stopServer() {
        wireMock.stop();
    }

    @DynamicPropertySource
    static void paymentProperties(DynamicPropertyRegistry registry) {
        registry.add("payment.base-url", wireMock::baseUrl);
    }
}
```

This pattern can work when the context is never reused after the server stops. However, if the context cache reuses the client bean in another class, the base URL may point to a stopped server. For servers shared across multiple classes, manage the server at the suite scope or as a context bean.

If a server only serves a single test method and no client is cached with that endpoint, creating and stopping the server in the method or via a JUnit extension is reasonable. Ensure beans using the server have ceased activity before stopping it.

## 9. Cleanup and Shutdown Order

When tests finish, cleanup must respect dependency relationships. Clients and connection pools should stop using a resource before that resource is shut down.

General order:

```text
Stop accepting new test requests
        |
        v
Wait for async tasks using dependencies to complete
        |
        v
Close ApplicationContext / clients / connection pools
        |
        v
Stop external services or containers
        |
        v
Clean up remaining data, temporary files, and network resources
```

The exact order depends on resource ownership. When a container is a context bean, Spring destroys beans according to the context lifecycle. When a container is a suite-scoped resource, contexts can be closed at the end of the suite before the container stops. Avoid stopping the database while a cached context's connection pool can still hand out connections.

For executors, stop submitting new tasks and wait for in-flight work before closing the database or broker those tasks use. Stopping the broker first can cause async tasks to fail during cleanup and leave later tests in an indeterminate state.

## 10. Isolating Data When Infrastructure Is Shared

Keeping a container alive longer reduces startup time, but causes multiple tests to share one service. Shared infrastructure requires a clear data isolation strategy.

Common options:

- Use unique IDs per test, such as UUIDs in order names or message keys.
- Create separate schemas or databases per test class if the database supports it.
- Use dedicated topics, queues, or consumer groups per test group.
- Clean up only records created by the test instead of truncating tables used by other tests.
- Reset mock server expectations after each test method.
- Use distinct key namespaces in Redis to avoid collisions.

`@Transactional` can roll back data created by the test thread, but it does not automatically roll back transactions on worker threads, message consumers, or `@Async` tasks. When work runs on another thread, transactions are usually independent. Use explicit commit boundaries and cleanup for worker-created data.

When multiple tests run in parallel, do not rely on execution order for data cleanup. Each test must own its own namespace or data. A shared container does not mean shared test state.

## 11. Parallel Tests and Shared Resources

When JUnit parallel execution is enabled, multiple tests may access a shared container or mock server simultaneously. That is valid if the service supports concurrent access and tests isolate their data. However, bugs like these can occur:

- One test resets the database while another test is reading.
- One test calls `wireMock.resetAll()` and wipes stubs belonging to another test.
- Two tests consume responses from the same MockWebServer queue.
- One test stops a shared container while other tests are still running.
- Tests write to the same file or fixed port.

For shared resources, lifecycle must be managed by a single owner. A test method must never stop a suite-scoped resource. If a mock server has stateful expectations, consider per-test instances or isolating stubs by path/header.

When a group of tests sharing state must be serialized, you can use JUnit `@ResourceLock` or appropriate execution configuration. This is a safeguard when resources cannot be isolated; do not use global locks to mask every data conflict.

## 12. Comparing Infrastructure Ownership Strategies

| Strategy | Infrastructure lifecycle | Context lifecycle | When appropriate | Main risk |
|---|---|---|---|---|
| JUnit instance `@Container` | Per test method | Can be cached longer than the method | Tests do not retain clients/contexts depending on the container across methods. | Reused context may point to a stopped container. |
| JUnit static `@Container` | One test class | Can be cached across multiple classes | Standalone test class whose context is not reused after the class. | Container stops before the cached context ends its lifecycle. |
| Suite-level singleton container | Entire test suite/JVM | Context can be cached across the suite | Multiple classes use the same service and a stable endpoint. | Shared data; requires isolation and cleanup. |
| Container as a Spring bean | Context lifecycle | Container and context share lifecycle | Client beans in the context depend on the container. | Closing context stops container; avoid new contexts depending on old beans. |
| Mock server in test method | One test method | Client created/used inside method | Small unit/integration tests without caching server-dependent clients. | Unsuitable for singleton beans holding a class-scoped server URL. |

There is no single strategy for every test. Choose based on ownership boundaries and actual usage duration. If the context cache retains a singleton client, the infrastructure that client calls must exist at least until the context closes.

## 13. Example Strategy Selection by Scenario

### One Test Class with Its Own Database

If the class uses a context only with its own container and does not share that context with other tests, `static @Container` can suffice. Ensure the context is not reused after the container stops; if context configuration is shared, adjust the lifecycle or mark the context dirty intentionally.

### Multiple Classes Sharing One Database

Use a singleton container or a Spring-managed container bean. Both options keep the endpoint stable when Spring reuses the context. Ensure each test creates independent data.

### Each Class Needs a Differently Configured Database

Use distinct context keys via appropriate configurations/properties/profiles so Spring creates separate contexts, while managing containers at the matching scope. If dynamic properties change without changing the cache key accordingly, use separate contexts or `@DirtiesContext` as needed.

### Mock HTTP Server Serving Only One Test

Start the server in the test method, build an HTTP client with the server's URL, and send requests. After verifying responses and ensuring the client has no background work remaining, stop the server. Do not inject the dynamic URL of a method-scoped server into a singleton bean in a long-lived cached context.

## 14. Configuring the Context Cache and Troubleshooting Failures

The Spring TestContext cache can be observed through debug logs for the `org.springframework.test.context.cache` package. Logs show hit/miss counts and cache size, which helps when investigating why a context was reused or rebuilt.

The default cache size can be adjusted via a system property:

```text
-Dspring.test.context.cache.maxSize=64
```

Increasing cache size can reduce context rebuilds in large suites, but it will not fix a container stopped prematurely. If a context holds a connection to an old endpoint, increasing cache size may keep the broken context around longer.

When encountering connection refused or datasource connection failures in a test suite, determine:

1. Which test class created the context first?
2. Which URL or port did the client/datasource bean store?
3. Is that container/server managed by JUnit, Spring, or test code?
4. At which callback was the resource stopped?
5. Do subsequent test classes reuse the same context cache key?
6. Does the dynamic property source return a different endpoint than the one the bean used at initialization?

Checking start/stop milestones and the context cache usually identifies the root cause faster than increasing timeouts or adding `Thread.sleep`.

## 15. Common Design Mistakes

### Container Stops After Class While Context Remains Cached

This is the most common mistake when combining static `@Container` with the Spring context cache. Solutions include extending the container lifecycle, turning the container into a context bean, or ensuring the context is closed before the container stops and is not reused.

### Using `@DirtiesContext` as General Cleanup

`@DirtiesContext` only manages the context. It does not automatically stop processes or resources managed by JUnit/test code. Each resource needs its own owner and cleanup.

### Changing DynamicPropertySource While Keeping Old Beans

Dynamic property suppliers do not automatically recreate `DataSource`, `WebClient`, or already initialized singleton beans. When endpoints change, a new context or a bean designed with an explicit refresh mechanism is required.

### Managing the Same Container with Multiple Mechanisms

Do not let both a JUnit extension and a Spring bean stop the same container. Choose one single owner to avoid premature stops or duplicate cleanup.

### Using a Shared Database Without Data Isolation

One test may read data created by another test or delete data another test relies on. Use dedicated IDs/schemas/topics and clean up within ownership boundaries.

### Shutting Down Infrastructure Before Async Tasks Finish

Workers may still be using the database or broker when the test ends. Wait for workers to complete or cancel them cleanly before stopping dependencies.

### Using `Thread.sleep` to Wait for Container Readiness

Testcontainers' container start API and wait strategies already provide readiness mechanisms. Use readiness checks and real connection conditions instead of sleeping for a fixed duration.

## 16. Lifecycle Management Checklist

- [ ] Identify which resources belong to the Spring context and which are managed by JUnit/tests.
- [ ] Identify across which test classes a context can be reused.
- [ ] Ensure databases, brokers, or mock servers outlive every context that depends on them.
- [ ] When using class/method-scoped `@Container`, verify the context cache does not outlive the container.
- [ ] For infrastructure shared across multiple classes, consider a singleton container or a Spring-managed container bean.
- [ ] When using `@DynamicPropertySource`, keep endpoints stable throughout the lifetime of contexts initialized from it.
- [ ] Use `@DirtiesContext` only when a context genuinely must be evicted from the cache, not as cleanup for all resources.
- [ ] Assign every resource a single owner responsible for start/stop.
- [ ] Clean up contexts/clients before stopping the external dependencies they use.
- [ ] Isolate database, queue, cache, and mock server state between tests.
- [ ] When running in parallel, prevent one test from stopping or resetting resources another test is using.
- [ ] Use readiness checks instead of `Thread.sleep` to wait for infrastructure readiness.

The Spring TestContext cache saves time by retaining application contexts, while Testcontainers and mock servers have lifecycles managed by JUnit, Spring beans, or test code. When those two lifecycles fall out of sync, a context can hold clients pointing to a stopped dependency. Designing clear ownership, keeping infrastructure alive long enough, managing dynamic properties consistently, and isolating data ensure integration tests run reliably both when contexts are cached and when suites run in parallel.
