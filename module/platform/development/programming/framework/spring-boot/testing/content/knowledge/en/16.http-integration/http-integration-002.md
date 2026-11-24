# TestRestTemplate, WebTestClient, and RestTestClient Across Spring Boot Versions

## 1. Why does the same HTTP integration test have multiple clients?

When testing a Spring Boot REST API, we usually want to **start the application on a real port, send an HTTP request, and verify the response from a consumer's perspective**. However, depending on the Spring Boot and Spring Framework version, the provided test client APIs, package imports, and auto-configuration mechanisms differ. Test code that is valid in Spring Boot 3.5 may fail to compile or fail to inject a bean when upgrading to Boot 4.

Three names to distinguish:

- **`TestRestTemplate`**: a test utility based on `RestTemplate` that provides synchronous HTTP calls and returns `ResponseEntity` for checking status/body. Commonly used in Spring Boot 3.x integration tests; still usable in Boot 4 if the proper module and annotation are configured.
- **`WebTestClient`**: a fluent test API originating from Spring WebFlux, yet **capable of testing real HTTP servers and mock WebFlux contexts**; some setups also support Spring MVC via MockMvc. Commonly used to assert `expectStatus`, `expectHeader`, and `expectBody`.
- **`RestTestClient`**: a new API from **Spring Framework 7 / Spring Boot 4**, wrapping `RestClient`, offering fluent expectations similar to `WebTestClient` while targeting **synchronous HTTP clients / Spring MVC**; it supports both real servers and MockMvc-bound modes without opening a port.

This lesson answers: **which client to use, which dependencies to add, how to import them, which server configuration to choose, and how far the test evidence goes**. The examples use Java 17+, but **do not mix code from the two version lines in the same build configuration**.

> Version scope: the Boot 3 section uses Spring Boot **3.5.x / Spring Framework 6.x**; the Boot 4 section uses **4.0.x / Spring Framework 7.x**. Module names, packages, and primary behaviors are aligned with the official documentation. For projects running a newer line, verify against the documentation of the **version locked in your build**, rather than guessing from IDE autocomplete or guides for an older line.

## 2. First, choose the right @SpringBootTest mode

Not every `@SpringBootTest` has a real HTTP listener.

| `webEnvironment` | Context loaded | Real embedded HTTP server? | Suitable test clients |
|---|---|---|---|
| `MOCK` (default) | Simulated web context when a web stack is on the classpath | **No** | `MockMvc` for MVC, `WebTestClient` bind-to-context for WebFlux, `RestTestClient` bound to MockMvc in Framework 7 |
| `RANDOM_PORT` | Web application context with server on a random port | **Yes** | All three clients can make real HTTP calls when provided and configured for the right version |
| `DEFINED_PORT` | Web context with server on configured port | **Yes** | Real HTTP client; watch out for port conflicts when tests run in parallel |
| `NONE` | Context without a web environment | **No** | Not suitable for automatically calling the application's HTTP endpoints |

**Recommendation when the goal is HTTP integration:** use `@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)` so the operating system chooses an available port, reducing conflicts across machines and CI jobs. Clients configured by Boot for a live server usually **resolve the base URL automatically**, so requests to `"/api/ping"` do not need manual `localhost:8080` concatenation.

If you use `MOCK`, a 200 response still has value for controllers/binding/JSON/filters in the loaded context, but **it does not prove real sockets, TCP, the server container, TLS, or any upstream proxy works**. Switching `MOCK` to `RANDOM_PORT` is not just changing speed: it is changing the **verification boundary**.

A note on transactions: when a real server handles requests on a separate thread, `@Transactional` on the test method **does not automatically roll back data committed by the HTTP server**. Tests that write data must have an independent fixture/cleanup strategy.

## 3. Version matrix and client selection

| Criterion | Boot 3.5 / Framework 6.x | Boot 4.0 / Framework 7.x |
|---|---|---|
| `TestRestTemplate` | `org.springframework.boot.test.web.client.TestRestTemplate` | Moved to `org.springframework.boot.resttestclient.TestRestTemplate` |
| Enabling TestRestTemplate in `@SpringBootTest(RANDOM_PORT)` | Provided by Boot under normal test config when matching dependencies are present | Requires **`@AutoConfigureTestRestTemplate`** and the related module |
| `WebTestClient` | `org.springframework.test.web.reactive.server.WebTestClient`; requires `spring-webflux` on classpath | **Still the same Spring Test package**, but requires **`@AutoConfigureWebTestClient`** when injected via Boot test context along with the corresponding test module |
| `RestTestClient` | **Not available** in Spring Framework 6.x | `org.springframework.test.web.servlet.client.RestTestClient` |
| Enabling RestTestClient in Boot context | Not applicable | **`@AutoConfigureRestTestClient`** from `org.springframework.boot.resttestclient.autoconfigure` |
| Real server with relative URLs | TestRestTemplate/WebTestClient with appropriate Boot auto-config | RestTestClient/WebTestClient/TestRestTemplate once the corresponding auto-config is **enabled** |
| Mock Spring MVC | `MockMvc`, or WebTestClient via MockMvc bridge | `MockMvc`, plus RestTestClient with MockMvc binding mode |
| Mock Spring WebFlux | WebTestClient | WebTestClient |
| Built-in fluent assertions API | WebTestClient | WebTestClient **and** RestTestClient |

**Key transition point:** Spring Boot 4 splits test/client components into specialized modules; you cannot assume `spring-boot-starter-test` alone brings in every tool or bean just like Boot 3.5 did. Check the dependency tree and auto-config annotations.

Avoid a naming confusion: `RestClient` is the synchronous production HTTP client, while `RestTestClient` is the **test facade** wrapping `RestClient`; `RestTemplate` is the older production HTTP client, while `TestRestTemplate` is the test utility built on it. Do not use `RestClient` in code and expect `expectStatus()` to exist — that method belongs to the testing API.

## 4. Shared example application for both version lines

To compare fairly, all three test clients will call the **same small application**. The production code below uses HTTP/Web annotations common to both Boot 3.5 and Boot 4.0; place it in a project with **one** consistent Boot version.

The application has three verifiable behaviors:
1. `GET /api/echo/Ada` returns `200 OK`, header `X-Echo: yes`, and text `Hello, Ada`.
2. `GET /api/echo/missing` returns `404 Not Found` with body `ECHO_NOT_FOUND`. The goal is to inspect the error response rather than assuming the client throws.
3. `POST /api/echo` receives JSON `{"name":"Neo"}`, returning `201 Created` and text `Created: Neo`.

The endpoints intentionally **do not write to a database** so we can focus on client selection and the HTTP boundary. Once the mechanism is clear, repository/transaction/security integration tests can be added.

### 4.1. Application class

File `src/main/java/com/example/httpit/HttpItApplication.java`:

```java
package com.example.httpit;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpItApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpItApplication.class, args);
    }
}
```

The file sits in the parent package of the controller so component scan discovers `@RestController`.

### 4.2. Request record

File `src/main/java/com/example/httpit/EchoRequest.java`:

```java
package com.example.httpit;

public record EchoRequest(String name) {}
```

A Java 17 record has a constructor and `name()` accessor. In a Boot project configured with an appropriate JSON converter/codec (such as Jackson), a JSON object with a `name` field is deserialized into this record.

### 4.3. REST controller

File `src/main/java/com/example/httpit/EchoController.java`:

```java
package com.example.httpit;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/echo")
public class EchoController {

    @GetMapping("/{name}")
    public ResponseEntity<String> greet(
            @PathVariable("name") String name) {

        if ("missing".equals(name)) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND)
                    .body("ECHO_NOT_FOUND");
        }

        return ResponseEntity.ok()
                .header("X-Echo", "yes")
                .body("Hello, " + name);
    }

    @PostMapping
    public ResponseEntity<String> create(
            @RequestBody EchoRequest request) {

        return ResponseEntity.status(HttpStatus.CREATED)
                .body("Created: " + request.name());
    }
}
```

The controller returns plain text responses so output can be compared **exactly** without depending on JSON field order. POST still verifies JSON request-body deserialization via the record. The demo application **does not add Spring Security** so GET/POST can be called without credentials/CSRF; in a real project with security, authentication/CSRF must be provided according to its security rules.

There is no fixed business stdout in the controller. The numbers 200, 201, 404 and the text bodies are **contracts asserted in tests**, not an application log transcript.

## 5. Configuration and testing on Spring Boot 3.5: TestRestTemplate

### 5.1. Dependencies on Boot 3.5

For a project already configured with the Spring Boot 3.5.x plugin, Java 17, dependency management, and Maven Central, the Gradle Groovy DSL dependencies section is:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is **not the full** `build.gradle`: the Boot plugin/toolchain/repositories must be configured in the project. With Boot 3.5, `spring-boot-starter-test` provides the standard JUnit/Boot test components; `TestRestTemplate` lives in `spring-boot-test` and is normally available for `RANDOM_PORT` tests when the classpath is compatible.

### 5.2. TestRestTemplate: full Java/JUnit test

File `src/test/java/com/example/httpit/Boot35TestRestTemplateTest.java`:

```java
package com.example.httpit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class Boot35TestRestTemplateTest {

    @Autowired
    TestRestTemplate rest;

    @Test
    void returns200WithBodyAndHeader() {
        ResponseEntity<String> response = rest.getForEntity(
                "/api/echo/Ada", String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("Hello, Ada", response.getBody());
        assertEquals(
                "yes", response.getHeaders().getFirst("X-Echo"));
    }

    @Test
    void returns404AsResponseInsteadOfThrowing() {
        ResponseEntity<String> response = rest.getForEntity(
                "/api/echo/missing", String.class);

        assertEquals(
                HttpStatus.NOT_FOUND, response.getStatusCode());
        assertEquals("ECHO_NOT_FOUND", response.getBody());
    }

    @Test
    void postSerializesRequestAndReturns201() {
        ResponseEntity<String> response = rest.postForEntity(
                "/api/echo",
                new EchoRequest("Neo"),
                String.class);

        assertEquals(
                HttpStatus.CREATED, response.getStatusCode());
        assertEquals("Created: Neo", response.getBody());
    }
}
```

### 5.3. Why is this test valuable?

- `@SpringBootTest(RANDOM_PORT)` starts a **real embedded server**; the `TestRestTemplate` provided by Boot with the proper root URL can call relative paths without hardcoding `8080`.
- The client is backed by `RestTemplate` and executes requests **synchronously**; the test receives `ResponseEntity<String>` containing status, headers, and body.
- **`TestRestTemplate` is fault-tolerant in a test-friendly sense** for 4xx/5xx: it does not throw a response-status exception by default like regular `RestTemplate` on its default handler; the test inspects error responses via `getStatusCode()`. Do not confuse this with ignoring network errors: connection refused, timeouts, or serialization bugs can still fail the request.
- POST verifies that the JSON request is serialized by the client and deserialized by the server. If the real system has authentication, filters, validation, or other JSON formats, matching tests must be added.
- This test does not involve a database or asynchronous processing; the 201 response here only means the controller code produced the expected response.

**Manual client alternative:** you can instantiate `TestRestTemplate` manually or use the underlying `RestTemplate`, but then you must configure base URL, authentication, interceptors, etc. yourself. When Boot provides a preconfigured client for `RANDOM_PORT`, injecting it directly is simpler and less error-prone.

## 6. Spring Boot 3.5: WebTestClient for a real server

`WebTestClient` is a test API with a fluent style `client.get().uri(...).exchange().expectStatus()...`. Although it originated in WebFlux, it **does not only test reactive servers**: it can connect to a live HTTP server of an MVC application when the appropriate test dependencies are present.

### 6.1. Additional dependency

If the Boot 3.5 project in Section 5 uses MVC but you want to run `WebTestClient`, add the test dependency for the Spring WebFlux/client stack:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-webflux'
}
```

Adding WebFlux only in test scope in the MVC example lets you use the client; if a project has both MVC and WebFlux on the runtime classpath, Spring Boot normally prefers **MVC** when auto-detecting the web application type. A real WebFlux application uses `spring-boot-starter-webflux` in `implementation` and does not need `starter-web` for this purpose.

### 6.2. WebTestClient on Boot 3.5

File `src/test/java/com/example/httpit/Boot35WebTestClientTest.java`:

```java
package com.example.httpit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class Boot35WebTestClientTest {

    @Autowired
    WebTestClient client;

    @Test
    void readsLiveServerWithFluentAssertions() {
        client.get()
                .uri("/api/echo/Ada")
                .accept(MediaType.TEXT_PLAIN)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals("X-Echo", "yes")
                .expectBody(String.class).isEqualTo("Hello, Ada");
    }

    @Test
    void handles404AsTestExpectation() {
        client.get()
                .uri("/api/echo/missing")
                .exchange()
                .expectStatus().isNotFound()
                .expectBody(String.class).isEqualTo("ECHO_NOT_FOUND");
    }

    @Test
    void sendsJsonAndChecks201() {
        client.post()
                .uri("/api/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new EchoRequest("Neo"))
                .exchange()
                .expectStatus().isCreated()
                .expectBody(String.class).isEqualTo("Created: Neo");
    }
}
```

This is an **alternative** to the `TestRestTemplate` test class; you do not need to run both to prove the same HTTP contract unless comparing them. The assertion APIs are similar, but the client mechanism differs:

- `exchange()` executes the request per `WebTestClient`'s configuration, and `expectStatus`/`expectBody` verify the response.
- `WebTestClient` does not force controllers to return `Mono` or `Flux`; it is an HTTP test client capable of calling an MVC server.
- When the server emits multiple elements (SSE/streaming) or a reactive response, `WebTestClient` is especially useful because it has APIs to consume streaming bodies and integrates with Reactor Test.
- Boot 3.5 conveniently autowires `WebTestClient` into `@SpringBootTest(RANDOM_PORT)` when `spring-webflux` is on the classpath. In a mock WebFlux environment, `@AutoConfigureWebTestClient` can be used; **do not infer a live server just because `WebTestClient` can be injected**.

If you do not need the WebFlux/client stack just to verify status/body on an MVC HTTP API, `TestRestTemplate` brings fewer dependencies to a pure Servlet Boot 3.5 project.

## 7. Spring Framework 7 / Boot 4: RestTestClient arrives

`RestTestClient` was added in **Spring Framework 7** as a test client built on `RestClient`. It uses `RestClient`'s request-execution API up to `exchange()`, and then provides fluent assertions afterward:

```java
client.get()
        .uri("/api/echo/Ada")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class).isEqualTo("Hello, Ada");
```

This is illustrative syntax inside a test that has `client`; the complete test class is in Section 8.

**Two important modes:**
- **Real HTTP server**: `RestTestClient.bindToServer().baseUrl("http://localhost:<port>").build()`, or Boot auto-configures the client for `RANDOM_PORT`.
- **Mock Spring MVC**: `RestTestClient.bindToController(...)` or `bindToApplicationContext(...)` uses the MockMvc infrastructure underneath, **without opening a TCP listener**.

`RestTestClient` is not merely a drop-in rename of `WebTestClient`. Its strength is using the **imperative `RestClient`** style and directly supporting mock MVC in Spring Framework 7. `WebTestClient` remains useful and supported in WebFlux/streaming applications as well as MVC testing cases configured with the appropriate bridge.

**Version warning:** `org.springframework.test.web.servlet.client.RestTestClient` **does not exist in Framework 6.x**. If your IDE reports "cannot resolve `RestTestClient`" in a Boot 3.x project, that is a version mismatch, not a missing mysterious import in `spring-boot-starter-test`. Do not arbitrarily force `spring-test:7.x` into a Spring Boot 3.x app using Spring 6.x; doing so breaks BOM/dependency alignment.

## 8. Full Java 17+ example: Boot 4.0 with @AutoConfigureRestTestClient

### 8.1. Modules and dependencies of Boot 4

In Spring Boot 4, many web/test clients are split into modules. A Gradle example **for a Boot 4.0.x project** that already declares the Spring Boot plugin, Java 17+, repositories, and dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
    implementation 'org.springframework.boot:spring-boot-starter-restclient'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-resttestclient'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

The pair `spring-boot-starter-restclient` (synchronous client) and `spring-boot-resttestclient` (test infrastructure) is declared **explicitly** so we do not rely on accidental transitive dependencies. If your project already uses equivalent starters/test modules under the BOM, you may already receive those modules transitively; **check the dependency tree rather than adding unnecessary duplicates**.

These artifacts and auto-configuration mechanisms apply to **Boot 4.x**; do not copy them verbatim into Boot 3.5 (which uses `spring-boot-starter-web`). `@SpringBootTest` with `@AutoConfigureRestTestClient` will not make things appear if the classpath is missing the corresponding module.

### 8.2. RestTestClient against a real HTTP server

File `src/test/java/com/example/httpit/Boot40RestTestClientTest.java`:

```java
package com.example.httpit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.resttestclient.autoconfigure.AutoConfigureRestTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.client.RestTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureRestTestClient
class Boot40RestTestClientTest {

    @Autowired
    RestTestClient client;

    @Test
    void checksRealHttpSuccess() {
        client.get()
                .uri("/api/echo/Ada")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals("X-Echo", "yes")
                .expectBody(String.class).isEqualTo("Hello, Ada");
    }

    @Test
    void checksRealHttpNotFound() {
        client.get()
                .uri("/api/echo/missing")
                .exchange()
                .expectStatus().isNotFound()
                .expectBody(String.class).isEqualTo("ECHO_NOT_FOUND");
    }

    @Test
    void postsJsonThroughRealServer() {
        client.post()
                .uri("/api/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .body(new EchoRequest("Neo"))
                .exchange()
                .expectStatus().isCreated()
                .expectBody(String.class).isEqualTo("Created: Neo");
    }
}
```

Changes compared to Boot 3.5:
- Import **`RestTestClient` from the Spring Test MVC package** `org.springframework.test.web.servlet.client`, **not** `org.springframework.test.web.reactive.server`.
- `@AutoConfigureRestTestClient` from Boot's `org.springframework.boot.resttestclient.autoconfigure` is the annotation used to create the client bean in the test context.
- `@SpringBootTest(RANDOM_PORT)` ensures calls go through a real HTTP server. The Boot-created client knows the base URL of the assigned port; relative paths work as shown.
- The client has the request body method `body(...)` in the style of `RestClient`, differing from `WebTestClient`'s `bodyValue(...)`.
- `expectStatus`, `expectHeader`, and `expectBody` verify the response. This is a **test facade**; if you use production `RestClient` directly, it does not have such a fluent expectation chain built in.

This test class uses the **same-package production files** from Section 4. No service or repository needs to be written for this example. With the right dependencies/versions and a web application that starts cleanly, the three tests are designed to pass; you must actually run them for PASS evidence.

### 8.3. RestTestClient with MockMvc without opening a server

In Spring Framework 7, you can test an MVC controller with `RestTestClient` without a listening socket:

```java
package com.example.httpit;

import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.client.RestTestClient;

class RestTestClientMockControllerTest {

    private final RestTestClient client =
            RestTestClient.bindToController(new EchoController())
                    .build();

    @Test
    void mockMvcStyleRequestWithoutRealHttpPort() {
        client.get()
                .uri("/api/echo/Ada")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("Hello, Ada");
    }
}
```

This is a **complete test class**, but it only tests the plain controller and the MVC mock setup of `bindToController`. It **does not** run all beans/filters/security/advice that the real application has unless you explicitly configure those components. If you want the application's Spring MVC context, use `RestTestClient.bindToApplicationContext(WebApplicationContext)`; if you want a real HTTP socket, use `bindToServer()` or Boot auto-configuration with `RANDOM_PORT`.

**Do not claim that all three binding modes are real HTTP integration.** The client name does not determine the level of integration; **the binding mode and server configuration** do.

## 9. Boot 4 still supports TestRestTemplate, but you must change the package and enable the bean

An application with many Boot 3.x tests based on `TestRestTemplate` does not have to migrate everything to `RestTestClient` immediately. However, when upgrading to Boot 4:

1. Change the import from `org.springframework.boot.test.web.client.TestRestTemplate` to `org.springframework.boot.resttestclient.TestRestTemplate`.
2. Enable auto-config with **`@AutoConfigureTestRestTemplate`** on `@SpringBootTest` classes that inject it.
3. Ensure the classpath includes **`spring-boot-resttestclient`** and **`spring-boot-restclient`** / matching starter.
4. Keep `RANDOM_PORT` if the test must actually go through the HTTP server.

Complete Boot 4.0 class example:

```java
package com.example.httpit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.resttestclient.TestRestTemplate;
import org.springframework.boot.resttestclient.autoconfigure.AutoConfigureTestRestTemplate;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureTestRestTemplate
class Boot40LegacyTemplateTest {

    @Autowired
    TestRestTemplate rest;

    @Test
    void keepsStatusDrivenAssertions() {
        ResponseEntity<String> response =
                rest.getForEntity(
                        "/api/echo/missing", String.class);

        assertEquals(
                HttpStatus.NOT_FOUND, response.getStatusCode());
        assertEquals("ECHO_NOT_FOUND", response.getBody());
    }
}
```

This snippet requires the same Boot 4 dependencies from Section 8 and the production code from Section 4. `TestRestTemplate` keeps its convenient property of inspecting HTTP 4xx/5xx via `ResponseEntity` rather than treating error statuses as exceptions by default.

**The main change is module splitting and explicit bean opt-in**, not the `getForEntity` API being renamed to something completely new.

If the Boot 4 project also uses `RestClient.Builder` in production code, `spring-boot-restclient` should be on the **main runtime classpath**; do not add it only in test scope and then get surprised when the bean exists in tests but is missing in production.

## 10. WebTestClient on Boot 4: still available, but must be explicitly auto-configured

`WebTestClient` is neither replaced nor removed by `RestTestClient`. It continues to be ideal for:
- Spring WebFlux annotated controllers and functional endpoints.
- Streaming responses, server-sent events (SSE), and backpressure/cancellation in applicable test scenarios.
- Live HTTP servers of MVC or WebFlux when the HTTP client stack is set up.
- Mock WebFlux contexts when you want fast tests without starting a server.

One correction needed from many Boot 3.x examples: in **Boot 4**, when you want to **inject** `WebTestClient` into a `@SpringBootTest`, add **`@AutoConfigureWebTestClient`**, and put the test module containing the annotation and the appropriate WebFlux client dependencies on the classpath.

Example imports for **Boot 4.x**:

```java
package com.example.httpit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webtestclient.autoconfigure.AutoConfigureWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class Boot40WebTestClientTest {

    @Autowired
    WebTestClient client;

    @Test
    void readsRunningHttpServer() {
        client.get()
                .uri("/api/echo/Ada")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("Hello, Ada");
    }
}
```

In a Boot 4 MVC application, the test dependencies need **`spring-boot-webflux-test`** (providing the support/annotation) and the WebFlux/client runtime such as `spring-webflux` with the Reactor Netty HTTP client or matching starter. A clear setup for the illustrative project adds:

```groovy
testImplementation 'org.springframework.boot:spring-boot-starter-webflux-test'
testImplementation 'org.springframework.boot:spring-boot-starter-webflux'
```

Keep `implementation 'org.springframework.boot:spring-boot-starter-webmvc'` if this is a Servlet application. Adding WebFlux only in **test scope** to run the client does not mean you have to convert the whole MVC server to WebFlux. If the real application is WebFlux, the WebFlux starter belongs in `implementation`, and the corresponding test module is the test dependency.

**Distinguish packages by version:**
- Boot 3.5: `org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient`.
- Boot 4.0: `org.springframework.boot.webtestclient.autoconfigure.AutoConfigureWebTestClient`.
- Both use `org.springframework.test.web.reactive.server.WebTestClient` for the test client class.

Changing the annotation import while keeping the same `WebTestClient` class name is a common source of `cannot resolve symbol` IDE errors after migration.

## 11. Distinguishing mock tests, server tests, and external-client tests

**Case A: you want to test the controller HTTP contract without starting a server.**

- Boot 3 MVC: `@WebMvcTest` + `MockMvc`; you can also use `WebTestClient` backed by `MockMvc` if the bridge is configured.
- Boot 3/4 WebFlux: `@WebFluxTest` + `WebTestClient` bound to context.
- Spring Framework 7 MVC: `RestTestClient.bindToController(...)` or `bindToApplicationContext(...)`, or `MockMvc` as before.

The result proves mappings, converters, validation, JSON, controller advice, and filters **actually registered in the test setup**. It does not prove TCP/embedded server behavior or the full production security/proxy/config.

**Case B: you want to test the application's HTTP server end-to-end.**

- `@SpringBootTest(RANDOM_PORT)` + a test client whose base URL is bound to the real port.
- Assert status, headers, content type, body, and error schema; add authentication/CSRF/cookies when the API is secured.
- With real services/repositories, you can test multiple layers; with mocked beans, you only prove the layers **still running for real** in the context.

The result proves HTTP requests travel through a real server; it does not by itself prove the production database, load balancer, TLS termination, external gateways, or cloud networking.

**Case C: you want to test your application calling an external HTTP API.**

Use `@RestClientTest` + `MockRestServiceServer`, WebClient testing support, a mock HTTP server, or appropriate contract tests. That is **client-side integration testing of outbound HTTP**, different from the three test clients used to **call your own application's endpoints**. Do not confuse `@RestClientTest` (slice for outbound `RestClient`) with `RestTestClient` (client for testing server endpoints).

## 12. Request and assertion API comparison

| Task | TestRestTemplate | WebTestClient | RestTestClient |
|---|---|---|---|
| GET | `getForEntity(path, String.class)` | `get().uri(path).exchange()` | `get().uri(path).exchange()` |
| Check status | `assertEquals(OK, response.getStatusCode())` | `expectStatus().isOk()` | `expectStatus().isOk()` |
| Check text body | `assertEquals("...", response.getBody())` | `expectBody(String.class).isEqualTo("...")` | `expectBody(String.class).isEqualTo("...")` |
| Header | `response.getHeaders().getFirst(...)` | `expectHeader().valueEquals(...)` | `expectHeader().valueEquals(...)` |
| POST object | `postForEntity(path, body, String.class)` | `post().uri(...).bodyValue(body).exchange()` | `post().uri(...).body(body).exchange()` |
| 4xx/5xx | Retrieve `ResponseEntity` to assert | Status expectation | Status expectation |
| Mock MVC without starting server | Not its primary purpose | Possible via MockMvc bridge | Has `bindToController` / `bindToApplicationContext` in Framework 7 |
| Mock WebFlux without starting server | No | **Yes** | Not the primary API for mock reactive context |
| Streaming/reactive body assertions | More manual | Strong, integrates with Reactor Test | Geared toward imperative request/response |

Do not claim one client is strictly "faster" based solely on its name: most time comes from the **context type**, whether a real server is started, infrastructure dependencies, database/test fixtures, and context cache hit rate. Fluent assertions improve test readability and authoring, but do not automatically increase coverage.

### 12.1. Checking 4xx statuses is different from transport errors

A `GET /missing` returning 404 is a **valid HTTP response** for the test to assert; whereas an unresolvable host, connection refused, TLS handshake failure, timeout, or codec deserialization error can cause the test to fail **before the status/body assertion step**.

With `TestRestTemplate`, "fault-tolerant" behavior means 4xx/5xx does not throw by default like `RestTemplate`'s default error handler; it does **not** mean the client ignores all errors. With `RestTestClient` and `WebTestClient`, `expectStatus().isNotFound()` must genuinely match the status; never turn every error response into a "test succeeded".

### 12.2. Testing JSON instead of just text

For endpoints returning JSON objects, `WebTestClient` and `RestTestClient` can inspect data types/bodies and provide content-based assertion APIs; when using JSON path, check the API applicable in your specific version. `TestRestTemplate` can deserialize into a DTO:

```java
ResponseEntity<MyResponse> response =
        rest.getForEntity("/api/resource/1", MyResponse.class);
assertEquals(1L, response.getBody().id());
```

This is an **illustration inside a test with `rest` and `MyResponse` already defined**, not part of the full program in Section 4. Do not assert that JSON field ordering is stable; check fields, semantic values, error codes, and content types required by the public contract.

### 12.3. Authentication, headers, and cookies

- `TestRestTemplate` has APIs supporting Basic Authentication and customizing the underlying `RestTemplate`; when testing with users/roles, verify actual status codes and do not print secrets in logs.
- `WebTestClient` and `RestTestClient` support request headers/cookies and client configuration; use the methods appropriate for your version.
- JWT/OAuth2 tokens, CSRF, redirects, session cookies, and Spring Security filters are only verified when the **real filter/security configuration** is in the call path.
- All three can bypass parts of production proxy/TLS if running only loopback HTTP; if transport security is a risk, run separate tests with appropriate TLS/gateway setup.

## 13. Running tests per version line

From the root of the **Boot 3.5 project**, run only the classes written for Boot 3.5:

```bash
./gradlew test --tests "com.example.httpit.Boot35TestRestTemplateTest"
./gradlew test --tests "com.example.httpit.Boot35WebTestClientTest"
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.httpit.Boot35TestRestTemplateTest"
.\gradlew.bat test --tests "com.example.httpit.Boot35WebTestClientTest"
```

From the root of the **Boot 4.0 project**, run only the classes belonging to Boot 4:

```bash
./gradlew test --tests "com.example.httpit.Boot40RestTestClientTest"
./gradlew test --tests "com.example.httpit.Boot40LegacyTemplateTest"
./gradlew test --tests "com.example.httpit.Boot40WebTestClientTest"
./gradlew test --tests "com.example.httpit.RestTestClientMockControllerTest"
```

Maven wrapper (single class example):

```bash
./mvnw -Dtest=Boot40RestTestClientTest test
```

Windows PowerShell:

```powershell
.\mvnw.cmd -Dtest=Boot40RestTestClientTest test
```

These commands assume you already have a build wrapper, plugins, Java 17+, and the proper dependencies. In multi-module Gradle/Maven builds, run against the right module. Boot 3 and Boot 4 classes **must not be compiled in the same source set** because they have different imports/annotations.

**There is no fixed stdout** from these sample tests. When running via Gradle `test`, check `build/reports/tests/test/index.html`; Maven Surefire reports are usually in `target/surefire-reports/`. Only conclude PASS when the tests are genuinely discovered, executed, and assertions pass; check for skipped tests, build caching, or missing dependencies.

## 14. Migration checklist from Boot 3.5 to Boot 4.0

1. **Check the actual version in your build/BOM**, do not guess from the classpath. Boot 3.x uses Spring Framework 6.x, Boot 4.x uses Framework 7.x.
2. If `TestRestTemplate` fails to compile, update the package to `org.springframework.boot.resttestclient` and declare the `spring-boot-resttestclient` module.
3. If a Boot 4 test cannot inject `TestRestTemplate`, add `@AutoConfigureTestRestTemplate`; verify `spring-boot-restclient` is also present.
4. If migrating to `RestTestClient`, use `@AutoConfigureRestTestClient`, import `org.springframework.test.web.servlet.client.RestTestClient`, and convert `ResponseEntity`-style assertions to fluent expectations.
5. If continuing with `WebTestClient`, keep importing `org.springframework.test.web.reactive.server.WebTestClient` but use `@AutoConfigureWebTestClient` **from the Boot 4 package**, and add the required WebFlux test client dependencies.
6. Double-check `@SpringBootTest(webEnvironment = RANDOM_PORT)`: if it reverts to default `MOCK`, the test no longer proves a real HTTP server.
7. Distinguish the test auto-config annotations and modules of **Boot 3** from **Boot 4**; do not mix `org.springframework.boot.test.autoconfigure.*` imports from the older line into the new project.
8. Verify the client actually uses the random-port base URL; do not hardcode `8080` or send requests to another instance on the machine.
9. In applications with both MVC and WebFlux, verify which web context type is actually selected; MVC usually wins by default when both stacks are present.
10. For tests writing to a DB through a real HTTP server, design committed fixture/cleanup strategies without relying on test-thread rollback.
11. Check server-side filters, authentication, CORS/CSRF, JSON mapping, and error payloads; changing the client does not mean the API contract remained intact.
12. Re-run the test classes for the target version line and inspect the actual report before deleting old code.

## 15. Common errors and how to fix them

| Error or symptom | Possible cause | Specific action |
|---|---|---|
| `Cannot resolve RestTestClient` on Boot 3 | Framework 6.x does not have the new class | Keep `WebTestClient`/`TestRestTemplate` or upgrade Boot/Framework **together** |
| `Cannot resolve TestRestTemplate` after Boot 4 upgrade | Package moved, module not declared | Import from `org.springframework.boot.resttestclient`; add the test module |
| `NoSuchBeanDefinitionException: TestRestTemplate` in Boot 4 | No longer auto-created solely via `@SpringBootTest` | Add `@AutoConfigureTestRestTemplate` and dependencies |
| `NoSuchBeanDefinitionException: RestTestClient` | Missing `@AutoConfigureRestTestClient` or module | Add annotation, check dependency tree |
| `NoSuchBeanDefinitionException: WebTestClient` on Boot 4 upgrade | New auto-config not enabled or missing spring-webflux/test module | Right-package `@AutoConfigureWebTestClient` + dependencies |
| `cannot find AutoConfigureWebTestClient` | Copied import package from Boot 3 into Boot 4 | Change to `org.springframework.boot.webtestclient.autoconfigure` |
| Client calls `localhost:8080` and fails | `RANDOM_PORT` server listens on a different port | Use the autoconfigured client or `@LocalServerPort` to build base URL |
| Mock test passes but live HTTP fails | Mock does not pass through real server socket or filters/container | Add `@SpringBootTest(RANDOM_PORT)` |
| HTTP 404 makes test throw instead of assert | Using plain `RestTemplate` or custom error handler | Check client type; use `ResponseEntity`/`TestRestTemplate` or test client expectations |
| `.bodyValue` method missing on RestTestClient | Mixing WebTestClient request API with RestClient request API | Use `.body(...)` in RestTestClient |
| Test compiles but application lacks `RestClient.Builder` | RestClient auto-config was split from web starter in Boot 4 | Add the restclient module/starter on main runtime if production needs it |
| Test returns 200 without verifying JSON | Asserting status only, ignoring body contract | Assert required headers/body/fields/errors |
| Test uses `@Transactional` yet leaves DB rows | HTTP server requests have independent transactions | Clean up outside the test transaction, isolate database fixtures |
| Security test disables filters and claims 401/403 works | Security stack is not in the call path | Test with real filters/security and appropriate credentials |
| Startup fails due to both MVC/WebFlux dependencies | Application auto-detection picked an unexpected stack | Choose the right starter and web application type |
| Test slow/flaky for unclear reasons | Server startup, port conflicts, network, DB fixtures, or context reuse | Use `RANDOM_PORT`, controlled context caching, independent fixtures |

## 16. Choosing a client for real-world scenarios

If you are working on a **Boot 3.5 MVC REST API** and just need to send real HTTP and assert status/body: **`TestRestTemplate`** is the pragmatic choice. If you want fluent assertions, streaming, or already use Reactor tooling: **`WebTestClient`** is a solid option when the classpath permits.

If you are moving to **Boot 4.x** and your application is **MVC with Spring Framework 7**, prioritize **`RestTestClient`** for synchronous HTTP integration tests or testing controllers via MockMvc. It does not force bringing in a WebFlux server model just to get fluent assertion APIs.

If your application uses **WebFlux/Reactive Streams**, **`WebTestClient`** remains the natural choice for mock WebFlux contexts, HTTP integration, and streaming scenarios. If you want to preserve existing `TestRestTemplate` tests on Boot 4, there is a clear migration path, though you must update packages, modules, and annotations.

**The final decision rests on three things:** *Spring Boot/Framework version*, *web stack and mock vs real server environment*, and *the HTTP contract to protect*. Choosing a client based on these three criteria keeps tests easy to understand, avoids copying mismatched imports from other guides, and prevents mistaking an MVC slice test for socket-level HTTP integration.

## 17. Official documentation to verify by version

- [Spring Boot 3.5 – Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `RANDOM_PORT`, `TestRestTemplate`, `WebTestClient`, mock/live environments.
- [Spring Boot 4.0 – Testing Spring Boot Applications](https://docs.spring.io/spring-boot/4.0/reference/testing/spring-boot-applications.html): `@AutoConfigureRestTestClient`, `@AutoConfigureWebTestClient`, `@AutoConfigureTestRestTemplate`, and new modules/packages.
- [Spring Boot 4.0 – Test Utilities](https://docs.spring.io/spring-boot/4.0/reference/testing/test-utilities.html): `TestRestTemplate` characteristics and `RestTestClient` scope.
- [Spring Framework – RestTestClient](https://docs.spring.io/spring-framework/reference/testing/resttestclient.html): how to bind to controllers, application context, router functions, and HTTP servers.
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): package/module/test auto-configuration changes when upgrading.

**Conclusion:** The three test clients are not completely interchangeable aliases. `TestRestTemplate` uses synchronous HTTP and `ResponseEntity`; `WebTestClient` provides fluent assertions for WebFlux and compatible HTTP servers; `RestTestClient` is Framework 7's new option for imperative HTTP testing and mock Spring MVC. When moving from Boot 3.5 to 4.x, the most important thing is not just renaming the client, but **updating the packages, dependencies, auto-configuration annotations, and test boundaries properly**; then running tests against a real server whenever the goal requires HTTP integration.