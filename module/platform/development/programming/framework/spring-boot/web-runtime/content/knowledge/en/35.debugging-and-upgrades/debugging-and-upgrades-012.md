# Verifying Through Real Server Testing After Changing Web Stack or Server

## 1. Why Are a Green Build and Green MockMvc Insufficient for Upgrades?

A Spring Boot application may run fine on **Spring MVC over Tomcat**, yet after switching to **Jetty**, **Undertow**, or replacing **Spring MVC entirely with Spring WebFlux/Reactor Netty**, tests that only invoke controllers via mocks stay green while production breaks:

- Multipart uploads are rejected by the new parser even though `MockMultipartFile` still passes in unit tests.
- HTTP 404/500 responses return different bodies or content types due to `/error`, container error dispatch, or reactive error handlers.
- Session cookies change name, path, `SameSite`/`Secure` policy, or fail to persist across requests.
- Large request headers, URIs, or form posts are rejected before reaching the controller.
- SSE/NDJSON gets buffered, or the response commits before an error handler tries changing status.
- Clients disconnect while stream writers still hold threads/files or Reactor subscriptions fail to clean up.
- CORS preflight/redirects, URL encoding, route matching, and method resolution behave differently.
- HTTP/2 ALPN/TLS, proxy headers, keep-alive, compression, and timeouts act differently from the old environment.
- An application silently keeps running MVC because both `spring-boot-starter-web` and `spring-boot-starter-webflux` sit on the classpath.

This article belongs to **Debugging and Upgrades** in **Spring Boot - web-runtime**. Its mission is building a **live-server-verified HTTP contract suite** applying the *same standard* before and after switching frameworks or embedded servers.

Illustrative scope: **Java 17+, Spring Boot 3.3.13, Spring Framework 6.1.x, JUnit 5**. Examples use Spring Boot 3.3 for consistent APIs; for real deployments, use a security-supported branch and check changes in newer Boot/Framework major versions. Test outcomes described here are **design expectations**, not Gradle logs executed by the author.

After this article, you will be able to:
1. Distinguish changing the **web stack** from changing the **embedded server**.
2. Confirm a test process actually opened a live TCP port and identify which server is running.
3. Use `@SpringBootTest(RANDOM_PORT)`, `@LocalServerPort`, and JDK `HttpClient` to test Spring MVC across Tomcat/Jetty/Undertow.
4. Use WebFlux `@AutoConfigureWebTestClient`, `FluxExchangeResult`, and `StepVerifier` to test SSE/NDJSON and cancellation on real Reactor Netty.
5. Catch bugs that **only** surface across real networks, parsers, and dispatches with a CI-ready matrix.
6. Set go/no-go rollout criteria and avoid mistaking infrastructure failures for business controller bugs.

## 2. Two Very Different Changes

### 2.1. Swapping the Embedded Server While Keeping Spring MVC

```text
Before:
  spring-boot-starter-web
      └── Spring MVC / DispatcherServlet
             └── Embedded Tomcat

After:
  spring-boot-starter-web
      └── Spring MVC / DispatcherServlet
             └── Embedded Jetty or Undertow
```

Controllers can keep `@RestController`, `@GetMapping`, `HttpServletRequest`, and `MultipartFile`. However, HTTP parsing, connector threads, Servlet async, multipart implementations, error dispatch, HTTP/2, and header limits can change. This is a **server migration**, not a reactive rewrite.

Spring Boot 3.3 supports Tomcat, Jetty, and Undertow for Servlet apps. `spring-boot-starter-web` pulls in Tomcat by default; to use Jetty or Undertow, **exclude the old server dependency and add the new starter**.

### 2.2. Replacing MVC with WebFlux (Usually Swapping the Server Too)

```text
Before:
  Spring MVC / DispatcherServlet
      └── Servlet container (Tomcat/Jetty/Undertow)

After:
  Spring WebFlux / DispatcherHandler
      └── Reactor Netty (default)
          or a supported reactive server adapter
```

This changes the **request-handling framework**:
- `HttpServletRequest`, `HttpSession`, Servlet `Filter`, and `HandlerInterceptor` do not automatically turn into `ServerWebExchange`, `WebSession`, and `WebFilter`.
- MVC `HttpMessageConverter` differs from WebFlux `HttpMessageReader/Writer`.
- Controller methods may keep `@GetMapping` names, yet APIs, threading, cancellation, exception handling, and codecs differ.
- Blocking JDBC/JPA/`RestTemplate` does not become non-blocking just because a controller returns `Mono`.
- Reactor Netty is the default reactive WebFlux server, though reactive web apps also have adapters for other supported servers in Boot 3.3.

**Very common trap:** adding `spring-boot-starter-webflux` to an app already carrying `spring-boot-starter-web` just to use `WebClient` **does not switch the server to WebFlux**. Boot 3.3 prioritizes MVC when both exist. Verify the classpath, `WebApplicationType`, actual `WebServerApplicationContext`, startup logs, and runtime behavior rather than guessing from dependency names.

### 2.3. Identification Table

| Indicator | MVC/Servlet | WebFlux/Reactive |
|---|---|---|
| Dispatcher | `DispatcherServlet` | `DispatcherHandler` |
| Request API | `HttpServletRequest` | `ServerWebExchange` |
| Session API | `HttpSession` | `WebSession` |
| Filter | `jakarta.servlet.Filter` | `WebFilter` |
| Message conversion | `HttpMessageConverter` | `HttpMessageReader/Writer` |
| Streaming controller | `StreamingResponseBody`/`SseEmitter` | `Flux<DataBuffer>`/`Flux<ServerSentEvent<T>>` |
| Default HTTP server | Tomcat via `starter-web` | Reactor Netty via `starter-webflux` |
| Web context check | `ServletWebServerApplicationContext` | `ReactiveWebServerApplicationContext` |
| Mock controller test | `MockMvc` | `WebTestClient.bindToController` |
| Real HTTP test | `RANDOM_PORT` + HTTP client | `RANDOM_PORT` + `WebTestClient`/JDK client |

**Never assume every Spring MVC API has a 1:1 reactive counterpart.** Spring Security also changes from `SecurityFilterChain` to `SecurityWebFilterChain`, and error handling and session persistence require their own matrix.

## 3. What Mock Tests Cover, and What They Miss

Both test styles belong together, without replacing one another.

| Approach | Opens HTTP socket? | Tests well | Does NOT verify |
|---|---|---|---|
| Plain Java unit test | No | Pure business rules | HTTP stack |
| `MockMvc` / `@WebMvcTest` | No | Controller mapping, binding, validation, advice, mock Servlet async | Container header parser, TCP, real multipart parsing/error dispatch |
| `WebTestClient.bindToController` | No | WebFlux annotated handlers + codecs in mock | Reactor Netty socket/cancel/parser |
| Default `@SpringBootTest` (`MOCK`) | Usually no | Full app beans + mock web layer | Real embedded server |
| `@SpringBootTest(RANDOM_PORT)` | **Yes** | App + embedded server + HTTP transport | Ingress/CDN outside app |
| `WebTestClient.bindToServer` | **Yes**, if aimed at live port | HTTP responses + streaming `Flux` | Real browsers/proxies |
| JDK `HttpClient` | **Yes** | Headers/cookies/binary bodies/HTTP versions/stream close | All browser behaviors |
| Staging via ingress/TLS/HTTP/2 | **Yes, multi-hop** | Routing, ALPN, buffering, LB/edge limits | Full-scale load/chaos tests |

In Boot 3.3:
- `@SpringBootTest(webEnvironment = WebEnvironment.MOCK)` is the default and does not start a server like `RANDOM_PORT`.
- `RANDOM_PORT` binds a free port in tests; use `@LocalServerPort` instead of hardcoding 8080.
- `DEFINED_PORT` risks port collisions during parallel runs and is unnecessary for smoke integration tests.
- Under `RANDOM_PORT`, the HTTP client and server run in separate threads and transactions; `@Transactional` on a **test method** will not roll back transactions committed on the HTTP server thread.

**Transaction trap example:** if a test creates an order over HTTP POST and expects the DB row to disappear via `@Transactional` rollback, that fails because the server thread ran its own transaction. Clean up using data fixtures, repository cleanup, test-only reset endpoints, or DB container resets rather than expecting test-method rollback.

## 4. Test the "Observable Contract," Not Old Implementation Details

A good migration test asserts only what clients and operators have a right to depend on:
- Exact status codes for success, business failure, validation failure, not-found, and unhandled failure.
- `Content-Type`/charset, JSON/XML/text/binary payloads, schemas, and business values.
- Standard headers: `Location`, `Cache-Control`, `Content-Disposition`, `ETag`, `Vary`, CORS; never treat header order as a contract.
- Cookies: name, path/domain, `Secure`/`HttpOnly`/`SameSite`, and continuity across requests.
- URL encoding, query parameters, and matrix/path variables where contracted.
- Multipart uploads, file sizes, part counts, and parser rejections.
- Async: requests do not terminate prematurely, timeouts, and error advice.
- SSE/NDJSON: event/record contents, ordering, terminal signals, and cancellation/cleanup.
- HTTP/1.1 keep-alive, TLS, and HTTP/2 when required by infra/security policy.
- Responses through reverse proxies/ingress, compression, and large headers/bodies.
- Metrics/logging: status/outcome, aborted requests, resource usage, server startup/shutdown.

**Do NOT assert:**
- JSON property ordering unless the schema mandates it.
- `Server` response headers exposing vendor/version.
- A 1:1 count of TCP packets to `Flux.onNext` events.
- Exact wording/layout of container-default HTML error pages.
- That client abort errors are always literally `Broken pipe` or `IOException` within 1 ms.
- HTTP status 503 for **every** new request during graceful shutdown; container rejection behavior varies.

Before upgrading, record a baseline of responses, latency, HTTP behavior, and resource usage. When switching servers, keep **shared contract tests** identical and add server-specific assertions only where **product contracts permit differences**.

## 5. Minimum Test Matrix for Real Server Runs

| Category | Test scenarios | Why `MockMvc` is insufficient |
|---|---|---|
| Startup | Expected web stack and server runtime | `MockMvc` starts no embedded server |
| Success | JSON UTF-8, URI encoding, queries | Exercises network serializer and request decoder |
| Content negotiation | Valid and invalid `Accept`/`Content-Type` | Real server + message converters/codecs |
| Method mapping | GET/POST/OPTIONS/HEAD | Headers, preflight, container routing |
| Error | 404/422/500, `ProblemDetail`, and `/error` | Servlet error-page dispatch does not run like a real container in `MockMvc` |
| Multipart | Real wire-formatted multipart, >size cap | `MockMultipartFile` skips the real parser |
| Headers | Cookie/Authorization, oversized headers | Parsers reject before controllers |
| Session | Cookie jar across two requests | Container cookie behavior and session lifecycle |
| Async MVC | `Callable`/`DeferredResult` | Real async dispatch and executor behavior |
| Streaming | Incremental NDJSON/SSE consumption | Network flushing, body consumers, media encoding |
| Client abort | Read first event then close/cancel | TCP/HTTP transport and cancellation propagation |
| Security | CSRF, CORS, auth sessions, redirects | Filter ordering and cookies across stack switches |
| HTTP/2/TLS | ALPN, cert trust, cipher/hostname | Mock tests perform no TLS handshake |
| Compression | `Content-Encoding`/`Vary`, streaming | Container/proxy encoder behavior |
| Graceful shutdown | `SIGTERM` during in-flight request | No network accept/drain in mocks |
| Operations | Actuator readiness/metrics/traces | Middleware and live web server observations |

Run tests in tiers: fast PR checks (HTTP core), nightly/CI matrices across Tomcat/Jetty/Undertow and WebFlux, staging via TLS/ingress, plus canary metrics and rollback drills.

## 6. Project A: One Test Suite for Spring MVC + Tomcat/Jetty/Undertow

The Spring Boot 3.3.13 Java 17+ sample below selects the embedded server via a **Gradle project property** while keeping identical source code and HTTP tests. Endpoints cover typical upgrade failure points:
- `GET /api/hello`: query decoding, JSON/UTF-8, stable headers, CORS.
- `POST /api/echo`: JSON binding, content-type, business error with `ProblemDetail`.
- `GET /api/missing`: real 404 path (missing route).
- `GET /api/crash`: unhandled exception reaching the container/error pipeline.
- `POST /api/upload`: wire-level multipart, reading only file metadata.
- `GET /api/async`: Servlet `Callable`.
- `GET /api/stream`: real NDJSON stream with cleanup probe.
- `GET /api/session`: session counter across requests via cookie jar.

### 6.1. Project Layout

```text
server-contract-mvc/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/servercontract/
    │   │   └── ServletContractApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/servercontract/
            └── ServletLiveContractTest.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'server-contract-mvc'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

def serverEngine = (findProperty('serverEngine') ?: 'tomcat').toString()
if (!(serverEngine in ['tomcat', 'jetty', 'undertow'])) {
    throw new GradleException(
            "Choose -PserverEngine=tomcat|jetty|undertow")
}

dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        if (serverEngine != 'tomcat') {
            exclude group: 'org.springframework.boot',
                    module: 'spring-boot-starter-tomcat'
        }
    }

    if (serverEngine == 'jetty') {
        implementation 'org.springframework.boot:spring-boot-starter-jetty'
    }
    if (serverEngine == 'undertow') {
        implementation 'org.springframework.boot:spring-boot-starter-undertow'
    }

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
    systemProperty 'expectedServerEngine', serverEngine
}
```

How it works:
- With `-PserverEngine=tomcat`, `starter-web` retains default Tomcat.
- With `jetty` or `undertow`, transitive Tomcat is excluded and the chosen server starter is added.
- A Gradle project property is a **build-time** variable; it does not swap servers via `--server.port` or a runtime env var.
- Inspect the dependency tree via `gradle dependencies --configuration runtimeClasspath` and `dependencyInsight` to ensure no duplicate server factories slip in.
- If other starters or transitive modules pull Tomcat back in, resolve the entire dependency graph rather than just one exclusion.

**Do not reuse the same built JAR expecting `serverEngine` to switch at runtime** under this build pattern. Re-run `gradle test` for each property value to build each distinct classpath.

### 6.2. Runtime Configuration

**`src/main/resources/application.properties`:**

```properties
server.port=8080

# Intended for testing real parser/response behavior:
server.max-http-request-header-size=8KB
spring.servlet.multipart.max-file-size=64KB
spring.servlet.multipart.max-request-size=128KB
spring.mvc.async.request-timeout=5s

# Prevent unhandled exceptions from leaking stack/message to HTTP clients:
server.error.include-message=never
server.error.include-stacktrace=never

# Avoid altering compression in core contract tests;
# test compression in a dedicated suite.
server.compression.enabled=false
```

**Explanation:** these multipart properties belong to the Servlet stack and do not bound general JSON bodies. `server.max-http-request-header-size` is a common property, yet parser semantics vary by server; never assert "byte 8193 is always 431" across every connector. `spring.mvc.async.request-timeout` is the MVC async deadline, not an HTTP client read timeout.

### 6.3. Java 17+ Application

**`src/main/java/com/example/servercontract/ServletContractApplication.java`:**

```java
package com.example.servercontract;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.concurrent.Callable;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.servlet.http.HttpSession;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@SpringBootApplication
public class ServletContractApplication {
    public static void main(String[] args) {
        SpringApplication.run(ServletContractApplication.class, args);
    }
}

record Greeting(String message) {}

class ContractRejectedException extends RuntimeException {
    ContractRejectedException(String message) {
        super(message);
    }
}

@Component
class StreamProbe {
    final AtomicInteger active = new AtomicInteger();
    final AtomicInteger finished = new AtomicInteger();
}

@Configuration(proxyBeanMethods = false)
class ServletAsyncConfig implements WebMvcConfigurer {
    @Bean
    ThreadPoolTaskExecutor mvcTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("mvc-contract-");
        return executor;
    }

    private final ThreadPoolTaskExecutor taskExecutor;

    ServletAsyncConfig(ThreadPoolTaskExecutor taskExecutor) {
        this.taskExecutor = taskExecutor;
    }

    @Override
    public void configureAsyncSupport(
            AsyncSupportConfigurer configurer) {
        configurer.setTaskExecutor(taskExecutor);
        configurer.setDefaultTimeout(5000L);
    }
}

@RestController
@RequestMapping("/api")
class ServletContractController {
    private final StreamProbe probe;

    ServletContractController(StreamProbe probe) {
        this.probe = probe;
    }

    @CrossOrigin(origins = "https://frontend.example")
    @GetMapping("/hello")
    ResponseEntity<Greeting> hello(@RequestParam String name) {
        return ResponseEntity.ok()
                .header("X-Contract-Version", "1")
                .body(new Greeting("Hello " + name));
    }

    @PostMapping(
            path = "/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    Map<String, String> echo(
            @RequestBody Map<String, String> input) {
        String value = input.get("value");
        if (value == null || value.isBlank()) {
            throw new ContractRejectedException("Missing value");
        }
        return Map.of("value", value);
    }

    @GetMapping("/crash")
    String crash() {
        throw new IllegalStateException("internal diagnostic marker");
    }

    @PostMapping(
            path = "/upload",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    Map<String, Long> upload(
            @RequestParam("file") MultipartFile file) {
        return Map.of("bytes", file.getSize());
    }

    @GetMapping("/async")
    Callable<String> async() {
        return () -> {
            Thread.sleep(100);
            return "async-ok";
        };
    }

    @GetMapping(
            path = "/stream",
            produces = "application/x-ndjson")
    StreamingResponseBody stream() {
        return output -> {
            probe.active.incrementAndGet();
            try {
                for (int index = 0; index < 30; index++) {
                    byte[] line = ("{\"n\":" + index + "}\n")
                            .getBytes(StandardCharsets.UTF_8);
                    output.write(line);
                    output.flush();

                    try {
                        Thread.sleep(35);
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                        throw new IOException(
                                "stream worker interrupted", ex);
                    }
                }
            } finally {
                probe.active.decrementAndGet();
                probe.finished.incrementAndGet();
            }
        };
    }

    @GetMapping("/session")
    Map<String, Integer> session(HttpSession session) {
        Integer seen = (Integer) session.getAttribute("visits");
        int now = seen == null ? 1 : seen + 1;
        session.setAttribute("visits", now);
        return Map.of("visits", now);
    }
}

@RestControllerAdvice
class ContractAdvice {
    @ExceptionHandler(ContractRejectedException.class)
    ResponseEntity<ProblemDetail> rejected(
            ContractRejectedException exception) {
        ProblemDetail body = ProblemDetail.forStatus(422);
        body.setTitle("Invalid contract input");
        body.setDetail("Required field is missing");
        return ResponseEntity.status(422).body(body);
    }
}
```

**Important note about `@Configuration` in this example:** avoid declaring `@Bean ThreadPoolTaskExecutor` and constructor-injecting that same bean into the **same** `@Configuration` class; in some cases that creates a dependency cycle. To ensure the code is cleanly runnable without self-dependency, **split the executor factory and async config into two classes** as shown in the safe replacement below, keeping the controller/records/probe/advice unchanged:

```java
// Replace the ServletAsyncConfig class above with these two classes:
@Configuration(proxyBeanMethods = false)
class AsyncExecutorBeans {
    @Bean
    ThreadPoolTaskExecutor mvcTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("mvc-contract-");
        return executor;
    }
}

@Configuration(proxyBeanMethods = false)
class ServletAsyncConfig implements WebMvcConfigurer {
    private final ThreadPoolTaskExecutor taskExecutor;

    ServletAsyncConfig(ThreadPoolTaskExecutor taskExecutor) {
        this.taskExecutor = taskExecutor;
    }

    @Override
    public void configureAsyncSupport(
            AsyncSupportConfigurer configurer) {
        configurer.setTaskExecutor(taskExecutor);
        configurer.setDefaultTimeout(5000L);
    }
}
```

This replacement is **part of the same Java file**: only **one** definition of `ServletAsyncConfig` must exist in the final code. Do not leave both versions when copying, or compilation will fail with duplicate class. `ThreadPoolTaskExecutor` provides a bounded pool/queue supporting `Callable`/`StreamingResponseBody`, with Spring managing `@Bean` shutdown.

Additional notes:
- `/api/hello` tests UTF-8 queries/JSON and CORS without depending on JSON field order.
- `/api/echo` returns 422 via advice, while `/api/crash` is uncaught by advice and travels through Boot/Servlet container's default error pipeline.
- `/api/upload` avoids calling `file.getBytes()` so large files aren't buffered in heap; the parser is exercised over **real HTTP multipart**.
- `/api/async` returns `Callable<String>`; the HTTP response finishes only after async execution/dispatch, not when the controller method returns `Callable`.
- `/api/stream` streams responses with flushing and `finally` probe; when the client closes early, the writer may hit `IOException` or finish normally before socket error surfaces. The test asserts only eventual cleanup.
- `/api/session` creates and updates `HttpSession`. The common container cookie is `JSESSIONID`; tests use `CookieManager` instead of hardcoding cookie names.
- `server.error.include-message=never` and `include-stacktrace=never` prevent leaking internal diagnostic markers; production still needs explicit logging/Actuator policies.
- A single file contains one top-level `public class ServletContractApplication`; the other classes are package-private in the same package.

**When assembling the complete compilable code, use the two-class `AsyncExecutorBeans` + `ServletAsyncConfig` version from the second block in place of the single `ServletAsyncConfig` in the first block.** The tests and behavior assume the cycle-free version. This replacement note is simply a clear file-assembly step, not two separate projects.

## 7. Real-HTTP JUnit Tests for Spring MVC (Without `MockMvc`)

The test suite uses `@SpringBootTest(webEnvironment=RANDOM_PORT)` and JDK `java.net.http.HttpClient`. Against a live server:
- The container parses URLs/queries/headers and performs real Servlet dispatch.
- Multipart transmits wire-formatted bytes over TCP.
- The error controller handles unhandled exceptions inside the real container environment.
- A cookie jar persists across two requests.
- A response stream is read partially and then intentionally closed.

**`src/test/java/com/example/servercontract/ServletLiveContractTest.java`:**

```java
package com.example.servercontract;

import java.io.BufferedReader;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Arrays;
import java.util.Locale;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ServletLiveContractTest {

    @LocalServerPort
    int port;

    @Autowired
    ServletWebServerApplicationContext context;

    @Autowired
    StreamProbe probe;

    private HttpClient client() {
        return HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofSeconds(3))
                .build();
    }

    private URI uri(String path) {
        return URI.create("http://127.0.0.1:" + port + path);
    }

    @Test
    void actualServerMatchesChosenBuild() {
        String expected = System.getProperty(
                "expectedServerEngine", "tomcat");
        String actual = context.getWebServer()
                .getClass().getSimpleName()
                .toLowerCase(Locale.ROOT);

        assertThat(actual).contains(expected);
        assertThat(port).isPositive();
    }

    @Test
    void jsonUtf8AndCustomHeaderSurviveServerChange()
            throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                uri("/api/hello?name=Tr%C3%A0%20%26%20B%C3%A1nh"))
                .GET().build();

        HttpResponse<String> response = client().send(
                request, HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(response.body())
                .contains("Hello Trà & Bánh");
        assertThat(response.headers()
                .firstValue("content-type").orElse(""))
                .contains("application/json");
        assertThat(response.headers()
                .firstValue("x-contract-version").orElse(""))
                .isEqualTo("1");
    }

    @Test
    void corsPreflightIsNotChanged() throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                uri("/api/hello?name=Test"))
                .method("OPTIONS",
                        HttpRequest.BodyPublishers.noBody())
                .header("Origin", "https://frontend.example")
                .header("Access-Control-Request-Method", "GET")
                .build();

        HttpResponse<String> response = client().send(
                request, HttpResponse.BodyHandlers.ofString());

        assertThat(response.statusCode()).isBetween(200, 299);
        assertThat(response.headers()
                .firstValue("Access-Control-Allow-Origin")
                .orElse(""))
                .isEqualTo("https://frontend.example");
    }

    @Test
    void jsonInputAndBusinessErrorAreEquivalent()
            throws Exception {
        HttpRequest good = HttpRequest.newBuilder(
                uri("/api/echo"))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(
                        "{\"value\":\"hello\"}"))
                .build();

        HttpResponse<String> success = client().send(
                good, HttpResponse.BodyHandlers.ofString());
        assertThat(success.statusCode()).isEqualTo(200);
        assertThat(success.body()).contains("\"value\":\"hello\"");

        HttpRequest bad = HttpRequest.newBuilder(
                uri("/api/echo"))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString("{}"))
                .build();

        HttpResponse<String> rejected = client().send(
                bad, HttpResponse.BodyHandlers.ofString());

        assertThat(rejected.statusCode()).isEqualTo(422);
        assertThat(rejected.body())
                .contains("Invalid contract input");
        assertThat(rejected.body())
                .doesNotContain("internal diagnostic marker");
    }

    @Test
    void containerNotFoundAndUnhandledErrorAreVisible()
            throws Exception {
        HttpResponse<String> missing = client().send(
                HttpRequest.newBuilder(uri("/api/missing"))
                        .GET().build(),
                HttpResponse.BodyHandlers.ofString());

        assertThat(missing.statusCode()).isEqualTo(404);

        HttpResponse<String> crash = client().send(
                HttpRequest.newBuilder(uri("/api/crash"))
                        .GET().build(),
                HttpResponse.BodyHandlers.ofString());

        assertThat(crash.statusCode()).isEqualTo(500);
        assertThat(crash.body())
                .doesNotContain("internal diagnostic marker");
    }

    private byte[] multipartBody(int length) throws Exception {
        String boundary = "LiveContractBoundary";
        String prefix = "--" + boundary + "\r\n"
                + "Content-Disposition: form-data; "
                + "name=\"file\"; filename=\"sample.txt\"\r\n"
                + "Content-Type: text/plain\r\n\r\n";
        String suffix = "\r\n--" + boundary + "--\r\n";

        ByteArrayOutputStream out = new ByteArrayOutputStream();
        out.write(prefix.getBytes(StandardCharsets.UTF_8));
        byte[] file = new byte[length];
        Arrays.fill(file, (byte) 'x');
        out.write(file);
        out.write(suffix.getBytes(StandardCharsets.UTF_8));
        return out.toByteArray();
    }

    @Test
    void multipartIsParsedByRealContainer()
            throws Exception {
        byte[] body = multipartBody(4096);
        HttpRequest request = HttpRequest.newBuilder(
                uri("/api/upload"))
                .header("Content-Type",
                        "multipart/form-data; boundary=LiveContractBoundary")
                .POST(HttpRequest.BodyPublishers.ofByteArray(body))
                .build();

        HttpResponse<String> response = client().send(
                request, HttpResponse.BodyHandlers.ofString());

        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(response.body()).contains("\"bytes\":4096");
    }

    @Test
    void servletAsyncRequestFinishesBeforeHttpResponse()
            throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                uri("/api/async")).GET().build();

        HttpResponse<String> response = client().send(
                request, HttpResponse.BodyHandlers.ofString());

        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(response.body()).isEqualTo("async-ok");
    }

    @Test
    void cookieJarPreservesSessionAcrossRequests()
            throws Exception {
        CookieManager cookieManager = new CookieManager(
                null, CookiePolicy.ACCEPT_ALL);
        HttpClient sessionClient = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .cookieHandler(cookieManager)
                .build();

        HttpRequest request = HttpRequest.newBuilder(
                uri("/api/session")).GET().build();

        HttpResponse<String> first = sessionClient.send(
                request, HttpResponse.BodyHandlers.ofString());
        HttpResponse<String> second = sessionClient.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertThat(first.statusCode()).isEqualTo(200);
        assertThat(first.body()).contains("\"visits\":1");
        assertThat(second.statusCode()).isEqualTo(200);
        assertThat(second.body()).contains("\"visits\":2");
    }

    @Test
    void clientCanAbortRealStreamingBodyAndCleanupHappens()
            throws Exception {
        int before = probe.finished.get();

        HttpRequest request = HttpRequest.newBuilder(
                uri("/api/stream"))
                .header("Accept", "application/x-ndjson")
                .GET().build();

        HttpResponse<InputStream> response = client().send(
                request, HttpResponse.BodyHandlers.ofInputStream());

        assertThat(response.statusCode()).isEqualTo(200);

        try (InputStream data = response.body()) {
            BufferedReader reader = new BufferedReader(
                    new InputStreamReader(data,
                            StandardCharsets.UTF_8));
            assertThat(reader.readLine()).isEqualTo("{\"n\":0}");
            // Close body before reading all 30 records.
        }

        await().atMost(Duration.ofSeconds(5))
                .untilAsserted(() -> {
                    assertThat(probe.finished.get())
                            .isGreaterThan(before);
                    assertThat(probe.active.get()).isZero();
                });
    }
}
```

**Expectation:** **9 tests** run on each server classpath and verify the observable HTTP contract. This is by design inspection; JDK/Gradle were not executed to assert PASS. Intentional assertions:
- 404/500 assert only **status** plus non-leakage of internal messages, without depending on container-default HTML/JSON bodies.
- The multipart test is genuine via JDK `HttpClient` and encoded boundaries; `MockMultipartFile` would not exercise the network parser.
- The session test uses `CookieManager` and the same `HttpClient` across two requests without hardcoding cookie names. Switching to Spring Session/Redis may change cookie names while keeping continuity testable.
- The stream test proves **eventual cleanup**, without requiring the server to observe a specific TCP reset or `IOException`. A finite stream might finish normally, which is fine for a bounded cleanup test.
- The server-identity test fails loudly if the classpath accidentally retains Tomcat.

**Reminder when assembling section 6.3's code:** keep the **two `@Configuration` classes** from the replacement block rather than the self-dependent `ServletAsyncConfig`. Otherwise, files map directly to the stated layout.

### 7.1. Running the Same Tests Across Three Servers

In the MVC project with JDK 17+ and Gradle:

```bash
gradle clean test -PserverEngine=tomcat
gradle clean test -PserverEngine=jetty
gradle clean test -PserverEngine=undertow
```

If using the Gradle Wrapper:
```bash
./gradlew clean test -PserverEngine=tomcat
./gradlew clean test -PserverEngine=jetty
./gradlew clean test -PserverEngine=undertow
```

**Run sequentially** if Gradle/test runners share a build directory; in CI, use isolated jobs or separate Gradle caches/workdirs. Confirm all three jobs execute the same HTTP contract suite and report the actual engine rather than just inspecting `build.gradle`.

If a server fails to boot due to dependency version incompatibility, the test **fails clearly**. Never override the server-identity test to make it pass; rely on the Spring Boot BOM, check transitive dependencies (Jackson, Jetty servlet APIs, embedded server factories), and verify version-specific config properties.

### 7.2. Add Real Negative Tests

The tests above are a **happy-path/core smoke suite**. Also add:
- Multipart file **64KB+1**: container may respond with 413, 400, or connection reset per implementation; verify **no file is saved** without demanding identical error JSON across all servers.
- HTTP headers over 8KB: parsers may reject with 400/431/close before the controller; test below and above the threshold on each server.
- Long URIs, invalid percent-encoding, and duplicate headers: test parser/normalization.
- Oversized JSON bodies: `spring.servlet.multipart.max-file-size` does not cap JSON automatically; enforce separate app/ingress body limits.
- Unsupported media types → typically 415, unacceptable `Accept` → typically 406; test per contract/content negotiation.
- Redirect slashes, encoded slashes/semicolons, and path variables: check canonicalization and proxy behavior to prevent request smuggling/path traversal.
- Slowloris/slow POST, keep-alive reuse, idle timeouts, and max connections: run in load/chaos suites rather than turning CI unit tests into stress tools.
- Servlet error dispatch from unhandled exceptions: inspect status/content-type/traces and `/error` instead of inferring container behavior from `MockMvc`.

## 8. Why Does a Real Server's 500 Differ from `MockMvc`'s 500?

The Spring Boot Servlet stack routes container errors via error-page dispatch to `/error` / `BasicErrorController` where appropriate. When an exception is caught by `@ExceptionHandler`, the response returns straight to the client. When an exception goes **unhandled** in the controller, the container/web framework determines status, dispatch, and body per version and config.

```text
GET /api/crash
       │
       ▼
DispatcherServlet
       │
 IllegalStateException
       │
 @ExceptionHandler? No
       │
 Servlet error dispatch / Boot Error MVC
       │
       ▼
HTTP 500 + body decided by Boot/container
```

In `MockMvc`, requests do not traverse a real Servlet container like Tomcat or Jetty; error-page dispatch cannot be deduced from controller-only tests. Boot Testing docs emphasize using a **fully running server** when verifying error pages.

In WebFlux, `DefaultErrorWebExceptionHandler`/`WebExceptionHandler` has a different pipeline; do not assume `BasicErrorController` exists. When switching stacks:
- Pin status and client-visible problem contracts in an **application error mapper** if required by clients.
- Never rely on a server's default error HTML/JSON.
- Ensure exception messages and stack traces never leak to clients.
- Test errors occurring before response commit and **after** a stream sends its first chunk.
- Remember a 500 response may not mean Micrometer observation shows `error != none` if advice handled the exception without setting error; test metrics policy separately.

## 9. Moving to WebFlux Needs Its Own Project and Tests

Switching from MVC to WebFlux is **not just swapping Tomcat for Netty**. The project below provides equivalent endpoint contracts plus reactive streaming/cancellation. It deliberately **omits `spring-boot-starter-web`** so Spring Boot starts a reactive server.

### 9.1. Project Layout

```text
server-contract-webflux/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/reactivecontract/
    │   │   └── ReactiveContractApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/reactivecontract/
            └── ReactiveLiveContractTest.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'server-contract-webflux'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/resources/application.properties`:**

```properties
server.port=8081
server.max-http-request-header-size=8KB
spring.codec.max-in-memory-size=256KB
server.error.include-message=never
server.error.include-stacktrace=never
```

**There is no `spring.servlet.multipart.*`** because the project does not use Servlet multipart. If adding WebFlux multipart, configure `spring.webflux.multipart.*` and test WebFlux's parser; never port `MultipartFile`/`MockMultipartFile` tests directly assuming identical semantics.

### 9.2. Reactive Java 17+ Application

**`src/main/java/com/example/reactivecontract/ReactiveContractApplication.java`:**

```java
package com.example.reactivecontract;

import java.time.Duration;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.WebSession;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;

@SpringBootApplication
public class ReactiveContractApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveContractApplication.class, args);
    }
}

record Greeting(String message) {}
record Echo(String value) {}
record Tick(long n) {}

class ContractRejectedException extends RuntimeException {
    ContractRejectedException(String message) {
        super(message);
    }
}

@Component
class ReactiveProbe {
    final AtomicInteger active = new AtomicInteger();
    final AtomicInteger cancellations = new AtomicInteger();
}

@RestController
@RequestMapping("/api")
class ReactiveContractController {
    private final ReactiveProbe probe;

    ReactiveContractController(ReactiveProbe probe) {
        this.probe = probe;
    }

    @CrossOrigin(origins = "https://frontend.example")
    @GetMapping("/hello")
    Mono<ResponseEntity<Greeting>> hello(
            @RequestParam String name) {
        return Mono.just(ResponseEntity.ok()
                .header("X-Contract-Version", "1")
                .body(new Greeting("Hello " + name)));
    }

    @PostMapping(
            path = "/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    Mono<Echo> echo(@RequestBody Mono<Echo> input) {
        return input.flatMap(value -> {
            if (value.value() == null
                    || value.value().isBlank()) {
                return Mono.error(
                        new ContractRejectedException("Missing value"));
            }
            return Mono.just(value);
        });
    }

    @GetMapping("/crash")
    Mono<String> crash() {
        return Mono.error(new IllegalStateException(
                "internal diagnostic marker"));
    }

    @GetMapping("/async")
    Mono<String> async() {
        return Mono.delay(Duration.ofMillis(100))
                .map(unused -> "async-ok");
    }

    @GetMapping(
            path = "/ndjson",
            produces = "application/x-ndjson")
    Flux<Tick> ndjson() {
        return Flux.interval(Duration.ofMillis(30))
                .take(3)
                .map(Tick::new);
    }

    @GetMapping(
            path = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    Flux<ServerSentEvent<String>> events() {
        return Flux.interval(Duration.ofMillis(40))
                .map(i -> ServerSentEvent.<String>builder()
                        .id(Long.toString(i))
                        .data("tick-" + i)
                        .build())
                .doOnSubscribe(s ->
                        probe.active.incrementAndGet())
                .doFinally(signal -> {
                    probe.active.decrementAndGet();
                    if (signal == SignalType.CANCEL) {
                        probe.cancellations.incrementAndGet();
                    }
                });
    }

    @GetMapping("/session")
    Mono<Map<String, Integer>> session(WebSession session) {
        Integer before = session.getAttribute("visits");
        int now = before == null ? 1 : before + 1;
        session.getAttributes().put("visits", now);
        return Mono.just(Map.of("visits", now));
    }
}

@RestControllerAdvice
class ReactiveContractAdvice {
    @ExceptionHandler(ContractRejectedException.class)
    ResponseEntity<ProblemDetail> rejected(
            ContractRejectedException exception) {
        ProblemDetail body = ProblemDetail.forStatus(
                HttpStatus.UNPROCESSABLE_ENTITY);
        body.setTitle("Invalid contract input");
        body.setDetail("Required field is missing");
        return ResponseEntity.status(
                HttpStatus.UNPROCESSABLE_ENTITY).body(body);
    }
}
```

Explanation:
- Uses `Mono.delay` and `Flux.interval` rather than blocking the Reactor Netty event loop with `Thread.sleep`.
- `Flux<Tick>` uses `take(3)`, so the finite HTTP NDJSON stream completes.
- SSE `Flux<ServerSentEvent<String>>` never completes, letting the client **explicitly cancel** after two events.
- The probe records `doFinally(CANCEL)` in the reactive chain. Upstream/operator cancellations can also emit `CANCEL`; the test ensures the client triggers it.
- `WebSession` differs from `HttpSession`, and its default cookie name may differ. Session attributes in this sample are in-memory within **one** test server, not shared between MVC and WebFlux.
- Never call `subscribe()` inside controllers; detaching from the HTTP lifecycle breaks server cancellation and cleanup.
- Never call `Mono.block()` inside handlers; blocking JDBC/JPA/I/O needs architectural separation when moving to reactive.
- The demo omits auth to isolate HTTP behavior. Real apps must convert `SecurityFilterChain` to `SecurityWebFilterChain` when changing security stacks and test CSRF/auth/cookies.
- One file has a single `public class` matching `ReactiveContractApplication.java`; records/controllers/advice are package-private in the same package.

## 10. WebFlux Tests Against Live Reactor Netty (Not `bindToController`)

**`src/test/java/com/example/reactivecontract/ReactiveLiveContractTest.java`:**

```java
package com.example.reactivecontract;

import java.time.Duration;
import java.util.Locale;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.web.reactive.context.ReactiveWebServerApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveLiveContractTest {

    @Autowired
    WebTestClient client;

    @Autowired
    ReactiveWebServerApplicationContext context;

    @Autowired
    ReactiveProbe probe;

    @Test
    void reallyStartsReactorNettyServer() {
        String actual = context.getWebServer()
                .getClass().getSimpleName()
                .toLowerCase(Locale.ROOT);
        assertThat(actual).contains("netty");
    }

    @Test
    void jsonAndUtf8Contract() {
        client.get()
                .uri("/api/hello?name=Tr%C3%A0%20%26%20B%C3%A1nh")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .valueEquals("X-Contract-Version", "1")
                .expectBody()
                    .jsonPath("$.message")
                    .isEqualTo("Hello Trà & Bánh");
    }

    @Test
    void reactiveJsonBindingAndErrorAdvice() {
        client.post()
                .uri("/api/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new Echo("hello"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.value").isEqualTo("hello");

        client.post()
                .uri("/api/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{}")
                .exchange()
                .expectStatus().isEqualTo(422)
                .expectBody()
                .jsonPath("$.title")
                .isEqualTo("Invalid contract input");
    }

    @Test
    void reactiveUnhandledErrorReturns500() {
        client.get().uri("/api/crash")
                .exchange()
                .expectStatus().is5xxServerError()
                .expectBody()
                .jsonPath("$.status")
                .isEqualTo(500);
    }

    @Test
    void asynchronousResponseCompletes() {
        client.get().uri("/api/async")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("async-ok");
    }

    @Test
    void ndjsonRecordsArriveAndComplete() {
        FluxExchangeResult<Tick> result = client.get()
                .uri("/api/ndjson")
                .accept(MediaType.parseMediaType(
                        "application/x-ndjson"))
                .exchange()
                .expectStatus().isOk()
                .returnResult(Tick.class);

        StepVerifier.create(result.getResponseBody())
                .expectNext(new Tick(0),
                        new Tick(1),
                        new Tick(2))
                .expectComplete()
                .verify(Duration.ofSeconds(5));
    }

    @Test
    void sseCancelEventuallyReachesLiveServer() {
        int before = probe.cancellations.get();

        FluxExchangeResult<String> result = client.get()
                .uri("/api/events")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .returnResult(String.class);

        StepVerifier.create(result.getResponseBody())
                .expectNext("tick-0", "tick-1")
                .thenCancel()
                .verify(Duration.ofSeconds(5));

        await().atMost(Duration.ofSeconds(5))
                .untilAsserted(() ->
                        assertThat(probe.cancellations.get())
                                .isGreaterThan(before));
    }

    @Test
    void cookieIsReusedWithExplicitHeader() {
        EntityExchangeResult<byte[]> first = client.get()
                .uri("/api/session")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.visits").isEqualTo(1)
                .returnResult();

        String setCookie = first.getResponseHeaders()
                .getFirst(HttpHeaders.SET_COOKIE);

        assertThat(setCookie).isNotBlank();
        String cookiePair = setCookie.split(";", 2)[0];

        client.get().uri("/api/session")
                .header(HttpHeaders.COOKIE, cookiePair)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.visits").isEqualTo(2);
    }
}
```

**Expectation:** eight tests verify the live app listens on Reactor Netty, plus JSON/async/error APIs, NDJSON, SSE cancellation, and session continuity. These tests never call `WebTestClient.bindToController`, so they send real HTTP requests to the Boot-assigned random port.

**Deliberate notes:**
- `@AutoConfigureWebTestClient` with `RANDOM_PORT` auto-binds the client to the real embedded server.
- `StepVerifier.verify(Duration)` and Awaitility `atMost` prevent tests from hanging if a stream breaks.
- `thenCancel` on a live HTTP client's response body triggers network stream cancellation, corroborated by the server probe. Cancellation delivery is asynchronous and sensitive to TCP/proxy/version timing—if flaky, inspect transport and probe rather than demanding instantaneous cancellation.
- `WebSession` is a different contract from `HttpSession`; the two demo projects do not claim session cookies or serialized attributes are cross-compatible across stacks.
- When running on a server other than Reactor Netty, update the expected server identity or split into a matrix; **never delete the server-identity test** just to force the suite green.

Run:

```bash
gradle test
```

This suite provides complete runnable code for basic HTTP + streaming. TLS, HTTP/2, and ingress are excluded here since they require separate infra/certs; those tests are detailed in later sections.

## 11. Switching the WebFlux Server Off Reactor Netty: Do Not Confuse with Changing Stack

A WebFlux app can run on another supported server adapter for that Spring Boot version. For instance, Spring Boot 3.3 docs show replacing default Reactor Netty with Undertow in Gradle via module replacement:

```groovy
// Snippet from the Spring Boot 3.3 guide for WebFlux:
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-undertow'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    modules {
        module('org.springframework.boot:spring-boot-starter-reactor-netty') {
            replacedBy(
                'org.springframework.boot:spring-boot-starter-undertow',
                'Use Undertow instead of Reactor Netty')
        }
    }
}
```

**Snippet**, not a complete build file; integrate it into your Gradle project using the right DSL. Reactor Netty may remain needed as the **`WebClient` HTTP connector** in some setups even when the server doesn't run Reactor Netty. Keeping Netty on the client classpath does not reveal which server runs inbound HTTP. Verify using the **runtime web server class** and live HTTP, not `dependencyInsight` alone.

When replacing Netty with Tomcat/Jetty/Undertow:
- Spring WebFlux remains `DispatcherHandler`.
- WebFlux `WebFilter`/`ServerWebExchange` APIs remain on the reactive stack.
- HTTP framing/parsing, WebSockets, HTTP/2, compression, limits, and runtime resources can change.
- You may need to adjust HTTP client connector dependencies for `WebTestClient`; don't settle for a green build if the HTTP client cannot connect.
- Re-run the full streaming/cancellation suite on the target server and test transports under load.

**Do not assume the app switched to the Servlet stack just because Tomcat is on the classpath.** WebFlux running on a Servlet-based reactive adapter is still the reactive framework; MVC + Tomcat is a Servlet MVC app.

## 12. Multipart Differences Across Servlet Containers and WebFlux

### 12.1. Keeping MVC, Swapping Tomcat → Jetty/Undertow

In Spring MVC, `MultipartFile` is created after the Servlet multipart parser processes the request. Common configuration:

```properties
spring.servlet.multipart.max-file-size=64KB
spring.servlet.multipart.max-request-size=128KB
spring.servlet.multipart.file-size-threshold=0B
```

Still test over **HTTP multipart wire format**:
- Single file under cap → 200.
- Single file over cap → rejected; may yield 413, 400, or connection reset depending on parser/swallow/error dispatch.
- Total request with multiple files + part headers exceeding cap.
- Many form parts, long filenames, malformed `Content-Disposition`.
- Multipart temp disk cleanup on request failure or client abort.

`MockMultipartFile` is merely a test object and does not force Tomcat/Jetty/Undertow to parse real bytes. In section 7's MVC code, `multipartBody(...)` builds real boundaries and part headers to exercise the container path.

**Do not confuse `server.tomcat.max-swallow-size` with max upload size.** Swallow size limits how many bytes Tomcat reads and discards after rejecting an upload, not valid file sizes. Jetty/Undertow use different parser settings; do not copy `server.tomcat.*` expecting them to apply.

### 12.2. MVC → WebFlux

WebFlux binds `FilePart`/`Part` or `Flux<PartEvent>` rather than the Servlet `MultipartResolver`. Properties:

```properties
spring.webflux.multipart.max-in-memory-size=16KB
spring.webflux.multipart.max-disk-usage-per-part=128KB
spring.webflux.multipart.max-parts=4
spring.webflux.multipart.max-headers-size=2KB
spring.codec.max-in-memory-size=64KB
```

Meaning:
- `spring.codec.max-in-memory-size` limits **decoder aggregation** for codecs/readers honoring it, **not total request body size**.
- WebFlux `max-in-memory-size` caps non-file form parts and sets the threshold for spooling file parts to disk.
- `max-disk-usage-per-part` caps disk space per individual file part when spooled.
- `max-parts` caps part count to prevent parser overhead from many tiny parts.
- `max-headers-size` limits headers **within each multipart part**, not socket-level HTTP headers.
- `Flux<PartEvent>` streaming has its own ownership/`DataBuffer`/total-byte quotas; do not assume non-streaming spool limits guard custom streaming code.

When migrating an upload endpoint from MVC to WebFlux, write **new server integration tests** covering file sizes, temp disk usage, and success/error/cancel paths instead of just swapping `MultipartFile` imports for `FilePart`.

## 13. HTTP Header, URI, Form, and Codec Limits: Test the Real Parser

Changing embedded servers can allow a small request while rejecting requests with large cookies/headers inside the HTTP parser.

Spring Boot 3.3 common property:

```properties
server.max-http-request-header-size=8KB
```

Per Boot 3.3 docs, Tomcat applies the limit to the **combined request line + headers**, whereas Netty applies semantics per header. Jetty/Undertow also have distinct implementations and decoder configs. Thus the same `8KB` does not guarantee identical behavior.

Tests to run:
- Single `X-Test` header long yet below cap.
- Multiple headers whose total exceeds cap.
- Large cookies and `Authorization` headers.
- Long queries / initial request lines.
- Method / `Transfer-Encoding` edge cases.
- With and without a proxy in front of the app.

**Do not demand HTTP 431 exclusively.** Oversized request headers can produce 400, 431, or connection reset depending on server/layer; enforce a **consistent product rule at ingress** if clients require one standardized error response.

**Do not raise limits globally to mask bloated cookies.** Large header buffers multiplied across concurrent connections inflate memory and DoS exposure. Fix token serialization, forwarded headers, CORS/security, and route design first.

### 13.1. `Content-Length` Is Not Enough

HTTP request bodies can use chunked transfers or HTTP/2 proxy framing. `Content-Length` may be absent, and compression alters decoded size vs. wire size.

To enforce real raw body limits:
- Enforce limits at ingress/proxy.
- In MVC routes, read `ServletInputStream` with a byte quota.
- In WebFlux routes, consume `Flux<DataBuffer>` with a byte counter or bounded join.
- Use multipart parser quotas for uploads.
- Bound max in-flight bytes, concurrency, and disk usage.

**Do not assume `spring.servlet.multipart.max-request-size` guards JSON bodies.** **Do not assume `spring.codec.max-in-memory-size` guards total streamed bodies.** Both misconceptions surface only when sending real payloads through a live server.

## 14. Async & Streaming: Races Exposed by Server Changes

### 14.1. Servlet Async Does Not Finish When Controller Returns `Callable`

```java
@GetMapping("/async")
Callable<String> async() {
    return () -> {
        Thread.sleep(100);
        return "ready";
    };
}
```

In `MockMvc`, testing requires `request().asyncStarted()`, `request().asyncResult(...)`, and `asyncDispatch(...)`. Yet verifying real Servlet async requests/connections requires a **live HTTP client hitting `RANDOM_PORT`**, like `/api/async` in the MVC project.

Server-migration bugs can occur after the controller returns, during async dispatch, or on response flush. Calling `Callable.call()` directly in a unit test never exercises the web runtime.

### 14.2. Never Equate NDJSON/SSE `onNext` with "One TCP Packet"

HTTP servers and proxies can:
- Buffer bytes and flush at thresholds.
- Coalesce multiple records into one network write.
- Compress bodies, altering emission timing.
- Split HTTP/2 `DATA` frames independently of Java item boundaries.
- Pause writes when clients read slowly or stop reading.

Therefore tests should parse **records/events**, never asserting TCP segment counts or exact per-write timing. For SSE, parse `data`/`id` per protocol; for NDJSON, parse each line as a JSON object.

### 14.3. Real Client Aborts Differ from Local `StepVerifier.thenCancel`

```java
// Local unit test: NO HTTP connection.
StepVerifier.create(Flux.interval(Duration.ofMillis(20)))
        .expectNextCount(2)
        .thenCancel()
        .verify(Duration.ofSeconds(5));
```

```java
// Network integration test: getResponseBody() comes from a live WebTestClient.
FluxExchangeResult<String> result = liveClient.get()
        .uri("/api/events")
        .exchange()
        .expectStatus().isOk()
        .returnResult(String.class);

StepVerifier.create(result.getResponseBody())
        .expectNext("tick-0", "tick-1")
        .thenCancel()
        .verify(Duration.ofSeconds(5));
```

In the second example, `liveClient` must be bound to a **live running server**, via `@AutoConfigureWebTestClient` + `RANDOM_PORT` or `WebTestClient.bindToServer().baseUrl(...)`. Combine a server probe with bounded `await` to verify the server received cancellation. If reactive code called `subscribe()` detached from the request, it keeps running after client cancel—tests must catch this leak.

### 14.4. When a Client Disconnects Mid-Upload/Download

Check:
- `DataBuffer` resources are released on error/cancel with no double-release.
- Spring MVC `StreamingResponseBody`/`SseEmitter` clean up via `finally`, `onCompletion`, `onTimeout`, and `onError`.
- Staging/temp files are deleted on complete/error/cancel, plus orphan cleanup after JVM crashes.
- If a 200 response already committed, do not expect a JSON 500 after a mid-stream error.
- If a client aborts after the server commits DB/payment work, cancellation **does not roll back the commit**; retries require idempotency/reconciliation.
- Do not assert a single literal `Broken pipe` exception: Tomcat/Jetty/Netty/OSes vary.

## 15. TLS/SSL Bundles and HTTP/2: Verify with Real Handshakes

Mock `MockMvc`/`WebTestClient` performs no TLS handshake. After swapping servers or upgrading Boot, run live network checks for TLS and HTTP/2 if your product uses them.

In Spring Boot 3.3, configure **SSL bundles** (PEM or JKS/PKCS12) and reference them on the server:

```properties
# Example snippet for a pre-generated PKCS12 config:
spring.ssl.bundle.jks.local-server.keystore.location=classpath:local-server.p12
spring.ssl.bundle.jks.local-server.keystore.password=changeit
spring.ssl.bundle.jks.local-server.keystore.type=PKCS12

server.ssl.bundle=local-server
server.port=8443
server.http2.enabled=true
```

**This is a snippet**, working only when `local-server.p12` holds a matching private key/certificate. Production uses restricted-access secret managers/mounts and valid CA chains; never hardcode `changeit` as a production secret.

Generate a lab-only certificate locally:

```bash
keytool -genkeypair \
  -alias localhost \
  -storetype PKCS12 \
  -keystore local-server.p12 \
  -storepass changeit \
  -keypass changeit \
  -keyalg RSA -keysize 2048 \
  -validity 3 \
  -dname "CN=localhost" \
  -ext "SAN=dns:localhost,ip:127.0.0.1"

keytool -exportcert -rfc \
  -alias localhost \
  -keystore local-server.p12 \
  -storepass changeit \
  -file local-server.crt
```

In the sample project, place `local-server.p12` in `src/main/resources` **for the lab only**, or configure a secure filesystem path. Never commit private keys to shared repositories. Use valid CA-issued certs/trust chains in production.

Verify:

```bash
curl -v --cacert local-server.crt \
  https://localhost:8443/api/hello?name=Test

curl -v --http2 --cacert local-server.crt \
  https://localhost:8443/api/hello?name=Test
```

`curl --http2` requires a curl build supporting HTTP/2, negotiated via ALPN over TLS. If client and server disagree on ALPN or a server adapter requires extra HTTP/2 dependencies/config, requests silently fall back to HTTP/1.1; **never treat "`curl` returned 200" as proof of HTTP/2**. Inspect `ALPN` and negotiated HTTP version in verbose output, or check `HttpResponse.version()` in JDK `HttpClient`.

Testing JDK `HttpClient` with a proper truststore:

```java
// Snippet in a network integration test; do not use trust-all SSL.
KeyStore trustStore = KeyStore.getInstance("PKCS12");
try (InputStream input =
        Files.newInputStream(Path.of("local-truststore.p12"))) {
    trustStore.load(input, "changeit".toCharArray());
}
TrustManagerFactory tmf = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
tmf.init(trustStore);

SSLContext sslContext = SSLContext.getInstance("TLS");
sslContext.init(null, tmf.getTrustManagers(), null);

HttpClient client = HttpClient.newBuilder()
        .sslContext(sslContext)
        .version(HttpClient.Version.HTTP_2)
        .build();

HttpResponse<String> response = client.send(
        HttpRequest.newBuilder(
                URI.create("https://localhost:8443/api/hello?name=Test"))
                .GET().build(),
        HttpResponse.BodyHandlers.ofString());

assertEquals(HttpClient.Version.HTTP_2, response.version());
```

Required imports include `java.security.KeyStore`, `java.nio.file.Files`/`Path`, `javax.net.ssl.TrustManagerFactory`/`SSLContext`, `java.net.URI`, `java.net.http.*`, and `org.junit.jupiter.api.Assertions.assertEquals`. This **test snippet** requires a truststore with the trusted cert/CA and a server supporting h2; it will not run as-is without `local-truststore.p12`. Never use `curl -k` or disable hostname verification just to make TLS tests pass.

**Each server has its own HTTP/2 nuances** (ALPN, native support, optional dependencies); consult the actual Boot 3.3 and server docs. When TLS terminates at ingress, the app may only see HTTP/1.1 from the proxy: verify protocols on the **exact hop** requiring HTTP/2 rather than confusing client→ingress with ingress→application.

## 16. Proxies/Ingress Can Mask Backend Server Differences

```text
External client
      │  TLS + HTTP/2
      ▼
CDN / API Gateway / NGINX
      │  May buffer, rewrite, limit, compress
      ▼
Spring Boot server
      │  HTTP/1.1 or HTTP/2 depending on topology
      ▼
Controller / downstream
```

Issues:
- Proxy returns 413 for body size before Boot receives the request.
- Proxy rejects oversized headers or long URIs before the embedded server.
- Proxy buffering prevents SSE events from reaching browsers incrementally.
- Misconfigured `X-Forwarded-For`/`Forwarded` and `X-Forwarded-Proto` cause HTTP redirects, dropped `Secure` cookies, or redirect loops.
- NGINX/Ingress holds stale connections during rollouts or times out earlier than the server.
- CORS preflight handled by the gateway means requests never reach the controller.
- HTTP/2 may apply only client→proxy, not proxy→Boot.
- Compression/gzip changes wire byte counts vs. decoded bodies.

**Keep at least three test tiers:**
1. Local `RANDOM_PORT`: bypasses proxy, targets embedded server directly.
2. Staging ingress: real routing, TLS, header/body limits, compression, and HTTP protocol.
3. Production canary: monitors 4xx/5xx, latency, cancellations, memory, and client-side errors during rollout.

Not every staging failure is a Java controller bug. Use safe correlation request IDs, proxy access logs, and server observations to locate the **first rejecting layer**. Never put `Authorization` tokens, raw `Cookie`s, session IDs, or PII into test logs or metric tags.

## 17. Authentication, Sessions, and Security When Changing Stacks

An HTTP contract suite consisting solely of anonymous GETs misses critical bugs:
- MVC `SecurityFilterChain` is not equivalent to WebFlux `SecurityWebFilterChain`.
- `JSESSIONID` cookies and reactive `WebSession`/Spring Session may not share names, configs, or serializers.
- Cookie `Secure`/`SameSite`/`HttpOnly`/`Domain`/`Path` can shift when TLS termination changes.
- CSRF protection on state-changing requests can break if security filters are dropped or altered.
- Authentication principals/session attributes may fail to deserialize after schema/serializer upgrades.
- Redirects to login or OAuth callbacks compute wrong schemes/hosts if forwarded headers break.
- CORS policies and credentials differ across proxies, MVC, and WebFlux.

Mandatory tests using a **client with a real cookie jar**:
1. Log in as a test user (never production credentials).
2. Retain `Set-Cookie`; send an authenticated request to a protected endpoint.
3. POST with a valid CSRF token and test missing token → expected 403 per policy.
4. Logout/invalidate; verify the old cookie loses access.
5. Canary / mixed versions: session created on V1, read by V2, and reverted to V1 if product contract requires it.
6. Rollback after V2 writes a session: rolling back only the container image leaves V2 session bytes in Redis/JDBC.
7. Verify TLS/`SameSite`/`Domain` when cross-site frontends rely on cookies.

**Never treat the local `/api/session` demo as sufficient for Spring Security.** It checks session continuity only within **one** embedded server. Real integrations must test login, roles, CSRF, and Spring Session under production-like auth configs across releases.

## 18. Threading, Resource Leaks, and Performance After Server Migration

Changing containers changes:
- Servlet worker thread pools and acceptor configurations.
- Reactor Netty event loops and `ByteBuf` direct memory.
- Request/body parsing, async continuations, and timeouts.
- Connection pools, keep-alive, and HTTP/2 concurrency.
- TLS handshakes and SSL engines.
- Backpressure and stream buffering behavior.
- Error dispatch and probe metric names.

Never benchmark performance with a single localhost HTTP request; proper benchmarks require warm-up, realistic traffic concurrency, payload distributions, GC/heap/direct memory, CPU, jitter, and production-like proxy paths.

**Key MVC ↔ WebFlux differences:**
- MVC can run blocking JDBC/`RestClient` on request threads, and `Callable`/`StreamingResponseBody` need bounded executors.
- WebFlux event loops must never run blocking `Thread.sleep`/JDBC directly; use non-blocking APIs or offload to `boundedElastic` while dependencies remain un-migrated.
- `Flux<DataBuffer>` can carry pooled buffers; whoever consumes must release properly. Retaining buffers across cancellations needs explicit lifecycle handling.
- Changing web stack and DB client/ORM/HTTP client simultaneously makes regressions hard to isolate; roll out in smaller steps where possible.
- Never assume HTTP graceful shutdown waits for detached `@Async` tasks. Background jobs need explicit executor shutdown policies or durable brokers.

Post-upgrade, monitor:
- HTTP p50/p95/p99 and in-flight request counts.
- Thread pool active/queued/rejected counts.
- JVM heap, direct memory, buffer leak warnings, and GC pauses.
- Per-route 4xx/5xx, request parser rejections, and error dispatches.
- Stream cancellations/completions and active connections.
- Timeouts, retries, and outbound HTTP client errors.
- Multipart temp disk usage and orphan files.
- Graceful shutdown `SIGTERM`→exit duration and in-flight request draining.
- HTTP/2 stream resets, TLS handshake errors, and proxy 499/502/503s.

## 19. Dependency and Auto-Configuration Regressions

Upgrading Spring Boot or switching embedded servers can introduce silent changes in transitive dependencies and auto-configuration:
- `javax.servlet.*` changed to `jakarta.servlet.*` in Boot 2→3; legacy classes fail to compile on Boot 3.
- Spring Boot 3.3 requires Java 17+; dependency bytecode must be compatible.
- Tomcat/Jetty/Undertow Servlet API levels and web-server factories can collide if a library pulls another version.
- Adding `spring-boot-starter-webflux` solely for `WebClient` normally keeps MVC, as noted in section 2.
- A custom `WebServerFactoryCustomizer` or `WebMvcConfigurer` bean can alter routing/headers; starters aren't the only factor.
- `@EnableWebMvc` or `@EnableWebFlux` can disable default Boot auto-configurations; review full configuration diffs.
- Micrometer/Actuator observation instrumentation and HTTP server tags can change across versions; verify metrics contracts.
- Jackson modules/codecs can alter JSON date/enum/null formatting, so maintain golden response schemas.
- Spring Security upgrades can change request matchers, filter chains, or session serialization.

Gradle inspection commands:

```bash
gradle dependencies --configuration runtimeClasspath

gradle dependencyInsight \
  --configuration runtimeClasspath \
  --dependency spring-boot-starter-tomcat

gradle dependencyInsight \
  --configuration runtimeClasspath \
  --dependency spring-boot-starter-webflux
```

Archive the dependency graph and image digest as CI artifacts; if a test thinks it runs Jetty while runtime actually runs Tomcat, block the merge. When running cross-version tests, avoid sharing stale Gradle caches/configs that skip re-resolving dependencies across targets.

## 20. Running a CI Matrix and Choosing Test Gates

A sound web-runtime upgrade pipeline:

```text
Commit / Pull Request
   │
   ├── javac + static analysis + unit tests
   ├── MVC mock/controller-slice tests
   ├── MVC RANDOM_PORT Tomcat contract suite
   ├── MVC RANDOM_PORT Jetty contract suite
   ├── MVC RANDOM_PORT Undertow contract suite
   └── WebFlux RANDOM_PORT Netty contract suite
                 │
                 ▼
          Artifact/Image build
                 │
                 ▼
       Staging HTTPS/HTTP2/Ingress
           ├── auth/session/CSRF
           ├── multipart limits
           ├── SSE/NDJSON/disconnect
           ├── header/URI parser
           └── graceful/timeout/load
                 │
                 ▼
          Canary rollout with SLIs
                 │
          PASS ───┴─── FAIL
           │            │
        Promote      Halt/rollback
```

**Not every project needs all four servers in production.** If migrating only Tomcat→Jetty, CI can test baseline Tomcat + candidate Jetty. If both remain active during rollout, both must satisfy the **exact same external contract**. Avoid building a bloated matrix that skips critical request paths.

### 20.1. GitHub Actions (Complete Workspace Idea)

```yaml
name: mvc-server-matrix
on:
  pull_request:
  workflow_dispatch:

jobs:
  live-contract:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        server: [tomcat, jetty, undertow]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
      - uses: gradle/actions/setup-gradle@v4
      - name: Run HTTP server contract
        run: gradle clean test -PserverEngine=${{ matrix.server }}
```

**Placeholder note:** in a real workflow, the expression on the `run` line must be `-PserverEngine=` followed by GitHub Actions syntax `${{{ matrix.server }}`. If using JS/template rendering to generate Markdown, preserve `${{{ matrix.server }}` as `$` + `{{ matrix.server }}` (two opening braces). Use this corrected template when copying:

```yaml
      - name: Run HTTP server contract
        run: gradle clean test -PserverEngine=${{{ matrix.server }}
```

Keep **only one** `Run HTTP server contract` step in the finished workflow; the first block shows the full skeleton and the second shows the corrected GitHub expression line. The WebFlux project runs a similar workflow with `gradle test`.

**CI practice:** save JUnit XML reports, build logs, and runtime server identity. When tests fail, keep captured requests/responses free of **secrets or PII**, and preserve staging container/proxy logs. A failure occurring only on Undertow is still a real regression even if the other servers pass.

## 21. Critical Tests Omitted from the Demo That Real Projects Need

The illustrative project cannot cover every business contract; real migrations should add targeted tests:

**1. Redirects, `Location`, and proxy proto:** external HTTPS requests through a proxy must emit `Location: https://...` without HTTP redirect loops. Test trusted-forwarded-header config, and never trust forged forwarded headers sent directly by clients.

**2. Multipart and async upload timeouts:** valid boundary uploads, oversized files, mid-body client aborts, and temp file cleanup. Test with `HttpClient`, `curl --data-binary`, or streaming clients—not only `MockMultipartFile`.

**3. Authentication/CSRF/SameSite:** use a browser or HTTP client with a cookie jar across login, logout, and protected POSTs; when switching security stacks, confirm role authorization does not regress.

**4. Validation errors:** `@Valid` requires the Bean Validation starter/config; test invalid JSON/schemas and 400/422/415. Without `starter-validation` on Boot 3, do not assume `@NotBlank` is enforced automatically.

**5. Errors after response commit:** stream returns 200, flushes event 1, then producer errors; verify the client sees the prefix + termination/error and resources clean up, rather than asserting HTTP 500.

**6. Chunked uploads / large bodies:** verify `Transfer-Encoding: chunked`, absent `Content-Length`, backpressure, and byte counting—never confusing codec caps with wire body caps.

**7. CORS and `OPTIONS`:** valid preflight allowed, wrong origin rejected, header/credential policies, and gateway differences.

**8. HTTP methods / encoded URIs:** `DELETE`/`PUT`/`PATCH`/`HEAD`/`OPTIONS`, path variables with UTF-8/reserved chars, trailing slashes, and matrix params if used. Avoid relaxing path matching blindly to pass tests if it opens path traversal.

**9. WebSockets/SSE:** connect, send/receive multiple frames/events, pings/heartbeats, client disconnect, session close, and reconnect cursors; watch TCP fragmentation/cancellation differences.

**10. Resource exhaustion:** slow clients, long-held connections, chunked uploads, multipart temp disk, active thread pools, and direct memory. Use dedicated load tests—never send DoS load at unauthorized targets.

**11. Graceful shutdown:** `SIGTERM` while HTTP/SSE requests are active, readiness→drain, bounded exit, server connection resets, and job durability; never rely solely on `context.close()` in unit tests.

**12. Observability:** live `http.server.requests` status/outcome/error/tags; a handled 500 may record `error=none` if advice catches it without calling `setError`, so never rely solely on the error tag for availability SLOs.

## 22. "Golden Contracts" and Diffing Baseline vs. Candidate

When comparing Tomcat V1 vs. Jetty V2 or MVC vs. WebFlux, never diff raw HTTP response bytes directly and flag every byte difference as a regression:

| Field | How to compare |
|---|---|
| HTTP status | Exact when contracted |
| JSON response | Parse JSON, compare fields/types/semantics, ignore object key order |
| `Content-Type` | Compare media type/charset contract; avoid hardcoding parameter order |
| Response headers | Documented headers only; ignore dynamic `Date`/`Server` unless contracted |
| Cookies | `Name`, `Path`, `Domain`, `Secure`, `HttpOnly`, `SameSite`, expiry; ignore random session IDs |
| Error response | Status + stable error code / `ProblemDetail` fields, no stack traces |
| Streaming | Event/data order + completion/cancel, not network packet count |
| Multipart | Accept/reject policy and file integrity, not parser HTML error bodies |
| HTTP/2/TLS | Negotiated protocol, trust chain, hostname, ALPN, header preservation |
| Timing | SLO/p99 and upper bounds with margin, never exact milliseconds |
| Availability | Error ratio across client/proxy/server, not just server-completed 5xx |

**Golden fixtures** should capture request method/URI, sanitized headers/body, and expected status/JSON schema/cookies/traces; never store real session cookies, bearer tokens, database IDs, or PII in test snapshots.

Upgrading Spring Boot can alter default error JSON shapes even when uncontracted. If clients already parse default error bodies, treat that as a **de facto contract** to detect and stabilize via a custom error mapper before upgrading.

**Maintain at least two test classes:**
- *Compatibility tests* asserting what must stay unchanged.
- *Intentional-change tests* verifying product-approved new behaviors, paired with client migration docs.

## 23. Troubleshooting When Changing Web Runtime

| Symptom | Typical cause | How to verify |
|---|---|---|
| Test claims "Jetty" yet logs show Tomcat | Transitive Tomcat starter remains | Assert actual server class + `dependencyInsight` |
| Added WebFlux yet app stays MVC | Both starters on classpath | Inspect `ServletWebServerApplicationContext`/`DispatcherServlet` |
| Unit/`MockMvc` green, production 500 | Container error dispatch/multipart/parser differs | `RANDOM_PORT` + logs from live server |
| HTTP 404 returns different HTML/JSON | Server error pipeline / content negotiation | Assert status + custom problem contract |
| Multipart upload fails on Jetty | Parser limits/temp/part headers differ | Real boundary upload over HTTP |
| 500 without hitting app handler | Parser/container/proxy rejected early | Request logs, gateway logs, server traces |
| Lost session after stack switch | Cookie name/serializer/store/`SecurityContext` differs | Cookie jar, shared store, cross-instance test |
| UTF-8 query produces different result | URL encoding/URI parsing/forwarded config | Percent-encoded requests and JSON responses |
| CORS preflight passes locally yet fails in staging | Proxy/auth CORS handling | `OPTIONS` through ingress with real headers |
| SSE arrives batched as one response | Container/proxy buffering/compression | `curl -N` and live `WebTestClient` |
| SSE cancel doesn't trigger immediate cleanup | Async OS/connector signal or detached task | Bounded Awaitility + server probe |
| Netty memory climbs after stream abort | `DataBuffer` leak or broken cancel cleanup | Leak detection / direct memory metrics |
| 8KB header works on Tomcat yet differs on Netty | Header limit semantics differ | Per-server parser boundary tests |
| Large WebFlux JSON hits codec error | `max-in-memory-size` decoder aggregation | Test exact payload/data codec |
| Servlet `@Async` test misbehaves | Mock async dispatch vs. detached job | Measure response lifecycle over real HTTP |
| HTTP/2 negotiates down to HTTP/1.1 | ALPN/curl/server TLS HTTP/2 config | Inspect negotiated protocol / cert chain |
| Redirect drops HTTPS | Forwarded headers / proxy trust config | Request via ingress, check `Location` + `Secure` cookie |
| Client times out while server returns 200 | Client/proxy timeout shorter than server | Correlation IDs and multi-hop logs |
| Rolled-back image still fails on sessions | V2 session format remains in Redis | Cross-version session reader/writer tests |
| Context test collides on port 8080 | Used `DEFINED_PORT`/hardcoded port | `RANDOM_PORT` + `@LocalServerPort` |
| Test uses `@Transactional` yet DB retains row | Server transaction ran on separate thread | Explicit cleanup or DB isolation in integration tests |
| Flaky test from fixed sleeps | Non-deterministic network/scheduler timing | Latches + bounded eventual assertions |
| Negative or leaking active probe count | Multiple cleanups / multiple subscribes | Separate per-request state, idempotent cleanup |
| HTTP 200 yet client gets truncated body | Disconnect after headers/partial flush | Stream checksums / record counts / retry semantics |

## 24. Pre-Promotion Checklist

- [ ] Verified actual **web stack** and **embedded server**, not guessed from starter names.
- [ ] When swapping servers, excluded old default starter and added proper replacement.
- [ ] When moving MVC→WebFlux, removed Servlet-only filters/APIs and audited blocking calls.
- [ ] Ran the exact same HTTP contract test suite against baseline and candidate.
- [ ] Tested `@SpringBootTest(RANDOM_PORT)` with JDK `HttpClient` or live `WebTestClient`.
- [ ] Asserted actual server class rather than fragile log formatting.
- [ ] Tested UTF-8 queries, JSON bodies, statuses 200/404/422/500, and content negotiation.
- [ ] Tested CORS preflights, redirects, and trusted forwarded headers.
- [ ] Tested session cookie continuity and auth/CSRF where applicable.
- [ ] Tested real multipart wire bytes, part headers, and file/request size limits.
- [ ] Tested Servlet async `Callable`/`DeferredResult` and reactive `Mono`/`Flux` appropriately.
- [ ] Tested finite NDJSON/SSE, early disconnects, cancellation, and cleanup.
- [ ] Tested mid-stream errors after response commit without expecting a fresh 500.
- [ ] Tested HTTP header/URI limits against real servers and proxies.
- [ ] Tested TLS trust/hostnames and negotiated HTTP/2 versions if required.
- [ ] Tested latency/resource usage under concurrent load, temp disk, and direct memory.
- [ ] Tested graceful `SIGTERM`, readiness/ingress drain, and rollback.
- [ ] Did not assume test `@Transactional` rolls back HTTP server-side DB writes.
- [ ] Ran schema/auth/session compatibility tests across mixed versions.
- [ ] Inspected gateway and server logs/metrics since requests can fail before controllers.
- [ ] Kept secrets/PII out of test snapshots, curl logs, and metric tags.
- [ ] Kept rollback targets compatible with persisted data/sessions, not just container images.

## 25. Self-Check Questions

**1. Does replacing Tomcat with Jetty turn Spring MVC into WebFlux?**  
No. That only swaps the embedded Servlet container; MVC still uses `DispatcherServlet`.

**2. Does adding `spring-boot-starter-webflux` to an MVC app automatically launch Reactor Netty?**  
Not by default in Boot 3.3: MVC takes precedence when both starters exist. The WebFlux starter may simply supply `WebClient`.

**3. If `MockMvc` already tests 500 from a controller exception, why add a live server test?**  
Because Servlet container error-page dispatch/`BasicErrorController`, parsers/headers/cookies, and network behaviors are not fully simulated by `MockMvc`.

**4. Why isn't `@SpringBootTest` without `RANDOM_PORT` enough for socket tests?**  
It defaults to `MOCK` environment; `RANDOM_PORT` boots a real embedded server and injects the port via `@LocalServerPort`.

**5. Should you assert the exact server class?**  
Yes—assert or log the runtime web server identity when server migration is the goal, catching accidental classpath retention of old Tomcat/Netty.

**6. If two servers return JSON properties in different order, is it a regression?**  
Not necessarily. Unless key order is contracted, parse JSON and compare schema/values instead of raw bytes.

**7. Why might a 100KB mock multipart upload pass while the real server rejects it?**  
`MockMultipartFile` skips the Servlet parser, container file/request size limits, and header/boundary rules.

**8. Why does an 8KB header limit behave differently between Tomcat and Reactor Netty?**  
HTTP parser and config semantics differ by server; Boot 3.3 documents Tomcat bounding combined request line + headers while Netty bounds individual headers.

**9. Can you test client abort locally with `StepVerifier` on a `Flux` and conclude sockets close cleanly?**  
No. Test the response body from a client connected to a live server, verifying server-side cancellation/cleanup via a bounded wait.

**10. Why shouldn't you assert 500 after SSE already flushed 200?**  
Headers/status are already committed; subsequent errors terminate the stream/connection rather than producing a new HTTP 500.

**11. What must a passing HTTP/2 test assert?**  
That HTTP/2 was actually negotiated alongside TLS/ALPN/trust/hostname—not just HTTP 200 or passing `curl --http2`.

**12. If a `@Transactional` test calls a `RANDOM_PORT` endpoint, do server DB writes roll back?**  
No. The server runs in its own thread and transaction; use explicit cleanup or DB isolation in integration tests.

**13. Why might CORS pass on localhost yet fail through ingress?**  
The gateway may intercept `OPTIONS` or alter `Origin`/headers/security/filter chains; test the actual network hop.

**14. Does sticky load balancing fix V1/V2 session incompatibility?**  
No. Pod restarts/rollbacks and shared serialized session data still require dual-reader/schema compatibility.

**15. In the stream demo where the client closes early and `probe.finished` increments, does that prove an `IOException` occurred?**  
No. It only proves the callback eventually finished; because the stream is finite, the server may have completed naturally. Proving transport abort requires connector-side evidence.

## 26. Official Reference Sources

1. Spring Boot **3.3 Embedded Web Servers** — swapping Tomcat for Jetty/Undertow, swapping Reactor Netty for another reactive server; Gradle/Maven dependency practices. https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
2. Spring Boot **3.3 Testing Spring Boot Applications** — `MOCK`/`RANDOM_PORT`, `@LocalServerPort`, `WebTestClient`, and `@Transactional` limits across server threads. https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
3. Spring Boot **3.3 Reactive Web Applications** — choosing MVC vs. WebFlux when both starters coexist, Reactor Netty defaults. https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
4. Spring Boot **3.3 Servlet Web Applications** — Spring MVC, multipart, embedded servers, and web filters. https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
5. Spring Boot **3.3 Common Application Properties** — HTTP headers, multipart, codecs, TLS, compression, async. https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
6. Spring Framework — **`WebTestClient`** (mock bind options, `bindToServer`, and `FluxExchangeResult` for streaming). https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
7. Spring Framework — **MockMvc Async Requests** (async dispatch) and why it is insufficient for containers. https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/async-requests.html
8. Spring Framework — **MVC Async Requests** (`Callable`, `DeferredResult`, `StreamingResponseBody`, `SseEmitter`). https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
9. Spring Framework — **WebFlux** (reactive pipeline, body codecs, backpressure, `WebSession`). https://docs.spring.io/spring-framework/reference/web/webflux.html
10. Spring Framework — **Data Buffers and Codecs**, pooled memory and release semantics. https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html
11. Spring Boot **3.3 Graceful Shutdown**, request draining and server-specific behaviors. https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
12. Spring Boot **3.3 SSL**, SSL bundles and server TLS. https://docs.spring.io/spring-boot/3.3/reference/features/ssl.html
13. Project Reactor — **`StepVerifier`** and virtual-time testing. https://projectreactor.io/docs/core/release/reference/testing.html
14. Apache Tomcat **10.1 HTTP Connector**, request headers, form post, swallow, and connector limits. https://tomcat.apache.org/tomcat-10.1-doc/config/http.html
15. RFC **9110 HTTP Semantics** (4xx/5xx, `Content-Type`, Content Negotiation) and RFC **9113 HTTP/2**. https://www.rfc-editor.org/rfc/rfc9110.html , https://www.rfc-editor.org/rfc/rfc9113.html

**Summary:** When changing the **web stack** or **embedded HTTP server**, green builds and mock tests are not enough to guarantee the HTTP contract holds. Run **the exact same live-server test suite** (Spring Boot `RANDOM_PORT`) before and after upgrades, verifying runtime server identity and every client-visible contract: statuses, headers, JSON, cookies, multipart, async, streaming, cancellation, error dispatch, TLS/HTTP/2, and ingress. When differences appear, classify them across framework, container, proxy, and business contract; decide whether to fix or accept changes before promoting, rather than letting customers discover them during a rolling deployment.
