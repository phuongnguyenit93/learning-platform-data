# @DynamicPropertySource for Dynamically Created Ports, URLs, and Resources in Spring Boot Tests

## 1. Why are dynamic properties needed in test environments?

In a Spring Boot integration test, the application needs the address of a database, HTTP mock server, message broker, or supporting service. These resources are often created **at test runtime**, with ports and URLs unknown ahead of time:

- Testcontainers maps PostgreSQL port `5432` inside a container to a **random port on the test host**.
- An HTTP stub server listens on port `0` so the operating system assigns an available port.
- A broker uses a hostname, port, or certificate only available after the resource starts.
- Tests running in parallel need distinct endpoints to avoid fixed-port collisions.

Hard-coding `localhost:5432`, `localhost:8080`, or a developer's local URL in `application-test.yml` can make tests pass on one machine yet fail on CI or accidentally hit an already-running service. **`@DynamicPropertySource`** lets a test **register properties computed from live resources** into the Spring TestContext `Environment` before dependent beans are created.

The goal is for the code under test to keep reading keys such as `spring.datasource.url`, `partner.base-url`, or `messaging.bootstrap-servers` normally, while the **test owns the value source** and manages resource lifecycles.

**Principle:** create or prepare the test resource → register property names and value suppliers → Spring initializes the context → beans read properties → test runs assertions. Do not confuse registering a `Supplier` with actually starting the resource.

## 2. What is @DynamicPropertySource?

`@DynamicPropertySource` belongs to the Spring TestContext Framework, in package:

```java
org.springframework.test.context.DynamicPropertySource
```

A method marked with this annotation must normally be **`static`**, accept **one `DynamicPropertyRegistry` parameter**, and return `void`:

```java
@DynamicPropertySource
static void registerProperties(DynamicPropertyRegistry registry) {
    registry.add("partner.base-url", () -> dynamicBaseUrl());
}
```

This snippet illustrates syntax: `dynamicBaseUrl()` must be defined in the test class; it is not a standalone Java program. The key API is:

```java
registry.add("property.name", supplierOfValue);
```

- **Property name** is the key actually read by beans/application, such as `spring.datasource.url` or `demo.ping.base-url`.
- **`Supplier<?>`** supplies the value when the property needs to be resolved. You do not have to pre-build the property string before registration time.
- Spring attaches dynamic properties to the test context's `Environment`, so `@Value`, `Environment.getProperty(...)`, and property binding mechanisms can read them.
- Dynamic properties have high precedence in Spring TestContext, typically **overriding matching keys** from `@TestPropertySource`, environment variables, system properties, and loaded application property sources.
- Methods can be inherited across a test context hierarchy, though differing resources across subclasses require care because of context caching.

**Limitations:** `@DynamicPropertySource` does not install a JUnit extension, does not create a database/broker, does not expose ports, does not connect to Docker, and does not turn a minimal `@ContextConfiguration` into a full Boot application. It only supplies dynamic values into the test environment.

## 3. Understanding the lifecycle: register early, resolve when needed

For an integration test, the conceptual order is usually:

```text
Test class and test resources are prepared
      │
      ├─ PostgreSQL container / HTTP stub / broker is ready
      │      (may be coordinated by a JUnit extension or test code)
      │
      ├─ Spring TestContext detects @DynamicPropertySource method
      │      registry.add("...", Supplier)
      │
      ├─ ApplicationContext begins refreshing
      │      bean requests property → Environment invokes Supplier
      │
      ├─ Bean receives the appropriate URL / host / port
      │
      └─ @Test executes with the injected configuration
```

**Subtle detail:** `registry.add` registers a **supplier**, not an immediate call to `getMappedPort` if you pass a method reference or lambda. Under the dynamic properties mechanism, the supplier is evaluated when the property is resolved; a property may be read multiple times. Therefore:

- **Resource initialization must follow the right order**: by the time Spring reads the property, the server/container must be running or have reliable port information.
- **The supplier should return a stable value** for the lifetime of the context. Do not start a new server, allocate a new port, or reset state on every `get()` call.
- **Do not read mapped ports before the container starts**. With Testcontainers, calling `getMappedPort` too early can fail because the port is not mapped yet.
- **Never build URLs by guessing ports** or taking only the container's internal port. The URL must use the host and port **reachable from the test JVM**.

Conceptually sound example with a lifecycle-managed container:

```java
registry.add("spring.datasource.url", postgres::getJdbcUrl);
registry.add("spring.datasource.username", postgres::getUsername);
registry.add("spring.datasource.password", postgres::getPassword);
```

This is an **illustrative snippet inside a test with a `postgres` `PostgreSQLContainer` field**, not a standalone file. Method references defer fetching the URL and connection details until Spring actually needs the properties.

## 4. Runnable Java 17+ example: random-port HTTP server

This example needs no Docker, database, or external network. A local HTTP server using only JDK 17 binds to **port `0`**, letting the OS allocate a free port. The test registers `demo.ping.base-url` via `@DynamicPropertySource`. Spring creates a client bean reading that URL; the test sends a real HTTP request to the local server and verifies the response.

You need a project with Java 17+, Spring TestContext, and JUnit Jupiter. In a Spring Boot project, `spring-boot-starter-test` normally provides the required test libraries. The example intentionally uses `@ContextConfiguration` instead of loading full Boot just to prove **dynamic property → bean wiring → HTTP call**.

### 4.1. Real client reading base URL via constructor

File `src/main/java/com/example/testing/PingClient.java`:

```java
package com.example.testing;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Objects;

public final class PingClient {

    private final URI baseUri;
    private final HttpClient httpClient;

    public PingClient(URI baseUri, Duration connectTimeout) {
        this.baseUri = Objects.requireNonNull(baseUri, "baseUri");
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(connectTimeout)
                .build();
    }

    public URI baseUri() {
        return baseUri;
    }

    public String ping() {
        HttpRequest request = HttpRequest.newBuilder(
                        baseUri.resolve("/ping"))
                .timeout(Duration.ofSeconds(3))
                .GET()
                .build();

        try {
            HttpResponse<String> response = httpClient.send(
                    request,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));

            if (response.statusCode() != 200) {
                throw new IllegalStateException(
                        "Unexpected HTTP status: " +
                        response.statusCode());
            }

            return response.body();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Ping interrupted", e);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }
}
```

This is a plain Java class. `PingClient` has no idea which port the test runs on; it simply accepts a `URI` at construction time. Both `HttpClient` and `HttpServer` are included in JDK 17, so the example needs no external HTTP mocking library. Spring enters the picture by injecting the dynamic URL into the constructor through a bean configuration.

### 4.2. Test creating the server, registering the URL, and verifying the bean receives the right address

File `src/test/java/com/example/testing/PingClientDynamicPropertyTest.java`:

```java
package com.example.testing;

import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.io.UncheckedIOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.junit.jupiter.SpringExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@ExtendWith(SpringExtension.class)
@ContextConfiguration(
        classes = PingClientDynamicPropertyTest.TestConfig.class)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class PingClientDynamicPropertyTest {

    private static final HttpServer SERVER = startServer();

    @Configuration(proxyBeanMethods = false)
    static class TestConfig {

        @Bean
        PingClient pingClient(
                @Value("${demo.ping.base-url}") String baseUrl,
                @Value("${demo.ping.connect-timeout-ms}") long timeoutMs) {
            return new PingClient(
                    URI.create(baseUrl),
                    Duration.ofMillis(timeoutMs));
        }
    }

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("demo.ping.base-url",
                () -> "http://127.0.0.1:" +
                        SERVER.getAddress().getPort());
        registry.add("demo.ping.connect-timeout-ms",
                () -> "1000");
    }

    @Autowired
    private PingClient client;

    @Autowired
    private Environment environment;

    @Test
    void injectsDynamicallyAssignedPortAndReachesServer() {
        int port = SERVER.getAddress().getPort();

        assertTrue(port > 0);
        assertEquals(
                "http://127.0.0.1:" + port,
                client.baseUri().toString());
        assertEquals(
                client.baseUri().toString(),
                environment.getProperty("demo.ping.base-url"));
        assertEquals("pong", client.ping());
    }

    @AfterAll
    static void stopServer() {
        SERVER.stop(0);
    }

    private static HttpServer startServer() {
        try {
            HttpServer server = HttpServer.create(
                    new InetSocketAddress("127.0.0.1", 0),
                    0);

            server.createContext("/ping", exchange -> {
                byte[] body = "pong".getBytes(StandardCharsets.UTF_8);
                try {
                    exchange.getResponseHeaders().set(
                            "Content-Type",
                            "text/plain; charset=utf-8");
                    exchange.sendResponseHeaders(200, body.length);
                    try (OutputStream output =
                                 exchange.getResponseBody()) {
                        output.write(body);
                    }
                } finally {
                    exchange.close();
                }
            });

            server.start();
            return server;
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }
}
```

### 4.3. What is happening?

1. The `SERVER` field creates an `HttpServer` with `new InetSocketAddress("127.0.0.1", 0)`. Port `0` tells **the operating system to pick an available port**; once bound, `SERVER.getAddress().getPort()` returns the assigned port.
2. `startServer()` registers the `/ping` route returning text `pong` over HTTP and starts the server **before the client bean needs the URL**.
3. The `properties(DynamicPropertyRegistry)` method is `static`; it registers one supplier for `demo.ping.base-url` and one for timeout. The URL is derived from the **actually allocated port**, not `8080` or `0`.
4. `TestConfig` is a minimal Spring configuration; `@Value` parameters pull properties from the context and pass them to the client constructor. No broad component scan, Spring Boot server, database, or broker is involved.
5. `@Autowired` injects `PingClient` and the test context's `Environment` into the test class.
6. The test verifies the port is greater than `0`, the client's URL matches the dynamic property URL, and `client.ping()` receives `"pong"` accurately.
7. `@AfterAll` shuts down the server when the test class finishes. `@DirtiesContext(AFTER_CLASS)` evicts this context from the cache at class end, preventing a cached client from holding a URL pointing to a stopped server.

On each run, the port number may differ. **There is no fixed stdout showing a port number**: what is asserted is the proper relationship among the real port, dynamic property, and client address. A passing test means HTTP communication with the local stub succeeded and URL injection works under the declared configuration; it **does not prove** an external service or a full Spring Boot context works properly.

### 4.4. Running the test

With Gradle wrapper (Linux/macOS):

```bash
./gradlew test --tests "com.example.testing.PingClientDynamicPropertyTest"
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.testing.PingClientDynamicPropertyTest"
```

With Maven wrapper (Linux/macOS):

```bash
./mvnw -Dtest=PingClientDynamicPropertyTest test
```

Windows PowerShell:

```powershell
.\mvnw.cmd -Dtest=PingClientDynamicPropertyTest test
```

These commands assume wrappers and a JUnit Jupiter-capable runner are present; Gradle usually needs `useJUnitPlatform()` on the `test` task. The JDK must provide module `jdk.httpserver`, which is included in JDK 17. If the build uses `module-info.java` with the Java Platform Module System, you may need `requires jdk.httpserver;` in the appropriate module configuration. In standard classpath-based Spring Boot projects, the files above suffice once test dependencies are configured.

After running, check the results for this class in `build/reports/tests/test/index.html` (Gradle `test` task) or `target/surefire-reports/` (Maven Surefire). Do not treat a green build where tests were skipped or cached as proof of fresh test execution.

## 5. Real-world scenario: Testcontainers providing a dynamic JDBC URL

A very common pattern is a Spring Boot integration test starting PostgreSQL via Testcontainers, then pushing three properties into datasource configuration:

```java
@DynamicPropertySource
static void postgresProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url",
            postgres::getJdbcUrl);
    registry.add("spring.datasource.username",
            postgres::getUsername);
    registry.add("spring.datasource.password",
            postgres::getPassword);
}
```

Note: `getJdbcUrl()` normally includes the hostname and host-mapped port assigned **after the container starts**. Registering method references defers access instead of reading the port prematurely. Do not use `jdbc:postgresql://localhost:5432/...` unless you intentionally configured Testcontainers to bind a fixed port for a specific testing reason.

### 5.1. An illustrative integration test class

The example below uses `org.testcontainers.containers.PostgreSQLContainer` and Testcontainers JUnit Jupiter APIs typical of Testcontainers 1.x; **artifact coordinates/packages can change across major versions**, so choose a Testcontainers and JDBC driver version compatible with your project. This test requires an available Docker/container runtime, the PostgreSQL driver, Spring JDBC auto-configuration (such as `spring-boot-starter-jdbc`), and the corresponding Testcontainers libraries.

File `src/test/java/com/example/testing/PostgresDynamicPropertiesTest.java`:

```java
package com.example.testing;

import java.sql.Connection;
import java.sql.SQLException;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
@SpringBootTest(
        classes = PostgresDynamicPropertiesTest.TestBootConfig.class)
class PostgresDynamicPropertiesTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestBootConfig {
    }

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("catalog_test")
                    .withUsername("test")
                    .withPassword("test");

    @DynamicPropertySource
    static void dataSourceProperties(
            DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url",
                postgres::getJdbcUrl);
        registry.add("spring.datasource.username",
                postgres::getUsername);
        registry.add("spring.datasource.password",
                postgres::getPassword);
    }

    @Autowired
    private DataSource dataSource;

    @Test
    void canOpenConnectionToDynamicPostgres() throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            assertTrue(connection.isValid(2));
        }
    }
}
```

The test above is a complete integration test verifying **creation of a `DataSource` and opening a JDBC connection** to PostgreSQL started in an appropriate Testcontainers environment. It does not yet test entity mappings, migrations, SQL queries, or rollback/commit; add dedicated data tests to verify those. If Docker is unavailable or dependencies are missing, the test may fail during setup before reaching assertions.

In Spring Boot versions supporting newer Testcontainers integrations—such as Spring Boot's `@ServiceConnection`—supported service containers can be wired automatically into auto-configuration without manually registering every property. **`@DynamicPropertySource` remains valuable for custom keys, HTTP stubs, and unrecognized resources.** Avoid using both mechanisms to configure the same connection without understanding their precedence.

## 6. Host, container port, and mapped port: do not confuse them

With Testcontainers, at least three concepts must be kept distinct:

| Concept | Example | Meaning |
|---|---|---|
| **Container port** | PostgreSQL listens on `5432` inside the container | Only the port inside the container's network namespace |
| **Mapped host port** | Docker maps to `32785` on the host in a hypothetical run | Port reachable by the test JVM process from the appropriate host |
| **Container host/address** | Value from `container.getHost()` | Host address appropriate to the Docker/Testcontainers setup; not always hardcoded `localhost` |

If you must construct a URL manually for a `GenericContainer`, the conceptual form is:

```java
registry.add("demo.service.url", () ->
        "http://" + serviceContainer.getHost()
        + ":" + serviceContainer.getMappedPort(8080));
```

This is an **illustrative snippet**: `serviceContainer` must be declared and started, port `8080` must actually be exposed, and the service must speak HTTP. For PostgreSQL, prefer the dedicated container's `getJdbcUrl()` instead of manually assembling a JDBC URL from parts.

**Port `0` is an allocation request, not a port to call.** For a local HTTP server, `new InetSocketAddress(..., 0)` requests a free port; after binding, retrieve the actual port. For a Spring Boot server running `webEnvironment = RANDOM_PORT`, setting `server.port=0` likewise asks for port allocation; it **does not equal the assigned port number**.

## 7. Distinguishing @DynamicPropertySource from @LocalServerPort

The two annotations solve different problems:

- **`@DynamicPropertySource`** feeds addresses of **external or test-created resources** into `Environment` before dependent beans need them—such as a PostgreSQL container URL or mock HTTP server.
- Spring Boot's **`@LocalServerPort`** receives the **actual port that the Boot application's own embedded HTTP server is listening on** in tests that start a web server, typically `@SpringBootTest(webEnvironment = RANDOM_PORT)`.

Sample Boot server snippet (not a complete test class):

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealHttpServerTest {
    @LocalServerPort
    int actualPort;

    @Test
    void portIsAssigned() {
        assertTrue(actualPort > 0);
    }
}
```

The sample needs imports and a valid web-configured Boot application. **Never try reading an instance `@LocalServerPort` field to feed a static `@DynamicPropertySource`**, because dynamic properties are normally registered before the test instance receives injection, and the embedded server's actual port only exists after the server starts. With `RANDOM_PORT`, use `@LocalServerPort`, `WebTestClient`, `TestRestTemplate`, or an HTTP client per your Boot test setup.

Conversely, if the Boot app **needs to call an HTTP mock server** when its beans are constructed, the mock server's URL is a configuration input and should be provided via dynamic properties before context refresh.

## 8. Property precedence with multiple configuration sources

Spring can resolve the same key from multiple sources:

- `application.yml`, `application-test.yml`, or property files via Boot's mechanism.
- `@TestPropertySource` from Spring TestContext.
- Environment variables, system properties, and properties passed via command line/build.
- Keys registered via `@DynamicPropertySource`.

In Spring TestContext, dynamic properties typically have **higher precedence** than the sources listed above. If a test file already declares `partner.base-url=http://localhost:8080` while `@DynamicPropertySource` registers `partner.base-url=http://127.0.0.1:<dynamicPort>`, beans will normally see the dynamic URL.

This is very handy for overriding default environments, yet also easy to misinterpret:

1. **Duplicate-looking key that differs from the actual bound name:** `partner.base-url` is not `partner.url`; check the `@Value` or `@ConfigurationProperties` prefix that the code reads.
2. **Dynamic value shadowed by another test or bean-specific config:** inspect how the context is built and the specific bean's property source rather than guessing.
3. **Supplier returns `null` or throws an exception:** beans reading the property may fail during context initialization.
4. **Property changes after beans were already created:** changing what the supplier returns does not automatically reconfigure initialized beans holding the old value. Dynamic properties are a **test context startup configuration mechanism**, not a live bean-refresh system.

When diagnosing, inject `Environment` into the test and inspect the actual key, as in `environment.getProperty("demo.ping.base-url")`. Also verify the bean received that value; seeing a value in `Environment` alone does not prove the adapter used it to connect.

## 9. Context cache and resources with separate lifecycles

Spring TestContext can cache an `ApplicationContext` across tests with equivalent configurations. Meanwhile, a PostgreSQL container or mock HTTP server might be started and stopped at individual test class scope.

This is a subtle source of bugs:
- Class A builds a context whose supplier returns a URL with port A.
- A finishes and stops server/container A.
- Class B uses an identical context configuration yet starts resource B on port B.
- If Spring **reuses the cached context holding the bean from A**, the client may still point to port A even though B's supplier differs.

Solutions depend on scope:
- Use a shared resource whose lifetime spans at least as long as all contexts using it, managed explicitly by your test suite setup.
- Ensure test classes have distinct context cache keys when their underlying dedicated resources truly differ.
- Use `@DirtiesContext` at the appropriate class or phase to force evicting a context whose beans are tied to a stopped resource.
- Do not create different resources in subclasses while reusing the exact same inherited `@DynamicPropertySource` method and expect the cache to notice different ports automatically.

The HTTP server example in Section 4 uses `@DirtiesContext(AFTER_CLASS)` because the server stops in `@AfterAll`. This adds context-rebuild overhead if other tests share similar contexts; use it only when real state/lifecycle risk exists. Do not slap `@DirtiesContext` on every test without weighing performance.

**Parallel test execution:** If multiple tests share a mutable static server field or JVM-wide `System.setProperty`, state can collide. Prefer isolated resources and dynamic properties tied to the right context, or properly synchronized/configured shared resources. Never mutate `System.setProperty("spring.datasource.url", ...)` casually across tests since it affects the entire JVM.

## 10. Choosing the right configuration mechanism for each scenario

| Problem | Suitable mechanism | Reason |
|---|---|---|
| URL of an HTTP stub server with an auto-assigned port | `@DynamicPropertySource` + supplier returning URL after server starts | Property tied to live runtime resource |
| JDBC URL/username/password of Testcontainers | `@DynamicPropertySource` or Boot's supported service connection mechanism | Avoids hard-coding host/mapped port |
| Constant configuration `feature.enabled=true` | `@TestPropertySource`, Boot test properties, or explicit config | No dynamic supplier needed |
| Checking the **Boot application's own HTTP server port** | `@LocalServerPort` with `RANDOM_PORT` | Port only exists after server startup |
| Testing pure Java functions only | Unit test with constructor parameters | No Spring properties/context needed |
| Needing a property to vary across individual test methods | Appropriate context/bean per case or redesigned injection | Dynamic properties are not a live intra-context switcher |
| Multiple modules/suites sharing a container | Clear lifecycle and context cache management | Prevents stale URLs or stopped resources |
| Tests targeting a real external API | Local stub/container or controlled dedicated test environment | Avoids network flakiness, secrets, and production data |

**Never put real passwords into test code.** Sample container usernames/passwords are temporary test values. For external services, use fake tokens or secrets provisioned safely for the test environment; avoid printing credential-bearing URLs to logs unnecessarily.

## 11. Common errors and how to diagnose them

### 11.1. `@DynamicPropertySource` method has the wrong signature

Fails when using an instance method, a method with different parameters, or a non-void return type:

```java
// Wrong: not a static method as required by Spring TestContext.
@DynamicPropertySource
void properties(DynamicPropertyRegistry registry) {
    registry.add("demo.url", () -> "http://127.0.0.1:9000");
}
```

This is an **intentionally wrong example**, not to be used in complete tests. The right signature is a `static void` method taking one `DynamicPropertyRegistry`. If the test fails before entering `@Test`, read Spring TestContext's discovery/configuration error and stack trace.

### 11.2. Reading mapped port before the container is running

Conceptually wrong:

```java
String url = "http://" + container.getHost()
        + ":" + container.getMappedPort(8080); // Might be too early!
registry.add("demo.url", () -> url);
```

This **risk-illustration snippet** assumes `container` is declared. Ensure the container has already started before accessing the mapped port; typically register a supplier that queries it at property resolution time, e.g., `() -> "..." + container.getMappedPort(8080)`, with container lifecycle properly coordinated.

### 11.3. Using the internal container port as the host port

A container exposing port `5432` does not mean the test JVM can reach `localhost:5432`. Retrieve the mapped port and proper host, or use the specialized container's connection URL API. On remote Docker setups, `container.getHost()` matters even more.

### 11.4. Registering the wrong key compared to what the bean reads

If code reads `@Value("${payment.gateway-url}")` while the test registers `payment.url`, the bean can still pick up a fallback from a config file or fail on a missing placeholder. Verify the **exact key**, `@ConfigurationProperties` binding, and `Environment` in the test.

### 11.5. Supplier returns a different value on every invocation

Wrong:

```java
registry.add("demo.url", () -> startAnotherServerAndReturnUrl());
```

This is a **counterexample**—the function is undefined because it illustrates an anti-pattern: spawning a new server on every resolution gives different beans different URLs and leaks resources. Start the server under intentional lifecycle management, then have the supplier only read that server's stable address.

### 11.6. Cached context pointing to a stopped resource

Symptom: a test passes on its own yet fails in the full suite with `Connection refused` or timeouts, especially across classes sharing the Spring context cache. Inspect when containers/servers start and stop, the URL held inside the bean, and whether contexts are cached. Use consistent lifecycles or `@DirtiesContext` where appropriate.

### 11.7. Confusing the Boot app port with the mock server port

`@LocalServerPort` reads the embedded server port after Boot starts; `@DynamicPropertySource` feeds mock server/container URLs to beans before they configure themselves. Never read an instance-injected `@LocalServerPort` inside a static supplier, and never treat `server.port=0` as the actual port.

### 11.8. Drawing overly broad conclusions from a passing test

A test reading `spring.datasource.url` from `Environment` does not prove JDBC connects. A passing `DataSource.getConnection()` does not prove migrations or JPA queries are right. A passing HTTP stub `ping` does not prove a real external API honors the same contract. **Assertions must verify the exact boundary the test was designed to protect.**

## 12. Checklist for safe @DynamicPropertySource implementation

- [ ] Identified which properties truly need dynamic values (host, mapped port, JDBC URL, endpoint, test credentials).
- [ ] `@DynamicPropertySource` method is `static void`, takes one `DynamicPropertyRegistry`, inside a test class processed by Spring TestContext.
- [ ] Test integrates Spring TestContext via `SpringExtension`, `@SpringBootTest`, or an appropriate mechanism.
- [ ] Resources are created and ready **before beans need to read** the properties.
- [ ] Suppliers do not allocate new resources per call; values stay stable over the context lifetime.
- [ ] URLs use **actually reachable** host and port—not `container port`, `mapped port` mixups, or `server.port=0`.
- [ ] Registered keys match `@Value`, `@ConfigurationProperties`, or auto-configuration properties in use.
- [ ] Verified the real bean receives the right values, with behavioral assertions such as opening a JDBC connection or calling the HTTP stub.
- [ ] Handled resource stop/cleanup and context caching, especially when test classes/subclasses use different endpoints.
- [ ] Avoided JVM-global system properties or fixed ports that collide under parallel execution.
- [ ] Distinguished Boot's `@LocalServerPort` from dynamic properties of supporting resources.
- [ ] Verified test results via actual task/report outputs; did not extrapolate that full production infrastructure was tested.

**Conclusion:** `@DynamicPropertySource` bridges **information known only at test runtime** (ports, URLs, credentials, temporary resources) with **Spring's `Environment` before beans consume them**. Registering suppliers with the right signature, keeping resources alive long enough, using real host/mapped ports, and accounting for context caching make Spring Boot tests reproducible locally and on CI without hard-coding infrastructure addresses.