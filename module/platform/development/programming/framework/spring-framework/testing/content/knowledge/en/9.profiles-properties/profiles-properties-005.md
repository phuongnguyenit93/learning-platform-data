# @DynamicPropertySource for Runtime-Assigned Addresses and Ports

In integration testing, a backing service may be started at an address or port known only at runtime. For example, Testcontainers creates a PostgreSQL container and maps internal port `5432` to an available port on the host machine. The host port can differ on each run to avoid conflicting with other processes. A mock HTTP service may also choose a random port on startup.

The Spring application still needs to receive the exact connection address to create a `DataSource`, HTTP client, or integration bean. If `localhost:5432` or a fixed port is hardcoded in a test configuration file, the test can become dependent on the host machine's environment. `@DynamicPropertySource` solves this problem by registering Spring properties from values provided at runtime.

This annotation is commonly used with Spring Test and Testcontainers. A `static` method receives a `DynamicPropertyRegistry`, then registers property names with a `Supplier`. Spring fetches the value only when the property is accessed, allowing it to read the host and mapped port after the test resource has started.

## 1. The Problem with Fixed Addresses and Ports

Suppose an application has a PostgreSQL connection configuration:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders
    username: orders
    password: secret
```

This setup only works if PostgreSQL is actually running on the host at port `5432`, a database named `orders` exists, and the credentials match. In CI or on a teammate's machine, that port might already be in use, the database might not be installed, or the service might run in a container with a different mapped host port.

Testcontainers typically lets a container listen on a fixed internal port and maps that port to an available port on the host. For example:

```text
PostgreSQL container
    container port: 5432
             |
             | Docker port mapping
             v
Test host
    host: localhost (or host suitable for runtime)
    mapped port: 49172 (for example, assigned at runtime)
```

The application must connect to the address provided by the container and cannot assume the host port is always `5432`. Similarly, if an HTTP service starts on a random port, the URL must be constructed after the service has chosen its port.

## 2. What Is @DynamicPropertySource?

`@DynamicPropertySource` is a Spring Test annotation used to register dynamic properties into `Environment` when Spring prepares the `ApplicationContext` for a test. The annotated method must be `static` and take a single parameter of type `DynamicPropertyRegistry`.

Skeleton example:

```java
@DynamicPropertySource
static void registerProperties(DynamicPropertyRegistry registry) {
    registry.add("service.base-url", () -> "http://localhost:49172");
}
```

`registry.add(...)` accepts:

- The property name the application will read, such as `spring.datasource.url` or `partner.api.base-url`.
- A `Supplier` returning the property's value when Spring needs to read it.

This method does not start the server itself, does not allocate a port itself, and does not check whether the service is ready. It only wires runtime values produced by another component into Spring's configuration.

Properties registered this way have higher precedence than normal configuration sources such as `@TestPropertySource`, system properties, environment variables, and property sources added with `@PropertySource`. Thus, a dynamic value can override default configuration in `application.yml` or a test property source value when the same property name is used.

## 3. Structure of the Registration Method

Spring provides two main types:

```java
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
```

A registration method has the form:

```java
@DynamicPropertySource
static void registerServiceProperties(DynamicPropertyRegistry registry) {
    registry.add("partner.api.host", () -> "127.0.0.1");
    registry.add("partner.api.port", () -> 49172);
    registry.add("partner.api.base-url", () -> "http://127.0.0.1:49172");
}
```

This example illustrates static values wrapped in suppliers. In practice, suppliers typically read the host and port from a started container or server:

```java
registry.add("partner.api.host", partnerServer::getHost);
registry.add("partner.api.port", () -> partnerServer.getMappedPort(8080));
```

The second example only illustrates the idea; depending on each server or container API, pass the internal container port into `getMappedPort(int)` if the method requires an argument. The next section shows a complete registration example.

Key points to remember:

- The method must be `static`, because Spring needs to read configuration before creating the test instance.
- The parameter must be `DynamicPropertyRegistry`.
- `registry.add` accepts a supplier, so use a method reference or lambda to retrieve the value when needed.
- The property name must match the name the application actually uses.
- The resource providing the host and port must remain active for as long as the `ApplicationContext` uses those properties.

## 4. Complete Example with PostgreSQL Testcontainers

### 4.1. Declaring test dependencies

In a Spring Boot project, the test starter usually already provides Spring Test and JUnit Jupiter. Add the Testcontainers modules corresponding to JUnit Jupiter and PostgreSQL.

Gradle Groovy example:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'

    testImplementation platform(
        "org.testcontainers:testcontainers-bom:${testcontainersVersion}"
    )
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
}
```

`testcontainersVersion` should be defined centrally in the project's version catalog or Gradle configuration. The Testcontainers BOM aligns Testcontainers modules with one another. Avoid arbitrarily assigning different versions to `junit-jupiter`, `postgresql`, and related Testcontainers modules.

Maven example:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>testcontainers-bom</artifactId>
            <version>${testcontainers.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
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

The Maven example assumes `${testcontainers.version}` is declared in `properties` or a parent POM. If a project does not use Spring Boot, standalone `spring-test` and JUnit Jupiter can still be used, provided dependency management aligns the required versions.

### 4.2. Registering URL, username, and password from a container

Suppose an application has a repository that needs to connect to PostgreSQL. The test class can declare a static container and register properties:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertNotNull;

@Testcontainers
@SpringBootTest
class OrderRepositoryIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("orders")
                    .withUsername("orders")
                    .withPassword("secret");

    @DynamicPropertySource
    static void registerDataSourceProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void repositoryUsesRunningPostgresContainer() {
        assertNotNull(orderRepository);
    }
}
```

`@Container` marks a container managed by the Testcontainers JUnit Jupiter extension. Because the field is `static`, the container has class-level lifecycle and is shared across test methods in the class. PostgreSQL listens on default internal port `5432`; Testcontainers maps that port to an available port on the host.

`getJdbcUrl()` returns the JDBC URL including the host and mapped port. `getUsername()` and `getPassword()` return the credentials configured for the container. Method references are passed directly to `registry.add`, allowing Spring to obtain the values when properties are resolved.

In the application, Spring Boot reads the three `spring.datasource.*` properties to create the `DataSource`. The `application.yml` file can keep default values for other environments; the test's dynamic properties take higher precedence in the test context.

### 4.3. Why use a supplier?

You can write:

```java
registry.add("spring.datasource.url", () -> postgres.getJdbcUrl());
```

or:

```java
registry.add("spring.datasource.url", postgres::getJdbcUrl);
```

Both forms provide a supplier. The value is retrieved when Spring accesses the property, rather than forcing the getter to be called immediately at registration time. This matters because the host and mapped port are only meaningful after the container has started.

Do not compute the address before the container is started and keep a default value instead. A supplier also does not start the container by itself; container lifecycle remains the responsibility of Testcontainers or server management code.

## 5. Registering Host and Mapped Port of an HTTP Container

An application does not always need a JDBC URL. A service might call an HTTP dependency running in a container, such as a catalog service, identity provider, or mock API.

Suppose the container listens on internal port `8080`:

```java
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.utility.DockerImageName;

@Container
static final GenericContainer<?> partner =
        new GenericContainer<>(DockerImageName.parse("example/partner-api:1.0"))
                .withExposedPorts(8080);
```

After the container has started, Testcontainers provides:

- `partner.getHost()`: the host the test process should use to reach the container.
- `partner.getMappedPort(8080)`: the host port mapped from internal port `8080`.

Register the base URL property:

```java
@DynamicPropertySource
static void registerPartnerProperties(DynamicPropertyRegistry registry) {
    registry.add("partner.api.base-url", () ->
            "http://" + partner.getHost() + ":" + partner.getMappedPort(8080)
    );
}
```

The application can read this value via `@Value`:

```java
@Component
class PartnerClient {

    private final RestClient restClient;

    PartnerClient(
            RestClient.Builder builder,
            @Value("${partner.api.base-url}") String baseUrl
    ) {
        this.restClient = builder.baseUrl(baseUrl).build();
    }
}
```

Or use `@ConfigurationProperties` if there are multiple related properties:

```java
@ConfigurationProperties(prefix = "partner.api")
public record PartnerApiProperties(URI baseUrl) {
}
```

When using record binding, enable configuration properties scanning or register the class with `@EnableConfigurationProperties`. The `URI` type models an endpoint address more clearly than an arbitrary string.

Do not hardcode `localhost` if the Testcontainers environment might use a different Docker host. `getHost()` provides the address Testcontainers determines to be reachable from the test process.

## 6. Registering Host, Port, and URL Separately

Some clients accept a separate host and port instead of a base URL. Each property can be registered individually:

```java
@DynamicPropertySource
static void registerPartnerProperties(DynamicPropertyRegistry registry) {
    registry.add("partner.api.host", partner::getHost);
    registry.add("partner.api.port", () -> partner.getMappedPort(8080));
}
```

Spring can convert values to the target type when injecting. For example:

```java
@Component
class PartnerConnectionSettings {

    private final String host;
    private final int port;

    PartnerConnectionSettings(
            @Value("${partner.api.host}") String host,
            @Value("${partner.api.port}") int port
    ) {
        this.host = host;
        this.port = port;
    }
}
```

If the application uses `@ConfigurationProperties`, you can declare a class holding `host` and `port` and let Spring bind properties by prefix. That approach is usually better when endpoint configuration also includes scheme, timeout, path, or authentication.

Register properties to match the application's configuration model. If the client accepts a single `URI`, register the base URL; if the client needs separate host and port, register two separate properties. Avoid maintaining multiple duplicate-meaning properties that could drift out of sync.

## 7. Using with WireMock or a Random-Port Server

An in-JVM server can also select a port on startup. For example, WireMock supports `dynamicPort()` and exposes the actual port via `port()`.

One way to organize this is to start the static server before Spring creates the context, then register the port:

```java
import com.github.tomakehurst.wiremock.WireMockServer;
import org.junit.jupiter.api.AfterAll;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.options;

class PartnerClientIntegrationTest {

    static final WireMockServer wireMock =
            new WireMockServer(options().dynamicPort());

    static {
        wireMock.start();
    }

    @DynamicPropertySource
    static void registerPartnerProperties(DynamicPropertyRegistry registry) {
        registry.add("partner.api.base-url", wireMock::baseUrl);
    }

    @AfterAll
    static void stopWireMock() {
        wireMock.stop();
    }
}
```

`baseUrl()` returns the URL with the server's actual port. The example uses a static initializer so the server is already running before Spring resolves properties. If using another lifecycle mechanism, ensure the server has started before beans depending on the endpoint are created.

For servers managed by a JUnit extension, pay attention to lifecycle ordering between the extension starting the server and Spring Test initializing the context. Do not assume an arbitrary `@BeforeAll` always runs before all Spring context preparation steps. Lifecycle organization must guarantee the supplier is only invoked once the server is ready and the server is not stopped while the context is still in use.

In a real test class, add the WireMock dependency matching your version. If a test needs multiple servers, each base URL can be registered under distinct properties.

## 8. Combining with @TestPropertySource and application.yml

Projects often keep default configuration in `src/main/resources/application.yml`:

```yaml
partner:
  api:
    base-url: http://localhost:8080
```

This value can serve local configuration or a separately provisioned environment. In an integration test, `@DynamicPropertySource` supplies the actual URL:

```java
@DynamicPropertySource
static void registerPartnerProperties(DynamicPropertyRegistry registry) {
    registry.add("partner.api.base-url", partner::getBaseUrl);
}
```

If the test class also has:

```java
@TestPropertySource(properties = "partner.api.base-url=http://localhost:9999")
```

then the dynamic property of the same name has higher precedence and the value from the supplier is used. This is useful when a test property file supplies defaults while the real endpoint is only known after starting the resource.

Name properties to match application configuration. If the application reads `partner.client.url` while the test registers `partner.api.base-url`, the dynamic value will not affect the client. A common mistake is registering the right host/port under the wrong prefix compared to `@ConfigurationProperties` or `@Value`.

## 9. Combining with @ServiceConnection in Spring Boot

In some Spring Boot tests using Testcontainers, `@ServiceConnection` can be used instead of manually registering common connection properties.

PostgreSQL example:

```java
@Testcontainers
@SpringBootTest
class OrderRepositoryIntegrationTest {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");
}
```

Spring Boot recognizes the container type and creates connection details for the corresponding service. This is convenient when standard datasource configuration is needed without manually mapping URL, username, and password.

`@DynamicPropertySource` remains useful when:

- A property does not belong to a service connection type automatically recognized by Spring Boot.
- The application needs custom properties, such as `partner.api.base-url`, a mock API token, or an internal service port.
- The project uses only Spring Framework without Spring Boot's service connection mechanism.
- Explicit control is needed over how runtime resources map to property names.

There is no need to re-register `spring.datasource.*` with `@DynamicPropertySource` if `@ServiceConnection` already provides full connection details and the application uses that mechanism. Choose one consistent configuration approach to avoid two sources trying to control the same connection.

## 10. Container Lifecycle, Suppliers, and the Context Cache

An important consideration is that Spring Test's `ApplicationContext` can be cached across test classes. Meanwhile, a container or server may be started and stopped according to a test class's lifecycle. These two lifecycles must be compatible.

### 10.1. Suppliers do not manage resource lifecycle

The snippet:

```java
registry.add("partner.api.base-url", () ->
        "http://" + partner.getHost() + ":" + partner.getMappedPort(8080)
);
```

only returns the container's address. It does not guarantee the container is still running when a bean uses that URL. If the container has stopped, the property value may remain in the context while connections fail.

Therefore, the resource supplying the property must live at least as long as the context needs to use it. With a `static @Container`, Testcontainers manages the container at class scope. If the context is reused beyond the container's lifecycle, adjust how resources or contexts are managed.

### 10.2. Context cache and subclasses inheriting DynamicPropertySource

`@DynamicPropertySource` methods can be inherited from a parent test class. This is useful when multiple test classes share one container or the same test infrastructure.

However, if subclasses use different containers or dynamic values change across subclasses, Spring may reuse a cached `ApplicationContext` with configuration built from earlier values. In that case, the context may keep using the old address.

Spring Test documentation notes that when dynamic properties vary across subclasses, `@DirtiesContext` may be needed to ensure the context cache is refreshed between classes. Example:

```java
@Testcontainers
abstract class AbstractDatabaseIntegrationTest {

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

Subclasses can share infrastructure and the same container lifecycle. If each subclass needs a different container or endpoint, consider separate contexts, `@DirtiesContext` in the right scope, or managing a container whose lifecycle outlives the context.

### 10.3. Avoiding stopping servers too early

A common mistake is stopping WireMock or a container after a test class while the context remains in the cache and is reused by another test. Then the HTTP client bean still holds the old URL while the server is no longer running.

Common remedies include:

- Using resources with lifecycles matching the cached context.
- Using a static container shared across test classes that share the same configuration.
- Marking the context for eviction from the cache with `@DirtiesContext` when the context-bound resource ends.
- Separating test classes so contexts and resources have independent, controllable lifecycles.

Do not add `@DirtiesContext` to every test out of habit, because it reduces caching benefits and slows the suite down. Use it only when context state or lifecycle-bound resources genuinely require refreshing.

## 11. Common Pitfalls When Using @DynamicPropertySource

### 11.1. Non-static method

Spring needs to read dynamic properties during context preparation, before the test instance is fully constructed. If the method is not `static`, Spring cannot invoke it under the annotation's contract. Declare `static void`.

### 11.2. Wrong method parameters

The method must accept a single `DynamicPropertyRegistry` parameter. Do not pass `Environment`, `ApplicationContext`, or a self-created registry.

### 11.3. Registering a property under the wrong name

If the application reads `spring.datasource.url`, registering `spring.datasource.jdbc-url` will not automatically replace that property. Check prefixes and field names in application configuration.

### 11.4. Reading the port before the container starts

The mapped port exists only after the container has started. Use a supplier to defer fetching the value and ensure Testcontainers lifecycle starts the container before Spring needs the value.

### 11.5. Using the container port instead of the mapped port

`8080` may be the port inside the container, but a client running on the host needs the mapped host port. With Testcontainers, use `getMappedPort(8080)` and `getHost()`.

### 11.6. Assuming host is always localhost

In many Docker environments, `localhost` may not point to where the container is reachable from the test process. Use `getHost()` to obtain the host provided by Testcontainers.

### 11.7. Container stopped while context remains cached

The context may still hold the old URL after the container exits. Align container lifecycle with the context or refresh the context when needed.

### 11.8. Supplier returning unstable values

A supplier should return the same endpoint throughout the context's lifetime. If each invocation generates a different port or URL, beans may receive inconsistent configuration. Create the resource once, keep the host and mapped port stable, and let the supplier read those values.

### 11.9. Expecting @DynamicPropertySource to start the service itself

The annotation only registers properties. If the container or server has not been started, the supplier may fail to retrieve host/port or the client may fail to connect. Manage lifecycle with Testcontainers, a JUnit extension, or an appropriate startup mechanism.

## 12. Workflow for Applying to a Runtime-Assigned Endpoint

When an integration test needs to connect to a service whose address or port varies, follow this sequence:

1. **Identify the service providing the endpoint.** For example PostgreSQL, Redis, WireMock, or an HTTP container.
2. **Choose the lifecycle management mechanism.** Use the Testcontainers JUnit extension, the library's server lifecycle, or a shared fixture.
3. **Start the resource before Spring needs properties.** Verify that the host and mapped port are retrievable.
4. **Register properties with `@DynamicPropertySource`.** Use the exact property names read by the application and pass suppliers to retrieve runtime values.
5. **Initialize clients or beans from properties.** You can use `@Value`, `@ConfigurationProperties`, or datasource auto-configuration.
6. **Keep the resource active throughout the context lifetime.** Account for the context cache and inheritance relationships between test classes.
7. **Verify integration behavior.** Perform a real operation via a repository or HTTP client to prove the endpoint is configured properly.

For example, with a PostgreSQL container, `getJdbcUrl()` provides the JDBC URL with host and mapped port. With an HTTP container, combine `getHost()` and `getMappedPort(containerPort)` to construct the base URL. Both cases avoid hardcoding host ports and allow tests to run in environments with different port allocation behavior.

`@DynamicPropertySource` bridges runtime-allocated test resources and Spring's `Environment`. The `static` method registers properties via `DynamicPropertyRegistry`; suppliers provide the host, mapped port, or URL when Spring needs to read them. When combined properly with Testcontainers or server lifecycles, context cache management, and application property names, integration tests can reliably connect to services whose addresses and ports vary on every run.
