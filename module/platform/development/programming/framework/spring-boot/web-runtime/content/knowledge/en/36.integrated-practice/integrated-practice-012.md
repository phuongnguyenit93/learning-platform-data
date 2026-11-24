# Building a Test Suite to Reproduce Common Spring Boot Web Runtime Errors

## 1. Context, Objectives, and Practice Outcomes

A Spring Boot endpoint can return **404, 400, 401, 403, 405, 406, 409, 415, 429, 500, 503, 504**, or fail to respond before a deadline. Those status codes look similar in brief logs, yet their **origins** differ vastly: Servlet context paths, handler mappings, HTTP methods, JSON decoders, Bean Validation, Spring Security, domain services, reverse proxies, connection pools, or a slow upstream. A strong test suite must **reproduce errors deterministically** and guard against regressions so fixed bugs never return.

This lesson belongs to **Integrated Practice** in the **Spring Boot - web-runtime** module, directly addressing: **Building a test suite to reproduce common web runtime errors**. Instead of a loose list of commands, it delivers **a runnable Java 17+ Maven project** using Spring Boot 3.5.16, Spring MVC/Tomcat, Bean Validation, Spring Security, Actuator, JUnit 5, MockMvc, and JDK `HttpClient`.

The practice suite includes:

- **21 HTTP integration tests** using `@SpringBootTest(webEnvironment = RANDOM_PORT)` + Java 17 `HttpClient` against real embedded Tomcat.
- **3 controller slice tests** using `@WebMvcTest` + `MockMvc` for fast mapping/validation checks, with transparent coverage limits.
- An application featuring context path `/lab`, widget read/create APIs, validation, ETag caching, domain 404s, unexpected 500s, HTTP Basic auth, and 401/403 authorization.
- A diagnostic matrix, **red → green → regression** exercises, and extensions covering uploads, CORS, proxies, streaming, WebFlux, timeouts, and overload.
- Maven and `curl` instructions, guidance on reading results, fixture design, and CI practices that keep tests away from production.

Objectives after this lesson:

1. Distinguish **MockMvc** tests from real HTTP over sockets, never citing green slice tests as proof of context-path, connector, or proxy behavior.
2. Construct deliberate error requests and assert **HTTP status, headers, body, and side effects** at the appropriate boundary.
3. Write 400 tests for malformed JSON and Bean Validation, 405 for methods, 406 for `Accept`, 415 for `Content-Type`, and 404 for routes/domain misses.
4. Test 401 unauthenticated and 403 unauthorized responses, recognizing CSRF can return 403 before reaching the controller.
5. Test an unhandled 500 response, separating unexpected failures from domain errors with explicit contracts.
6. Verify 201 + `Location` + resource read-back, plus ETag and conditional GET 304 without body transfer.
7. Write deterministic tests: random ports, synthetic data, order independence, no arbitrary sleeps, and no unauthorized external calls.
8. Select the right test strategy when bugs occur only under WebFlux, SSE/NDJSON, reverse proxies, TLS, high load, or real databases.

**Guiding principle:** each test represents a *failure hypothesis*, *reproduction condition*, *measured/asserted signal*, and *scope limit*. Not all web runtime failures live inside a Java controller.

## 2. Map of Error Sources and Test Levels

```text
Browser / Mobile / curl
       |
       v
DNS, TLS, load balancer, ingress / reverse proxy
       |-- wrong Host, path rewrite, timeout, header limits
       v
Embedded Tomcat + Servlet context /lab
       |-- missing /lab => 404 before controller
       v
Spring Security filter chain
       |-- unauthenticated => 401; missing role/CSRF => 403
       v
DispatcherServlet / HandlerMapping
       |-- path 404; method 405; produces 406; consumes 415
       v
HTTP converters / Bean Validation
       |-- malformed JSON / invalid DTO => 400
       v
Controller / service / domain
       |-- known resource => 200; created => 201
       |-- missing business object => explicit 404
       |-- unexpected failure => 500
       v
Serialization / cache / response completion
       |-- ETag + If-None-Match => 304
       |-- streamed response / client disconnect / proxy buffering
```

| Test Level | Tools | Verifies | Does Not Prove |
| --- | --- | --- | --- |
| Unit | JUnit/Mockito, `StepVerifier` if Reactive | Conditions, error branches, domain state, publisher signals | HTTP mapping, Jackson, filter chain |
| Web slice | `@WebMvcTest` + MockMvc, or `@WebFluxTest` + WebTestClient | Controller mapping, validation, codecs, advice in slice | Tomcat/Netty sockets, public proxies, mocked services/DB |
| Full app mock | `@SpringBootTest` + `@AutoConfigureMockMvc` | Full app wiring, mocked filter/handler chain | Real socket/TLS/container error pages |
| Real HTTP | `@SpringBootTest(RANDOM_PORT)` + JDK HttpClient/WebTestClient | Embedded server, context path, HTTP responses, wiring | External CDNs, ingress, unconnected remote APIs/DBs |
| Staging / E2E | HTTP through gateway + test data/credentials | Public URLs, TLS, proxy/auth/upstream integration | Capacity or rare race faults without dedicated load/chaos tests |

Per Spring Boot 3.5 docs, `@SpringBootTest` defaults to `webEnvironment=MOCK`, which **does not start an embedded server**; `RANDOM_PORT` starts a live server. `@WebMvcTest` runs faster as a **slice**, and when Spring Security is on the classpath, check which filters apply rather than merely asserting 200.

**This test suite targets Servlet MVC.** For native Netty WebFlux, use `@WebFluxTest`, `WebTestClient`, and Reactive Streams tests. Never add `spring-boot-starter-webflux` into an MVC POM and call it a WebFlux test: when both MVC and WebFlux are on the classpath, Spring Boot prioritizes MVC by default.

## 3. Selecting Deterministically Reproducible Errors

The lab deliberately exercises both "happy paths" and "error paths" against the **same system**:

| Case | Request | Expected | Source / Layer |
| --- | --- | --- | --- |
| OK health | `GET /lab/actuator/health` | 200 | Actuator under context path |
| Valid URL | `GET /lab/api/ping` | 200 JSON | Handler mapping |
| Missing context | `GET /api/ping` | 404 | Tomcat context path |
| Wrong route | `GET /lab/api/pign` | 404 | Spring handler/resource lookup |
| Extra trailing slash | `GET /lab/api/ping/` | 404 per default matching | Path matching |
| Wrong HTTP verb | `POST /lab/api/ping` | 405 | Method condition |
| Wrong Accept | `GET /lab/api/ping`, `Accept: application/xml` | 406 | Produces / media negotiation |
| Wrong request Content-Type | `POST /lab/api/widgets`, `text/plain` | 415 | Consumes / media negotiation |
| Malformed JSON | POST unparseable JSON | 400 | `HttpMessageConverter` |
| Invalid DTO | POST blank name / quantity 0 | 400 | Jakarta Bean Validation |
| Missing query param | `GET /lab/api/page` | 400 | Required parameter |
| Wrong query param type | `GET /lab/api/page?size=abc` | 400 | Type conversion |
| Existing resource | `GET /lab/api/widgets/w1` | 200 | Domain service |
| Nonexistent resource | `GET /lab/api/widgets/unknown` | 404 with custom code | Domain + advice |
| Create resource | Valid POST widget | 201 + `Location`; GET returns 200 | Controller + in-memory store |
| Unhandled failure | `GET /lab/api/fail` | 500 | Unexpected exception |
| Unauthenticated | `GET /lab/api/secure/member` | 401 | Spring Security |
| Authenticated | GET member with Basic demo user | 200 | Authentication |
| Insufficient role | GET admin with Basic demo user | 403 | Authorization |
| Conditional cache | GET snapshot, then `If-None-Match` | 200 then 304 | ETag semantics |
| Actuator mappings | `GET /lab/actuator/mappings` | 200 local, lists routes | Mapping diagnostics |

**Note:** the 401/403/405/406/415 statuses above hold when the test environment matches this source configuration. Custom security, proxies, WAFs, content negotiation, and error handlers can alter responses. This test suite intentionally fixes those conditions—never claim every Spring Boot app returns identical codes for every request.

## 4. Building a Standalone MVC/Tomcat Test Project

### 4.1. Directory Structure

```text
runtime-error-lab/
├─ pom.xml
└─ src/
   ├─ main/
   │  ├─ java/com/example/runtimelab/
   │  │  ├─ RuntimeErrorLabApplication.java
   │  │  ├─ Widget.java
   │  │  ├─ CreateWidgetRequest.java
   │  │  ├─ WidgetService.java
   │  │  ├─ InMemoryWidgetService.java
   │  │  ├─ UnknownWidgetException.java
   │  │  ├─ ApiErrorHandler.java
   │  │  ├─ SecurityConfiguration.java
   │  │  └─ RuntimeApiController.java
   │  └─ resources/
   │     └─ application.properties
   └─ test/
      └─ java/com/example/runtimelab/
         ├─ RuntimeHttpIntegrationTest.java
         └─ RuntimeWebSliceTest.java
```

Every public top-level Java type sits in a file matching its name under `com.example.runtimelab`. The root application class lives in the parent package so Spring Boot component scanning discovers the controller, service, advice, and security config.

### 4.2. Valid Maven POM — Spring Boot 3.5.16 / Java 17

**`pom.xml`**

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
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>runtime-error-lab</artifactId>
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
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
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

- `starter-web`: **Spring MVC + embedded Tomcat**, plus JSON/Jackson.
- `starter-validation`: enables Jakarta Bean Validation for request DTOs.
- `starter-security`: enables the Spring Security Servlet filter chain and lab HTTP Basic auth.
- `starter-actuator`: provides health/mappings, exposed strictly in the local lab.
- `starter-test`: provides JUnit Jupiter, MockMvc, AssertJ, and Mockito.
- `spring-security-test`: included for future MockMvc role/CSRF tests; the real HTTP suite sends JDK HTTP Basic headers.
- No database, Redis, or third-party API needed; an in-memory store backs HTTP state with simple fixtures.

### 4.3. Local-Lab-Only Runtime Configuration

**`src/main/resources/application.properties`**

```properties
spring.application.name=runtime-error-lab
server.port=8080

# Prevent exposing demo externally. In containers, configure
# bind address per topology rather than copying 127.0.0.1 blindly.
server.address=127.0.0.1
server.servlet.context-path=/lab

# Local diagnostics only; never expose mappings publicly in production.
management.endpoints.web.exposure.include=health,mappings

# Hide internal error messages/stack traces in default HTTP responses.
server.error.include-message=never
server.error.include-stacktrace=never
```

`server.servlet.context-path=/lab` requires HTTP clients to request `/lab/api/...`. Controller `@RequestMapping("/api")` **must not** repeat `/lab`. If later setting `spring.mvc.servlet.path` to something other than `/`, check matching compatibility with `PathPatternParser` for your Boot version.

### 4.4. Main Application

**`src/main/java/com/example/runtimelab/RuntimeErrorLabApplication.java`**

```java
package com.example.runtimelab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RuntimeErrorLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(RuntimeErrorLabApplication.class, args);
    }
}
```

### 4.5. Domain DTO and Validation

**`src/main/java/com/example/runtimelab/Widget.java`**

```java
package com.example.runtimelab;

public record Widget(String id, String name, int quantity) {}
```

**`src/main/java/com/example/runtimelab/CreateWidgetRequest.java`**

```java
package com.example.runtimelab;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record CreateWidgetRequest(
        @NotBlank String name,
        @Min(1) int quantity
) {}
```

Java 17 records serve as immutable DTOs serialized/deserialized by Jackson. `@NotBlank` rejects `null`, empty, and whitespace-only strings; `@Min(1)` rejects zero and negative numbers. Input validation happens at the web boundary and never replaces domain authorization or production DB constraints.

### 4.6. Service Contract

**`src/main/java/com/example/runtimelab/WidgetService.java`**

```java
package com.example.runtimelab;

public interface WidgetService {
    Widget find(String id);
    Widget create(CreateWidgetRequest input);
}
```

### 4.7. Domain Not-Found Exception

**`src/main/java/com/example/runtimelab/UnknownWidgetException.java`**

```java
package com.example.runtimelab;

public class UnknownWidgetException extends RuntimeException {
    public UnknownWidgetException(String id) {
        super("Widget not found");
    }
}
```

The message avoids sensitive data or raw upstream exceptions. `@RestControllerAdvice` maps this domain exception to a 404 JSON response with a fixed `code` so clients know how to react.

### 4.8. Runnable In-Memory Service

**`src/main/java/com/example/runtimelab/InMemoryWidgetService.java`**

```java
package com.example.runtimelab;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Service;

@Service
public class InMemoryWidgetService implements WidgetService {

    private final Map<String, Widget> store =
        new ConcurrentHashMap<>();
    private final AtomicLong sequence = new AtomicLong(100);

    public InMemoryWidgetService() {
        store.put("w1", new Widget("w1", "Book", 10));
    }

    @Override
    public Widget find(String id) {
        Widget widget = store.get(id);
        if (widget == null) {
            throw new UnknownWidgetException(id);
        }
        return widget;
    }

    @Override
    public Widget create(CreateWidgetRequest input) {
        String id = "w" + sequence.incrementAndGet();
        Widget widget =
            new Widget(id, input.name(), input.quantity());
        store.put(id, widget);
        return widget;
    }
}
```

`ConcurrentHashMap` and `AtomicLong` suffice for concurrent lab requests, yet **are not** database transactions, constraints, persistent storage, or an authorization layer. Tests verify HTTP behavior of **this app**, not external DB writes.

Because Spring Test caches `ApplicationContext` instances, generated IDs may advance if tests share or restart contexts. Tests **must not assert the ID is always `w101`**—read the returned ID and verify `GET` retrieval.

### 4.9. Error Advice for Domain 404

**`src/main/java/com/example/runtimelab/ApiErrorHandler.java`**

```java
package com.example.runtimelab;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiErrorHandler {

    @ExceptionHandler(UnknownWidgetException.class)
    public ResponseEntity<Map<String, String>> unknownWidget(
            UnknownWidgetException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(Map.of(
                "code", "WIDGET_NOT_FOUND",
                "message", "Widget not found"
            ));
    }
}
```

Important: a typo path `/lab/api/widgtes` also returns HTTP 404 without passing through `UnknownWidgetException`; never assume every 404 carries `code=WIDGET_NOT_FOUND`. Keep separate tests distinguishing **routing 404** from **domain 404**.

### 4.10. Intentional Spring Security Filter Chain

**`src/main/java/com/example/runtimelab/SecurityConfiguration.java`**

```java
package com.example.runtimelab;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            // LAB ONLY: non-cookie API POSTs for testing 405/400/415.
            // Never broadly disable CSRF in production with cookie-based auth.
            .csrf(csrf -> csrf.ignoringRequestMatchers(
                "/api/widgets", "/api/ping"))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/secure/admin").hasRole("ADMIN")
                .requestMatchers("/api/secure/**").authenticated()
                .anyRequest().permitAll())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername("student")
                .password("{noop}lab-only-password")
                .roles("USER")
                .build()
        );
    }
}
```

**Loopback/local training only.** `{noop}` uses unhashed passwords with public tutorial credentials—**never deploy this configuration to production**. Real apps need secure user storage, proper password encoders, HTTPS, and real security policies. Ignoring CSRF on those two API paths is solely so the lab can reproduce HTTP 405/415/400 without CSRF returning 403 first; production must evaluate cookies/sessions, token auth, cross-origin flows, and authorization.

Matcher `/api/secure/**` evaluates **inside the application context**; do not prepend `/lab` just because the Servlet context path is `/lab`. When the security filter rejects before the controller, 401/403 reflects **security**, not a missing handler mapping.

Without Basic credentials, `/api/secure/member` returns 401 with `WWW-Authenticate`. Sending the `USER`-role credentials to `/api/secure/admin` returns 403, proving authentication succeeded while the `ADMIN` role is missing.

### 4.11. Controller Covering Path/Method/Media/Validation/Cache/Error

**`src/main/java/com/example/runtimelab/RuntimeApiController.java`**

```java
package com.example.runtimelab;

import java.net.URI;
import java.time.Duration;
import java.util.Map;

import jakarta.validation.Valid;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@RestController
@RequestMapping("/api")
public class RuntimeApiController {

    private final WidgetService widgets;

    public RuntimeApiController(WidgetService widgets) {
        this.widgets = widgets;
    }

    @GetMapping(
        path = "/ping",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Map<String, String> ping() {
        return Map.of("message", "pong");
    }

    @GetMapping(
        path = "/widgets/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Widget find(@PathVariable("id") String id) {
        return widgets.find(id);
    }

    @PostMapping(
        path = "/widgets",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<Widget> create(
            @Valid @RequestBody CreateWidgetRequest input) {
        Widget widget = widgets.create(input);

        URI location = ServletUriComponentsBuilder
            .fromCurrentRequest()
            .path("/{id}")
            .buildAndExpand(widget.id())
            .toUri();

        return ResponseEntity.created(location).body(widget);
    }

    @GetMapping(
        path = "/page",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Map<String, Integer> page(
            @RequestParam("size") int size) {
        return Map.of("size", size);
    }

    @GetMapping(
        path = "/snapshot",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<Map<String, String>> snapshot() {
        return ResponseEntity.ok()
            .eTag("\"snapshot-v1\"")
            .cacheControl(
                CacheControl.maxAge(Duration.ofSeconds(60))
                    .cachePublic()
            )
            .body(Map.of("version", "v1"));
    }

    @GetMapping(
        path = "/secure/member",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Map<String, String> member() {
        return Map.of("access", "member");
    }

    @GetMapping(
        path = "/secure/admin",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Map<String, String> admin() {
        return Map.of("access", "admin");
    }

    @GetMapping("/fail")
    public void failOnPurpose() {
        // Deliberate 500 error solely for testing/runtime verification.
        throw new IllegalStateException(
            "Deliberate server failure for test"
        );
    }
}
```

**Points to verify:**

- `@RequestMapping("/api")` plus `@GetMapping("/ping")` defines **internal mapping `/api/ping`**; `/lab` sits at the Servlet layer outside annotations.
- `@PostMapping(consumes=application/json)` triggers 415 on `text/plain`.
- `@GetMapping(produces=application/json)` triggers 406 when client sends only `Accept: application/xml`.
- `@Valid @RequestBody` catches malformed JSON and Bean Validation; invalid DTOs never reach the service.
- `@RequestParam("size") int size` triggers 400 on **missing parameter** or **type conversion failure**.
- `ServletUriComponentsBuilder.fromCurrentRequest()` builds `Location` from the live request including context path, instead of hardcoding `/api/widgets/{id}` and dropping `/lab`.
- `ResponseEntity.eTag` plus `Cache-Control` enables conditional GET testing: when `If-None-Match` matches the ETag, the response shrinks to 304.
- `/fail` **deliberately throws** to test 500—never include a fault endpoint like this in production. Default error bodies vary across Boot versions and `Accept` headers, so assert status rather than comparing raw error JSON byte-for-byte.
- `/secure` routes are guarded by the Servlet security filter chain upstream of the controller.

## 5. HTTP Tests Running Through Real Tomcat

### 5.1. Why Use JDK `HttpClient`?

Whenever testing **context paths, Servlet container behavior, HTTP headers, security filter chains, and real status codes**, boot a real server. `@SpringBootTest(RANDOM_PORT)` launches embedded Tomcat on a random port, injected via `@LocalServerPort`. `java.net.http.HttpClient` from JDK 17 sends real HTTP over loopback with zero extra client dependencies.

`@WebMvcTest` and MockMvc are great for controller slices, yet never prove traffic passes through the connector, socket, Tomcat context root, or container error dispatch. The HTTP tests below cover both **happy paths** and **failure paths**.

### 5.2. File `RuntimeHttpIntegrationTest.java` — 21 Test Methods

**`src/test/java/com/example/runtimelab/RuntimeHttpIntegrationTest.java`**

```java
package com.example.runtimelab;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Base64;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class RuntimeHttpIntegrationTest {

    @LocalServerPort
    int port;

    private final HttpClient client =
        HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .build();

    private final ObjectMapper json = new ObjectMapper();

    private HttpResponse<String> call(
            String method,
            String path,
            String accept,
            String contentType,
            String body,
            String basicCredentials,
            String ifNoneMatch) throws Exception {

        URI uri = URI.create(
            "http://127.0.0.1:" + port + path
        );

        HttpRequest.Builder builder =
            HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(5));

        if (accept != null) {
            builder.header("Accept", accept);
        }
        if (contentType != null) {
            builder.header("Content-Type", contentType);
        }
        if (ifNoneMatch != null) {
            builder.header("If-None-Match", ifNoneMatch);
        }
        if (basicCredentials != null) {
            String encoded = Base64.getEncoder().encodeToString(
                basicCredentials.getBytes(StandardCharsets.UTF_8)
            );
            builder.header("Authorization", "Basic " + encoded);
        }

        if ("GET".equals(method)) {
            builder.GET();
        } else {
            builder.method(
                method,
                HttpRequest.BodyPublishers.ofString(
                    body == null ? "" : body
                )
            );
        }

        return client.send(
            builder.build(),
            HttpResponse.BodyHandlers.ofString()
        );
    }

    private HttpResponse<String> get(String path) throws Exception {
        return call("GET", path, null, null, null, null, null);
    }

    private HttpResponse<String> getAccept(
            String path, String accept) throws Exception {
        return call("GET", path, accept, null, null, null, null);
    }

    private HttpResponse<String> getBasic(
            String path, String credentials) throws Exception {
        return call("GET", path, null, null, null, credentials, null);
    }

    private HttpResponse<String> post(
            String path, String contentType, String body)
            throws Exception {
        return call(
            "POST", path, null, contentType, body, null, null
        );
    }

    // 1. Correct context path + JSON contract.
    @Test
    void correctContextPathReturns200AndJson() throws Exception {
        HttpResponse<String> r = get("/lab/api/ping");

        assertEquals(200, r.statusCode());
        assertTrue(r.headers()
            .firstValue("Content-Type")
            .orElse("")
            .contains("application/json"));
        assertEquals(
            "pong",
            json.readTree(r.body()).get("message").asText()
        );
    }

    // 2. Missing Servlet context never reaches the controller.
    @Test
    void missingContextPrefixReturns404() throws Exception {
        assertEquals(404, get("/api/ping").statusCode());
    }

    // 3. Typo in handler mapping.
    @Test
    void wrongRouteReturns404() throws Exception {
        assertEquals(404,
            get("/lab/api/pign").statusCode());
    }

    // 4. Spring 6 PathPatternParser does not auto-match trailing slash.
    @Test
    void extraTrailingSlashIsNotSilentlyAccepted()
            throws Exception {
        assertEquals(404,
            get("/lab/api/ping/").statusCode());
    }

    // 5. POST to GET-only path: 405, not 404.
    @Test
    void unsupportedHttpMethodReturns405() throws Exception {
        HttpResponse<String> r = call(
            "POST", "/lab/api/ping",
            null, null, "", null, null
        );
        assertEquals(405, r.statusCode());
    }

    // 6. produces=JSON but client only accepts XML: 406.
    @Test
    void incompatibleAcceptReturns406() throws Exception {
        assertEquals(406,
            getAccept(
                "/lab/api/ping",
                "application/xml"
            ).statusCode());
    }

    // 7. consumes=JSON but request text/plain: 415.
    @Test
    void wrongRequestContentTypeReturns415() throws Exception {
        assertEquals(415,
            post(
                "/lab/api/widgets",
                "text/plain",
                "name=Notebook&quantity=2"
            ).statusCode());
    }

    // 8. The JSON decoder should reject malformed text.
    @Test
    void malformedJsonReturns400() throws Exception {
        assertEquals(400,
            post(
                "/lab/api/widgets",
                "application/json",
                "{ invalid-json "
            ).statusCode());
    }

    // 9. Bean Validation should reject blank name and quantity 0.
    @Test
    void invalidDtoReturns400() throws Exception {
        assertEquals(400,
            post(
                "/lab/api/widgets",
                "application/json",
                "{\"name\":\" \",\"quantity\":0}"
            ).statusCode());
    }

    // 10. A required query parameter was omitted.
    @Test
    void missingQueryParameterReturns400() throws Exception {
        assertEquals(400,
            get("/lab/api/page").statusCode());
    }

    // 11. String "abc" cannot be converted to int.
    @Test
    void invalidQueryParameterTypeReturns400()
            throws Exception {
        assertEquals(400,
            get("/lab/api/page?size=abc").statusCode());
    }

    // 12. Positive control for query parameter binding.
    @Test
    void validQueryParameterReturnsJson() throws Exception {
        HttpResponse<String> r =
            get("/lab/api/page?size=25");

        assertEquals(200, r.statusCode());
        assertEquals(
            25,
            json.readTree(r.body()).get("size").asInt()
        );
    }

    // 13. Seed item is found.
    @Test
    void knownWidgetReturns200() throws Exception {
        HttpResponse<String> r =
            get("/lab/api/widgets/w1");

        assertEquals(200, r.statusCode());
        JsonNode body = json.readTree(r.body());
        assertEquals("w1", body.get("id").asText());
        assertEquals("Book", body.get("name").asText());
    }

    // 14. Domain not-found must contain stable business code.
    @Test
    void missingWidgetReturnsDomain404() throws Exception {
        HttpResponse<String> r =
            get("/lab/api/widgets/no-such-widget");

        assertEquals(404, r.statusCode());
        assertEquals(
            "WIDGET_NOT_FOUND",
            json.readTree(r.body()).get("code").asText()
        );
    }

    // 15. POST then follow Location; no hardcoded generated ID.
    @Test
    void createReturns201LocationAndReadableResource()
            throws Exception {

        HttpResponse<String> created = post(
            "/lab/api/widgets",
            "application/json",
            "{\"name\":\"Marker\",\"quantity\":3}"
        );

        assertEquals(201, created.statusCode());
        JsonNode item = json.readTree(created.body());
        assertEquals("Marker", item.get("name").asText());
        assertEquals(3, item.get("quantity").asInt());

        String location = created.headers()
            .firstValue("Location")
            .orElseThrow();

        assertTrue(location.contains("/lab/api/widgets/"));
        URI locationUri = URI.create(location);
        assertEquals(
            "/lab/api/widgets/" + item.get("id").asText(),
            locationUri.getRawPath()
        );

        HttpResponse<String> fetched =
            get(locationUri.getRawPath());

        assertEquals(200, fetched.statusCode());
        assertEquals(
            item.get("id").asText(),
            json.readTree(fetched.body()).get("id").asText()
        );
    }

    // 16. Unhandled exception must not masquerade as 200.
    @Test
    void unexpectedExceptionReturns500() throws Exception {
        assertEquals(500,
            get("/lab/api/fail").statusCode());
    }

    // 17. Anonymous requests to protected route get 401.
    @Test
    void anonymousMemberRequestReturns401() throws Exception {
        HttpResponse<String> r =
            get("/lab/api/secure/member");

        assertEquals(401, r.statusCode());
        assertTrue(r.headers()
            .firstValue("WWW-Authenticate")
            .orElse("")
            .contains("Basic"));
    }

    // 18. Authenticated user can access member endpoint.
    @Test
    void memberWithCredentialsReturns200() throws Exception {
        HttpResponse<String> r = getBasic(
            "/lab/api/secure/member",
            "student:lab-only-password"
        );

        assertEquals(200, r.statusCode());
        assertEquals(
            "member",
            json.readTree(r.body()).get("access").asText()
        );
    }

    // 19. Authenticated USER lacks ADMIN role: 403.
    @Test
    void userCannotAccessAdminReturns403() throws Exception {
        assertEquals(403,
            getBasic(
                "/lab/api/secure/admin",
                "student:lab-only-password"
            ).statusCode());
    }

    // 20. Conditional request: GET 200 with ETag, then 304.
    @Test
    void matchingIfNoneMatchReturns304() throws Exception {
        HttpResponse<String> first =
            get("/lab/api/snapshot");

        assertEquals(200, first.statusCode());
        String etag = first.headers()
            .firstValue("ETag")
            .orElseThrow();

        HttpResponse<String> second = call(
            "GET",
            "/lab/api/snapshot",
            null, null, null, null, etag
        );

        assertEquals(304, second.statusCode());
        assertTrue(second.body().isEmpty());
    }

    // 21. Diagnostic endpoint is under Servlet context path.
    @Test
    void actuatorMappingsUsesContextPath() throws Exception {
        HttpResponse<String> r =
            get("/lab/actuator/mappings");

        assertEquals(200, r.statusCode());
        assertTrue(r.body().contains("/api/ping"));
    }
}
```

**This is a complete test class.** `@SpringBootTest(RANDOM_PORT)` assigns a random port so it never conflicts with another app running on port 8080. The `call` helper varies HTTP method, `Accept`, `Content-Type`, `Authorization`, and `If-None-Match` so each failure condition has a crisp reproduction.

**QA notes on the HTTP tests:**

- The 500 test causes the app to log an exception stack trace to the server log. That is **intentional**—do not mistake the stack trace log for a failed test, and never ship `/fail` to production.
- The 404 test outside the context path asserts only status; Tomcat's 404 body may differ from Spring MVC/`BasicErrorController` 404s.
- The domain 404 test **can assert `code`** because `ApiErrorHandler` defines that JSON contract, whereas route-typo 404s should not be forced to share the business code.
- The 201 test **never** hardcodes `w101`; it reads the returned ID and follows `Location`, eliminating flakiness across cached contexts.
- The conditional cache test passes the exact `ETag` returned by the first response in `If-None-Match` rather than hardcoding wire quoting; `304` cleanly has an empty body.
- The 401/403 security tests traverse the **real `SecurityFilterChain`**. Bypassing filters and asserting 401 tests nothing meaningful at the wrong layer.
- `HttpClient` uses a 5-second per-request timeout so a hung server fails cleanly instead of hanging CI. That is a **test timeout**, not an API timeout SLA.
- All tests use **in-memory state** with zero database, Internet, or production credential dependencies.

## 6. Controller Web-Slice Tests: Fast, with Clear Boundaries

Web slice tests catch annotation, HTTP converter, and validation bugs without booting Tomcat. However, with Spring Security on the classpath, default/custom filters alter status codes. To **demonstrate mapping-only tests**, this file intentionally disables filters in MockMvc; therefore **never cite these tests as proof of authentication, authorization, or CSRF**. Those are covered by the real HTTP tests in section 5.

**`src/test/java/com/example/runtimelab/RuntimeWebSliceTest.java`**

```java
package com.example.runtimelab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verifyNoInteractions;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@WebMvcTest(controllers = RuntimeApiController.class)
@AutoConfigureMockMvc(addFilters = false)
class RuntimeWebSliceTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    WidgetService widgets;

    @Test
    void controllerMappingReturnsPong() throws Exception {
        mvc.perform(get("/api/ping"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("pong"));
    }

    @Test
    void invalidJsonDtoGets400WithoutCallingService()
            throws Exception {

        mvc.perform(post("/api/widgets")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\" \",\"quantity\":0}"))
            .andExpect(status().isBadRequest());

        verifyNoInteractions(widgets);
    }

    @Test
    void wrongMethodGets405WithinWebSlice()
            throws Exception {

        mvc.perform(post("/api/ping"))
            .andExpect(status().isMethodNotAllowed());
    }
}
```

**Import note:** Java grammar permits wrapping static imports across lines around dots, though putting each static import on **one single line** avoids copy/paste surprises. Breaking lines right before `.` above remains valid tokenization as long as no stray characters creep in.

**Key distinctions:**

- `@WebMvcTest` skips `@Service` beans, so `@MockitoBean WidgetService` supplies the collaborator.
- Tests send `/api/ping` (internal app mapping) and **do not verify the `/lab` context root**, because MockMvc skips the Tomcat connector. Real HTTP tests verify `/lab/api/ping` works and `/api/ping` returns 404.
- `@AutoConfigureMockMvc(addFilters=false)` is **strictly for this mapping-only slice**. When testing Spring Security in a slice, leave filters enabled and use `spring-security-test` (e.g., `@WithMockUser` or `SecurityMockMvcRequestPostProcessors`), importing your custom security config if the slice doesn't pull it in automatically.
- `MockMvc` does not verify DNS, TLS, ingress, socket timeouts, or real Servlet error-page dispatches—use real HTTP integration tests for those.

## 7. Running the Project and Reading Results

### 7.1. Running Everything

From `runtime-error-lab`:

```bash
java -version
mvn test
```

Or with the Maven Wrapper **if created in the project**:

```bash
./mvnw test
```

On Windows PowerShell, use `mvnw.cmd test`. The first `mvn test` needs network access if dependencies are not cached locally. With a matching JDK/Maven environment, **24 test methods** are designed to pass: 21 HTTP integration + 3 web slice.

**Important:** these are **expected outcomes when the learner runs the suite**; this guide does not claim they were executed in the current workspace. Compiling and executing the tests locally is mandatory before relying on the sample in production CI.

Run individually:

```bash
mvn -Dtest=RuntimeHttpIntegrationTest test
mvn -Dtest=RuntimeWebSliceTest test
```

Maven prints tests run, failures, errors, and skipped counts. **Do not look only at `BUILD SUCCESS`**; check Surefire reports to confirm all intended test classes ran. If tests were skipped via filtering or naming mismatch, it is not a green regression suite.

### 7.2. Running the App to Reproduce via curl

```bash
mvn spring-boot:run
```

The app configures `server.address=127.0.0.1` and `server.servlet.context-path=/lab`. Try:

```bash
curl -i "http://127.0.0.1:8080/lab/api/ping"
curl -i "http://127.0.0.1:8080/api/ping"
curl -i -X POST "http://127.0.0.1:8080/lab/api/ping"
curl -i -H "Accept: application/xml" \
  "http://127.0.0.1:8080/lab/api/ping"
curl -i -H "Content-Type: text/plain" \
  -d "name=Pencil" \
  "http://127.0.0.1:8080/lab/api/widgets"
curl -i -H "Content-Type: application/json" \
  -d '{"name":"Pencil","quantity":4}' \
  "http://127.0.0.1:8080/lab/api/widgets"
curl -i "http://127.0.0.1:8080/lab/api/secure/member"
curl -i -u student:lab-only-password \
  "http://127.0.0.1:8080/lab/api/secure/member"
curl -i -u student:lab-only-password \
  "http://127.0.0.1:8080/lab/api/secure/admin"
```

PowerShell aliases `curl` differently; use `curl.exe` when needed. **Never use this lab account on any real system**; if deploying publicly, remove/replace `{noop}` passwords and demo security rules, or do not deploy the demo project.

### 7.3. Analyzing Results Beyond Status Codes

Record a short summary table per case:

| Case | Request + Headers | Expected | Actual | Layer | Evidence |
| --- | --- | --- | --- | --- | --- |
| C01 | GET `/api/ping` | 404 | *when run* | Servlet context | `context=/lab`, no mapping invoked |
| C02 | GET `/lab/api/ping` | 200 | *when run* | Spring MVC | JSON `message=pong` |
| C03 | POST `/lab/api/ping` | 405 | *when run* | Handler method | Allowed methods |
| C04 | POST invalid JSON | 400 | *when run* | HTTP decoder | Parse/validation |
| C05 | GET `secure/admin` USER | 403 | *when run* | Authorization | `roles=USER` |
| C06 | GET snapshot + `If-None-Match` | 304 | *when run* | Conditional response | ETag matched |

`*when run*` denotes **results collected by the learner**, not pre-recorded outputs. Note that 404/500 bodies vary with `Accept` and Boot patch versions; anchor core assertions on **status codes + app-defined JSON contracts**.

## 8. Controlled Red → Green → Regression Workflow

Goal: **reproduce a bug first, then fix its root cause**, never rewriting tests to bless broken output.

### 8.1. Red: Wrong Context Path

Scenario: callers hit `GET /api/ping` while the app sets `server.servlet.context-path=/lab`.

- **Red:** real HTTP test `missingContextPrefixReturns404` proves the old URL fails. If the contract truly requires `/api/ping`, the bug sits in config/client contract, not `@GetMapping`.
- **Fix:** align on the canonical base URL; update callers or fix context path / nginx rewrite consistently.
- **Green:** `GET /lab/api/ping` returns 200 per agreed contract.
- **Regression:** keep both the positive and negative tests so future deploys never **double** or **drop** the prefix.

**Never "fix" it by adding `/lab` to `@RequestMapping` when context path is already `/lab`**, which creates `/lab/lab/api/ping`.

### 8.2. Red: Missing Bean Validation

Scenario: POST `{"name":" ","quantity":0}` returns 201 because someone removed `@Valid` or `starter-validation`.

- **Red:** `invalidDtoReturns400` fails (actual 201).
- **Fix:** restore the validation dependency, `@Valid @RequestBody`, and constraint annotations.
- **Green:** invalid POST returns 400.
- **Regression:** beyond status, verify via service/mock check that invalid payloads never create widgets; with a real DB, check table state.

Note: 400 from malformed JSON differs from 400 from Bean Validation. Same status, different root cause, logs, and contract—keep **two distinct tests**.

### 8.3. Red: Security Policy Disabled

Scenario: a security config edit leaves `GET /api/secure/admin` open without `ADMIN`.

- **Red:** `userCannotAccessAdminReturns403` returns 200.
- **Fix:** restore `hasRole("ADMIN")`, verify matcher ordering, filter chain binding, and granted authorities.
- **Green:** `USER` role gets 403; anonymous member gets 401; authenticated `USER` gets 200 on member.
- **Regression:** keep all three checks—anonymous, valid auth, insufficient role—rather than merely asserting everything fails.

If a MockMvc test uses `addFilters=false`, security tests there **cannot** prove the real policy. Use full HTTP tests or slices with the real security chain/`spring-security-test`.

### 8.4. Red: JSON Client Sends Wrong Content-Type

Scenario: frontend posts `text/plain` to a JSON POST endpoint.

- **Red:** `wrongRequestContentTypeReturns415` catches it.
- **Fix:** client sends `Content-Type: application/json` with valid JSON. Never loosen the server to accept `text/plain` just to silence the error if the API contract forbids it.
- **Green:** POST with proper Content-Type returns 201.
- **Regression:** keep the 415 test so unintended formats aren't silently accepted later.

### 8.5. Red: Business Not-Found Leaks as 500

Scenario: service throws `NullPointerException` when a widget is missing and the controller has no error handler.

- **Red:** `missingWidgetReturnsDomain404` returns 500 or omits `code=WIDGET_NOT_FOUND`.
- **Fix:** throw an explicit domain exception on absence and map it consistently via `@RestControllerAdvice`.
- **Green:** 404 JSON includes the right code; `/api/pign` still returns 404 **without** inheriting the domain code.
- **Regression:** test both valid-route-missing-entity and invalid-route to keep the two 404 sources separate.

### 8.6. Red: Location Header Missing Context Path

Scenario: controller hardcodes `Location: /api/widgets/w101` while the app runs at `/lab`.

- **Red:** `createReturns201LocationAndReadableResource` fails to read back the resource from `Location`.
- **Fix:** use `ServletUriComponentsBuilder.fromCurrentRequest()` or a URI builder honoring context and trusted proxy config.
- **Green:** POST 201 returns `Location` with `/lab/api/widgets/{id}`, and GET returns 200.
- **Regression:** behind a reverse proxy adding `/portal`, add staging ingress tests verifying absolute `Location` never points internally.

### 8.7. Preserving Reproducibility Discipline

For a real production incident:

1. Scrub/mask PII in request fixtures while keeping exact HTTP method, path, and header types.
2. Isolate the layer: gateway, container, MVC, security, codec, service, DB, or response streaming.
3. Write a **failing test** asserting the right requirement—never hardcode the buggy output.
4. Confirm it fails **for the right reason** (not missing test tokens or DB setup).
5. Apply the minimal code/config fix.
6. Run the single test, the module suite, and integration/staging checks as needed.
7. Record the regression case ID and rationale so nobody deletes it later for "flaking occasionally."

In this guide's code listing, examples represent the **clean baseline + fixed negative assertions**. To practice red-green TDD yourself, intentionally break one condition as described, watch the test turn red, then revert/fix. Do not assume the listed source ships with pre-seeded bugs.

## 9. Understanding 4xx Errors by Layer

### 9.1. 404: Context Path, Handler Mapping, Static Resources, and Domain

A 404 response can originate from:

- **Container** before `DispatcherServlet` when the Servlet context path is missing.
- **HandlerMapping** when no controller route matches the path.
- **Static resource handler** catching `/**` and finding no asset (`NoResourceFoundException` in Spring Framework 6.1+).
- **Controller/service** explicitly returning 404 for a missing business entity.
- **Reverse proxy/ingress** returning 404 before reaching the Java app.

Never assert all 404s return identical JSON bodies. Use internal `/actuator/mappings` diagnostics and request correlation IDs to separate sources.

### 9.2. 405, 406, and 415

- 405: wrong HTTP method (POST on a GET-only endpoint).
- 406: request `Accept` incompatible with endpoint `produces`.
- 415: request `Content-Type` incompatible with `consumes` or unsupported by decoders.

Gateways or security filters can reject earlier with 401/403, so verify filters don't preempt 405/415 tests. Lab security intentionally permits anonymous access to `/api/ping` and `/api/widgets` with scoped CSRF exceptions.

### 9.3. 400: JSON Syntax, Validation, Binding, and Queries

Distinct causes:

- Malformed JSON → `HttpMessageNotReadableException` / decoder failure.
- Valid JSON violating `@NotBlank`/`@Min` → Bean Validation failure.
- Query `size=abc` unconvertible to `int` → type mismatch.
- Missing `size` query param → missing request parameter.
- Oversized upload or malformed multipart → 400/413 or container-specific error; configure limits and test separately.

Avoid lumping all of them under generic "bad request" logs without error classification, and never leak raw exceptions, stack traces, or SQL queries to clients.

### 9.4. 401 vs 403 and CSRF

- **401 Unauthorized** in HTTP means missing or invalid authentication credentials, usually paired with `WWW-Authenticate`.
- **403 Forbidden** means authenticated yet denied access, or blocked by CSRF/security rules.
- Spring Security's filter chain runs before MVC handlers, so 403 does not require `@PreAuthorize`.
- A `USER` getting 403 on an `ADMIN` route is right—never disable security just to get a 200 in tests.

The demo uses HTTP Basic and one local account to reproduce 401/403 deterministically. **Never ship plaintext/`{noop}` demo accounts to production.**

## 10. 5xx Errors and Timeouts: Avoid Arbitrary Sleeps

### 10.1. 500: Unhandled Exception

In the lab, `/api/fail` throws an intentional `IllegalStateException` and the real HTTP test asserts status 500. Startup errors, Servlet filter exceptions, post-commit JSON serialization errors, or proxy errors behave differently. Avoid coupling assertions to exact `BasicErrorController` JSON formats across Boot versions.

### 10.2. 503 and 429: Admission Control and Capacity

- 429 Too Many Requests fits per-identity/quota rate limiting.
- 503 Service Unavailable fits overload, maintenance, pool exhaustion, or unavailable dependencies—coming from either app or proxy.

For deterministic tests, **never** fire 1,000 random requests hoping to trip 429. Inject a fake rate limiter/bulkhead with a **deterministic clock and quota** (e.g., 2 requests/identity, 3rd returns 429), assert `Retry-After` if contracted, and reset fixtures between tests. For 503, stub the dependency as unavailable instead of breaking a real DB.

### 10.3. 504 and 408: Timeout Boundaries

- 408 Request Timeout typically indicates the server timed out waiting for client request data.
- 504 Gateway Timeout indicates a proxy/gateway timed out waiting on upstream, or an app intentionally mapped a downstream timeout to 504.
- A client `HttpTimeoutException` is a **test-client error** and does not prove the server emitted HTTP 504—if the client's deadline expired first, there may be **no HTTP status at all**.
- `Mono.timeout(...)` in WebFlux or `CompletableFuture.orTimeout(...)` does not guarantee underlying blocking native I/O/DB work stopped; configure driver timeouts and cleanup.

To test server 504, pair an intentionally delayed upstream HTTP stub with a short client timeout inside the app and assert **HTTP 504**. To test client-side timeouts, assert `HttpTimeoutException` separately without conflating the two. Avoid `Thread.sleep` for CI-sensitive timing assertions when fake clocks or `StepVerifier.withVirtualTime` apply.

### 10.4. Already-Committed Responses

If a streaming endpoint already flushed 200 headers/body before the source errored, the server **cannot reliably switch the status to 500/504**. Clients observe broken connections or stream error frames. Assert headers, event counts, and terminal signals—not only the initial status.

## 11. Streaming/WebFlux: Extending Tests to Reactive Runtimes

**This section is a conceptual extension, not compiled inside the section 4 Spring MVC project.** In a separate reactive app using `spring-boot-starter-webflux` and `reactor-test`, different runtime bugs arise:

- A WebFlux handler returning `Flux` calls `Thread.sleep`/JDBC/`Mono.block()` on a Netty event loop → queueing and starvation.
- Reverse proxy buffering delays SSE `text/event-stream` delivery into a single lump.
- Client parses NDJSON `application/x-ndjson` as a single JSON document.
- Uncancelled infinite streams leak subscriptions, connections, or memory.
- `@WebFluxTest` passes mock exchanges while real Netty HTTP fails on base path, codec, or TLS settings.

### 11.1. Spring WebFlux SSE Snippet

Illustrative snippet (**does not compile standalone inside section 4's Maven MVC project**):

```java
@GetMapping(
    path = "/events",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE
)
public Flux<ServerSentEvent<String>> events() {
    return Flux.interval(Duration.ofMillis(100))
        .take(3)
        .map(n -> ServerSentEvent.<String>builder()
            .id(Long.toString(n))
            .data("event-" + n)
            .build());
}
```

WebFlux streaming tests pair `WebTestClient`, `FluxExchangeResult<ServerSentEvent<String>>`, and `StepVerifier`:

```java
FluxExchangeResult<ServerSentEvent<String>> result =
    client.get().uri("/events")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .exchange()
        .expectStatus().isOk()
        .returnResult(
            new ParameterizedTypeReference<
                ServerSentEvent<String>>() {}
        );

StepVerifier.create(result.getResponseBody())
    .assertNext(e -> assertEquals("event-0", e.data()))
    .expectNextCount(1)
    .assertNext(e -> assertEquals("event-2", e.data()))
    .verifyComplete();
```

This snippet assumes a WebFlux test with `client`, imports, and a matching controller. Never drop it into the MVC demo and claim Reactor Netty is running. For infinite streams, use `thenCancel()` instead of `verifyComplete()`.

### 11.2. Safely Reproducing the Blocking Anti-Pattern

Wrong when calling a blocking dependency directly on the event loop:

```java
// Wrong in a reactive handler; blockingClient is hypothetical.
String value = blockingClient.fetch();
return Mono.just(value);
```

Proper offloading pattern:

```java
Mono<String> value =
    Mono.fromCallable(() -> blockingClient.fetch())
        .subscribeOn(Schedulers.boundedElastic());
```

`Mono.fromCallable` **defers** the blocking call until subscription; `subscribeOn` puts the source call onto `boundedElastic`, keeping the event loop clear. It still occupies a worker thread and neither speeds up the database nor removes pool limits. Verify offloading with thread checks or compatible BlockHound instrumentation on a live Netty path—a `StepVerifier` over `Mono.just(...)` proves nothing about end-to-end non-blocking execution.

### 11.3. SSE and Cancellation Need Real HTTP Tests

`@WebFluxTest` configures `WebTestClient` against mock exchanges **without starting a real Netty port**. To test streaming over sockets:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class StreamingHttpTest {
    @Autowired WebTestClient client;
}
```

This requires WebFlux on the classpath and concrete test methods. Consume the `Flux` result with `StepVerifier.thenCancel()`; when verifying server-side cleanup, check active subscription counters **eventually** rather than immediately after cancel due to async TCP disconnect propagation. Proxy buffering and reconnects require staging tests through the edge, not mock exchanges.

## 12. Reverse Proxies, Forwarding, and Non-JVM Failures

Bugs appearing only behind ingress/CDNs rarely surface in in-process `@SpringBootTest(RANDOM_PORT)` tests that bypass proxies. Test **both paths**:

```text
Direct to app:
  http://127.0.0.1:8080/lab/api/ping

Via gateway:
  https://service.example.test/portal/lab/api/ping
```

If direct returns 200 while public returns 404, check:

1. Host-based routing: do `Host`/SNI target the right virtual host?
2. Is path prefix `/portal` stripped before reaching Tomcat?
3. App context `/lab` + controller `/api/ping`: did a prefix get dropped or doubled?
4. HTTP vs HTTPS redirects and `X-Forwarded-Proto`/`Forwarded` trust boundaries at the edge.
5. Service port, namespace, and rollout revision across Pods.
6. Proxy limits on request size, headers, gzip/chunked encoding, or idle timeouts.

**Never treat `X-Forwarded-Prefix` as an automatic path-rewriting command.** Proxies can strip paths, keep paths, or attach forwarded headers so the app reconstructs public URLs. Test absolute `Location` hostnames, schemes, and prefixes on real staging routes. Trust forwarded headers strictly from **trusted proxies**, stripping/overwriting client-sent values at the edge to prevent host-header poisoning and open redirects.

Illustrative Nginx rule (for reading, not standalone deployment):

```nginx
location /portal/ {
    proxy_pass http://127.0.0.1:8080/;
}
```

With a prefix location and trailing `/` on `proxy_pass`, Nginx typically replaces `/portal/` with `/`, turning `/portal/lab/api/ping` into upstream `/lab/api/ping`. Omitting the trailing URI changes rewrite behavior; regex locations and normalization also interact. Inspect real upstream access logs rather than guessing backend URLs from a snippet.

## 13. Sessions, Cookies, File Uploads, and Security Edge Cases

The core lab leaves out sessions and file uploads to avoid mixing file/permission mechanics into status-code fundamentals. Before production, add coverage for:

### 13.1. Cookies / Sessions

Verify:

- `Set-Cookie: HttpOnly; Secure; SameSite` aligned with HTTPS/cross-site policies.
- Cookie `Path` matching context `/lab` or proxy prefix.
- Session isolation across users and proper CSRF token binding.
- Session expiration, invalidation, and session-fixation protection on login/logout.
- Do not assume `SameSite` replaces all CSRF protections across every threat model.

JDK `HttpClient` has no browser cookie jar by default. When testing sessions, create a **separate `CookieManager` per test user** and assert actual cookies, or use browser E2E tests for domain/same-site rules. Never share one `CookieManager` between User A and User B and mistake it for a server leak.

### 13.2. Uploads / Downloads

Common test cases:

- Invalid multipart `Content-Type` or missing required part → 400/415 per contract.
- Oversized file → 413 or contract-mapped status; do not assume all containers return identical 413s.
- `Content-Disposition` filenames with special characters, Unicode, or `../` traversal patterns encoded/validated cleanly.
- Downloads return proper `Content-Type` and `Content-Length`/streaming without exposing files outside allowlists.
- `../` or percent-encoded traversal attempts blocked in authorized sandbox tests using fake fixtures.

Avoid uploading 5 GB in CI just to test 413: lower the limit in a test profile, send a few KB past the cap, and verify the contracted error handling.

### 13.3. CORS / Preflight

Browsers can block calls on CORS even when GET returns 200 directly. Test preflights:

```text
OPTIONS /lab/api/widgets
Origin: https://frontend.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: Content-Type
```

CORS is browser-enforced; `curl` bypasses it while browsers block JS reads. Verify `Access-Control-Allow-Origin` and `Access-Control-Allow-Methods` with real `CorsConfiguration` alongside Spring Security filter ordering and CSRF. Never combine `Access-Control-Allow-Origin: *` with credentials for private data.

### 13.4. Caching / ETags

`304 Not Modified` is a **conditional response**, not an HTTP error. For cached endpoints:

- Send initial GET and capture `ETag`.
- Send `If-None-Match` with that exact value.
- Verify `304` with empty body.
- Mutate underlying data, verify `ETag` changes and 200 returns the fresh body.
- Never public-cache user secrets; apply `Cache-Control: private, no-store` where required.

CDN/reverse proxy caching can diverge from localhost behavior; test staging edge rules too. For large streams, body-buffering ETag filters consume heavy memory—evaluate before enabling globally.

## 14. Avoiding "False Green" and Flaky Tests

A reliable regression suite tests real behavior deterministically.

| Anti-Pattern | Why It Fails | Fix |
| --- | --- | --- |
| Calling controller method directly and claiming "HTTP 200" | Skips mappings, codecs, filters, and container | Use web slice or real HTTP |
| Default `@SpringBootTest` claimed as "tested Tomcat" | Default `MOCK` opens no port | Use `RANDOM_PORT` to test the connector |
| Asserting every 404 returns identical JSON | Container, domain, static handlers, and gateways differ | Assert domain JSON only where the app owns it |
| Invalid POST returns 403 and test claims "validation passed" | CSRF/security blocked before controller | Configure auth/CSRF properly and verify service uncalled |
| Hardcoding generated ID as `w101` | Context caching/test ordering shifts counters | Extract ID from response and verify read-back |
| Hardcoding port 8080 in integration tests | Collides on CI runners | Use `@LocalServerPort` |
| `Thread.sleep(100)` waiting on async work | CI/GC jitter causes flakiness | Fake clocks, `StepVerifier` virtual time, or bounded polling/Awaitility |
| Tests calling live production APIs | Risk of corrupting data, burning quotas, or leaking secrets | Use local stubs, Testcontainers, or authorized staging |
| Asserting only HTTP 200 | Body or headers may be wrong | Assert media type, fields, `Location`, `ETag` |
| Dropping failed requests from RPS/latency stats | Distorts SLOs/goodput | Count all HTTP statuses and timeouts |
| Mocking services to always succeed | Misses DB errors and connection pool exhaustion | Add integration/contract tests |
| Disabling security across all tests | Misses 401/403/CSRF bugs | Separate mapping slices from security integration tests |
| Asserting latency `< 30ms` in unit/CI tests | Timing depends on CI hardware | Use generous deadlines; benchmark separately |
| Tests leaving dirty DB/queue state | Cross-test data pollution | Isolate fixtures, unique keys, and clean boundaries |
| Putting `@Transactional` on `RANDOM_PORT` expecting rollback | Server handler runs in a separate transaction | Reset data explicitly instead of relying on test-thread rollback |
| Testing only single Pod / localhost | Misses proxy, multi-replica, and rollout bugs | Add staging E2E and rollout checks |

### 14.1. Four Assertion Dimensions for Error Tests

Not every test needs four separate Java assertions, yet consider all four **dimensions** of the contract:

1. **Status**: exact 200/201/304/400/401/403/404/405/406/415/500.
2. **Headers**: `Content-Type`, `Location`, `WWW-Authenticate`, `ETag`, `Cache-Control`, CORS/`Retry-After` as applicable.
3. **Body**: expected data schema/fields, business error codes, zero stack traces or PII.
4. **Side effects**: invalid writes leave state untouched; created resources are retrievable; timeouts don't duplicate writes; cancellation cleans up streams.

For container routing 404s, checking status alone can suffice when the body belongs to the container rather than an app contract. For business 404s, assert the stable error code.

### 14.2. Splitting CI into Two Lanes

- **Fast suite**: unit + web slice tests on every commit with minimal dependencies and lean contexts.
- **Integration suite**: `RANDOM_PORT` + Testcontainers/HTTP stubs on PRs and pre-release gates.

As projects grow, use JUnit `@Tag("integration")` or Maven Surefire/Failsafe profiles. If adopting `maven-failsafe-plugin` for `*IT` classes, configure both plugin goals and `verify` phase properly; this sample names all tests `*Test` so `mvn test` runs all 24 tests simply.

Never delete slow integration tests just to speed up CI; move them to a dedicated lane with clear ownership. Root-cause flaky tests rather than burying failures behind blind retries.

### 14.3. Data and Security Boundaries

- Use synthetic accounts and fake data only; never commit production credentials to source control or logs.
- Redact `Authorization`, `Cookie`, JWTs, session IDs, and PII from test failure output.
- Never expose Actuator `mappings`, `env`, or `threaddump` publicly; bind `127.0.0.1` in the lab.
- Never aim load or chaos tests at production or unauthorized third-party services.
- Keep real Spring Security policies active in authorization tests, clearly separated from filter-disabled mapping slices.
- Ensure test failures never dump secrets in stack traces; `/fail` throws only a non-sensitive message.
- Run path-traversal/upload tests strictly inside sandboxed temp directories.

## 15. Practice Completion Checklist

- [ ] Project compiles on Java 17+ using consistent Spring Boot 3.5.x imports and dependencies.
- [ ] `server.servlet.context-path=/lab` treated as container prefix and not duplicated in `@RequestMapping`.
- [ ] Positive 200 and negative 404 tests cover missing context path, wrong route, and trailing slash.
- [ ] Tests cover 405 method, 406 `Accept`, and 415 `Content-Type`.
- [ ] Tests cover 400 malformed JSON, 400 Bean Validation, 400 missing required query param, and 400 int binding failure.
- [ ] Tests cover 200 existing widget read and domain 404 with JSON error code.
- [ ] Test covers 201 + `Location` + read-back without hardcoding generated IDs.
- [ ] Deliberate 500 test exists without brittle assertions on framework default error bodies.
- [ ] Tests cover 401 anonymous, 200 authorized user, and 403 missing role against the **real `SecurityFilterChain`**.
- [ ] Tests cover 200 ETag and conditional GET 304 via `If-None-Match`.
- [ ] Actuator `mappings` diagnostic checked under context path, local/internal only.
- [ ] Clear separation between `@WebMvcTest`/MockMvc slices and `RANDOM_PORT` real HTTP.
- [ ] Tests use timeouts, random ports, order independence, and local-only fake credentials.
- [ ] 403 CSRF never confused with 400 validation or 405 method errors.
- [ ] Proxy, TLS, CORS, and WebFlux tests are not faked with mock MVC and claimed as E2E.
- [ ] When adding sessions, DBs, or uploads, fixtures and cleanup match transaction/network boundaries.
- [ ] Every bug fits a reproducible **red → green → regression** loop independent of one developer's machine.
- [ ] QA reports state exact tested scope without fabricating throughput/latency benchmarks.

## 16. Self-Check Questions and Answers

**1. Why does `GET /api/ping` return 404 while `GET /lab/api/ping` returns 200?**  
Because the Servlet context path is `/lab`. The controller maps `/api/ping` inside that context.

**2. Should a POST to a GET-only route return 404 or 405?**  
Typically 405 when the path has a handler that rejects the HTTP method and no earlier filter/security rule blocks it.

**3. What occurs when `Accept: application/xml` hits an endpoint with `produces=application/json`?**  
Typically 406 Not Acceptable.

**4. What occurs when a `text/plain` body hits `@PostMapping(consumes=application/json)`?**  
Typically 415 Unsupported Media Type.

**5. Are malformed JSON and `@NotBlank` failures the same error?**  
Both may return 400, yet one happens in the JSON decoder and the other in Bean Validation. Keep separate tests.

**6. How do missing Basic credentials and valid `USER` credentials lacking `ADMIN` differ?**  
Missing credentials typically return 401; insufficient role returns 403.

**7. Why doesn't a passing MockMvc test prove Tomcat context path `/lab` works?**  
MockMvc simulates Servlet requests/responses in-process without starting Tomcat's socket or context registration.

**8. How do you avoid flaky IDs when testing resource creation?**  
Read the ID/`Location` from the POST response and fetch it back rather than hardcoding counter values.

**9. Why should `GET /lab/api/widgets/nope` assert the domain error code while `GET /lab/api/pign` need not?**  
Domain 404 follows the app/advice contract; route-typo 404s may come from container or static resource handling.

**10. If an invalid POST returns 403, does that prove `@Valid` works?**  
No. Security or CSRF likely blocked the request before validation ran.

**11. Does `@SpringBootTest` open a real server port by default?**  
No; set `RANDOM_PORT` to boot a real embedded server.

**12. Why is HTTP 304 not an error?**  
It tells the client its cached representation still matches the current ETag/`Last-Modified`, saving body bandwidth.

**13. If the test client times out, did the server definitely return 504?**  
No. A client timeout can happen without receiving any HTTP response.

**14. If SSE emits a 200 event and the publisher later errors, is asserting status 200 enough?**  
No. Check stream signals, termination, cancellation, and resource cleanup.

**15. If hitting the backend directly returns 200 while the gateway returns 404, should you edit `@GetMapping` first?**  
No. Inspect host routing, path rewrites, and upstream ports at the gateway first.

**16. Does passing 24 functional tests prove the API handles 10,000 RPS?**  
No. Functional regression suites are not capacity or performance benchmarks.

**17. Can the lab's `{noop}` account be shipped to production to simplify 401/403 smoke tests?**  
No. It uses a public, unhashed password strictly for loopback lab use.

**18. What extra testing tools are needed when moving to WebFlux?**  
`@WebFluxTest`/`WebTestClient`, `StepVerifier` for `Flux`/`Mono`, plus checks for event-loop blocking, cancellation, NDJSON/SSE, and real Netty HTTP.

## 17. Official References

- Spring Boot 3.5 — **Testing Spring Boot Applications**, `@WebMvcTest`, `@SpringBootTest`, `RANDOM_PORT`, and transaction semantics: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 — **Servlet Web Applications**, path mapping/static resources: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Spring Boot 3.5 — **Common Application Properties**, `server.servlet.context-path`, Actuator/security settings: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html
- Spring Boot 3.5 — **Actuator Mappings Endpoint**: https://docs.spring.io/spring-boot/3.5/api/rest/actuator/mappings.html
- Spring Framework — **MockMvc**: https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html
- Spring Framework — **HTTP Status Code Handling**: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html
- Spring Framework — **Web MVC Request Mapping and Content Negotiation**: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html
- Spring Framework — **WebTestClient**: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Spring Security — **Servlet Testing with MockMvc**: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Security — **CSRF Protection**: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Project Reactor — **Testing Reactive Streams with StepVerifier**: https://projectreactor.io/docs/core/release/reference/testing.html
- Spring Boot 3.5.16 — **Release 25/06/2026, final OSS 3.5.x**: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/

**Conclusion:** A thorough web runtime test suite goes far beyond checking "GET returns 200." It deterministically reproduces **wrong context paths, bad handler/method/media types, JSON/validation errors, 401/403 security failures, domain 404s, unexpected 500s, conditional 304 caching**, and side effects—separating controller-slice MockMvc from real HTTP over Tomcat. For proxies, WebFlux streaming, uploads, sessions, rate limiting, timeouts, and databases, extend coverage with layer-appropriate integration/E2E tests. Keep fixtures synthetic, assert status/headers/body contracts, and follow **red → green → regression** so resolved bugs stay resolved.