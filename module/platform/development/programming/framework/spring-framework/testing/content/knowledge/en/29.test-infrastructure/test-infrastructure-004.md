# Registering Dynamic Addresses After Resources Are Ready

In Spring integration testing, an auxiliary resource often does not have a fixed address. A database running in a container may be mapped to a random port on the host machine; an HTTP stub server may choose an ephemeral port at startup; a test service may only know its hostname and port after the runtime finishes creating the resource.

The Spring application still needs that address to configure a `DataSource`, `RestClient`, `RestTemplate`, or other client. If you hardcode the address in `application-test.properties`, tests become coupled to a specific port or environment and easily collide during parallel runs.

Spring Test provides `@DynamicPropertySource` and `DynamicPropertyRegistry` to register properties whose values are obtained from running resources. Combined with lazily evaluated suppliers, this mechanism ensures Spring receives the right dynamic address when properties are read, provided the resource has started and is ready at that time.

## 1. Why Do Test Addresses Need Dynamic Registration?

Suppose a test needs to call an auxiliary HTTP service. If the server always uses port 8080, multiple tests or processes can contend for the same port. If the server picks a random port, the address is only known after the server starts.

Example:

~~~text
Before startup:
  host = unknown
  port = unknown

After startup:
  host = 127.0.0.1
  port = 49173
  base URL = http://127.0.0.1:49173
~~~

A client in Spring might require the property:

~~~properties
partner.base-url=http://127.0.0.1:49173
~~~

Do not pre-select a port and hope it is still free when the server binds. Let the resource pick an actual endpoint, wait for the resource to become ready, and then supply that address to Spring.

Common scenarios:

- Testcontainers assigns a dynamic host port for a port inside a container.
- WireMock or MockWebServer runs on a random port.
- An embedded server starts with port 0.
- A test fixture starts an auxiliary service and publishes its address after binding a socket.
- A cloud resource or test environment provisions an endpoint at creation time.

## 2. The Right Lifecycle: Start, Wait for Readiness, Then Use the Address

Registering a property only provides a value to Spring. It does not automatically start a database, container, or HTTP server. The test must coordinate resource lifecycles explicitly:

~~~text
Create test resource
       |
       v
Start resource
       |
       v
Wait for readiness / health check to succeed
       |
       v
Read actual host and port
       |
       v
Register dynamic property for Spring
       |
       v
ApplicationContext creates client / DataSource
       |
       v
Run test
       |
       v
Close ApplicationContext and resource
~~~

Points to distinguish:

- **Port assigned** means the runtime has selected or mapped a port.
- **Resource ready** means the service has started and can handle the kind of requests the test needs.
- **Property registered** means Spring can look up a configuration value.
- **Client initialized** means the application has read the property and may hold that address in its configuration.

A port being assigned does not guarantee the service is ready. For instance, a container may be running while the database is still initializing its schema or not yet accepting connections. Use your resource management tool's readiness check before letting tests use the endpoint.

## 3. @DynamicPropertySource and DynamicPropertyRegistry

`@DynamicPropertySource` is a Spring Test annotation introduced in Spring Framework 5.2.5. It marks a static method used to register dynamic properties into the `Environment` of the test `ApplicationContext`.

The annotated method must accept a single parameter of type `DynamicPropertyRegistry`:

~~~java
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

@DynamicPropertySource
static void registerProperties(DynamicPropertyRegistry registry) {
    registry.add("partner.base-url", () -> "http://localhost:49173");
}
~~~

Core API:

~~~java
registry.add("property.name", supplier);
~~~

Where:

- `property.name` is the name of the property the application will read.
- `supplier` is a `Supplier<?>` providing the value when the property is resolved.

Multiple properties can be registered in the same method:

~~~java
@DynamicPropertySource
static void registerProperties(DynamicPropertyRegistry registry) {
    registry.add("partner.base-url", partnerServer::baseUrl);
    registry.add("partner.api-key", () -> "test-api-key");
    registry.add("feature.remote-check", () -> true);
}
~~~

The supplier is evaluated lazily when the property value is accessed. Thus, you can pass a method reference or lambda so host/port values are read only when Spring actually needs the property:

~~~java
registry.add("partner.base-url", partnerServer::baseUrl);
~~~

Do not invoke the address getter outside the supplier if the resource is not ready yet:

~~~java
// Avoid: the method is called eagerly when registering the property.
String baseUrl = partnerServer.baseUrl();
registry.add("partner.base-url", () -> baseUrl);
~~~

If `baseUrl()` only returns a valid value after the server starts, the snippet above can read it too early. Use a method reference or lambda that invokes the method after the resource has started:

~~~java
registry.add("partner.base-url", partnerServer::baseUrl);
~~~

The supplier is not a callback for starting the resource. It only supplies a value. Starting and readiness checks must still be managed separately.

### Dynamic Properties Have High Precedence

Properties registered via `@DynamicPropertySource` have higher precedence than standard property sources such as `@TestPropertySource`, system properties, environment variables, and property sources added via `@PropertySource` or standard context configuration.

This allows test resource endpoints to override default settings in properties files. However, use specific property names and override only the values needed for testing to avoid confusing configuration.

## 4. Example with WireMock Using a Random Port

WireMock can start on a dynamic port. After calling `start()`, `baseUrl()` returns the server's actual address.

The following example demonstrates starting the resource before Spring creates the `ApplicationContext`, then registering that address with `@DynamicPropertySource`:

~~~java
import static com.github.tomakehurst.wiremock.client.WireMock.aResponse;
import static com.github.tomakehurst.wiremock.client.WireMock.get;
import static com.github.tomakehurst.wiremock.client.WireMock.urlEqualTo;
import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.options;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import com.github.tomakehurst.wiremock.WireMockServer;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class PartnerClientIntegrationTests {

    private static final WireMockServer partnerServer =
        new WireMockServer(options().dynamicPort());

    static {
        partnerServer.start();
    }

    @DynamicPropertySource
    static void partnerProperties(DynamicPropertyRegistry registry) {
        registry.add("partner.base-url", partnerServer::baseUrl);
    }

    @Autowired
    PartnerClient partnerClient;

    @Test
    void callsPartnerAtItsAssignedAddress() {
        partnerServer.stubFor(get(urlEqualTo("/status"))
            .willReturn(aResponse()
                .withStatus(200)
                .withHeader("Content-Type", "text/plain")
                .withBody("UP")));

        assertThat(partnerClient.status()).isEqualTo("UP");
    }

    @AfterAll
    static void stopPartnerServer() {
        partnerServer.stop();
    }
}
~~~

In this example:

1. The static initializer starts the WireMock server and lets the OS assign a free port.
2. `@DynamicPropertySource` registers a supplier returning `partnerServer.baseUrl()`.
3. Spring reads `partner.base-url` when creating `PartnerClient`.
4. The test configures a stubbed response and calls the client.
5. After the class's tests complete, the server is stopped.

Starting in a static initializer is a simple way to ensure the resource is started before Spring needs to create the context. In projects with a dedicated lifecycle extension, that extension can manage start/stop as long as ordering guarantees the resource is ready before properties are first read.

An illustrative client:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
class PartnerClient {

    private final RestClient restClient;

    PartnerClient(@Value("${partner.base-url}") String baseUrl) {
        this.restClient = RestClient.builder()
            .baseUrl(baseUrl)
            .build();
    }

    String status() {
        return restClient.get()
            .uri("/status")
            .retrieve()
            .body(String.class);
    }
}
~~~

The example uses `RestClient`, available since Spring Framework 6.1. For applications using `RestTemplate`, `WebClient`, or another client, the property registration principle remains the same.

## 5. Example with Testcontainers and Dynamically Mapped Ports

Containers declare ports inside the image, but Testcontainers can map those ports to random ports on the host. Never assume the host port equals the container port.

PostgreSQL example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class OrderRepositoryIntegrationTests {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Test
    void applicationCanUseDatabase() {
        // Test repository or service.
    }
}
~~~

Testcontainers manages the static container lifecycle through the JUnit Jupiter extension. The container is started before tests run, and the suppliers retrieve the JDBC URL, username, and password from that container.

`getJdbcUrl()` contains the actual host and mapped port. Do not construct `localhost:5432` manually, because container port 5432 may be mapped to a different port on the test machine.

For containers providing HTTP services, obtaining the endpoint follows the same principle:

~~~java
registry.add("partner.base-url", () ->
    "http://" + service.getHost() + ":" + service.getMappedPort(8080)
);
~~~

In this example, `8080` is the exposed port inside the container. `getMappedPort(8080)` returns the host-side port after the container starts. The supplier should only be called after the container has started.

### Waiting for Container Readiness

Testcontainers provides startup checks and wait strategies. For an HTTP service, you can configure waiting on an HTTP health endpoint:

~~~java
static final GenericContainer<?> partner =
    new GenericContainer<>(DockerImageName.parse("example/partner:1.0"))
        .withExposedPorts(8080)
        .waitingFor(
            Wait.forHttp("/health")
                .forPort(8080)
                .forStatusCode(200)
        );
~~~

When using a wait strategy, `start()` only completes after the wait condition succeeds or a startup timeout occurs. This prevents Spring from creating a client with an endpoint whose port exists while the service cannot yet accept requests.

Common wait types:

| Wait strategy | When to use |
|---|---|
| `Wait.forListeningPort()` | Only need to confirm the port starts listening. |
| `Wait.forHttp(path)` | Need an HTTP health endpoint returning an expected status. |
| `Wait.forLogMessage(regex, count)` | Resource emits a log message indicating readiness. |
| `Wait.forHealthcheck()` | Image defines a health check reported as healthy by the container runtime. |

Choose a readiness condition that reflects the capability the test actually requires. A listening port may not mean the database is accepting queries or the HTTP API is ready to process business requests.

## 6. Do Not Read Host/Port Too Early

Many APIs only return an endpoint after the resource is started:

| API | When it can be read |
|---|---|
| `WireMockServer.baseUrl()` | After WireMock starts. |
| `GenericContainer.getHost()` | After container starts. |
| `GenericContainer.getMappedPort(port)` | After container starts and ports are mapped. |
| `PostgreSQLContainer.getJdbcUrl()` | After container starts. |
| `WebServer.getPort()` with port 0 | After embedded server binds an actual port. |

This is why suppliers matter:

~~~java
registry.add("partner.base-url", () ->
    "http://" + container.getHost() + ":" + container.getMappedPort(8080)
);
~~~

Do not compute the address at field declaration time if the resource has not started yet:

~~~java
// May fail if the container has not been started yet.
static final String PARTNER_URL =
    "http://" + container.getHost() + ":" + container.getMappedPort(8080);
~~~

Keep endpoint lookups inside the supplier, or compute values only after an explicit start/readiness step.

Spring may invoke the supplier whenever the property is accessed; do not assume it is called only once. The supplier should return the same valid address throughout the `ApplicationContext` lifetime and should not perform side effects such as starting or stopping containers.

## 7. When Are Properties Read?

`@DynamicPropertySource` is used by Spring Test while preparing the `ApplicationContext`. The dynamic property source is added to the `Environment`, and beans can then read properties during configuration binding or initialization.

Example:

~~~java
@ConfigurationProperties(prefix = "partner")
public record PartnerProperties(URI baseUrl) {}
~~~

Spring binds the property:

~~~properties
partner.base-url=http://...
~~~

Or a bean reads it directly:

~~~java
PartnerClient(@Value("${partner.base-url}") String baseUrl) {
    // Build client from baseUrl.
}
~~~

Once the bean is created and the client has stored the base URL, changing the supplier's return value later does not automatically reconfigure the existing client. Therefore, the endpoint must remain stable throughout the context lifecycle. If a resource restarts and receives a new port, you generally need to recreate the corresponding context/client or use an intentional configuration refresh mechanism.

### Precedence Does Not Replace Lifecycle

Dynamic properties can override static properties, but precedence does not make a resource ready on its own. If a supplier is called before a container starts, `getMappedPort()` can still throw an exception. Start and readiness ordering must be solved independently of property precedence.

## 8. Managing Resources with JUnit and Spring Test

Auxiliary resources and the `ApplicationContext` have separate lifecycles. Ensure that:

- The resource starts before Spring reads the endpoint.
- The resource is not stopped while tests or beans still need to call it.
- Tests do not accidentally share a mutable resource across multiple classes running in parallel.
- The resource is stopped even if tests fail.

### Static Resources Shared Within a Single Test Class

With WireMock or an in-JVM Java server, you can use a static field and `@AfterAll` as in the earlier example. If starting the resource in a static initializer, ensure startup finishes before the Spring extension prepares the context.

### Using JUnit Extensions

If the resource management library provides a JUnit extension, prefer the official extension for consistent lifecycles. Example with Testcontainers:

~~~java
@Testcontainers
class DatabaseTests {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");
}
~~~

A static container is shared across test methods in the class. An instance container can be started and stopped per test method. Choose scope based on startup cost and required isolation level.

### Do Not Stop Resources Too Early

If the `ApplicationContext` is cached and reused across multiple test classes, a static resource belonging to only one class may stop while the context still holds beans pointing to the old address. This causes confusing failures in later tests.

Ways to handle this:

- Place the resource at a scope that outlives every context using it.
- Use a shared base test class to manage the resource and context configuration.
- Separate contexts if classes require resources with different lifecycles or endpoints.
- Close the context before stopping the resource if the test fixture manages both lifecycles directly.

## 9. Inheriting @DynamicPropertySource and the Context Cache

A `@DynamicPropertySource` method can be declared in a superclass and inherited by test subclasses. This is useful when multiple integration tests share the same database or test service.

Example:

~~~java
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

@SpringBootTest
class OrderRepositoryTests extends AbstractDatabaseIntegrationTest {
    // Repository tests.
}

@SpringBootTest
class CustomerRepositoryTests extends AbstractDatabaseIntegrationTest {
    // Repository tests.
}
~~~

When subclasses share the same resource and configuration, inheritance avoids duplicating property registration.

However, Spring Test caches the `ApplicationContext` for reuse across tests with equivalent configurations. If subclasses inherit the same method while the underlying resource or effective dynamic property values change between classes, a cached context may retain the old configuration. In that case, consider `@DirtiesContext` on the superclass or separating configurations/contexts so each resource has an appropriate context.

Do not apply `@DirtiesContext` mechanically. If the resource is static and endpoints remain unchanged across the context's lifetime, context caching is usually beneficial for test execution time.

## 10. Registering Multiple Dynamic Addresses

A single test may depend on multiple resources:

- Database.
- Message broker.
- HTTP stub server.
- Cache.

Register all properties in the same method:

~~~java
@DynamicPropertySource
static void registerInfrastructure(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);

    registry.add("partner.base-url", partnerServer::baseUrl);

    registry.add("cache.host", redis::getHost);
    registry.add("cache.port", () -> redis.getMappedPort(6379));
}
~~~

Each supplier must pull values from the right resource. Avoid reusing one host or port across multiple services simply because they happen to run on the same local machine.

If one resource depends on another, start them in dependency order. For example, the application needs the database before schema initialization; if an HTTP stub does not depend on the database, it can start in parallel, but all must be ready before their corresponding beans begin using them.

## 11. Registering Dynamic Properties via ApplicationContextInitializer

Before `@DynamicPropertySource` existed, a common approach was `ApplicationContextInitializer`. This remains useful in some special setups or older codebases:

~~~java
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.test.context.support.TestPropertyValues;

class PartnerContextInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        String baseUrl = PartnerTestResource.baseUrl();
        TestPropertyValues.of(
            "partner.base-url=" + baseUrl
        ).applyTo(context.getEnvironment());
    }
}
~~~

Register the initializer on the test:

~~~java
@SpringBootTest
@ContextConfiguration(initializers = PartnerContextInitializer.class)
class PartnerIntegrationTests {
}
~~~

The initializer runs while preparing the context. The resource must be started and ready before the initializer reads the address. Unlike `DynamicPropertyRegistry`, the example above constructs the property string immediately inside the initializer.

With Spring Framework 5.2.5 and later, `@DynamicPropertySource` is usually more concise and clearly expresses registering dynamic values with suppliers. There is no need to switch to an initializer if the annotation fits the test lifecycle.

## 12. Spring Boot @ServiceConnection and When to Use It

With Spring Boot 3.1 and later, `@ServiceConnection` can automatically generate connection details for common Testcontainers such as PostgreSQL, Redis, Kafka, and other supported services.

Example:

~~~java
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class DatabaseIntegrationTests {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");
}
~~~

Spring Boot recognizes the container type and creates connection details for the matching auto-configuration. In standard supported cases, you do not need to manually register `spring.datasource.url`, username, and password.

Choose `@ServiceConnection` when:

- Using Spring Boot.
- The container type is supported by Spring Boot.
- You want Boot to auto-configure connections by service type.

Choose `@DynamicPropertySource` when:

- Using Spring Framework Test directly or preferring not to depend on Boot-specific mechanisms.
- The resource is WireMock, MockWebServer, or a custom service.
- The application requires a custom property such as `partner.base-url`.
- Registering values that lack a corresponding connection details auto-configuration.

Both mechanisms can coexist in a test suite, though you should avoid registering two competing sources for the same connection configuration without a clear reason.

## 13. When the Application Itself Runs on a Random Port

If the Spring Boot application itself is the resource under test, the embedded server can be started on a random port:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ApplicationHttpIntegrationTests {

    @LocalServerPort
    int port;

    @Test
    void respondsOnAssignedPort() {
        // Use the injected port to call the running server.
    }
}
~~~

In this case, `@LocalServerPort` is the appropriate way to obtain the embedded server's port after the server starts. Do not attempt to read that port in `@DynamicPropertySource` of the same context, because dynamic property sources are processed during context preparation before that context's embedded server finishes starting.

If another service bean inside the application needs to know the embedded server's own address, review the lifecycle and configuration design separately. Avoid creating a circular dependency where the context needs a property to start the server while the property is only available after the server starts.

## 14. Common Mistakes

### Reading getMappedPort Before the Container Starts

Testcontainers only knows port mappings after the container has started. Put the call inside a supplier or read it after the start step.

### Thinking Property Registration Starts the Resource Automatically

`registry.add` only registers a supplier. The test still must start the container/server and wait for readiness.

### Checking Only That the Port Is Open

A listening port does not guarantee the service is ready for business traffic. Use an appropriate health check or wait strategy.

### Using Fixed Ports

Fixed ports can collide across processes or CI machines. Prefer dynamic ports and read the address provided by the resource.

### Eagerly Evaluating the Supplier

Calling `getMappedPort()` or `baseUrl()` before startup can fail. Use a lambda or method reference to evaluate the value when the property is accessed.

### Stopping the Resource Before the Context Finishes

Beans may retain the old endpoint and keep calling a stopped resource. Synchronize the resource lifecycle with the context using it.

### Reusing a Context While Changing Endpoints

The context cache may reuse beans configured with the old endpoint. If endpoints change across test classes, consider separating contexts or using `@DirtiesContext`.

### Confusing Container Port with Host Port

`getMappedPort(8080)` returns the host-side port mapped from port 8080 inside the container. Clients running outside the container usually need the host and mapped port, not `localhost:8080`.

### Registering the Wrong Property Name

The property must match the exact name read by `@Value`, `@ConfigurationProperties`, or auto-configuration. Verify prefixes and property name structure.

### Using @DynamicPropertySource for the Embedded Server's Own Port

Property sources are processed while preparing the context, before the embedded server has its final port. Use `@LocalServerPort` after server startup or an appropriate lifecycle hook.

## 15. Implementation Checklist in Tests

When a test needs the address of a dynamic resource, follow these steps in order:

1. Identify what manages the resource: JUnit extension, Testcontainers, WireMock, or a custom fixture.
2. Choose a dynamic port or let the runtime assign a mapping; avoid hardcoded ports.
3. Start the resource before Spring needs to configure clients.
4. Wait for readiness using a health check, wait strategy, or startup completion signal.
5. Register properties via `@DynamicPropertySource` and `DynamicPropertyRegistry`.
6. Place host/port lookup calls inside suppliers if the address is only available after startup.
7. Let Spring create the `ApplicationContext` and bind properties into beans.
8. Keep the resource alive for the entire time the context and tests need to use it.
9. Close the context and resource according to an explicit lifecycle.
10. If endpoints change across classes while the context is cached, consider separating contexts or using `@DirtiesContext`.

Dynamic address registration works effectively when properties are read at the right time and resources have clear lifecycles. `@DynamicPropertySource` bridges runtime-assigned endpoints into Spring's `Environment`; suppliers defer value retrieval, while startup and readiness steps ensure that address is genuinely usable when the application initializes.
