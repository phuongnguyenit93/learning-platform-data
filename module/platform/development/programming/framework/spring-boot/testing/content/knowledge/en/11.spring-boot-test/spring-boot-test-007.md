# `@LocalServerPort`, management ports, and target URLs in Spring Boot tests

## Goal

In Spring Boot integration tests, hardcoding URLs like `http://localhost:8080/api/orders` can cause tests to pass on a local machine yet fail in CI: the port may be occupied, configured differently, or multiple test processes may run concurrently. It becomes even easier to get confused when an application uses **Spring Boot Actuator**: business endpoints and management endpoints may run **on two different HTTP servers/ports**.

The `@LocalServerPort` annotation lets tests retrieve **the application's actual HTTP port after the server has started**. If a separate management server exists, `@LocalManagementPort` retrieves **the actual management port**. From the port, hostname, scheme, and path, tests construct **accurate target URLs** for each endpoint type.

After this lesson, you will be able to:

- Distinguish `@SpringBootTest` with `MOCK`, `RANDOM_PORT`, `DEFINED_PORT`, and `NONE`.
- Know when `@LocalServerPort` has a value and why `server.port=0` **differs** from the listening port.
- Distinguish `server.port`, `local.server.port`, `management.server.port`, and `local.management.port`.
- Configure Spring Boot Actuator on the **same port** or a **separate port** and call `/actuator/health` at the right address.
- Write integration tests with Java 17, JUnit Jupiter, and Spring Boot using random ports, sending real HTTP and checking both status codes and JSON bodies.
- Handle changed context paths, management base paths, bind addresses, SSL/HTTPS, and security.
- Analyze `Connection refused`, 404, 401/403, port 0, or failed bean injection errors.
- Choose `MockMvc`, `TestRestTemplate`, `WebTestClient`, or Java `HttpClient` according to test scope.

Examples use **Spring Boot 3.3.x, Servlet MVC, Java 17**; import packages and client APIs may differ in newer Spring Boot lines. The example is presented as a standalone project that can be created and run via Gradle Wrapper.

## 1. Why distinguish configured ports from actual runtime ports?

Suppose a test writes:

~~~java
HttpRequest request = HttpRequest.newBuilder(
        URI.create("http://localhost:8080/api/greeting"))
        .GET()
        .build();
~~~

This is an illustrative Java snippet without full classes/imports. It **assumes** the test application is listening on port 8080. That assumption breaks when:

- `@SpringBootTest(webEnvironment = RANDOM_PORT)` asks the OS to pick an available port;
- the project configures a different `server.port`;
- another application already holds port 8080;
- multiple tests or modules run in parallel;
- tests run inside a container where `localhost` points to the client container rather than the intended server;
- the server binds only to a specific network interface.

With `RANDOM_PORT`, the configuration essentially means `server.port=0`: **0 is a request to find a free port**, not an address clients can connect to. Once the embedded server binds successfully, there is an **actual port** (for example 51237, varying across runs). The test reads that port and builds the URL.

~~~text
@SpringBootTest(webEnvironment = RANDOM_PORT)
         |
         v
Boot asks embedded server to bind port 0
         |
         v
OS allocates a free port, e.g., 51237
         |
         v
Spring publishes local.server.port = 51237
         |
         v
@LocalServerPort int port  --> 51237
         |
         v
Client calls http://127.0.0.1:51237/api/greeting
~~~

The number 51237 is **purely illustrative**, not a fixed predictable output. A proper test must never `assertEquals(51237, port)`. It should verify `port > 0` and send HTTP to the injected port.

## 2. `webEnvironment` modes of `@SpringBootTest`

`@SpringBootTest` loads a Spring Boot application context, yet **not every mode starts a real server**.

| Mode | Real HTTP server? | Used to verify | `@LocalServerPort` |
| --- | --- | --- | --- |
| `MOCK` (default) | No | Bean wiring, MVC MockMvc, many config tests | Normally no runtime server port |
| `RANDOM_PORT` | Yes, picks an available port | End-to-end HTTP over loopback, codecs, servlet container | Present when real web server starts |
| `DEFINED_PORT` | Yes, uses configured or default port | Tests requiring a specific port, very prone to collisions | Can retrieve running port; often unnecessary if known, though config check matters |
| `NONE` | No | Scenarios needing no web environment | No web-server port |

`MOCK` lets you use `@AutoConfigureMockMvc` with Servlet MVC without opening a TCP port. It can be faster and less sensitive to networking. `RANDOM_PORT` verifies **a real HTTP request** passing through the embedded server; suitable when confirming HTTP serialization, filters, status codes, headers, cookies, port routing, or servlet container behavior. `DEFINED_PORT` can collide if another service uses the port on the same machine, so **prefer `RANDOM_PORT` for integration tests**.

Proper annotation usage:

~~~java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealHttpIntegrationTest {

    @LocalServerPort
    int port;

    // @Test with a real HTTP client...
}
~~~

This is a snippet; the runnable files are in section 5. Merely placing `@LocalServerPort` on a JUnit test class **that does not bootstrap a server** will not start a server automatically. Before using the annotation, choose a web environment with a running listener.

### What is `@LocalServerPort`?

Spring Boot 3.3 declares the annotation at:

~~~java
import org.springframework.boot.test.web.server.LocalServerPort;
~~~

It is a convenient shorthand equivalent to `@Value("${local.server.port}")` for injecting the runtime property. The `local.server.port` property is published **after the embedded server starts and fires its initialization event**, not as an initial configuration value. Therefore:

- **`server.port`**: requested port from configuration; `0` means pick a random port.
- **`local.server.port`**: actual port after the server begins listening.
- **`@LocalServerPort`**: injects `local.server.port` into a test field/parameter as supported by Boot Test.

Do not put `@LocalServerPort` into a production bean constructor expecting the property to always be available during bean creation. Test instances are prepared by Spring TestContext after server initialization; production beans may be created too early to see this runtime value.

## 3. Management port: does Actuator share or run separately?

**Spring Boot Actuator** provides operational/management endpoints such as `/actuator/health` and `/actuator/info`. They are **not the same thing** as business controllers like `/api/greeting`.

By default, when an app uses HTTP Actuator without a separate management port configured, management endpoints are usually served on the **same port as the application** (subject to exposure and security conditions). For example:

~~~text
http://127.0.0.1:<application-port>/api/greeting
http://127.0.0.1:<application-port>/actuator/health
~~~

In this scenario, constructing Actuator URLs using the **application port** makes sense, and you should not assume a separate server's `local.management.port` property exists.

When `management.server.port` is set to a different port from the application port, Spring Boot can create a **separate management web server/context**:

~~~text
                       Spring Boot test process
                                |
                 +--------------+------------------+
                 |                                 |
       Application HTTP server             Management HTTP server
       server.port = 0                     management.server.port = 0
       local.server.port = 51237           local.management.port = 53241
                 |                                 |
      /api/greeting                          /actuator/health
                 |                                 |
       @LocalServerPort                  @LocalManagementPort
                 |                                 |
       http://127.0.0.1:51237/...         http://127.0.0.1:53241/...
~~~

The two sample ports 51237 and 53241 only illustrate the distinction. **Never hardcode them**.

### Four properties to remember

| Property/annotation | Meaning | When to use? |
| --- | --- | --- |
| `server.port` | Port the application server is asked to bind; `0` selects a free port | Application configuration |
| `local.server.port` / `@LocalServerPort` | Actual bound application port | HTTP tests hitting the app server |
| `management.server.port` | Requested management port; omitting usually shares app port; `0` requests a separate random port when management server is configured separately | Actuator configuration |
| `local.management.port` / `@LocalManagementPort` | Actual management web server port published when a separate server exists | Testing Actuator endpoints on the management server |

In Spring Boot 3.3, the `@LocalManagementPort` import is:

~~~java
import org.springframework.boot.test.web.server.LocalManagementPort;
~~~

It is designed to inject the runtime management HTTP port, equivalent to `@Value("${local.management.port}")` when published by the management server.

**Essential distinction:** `management.server.port=0` is an **input configuration**, whereas `@LocalManagementPort` is the **allocated port result after startup**. Never call Actuator with `http://localhost:0/actuator/health`.

### How does `RANDOM_PORT` affect the management port?

In Spring Boot 3.3, when `@SpringBootTest(webEnvironment = RANDOM_PORT)` loads an app whose **management server uses a different port than the application**, Boot also arranges for the management server to use a random port for testing. Still, to keep lessons explicit and independent of cross-version changes, the example sets **`management.server.port=0` explicitly**. That clearly expresses the intent: a separate, OS-allocated management port.

**Do not infer** that the management port equals `@LocalServerPort`, or that `@LocalManagementPort` always resolves when Actuator is absent from the classpath, HTTP management endpoints/servers are disabled, or management shares the main application server.

## 4. Target URLs include more than just the port

A URL used in tests usually looks like:

~~~text
<scheme>://<host>:<port><context-prefix><endpoint-path>?<query>
~~~

Example:

~~~text
http://127.0.0.1:51237/api/greeting
http://127.0.0.1:53241/actuator/health
~~~

**Even with the right port, a URL can fail** if host, protocol, or path is wrong:

- **Scheme:** `http` if TLS is off; must use `https` if SSL is enabled.
- **Host:** `127.0.0.1` is IPv4 loopback; works when test client and embedded server run in the same network namespace and the server binds a compatible address. `localhost` can resolve to IPv4 or IPv6 depending on the system.
- **Port:** obtained from `@LocalServerPort`/`@LocalManagementPort`, never copied from example numbers.
- **Servlet MVC applications:** `server.servlet.context-path=/shop` changes controller `/api/greeting` into `/shop/api/greeting`.
- **Actuator base path:** defaults to `management.endpoints.web.base-path=/actuator`, changeable to e.g. `/manage`.
- **Management server base path:** if Actuator runs on a separate port, `management.endpoints.web.base-path` is resolved relative to `management.server.base-path` (if configured).

When the management server shares the Servlet app port, Actuator endpoints are typically affected by `server.servlet.context-path`. When management uses a separate port, do not blindly prepend `server.servlet.context-path` to management URLs: paths follow the **management context configuration**, not necessarily the app context path.

### Three path scenarios to distinguish

| Scenario | Application URL | Health URL |
| --- | --- | --- |
| Default, Actuator shares port | `http://127.0.0.1:APP/api/greeting` | `http://127.0.0.1:APP/actuator/health` |
| Separate management port, default base path | `http://127.0.0.1:APP/api/greeting` | `http://127.0.0.1:MGMT/actuator/health` |
| App `server.servlet.context-path=/shop`, separate management, `management.endpoints.web.base-path=/ops` | `http://127.0.0.1:APP/shop/api/greeting` | `http://127.0.0.1:MGMT/ops/health` (when `management.server.base-path` is unchanged) |

`APP` and `MGMT` are placeholders, not environment variable names. They stand for the actual runtime port values injected by Spring.

## 5. Complete Java 17 + Spring Boot 3.3 project: testing both ports

This is a **runnable example** using Servlet MVC and Spring Boot Actuator, requiring no database or external systems. There are two integration test classes:

1. `ApplicationPortHttpTest` tests real HTTP on a **random application port**.
2. `SeparateManagementPortHttpTest` adds `management.server.port=0`, checks **two different ports**, calls the controller on the application port, and calls health on the management port.

It uses **Java 17 `HttpClient`** so learners clearly see URLs built from ports. Neither `WebTestClient` nor RestAssured is needed for this example.

### 5.1. File structure

~~~text
port-management-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/testing/
    │   ├── DemoApplication.java
    │   └── GreetingController.java
    └── test/java/com/example/testing/
        ├── ApplicationPortHttpTest.java
        └── SeparateManagementPortHttpTest.java
~~~

Wrapper files should be generated by an appropriate Gradle installation or already exist in the repository. Never copy `gradle-wrapper.jar` manually as text.

**`settings.gradle`**

~~~groovy
rootProject.name = 'port-management-demo'
~~~

**`build.gradle`** (Groovy DSL; example uses Java 17 and Spring Boot 3.3.5):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

Dependency breakdown:

- `spring-boot-starter-web` provides the Servlet MVC environment and embedded web server, plus Jackson JSON support in this version.
- `spring-boot-starter-actuator` provides management endpoints, including health.
- `spring-boot-starter-test` includes Spring TestContext, JUnit Jupiter, and common testing utilities.
- `junit-platform-launcher` is the runtime launcher enabling Gradle to execute Jupiter.
- `useJUnitPlatform()` ensures the test task uses JUnit Platform.
- If using another Gradle/Boot version, verify compatibility. Do not mix Boot 3.3 dependencies with Boot 4 annotations/APIs without confirmation.

### 5.2. Real HTTP application

**`src/main/java/com/example/testing/DemoApplication.java`**

~~~java
package com.example.testing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/testing/GreetingController.java`**

~~~java
package com.example.testing;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    @GetMapping("/api/greeting")
    public GreetingResponse greeting() {
        return new GreetingResponse("hello", 1);
    }

    public record GreetingResponse(String message, int version) {
    }
}
~~~

The controller exposes one stable endpoint:

~~~http
GET /api/greeting HTTP/1.1
Host: 127.0.0.1:<application-port>
~~~

With Jackson JSON serialization, the expected body has these values:

~~~json
{
  "message": "hello",
  "version": 1
}
~~~

Property ordering in the JSON object is not enforced here; tests parse with `ObjectMapper` and check each field's value. The simple payload keeps focus on **addresses/ports** instead of database or complex business noise.

### 5.3. Testing the application port with `@LocalServerPort`

**`src/test/java/com/example/testing/ApplicationPortHttpTest.java`**

~~~java
package com.example.testing;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = DemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ApplicationPortHttpTest {

    @LocalServerPort
    private int applicationPort;

    @Autowired
    private ObjectMapper mapper;

    private final HttpClient client = HttpClient.newHttpClient();

    private String appUrl(String path) {
        return "http://127.0.0.1:" + applicationPort + path;
    }

    @Test
    void injectedApplicationPortIsARealPort() {
        assertTrue(applicationPort > 0);
        assertTrue(applicationPort <= 65535);
    }

    @Test
    void applicationEndpointRespondsOverRealHttp() throws Exception {
        URI uri = URI.create(appUrl("/api/greeting"));
        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());

        JsonNode body = mapper.readTree(response.body());
        assertEquals("hello", body.path("message").asText());
        assertEquals(1, body.path("version").asInt());
    }
}
~~~

**Why doesn't this test use 8080?** `applicationPort` only receives its actual value after the Spring Boot test context and web server initialize. Therefore `appUrl` uses the Spring-injected port. The test requires client and server to run in the **same local network environment** so `127.0.0.1` reaches the server.

**Why `@Autowired ObjectMapper`?** That is the Boot application's Jackson mapper, parsing JSON without fragile plain-text comparisons. If key order or whitespace changes while data remains valid, the test does not fail needlessly.

**Why set `timeout`?** Request timeouts prevent tests from hanging indefinitely when a server fails to respond; connect timeouts and response timeouts are separate concepts, and systems with slower I/O must choose suitable limits. The 5-second value is an example, not an SLA.

This class has **2 JUnit test invocations**, expected to pass if the project starts and the endpoint responds properly.

### 5.4. Testing a separate management port with `@LocalManagementPort`

**`src/test/java/com/example/testing/SeparateManagementPortHttpTest.java`**

~~~java
package com.example.testing;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalManagementPort;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = DemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
                "management.server.port=0",
                "management.endpoints.web.exposure.include=health"
        })
class SeparateManagementPortHttpTest {

    @LocalServerPort
    private int applicationPort;

    @LocalManagementPort
    private int managementPort;

    @Autowired
    private ObjectMapper mapper;

    private final HttpClient client = HttpClient.newHttpClient();

    private String appUrl(String path) {
        return "http://127.0.0.1:" + applicationPort + path;
    }

    private String managementUrl(String path) {
        return "http://127.0.0.1:" + managementPort + path;
    }

    private HttpResponse<String> get(String url) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                URI.create(url))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        return client.send(
                request, HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void applicationAndManagementHaveDifferentRuntimePorts() {
        assertTrue(applicationPort > 0);
        assertTrue(managementPort > 0);
        assertNotEquals(applicationPort, managementPort);
    }

    @Test
    void applicationEndpointUsesApplicationPort() throws Exception {
        HttpResponse<String> response =
                get(appUrl("/api/greeting"));

        assertEquals(200, response.statusCode());

        JsonNode body = mapper.readTree(response.body());
        assertEquals("hello", body.path("message").asText());
        assertEquals(1, body.path("version").asInt());
    }

    @Test
    void actuatorHealthUsesManagementPort() throws Exception {
        HttpResponse<String> response =
                get(managementUrl("/actuator/health"));

        assertEquals(200, response.statusCode());

        JsonNode body = mapper.readTree(response.body());
        assertEquals("UP", body.path("status").asText());
    }
}
~~~

This class has **3 test invocations**. In Spring Boot 3.3.x, `RANDOM_PORT` and `management.server.port=0` cause both the app server and management server to bind real OS-assigned ports, not port 0. Two servers binding on compatible loopback addresses cannot simultaneously share one TCP port; `assertNotEquals` reflects the **split-port** configuration requirement.

**Note:** `@LocalManagementPort` is only meaningful when a separate management HTTP server has actually initialized and published `local.management.port`. If you remove the Actuator starter or disable HTTP management endpoints/servers, do not assume injection continues to work. When Actuator shares the app port, use the application port to call health instead of forcing a separate management port injection.

### 5.5. Why does the health response return `"UP"`?

In the demo project with no database, external queue, or failing health contributor, aggregate health is normally `UP` with HTTP status 200. Adding a database/Redis/custom `HealthIndicator` can cause the endpoint to return `DOWN` or `OUT_OF_SERVICE` with another status code per configuration. Tests should assert results **matching prepared fixtures and infrastructure**, rather than hardcoding `UP` for all environments.

Spring Boot Actuator also enforces exposure and security policies. In the demo starter **without** Spring Security and with health exposed, HTTP GET on the management port returns health JSON. In real apps with security, proxies, or health groups, status may be 401/403 if unauthorized or unexposed; **never disable security** solely to get a 200 without honoring the contract.

### 5.6. Running both test classes

From the root directory containing Gradle Wrapper:

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Run a single class:

~~~bash
./gradlew test --tests 'com.example.testing.SeparateManagementPortHttpTest'
~~~

The example suite contains **2 + 3 = 5 `@Test` methods**, one invocation each. Expect **5 tests passing** when the server and demo dependencies work properly. There are no `System.out.println` statements in test code, so no fixed business stdout; Gradle prints `BUILD SUCCESSFUL` and generates reports at:

~~~text
build/
├── reports/tests/test/index.html
└── test-results/test/
    ├── TEST-com.example.testing.ApplicationPortHttpTest.xml
    └── TEST-com.example.testing.SeparateManagementPortHttpTest.xml
~~~

Check the fresh XML/HTML reports to verify actual executed tests. `UP-TO-DATE` or `FROM-CACHE` means the task may have reused earlier outputs; when diagnosing, use `./gradlew test --rerun-tasks`.

If a project does not yet have a Wrapper, you need a compatible installed Gradle to bootstrap one, e.g., `gradle wrapper --gradle-version 8.8 --distribution-type bin` for the Boot 3.3.x/Java 17 demo. Then commit `gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.properties`, and `gradle-wrapper.jar` per repo policy. In real codebases, **use the existing Wrapper**, without arbitrarily upgrading versions just to match a tutorial.

## 6. When Actuator shares the application port

If `management.server.port` is **not** set separately from the application and Actuator is present, the health URL normally uses the main app port:

~~~java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class SharedPortExampleTest {

    @LocalServerPort
    int port;

    @Test
    void healthWouldUseApplicationPort() {
        String url = "http://127.0.0.1:" + port
                + "/actuator/health";
        // Use a real HTTP client to send GET and assert response.
    }
}
~~~

This is a **path-illustration snippet**, not a test with full assertions; treat only the project in section 5 as complete runnable code. With default configuration and the Actuator dependency, this URL serves health on the app port.

In real codebases with `server.servlet.context-path`, `management.endpoints.web.base-path`, or custom security, build the URL from those properties. Avoid hardcoding `/actuator/health` as an immutable contract.

### Does `@LocalManagementPort` always equal `@LocalServerPort`?

**Do not assume so.** Both names and properties are designed for two distinct roles. When the management server is **separate**, they reflect different ports. When Actuator **shares** the application server, the most reliable approach is constructing the management URL from the **application port** (if the endpoint is exposed), rather than requiring injection of `local.management.port` for a separate server that does not exist.

The primary purpose of `@LocalManagementPort` is not to be “an alias for the main port” but to help discover the **runtime management port** when a separate management server receives a port.

## 7. Use `TestRestTemplate`, `WebTestClient`, or Java `HttpClient`?

You do not always need to build every URL manually if a client supports Spring Boot's base URI. However, when a separate management port exists, know **which server that client targets**.

### 7.1. `TestRestTemplate` in Spring Boot 3.3

With `@SpringBootTest(webEnvironment=RANDOM_PORT)`, Spring Boot supports autowiring `TestRestTemplate`, preconfigured to call the application server via relative paths.

~~~java
@Autowired
TestRestTemplate rest;

@Test
void applicationRoute() {
    ResponseEntity<String> response =
            rest.getForEntity("/api/greeting", String.class);
    assertEquals(HttpStatus.OK, response.getStatusCode());
}
~~~

This snippet assumes a test class with JUnit/Spring Web and Spring TestRestTemplate imports. In Boot 3.3, import `org.springframework.boot.test.web.client.TestRestTemplate`; it is not ordinary `RestTemplate`.

When calling a **management server on another port**, do not expect `rest.getForEntity("/actuator/health", ...)` to automatically switch to the management port; the default running-server test client is bound to the **application root URI**. You can pass an absolute URL containing the management port:

~~~java
String healthUrl = "http://127.0.0.1:"
        + managementPort + "/actuator/health";
ResponseEntity<String> response =
        rest.getForEntity(healthUrl, String.class);
~~~

This snippet illustrates code inside a test with `managementPort` already injected. With Spring Security, SSL, or complex auth, pick a client/configuration matching the contract instead of expecting `TestRestTemplate` to handle every edge case automatically.

### 7.2. `WebTestClient`

`WebTestClient` offers a fluent API for inspecting HTTP responses and bodies. Spring Boot 3.3 can configure the client against the running server to use relative URIs in appropriate tests; **Spring WebFlux must be on the test classpath** to use this client in many Boot 3.x configurations. Do not add all of WebFlux just to test ports if Java `HttpClient` already fits.

Conceptual example:

~~~java
webTestClient.get().uri("/api/greeting")
        .exchange()
        .expectStatus().isOk();
~~~

This snippet assumes `webTestClient` is injected/configured in a test; it is not a standalone class. If you want to call a separate management server, you need the **right base URL for the management port** or an absolute URI accepted by the client; never assume relative URIs auto-select the management port.

### 7.3. Java 17 `HttpClient`

`java.net.http.HttpClient` is part of the JDK, requires no extra HTTP test client dependency, and makes every part of the URL explicit:

~~~java
URI uri = URI.create(
        "http://127.0.0.1:" + applicationPort + "/api/greeting");

HttpRequest request = HttpRequest.newBuilder(uri)
        .GET()
        .build();

HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());
~~~

This snippet is taken from the full example in section 5. It is great for learning how URLs/ports are constructed, though in projects with complex auth/sessions/headers, a dedicated configured test client can keep tests shorter and cleaner.

### 7.4. RestAssured and global state

If using RestAssured, prefer specifying the port **per request**:

~~~java
given()
    .port(applicationPort)
.when()
    .get("/api/greeting")
.then()
    .statusCode(200);
~~~

This snippet requires the RestAssured dependency and static imports, outside the runnable project in this article. Avoid setting `RestAssured.port = applicationPort` as a **global static variable** in parallel tests, because another test class can overwrite the port and cause race interference. When testing management endpoints, specify `.port(managementPort)` or a separate base URI for that request.

## 8. Building accurate URLs when context path and base path change

A common mistake: the port injects properly, yet the test sends GET to the **wrong path**. Keep application server configuration and management server configuration separate.

### 8.1. `server.servlet.context-path`

With Servlet MVC:

~~~properties
server.servlet.context-path=/shop
~~~

A controller mapping `@GetMapping("/api/greeting")` is now served at `/shop/api/greeting`, no longer `/api/greeting`.

Therefore the test must build:

~~~java
String appUrl = "http://127.0.0.1:" + applicationPort
        + "/shop/api/greeting";
~~~

If the context path is configured for a test profile, centralize base URL construction or read configuration from the test context when reasonable, avoiding duplicating paths across dozens of tests.

### 8.2. `management.endpoints.web.base-path`

Actuator places endpoints under `/actuator` by default. It can be changed:

~~~properties
management.endpoints.web.base-path=/manage
~~~

Then the health endpoint is typically `/manage/health` (depending on management server base path and security). When the management server uses a separate port, use:

~~~java
String healthUrl = "http://127.0.0.1:" + managementPort
        + "/manage/health";
~~~

### 8.3. `management.server.base-path` and separate management servers

When a separate management server is configured, `management.server.base-path` can also be set. Under Spring Boot 3.3 rules, `management.endpoints.web.base-path` is relative to this management server base path. For example, if `management.server.base-path=/internal` and `management.endpoints.web.base-path=/actuator`, the expected management path is `/internal/actuator/health`.

**Do not mistakenly apply the application server's `server.servlet.context-path`** to a separate management server. That commonly causes 404 even when the management port is right.

### 8.4. `management.server.address` and bind interfaces

You can restrict the management server to loopback only:

~~~properties
management.server.port=8081
management.server.address=127.0.0.1
~~~

This fits deployments permitting management access internally only. In Boot, configuring a management address different from the application address is **only supported when the management port differs from the application port**. If running tests in a container with a separate network namespace, the client's `127.0.0.1` does not reach the server container; use the real hostname and internal routing.

**A port does not include a hostname.** `@LocalServerPort` and `@LocalManagementPort` supply only port numbers; host/address is a separate decision based on how the server binds and where the client runs.

### 8.5. HTTP and HTTPS

If the application enables `server.ssl.*`, clients must use `https://` and trust the certificate appropriately. With a separate management port, `management.server.ssl.*` can differ from `server.ssl.*`, meaning **the two servers can use two different schemes**.

Never resolve a certificate error by blindly disabling TLS validation in production-bound tests. Use a controlled truststore/test certificate, or internal HTTP strictly within test scope matching the goal. Tests should be clear about whether they are testing TLS or only endpoint logic.

## 9. Test hits the right endpoint on the wrong server

If the management port differs from the app port, a request to:

~~~text
http://127.0.0.1:<application-port>/actuator/health
~~~

can get 404, 401/403, or hit another route/proxy instead of the management endpoint. If the test expects health on the management port, it must use:

~~~text
http://127.0.0.1:<management-port>/actuator/health
~~~

Do not immediately conclude 404 means the Actuator dependency is missing; check **right port, right path, right exposure** first. Likewise, sending `/api/greeting` to the management port usually fails because business controllers are served by the application server.

### What should be verified?

| Check | What it verifies | What it does NOT prove |
| --- | --- | --- |
| `applicationPort > 0` | Spring published a valid port number | HTTP endpoint responds properly |
| GET app endpoint on application port | HTTP routing/controller/serialization work | Management server works |
| `managementPort > 0` | Runtime management port published | Health endpoint is exposed and healthy |
| `applicationPort != managementPort` | Both servers configured on separate ports in demo | All production firewalls/proxies are right |
| GET `/actuator/health` on management port | Right route/port and health responds | All external production dependencies are healthy in other environments |
| Intentional 401/403 check | Auth/authorization policy takes effect | Endpoint does not exist |

Checking both **status code and body** catches bugs better than merely verifying “connection succeeded”. Still, write expectations per real specs: in an app with a health contributor reporting `DOWN`, 503 may reflect infrastructure failure rather than port misconfiguration.

## 10. `@Transactional` with `RANDOM_PORT` does not roll back as many assume

When `@SpringBootTest(webEnvironment=RANDOM_PORT)` starts a real HTTP server, requests sent by the HTTP client typically run on a **server thread**, separate from the test method thread. If the test is annotated with `@Transactional`, rolling back the **test method's transaction** at completion does not automatically roll back transactions committed on the server thread.

Conceptual example:

~~~java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Transactional
class OrderHttpIntegrationTest {
    // An HTTP POST request may commit data on the server thread.
    // Rolling back the test thread's transaction does not undo that commit.
}
~~~

This is a cautionary snippet, outside the runnable project in section 5. If HTTP tests create data, you need an **explicit cleanup/fixture mechanism**: delete data by ID, reset the database/container between tests, or use a suitable state isolation strategy. Never conclude “the test has `@Transactional`, so the database stays clean”.

The example uses stateless GET requests so tests can run repeatedly in any order.

## 11. Why might you not need a real server?

Not every Spring Boot test should use `RANDOM_PORT`. If you only check that a controller returns the expected JSON, validation, or exception handler, `@WebMvcTest`/`MockMvc` may suffice without opening a socket:

~~~java
@WebMvcTest(GreetingController.class)
class GreetingControllerMvcTest {
    // @Autowired MockMvc...
    // mockMvc.perform(get("/api/greeting"))...
}
~~~

This is an illustrative snippet; imports and test methods are needed for a complete project. With `MockMvc`, there is no real TCP port, so `@LocalServerPort` is unnecessary. Pure controller/service logic might only need JUnit + constructor injection.

Use `RANDOM_PORT` when goals require:

- Verifying requests travel through a real embedded web server (Tomcat/Jetty/Undertow/Netty per stack).
- Confirming routing, HTTP headers, cookies, request-size limits, redirects, or container-dependent behavior.
- Verifying application and Actuator ports, real URLs, or port management.
- Testing multi-layer flows with an HTTP client, close to how real clients interact.
- Checking proxy/TLS/network effects when fixtures match the goal.

If the goal is just a simple calculation, starting two embedded servers and using an HTTP client is slow and adds unrelated failure points.

## 12. Common errors when testing server ports

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `@LocalServerPort` cannot be injected | Test uses `MOCK`/`NONE`, server didn't start, or wrong annotation package | Use `RANDOM_PORT` for real HTTP, import right Boot 3.3 package |
| Port read via `server.port` is still 0 | Reading requested port config instead of bound port | Use `@LocalServerPort` / `local.server.port` |
| `Connection refused` to `localhost:8080` | Server uses random port or isn't running | Read runtime port; check server/context startup |
| `Connection refused` with right port yet wrong host | Server bound different interface or client in another container | Check bind address/network namespace, hostname/routing |
| `@LocalManagementPort` missing value | No separate management HTTP server or runtime property absent | Check Actuator starter and management server config; use app port if shared |
| Health returns 404 on application port | Management runs on another port or different base path | Use actual management port and management path |
| Health returns 401/403 | Spring Security/management authorization applies | Use matching test credentials, do not disable security carelessly |
| Health returns 503 or `DOWN` | A health contributor is unhealthy | Check fixtures/infrastructure and health groups before changing paths |
| `Address already in use` | `DEFINED_PORT` or fixed management port collides with another process | Use `RANDOM_PORT`/`management.server.port=0` in integration tests |
| Random failures when running in parallel | Using global RestAssured port, static base URL, or external shared state | Keep port/base URL per instance/request, avoid static mutable state |
| Actuator endpoint missing | Missing actuator starter, unexposed endpoint, disabled, or wrong path | Check dependency + management endpoint exposure/config |
| Passes locally, fails on CI | Hostname, bind address, timeout, container routing, port policy | Use environment-appropriate address and finite timeouts |
| SSL handshake error | Calling HTTPS over HTTP, wrong certificate/truststore | Match scheme and configure safe test trust |
| Right status yet wrong JSON response | Only asserted HTTP 200 | Parse/assert important body fields |
| Test rollback does not clean data | HTTP request ran in a transaction off the test thread | Use appropriate cleanup/fixtures |

### Distinguishing 404 from Connection refused

**Connection refused** is usually a TCP-layer error: no listener accepts connections on that host/port or the connection was rejected. It differs from **HTTP 404**, which means the client connected to an HTTP server and the server replied “route/resource not found”. Therefore:

- If **Connection refused**: check listener, port, bind address, and scheme/network.
- If **404**: check which server received the request, path/context-path/management base path, and endpoint mapping.
- If **401/403**: check authentication/authorization first, rather than assuming the port is wrong.
- If **503 from health**: the route may be right while the system or a health contributor is unhealthy.

Analyzing by layer avoids wrong fixes: adding `@LocalServerPort` will not fix an unexposed health endpoint; enabling exposure will not fix connecting to a host with no server.

## 13. Safe management configuration in tests

A clear test configuration set might look like:

~~~properties
# Illustrative values for local test environment
server.port=0
management.server.port=0
management.endpoints.web.exposure.include=health,info
~~~

When using `@SpringBootTest(webEnvironment=RANDOM_PORT)`, manually adding `server.port=0` is unnecessary because the annotation already requests a random port. The management test class in section 5.4 declares `management.server.port=0` directly in `properties` to keep the test self-contained and clear in intent.

**Never ship `management.endpoints.web.exposure.include=*` to production just for test convenience.** Some Actuator endpoints expose environment details, metrics, or sensitive management operations. Expose only needed endpoints, backed by proper authentication/authorization and network policies.

### What does `management.server.port=-1` mean?

In Spring Boot, setting:

~~~properties
management.server.port=-1
~~~

is used to **disable management HTTP endpoints/server** in applicable configurations. In that case, do not expect a management URL to respond or `@LocalManagementPort` to resolve. If a test only needs business HTTP, disabling management can trim dependencies; if the test targets health/Actuator, management HTTP must stay enabled.

### A separate management port is not the sole security boundary

Even when Actuator runs on its own port, a network policy or proxy can still expose it unintentionally. Local port tests only prove **application configuration in the test environment**, not real security and deployment routing.

## 14. Practice exercises

**Exercise A — application port only:** Run `ApplicationPortHttpTest` several times. Note that the port may vary, yet both tests pass. Explain why `server.port=0` cannot be used directly as a client URL.

**Exercise B — two separate ports:** Run `SeparateManagementPortHttpTest`, compare runtime application and management ports, and send GET requests to both corresponding URLs. Temporarily swap `managementUrl` to use `applicationPort` to observe different behavior. Revert the code afterward.

**Exercise C — changing base path:** Add `management.endpoints.web.base-path=/manage` to the management test class; update the health path to `/manage/health`. Predict that requests to `/actuator/health` on the management port will fail as expected, while the updated path succeeds.

**Exercise D — application context path:** Add `server.servlet.context-path=/shop` to a test. Change `appUrl("/api/greeting")` to `appUrl("/shop/api/greeting")`. Explain why a separate-port management URL does not necessarily carry the `/shop` prefix.

**Exercise E — simulating port collision:** Try `DEFINED_PORT` with a fixed port already occupied by another process in an isolated test sandbox. Observe the bind-address failure and switch back to `RANDOM_PORT`. Never kill a production process just to “free” a port for testing.

**Exercise F — secured management:** If the app uses Spring Security, add a contract health test expecting 401 for anonymous or 200 for an authorized user, depending on config. Never assume health always returns 200 when authentication is active.

**Exercise G — protecting transactions:** Add a POST creating an entity in a test DB environment. Verify that test-method rollback does not automatically clean data committed by the HTTP server thread; propose independent fixtures/cleanup.

## 15. Pre-completion checklist for port-based tests

- [ ] Do I need a **real HTTP server** or just MockMvc/unit tests?
- [ ] Is `@SpringBootTest(webEnvironment=RANDOM_PORT)` applied appropriately when real HTTP is needed?
- [ ] Did I import `org.springframework.boot.test.web.server.LocalServerPort` matching Spring Boot 3.3?
- [ ] Am I using the **actual `local.server.port`**, not the `server.port=0` config value?
- [ ] If Actuator uses a separate server, are `spring-boot-starter-actuator`, `management.server.port`, and `@LocalManagementPort` configured properly?
- [ ] Does the management server actually run separately or share a port? Do not force two ports to differ unless config requires it.
- [ ] Does the client URL have the right **scheme, host, port, context path, and endpoint path**?
- [ ] Does the test client run in the same network namespace as the server when using `127.0.0.1` loopback?
- [ ] Do security/TLS/exposure/base-path settings alter health responses?
- [ ] Do parallel tests avoid mutable global static port/base URL state?
- [ ] Did I assert status **and** required content/contract, not merely connection success?
- [ ] Do stateful/transactional HTTP tests clean up properly?
- [ ] Do Gradle reports confirm tests actually executed (not merely `UP-TO-DATE`)?
- [ ] Are example ports 8080, 51237, 53241 treated purely as illustrations, never hardcoded into test expectations?

## 16. Official reference documentation

The links below align with the **Spring Boot 3.3** line of the sample project; when using another version, consult the reference/Javadoc for that exact version.

- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `webEnvironment` modes, random ports, and HTTP test clients.
- [Spring Boot 3.3 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): `server.port=0`, discovering runtime ports, and `@LocalServerPort`.
- [Spring Boot 3.3 — Actuator REST API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/index.html): management endpoint URL conventions.
- [Spring Boot 3.3 — LocalManagementPort API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/web/server/LocalManagementPort.html): annotation for the management HTTP port.
- [Spring Boot 3.3 — LocalServerPort API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/web/server/LocalServerPort.html): annotation for the application HTTP port.

**Remember:** `@LocalServerPort` retrieves the **application** port assigned after a real server starts. `@LocalManagementPort` retrieves the **management** port when a separate management web server exists. `server.port=0` and `management.server.port=0` only request port allocation — they are not ports clients connect to. Always construct URLs from **runtime port + right host/scheme/path**, verify whether Actuator shares or splits ports, and verify responses via a real HTTP client when the goal is HTTP integration testing.
