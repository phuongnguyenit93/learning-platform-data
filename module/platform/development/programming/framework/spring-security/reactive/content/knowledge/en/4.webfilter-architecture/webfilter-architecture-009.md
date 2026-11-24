# Continuation, Early Termination, and Error Propagation in the WebFilter Chain

## Objectives

When a request enters Spring WebFlux, multiple `WebFilter` instances can run before and after the WebHandler. A filter can **forward the request to the next filter**, **terminate the request on the spot**, or **let an error propagate back to outer handlers**. In Spring Security Reactive, this choice directly impacts authentication, authorization, HTTP status codes, and error control.

After this lesson, you will be able to:

1. Accurately explain `WebFilter.filter(ServerWebExchange, WebFilterChain)` and the meaning of `Mono<Void>`.
2. Write a pass-through filter via `return chain.filter(exchange)` with Reactor-compliant post-processing.
3. Write a request-blocking branch by setting the status and returning `response.setComplete()` without calling downstream.
4. Track `onComplete`, `onError`, and `cancel`; distinguish HTTP 403/500 from Reactor error signals.
5. Know when to use `doOnError`, `onErrorMap`, `onErrorResume`, and when to let Spring Security/WebFlux handle errors.
6. Build and test a Java 17+ WebFlux example covering all three scenarios: continuation, early termination, and error propagation.

This lesson focuses on the **WebFilter architecture** of Spring Security Reactive and Spring WebFlux, including integration with `SecurityWebFilterChain`. Examples target Spring Boot 3.x, Spring Framework 6.x, Spring Security 6.x, and Java 17+.

## 1. Contracts of WebFilter and WebFilterChain

Two primary API signatures:

```java
// Abbreviated API declarations for reading comprehension, not a file to create.
public interface WebFilter {
    Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain);
}

public interface WebFilterChain {
    Mono<Void> filter(ServerWebExchange exchange);
}
```

`ServerWebExchange` describes WebFlux's request and response. `WebFilterChain` passes the remaining request work to the next filter and eventually to the WebHandler. `Mono<Void>` represents **when the request lifecycle completes or fails**; it does not contain the response body. A controller can return `Mono<String>` or `Flux<T>`, whereas a filter uses `Mono<Void>` to represent lifecycle completion.

Nested model:

```text
Client
  |
  v
WebFilter A (enter)
  |
  +-- chain.filter(exchange) --> WebFilter B (enter)
                                  |
                                  +-- chain.filter(exchange)
                                  |       |
                                  |       v
                                  |    WebHandler / Controller
                                  |       |
                                  |       v
                                  |    publisher completes/errors/cancels
                                  |
                                  v
                              WebFilter B (post-processing)
  |
  v
WebFilter A (post-processing)
  |
  v
WebFlux completes response
```

Entry order is typically outer-to-inner; termination signals are observed along each publisher's operators, inner-to-outer. That **does not mean all code runs on a single fixed thread**. Reactor can switch execution schedulers, while Spring WebFlux manages the subscription.

Spring Security Reactive adds `WebFilterChainProxy` and one or more `SecurityWebFilterChain` beans. A request passes through WebFlux's global WebFilter chain and, if applicable, enters the security filters inside a `SecurityWebFilterChain`. A global `@Bean WebFilter` with `@Order` and a filter configured via `ServerHttpSecurity` belong to **two different ordering layers**.

## 2. Three Ways a Reactor Chain Terminates

With `Mono<Void>`, you must distinguish **Reactor signals** from **HTTP outcomes**.

| Signal | What happens? | Relation to HTTP |
|---|---|---|
| `onComplete` | Publisher completed normally | Response can still be 200, 204, 302, 403, 429, etc. |
| `onError(Throwable)` | An unhandled error escaped the publisher | Requires an appropriate error handler to map to HTTP, often 5xx for app errors |
| `cancel` | Subscription was cancelled, e.g., client disconnected | No guarantee a new HTTP response can be sent |

For example, a filter that intentionally returns `403` via `setStatusCode(HttpStatus.FORBIDDEN)` and `setComplete()` can emit **onComplete**, because the filter successfully produced the 403 response. A controller returning `Mono.error(new IllegalStateException(...))` can emit **onError**, which WebFlux's error handler then translates into HTTP 500.

`Mono<Void>` does not emit a `Void` value. Therefore, `doOnNext(...)` is unsuitable for knowing when a filter finishes; use `doOnSuccess(...)` for success, `doOnError(...)` for errors, and `doFinally(...)` to observe completion, error, and cancellation together.

## 3. Continuing Processing: Returning `chain.filter(exchange)`

This is the simplest filter form:

```java
@Component
public class PassThroughFilter implements WebFilter {

    @Override
    public Mono<Void> filter(ServerWebExchange exchange,
                             WebFilterChain chain) {
        return chain.filter(exchange);
    }
}
```

This is an illustrative class in a WebFlux project requiring imports for `org.springframework.stereotype.Component`, `org.springframework.web.server.WebFilter`, `ServerWebExchange`, `WebFilterChain`, and `reactor.core.publisher.Mono`. Calling `chain.filter(exchange)` **delegates** processing to the rest of the chain, and the returned publisher reflects the outcome of the whole chain.

### 3.1. Before, After, and Observing Errors

Illustrative `filter(...)` body with a declared logger `log`:

```java
@Override
public Mono<Void> filter(ServerWebExchange exchange,
                         WebFilterChain chain) {
    String path = exchange.getRequest().getPath().value();

    return Mono.defer(() -> {
        log.info("BEFORE {}", path);

        return chain.filter(exchange)
            .doOnSuccess(ignored -> log.info("COMPLETE {}", path))
            .doOnError(error -> log.warn("ERROR {}: {}", path,
                error.getClass().getSimpleName()))
            .doFinally(signal -> log.info("FINALLY {}: {}", path, signal));
    });
}
```

- `Mono.defer(...)` creates a publisher per subscription and defers side effects until the request actually executes.
- `doOnSuccess(...)` runs when the downstream publisher completes **normally**; for `Mono<Void>`, the callback argument may be `null`.
- `doOnError(...)` only **observes the error**. It does not alter the error, produce an HTTP response, or guarantee the error becomes 500.
- `doFinally(...)` sees `SignalType.ON_COMPLETE`, `ON_ERROR`, or `CANCEL`, useful for lightweight telemetry/cleanup.

To run another step after `chain.filter(exchange)` succeeds, use:

```java
return chain.filter(exchange)
    .then(Mono.fromRunnable(() -> metrics.countCompleted()));
```

This snippet sits inside a filter with an appropriate `metrics` object; if downstream errors, `then(...)` does **not** execute the next publisher. To count errors and cancellations as well, record inside `doFinally` or use signal-specific hooks.

### 3.2. Three Common Coding Mistakes

**Wrong — subscribing manually and returning an unrelated publisher:**

```java
chain.filter(exchange).subscribe();
return Mono.empty();
```

That filter creates a separate subscription, which can make the framework think the request finished while downstream is still running. Errors, response writes, cancellation, and Reactor Context no longer follow the main request lifecycle.

**Right:**

```java
return chain.filter(exchange);
```

**Wrong — creating the publisher and discarding it:**

```java
chain.filter(exchange);
return exchange.getResponse().setComplete();
```

Merely constructing the publisher from `chain.filter` does not mean its inner work was subscribed to or executed. To continue, you must **return** it. To terminate early, do **not** call the chain; never combine the two like above.

**Wrong — blocking the event loop:**

```java
chain.filter(exchange).block();
return Mono.empty();
```

Calling `block()` inside a reactive server's WebFilter can stall the event loop, trigger blocking errors, or break cancellation/context structure. Compose with Reactor operators instead.

## 4. Early Termination: Not Calling `chain.filter(exchange)`

A filter may reject a request before the controller or return its own response. For example:

```java
@Override
public Mono<Void> filter(ServerWebExchange exchange,
                         WebFilterChain chain) {
    if ("/blocked".equals(exchange.getRequest().getPath().value())) {
        exchange.getResponse().setStatusCode(HttpStatus.FORBIDDEN);
        return exchange.getResponse().setComplete();
    }

    return chain.filter(exchange);
}
```

This is an illustrative method snippet requiring `org.springframework.http.HttpStatus` and WebFlux API imports.

When the path is `/blocked`, `chain.filter(exchange)` is **not** called, so **downstream** filters and the WebHandler **do not run**. However, **outer** filters that called into this filter still receive the completion signal and can run `doOnSuccess`/`doFinally`.

```text
A: enter -> B: check /blocked
             -> status = 403
             -> response.setComplete()
             -> do NOT call chain.filter
A: receives onComplete (still runs post-processing)
Client: HTTP 403, no body from controller
```

Key point: an HTTP 403 can be **the normal completion of response creation**, not an `onError`.

### 4.1. `setComplete()` vs. `Mono.empty()`

`ServerHttpResponse.setComplete()` represents completing the WebFlux-managed response. In a blocking branch, set status/headers before calling it. Returning `Mono.empty()` immediately without writing the response or setting a status easily produces misleading HTTP outcomes, because the framework does not know whether you intended denial, rate limiting, or success.

Some short-circuit scenarios:

- Rate limiting: set `429 Too Many Requests` and consider an appropriate `Retry-After`.
- Temporary maintenance: set `503 Service Unavailable` and retry info if applicable.
- Redirect: set a 3xx status and a trusted `Location`.
- Cache hit: construct a complete response from cache with proper headers/content type.
- Security access denial: **prefer Spring Security mechanisms** (authorization, entry point, denied handler) to keep policies consistent.

Do not write a global WebFilter checking roles via a client-supplied user header. Statuses 401/403 and identity checks belong to verified authentication/authorization.

### 4.2. Committed HTTP Responses

Once the response has committed headers or begun sending body bytes, changing the status no longer takes effect. `ServerHttpResponse.isCommitted()` helps inspect state; `setStatusCode(...)` returns a boolean indicating whether setting the status was accepted. Trying to modify status inside `doFinally` is usually too late. Block requests **before** downstream writes the response.

### 4.3. Why `permitAll()` Is Not a Short-Circuit

Spring Security rule:

```java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/public").permitAll()
    .anyExchange().authenticated()
)
```

`permitAll()` means **the authorization step allows proceeding**, not that it generates a response or skips the controller. If the public endpoint returns 404 or 500, `permitAll()` does not turn it into 200. If an upstream rate-limit filter blocks the request, security's `permitAll()` policy cannot force the request forward either.

## 5. How Do Errors Propagate Back Through Filters?

Suppose a controller returns a failing publisher:

```java
@GetMapping("/failure")
public Mono<String> failure() {
    return Mono.error(new IllegalStateException("demo failure"));
}
```

This is a method inside a `@RestController` with appropriate imports. If no inner error handler turns the error into a response, `onError(IllegalStateException)` propagates back to filters wrapping downstream:

```text
Outer WebFilter
  |
  v
Inner WebFilter
  |
  v
Controller -> Mono.error(IllegalStateException)
  |
  +-- error --> Inner.doOnError
                  |
                  +-- error --> Outer.doOnError
                                 |
                                 +--> WebFlux error handling
                                       |
                                       +--> HTTP 500 if response
                                            not yet committed
```

Errors only pass through publisher segments **within scope** of the observing operator. If an inner `@ExceptionHandler` or `onErrorResume` has already consumed the error, the outer filter may only see `onComplete`. Therefore, never assume every filter logs an error just because HTTP returned 500.

### 5.1. Three Operators to Distinguish

| Operator | What it does | Downstream/Outer signal |
|---|---|---|
| `doOnError(error -> log...)` | Observes for logging/metrics | Remains `onError` unless the callback itself throws |
| `onErrorMap(error -> new DomainException(...))` | Translates the error to another error | Remains `onError` with the new throwable |
| `onErrorResume(DomainException.class, e -> fallback)` | Replaces the error with another publisher when type matches | May become `onComplete` if fallback succeeds |
| `doFinally(signal -> ...)` | Observes termination, including `cancel` | Does not alter the original signal |

Illustrative example of an adapter converting **one specific business error** into HTTP 503:

```java
// Custom business exception (created in project, not colliding with framework classes).
class DependencyUnavailableException extends RuntimeException {
    DependencyUnavailableException(String message) {
        super(message);
    }
}

// @Bean method inside a @Configuration class with appropriate imports.
@Bean
WebFilter dependencyFailureAdapter() {
    return (exchange, chain) -> chain.filter(exchange)
        .onErrorResume(DependencyUnavailableException.class, error -> {
            if (exchange.getResponse().isCommitted()) {
                return Mono.error(error);
            }
            exchange.getResponse().setStatusCode(
                HttpStatus.SERVICE_UNAVAILABLE);
            return exchange.getResponse().setComplete();
        });
}
```

The snippet above is **class-scoped illustrative code**, not a standalone Java file since imports and class layout are needed. The error must originate from the pipeline inside this filter and not already be handled by another handler. Only when the response is uncommitted can status 503 be set. Other error types continue propagating without being turned into 503.

**Do not use a blanket catch-all fallback arbitrarily:**

```java
return chain.filter(exchange)
    .onErrorResume(error -> Mono.empty());
```

That pattern can "swallow" security and programming bugs, hide incidents, and return responses that mask the root cause. Target specific exception types with explicit response and logging policies, letting out-of-scope errors propagate.

### 5.2. Error Signals Differ from Synchronous Exceptions

In Reactor, errors occurring at subscription time can appear via `Mono.error(...)` or when a `map`/`flatMap` callback throws. Either way, once inside the publisher, it travels via `onError`. An exception thrown **before returning the publisher** in the setup path may be caught at another framework layer; use `Mono.defer(...)` so side effects and errors belong to subscription execution when appropriate.

Do not replace proper exception mapping with `try/catch` blocks around `chain.filter`: many errors occur **after** the method returns, during asynchronous subscription and execution. Synchronous `try/catch` does not catch `onError` signals from the downstream publisher.

## 6. How Does Spring Security Reactive Turn AuthN/AuthZ Errors into HTTP?

Spring Security WebFlux typically uses these components:

- `AuthenticationWebFilter`: performs authentication per the configured mechanism; an authentication failure handler can return a challenge, redirect, or another response.
- `AuthorizationWebFilter`: decides whether a request is allowed into the resource via `ReactiveAuthorizationManager`.
- `ExceptionTranslationWebFilter`: translates eligible `AuthenticationException`/`AccessDeniedException` signals emitted from the security chain within its scope into HTTP responses via an authentication entry point or access-denied handler.

In a typical HTTP Basic configuration:

| Request | Security Interpretation | Typical HTTP Status |
|---|---|---|
| No credentials, endpoint needs authentication | Entry point needed to request authentication | `401` and Basic challenge |
| Wrong credentials | Authentication failed | `401` |
| Authenticated but missing role | Authorization denied | `403` |
| Sufficient permissions | Proceeds to controller | `200` if controller succeeds |
| Unhandled controller error | Application/WebFlux error | `500` if response uncommitted |

These statuses **are not absolute laws**: form login may redirect to a login page; custom handlers may return JSON and different statuses. `401/403` also do not require `Mono.error` across every filter, because a security handler may write the response and complete normally.

**Crucial placement note:** a global WebFilter **outside** `WebFilterChainProxy` that throws `AccessDeniedException` itself may sit outside `ExceptionTranslationWebFilter`'s error-catching scope. Never assume it will automatically yield 403; Spring Security works best when policies live in `authorizeExchange` and standard security handlers.

When customizing, use:

- `ServerHttpSecurity.authorizeExchange(...)` to require `authenticated()`, `hasRole(...)`, `hasAuthority(...)`, or `denyAll()`.
- `ServerHttpSecurity.exceptionHandling(...)` with `ServerAuthenticationEntryPoint` or `ServerAccessDeniedHandler` to customize auth/access-denied responses.
- `ServerHttpSecurity.addFilterAt(WebFilter, SecurityWebFiltersOrder)` when a specialized security filter is genuinely needed inside the chain; pick the right slot and know what runs before/after.
- Global `WebFilter` for instrumentation, correlation IDs, and application-wide concerns; never confuse a global bean's `@Order` with `SecurityWebFiltersOrder` inside the security chain.

## 7. Cancellation and Timeouts Are Not Always onError

Clients can close connections mid-flight, and upstream can proactively cancel a subscription. `doOnError` is not invoked on a pure cancellation. To observe all three outcomes:

```java
return chain.filter(exchange)
    .doFinally(signal -> {
        switch (signal) {
            case ON_COMPLETE -> metrics.completed();
            case ON_ERROR -> metrics.failed();
            case CANCEL -> metrics.cancelled();
            default -> { }
        }
    });
```

This is an illustrative snippet inside a filter method using a provided `metrics` object, Reactor's `SignalType`, and Java 17 switch expressions. Do not write a response from `doFinally` when the signal is `CANCEL` because the client may already be disconnected. Metric recording should be fast and never block the event loop.

Reactor's `timeout(Duration...)` can emit `TimeoutException` if a publisher is slow and cancel upstream, whereas an external client/proxy timeout may manifest as cancellation/disconnect. Do not assume every timeout turns into 504. Mapping a timeout to an HTTP status requires explicit handling, checking `!isCommitted()`, and ensuring error details do not leak.

## 8. Runnable Project: All Three Cases on One WebFilter Chain

We create a small WebFlux application using two global WebFilters and a controller. Spring Security remains integrated, configured with `permitAll` **solely for studying filter flow** so it does not obscure the three outcomes. This configuration is not a production policy.

### 8.1. Initializing the Gradle Project

Use Spring Initializr with Gradle, Java 17+, Spring Boot 3.x, Spring Reactive Web, Spring Security, and Spring Boot Starter Test. In the Initializr-generated `build.gradle`, required dependencies are:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
```

This is a **Gradle dependency configuration snippet**, not a complete standalone `build.gradle`. Keep the Spring Boot plugin, repositories, dependency management, Java toolchain, and wrapper generated by Initializr. Do not add `spring-boot-starter-web` to an inbound WebFlux demo.

File layout:

```text
src/main/java/demo/webfilterflow/
  FlowApplication.java
  WebSecurityConfig.java
  FlowFilters.java
  FlowController.java
src/test/java/demo/webfilterflow/
  FlowIntegrationTests.java
```

### 8.2. `FlowApplication.java`

```java
package demo.webfilterflow;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FlowApplication {

    public static void main(String[] args) {
        SpringApplication.run(FlowApplication.class, args);
    }
}
```

### 8.3. `WebSecurityConfig.java`

```java
package demo.webfilterflow;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class WebSecurityConfig {

    @Bean
    public SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .anyExchange().permitAll())
            .httpBasic(basic -> basic.disable())
            .formLogin(login -> login.disable())
            .build();
    }
}
```

All GET endpoints are permitted through authorization in order to observe the behavior of global filters. HTTP Basic/form login are disabled to avoid challenges/redirects outside the lesson's focus. Default CSRF is kept; since the demo uses only GET, CSRF does not need to be disabled to run.

### 8.4. `FlowFilters.java`: Outer Observer and Inner Gate

```java
package demo.webfilterflow;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.WebFilter;
import reactor.core.publisher.Mono;

@Configuration
public class FlowFilters {

    private static final Logger log =
        LoggerFactory.getLogger(FlowFilters.class);

    @Bean
    @Order(-200)
    public WebFilter traceWebFilter() {
        return (exchange, chain) -> {
            String path = exchange.getRequest().getPath().value();

            return Mono.defer(() -> {
                log.info("BEGIN {}", path);

                return chain.filter(exchange)
                    .doOnSuccess(ignored ->
                        log.info("COMPLETE {}", path))
                    .doOnError(error ->
                        log.warn("ERROR {} {}", path,
                            error.getClass().getSimpleName()))
                    .doFinally(signal ->
                        log.info("FINALLY {} {}", path, signal));
            });
        };
    }

    @Bean
    @Order(-190)
    public WebFilter gateWebFilter() {
        return (exchange, chain) -> {
            String path = exchange.getRequest().getPath().value();

            if ("/stop".equals(path)) {
                exchange.getResponse()
                    .setStatusCode(HttpStatus.FORBIDDEN);
                return exchange.getResponse().setComplete();
            }

            return chain.filter(exchange);
        };
    }
}
```

Between these two beans, `@Order(-200)` runs before `@Order(-190)`. Other framework filters may sit around or between them depending on configuration; never use these values to infer ordering inside `SecurityWebFilterChain`.

When a request enters `traceWebFilter`, `BEGIN` is logged upon subscription; `gateWebFilter` checks the path. For `/stop`, the gate sets `403` and completes without calling the chain further. The outer `traceWebFilter` still observes completion, **not necessarily `onError`**. For `/failure`, the controller emits an error and trace receives `doOnError` if no inner handler consumed it.

### 8.5. `FlowController.java`

```java
package demo.webfilterflow;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class FlowController {

    @GetMapping("/ok")
    public Mono<String> ok() {
        return Mono.just("ok");
    }

    @GetMapping("/stop")
    public Mono<String> shouldNotRun() {
        return Mono.just("controller-was-called");
    }

    @GetMapping("/failure")
    public Mono<String> failure() {
        return Mono.error(new IllegalStateException("demo failure"));
    }
}
```

The `/stop` handler really exists, yet should not be invoked because the gate stops the request beforehand. `/failure` intentionally emits an error to observe the `onError` path; real applications must handle business errors according to their own policy.

### 8.6. Run and Check via HTTP

From the root of the Initializr project:

```bash
./gradlew bootRun
```

Windows:

```powershell
.\gradlew.bat bootRun
```

When the server is listening on default port 8080, send requests:

```bash
curl -i http://localhost:8080/ok
curl -i http://localhost:8080/stop
curl -i http://localhost:8080/failure
```

On PowerShell, use `curl.exe` if `curl` is a different alias. Expectations:

| Request | HTTP Status | Body |
|---|---|---|
| `GET /ok` | `200` | `ok` |
| `GET /stop` | `403` | No body written by controller |
| `GET /failure` | `500` when Boot handles unmapped error | Error body generated by WebFlux/Boot; do not assume fixed content |

Expected observations in filter logs for **each independent request**:

```text
/ok:
  BEGIN /ok
  COMPLETE /ok
  FINALLY /ok onComplete

/stop:
  BEGIN /stop
  COMPLETE /stop
  FINALLY /stop onComplete

/failure:
  BEGIN /failure
  ERROR /failure IllegalStateException
  FINALLY /failure onError
```

This is an **expected signal schematic**, not fixed stdout to match whitespace/log format verbatim; Spring/Netty may print additional logs and concurrent requests may interleave. For `/stop`, HTTP 403 accompanied by normal Reactor completion is the intentional result. For `/failure`, the error is handled by the general error handler into HTTP 500 when the response is uncommitted.

### 8.7. `FlowIntegrationTests.java`

```java
package demo.webfilterflow;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class FlowIntegrationTests {

    @Autowired
    WebTestClient client;

    @Test
    void continueReachesController() {
        client.get().uri("/ok")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("ok");
    }

    @Test
    void earlyFinishSkipsController() {
        client.get().uri("/stop")
            .exchange()
            .expectStatus().isForbidden()
            .expectBody().isEmpty();
    }

    @Test
    void errorGetsMappedByWebFlux() {
        client.get().uri("/failure")
            .exchange()
            .expectStatus().is5xxServerError();
    }
}
```

Run:

```bash
./gradlew test
```

Windows:

```powershell
.\gradlew.bat test
```

**Expect 3 passing tests** when classes and dependencies match the example. The tests use `WebTestClient` on a random port, verifying actual outcomes over HTTP. Gradle/JUnit stdout formatting is not guaranteed fixed. To test exact signals inside a standalone filter, use Reactor Test's `StepVerifier`, though these HTTP integration tests already prove which controller ran and the final HTTP status.

## 9. Explaining Each Scenario Yourself

### `GET /ok`

```text
trace: BEGIN
  gate: path != /stop -> return chain.filter(exchange)
    security: permitAll -> continue
    controller: Mono.just("ok") -> WebFlux writes body
trace: doOnSuccess -> COMPLETE
trace: doFinally(ON_COMPLETE)
HTTP 200, body ok
```

### `GET /stop`

```text
trace: BEGIN
  gate: path == /stop
    -> setStatusCode(403)
    -> response.setComplete()
    -> do not call downstream chain
trace: doOnSuccess -> COMPLETE
trace: doFinally(ON_COMPLETE)
HTTP 403, controller /stop does not run
```

Here, `COMPLETE` in the log does not mean HTTP 200; it simply reports that the publisher finished normally.

### `GET /failure`

```text
trace: BEGIN
  gate: path != /stop -> chain.filter
    controller: Mono.error(IllegalStateException)
trace: doOnError -> ERROR
trace: doFinally(ON_ERROR)
WebFlux error handler -> HTTP 500 (when not committed)
```

If `onErrorResume(IllegalStateException.class, ...)` is placed **inside** `trace` and produces a successful response, `trace` may only see completion. If the handler sits **outside** `trace`, `trace` may still see `onError` while the final HTTP response is turned into the fallback. Operator placement determines observable behavior.

## 10. Choosing the Right Layer for Each Need

| Need | Preferred API or Mechanism | Reason |
|---|---|---|
| Request logging, correlation ID, metrics | Global `WebFilter` + `doFinally` | Independent of authentication |
| Forward request to controller | `return chain.filter(exchange)` | Preserves subscription and lifecycle |
| Block traffic by quota/infrastructure rule | WebFilter/gateway with explicit status | Proactively short-circuits before downstream |
| Authorization by role, scope, principal | `ServerHttpSecurity.authorizeExchange` | Integrates auth context and 401/403 |
| Handle missing credentials | `ServerAuthenticationEntryPoint` / authentication failure handler | HTTP Basic, form, OAuth have different behaviors |
| Handle insufficient permissions | `ServerAccessDeniedHandler` | Matches security semantics |
| Add a security WebFilter into the chain | `addFilterAt` with `SecurityWebFiltersOrder` | Defines position in the security pipeline |
| Handle business exceptions | `@ExceptionHandler`, WebFlux error handler, or conditional fallback | Avoids swallowing all errors in a generic filter |

A global WebFilter can run **before** some security filters; a security filter can stop the request before the controller. Therefore, predicting HTTP statuses and error signals requires inspecting **exact operator placement**, not just exception classes or endpoint names.

## 11. Common Mistakes

1. **Not returning the publisher from `chain.filter`.** Merely creating a publisher does not ensure downstream executes; return the publisher itself.
2. **Calling `subscribe()` manually.** Detaches the request from framework-managed lifecycle/tracing/cancellation.
3. **Calling `block()` on the event loop.** Can stall the server; compose asynchronous operators instead.
4. **Assuming HTTP 403 is always `onError`.** A filter writing a 403 response and calling `setComplete()` can complete normally.
5. **Short-circuiting without setting an HTTP status.** Clients may receive misleading responses.
6. **Using `doOnError` expecting errors to turn into statuses automatically.** It only observes; an error handler decides the response.
7. **Catching every error with `onErrorResume(e -> Mono.empty())`.** Easily swallows security/programming errors and hides incidents.
8. **Trying to write a response inside `doFinally`.** Headers/body may already be committed or the client disconnected.
9. **Trying to modify status after response commit.** Check `isCommitted()` and act early.
10. **Equating `permitAll` with skipping all filters.** `permitAll` only lets the authorization step continue.
11. **Confusing global `@Order` with `SecurityWebFiltersOrder`.** The two layers have distinct configuration orderings.
12. **Throwing `AccessDeniedException` from a global filter expecting 403 automatically.** The security error translator only catches errors within its scope.
13. **Not distinguishing cancellation from error.** `doOnError` does not represent client disconnect; `doFinally` can observe `CANCEL`.
14. **Logging raw `Authorization` header values.** Filters can see credentials/tokens; never write secrets to logs.
15. **Reading thread-local `SecurityContextHolder` inside a reactive pipeline.** Use `ReactiveSecurityContextHolder`/WebFlux injection for subscription-scoped security context.

## 12. Check Questions

**Question 1.** A filter returns `response.setComplete()` with status 429 without calling `chain.filter(exchange)`. What happens?

**Answer:** Downstream filters and the controller do not run. Filters entered earlier can still observe `onComplete` and run post-processing. HTTP 429 is not necessarily a Reactor `onError`.

**Question 2.** Fix the following code:

```java
chain.filter(exchange).subscribe();
return Mono.empty();
```

**Answer:** `return chain.filter(exchange);`. The framework controls subscription, errors, and cancellation; the filter must not subscribe itself.

**Question 3.** Why does `doOnError` in an outer filter not run when the controller errors?

**Answer:** The error may have been converted into a normally completing publisher by an `@ExceptionHandler` or `onErrorResume` at an inner layer before reaching the outer filter. Check downstream scope and handler placement.

**Question 4.** For a JWT API, to restrict `/admin` to `SCOPE_admin`, should you write a global WebFilter that compares tokens manually or use the security DSL?

**Answer:** Use `authorizeExchange(...).hasAuthority("SCOPE_admin")` alongside verified JWT resource server/authority mapping. The security DSL provides consistent authentication/authorization semantics.

**Question 5.** After the response sends part of the body, can a filter switch from 200 to 503 via `onErrorResume`?

**Answer:** Usually no, because headers are already committed; you must record and propagate the error or handle the connection properly, never attempting to send a second response.

**Question 6.** When a client disconnects, must `doOnError` run?

**Answer:** No. Client disconnect can cause the subscription to receive `CANCEL`; observe via `doFinally` to distinguish cancellation from error.

## Key Takeaways

```text
WebFilter.filter(...) -> Mono<Void>

CONTINUE:
  return chain.filter(exchange)
  -> downstream runs, result propagates back to outer filters

EARLY FINISH:
  response.setStatusCode(...)
  return response.setComplete()      // do not call chain.filter
  -> downstream stops, outer filters can still observe onComplete

ERROR:
  Mono.error(e) -> onError propagates back through operators
  doOnError: observe
  onErrorMap: transform error
  onErrorResume: can recover
  error handler: can map to HTTP response if not committed

CANCEL:
  subscription cancelled -> doFinally(CANCEL)
  do not assume HTTP response can still be sent
```

In Spring Security Reactive, **HTTP status**, **Reactor signal**, and **authentication/authorization decision** are three distinct concepts. Only by understanding all three can you explain why a filter stops a request, why a completion log accompanies a 403, or why an error reaches only certain filters in the chain.

## Official Documentation

- [Spring Framework — WebFilter API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/server/WebFilter.html)
- [Spring Framework — WebFilterChain API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/server/WebFilterChain.html)
- [Spring Framework — WebExceptionHandler API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/server/WebExceptionHandler.html)
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security — Reactive authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html)
- [Spring Security — ExceptionTranslationWebFilter](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/authorization/ExceptionTranslationWebFilter.html)
- [Project Reactor — Error handling operators](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)
