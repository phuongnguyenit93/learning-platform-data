# Dynamic Ports and Avoiding Network Resource Contention

## 1. Lesson Objective

Under **Isolation and Parallel Execution** in **Spring Boot - testing**, an integration test must never implicitly assume that port **8080, 8081, 9090, 5432, 6379, or 8089** is free. When running multiple test classes, Gradle test forks, CI jobs, Docker containers, or multiple applications on one machine, processes may try to bind the same fixed port. The result is **`BindException: Address already in use`**, tests passing individually yet failing in the suite, or a test accidentally connecting to an instance started by another process.

Primary solution: **have the server itself bind port 0, let the OS assign an available port, and read back the actual port from the started server.** For Spring Boot web integration tests, use **`@SpringBootTest(webEnvironment = RANDOM_PORT)`** and **`@LocalServerPort`**. For raw Java TCP listeners, use **`new ServerSocket(0)`**. For downstream stubs, use **WireMock `dynamicPort`**, **`HttpServer` bound to port 0**, or container mapped ports; pass the live URL into Spring via **`@DynamicPropertySource`** or service connections.

This lesson uses **Java 17, Spring Boot 3.4.5, Spring MVC, JUnit Jupiter, and Spring TestContext**. The complete example features `/api/ping`, a proxy endpoint calling an HTTP stub only when enabled, and three test groups:
1. **`RANDOM_PORT`** with a real HTTP client getting the port from `@LocalServerPort`.
2. **`@DynamicPropertySource`** with a downstream HTTP stub opening port 0 before Boot's `ApplicationContext` is created.
3. **`MockMvc`** opening no TCP listener when only MVC request handling needs verification.
Plus a plain JUnit test holding two `ServerSocket(0)` instances simultaneously to demonstrate dynamic ports and ownership.

The objective is not generating unpredictable port numbers; it is **eliminating fixed-port assumptions, bounding resource ownership, and avoiding races when configuring test endpoints**. Commands and expected outcomes are explained from source code; **no claim is made that Gradle or the HTTP server was executed during authoring**.

## 2. What Does "Dynamic Port" Mean?

A TCP listener typically binds to a tuple of **local address, local port, protocol, and network namespace**. If an application tries to bind `127.0.0.1:8080` while another process already holds a conflicting socket, the OS rejects it per bind/reuse rules. Running both tests on "localhost" does **not** give each test its own port namespace.

In Java:

~~~java
try (ServerSocket server = new ServerSocket(0)) {
    int actualPort = server.getLocalPort();
    System.out.println(actualPort);
}
~~~

Port **0** tells the OS to pick an available port when binding. **`getLocalPort()`** reads the real port **after the listener has been created successfully**; the value is a positive number in the valid TCP port range, **not a predictable fixed number**. This is an illustrative snippet, without predicting stdout that varies by machine.

In Spring Boot:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class HttpIntegrationTest {
    @LocalServerPort
    int port;
}
~~~

Boot starts a **real embedded web server**, configures server port 0, and injects the bound port via **`@LocalServerPort`** into the test instance. Never assert that the port equals **one specific number**. Assert validity conditions and send HTTP requests to the live port.

**Dynamic ports alone do not make all tests independent.** Two tests can still write to the same database table, Redis key, file, or static singleton state. They only solve bind/address contention and prevent hitting the wrong endpoint.

## 3. RANDOM_PORT vs MOCK, DEFINED_PORT, and NONE

| WebEnvironment | Real server socket | Port | When to use |
| --- | --- | --- | --- |
| **`MOCK`** (default) | No | No real local server port | Spring MVC controller/filter tests with `MockMvc` |
| **`RANDOM_PORT`** | Yes | OS assigns port on bind | App-level HTTP E2E, cookies, redirects, real clients |
| **`DEFINED_PORT`** | Yes | `server.port` or default 8080 | Rarely suitable for parallel integration tests |
| **`NONE`** | No | None | Non-web context/config/service tests |

In Spring Boot 3.4, **`@SpringBootTest` does not automatically start an HTTP server just because it says BootTest**. The default is **`WebEnvironment.MOCK`**, which opens no listener. If a test uses **`@AutoConfigureMockMvc`**, requests flow through in-process mock servlet infrastructure without a TCP port.

**`RANDOM_PORT`** binds a real socket, letting tests use Java `HttpClient`, `RestClient`, `TestRestTemplate`, or `WebTestClient` pointed at the running server. When requests require real cookies, redirects, sessions, network headers, or embedded server settings, this is the right level.

**`DEFINED_PORT`** easily collides under parallel runs or when a dev app is already running on 8080. Use it only when a product requirement **strictly mandates a fixed port** and the test holds exclusive ownership of the resource/network namespace.

**`NONE`** fits tests focused purely on bean creation, `@ConfigurationProperties`, database services, queues, or background tasks without a servlet web environment.

### RANDOM_PORT Does Not Mean Unique per Test Method

Spring TestContext maintains an **`ApplicationContext` cache**. If multiple test methods or classes share the same context configuration, they may be served by **the exact same context and embedded web server**, and thus the **same port**. Therefore:
- Do not assert each test method gets a different port.
- Do not key test state by port instead of test identity.
- Do not add `@DirtiesContext` merely to force a different port unless actually required.
- Do not concatenate the port with the test name as a durable unique ID.
- Across two separate JVM test forks, each JVM still binds its own port via port 0.

If every test needs its own process/server, that is a **lifecycle isolation contract** distinct from requesting `RANDOM_PORT`.

## 4. TOCTOU: Why "Find a Free Port Then Use It Later" Is Dangerous

An anti-pattern:

~~~java
int candidate;
try (ServerSocket socket = new ServerSocket(0)) {
    candidate = socket.getLocalPort();
}
// Socket is closed: the port is NO LONGER reserved for you.
startEmbeddedServer(candidate);
~~~

This is a **counter-example excerpt**. The gap between **checking a free port** and **binding the new listener** is a **TOCTOU (time-of-check vs time-of-use)** race. Once the probing socket closes, any other process/test can grab that port.

Similarly, avoid:
- Shell commands parsing `netstat` to pick an "unused" port.
- `ServerSocket(0).getLocalPort()` followed by immediate close to pass `server.port`.
- Writing a `findAvailablePort()` helper and assuming the port is "reserved".
- A fixed port plus test index without ownership/lifecycle control.
- Pinging `localhost:8089`, getting no reply, and assuming the port is free.

**Correct:** tell the **actual target server** to bind port 0 and **keep the socket open** throughout the test. Read the port from the live server via `@LocalServerPort`, `ServerSocket.getLocalPort()`, `WireMockRuntimeInfo`, or `Testcontainers.getMappedPort` after the resource has started.

### When Should You Hold a Manually Created Server Socket?

If the test itself acts as a raw TCP server, keep **`ServerSocket`** inside `try-with-resources` until assertions finish. If the test needs an HTTP stub, let the **HTTP stub** manage its own port-0 socket rather than using a separate `ServerSocket` to "claim" a port beforehand. Spring Boot embedded Tomcat/Jetty/Netty manages its own lifecycle: set **`server.port=0`** rather than guessing a port ahead of time.

### TIME_WAIT, SO_REUSEADDR, and Port Reuse

After closing TCP connections, the OS may retain connection states like `TIME_WAIT`; socket options such as `SO_REUSEADDR`/`SO_REUSEPORT` have OS-dependent semantics. **Do not assume a freshly released port can always be rebound immediately**, and do not try to "fix" `BindException`s with reuse flags. Port 0 with server-owned lifecycles is the durable default for tests.

## 5. Hands-On Project Structure

~~~text
settings.gradle
build.gradle
src/main/java/com/example/portqa/PortQaApplication.java
src/main/java/com/example/portqa/PingController.java
src/main/java/com/example/portqa/RemoteStatusProperties.java
src/main/java/com/example/portqa/RemoteStatusClient.java
src/main/java/com/example/portqa/RemoteStatusConfiguration.java
src/main/java/com/example/portqa/RemoteStatusController.java
src/test/java/com/example/portqa/RandomPortHttpTest.java
src/test/java/com/example/portqa/RandomPortRemoteStubTest.java
src/test/java/com/example/portqa/PingControllerMvcSliceTest.java
src/test/java/com/example/portqa/EphemeralPortSocketTest.java
~~~

**Architectural intent:** `PingController` has no upstream dependency. `RemoteStatusClient`/`RemoteStatusController` exist only when **`remote.status.enabled=true`**. Thus ping tests need no HTTP stub, while downstream integration tests enable the feature and inject the dynamic base URL via **`@DynamicPropertySource`**.

### 5.1. settings.gradle

~~~groovy
rootProject.name = 'spring-random-port-tests'
~~~

### 5.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.5'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.addAll(['--add-modules', 'jdk.httpserver'])
}

tasks.named('test') {
    useJUnitPlatform()
    jvmArgs '--add-modules', 'jdk.httpserver'
}
~~~

**`spring-boot-starter-web`** provides Spring MVC and `RestClient.Builder` auto-configuration. **`spring-boot-starter-validation`** enables `@NotNull` on the URI config. **`spring-boot-starter-test`** brings in JUnit Jupiter, MockMvc, Spring TestContext, and AssertJ. The Java test stub uses the JDK **`jdk.httpserver`** module; Gradle explicitly configures the module for compile/test so the project does not rely on runtime module resolution defaults.

Testcontainers and WireMock are not used in the runnable project, so core tests run without Docker. Section 12 illustrates those tools when real projects require databases or complex HTTP stubs.

### 5.3. PortQaApplication.java

~~~java
package com.example.portqa;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PortQaApplication {

    public static void main(String[] args) {
        SpringApplication.run(PortQaApplication.class, args);
    }
}
~~~

The project uses a consistent `com.example.portqa` package so component scanning discovers controllers and configurations. Never open ports in static initializers or application `@PostConstruct` methods: Spring Boot's embedded server manages the listener during startup.

### 5.4. PingController.java

~~~java
package com.example.portqa;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {

    @GetMapping(
        value = "/api/ping",
        produces = MediaType.TEXT_PLAIN_VALUE)
    public String ping() {
        return "pong";
    }
}
~~~

This endpoint is **stateless with no DB/external dependency**. Testing via `RANDOM_PORT` proves real HTTP networking; testing via `MockMvc` verifies routing/response without a socket. Same controller, **two different kinds of evidence**.

### 5.5. RemoteStatusProperties.java

~~~java
package com.example.portqa;

import java.net.URI;

import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "remote.status")
public class RemoteStatusProperties {

    @NotNull
    private URI baseUrl;

    public URI getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(URI baseUrl) {
        this.baseUrl = baseUrl;
    }
}
~~~

Do not hard-code `http://localhost:8089` as a default. When the feature is enabled, the test must pass the stub's live URL. In production, `application.yaml`/environment provides `base-url`. When disabled, the configuration class below does not register the properties bean, so no URL is required.

**`@NotNull`** only checks that a URI is present; production code may also check HTTP(S) schemes, hosts, absolute URIs, TLS policies, and credential handling. Do not treat successful URI parsing as a healthy backend.

### 5.6. RemoteStatusClient.java

~~~java
package com.example.portqa;

import org.springframework.web.client.RestClient;

public final class RemoteStatusClient {

    private final RestClient client;

    public RemoteStatusClient(
            RestClient.Builder builder,
            RemoteStatusProperties properties) {
        this.client = builder
            .baseUrl(properties.getBaseUrl().toString())
            .build();
    }

    public String readStatus() {
        return client.get()
            .uri("/status")
            .retrieve()
            .body(String.class);
    }
}
~~~

**`RestClient`** is Spring Framework 6.x's synchronous HTTP client. Tests can use a local stub on a dynamic port as a real downstream rather than mocking the client. Never take the port from **`@LocalServerPort`** to call downstream: that port belongs to the **application under test**, not the HTTP stub.

In production, configure client connect/read timeouts and error handling appropriately; this lesson focuses only on isolation/dynamic addressing. If upstream returns 503, `RestClient.retrieve()` throws an HTTP status exception by default—a separate runtime resilience contract.

### 5.7. RemoteStatusConfiguration.java

~~~java
package com.example.portqa;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
    prefix = "remote.status",
    name = "enabled",
    havingValue = "true")
@EnableConfigurationProperties(RemoteStatusProperties.class)
public class RemoteStatusConfiguration {

    @Bean
    RemoteStatusClient remoteStatusClient(
            RestClient.Builder builder,
            RemoteStatusProperties properties) {
        return new RemoteStatusClient(builder, properties);
    }
}
~~~

The feature defaults to **off** (`matchIfMissing=false`). Ping tests need no external base URL. Downstream tests set **`remote.status.enabled=true`** and **`remote.status.base-url`** via `@DynamicPropertySource` before `ApplicationContext` startup.

### 5.8. RemoteStatusController.java

~~~java
package com.example.portqa;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@ConditionalOnProperty(
    prefix = "remote.status",
    name = "enabled",
    havingValue = "true")
public class RemoteStatusController {

    private final RemoteStatusClient client;

    public RemoteStatusController(RemoteStatusClient client) {
        this.client = client;
    }

    @GetMapping(
        value = "/api/remote-status",
        produces = MediaType.TEXT_PLAIN_VALUE)
    public String remoteStatus() {
        return client.readStatus();
    }
}
~~~

When `enabled=false`, the controller registers no route and the client needs no base URL. When `enabled=true`, the controller forwards requests upstream through `RestClient` using the property-bound URL.

## 6. RANDOM_PORT + @LocalServerPort with a Real HTTP Client

**src/test/java/com/example/portqa/RandomPortHttpTest.java**

~~~java
package com.example.portqa;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = WebEnvironment.RANDOM_PORT,
    properties = {
        "server.address=127.0.0.1",
        "remote.status.enabled=false"
    })
class RandomPortHttpTest {

    @LocalServerPort
    private int port;

    @Test
    void realHttpRequestUsesAssignedPort() throws Exception {
        assertTrue(port > 0 && port <= 65535);

        URI uri = URI.create(
            "http://127.0.0.1:" + port + "/api/ping");

        HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(2))
            .build();

        HttpRequest request = HttpRequest.newBuilder(uri)
            .timeout(Duration.ofSeconds(3))
            .GET()
            .build();

        HttpResponse<String> response = client.send(
            request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertEquals("pong", response.body());
    }

    @Test
    void disabledProxyRouteIsAbsent() throws Exception {
        HttpClient client = HttpClient.newHttpClient();

        HttpRequest request = HttpRequest.newBuilder(
            URI.create(
                "http://127.0.0.1:" + port
                + "/api/remote-status"))
            .timeout(Duration.ofSeconds(3))
            .GET()
            .build();

        HttpResponse<String> response = client.send(
            request, HttpResponse.BodyHandlers.ofString());

        assertEquals(404, response.statusCode());
    }
}
~~~

**Key points:**
- `@SpringBootTest(RANDOM_PORT)` opens a **real server**, not `MockMvc`.
- `@LocalServerPort` supplies the **bound port**; never read it in a static initializer or test constructor.
- The request URI is built **inside the `@Test` method**, after the Spring context/server has started.
- **`server.address=127.0.0.1`** binds only loopback in tests, avoiding accidentally exposing test endpoints on all network interfaces.
- Do not assert the port differs from 8080 or falls in a specific ephemeral range: OS port selection varies across machines.
- Do not assert different test methods receive different ports; Spring's context cache may reuse one server/port.
- The disabled proxy endpoint does not get injected with a nonexistent upstream URL.

**Lifecycle distinction:** `@LocalServerPort` is meaningful only when a web server is running. In `@WebMvcTest`/`@SpringBootTest(MOCK)`, there is no real server, so `@LocalServerPort` cannot be used as a URL source.

## 7. Downstream Stubs Must Also Use Dynamic Ports

When an app takes configuration to call an external API, running the application itself on `RANDOM_PORT` is **not enough**. A WireMock/MockWebServer/HttpServer fixed at port 8089 can still contend with another test. In this full project, JDK **`com.sun.net.httpserver.HttpServer`** binds `127.0.0.1:0`, starts before the Spring application context, and supplies its dynamic base URL to the app via **`@DynamicPropertySource`**.

**src/test/java/com/example/portqa/RandomPortRemoteStubTest.java**

~~~java
package com.example.portqa;

import java.io.IOException;
import java.io.OutputStream;
import java.io.UncheckedIOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import com.sun.net.httpserver.HttpServer;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = WebEnvironment.RANDOM_PORT,
    properties = "server.address=127.0.0.1")
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class RandomPortRemoteStubTest {

    // Stub is started before Spring needs to resolve properties.
    private static final HttpServer STUB = startStub();

    @LocalServerPort
    private int appPort;

    @DynamicPropertySource
    static void remoteStatusProperties(
            DynamicPropertyRegistry registry) {
        registry.add(
            "remote.status.enabled", () -> "true");
        registry.add(
            "remote.status.base-url",
            () -> "http://127.0.0.1:"
                + STUB.getAddress().getPort());
    }

    @Test
    void appProxyCallsDynamicUpstreamPort() throws Exception {
        int stubPort = STUB.getAddress().getPort();

        assertTrue(appPort > 0);
        assertTrue(stubPort > 0);

        URI appUri = URI.create(
            "http://127.0.0.1:" + appPort
            + "/api/remote-status");

        HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(2))
            .build();

        HttpRequest request = HttpRequest.newBuilder(appUri)
            .timeout(Duration.ofSeconds(4))
            .GET()
            .build();

        HttpResponse<String> response = client.send(
            request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertEquals("upstream-ready", response.body());
    }

    @AfterAll
    static void stopStub() {
        STUB.stop(0);
    }

    private static HttpServer startStub() {
        try {
            InetSocketAddress address = new InetSocketAddress(
                InetAddress.getByName("127.0.0.1"), 0);

            HttpServer server = HttpServer.create(address, 0);

            server.createContext("/status", exchange -> {
                byte[] bytes = "upstream-ready".getBytes(
                    StandardCharsets.UTF_8);

                exchange.getResponseHeaders().set(
                    "Content-Type",
                    "text/plain; charset=UTF-8");

                exchange.sendResponseHeaders(
                    200, bytes.length);

                try (OutputStream out =
                        exchange.getResponseBody()) {
                    out.write(bytes);
                }
            });

            server.start();
            return server;
        } catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }
    }
}
~~~

### Why Doesn't This Race?

**`STUB`** binds port 0 itself and holds the socket throughout the test class. **`@DynamicPropertySource`** registers a **`Supplier`** reading the exact base URL from the already-started `STUB`. Spring Boot creates `RemoteStatusProperties`/`RemoteStatusClient` when loading the context and uses the live stub port, not a guessed port.

**`@LocalServerPort`** is the **application inbound port**; **`STUB.getAddress().getPort()`** is the **upstream outbound destination port**. These two ports belong to two separate servers. The test connects only to the app inbound port, while the app's `RestClient` connects to the stub outbound port. Never swap the two directions.

**`@DirtiesContext(AFTER_CLASS)`** is chosen deliberately here to prevent a context whose bean points to a stopped stub from being cached/reused in another class. Do not overuse `@DirtiesContext` across an entire suite; if using a long-lived test-owned reusable stub matching the shared context lifecycle, you can avoid context recreation provided no stale endpoint exists. **`@AfterAll`** stops `STUB` to prevent leaking sockets/threads.

Never assert that `appPort` must differ from another test class's port: Spring TestContext caching and OS allocation decide that. Never assert "two random numbers are unequal" instead of testing that the actual request succeeds.

### Why Not Use @LocalServerPort Inside @DynamicPropertySource?

`@DynamicPropertySource` runs **as Spring prepares to build the `ApplicationContext`**; `@LocalServerPort` becomes available only **after the embedded server binds successfully**. If an external client configuration needed the app server port during Spring context initialization, you would hit a lifecycle circular dependency. For downstream stubs, the resource **must start before the context**, making `@DynamicPropertySource`'s `Supplier` appropriate.

If a consumer needs the URL of the **application under test**, construct the URL inside the test method after `@LocalServerPort` injection or use a test client configured by Boot. Never wire `@DynamicPropertySource` from a non-static `@LocalServerPort` field before the field has been injected.

## 8. When No Socket Is Needed: MockMvc or @WebMvcTest

**src/test/java/com/example/portqa/PingControllerMvcSliceTest.java**

~~~java
package com.example.portqa;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(PingController.class)
class PingControllerMvcSliceTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void pingRouteWorksWithoutOpeningHttpPort() throws Exception {
        mockMvc.perform(get("/api/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }
}
~~~

**`@WebMvcTest`** is an MVC slice test: it boots servlet test infrastructure without binding a real HTTP socket. When only verifying request mapping, validation, serialization, status codes, controller advice, or Spring MVC filter interactions, this is typically **fast and completely avoids network collisions**.

**`@SpringBootTest(webEnvironment=MOCK)` + `@AutoConfigureMockMvc`** is another option when full Spring beans are needed without TCP. Do not spin up `RANDOM_PORT` for every controller test when `MockMvc` suffices. Conversely, `MockMvc` does not prove embedded server ports, real TLS sockets, actual over-the-wire HTTP redirects/cookies, or proxy configuration.

In the sample project, **`PingController`** is standalone; `@WebMvcTest(PingController.class)` does not need `RemoteStatusClient`. If a controller slice has dependencies, provide test fixtures or **`@MockitoBean`** at the proper boundary rather than pulling in full external integrations just to boot the slice.

## 9. Plain Java Socket Test Proving Two Listeners Can Coexist

**src/test/java/com/example/portqa/EphemeralPortSocketTest.java**

~~~java
package com.example.portqa;

import java.net.InetAddress;
import java.net.ServerSocket;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class EphemeralPortSocketTest {

    @Test
    void twoLiveSocketsOwnDifferentAssignedPorts()
            throws Exception {

        InetAddress loopback =
            InetAddress.getByName("127.0.0.1");

        try (ServerSocket first =
                new ServerSocket(0, 50, loopback);
             ServerSocket second =
                new ServerSocket(0, 50, loopback)) {

            int firstPort = first.getLocalPort();
            int secondPort = second.getLocalPort();

            assertTrue(firstPort > 0);
            assertTrue(secondPort > 0);
            assertNotEquals(firstPort, secondPort);
        }
    }
}
~~~

**Why is this more reliable than finding a free port manually?** Both sockets **remain open and listening** while assertions execute; the OS cannot assign the same bind endpoint to two live standard TCP listeners with default options. Sockets close via `try-with-resources` even if assertions fail.

**Limitation:** two distinct ports within one test do not imply two independent test processes will always get different port numbers over time. Ports can be recycled after listeners close. Tests must never store port numbers in database keys or snapshots for cross-CI comparisons.

## 10. @DynamicPropertySource and Lifecycle Ordering

**`@DynamicPropertySource`** in Spring Framework 6.2 requires a **static method** taking **`DynamicPropertyRegistry`**. It registers **`Supplier`s** so the Spring Environment can fetch dynamic values when needed—typically URLs/ports of resources started by the test.

~~~java
@DynamicPropertySource
static void properties(DynamicPropertyRegistry registry) {
    registry.add("remote.status.base-url",
        () -> "http://127.0.0.1:"
            + STUB.getAddress().getPort());
}
~~~

In the full example, `STUB` is created and started in a static field initializer, so the `Supplier` has a valid port when the context binds. A bug-prone design is starting the external stub in **`@BeforeEach`**, because the Spring `ApplicationContext` may already be built **before `@BeforeEach`**, causing the property to resolve too early. **Start the resource before the context** using static lifecycles, Spring-managed `@TestConfiguration` beans/service connections, or a lifecycle extension with verified startup ordering.

### Avoiding Stale Properties Due to Context Caching

Spring TestContext caches `ApplicationContext` by configuration. If one test class's static stub stops and another class inherits the same `@DynamicPropertySource` method with a new port, the context cache can retain the old base URL. Fixes:
- Keep the resource alive at least as long as the cached context.
- Use `@DirtiesContext` **selectively** when endpoints/lifecycles change.
- Separate test classes with distinct configurations/context cache keys.
- Use Spring Boot 3.4 **`@ServiceConnection`** / container-as-bean where supported.
- Never write dynamic ports into global `System.setProperty` or static shared mutable fields from parallel tests.

**`@DynamicPropertySource` is not a tool to publish a `RANDOM_PORT` app's port to itself before startup**. Use it to pass the port of an **already-started external resource** into the `ApplicationContext`.

### Port Selection and Races in JUnit Extensions

When using `WireMockExtension`, `MockWebServer`, or Testcontainers-managed resources, check **extension lifecycle order** before registering dynamic property Suppliers. Lazy Suppliers help, yet if the context initializes before the extension starts, querying an unopened port fails. For Spring-managed resource lifecycles, Spring Boot service connections/bean configurations are often safer. Never blindly copy snippets when extension hook order is unclear.

## 11. Testcontainers: Container Port Differs from Host Port

With Docker, there are two address spaces:
- **Container port**: e.g., PostgreSQL **5432** inside the container.
- **Host mapped port**: the host port chosen by Docker/Testcontainers for the test JVM to connect to.

Never hard-code **`localhost:5432`** inside the test JVM assuming it hits the PostgreSQL container. When multiple containers expose 5432, each gets mapped to a **different host port**.

An illustrative example, **not part of the runnable project**:

~~~java
@Testcontainers
class PostgresMappedPortExample {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16");

    @Test
    void useMappedEndpointAfterStart() {
        assertTrue(postgres.isRunning());

        String host = postgres.getHost();
        int mappedPort =
            postgres.getMappedPort(5432);

        assertTrue(mappedPort > 0);
    }
}
~~~

Requires Testcontainers JUnit Jupiter + PostgreSQL dependencies, imports, and a Docker daemon. **`getMappedPort(5432)`** works **only after the container has started**. In practice with `PostgreSQLContainer`, prefer **`postgres.getJdbcUrl()`**, `getUsername()`/`getPassword()`, or Spring Boot **`@ServiceConnection`** over manually assembling JDBC URLs.

Spring Boot 3.4 supports:

~~~java
@Container
@ServiceConnection
static PostgreSQLContainer<?> db =
    new PostgreSQLContainer<>("postgres:16");
~~~

This is an **illustrative excerpt** of a test using `@Testcontainers`/`@SpringBootTest` and `spring-boot-testcontainers`. `@ServiceConnection` supplies **`ConnectionDetails`** taking precedence over supported datasource connection properties. Do not assume the DB is running if the Testcontainers extension hasn't started or Docker is unavailable. Do not accidentally misuse `@ServiceConnection` as a substitute for verifying test configuration correctness.

### Avoid Fixed Host Port Bindings in Testcontainers

Do not force every test container to bind host port 5432 or 6379. Testcontainers maps exposed container ports to dynamic host ports by default. When multiple services must communicate inside Docker, prefer **Docker network aliases/hostnames** on the same network over publishing fixed host ports.

If a test binds a fixed host port, it conflicts with local PostgreSQL, other Docker processes, or parallel CI workers. Use fixed bindings only when an integration constraint strictly requires it and the resource is exclusively managed.

## 12. WireMock and MockWebServer: Keeping Ports Dynamic

WireMock's JUnit Jupiter **`@WireMockTest`** starts stubs on a random port by default, and **`WireMockRuntimeInfo`** exposes the actual port/baseUrl. With programmatic `WireMockExtension`, configure **`dynamicPort()`**.

Illustrative example, **not part of the runnable project**:

~~~java
@WireMockTest
class ExternalApiStubExample {

    @Test
    void stubUsesAssignedPort(
            WireMockRuntimeInfo runtimeInfo) {

        String baseUrl = runtimeInfo.getHttpBaseUrl();
        assertNotNull(baseUrl);

        // Configure client under test to target baseUrl.
    }
}
~~~

This snippet requires the WireMock JUnit Jupiter dependency and `org.wiremock.junit5` imports; exact API names depend on the pinned WireMock version. Never assume port 8080/8089. Note that **`@WireMockTest`** manages its own extension lifecycle; if a Spring `ApplicationContext` needs the stub URL at startup, align lifecycles in the right order (e.g., static `WireMockServer` started before context + `@DynamicPropertySource` or a Spring-managed stub bean). Reading `runtimeInfo` inside a `@Test` method is **too late** if a client bean already read the base URL during Spring context initialization.

`MockWebServer` (OkHttp) also starts on port 0 and exposes **`server.url("/").toString()`** once running. All libraries need **one single source of truth for the port**: the live server API, never a separate free-port helper.

## 13. Management Server: The Second Port Often Overlooked

If a Spring Boot application sets **`management.server.port`** differently from the application server port, there are **two web listeners**. Per Spring Boot 3.4 docs, **`@SpringBootTest(RANDOM_PORT)`** also assigns a **separate random management port** when the management server is configured on a distinct port.

Never use the application **`@LocalServerPort`** to hit `/actuator/health` on a separate management connector. Read the actual **local management port**/management endpoint URL per your version or test client config, keeping a clear distinction between inbound application and management listeners.

When including an Actuator example:
- add **`spring-boot-starter-actuator`**;
- configure `management.server.port` per test policy;
- restrict endpoints/loopback binding;
- verify the actual management port instead of assuming 9000/8081;
- assert readiness/liveness only when Actuator health groups are explicitly enabled.

**The runnable project opens no separate management server**, so there is no secondary port collision. In real applications, also watch out for debug/JMX/RMI ports, standalone Prometheus exporters, gRPC servers, embedded LDAP/FTP, Kafka broker stubs, and service discovery/test proxies—any of these can trigger `BindException` unrelated to `server.port`.

## 14. Network Namespaces, localhost, and Docker

**`127.0.0.1`** inside the test JVM is the loopback of the **network namespace where the JVM runs**. If the JVM runs on the host while a backend runs inside a Docker container, **the JVM's localhost is not the container's localhost**. If two containers share a Docker network, each container has its own loopback.

Cases:
- Host JVM → Testcontainers DB: use **`container.getHost()` + mapped port** or service connection.
- Container A → Container B on the same Docker network: use **network alias + container port**, not the host mapped port by default.
- CI service container → app container: configure the service name/network supplied by CI.
- Kubernetes pod → service: use DNS/service discovery; never use `localhost` unless actually sharing a pod/network namespace.
- A server binding **`0.0.0.0`** accepts traffic on all interfaces; tests wishing to limit exposure should bind **`127.0.0.1`** when appropriate.

**Do not inspect dynamic ports by reading `server.port` from `Environment` after binding.** The configured `0` may still remain `0`, while the actual bound port lives in `WebServer` and `@LocalServerPort`. Likewise, a fixed container port like 5432 differs from the host mapped port.

## 15. Parallel Tests: Sockets Are Only One Kind of Shared State

When enabling JUnit parallel execution or Gradle `maxParallelForks`, sources of collision include:

| Resource | Contention | Strategy |
| --- | --- | --- |
| Embedded Spring web server | Same fixed 8080 | `RANDOM_PORT` |
| HTTP mock server | Same 8089 | `dynamicPort`/port 0 |
| Database container | Host port 5432 | Testcontainers dynamic mapping |
| Redis/Kafka test services | Fixed published ports | Dynamic mapped ports/network aliases |
| Database rows | Same table/IDs | Unique IDs, schema-per-test/transaction isolation |
| Filesystem output | Same file path | `@TempDir`/unique temp directories |
| Static singleton/cache | Cross-test data | Reset/immutable fixtures, avoid globals |
| Spring ApplicationContext | Cached mutable beans | Per-test data isolation, selective `DirtiesContext` |
| System properties | Shared JVM global | Test-scoped properties/config |
| WireMock stubs | Shared mutable expectations | Per-test server/reset/isolated instance |
| External API quota | Shared account/rate-limit | Fake/stub, controlled integration jobs |

**`@SpringBootTest(RANDOM_PORT)`** solves app server bind conflicts, **not database transactions**. Because the HTTP client and server run on separate threads, **`@Transactional` on the test method does not automatically roll back transactions committed by the server request**. If a test writes to the DB through real HTTP, clean up data/test schemas explicitly rather than expecting test-managed transaction rollback.

### Test Instance Lifecycle and Shared State

JUnit Jupiter creates test instances **`PER_METHOD`** by default, yet static fields, Spring singleton beans, and cached contexts remain shared. Using `@TestInstance(PER_CLASS)` or `@Execution(CONCURRENT)` while mutating shared state requires explicit thread safety.

Never keep a global `static String currentBaseUrl` overwritten by multiple tests; parallel test classes can hit each other's stubs. Use test-scoped immutable URIs, properly scoped `@DynamicPropertySource`, or per-context DI. Never store a test class's port/URL in a system property expecting other classes not to collide.

### When You Are Forced to Use a Fixed Resource

If protocol/infrastructure constraints forbid dynamic ports, guarantee **exclusive ownership** via JUnit `ResourceLock`, CI job isolation, unique network namespaces, dedicated forks/namespaces, or a properly scoped singleton test resource. `@ResourceLock` synchronizes **only within that JUnit execution**, not across other JVMs/CI workers; never treat it as an OS-level distributed lock.

## 16. HTTP Client Timeouts and Readiness with Dynamic Ports

A bound port does not guarantee business endpoints are ready to handle traffic. In Spring Boot `RANDOM_PORT`, `@LocalServerPort` is injected after the embedded server starts; tests can call HTTP directly. For external stubs/containers:
- start the resource before binding properties;
- wait for a **readiness condition**, not just process creation;
- use **bounded connect/request timeouts**;
- verify status/body contracts rather than mere TCP socket connect;
- never use `Thread.sleep(2000)` guessing the server is ready;
- shut down resources after tests to avoid leaking ports/threads.

Diagnostic network failures:
- **`BindException: Address already in use`** → local listener could not bind, usually port/address contention.
- **`ConnectException: Connection refused`** → client hit a host/port with no active listener or rejected route.
- **`SocketTimeoutException` / `HttpTimeoutException`** → wait exceeded timeout budget.
- **`UnknownHostException`** → DNS/name resolution failure, distinct from bind collisions.
- **`SSLHandshakeException`** → TLS trust/certificate/protocol issue, not solved by `RANDOM_PORT`.

**Do not catch every exception and retry indefinitely.** With a wrong hard-coded URL, retrying just slows down the test. Debugging must distinguish a taken port, an unstarted server, a client targeting the wrong port, and a remote protocol error.

### Avoiding IPv4/IPv6 Mismatches

`localhost` can resolve to **`::1`** (IPv6) on one machine and **`127.0.0.1`** (IPv4) on another. If a stub binds strictly to `127.0.0.1` while the client calls `localhost` and the OS prefers IPv6, the test can fail even with the right port. The runnable example consistently binds and calls **`127.0.0.1`**. When IPv6 is required, configure addresses explicitly and test both per requirements.

## 17. Anti-Patterns to Avoid

| Anti-pattern | Why It Fails | Replace With |
| --- | --- | --- |
| `@SpringBootTest(DEFINED_PORT)` for all HTTP tests | 8080 collisions | `RANDOM_PORT` |
| Setting `server.port=8080` in test profile | Shared fixed port | Port 0 |
| "Find free port" then closing the socket | TOCTOU race | Real server binding port 0 |
| Reading `@LocalServerPort` in static setup | Server/context not ready yet | Read after startup |
| Asserting every `@Test` gets a new port | Context cache reuse | Assert HTTP behavior |
| Using `@LocalServerPort` as the stub port | Confuses app/stub roles | `Stub.getAddress().getPort()` |
| Mock server pinned to 8089 | Parallel collision | `dynamicPort` |
| Testcontainers binding fixed host port 5432 | Collides with host Postgres | `getMappedPort` / `@ServiceConnection` |
| Calling `getMappedPort` before start | No mapped port yet | Start container first |
| Hard-coding `localhost` inside Docker containers | Wrong network namespace | Container network alias/host mapped endpoint |
| Full HTTP integration for every controller case | Slow/network overhead | `MockMvc`/`WebMvcTest` when sufficient |
| Using port as a unique test ID | Port reuse/context caching | UUID/correlation ID |
| Storing port in global System property | Parallel tests overwrite each other | `DynamicPropertySource`/context config |
| `@DirtiesContext` on every test | Slow and masks shared state | Use only when lifecycle demands |
| Stopping shared stub while cached context still uses it | Stale URL/connection refused | Align resource/context lifecycles |
| Using `Thread.sleep` to wait for server | Flaky on CI | Startup lifecycle and bounded readiness |
| Separate ports yet shared DB | Cross-test data collision | DB fixture/schema isolation |
| `@Transactional` HTTP test expecting server rollback | Separate threads/transactions | Cleanup via API/DB |
| Catching `BindException` and retrying forever | Masks races/config bugs | Fix port/lifecycle |
| Asserting only 200 without verifying body | Could hit wrong process | Assert deterministic payload |
| Binding `0.0.0.0` unnecessarily | Exposes on CI network | Bind loopback when possible |

## 18. Run Commands and Expected Outcomes

With Java 17 and a compatible Gradle Wrapper:

~~~bash
./gradlew clean test
./gradlew test --tests com.example.portqa.RandomPortHttpTest
./gradlew test --tests com.example.portqa.RandomPortRemoteStubTest
./gradlew test --tests com.example.portqa.PingControllerMvcSliceTest
./gradlew test --tests com.example.portqa.EphemeralPortSocketTest
~~~

On Windows, use **`gradlew.bat`**. If Wrapper scripts are not yet generated, use an installed Gradle or generate the Gradle Wrapper first; `build.gradle` does not bundle `./gradlew`. The outcomes below are **expected per assertions**, not stdout from an actual execution.

| Test | What Must Hold |
| --- | --- |
| `realHttpRequestUsesAssignedPort` | `@LocalServerPort` >0, HTTP `/api/ping` 200 body `pong` |
| `disabledProxyRouteIsAbsent` | HTTP `/api/remote-status` returns 404 when feature off |
| `appProxyCallsDynamicUpstreamPort` | App HTTP 200 body `upstream-ready` from dynamic stub port |
| `pingRouteWorksWithoutOpeningHttpPort` | `MockMvc` 200, body `pong`, no socket opened |
| `twoLiveSocketsOwnDifferentAssignedPorts` | Two live `ServerSocket`s hold distinct valid ports |

**Do not print/pin specific ports in expected output**: every JVM/CI run can receive different numbers. If a test fails, log actual diagnostics including `appPort`/`stubPort` and bind addresses in test logs, while keeping secrets/credential-bearing URLs out of artifacts.

## 19. Scenario Exercises

**Scenario A.** Two classes both use `@SpringBootTest(RANDOM_PORT)` and share one cached `ApplicationContext`. Must they get two different ports? **No**. Context reuse means the same server/port can be shared validly. Test data must still be isolated separately.

**Scenario B.** The stub runs on 8089, the app runs on `RANDOM_PORT`; the parallel suite still fails with `BindException`. **The stub is still fixed on 8089**. Move the stub to `dynamicPort` and inject its URL.

**Scenario C.** A test opens `new ServerSocket(0)`, grabs the port, and closes it before starting the app on that port. Does a race remain? **Yes**. That is TOCTOU; let the app bind port 0 directly.

**Scenario D.** A `@DynamicPropertySource` supplier needs a URL, yet the stub starts in `@BeforeEach`. Is this safe? **Not guaranteed**; the Spring context can initialize before `@BeforeEach`. Start the stub before the context.

**Scenario E.** A Docker container exposes 5432, and the test JVM connects to `localhost:5432`. Is that right? **No**; use `container.getHost()`/`getMappedPort(5432)` or JDBC URL/service connection.

**Scenario F.** `appPort` is injected via `@LocalServerPort`, yet the test client hits `localhost:8080`. Where is the bug? The test **ignores `actualPort`**.

**Scenario G.** Does `RANDOM_PORT` solve duplicate database row IDs across tests? **No**, only socket binding.

**Scenario H.** A `MockMvc` route test needs no socket, yet the test uses `RANDOM_PORT`. Is it needed? **No**; `@WebMvcTest` or `MOCK` + `@AutoConfigureMockMvc` suffices.

**Scenario I.** Server binds `127.0.0.1`, client calls `localhost` which resolves to `::1`; can it be refused? **Yes**. Use a consistent address family.

**Scenario J.** Why doesn't the test assert the port falls within `49152–65535`? **Ephemeral port ranges are OS-configured**, not a fixed Boot contract.

**Scenario K.** What is the purpose of `@DirtiesContext(AFTER_CLASS)` on the stub test? **Closing the context configured against a stub the test has stopped**, preventing reuse of a stale endpoint. Not needed in every case.

**Scenario L.** What if `management.server.port` differs from `server.port`? There are **two listeners**, so tests must read the actual management endpoint port.

**Scenario M.** Can two CI jobs use different ports yet still collide on a Redis key? **Data contention still occurs**. You need key namespaces/isolated instances.

**Scenario N.** Does an open port mean the HTTP API is fully ready? **No**. Check actual endpoints/health.

**Scenario O.** Can JUnit `@ResourceLock("port8080")` lock another CI machine? **No**; it synchronizes only within the JUnit runtime managing that lock.

## 20. QA Checklist for Parallel Tests

- Never hard-code `server.port`/`management.port`/mocked-server ports in the suite without an explicit reason.
- Full HTTP integration tests use **`@SpringBootTest(RANDOM_PORT)`**.
- `@LocalServerPort` is read **after context startup**, never in static initializers.
- Every request to the app uses the **actual port**, never assuming 8080.
- When only MVC mapping is needed, use **`@WebMvcTest`/`MockMvc`** instead of a real server.
- External HTTP stubs bind port **0** and keep the listener open for the test's duration.
- `@DynamicPropertySource` reads URLs from an **already-started stub**, aligned with lifecycle/context caching.
- Never use **`findAvailablePort` → close → bind**.
- Never use ports as unique identifiers for test methods.
- Never confuse the app port with a downstream stub port.
- Never confuse a Docker container port with a host mapped port.
- Include timeouts and readiness checks; avoid arbitrary `Thread.sleep`.
- Keep IPv4/IPv6 test addresses consistent and restrict to loopback when appropriate.
- Close test resources promptly; avoid stale clients pointing at stopped servers.
- With JUnit parallelism/test forks enabled, avoid static/global mutable endpoint URLs overwritten across tests.
- When a fixed resource is unavoidable, enforce an exclusive test environment and properly scoped resource locking.
- Isolate test data/databases/files/Redis keys as well, not just network ports.
- Do not mistake `@Transactional` on HTTP tests for rolling back server transactions.
- Never fabricate actual port numbers, stdout, or unobserved test execution results.
- Verify source code compiles and places files/packages/dependencies accurately for Java 17 and Boot 3.4.5.

**Conclusion:** **Dynamic ports delegate port selection to the OS at the exact moment the real server binds, then use that assigned port throughout the test lifecycle.** In Spring Boot, use **`RANDOM_PORT` + `@LocalServerPort`** for real HTTP tests; use **`@WebMvcTest`/`MockMvc`** when networking is unnecessary; start HTTP stubs with **port 0 + `@DynamicPropertySource`**; and use Testcontainers **mapped ports/`@ServiceConnection`** for backends. Combine dynamic ports with proper resource lifecycles, context cache alignment, and test data isolation for resilient parallel suites.

## Official Documentation

- Spring Boot 3.4 — Testing Spring Boot Applications, `webEnvironment=RANDOM_PORT`, `LocalServerPort`, transaction boundaries, and management port: https://docs.spring.io/spring-boot/3.4/reference/testing/spring-boot-applications.html
- Spring Boot 3.4 — Testcontainers, `@ServiceConnection`: https://docs.spring.io/spring-boot/3.4/reference/testing/testcontainers.html
- Spring Framework 6.2 — `@DynamicPropertySource`: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/dynamic-property-sources.html
- Spring Framework 6.2 — Spring TestContext caching: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html
- WireMock — JUnit Jupiter extension and dynamic port: https://wiremock.org/docs/junit-jupiter/
- WireMock — Java configuration/`dynamicPort`: https://wiremock.org/docs/configuration/
- Java 17 — `ServerSocket` / `getLocalPort`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html
- Java 17 — `HttpClient`: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- Testcontainers — Networking and communication: https://java.testcontainers.org/features/networking/