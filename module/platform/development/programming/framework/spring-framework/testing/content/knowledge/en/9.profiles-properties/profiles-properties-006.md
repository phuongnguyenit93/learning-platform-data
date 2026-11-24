# DynamicPropertyRegistry and Dynamically Supplied Values

Integration tests often require configuration that is only known once test resources have started. A PostgreSQL container may be mapped to a random port; a mock HTTP server may pick a free port; a test broker may generate a dedicated connection address for each run. If these values are hardcoded into `application-test.yml`, tests become environment-dependent or prone to port conflicts.

Spring Test provides `@DynamicPropertySource` and `DynamicPropertyRegistry` to register properties from suppliers. Tests declare property names along with a `Supplier`, and Spring adds those values to `Environment` when creating the `ApplicationContext`. This connects application configuration to resources whose addresses appear only at runtime, while keeping tests self-describing about their configuration sources.

## 1. Why Are Dynamic Properties Needed?

Ordinary properties usually come from configuration files, environment variables, JVM system properties, or test runner arguments. They suit stable values such as feature flags, timeouts, profiles, or schema names. However, some values are known only after a test dependency starts:

- JDBC URL and port of a database container.
- Host/port of a mock HTTP server.
- Kafka bootstrap servers or the address of a test message broker.
- Endpoint of a mock service started on a random port.
- Temporary directories, test tokens, or connection details allocated at runtime.

For example, Testcontainers may assign a different host port on every run. If configuration hardcodes `localhost:5432`, tests may accidentally connect to a local database or fail when that port is already occupied.

`@DynamicPropertySource` solves this by registering a supplier that retrieves the value from the running resource itself:

```java
@DynamicPropertySource
static void registerProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
}
```

Here, `postgres::getJdbcUrl` is a method reference matching `Supplier`. Spring invokes the supplier when the property is accessed. Consequently, the registration method can execute before the final value needs to be read, as long as the resource is ready at the moment the supplier is invoked.

## 2. `@DynamicPropertySource` and `DynamicPropertyRegistry`

`@DynamicPropertySource` is an annotation in the Spring TestContext Framework. It marks a method used to add dynamic properties to the `Environment` of a test `ApplicationContext`.

The annotated method must:

- Be `static`.
- Accept a single parameter of type `DynamicPropertyRegistry`.
- Register properties via `registry.add(name, supplier)`.
- Be placed in the test class or an appropriate superclass/enclosing class for Spring Test to discover.

`DynamicPropertyRegistry` provides the `add(String name, Supplier<Object> valueSupplier)` method. The property name is the string the application reads via `@Value`, `Environment`, or `@ConfigurationProperties`; the supplier returns the value to provide.

Simple example:

```java
@SpringBootTest
class FeatureConfigurationTest {
    @DynamicPropertySource
    static void featureProperties(DynamicPropertyRegistry registry) {
        registry.add("feature.checkout.enabled", () -> true);
        registry.add("feature.checkout.max-items", () -> 12);
        registry.add("feature.checkout.label", () -> "integration-test");
    }

    @Autowired
    private Environment environment;

    @Test
    void readsDynamicallyRegisteredProperties() {
        assertThat(environment.getProperty("feature.checkout.enabled", Boolean.class))
                .isTrue();
        assertThat(environment.getProperty("feature.checkout.max-items", Integer.class))
                .isEqualTo(12);
        assertThat(environment.getProperty("feature.checkout.label"))
                .isEqualTo("integration-test");
    }
}
```

Spring can convert data types when reading properties via `Environment` or binding into `@ConfigurationProperties`. The supplier returns `Object`, so it can provide strings, numbers, booleans, or any value type suited to the property consumer.

### 2.1. Suppliers are evaluated on demand

Unlike calling `getJdbcUrl()` directly and storing the string in a variable inside the configuration method, registering a method reference defers the retrieval action:

```java
registry.add("spring.datasource.url", postgres::getJdbcUrl);
```

A supplier lets the property obtain its value after the resource has started and is ready to expose its endpoint. This is why dynamic properties fit randomly assigned ports.

You can register using a lambda:

```java
registry.add("catalog.api.base-url", () -> mockServer.url("/").toString());
```

Or a method reference:

```java
registry.add("spring.datasource.username", postgres::getUsername);
registry.add("spring.datasource.password", postgres::getPassword);
```

Choose a style that makes retrieval timing and the data source clear. Do not precompute a URL from an unallocated port or an unstarted container.

### 2.2. Registering multiple related properties

A single resource often supplies multiple properties. For example, a database container supplies URL, username, and password. Register them together in one place so readers see they belong to the same dependency:

```java
@DynamicPropertySource
static void databaseProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
```

For a mock service, you can register the URL along with control flags:

```java
@DynamicPropertySource
static void serviceProperties(DynamicPropertyRegistry registry) {
    registry.add("catalog.client.base-url", catalogServer::baseUrl);
    registry.add("catalog.client.connect-timeout", () -> "2s");
    registry.add("catalog.client.enabled", () -> true);
}
```

Property names must match the keys read by the application. If a service uses `catalog.client.url` while the test registers `catalog.client.base-url`, the property will not take effect even though the registration method runs successfully.

## 3. Integrating with Testcontainers

Testcontainers starts real dependencies inside containers so integration tests can verify actual drivers, SQL, migrations, and protocols. Connection addresses are usually known only after a container runs, making `@DynamicPropertySource` a common way to pass those values into Spring.

PostgreSQL example:

```java
@SpringBootTest
@Testcontainers
class CustomerRepositoryIntegrationTest {
    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("customers")
                    .withUsername("test-user")
                    .withPassword("test-password");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    private CustomerRepository customers;

    @Test
    void savesAndLoadsCustomer() {
        Customer saved = customers.save(new Customer("Lan"));

        assertThat(customers.findById(saved.id()))
                .get()
                .extracting(Customer::name)
                .isEqualTo("Lan");
    }
}
```

`@Container` marks the container managed by the Testcontainers JUnit Jupiter extension. Because the field is `static`, the container has class-level lifecycle per the extension's convention. `@DynamicPropertySource` registers suppliers retrieving the JDBC URL and credentials from that container. When Spring creates the datasource, properties are read from the started container.

The example assumes the project declares appropriate Testcontainers dependencies, including the PostgreSQL module and JUnit Jupiter integration. Dependency versions must be compatible with the Spring Boot, JUnit, and Testcontainers versions used by the project.

### 3.1. Class-scoped vs. method-scoped containers

Testcontainers JUnit Jupiter supports both static and instance containers:

- A `static` container is started once per class and stopped after the class.
- An instance container is started per test method and stopped after that method.

Dynamic property methods must be `static`, so the common pattern is a static container shared across the test class. If each method needs its own container, consider another resource management approach or design tests so property/context lifecycles align. A Spring `ApplicationContext` is not automatically recreated for each test method merely because an instance container changes.

Do not change a container's endpoint while the context is actively using a datasource created from the old endpoint. The context and its dependencies must have compatible lifecycles.

### 3.2. Spring Boot `@ServiceConnection` as an alternative

In Spring Boot versions supporting Testcontainers service connections, `@ServiceConnection` can automatically configure several common connection factories without manually registering individual datasource properties. This mechanism is convenient when using container types recognized by Spring Boot.

`@DynamicPropertySource` remains useful when:

- The application needs custom property names not belonging to standard service connections.
- The dependency is not supported by `@ServiceConnection`.
- The test needs to supply multiple customized runtime values.
- You want explicit control over how properties map into `Environment`.

Avoid using both mechanisms simultaneously for the same property if doing so creates duplicate configuration or makes it hard to tell which source wins. Pick the mechanism matching your dependency type and Spring Boot version.

## 4. Connecting a Mock HTTP Server

A service client often receives its base URL from a property:

```java
@ConfigurationProperties(prefix = "catalog.client")
record CatalogClientProperties(URI baseUrl) {
}

@Component
class CatalogClient {
    private final WebClient webClient;

    CatalogClient(CatalogClientProperties properties,
                  WebClient.Builder builder) {
        this.webClient = builder.baseUrl(properties.baseUrl().toString()).build();
    }
}
```

In an integration test, a mock server can start on a random port. The test registers the actual URL via a dynamic property so Spring binds it into `CatalogClientProperties`.

```java
@SpringBootTest
class CatalogClientIntegrationTest {
    static final MockWebServer server = new MockWebServer();

    static {
        try {
            server.start();
        } catch (IOException exception) {
            throw new ExceptionInInitializerError(exception);
        }
    }

    @DynamicPropertySource
    static void catalogProperties(DynamicPropertyRegistry registry) {
        registry.add("catalog.client.base-url",
                () -> URI.create(server.url("/").toString()));
    }

    @AfterAll
    static void stopServer() throws IOException {
        server.shutdown();
    }

    @Autowired
    private CatalogClient client;

    @Test
    void callsConfiguredCatalogEndpoint() throws Exception {
        server.enqueue(new MockResponse()
                .setResponseCode(200)
                .addHeader("Content-Type", "application/json")
                .setBody("""{"id":"item-42","name":"Keyboard"}"""));

        CatalogItem item = client.findById("item-42");

        assertThat(item.name()).isEqualTo("Keyboard");
        RecordedRequest request = server.takeRequest(1, TimeUnit.SECONDS);
        assertThat(request).isNotNull();
        assertThat(request.getPath()).isEqualTo("/items/item-42");
    }
}
```

The example uses a static initializer so the server is ready before Spring needs to read properties. In a real project, you can use a JUnit extension or fixture managing server lifecycle; the crucial requirement is that the server is started before the supplier is evaluated and stopped after the test class finishes.

The property name `catalog.client.base-url` must match how `CatalogClientProperties` binds. If the record uses `URI baseUrl`, Spring Boot Configuration Properties binds the `base-url` key to the `baseUrl` component via relaxed binding.

Do not use an assumed URL like `http://localhost:8080` when a mock server can allocate a random port. Dynamic URLs avoid conflicts with other processes and make tests more independent of machine configuration.

## 5. Precedence Order of Dynamic Properties

A dynamic property source has high precedence in `Environment`. Properties registered with `@DynamicPropertySource` take precedence over normal sources such as:

- `@TestPropertySource`.
- JVM system properties.
- Operating system environment variables.
- Property sources declared in the application, such as `application.properties` or `application.yml`.

This allows tests to override default production endpoints with the address of a container or mock server. For example, `application.yml` might contain:

```yaml
catalog:
  client:
    base-url: https://catalog.example.test
```

A test can supply the runtime endpoint:

```java
@DynamicPropertySource
static void catalogProperties(DynamicPropertyRegistry registry) {
    registry.add("catalog.client.base-url", mockServer::baseUrl);
}
```

When the application reads this property in the test context, the dynamic value takes precedence. Still, register the exact key and override only the necessary values. A single dynamic property does not automatically replace every property sharing the same prefix.

### 5.1. Checking the actual value in `Environment`

When unsure which property is winning, you can inject `Environment` and read the key directly:

```java
@Autowired
private Environment environment;

@Test
void usesContainerJdbcUrl() {
    String url = environment.getRequiredProperty("spring.datasource.url");

    assertThat(url).isEqualTo(postgres.getJdbcUrl());
}
```

In a configuration test, this assertion confirms the registered property value. If the goal is to test the real datasource, execute a query or save/read data through a repository to verify the connection works.

Do not log credentials or tokens in test output. When debugging, prefer printing the host, port, or resolved property name, and mask authentication details.

## 6. Dynamic Properties and `@ConfigurationProperties`

Dynamic properties work with Spring's normal property-reading mechanisms. For instance, a `@ConfigurationProperties` bean can bind a URL supplied by the registry:

```java
@ConfigurationProperties(prefix = "payment.gateway")
record PaymentGatewayProperties(URI baseUrl, Duration timeout) {
}
```

The test registers the properties:

```java
@DynamicPropertySource
static void paymentProperties(DynamicPropertyRegistry registry) {
    registry.add("payment.gateway.base-url", paymentServer::baseUrl);
    registry.add("payment.gateway.timeout", () -> "1500ms");
}
```

Spring Boot binds these values into the record when creating the configuration bean. `Duration` supports formats recognized by Spring Boot, such as `1500ms`, `2s`, or `1m`.

If a property fails to bind, check:

1. Whether the prefix on `@ConfigurationProperties` is correct.
2. Whether the registered property name matches relaxed binding rules.
3. Whether the configuration properties class has been scanned or enabled.
4. Whether another bean or higher-precedence property source exists.
5. Whether the supplier returns a value compatible with the target type.

Do not confuse registering a property with automatically creating configuration beans. `@DynamicPropertySource` only adds values to `Environment`; the application still needs the usual `@ConfigurationProperties` registration and binding setup.

## 7. Inheriting `@DynamicPropertySource` Methods

`@DynamicPropertySource` methods can be placed in a superclass so multiple integration tests share one resource or the same property registration logic:

```java
abstract class BaseDatabaseIntegrationTest {
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

@SpringBootTest
class CustomerRepositoryTest extends BaseDatabaseIntegrationTest {
    @Autowired
    private CustomerRepository customers;
}

@SpringBootTest
class OrderRepositoryTest extends BaseDatabaseIntegrationTest {
    @Autowired
    private OrderRepository orders;
}
```

Subclasses inherit the property registration method. This reduces boilerplate for groups of tests sharing the same database configuration.

### 7.1. When subclasses use different resources

A subtle situation arises when a superclass has `@DynamicPropertySource`, yet the supplier returns different values per subclass. Spring treats dynamic property source methods as part of the test context configuration and caches contexts based on the merged configuration. Runtime values returned by suppliers do not necessarily create distinct cache keys for every value.

For instance, two subclasses inherit the same method, but each subclass swaps the container or endpoint in its own way. If Spring reuses the context created for the previous class, beans may retain connections created from the old endpoint.

When dynamic properties genuinely vary across subclasses and alter the required context, mark the context dirty on the base class or structure tests so each resource group gets its own context:

```java
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
abstract class BaseExternalServiceIntegrationTest {
    // Dynamic property source and resources used per test group.
}
```

`@DirtiesContext` removes the context from the cache after the class. Use it only when differing dynamic values genuinely require a separate context. If all subclasses share one container and endpoint, keeping the context cached is usually more efficient.

## 8. Dynamic Properties and Resource Lifecycles

A supplier only provides values; it does not start or stop containers, servers, or brokers. Tests must manage resource lifecycles using Testcontainers, JUnit extensions, `@BeforeAll`/`@AfterAll`, or appropriate cleanup mechanisms.

A general sequence:

```text
Start test resource
        |
        v
Spring reads test configuration
        |
        v
@DynamicPropertySource registers supplier
        |
        v
Environment retrieves property
        |
        v
Spring creates beans using endpoint/credentials
        |
        v
Test executes requests or queries
        |
        v
Close context and release resources
```

Exact ordering depends on how the extension or fixture starts the resource. The practical rule is that the supplier must be able to read a valid value when Spring resolves properties, and the resource must stay alive for as long as beans use it.

### 8.1. Do not return stale endpoints

Avoid storing a URL/port before the server starts or returning a value that changes after the context has created clients. If a resource can restart and receive a new port, an existing context does not automatically update datasources or HTTP clients already built from the old property.

When restarting a resource, decide whether a new context must be created or whether the endpoint can stay stable. If the context needs recreation, manage it with test lifecycle hooks and `@DirtiesContext` at the appropriate scope.

### 8.2. Suppliers are not the place for side effects

A supplier should read values from an already initialized resource. Do not use a supplier to start containers, create databases, send requests, or mutate global state. Properties may be accessed multiple times; side effects inside a supplier can repeat and make outcomes unpredictable.

Separate responsibilities:

- Extensions/fixtures start and stop resources.
- `@DynamicPropertySource` registers connection values.
- Spring creates beans based on properties.
- Tests execute behavior and clean up needed data.

## 9. Comparing with `@TestPropertySource` and Profiles

These three mechanisms are often used together, serving different kinds of configuration:

| Mechanism | Value Source | When Appropriate |
|---|---|---|
| `@ActiveProfiles` | Selects configuration group by profile | Want to enable `application-integration.yml` or test environment config |
| `@TestPropertySource` | Static files or inline properties | Timeouts, feature flags, queue names, or known-ahead values |
| `@DynamicPropertySource` | Suppliers retrieving values at runtime | URLs/ports/credentials of containers or test servers |

Combined example:

```java
@SpringBootTest
@ActiveProfiles("integration")
@TestPropertySource(properties = {
        "catalog.client.retry.max-attempts=2",
        "catalog.client.connect-timeout=1s"
})
class CatalogIntegrationTest {
    @DynamicPropertySource
    static void dynamicCatalogProperties(DynamicPropertyRegistry registry) {
        registry.add("catalog.client.base-url", catalogServer::baseUrl);
    }
}
```

Profiles choose the shared configuration group; `@TestPropertySource` supplies fixed test values; the dynamic registry supplies the endpoint known only after the server starts. Splitting responsibilities this way keeps the source of every property clear.

## 10. Troubleshooting Dynamic Properties

### 10.1. Property not found

If the application reports `Could not resolve placeholder`, check the key name in `registry.add` against the key read by `@Value` or `@ConfigurationProperties`. Verify that the method is annotated with `@DynamicPropertySource`, is `static`, and accepts `DynamicPropertyRegistry`.

For example, if the application reads:

```java
@Value("${catalog.client.base-url}")
private URI baseUrl;
```

the registry must register `catalog.client.base-url`, not a similar-looking key like `catalog.base-url`.

### 10.2. Supplier invoked before resource is ready

If the supplier calls `getJdbcUrl()` before the container is running, check how Testcontainers lifecycle is managed. With JUnit Jupiter, use an extension-managed static container or ensure the fixture starts before Spring resolves properties.

Do not call `start()` repeatedly inside the supplier. That mixes resource lifecycle with configuration reading and can spawn unintended containers.

### 10.3. Connecting to the wrong port or a stale endpoint

Print the non-sensitive host/port returned by the supplier, check running containers, and verify whether the context was cached from another test. If endpoints vary across subclasses while the context is reused, review inheritance configuration and `@DirtiesContext` scope.

### 10.4. Property value not bound into bean

Check the prefix, key name, data type, and `@ConfigurationProperties` registration. A property present in `Environment` yet absent from a configuration bean is usually a binding or bean registration issue, not a supplier issue.

### 10.5. Property overridden

Dynamic property sources outrank normal property sources, but if the test reads a different key or application logic overwrites the value after binding, results may differ from expectations. Read the key directly from `Environment`, then check the bound bean to isolate whether the issue lies in the property source or bean configuration step.

### 10.6. Context cache masking endpoint changes

If a supplier returns different values per subclass while the dynamic source method is inherited unchanged, the context key may not reflect that runtime change. Separate contexts or mark dirty when differing endpoints truly require a fresh context.

## 11. Combined Example: Database and Service Endpoint

An application may need both a database container and a mock HTTP service. Each dependency supplies a dynamic endpoint:

```java
@SpringBootTest
@Testcontainers
class OrderIntegrationTest {
    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Container
    static final GenericContainer<?> catalog =
            new GenericContainer<>("wiremock/wiremock:3.9.1")
                    .withExposedPorts(8080);

    @DynamicPropertySource
    static void runtimeProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);

        registry.add("catalog.client.base-url", () ->
                "http://" + catalog.getHost() + ":" +
                        catalog.getMappedPort(8080));
    }

    @Autowired
    private OrderService orders;

    @Test
    void createsOrderUsingRuntimeDependencies() {
        Order order = orders.create(new CreateOrderCommand("customer-42"));

        assertThat(order.id()).isNotBlank();
    }
}
```

This example illustrates registering multiple runtime dependencies in one registry. For a meaningful real test, the catalog container needs expected stubs/responses configured and the test should verify application behavior using those responses. `GenericContainer` here merely illustrates a service with an exposed port; in real projects, use a dedicated Testcontainers module or suitable mock server.

Avoid writing tests that only verify the application starts if the goal is integration testing. Execute a business operation spanning the database and service endpoint, then assert outcomes at the appropriate boundary.

## 12. Common Design Mistakes

### Hardcoding test resource ports

Fixed ports may already be occupied or point to another service. Use random ports and register the endpoint at runtime.

### Using `@DynamicPropertySource` for static properties

Known timeouts or feature flags usually belong in inline properties or `@TestPropertySource`. Reserve the dynamic registry for values genuinely available only at runtime.

### Forgetting to manage resource lifecycles

The registry does not start or stop containers. Use extensions or fixtures to manage start/stop and ensure resources stay alive for as long as the context uses them.

### Registering the wrong property name

The supplier still gets registered while the application reads a different key. Match property names exactly and inspect `Environment` when needed.

### Introducing side effects in suppliers

Suppliers may be invoked when properties are resolved. Only read values; start resources in lifecycle hooks or extensions.

### Sharing contexts when endpoints change

The context cache may reuse beans bound to an old endpoint. Align contexts with resource lifecycles or use `@DirtiesContext` when needed.

### Assuming dynamic properties auto-create configuration beans

The registry only adds values to `Environment`. `@ConfigurationProperties` beans still must be scanned/enabled, and clients still must be registered as usual.

## 13. Workflow for Applying `DynamicPropertyRegistry`

When an integration test needs runtime-only values, follow this sequence:

1. Identify the properties the application needs to read, such as a JDBC URL or an HTTP client's base URL.
2. Choose the test resource supplying those values: Testcontainers, mock server, or corresponding fixture.
3. Determine the resource's lifecycle and ensure it is ready when Spring resolves properties.
4. Declare a `static` method with `@DynamicPropertySource` and a `DynamicPropertyRegistry` parameter.
5. Register each key with a supplier or method reference retrieving the value from the resource.
6. Verify properties are resolved and beans have bound the right values.
7. Exercise real integration behavior; do not merely verify the context starts.
8. If endpoints change across test classes, account for the context cache and separate contexts when needed.
9. Stop resources after tests complete and clean up data outside transactions.

A dynamic property should have a single source, a clear name, and a lifecycle compatible with the beans consuming it. When endpoints vary, account for both suppliers and the context cache; merely registering a lambda does not automatically reconfigure an already created client or datasource.

## 14. Key Principles to Remember

- `@DynamicPropertySource` marks a static method that registers properties for a test context.
- `DynamicPropertyRegistry.add(name, supplier)` binds a key to a value supplied via a supplier.
- Suppliers fit ports, URLs, and credentials known only after test resources start.
- The registry adds values to `Environment`; it does not start containers, create beans, or manage cleanup.
- Dynamic properties outrank `@TestPropertySource`, JVM system properties, environment variables, and ordinary application property sources.
- Use `@ConfigurationProperties` or `@Value` as usual to consume registered properties.
- Dynamic property source methods can be inherited, but watch the context cache if runtime values vary across subclasses.
- Use `@DirtiesContext` only when changing endpoints require a fresh context; do not use it as a substitute for database or broker cleanup.
- Keep suppliers pure data readers and let extensions/fixtures manage resource lifecycles.

`DynamicPropertyRegistry` connects Spring configuration to dependencies allocated at runtime. When property names, suppliers, and resource lifecycles are declared clearly, integration tests can use random ports and isolated endpoints while still initializing the `ApplicationContext` consistently.
