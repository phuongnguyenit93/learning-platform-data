# HTTP Integration in Spring Boot: Configuring Base URL from RANDOM_PORT Instead of Hardcoding Ports

## 1. Problem and goal

An HTTP integration test must send requests to the **real embedded server** started by Spring Boot, rather than calling the controller directly or sending requests via MockMvc. Many simple examples hardcode `http://localhost:8080` in tests; this only works when the real server is always running on port 8080. In CI, tests may run in parallel, port 8080 may already be occupied, or the context may only be created for the test environment; the result is `Connection refused`, accidentally hitting another application, or tests depending on a developer's machine.

The standard solution is to use:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ApiHttpIntegrationTest {

    @LocalServerPort
    int port;
}
```

Spring Boot starts a **real server** on an available port chosen by the operating system; once the server is running, `@LocalServerPort` supplies the **actual port number** to the test. From there, the test builds the base URL at the proper lifecycle phase and passes it to an HTTP client: Java 17 `HttpClient`, `WebTestClient`, Rest Assured, or uses `TestRestTemplate` already preconfigured by Spring Boot with the root URI.

### Expected outcomes

- Choose `@SpringBootTest(webEnvironment = RANDOM_PORT)` properly and obtain the runtime port instead of assuming 8080.
- Distinguish `server.port=0` (requesting a random port) from `local.server.port` (the actual port after opening the server).
- Build a valid base URI with **scheme + host + port + context path**, avoiding misplaced `/` slashes or unsafe query string encoding.
- Know how to use both manually constructed HTTP clients and Spring Boot autoconfigured clients.
- Write tests that verify HTTP status, JSON body, and 4xx errors over a real socket; do not merely assert that the context starts.
- Understand the limitations around transaction rollback, context caching, management ports, HTTPS, and parallel execution.
- Avoid creating flaky tests with calls to fixed ports or using `Thread.sleep` to "wait for the server".

This lesson includes a complete, standalone runnable example with **Java 17, Spring Boot 3.5.0, Maven, and JUnit Jupiter**. Some Spring Boot 4 APIs are noted separately because Boot 4's HTTP test client infrastructure has been reorganized.

## 2. Why is RANDOM_PORT safer than 8080?

Comparison:

| Configuration | Real server? | Port | When to use |
| --- | --- | --- | --- |
| Default `@SpringBootTest` | **No** (`MOCK` web environment if a web stack is present) | No HTTP listening port | Context/wiring tests, optionally combined with MockMvc |
| `@SpringBootTest(webEnvironment=RANDOM_PORT)` | **Yes** | Port chosen by OS on server startup | Real HTTP integration tests, especially in CI |
| `@SpringBootTest(webEnvironment=DEFINED_PORT)` | **Yes** | Configured `server.port` or default 8080 | Systems that genuinely require a specific port |
| `@SpringBootTest(webEnvironment=NONE)` | **No** | No web server | Batch/non-web integration |
| `@WebMvcTest` + MockMvc | Does not open a TCP socket | No real port | Controller/MVC slice |
| `@WebFluxTest` + mock-bound WebTestClient | Does not open a TCP socket | No real port | WebFlux slice |

Spring Boot provides `WebEnvironment.RANDOM_PORT` by instructing the server to use `server.port=0`. In networking, port 0 is a directive meaning **"assign an available port"**; it is **not** the port that clients should call.

**Wrong:**

```java
// Do not write this in an HTTP integration test:
URI url = URI.create("http://localhost:8080/api/ping");

// Also wrong: server.port can be 0 to request a random port.
@Value("${server.port}")
int actualPort;
```

**Right:**

```java
@LocalServerPort
int port;  // The assigned HTTP port after the server starts.

@BeforeEach
void initializeUrl() {
    String baseUrl = "http://127.0.0.1:" + port;
}
```

The two snippets above only illustrate configuration; the runnable project is in Sections 8–11. `@LocalServerPort` resides in `org.springframework.boot.test.web.server.LocalServerPort` in Spring Boot 3.5 and is a shorthand equivalent to injecting `@Value("${local.server.port}")`.

### Do not assert "random port is not 8080"

The OS picks a port based on machine state. In most cases you will see a number other than 8080, but a test **must not assert** `port != 8080` because that choice is not part of the contract and could still collide. Just verify `port > 0`, send requests to the freshly started server, and check the response against the contract.

### Benefits when CI runs in parallel

If worker A and worker B both start the application on port 8080, the second worker can fail to bind the socket. `RANDOM_PORT` lets the OS allocate distinct ports to servers **running simultaneously**. This eliminates port collisions, though it **does not automatically isolate databases, filesystems, message brokers, static state, or server management ports**. Those resources require separate isolation policies.

## 3. @LocalServerPort lifecycle: when does it get its value?

Short mechanism:

```mermaid
flowchart TD
    A[Test runner creates Spring TestContext] --> B[SpringApplication creates ApplicationContext]
    B --> C[Embedded server binds port = 0]
    C --> D[OS allocates an actual local TCP port]
    D --> E[Boot publishes local.server.port]
    E --> F[Inject @LocalServerPort into test instance]
    F --> G[@BeforeEach builds URI and HTTP client]
    G --> H[Send HTTP request to server]
    H --> I[Assert status, headers, JSON, and side effects]
```

`local.server.port` only has a meaningful value **after the embedded web server has been initialized**. Therefore:

- Using `@LocalServerPort` in the **test class** and building the URI in a test method or `@BeforeEach` is clear and safe.
- Do not write `static final String BASE_URL = "http://localhost:" + port;` from a field that has not been injected yet.
- Do not read `local.server.port` in an application static initializer or a bean factory method running before server start.
- Do not use `@BeforeAll static` to reference an instance field `port` assuming it is already populated.
- Do not hardcode a port printed in a previous run's logs into a configuration file.
- Do not naively use `@DynamicPropertySource` to read the application's server port via a static method **before the server starts**; that mechanism is mainly intended for dynamic values from dependencies like Testcontainers prepared in the proper lifecycle.

You can inject the port via a constructor or test method parameter if the Spring/JUnit test extension and annotations support it, though the field + `@BeforeEach` pattern is easier for beginners to read.

### Distinguishing server.port and local.server.port

| Key | Meaning | Timing |
| --- | --- | --- |
| `server.port` | Port the application is **requested** to bind; `0` means random | Before opening the socket |
| `local.server.port` | Port the application **actually** bound to | After the embedded server starts |
| `management.server.port` | Requested management endpoint port (if configured separately) | Before the management server starts |
| `local.management.port` | Actual management server port (when separate) | After the management server starts |

Spring Boot provides `@LocalManagementPort` to access the actual management port when the management server runs on a separate port (requires the Actuator dependency/configuration). **Do not** take `@LocalServerPort` and assume it is the Actuator port in all configurations.

## 4. What is a valid base URL?

A base URL for HTTP integration typically consists of:

```text
scheme://host:port[/context-path]
http://127.0.0.1:52741
https://localhost:54443
http://127.0.0.1:52741/shop
```

Parts to distinguish:

| Component | Source | Notes |
| --- | --- | --- |
| `scheme` | HTTP or HTTPS configured by the test server | If TLS is enabled, use `https` and proper trust/cert |
| `host` | Interface address the server binds to | For local tests, usually `localhost` or `127.0.0.1` |
| `port` | `@LocalServerPort` | Do not hardcode or read `server.port=0` |
| `context path` | Servlet: `server.servlet.context-path` | Must include path accurately; do not drop `/shop` |
| `reactive base path` | WebFlux: `spring.webflux.base-path` when configured | Do not confuse with Servlet context path |
| `endpoint path` | Controller route | With or without leading `/`, depending on how URI is built |
| Query values | Test inputs | Encode via a URI builder or equivalent tool |

For example, if a servlet app configures `server.servlet.context-path=/shop`, the controller route `/api/ping` must be called at **`/shop/api/ping`**. Do not call `URI.resolve("/api/ping")` on a base URI containing `/shop/` if you want to keep the `/shop` prefix: a path starting with `/` in `URI.resolve` replaces the base URI's path component.

### URI.resolve and slashes

```java
URI root = URI.create("http://127.0.0.1:52741/shop/");

URI ok = root.resolve("api/ping");
// http://127.0.0.1:52741/shop/api/ping

URI losesPrefix = root.resolve("/api/ping");
// http://127.0.0.1:52741/api/ping
```

This is standard Java illustration needing no Spring, and the URIs in comments show the standard resolved output. To avoid bugs, normalize the base URL in one place and pick a single path-joining approach, or use `UriComponentsBuilder`.

### Encoding query parameters

Wrong:

```java
String name = "Lan & An";
// The & is interpreted as a query parameter separator if concatenated directly.
String path = "/api/greet?name=" + name;
```

One approach in Java 17:

```java
String encoded = URLEncoder.encode(
        "Lan & An", StandardCharsets.UTF_8);
URI uri = URI.create(baseUrl + "/api/greet?name=" + encoded);
```

`URLEncoder` uses HTML form encoding, where spaces become `+`; for standard Spring MVC query parameters, `+` is decoded back to a space. It is **not** a general-purpose encoder for path segments; if a path contains names with `/`, `%`, or non-ASCII characters, use a URI builder aligned with path/query structure.

With Spring's URI builder:

```java
URI uri = UriComponentsBuilder
        .fromUriString(baseUrl)
        .path("/api/greet")
        .queryParam("name", "Lan & An")
        .build()
        .encode()
        .toUri();
```

This is an illustrative snippet requiring `import org.springframework.web.util.UriComponentsBuilder`. In the sample project, we will demonstrate both JDK query encoding and URI builder usage via `WebTestClient`.

## 5. Three common HTTP client choices

### 5.1. TestRestTemplate: simplest for Boot 3.x servlet integration

Spring Boot provides `TestRestTemplate` and auto-configures it when `@SpringBootTest` starts an embedded server. In Boot 3.5:

```java
@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
class ExampleTest {
    @Autowired
    TestRestTemplate restTemplate;

    @Test
    void testEndpoint() {
        ResponseEntity<String> response =
                restTemplate.getForEntity("/api/ping", String.class);
        assertEquals(HttpStatus.OK, response.getStatusCode());
    }
}
```

This is an illustrative snippet; a runnable example with full imports is in Section 10. Key takeaway: `"/api/ping"` is a **relative URL**. `TestRestTemplate` is already configured to point at the test server and its random port, so you normally **do not need to build the base URL manually**.

`TestRestTemplate` also has a useful property: 4xx/5xx responses **do not automatically throw an exception** the way `RestTemplate`'s default error handler typically does; the test receives a `ResponseEntity` and asserts status/body. This is an important difference when testing error branches.

Do not manually instantiate `new TestRestTemplate()` and expect the instance to automatically know the Spring server's port. Auto-configuration only applies when using the bean provided by the test context (or when you intentionally configure a root URI on your instance).

### 5.2. WebTestClient: fluent assertions, supporting MVC/servers and reactive streams

When `spring-webflux` and the appropriate HTTP client dependencies are on the test classpath, you can use `WebTestClient`. Per Spring Boot 3.5 docs, with `RANDOM_PORT` Boot can provide a `WebTestClient` pointed at the server so you can use relative paths:

```java
@Autowired
WebTestClient client;

// Example:
client.get().uri("/api/ping")
        .exchange()
        .expectStatus().isOk();
```

With a **manually created client**, you must bind explicitly to the server:

```java
WebTestClient client = WebTestClient.bindToServer()
        .baseUrl("http://127.0.0.1:" + port)
        .responseTimeout(Duration.ofSeconds(5))
        .build();
```

Do not confuse `WebTestClient.bindToServer()` with `bindToController(...)` or `bindToApplicationContext(...)`. The latter two can run over a mock exchange without opening the network, so they **do not prove a real HTTP socket**.

In a Spring Boot servlet MVC app, add `spring-boot-starter-webflux` in **test scope** if you want `WebTestClient` + the Reactor Netty HTTP client; Spring Boot usually prefers MVC when both MVC and WebFlux are on the classpath. Do not add WebFlux to production just for the test client.

### 5.3. Java 17 HttpClient: independent of Spring test clients

Java's `java.net.http.HttpClient` has been built in since Java 11 and is available in Java 17:

```java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .build();

HttpRequest request = HttpRequest.newBuilder(
        URI.create(baseUrl + "/api/ping"))
    .timeout(Duration.ofSeconds(5))
    .GET()
    .build();

HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());
assertEquals(200, response.statusCode());
```

This is an illustrative snippet requiring imports. `connectTimeout` limits connection establishment (not all HTTP phases); `HttpRequest.Builder.timeout` is the request timeout; the test still needs assertions on body and status.

The JDK `HttpClient` is useful when you want to avoid coupling to Spring test client packages across Boot 3 and Boot 4. However, you must build URIs, set headers, serialize JSON, and handle responses yourself. If authentication, TLS, cookies, or redirect policies apply, configure them explicitly; never disable TLS certificate verification just to make tests pass.

### Quick comparison

| Client | How is the runtime port handled? | Strengths | Watch out for |
| --- | --- | --- | --- |
| Autowired `TestRestTemplate` | Uses root URI to test server automatically; call `/api/...` paths | Simple, 4xx does not throw by default | Boot 3.x package/API; check version when upgrading |
| Autowired `WebTestClient` | Boot 3.5 can wire it to `RANDOM_PORT` when classpath matches | Fluent status/header/body assertions, streaming | Needs `spring-webflux`; distinguish mock-bound vs server-bound |
| `WebTestClient.bindToServer()` | Manually build `baseUrl("http://...:"+port)` | Explicit control over timeouts/client | Do not use `bindToController` if real HTTP is wanted |
| JDK `HttpClient` | Manually build URI from `@LocalServerPort` | No extra HTTP test client dependency | Must decode JSON and inspect status manually |
| Rest Assured | Set `port(port)` or base URI per request | Fluent HTTP DSL syntax | Requires dependency; avoid mutable global `RestAssured.port` in parallel runs |

## 6. Building the base URL at the right lifecycle phase

A clean test structure:

```java
@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
class ProductHttpTest {
    @LocalServerPort
    int port;

    private String baseUrl;

    @BeforeEach
    void setUp() {
        assertTrue(port > 0);
        baseUrl = "http://127.0.0.1:" + port;
    }
}
```

This is an illustrative snippet. `@BeforeEach` runs once the Spring test context and server are initialized, so the runtime port is available. JUnit Jupiter's default test instance lifecycle is per-method; each method can build its URL/client without relying on static state.

Storing URLs and ports in **shared suite-wide static global state** mutated across multiple test classes is discouraged. When a context is reloaded with `@DirtiesContext` or multiple Spring applications run concurrently, stale static URLs can point to a closed server or another class's port.

### Using a small helper instead of copy-pasting port concatenation

```java
static URI baseUri(int port) {
    if (port <= 0 || port > 65535) {
        throw new IllegalArgumentException(
                "expected an allocated TCP port");
    }
    return URI.create("http://127.0.0.1:" + port);
}
```

This is a Java method you can copy into a test utility if multiple tests need it. However, a test helper must never start its own server or probe for a free port with `new ServerSocket(0)`, close the socket, and try to force the application onto that port: that introduces a **race condition** between finding the port and the server binding it. Delegating port allocation to the embedded server/OS via `RANDOM_PORT` is safer.

### Choosing localhost or 127.0.0.1?

`localhost` can resolve to IPv4 `127.0.0.1` or IPv6 `::1` depending on the environment. In this example we use `127.0.0.1` to denote IPv4 loopback and assume the embedded test server accepts IPv4 connections (usually true by default). If an application binds only to IPv6, a specific interface, or another `server.address`, adjust the base URI accordingly. IPv6 literals must use square brackets, e.g., `http://[::1]:52741`.

Never use `0.0.0.0` as the client host: that is a server bind address, **not a connection target** for an HTTP client.

## 7. Test configuration and environment safety

In Boot 3.5, you can use:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class RealApiTest {
    // ...
}
```

File `src/test/resources/application-test.properties`:

```properties
spring.main.banner-mode=off
logging.level.org.springframework.web=WARN
```

There is no need to put `server.port=0` in the test file when `RANDOM_PORT` is already specified, because the annotation itself requests a random port. If another property such as `server.port=8080` sits in a higher-precedence config source and overrides runtime behavior, verify the annotation/property sources and check the **actual** port via `@LocalServerPort` rather than guessing from files.

**Never let a test app connect to production.** When an application uses a database, Redis, Kafka, payment gateways, or SMTP, configure proper test profiles, fakes, sandboxes, or Testcontainers. Running the server on a random local port does not automatically protect outbound calls made by the application.

### Scheme when running HTTPS

If `server.ssl.enabled=true` is turned on and only HTTPS is accepted, the base URL must use `https://...:<port>`. Beyond the scheme, the test client must trust the certificate properly. Self-signed certificates can be configured via a test truststore; never unconditionally disable hostname/certificate verification.

### Context path

If a Servlet MVC app configures:

```properties
server.servlet.context-path=/shop
```

then the valid URI will be `http://127.0.0.1:<port>/shop/api/ping`. The base URL for a manually created client can be `http://127.0.0.1:<port>/shop/`, then appending the relative path `api/ping` (without a leading slash). For WebFlux, the base-path property is `spring.webflux.base-path`, not Servlet `server.servlet.context-path`.

**Do not accidentally add the prefix twice.** Does the client already prepend a root URI while the test appends the full URL again? Pick one clear approach: either use `TestRestTemplate` relative paths including the required context path, or build absolute URIs with `@LocalServerPort` for manually constructed HTTP clients.

### Management port and Actuator

Spring Boot can run Actuator management endpoints on a different port than the main application if `management.server.port` is configured separately. With `RANDOM_PORT`, the management server can be assigned its own random port. `@LocalServerPort` is the **application** port, not always the management port. When testing `/actuator/health`, verify endpoint exposure configuration and use `@LocalManagementPort` if a separate management port is used. A `/api/ping` test on the app port does not prove Actuator endpoints work.

## 8. Complete Maven/Java 17 project

To avoid database or async infrastructure distracting from the topic, the sample application has three **stateless** endpoints:

- `GET /api/ping` → HTTP 200, JSON `{"status":"up"}`.
- `GET /api/greet?name=Lan` → HTTP 200, JSON `{"message":"Hello, Lan"}`; if name is blank/whitespace, returns 400.
- `POST /api/messages` with JSON `{"text":"  hello  "}` → HTTP 201, JSON `{"text":"hello"}`.

In the test project, there will be three test classes hitting the same embedded server:

1. `TestRestTemplateRandomPortTest`: bean auto-routed to root URL, relative requests, HTTP 400 branch.
2. `JdkHttpClientRandomPortTest`: reads the actual port, builds base URI in `@BeforeEach`, tests queries with spaces/`&`/Unicode and JSON POST.
3. `WebTestClientRandomPortTest`: manually calls `bindToServer().baseUrl(...)`, checks status and JSON with fluent API.

### 8.1. File tree

```text
random-port-demo/
├── pom.xml
└── src/
    ├── main/java/example/randomport/
    │   ├── RandomPortApplication.java
    │   └── ApiController.java
    └── test/
        ├── resources/application-test.properties
        └── java/example/randomport/
            ├── TestRestTemplateRandomPortTest.java
            ├── JdkHttpClientRandomPortTest.java
            └── WebTestClientRandomPortTest.java
```

### 8.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>random-port-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>

        <!-- Only for WebTestClient in tests.
             Includes Reactor Netty client stack. Boot still prefers MVC. -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Why add `spring-boot-starter-webflux` in **test scope**: in Spring Boot 3.5, `WebTestClient` needs `spring-webflux` and an actual HTTP client connector. The WebFlux starter brings in all required pieces while the production app still depends only on the MVC starter. If a project only uses `TestRestTemplate` and `HttpClient`, dropping the WebFlux test dependency makes sense.

All Maven dependency versions are managed by the Boot parent/BOM. When upgrading Boot majors, never manually mix mismatched Spring Framework or Reactor versions.

### 8.3. Application class

`src/main/java/example/randomport/RandomPortApplication.java`:

```java
package example.randomport;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RandomPortApplication {
    public static void main(String[] args) {
        SpringApplication.run(RandomPortApplication.class, args);
    }
}
```

Place classes in the same `example.randomport` package or subpackages so default component scanning finds the controller. With test classes in the same package, Boot discovers the application configuration automatically.

### 8.4. ApiController.java

`src/main/java/example/randomport/ApiController.java`:

```java
package example.randomport;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api")
public class ApiController {

    public record PingResponse(String status) {}
    public record GreetingResponse(String message) {}
    public record MessageRequest(String text) {}
    public record MessageResponse(String text) {}

    @GetMapping("/ping")
    public PingResponse ping() {
        return new PingResponse("up");
    }

    @GetMapping("/greet")
    public GreetingResponse greet(@RequestParam String name) {
        if (name.isBlank()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "name must not be blank");
        }
        return new GreetingResponse("Hello, " + name.strip());
    }

    @PostMapping("/messages")
    public ResponseEntity<MessageResponse> createMessage(
            @RequestBody MessageRequest request) {
        if (request.text() == null || request.text().isBlank()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "text is required");
        }
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new MessageResponse(request.text().strip()));
    }
}
```

The code uses Java records to cut boilerplate, compatible with Java 17/Jackson in Boot 3.5. All endpoints are **stateless**, with no database, so tests do not depend on ordering or data cleanup. HTTP 400 is the policy defined by the controller; do not claim every invalid input in Boot automatically produces the exact same body.

### 8.5. application-test.properties

`src/test/resources/application-test.properties`:

```properties
spring.main.banner-mode=off
logging.level.org.springframework.web=WARN
```

Notice we intentionally **do not** set `server.port=8080` or `server.port=0` in the file. `@SpringBootTest(webEnvironment=RANDOM_PORT)` requests the random port. There are no external services or secrets.

## 9. TestRestTemplateRandomPortTest.java: using relative URLs

`src/test/java/example/randomport/TestRestTemplateRandomPortTest.java`:

```java
package example.randomport;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class TestRestTemplateRandomPortTest {

    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate restTemplate;

    @Test
    void relativePathAutomaticallyUsesStartedServer() {
        assertTrue(port > 0);

        ResponseEntity<ApiController.PingResponse> response =
                restTemplate.getForEntity(
                        "/api/ping",
                        ApiController.PingResponse.class);

        assertEquals(200, response.getStatusCode().value());
        assertNotNull(response.getBody());
        assertEquals("up", response.getBody().status());
    }

    @Test
    void badInputReturnsHttp400RatherThanThrowingClientError() {
        ResponseEntity<String> response =
                restTemplate.getForEntity(
                        "/api/greet?name=",
                        String.class);

        assertEquals(400, response.getStatusCode().value());
    }
}
```

**Explanation:** the `TestRestTemplate` bean is automatically configured for the running embedded test server. Requests use `"/api/ping"` and `"/api/greet?name="`, with no port numbers in source code. The test still injects `@LocalServerPort` to demonstrate **a runtime port exists**, though it does not need to concatenate it into the URL because the bean already resolves the root URI.

`TestRestTemplate` does not throw an exception by default on 4xx/5xx responses; the second method verifies the exact status. For standard `RestTemplate`, the default error handler can throw `HttpClientErrorException` instead of returning a normal response; do not mix the two clients.

**Do not** assume `getRootUri()` on every `TestRestTemplate` always exposes the exact base URL string in a fixed format: the implementation may use an internal `UriTemplateHandler`. What should be verified is an actual relative request reaching the running application.

## 10. JdkHttpClientRandomPortTest.java: building URLs manually

`src/test/java/example/randomport/JdkHttpClientRandomPortTest.java`:

```java
package example.randomport;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class JdkHttpClientRandomPortTest {

    @LocalServerPort
    int port;

    @Autowired
    ObjectMapper mapper;

    private String baseUrl;
    private HttpClient client;

    @BeforeEach
    void setUp() {
        assertTrue(port > 0);
        baseUrl = "http://127.0.0.1:" + port;
        client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .build();
    }

    @Test
    void encodedQueryIsDeliveredToRealServer() throws Exception {
        String name = "Mỹ & An";
        String encoded = URLEncoder.encode(
                name, StandardCharsets.UTF_8);
        URI url = URI.create(
                baseUrl + "/api/greet?name=" + encoded);

        HttpRequest request = HttpRequest.newBuilder(url)
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());

        JsonNode json = mapper.readTree(response.body());
        assertEquals("Hello, Mỹ & An",
                json.path("message").asText());
    }

    @Test
    void jsonPostReturns201OverRealHttp() throws Exception {
        URI url = URI.create(baseUrl + "/api/messages");
        HttpRequest request = HttpRequest.newBuilder(url)
                .timeout(Duration.ofSeconds(5))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(
                        "{\"text\":\"  hello  \"}"))
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(201, response.statusCode());

        JsonNode json = mapper.readTree(response.body());
        assertEquals("hello", json.path("text").asText());
    }

    @Test
    void unknownEndpointReturns404FromThisServer()
            throws Exception {
        URI url = URI.create(baseUrl + "/api/not-here");
        HttpRequest request = HttpRequest.newBuilder(url)
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(404, response.statusCode());
    }
}
```

Benefits:

- All three tests use the exact port injected by `@LocalServerPort` after startup.
- `URLEncoder` prevents `&` in the name from acting as a query separator; the test verifies the server returns Unicode properly.
- POST sends a real JSON body with an explicit content type and asserts 201 plus the response field.
- The 404 test verifies the server received the request for a non-existent endpoint, rather than failing with `Connection refused` on the wrong port.
- `connectTimeout` and request `timeout` help CI fail within bounded time instead of hanging indefinitely if server/connectivity has issues.

In practice, you can create one shared `HttpClient` **per test class** to reduce overhead, provided headers/cookies/state do not bleed across test methods. This lesson creates the client in `@BeforeEach` to keep lifecycle clear.

## 11. WebTestClientRandomPortTest.java: bindToServer with baseUrl

`src/test/java/example/randomport/WebTestClientRandomPortTest.java`:

```java
package example.randomport;

import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class WebTestClientRandomPortTest {

    @LocalServerPort
    int port;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        assertTrue(port > 0);

        client = WebTestClient.bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .responseTimeout(Duration.ofSeconds(5))
                .build();
    }

    @Test
    void relativeGetUsesConfiguredBaseUrl() {
        client.get()
                .uri(uriBuilder -> uriBuilder
                        .path("/api/greet")
                        .queryParam("name", "Lan Anh")
                        .build())
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(
                            MediaType.APPLICATION_JSON)
                .expectBody()
                    .jsonPath("$.message")
                    .isEqualTo("Hello, Lan Anh");
    }

    @Test
    void postCanCheckStatusAndJsonWithoutHardcodedPort() {
        client.post()
                .uri("/api/messages")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(
                        new ApiController.MessageRequest("  hello  "))
                .exchange()
                .expectStatus().isCreated()
                .expectBody()
                    .jsonPath("$.text")
                    .isEqualTo("hello");
    }
}
```

`WebTestClient.bindToServer()` uses a real HTTP connection; `baseUrl` comes directly from the assigned port. If your tests primarily target Spring WebFlux, the same approach applies when Spring Boot starts the reactive server.

Because the demo has both `spring-boot-starter-web` and the WebFlux starter in **test scope**, Spring Boot normally selects the Servlet MVC application type. `WebTestClient` is only an HTTP client here; it does not turn MVC controllers into WebFlux controllers. In Boot 3.5, when WebFlux client dependencies are present, you can `@Autowired WebTestClient` in a `RANDOM_PORT` test and use relative URIs without calling `bindToServer` manually; this example builds it manually on purpose to illustrate base URL setup.

Do not call `WebTestClient.bindToController(...)` if your goal is to verify the real server's port: that method binds to a mock WebFlux exchange and does not verify network sockets.

## 12. Running the project and expected results

Requires **JDK 17+**, Maven, and access to download dependencies from the repository on the first run. From the directory containing `pom.xml`:

```bash
mvn test
```

Run each class individually:

```bash
mvn test -Dtest=TestRestTemplateRandomPortTest
mvn test -Dtest=JdkHttpClientRandomPortTest
mvn test -Dtest=WebTestClientRandomPortTest
```

There are **7 test methods**:

| Class | Test count | What it verifies |
| --- | --- | --- |
| `TestRestTemplateRandomPortTest` | 2 | Relative URL reaches the random-port server automatically; 400 returned as response |
| `JdkHttpClientRandomPortTest` | 3 | Runtime URL / Unicode query / JSON POST / 404 over real HTTP |
| `WebTestClientRandomPortTest` | 2 | Explicit `bindToServer` base URL, GET/POST contract |
| **Total** | **7** | No database, Docker, or fixed ports required |

Expected result is **7 PASS, 0 FAIL, 0 SKIPPED** in a suitable environment. This is expected behavior from the source code, not a hardcoded stdout transcript. Maven may log a port like `Tomcat started on port 52741` or a different number **on each context startup**; do not assert the port number from logs. The tests do not call `System.out.println`, so there is no fixed application stdout. Inspect `target/surefire-reports` to verify the actual test count.

### A successful run example

Suppose the OS assigns port 52741 (purely an example, not a fixed expected value):

```text
Test context starts embedded server on http://127.0.0.1:52741
Test sends GET http://127.0.0.1:52741/api/ping
Response: HTTP 200
Body: {"status":"up"}
```

The only thing the test needs to know is the **response** from the newly started server, not the port number itself. The context may be reused within the same JVM test suite; the port does not necessarily change between classes or per test method.

## 13. Testing with REST Assured if your project uses it

Rest Assured provides a convenient DSL for HTTP integration. An **illustrative snippet**, requiring the `io.rest-assured:rest-assured` test dependency and imports:

```java
@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
class RestAssuredHttpTest {
    @LocalServerPort
    int port;

    @Test
    void checksPing() {
        given()
            .baseUri("http://127.0.0.1")
            .port(port)
        .when()
            .get("/api/ping")
        .then()
            .statusCode(200)
            .body("status", equalTo("up"));
    }
}
```

Prefer **`baseUri` and `port` on the request specification** rather than mutating global `RestAssured.port = port` or `RestAssured.baseURI` when multiple tests run in parallel. If a team uses global configuration, it must have clear scoping and teardown.

REST Assured can run over real HTTP, but it does not automatically know the port from `@SpringBootTest`. You still need `@LocalServerPort` / runtime port injection or a separate verified auto-configuration mechanism.

## 14. Using @BeforeEach, @BeforeAll, or constructor injection?

| Approach | Recommended? | Things to note |
| --- | --- | --- |
| `@LocalServerPort` field and build base URL inside test method | Yes | Simplest, no shared state |
| `@BeforeEach` building base URL/client | Yes | Runs after Spring TestContext injection, clear lifecycle |
| Test constructor accepting `@LocalServerPort int port` | Possible | Requires appropriate test extension / parameter resolver, fits class design |
| `@BeforeAll static` reading instance `port` | No | Instance field does not exist yet or is invalid in Java |
| `static final` URL built from test port | No | Port has not been allocated during static initialization |
| Production bean using `@Value("${local.server.port}")` at startup | Unsuitable | Actual port is only known after server initialization |
| Picking port manually via `ServerSocket(0)` and closing before start | Avoid | Race between "finding a free port" and actual bind |
| `@DirtiesContext` to rotate ports after every method | Usually unnecessary | Increases startup cost, not automatic test isolation |

### Context caching and multiple classes

Spring TestContext caches contexts by merged configuration. If the three test classes in the demo have equivalent context keys, they can share a single application context and the same random port. Therefore:

- Do not assert that ports differ between `TestRestTemplateRandomPortTest` and `WebTestClientRandomPortTest`.
- Do not store the port in a static field and reuse it in another class, because cache eviction, JVM forks, or `@DirtiesContext` can change it.
- If a test genuinely mutates beans/context and needs `@DirtiesContext`, clients must rebuild URLs after the context restarts.
- Caching is a performance optimization; it does **not** mean singleton/DB data has been reset.

When Maven/Gradle runs with multiple forks, each JVM has its own context cache and starts servers on separate ports. That is normal behavior.

## 15. Transactions and data when sending real HTTP

Spring Boot documentation warns: with `RANDOM_PORT`/`DEFINED_PORT`, the HTTP client and server execute on separate threads/transactions. If a test method is annotated with `@Transactional`, rolling back the transaction on the **test thread** does not roll back changes already committed by the server.

Warning example:

```java
@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
@Transactional
class UnsafeAssumptionTest {
    @Test
    void shouldNotAssumeServerWritesAreRolledBack() {
        // Send POST via HttpClient to server.
        // Server transaction may commit independently.
        // Test-method rollback does NOT automatically delete those rows.
    }
}
```

This is an **illustrative snippet, not a standalone test**. The sample project in Section 8 is intentionally stateless, so it has no database cleanup. In real applications:

- Tests create data with a dedicated correlation ID, then clean up only the test's own records.
- When DB/transaction tests share a suite, use isolated schemas/databases/containers or controlled transactional cleanup.
- Do not call `repository.deleteAll()` in teardown if other tests might share the DB.
- If a POST request times out before the client receives the ID, the server may still have committed; cleanup must rely on a test identifier rather than solely on the response.
- Do not use `@Rollback(false)` suite-wide without cleanup.
- If you only want to test controller mapping without real HTTP, use `@WebMvcTest`/MockMvc to avoid server setup and out-of-scope transactions.

The key point is that **having the right port does not mean the test environment has isolated all side effects**.

## 16. HTTPS, proxies, and security

### HTTPS

The sample uses local HTTP. If the app enables TLS:

- The base URL must switch to `https://localhost:<port>` or the address matching the certificate.
- Valid test keystore/truststore setup is needed; HTTPS can FAIL on certificate trust even when the server opened the right port.
- Never disable hostname verification client-wide just because a test certificate does not match.
- If a proxy/ingress is a required component, `RANDOM_PORT` on loopback does not prove that infrastructure works properly.

### Spring Security

When `spring-boot-starter-security` is present, endpoints may require login/CSRF/tokens per configuration. HTTP integration tests using a real client must send valid credentials (Bearer/Basic/cookie/CSRF headers if the contract requires them). Never turn off security to make tests pass and treat that as proof that endpoints are secure.

`TestRestTemplate` provides Basic Auth configuration; `HttpClient` lets you add headers; `WebTestClient` supports `headers(...)` or suitable mutators/test support. Place fake/sandbox credentials in test profiles or CI secrets; never hardcode production tokens.

### Host and network

`RANDOM_PORT` tests usually run on the same machine/process, so `127.0.0.1` is appropriate. If the server binds inside a container or remote network, the host and port may be remapped; `@LocalServerPort` only reports the server port inside the Boot environment, not necessarily the **published port** seen from another host. When testing an app in a Docker container from an external runner, use the mapped port/host provided by Testcontainers or the environment rather than a loopback URL in the wrong network namespace.

## 17. Common errors and how to fix them

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| `Connection refused localhost:8080` | Hardcoded 8080 even though test runs random port | Inject `@LocalServerPort` or use `TestRestTemplate` relative URLs |
| `port=0` in logs/URI | Using `server.port` instead of `local.server.port` | Inject the actual port after startup |
| `Could not resolve placeholder 'local.server.port'` | Test has no real server or reads the value too early | Use `RANDOM_PORT`, read within the test lifecycle |
| Null/zero port in static initializer | Static initializer runs before DI/server | Move into `@BeforeEach` |
| `@LocalServerPort` has no effect | Using default `@SpringBootTest` `MOCK` | Choose `RANDOM_PORT`/`DEFINED_PORT` |
| `TestRestTemplate` cannot be autowired | Not running an embedded-server test or wrong dependencies | Use Boot 3 test starter and `RANDOM_PORT` |
| `TestRestTemplate` relative URL hits wrong path | Missing context path prefix | Add the proper prefix or build absolute URI |
| `WebTestClient` does not compile | Missing `spring-webflux` test dependency | Add appropriate WebFlux test client dependencies |
| `WebTestClient` runs without starting real server | Using `bindToController`/mock-bound client | Use `bindToServer` and runtime base URL |
| HTTP GET returns 404 on declared path | Wrong context path, prefix, route, or URI resolution | Check endpoint path and base URI |
| Query containing `&` splits into multiple params | Concatenating query string without encoding | Use `URLEncoder`/URI builder |
| HTTPS request fails on certificate | Truststore/hostname mismatch | Configure valid test certificates |
| Test passes alone, fails in parallel CI | Fixed port or shared DB/files/static resources | `RANDOM_PORT` + resource isolation |
| `@Transactional` leaves DB rows after POST | Server transaction is separate from test thread | Clean up test-owned data explicitly |
| Test request times out even after server started | Client uses wrong host/port or server is slow | Check runtime URL, timeouts, and logs |
| Test fails because random port "did not change" between methods | Context cache reuses the server | Remove assertions requiring the port to change |
| `@LocalServerPort` returns app port, actuator is elsewhere | Management server configured separately | Use actual management port when testing Actuator |
| Boot 4 test uses old `TestRestTemplate` import | Test clients reorganized | Use `RestTestClient` + Boot 4 focused test modules |

### Step-by-step debugging, no guessing

1. Confirm the test has `@SpringBootTest(webEnvironment=RANDOM_PORT)`.
2. Confirm the embedded server started cleanly; if the context fails, read the deepest `Caused by`.
3. Check `port > 0` after injection without writing it into config files.
4. Verify **scheme, host, context path, and endpoint path** are correct.
5. Separate connect/socket errors from HTTP 404/400/500 responses: receiving an HTTP status proves **some server** responded, though you must still verify it is the right server via the response contract.
6. Check client deadlines/truststores, authentication, and headers.
7. Verify the build tool actually executes the tests and that test client dependencies are compatible.
8. For flaky failures, run multiple test classes together or in parallel to hunt down static state/shared resources instead of switching to a fixed port.

## 18. Spring Boot 4: do not copy Boot 3 test clients verbatim

The runnable snippets in this lesson target **Spring Boot 3.5.0**. In Spring Boot 4, the current reference favors `RestTestClient` (Spring Framework) combined with `@AutoConfigureRestTestClient` and focused test starters, rather than defaulting to `TestRestTemplate` as Boot 3.x did. The following concepts remain semantically identical:

- `@SpringBootTest(webEnvironment=RANDOM_PORT)` starts a real server on an OS-assigned port.
- `@LocalServerPort` retrieves the application port at runtime.
- Boot-autoconfigured clients can use relative URIs under proper test setups.
- Manually created clients must bind their base URL to the actual port.
- Real HTTP tests must distinguish client and server transactions.

When upgrading versions, inspect test dependencies, client packages/imports, Boot test auto-configuration, and JUnit/Spring Framework versions. **Do not** merely change `<version>3.5.0</version>` to 4.x and assume `TestRestTemplate`/`WebTestClient` imports work identically.

JDK `HttpClient` in this lesson remains independent of Spring's test client modules, making it useful for separating Boot bootstrap issues from URL issues.

## 19. Final lesson checklist

- [ ] Does the test need real HTTP and declare `@SpringBootTest(webEnvironment=RANDOM_PORT)`?
- [ ] Are `localhost:8080` and fixed ports absent from test requests?
- [ ] Is it clear that `server.port=0` is only a random-port request, not the actual port?
- [ ] Is `@LocalServerPort` injected after server startup?
- [ ] Is the base URL built in `@BeforeEach` or a test method rather than a static initializer?
- [ ] Are HTTP/HTTPS scheme, host, port, and context path combined accurately?
- [ ] Are queries/paths containing Unicode or `&`/`/` properly encoded?
- [ ] With `TestRestTemplate`, do you know when to use relative URIs and how to inspect 4xx?
- [ ] With `WebTestClient`, do you distinguish `bindToServer` from `bindToController`/`bindToApplicationContext`?
- [ ] With `HttpClient`, are request timeouts configured and real status/body asserted?
- [ ] Do tests avoid asserting that ports change across methods/classes due to context caching?
- [ ] Do tests avoid asserting that a random port must not be 8080?
- [ ] Are separate management ports distinguished from the application port?
- [ ] If a database is used, are HTTP-server commits not assumed to roll back with the test thread?
- [ ] Are external data/files/brokers isolated or intentionally cleaned up?
- [ ] Are production connections and leaked credentials prevented in test profiles?
- [ ] Do tests avoid disabling TLS/security just to get a 200 status?
- [ ] Does CI verify real test counts, avoid port conflicts, and avoid infinite waits?
- [ ] When using Boot 4, have HTTP test clients/modules/imports been updated for that version?

## 20. Official references

1. [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, `webEnvironment`, random port, `@LocalServerPort`, `TestRestTemplate`/`WebTestClient`, transaction caveats.
2. [Spring Boot 3.5 — @LocalServerPort API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/web/server/LocalServerPort.html): injection via `local.server.port`.
3. [Spring Boot 3.5 — WebEnvironment API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/SpringBootTest.WebEnvironment.html): `RANDOM_PORT`, `MOCK`, `DEFINED_PORT`, `NONE`.
4. [Spring Boot 3.5 — TestRestTemplate API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/web/client/TestRestTemplate.html): fault-tolerant HTTP client, 4xx/5xx status, and relative URIs.
5. [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): `bindToServer`, `baseUrl`, response assertions.
6. [Spring Framework — UriComponentsBuilder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/util/UriComponentsBuilder.html): safe URI/query/path construction.
7. [Spring Boot Reference — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): comparison of recommended HTTP clients in Boot 4.
8. [JUnit Jupiter User Guide](https://docs.junit.org/5.13.4/writing-tests/): `@BeforeEach`, test lifecycle, assertions, and reports.
9. [Java 17 HTTP Client API](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): `HttpClient`, `HttpRequest`, and `HttpResponse`.

**Remember:** `RANDOM_PORT` instructs Spring Boot to open an HTTP server on an **OS-assigned port**; `@LocalServerPort` provides the **actual port after startup**. For manually created clients, build the base URL from this port; for Boot 3.5's autowired `TestRestTemplate`, you can use relative URLs because Boot configures the root URI. A successful test sends requests to the **exact server just started** and asserts **status/body/side effects**, not merely printing a port number.