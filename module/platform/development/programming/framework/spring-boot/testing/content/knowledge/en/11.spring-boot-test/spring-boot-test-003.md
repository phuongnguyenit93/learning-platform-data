# `@SpringBootTest(webEnvironment = MOCK)` does not mean an embedded server is listening

> **Module:** Spring Boot – testing  
> **Group:** `@SpringBootTest`  
> **Topic:** `MOCK` does not mean an embedded server is listening  
> **Goal:** Distinguish between a mock web environment and a real HTTP server; use `MockMvc` appropriately; know when to pick `RANDOM_PORT` or `DEFINED_PORT`; build Java 17/Spring Boot tests demonstrating how the two modes differ.

## 1. Core takeaway

**`@SpringBootTest` uses `webEnvironment = MOCK` by default and does not start an embedded HTTP server.** Spring Boot still creates an `ApplicationContext`, loads the required beans, sets up a simulated web environment, and allows testing requests/responses with `MockMvc`. However, that does not mean Tomcat/Jetty/Undertow has opened a TCP port for browsers, `curl`, or an external `HttpClient` to connect to.

```java
@SpringBootTest // webEnvironment = MOCK is the default
@AutoConfigureMockMvc
class ApplicationMockTest {
    // Use MockMvc to test MVC without opening an HTTP port.
}
```

Meanwhile:

```java
@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class ApplicationRealHttpTest {
    // Spring Boot starts a real embedded HTTP server on a random port.
}
```

The two snippets above are **annotation illustrations**, not standalone test classes with imports/test methods. A complete runnable project is in section 5.

**Clearly distinguish four things:**

- **Spring ApplicationContext:** the container for beans, dependency injection, configuration, and lifecycle.
- **Mock web environment:** a context configured to operate under the Servlet/WebFlux model without an embedded listener.
- **`MockMvc`:** a toolkit for testing Spring MVC with mock requests/responses **in-process**, invoking `DispatcherServlet`/MVC infrastructure without sending TCP/HTTP sockets to a server.
- **Embedded HTTP server:** a real server (typically Tomcat when using default `spring-boot-starter-web`) opening a socket and listening on a port to accept HTTP requests from external clients or an `HttpClient`/REST client.

**Common trap:** `mockMvc.perform(get("/api/..."))` returns `200 OK`, yet `curl http://localhost:8080/api/...` reports “connection refused”. That is not a contradiction: `MockMvc` processed the request inside the test context, while the `MOCK`-mode test never started a server on port 8080.

## 2. Why is the name `MOCK` easy to misunderstand?

The word “mock” here refers to the **inbound web environment**; it does not mean:

- Spring skips creating real beans.
- Controllers/services/repositories are all mocked by Mockito.
- `@SpringBootTest` only executes unit tests.
- Every HTTP request goes through a server socket.
- Databases, outbound REST clients, schedulers, or message publishers are automatically mocked.
- Having Tomcat on the classpath via `spring-boot-starter-web` makes Tomcat listen automatically.

In a typical Spring MVC application, `@SpringBootTest(webEnvironment=MOCK)` can load **all application logic, configuration, and beans**. Only the **running HTTP server** is omitted compared to `RANDOM_PORT`/`DEFINED_PORT`. If a real bean calls an external API in its constructor, `@PostConstruct`, or during a test method, it **can still make outbound network connections**.

This is completely different from declaring `@MockitoBean`: that annotation replaces/defines a specific bean as a Mockito mock. `@MockitoBean` does not change `webEnvironment`; to avoid calling external services, you must mock/fake those external dependencies themselves. A test using `@SpringBootTest(MOCK)` whose real repository points to a production database is still dangerous. Configure test profiles, Testcontainers, fake HTTP adapters, isolated credentials, and network restrictions.

### 2.1. How does `MockMvc` process a request?

```text
                     MOCK web environment
                    @SpringBootTest(MOCK)
                              │
                              ▼
                       ApplicationContext
                              │
                              ▼
Test method → MockMvc.perform(GET /api/greet/Mai)
                              │
                              ▼
                   MockHttpServletRequest
                              │
                              ▼
                       DispatcherServlet
                              │
                              ▼
                    Controller → Service
                              │
                              ▼
                   MockHttpServletResponse
                              │
                              ▼
           .andExpect(status().isOk())
           .andExpect(content().string(...))

       NO TCP accept()/listen() happens here.
       NO packets are sent to localhost:8080.
```

Strengths: faster than booting a real server; tests mappings, converters, Spring MVC validation/exception handling, configured filters, controller advice, and the security filter chain within supported scope. Limitations: does not verify all real servlet container behavior, networking, TLS, connectors, compression, socket/timeouts, or container error-page dispatching.

### 2.2. Real HTTP requests in `RANDOM_PORT`

```text
                      RANDOM_PORT
                 @SpringBootTest(RANDOM_PORT)
                              │
                              ▼
                        WebServer context
                              │
                  Embedded Tomcat starts
                              │
                       TCP port 49xxx
                              ▲
                              │
    Java HttpClient  ── HTTP request via 127.0.0.1:49xxx
                              │
                              ▼
                     Servlet container
                              │
                              ▼
                 DispatcherServlet → Controller
                              │
                              ▼
                   HTTP response over socket
                              │
                              ▼
                      Java HttpClient
```

Port `49xxx` is only an **example**, not a fixed port. Spring Boot asks the OS to allocate a free port and exposes the value via `@LocalServerPort` when the application starts in a real web-server mode.

## 3. Four values of `SpringBootTest.WebEnvironment`

| Mode | Context created | Embedded server listening? | Typical client | When to choose |
| --- | --- | --- | --- | --- |
| **`MOCK`** (default) | Mock web `ApplicationContext` if web technology is present | **No** | `MockMvc`; or a client bound to a mock context depending on stack | Test MVC/framework/application wiring without sockets |
| **`RANDOM_PORT`** | Web-server `ApplicationContext` | **Yes**, OS-assigned port | `HttpClient`, `WebTestClient`, `TestRestTemplate` when appropriate | Real HTTP testing, servlet container integration, avoiding port collisions |
| **`DEFINED_PORT`** | Web-server `ApplicationContext` | **Yes**, configured port or default 8080 | HTTP client to fixed host:port | Tests requiring a fixed port; harder to parallelize |
| **`NONE`** | `ApplicationContext` without a web environment | **No** | Call Java services/beans directly | Test logic/beans without MVC/HTTP |

Exceptions to remember:

- With `MOCK`, if no web environment is on the classpath, Spring Boot can create a regular non-web `ApplicationContext`.
- `RANDOM_PORT` and `DEFINED_PORT` can be **servlet or reactive** depending on dependencies and configuration.
- `DEFINED_PORT` defaults to the application's `server.port` or 8080 if unconfigured. Opening a fixed port risks colliding with another process.
- `NONE` creates no web environment even when the project has web dependencies; it fits when only non-web beans are needed.

### 3.1. Why doesn't `server.port=0` turn `MOCK` into a real server?

`server.port=0` is used in **real embedded server modes** so the OS picks a free port. In `MOCK`, no embedded server is started, so merely setting `server.port=0` creates no listener.

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK,
    properties = "server.port=0")
@AutoConfigureMockMvc
class StillNoSocketTest {
    // "server.port=0" is just a property; there is no real embedded server.
}
```

The snippet above illustrates configuration, not a runnable test. **Do not equate the `server.port` property with the runtime `local.server.port` property:** `server.port` expresses configuration intent; `local.server.port` is published once a real web server has successfully bound in an appropriate test runtime.

### 3.2. Why is `@AutoConfigureMockMvc` important?

`@SpringBootTest` loads the context, but **does not guarantee a `MockMvc` bean is configured for injection**. With Spring MVC, add `@AutoConfigureMockMvc` when you want to use `@Autowired MockMvc`:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class ControllerMockTest {
    @Autowired
    MockMvc mvc;
}
```

`@WebMvcTest(SomeController.class)` also **auto-configures `MockMvc`** and loads only a web slice, not the full application context. Thus:

- `@SpringBootTest(MOCK) + @AutoConfigureMockMvc`: broad application context, mock HTTP requests/responses.
- `@WebMvcTest`: narrow MVC slice, mock HTTP requests/responses, typically uses `@MockitoBean` for service dependencies.
- `@SpringBootTest(RANDOM_PORT)`: broad context **plus a real embedded HTTP server**.

“Full context” and “real HTTP server” are **two orthogonal axes** and must not be conflated.

## 4. Choosing test level by what you want to prove

| What needs proving | Right tool | What remains unproven |
| --- | --- | --- |
| Computing a value accurately | JUnit + Java class, no Spring | Spring bean wiring/MVC |
| Controller maps `GET /api/...` and returns right JSON/text | `@WebMvcTest` + `MockMvc` | Network port/Tomcat connector, real services if mocked |
| Controller and real service collaborate; filters/exception handlers apply in MVC | `@SpringBootTest(MOCK)` + `@AutoConfigureMockMvc` | Real HTTP listener/transport |
| Real app receives requests via HTTP TCP and sends responses | `@SpringBootTest(RANDOM_PORT)` + HTTP client | Production infrastructure like ingress/TLS/load balancer if outside test |
| HTTP server runs on a fixed port for external systems | `@SpringBootTest(DEFINED_PORT)` | Does not prevent port collisions |
| Spring creates beans and non-web profiles/configs properly | `@SpringBootTest(NONE)` or suitable test context | HTTP endpoints |

**Rule:** Never use `MockMvc` to claim a real server is listening. Conversely, do not force every controller test onto `RANDOM_PORT`; many MVC checks run faster under `MOCK`. Pick the **cost proportional to the risk the test needs to catch**.

## 5. Complete example: same API, two execution paths

This section uses **Java 17+, Spring Boot 3.5.16, Maven, JUnit Jupiter, Spring MVC**. The project has a minimal API, one `MOCK` test, one `RANDOM_PORT` test, and one `@WebMvcTest`. When properly configured, all of them run via `mvn test`.

### 5.1. Project structure

```text
mock-vs-http-server/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/webmode/
    │       ├── WebModeApplication.java
    │       ├── GreetingService.java
    │       └── GreetingController.java
    └── test/
        └── java/com/example/webmode/
            ├── MockEnvironmentTest.java
            ├── RealHttpServerTest.java
            └── WebMvcSliceTest.java
```

Note on filenames: Java requires public types to live in matching filenames. The code blocks below represent **separate files**; do not place multiple `package` declarations in one file.

### 5.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>mock-vs-http-server</artifactId>
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
```

With standard `spring-boot-starter-web` on Boot 3.5, the default embedded server is usually Tomcat when **running in a server mode**. Having this dependency on the classpath **does not make `MOCK` bind a port automatically**. `spring-boot-starter-test` in `scope=test` supplies JUnit, Spring Test/MockMvc, Mockito, and AssertJ for testing.

### 5.3. Application code

```java
// src/main/java/com/example/webmode/WebModeApplication.java
package com.example.webmode;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebModeApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebModeApplication.class, args);
    }
}
```

```java
// src/main/java/com/example/webmode/GreetingService.java
package com.example.webmode;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String greeting(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Name must not be blank");
        }
        return "Hello, " + name.trim() + "!";
    }
}
```

```java
// src/main/java/com/example/webmode/GreetingController.java
package com.example.webmode;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {
    private final GreetingService service;

    public GreetingController(GreetingService service) {
        this.service = service;
    }

    @GetMapping(value = "/api/greet/{name}",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String greet(@PathVariable String name) {
        return service.greeting(name);
    }
}
```

The API has one contract:

- `GET /api/greet/Mai` → HTTP **200**, body text **`Hello, Mai!`**.
- Requires no database, security, cloud secrets, or external APIs.
- The controller calls the real service when both are in the application context; if a slice test mocks the service, it only checks mapping/response from mocked data.

### 5.4. Test 1: `MOCK` still processes requests but has no listener

```java
// src/test/java/com/example/webmode/MockEnvironmentTest.java
package com.example.webmode;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.boot.web.context.WebServerApplicationContext;
import org.springframework.context.ApplicationContext;
import org.springframework.core.env.Environment;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(webEnvironment = WebEnvironment.MOCK)
@AutoConfigureMockMvc
class MockEnvironmentTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ApplicationContext context;

    @Autowired
    Environment environment;

    @Test
    void mvcWorksWithoutAListeningWebServer() throws Exception {
        mvc.perform(get("/api/greet/Mai"))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello, Mai!"));

        // In the sample project under MOCK mode, there is no web-server context.
        assertFalse(context instanceof WebServerApplicationContext);

        // This is the runtime listener property, not server.port config.
        assertNull(environment.getProperty("local.server.port"));
    }
}
```

**Explanation:**

- `@SpringBootTest(webEnvironment=MOCK)` creates a mock servlet web environment without starting an embedded server.
- `@AutoConfigureMockMvc` adds `MockMvc` to test Spring MVC in the same process.
- `mvc.perform(...)` flows through the MVC infrastructure and this project's real service, because there is no Mockito override.
- `assertFalse(context instanceof WebServerApplicationContext)` expresses how the `MOCK` context differs from a web-server context in this Servlet configuration.
- `assertNull(environment.getProperty("local.server.port"))` shows **no real listener port is published** in the sample test environment.

Do not make an `HttpClient` connection to `localhost:8080` to “prove MOCK is not listening” using `assertThrows(ConnectionException...)`. If another app occupies port 8080, the connection will not fail and the test becomes environment-dependent. The distinction is already established via mode and test runtime properties.

**Avoid writing:** `@LocalServerPort int port` expecting it to contain a port while `MOCK` runs. There is no test HTTP listener to provide a value. Trying to inject a nonexistent property can make the test fail when creating the context/test instance.

### 5.5. Test 2: `RANDOM_PORT` starts a real HTTP server

```java
// src/test/java/com/example/webmode/RealHttpServerTest.java
package com.example.webmode;

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

@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
class RealHttpServerTest {

    @LocalServerPort
    int port;

    @Test
    void sendsRealHttpRequestToAnEmbeddedListener() throws Exception {
        assertTrue(port > 0, "A real server port must be allocated");

        URI uri = URI.create(
                "http://127.0.0.1:" + port + "/api/greet/Mai");

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .build();
        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        HttpResponse<String> response =
                client.send(request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertEquals("Hello, Mai!", response.body());
    }
}
```

**Explanation:**

1. `RANDOM_PORT` instructs Spring Boot to build a web-server context and a real embedded server, binding an OS-chosen TCP port.
2. `@LocalServerPort` receives the opened port value. It comes from the runtime listener, not a hardcoded number like 8080.
3. JDK's `HttpClient` establishes an HTTP connection to the loopback address and receives the response over a socket.
4. Assertions check the **allocated server port**, status 200, and contract-compliant body.
5. Client and server run in the same test JVM, yet they are **two ends of an HTTP connection over TCP** — unlike `MockMvc`, which does not invoke mock servlet request objects directly.

**Practical note:** Do not build a fixed URL `http://localhost:8080` in a `RANDOM_PORT` test. Random ports prevent port conflicts, allow multiple independent test suites/processes, and reduce environment assumptions. Never try to predict the port before the test starts.

### 5.6. Test 3: `@WebMvcTest` also has no real server

```java
// src/test/java/com/example/webmode/WebMvcSliceTest.java
package com.example.webmode;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(GreetingController.class)
class WebMvcSliceTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    GreetingService service;

    @Test
    void controllerMapsAndRendersMockServiceResponse() throws Exception {
        when(service.greeting("An")).thenReturn("Hello, An!");

        mvc.perform(get("/api/greet/An"))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello, An!"));

        verify(service).greeting("An");
    }
}
```

**Scope differs from Test 1:** `@WebMvcTest` focuses solely on an MVC slice and mocks the service dependency, whereas `@SpringBootTest(MOCK)` in Test 1 loads a broad application context and uses the real service. **Neither creates an embedded server listener.** Test 3 does not prove the real service formats names properly because the service is stubbed with Mockito; separate unit/integration tests are needed for that logic.

### 5.7. Running the project and understanding test counts

Requirements: JDK 17+ and Maven able to resolve the dependencies in `pom.xml`. From the `mock-vs-http-server` directory:

```bash
java -version
mvn -version
mvn test
mvn -Dtest=MockEnvironmentTest test
mvn -Dtest=RealHttpServerTest test
mvn -Dtest=WebMvcSliceTest test
```

With the three test classes above, each class has **one `@Test` method**, so running `mvn test` on the sample project executes **3 test methods** (excluding any additional tests you add yourself).

**Output to confirm:**

- `MockEnvironmentTest`: `MockMvc` receives 200 and `Hello, Mai!`; no `WebServerApplicationContext`; `local.server.port` is not provided.
- `RealHttpServerTest`: Spring Boot binds a random port greater than 0; JDK `HttpClient` receives a real 200 response and body `Hello, Mai!`.
- `WebMvcSliceTest`: Controller mapping and response from the mocked service are right, without opening a real server.

Maven/Spring logs, random ports, execution duration, and context initialization order vary across machines; there is no fixed exact stdout. **Do not treat seeing “Tomcat initialized” in the log of another test as evidence that `MOCK` opened a server:** the whole suite runs multiple independent test contexts; the `RANDOM_PORT` test may execute before or after in the same Maven run.

## 6. Misconceptions about “server running”

### 6.1. `mvn test` differs from `mvn spring-boot:run`

`mvn test` launches the test runner with different application contexts according to each test class's annotations. In a suite containing both `MOCK` and `RANDOM_PORT`, only tests requiring a real server need to start an embedded listener.

`mvn spring-boot:run` runs the **normal application**. Since the sample project has `spring-boot-starter-web` and no special configuration, Spring Boot typically opens port 8080 (unless overridden):

```bash
mvn spring-boot:run
```

In another terminal, after the app starts:

```bash
curl --fail http://localhost:8080/api/greet/Mai
```

The returned body of the sample application is:

```text
Hello, Mai!
```

If port 8080 is already taken, the application usually fails to start on that port; pick another port via appropriate runtime configuration. **The `curl` command here checks the normally running app, not that a `MOCK` test has a listener.**

### 6.2. Why can `MockMvc` send requests even without a port?

Because `MockMvc` constructs a `MockHttpServletRequest` in memory and directly invokes `DispatcherServlet`/handler mappings/filters/controllers via Spring MVC Test mechanics. It does not open a port to accept HTTP from another machine. Method names like `perform(get(...))` look like HTTP, but there is no TCP protocol at that boundary.

`MockMvc` can run under `@WebMvcTest`, `@SpringBootTest(MOCK) + @AutoConfigureMockMvc`, or manual `MockMvcBuilders` setup. **The existence of a `MockMvc` bean does not mean a listening embedded servlet container bean exists.**

### 6.3. Why does a test see a `TomcatServletWebServerFactory` bean without a server?

In a web application, auto-configuration and dependencies may create beans/factories/configurations related to the embedded server. However, a **factory** does not mean a **running server instance**, and a server class on the classpath does not mean a listener has bound a port. Only conclude a server is running when the app has started an appropriate web-server context and obtained a real port or connected to a known listener.

### 6.4. Does `@LocalServerPort` work with `MOCK`?

There is no test listener port in `MOCK` to supply. In `RANDOM_PORT`, Spring Boot assigns `local.server.port` when the web server starts. With `DEFINED_PORT`, `@LocalServerPort` can also retrieve the actual port after binding. Under `MOCK`, do not inject or assert an assumed port like 8080 to “confirm running”. Seeing `server.port=8080` in `Environment` is merely **configuration**, not proof of a listener.

### 6.5. Why doesn't `MOCK` prevent all network access?

`MOCK` only governs the **inbound web server**. It does not replace outbound HTTP clients, JDBC, Kafka producers, or SMTP connections in the application. A real bean can still call an external API, and a `@Scheduled` job can run once the context loads.

To guarantee tests do not touch production: use a `test` profile, inject fake/mock outbound ports, use test databases, sandbox credentials, and egress-blocking policies. Trying to “fix” this by switching from `RANDOM_PORT` to `MOCK` will not block all outbound connections.

## 7. What can `MockMvc` test, and what can it not test?

### 7.1. MVC behaviors typically testable

- Request mapping: paths, HTTP methods, query parameters, path variables.
- Data binding, conversion, and validation via MVC infrastructure.
- HTTP status, response headers, body, and JSON serialization performed inside the context.
- Controller advice and exception handlers belonging to Spring MVC.
- Filters when configured to apply; Spring Security filter chain within mock MVC test scope.
- Collaboration between controller and service/repository **if those beans are real and loaded into the context**.

Assertion example:

```java
mvc.perform(get("/api/greet/Mai"))
        .andExpect(status().isOk())
        .andExpect(content().string("Hello, Mai!"));
```

This snippet goes inside a test with `MockMvc mvc`; it is not a standalone Java program.

### 7.2. Characteristics requiring a real server or broader environment

- Having a socket in `listen()` state reachable by a TCP client.
- Tomcat/Jetty/Undertow connector configuration, TLS/SSL handshakes, HTTP protocol behavior.
- Network latency, client/server timeouts, connection pooling, port binding.
- Compression/proxy/ingress/load-balancing behavior and real headers added by infrastructure.
- Certain error-page/dispatch mechanisms provided by the servlet container (beyond MVC exception handlers).
- Session cookies/redirects/forwards under real container behavior where MockMvc simulates differently.
- Behavior depending on client/server transactions running on separate threads/processes.

Even `RANDOM_PORT` still **does not test the entire production path** if the app under test does not go through proxies, ingress, CDN, firewalls, TLS termination, or corresponding dependent services. Choose the test level matching the specific risk coverage needed.

## 8. How do `@WebMvcTest`, `@AutoConfigureMockMvc`, and Mockito differ?

| Tool/annotation | Scope of effect | Opens a port? |
| --- | --- | --- |
| `@WebMvcTest(Controller.class)` | Spring MVC slice test, auto-configures MockMvc; services typically need Mockito beans | No |
| `@SpringBootTest(MOCK)` | Broad application context with mock web environment | No |
| `@AutoConfigureMockMvc` | Adds `MockMvc` to interact within compatible Servlet MVC test contexts | No, by itself it opens no port |
| `@MockitoBean` | Replaces/defines a dependency bean as a Mockito mock | No |
| `MockMvcBuilders.standaloneSetup(...)` | Manually builds MockMvc for a controller/handler without full Spring context | No |
| `@SpringBootTest(RANDOM_PORT)` | Broad context with an embedded HTTP server | Yes |
| `@SpringBootTest(DEFINED_PORT)` | Broad context with an embedded HTTP server on configured port | Yes |

Two commonly confused cases:

**A.** `@SpringBootTest(MOCK) + @AutoConfigureMockMvc` can load real services and real repositories. It does not “mock everything”; only Servlet requests/responses are simulated.

**B.** `@WebMvcTest` does not automatically create all service beans. If a controller needs a service, the author typically adds `@MockitoBean` or `@Import` for the required dependency. It focuses on the controller slice and needs no real server.

## 9. `DEFINED_PORT` mode and parallel execution risks

If a server must run on a configured port, you can use:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.DEFINED_PORT,
    properties = "server.port=9095")
class FixedPortHttpTest {
    // A real test needs an HTTP client and appropriate assertions.
}
```

This is an **annotation template**, not a complete test. `DEFINED_PORT` starts a real server and tries to bind port `9095` in this example. If the port is occupied by another process, the test can fail. Two tests running in parallel on the same machine using the same fixed port also collide easily.

**Prefer `RANDOM_PORT` for most HTTP integration tests:** Spring Boot/OS allocates a dynamic port and `@LocalServerPort` supplies the actual port. Never call `Thread.sleep(...)` to guess when the server opens; `@SpringBootTest(RANDOM_PORT)` waits for the Spring test context to be ready before executing test methods in the standard lifecycle.

In production, ports are usually explicitly configured by the deployment platform; that serves a different purpose than testing.

## 10. Execution path with WebFlux/reactive

If only Spring WebFlux is on the classpath, Spring Boot can build a **ReactiveWebApplicationContext** for `MOCK`, and `WebTestClient` can bind to the mock context/handlers for testing without a real HTTP listener. When `RANDOM_PORT` is selected, the reactive app runs a real embedded server and an HTTP client can send requests to that port.

**Two distinct ways to use `WebTestClient`:**

- **Bind to application context/controller:** the test client drives requests in-process without necessarily opening networking.
- **Bind to server URL:** the test client sends requests over HTTP to a real endpoint.

Thus, the mere presence of `WebTestClient` does not prove a server is listening; check how it is configured/bound.

If both Spring MVC and WebFlux are on the classpath, Spring Boot usually prefers Spring MVC; to test a reactive app, `spring.main.web-application-type=reactive` must be configured properly. This article's primary example uses Spring MVC, so `MockMvc` and `@AutoConfigureMockMvc` are the direct choices.

## 11. Transactions, rollback, and test data

Distinguishing `MOCK` from `RANDOM_PORT` also affects how you reason about test transactions.

Spring Test can automatically roll back a `@Transactional` test method's transaction under test management. However:

- In `MOCK` using `MockMvc`, request handling occurs inside the test's mock infrastructure (possibly sharing thread/transaction context depending on configuration). DB changes still must be understood in light of how transactions and beans are created.
- In `RANDOM_PORT`/`DEFINED_PORT`, the HTTP client and embedded server run on **different threads**, so a transaction opened on the test thread does not automatically span the server thread's transaction. Rolling back the test method **does not automatically roll back** transactions committed by the server.
- With a real/containerized database, you need test data, cleanup, transaction boundaries, and isolated test fixtures. Never use a production database, and never just add `@Transactional` and assume it is safe.

For example, a real HTTP test calls an order creation endpoint: a 201 response does not prove the data will be auto-deleted after the test. Design explicit cleanup, ephemeral test databases, or idempotent state when needed.

## 12. Diagnosing “weird” test behavior

| Symptom | Common Likelihood | How to Check |
| --- | --- | --- |
| `MockMvc` returns 200 but `curl` to 8080 refuses connection | `MOCK` context creates no listener | Check `webEnvironment`; use `RANDOM_PORT` if real HTTP is needed |
| `@Autowired MockMvc` bean not found in `@SpringBootTest` | Missing `@AutoConfigureMockMvc` or incompatible web stack | Add the right annotation; distinguish MVC from WebFlux |
| `@LocalServerPort` unresolved in `MOCK` test | No real port exists | Use only with a real server |
| `RANDOM_PORT` test calls port 8080 and fails | Real port is randomly assigned | Use `@LocalServerPort` |
| `DEFINED_PORT` fails to start | Fixed port already taken | Change port or prefer `RANDOM_PORT` |
| `@WebMvcTest` reports missing service bean | Slice does not load business services | Use `@MockitoBean`/`@Import` per goal |
| `MOCK` test still sends emails/SQL | Outbound dependencies are still real beans | Replace with fakes/mocks, configure test resources and network policy |
| `RANDOM_PORT` test leaves DB records despite `@Transactional` | Server transaction runs off the test thread | Clean up/roll back on the server transaction or use ephemeral test DB |
| Real HTTP test passes locally, fails on CI | Host/port/firewall/profile/timing differs | Check allocated port, loopback, readiness, and test resources |
| Log shows server initialized during `mvn test` yet `MOCK` test has no port | Suite also runs another test context (`RANDOM_PORT`) | Run the class separately; match annotations of the class under inspection |

**Debugging strategy:** Identify the **specific annotations and test class**, check whether the test client invokes a mock layer or an HTTP socket, and verify runtime `local.server.port` only where a real server exists. Do not guess from combined log lines across the whole suite.

## 13. Anti-patterns that lead to false conclusions

### 13.1. “`@SpringBootTest` means the server is already running”

False. The default is `MOCK`. A real embedded server requires `RANDOM_PORT` or `DEFINED_PORT`.

### 13.2. “Having `@AutoConfigureMockMvc` means the server is open”

False. It creates/configures `MockMvc`; it does not turn mock requests into sockets.

### 13.3. “Mockito mock beans and `MOCK` are the same thing”

False. `MOCK` describes the **web environment**, while `@MockitoBean` describes a **bean dependency**. You can have real services in `MOCK`; conversely, you can mock a payment gateway even while running a real HTTP server on `RANDOM_PORT`.

### 13.4. “`MOCK` has `server.port=8080`, so `curl` will connect”

False. `server.port` is a configuration value, while a listener only exists if the mode and runtime actually start a server. `local.server.port` represents the actual port after binding.

### 13.5. “MockMvc tests all HTTP behavior sufficiently”

No. It tests Spring MVC fairly thoroughly, but not real transport/containers. SSL/TLS, servlet container session/error pages, connectors, network timeouts, and proxies may require real HTTP tests.

### 13.6. “Using `RANDOM_PORT` for every test is always more accurate”

Not necessarily. Pure logic tests need no Spring, MVC mappings are usually tested with `MockMvc`, and only HTTP transport needs a real listener. Widening the context unnecessarily makes tests slower, environment-dependent, and harder to diagnose without clear goals.

### 13.7. “A `MOCK` test definitely cannot cause external side effects”

False. It does not block outbound HTTP, DB writes, Kafka publishing, or schedulers. Use test-only credentials, fake outbound adapters, test containers, and network constraints.

### 13.8. “A `RANDOM_PORT` test is definitely identical to production”

False. It tests the embedded server in the same JVM and HTTP endpoints, without adding production load balancers, ingress, TLS termination, CDNs, network ACLs, or external services. Use E2E/staging when needed.

## 14. Checklist before reviewing a web test

- [ ] Identified the target: logic, MVC wiring, or real HTTP listener/network.
- [ ] If using `@SpringBootTest` without arguments, aware that `webEnvironment = MOCK` by default.
- [ ] With `MOCK` and Spring MVC, included `@AutoConfigureMockMvc` when injecting `MockMvc`.
- [ ] Do not treat `MockMvc.perform(...)` as a request going over a TCP socket.
- [ ] Do not inject `@LocalServerPort` in tests without an embedded listener.
- [ ] If real HTTP is needed, use `RANDOM_PORT` and have the client target the allocated port.
- [ ] When using `DEFINED_PORT`, considered port collisions and parallel tests.
- [ ] Distinguished `@WebMvcTest` (slice) from `@SpringBootTest(MOCK)` (broad context).
- [ ] Verified which outbound beans are real/mocked, without confusing `MOCK` with Mockito.
- [ ] Do not rely on the test thread's `@Transactional` to guarantee rollback of data from the HTTP server thread.
- [ ] If container/network behavior is needed, included real HTTP tests or appropriate staging checks.
- [ ] Test assertions measure behavior matching the chosen level, without overclaiming beyond scope.

## 15. Self-check

**Question 1.** Why does `MockMvc` return 200 inside `@SpringBootTest` while a browser cannot open `localhost:8080`?

**Answer:** `@SpringBootTest` defaults to `MOCK`, so Spring MVC handles mock requests in-process and does not bind an HTTP port.

**Question 2.** To verify Tomcat receives real HTTP requests on a random port, which annotation should you use?

**Answer:** `@SpringBootTest(webEnvironment = RANDOM_PORT)`; obtain the real port with `@LocalServerPort` and call it using an appropriate HTTP client such as `HttpClient`/`WebTestClient`/`TestRestTemplate`.

**Question 3.** Why is `@WebMvcTest` still suitable when no HTTP server is opened?

**Answer:** It focuses on the Spring MVC slice and uses `MockMvc` to verify mapping/responses/validation without needing a container listener.

**Question 4.** Can you test a controller and a real service under `MOCK`?

**Answer:** Yes. `@SpringBootTest(MOCK) + @AutoConfigureMockMvc` with a real service bean flows through Spring MVC to the real service; it still does not test an HTTP socket.

**Question 5.** Does setting `server.port=0` in a `MOCK` test guarantee the server listens?

**Answer:** No. `server.port=0` only controls the port when an embedded web server is started; `MOCK` does not do that.

**Question 6.** What is the simplest way to tell whether an HTTP request goes through a socket or a mock layer?

**Answer:** Check **how the client is configured**: `MockMvc.perform`/bind-to-context clients process internally; `HttpClient` targeting `http://127.0.0.1:<local.server.port>` under `RANDOM_PORT` executes requests over TCP.

**Question 7.** A `@Transactional` test calls a real API on `RANDOM_PORT`; when the test finishes and rolls back, does it revert DB writes on the server thread?

**Answer:** Never assume so. The test thread's transaction differs from the HTTP server thread's transaction; cleanup/rollback must happen in the right transaction or use an isolated DB.

**Question 8.** Can a `@SpringBootTest(MOCK)` call production Kafka?

**Answer:** Yes, if real beans and credentials/configs still point to production Kafka. `MOCK` only changes the web server environment; outbound connections must be isolated.

## 16. Official documentation

- Spring Boot 3.5 – [Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): clear explanation of default `MOCK`, `RANDOM_PORT`, `DEFINED_PORT`, `NONE`; MockMvc and real servers.
- Spring Boot 3.5 – [`SpringBootTest.WebEnvironment` API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/SpringBootTest.WebEnvironment.html): meaning of each mode and context created.
- Spring Framework 6.2 – [MockMvc Overview](https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/overview.html): mock Servlet API, `DispatcherServlet`, and testing without a running server.
- Spring Framework 6.2 – [MockMvc vs End-to-End Tests](https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/vs-end-to-end-integration-tests.html): limitations compared to real client/server setups.
- Spring Boot 3.5 – [Testing How-to](https://docs.spring.io/spring-boot/3.5/how-to/testing.html): MVC slices, Spring Security testing, and test options.

**One sentence to remember:** **“`MOCK` tests the web flow *inside the application*; `RANDOM_PORT`/`DEFINED_PORT` additionally tests the HTTP path *through a listening server*.”** Thus a passing MockMvc test does not prove Tomcat opened a port, and opening a port does not by itself prove all production dependencies are isolated.
