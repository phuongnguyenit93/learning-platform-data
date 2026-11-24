# @LocalServerPort and Server-Assigned Port Discovery in Spring Boot Web Runtime Testing

## 1. Why Do HTTP Tests Need to Know the Actual Port?

A Spring Boot application typically listens on `8080` when run standalone. However, a test suite may run concurrently alongside a development instance, another test, a Docker service, or a process already holding that port. If an integration test always calls `http://localhost:8080`, it can:

- Fail with `BindException: Address already in use`.
- Accidentally call **a different application** running on the machine.
- Pass falsely because an endpoint with the same name exists on an older instance.
- Pass on the author's machine yet fail on CI.
- Collide over ports when multiple test forks/builds run in parallel.

Spring Boot's solution is to **let the web server bind to a port assigned by the operating system**, then **read the actual bound port** to send real HTTP requests. In tests, the most important pair is:

```java
@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderHttpTest {

    @LocalServerPort
    int port;
}
```

With **Spring Boot 3.3.x**, the proper imports are:

```java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
```

This lesson focuses on **web runtime testing**, not picking a “random” port for arbitrary purposes. Examples use **Java 21, Spring Boot 3.3.13, JUnit Jupiter 5, Gradle**, compatible with Java 17+ knowledge. In particular, you must distinguish among `server.port`, `local.server.port`, application HTTP port, management HTTP port, and container or upstream service ports.

## 2. Three Concepts: Configured Port, Bound Port, Test Port Injection

| Concept | Example | Meaning |
| --- | --- | --- |
| `server.port` | `8080`, `9090`, `0` | Configuration value for the embedded server to **attempt to bind** |
| **Bound/local server port** | `49317` | The **actual** port on which the web server socket is listening |
| `local.server.port` | `49317` | Property published by Spring Boot **after server initialization** |
| `@LocalServerPort` | `int port` | Test annotation injecting the value from `local.server.port` |
| `management.server.port` | `9091` | Separate configured port for the management server, if used |
| `local.management.port` | `49318` | **Bound** management port, when a management web server exists |
| `@LocalManagementPort` | `int managementPort` | Annotation reading `local.management.port` in tests |

When `server.port=8080`, the configured port and bound port are normally both 8080 if startup succeeds. When `server.port=0`, the configured port continues to mean **“let the OS choose an available port”**, rather than mutating into a fixed config value after startup.

Example:

```text
Before startup:
  server.port = 0

Operating system binds socket:
  actual listening port = 49317

After server initialization:
  local.server.port = 49317

Test:
  @LocalServerPort int port = 49317
```

The number `49317` is illustrative only. On another machine or run it may get another port; **do not claim it is always different** because the OS can reuse a recently freed port.

## 3. The OS Assigns the Port on `bind(0)`, Not Spring Picking Numbers Arbitrarily

A TCP/HTTP server accepting connections must bind an IP address and port. When an application specifies **port 0**, the socket API asks the operating system to choose an available port within the permitted system range. The OS picks and binds the port atomically in the same socket resource allocation step.

```text
Spring Boot context startup
    |
    v
Embedded Tomcat / Jetty / Undertow / Reactor Netty
    |
    v
Bind listen socket with requested port 0
    |
    v
Operating system picks an available port and binds socket
    |
    v
WebServer.getPort() -> actual positive port
    |
    v
Boot publishes local.server.port
    |
    v
Test receives @LocalServerPort and calls HTTP endpoint
```

Do not call this algorithm “Spring generating random numbers with `Random.nextInt`.” The critical distinction is that the **OS both selects and holds the socket**. If test code probes for a free port and closes the socket to pass that number to the server, a **race condition** opens between those two moments where another process can grab the port.

A port “free at check time” is not guaranteed “free when Spring Boot binds.” Using `server.port=0`/`RANDOM_PORT` avoids the unsafe check-and-reuse step.

**Limitation:** A random port reduces port contention for the test web server, **it does not guarantee** that database schemas, Kafka topics, file paths, caches, shared static state, management ports, or other external resources are isolated too.

## 4. Four `@SpringBootTest.webEnvironment` Modes in Spring Boot 3.3

| Value | Real Embedded HTTP Server? | Appropriate Testing Approach | `@LocalServerPort`? |
| --- | --- | --- | --- |
| `MOCK` (default) | **No** | `MockMvc`, mock-bound `WebTestClient`; test MVC handlers/services | No test-bound HTTP port |
| `RANDOM_PORT` | **Yes** | Real HTTP client calling OS-chosen local socket | Yes |
| `DEFINED_PORT` | **Yes** | Real HTTP client calling configured port or default 8080 | Usable after startup; often unnecessary |
| `NONE` | **No** | Testing application context or non-web components | No |

Distinguishing examples:

```java
@SpringBootTest
class MockByDefaultTest {
    // MOCK: does not create an HTTP listener automatically.
}
```

and:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RunningServerTest {
    @LocalServerPort
    int port;
}
```

**`MOCK` is not a server listening on localhost**. With `MockMvc`, requests are dispatched inside a simulated web application context, normally bypassing TCP, TLS, socket accept queues, or a real web container.

Choose `RANDOM_PORT` when the behavior under test depends on the real web runtime: network listener, Servlet container, HTTP status/headers, actual codecs, filters, error dispatch, cookies, redirects, compression, and HTTP client–server interaction. Choose `MOCK` when only verifying controller mappings and web logic without networking.

## 5. How Does `RANDOM_PORT` Compare to `server.port=0`?

On Spring Boot 3.3, `@SpringBootTest(webEnvironment = RANDOM_PORT)` creates a **web server application context** and configures tests so the embedded HTTP server chooses a dynamic port—essentially `server.port=0`.

```text
@SpringBootTest(RANDOM_PORT)
    |
    v
Test context loads Spring Boot app
    |
    v
Test bootstrapping applies server.port=0
    |
    v
Web server starts and binds actual port
    |
    v
local.server.port becomes available
    |
    v
Test field @LocalServerPort receives actual port
```

In a normal application, you can also write:

```properties
server.port=0
```

to run a **non-test** process on an OS-assigned port. However, `@LocalServerPort` is a **test-support** annotation, not the recommended mechanism for application beans to obtain their port during construction.

**Avoid confusing `server.port=0` with no server:** port 0 asks to **create a web server on an OS-selected port**. In Spring Boot, `server.port=-1` is a different mechanism to disable HTTP endpoints in compatible web context configurations; `webEnvironment=NONE` goes even further by creating no web environment at all.

## 6. How Does `@LocalServerPort` Work?

In Spring Boot 3.3, `@LocalServerPort` resides in:

```java
org.springframework.boot.test.web.server.LocalServerPort
```

This annotation is a shortcut equivalent to:

```java
@Value("${local.server.port}")
```

on a test field or supported injection point. For example, a test can write:

```java
@LocalServerPort
int port;
```

or:

```java
@Value("${local.server.port}")
int port;
```

Important point: **`local.server.port` is published after the HTTP server initializes**, whereas `server.port` is the input configuration value. Spring Boot's `ServerPortInfoApplicationContextInitializer` listens for `WebServerInitializedEvent` to place the actual port into the `Environment`.

Thus, inside a test whose context has finished loading, `@LocalServerPort` normally holds a positive real port. However, inside the constructor of an ordinary `@Configuration`/`@Bean`, the server may not have started yet and this property may **not exist yet**. Do not turn a test-only convenience annotation into an application startup dependency.

## 7. Exact Lifecycle Sequence to Remember

```text
JUnit starts test class
   |
   v
Spring TestContext/bootstrapper
   |
   v
Create Spring ApplicationContext and register properties
   |
   v
Create beans / configure embedded web server
   |
   v
Embedded web server binds port 0
   |
   v
WebServerInitializedEvent is published
   |
   v
local.server.port is provided in Environment
   |
   v
Spring injects test instance fields (e.g. @LocalServerPort)
   |
   v
@BeforeEach and @Test execute
```

The diagram shows the **logical lifecycle**; exact ordering of some Spring callbacks can vary by context/registration. The crucial contract is that **test fields are used after `@SpringBootTest(RANDOM_PORT)` startup completes**, not read in a static field initializer or an application bean before socket binding.

**Do not fetch the port in a static `@BeforeAll` before a test instance exists**, unless the JUnit lifecycle configuration permits it and the test context is already ready—still verify injection. The simplest and most reliable way is using an **instance field** in `@Test` or `@BeforeEach`.

## 8. Runnable Spring Boot MVC Project: Structure

A small app demonstrating full HTTP integration tests:

```text
build.gradle
src/main/java/com/example/portdemo/
  PortDemoApplication.java
  PingController.java
src/main/resources/application.properties
src/test/java/com/example/portdemo/
  RandomPortHttpTest.java
```

Requirements: Gradle Wrapper available, JDK 21, loopback networking. When creating a real project, ensure packages sit beneath the package containing `@SpringBootApplication` so component scanning finds controllers.

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-web` brings in Servlet MVC and default embedded Tomcat; `spring-boot-starter-test` brings in Spring Boot Test, JUnit Jupiter, AssertJ, and utilities. **There is no need** to manually add `spring-boot-starter-webflux` just to use `@LocalServerPort` or `TestRestTemplate`.

Versions in the example are for learning purposes; production projects should follow the organization's approved Spring Boot BOM/version and Java toolchain.

## 9. Demo Application and Controller

**`src/main/java/com/example/portdemo/PortDemoApplication.java`:**

```java
package com.example.portdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PortDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(PortDemoApplication.class, args);
    }
}
```

**`src/main/java/com/example/portdemo/PingController.java`:**

```java
package com.example.portdemo;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {

    @GetMapping("/api/ping")
    public Map<String, String> ping() {
        return Map.of("status", "ok");
    }

    @GetMapping("/api/echo/{id}")
    public Map<String, String> echo(@PathVariable String id) {
        return Map.of("id", id);
    }
}
```

This is a test-only friendly controller: it has a fixed endpoint `/api/ping` and a path-variable endpoint `/api/echo/{id}` to confirm HTTP route dispatch. It **does not** authenticate users and connects to no database; for learning only, do not expose to the Internet like a real product.

**`src/main/resources/application.properties`:**

```properties
# Configuration used during normal bootRun.
server.address=127.0.0.1
server.port=8080
```

Worth remembering: when a test uses `@SpringBootTest(RANDOM_PORT)`, the test configuration **chooses a dynamic port instead of 8080**. Running the same application source with `./gradlew bootRun` without test annotations still uses `8080` above if that port is free.

## 10. Real HTTP Tests: `@LocalServerPort`, `TestRestTemplate`, and `Environment`

**`src/test/java/com/example/portdemo/RandomPortHttpTest.java`:**

```java
package com.example.portdemo;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.boot.web.context.WebServerApplicationContext;
import org.springframework.core.env.Environment;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "server.address=127.0.0.1")
class RandomPortHttpTest {

    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate client;

    @Autowired
    Environment environment;

    @Autowired
    WebServerApplicationContext webContext;

    @Test
    void injectsActualPortAfterEmbeddedServerStarted() {
        assertThat(port).isBetween(1, 65535);
        assertThat(webContext.getWebServer().getPort()).isEqualTo(port);
        assertThat(environment.getProperty(
                "local.server.port", Integer.class)).isEqualTo(port);
    }

    @Test
    void relativeUrlTargetsTheRunningRandomPort() {
        ResponseEntity<String> response =
                client.getForEntity("/api/ping", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody())
                .contains("\"status\":\"ok\"");
    }

    @Test
    void pathVariableIsHandledByRealHttpServer() {
        ResponseEntity<String> response =
                client.getForEntity("/api/echo/book-7", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody())
                .contains("\"id\":\"book-7\"");
    }
}
```

**Explanation:**

- `@SpringBootTest(...RANDOM_PORT)` starts real Tomcat on an OS-assigned port.
- `@LocalServerPort` retrieves the **bound port**, not `server.port=8080` from source `application.properties`.
- `WebServerApplicationContext.getWebServer().getPort()` confirms the port at the embedded runtime layer; this checks independently of the annotation.
- `Environment.getProperty("local.server.port", Integer.class)` reads the property published once the server initialized; distinct in meaning from `server.port`.
- Spring Boot provides a `TestRestTemplate` linked to the started test server; **relative URI `/api/ping`** resolves to the running local server port.
- The tests verify responses traverse a **real HTTP socket**, rather than calling controller methods directly.

If an application enables Spring Security, responses may be blocked by authentication/CSRF and tests need appropriate credentials/roles configured. This demo has no Spring Security, so HTTP 200 is expected.

## 11. Running Tests and Understanding Output

From the project containing `gradlew`:

```bash
./gradlew test
```

On Windows PowerShell:

```powershell
.\gradlew.bat test
```

The expected result given valid JDK, dependencies, loopback, and project structure is **tests PASS**. **There is no fixed port or exact Gradle stdout**: the test framework may log something like:

```text
Tomcat started on port 49152 (http) with context path '/'
```

The line and number `49152` are **illustrative**, not required output. Do not write test assertions that parse logs for `"Tomcat started on port ..."`. Switching embedded servers from Tomcat to Jetty or WebFlux Netty changes the log text even when HTTP behavior remains correct.

To investigate failures, check: did the app context start cleanly? Is `local.server.port` present? Is the test using `MOCK` or `RANDOM_PORT`? Does the client automatically use a relative base URL? Does a profile alter HTTP/HTTPS/context path?

## 12. When You Need to Build an Absolute URL from the Assigned Port

`TestRestTemplate` handles relative URLs conveniently, yet some tests must pass a full URL to an external client, WebSocket client, callback, or unconfigured SDK. In that case, construct the URL **after the field has been injected**:

```java
String baseUrl = "http://127.0.0.1:" + port;
String pingUrl = baseUrl + "/api/ping";
```

This is an **in-test integration fragment**, not standalone runnable code; `port` comes from `@LocalServerPort`.

Add a test using JDK `HttpClient` to `RandomPortHttpTest`:

```java
@Test
void jdkHttpClientCanUseDiscoveredPort() throws Exception {
    java.net.http.HttpClient http =
            java.net.http.HttpClient.newHttpClient();

    java.net.URI uri = java.net.URI.create(
            "http://127.0.0.1:" + port + "/api/ping");

    java.net.http.HttpRequest request =
            java.net.http.HttpRequest.newBuilder(uri).GET().build();

    java.net.http.HttpResponse<String> response =
            http.send(request,
                    java.net.http.HttpResponse.BodyHandlers.ofString());

    assertThat(response.statusCode()).isEqualTo(200);
    assertThat(response.body()).contains("\"status\":\"ok\"");
}
```

JDK 17+ already includes `java.net.http.HttpClient`, requiring no extra HTTP client dependency. This test proves that **a client unaware of the Spring context** can still use the newly discovered port.

Do not build URLs in a static initializer using an uninjected `port`. Avoid hardcoding the `http` scheme when testing SSL: if the app enables HTTPS, the base URL must be `https://...` and the client needs proper trust material. Do not disable certificate verification indiscriminately to test over HTTPS.

## 13. How Does `TestRestTemplate` Differ from Regular `RestTemplate`?

`TestRestTemplate` is Spring Boot's utility for integration tests, offering several test-friendly behaviors:

- When paired with `RANDOM_PORT`/`DEFINED_PORT`, it can call **relative URLs** instead of concatenating host/port manually.
- It does not throw the same way default `RestTemplate` does for many HTTP 4xx/5xx responses; tests can directly assert `ResponseEntity.getStatusCode()` and the error body.
- Offers helpers for Basic Auth when appropriate, such as `withBasicAuth(...)`.
- Uses real HTTP when the embedded server has started.

Example testing a non-existent route:

```java
@Test
void missingEndpointReturnsHttp404() {
    ResponseEntity<String> response =
            client.getForEntity("/does-not-exist", String.class);

    assertThat(response.getStatusCode()).isEqualTo(
            HttpStatus.NOT_FOUND);
}
```

This is an additional method inside `RandomPortHttpTest`. If a real app defines a custom fallback route or security filter, outcomes may differ. **Do not call `getForObject` expecting HTTP 404 to throw automatically** by default and ignore status; use `getForEntity` to inspect status directly.

A standalone `new RestTemplate()` **will not automatically know the test's random port**. If using `RestTemplate`, `RestClient`, OkHttp, or a custom HTTP client, configure the base URL with `@LocalServerPort` after startup.

## 14. `WebTestClient` Can Reduce Manual Port Concatenation

In Spring Boot 3.3, running-server tests can `@Autowired WebTestClient` when `spring-webflux` is on the test classpath. For the MVC project above, add the dependency **in test scope only** if you wish to use `WebTestClient`:

```groovy
testImplementation 'org.springframework.boot:spring-boot-starter-webflux'
```

Then a separate test:

```java
package com.example.portdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "server.address=127.0.0.1")
class WebTestClientRandomPortTest {

    @Autowired
    WebTestClient webClient;

    @Test
    void autoConfiguredClientCallsActualServer() {
        webClient.get()
                .uri("/api/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.status").isEqualTo("ok");
    }
}
```

`WebTestClient` is wired by Boot to the running test server, so relative URIs target the bound port. There is no need to manually construct `WebTestClient.bindToServer().baseUrl("http://localhost:8080")` for this case.

**Important:** Putting both `spring-boot-starter-web` and `spring-boot-starter-webflux` into the runtime application usually causes Spring Boot to select the **Servlet** application type because MVC takes precedence. Only add WebFlux to `testImplementation` to avoid accidentally altering production runtime dependencies.

## 15. Same `WebTestClient`, Different Between Mock-Bound and Live-Bound

A test API can use the same `WebTestClient` name in two modes:

**Mock environment:**

```java
@SpringBootTest
@AutoConfigureWebTestClient
class MockBoundExample {
    @Autowired
    WebTestClient client;
}
```

**Real HTTP environment:**

```java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealHttpExample {
    @Autowired
    WebTestClient client;
}
```

The snippets above are **illustrative patterns**, needing appropriate imports/dependencies. With `@AutoConfigureWebTestClient` in `MOCK`, the client can bind to the **application context** without opening a real TCP port. In `RANDOM_PORT`, `WebTestClient` is bound to the started server. **Do not assume a network socket exists merely because the test calls `.exchange()`**.

To verify a bug depending on Tomcat connectors, cookie serialization, proxy/real HTTP headers, or TLS, use a **real-bound client**. To test handler/validation logic quickly, mock-bound is usually cheaper. Choose the tool by failure mode rather than API name.

## 16. Spring WebFlux: `@LocalServerPort` Still Applies

`@LocalServerPort` is not exclusive to Tomcat. `@SpringBootTest(RANDOM_PORT)` works with **reactive web applications** when Boot selects WebFlux. For a standalone WebFlux project:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Reactive controller:

```java
package com.example.reactiveport;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ReactivePingController {

    @GetMapping("/api/ping")
    public Mono<String> ping() {
        return Mono.just("reactive-ok");
    }
}
```

Test:

```java
package com.example.reactiveport;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ReactivePortTest {

    @LocalServerPort
    int port;

    @Autowired
    WebTestClient client;

    @Test
    void nettyServerBindsARealRandomPort() {
        assertThat(port).isPositive();

        client.get()
                .uri("/api/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("reactive-ok");
    }
}
```

These snippets require `@SpringBootApplication` in the same project/package and the stated dependencies; this is a **WebFlux integration example**, not a complete standalone source if only copying controller/test. With the default WebFlux starter, the server uses Reactor Netty; the engine can be swapped, while `RANDOM_PORT`/`@LocalServerPort` still follows the Spring Boot web runtime.

If both MVC and WebFlux are on the **runtime** classpath and you intentionally want to test a reactive app, look into setting `spring.main.web-application-type=reactive`; do not assume WebFlux always wins when both starters are present.

## 17. The Assigned Port Belongs to the **Web Server**, Not the Client

Three things are easily confused:

```text
HTTP client local ephemeral port:  52042
HTTP server listen port:          49317
Database port:                    5432
```

During an HTTP test:

```text
Client 127.0.0.1:52042 ---> Server 127.0.0.1:49317
```

`@LocalServerPort` returns **49317**, the port the server is listening on, not `52042` of the client socket and not a database port or Testcontainers mapping.

Similarly, when an app sits behind a reverse proxy:

```text
Browser -> https://public.example.test:443
Proxy   -> http://127.0.0.1:49317
```

`@LocalServerPort` does not return `443` because that is the proxy's **public ingress port**. It only reflects the **local embedded application server** inside the test context; testing gateways/ingress requires a separate setup.

## 18. Why Not Hardcode Port 8080 in Tests?

Anti-pattern:

```java
String url = "http://localhost:8080/api/ping";
```

With `RANDOM_PORT`, this URL **has nothing to do** with the newly bound port. If a process on 8080 happens to return `{"status":"ok"}`, the test can **PASS falsely** even if your app under test has broken mapping, security, or data.

Proper way when a full URL is needed:

```java
String url = "http://127.0.0.1:" + port + "/api/ping";
```

Or use auto-bound `TestRestTemplate`/`WebTestClient` and relative paths. With a variable URL, tests should assert the server started, `port > 0`, response status/body, and expected behaviors.

Do not fix tests by forcing `server.port=8080` to match an old URL; that reintroduces collision problems, especially in CI.

## 19. `server.port=0` Differs from Finding a Free Port Yourself and Closing the Socket

A pattern often seen online:

```java
try (ServerSocket socket = new ServerSocket(0)) {
    int port = socket.getLocalPort();
}
// Socket is closed; another process can claim the port.
// Only afterward is Spring Boot configured with server.port=port.
```

**This is an anti-pattern** if the goal is “guaranteeing the port won't be contested.” Once closed, the socket no longer reserves ownership of the port. It is useful only to understand the `ServerSocket` API, **not as a port allocation design for HTTP tests**.

With Spring Boot tests:

```java
@SpringBootTest(
  webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
```

the server binds `0` directly and Spring Boot publishes the port already held. There is no self-inflicted gap between “check free port” and “bind actual listener.”

If a dependency **must know the port before the server starts**, redesign the dependency initialization/lifecycle or pass the URL after startup rather than closing a preallocated `ServerSocket`.

## 20. Standalone Java 17 Practice: Understanding Port-0 Sockets with an Open Listener

To see the OS port-assignment mechanism without Spring, the program below keeps the `ServerSocket` **open** while the client connects:

**`EphemeralPortDemo.java`:**

```java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.PrintWriter;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class EphemeralPortDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();

        try (ServerSocket server =
                     new ServerSocket(0, 1, loopback)) {
            int assigned = server.getLocalPort();
            ExecutorService executor =
                    Executors.newSingleThreadExecutor();

            try {
                Future<String> received = executor.submit(() -> {
                    try (Socket accepted = server.accept();
                         BufferedReader input = new BufferedReader(
                             new InputStreamReader(
                                 accepted.getInputStream(),
                                 StandardCharsets.UTF_8))) {
                        return input.readLine();
                    }
                });

                try (Socket client =
                             new Socket(loopback, assigned);
                     PrintWriter writer = new PrintWriter(
                             client.getOutputStream(), true,
                             StandardCharsets.UTF_8)) {
                    writer.println("ping");
                }

                System.out.println("port-assigned=" + (assigned > 0));
                System.out.println(
                        "server-received="
                                + received.get(5, TimeUnit.SECONDS));
            } finally {
                executor.shutdownNow();
            }
        }
    }
}
```

Run on JDK 17+:

```bash
javac EphemeralPortDemo.java
java EphemeralPortDemo
```

**Exact stdout when localhost networking works:**

```text
port-assigned=true
server-received=ping
```

Lesson learned: the OS selects the port and the **listener still owns the port** while the client uses it. In Spring Boot, the embedded server holds the socket listener and `@LocalServerPort` simply passes the bound port into tests after initialization. Do not reuse this snippet as a custom port allocator for Spring Boot.

## 21. When Is the Port Published and Why Can Early Configuration Fail?

A design mistake is creating a bean:

```java
@Configuration
class EarlyClientConfiguration {

    @Bean
    RestClient selfCallingClient(
            @Value("${local.server.port}") int port) {
        return RestClient.create("http://localhost:" + port);
    }
}
```

This is an **anti-pattern** for application startup with `server.port=0`. When Spring creates `EarlyClientConfiguration` and the `selfCallingClient` bean, the web server may not have finished binding yet and `local.server.port` does not exist yet, leading to placeholder resolution failure or lifecycle dependency cycles. In tests, the annotation on the **test instance** works because the web context starts before test methods run.

If the application genuinely needs to know its own port after startup, use an appropriate lifecycle event:

- `WebServerInitializedEvent` when the embedded web server is initialized.
- `WebServerApplicationContext.getWebServer().getPort()` **after startup**.
- `ApplicationReadyEvent` or a post-context-ready step when appropriate for the use case.

It is not recommended for a service to call its own public URL over HTTP just to run internal business logic; normally invoke service methods directly to avoid unexpected network loops/transactions/authorization issues.

## 22. Spring Boot Program Reading the Port After Server Init via Event

In application code (not tests), you can listen for:

```java
package com.example.portdemo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.boot.web.context.WebServerInitializedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.stereotype.Component;

@Component
public class ActualPortLogger
        implements ApplicationListener<WebServerInitializedEvent> {

    private static final Logger log =
            LoggerFactory.getLogger(ActualPortLogger.class);

    @Override
    public void onApplicationEvent(WebServerInitializedEvent event) {
        int port = event.getWebServer().getPort();
        String namespace =
                event.getApplicationContext().getServerNamespace();

        if (namespace == null) {
            log.info("Application HTTP server bound to port {}", port);
        }
    }
}
```

This file can be added to the MVC demo application. When the web server initializes, `event.getWebServer().getPort()` is the real port. Checking `getServerNamespace()` distinguishes the main web context from the management context when running a **separate management server**; namespaces can vary by design.

Do not read the port inside a component's constructor and conclude the server has started. An `ApplicationListener` must also be registered before the event fires; a Spring-managed listener bean in the context covers standard cases per Boot docs. When an app has multiple nested web contexts or custom web servers, identify **which context the event belongs to** before recording it.

## 23. If the Port Is Needed in Test Setup, Fetch It in `@BeforeEach` or `@Test`

Example:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class CallbackTest {

    @LocalServerPort
    int port;

    private String callbackBaseUrl;

    @BeforeEach
    void configureCallbackUrl() {
        callbackBaseUrl = "http://127.0.0.1:" + port;
    }

    @Test
    void usesActualPort() {
        assertThat(callbackBaseUrl).contains("127.0.0.1:");
        assertThat(port).isPositive();
    }
}
```

This is an **integration pattern**, needing JUnit/AssertJ/Spring imports and a matching app. The key point is not the assertions themselves, but **when the URL is built**: `@BeforeEach` runs after Spring TestContext has injected `port`.

Avoid:

```java
static String URL = "http://localhost:" + port;
```

because `port` is an instance field; it cannot be accessed from a static initializer. Also avoid assigning another field eagerly:

```java
String url = "http://localhost:" + port;
```

in a test field initializer: when the Java constructor/initializer runs, `port` may still be default `0`, capturing a wrong URL. Build the URL inside `@BeforeEach`/test methods rather than eager field initialization.

## 24. Why Is `@DynamicPropertySource` Unsuitable for Reading `@LocalServerPort`?

Spring TestContext normally evaluates `@DynamicPropertySource` **while building the ApplicationContext**, meaning **before the web server finishes starting**.

An anti-pattern:

```java
@LocalServerPort
int port;

@DynamicPropertySource
static void dynamicProperties(DynamicPropertyRegistry registry) {
    // Cannot read instance port here.
    // Even stashing in static can execute too early.
}
```

`@DynamicPropertySource` fits **dependencies started before the context**, such as Testcontainers PostgreSQL/Kafka or a mock HTTP server launched earlier by the test framework—not constructing the URL of the **Spring Boot server itself currently being bootstrapped**.

If a component must know its self URL at startup, review the architecture and lifecycle dependency. If another system needs a callback URL after the app listens, configure it via a post-bind event or post-startup test API. Do not try to write `local.server.port` into a dynamic property earlier than the event that produces it.

## 25. `@LocalManagementPort`: The Actuator Port Can Differ from the App Port

When an app runs Spring Boot Actuator on a **separate port**, there are two listeners:

```text
Application HTTP server:
  local.server.port       -> application endpoints

Management HTTP server:
  local.management.port   -> Actuator endpoints
```

Annotation import in Spring Boot 3.3:

```java
import org.springframework.boot.test.web.server.LocalManagementPort;
```

If `management.server.port` is not configured separately, Actuator may share the web server with the app, and no separate management listener exists. **Do not assume `@LocalManagementPort` always receives a distinct port.**

According to Spring Boot 3.3 testing docs, when an application is configured with a **management server on a different port**, `@SpringBootTest(RANDOM_PORT)` can assign **both the main server and management server** separate random ports in tests. Check runtime info instead of guessing the management port from `management.server.port` in properties files.

## 26. Testing Actuator on a Separate Management Port

This is a **standalone variant** of the MVC demo: add Actuator in Gradle:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-actuator'
```

Testing application and management ports when configured on different ports:

```java
package com.example.portdemo;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.boot.test.web.server.LocalManagementPort;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "server.address=127.0.0.1",
        "management.server.address=127.0.0.1",
        "management.server.port=9091",
        "management.endpoints.web.exposure.include=health"
    })
class SeparateManagementPortTest {

    @LocalServerPort
    int appPort;

    @LocalManagementPort
    int managementPort;

    @Test
    void portsAreBoundIndependently() {
        assertThat(appPort).isBetween(1, 65535);
        assertThat(managementPort).isBetween(1, 65535);
        assertThat(managementPort).isNotEqualTo(appPort);
    }
}
```

The test sets `management.server.port=9091` to **enable the separate management listener mechanism** as configured in the application. With `RANDOM_PORT` in Spring Boot 3.3, test bootstrapping supports choosing a random port for the management listener when a separate management server is used. Do not assert “managementPort must always equal 9091.”

To call `/actuator/health`, build the URL **with `managementPort`**, not the relative URL of `TestRestTemplate` bound to the application port:

```java
String healthUrl =
        "http://127.0.0.1:" + managementPort + "/actuator/health";
```

This is an in-test integration snippet. If the Actuator base path changes, Spring Security protects the endpoint, or separate management SSL is enabled, use the right base path/scheme/credentials. Do not expose the management port to the Internet for testing.

## 27. Comparing `server.port`, `local.server.port`, Management, and Testcontainers

| Case | Proper Discovery Property/Method | Do Not Use |
| --- | --- | --- |
| Test Spring Boot HTTP app | `@LocalServerPort`, `local.server.port` | Hardcode `8080` |
| Production server using `server.port=0` | `WebServerInitializedEvent` or `WebServerApplicationContext` after startup | `@LocalServerPort` in bean constructor |
| Actuator separate listener | `@LocalManagementPort`, `local.management.port` | App port to guess management URL |
| PostgreSQL Testcontainer mapped port | `container.getMappedPort(5432)` or Testcontainers JDBC URL | `@LocalServerPort` |
| Separate WireMock/mock server | Port exposed by mock server after start | Spring app's `local.server.port` |
| Browser via ingress/reverse proxy | Public route/ingress port and host | Embedded server port to guess public URL |
| JDK `HttpClient` outbound TCP source port | OS/socket networking semantics, rarely needed | Spring web server local port |
| WebSocket endpoint on same embedded server | `ws://host:<local.server.port>/...` or `wss` if TLS | An assumed separate WebSocket port |

`@LocalServerPort` cannot substitute for Testcontainers mapped ports. If an integration test needs the Spring app to connect to a DB container, inject the **DB URL** before Spring context startup via `@DynamicPropertySource` or Spring Boot service connections; that flows in the **reverse direction** compared to an HTTP test client discovering Spring's listener after startup.

## 28. `@LocalServerPort` in `MOCK`/`NONE`: Common Mistakes

Problematic example:

```java
@SpringBootTest
class IncorrectMockTest {
    @LocalServerPort
    int port;
}
```

`@SpringBootTest` defaults to `MOCK`, with no embedded HTTP listener; therefore no actual bound port exists for `local.server.port`. The test may fail with unresolved placeholder/injection errors or lack a valid port depending on setup.

Similarly:

```java
@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.NONE)
```

is designed not to create a web environment; `@LocalServerPort` cannot be used to call a server that was never started.

**Proper fixes:**

- If real networking is required, switch to `RANDOM_PORT`.
- If only testing controllers at the MVC layer, use `@WebMvcTest`/`MockMvc` or mock-bound setup.
- If the application context is needed without HTTP, remove port injection.

Do not add `@LocalServerPort` to every test class as “decoration” or assume the test library will automatically open a socket.

## 29. `DEFINED_PORT`: When Suitable and What Risks?

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.DEFINED_PORT)
```

starts the web server on the configured `server.port` (or default `8080` when unconfigured), unless overridden by profiles/properties. This mode is useful for integration tests that **strictly require a fixed port** so an external system can connect.

However, risks include:

- Port collisions between tests and a running IDE/server.
- Parallel CI jobs competing for the same host port.
- Tests accidentally hitting an older process occupying the port when checks are missing.
- Harder test reuse locally and in CI.
- A test class with a cached context holding the port across many methods.

In most HTTP integration tests for a service, prefer `RANDOM_PORT`. Use `DEFINED_PORT` only with a concrete reason, port ownership, and lifecycle cleanup. Even with `DEFINED_PORT`, tests can inspect the actual bound port after startup via `local.server.port`/web context instead of making blind assumptions.

## 30. Context Caching: The Port Does Not Automatically Change per Test Method

Spring TestContext framework **caches the ApplicationContext** across compatible tests for speed. If two test methods share the same Spring context, they normally share **the same embedded server and the same random port**.

```text
JUnit test method A ─┐
                     ├─ cached SpringBootTest ApplicationContext
JUnit test method B ─┘             |
                                   v
                          one embedded server
                          one bound local port
```

Therefore, never assert:

```text
portInMethodA != portInMethodB
```

that is not the contract of `RANDOM_PORT`. “Random” describes **how the server binds when a context starts**, not a requirement to change ports after every request/method.

When a context is closed/recreated (`@DirtiesContext`, differing profiles/configuration, or cache eviction), the new server may receive another port — yet the OS may still **reuse the same port number**. Tests must not depend on port uniqueness over time.

## 31. Parallel Testing and Context Independence

`RANDOM_PORT` reduces fixed-port contention when multiple application contexts run on the same host. It does not automatically make the entire test suite thread-safe.

Other sources of conflict:

- Shared database schemas/tables or test fixtures.
- Mutable static singleton state.
- Same file paths/temp directories.
- Background jobs emitting events onto a shared broker topic.
- Shared Redis caches/session stores.
- External API rate limits.
- A remaining **fixed** management port.
- A mock server/WireMock using a fixed port.
- Shared `@TestPropertySource`/system properties mutated while other tests run.

Design isolation by **resource ownership**: random HTTP ports for web apps, mapped ports for Testcontainers, test-specific databases/schemas/topics, and proper data cleanup or transaction boundaries. When running parallel Gradle test forks, determine whether processes/contexts share any external systems.

## 32. Transactions in Real HTTP Tests Do Not Auto-Rollback Server-Side Work

Spring Boot 3.3 docs warn: `@SpringBootTest` with `RANDOM_PORT` or `DEFINED_PORT` runs the **HTTP client and HTTP server on different threads**, so the test method's transaction and the transaction opened on the server are **not the same transaction**.

Example:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Transactional
class CreateOrderHttpTest {
    // Calling HTTP POST to create an order lets the server commit its own transaction.
    // Rolling back on the test thread does not undo the server-side DB commit.
}
```

This is an illustrative pattern requiring real `spring-tx`/test dependencies and persistence setup; it is **not a data cleanup mechanism**.

If a test executes `POST /orders` and the backend commits a row, the test needs cleanup via database transaction/fixture strategy, idempotent deletes, or isolated schemas/containers. Never assume `@Transactional` on the test method deletes state created by the HTTP server thread.

This is one reason to separate unit/slice tests (which have easily controlled transaction scopes) from real HTTP integration tests.

## 33. Bind Address Differs from Port: `127.0.0.1`, `localhost`, IPv4/IPv6

A TCP port only makes sense together with its **listening address and protocol**. For example:

```text
Server binds 127.0.0.1:49317   -> IPv4 loopback
Client connects ::1:49317     -> IPv6 loopback
```

If OS/hostname resolution prefers IPv6 while the server only binds IPv4, `http://localhost:49317` can occasionally fail in test setups. In the demo:

```properties
server.address=127.0.0.1
```

so tests use:

```java
"http://127.0.0.1:" + port
```

to keep IPv4 loopback consistent. In real apps, `server.address=0.0.0.0` binds all IPv4 interfaces, which is a network/security decision **unnecessary for local tests**.

`@LocalServerPort` only supplies the **port number**. It does not determine public hostnames, DNS, schemes, reverse proxy prefixes, or CORS origins. When an app uses an IPv6 literal, the URL may need the form `http://[::1]:<port>/...`.

## 34. HTTPS, `server.servlet.context-path`, and Proper Base URLs

When using HTTPS, a valid URL requires **scheme, host, port, and path**:

```text
https://127.0.0.1:<assigned-port>/<context-path>/api/ping
```

`@LocalServerPort` **does not return the scheme** and does not configure SSL trust for JDK `HttpClient`/`TestRestTemplate`. If the server has only an HTTPS listener and the client calls `http`, the failure is a handshake/protocol error, not a port discovery failure.

With MVC:

```properties
server.servlet.context-path=/demo
```

app routes sit under base path `/demo`; the real HTTP URL is typically:

```text
http://127.0.0.1:<port>/demo/api/ping
```

If using `TestRestTemplate` root URI auto-config, verify how the client handles context paths for your version and test setup; when unsure, construct full URLs including context path and assert. With WebFlux, the context path property differs from MVC Servlet (`spring.webflux.base-path` in compatible configs). Do not swap framework properties without checking.

The management endpoint base path defaults to `/actuator` and can be customized. When using a separate management port, confirm both context and management base paths independently.

## 35. Port `0` Does Not Guarantee All External Services Are Ready

Once the embedded HTTP server binds, `@LocalServerPort` is positive; however, that does not necessarily prove:

- External database fixtures or migrations have finished.
- Background consumers have subscribed to brokers.
- Caches are warmed.
- A remote dependency is ready.
- An asynchronously triggered task has completed.
- An external TLS reverse proxy has updated its route.

An HTTP integration test needs a **business-meaningful readiness condition**. If an HTTP endpoint depends on async setup, use bounded polling/eventual assertions instead of an arbitrary `Thread.sleep(10000)` to “wait for the server.”

`@SpringBootTest` completes context startup before test methods run, yet async jobs launched by the app have their own lifecycles. **A bound port proves the listener**, not a comprehensive health check of every dependency.

## 36. Checking the Actual Port Without Parsing Startup Logs

There are several valid ways:

| Method | Where Used | Advantage |
| --- | --- | --- |
| `@LocalServerPort int port` | Spring Boot tests | Simple, valid after test context startup |
| `@Value("${local.server.port}")` | Test field or post-startup code | Accesses equivalent property |
| `Environment.getProperty("local.server.port")` | After web server initialized | Explicitly reads Environment |
| `WebServerApplicationContext.getWebServer().getPort()` | Running context | Accesses embedded server object |
| `ApplicationListener<WebServerInitializedEvent>` | Runtime listener after bind | Receives startup event and actual port |
| `TestRestTemplate` | Real HTTP tests | Supports relative URLs without manual concatenation |
| `WebTestClient` | WebFlux or MVC tests with WebFlux test dependency | Fluent HTTP assertions |

Do not regex-parse a `Tomcat started on port ...` stdout line, because startup log format, server type, and logger configuration can all change. Rely on the framework's published contract instead of scraping output.

## 37. Diagnosing Test Failures by Symptom

| Symptom | Prominent Possibility | Check |
| --- | --- | --- |
| `Could not resolve placeholder 'local.server.port'` | No real server, injected too early | `MOCK` or `RANDOM_PORT`? Test field or bean constructor? |
| Injected port is `0` | Field uninjected / read too early / bad test setup | Lifecycle, instance vs static field, test annotations |
| `Connection refused` on 8080 | Client hardcodes old port | Use `@LocalServerPort` or auto-bound test client |
| `Connection refused` on random port | Server shut down, hostname/bind mismatch, wrong context | Web server lifecycle, `server.address`, context cache |
| `Address already in use` | Fixed port occupied, external port still fixed | `DEFINED_PORT`, `server.port`, `management.server.port`, mocks |
| Test PASSES yet app under test is broken | HTTP request hit another process | Log actual port, test unique endpoint, drop 8080 |
| HTTP 404 | Right port, wrong route/context path | `/api/ping`, context path, filters/router |
| HTTP 401/403 | Security policy | Test auth/CSRF; do not blame the port |
| TLS handshake exception | `https`/`http` mix-up or trust setup | Server SSL config, client TLS |
| `@LocalManagementPort` fails to resolve | No separate management server or Actuator missing | Management listener and version |
| Port matches previous run | OS reused it or context cached | Do not assert uniqueness across executions |
| Missing `WebTestClient` bean | Missing WebFlux test classpath or differing config | Boot 3.3 dependencies, running vs mock binding |
| Port changes on another test class | Context recreated | Context cache profiles/configuration |
| Server runs yet callback URL is wrong | URL built before injection | Move logic into `@BeforeEach`/test method |
| Bind error only when running parallel | A dependency still uses a fixed port | Check Testcontainers, WireMock, management, forks |

When port failures occur, **resist immediately adding “retry test 3 times.”** Identify whether it is port collision, bind/interface mismatch, startup race, closed context, or hitting the wrong server. Retries can mask test flakiness that needs fixing.

## 38. Testing Ports with Meaningful Assertions

A solid test confirms at least:

1. `@LocalServerPort` returns a valid positive number.
2. `webContext.getWebServer().getPort()` matches the injected port.
3. A real HTTP request over that port returns the expected status.
4. Body/headers reflect the **actual test application** running.
5. No reliance on fixed port numbers or parsing startup logs.

Sensible assertions:

```java
assertThat(port).isBetween(1, 65535);
assertThat(webContext.getWebServer().getPort()).isEqualTo(port);
```

Unhelpful assertions:

```java
assertThat(port).isEqualTo(8080);
assertThat(port).isNotEqualTo(previousTestPort);
```

The core lesson is that **the port is discovered after binding** and tests interact with the right server—not proving a random number generator.

If you want to test two independent contexts simultaneously, start two servers assigned port 0 by the OS in **overlapping lifecycles**, confirm both accept connections, and use their respective URLs. Do not assert that ports from **two sequential runs** must differ.

## 39. Ports and Test Scope: Do Not Confuse Testcontainers with Spring Server

A complex integration test may involve:

```text
Spring Boot app HTTP      127.0.0.1:<appPort>
Testcontainers PostgreSQL localhost:<mappedDbPort>
WireMock downstream       localhost:<wireMockPort>
Kafka broker              localhost:<mappedBrokerPort>
```

For the Spring app, `@LocalServerPort` is solely `appPort`.

For Testcontainers, obtain mapped info from the container lifecycle, e.g., `container.getJdbcUrl()`, `container.getMappedPort(5432)`, or Spring Boot `@ServiceConnection` on supported versions. For WireMock/test stubs, fetch the stub server's actual URL after startup. These ports **are unrelated** to `local.server.port`.

When a test sends a callback URL to a mock service needing `appPort`, only update the callback URL **after the Spring server has bound**. If application code needs a callback URL during bean construction, redesign how the dependency is passed instead of guessing the port.

## 40. Port 0 Does Not Replace Authorization, Test Isolation, or Network Safety

Using an OS-assigned port does not make the server private. Binding `0.0.0.0`/`::` allows listening on multiple network interfaces on a **dynamically assigned port**. Tests exposing unsecured endpoints can still be reached by other hosts if network policy permits.

Recommended for local tests:

```properties
server.address=127.0.0.1
```

or the corresponding IPv6 loopback config. When testing remote/container networking, configure host mappings properly per environment rather than opening ports carelessly.

Some test frameworks drive browsers in a separate container, where `127.0.0.1` points to **the browser container itself**, not the test JVM. In those cases, you need network aliases/exposed mappings from the integration environment; `@LocalServerPort` still reports only the **JVM-side port** without altering host networking automatically.

Do not log access tokens/cookies or sensitive data inside URLs just because you are debugging a random port. You can log `port` and route templates in test diagnostics without printing raw Authorization/query/body values.

## 41. Test Suite Design: Layering Instead of Using `RANDOM_PORT` Everywhere

A large Spring Boot test suite should balance cost:

| Test Layer | How Implemented | Goal |
| --- | --- | --- |
| Unit test | JUnit/Mockito without Spring | Pure business logic |
| MVC slice | `@WebMvcTest`, `MockMvc` | Controller mapping/validation/security rules |
| Full app mock web | `@SpringBootTest` + `@AutoConfigureMockMvc` | Multi-bean wiring without sockets |
| Full app real web | `@SpringBootTest(RANDOM_PORT)` | HTTP transport, container, filters, serialization |
| End-to-end system | App + DB/broker/proxy or deployed env | Cross-service contracts, TLS/ingress |

`RANDOM_PORT` incurs startup cost, server threads, and test context resources. It fits tests where **real HTTP transport adds value**, and is unnecessary for every service method.

Keep test classes sharing identical configuration to leverage Spring context caching appropriately, while preventing application state from leaking across methods. `@DirtiesContext` should only be used when actually needing to recreate the context; it slows the suite and changes ports on rebuild.

## 42. Practice and Review Questions

1. Why does default `@SpringBootTest` not give `@LocalServerPort` a real port?
2. What does `RANDOM_PORT` do with `server.port`?
3. Why does `server.port=0` not mean the final HTTP port is `0`?
4. Is `local.server.port` published before or after the embedded server binds?
5. Why does `@LocalServerPort` fit a test field yet easily break inside an application bean constructor?
6. Where does `TestRestTemplate.getForEntity("/api/ping", ...)` learn the random port?
7. What is the difference between mock-bound and live HTTP-bound `WebTestClient`?
8. In the demo, why do tests avoid asserting that the port is `8080`?
9. If two test methods reuse a cached context, must they use two different ports?
10. Why not open `ServerSocket(0)` and close it to “reserve” a free port for Spring?
11. When a test has a separate management port, which annotation retrieves it?
12. Is `@LocalServerPort` the public ingress port or the internal listener port?
13. If a `@Transactional` test sends a real HTTP POST, why does rolling back the test transaction not necessarily roll back the server transaction?
14. With `server.servlet.context-path=/demo`, how does the request URL change?
15. Why can `localhost` resolve to IPv6 loopback while the server binds only IPv4?
16. Can `@DynamicPropertySource` be used to read the main app's port before startup?
17. When both `starter-web` and `starter-webflux` are present at runtime, which web application type does Spring Boot usually choose?
18. Does a positive injected port suffice to prove databases/brokers are ready?
19. In a setup with Testcontainers DB, how do you get the mapped DB port and why not use `@LocalServerPort`?
20. When is `DEFINED_PORT` justified, and what risk does it increase?

**Exercise A:** Run the MVC demo and observe `RANDOM_PORT` tests PASS. Change the test URL to `8080` and verify why the test no longer guarantees hitting the right app.

**Exercise B:** Add a `@SpringBootTest(MOCK)` test using `MockMvc` and compare runtime, execution stack, and the absence of sockets.

**Exercise C:** Run the same test class twice and record the port. If both runs get the same number, explain why that still satisfies the `RANDOM_PORT` contract.

**Exercise D:** Enable a separate management port and `@LocalManagementPort`; confirm two HTTP endpoints can be called on two different ports per test configuration.

**Exercise E:** Using a standalone WebFlux starter, verify the Reactor Netty listener with `@LocalServerPort` and real-bound `WebTestClient`; do not use fixed ports.

## 43. Conclusion: Request Port 0, Wait for Bind, Read Actual Port, Then Send HTTP

The right mental sequence:

```text
RANDOM_PORT / server.port=0
        |
        v
OS picks and holds listener port on bind
        |
        v
WebServerInitializedEvent
        |
        v
local.server.port = bound HTTP port
        |
        v
@LocalServerPort injected into test
        |
        v
TestRestTemplate / WebTestClient / JDK HttpClient calls the right URL
```

**Four essentials to remember:**

1. `@SpringBootTest(RANDOM_PORT)` runs a **real HTTP server**; `MOCK` runs no listener.
2. `@LocalServerPort` delivers the **bound port** into tests—it does not return `server.port=0` and does not require a fixed port number.
3. `local.server.port` appears **after** server initialization; early application startup must not depend on it.
4. Test management ports, database containers, mock servers, and proxies must discover their **respective port types**, rather than using one annotation for everything.

Understanding this boundary prevents port collisions in integration tests, avoids calling stale processes, and enables parallel execution in CI without forcing multiple apps onto one shared HTTP port.

### References

- Spring Boot 3.3 — Testing Spring Boot Applications, Running Server / RANDOM_PORT: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3 — Embedded Web Servers, Random Port and Discover HTTP Port at Runtime: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- Spring Boot 3.3.13 — `LocalServerPort` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/web/server/LocalServerPort.html
- Spring Boot 3.3.13 — `LocalManagementPort` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/web/server/LocalManagementPort.html
- Spring Boot 3.3.13 — `ServerPortInfoApplicationContextInitializer` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/context/ServerPortInfoApplicationContextInitializer.html
- Spring Boot 3.3 — Actuator HTTP Management Port: https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html
- Spring Framework — TestContext framework and context caching: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html
- Oracle Java 21 — `ServerSocket` and `getLocalPort`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/ServerSocket.html
- Oracle Java 21 — HTTP client: https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html