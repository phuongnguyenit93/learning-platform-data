# Limitations of MockMvc Compared to Real HTTP Server Calls

## 1. Big Picture

**MockMvc** is Spring Test's tool for testing **Spring MVC request handling** **without starting an HTTP server listening on a network port**. When calling `mockMvc.perform(...)`, Spring Test constructs simulated Servlet API request/response objects and passes them through `DispatcherServlet` and matching MVC components. You still exercise request mapping, argument binding, JSON converters, validation, controller advice, many filters, and application logic; however, there is no real TCP connection from an HTTP client to an embedded servlet container.

By contrast, a test sending real HTTP requests—for example, using `@SpringBootTest(webEnvironment = RANDOM_PORT)` and `java.net.http.HttpClient`—starts an embedded server, binds a listening port, and sends requests over a socket. That covers **HTTP transport behavior, the servlet container, and separate client/server threads** that MockMvc does not directly exercise.

Both approaches are valuable. Common mistakes include treating MockMvc as "the entire production application" or assuming a single HTTP request over `RANDOM_PORT` automatically verifies all production infrastructure (proxies/TLS/load balancers/cloud networking). Both assumptions overreach.

**Learning objectives:**

- Explain accurately which layers MockMvc executes and which layers it bypasses.
- Compare `@WebMvcTest`, `@SpringBootTest(MOCK) + @AutoConfigureMockMvc`, and `@SpringBootTest(RANDOM_PORT)`.
- Write runnable Java 17+/Spring Boot 3.x examples comparing MockMvc tests against real HTTP calls via JDK `HttpClient` to the **same endpoint**.
- Distinguish behaviors of filters/Spring Security, sessions/cookies, async, encoding, networking, ports, transactions, and rollbacks.
- Pick tools based on the bugs you need to catch, not because one tool sounds "stronger."
- Avoid misconceptions about Spring Boot 3/4, WebFlux, Spring TestContext caching, and CI environments.

## 2. What Does MockMvc Actually Execute?

### 2.1. Requests Handled Inside the Test JVM

When calling:

```java
mockMvc.perform(get("/api/greetings/Lan"))
       .andExpect(status().isOk());
```

this is a **snippet inside a test configured with MockMvc**, not a standalone Java program. Conceptual sequence:

```text
JUnit test method
   |
   +-- MockMvc.perform(...)
         |
         +-- MockHttpServletRequest / MockHttpServletResponse
         |
         +-- Servlet Filter chain (if registered with MockMvc)
         |
         +-- DispatcherServlet
               |
               +-- HandlerMapping
               +-- HandlerAdapter
               +-- Argument resolvers, data binding, validation
               +-- Controller --> Service --> Repository (if configured)
               +-- HttpMessageConverter, exception resolvers
         |
         +-- Mock response --> status(), header(), jsonPath()...
```

**There is no real HTTP socket layer between the test method and `DispatcherServlet`.** That allows MockMvc to thoroughly inspect how Spring MVC handles requests without allocating network ports, keeping execution fast and controller/mapping failures easy to isolate.

**Note:** servlet filters run only if registered with MockMvc per configuration. With Spring Boot's `@AutoConfigureMockMvc`, `addFilters = true` is the default and adds appropriate filters from the context into the mock pipeline. With manually created `MockMvcBuilders.standaloneSetup(...)`, filter configuration differs and does not automatically mirror the whole application.

### 2.2. Why MockMvc Does Not Mean "Mock Controller"

The name "MockMvc" is easy to misread. MockMvc **does not automatically turn controllers, services, or repositories into Mockito mocks**. It mocks the **Servlet request/response** while running real Spring MVC machinery.

- With `@WebMvcTest(SomeController.class)`: Spring Boot loads an **MVC slice** containing the controller and relevant web components; services/repositories typically require explicit mocks or imports.
- With `@SpringBootTest(webEnvironment = MOCK)` plus `@AutoConfigureMockMvc`: Spring Boot loads the **full application context per test configuration**, yet still starts no embedded server.
- With `MockMvcBuilders.standaloneSetup(controller)`: you pass the controller and needed infrastructure yourself; full context loading does not occur automatically.

Thus two tests can both use MockMvc while having completely different **dependency graph breadths**. Always identify both **how the `ApplicationContext` is built** and **how requests are dispatched**.

## 3. Which Layers Does Real HTTP Add?

A test running real HTTP, typically via:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class RealHttpTest {
    @LocalServerPort
    int port;
}
```

starts an embedded server (Tomcat, Jetty, or whichever servlet container the project configures) listening on a random port. JDK `HttpClient`, `TestRestTemplate`, `RestClient`, or `WebTestClient.bindToServer()` can then send HTTP traffic to that port.

Execution flow differs:

```text
JUnit test method (client thread)
   |
   +-- HTTP client constructs method/URI/headers/body
   |
   +-- HTTP encoding, TCP socket, localhost:<randomPort>
   |
   +-- Embedded servlet container / connector
   |      |
   |      +-- Parses request line, headers, body
   |      +-- Real Servlet request/response
   |      +-- Configured servlet filter chain
   |      +-- DispatcherServlet
   |             +-- Controller --> Service --> Repository
   |             +-- MVC converters / exception resolvers
   |
   +-- HTTP response bytes over socket
   |
   +-- Client decodes response --> assertions
```

This catches additional issues in **server startup, port binding, container integration, network-level request/response framing, HTTP client behavior, timeouts, and transport configuration**. However, it **still does not reproduce** reverse proxies, TLS termination, load balancers, firewalls, WAFs, internet latency, or ingress configuration unless those components are included in the test environment.

## 4. Practical Comparison Matrix

| Aspect | MockMvc | Real HTTP to Embedded Server |
|---|---|---|
| Spring MVC routing/controllers | Yes | Yes |
| JSON serialization/deserialization | Yes, per configured converters | Yes, plus HTTP request/response encoding |
| `@Valid`, binding, controller advice | Yes | Yes |
| Real services/repositories | Depends on loaded application context | Depends on loaded application context |
| Filter chain | Yes **if registered with MockMvc** | Passes through container/app-registered filter chain |
| Authentication/authorization | Testable with Spring Security Test and filter chain | Testable per real client/server behavior |
| Listening TCP port | **No** | **Yes** |
| Tomcat/Jetty/Undertow connector | Does not run through socket/connector | Yes, for the selected embedded server |
| HTTP parser, header limits, keep-alive | Not verified over a network wire | Verifiable with matching client/connector |
| TLS handshake, certificates | No | Yes **if test configures real HTTPS** |
| Reverse proxy, gateway, LB | No | **No**, unless present in the test environment |
| Client and server on separate threads | Usually not on synchronous paths | Yes |
| `@Transactional` on test method | Can cover synchronous MVC processing | Does not automatically cover server-thread transactions |
| Suite execution speed | Usually fast, low overhead | Usually heavier due to server/port/sockets |
| Catching network timeouts | Cannot measure real network timeouts | Can test configured client/server timeouts |
| Checking JSON/status responses | Yes | Yes |

**Do not treat this table as an absolute guarantee:** for example, Spring MVC async in MockMvc can use background threads; a real HTTP test using a basic client might miss browser-specific quirks; full-context tests might still mock external gateways. Always determine scope from actual configuration and assertions.

## 5. Choosing the Right Spring Boot Annotation

### 5.1. MockMvc with an MVC Slice

```java
@WebMvcTest(controllers = GreetingController.class)
class GreetingSliceTest {

    @Autowired
    MockMvc mockMvc;
}
```

This is a **configuration snippet** without test methods. `@WebMvcTest` targets controllers and MVC support components without loading all services. Ideal for testing mappings, validation, JSON, and exception handlers within a web slice.

### 5.2. MockMvc with Full Application Context

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureMockMvc
class GreetingFullMockMvcTest {

    @Autowired
    MockMvc mockMvc;
}
```

Even though the context can contain real services and repositories, **no HTTP server starts**. This tests collaboration across Spring beans and MVC inside the test JVM—not socket behavior.

`MOCK` is `@SpringBootTest`'s default. Writing it explicitly helps readers distinguish it from `RANDOM_PORT`.

### 5.3. Real HTTP Server on a Random Port

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class GreetingHttpTest {

    @LocalServerPort
    int port;
}
```

In Spring Boot 3.x, import `@LocalServerPort` from `org.springframework.boot.test.web.server.LocalServerPort`. Pick an HTTP client and target `http://127.0.0.1:<port>/...`; the server opens a real listening socket.

**You do not need** `@AutoConfigureMockMvc` to use JDK `HttpClient`. If both are present in a `RANDOM_PORT` test, keep clear which calls are `mockMvc.perform(...)` (in-JVM) and which are real HTTP (over the port). Simply starting a live server via an annotation does not suddenly route `MockMvc.perform` over TCP.

### 5.4. `DEFINED_PORT`, `NONE`, and When to Avoid Them

- `DEFINED_PORT` starts the server on the configured port, usually 8080 by default. Useful when interacting with external processes outside the test, but prone to port conflicts during parallel CI runs.
- `NONE` starts `SpringApplication` without any web environment; it is **not suitable** for servlet MockMvc request processing.
- `RANDOM_PORT` is safer for real HTTP integration tests in CI because it avoids port contention across jobs.

If a project runs a management server on a separate port, a `RANDOM_PORT` test can also assign a separate random management port. When testing actuator endpoints, verify the right port, context path, and security policy.

## 6. Runnable Example: One App, Two Testing Methods

We test the exact same endpoint through two paths: (1) `MockMvc`, and (2) JDK `HttpClient` over real HTTP. Both share the same logic, web config, and test filter. The difference lies in how requests enter Spring MVC.

**Requirements:** Java 17+, Spring Boot **3.x**, JUnit Jupiter, Servlet MVC (e.g. `spring-boot-starter-web`). No PostgreSQL, Docker, external HTTP, Spring Security, or data store required. The example is self-contained when placed under the matching filenames/packages and valid build configuration.

### 6.1. Dependencies and Build Tool

Gradle Groovy DSL — add to a `build.gradle` that already configures the Spring Boot plugin, repositories, and Java toolchain:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Maven — dependencies block inside a `pom.xml` with a compatible Spring Boot parent/BOM and Surefire:

```xml
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
</dependencies>
```

These are **snippets**, not complete build files. Do not duplicate dependencies already declared in your project. JDK 17 includes `java.net.http.HttpClient`, so no extra HTTP client library is needed for tests.

### 6.2. File Tree

```text
src/
├── main/java/com/example/mvclimits/
│   ├── BoundaryApplication.java
│   ├── GreetingController.java
│   └── MarkerFilter.java
└── test/java/com/example/mvclimits/
    ├── MockMvcBoundaryTest.java
    └── RealHttpBoundaryTest.java
```

Place all classes under package `com.example.mvclimits` so `@SpringBootApplication` scans the beans properly. No bean calls external services, and there is no mutable shared fixture.

### 6.3. Application Class

**File `src/main/java/com/example/mvclimits/BoundaryApplication.java`:**

```java
package com.example.mvclimits;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(BoundaryApplication.class, args);
    }
}
```

No fixed port is configured. In `MOCK` tests, no port opens; in `RANDOM_PORT` tests, Spring Boot picks an available port automatically.

### 6.4. Controller Receiving Path, Header, and JSON Body

**File `src/main/java/com/example/mvclimits/GreetingController.java`:**

```java
package com.example.mvclimits;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/greetings")
public class GreetingController {

    public record GreetingRequest(String name) {}

    public record GreetingReply(String message, String requestId) {}

    @GetMapping("/{name}")
    public GreetingReply greet(
            @PathVariable String name,
            @RequestHeader(
                name = "X-Request-Id",
                required = false
            ) String requestId) {

        return reply(name, requestId);
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public GreetingReply create(
            @RequestBody GreetingRequest request,
            @RequestHeader(
                name = "X-Request-Id",
                required = false
            ) String requestId) {

        return reply(request.name(), requestId);
    }

    private GreetingReply reply(String name, String requestId) {
        String id = requestId == null ? "absent" : requestId;
        return new GreetingReply("Xin chào " + name, id);
    }
}
```

This is a simple controller. GET demonstrates path/header binding; POST demonstrates JSON request-body conversion, status 201, and JSON response conversion. There is no validation logic in the example—to avoid conflating JSON parsing with Bean Validation, syntactically invalid JSON is tested separately.

### 6.5. Real Servlet Filter Used in Both Test Approaches

**File `src/main/java/com/example/mvclimits/MarkerFilter.java`:**

```java
package com.example.mvclimits;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class MarkerFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        response.setHeader("X-Filter-Visited", "yes");
        chain.doFilter(request, response);
    }
}
```

The filter sets an easily observable response header. When Boot auto-configures `MockMvc` with `addFilters=true` (default), the filter bean is added to the mock chain. When running a real server, Boot also registers the filter with the servlet container. Both test classes assert `X-Filter-Visited: yes`.

**Important takeaway:** both paths can execute the same filter logic. Thus "MockMvc skips all filters" is **false**. Its limitation is skipping **container/network integration** such as the HTTP connector—not skipping application filter code by default.

### 6.6. Test 1 — In-Process MockMvc, No Server

**File `src/test/java/com/example/mvclimits/MockMvcBoundaryTest.java`:**

```java
package com.example.mvclimits;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(
    classes = BoundaryApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureMockMvc
class MockMvcBoundaryTest {

    @Autowired
    MockMvc mvc;

    @Test
    void getChecksMvcMappingJsonAndConfiguredFilter()
            throws Exception {

        mvc.perform(get("/api/greetings/Lan")
                .header("X-Request-Id", "mock-get")
                .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(header().string(
                        "X-Filter-Visited", "yes"))
                .andExpect(jsonPath("$.message").value("Xin chào Lan"))
                .andExpect(jsonPath("$.requestId").value("mock-get"));
    }

    @Test
    void postChecksJsonRequestBodyAndCreatedStatus()
            throws Exception {

        mvc.perform(post("/api/greetings")
                .header("X-Request-Id", "mock-post")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"Minh\"}"))
                .andExpect(status().isCreated())
                .andExpect(header().string(
                        "X-Filter-Visited", "yes"))
                .andExpect(jsonPath("$.message").value("Xin chào Minh"))
                .andExpect(jsonPath("$.requestId").value("mock-post"));
    }

    @Test
    void malformedJsonReturnsBadRequest()
            throws Exception {

        mvc.perform(post("/api/greetings")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{"))
                .andExpect(status().isBadRequest());
    }
}
```

**Expected result:** **3 JUnit tests pass**. The context contains the real controller and filter, and MockMvc uses `MockHttpServletRequest/Response`. The test neither needs nor starts a server socket and has no localhost port. Malformed JSON is normally converted by Spring MVC into HTTP 400 via `HttpMessageNotReadableException`.

Do not infer from passing status/header checks that TLS certificates, proxy headers, or server connectors were tested. Those steps **do not exist during `mvc.perform(...)`**.

### 6.7. Test 2 — Real HTTP via `java.net.http.HttpClient`

**File `src/test/java/com/example/mvclimits/RealHttpBoundaryTest.java`:**

```java
package com.example.mvclimits;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    classes = BoundaryApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class RealHttpBoundaryTest {

    @LocalServerPort
    int port;

    @Autowired
    ObjectMapper mapper;

    private final HttpClient client = HttpClient.newHttpClient();

    private URI endpoint(String path) {
        return URI.create(
                "http://127.0.0.1:" + port + path);
    }

    @Test
    void getUsesActualListeningPortAndRealHttpTransport()
            throws Exception {

        assertThat(port).isGreaterThan(0);

        HttpRequest request = HttpRequest.newBuilder(
                endpoint("/api/greetings/Lan"))
                .header("X-Request-Id", "http-get")
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(response.headers()
                .firstValue("X-Filter-Visited"))
                .contains("yes");

        JsonNode json = mapper.readTree(response.body());
        assertThat(json.path("message").asText())
                .isEqualTo("Xin chào Lan");
        assertThat(json.path("requestId").asText())
                .isEqualTo("http-get");
    }

    @Test
    void postJsonOverHttpReturnsCreated()
            throws Exception {

        HttpRequest request = HttpRequest.newBuilder(
                endpoint("/api/greetings"))
                .header("X-Request-Id", "http-post")
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(
                        "{\"name\":\"Minh\"}",
                        StandardCharsets.UTF_8))
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

        assertThat(response.statusCode()).isEqualTo(201);
        assertThat(response.headers()
                .firstValue("X-Filter-Visited"))
                .contains("yes");

        JsonNode json = mapper.readTree(response.body());
        assertThat(json.path("message").asText())
                .isEqualTo("Xin chào Minh");
        assertThat(json.path("requestId").asText())
                .isEqualTo("http-post");
    }

    @Test
    void malformedJsonIsRejectedOverHttp()
            throws Exception {

        HttpRequest request = HttpRequest.newBuilder(
                endpoint("/api/greetings"))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(
                        "{", StandardCharsets.UTF_8))
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

        assertThat(response.statusCode()).isEqualTo(400);
    }
}
```

**Expected result:** **3 JUnit tests pass**. `@LocalServerPort` receives a valid value only when the web test actually starts a server via `RANDOM_PORT`/`DEFINED_PORT`; here it is `RANDOM_PORT`. `HttpClient.send(...)` transmits HTTP requests to loopback and reads response bytes over a socket.

This class exercises **real server startup + real HTTP calls**, yet still does not prove TLS or reverse proxies because it calls `http://127.0.0.1` with no proxy. The exact server implementation depends on project dependencies/configuration; do not assume a fixed container like Tomcat if the project swaps in Jetty.

### 6.8. Running Both Test Groups

Linux/macOS, choosing your project's build tool:

```bash
# Gradle Wrapper:
./gradlew test --tests "com.example.mvclimits.MockMvcBoundaryTest"
./gradlew test --tests "com.example.mvclimits.RealHttpBoundaryTest"

# Or Maven Wrapper:
./mvnw -Dtest=MockMvcBoundaryTest test
./mvnw -Dtest=RealHttpBoundaryTest test
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.mvclimits.MockMvcBoundaryTest"
.\gradlew.bat test --tests "com.example.mvclimits.RealHttpBoundaryTest"

# Or with Maven Wrapper:
.\mvnw.cmd "-Dtest=MockMvcBoundaryTest" test
.\mvnw.cmd "-Dtest=RealHttpBoundaryTest" test
```

**The sample has 6 tests total, split evenly across 2 test classes.** Running each class individually runs 3 tests; running the full suite executes these 6 alongside any other project tests. The code prints no explicit stdout; startup logs and summaries come from Boot, the build tool, and JUnit per version.

Build-tool snippets assume the project already has a wrapper and matching plugin setup. Do not run both Gradle and Maven on a single-build-system project.

### 6.9. What Do Both Runs Prove, and What Do They Leave Unproven?

Both suites verify routing, JSON bodies, response status, and the filter header. Overlapping **MVC contract** behavior is checked by both mechanisms.

Differences proven by **setup and transport**:

- MockMvc tests call `mockMvc.perform(...)` on mock requests/responses with no port.
- Real HTTP tests inject `@LocalServerPort`, build URIs with a port, and call JDK `HttpClient` over a socket.
- Only the real HTTP group passes through the running server's network connector and HTTP request parser.

When both pass, you can conclude the sample app handles those tested requests properly **both in MockMvc and over an embedded HTTP server**. You **cannot** claim "every container edge case, browser behavior, security rule, HTTP/2 detail, or production network path is verified."

## 7. Transport Limits That MockMvc Cannot Replace

### 7.1. Server Startup, Ports, and Sockets

MockMvc **cannot catch errors such as**:

- HTTP server failing to bind an already-occupied port.
- Connector configuration failing at startup.
- Real clients failing to connect or getting connection refused.
- Unexpected server socket closure or network-layer timeouts.
- Misconfigured HTTP keep-alive or connection pooling.

Catching these requires at least one test with a real server and HTTP client. Even so, `RANDOM_PORT` usually **does not catch production port 8080 conflicts**, since it asks the OS for any free port. If testing a fixed port or production networking, use a matching environment.

### 7.2. HTTP Parsers and Header Handling

MockMvc lets you populate headers, paths, query strings, and content directly on the mock request. It does not exercise the embedded server's parser handling **raw HTTP wire bytes**:

- Request-line and header size limits.
- Invalid headers or container-specific header normalization.
- Wire framing via `Transfer-Encoding: chunked` vs. `Content-Length`.
- Connection reuse, mid-request disconnects, or slow clients.
- Specific HTTP/1.1, HTTP/2, upgrade, or streaming mechanics.

**This does not mean MockMvc skips all URL/header checks.** Spring MVC still parses and resolves mappings, query params, and headers represented by the mock request; it only skips the real server's **HTTP connector/network parser**.

Even real HTTP tests using JDK `HttpClient` have limits: standard clients normalize requests and refuse to emit malformed raw headers. Testing low-level protocol parsers may require specialized socket/client tests or protocol security testing.

### 7.3. TLS, HTTPS, Certificates, and Proxies

MockMvc can simulate request attributes like scheme, secure flag, or forwarded headers for controllers/filters to inspect. However, it **performs no TLS handshakes or certificate verification**.

A real HTTP test calling `http://127.0.0.1:<port>` does **not** test HTTPS either. Testing real HTTPS requires configuring an SSL keystore/truststore, calling `https://...`, and validating certificates and client trust.

For reverse proxies, load balancers, and API gateways, even a localhost embedded server over real HTTP does not test:

- TLS termination at ingress.
- Real `X-Forwarded-*` / `Forwarded` header propagation from a proxy.
- Path rewriting, host routing, or gateway authentication.
- WAF rules, sticky sessions, rate limiting, retries, or proxy timeouts.
- DNS, cloud firewalls, service meshes, and network policies.

Verifying these requires tests in an environment containing the actual infrastructure components. MockMvc can test **application logic reacting to forwarded headers** when filter/handler config is present, yet it never proves the proxy sends the right headers in production.

### 7.4. Compression and Response Streaming

MockMvc can inspect content and response headers produced by MVC code, yet it does not replace real container compression/chunking tests. For instance, if gzip is configured on the server connector, send real HTTP with `Accept-Encoding: gzip` and verify compressed bytes/headers with an appropriate client.

Likewise, when APIs return large files, streaming bodies, Server-Sent Events, or multipart uploads, MockMvc verifies partial application logic, while **backpressure, client disconnects, timeouts, chunk boundaries, and network throughput** require tests over real transport or integrated environments.

Never use `content().string(...)` in MockMvc to claim the application handles 100 MB downloads over the network cleanly.

## 8. Spring Security and Servlet Filters: Configuration Makes the Difference

### 8.1. MockMvc Can Test Security

A common myth is: "MockMvc does not run Spring Security." In reality, with Spring Security Test integrated and the filter chain registered, MockMvc effectively tests authentication, authorization, 401/403 access denial, and CSRF.

With `@AutoConfigureMockMvc` in Spring Boot, `addFilters = true` is the default. For example:

```java
@AutoConfigureMockMvc(addFilters = true)
```

retains the matching Servlet Filters from the context. If the security starter is present, unauthenticated requests may be blocked before the controller—which can be the exact intended behavior.

In unit/MVC-slice tests, `@WithMockUser` or `SecurityMockMvcRequestPostProcessors.user(...)` / `csrf()` supply a security context and test CSRF tokens without running a real login or OIDC handshake.

### 8.2. Testing with Mock Authentication vs. Real Authentication Handshakes

`@WithMockUser` verifies **application authorization rules for a simulated principal**. It does not prove:

- Browser OAuth/OIDC redirects and authorization-code flows work.
- JWTs are signed properly by a real issuer and sent properly by clients.
- Session cookie flags, redirects, and SSO proxies work end-to-end.
- TLS protects cookies and tokens on the wire.
- The external identity provider or gateway is reachable and healthy.

Those contracts require integration/E2E tests at the right level. Still, there is no reason to discard security MockMvc tests: they are fast, focused, and excellent at catching access-control regressions.

### 8.3. Never Use `addFilters=false` to "Fix" a 403 Test

```java
@AutoConfigureMockMvc(addFilters = false)
```

allows requests to reach the controller while skipping the filter chain; such a test **no longer proves security filter behavior**. If an endpoint is protected, supply valid authenticated users, tokens, and CSRF per policy and assert both allowed and denied cases.

**Distinction:** excluding filters from `MockMvc` does not necessarily remove filter beans from the Spring context. This differs from component-scan `excludeFilters` on a test slice.

## 9. Transactions and Rollbacks: A Limit That Causes Serious Bugs

### 9.1. Test Transactions and Synchronous MockMvc

Spring TestContext can open a **test-managed transaction** when a test method is annotated `@Transactional` and a transaction manager is available. Afterward, that transaction rolls back by default.

With MockMvc running requests **synchronously on the test thread**, controller/service/repository code can join that transaction under compatible propagation settings. Consequently, DB mutations during `mockMvc.perform(...)` can roll back when the test finishes.

However, do not assume every mutation rolls back:

- `@Async` or off-thread execution does not inherit the test thread's `ThreadLocal` transaction.
- `REQUIRES_NEW` opens an independent transaction that commits.
- External queues, caches, files, and HTTP side effects never roll back with a database test transaction.
- Code using a different transaction manager may not join the test transaction.

### 9.2. Real HTTP: Client and Server Run on Different Threads/Transactions

Per Spring Boot documentation for `@SpringBootTest(RANDOM_PORT/DEFINED_PORT)`, the HTTP client and embedded server run on **separate threads**, so a transaction opened on the test thread **does not roll back** transactions executed on the server side.

Example:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@Transactional
class OrderHttpTest {
    // Sends a real HTTP POST to the server.
}
```

This is an **illustrative snippet**, not a complete test. `@Transactional` here cannot serve as automatic cleanup for a POST handled and committed in the server's own transaction. Data persists after the test finishes.

**Practical consequence:** migrating a test suite from MockMvc to real HTTP while keeping `@Transactional` can start polluting the database and causing order-dependent test failures.

### 9.3. Data Strategies for Real HTTP Tests

Pick an appropriate strategy:

- Use a dedicated test database/container, seeding and cleaning up via APIs or controlled administrative queries.
- Give parallel suites or workers isolated schemas/databases.
- Generate unique test IDs and clean up in `@AfterEach` or a fixture manager.
- Verify no background jobs or triggers interfere with cleanup order.
- Never point tests at a production database or share mutable developer tables.
- Do not abuse `@DirtiesContext` to "wipe the database": that annotation mainly resets the context cache and does not clean committed rows in external systems.

Especially for async flows, wait using deterministic conditions and bounded timeouts rather than fixed sleeps before asserting persisted state.

## 10. Async, Streaming, and Request Lifecycles

### 10.1. Spring MVC Async in MockMvc

A controller may return `Callable`, `DeferredResult`, or another async return type. In MockMvc, you typically test two phases:

```java
MvcResult pending = mockMvc
        .perform(get("/api/async"))
        .andExpect(request().asyncStarted())
        .andReturn();

mockMvc.perform(asyncDispatch(pending))
       .andExpect(status().isOk());
```

**This is an illustrative snippet** assuming an async `/api/async` endpoint exists; it needs imports `MockMvcResultMatchers.request` and `MockMvcRequestBuilders.asyncDispatch`. Do not copy it onto the synchronous controller in Section 6, which never starts async processing.

Over real HTTP, clients wait for the final response (or consume streamed chunks). Network timeouts, disconnects, or client-side cancellations can surface bugs invisible to MockMvc's `asyncDispatch`.

### 10.2. ThreadLocal, Security Context, and Request Attributes

While synchronous MockMvc usually runs on the test thread, asynchronous logic moves onto worker executors and requires proper propagation of security contexts, MDC logging, transactions, or request context. If MockMvc passes simply because everything ran on one thread while production uses async executors, propagation bugs will slip past.

A real HTTP test adds a client/server thread boundary, yet **still does not stress race conditions**. Concurrency risks need dedicated controlled tests, drawing conclusions only about conditions actually exercised.

### 10.3. Sessions and Cookies

MockMvc supports `MockHttpSession`, reading/writing cookies, and chaining requests by reusing sessions/cookies in tests. That is effective for verifying **application-level** session handling.

Still, it does not fully verify:

- Browser cookie storage/sending under `SameSite`, `Secure`, `Domain`, and `Path` rules over real networks.
- Load-balancer sticky sessions.
- Session replication / distributed session stores.
- Browser redirect chains, CORS preflight, and credential flags outside the server.
- TLS-only (`Secure`) cookie transmission.

Even a real HTTP client does not behave identically to a browser: JDK `HttpClient` requires explicit `CookieHandler` and redirect policies to mimic a browser's cookie jar and redirects. Inspect client settings and use browser-level tests when browser behavior is part of the contract.

## 11. Request URLs, Content Encoding, and Forwarded Headers

### 11.1. Paths/Queries/Encoding in MockMvc

You can write:

```java
mockMvc.perform(get("/api/search")
        .param("q", "cà phê")
        .header("X-Request-Id", "test-123"))
        .andExpect(status().isOk());
```

**This snippet assumes the endpoint exists**, not a standalone runnable example. `param(...)` populates logical request parameters on the mock Servlet request rather than percent-encoding a URI and transmitting it over TCP.

When bugs occur only with Unicode paths, spaces, `%` signs, encoded `/` characters, or very long query strings, add real HTTP tests using URIs built and encoded per contract. Embedded containers can handle encoded slashes, URI normalization, and size limits differently from mock requests.

### 11.2. Multipart Uploads

MockMvc provides `multipart(...)` to construct `MockMultipartFile` objects and check how controllers handle multipart arguments. It does not transmit real MIME multipart boundaries over an HTTP socket.

If bugs live in client multipart boundaries, upload size limits, container multipart parsers, large-file streaming, or proxy body caps, use a real HTTP client/server; if bugs live in controller validation or service calls from multipart handlers, MockMvc remains very effective.

### 11.3. Encoding and Charsets

MockMvc exercises Spring MVC converters using configured mock request/response encodings. Real HTTP additionally goes through client-side byte encoding of URIs/headers/bodies, server-side decoding, and response byte decoding. Therefore, to prove wire-level charset behavior, use an HTTP client and assert decoded Unicode strings.

The runnable example in Section 6 intentionally returns the Vietnamese string **“Xin chào Lan”** on both paths. When both tests pass, we know the JSON converter and HTTP test path handled that string properly **in those specific requests**. Do not assume every other encoding, locale, or Unicode normalization case works automatically.

## 12. Full Context Does Not Mean Real HTTP

A very common trap:

```java
@SpringBootTest
@AutoConfigureMockMvc
class FullContextTest {
    @Autowired MockMvc mvc;
}
```

It may load **every real bean** in the app, yet by default `@SpringBootTest` uses `WebEnvironment.MOCK` with no server socket. Conversely:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class HttpContextTest {
}
```

starts an embedded server. Yet if you use Mockito to replace `PaymentGateway` with a mock, real HTTP calls still do not test the production payment provider.

Keep **two independent axes** clear in test documentation:

1. **Spring context breadth:** controller-only slice, full context, or full context with selective overrides.
2. **Request transport:** in-process MockMvc or real HTTP over a server/port.

A test can be full context + MockMvc, full context + HTTP, or MVC slice + MockMvc. Never just slap the label "integration test" on a test and assume full coverage.

### 12.1. Non-Equivalent Combinations

| Combination | What You Can Conclude |
|---|---|
| `@WebMvcTest + MockMvc` | MVC mapping/converters/validation with slice-scoped beans/filters |
| `@SpringBootTest(MOCK) + MockMvc` | Full-context MVC pipeline, no socket |
| `@SpringBootTest(RANDOM_PORT) + HttpClient` | Full test context, embedded servlet container, and HTTP socket |
| `@SpringBootTest(RANDOM_PORT) + MockMvc` | If MockMvc is also auto-configured, `MockMvc.perform` remains in-process |
| Browser → staging ingress → service | Real browser/network/ingress per staging config, not automatically 100% identical to production |

## 13. Choosing Tests by Real Risk

### 13.1. When MockMvc Is Strong Enough

MockMvc is an ideal fit when verifying:

- Controller mappings and HTTP methods/paths.
- Spring MVC JSON serialization/deserialization.
- `@Valid`, argument conversion, and message conversion.
- `@ControllerAdvice` and exception-to-status mapping.
- Servlet Filters and Spring Security rules registered in MockMvc.
- Controller delegation to real services/repositories inside a full test context.
- 400/404/409 error contracts per API specification.
- Framework-level session flows and async dispatch logic.

Especially suited for fast CI feedback and daily development loops.

### 13.2. When Real HTTP Is Mandatory

Include at least a targeted set of `RANDOM_PORT`/HTTP tests for risks such as:

- Does the application boot an embedded server under its real configuration?
- Do real clients send the right URIs, methods, headers, and bodies?
- Do HTTP responses preserve expected status, content encoding, cookies, and redirects?
- Do server connectors, compression, timeouts, multipart size limits, and HTTP protocol behaviors match requirements?
- Proving database transactions behave properly across separate client/server threads.
- Bugs reproducible only across sockets, connection pools, or request-body streaming.
- Production HTTP client libraries configured with custom proxies or timeouts.

Pick a concise, high-value set of boundary tests; do not duplicate hundreds of MockMvc cases into hundreds of socket tests unless they add real defect-detection power.

### 13.3. When Localhost Real HTTP Is Still Not Enough

Add staging, E2E, or contract tests with matching infrastructure for:

- API gateways, ingress controllers, and path rewriting.
- HTTPS certificates, mTLS, and proxy authentication.
- Browser security and cross-origin (CORS) behaviors.
- Load balancers, horizontal scaling, and sticky sessions.
- Container images, Kubernetes readiness/liveness probes, and cloud secrets.
- DNS, network policies, firewalls, and production-specific topology.

Aim for a **clear, layered testing pyramid**, never claiming any single test type replaces all others.

## 14. Versions: Spring Boot 3.x, 4.x, and Client Choices

### 14.1. Imports in Spring Boot 3.x

The runnable example uses:

```java
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.web.servlet.MockMvc;
```

In Spring Boot 3.x, Servlet MVC apps typically use `spring-boot-starter-web` and tests use `spring-boot-starter-test`. Java 17+ is supported. If your app includes Spring Security, add security test support and configure auth/CSRF explicitly, because the Section 6 runnable example has **no Security dependency**.

### 14.2. Checking Packages and Starters When Moving to Spring Boot 4.x

Spring Boot 4 reorganizes MVC testing auto-configuration, for example:

```java
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
```

Web MVC production and testing starters belong to the new modular layout, such as `spring-boot-starter-webmvc` and `spring-boot-starter-webmvc-test`; verify versions/BOMs and docs for your active branch. Do not copy Boot 3 imports verbatim into Boot 4 and assume annotations were deleted.

**The core mental model stays the same:** MockMvc uses a mock Servlet pipeline with no socket; `RANDOM_PORT` starts a real embedded HTTP server. However, classpaths, modules, JUnit/Jackson versions, and imports change, so Section 6 explicitly targets **Spring Boot 3.x**.

### 14.3. WebFlux Is Not Servlet MVC

If an application uses **Spring WebFlux (reactive stack)** exclusively, `MockMvc` is not the equivalent tool for reactive handlers. For WebFlux, use `WebTestClient` bound to the application context or a live server.

Spring Framework also supports binding `WebTestClient` to `MockMvc` for MVC apps, which **does not automatically make it real HTTP**; what matters is whether the client is configured with **`bindToMockMvc`** or **`bindToServer`**.

**Never judge "realness" from the client's class name alone.** `WebTestClient` can run either simulated or live HTTP depending on how it is bound.

## 15. Common Pitfalls and Root-Cause Tracing

| Symptom | Possible Cause | How to Check/Fix |
|---|---|---|
| `Connection refused` calling localhost in a `MOCK` test | `@SpringBootTest(MOCK)` opens no server socket | Use MockMvc or switch to `RANDOM_PORT` + a real client |
| `@LocalServerPort` has no valid value | Embedded server not started or wrong import/version | Use `RANDOM_PORT`, verify config and port binding |
| MockMvc passes, real HTTP returns 404 | Different context path, encoding, URI, container config, or test setup | Compare raw HTTP requests, mappings, and port/context path |
| MockMvc passes, real HTTP times out | Network connector/client timeout or slow server thread/I/O | Check client timeouts, server logs, and blocking calls |
| HTTP 401/403 instead of 200/201 | Active security filter chain, missing auth, or missing CSRF | Supply auth/CSRF per policy; don't disable filters blindly |
| MockMvc 200 yet real HTTP 413 | Server or proxy body/header size limits | Test over real HTTP with controlled payload sizes |
| HTTPS client throws certificate error | Missing/misconfigured truststore, SNI, certificate, or TLS | Test real HTTPS; never cite MockMvc as TLS proof |
| `@Transactional` real HTTP test leaves rows behind | Test/client thread and server thread use separate transactions | Clean up database/fixtures explicitly; don't rely on test rollback |
| JSON differs on special characters | Charset mismatch across bytes/headers/client decoding | Compare `Content-Type` charset and raw/decoded response bodies |
| MockMvc filter header missing | Filter unregistered, `addFilters=false`, or `standaloneSetup` differs from Boot | Check filter chain/config; never assume filters always run |
| Using `RANDOM_PORT` yet still calling `mockMvc.perform` | MockMvc remains in-process | Point an HTTP client at `@LocalServerPort` |
| Suite slows down sharply after switching to real HTTP | Server startups, DB migrations, context cache misses | Keep a small set of boundary HTTP tests and fast MVC/unit suites |
| Green in IDE, red in CI | Differing JDK, port conflicts, dependencies, proxies, credentials, races, test selection | Run via wrapper; compare logs, test reports, and environments |
| WebFlux controller fails under MockMvc | Wrong web stack | Use `WebTestClient` with reactive configuration |
| HTTP 400 on invalid JSON | Message converter rejected the body before the controller | Inspect request bytes, content type, and resolved exception |
| Real HTTP passes yet staging fails | Missing proxy/TLS/ingress/env factors in localhost tests | Add environment-level tests at the matching boundary |

### 15.1. Debug Layer by Layer Instead of Patching the Wrong Place

1. Confirm JUnit/Gradle/Maven **actually ran** the test and did not skip it.
2. Confirm the application context starts cleanly. On `Failed to load ApplicationContext`, read the bean/config root cause first.
3. Identify the **request path**: `MockMvc.perform` or an HTTP client hitting host/port?
4. If using real HTTP, verify `@LocalServerPort`, URI, context path, connector, and client timeouts.
5. Check Servlet Filters and Spring Security before MVC mappings.
6. Check routes, path/query encoding, JSON converters, and validation.
7. Check service/repository fixtures, transactions/threads, and cleanup.
8. Check response status, headers, and body at the right boundary.
9. If failures happen only in staging/production, inspect TLS, proxies, ingress, distributed state, and network policies.

Diagnose each failure at the layer where it originates. A TCP `Connection refused` cannot be fixed by editing `jsonPath(...)`, and a `NoSuchBeanDefinitionException` is not caused by lacking a real HTTP client.

## 16. Practice Exercises and Answers

### Exercise A — A Test with Full Spring Context, Yet No Real HTTP

You see:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ProductsTest {
    @Autowired MockMvc mvc;
}
```

Question: does this test class start an HTTP server by default? Does it run real services?

**Answer:** by default it opens no server socket because `@SpringBootTest` uses `webEnvironment=MOCK`. However, services are still real beans in the application context. Two independent axes apply: **context breadth** and **request path**.

### Exercise B — Testing a Random Port and Real Response

How must the configuration change?

**Answer:** use `@SpringBootTest(webEnvironment = RANDOM_PORT)`, inject `@LocalServerPort`, send requests via `HttpClient` to `http://127.0.0.1:<port>`, and assert status/headers/body. Do not simply add `@LocalServerPort` to a `MOCK` test.

### Exercise C — Filter Not Running in MockMvc

A test sets `@AutoConfigureMockMvc(addFilters = false)` and expects to prove an audit filter sets a header. Why does the assertion fail?

**Answer:** you explicitly disabled registering context filters into `MockMvc`. Re-enable filter registration and ensure the filter bean/chain is valid; optionally add a real HTTP test to verify container registration.

### Exercise D — `@Transactional` Failing to Clean Data

A real HTTP POST test writes to a repository; the test method has `@Transactional`, yet the row stays in the database. Is Spring TestContext rollback broken?

**Answer:** not necessarily. The server handles the request in its own thread and transaction; the client test thread's transaction does not roll back server transactions. Use proper test fixtures, cleanup, or isolated schemas.

### Exercise E — Bug Appearing Only Over HTTPS Behind a Reverse Proxy

Should you prioritize MockMvc, localhost HTTP, or a staging gateway?

**Answer:** MockMvc can check controller/filter logic on forwarded headers; localhost HTTP checks the embedded connector yet **proves neither TLS termination nor proxy behavior**. Testing HTTPS/proxy issues requires an environment and client passing through a real gateway/TLS layer.

### Exercise F — Does `WebTestClient` Always Send Real HTTP?

**Answer:** no. `WebTestClient` supports binding to a mock application/`MockMvc` as well as binding to a live server. Always check how it is configured: only **`bindToServer`** targeting a live host/port exercises the HTTP network path.

### Checklist Before Concluding a Web Test Is Sufficient

- [ ] Clearly state whether the context is an MVC slice or a full Spring Boot context.
- [ ] Clearly state whether requests use in-process `MockMvc` or a real HTTP client/server.
- [ ] For MockMvc, verify whether filters/security are registered.
- [ ] For real HTTP, verify port, base URL, context path, and client timeouts.
- [ ] Never use mock HTTP to claim TCP/TLS/HTTP2/container connector coverage.
- [ ] Never use localhost real HTTP to claim proxy/load-balancer/internet coverage.
- [ ] Include explicit assertions on status, headers, JSON fields, and business contracts.
- [ ] Cover negative cases: malformed bodies, 4xx errors, and authentication where required.
- [ ] Align test transactions and cleanup with actual thread and connection boundaries.
- [ ] Test async, streaming, and multipart at the appropriate layer.
- [ ] Never disable Spring Security/CSRF unintentionally.
- [ ] Confirm whether the project uses Servlet MVC or WebFlux.
- [ ] Keep Boot 3.x vs. Boot 4.x dependencies and imports consistent.
- [ ] Never hit production endpoints or use production credentials in tests.
- [ ] Run tests with the project's JDK/build wrapper and confirm exact counts in CI reports.

## 17. Summary

**MockMvc verifies Spring MVC request handling using a mock Servlet API—it does not verify an HTTP connection to a real server.** It can still execute real controllers, services, repositories, and filters per configuration, making it powerful for MVC-level API contracts.

**Real HTTP with `@SpringBootTest(RANDOM_PORT)`** adds an embedded server, listening port, sockets, HTTP transport, and client/server thread boundaries—at the cost of heavier startup, separate server transactions, and stricter fixture cleanup. Even localhost real HTTP does not verify proxies, TLS, gateways, or cloud infrastructure unless they are present in the test environment.

The strongest approach is **deliberate combination**: fast unit, MVC slice, and MockMvc tests for rapid feedback, a focused suite of real HTTP integration tests for transport/container boundaries, and environment-level tests tailored to deployment infrastructure.

## Official References

- [Spring Framework — MockMvc Overview](https://docs.spring.io/spring-framework/reference/testing/mockmvc/overview.html): MockMvc invokes `DispatcherServlet` via mock Servlet APIs without a running server.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): Spring MVC testing options, setup, and `MockMvcTester`/`WebTestClient` bridges.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `MOCK`, `RANDOM_PORT`, `DEFINED_PORT`, transaction caveats, and `TestRestTemplate`/`WebTestClient`.
- [Spring Boot 3.5 — AutoConfigureMockMvc Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/web/servlet/AutoConfigureMockMvc.html): `addFilters` and MockMvc configuration.
- [Spring Boot 4 — AutoConfigureMockMvc Javadoc](https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/webmvc/test/autoconfigure/AutoConfigureMockMvc.html): Spring Boot 4 package updates.
- [Spring Framework — MockMvc Async Requests](https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/async-requests.html): testing `asyncStarted` and `asyncDispatch`.
- [Spring Security — MockMvc Test Setup](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html): integrating Spring Security with MockMvc.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): the HTTP client used in the socket-based example.