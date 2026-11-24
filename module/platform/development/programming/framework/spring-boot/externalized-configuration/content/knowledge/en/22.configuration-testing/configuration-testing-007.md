# Supplying Dynamic Values with `@DynamicPropertySource` in Spring Boot Tests

## 1. The Problem: Test Configuration Unknown When Writing YAML

Spring Boot lets applications pull configuration from `application.yml`, `application.properties`, environment variables, Java system properties, and other `PropertySource`s. In an integration test, the values an application needs may **only appear after test resources finish starting**.

Examples:

- A PostgreSQL container listens on internal port `5432`, while Docker maps it to a random host port.
- A Redis or Kafka container is spun up fresh for each CI run.
- An HTTP mock server starts on a free OS-assigned port.
- Tests need to supply URLs, hosts, ports, credentials, or resource names generated during fixture setup.
- The Spring application context must see those values **before creating dependent beans** such as `DataSource` or HTTP clients.

If you hardcode:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/testdb
~~~

tests fail whenever the container maps to port `51423` or `49311`. Test code can ask Testcontainers for the real port, yet it must **pass that value into Spring's `Environment`** so auto-configuration reads it properly.

The Spring TestContext Framework provides `@DynamicPropertySource` for this job.

> **Core idea:** `@DynamicPropertySource` marks a `static` method inside an integration test class. The method receives `DynamicPropertyRegistry` and registers pairs of **property name + `Supplier` returning the value on demand**. Spring inserts them into the test application context's property sources.

This mechanism is not production hot-reload. It exists primarily for tests with dynamically provisioned external resources.

## 2. Components and Packages

Primary imports:

~~~java
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.DynamicPropertyRegistry;
~~~

Both belong to Spring Framework's `org.springframework.test.context` package. With Spring Boot, `spring-boot-starter-test` normally brings in Spring Test and JUnit Jupiter.

Conceptual flow:

~~~text
JUnit / Spring TestContext
           |
           v
@DynamicPropertySource static method
           |
           v
DynamicPropertyRegistry.add(name, Supplier)
           |
           v
Dynamic PropertySource in Environment
           |
           v
Spring Boot Binder / @Value / @ConfigurationProperties
           |
           v
Application bean receives URL, host, port ...
~~~

Division of responsibilities:

| Component | Responsibility |
| --- | --- |
| `@DynamicPropertySource` | Marks the method registering dynamic properties on the test class |
| `DynamicPropertyRegistry` | Accepts property names and value suppliers |
| `Supplier` | Returns the value when the framework resolves the property |
| `Environment` | Combines configuration sources according to precedence |
| `@Value` | Injects a single property value into a bean |
| `@ConfigurationProperties` | Binds a configuration group into a typed Java object |
| `Testcontainers` | Manages actual containers/test resources if used |

`@DynamicPropertySource` does not start containers for you, does not spin up HTTP servers, and does not turn arbitrary keys into keys understood by Spring Boot auto-configuration.

## 3. Exact Method Signature Rules

Minimal template:

~~~java
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

class EndpointIntegrationTest {

    @DynamicPropertySource
    static void register(DynamicPropertyRegistry registry) {
        registry.add("app.client.host", () -> "127.0.0.1");
        registry.add("app.client.port", () -> 50001);
        registry.add("app.client.timeout", () -> "3s");
    }
}
~~~

For a method annotated with `@DynamicPropertySource` in an integration test class:

1. It must be **`static`**.
2. It must accept **a single parameter** of type `DynamicPropertyRegistry`.
3. It is normally declared returning **`void`**.
4. Values are registered via `registry.add(propertyName, valueSupplier)`.
5. The test class must execute through **Spring TestContext**, e.g. `@SpringBootTest` or `@SpringJUnitConfig`.

An **invalid** example missing `static`:

~~~java
@DynamicPropertySource
void register(DynamicPropertyRegistry registry) {
    registry.add("app.client.port", () -> 50001);
}
~~~

Another **invalid** example missing the registry parameter:

~~~java
@DynamicPropertySource
static void register() {
}
~~~

And you cannot add an arbitrary `Environment` parameter:

~~~java
// Invalid signature for @DynamicPropertySource.
@DynamicPropertySource
static void register(
        DynamicPropertyRegistry registry, Environment environment) {
}
~~~

Do not annotate this method with `@Bean` like a regular factory method. TestContext discovers and invokes it under the annotation's own contract.

## 4. `DynamicPropertyRegistry.add` and Laziness

API:

~~~java
registry.add("app.client.port", () -> 50001);
~~~

The second parameter is a `Supplier`, not a precomputed value.

Wrong:

~~~java
registry.add("app.client.port", 50001);
~~~

Right:

~~~java
registry.add("app.client.port", () -> 50001);
~~~

Right with a method reference:

~~~java
registry.add("app.client.port", mockServer::getPort);
~~~

The supplier is invoked **when the property is resolved**. For example:

~~~java
registry.add("app.client.port", () -> {
    System.out.println("Resolving app.client.port");
    return mockServer.getPort();
});
~~~

Calling `registry.add(...)` does not necessarily call `mockServer.getPort()` at registration time. If no bean or code ever asks for the property, the supplier may never run during the test.

However, **lazy does not mean "called only once."** A property can be resolved at multiple points, so the supplier may be invoked repeatedly. Therefore it should:

- Return quickly and deterministically.
- Only read state from an already-started resource.
- Never start/stop containers or servers on each invocation.
- Never mutate global state.
- Never generate a fresh random number on every lookup.

Risky example:

~~~java
registry.add("app.client.port", () ->
        java.util.concurrent.ThreadLocalRandom.current()
            .nextInt(20000, 60000));
~~~

If two beans resolve the property at different times, they could receive **two different ports** bound to no running server.

## 5. Small Test Proving Precedence

First without Docker, you can write a self-contained test:

~~~java
package com.example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.TestPropertySource;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = DynamicPortTest.TestApp.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@TestPropertySource(properties = "app.client.port=12345")
class DynamicPortTest {

    @SpringBootApplication
    static class TestApp {
    }

    @DynamicPropertySource
    static void dynamicPort(DynamicPropertyRegistry registry) {
        registry.add("app.client.port", () -> 50001);
    }

    @Autowired
    Environment environment;

    @Test
    void choosesDynamicValue() {
        Integer port = environment.getProperty(
                "app.client.port", Integer.class);

        assertThat(port).isEqualTo(50001);
    }
}
~~~

In this example:

- `@TestPropertySource` supplies static value `12345`.
- `@DynamicPropertySource` supplies a supplier returning `50001` for the same key.
- Under Spring TestContext precedence, **dynamic properties outrank `@TestPropertySource`**.
- `Environment` returns `50001`.
- The test needs no web server because `webEnvironment=NONE`.

This verifies the mechanism cleanly before bringing in complex containers or fixtures.

## 6. Dynamic Values Bound into `@ConfigurationProperties`

Suppose an application defines client configuration:

~~~java
package com.example.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        String host,
        int port,
        Duration timeout) {
}
~~~

Application class registering properties:

~~~java
package com.example;

import com.example.config.ClientProperties;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(ClientProperties.class)
public class DemoApplication {
}
~~~

Test:

~~~java
package com.example;

import com.example.config.ClientProperties;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = DemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class ClientPropertiesTest {

    @DynamicPropertySource
    static void dynamicClientSettings(DynamicPropertyRegistry registry) {
        registry.add("app.client.host", () -> "127.0.0.1");
        registry.add("app.client.port", () -> 50001);
        registry.add("app.client.timeout", () -> "750ms");
    }

    @Autowired
    ClientProperties client;

    @Test
    void bindsTypedValues() {
        assertThat(client.host()).isEqualTo("127.0.0.1");
        assertThat(client.port()).isEqualTo(50001);
        assertThat(client.timeout())
                .isEqualTo(Duration.ofMillis(750));
    }
}
~~~

The same Spring Boot binding system applies as with YAML: `750ms` converts to `Duration`, `port` converts to integer, and fields populate the object.

`@DynamicPropertySource` does not require manually parsing keys. Simply register keys **matching the prefix and model** of the consuming component.

## 7. Why Testcontainers Is Commonly Paired with `@DynamicPropertySource`

Testcontainers runs real services inside containers. A service listens on a fixed port **inside the container**, while Docker maps a different port on the host:

~~~text
Inside PostgreSQL container: port 5432
Run #1 host mapped port: 49321
Run #2 host mapped port: 51437

postgres.getJdbcUrl()
postgres.getUsername()
postgres.getPassword()
          |
          v
DynamicPropertyRegistry
          |
          v
spring.datasource.url
spring.datasource.username
spring.datasource.password
          |
          v
Spring Boot DataSource auto-configuration
~~~

Never assume a container is reachable on `localhost:5432`. Testcontainers provides APIs returning the JDBC URL containing the right host, mapped port, and database.

Method references fit naturally:

~~~java
registry.add("spring.datasource.url", postgres::getJdbcUrl);
registry.add("spring.datasource.username", postgres::getUsername);
registry.add("spring.datasource.password", postgres::getPassword);
~~~

These three keys are the exact properties Spring Boot expects when configuring a datasource via standard auto-configuration.

If you register a custom key `test.postgres.jdbc-url` while Spring Boot waits for `spring.datasource.url`, auto-configuration does not magically treat the two as synonymous.

## 8. Complete Example: PostgreSQL Container in an Integration Test

### 8.1. Dependencies

With Maven, Spring Boot 3.x, and Spring Boot BOM/dependency management:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jdbc</artifactId>
</dependency>

<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
</dependency>

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
~~~

Testcontainers versions must be compatible with your project's Spring Boot/Java versions and BOM. Testcontainers also requires a working Docker-compatible runtime locally/in CI; adding dependencies alone is not enough.

### 8.2. Test Code

~~~java
package com.example;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
@SpringBootTest(
        classes = DemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class PostgreSqlIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                .withDatabaseName("integration_db")
                .withUsername("integration_user")
                .withPassword("integration_password");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    DataSource dataSource;

    @Test
    void canQueryDatabase() {
        Integer result = new JdbcTemplate(dataSource)
                .queryForObject("select 1", Integer.class);

        assertThat(result).isEqualTo(1);
    }
}
~~~

Explanation:

1. `@Testcontainers` enables Testcontainers' JUnit Jupiter extension.
2. `@Container static` delegates container lifecycle management to the extension per test class.
3. The container runs a dedicated test PostgreSQL instance with example database/user/password.
4. `@DynamicPropertySource` supplies the JDBC URL and credentials **of the running container**.
5. Spring Boot binds `spring.datasource.*` to create `DataSource`.
6. `JdbcTemplate` confirms the connection can execute a simple query.

The password in the snippet is strictly for an isolated test container, never a production credential.

### 8.3. Watch Out for Context Caching and Lifetimes

A cached Spring context can outlive a static Testcontainers container managed per test class by the JUnit extension. If the container stops yet the context remains cached and gets reused, the cached datasource tries connecting to a dead port.

This is not a bug in dynamic properties; it is a **mismatch between resource lifecycle and context caching**. Later sections show how to prevent this.

## 9. Redis Container with a Mapped Port

Another example:

~~~java
package com.example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
@SpringBootTest(
        classes = DemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class RedisIntegrationTest {

    @Container
    static GenericContainer<?> redis =
            new GenericContainer<>("redis:7-alpine")
                .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisSettings(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", redis::getHost);
        registry.add("spring.data.redis.port",
                () -> redis.getMappedPort(6379));
    }

    @Autowired
    Environment environment;

    @Test
    void usesCorrectMappedPort() {
        Integer port = environment.getProperty(
                "spring.data.redis.port", Integer.class);

        assertThat(port).isEqualTo(redis.getMappedPort(6379));
    }
}
~~~

In Spring Boot 3.x, Redis connection properties use prefix `spring.data.redis`. Older Boot examples may use `spring.redis`, so check your Boot version.

This test only verifies **resolved configuration values**. To test actual Redis client connectivity, include the client/dependency and perform Redis read/write operations in the test.

## 10. Precedence of Dynamic Properties

Per Spring Framework TestContext documentation, dynamic properties outrank sources such as:

- `@TestPropertySource` (both files and inline properties).
- Java system properties (e.g. `-Dapp.key=value`).
- OS environment variables.
- Property sources added by the application via `@PropertySource`.
- Property sources added programmatically by the application via standard mechanisms.

Example:

~~~yaml
# application.yml
app:
  client:
    port: 10000
~~~

~~~java
@SpringBootTest(properties = "app.client.port=20000")
@TestPropertySource(properties = "app.client.port=30000")
class ClientTest {

    @DynamicPropertySource
    static void dynamic(DynamicPropertyRegistry registry) {
        registry.add("app.client.port", () -> 40000);
    }
}
~~~

The resolved value of `app.client.port` in the test context's Spring Environment is **40000** under the precedence above.

This lets container addresses override static developer URLs without editing main configuration files.

### 10.1. Only Registered Keys Are Overridden Directly

Suppose YAML has:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/defaultdb
    username: default_user
    password: default_password
~~~

And the dynamic registry overrides only the URL:

~~~java
registry.add("spring.datasource.url", postgres::getJdbcUrl);
~~~

The result can mix the container's URL with YAML's username and password—an **inconsistent** state likely causing authentication failures.

Register the complete set of properties needed for an external service:

~~~java
registry.add("spring.datasource.url", postgres::getJdbcUrl);
registry.add("spring.datasource.username", postgres::getUsername);
registry.add("spring.datasource.password", postgres::getPassword);
~~~

A dynamic source does not remove related keys that you omitted from registration.

## 11. Comparison with `@TestPropertySource`

`@TestPropertySource` fits **known-ahead-of-time** configuration:

~~~java
@TestPropertySource(properties = {
    "app.feature.enabled=true",
    "app.client.timeout=2s"
})
~~~

Or loading a file:

~~~java
@TestPropertySource(locations = "classpath:/test-settings.properties")
~~~

It has no direct way to know **which port Docker will assign at runtime** before the container starts.

| Criterion | `@TestPropertySource` | `@DynamicPropertySource` |
| --- | --- | --- |
| Declaration point | Annotation on test class | Annotation on `static` method |
| Input | Static key-values or files | Key + `Supplier` |
| Fits container-assigned ports | Not directly | Yes |
| Can load `.properties` files | Yes | Not the API's purpose |
| Precedence for same key | Lower than dynamic sources | Higher than test property sources |
| Needs external lifecycle management | No for static data | Yes when supplier reads containers/servers |
| Works without a Spring context | Does not build Environment automatically | Also does not build Environment automatically |

If you only want `app.feature.enabled=true`, `@TestPropertySource` or `@SpringBootTest(properties=...)` is simpler without needing a dynamic supplier.

## 12. `@SpringBootTest(properties=...)` and Compile-Time Limits

A static value can be written:

~~~java
@SpringBootTest(properties = {
    "app.cache.enabled=false",
    "app.client.timeout=500ms"
})
~~~

Java annotation attributes require compile-time constants, however. You cannot pass runtime values like `testServer.getPort()` directly into a string attribute.

Meanwhile:

~~~java
@DynamicPropertySource
static void dynamic(DynamicPropertyRegistry registry) {
    registry.add("app.client.port", testServer::getPort);
}
~~~

registers a method reference evaluated on demand.

Also distinguish `@SpringBootTest(webEnvironment = RANDOM_PORT)`: that is Spring Boot's mechanism for choosing a port for the **application's own embedded web server**, readable via `@LocalServerPort`. `@DynamicPropertySource` typically supplies endpoints of **external dependencies** like database containers or mock HTTP services.

Do not use dynamic properties just to force the application's embedded web server onto a port; `RANDOM_PORT` has its own dedicated contract.

## 13. Combining with `@ActiveProfiles("test")`

A test can combine static profiles with dynamic properties:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class RepositoryTest {

    @DynamicPropertySource
    static void register(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }
}
~~~

Clean separation:

- `@ActiveProfiles("test")`: activates the test profile and `application-test.yml`.
- `application-test.yml`: stable settings like feature flags, timeouts, and logging levels.
- `@DynamicPropertySource`: hosts, ports, URLs, and runtime credentials produced by fixtures.
- Testcontainers or equivalent extensions: create and manage actual resources.

Example YAML for the test profile:

~~~yaml
app:
  features:
    payments-enabled: false
  client:
    timeout: 3s
~~~

Static settings remain active; the dynamic source only needs to register runtime-determined properties.

## 14. Do Not Confuse Dynamic Properties with Bean Refreshing

Example:

~~~java
static final AtomicReference<String> currentUrl =
        new AtomicReference<>("http://127.0.0.1:51001");

@DynamicPropertySource
static void dynamic(DynamicPropertyRegistry registry) {
    registry.add("app.api.url", currentUrl::get);
}
~~~

After the context has refreshed:

~~~java
currentUrl.set("http://127.0.0.1:52002");
~~~

Calling:

~~~java
environment.getProperty("app.api.url");
~~~

**can** read the new value from the Supplier when resolved. However, an already-injected bean field:

~~~java
@Value("${app.api.url}")
private String apiUrl;
~~~

does not automatically update `apiUrl`.

Likewise, a `@ConfigurationProperties` record bound at startup continues holding the old URL until the bean is recreated or rebound via a dedicated mechanism.

**Two separate concepts:**

1. `Supplier` supplies a value during lookup.
2. Spring binds/injects values into beans during bean creation.

`@DynamicPropertySource` does not re-run step 2 whenever a Supplier's return value changes. To test multiple endpoints, create separate contexts or perform explicit lookup where truly dynamic behavior is required.

## 15. Spring TestContext Caching and Stale Endpoints

Spring TestContext Framework caches application contexts with equivalent configurations to reduce startup overhead. While useful, this can expose bugs with dynamic resources.

Example:

~~~text
Test A
  Container A: port 51001
  ApplicationContext X
  DataSource X -> jdbc:...:51001

Test A finishes
  Container A stops
  ApplicationContext X may remain in cache

Test B
  Container B: port 52002
  TestContext reuses ApplicationContext X
  DataSource X still points to port 51001
  -> Connection refused
~~~

**Do not assume** that returning a different value from a supplier forces Spring to recreate the context. Cache keys do not necessarily include runtime values computed by suppliers.

Spring Framework documentation recommends considering `@DirtiesContext` on base classes when dynamic properties change across subclasses and cause context-caching issues.

~~~java
import org.springframework.test.annotation.DirtiesContext;

@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
abstract class BaseIntegrationTest {
    @DynamicPropertySource
    static void dynamic(DynamicPropertyRegistry registry) {
        // Values from fixtures specific to each test class.
    }
}
~~~

This tells Spring to mark the context dirty after the class, preventing reuse of a stale context by the next class.

**Trade-off:** recreating Spring contexts is slow. If multiple tests can share **a single long-lived shared container**, managing shared lifecycles properly is usually faster than dirtying the context after every class.

## 16. Inheriting `@DynamicPropertySource`

A `@DynamicPropertySource` method can be inherited from a test superclass, an interface recognized by the framework, or an enclosing test class under nested test configuration rules.

Base class example:

~~~java
public abstract class BaseDatabaseTest {

    protected static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                .withDatabaseName("shared_test");

    static {
        postgres.start();
    }

    @DynamicPropertySource
    static void database(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }
}
~~~

Child tests:

~~~java
@SpringBootTest
class OrderRepositoryTest extends BaseDatabaseTest {
}

@SpringBootTest
class CustomerRepositoryTest extends BaseDatabaseTest {
}
~~~

This example starts a static container via a static initializer as a shared-fixture pattern. Ensure appropriate cleanup/lifecycle handling at suite/JVM shutdown and ensure tests do not interfere with each other's data.

If subclasses swap container instances or expose different dynamic properties, evaluate context caching as described earlier.

### 16.1. Should the Entire Suite Share One Database?

Sharing a container cuts startup time, yet risks test A leaving data for test B. You can use:

- Transaction rollbacks where appropriate.
- Explicit data cleanup.
- Separate schemas/databases per test group.
- Independent containers/contexts when isolation outweighs speed.

`@DynamicPropertySource` only supplies connection info; it does not isolate data automatically.

## 17. Risks Under Parallel Test Execution

Some CI environments enable parallel test execution. Keep in mind:

- Static references are shared across tests in the same JVM.
- A container must never stop while a cached context still needs it.
- Do not mutate a static `postgres` field across two tests running concurrently.
- Do not call `System.setProperty(...)` to swap endpoints per test, as it is JVM-global state.
- Ensure Suppliers never mutate state or start servers repeatedly.
- When two tests modify the same database concurrently, enforce proper transactions/isolation.
- Test contexts connecting to distinct resources need explicit separation of resources and contexts.

Good Supplier example:

~~~java
registry.add("spring.datasource.url", postgres::getJdbcUrl);
~~~

Risky example:

~~~java
registry.add("app.api.url", () -> {
    server.startOnRandomPort();
    return server.baseUrl();
});
~~~

Suppliers should never start a server each time a property is read. Resources must be started and ready before lookup.

## 18. Is JUnit `@BeforeAll` Early Enough?

One pattern for starting a mock server:

~~~java
static final MockServerFixture server = new MockServerFixture();

@BeforeAll
static void start() {
    server.startOnRandomPort();
}

@DynamicPropertySource
static void dynamic(DynamicPropertyRegistry registry) {
    registry.add("app.api.url", server::baseUrl);
}
~~~

Be careful: Spring TestContext/extension lifecycles and JUnit callbacks can cause context setup to resolve properties earlier than you expect `@BeforeAll` to execute. Do not assume this pattern is always safe in every arrangement.

Safer options:

- Use JUnit/Testcontainers extensions with compatible lifecycle contracts.
- Start fixtures before the context resolves properties, such as controlled static initialization.
- Use a base test fixture with a clearly defined shared lifecycle.
- Have Suppliers read URLs/ports only after the server has actually started.

Illustrative static fixture example:

~~~java
static final MockServerFixture server =
        MockServerFixture.startOnRandomPort();

@DynamicPropertySource
static void dynamic(DynamicPropertyRegistry registry) {
    registry.add("app.api.url", server::baseUrl);
}
~~~

`MockServerFixture` is an illustrative class, not a built-in Spring API. With WireMock, OkHttp MockWebServer, or similar tools, adapt to the library's real lifecycle and API.

## 19. Spring Boot `@ServiceConnection` Can Replace It Where Supported

In Spring Boot 3.1+, `@ServiceConnection` with `spring-boot-testcontainers` integrates supported Testcontainers services into Spring Boot auto-configuration via **ConnectionDetails**.

Example:

~~~java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class DatabaseConnectionTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    // Test uses the auto-configured DataSource.
}
~~~

When Spring Boot recognizes a supported container and service type, it supplies connection details without requiring a `@DynamicPropertySource` method to register `spring.datasource.url`, `username`, and `password` manually.

### 19.1. Comparison

| `@DynamicPropertySource` | `@ServiceConnection` |
| --- | --- |
| Part of Spring TestContext | Part of Spring Boot Testcontainers integration |
| Registers properties by key and supplier | Supplies ConnectionDetails for supported services |
| Works with Testcontainers or custom-managed resources | Targets Testcontainers/service connections recognized by Boot |
| Requires knowing consumer property names | Avoids listing URL/username/password keys |
| Fits custom SDKs and HTTP clients | Fits auto-configurations consuming ConnectionDetails |
| Values appear in Environment under keys | Contract is the connection abstraction, not arbitrary custom keys |

When supplying `vendor.client.base-url` to a custom SDK, `@DynamicPropertySource` remains essential. When pairing a PostgreSQL container with Boot DataSource auto-configuration, `@ServiceConnection` cuts boilerplate.

Avoid combining both to configure the **exact same dependency** unless you clearly understand ConnectionDetails vs. environment property precedence in your Spring Boot version.

## 20. `DynamicPropertyRegistrar` as Another Option in Spring Framework 6.2+

Spring Framework 6.2+ introduces `DynamicPropertyRegistrar`: a bean that registers dynamic properties when the test ApplicationContext initializes.

Example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.DynamicPropertyRegistrar;

@Configuration(proxyBeanMethods = false)
class TestServerConfig {

    @Bean
    TestApiServer apiServer() {
        return new TestApiServer();
    }

    @Bean
    DynamicPropertyRegistrar apiUrl(TestApiServer apiServer) {
        return registry -> registry.add(
                "app.api.base-url", apiServer::getBaseUrl);
    }
}
~~~

`TestApiServer` is an illustrative class you would implement; this code highlights how the registrar receives a bean and registers a method reference.

Differences:

- `@DynamicPropertySource` is a **static method on the test class**; ideal for resources created **outside** the Spring context.
- `DynamicPropertyRegistrar` is a **bean in the test context**; it can inject another bean and register properties supplied by that bean.

Registrar beans are discovered and initialized early before normal singleton pre-instantiation so they can register properties. Any bean injected into a registrar is also initialized early.

Do not wire complex business services into a registrar unnecessarily, as lifecycle ordering becomes hard to manage. Projects on Spring Framework prior to 6.2 do not have this API; verify versions via dependency management.

## 21. Data Types: Suppliers Do Not Always Return Strings

Suppliers can return primitives/wrappers or convertible objects:

~~~java
@DynamicPropertySource
static void properties(DynamicPropertyRegistry registry) {
    registry.add("app.worker.count", () -> 4);
    registry.add("app.worker.enabled", () -> true);
    registry.add("app.worker.timeout", () -> "750ms");
    registry.add("app.worker.endpoint",
            () -> "http://127.0.0.1:50001");
}
~~~

Model:

~~~java
import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        int count,
        boolean enabled,
        Duration timeout,
        URI endpoint) {
}
~~~

Spring Boot's binder and conversion convert these into target types.

Keep in mind:

- String `750ms` parses into `Duration.ofMillis(750)`.
- A syntactically valid URI does not guarantee the endpoint is reachable or safe.
- A supplier returning an unconvertible value causes a binding/conversion failure.
- Missing keys can still become null/defaults depending on the model; dynamic properties are not automatically required.
- Business validation still requires `@Validated` and matching constraints/logic.

## 22. Dynamic Values Should Never Be Production Secrets

Passing a password for a PostgreSQL test container:

~~~java
registry.add("spring.datasource.password", postgres::getPassword);
~~~

is normal for isolated container tests. However, the registry does not encrypt or automatically secure secrets.

Practices to follow:

- Never log the entire `Environment` or properties objects holding credentials.
- Never pass production tokens into test fixtures just to make integration tests feel "realistic."
- Never publicly expose Actuator endpoints like `/actuator/env` or `/actuator/configprops`.
- Never embed passwords in assertion failure messages or logs.
- Avoid suppliers that fetch values from external accounts outside test scope.
- Use dedicated, least-privilege test credentials and dummy data.

High precedence is not a security control; a dynamic source is simply a property supplier.

## 23. One Method Registering Multiple Dynamic Properties

You can register multiple keys in the same method:

~~~java
@DynamicPropertySource
static void allResources(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);

    registry.add("spring.data.redis.host", redis::getHost);
    registry.add("spring.data.redis.port",
            () -> redis.getMappedPort(6379));

    registry.add("app.partner.base-url", mockServer::baseUrl);
}
~~~

You do not need a separate method per key.

However, if a test only exercises a repository, it may only need PostgreSQL; starting Redis and an HTTP mock server brings zero benefit when unused. The more resources you attach, the slower and more fragile tests become due to unrelated dependencies.

Tailor setup to each test group's purpose. When sharing fixtures, define lifecycles and data isolation before optimizing context caching.

## 24. When Should You Avoid `@DynamicPropertySource`?

Do not use it just to pass any arbitrary setting.

| Scenario | Simpler / better option |
| --- | --- |
| Toggling a fixed feature flag | `@TestPropertySource` or `@SpringBootTest(properties=...)` |
| Plain unit test without Spring context | Pass parameters directly or mock dependencies |
| Selecting a test profile | `@ActiveProfiles("test")` |
| Embedded app web server on random port | `@SpringBootTest(webEnvironment=RANDOM_PORT)` + `@LocalServerPort` |
| ConnectionDetails from Boot-supported Testcontainers | Consider `@ServiceConnection` |
| Dynamic value from a context bean (Framework 6.2+) | `DynamicPropertyRegistrar` |
| Updating configuration in running production | Proper externalized config / production refresh mechanism |
| Test wanting a different random value on every read | Redesign fixture; dynamic sources must not emit unstable endpoints |

For integration tests with dynamic resources, `@DynamicPropertySource` is natural. For short unit tests, it only adds complexity.

## 25. Common Errors and Fixes

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Method never invoked by Spring | Test does not run with Spring TestContext or lacks annotation | Use `@SpringBootTest`/`@SpringJUnitConfig` and proper annotation |
| Method signature error | Not `static` or wrong parameter count/type | Use `static void method(DynamicPropertyRegistry registry)` |
| Compile error on `registry.add` | Passed a raw value directly | Wrap in `() -> value` or a method reference |
| Mapped port getter fails | Container not started yet | Manage container lifecycle before resolution |
| Bean still uses production datasource | Misspelled dynamic key or context uses another config | Check `spring.datasource.*` and wiring |
| DataSource URL right, auth fails | Missing dynamic username/password | Supply the complete container credential set |
| Test B context hits stopped container A | Context caching and fixture lifetime mismatch | Align shared lifecycle or use `@DirtiesContext` |
| Environment changes, bean stays stale | Bean bound/injected only at creation | Create new context/bean or use intentional refresh |
| CI fails to start containers | No Docker-compatible runtime or missing permissions | Configure Testcontainers CI environment properly |
| `@TestPropertySource` value loses | Dynamic source has higher precedence | Register only the keys meant to override |
| Supplier returns different port each call | Randomness or side effects inside lookup | Fix endpoint when fixture starts |
| `@DynamicPropertySource` does nothing in plain JUnit | No Spring context | Remove annotation or enable Spring TestContext |
| `@ServiceConnection` does not populate custom URL key | No ConnectionDetails for that SDK | Use dynamic registry with the custom property |
| Nested/inherited tests see wrong values | Cache/lifecycle or inheritance rules | Check `@NestedTestConfiguration` and context reuse |
| Random failures under parallel runs | Mutable static fixture, container stopped early | Isolate resources and keep fixtures immutable |

Break diagnosis into clear steps:

1. Did the test resource start successfully?
2. Which resource is the Supplier reading from?
3. Does the Supplier return a valid, stable value?
4. Does the property name match what the bean/auto-configuration reads?
5. Is another key or ConnectionDetails controlling the connection?
6. Is the context being reused from an earlier test?
7. Are beans needing updated values recreated/rebound?

## 26. Exercise 1: Fix an Invalid Method

Given:

~~~java
@DynamicPropertySource
void configure(DynamicPropertyRegistry registry) {
    registry.add("app.client.port", 54321);
}
~~~

**Task:** fix it so Spring TestContext can invoke it.

**Answer:**

~~~java
@DynamicPropertySource
static void configure(DynamicPropertyRegistry registry) {
    registry.add("app.client.port", () -> 54321);
}
~~~

Two changes:

- Added `static`.
- Replaced the direct value with a `Supplier`.

## 27. Exercise 2: Dynamic Source Overriding Test YAML

YAML:

~~~yaml
# application-test.yml
app:
  catalog:
    port: 8080
~~~

Test:

~~~java
@DynamicPropertySource
static void properties(DynamicPropertyRegistry registry) {
    registry.add("app.catalog.port", () -> 55001);
}
~~~

**Question:** what does `Environment.getProperty("app.catalog.port", Integer.class)` normally return?

**Answer:** **55001**, because dynamic sources outrank regular static properties in the test context.

**Follow-up question:** if the dynamic source only registers `app.catalog.host`, is `app.catalog.port` removed?

**Answer:** No. `port` is not registered/overridden by the dynamic source, so it resolves from the remaining property sources.

## 28. Exercise 3: Testcontainers PostgreSQL

Suppose you have:

~~~java
static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");
~~~

**Task:** supply the dynamic properties for a Spring Boot datasource.

**Answer:**

~~~java
@DynamicPropertySource
static void database(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
~~~

Important: the container must be started/managed via proper lifecycle hooks before getters are invoked. Never hardcode `5432` as the host mapped port.

## 29. Exercise 4: Changing Values After Context Startup

Test has:

~~~java
static final AtomicReference<String> url =
        new AtomicReference<>("http://localhost:50001");

@DynamicPropertySource
static void properties(DynamicPropertyRegistry registry) {
    registry.add("app.client.url", url::get);
}
~~~

After context refresh:

~~~java
url.set("http://localhost:50002");
~~~

**Question:** will a bean field injected with `@Value("${app.client.url}")` automatically change to `50002`?

**Answer:** No. `Environment` can read the new value when queried, yet the already-injected field does not automatically rebind. Changing runtime behavior requires a different design (dynamic lookup, new context, bean recreation, or refresh).

## 30. Exercise 5: Choosing the Right Tool

| Need | Choice |
| --- | --- |
| Simply enable `app.feature.enabled=true` in a test | `@TestPropertySource` or `@SpringBootTest(properties=...)` |
| Redis container with a random mapped port | `@DynamicPropertySource` |
| PostgreSQL container using Boot auto-configuration with ServiceConnection | `@ServiceConnection` if version and dependencies fit |
| Java unit test without Spring | Pass dependencies/values directly |
| Dynamic value from a bean in the test context, Framework 6.2+ | `DynamicPropertyRegistrar` |
| Subclass uses a new container while context cache holds an old one | Fix lifecycle/context caching; consider `@DirtiesContext` |

## 31. Project Adoption Checklist

1. Method has `@DynamicPropertySource`, is `static`, returns `void`, and accepts a single registry parameter.
2. `registry.add(...)` receives the exact property key and a supplier, not a raw value.
3. Test executes through Spring TestContext.
4. Resource is started before suppliers are resolved.
5. Suppliers never start/stop resources, generate new random numbers, or cause side effects.
6. Ports/URLs come from real fixtures rather than being hardcoded.
7. For datasources, URL, username, and password are registered consistently together.
8. Precedence is understood: dynamic properties outrank static test settings.
9. Never assume changing a DynamicPropertySource refreshes existing singletons automatically.
10. Review TestContext caching when fixtures vary across test classes.
11. If using `@DirtiesContext`, account for context-recreation cost.
12. Avoid touching global JVM properties when configuring a single test context.
13. Never log credentials, tokens, or the full Environment.
14. When only static values are needed, use simpler static test property mechanisms.
15. Consider `@ServiceConnection` for Spring Boot-supported container services.
16. Use `DynamicPropertyRegistrar` when bean-based dynamic registration is genuinely needed and supported.
17. Ensure CI provides a compatible container runtime, timeouts, and resource isolation.
18. Write assertions confirming **beans or clients actually use** the dynamic endpoint, not just that the Supplier returns a String.

## 32. Key Takeaways

- **`@DynamicPropertySource`** is Spring TestContext's mechanism for feeding runtime values from integration-test fixtures into `Environment`.
- **The method must be `static`**, taking a single `DynamicPropertyRegistry`.
- **`registry.add(name, supplier)`** registers a value provider; the Supplier is invoked when the property is resolved.
- **Dynamic properties have high precedence**, outranking `@TestPropertySource`.
- **Testcontainers** is the classic use case because hosts, mapped ports, and JDBC URLs are only known at runtime.
- **Use exact property keys** read by Spring Boot auto-configuration or `@ConfigurationProperties`.
- **Coordinate lifecycles and the TestContext cache** so beans never point to stopped containers.
- **No automatic rebinding occurs** for already-injected beans if a Supplier's value changes after startup.
- **Spring Boot's `@ServiceConnection`** can replace manual datasource property registration in supported cases.
- **`DynamicPropertyRegistrar`** (Spring Framework 6.2+) registers dynamic properties from beans inside the test context.

### References

- Spring Framework — Dynamic Property Sources: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html
- Spring Framework Javadoc — DynamicPropertySource: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/DynamicPropertySource.html
- Spring Framework Javadoc — DynamicPropertyRegistry: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/DynamicPropertyRegistry.html
- Spring Framework — Context Caching: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html
- Spring Framework — Test Property Sources: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/property-sources.html
- Spring Boot — Testcontainers and Service Connections: https://docs.spring.io/spring-boot/reference/testing/testcontainers.html
- Testcontainers Java — JUnit Jupiter Extension: https://java.testcontainers.org/test_framework_integration/junit_5/
