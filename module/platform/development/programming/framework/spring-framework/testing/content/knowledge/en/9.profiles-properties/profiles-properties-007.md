# `DynamicPropertyRegistrar` by Supported Spring Version

In integration testing, some properties only have values after test resources have started. For example, Testcontainers may assign a random port for PostgreSQL; an embedded HTTP server may choose an available port; or a bean starting a mock service may expose its URL after startup. These values cannot be fixed in `application-test.properties` because they are known only at runtime.

Spring Test provides a dynamic property mechanism to register such values into `Environment`. Before Spring Framework 6.2, the common approach was using a static `@DynamicPropertySource` method on the test class. Starting with **Spring Framework 6.2.0**, `DynamicPropertyRegistrar` was added: a bean inside the test `ApplicationContext` itself can register dynamic properties, including properties obtained from other beans in the context.

`DynamicPropertyRegistrar` is useful when test resources or servers are managed as Spring beans. It keeps dynamic configuration close to the resource-creation configuration rather than placing every value into a static method on the test class.

## 1. Which Spring Versions Support `DynamicPropertyRegistrar`?

`DynamicPropertyRegistrar` was introduced in **Spring Framework 6.2.0** and belongs to the package:

```java
org.springframework.test.context.DynamicPropertyRegistrar
```

Therefore:

| Spring Framework Version | Capabilities |
| --- | --- |
| Before 5.2.5 | No `DynamicPropertyRegistry` or `@DynamicPropertySource` |
| 5.2.5 through 6.1.x | Has `DynamicPropertyRegistry` and `@DynamicPropertySource`; no `DynamicPropertyRegistrar` |
| 6.2.0 and later | Adds `DynamicPropertyRegistrar` beans and the ability to register dynamic properties from within the test `ApplicationContext` |

Spring Framework 7.x continues to support this API. When using Spring Boot, check the actual Spring Framework version pulled in by dependency management rather than looking only at the version of a single library or starter. Different Spring Boot versions manage different Spring Framework versions.

With Maven, you can inspect the actual dependency using:

```bash
mvn dependency:tree -Dincludes=org.springframework:spring-test
```

With Gradle:

```bash
./gradlew dependencyInsight --dependency spring-test --configuration testRuntimeClasspath
```

If `spring-test` is on a version lower than 6.2, `DynamicPropertyRegistrar` cannot be imported. Use `@DynamicPropertySource` if appropriate or upgrade Spring Framework according to your application's compatibility matrix.

Note that `DynamicPropertyRegistry` has existed since Spring Framework 5.2.5. The registry API and `@DynamicPropertySource` annotation predate `DynamicPropertyRegistrar`; do not confuse their version milestones.

## 2. What Is `DynamicPropertyRegistrar`?

`DynamicPropertyRegistrar` is a functional interface in the Spring TestContext Framework. It defines a single method:

```java
void accept(DynamicPropertyRegistry registry);
```

A bean in the test `ApplicationContext` implementing this interface is automatically detected by Spring Test. Spring eagerly initializes registrar beans before the regular singleton pre-instantiation phase, then invokes `accept()` with a `DynamicPropertyRegistry` so the registrar can add properties.

Minimal example:

```java
@TestConfiguration
class ApiTestConfiguration {

    @Bean
    ApiServer apiServer() {
        return new ApiServer();
    }

    @Bean
    DynamicPropertyRegistrar apiPropertiesRegistrar(ApiServer apiServer) {
        return registry -> registry.add("api.url", apiServer::getUrl);
    }
}
```

`ApiServer` is a bean managed inside the test context. The registrar receives that bean as a dependency and registers the `api.url` property using the `apiServer::getUrl` method reference.

Other beans in the context can read the property:

```java
@Component
class ApiClientConfiguration {

    ApiClientConfiguration(@Value("${api.url}") URI apiUrl) {
        // Use apiUrl to configure the client
    }
}
```

This is a key difference from `@DynamicPropertySource`: a registrar is a bean, so it can interact directly with other beans in the `ApplicationContext`.

## 3. DynamicPropertyRegistry and Supplier

`DynamicPropertyRegistry` provides the `add()` method:

```java
void add(String name, Supplier<Object> valueSupplier);
```

The second parameter is a `Supplier`, so the value is supplied when the property is resolved rather than having to be computed at the exact moment `add()` is called.

Example:

```java
registry.add("service.port", server::getPort);
registry.add("service.url", () -> "http://localhost:" + server.getPort());
```

A method reference or lambda can read runtime values. This is useful when a port or URL is assigned dynamically after the server starts.

Do not mistake `Supplier` for a task executed continuously. The supplier is invoked when Spring needs to resolve the property; if the source value changes between resolutions, results may change accordingly. For application configuration such as a database URL, ensure the resource is started and its value is stable before property-consuming beans are initialized.

## 4. When Are Registrars Discovered and Invoked?

Spring Test automatically detects beans of type `DynamicPropertyRegistrar` in the test `ApplicationContext`. Registrar beans are eagerly initialized before the singleton pre-instantiation phase. After a registrar is initialized, Spring invokes `accept(registry)` to register properties.

General flow:

```text
Create test ApplicationContext
          |
          v
Register bean definitions from test config
          |
          v
Initialize DynamicPropertyRegistrar beans (eager)
          |
          v
Call accept(DynamicPropertyRegistry)
          |
          v
Register property suppliers into Environment
          |
          v
Initialize regular singleton beans
          |
          v
Beans resolve properties as needed
```

This sequence ensures properties are registered before most regular singletons need to resolve their configuration.

### Warning about eager initialization

If a registrar interacts with another bean, that bean and its dependencies are also eagerly initialized. This is intentional behavior so the registrar can read values from source beans, but it can shift initialization timing compared to a context using only lazy beans.

For example, a registrar needs `ApiServer` to get the port. When Spring creates the registrar, `ApiServer` must be created first. If the constructor or init method of `ApiServer` starts the server, the server may start early during context bootstrap.

Avoid dependency cycles like:

```text
DynamicPropertyRegistrar
       |
       v
ApiClient bean
       |
       v
api.url property
       ^
       |
Registrar attempts to register api.url from ApiClient
```

A registrar should depend on the bean supplying the source value, not on the consumer needing the property that the registrar itself registers. For example, the registrar gets the URL from `ApiServer`; `ApiClient` is the consumer of `api.url`.

## 5. Complete Example with a Random-Port Server

Suppose a test needs an internal HTTP server. The server selects an available port on startup and supplies its URL to `RestClient` or another client in the application.

A simple abstraction:

```java
public class ApiServer {

    private final HttpServer server;

    public ApiServer() throws IOException {
        this.server = HttpServer.create();
    }

    public void start() throws IOException {
        server.bind(new InetSocketAddress("localhost", 0), 0);
        server.start();
    }

    public int getPort() {
        return server.getAddress().getPort();
    }

    public String getUrl() {
        return "http://localhost:" + getPort();
    }

    public void stop() {
        server.stop(0);
    }
}
```

Test configuration:

```java
@TestConfiguration
class ApiServerTestConfiguration {

    @Bean(initMethod = "start", destroyMethod = "stop")
    ApiServer apiServer() throws IOException {
        return new ApiServer();
    }

    @Bean
    DynamicPropertyRegistrar apiServerProperties(ApiServer apiServer) {
        return registry -> registry.add("test.api.base-url", apiServer::getUrl);
    }
}
```

A consumer can inject the URL:

```java
@Component
class ExternalApiClient {

    private final RestClient restClient;

    ExternalApiClient(@Value("${test.api.base-url}") String baseUrl) {
        this.restClient = RestClient.builder()
            .baseUrl(baseUrl)
            .build();
    }
}
```

A test loads the configuration:

```java
@SpringBootTest
@Import(ApiServerTestConfiguration.class)
class ExternalApiClientIntegrationTest {

    @Autowired
    Environment environment;

    @Autowired
    ExternalApiClient client;

    @Test
    void exposesTheStartedServerUrlAsADynamicProperty() {
        String baseUrl = environment.getRequiredProperty("test.api.base-url");

        assertTrue(baseUrl.startsWith("http://localhost:"));
    }
}
```

This example illustrates how a context-managed resource supplies a dynamic property. In a real project, `ApiServer` could be a dedicated test server or a bean created by a library. If the server needs to start via its own lifecycle, configure `initMethod`/`destroyMethod` or an appropriate lifecycle interface and ensure the URL is available when consumers initialize.

## 6. Example with Testcontainers and PostgreSQL

A common use case is using Testcontainers to launch a database on a random port. If the container is managed as a Spring bean in the test context, `DynamicPropertyRegistrar` can retrieve the JDBC URL, username, and password from the container bean.

Example with Testcontainers:

```java
@TestConfiguration
class PostgreSqlTestConfiguration {

    @Bean(initMethod = "start", destroyMethod = "stop")
    PostgreSQLContainer<?> postgresContainer() {
        return new PostgreSQLContainer<>("postgres:16-alpine");
    }

    @Bean
    DynamicPropertyRegistrar postgresProperties(
            PostgreSQLContainer<?> postgresContainer) {

        return registry -> {
            registry.add("spring.datasource.url", postgresContainer::getJdbcUrl);
            registry.add("spring.datasource.username", postgresContainer::getUsername);
            registry.add("spring.datasource.password", postgresContainer::getPassword);
        };
    }
}
```

A test using that configuration:

```java
@SpringBootTest
@Import(PostgreSqlTestConfiguration.class)
class OrderRepositoryIntegrationTest {

    @Autowired
    OrderRepository repository;

    @Test
    void persistsOrderInTheContainerDatabase() {
        // Write and read data via the real repository
    }
}
```

When Spring initializes the registrar, the `postgresContainer` dependency is created and its `start()` init method is called. The registrar registers suppliers retrieving connection details from the container. Singletons such as the datasource can then resolve `spring.datasource.url`, username, and password.

In this example, the container is a bean so its lifecycle is tied to the context. Spring calls `stop()` when the bean is destroyed. Keep the context cache in mind: if multiple test classes share the context, the container may live longer than a single test method. That is often desirable for context reuse, though you need to understand when the context is closed or evicted from the cache.

Another option is using the Testcontainers JUnit extension with a static `@Container` field and `@DynamicPropertySource`. When the container is managed outside the Spring context, that static approach is often more natural.

## 7. Comparing `DynamicPropertyRegistrar` and `@DynamicPropertySource`

Both mechanisms register dynamic properties, but they differ in placement and value source.

| Criterion | `@DynamicPropertySource` | `DynamicPropertyRegistrar` |
| --- | --- | --- |
| Available since | Spring Framework 5.2.5 | Spring Framework 6.2.0 |
| Where declared | `static` method on test class or suitable superclass | Bean in the test `ApplicationContext` |
| Input | `DynamicPropertyRegistry` passed to the method | `DynamicPropertyRegistry` passed to `accept()` |
| Accessing other Spring beans | Not directly through the static test method | Can inject and interact with context beans |
| Suitable cases | Static resources or resources managed by JUnit/Testcontainers extension | Resources/servers managed as Spring beans |
| Timing | Registers dynamic properties while preparing the test context | Registrar beans are eagerly initialized before singleton pre-instantiation |

### Traditional approach: `@DynamicPropertySource`

```java
@SpringBootTest
@Testcontainers
class OrderRepositoryTest {

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

The method must be `static` and take a single `DynamicPropertyRegistry` parameter. This fits when the container is managed by the JUnit Testcontainers extension and does not need access to Spring context beans to produce properties.

### Newer approach: registrar bean

```java
@TestConfiguration
class DatabaseTestConfiguration {

    @Bean
    DynamicPropertyRegistrar databaseProperties(DatabaseServer databaseServer) {
        return registry -> {
            registry.add("spring.datasource.url", databaseServer::jdbcUrl);
            registry.add("spring.datasource.username", databaseServer::username);
        };
    }
}
```

A registrar fits when `DatabaseServer` is a bean in the context or supplied by another test configuration. No static method on the test class is needed.

The two approaches are not mutually exclusive. A test can have multiple dynamic property sources, though you should avoid registering the same key in multiple places because it becomes hard to tell which source determines the final value. Pick one primary mechanism per resource group.

## 8. Precedence of Dynamic Properties

Dynamic properties have higher precedence than the following sources:

- `@TestPropertySource`.
- Operating system environment variables.
- Java system properties.
- Property sources added with `@PropertySource`.
- Application property sources added through standard declarative or programmatic means.

This allows tests to selectively override environment configuration. For example, `spring.datasource.url` registered by a registrar takes precedence when Spring resolves the property over URLs set in `application-test.properties` or corresponding system properties.

High precedence is useful for ensuring tests use the right test container or server. However, it can also mask misconfiguration if a registrar registers the wrong key or value. Verify key properties via `Environment` when diagnosing a context.

Example:

```java
@Autowired
Environment environment;

@Test
void usesTheContainerJdbcUrl() {
    String jdbcUrl = environment.getRequiredProperty("spring.datasource.url");

    assertTrue(jdbcUrl.startsWith("jdbc:postgresql://"));
}
```

Do not log passwords or secrets for diagnostics. When checking, verify the source or safe characteristics of the configuration rather than printing secret values.

## 9. Using a Registrar When Properties Come from Another Bean

This is the scenario `DynamicPropertyRegistrar` solves more cleanly than a static method. Suppose a test bean launches WireMock or a mock server and exposes its base URL.

```java
@TestConfiguration
class MockServerConfiguration {

    @Bean(initMethod = "start", destroyMethod = "stop")
    MockWebServer mockWebServer() {
        return new MockWebServer();
    }

    @Bean
    DynamicPropertyRegistrar mockServerProperties(MockWebServer mockWebServer) {
        return registry -> registry.add(
            "catalog.api.base-url",
            () -> mockWebServer.url("/").toString()
        );
    }
}
```

Consumers can inject `${catalog.api.base-url}` or read it via `Environment`. The registrar reads the value from the server bean instead of having to access a static field.

The important consideration is that the server must be started before the URL is used. If `MockWebServer` starts in its init method, Spring finishes initializing the dependency before the registrar registers the property. The supplier will retrieve the URL when the property is resolved.

## 10. Eager Initialization and Bean Lifecycle

Because registrars are eagerly initialized, there are several consequences to understand:

1. A registrar is not a typical lazy bean; Spring must instantiate it to register properties.
2. Beans injected into the registrar's constructor or factory method are also initialized early.
3. Dependencies of those beans can be initialized transitively.
4. If a source bean starts a server or container, that resource may start earlier than expected.
5. If a registrar depends on a consumer of the very property it registers, it can create a circular dependency or cause the consumer to initialize before the property is ready.

Design should keep responsibilities clearly separated:

```text
Resource bean (starts server/container)
          |
          v
DynamicPropertyRegistrar
          |
          v
Environment property
          |
          v
Consumer bean (HTTP client / DataSource)
```

The registrar depends on the resource bean; the consumer depends on the property. Do not create a reverse dependency from the registrar to the consumer.

If resource initialization is expensive, consider the test context scope and context reusability. Avoid creating multiple identical containers just because each test method has its own registrar; Spring Test normally caches contexts for equivalent configurations.

## 11. Registrars and `@DynamicPropertySource` on `@Bean` Methods

Spring Framework 6.2 also supports applying `@DynamicPropertySource` on a `@Bean` method inside a configuration class. In certain cases, this is used to request eager initialization of the corresponding bean so that properties it registers are available to other singletons.

General example:

```java
@TestConfiguration
class EmbeddedServerConfiguration {

    @Bean
    @DynamicPropertySource
    ApiServer apiServer(DynamicPropertyRegistry registry) {
        ApiServer server = new ApiServer();
        server.start();
        registry.add("api.url", server::getUrl);
        return server;
    }
}
```

This is another way to tie bean creation to dynamic property registration. If the goal is to register properties from another bean in the context, `DynamicPropertyRegistrar` usually expresses intent more clearly. Avoid using both mechanisms for the same key unnecessarily.

Check the API of your Spring version and the bean's lifecycle. For resources requiring cleanup, ensure a `destroyMethod` or appropriate lifecycle is configured to release resources when the context closes.

## 12. Registering Multiple Properties in One Registrar

A single registrar can register multiple properties related to the same resource:

```java
@Bean
DynamicPropertyRegistrar redisProperties(RedisTestServer redis) {
    return registry -> {
        registry.add("spring.data.redis.host", redis::host);
        registry.add("spring.data.redis.port", redis::port);
        registry.add("spring.data.redis.username", redis::username);
        registry.add("spring.data.redis.password", redis::password);
    };
}
```

Grouping properties belonging to one resource in the same registrar keeps configuration cohesive. If there are multiple independent resources such as a database, message broker, and mock HTTP server, you can create a separate registrar per resource to keep dependencies and lifecycles clear.

Name properties according to the conventions used by the application. With Spring Boot, relaxed binding and kebab-case names are typically used in configuration files; in the registry, register the exact key resolved by consumers.

## 13. Registrars Do Not Replace Resource Lifecycle Management

`DynamicPropertyRegistrar` only registers properties. It does not automatically create, start, stop, or clean up containers/servers unless those actions are configured in the bean lifecycle.

For example, if a registrar registers `server.getPort()` when the server has not yet started, the port value may be invalid or unready. Manage resources via:

- `@Bean(initMethod = "start", destroyMethod = "stop")` when appropriate.
- `InitializingBean` and `DisposableBean` if using lifecycle interfaces.
- `SmartLifecycle` for resources that need to participate in context start/stop phases.
- Testcontainers JUnit extension if containers are managed outside the Spring context.
- A dedicated extension or fixture if the resource lifecycle belongs to another test framework.

Choose one clear lifecycle owner. Avoid having both a JUnit extension and a Spring bean start/stop the same container, as that can stop the resource while the context still uses it or start it multiple times.

## 14. Handling Unresolved Properties

If a bean injects `@Value("${api.url}")` but the registrar does not register the property, the context can fail during bean creation. Common causes include:

- The test configuration containing the registrar was not imported or scanned.
- The test context is running Spring Framework older than 6.2, so the registrar API does not exist.
- The source bean was not created or its init method failed.
- The property name in the registrar differs from the consumer's name.
- The registrar depends on the consumer bean, creating an initialization cycle.
- The supplier is only called at property resolution time, and at that point the resource is not yet ready.
- Another property source or profile misleads the reader about which value is used.

To diagnose:

```java
String apiUrl = environment.getProperty("api.url");
assertNotNull(apiUrl, "api.url must be registered by the test context");
```

Inspect `Environment` after the context has initialized. When a value is missing, verify whether the registrar bean is in the context and whether `accept()` was invoked. Avoid adding a default production URL in tests just to let the context start, as that could cause tests to accidentally call real services.

## 15. Using Registrars in Test Slices vs. Full Contexts

`DynamicPropertyRegistrar` is detected in the test `ApplicationContext`, so it can be used in test contexts created by corresponding Spring Test annotations. However, the test configuration must actually be loaded into that slice/context.

With `@SpringBootTest`, you can import the test configuration:

```java
@SpringBootTest
@Import(ApiServerTestConfiguration.class)
class ApiIntegrationTest {
}
```

With a slice such as `@DataJpaTest`, verify that the required configuration is included in the slice and does not inadvertently pull in the entire application. If a registrar supplies datasource properties, slice configuration and datasource auto-configuration must be arranged accordingly.

For `@WebMvcTest`, if a dynamic property only serves a mocked client or a bean excluded from the slice, a registrar may not be needed. Choose test slices based on the behavior under test rather than adding out-of-scope resources just to use this API.

## 16. Combining Registrars with `@ActiveProfiles` and Property Files

Dynamic properties often supplement or override profile configurations. For example, `application-test.yml` can contain shared settings:

```yaml
feature:
  audit-enabled: false

spring:
  datasource:
    hikari:
      maximum-pool-size: 3
```

While the registrar supplies the database container's URL, username, and password:

```java
@Bean
DynamicPropertyRegistrar databaseProperties(PostgreSQLContainer<?> postgres) {
    return registry -> {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    };
}
```

Profiles continue to provide shared static configuration; the registrar provides values known only after the resource starts. Because dynamic properties have high precedence, registered keys override lower-precedence configuration sources during resolution.

## 17. Common Mistakes

- **Using a registrar on Spring Framework 6.1 or lower:** the class/interface does not exist in `spring-test` for those versions.
- **Confusing version milestones:** `DynamicPropertyRegistry` and `@DynamicPropertySource` are from 5.2.5, whereas `DynamicPropertyRegistrar` is from 6.2.0.
- **Putting the registrar in the wrong context:** the bean is not discovered if the test configuration is not loaded.
- **Assuming the registrar starts resources by itself:** registrars only register properties; resources need their own lifecycles.
- **Ignoring eager initialization:** registrar dependencies may be created early, starting servers/containers during context bootstrap.
- **Creating circular dependencies:** the registrar injects a consumer that needs the property the registrar registers.
- **Registering the same key in multiple places:** the value source becomes confusing and hard to diagnose.
- **Registering a URL before the server is ready:** the supplier is called on resolution, yet the resource has not been started properly.
- **Letting tests fall back to production URLs:** a missing property could cause clients to hit real systems if dangerous defaults exist.
- **Overlooking the context cache:** a container or server may live with the context longer than a single test method.
- **Using a registrar when static `@DynamicPropertySource` already fits:** adding unnecessary beans and dependencies for a resource managed outside the context.

## 18. Workflow for Choosing a Dynamic Property Mechanism

When a test needs runtime properties, identify the value source first:

1. **Fixed values for tests:** use `@TestPropertySource`, `properties` on test annotations, or test configuration files.
2. **Values from static/external resources outside the Spring context:** use `@DynamicPropertySource` with a `static` method, such as a container managed by the JUnit Testcontainers extension.
3. **Values from beans inside the test ApplicationContext:** use `DynamicPropertyRegistrar` on Spring Framework 6.2 or later.
4. **Resources needing start/stop:** manage lifecycle via Spring beans or test extensions; the registrar only reads the resource's values.
5. **Consumers needing properties at startup:** ensure the registrar registers properties before singleton consumers and creates no dependency cycles.
6. **Applications on versions older than 6.2:** continue using `@DynamicPropertySource` or upgrade Spring Framework according to compatible dependency management.

`DynamicPropertyRegistrar` extends dynamic property testing by bringing property registration inside the `ApplicationContext`. Starting with Spring Framework 6.2.0, registrar beans can read values from other beans, register suppliers into `Environment`, and supply runtime configuration to singletons initialized afterward. Pay attention to eager initialization, resource lifecycles, resolution order, and property precedence so integration tests use the exact resources they manage.

## 19. Official Documentation

- [Spring Framework Reference — Context Configuration with Dynamic Property Sources (6.2)](https://www.springframework.org/spring/reference/6.2/testing/testcontext-framework/ctx-management/dynamic-property-sources.html)
- [DynamicPropertyRegistrar Javadoc (Spring Framework 6.2)](https://docs.spring.io/spring-framework/docs/6.2.2/javadoc-api/org/springframework/test/context/DynamicPropertyRegistrar.html)
- [Spring Framework 6.2 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-6.2-Release-Notes)
