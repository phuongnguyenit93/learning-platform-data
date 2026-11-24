# Handling Errors After the Response Is Sent or Streaming Has Begun

> **Parent topic:** Error responses in **Spring Security reactive / Spring WebFlux**. This lesson focuses on the **HTTP response committed** boundary, errors occurring while a `Mono`/`Flux` is already being written to the network, and how to coordinate HTTP error handling with authentication/authorization. Examples use **Java 17+, Spring Boot 3.x, Spring Framework 6.x, Spring Security 6.x, and Reactor**. The implementation code uses fake passwords only for test environments; real systems must use TLS and trusted authentication systems.

## 1. Objectives and Central Question

After this lesson, you can:

1. Distinguish **errors before the response is committed** from **errors after status/headers are committed**.
2. Understand what `ServerHttpResponse.isCommitted()`, `setStatusCode(...)`, and `beforeCommit(...)` can actually do.
3. Know why `@ExceptionHandler`, `WebExceptionHandler`, `ResponseStatusExceptionHandler`, or Spring Security handlers **cannot change an already-sent response** into 401/403/500.
4. Write a WebFlux API returning JSON errors when failure happens **before the body**.
5. Design **Server-Sent Events (SSE)** to emit errors at the **application protocol level** once initial events have already gone out.
6. Distinguish stream errors handled with `onErrorResume` from unhandled errors that terminate the stream/connection.
7. Test unauthenticated requests, errors mapped to 503 before commit, streams with an error event, and publishers emitting `onError`.
8. Prevent leaking sensitive content or unauthorized data in an already-started response; understand cancellation, timeouts, retries, logging, and proxy buffering.

**Upfront conclusion:** **HTTP status and headers can only be set before commit; after commit you cannot "turn 200 into 500".** With streaming, if you still control the publisher and the protocol permits it, you can **emit a structured error record/event inside the body**, or terminate the stream/connection. That is not a new HTTP error response.

## 2. What Does HTTP Response Committed Mean?

In WebFlux, a response moves through logical phases:

```text
Request received
    |
    v
Handler / Security determine status, headers, body publisher
    |
    v
Response not yet committed
    |
    +-- Error before commit?
    |       -> appropriate handler can choose 4xx/5xx and error body
    |
    v
Commit status + headers + cookies
    |
    v
Write body (one or more DataBuffers/chunks/events)
    |
    +-- Error after commit?
    |       -> CANNOT change already-committed status/headers
    |       -> app-level error event if protocol permits
    |       -> or terminate stream/connection, record logs/metrics
    |
    v
Complete or abnormal termination
```

`ServerHttpResponse` is provided by Spring Framework via `ServerWebExchange.getResponse()`. Once status/headers are committed:

- You cannot change an already-sent status from **200 OK** to **500 Internal Server Error**, **401 Unauthorized**, or **403 Forbidden** for the same response.
- You cannot send a new `Content-Type: application/problem+json` response header to turn an ongoing SSE/JSON body into error JSON.
- You cannot go back to erase bytes already sent to the client, recall data, or "take back" part of a streamed JSON array.
- `response.setStatusCode(HttpStatus.INTERNAL_SERVER_ERROR)` may return `false` because status is committed; code should respect that signal and **not assume** the status was changed.
- Calling `setComplete()` or another error writer does not create a **second HTTP response**.

**Distinguish commit from when the client actually sees data:** `isCommitted()` reflects state at the reactive framework/server side. Proxies, kernel socket buffers, and clients may keep buffering, so packet arrival times at the client may vary. For the application, however, **after commit there is no second chance to rewrite status/headers**, even if the client has not rendered data yet.

### 2.1 One Error Before Commit and One Error After Commit

**Before commit:**

```text
GET /api/report
  -> repository.findById(...) fails before producing body
  -> @ExceptionHandler / error handler chooses status 503
  -> HTTP/1.1 503 Service Unavailable
  -> Content-Type: application/problem+json
  -> JSON ProblemDetail
```

**After commit:**

```text
GET /stream/live
  -> status 200 and Content-Type: text/event-stream are committed
  -> first event passes through the response writer
  -> downstream publisher emits onError
  -> CANNOT switch status 200 to 500
  -> client sees stream abort abnormally or an app-error event
     (if the app proactively converted the error into an event)
```

Do not promise that every server closes TCP the same way or that every client sees HTTP 500. In streaming scenarios, outcomes depend on codecs, Netty/Jetty, HTTP/1.1 or HTTP/2, chunk buffering, networks, and reverse proxies.

## 3. ServerHttpResponse API and Practical Limits

| API | Purpose | Caution when response committed |
| --- | --- | --- |
| `response.isCommitted()` | Checks whether response is already committed | Status information, not a transaction lock |
| `response.setStatusCode(HttpStatusCode)` | Sets status before commit | Returns `false` if unchangeable due to commit |
| `response.getHeaders()` | Reads/sets headers | Do not expect adding/modifying headers after commit |
| `response.addCookie(...)` | Sends response cookie | May fail when response is already committed |
| `response.beforeCommit(Supplier<? extends Mono<Void>>)` | Registers work to run right **before** commit | Not a "fix error after commit" callback |
| `response.writeWith(...)` | Writes body from `DataBuffer` publisher | Errors after writing begins do not change status automatically |
| `response.writeAndFlushWith(...)` | Writes and flushes by publisher groups | Often used for streaming; does not guarantee recovery as a fresh response |
| `response.setComplete()` | Completes response without writing more body from that caller | Does not reset status or erase sent bytes |

Example **illustrative snippet inside a WebFilter/handler with `exchange`**:

```java
ServerHttpResponse response = exchange.getResponse();

if (!response.isCommitted()) {
    boolean changed = response.setStatusCode(
        HttpStatus.SERVICE_UNAVAILABLE
    );
    // changed only says whether the status was accepted at call time.
}
else {
    // Only log/metrics and handle publisher errors within scope.
    // Do not attempt to build a new HTTP error response here.
}
```

The snippet above requires imports `org.springframework.http.HttpStatus` and `org.springframework.http.server.reactive.ServerHttpResponse`. Checking `!isCommitted()` and then calling `setStatusCode` is **not an atomic transaction** across all async tasks; always respect the return value or let the framework manage error responses. In production, avoid having multiple WebFilters race to set status.

### 3.1 Proper Use of beforeCommit

`beforeCommit` is designed for work that must finish **before** the response commits: adding headers, correlation IDs, observability logic, or a short appropriate reactive step. Example:

```java
exchange.getResponse().beforeCommit(() ->
    Mono.fromRunnable(() ->
        log.debug("Response is about to commit")
    )
);
```

This is a **snippet**, requiring `exchange`, `log`, and Reactor `Mono` import. Never use this callback to run blocking I/O, `Thread.sleep`, or `block()`. **It does not run after commit to fix subsequent errors**, and if the callback itself fails, it can cause a commit failure.

### 3.2 Operations That Cannot "Fix" Late Errors

All of the following ideas are wrong once body bytes have started going out:

- Calling `response.setStatusCode(HttpStatus.INTERNAL_SERVER_ERROR)` and expecting the client to see 500.
- Building `ResponseEntity.status(500).body(problem)` inside an `onErrorResume` **outside an already-committed body writer**, expecting WebFlux to send a second HTTP response.
- Sending `WWW-Authenticate` after an SSE stream has started to "switch" the response to 401.
- Throwing `ResponseStatusException(HttpStatus.FORBIDDEN)` after the first event and thinking an exception handler can change status.
- Calling `response.getHeaders().set(...)` after commit without a pre-designed valid trailers mechanism; trailers do not replace HTTP status.
- Logging the exception and returning `Mono.empty()` in a global error handler without signaling to the client that the stream was truncated.
- Calling `subscribe()` manually to write an error message alongside the response owned by WebFlux, causing **two writers** to race on the same response.

## 4. WebFlux Exception Handling Chain

WebFlux has several error-handling mechanisms. Understand their boundaries:

| Mechanism | What it is for | Committed boundary |
| --- | --- | --- |
| `@ExceptionHandler` in `@RestControllerAdvice` | Maps handler exceptions to `ResponseEntity`/`ProblemDetail`/body | Can build response when error is caught **before commit** |
| `ResponseStatusException` | Attaches HTTP status to WebFlux-handled errors | Cannot rewrite an already-committed status |
| `WebExceptionHandler` | Handles exceptions traversing `WebFilter`/`WebHandler` | Can return a new response while still committable |
| `WebFluxResponseStatusExceptionHandler` | Handles `ResponseStatusException`, `@ResponseStatus` | **Javadoc explicitly states:** if response is committed, error stays unresolved and propagates |
| Spring Boot `ErrorWebExceptionHandler` | Renders global errors when possible | Cannot create new error body/status after commit |
| Reactor `onErrorResume` *inside stream publisher* | Converts error source into valid event/fallback before body writer sees `onError` | Can emit an **in-band event**, does not change HTTP status |
| `doOnError` / `doFinally` | Logs errors, metrics, signals/cancellation | Does not "swallow" errors and creates no HTTP response |
| `ServerAuthenticationEntryPoint` | Handles authentication challenges (e.g., Basic 401) | Must happen before response is sent |
| `ServerAccessDeniedHandler` | Handles access denials (usually 403) | Cannot change an already-committed 200 response |

A `@ControllerAdvice` usually fits **JSON errors before the server begins writing a body**. For errors happening after the first `Flux` event, do not automatically expect advice to run and send a clean JSON body. Spring Framework Javadoc for `WebFluxResponseStatusExceptionHandler` explicitly notes that if the response is committed, the exception remains unresolved and is propagated.

### 4.1 Where Does Spring Security Sit in These Errors?

Spring Security WebFlux uses `SecurityWebFilterChain` and WebFilters such as authentication/authorization, where `AccessDeniedException` handling invokes `ServerAuthenticationEntryPoint` or `ServerAccessDeniedHandler` depending on the principal and error type.

**Before writing body:** if a user has no credentials, a protected endpoint request can receive **401**; if authenticated yet lacking a role, it can receive **403**.

**After the body stream has started:** if a mid-stream step detects revoked permissions or a late method security check fires, the response may already be **200**; Spring Security cannot alter committed status/headers. That **does not mean you keep sending data**: **stop the stream**, send no more sensitive data, and emit an application-protocol error signal if permitted and safe.

**Crucial design lesson:** Perform authentication/authorization checks deciding **whether the stream may open** before emitting the first body chunk. If permissions can change during a long-lived stream, recheck permissions at appropriate checkpoints **before emitting the next event**, with an explicit stream-termination policy when permissions are revoked. Never emit data while awaiting permission checks.

## 5. Errors in Reactor: onNext, onError, and onComplete

A publisher follows the Reactive Streams contract:

```text
onSubscribe
    |
    +-- onNext(value1)
    +-- onNext(value2)
    +-- ...
    |
    +-- onComplete
    |
    or
    +-- onError(exception)
```

**`onError` is a terminal signal**. Once a publisher emits `onError`, it must not emit further `onNext` signals on that subscription. `onErrorResume` does not "make the failed publisher continue as if nothing happened"; it **switches to a fallback publisher** before the downstream subscriber receives the error, if placed in the right spot.

In a WebFlux HTTP response, the subscriber is the framework/codec/body writer. When the body publisher signals `onError`, the server must handle the failure while the response may already be committed. If already committed, it can no longer send a new status.

### 5.1 Catching Errors Before Reaching the Body Writer

```java
Flux<ServerSentEvent<String>> events = upstreamEvents
    .onErrorResume(DependencyUnavailableException.class, ex ->
        Flux.just(ServerSentEvent.<String>builder()
            .event("app-error")
            .data("DEPENDENCY_UNAVAILABLE")
            .build())
    );
```

This is a **snippet** assuming `upstreamEvents`, the exception class, and appropriate imports. It illustrates: the handler receives a **transformed event stream**, including an error-reporting event instead of an unhandled `onError`. When the error event follows earlier events, the HTTP status stays at the committed status (usually **200**).

**Warning:** An event named `app-error` is **not** `HTTP 500`, nor is it a JavaScript `EventSource.onerror` network failure. Clients must actively read `app-error` and handle it per the documented **contract**.

### 5.2 Catching Errors in the Wrong Place

```java
Flux<String> unsafe = source
    .map(this::serialize)
    .doOnError(log::warn);

// Later, at a layer outside response.writeWith(...):
// trying to change HTTP status when the log reports an error.
```

This is **illustrative pseudocode**, without pre-defined `source` / `serialize` / `log`. `doOnError` only observes the signal without recovering. If serialization or the data source fails **after commit**, setting status 500 at that point is too late.

Instead, define error boundaries early: domain errors inside the publisher can become **protocol-level events**; serialization/transport errors after bytes have gone out cannot be fully recovered via status, so log/metric and let the connection close properly.

### 5.3 onErrorResume Does Not Cure Every Error

An `onErrorResume(Throwable.class, ...)` catching every error and turning it into "success" can mask security exceptions, severe infrastructure failures, or leak wrong data. Handle only **known error types** that have a corresponding event protocol. Never turn `AccessDeniedException` into an "OK" event and keep streaming sensitive data.

In streaming apps with access control, classify:

- **Transient upstream error:** may emit `app-error` with a non-sensitive code and end the stream.
- **Revoked permissions:** stop sending data; optionally emit a minimal "access-revoked" event if protocol/authorization allow, then terminate.
- **Serialization/codec/transport bug:** normally cannot guarantee sending another valid event; let the publisher error, record the incident, and let the client reconnect per policy.
- **Client cancelled subscription:** do not try to emit more events, because the subscriber is no longer receiving data.

## 6. Hands-on: Two Error Types on One WebFlux Server

We will build an API with two response types:

1. **Normal JSON request**, error occurs before body is written → `@RestControllerAdvice` produces **503** with `ProblemDetail`.
2. **SSE stream**, after one data event the source emits an error. For the properly handled endpoint, we turn the error into an **`app-error` event** and complete; for the deliberately unhandled endpoint, the publisher emits `onError` and the server may terminate the stream abnormally.

HTTP Basic is enabled so Spring Security's 401 **before** the stream opens is clearly visible. Users and passwords are for localhost practice only.

### 6.1 Dependencies and Project Structure

Create a Spring Boot **3.x**, Java **17+**, Gradle Groovy project selecting Spring Reactive Web and Spring Security. The `dependencies` block of `build.gradle` with the Spring Boot plugin already configured:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Do not simultaneously add `spring-boot-starter-web` for the demo HTTP server. If both MVC and WebFlux are present, Spring Boot normally picks MVC by default; `SecurityWebFilterChain` belongs to the reactive HTTP stack, not Servlet `SecurityFilterChain`.

Create the files:

```text
src/main/java/com/example/streamfailures/
  StreamFailuresApplication.java
  SecurityConfig.java
  ErrorDemoController.java
  EarlyErrorAdvice.java
  ResponseAuditWebFilter.java
src/test/java/com/example/streamfailures/
  StreamErrorPublisherTest.java
  StreamErrorHttpTest.java
```

All classes live in package `com.example.streamfailures`. These are **separate Java files**—do not combine multiple `public class` definitions into one file. Gradle wrapper compiles them with dependencies; **do not run individual files with bare `javac`** missing Spring and Reactor.

### 6.2 StreamFailuresApplication.java

`src/main/java/com/example/streamfailures/StreamFailuresApplication.java`:

```java
package com.example.streamfailures;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StreamFailuresApplication {
    public static void main(String[] args) {
        SpringApplication.run(StreamFailuresApplication.class, args);
    }
}
```

### 6.3 SecurityConfig.java: Authentication/Authorization Before Streaming

`src/main/java/com/example/streamfailures/SecurityConfig.java`:

```java
package com.example.streamfailures;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public/**").permitAll()
                .pathMatchers("/api/**", "/stream/**").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        var user = User.withUsername("reader")
            .password(encoder.encode("reader-demo-password"))
            .roles("READER")
            .build();
        return new MapReactiveUserDetailsService(user);
    }
}
```

**Security explanation:**

- `/public/**` allows access without credentials; `/api/**` and `/stream/**` require valid authentication.
- The HTTP Basic filter verifies credentials **before** the controller creates an SSE publisher for protected routes. Therefore `GET /stream/handled` without a Basic header returns **401** without leaking event data.
- `MapReactiveUserDetailsService` and the demo password are only so the exercise can run. Production must use a secure Identity Provider/user store, HTTPS/TLS, and never log `Authorization` headers.
- `authenticated()` only checks login; if a stream carries data distinguished by role/tenant, add `hasRole`/`hasAuthority` or service-level resource permissions **before emitting events**.
- `anyExchange().denyAll()` denies requests outside the allowlist for this security chain.
- The example is GET-only; default CSRF still affects POST/PUT/DELETE. Never disable CSRF to "fix" an error occurring in SSE GET.

### 6.4 ErrorDemoController.java: JSON Error and Two SSE Types

`src/main/java/com/example/streamfailures/ErrorDemoController.java`:

```java
package com.example.streamfailures;

import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
public class ErrorDemoController {

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping(
        value = "/api/early-error",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<String> earlyError() {
        // Publisher fails before WebFlux has any body data to write.
        return Mono.error(new DemoFailureException(
            "Simulated dependency failure"
        ));
    }

    @GetMapping(
        value = "/stream/handled",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    public Flux<ServerSentEvent<String>> handledStream() {
        return eventsThenFailure()
            .onErrorResume(DemoFailureException.class, ex ->
                Mono.just(ServerSentEvent.<String>builder()
                    .event("app-error")
                    .data("DEPENDENCY_UNAVAILABLE")
                    .build())
            );
    }

    @GetMapping(
        value = "/stream/unhandled",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    public Flux<ServerSentEvent<String>> unhandledStream() {
        // Intentionally NO onErrorResume: illustrates mid-body failure.
        return eventsThenFailure();
    }

    private Flux<ServerSentEvent<String>> eventsThenFailure() {
        var first = ServerSentEvent.<String>builder()
            .id("1")
            .event("item")
            .data("first")
            .build();

        return Flux.concat(
            Mono.just(first).delayElement(Duration.ofMillis(40)),
            Mono.<ServerSentEvent<String>>error(
                new DemoFailureException(
                    "Simulated stream dependency failure"
                )
            )
        );
    }
}

// Exception used internally by the example, not a public class in this file.
final class DemoFailureException extends RuntimeException {
    DemoFailureException(String message) {
        super(message);
    }
}
```

**Source explanation:**

1. `earlyError()` returns a `Mono.error` **before any `onNext`**. WebFlux/`@ExceptionHandler` gets a chance to construct a proper HTTP error response.
2. `eventsThenFailure()` emits the first `ServerSentEvent`, then emits `onError`. `delayElement` helps illustrate ordering, though it **is not an absolute guarantee of network flush timing**; do not use it to prove `isCommitted()`.
3. `handledStream()` places `onErrorResume` **before the Flux reaches the body writer**, turning `DemoFailureException` into a final event named `app-error` with a **non-sensitive error code** as data. The response stays SSE; the HTTP status of an already-started stream remains 200.
4. `unhandledStream()` intentionally lets `onError` propagate. After the first event, the server may have committed; in that case the HTTP handler cannot turn it into clean 500 JSON. Exact TCP/HTTP2 termination behavior depends on runtime/buffering and is **not a stable application protocol**.
5. In real apps, data-source errors are `TimeoutException`, `WebClientResponseException`, database errors, serialization errors, or permission errors; use specific mappings instead of a blanket `onErrorResume(Throwable.class)` for all errors.
6. If the error is a **security denial**, always check permissions before emitting the first item rather than waiting until the stream has leaked content.

### 6.5 EarlyErrorAdvice.java: Handling Before Body Starts

`src/main/java/com/example/streamfailures/EarlyErrorAdvice.java`:

```java
package com.example.streamfailures;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class EarlyErrorAdvice {

    @ExceptionHandler(DemoFailureException.class)
    public ResponseEntity<ProblemDetail> handle(DemoFailureException ex) {
        ProblemDetail problem = ProblemDetail.forStatus(
            HttpStatus.SERVICE_UNAVAILABLE
        );
        problem.setTitle("Dependency unavailable");
        problem.setDetail("The request cannot be completed.");

        return ResponseEntity.status(
            HttpStatus.SERVICE_UNAVAILABLE
        ).body(problem);
    }
}
```

This is a **complete class** for Spring Framework 6.x. `ProblemDetail` is the standard RFC 9457 error response type. It produces **503 Service Unavailable** with sanitized details, without returning downstream `ex.getMessage()` since exception messages can hold internal passwords/tokens/queries/databases.

**Do not over-extrapolate:** This advice handles `DemoFailureException` while WebFlux can still build an error response, such as `/api/early-error`. It **does not guarantee** sending a `ProblemDetail` after an SSE body has already committed. In that situation, the exception handler may not be invoked or cannot write the expected error body.

### 6.6 ResponseAuditWebFilter.java: Observing Commit and Errors

A WebFilter can log response state on error and register a pre-commit callback. The key is **observing, never attempting late response edits**.

`src/main/java/com/example/streamfailures/ResponseAuditWebFilter.java`:

```java
package com.example.streamfailures;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
public class ResponseAuditWebFilter implements WebFilter {

    private static final Logger log =
        LoggerFactory.getLogger(ResponseAuditWebFilter.class);

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

        ServerHttpResponse response = exchange.getResponse();
        String requestId = exchange.getRequest().getId();

        response.beforeCommit(() ->
            Mono.fromRunnable(() ->
                log.debug(
                    "Committing requestId={} status={}",
                    requestId, response.getStatusCode()
                )
            )
        );

        return chain.filter(exchange)
            .doOnError(error ->
                log.warn(
                    "Request failed requestId={} committed={} type={}",
                    requestId,
                    response.isCommitted(),
                    error.getClass().getSimpleName()
                )
            )
            .doFinally(signal ->
                log.debug(
                    "Finished requestId={} signal={}",
                    requestId, signal
                )
            );
    }
}
```

**Logger scope:**

- `beforeCommit` runs before the response commits; used to observe timing, **not as a late error hook**.
- `doOnError` observes errors that the filter actually sees; depending on WebFilter position and exception handlers, not every application error propagates up to this logger.
- `doFinally` receives `ON_COMPLETE`, `ON_ERROR`, or `CANCEL` (and other Reactor signals if applicable) to support metrics. It does not write extra data itself.
- Never log `Authorization`, bodies, or exception messages that might contain PII/secrets. Server-generated `requestId` is safer for log correlation than trusting an arbitrary client header; if using trace IDs, bound size/source.
- WebFilters **must never call `subscribe()`** to send a new body, nor catch all `onError` and return empty as if the request succeeded.

## 7. Pure Publisher Testing: Difference Between Handled and Unhandled

The first test suite needs no Spring application context. It tests the **Reactor signals** produced by the controller, not predicting HTTP status on an aborted connection.

Create `src/test/java/com/example/streamfailures/StreamErrorPublisherTest.java`:

```java
package com.example.streamfailures;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.http.codec.ServerSentEvent;
import reactor.test.StepVerifier;

class StreamErrorPublisherTest {

    private final ErrorDemoController controller =
        new ErrorDemoController();

    @Test
    void handledStreamTurnsErrorIntoLastApplicationEvent() {
        StepVerifier.create(controller.handledStream())
            .assertNext(event -> {
                assertThat(event.event()).isEqualTo("item");
                assertThat(event.data()).isEqualTo("first");
                assertThat(event.id()).isEqualTo("1");
            })
            .assertNext(event -> {
                assertThat(event.event()).isEqualTo("app-error");
                assertThat(event.data()).isEqualTo(
                    "DEPENDENCY_UNAVAILABLE");
            })
            .verifyComplete();
    }

    @Test
    void unhandledStreamEmitsItemThenErrorSignal() {
        StepVerifier.create(controller.unhandledStream())
            .assertNext(event -> {
                assertThat(event.event()).isEqualTo("item");
                assertThat(event.data()).isEqualTo("first");
            })
            .expectError(DemoFailureException.class)
            .verify();
    }

    @Test
    void earlyFailureHasErrorWithoutBodyValue() {
        StepVerifier.create(controller.earlyError())
            .expectError(DemoFailureException.class)
            .verify();
    }
}
```

**Expected** results:

| Test | Signal sequence |
| --- | --- |
| `handledStreamTurnsErrorIntoLastApplicationEvent` | `onNext(item)` → `onNext(app-error)` → `onComplete` |
| `unhandledStreamEmitsItemThenErrorSignal` | `onNext(item)` → `onError(DemoFailureException)` |
| `earlyFailureHasErrorWithoutBodyValue` | `onError(DemoFailureException)` before any `onNext` |

**Do not confuse test scope:** Publisher tests verify signal ordering; they **do not prove the first event was flushed on the socket** or that status was committed. That requires HTTP integration tests and potentially network tools to observe timing.

Run:

```bash
./gradlew test --tests '*StreamErrorPublisherTest'
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests '*StreamErrorPublisherTest'
```

No special stdout is expected beyond runtime Gradle/JUnit output. The results above are assertions designed from source, **not build results executed here**.

## 8. HTTP Testing: 401 Before Stream, 503 Before Body, and 200 with app-error Event

Create `src/test/java/com/example/streamfailures/StreamErrorHttpTest.java`:

```java
package com.example.streamfailures;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class StreamErrorHttpTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicPingWorksWithoutAuthentication() {
        client.get()
            .uri("/public/ping")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void noCredentialIsRejectedBeforeStreamStarts() {
        client.get()
            .uri("/stream/handled")
            .accept(MediaType.TEXT_EVENT_STREAM)
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void earlyErrorCanProduceAReal503ProblemResponse() {
        client.get()
            .uri("/api/early-error")
            .headers(headers -> headers.setBasicAuth(
                "reader", "reader-demo-password"))
            .exchange()
            .expectStatus().isEqualTo(HttpStatus.SERVICE_UNAVAILABLE)
            .expectBody()
            .jsonPath("$.title").isEqualTo("Dependency unavailable");
    }

    @Test
    void handledSseKeepsHttp200AndSendsAppErrorEvent() {
        Flux<ServerSentEvent<String>> events = client.get()
            .uri("/stream/handled")
            .headers(headers -> headers.setBasicAuth(
                "reader", "reader-demo-password"))
            .accept(MediaType.TEXT_EVENT_STREAM)
            .exchange()
            .expectStatus().isOk()
            .returnResult(
                new ParameterizedTypeReference<
                    ServerSentEvent<String>>() {}
            )
            .getResponseBody();

        StepVerifier.create(events)
            .assertNext(event -> {
                assertThat(event.event()).isEqualTo("item");
                assertThat(event.data()).isEqualTo("first");
            })
            .assertNext(event -> {
                assertThat(event.event()).isEqualTo("app-error");
                assertThat(event.data()).isEqualTo(
                    "DEPENDENCY_UNAVAILABLE");
            })
            .verifyComplete();
    }
}
```

Tests run against a **real Spring Boot HTTP server on a random port**, passing through the Spring Security filter chain rather than binding the controller directly. `WebTestClient` consumes SSE as `ServerSentEvent<String>`, then `StepVerifier` checks both event names and data.

**Do not add an assertion that `/stream/unhandled` must return 500.** With a publisher failing after the first event, status may already be 200 and transport behavior depends on buffering/runtime. A specific integration test can observe stream failure or connection close, yet there is **no universal status 500 outcome** binding all containers/clients.

Expected outcomes:

- `GET /public/ping` → 200.
- `GET /stream/handled` without credentials → **401** before body because Spring Security requires authentication.
- `GET /api/early-error` with valid Basic → **503** and RFC 9457 `ProblemDetail` because the error is mapped before the response starts.
- `GET /stream/handled` with valid Basic → HTTP **200** and two events `item` / `app-error` because the application proactively defined an error frame.

Run:

```bash
./gradlew test --tests '*StreamErrorHttpTest'
```

The Java code has been reviewed as a consistent example for Spring Boot/Spring Security 6.x, yet **Gradle must be run in the project to verify in practice**, especially regarding codecs and your HTTP test runtime's behavior.

### 8.1 Why Is HTTP 200 Still "Having an Error"?

In SSE, HTTP status describes **opening and accepting the HTTP response**. An SSE connection can live for minutes or hours across many events. A data-source failure in minute five cannot travel back in time to change the status sent in minute one.

Therefore the application protocol needs one of two conventions:

- `event: app-error`, `data: DEPENDENCY_UNAVAILABLE` followed by intentionally closing the stream;
- Or closing the connection; the client handles reconnect/resume via `id`, checkpoints, and retry policy.

If you need to report **request-wide** failure with HTTP status 503, verify critical preconditions **before opening the stream**, such as authentication, authorization, resource existence, and upstream readiness. You cannot always know every future failure of a long stream before sending the status.

## 9. Testing with curl and Observing Live

Start:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

With the default port, URLs are under `http://localhost:8080`. Use HTTP only on localhost with demo passwords; real deployments must use **HTTPS/TLS**.

### 9.1 Error Before Commit

```bash
curl -i http://localhost:8080/api/early-error
curl -i -u reader http://localhost:8080/api/early-error
```

With `-u reader`, curl prompts interactively for the password. Enter `reader-demo-password`.

- Missing credentials → expected **401** Basic challenge.
- Valid credentials → expected **503** and ProblemDetail JSON body. Content-type header is normally `application/problem+json`; other headers vary by server.

Expected body shape after providing Basic credentials:

```json
{
  "type": "about:blank",
  "title": "Dependency unavailable",
  "status": 503,
  "detail": "The request cannot be completed."
}
```

This **illustrates the main fields**, not a byte-for-byte raw response; the framework may add `instance` or change property order. Do not use a rigid regex across every field to determine test pass.

### 9.2 Error After SSE Has Begun

```bash
curl -i -N -u reader http://localhost:8080/stream/handled
```

`-N` disables curl's output buffering so the event stream is easier to watch. Enter the demo password. Expected **SSE content shaped like**:

```text
id:1
event:item
data:first

event:app-error
data:DEPENDENCY_UNAVAILABLE

```

Whitespace after colons or metadata order may vary by encoder; do not rely on raw bytes in tests—decode as `ServerSentEvent`. HTTP status is normally **200**, because it is an accepted SSE stream and the application emitted the error event **inside the body**.

Compare with the unhandled endpoint:

```bash
curl -i -N -u reader http://localhost:8080/stream/unhandled
```

It produces the same first event and then the publisher signals `onError`. **Do not predict a fixed status or curl exit code**: once the HTTP response is committed, the HTTP status cannot be redone; transport may close/reset and the client receives an error or simply sees a stream missing normal termination. Inspect logs/metrics and observe the difference between an intentional `app-error` event and a transport failure.

## 10. What Should an SSE Error Event Contain?

A structured event may have a contract like:

```text
event: app-error
data: {"code":"DEPENDENCY_UNAVAILABLE","retryable":true,"requestId":"..."}
```

This is an **application protocol example**, not a mandatory Spring Security format or an HTTP error response. When using JSON in `data`, serialize via a proper codec (such as Jackson); never manually concatenate strings containing special characters without escaping.

Suggested fields:

| Field | Role | What to avoid |
| --- | --- | --- |
| `code` | Stable error code for client UI/retry decisions | Internal exception names/SQL/stack traces |
| `retryable` | Whether client may retry per contract | Marking every error as retryable |
| `requestId` / `traceId` | For support and correlation | Sensitive identifiers or tokens |
| `lastEventId` | Supports resume if server can replay | Promising replay when server keeps no checkpoints |
| `message` | User-friendly message | Leaking account, tenant, or secret data |
| `terminal` | Tells client whether error ends stream or can continue | Ambiguity causing clients to hang indefinitely |

**Emit an error event only if the body can still be written** and emitting the message does not violate security policy. If a protocol/serializer error already occurred and valid `text/event-stream` can no longer be written, trying to "inject JSON error" can corrupt the stream further.

### 10.1 EventSource Clients Do Not Automatically Understand app-error

In browsers, JavaScript `EventSource` receives custom-named events via `addEventListener`. Example:

```javascript
const source = new EventSource("/stream/handled");

source.addEventListener("item", (event) => {
  console.log("item:", event.data);
});

source.addEventListener("app-error", (event) => {
  console.warn("Application error:", event.data);
  source.close();
});

source.onerror = () => {
  console.warn("Transport failed or disconnected");
};
```

**This is a client snippet**, requiring a browser environment and an endpoint with suitable auth/cookie support. `EventSource` does not let you set arbitrary Basic `Authorization` headers via the standard API; the Java server example uses Basic, so test directly with curl/WebTestClient, or design browser auth via an appropriate cookie/session/token flow. Never put credentials in query strings to bypass EventSource limits.

`app-error` is a server-defined event, **distinct from** `EventSource.onerror` triggered on transport issues. Choosing the event name `error` can easily collide/confuse with the browser's native error event; this lesson uses `app-error` for clarity.

## 11. What About NDJSON, JSON Arrays, File Downloads, and WebSockets?

Not every streaming format allows injecting structured error events:

### 11.1 SSE (text/event-stream)

SSE is designed for multiple independent events, making it easy to send an **in-band event** reporting an error before closing. Clients must parse event types and handle them. HTTP status **does not** reflect subsequent domain error events.

### 11.2 NDJSON (application/x-ndjson)

NDJSON makes each line an independent JSON object. If **the contract is defined upfront**, you can return:

```text
{"type":"data","id":"1","value":"first"}
{"type":"error","code":"DEPENDENCY_UNAVAILABLE"}
```

However, the client must distinguish `type=data` from `type=error`. If the client assumes every line is a business record, an error line can break parsing or skew record counts. Never change the contract mid-stream without versioning/tests.

### 11.3 Partially Written JSON Array

With streaming `application/json` arrays:

```text
[{"id":1},{"id":2},
```

if an error occurs before the closing `]`, the body may be **invalid JSON**. You cannot simply write `{"status":500}` mid-array and expect the client to understand; nor can you rewind to the start of the response to change content-type/status. For **all-or-nothing** requirements, buffer/validate results before commit (watching memory limits), or use NDJSON/SSE with an explicit contract instead of one giant array.

### 11.4 File Downloads / Video Streams

Once part of a file has been sent, it cannot become 500 JSON. Clients must detect incomplete transfers via content length, checksums, range/resume, storage metadata, or transport errors. Never serve a truncated file while marking "download succeeded" in business state.

### 11.5 WebSockets

After HTTP Upgrade, a WebSocket is no longer a standard HTTP response. Application errors should be represented via messages/close frames per the designed protocol before closing the connection; HTTP 500 cannot be sent as a new response after upgrade. Check permissions **before handshake** and as needed during the session; never send sensitive messages after permissions are revoked.

### 11.6 GraphQL Subscriptions and gRPC Streaming

These protocols have their own ways to signal errors/termination (GraphQL payload/errors, gRPC status/trailers) and must follow their **protocol contracts**. Do not extrapolate the "SSE `app-error` event" rule onto every streaming framework.

## 12. Authorization Must Come Before Sensitive Data

This is the direct link between late errors and **Spring Security reactive**.

### 12.1 Right: Pre-Authorization Before Emitting Flux

```java
public Flux<DomainEvent> streamForUser(String userId) {
    return permissionService.canSubscribe(userId)
        .flatMapMany(allowed -> {
            if (!allowed) {
                return Flux.error(
                    new AccessDeniedException("Not permitted"));
            }
            return eventRepository.findEventsForUser(userId);
        });
}
```

This is a **method snippet** inside a service with `permissionService`, `eventRepository` dependencies and `AccessDeniedException`, `Flux` imports. Crucially, `canSubscribe` is checked before `eventRepository` emits the first event. If `canSubscribe` returns `Mono.empty()`, the snippet above does not automatically produce `false`; production should clarify fail-closed policy with `defaultIfEmpty(false)` and error handling.

**If the permission check returns false before any body**, WebFlux security can return 403 via the appropriate mechanism. If the same response has already sent data, it cannot switch to 403 and **already-sent data cannot be recalled**.

### 12.2 Better: Explicit Fail-Closed Decision

```java
public Flux<DomainEvent> streamForUser(String userId) {
    return permissionService.canSubscribe(userId)
        .defaultIfEmpty(false)
        .flatMapMany(allowed -> {
            if (!allowed) {
                return Flux.error(
                    new AccessDeniedException("Not permitted"));
            }
            return eventRepository.findEventsForUser(userId);
        });
}
```

This is still a snippet, not a standalone runnable Java file. For long-lived streams, decide **when permissions are rechecked** (e.g., token/session expiry, resource-level permissions, tenant membership). Initial authorization does not guarantee events emitted an hour later remain permitted if policies change.

### 12.3 Wrong: Send First, Check Permissions Later

```java
return sensitiveDataFlux
    .doOnNext(data -> {
        // Checking permissions after data is already sent is TOO LATE.
    });
```

This is **warning pseudocode**. Never use `doOnNext` as an enforcement mechanism if it merely logs/checks after items are already heading to the writer. Place permission checks **before emitting items** or at an authorization gate between data source and output, never letting sensitive data outrun policy.

### 12.4 Do Not Catch Security Exceptions Into "Success Data"

Dangerous example:

```java
return protectedEvents
    .onErrorResume(AccessDeniedException.class, ex ->
        Flux.just(ServerSentEvent.<String>builder()
            .event("item")
            .data("default-public-data")
            .build())
    );
```

This is a **warning snippet**, assuming `protectedEvents`. If upstream signals access denied, silently emitting a regular `item` event masks authorization failures and misleads clients into thinking data was authorized. When terminating a stream due to revoked permissions, stop the source and emit a minimal denial notice **only when contract and security permit**; never keep returning data disguised as success.

## 13. Retry, Timeout, and Cancellation After the First Event

### 13.1 retryWhen Can Emit Duplicate Data

`retryWhen(...)` **resubscribes to the source** on error. If the source already emitted three events and the response sent them, a retry can emit those three events again or produce different results. The client could receive:

```text
event id=1
event id=2
event id=3
upstream fails
retry:
event id=1  <-- may duplicate
event id=2  <-- may duplicate
event id=3  <-- may duplicate
event id=4
```

When retries are needed in streams, define event IDs, checkpoints/resume, idempotency, or retry **individual queries before emitting data**. Never attach a full-stream retry just to "avoid reporting errors", especially for events involving money/transactions/permissions.

### 13.2 timeout Does Not Automatically Return 504 After Commit

`Flux.timeout(Duration...)` can emit `TimeoutException` when no event arrives in time. If the response is not yet committed, an error handler can pick an appropriate HTTP status. Once inside a 200 stream, timeout is **a stream error** and cannot automatically become HTTP 504. Convert timeout into `app-error` with code `UPSTREAM_TIMEOUT` and terminate, or close the connection so the client reconnects per policy.

### 13.3 Client Cancels the Request

When a browser navigates away, a user clicks "Stop", a proxy disconnects, or a client cancels the subscription, the reactive pipeline receives **CANCEL**. `doFinally(signal -> ...)` can record metrics. Do not attempt to send an "HTTP error" to a client that already closed the connection.

If upstream allocates resources (DB cursors, SSE subscriptions, file streams), ensure cleanup via Reactor operators such as `usingWhen` or driver-supported resource lifecycles. Do not rely on `onComplete` as the sole cleanup, because cancel/error must also release resources.

### 13.4 Already-Executed Side Effects Do Not Automatically Roll Back

If a controller wrote a DB record or sent a message and the response later failed mid-stream, closing the stream does not automatically undo side effects. Never promise "request failed = transaction rolled back" once a transaction committed or sits out of scope. Use transaction boundaries, outbox/idempotency keys, and business states separate from HTTP streaming states.

## 14. ServerWebExchange, Reactor Context, and Exception Handling

`ServerWebExchange` represents the HTTP request/response in WebFlux. `ReactiveSecurityContextHolder` places `SecurityContext` in the Reactor Context bound to the subscription. Never use `ThreadLocal`-based `SecurityContextHolder.getContext()` inside a `Flux` hopping threads and expect the right principal to always be present.

Common error patterns:

- `AuthenticationException` before response starts: Spring Security can issue a challenge (401) or login redirect.
- `AccessDeniedException` from role/method security before commit: can become 403.
- `ResponseStatusException` before commit: WebFlux handlers can apply the specified HTTP status.
- Mid-stream repository failure: handle as a streaming data error, not by trying to build a new HTTP error response.
- Transport or serialization failure: most likely only closing the connection and logging remains.

Calling `subscribe()` manually to run side effects outside the stream creates a brand-new subscription. It may **fail to inherit the Reactor SecurityContext**, detach from the request lifecycle, and misroute errors. Return `Mono`/`Flux` to the framework or compose publishers with `flatMap`/`then`/`concatMap`.

### 14.1 Security Filter Errors Differ from Controller Errors

HTTP Basic authentication can fail **before the controller runs**. Thus do not rely on a domain-oriented `@RestControllerAdvice` to customize Spring Security's 401/403. To customize challenges/access-denied responses, use `ServerHttpSecurity.exceptionHandling(...)` with the corresponding `ServerAuthenticationEntryPoint`/`ServerAccessDeniedHandler`.

Once the response has started, **even custom entry points/access denied handlers** cannot alter committed status/headers. Never treat them as a solution for "catching all end-of-stream errors".

### 14.2 Choosing the Right Handler for the Moment

| Goal | What to do |
| --- | --- |
| Official HTTP 400/404/500/503 JSON | Detect and map errors **before commit**, using appropriate advice/error handler |
| HTTP 401 for missing/wrong credentials | Let Spring Security authentication filter/entry point handle before body |
| HTTP 403 for insufficient permissions | Enforce authorization checks **before emitting data** |
| SSE emitted events then downstream failed | Define `app-error` event **inside the publisher** or close the stream |
| Mid-transfer file download failure | Close/fail transport so client detects incomplete file and resumes if supported |
| Stop sending data after permissions revoked | Safely cancel/terminate stream; emit no further sensitive items |
| Debug committed state | `isCommitted()`, structured logs, metrics, tracing, integration tests |
| Guarantee all-or-nothing | Defer starting body until critical work finishes, or use async job workflow |

## 15. Common Mistakes When "Handling Errors Too Late"

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Always returning `ResponseEntity.status(500)` in `onErrorResume` regardless of sent body | Cannot change status/headers, may cause further write errors | Separate pre-commit errors from stream errors |
| Thinking `@RestControllerAdvice` guarantees turning 200 into 500 after first event | Handler cannot roll back HTTP response | Use in-band events or stream termination |
| Writing `ProblemDetail` JSON mid-SSE stream | Corrupts `text/event-stream` format | Emit SSE event with safe code if contract permits |
| Treating SSE `app-error` as an HTTP error status | Clients miss errors when only checking 200 status | Clients must parse event types |
| Only `doOnError(log)` and assuming recovered | Publisher still signals `onError`, stream still fails | Use selective `onErrorResume` when valid recovery exists |
| Catching all exceptions into a default `item` event | Masks security failures or critical errors | Map specific errors; fail closed |
| Calling `block()` on WebFlux event-loop | Can stall/block threads, lose reactive context | Use reactive operators |
| Calling `subscribe()`/writing body twice in error handler | Two subscriptions/writers race on response | Keep publisher managed by WebFlux |
| Trying to write `WWW-Authenticate` while stream is returning 200 | Cannot send valid challenge after commit | Authenticate before opening stream |
| Emitting data before checking permissions | Data already leaked, cannot be recalled | Authorize before first event and revalidate appropriately |
| Using `retryWhen` across entire stream without checkpoints | Clients receive duplicate events | Use IDs/resume/idempotency |
| Not testing cancel/timeout | Subscription/resource leaks | Clean up on cancel/error |
| Assuming `isCommitted() == false` guarantees no one is committing | Races with async tasks | Let framework manage writers, check `setStatusCode` return |
| Judging stream success by status 200 alone | Stream may abort early/fail domain rules | Observe completion, event codes, and integrity |
| Writing exception message into error event | Leaks SQL paths, internal URLs, credentials | Use public error codes and safe trace IDs |
| Expecting proxies to flush every event immediately | Buffering delays client receipt | Configure/test reverse proxies per protocol |
| Assuming 403 after POST is always authorization | CSRF may block before method security | Inspect CSRF + policies in order |
| Failing to distinguish domain and transport errors | Clients reconnect wrongly or miss business errors | Document event protocol and reconnect policy |

## 16. Advanced Practice: Handling Errors Before Opening the Stream

Suppose an SSE stream must fetch configuration, validate scope, and check dependencies before returning any items.

**Design suggestion (method snippet):**

```java
public Flux<ServerSentEvent<String>> openStream(String resourceId) {
    return accessPolicy.canStream(resourceId)
        .defaultIfEmpty(false)
        .flatMapMany(allowed -> {
            if (!allowed) {
                return Flux.error(new AccessDeniedException(
                    "Stream access denied"
                ));
            }

            return dependencyService.checkReady(resourceId)
                .thenMany(eventSource.watch(resourceId));
        });
}
```

This is an **architectural snippet**, requiring real `accessPolicy`, `dependencyService`, and `eventSource`, with appropriate class/exception imports. Benefits:

1. If permissions are insufficient, `Flux` emits an error before any event data; handlers/entry points can return a valid status.
2. If the dependency is unready, it can map to 503 **before opening SSE**.
3. Only when preconditions pass does the data publisher run.
4. If the dependency fails **after watching for a while**, stream errors must still be handled per earlier sections; preflight cannot guarantee the source never fails.

**Note:** `checkReady` is a readiness check subject to races: the dependency could die right after the check. If atomicity is required, use guaranteeing infrastructure protocols/workflows rather than just pinging before streaming.

### 16.1 When Is Buffering the Entire Response Reasonable?

If an endpoint must return a JSON object/array **only when all data is available**, you can use `collectList()` or aggregate within memory bounds and write the body only after the entire source completes:

```java
return reportRepository.fetchRows(query)
    .collectList()
    .map(rows -> new ReportResponse(rows));
```

This is a method snippet. It defers writing the body until the full list is ready, so source failures prior to completion can be mapped to an error status before commit. **In return**, it consumes memory, adds latency, and loses streaming benefits; never use it for unbounded or arbitrarily large datasets.

When very large datasets must be processed, an **asynchronous job** pattern is usually better: POST creates a job → status endpoint reports progress/result → download file once complete. Errors can then be represented as job state instead of trying to rewrite status on an already-started stream.

## 17. Production Testing and Observability Checklist

### 17.1 Before Response Has a Body

- [ ] Verify missing/invalid credentials receive Spring Security 401 or login redirect per mechanism.
- [ ] Verify authenticated users lacking role/scope receive 403 **before sensitive data is emitted**.
- [ ] Verify pre-commit validation, dependency, and business exceptions map to proper 4xx/5xx.
- [ ] Verify `ProblemDetail` contains no internal exception messages, secrets, or undisclosed tenant details.

### 17.2 After Stream Emits First Item

- [ ] Test that domain-handled streams emit a **contract-compliant** `app-error` event, then complete or stop per design.
- [ ] Test that unhandled-error streams emit `onError` and **do not** expect a fixed HTTP 500 status.
- [ ] Test that SSE clients do not look only at status 200, but also parse event types, error codes, and completion/reconnect.
- [ ] Test client cancellation and resource cleanup.
- [ ] Test timeouts, retries, event IDs/resume, avoiding duplicate emissions on resubscribe.
- [ ] Test permission revalidation on long-lived streams and ensure no events are sent after revocation.
- [ ] For JSON arrays/file downloads, test incomplete-payload detection and integrity.
- [ ] Test with reverse proxies/load balancers and appropriate buffering and timeout configs.

### 17.3 Logs and Metrics

- [ ] Record request ID/trace ID, route, error type, `response.isCommitted()`, and `COMPLETE/ERROR/CANCEL` signals where possible.
- [ ] Count **pre-commit HTTP errors**, **in-band domain error events**, and **transport/stream failures** separately.
- [ ] Do not rely solely on HTTP 5xx metrics: errors in a 200 stream need dedicated business metrics.
- [ ] Avoid logging passwords, access tokens, cookies, raw response bodies, or SQL/stack traces into client-returned events.
- [ ] Set alerts for abnormal stream terminations and abnormal reconnect rates.
- [ ] Test mid-stream connection drops across multiple clients and HTTP/1.1/HTTP2 when supported.

## 18. Self-Check Questions

**Question 1.** Why can `onErrorResume` inside an SSE publisher still work after the first event even though HTTP status does not change?

**Answer:** It changes **the publisher's data signals before the body writer**, without trying to build a new HTTP response. As long as the formatter/transport can still write SSE, it can emit `app-error` and complete while the committed status stays intact.

**Question 2.** Does `ServerHttpResponse.isCommitted()` prove the user already saw the first event on their screen?

**Answer:** No. It reflects commit state on the reactive server; proxies, sockets, and clients can buffer. Still, after commit, status/headers cannot be modified.

**Question 3.** If `WebFluxResponseStatusExceptionHandler` receives `ResponseStatusException(500)` after the response is committed, can it change the status?

**Answer:** No. The handler's Javadoc states the error remains unresolved and propagates when the response is committed.

**Question 4.** Should a protected SSE GET without credentials open the stream and then send an `app-error` event?

**Answer:** Not in the Basic model shown here. Spring Security must authenticate **before** permitting body emission; missing credentials get 401/challenge. Never open a sensitive stream only to discover afterward the caller lacks permission.

**Question 5.** Do HTTP 200 SSE and an `app-error` event contradict each other?

**Answer:** No. HTTP 200 describes opening the response successfully; `app-error` is a data-transfer failure defined by the application protocol.

**Question 6.** Can a `ProblemDetail` JSON be written at the end of a partially sent JSON array?

**Answer:** Not under a JSON array contract. The body risks becoming invalid JSON. To signal mid-stream errors, use SSE/NDJSON with an explicit schema, or switch to async jobs/buffered responses.

**Question 7.** Why shouldn't `retryWhen` be applied to the entire stream after a late error?

**Answer:** Retrying can resubscribe to the source and re-emit already-sent events, causing duplicates. Use event IDs, resume/checkpoints, idempotency, or retry only on sources that have not emitted data yet.

**Question 8.** Does logging with `doOnError` and returning the `Flux` mean the stream recovered?

**Answer:** No. `doOnError` only observes the error. Downstream still receives `onError` unless a valid recovery operator like `onErrorResume` is present.

**Question 9.** If a client already cancelled the subscription, should you try to send a final error event?

**Answer:** No. The client may no longer be reading; instead clean up resources and record `CANCEL` metrics.

**Question 10.** Why is a method security exception occurring after data has been sent a serious design flaw?

**Answer:** Already-sent data cannot be recalled and status cannot be changed to 403. Place authorization **before the first event**, and revalidate during long streams if policy requires.

## 19. Summary

**Three principles to remember:**

1. **Before commit:** Authenticate, authorize, validate, and map errors as early as possible; before body starts, the framework can emit HTTP-compliant 401/403/4xx/5xx.
2. **After commit:** You cannot create a "new error response" by changing status/headers. If the streaming protocol allows it, **proactively convert errors into in-stream events/records before the body writer**; otherwise terminate the stream/connection and log the failure.
3. **Data safety:** Never wait until after the first event to verify permissions. For long streams, establish clear policies for revalidation, cancellation, retry/idempotency, and client-side error interpretation.

For Spring Security WebFlux, an authorization failure at the start of a request remains an **HTTP authentication/authorization** problem. An error arising inside an already-streaming `Flux` becomes a **Reactive Streams and body-protocol** problem. Distinguishing these two boundaries avoids promising 500 after the client already received 200, or worse, leaking data before discovering the user lacks permission.

### Official Documentation and Reference Standards

- [Spring Framework 6.2 — WebFluxResponseStatusExceptionHandler Javadoc: error remains unresolved when response committed](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/reactive/handler/WebFluxResponseStatusExceptionHandler.html)
- [Spring Framework — ServerHttpResponse Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/http/server/reactive/ServerHttpResponse.html)
- [Spring Framework — WebFlux Reactive Core and WebExceptionHandler](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html)
- [Spring Framework — WebFlux Annotated Controllers, Return Values/SSE](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html)
- [Spring Framework — Error Responses and ProblemDetail](https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html)
- [Spring Security 6.5 — WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Security 6.5 — ServerHttpSecurity.ExceptionHandlingSpec](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/config/web/server/ServerHttpSecurity.ExceptionHandlingSpec.html)
- [Project Reactor — Error Handling Operators](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)
