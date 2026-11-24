# `@SpringBootTest.webEnvironment`: `MOCK`, `NONE`, `RANDOM_PORT` and `DEFINED_PORT`

`@SpringBootTest` allows JUnit Jupiter to create an `ApplicationContext` through Spring Boot's `SpringApplication` to test an application with real dependency injection, configuration, and beans. However, **initializing a Spring context does not mean opening an HTTP server**. The `webEnvironment` attribute determines whether the test uses a mock web environment, no web environment, or starts an embedded server on a real HTTP port.

Choosing the wrong mode can cause tests to accidentally call an external server, test `MockMvc` while assuming the network path was tested, inject `@LocalServerPort` into a portless context, or believe `@Transactional` rolls back every change caused by a real HTTP server. This article analyzes the mechanics, how to choose a mode based on proof scope, a runnable **Java 17 + Spring Boot 3.5 + JUnit Jupiter** example project, and common pitfalls when moving tests to CI.

## 1. Overview comparison

The `org.springframework.boot.test.context.SpringBootTest.WebEnvironment` enum has four options:

| Mode | Context | Embedded HTTP server | TCP Port | Common testing approach |
|---|---|---|---|---|
| **`MOCK`** — **default** | Mock web application context when web stack is present; falls back to non-web if missing | **No** | **No** | `MockMvc` + `@AutoConfigureMockMvc` (Servlet MVC), appropriate mock WebTestClient |
| **`NONE`** | ApplicationContext with `WebApplicationType.NONE` | **No** | **No** | Test beans, services, configuration without HTTP |
| **`RANDOM_PORT`** | WebServerApplicationContext | **Yes** | **Yes**, OS assigns randomly via `server.port=0` | `@LocalServerPort` + real HTTP client |
| **`DEFINED_PORT`** | WebServerApplicationContext | **Yes** | **Yes**, per `server.port` or default **8080** | Real HTTP client, verify port configuration |

Syntax:

```java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;

@SpringBootTest(webEnvironment = WebEnvironment.MOCK)
class ExampleSpringTest {
    // @Test methods in a real file.
}
```

This is only an annotation skeleton, not a standalone test. Omitting `webEnvironment` defaults to **`MOCK`**, which does not start a real server. `@SpringBootTest` already integrates JUnit Jupiter's `SpringExtension`, so a separate `@ExtendWith(SpringExtension.class)` is typically unnecessary.

Two decision axes to remember: **whether web infrastructure is present**, and **whether a real HTTP socket is opened**. `MOCK` is not `NONE`; both `RANDOM_PORT` and `DEFINED_PORT` start a real server, differing in how the port is obtained.

## 2. `MOCK`: testing MVC requests in-process, without networking

In a Spring MVC application, `MOCK` creates a web context with a mock servlet environment; Tomcat/Jetty/Undertow does not bind an HTTP socket. To get a Spring Boot-configured `MockMvc`, combine:

```java
@SpringBootTest(webEnvironment = WebEnvironment.MOCK)
@AutoConfigureMockMvc
class MvcCheckTest {
    @Autowired
    MockMvc mvc;
}
```

This is a structural snippet inside a test class with proper imports; it has no standalone test method. In **Spring Boot 3.5**, `@AutoConfigureMockMvc` is imported from `org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc`.

`MockMvc` simulates HTTP requests through `DispatcherServlet` and the Spring context's MVC/filter components, allowing you to test:

- Controller mappings, path/query parameters, binding, validation, and exception handlers.
- HTTP status, headers, body, JSON conversion, and loaded filter/security chains.
- Coordination between controllers and real beans in the context, per the test's dependencies.

`MockMvc` **does not test** TCP ports, container startup, socket timeouts, TLS termination, or deployment networking. **`MOCK` also does not automatically create a `MockMvc` bean** in all cases; `@AutoConfigureMockMvc` is needed to inject it in Servlet examples. If the classpath lacks a matching web application type, `MOCK` may become a non-web context.

Do not call `http://localhost:8080` via JDK HttpClient from a `MOCK` test and believe the request goes to the context under test. It may hit an entirely different process.

## 3. `NONE`: loads Spring beans while disabling the web environment

`NONE` runs `SpringApplication` with `WebApplicationType.NONE`. Web-independent beans like services, configurations, properties, and non-HTTP auto-configurations can still be loaded; there is no servlet/reactive web environment serving requests.

Skeleton example:

```java
@SpringBootTest(webEnvironment = WebEnvironment.NONE)
class ServiceContextTest {
    @Autowired
    SomeService service;
}
```

`SomeService` is a hypothetical type and the snippet above lacks a `@Test`; a complete sample is in section 6.

Choose `NONE` when verifying Spring Boot startup, DI/configuration for batch jobs, message consumers, or backend services that do not need HTTP. Note that `NONE` **does not shrink component scanning by itself**: a `@RestController` class can still be instantiated as a bean if scanned, though there is no HTTP dispatcher/server to route requests to it. Beans requiring servlet-specific infrastructure may prevent a non-web context from starting.

If you are only testing pure Java functions, there is no need for `@SpringBootTest(NONE)`: JUnit + `new Service(...)` is usually much lighter.

## 4. `RANDOM_PORT`: real HTTP server with dynamic port

`RANDOM_PORT` sets `server.port=0`, letting the embedded server pick an available port when opening a socket. Tests must retrieve the **actual port after startup**:

```java
import org.springframework.boot.test.web.server.LocalServerPort;

@LocalServerPort
private int port;
```

This snippet belongs inside a test class running a real server; it is not a standalone program. `port` is typically used to build a URI like `http://127.0.0.1:` + port + `/hello`.

`RANDOM_PORT` is the default choice to consider when testing real HTTP in CI because it rarely collides with other applications compared to a fixed port 8080. However:

- The port is chosen **when the server/context starts**, not necessarily changing before every method. Context caching may reuse the same port across multiple tests.
- A random port only solves **HTTP port binding**; it does not isolate databases, files, brokers, or singleton state.
- If the management server is configured on a separate port, under `RANDOM_PORT` it may receive a **different** random port from the application port.
- `@LocalServerPort` does not work as expected in `MOCK`/`NONE` because those modes have no real server publishing `local.server.port`.

## 5. `DEFINED_PORT`: real server, using the configured port

`DEFINED_PORT` also starts a real HTTP server, but **does not force `server.port=0`**. Without other configuration, Spring Boot typically uses **8080**; if `server.port=19081` is set, the server attempts to listen on 19081:

```java
@SpringBootTest(
        webEnvironment = WebEnvironment.DEFINED_PORT,
        properties = "server.port=19081")
class FixedPortTest {
    // HTTP requests to the server on 19081.
}
```

This skeleton lacks a test method. In a complete test, confirm the actual port using `@LocalServerPort` rather than guessing from the mode name.

**Important:** `DEFINED_PORT` does not forbid a random port. Because it **does not override** `server.port`, if the application configuration intentionally sets `server.port=0`, the server may still get a random port. The enum name describes using the existing port configuration, not a guarantee that the port is always fixed.

Predefined ports easily conflict on CI or developer machines: if another process already holds 19081, the context fails to bind the socket. For most HTTP integration tests, `RANDOM_PORT` is more convenient; choose `DEFINED_PORT` when you genuinely must test a predefined port condition.

## 6. Complete example project: one endpoint, four test classes

Goal: Spring MVC endpoint `GET /hello` returns **`Hello, test!`**. `MOCK` calls the endpoint in-process via MockMvc; `NONE` tests beans without starting HTTP; `RANDOM_PORT` and `DEFINED_PORT` call a real server via JDK `HttpClient`. Uses **Spring Boot 3.5.0** with Java 17 so imports have a clear version context. The code requires no DB or Spring Security.

```text
boot-web-env/
├── pom.xml
├── src/main/java/com/example/web/
│   ├── DemoApplication.java
│   ├── GreetingService.java
│   └── GreetingController.java
└── src/test/java/com/example/web/
    ├── MockModeTest.java
    ├── NoneModeTest.java
    ├── RandomPortModeTest.java
    └── DefinedPortModeTest.java
```

### 6.1. `pom.xml`

Complete Maven file:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>boot-web-env</artifactId>
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

The Maven parent manages compatible Spring/JUnit dependencies. The web starter puts Spring MVC and the embedded servlet container on the classpath. The test starter provides JUnit Jupiter, Spring TestContext, and MockMvc per Spring Boot 3.5. When applying to a real project, pick an approved Boot 3.5 patch release.

### 6.2. Application source code

File **`src/main/java/com/example/web/DemoApplication.java`**:

```java
package com.example.web;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

File **`src/main/java/com/example/web/GreetingService.java`**:

```java
package com.example.web;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String message() {
        return "Hello, test!";
    }
}
```

File **`src/main/java/com/example/web/GreetingController.java`**:

```java
package com.example.web;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {
    private final GreetingService service;

    public GreetingController(GreetingService service) {
        this.service = service;
    }

    @GetMapping(value = "/hello", produces = MediaType.TEXT_PLAIN_VALUE)
    public String hello() {
        return service.message();
    }
}
```

`@RestController` writes the returned string to the HTTP response body; thanks to `produces = TEXT_PLAIN_VALUE`, the output is clearly plain text. All classes are in `com.example.web`, allowing `@SpringBootApplication` to auto-discover the service and controller in this example.

### 6.3. `MOCK` test

File **`src/test/java/com/example/web/MockModeTest.java`**:

```java
package com.example.web;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(webEnvironment = WebEnvironment.MOCK)
@AutoConfigureMockMvc
class MockModeTest {
    @Autowired
    private MockMvc mvc;

    @Test
    void servesHelloUsingMockMvcWithoutTcp() throws Exception {
        mvc.perform(get("/hello"))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello, test!"));
    }
}
```

The test uses a **simulated MVC request** inside the context. It confirms Spring MVC mapping and response, without proving that an embedded server opened a socket.

### 6.4. `NONE` test

File **`src/test/java/com/example/web/NoneModeTest.java`**:

```java
package com.example.web;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.context.ApplicationContext;
import org.springframework.web.context.WebApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

@SpringBootTest(webEnvironment = WebEnvironment.NONE)
class NoneModeTest {
    @Autowired
    private ApplicationContext context;

    @Autowired
    private GreetingService service;

    @Test
    void loadsServiceWithoutServletWebContext() {
        assertFalse(context instanceof WebApplicationContext);
        assertEquals("Hello, test!", service.message());
    }
}
```

Expected outcome: Spring beans are injected normally, the context is not a Servlet WebApplicationContext, and **no HTTP request** occurs.

### 6.5. `RANDOM_PORT` test

File **`src/test/java/com/example/web/RandomPortModeTest.java`**:

```java
package com.example.web;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
class RandomPortModeTest {
    @LocalServerPort
    private int port;

    @Test
    void servesHelloOverRealHttpOnRandomPort() throws Exception {
        assertTrue(port > 0);

        HttpRequest request = HttpRequest.newBuilder(
                        URI.create("http://127.0.0.1:" + port + "/hello"))
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        HttpResponse<String> response = HttpClient.newHttpClient()
                .send(request,
                        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

        assertEquals(200, response.statusCode());
        assertEquals("Hello, test!", response.body());
    }
}
```

The real server starts before the test method, and `@LocalServerPort` receives the OS-allocated port. JDK `HttpClient` sends a real HTTP request, so the test verifies the loopback connection to the embedded server as well.

### 6.6. `DEFINED_PORT` test

File **`src/test/java/com/example/web/DefinedPortModeTest.java`**:

```java
package com.example.web;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment = WebEnvironment.DEFINED_PORT,
        properties = "server.port=19081")
class DefinedPortModeTest {
    @LocalServerPort
    private int port;

    @Test
    void servesHelloOverRealHttpOnConfiguredPort() throws Exception {
        assertEquals(19081, port);

        HttpRequest request = HttpRequest.newBuilder(
                        URI.create("http://127.0.0.1:" + port + "/hello"))
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        HttpResponse<String> response = HttpClient.newHttpClient()
                .send(request,
                        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

        assertEquals(200, response.statusCode());
        assertEquals("Hello, test!", response.body());
    }
}
```

Unlike `RANDOM_PORT`, this test explicitly requests **19081**. If the port is occupied, the test can fail right during context creation. Avoid running multiple instances of this test simultaneously on the same host.

### 6.7. Running and expected results

In the directory containing `pom.xml`, if Maven is installed:

```bash
mvn test
```

If the project has Maven Wrapper:

```bash
./mvnw test
```

Or run each class individually:

```bash
./mvnw -Dtest=MockModeTest test
./mvnw -Dtest=NoneModeTest test
./mvnw -Dtest=RandomPortModeTest test
./mvnw -Dtest=DefinedPortModeTest test
```

Windows uses `mvnw.cmd` if a wrapper is present. With these exact four example classes, expect **4 tests PASS, 0 FAIL** provided **port 19081 is free**, the JVM is allowed to open loopback TCP sockets, and dependencies are fully downloaded. There is no fixed business stdout; Maven Surefire displays reports depending on version. If the environment disallows opening sockets, the `MOCK`/`NONE` tests can run while `RANDOM_PORT`/`DEFINED_PORT` cannot.

## 7. Which client fits which mode?

| Tool | Uses a real socket? | Usage scope |
|---|---|---|
| `MockMvc` | **No** | Spring MVC `MOCK` or `@WebMvcTest` |
| `java.net.http.HttpClient` | **Yes**, if calling a real TCP URL | `RANDOM_PORT`/`DEFINED_PORT` |
| `TestRestTemplate` | **Yes** | Testing embedded HTTP server in Boot versions with matching helper/auto-config |
| `WebTestClient` | **Depends on binding** — mock/in-process or real server | WebFlux and appropriate HTTP cases |
| `@LocalServerPort` | Not a client; provides the listening port | Tests with a real embedded server |

Version note: Spring Boot 3.5 includes `TestRestTemplate` and corresponding helpers in test tooling. **Spring Boot 4.0+** restructures module splits and auto-configuration for test clients; verify imports/dependencies/version rather than assuming `TestRestTemplate` or `@AutoConfigureMockMvc` live in the exact same package across all lines. That is why the real HTTP server example uses **JDK 17 HttpClient** to avoid these changing dependencies.

Do not send requests to `localhost:8080` from a `MOCK` test: a succeeding request might just mean **another process** is listening on that port. Only use URLs/ports supplied by the actual test server.

## 8. Servlet MVC and WebFlux are another configuration dimension

Both `RANDOM_PORT` and `DEFINED_PORT` support Servlet/Reactive contexts when the appropriate web stack is present. Spring Boot detects from dependencies: Spring MVC present typically selects servlet; WebFlux-only selects reactive; both present usually gives MVC precedence.

If you want to test WebFlux when both MVC and WebFlux are on the classpath, configure explicitly:

```java
@SpringBootTest(
        webEnvironment = WebEnvironment.RANDOM_PORT,
        properties = "spring.main.web-application-type=reactive")
class ReactiveTestConfigExample {
    // This is a snippet; requires WebFlux dependency and concrete @Test.
}
```

`@AutoConfigureMockMvc` is for **Servlet MVC**, not all WebFlux tests. A `WebTestClient` can bind to a mock reactive context or a real HTTP server depending on configuration. Distinguish **web environment** from **web stack** to know precisely what the test proves.

## 9. Caution with `@Transactional` and real HTTP servers

Suppose a test adds `@Transactional` and sends a `POST /orders` request to a real server in `RANDOM_PORT`:

```java
@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
@Transactional
class OrderHttpIntegrationTest {
    // Sends real HTTP to create an order on the server thread.
}
```

This snippet illustrates a risk, not a standalone runnable file. In real HTTP modes, **the test client and the server handling the request run on different threads/transactions**. The test-managed transaction may roll back after the test, but **server-side committed transactions do not automatically roll back** with the test thread's transaction.

Therefore, do not assume POST/PUT tests creating data will auto-clean solely via `@Transactional`. You need a dedicated test database, isolated fixtures, or intentional cleanup/transactions; for timeouts, retries, or duplicate writes, test idempotency at the right layer. `@DirtiesContext` is not a guaranteed way to delete committed DB data: it closes/evicts the Spring context from cache, without reverting all external side effects.

In synchronous `MOCK`/MockMvc, some code may run on the same thread and transaction context as the test, but async processing, events, executors, or other threads still require separate transaction management. Do not apply a single rollback rule to all modes and tasks.

## 10. Context cache, performance, and CI

Spring TestContext caches `ApplicationContext` by configuration. Tests sharing the same context config can reuse beans and servers; changing `webEnvironment`, active profiles, properties, test mock beans, or `@DirtiesContext` can spawn another context and increase startup time.

- `RANDOM_PORT` does not promise **a new port per method**. Cached contexts may reuse the same port across multiple methods/classes.
- `DEFINED_PORT` easily causes bind collisions when multiple contexts/CI jobs share port 19081.
- `@DirtiesContext` can shut down and restart the server, slowing tests and changing the port in `RANDOM_PORT`.
- `@TestInstance(PER_METHOD)` only creates a new test object instance; it **does not** mean creating a new `ApplicationContext`.
- `RANDOM_PORT` does not automatically isolate databases or brokers: shared data and state still need a cleanup strategy.

Pick the lightest mode that still proves the right boundary: plain JUnit for standalone logic, `@WebMvcTest` for web slices, `MOCK` when a broad Spring Boot context is needed without sockets, and `RANDOM_PORT` when real HTTP is required.

## 11. Common errors

| Symptom | Cause | Fix |
|---|---|---|
| `MockMvc` cannot be injected | Only `MOCK` without `@AutoConfigureMockMvc`, or not MVC | Configure MockMvc matching your Boot version and web stack |
| `@LocalServerPort` fails to resolve | No embedded server in `MOCK`/`NONE` | Use `RANDOM_PORT`/`DEFINED_PORT` if real HTTP is needed |
| `MOCK` test calls localhost and “passes” | Accidentally hit an external app outside the test | Use `MockMvc` instead of a real HTTP client |
| `DEFINED_PORT` reports port in use | Another process/context is listening on that port | Free the port or switch to `RANDOM_PORT` |
| `RANDOM_PORT` request returns 404 | Wrong URI, context path, mapping, or web stack | Check actual port, endpoint, and route |
| `NONE` is missing servlet beans | Context created as non-web | Choose `MOCK` or a web server mode if web is needed |
| `MOCK` passes but production HTTP fails | Socket, server config, or proxy untested | Add real server/integration/deployment tests |
| DB still has rows after HTTP test | Server transaction differs from test transaction | Clean up data or roll back intentionally on the server |
| CI runs slowly due to many contexts | Too many modes/profiles, overusing `@DirtiesContext` | Load only needed contexts, optimize cache reuse |
| Reactive test actually runs MVC | Spring MVC usually takes precedence when both are on classpath | Check `web-application-type` and dependencies |

## 12. Mode selection checklist

- [ ] I determined whether the test needs **non-web beans**, **mock web**, or a **real server**.
- [ ] I know `MOCK` is the default for `@SpringBootTest`.
- [ ] I do not confuse `MOCK` with an HTTP server, or `NONE` with `MOCK`.
- [ ] If using `MockMvc`, I enabled the appropriate auto-configuration.
- [ ] If using `RANDOM_PORT`, I retrieve the real port from `@LocalServerPort`, without hardcoding 8080.
- [ ] If using `DEFINED_PORT`, I accounted for configured ports, busy ports, and parallel tests.
- [ ] The HTTP client/mock client targets the **right** server/context.
- [ ] I distinguish MVC/Servlet from WebFlux/Reactive.
- [ ] I checked client-helper changes for the Boot version in use.
- [ ] With a DB and real server, I do not rely solely on test `@Transactional` for cleanup.
- [ ] I understand how context caching and `@DirtiesContext` affect ports, performance, and shared state.
- [ ] I run tests with a build tool and read assertions instead of inferring success merely from app startup.

**Remember:** **`MOCK`** = simulated web context **without sockets**; **`NONE`** = Spring context **without web**; **`RANDOM_PORT`** = real HTTP server with a **random port**; **`DEFINED_PORT`** = real HTTP server on the **configured port**. Choose based on the scope you need to prove, not merely because a mode sounds “stronger”.

### Official references

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 — WebEnvironment Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/SpringBootTest.WebEnvironment.html)
- [Spring Boot 4.0 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/4.0/reference/testing/spring-boot-applications.html)
