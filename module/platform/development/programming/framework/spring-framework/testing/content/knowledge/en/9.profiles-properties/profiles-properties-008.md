# Limits of Dynamic Data When Contexts Are Shared

The Spring TestContext Framework can reuse the same ApplicationContext across multiple test classes to reduce initialization time. This is a major benefit of the context cache, but it also creates a constraint: every bean and configuration inside the context is created from the environment values present at the time the context is initialized.

When tests use dynamic data such as a random Testcontainers port, a WireMock URL, or a mock service endpoint, those values can change between test classes. If classes still share a cached context, beans inside the context may continue holding the old configuration even though the property supplier now returns a new value.

Therefore, when using dynamic data, resource lifecycles must be aligned with the ApplicationContext lifecycle. Long-lived shared resources can share contexts; resources that change per class need separate contexts or intentional refreshing.

## What Is Dynamic Data in Spring Tests?

Dynamic data refers to values known only when tests run or when test resources start. Common examples include:

- JDBC URLs and random ports allocated by Testcontainers.
- Host/port of WireMock or a mock web server.
- Endpoints of mock services started during tests.
- Tokens, queue names, or bucket names generated specifically for a test run.
- Connection details allocated by the CI environment.

These values are unsuitable for hardcoding in property files because addresses or ports may vary on each run. Spring Framework 5.2.5 and later provide `@DynamicPropertySource` and `DynamicPropertyRegistry` to register them into `Environment`.

~~~java
@DynamicPropertySource
static void registerProperties(DynamicPropertyRegistry registry) {
    registry.add("service.base-url", mockServer::getEndpoint);
}
~~~

A method annotated with `@DynamicPropertySource` must be static and accept a `DynamicPropertyRegistry`. Each `registry.add()` call registers a supplier for Spring to retrieve the value when the property is queried. This allows tests to register endpoints after test resources have been initialized.

## @DynamicPropertySource and Property Suppliers

Unlike inline properties in `@TestPropertySource`, dynamic properties do not require knowing the final value at compile time or when writing the test. A supplier can read values from a running container or server.

~~~java
@DynamicPropertySource
static void databaseProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
~~~

In this example, `postgres::getJdbcUrl` is a method reference registered as a supplier. Spring invokes the supplier when it needs to resolve the property. Multiple properties can be registered in the same method.

Dynamic property sources have higher precedence than typical test configuration sources such as `@TestPropertySource`, system properties, and environment variables. This is helpful when test-allocated endpoints must take priority over default machine or CI configurations.

However, a supplier is not a mechanism that automatically reconfigures every bean when values change. For instance, a `DataSource` created during ApplicationContext refresh normally reads the JDBC URL and initializes its pool once. If the supplier later returns a different URL, Spring does not automatically recreate the `DataSource`, close the old pool, or rebind already created beans.

This is a critical point when contexts are cached: suppliers can provide dynamic values, yet beans inside the context retain their own lifecycles.

## Why Can the Context Cache Hold Stale Configuration?

The TestContext Framework caches ApplicationContexts based on the merged configuration of tests. The cache key includes many factors such as configuration classes/locations, initializers, active profiles, property sources, context customizers, and loaders.

`@DynamicPropertySource` integrates into this mechanism via a context customizer. When a dynamic property source method is inherited from the same parent class, child test classes can have equivalent customizer configurations. If the remaining configuration factors also match, Spring may reuse the cached ApplicationContext.

Consider this scenario:

1. Test class A starts a PostgreSQL container and receives port `49152`.
2. `@DynamicPropertySource` registers the JDBC URL pointing to that port.
3. Spring creates the ApplicationContext and initializes `DataSource` with class A's URL.
4. Test class A finishes, and the container stops.
5. Test class B inherits the same `@DynamicPropertySource` method and starts a new container on port `49180`.
6. If the context cache reuses A's context, the `DataSource` inside the context may still point to port `49152`.

Even though the supplier could read the new endpoint if queried, the previously initialized `DataSource` does not automatically switch URLs. Test class B may encounter errors connecting to the old container or a resource that no longer exists.

~~~mermaid
sequenceDiagram
    participant A as Test class A
    participant C1 as Container A
    participant S as Spring Context Cache
    participant B as Test class B
    participant C2 as Container B

    A->>C1: Start up, receives port 49152
    A->>S: Dynamic property registers URL A
    S->>S: Create context and DataSource pointing to URL A
    A->>C1: Class ends, container stops
    B->>C2: Start up, receives port 49180
    B->>S: Needs context with same cache configuration
    S-->>B: May return old context
    Note over B,S: DataSource still holds URL A
    B->>S: Execute query
    S-->>B: Connection may fail
~~~

This is a lifecycle and caching issue, not necessarily a bug in `@DynamicPropertySource` or the database driver. The dynamic data source and the reused context have incompatible lifecycles.

## Example with Testcontainers and a Base Test Class

A common pattern is placing the container and property registration method on a base test class:

~~~java
abstract class AbstractPostgresIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void registerDatabaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }
}
~~~

Two test classes extend the base class:

~~~java
@Testcontainers
class CustomerRepositoryIT extends AbstractPostgresIntegrationTest {
    // Test customer repository.
}

@Testcontainers
class OrderRepositoryIT extends AbstractPostgresIntegrationTest {
    // Test order repository.
}
~~~

In this organization, the Testcontainers extension manages the static container per test class lifecycle. Subclasses may start and stop containers at different times, so the allocated endpoint can change.

The `registerDatabaseProperties()` method is inherited from the same base class. If both test classes have equivalent TestContext configurations, the cache may treat them as the same configuration and reuse the ApplicationContext. Then the second class's `DataSource` may still point to the first class's container.

## Approach 1: Mark the Context Dirty After Each Test Class

When each test class needs its own container or endpoint, you can instruct Spring to remove the ApplicationContext from the cache after the class finishes using `@DirtiesContext`.

~~~java
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class CustomerRepositoryIT extends AbstractPostgresIntegrationTest {
    // Test customer repository.
}

@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class OrderRepositoryIT extends AbstractPostgresIntegrationTest {
    // Test order repository.
}
~~~

After `CustomerRepositoryIT` finishes, Spring closes the context and removes the corresponding entry from the cache. When `OrderRepositoryIT` runs, the framework must create a new context and the supplier can provide the new container's endpoint.

This approach fits when:

- Each class has its own container or mock server.
- Endpoints, credentials, or connection data vary across classes.
- Beans in the context hold configuration bound from the previous initialization.
- You want each class to have its own ApplicationContext lifecycle.

`@DirtiesContext` has a cost: contexts must be recreated, beans reinitialized, and bootstrap steps can slow down the suite. Use it only on test classes with resource lifecycle reasons.

If multiple classes share the same cache key and run in parallel, one class closing the context while another class is using it can cause hard-to-reproduce errors. For test groups needing per-class contexts, avoid sharing the same cache entry during parallel execution; serialize that test group or design distinct context keys/resources clearly.

## Approach 2: Share a Long-Lived Dynamic Resource

If multiple test classes can use the same database or mock server, a simpler approach is sharing that resource across the entire lifecycle of the test suite. When the endpoint does not change, context reuse is safe and saves time.

Example of a Testcontainers singleton container:

~~~java
abstract class AbstractPostgresIntegrationTest {

    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    static {
        postgres.start();
    }

    @DynamicPropertySource
    static void registerDatabaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }
}
~~~

The container starts once in the JVM and remains alive while test classes share the context. Test classes can reuse the same endpoint, so the `DataSource` in the ApplicationContext does not end up pointing to a stopped container mid-suite.

This is the singleton container pattern. Manage container lifecycle clearly and let Testcontainers/Ryuk clean up resources when the JVM exits. Do not combine this manual startup pattern with `@Container` in a way that causes the extension to stop the container after each class; choose one lifecycle strategy consistently.

Sharing a container does not mean arbitrarily sharing test data. Tests still need isolated data, transactions, or appropriate cleanup. Connection resources can be shared while each test still creates its own records or schemas.

## Approach 3: Create Different Context Configurations When Endpoints Differ

Another option is ensuring each test class has a different context key. When merged configurations differ, Spring does not mistakenly reuse another class's context.

You can declare separate `@DynamicPropertySource` methods on each class if each class genuinely has its own property source, or create configurations/customizers whose identity reflects distinct endpoints or resources. However, avoid adding dummy properties just to force a cache miss. Configurations should reflect genuine differences in test environments.

In many cases, `@DirtiesContext` is clearer and easier to understand than a custom context customizer solely intended to create distinct cache keys. If you need a complex test framework with many dynamic resources, consider building a bootstrap/context customizer mechanism whose `equals()` and `hashCode()` rules accurately reflect resource identity.

## Dynamic Data Does Not Replace Profiles

Profiles and dynamic properties solve two different problems:

| Mechanism | Used For | Example |
|---|---|---|
| `@ActiveProfiles` | Selecting bean/configuration groups by environment or scenario | `integration`, `test`, `local` |
| `@TestPropertySource` | Declaring fixed properties for tests | `feature.payment.enabled=false` |
| `@DynamicPropertySource` | Supplying properties known only when test resources run | JDBC URL, random port, mock server endpoint |

Do not create a new profile for every random port or every container instance. Profiles represent configuration choices, whereas a dynamic endpoint is the value of a property. Using profiles to force separate contexts for each endpoint makes configurations hard to read and misrepresents what profiles mean.

Active profiles are part of the context cache key. They can produce distinct contexts when tests genuinely use different groups of beans/configurations. However, changing profiles is not a substitute for managing dynamic resource lifecycles.

## Lazy Suppliers Do Not Mean Beans Self-Update

A common misconception is that because `DynamicPropertyRegistry` takes a supplier, every bean always receives the new value whenever an endpoint changes.

The supplier is invoked when the property source needs to resolve the property. Yet many beans read properties only at initialization time:

~~~java
@Configuration
class ClientConfiguration {

    @Bean
    PaymentClient paymentClient(Environment environment) {
        String baseUrl = environment.getRequiredProperty("service.base-url");
        return new PaymentClient(baseUrl);
    }
}
~~~

In a real configuration, properties are bound into constructors or `@ConfigurationProperties` when beans are created. After the context refreshes, Spring does not automatically rebuild beans simply because a supplier returns a different value.

Even if a later `Environment` query sees the new value, an already initialized client or connection pool may still use the old value. Therefore, align bean lifetimes with endpoint lifetimes.

If an application genuinely needs to change endpoints at runtime, that is a separate runtime reconfiguration requirement. It needs an abstraction capable of safely updating clients/pools, managing old connections, and synchronizing access. `@DynamicPropertySource` primarily serves configuration provisioning when preparing the test context.

## Limits When Running Tests in Parallel

Sharing contexts and dynamic data across test classes can be risky during parallel execution:

- Class A may close the container while Class B is still using the shared context's connection pool.
- One class may mark the context dirty while another class is executing on that context.
- Two tests may write to the same database or queue even with the same endpoint.
- A static field holding an endpoint may be updated while another class is reading it.
- A mock server may be reset or stopped while requests from another class are still in flight.

If a resource is a shared singleton, keep it alive until all consuming tests finish and isolate data between tests. If a resource has class-level lifecycle, give that class its own context and avoid running classes concurrently that share a cache key while having different endpoints.

In parallel tests, you need not only unique endpoints but also clear ownership of data and resources. Using separate schemas, tenants, queues, or namespaces prevents tests from reading or deleting each other's data.

## Choosing a Strategy by Resource Lifecycle

| Resource Characteristics | Appropriate Context Strategy | Notes |
|---|---|---|
| One container used across the entire test suite | Share context and container | Endpoint remains stable throughout context lifetime |
| New container per test class | Separate context or `@DirtiesContext(AFTER_CLASS)` | Ensure old context closes before reusing the same cache key |
| Mock server with fixed endpoint, only resetting data | Can share context | Resetting must not discard state needed by other tests |
| Endpoint changes after context refresh | Create fresh context or dedicated runtime reconfiguration mechanism | Suppliers do not rebind existing beans automatically |
| Each class has its own database/schema | Separate context and configuration per class | Use separate namespaces, clean up within scope |
| Multiple classes running in parallel on a singleton resource | Share endpoint while isolating data | Do not stop or reset the resource while other classes use it |

The key decision is: how long does the dynamic resource live, how long does the context live, and which beans hold values bound from that resource. If a context outlives the resource its beans depend on, tests risk using stale configuration.

## Workflow for Investigating Stale Endpoint Errors

When a test class connects to a port or URL from a previous run, trace these steps:

1. Identify the property source: `@DynamicPropertySource`, `@TestPropertySource`, profile, or environment variable.
2. Record the actual endpoint of the resource in each test class.
3. Determine whether the dynamic property source method is inherited from the same superclass.
4. Determine whether the TestContext Framework reused the same ApplicationContext or created a new one.
5. Check when beans such as `DataSource`, HTTP clients, or message connection factories are initialized.
6. Check whether the old resource stopped before beans in the old context were closed.
7. Choose between sharing a long-lived resource or refreshing the context per class.
8. If running in parallel, check whether another class is using the same context or resource.

You can enable Spring TestContext logging to observe cache hits, cache misses, context creation, and context eviction. These logs confirm whether Spring actually reused a context instead of guessing from whether the property supplier was called.

## Common Misconceptions

**Assuming `@DynamicPropertySource` always creates a fresh context.** The annotation registers dynamic properties, but does not force Spring to create a new context if the cache already has a matching one.

**Assuming beans self-update when a supplier changes value.** Suppliers are resolved when properties are accessed; initialized beans typically keep previously bound values.

**Combining a per-class container lifecycle with a shared context cache.** The container may stop while the context remains cached. Align the two lifecycles or evict the context from the cache.

**Putting `@DirtiesContext` on every test.** Doing so reduces context reuse and increases suite runtime. Mark dirty only when context resources or state truly change in an unreusable way.

**Assuming `@ActiveProfiles` solves dynamic endpoints.** Profiles select configuration groups; they do not manage container lifecycles or automatically update datasources.

**Running classes in parallel with the same cache key but different endpoints.** One class closing the context or stopping the resource can affect the other class. Isolate contexts and resources before enabling parallel execution.

## Design Principles

Treat the ApplicationContext and the dynamic resources used by its beans as two objects with coupled lifecycles. If multiple test classes share a context, endpoints and services referenced by that context must stay stable for as long as the context is cached. If endpoints vary by class, use separate contexts or refresh the context before the next class uses it.

`@DynamicPropertySource` lets you register values known only when tests run. The TestContext cache saves time by reusing contexts. Both mechanisms work well together when resource and context lifecycles are designed in sync; otherwise, beans can hold onto stale endpoints and cause hard-to-reproduce connection failures.
