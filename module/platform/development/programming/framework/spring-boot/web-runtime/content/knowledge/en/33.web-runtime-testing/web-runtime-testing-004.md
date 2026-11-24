# @SpringBootTest with MOCK, RANDOM_PORT, and DEFINED_PORT

## 1. Learning Objectives and Differentiation Rules

`@SpringBootTest` is the annotation used to initialize a **Spring Boot ApplicationContext close to the real application** inside a test. This annotation does not automatically mean “start Tomcat,” “send HTTP over the network,” or “run end-to-end.” The **`webEnvironment`** attribute determines whether the test receives a **simulated web environment**, a **real web server on a random port**, or a **real web server on a defined port**.

This lesson belongs to the **Web runtime testing** group of the **Spring Boot - web-runtime** module, with the objectives:

1. Accurately distinguish `MOCK`, `RANDOM_PORT`, `DEFINED_PORT`, and also know `NONE` to avoid incomplete understanding.
2. Choose `MockMvc`/`WebTestClient` for a mock environment and `TestRestTemplate`/`WebTestClient`/a real HTTP client for a running-server environment.
3. Understand the difference between running a Spring MVC controller through mock servlet infrastructure and running the full embedded web server over a TCP socket.
4. Build a **Java 17 + Spring Boot 3.3.5 + Maven + JUnit Jupiter 5** project with three runnable test groups.
5. Properly use `@AutoConfigureMockMvc`, `@AutoConfigureWebTestClient`, `@LocalServerPort`, and `server.port` configuration according to purpose.
6. Know when testing the real HTTP stack is necessary (network binding, filters, cookies, HTTP status, server-specific behavior, compression, TLS, proxy).
7. Recognize the `@Transactional` trap: test rollback on the test thread **does not roll back** transactions in the server thread when called over real HTTP.
8. Organize tests without port conflicts in CI, without confusing “random” with “changing port per method,” and manage the Spring test context cache.

**Quick recall rules:**

- **`MOCK` (default):** full Spring application context, **does not start an embedded HTTP server**.
- **`RANDOM_PORT`:** full context + **real embedded server**, OS selects an available port.
- **`DEFINED_PORT`:** full context + **real embedded server**, uses `server.port` or default `8080`.
- **`NONE`:** full context but **no web environment**.

These descriptions follow **Spring Boot 3.3.x**; for other Spring Boot versions, check the corresponding packages and test client APIs. Do not apply Boot 4.x test APIs (which may change modules/packages) directly into a Boot 3.3 project.

## 2. What Does @SpringBootTest Start?

`@SpringBootTest` uses Spring Boot infrastructure to build an ApplicationContext (created via the `SpringApplication` mechanism). It typically locates the main `@SpringBootApplication` or `@SpringBootConfiguration` configuration by searching upward from the test class's package to parent packages.

~~~text
JUnit Jupiter runs test class
         |
         v
@SpringBootTest + Spring TestContext
         |
         +--> find @SpringBootApplication
         +--> load application.properties / test properties / profiles
         +--> wire dependency injection, services, controllers, auto-configs
         +--> determine webEnvironment
                   |
                   +--> MOCK:       mock web context, DOES NOT open port
                   +--> RANDOM_PORT: web context + auto-chosen HTTP listener port
                   +--> DEFINED_PORT:web context + fixed HTTP listener port
                   '--> NONE:       non-web ApplicationContext
         |
         v
Execute @Test and assertions
         |
         v
Context may be CACHED for reuse by other tests
~~~

Crucial point: **full context** only speaks to the scope of beans/auto-configuration loaded. Whether **requests go through the network/embedded container** is a separate choice.

A `@SpringBootTest(webEnvironment=MOCK)` still loads `@Service`, `@Repository`, transaction managers, event listeners, filters, security chains, and configured external dependencies. It is **not** the same as instantiating a `@Controller` with `new` in a unit test. Conversely, `@WebMvcTest` is a web slice test, not a full context.

### 2.1. Spring MVC or Spring WebFlux?

Spring Boot inspects the classpath to determine the web application type:

- **Spring MVC/Servlet present:** normally creates an MVC web context and embedded Tomcat/Servlet server when using a real port.
- **Only Spring WebFlux present:** creates a reactive web context; with the default Boot WebFlux starter, typically uses Reactor Netty when running a real server.
- **Both MVC and WebFlux present:** Boot 3.3 **prioritizes MVC** unless overridden via `spring.main.web-application-type=reactive`.
- **Both web stacks absent:** `MOCK` may fall back to a non-web ApplicationContext.

Injecting `WebClient` into an MVC project **does not automatically switch** the application to WebFlux. When writing tests, identify the **inbound runtime** in use to choose the right test client and expectations.

## 3. Comparison Table of the Three Main Modes

| Criterion | `MOCK` | `RANDOM_PORT` | `DEFINED_PORT` |
| --- | --- | --- | --- |
| `@SpringBootTest` default? | **Yes** | No | No |
| Starts full ApplicationContext? | Yes | Yes | Yes |
| Starts real embedded HTTP server? | **No** | **Yes** | **Yes** |
| Opens TCP port / receives real HTTP? | **No** | **Yes** | **Yes** |
| Chosen port | No test-listening port | `server.port=0` / available port | `server.port` or 8080 |
| Typical MVC test client | `MockMvc` | `TestRestTemplate` or real HTTP client | `TestRestTemplate` or real HTTP client |
| Typical reactive test client | `WebTestClient` bound-to-context | `WebTestClient` bound-to-server | `WebTestClient` bound-to-server |
| Use `@LocalServerPort` to read real port? | Not suitable | **Yes** | **Yes** |
| Tests network socket/embedded container? | No | Yes | Yes |
| Tests MVC routing/filter/serialization? | Yes, at mock servlet level | Yes, through HTTP runtime | Yes, through HTTP runtime |
| Port conflict risk in CI | None from embedded HTTP listener | Lower; OS assigns port | **High** if port collides |
| HTTP client and server run on different threads? | No real HTTP server | **Yes** | **Yes** |
| `@Transactional` rolls back server-side DB writes on HTTP call? | Possible on same test thread with sync mock request | **Does not auto-rollback** | **Does not auto-rollback** |
| Typical startup speed | Does not start server, usually lighter | Adds server start/stop overhead | Adds server start/stop overhead |
| When preferred | MVC handler behavior, validation, security/filter logic | Full HTTP stack integration, CI | Fixed port required in a controlled environment |

**`RANDOM_PORT` does not mean every `@Test` gets a new port.** The port is chosen when the server/context starts; multiple test methods sharing the same ApplicationContext normally share one port. Context caching can cause a group of test classes to share the same context and bound port.

**`DEFINED_PORT` does not mean the port is always 8080.** You can set `server.port=18081` or a value from a profile/config. If you deliberately set `server.port=0`, the OS still selects an ephemeral port despite the annotation being named `DEFINED_PORT`; what matters is the effective server property.

## 4. What Is WebEnvironment.NONE Used For?

Beyond the three modes in the title, Spring Boot provides:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class SomeContextTests {
    // ...
}
~~~

`NONE` creates a non-web ApplicationContext via SpringApplication, providing neither a mock servlet environment nor an embedded HTTP server. Useful when solely checking wiring/config/business services and wanting to skip the web environment. `NONE` is **not** a variant of `MOCK`: `MOCK` can create a mock web context to support MockMvc/WebTestClient, whereas `NONE` requests no web layer at all.

If a service explicitly depends on web-only beans, a `NONE` test may need extra configuration or be unsuitable. Do not pick `NONE` merely because a test does not send HTTP requests if app initialization requires essential web dependencies.

## 5. @SpringBootTest Defaults to MOCK; @AutoConfigureMockMvc Does Not Open a Port

Two annotations often appear together:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class GreetingMockTest {
    // ...
}
~~~

This means:

- `@SpringBootTest`: loads the **full context**.
- `webEnvironment` omitted: defaults to **`MOCK`**.
- `@AutoConfigureMockMvc`: configures a `MockMvc` bean to call into MVC infrastructure **without needing a TCP listener**.

`MockMvc` constructs simulated request/response objects at the Servlet MVC layer: you call `mvc.perform(get("/api/hello"))`, and Spring DispatcherServlet/handlers process it and return `MvcResult`. The outcome verifies status, headers, body, exception mapping, and filters if configured to run — yet **there is no DNS/TCP connect/TLS handshake/network proxy**.

### 5.1. What MOCK Tests Well

- `@RequestMapping`, HTTP method/path, `@RequestParam`, `@PathVariable`.
- JSON binding/serialization through MVC converters.
- Validation/exception handlers/response status.
- Servlet filters and Spring Security filters when properly integrated into mock tests.
- Controller/service wiring inside the Spring ApplicationContext.
- Business behavior that does not depend on real sockets.

### 5.2. What MOCK Does Not Prove

- That real embedded Tomcat/Jetty/Netty bound to the port properly.
- TCP/TLS/HTTP2/WebSocket Upgrade/chunked network semantics.
- Servlet container-level error page behavior (e.g., customized container-rendered error pages).
- Reverse proxy/gateway routing, firewalls, and DNS.
- Browser cookie policies/real redirects under a real network runtime.
- Connection timeouts, keep-alive, socket resets, compression, and real server configuration.

If a bug only manifests when requests traverse the connector/TLS/proxy, `MockMvc` can PASS while deployment still FAILS.

## 6. Shared MVC Lab: Java 17, Spring Boot 3.3.5, Maven

This is a **complete runnable project**, consisting of an application with REST endpoints and four test classes:

1. `GreetingMockTest` using `MOCK + MockMvc`.
2. `GreetingRandomPortTest` using `RANDOM_PORT + TestRestTemplate`.
3. `GreetingDefinedPortTest` using `DEFINED_PORT + TestRestTemplate`.
4. `GreetingNonWebTest` using `NONE` for comparison.

**Requirements:** JDK 17+, Maven 3.x, Internet access for initial Maven dependencies. To prevent tests from colliding with an already running server, stop any applications occupying port 18081 before running the full test suite.

### 6.1. Directory Structure

~~~text
spring-boot-web-environment-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/webtest/
    │   │   ├── WebEnvironmentApplication.java
    │   │   ├── GreetingService.java
    │   │   ├── GreetingResponse.java
    │   │   ├── GreetingRequest.java
    │   │   └── GreetingController.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/com/example/webtest/
            ├── GreetingMockTest.java
            ├── GreetingRandomPortTest.java
            ├── GreetingDefinedPortTest.java
            └── GreetingNonWebTest.java
~~~

Test classes live in the **same package** or a subpackage of the main class so `@SpringBootTest` locates `@SpringBootApplication` automatically. If tests are placed in an unrelated package, use `@SpringBootTest(classes=WebEnvironmentApplication.class)` or fix the package structure.

### 6.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>spring-boot-web-environment-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

- `spring-boot-starter-web` uses Spring MVC and embedded Tomcat.
- `spring-boot-starter-test` provides Spring Test, Spring Boot Test, MockMvc APIs, JUnit Jupiter, AssertJ, and Mockito in test scope.
- The project **omits WebFlux**, demonstrating that with MVC you can use `MockMvc` for `MOCK` and `TestRestTemplate` for real ports.
- Spring Boot parent manages JUnit/Spring/Test dependency versions; avoid mixing redundant JUnit 4/5 versions.
- Java 17 supports `record` for representing request/response DTOs.

### 6.3. application.properties

**`src/main/resources/application.properties`:**

~~~properties
spring.application.name=web-environment-lab

# INTENTIONALLY omit server.port.
# - DEFINED_PORT without override uses default 8080.
# - In the lab we override DEFINED_PORT to 18081 in the annotation.
# - RANDOM_PORT picks an ephemeral port.
# - MOCK does not open an embedded HTTP listener.
~~~

In real tests, Spring Boot merges properties from the application, test annotations, system/environment, active profiles, and other sources by precedence. External config can conflict — log effective test properties when debugging.

### 6.4. Main Application

**`src/main/java/com/example/webtest/WebEnvironmentApplication.java`:**

~~~java
package com.example.webtest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebEnvironmentApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebEnvironmentApplication.class, args);
    }
}
~~~

### 6.5. Service Containing Business Logic

**`src/main/java/com/example/webtest/GreetingService.java`:**

~~~java
package com.example.webtest;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    public String greeting(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

A simple service lets tests observe the full context genuinely injecting the bean. Production apps may call DBs/external APIs; extending to those requires test data and dependency isolation.

### 6.6. Request/Response DTOs

**`src/main/java/com/example/webtest/GreetingRequest.java`:**

~~~java
package com.example.webtest;

public record GreetingRequest(String name) {
}
~~~

**`src/main/java/com/example/webtest/GreetingResponse.java`:**

~~~java
package com.example.webtest;

public record GreetingResponse(String message) {
}
~~~

Jackson (via `starter-web`) serializes the record to JSON `{"message":"Hello, Lan!"}` and deserializes request JSON like `{"name":"An"}` into `GreetingRequest`. JSON whitespace may vary, while logical fields must match.

### 6.7. Controller with GET, POST, and 400 Error

**`src/main/java/com/example/webtest/GreetingController.java`:**

~~~java
package com.example.webtest;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class GreetingController {

    private final GreetingService service;

    public GreetingController(GreetingService service) {
        this.service = service;
    }

    @GetMapping("/hello")
    public GreetingResponse hello(
            @RequestParam(defaultValue = "World") String name) {
        return new GreetingResponse(service.greeting(name));
    }

    @PostMapping("/echo")
    public GreetingResponse echo(@RequestBody GreetingRequest request) {
        return new GreetingResponse(
                service.greeting(request.name()));
    }

    @GetMapping("/required")
    public ResponseEntity<String> required(
            @RequestParam("code") String code) {
        return ResponseEntity.ok(code);
    }
}
~~~

**API Contract:**

| Request | Expected Status | Response |
| --- | --- | --- |
| `GET /api/hello` | 200 | JSON message `Hello, World!` |
| `GET /api/hello?name=Lan` | 200 | JSON message `Hello, Lan!` |
| `POST /api/echo` body `{"name":"An"}` | 200 | JSON message `Hello, An!` |
| `GET /api/required?code=OK` | 200 | text `OK` |
| `GET /api/required` missing code | 400 | Error body per MVC/error handling |

**Do not hardcode the JSON error body** in this lesson's tests because error response structure can depend on Boot exception handling, content negotiation, and container. Only assert status 400 for missing required param.

## 7. Test 1 — MOCK + MockMvc (No Embedded Server)

**`src/test/java/com/example/webtest/GreetingMockTest.java`:**

~~~java
package com.example.webtest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class GreetingMockTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void getHelloUsesMvcRequestMapping() throws Exception {
        mvc.perform(get("/api/hello").param("name", "Lan"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message")
                        .value("Hello, Lan!"));
    }

    @Test
    void postEchoDeserializesJson() throws Exception {
        mvc.perform(post("/api/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"An\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message")
                        .value("Hello, An!"));
    }

    @Test
    void missingRequiredParameterIsBadRequest() throws Exception {
        mvc.perform(get("/api/required"))
                .andExpect(status().isBadRequest());
    }
}
~~~

**What is tested here:**

1. `@SpringBootTest(webEnvironment=MOCK)` creates the full application context without **opening an HTTP port**.
2. `@AutoConfigureMockMvc` provides `MockMvc`, supporting testing MVC dispatch/parameter binding and Jackson serialization.
3. `.param("name","Lan")` simulates a query parameter; no HTTP client socket is created.
4. `jsonPath("$.message")` checks the JSON **field**, avoiding whitespace/order sensitivity.
5. Missing required `code` is mapped by Spring MVC to HTTP 400 per request mapping.
6. Filters/security can run inside MockMvc if properly configured; `@AutoConfigureMockMvc(addFilters = false)` skips filters and can mask an authorization bug.
7. The test does not prove Tomcat started, because no embedded server exists at all.

### 7.1. Shorter Syntax Without Changing Mode

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class DefaultMockEnvironmentTest {
    // @SpringBootTest defaults to MOCK.
}
~~~

The snippet above only reminds you of the default and is **not a test class with assertions**. In the lab project, `GreetingMockTest` is the actually executed class. Do not add this empty class if you want a suite consisting solely of verified test cases.

### 7.2. How Is a Mock Context Still “Full”?

In a real project, valid `@Component`/`@Service`/`@Repository`/`@Configuration` beans can all be instantiated in the context. If a service calls a real external API during initialization, a `MOCK` test can still fail because real dependencies **are not mocked automatically**. To isolate dependencies, deliberately use test bean overrides, Testcontainers/WireMock/MockWebServer, or dedicated profiles.

This is the key difference from `@WebMvcTest(GreetingController.class)`: `@WebMvcTest` configures only **an MVC slice** and typically needs mocks/imports for `GreetingService`. With `@SpringBootTest(MOCK)`, the full real service is injected even though requests do not traverse the network.

## 8. Test 2 — RANDOM_PORT + TestRestTemplate (Real HTTP)

**`src/test/java/com/example/webtest/GreetingRandomPortTest.java`:**

~~~java
package com.example.webtest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "server.address=127.0.0.1")
class GreetingRandomPortTest {

    @LocalServerPort
    private int port;

    @Autowired
    private TestRestTemplate restTemplate;

    @Test
    void actualHttpServerResponds() {
        assertThat(port).isGreaterThan(0);

        String url = "http://127.0.0.1:" + port
                + "/api/hello?name=Lan";

        ResponseEntity<GreetingResponse> response =
                restTemplate.getForEntity(
                        url, GreetingResponse.class);

        assertThat(response.getStatusCode().is2xxSuccessful())
                .isTrue();
        assertThat(response.getBody()).isNotNull();
        assertThat(response.getBody().message())
                .isEqualTo("Hello, Lan!");
    }

    @Test
    void serverReturnsHttp400ForMissingParam() {
        String url = "http://127.0.0.1:" + port
                + "/api/required";

        ResponseEntity<String> response =
                restTemplate.getForEntity(url, String.class);

        assertThat(response.getStatusCode().value())
                .isEqualTo(400);
    }
}
~~~

**Meaning:**

1. `RANDOM_PORT` starts **real Tomcat** and binds to an OS-chosen port.
2. `@LocalServerPort` in Boot 3.3 has package **`org.springframework.boot.test.web.server.LocalServerPort`**; it is injected once the server has started.
3. `TestRestTemplate` is a test-oriented HTTP client; here we use an absolute URL to clearly show the **real port**.
4. `@SpringBootTest(properties = "server.address=127.0.0.1")` binds the listener to localhost so the lab does not expose itself on all network interfaces.
5. The HTTP request travels TCP → Tomcat → Servlet filters → DispatcherServlet → Controller → JSON response.
6. If the app also has a management server on a **separate port**, `RANDOM_PORT` mode can also give the management server a **separate random port**, not necessarily equal to the application port.
7. `assertThat(port).isGreaterThan(0)` does not check for port 8080 because the ephemeral port is non-deterministic.

### 8.1. RANDOM_PORT and server.port=0

Spring Boot implements the random port concept with configuration equivalent to `server.port=0` for the test web server. `0` instructs the server to ask the OS for **an available port on bind**, not that the real port will literally be 0.

If `application.properties` has `server.port=8080` while the test uses `RANDOM_PORT`, test infrastructure requests a random port per the mode; do not compute the base URL from property 8080. Use `@LocalServerPort` or a Boot-configured test client.

### 8.2. Is TestRestTemplate Available?

In **Spring Boot 3.3** with `spring-boot-starter-test` and `spring-boot-starter-web` as in the lab, `TestRestTemplate` can be autowired in running-server tests. It has “test-friendly” semantics: normally it does not throw an exception just because the server returned 4xx/5xx; you inspect status/body via `ResponseEntity`.

In a Spring Boot **4.x** project, modules/packages/client auto-configuration may differ; do not copy `org.springframework.boot.test.web.client.TestRestTemplate` without checking the version. This lesson pins **3.3.5**.

### 8.3. Can Standard Java Clients Be Used?

Yes. Once a real port is open, any compatible HTTP client can send requests — including JDK 17 `java.net.http.HttpClient`, WebClient, REST Assured, or curl from another process. `TestRestTemplate` is just a convenience, not what makes the real server run.

The snippet below goes **inside a test method that has the injected `port` variable**, not as a standalone source file:

~~~java
java.net.http.HttpClient client =
        java.net.http.HttpClient.newHttpClient();

java.net.http.HttpRequest request =
        java.net.http.HttpRequest.newBuilder(
                java.net.URI.create(
                        "http://127.0.0.1:" + port + "/api/hello"))
                .GET()
                .build();

java.net.http.HttpResponse<String> response =
        client.send(request,
                java.net.http.HttpResponse.BodyHandlers.ofString());

// response.statusCode() == 200
// response.body() contains JSON field "message"
~~~

JDK `HttpClient` can be used when you want to verify HTTP-layer details without depending on `TestRestTemplate`. Set connect/request timeouts so tests do not hang indefinitely if the server fails.

## 9. Test 3 — DEFINED_PORT + TestRestTemplate (Fixed Port)

**`src/test/java/com/example/webtest/GreetingDefinedPortTest.java`:**

~~~java
package com.example.webtest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.DEFINED_PORT,
        properties = {
                "server.address=127.0.0.1",
                "server.port=18081"
        })
class GreetingDefinedPortTest {

    @LocalServerPort
    private int port;

    @Autowired
    private TestRestTemplate restTemplate;

    @Test
    void predefinedPortIsActuallyUsed() {
        assertThat(port).isEqualTo(18081);

        String url = "http://127.0.0.1:" + port
                + "/api/hello?name=An";

        ResponseEntity<GreetingResponse> response =
                restTemplate.getForEntity(
                        url, GreetingResponse.class);

        assertThat(response.getStatusCode().value())
                .isEqualTo(200);
        assertThat(response.getBody()).isNotNull();
        assertThat(response.getBody().message())
                .isEqualTo("Hello, An!");
    }
}
~~~

**Points to remember:**

- `DEFINED_PORT` also starts real Tomcat just like `RANDOM_PORT`, differing only in **how the port is chosen**.
- `server.port=18081` is set via test properties so it does not collide with the dev server's default `8080`. Even so, if another process uses 18081, the test still fails to bind.
- `@LocalServerPort` still reads the actual server port; it is not exclusive to `RANDOM_PORT`.
- If `server.port=18081` is omitted and no other config exists, `DEFINED_PORT` uses `8080` per Boot default.
- If you deliberately set `server.port=0` with `DEFINED_PORT`, the embedded server may still bind an ephemeral port; do not abuse the mode name to deduce the actual bound value.

### 9.1. When Is DEFINED_PORT Valuable?

- An external test fixture/gateway must call an exact fixed host:port.
- A test topology involves multiple local services, each with an explicitly allocated port.
- Testing the behavior of a specific `server.port` configuration.

**Do not use it as a CI default** when multiple jobs run on the same host. Port conflict/flakiness is a significant risk. For pure HTTP integration tests, `RANDOM_PORT` is usually more suitable.

### 9.2. “Port 18081 was already in use” Error

That is a web server **bind failure**, typically occurring while creating the ApplicationContext, **before the test method body runs**. Do not try to fix it by increasing `TestRestTemplate` timeouts or blindly adding `@DirtiesContext`; check what occupies the port, run tests sequentially, switch to `RANDOM_PORT`, or allocate dedicated ports cleanly.

## 10. Test 4 — NONE to Show No Web Environment Needed

**`src/test/java/com/example/webtest/GreetingNonWebTest.java`:**

~~~java
package com.example.webtest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class GreetingNonWebTest {

    @Autowired
    private GreetingService service;

    @Test
    void serviceCanRunWithoutWebServer() {
        assertThat(service.greeting("Lan"))
                .isEqualTo("Hello, Lan!");
    }
}
~~~

`NONE` still loads the Spring beans needed by the app and can inject `GreetingService`, yet **provides neither a mock Servlet environment nor an embedded server**. In the simple lab project, the service has no web runtime dependencies, so the test runs. For real apps whose beans initialize with servlet request/session dependencies, appropriate configuration is required and `NONE` may not fit.

**You cannot use `MockMvc` the way a `MOCK` test does just because `@SpringBootTest` is present**, because `NONE` does not supply the required web context.

## 11. Building, Running, and Reading Output

In the `spring-boot-web-environment-lab` directory:

~~~bash
mvn clean test
~~~

The four `*Test.java` classes are discovered by Maven Surefire/JUnit Jupiter; the expected test set is:

- `GreetingMockTest`: 3 test methods.
- `GreetingRandomPortTest`: 2 test methods.
- `GreetingDefinedPortTest`: 1 test method.
- `GreetingNonWebTest`: 1 test method.

**Total: 7 test methods.** If the source code/properties remain intact and no process occupies port 18081, the expected outcome is **7 tests PASS, 0 failures, 0 errors**. The console shows Spring Boot startup logs, Tomcat “started on port(s)” for real-port modes, and the Maven test summary; do not hardcode entire stdout because log ordering, JDK/OS, and timing vary.

Example meaning of output (illustrative, not byte-for-byte):

~~~text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0

BUILD SUCCESS
~~~

When needing to run individual cases:

~~~bash
mvn -Dtest=GreetingMockTest test
mvn -Dtest=GreetingRandomPortTest test
mvn -Dtest=GreetingDefinedPortTest test
mvn -Dtest=GreetingNonWebTest test
~~~

**Bash/Linux and Windows PowerShell:** the one-line Maven commands above all express running one test class; how the shell parses `-Dtest=...` may require quoting in certain environments.

### 11.1. Trying the Real Application with curl

Manual application startup (not a test):

~~~bash
mvn spring-boot:run
~~~

Because `application.properties` does not set `server.port`, the dev app typically opens `8080`:

~~~bash
curl -i http://127.0.0.1:8080/api/hello?name=Lan
~~~

Expected status 200, JSON containing `"message":"Hello, Lan!"`. **This is a manual check of the running app**, unrelated to whether `MOCK` tests need to open a port. Stop the app before running a `DEFINED_PORT` test if the app is configured on the same test port.

### 11.2. Do Not Conclude a MOCK Test Bound a Port from Bean Logs

`@SpringBootTest(MOCK)` still logs Spring context startup and may instantiate many web-related beans. However, proving the server bound a real port requires server lifecycle/HTTP exchange in a running-server mode. `@LocalServerPort` should not be injected into a `MOCK` test expecting a meaningful port number.

## 12. @LocalServerPort and Common Confusions

In Spring Boot 3.3:

~~~java
import org.springframework.boot.test.web.server.LocalServerPort;
~~~

`@LocalServerPort` is a utility injecting the **actual HTTP port of the embedded web server** into a test. Commonly used with `RANDOM_PORT` and usable with `DEFINED_PORT`.

~~~java
@LocalServerPort
int port;
~~~

It relies on the runtime value **`local.server.port`** after the embedded server has started.

**Do not confuse three values:**

- `server.port`: property **requesting** the server to bind a port; if 0, asks the OS to choose.
- `local.server.port`: the **actual** port after the server has bound.
- `management.server.port` / `local.management.port`: management port if the management server opens separately.

If the application sets `management.server.port` different from the application server port, especially under `RANDOM_PORT`, the management server may receive a **different random port**. To call management APIs, resolve `@LocalManagementPort`/`local.management.port` separately in the proper environment rather than mistakenly using the application's `@LocalServerPort`.

### 12.1. Do Not Read local.server.port Too Early

`local.server.port` is only determined **after the embedded server finishes binding**. Using `@Value("${local.server.port}")` inside an application bean instantiated **before** the server starts may fail because the property is not ready yet. The safe approach is reading `@LocalServerPort` in integration tests after the context has started, or listening to `WebServerInitializedEvent` if actually needed at runtime.

### 12.2. Why Not Hardcode 8080 in RANDOM_PORT?

~~~java
// Wrong when testing webEnvironment=RANDOM_PORT:
String url = "http://localhost:8080/api/hello";
~~~

The ephemeral port usually **differs from 8080**, and another dev server might occupy 8080. Write:

~~~java
// Snippet inside a test with @LocalServerPort int port:
String url = "http://127.0.0.1:" + port + "/api/hello";
~~~

or use Boot-managed `TestRestTemplate` with relative URIs when an appropriate root URI is configured.

## 13. MockMvc, WebTestClient, and TestRestTemplate: Choosing the Right Client

| Test Client | Mock Environment? | Real HTTP Server? | Designed For |
| --- | --- | --- | --- |
| `MockMvc` | **Yes**, MVC layer | Does not call over network itself | Spring MVC request handling |
| `TestRestTemplate` | Not used as mock Servlet request | **Yes**, HTTP | Boot 3.3 running-server integration tests |
| `WebTestClient` bound-to-application-context | **Yes**, especially WebFlux mock | No | Reactive handler/router tests |
| `WebTestClient` bound-to-server | Needs no mock backend | **Yes** | Reactive and HTTP integration tests when dependencies support it |
| JDK `HttpClient`, curl, REST Assured | No (unless custom adapter attached) | **Yes** | Network-level HTTP tests |

### 13.1. MockMvc Is Not Mockito

- **Mockito**: creates mocks of collaborator methods (services/repositories), e.g., `when(service.greeting(...))`.
- **MockMvc**: creates mock servlet requests/responses and executes the Spring MVC pipeline.

In `@SpringBootTest(MOCK)`, you can use the **real service** with a **simulated request**. If you want to stub `GreetingService`, declare appropriate test bean overrides/mocks. Boot 3.3 supports `@MockBean`, though when upgrading to newer lines you should check Spring Framework/Boot recommendations (e.g., `@MockitoBean` in Spring Framework 6.2). Do not mix newer APIs into a Boot 3.3 lab without checking packages.

### 13.2. Can WebTestClient Be Used for MVC MOCK?

Spring Boot 3.3 docs show cases using `WebTestClient` to drive MVC tests when WebFlux test APIs are on the classpath and the MockMvc adapter is configured. However, **the MVC lab project does not add the WebFlux dependency**; using `MockMvc` is the direct, clear path. Do not conclude that `WebTestClient` can only run when starting a Netty server.

### 13.3. In MOCK, Choose the Right Binding Mode

The same `WebTestClient` API can be built **bound-to-controller/application-context** or **bound-to-server**. It does not become a network client simply because it uses fluent syntax `.get().uri(...).exchange()`. To prove sockets/networking, the test must use a running-server environment and a client configured against the real port.

## 14. WebFlux: MOCK and RANDOM_PORT with WebTestClient

This topic also applies to **Spring WebFlux**, where the typical test client is `WebTestClient` instead of `MockMvc`. This is a **separate project**—do not paste it into an MVC project with `starter-web`, so Boot does not prioritize Servlet automatically.

### 14.1. pom.xml for a Separate WebFlux Test Module

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>webflux-test-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

`spring-boot-starter-webflux` provides Spring WebFlux/reactive server. `spring-boot-starter-test` provides JUnit/Boot Test/WebTestClient test support; `reactor-test` is helpful when testing `Flux/Mono` with `StepVerifier`. Omit `starter-web` so the inbound runtime does not switch to Servlet.

### 14.2. WebFlux Project File Structure

~~~text
webflux-test-lab/
├── pom.xml
└── src/
    ├── main/java/com/example/reactivetest/
    │   ├── ReactiveTestApplication.java
    │   └── ReactiveHelloController.java
    └── test/java/com/example/reactivetest/
        ├── ReactiveMockTest.java
        └── ReactiveRandomPortTest.java
~~~

**`ReactiveTestApplication.java`:**

~~~java
package com.example.reactivetest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveTestApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveTestApplication.class, args);
    }
}
~~~

**`ReactiveHelloController.java`:**

~~~java
package com.example.reactivetest;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ReactiveHelloController {

    @GetMapping("/reactive/hello")
    public Mono<String> hello(
            @RequestParam(defaultValue = "World") String name) {
        return Mono.just("Hello, " + name + "!");
    }
}
~~~

### 14.3. WebFlux MOCK Test: Does Not Open a Server

**`src/test/java/com/example/reactivetest/ReactiveMockTest.java`:**

~~~java
package com.example.reactivetest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class ReactiveMockTest {

    @Autowired
    private WebTestClient client;

    @Test
    void helloViaReactiveMockEnvironment() {
        client.get()
                .uri("/reactive/hello?name=Lan")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("Hello, Lan!");
    }
}
~~~

`@AutoConfigureWebTestClient` in Boot 3.3 (package `org.springframework.boot.test.autoconfigure.web.reactive`) configures `WebTestClient` to enter WebFlux handler infrastructure **without opening a Netty listener** when `webEnvironment=MOCK`.

### 14.4. WebFlux RANDOM_PORT Test: Real Netty Server

**`src/test/java/com/example/reactivetest/ReactiveRandomPortTest.java`:**

~~~java
package com.example.reactivetest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "server.address=127.0.0.1")
@AutoConfigureWebTestClient
class ReactiveRandomPortTest {

    @LocalServerPort
    private int port;

    @Autowired
    private WebTestClient client;

    @Test
    void helloOverRealHttpConnection() {
        assertThat(port).isGreaterThan(0);

        client.get()
                .uri("/reactive/hello?name=An")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("Hello, An!");
    }
}
~~~

**Same client API, different transport:** the `MOCK` test uses a mock application handler context; the `RANDOM_PORT` test actually starts a Reactor Netty web server and the client sends HTTP to the bound port. Boot test's `WebTestClient` is preconfigured to resolve relative URIs against the running server.

If you want **`DEFINED_PORT` with WebFlux**, change the annotation to `WebEnvironment.DEFINED_PORT`, set `properties={"server.port=18082","server.address=127.0.0.1"}`, and use `@LocalServerPort` to inspect the port. The rest is similar, though it reintroduces port-conflict risks in CI.

### 14.5. Do Not “Enable Reactive” with Just a Fake Annotation

If a project accidentally contains both `spring-boot-starter-web` and `spring-boot-starter-webflux`, Boot usually picks Spring MVC. When you genuinely need to test a reactive app in that situation, Boot documentation advises setting:

~~~java
@SpringBootTest(
        properties = "spring.main.web-application-type=reactive")
class ReactiveConfiguredTest {
    // Test body/config specific to the use case.
}
~~~

This is an illustrative snippet, **not a runnable test with assertions**. Verify dependencies, runtime server, and test client properly before concluding you are testing WebFlux.

## 15. MOCK Is Neither @WebMvcTest Nor @WebFluxTest

All of them can **avoid opening a real port**, yet their context scopes differ.

| Annotation | Context | Purpose |
| --- | --- | --- |
| `@SpringBootTest(webEnvironment=MOCK)` | **Full Spring Boot context** with mock web environment | Testing multi-layer wiring and MVC/WebFlux behavior |
| `@WebMvcTest(GreetingController.class)` | **MVC slice** (mainly controller/web MVC infrastructure) | Controller mapping/serialization/error/security filter logic |
| `@WebFluxTest(ReactiveHelloController.class)` | **WebFlux slice** | Reactive controller/web layer |
| `@SpringBootTest(webEnvironment=RANDOM_PORT)` | Full context + real embedded server | HTTP integration/network behavior |
| `@SpringBootTest(webEnvironment=DEFINED_PORT)` | Full context + fixed-port embedded server | Integration on a prescribed port |

**Example of a web slice with a dependency:** `GreetingController` in the lab needs `GreetingService`. If you only test the controller via `@WebMvcTest(GreetingController.class)`, Spring does not instantiate all real services automatically; you must use a mock bean or import needed dependencies. In `@SpringBootTest(MOCK)`, `GreetingService` is created normally via component scanning.

### 15.1. When to Choose Which Test Type?

- Pure unit test for `GreetingService.greeting(...)`, without Spring: fastest, catches logic bugs.
- `@WebMvcTest`: ensure mapping/JSON/filters/controller contract in the web slice, mocking dependencies explicitly.
- `@SpringBootTest(MOCK)`: need real wiring and controller/service interaction without a network stack.
- `@SpringBootTest(RANDOM_PORT)`: need to prove HTTP sockets, server config, real status/headers/cookies/network semantics.
- `@SpringBootTest(DEFINED_PORT)`: when an external participant mandates an exact port; accepting collision risk.

Do not “push all tests to `RANDOM_PORT`” just to verify service addition. Starting a full context/server carries overhead and slows down the suite.

## 16. The Most Important Trap: @Transactional and Real HTTP Threads

Spring Test provides a **test-managed transaction** mechanism. When a test is annotated with `@Transactional` and an appropriate transaction manager is configured, Spring Test normally starts a transaction on the **test thread** and rolls it back after the test method. However, a real HTTP client and server run on separate threads.

### 16.1. MOCK with MockMvc

~~~text
JUnit test thread
   |
   | @Transactional test-managed transaction (when TxManager present)
   |
   '--> MockMvc.perform(...)
           |
           '--> DispatcherServlet / Controller on the same test thread
                 |
                 '--> Repository uses the test thread's transaction context
   |
   '--> rollback after test
~~~

With an MVC **synchronous mock request** and a standard synchronous transaction manager, database writes can belong to the test-managed transaction and roll back. However, if the controller dispatches async to another thread or code creates an independent transaction (`REQUIRES_NEW`), you cannot assume all side effects roll back with the test.

### 16.2. RANDOM_PORT/DEFINED_PORT with Real HTTP

~~~text
JUnit test thread                         Embedded server thread
     | @Transactional test                   |
     |                                       |
     | HTTP client GET/POST ---------------->|
     |                                       | Controller / @Transactional service
     |                                       | Server tx DB write + commit
     |<--------------------------- HTTP 200  |
     |
     | test transaction ROLLBACK
     '--> DOES NOT roll back server-committed transaction
~~~

**Warning in Spring Boot 3.3 documentation:** When using `RANDOM_PORT` or `DEFINED_PORT` for web integration tests, the HTTP client and server run in **different threads**, meaning **different transactions**. Server-side transactions are **not** rolled back just because the test method carries `@Transactional`.

This is a common source of flakiness: a test creates data via HTTP assuming `@Transactional` cleans it up; the next run hits duplicate keys or unexpected row counts.

### 16.3. How to Isolate DB for Real HTTP Tests

- Use a **dedicated test database**/container (Testcontainers or ephemeral DB) with managed lifecycle.
- Seed and clean up data via `@Sql` or repository setup/teardown, ensuring cleanup transactions actually commit if server writes committed.
- Use unique IDs/tenant keys per test, avoiding method-order dependency.
- Have an explicit cleanup/reset endpoint **in tests only** if needed; never expose destructive management endpoints in production.
- If migrations/async jobs exist, await completion conditions before asserting instead of guessing with `Thread.sleep`.
- Use clear transaction boundaries in application services and test setup.
- Do not put `@DirtiesContext` hoping server-side DB writes will roll back; it mainly governs the **context cache**, not automatically erasing external state.

## 17. Spring TestContext Caching and Why Ports May Be Reused

Spring Test Framework caches ApplicationContexts across tests with equivalent configuration, avoiding repeated full context startups.

### 17.1. With MOCK

Multiple tests with identical configuration can share one mock web context (no port). If a test mutates singleton state or leaves mock configuration unreset, subsequent tests can be affected.

### 17.2. With RANDOM_PORT

If the context is cached, the **embedded server and that random port can also be reused** across multiple test classes sharing the same cache key. The random port is selected **when the web server binds**, not per HTTP call or per `@Test`. Do not assert “two test methods must have different ports.”

### 17.3. With DEFINED_PORT

Especially sensitive to context caching/parallel tests. One test server still alive on fixed port 18081 can block another test (with a different context config) from binding that same port. Test teardown, JUnit parallelization, or Maven fork strategies can cause collisions.

**`@DirtiesContext`** asks the Spring test cache to evict/close the context at the configured time; useful when a test truly alters context state. However:

- Increases test time due to rebuilding/restarting the server.
- Does not solve an external process occupying the port.
- Does not roll back DB/external side effects.
- Should not be slapped onto every test class for convenience.

Whenever possible, use `RANDOM_PORT` and cleanly isolate external state.

## 18. Profiles and Test Properties: Avoiding Production Config by Mistake

`@SpringBootTest` allows overriding properties directly on the annotation:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "server.address=127.0.0.1",
        "app.feature.new-checkout=false"
    })
class MyIntegrationTest {
}
~~~

**Note:** This is a configuration example of a test class without methods, not a standalone file in the lab project. Property `app.feature.new-checkout` must actually be consumed by the app to have business effect.

With a test profile:

~~~java
@org.springframework.test.context.ActiveProfiles("test")
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ProfiledWebTest {
}
~~~

File `src/test/resources/application-test.properties` can contain:

~~~properties
app.dependency.base-url=http://127.0.0.1:18090
app.feature.new-checkout=false

# Do not hardcode server.port=8080 for RANDOM_PORT tests.
~~~

When a bean calls a real external dependency, you must supply a corresponding stub/test server or mock collaborator; `@SpringBootTest` does not automatically replace external services with fakes.

### 18.1. @DynamicPropertySource and Testcontainers

An external service/Testcontainer with an OS-selected port can publish runtime properties via `@DynamicPropertySource`. Example **snippet**:

~~~java
@org.springframework.test.context.DynamicPropertySource
static void registerTestProperties(
        org.springframework.test.context.DynamicPropertyRegistry registry) {
    registry.add("app.dependency.base-url",
            () -> "http://127.0.0.1:18090");
}
~~~

This only illustrates registering a test property; for a truly dynamic port, the supplier must read **information from an already-started test server/container**. Do not hardcode 18090 and call it dynamic. `@DynamicPropertySource` differs from `@LocalServerPort`: it typically supplies **dependencies' connection addresses before the context is built**, whereas `@LocalServerPort` reads the inbound web listener after the server starts.

### 18.2. Test Properties and Environment Precedence

Even if `src/main/resources/application.properties` specifies `server.port=8080`, `RANDOM_PORT` instructs test infrastructure to run the web server on a random port. With `DEFINED_PORT`, the effective property is the merge of sources. If binding to an unexpected port, check:

- `@SpringBootTest(properties=...)`, `@TestPropertySource`.
- `@ActiveProfiles` and `application-test.properties`.
- JVM system properties/environment variables.
- Test framework/context caching and Maven fork settings.
- Application Boot version, embedded server type, web application type.

Do not guess the port from the annotation name if unusual config overrides exist.

## 19. Mock Filter/Security Behavior vs HTTP Container Behavior

There are two common classes of web testing pitfalls.

### 19.1. MOCK Has Filters, Yet Does Not Mean Security Is Tested Properly

`@AutoConfigureMockMvc` by default applies registered Servlet filters; if Spring Security is on the classpath, ensure the security filter chain and test user/auth are properly configured. Using `addFilters=false` to test a controller “without having to log in” can let the suite PASS while unauthorized production requests are mishandled.

Use Spring Security test support (`@WithMockUser`, `SecurityMockMvcRequestPostProcessors`, or the appropriate auth mechanism) whenever the security contract is part of the behavior under test.

### 19.2. MOCK Does Not Reproduce Every Embedded Container Behavior

A mock servlet request can go through DispatcherServlet and Spring MVC exception resolution, yet **does not** produce the same network/container error pages, TLS, proxy headers, or Tomcat connector behavior. For example, official Spring Boot docs note that custom error pages depend on container error-page support, so a running-server test is required to verify rendering end-to-end.

**When choosing `RANDOM_PORT`**, do not assume the test automatically passes through the production reverse proxy. It only runs the local embedded server inside the test process. To test NGINX/ingress/firewalls, you need a dedicated integration/staging environment that actually contains those components.

## 20. What Differences Exist in Real Server Configurations?

### 20.1. The MOCK Path

~~~text
Test method
  |
  | MockMvc.perform(get("/api/hello"))
  v
MockHttpServletRequest/MockHttpServletResponse
  |
  v
MVC DispatcherServlet / handlers / converters
  |
  '--> MvcResult assertions
~~~

### 20.2. The RANDOM_PORT or DEFINED_PORT Path

~~~text
Test method
  |
  | TestRestTemplate / real HTTP client
  |
  v
TCP socket to 127.0.0.1:<bound-port>
  |
  v
Embedded Tomcat/Netty server
  |
  v
Web filters -> MVC/WebFlux pipeline
  |
  v
HTTP status + headers + body
  |
  '--> Client deserializes/asserts
~~~

### 20.3. What Can Only a Running Server Verify?

- Port binding/connector configuration errors.
- Whether an independent client can actually connect to host:port.
- Server compression headers/connection behavior (when enabled).
- Network timeouts and socket lifecycles.
- TLS certificates/handshakes, when the test fixture configures TLS.
- HTTP2/WebSocket upgrades on supported web servers, with matching clients.
- Certain error page/rendering behaviors handled by the container.

**Do not assume running-server mode covers every production path.** If the app sits behind a CDN, WAF, service mesh, API gateway, or mTLS ingress, local `RANDOM_PORT` tests do not cover those components.

## 21. Common Errors When Running Tests

| Error / Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `No qualifying bean of type MockMvc` | Missing `@AutoConfigureMockMvc` or not an MVC mock context | Add annotation and use `MOCK`/MVC properly |
| `@LocalServerPort` has no value in `MOCK` | No real embedded server | Do not inject port in `MOCK`; use `RANDOM_PORT`/`DEFINED_PORT` |
| `Connection refused: localhost:8080` with `RANDOM_PORT` | Hardcoded port 8080 while server uses ephemeral port | Use `@LocalServerPort`/Boot test client |
| `Port 18081 already in use` in `DEFINED_PORT` | Another app/process/test occupies port | Change port, stop process, use `RANDOM_PORT` |
| `MOCK` test PASSES, live test FAILS | Container/network/TLS/error page or client behavior differs | Inspect running server logs, real HTTP response |
| 404 when calling endpoint | Wrong `@RequestMapping`, context path, URI | Check mapping, context-path, HTTP method |
| `SpringBootConfiguration not found` | Test package outside main class search scope | Put test under main package or set `classes=...` |
| `@Transactional` test does not roll back HTTP DB writes | Client/server on different threads/transactions | DB isolation and explicit cleanup |
| Suite flakes when parallel | Fixed-port server collision or shared test state | `RANDOM_PORT`, isolate resources, manage context |
| `WebTestClient` fails to autowire in MVC project | WebFlux test APIs/auto-config absent | Use MockMvc/TestRestTemplate or add right deps/adapter |
| Running WebFlux yet logs start Tomcat/MVC | Both `starter-web` and `webflux` present; MVC prioritized | Check classpath/`web-application-type` |
| 401/403 when Spring Security enabled | Security filters active and test lacks auth | Use appropriate Spring Security test support |
| Missing Content-Type or different JSON field | Client, converter/DTO, or content negotiation | Inspect raw HTTP body/headers, JSON serializer |
| Test clients hang indefinitely | External dependency lacks timeout or server not ready | Set timeouts, isolate dependencies, startup checks |
| Flaky test because random port differs across methods | Code assumes fixed port | Inject actual port; do not cache in static singleton too early |
| `@DirtiesContext` does not delete data | Closes/evicts Spring context, does not reset remote DB | Use DB cleanup/test data isolation |
| Health management port differs from app port | Dedicated management server | Inject `local.management.port` or configure management separately |
| `TestRestTemplate` import missing on Boot 4 | API/modules changed across versions | Pin docs to Boot version, fix deps/imports |
| App fails as soon as test creates context | Bean init hits real DB/external service | Test config/containers/mocks; do not blame `webEnvironment` |

### 21.1. Three Checks When Debugging

1. **Which webEnvironment is active?** If `MOCK`, never treat testing a network port as the test goal. If `RANDOM_PORT`/`DEFINED_PORT`, verify the server bound and the client URL matches.
2. **Which test client is it and where is it bound?** MockMvc/WebTestClient bound-to-context differs from TestRestTemplate/WebTestClient bound-to-server.
3. **Are external resources controlled?** DB, Kafka, downstream HTTP, filesystem, security credentials, and test context caching can fail even when the HTTP handler itself is right.

## 22. Anti-Patterns to Avoid

1. **“@SpringBootTest always starts a real server.”** False; default `MOCK` does not start a server.
2. **“MOCK only loads the controller.”** False; it is a full Boot context, distinct from `@WebMvcTest`.
3. **“MockMvc sends requests through localhost.”** False; MockMvc processes inside MVC test infrastructure.
4. **“RANDOM_PORT picks a different port for every @Test method.”** False; chosen when the server context binds, and caching can reuse it.
5. **“DEFINED_PORT always defaults to 8080 regardless of server.port.”** False; it uses the effective `server.port`.
6. **“RANDOM_PORT always requires @LocalServerPort.”** Not strictly; Boot-configured clients may already have base URLs, though the annotation exposes the actual port.
7. **“@LocalServerPort belongs to the old package in all Boot versions.”** False; Boot 3.3 uses `org.springframework.boot.test.web.server.LocalServerPort`.
8. **“@Transactional test rolls back every server-side HTTP write.”** False when client/server are in different threads/transactions.
9. **“Having WebTestClient means a Netty server started.”** False; WebTestClient has mock modes.
10. **“Having WebClient in Spring MVC makes the web stack reactive.”** False; Boot prioritizes MVC when both starters are present.
11. **“@DirtiesContext cleans external DBs.”** False; separate DB cleanup is required.
12. **“Fixed-port tests are always more stable than random ports.”** False on parallel shared CI hosts.
13. **“Passing mock tests prove TLS/HTTP2/ingress work.”** False; must test running servers and matching infrastructure.
14. **“Disable all servlet filters so tests pass easily.”** Can mask security regressions.
15. **“Putting @SpringBootTest on all unit tests improves quality.”** No; slows the suite and adds external environment coupling.
16. **“A test HTTP call via RestTemplate in MOCK runs automatically.”** No listener exists; use `TestRestTemplate` in real server mode or `MockMvc`.
17. **“Port 0 means the server listens on port 0.”** No; it asks the OS for an ephemeral port.
18. **“Testing against a local real app is full end-to-end system testing.”** Not if external databases, gateways, and proxies are still mocked or bypassed.

## 23. Self-Check Questions

**Q1.** If `@SpringBootTest` omits `webEnvironment`, does the server open a real HTTP port?

**Q2.** How does `MOCK` with `@AutoConfigureMockMvc` differ from `@WebMvcTest` in ApplicationContext scope?

**Q3.** When is `RANDOM_PORT` needed instead of `MOCK`?

**Q4.** What port will `DEFINED_PORT` listen on if `server.port` is not set in any configuration?

**Q5.** If `server.port=18081` is set in a `DEFINED_PORT` test and another process listens on 18081, what happens?

**Q6.** Where does `@LocalServerPort` get its value, and why not use it in a `MOCK` test?

**Q7.** Must two test methods in a `RANDOM_PORT` class use two different ports?

**Q8.** Can `WebTestClient` run against both a mocked WebFlux context and a running WebFlux server?

**Q9.** With a real HTTP server, does a `@Transactional` test method roll back transactions inside the controller/service request?

**Q10.** Why is `MOCK` insufficient to prove a custom container error page?

**Q11.** With both Spring MVC and WebFlux starters present, which stack does Boot 3.3 usually select?

**Q12.** Why does `DEFINED_PORT` easily cause flakiness when running tests in parallel in CI?

**Q13.** Where do `TestRestTemplate` and `MockMvc` differ when both assert `status=200`?

**Q14.** A MockMvc test PASSES while the HTTPS certificate is invalid. Is that a contradiction?

**Q15.** When a test class cannot find `@SpringBootConfiguration`, how should package structure or test config be fixed?

**Q16.** Can `WebEnvironment.NONE` be used to test an `@Service` with no web dependencies?

**Q17.** Why does `@DirtiesContext` not delete database rows committed by the server thread?

**Q18.** Is it valid to use `@SpringBootTest(RANDOM_PORT)` and call hardcoded `http://localhost:8080`?

**Guided Answers:**

1. No, the default is **MOCK**.
2. `MOCK` loads the **full application context**; `@WebMvcTest` loads only the MVC slice.
3. When real socket/server/HTTP container behavior, TLS/headers/network-level integration is needed.
4. **8080** per Boot default if not overridden.
5. Context/server startup fails due to port conflict before test assertions run.
6. Reads actual bound port from runtime `local.server.port`; `MOCK` opens no real server.
7. No; the random port is picked at context startup and can be reused via caching.
8. Yes; see bound-to-context and bound-to-server modes.
9. Does not auto-rollback; HTTP server thread uses a separate transaction.
10. MockMvc does not execute the full embedded servlet container error-page machinery.
11. Spring MVC/Servlet, unless `web-application-type` is overridden.
12. Multiple processes/contexts can compete for the same fixed port.
13. MockMvc executes fake Servlet requests; TestRestTemplate sends real HTTP requests.
14. No, `MOCK` does not exercise TLS.
15. Place tests in the main package/subpackage or use `@SpringBootTest(classes=...)`.
16. Yes, if the service/config does not depend on web-specific beans.
17. `@DirtiesContext` primarily manages the Spring context cache; DB state needs separate reset/cleanup.
18. Wrong; must use actual `@LocalServerPort` or a configured test client.

## 24. Extended Hands-On Exercises

### Exercise A — Convert MOCK to RANDOM_PORT

Take `GreetingMockTest`, create a **new class** using `RANDOM_PORT`, `TestRestTemplate`, and `@LocalServerPort` instead of `MockMvc`. Compare Tomcat startup logs, execution time, and HTTP responses. Explain why changing only the annotation while keeping `mvc.perform(...)` will not prove requests go over TCP.

### Exercise B — Change DEFINED_PORT via Profile

Add `src/test/resources/application-it.properties`:

~~~properties
server.port=18111
server.address=127.0.0.1
~~~

Then create a `DEFINED_PORT + @ActiveProfiles("it")` test without overriding `server.port` in the annotation. Verify port 18111. Run two Maven processes concurrently with the same profile and observe the conflict; try switching one test to `RANDOM_PORT`.

### Exercise C — Test JSON POST

Starting from `GreetingMockTest.postEchoDeserializesJson()`, write the corresponding real HTTP `TestRestTemplate.postForEntity(...)`. Compare response body/headers/encoding without relying on exact JSON whitespace.

### Exercise D — Add Spring Security

Protect `GET /api/hello` with a test security filter chain. Compare default `@AutoConfigureMockMvc` with `addFilters=false`. Use Spring Security test support to properly test unauthorized/authenticated behavior; never disable security in production just to pass tests.

### Exercise E — Real Transaction Rollback

Add a dedicated test database with a POST that inserts a row. Run a `@Transactional` test via synchronous `MockMvc` and via `RANDOM_PORT`. Inspect the DB afterward and explain why the committed server transaction escaped test-managed rollback. Use an ephemeral DB/explicit rollback cleanup; avoid doing this on a real DB.

### Exercise F — WebFlux

Using the WebFlux project from section 14, add a `DEFINED_PORT` test on 18082 and compare `WebTestClient` across `MOCK`/`RANDOM`/`DEFINED`. Record the actual port and verify HTTP requests flow through Reactor Netty in running-server modes.

### Exercise G — Verify Management Port

Add Actuator to a test project with a separate management server and configure an appropriate management port. Use `@LocalServerPort` and `@LocalManagementPort` to demonstrate that the two bound ports are distinct concepts; note that `RANDOM_PORT` can cause the management port to be randomly chosen too.

## 25. Project Checklist for Choosing webEnvironment

- [ ] Identify whether the test goal is **controller behavior**, **wiring**, or **network/server runtime**.
- [ ] For `@SpringBootTest` without a declared mode, understand the **MOCK** default.
- [ ] For MVC `MOCK`, use `@AutoConfigureMockMvc` and `MockMvc`; do not assume an embedded server is listening.
- [ ] For WebFlux `MOCK`, use `@AutoConfigureWebTestClient` and bound-to-context `WebTestClient`.
- [ ] For running-server tests, choose `RANDOM_PORT` unless there is a clear reason for `DEFINED_PORT`.
- [ ] With `RANDOM_PORT`, read the actual port via `@LocalServerPort` or a Boot-configured client; never hardcode 8080.
- [ ] With `DEFINED_PORT`, assign a dedicated test port, managing conflicts and parallel CI jobs.
- [ ] Keep test classes under `@SpringBootApplication`'s package or specify `classes=...`.
- [ ] Use `spring-boot-starter-test` in test scope, pinned by the BOM.
- [ ] Do not confuse `MockMvc` with Mockito, or `MOCK` with `@WebMvcTest`.
- [ ] Verify whether the app actually runs MVC or WebFlux when both starters are present.
- [ ] In real HTTP tests, do not rely on test `@Transactional` to roll back server-side writes.
- [ ] Use test database/dependency isolation and explicit cleanup.
- [ ] Understand context caching and avoid overusing `@DirtiesContext`.
- [ ] Test security filters properly instead of disabling filters to turn the suite green.
- [ ] For proxy/TLS/HTTP2/network bugs, use a running server and matching test environment.
- [ ] Actually test 2xx, 4xx, auth, serialization, startup failures, and port conflicts.
- [ ] Monitor flaky tests, startup overhead, and CI environment behavior.
- [ ] When upgrading Spring Boot 3.x → 4.x, recheck test client imports/modules for that version.

## 26. Official References

1. **Spring Boot 3.3 — Testing Spring Boot Applications** (`MOCK`/`RANDOM_PORT`/`DEFINED_PORT`/`NONE`, transactions, `MockMvc`, `WebTestClient`, `TestRestTemplate`): https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
2. **Spring Boot 3.3 — Testing Overview** (`starter-test`, JUnit, Mockito/AssertJ): https://docs.spring.io/spring-boot/3.3/reference/testing/index.html
3. **Spring Boot 3.3 — @SpringBootTest Javadoc**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/SpringBootTest.html
4. **Spring Boot 3.3 — @LocalServerPort Javadoc**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/web/server/LocalServerPort.html
5. **Spring Boot 3.3 — @AutoConfigureMockMvc Javadoc**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/autoconfigure/web/servlet/AutoConfigureMockMvc.html
6. **Spring Boot 3.3 — @AutoConfigureWebTestClient Javadoc**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/autoconfigure/web/reactive/AutoConfigureWebTestClient.html
7. **Spring Boot 3.3 — TestRestTemplate Javadoc**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/web/client/TestRestTemplate.html
8. **Spring Framework 6.1 — Spring MVC Testing (MockMvc)**: https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html
9. **Spring Framework 6.1 — Spring WebFlux Testing (WebTestClient)**: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
10. **Spring Framework — TestContext transaction management**: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html
11. **Spring Framework — TestContext context caching**: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html
12. **Spring Framework — @DynamicPropertySource**: https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-dynamicpropertysource.html
13. **Spring Boot 3.3 — Test Slices**: https://docs.spring.io/spring-boot/3.3/reference/test-auto-configuration/slices.html