# Boundaries Between WebFilter, @ControllerAdvice, and WebExceptionHandler Errors in Spring Security WebFlux

## Lesson Objectives

In **Spring Security - reactive**, a request can be rejected at multiple stages before a controller runs: WebFlux `WebFilter`, Spring Security `AuthenticationWebFilter`/`AuthorizationWebFilter`, CSRF, router/handler mapping, reactive business logic, or while writing the response. When returning errors, you must pick the **right handling layer**: `@ControllerAdvice`, `WebExceptionHandler`, or **security exception handlers**.

This lesson belongs to the **Error Responses** group and focuses on *responsibility boundaries*, not just writing a class to return pretty JSON.

After this lesson, you can:

1. Accurately trace the path from Reactor Netty → `WebExceptionHandler` → `WebFilter` → `DispatcherHandler` → controller/handler.
2. Explain why `@RestControllerAdvice` normally handles errors from controllers and handler results, yet is **not a universal error handler for every WebFilter**.
3. Know that `WebExceptionHandler` handles unhandled errors from the WebFilter/`WebHandler` chain and how `@Order` interacts with Spring Boot's default error handler.
4. Separate Spring Security **401 authentication** and **403 authorization/CSRF** errors from 4xx business errors, 5xx filter errors, and 500 application errors.
5. Write a `WebFilter` that intentionally returns `Mono.error(...)`, a dedicated `@RestControllerAdvice`, and a `WebExceptionHandler` catching only permitted error types.
6. Build a runnable **Java 17+, Spring Boot 3.3.13, Spring WebFlux, Spring Security** example tested with `WebTestClient`.
7. Properly handle responses that are already `isCommitted()`: never promise to change status/body after the response has been sent.
8. Avoid dangerous bugs: catch-alls masking authentication errors, swallowing exceptions into `Mono.empty()`, double-writing bodies, leaking stack traces/tokens, and breaking filter order.
9. Use a decision table to choose where errors are returned for annotated controllers, functional endpoints, authentication, authorization, filters, connections, and post-commit errors.

**Technical scope:** `org.springframework.web.server.WebFilter` and `WebExceptionHandler` belong to **WebFlux reactive**; `@ControllerAdvice` uses WebFlux's annotated controller model. Do not confuse with Servlet `Filter`, `OncePerRequestFilter`, `HandlerExceptionResolver`, or Servlet `ExceptionTranslationFilter`.

## 1. Request and Error Processing Map

An overview diagram (details may vary by version/config):

```text
                 Reactor Netty / HTTP request
                            |
                            v
                 HttpWebHandlerAdapter
                            |
                            v
            WebExceptionHandler chain (unhandled errors)
                            |
                            v
                   WebFilter chain
                            |
        +-------------------+--------------------+
        |                   |                    |
        v                   v                    v
   Custom WebFilter   Spring Security        Other filter
                      WebFilterChainProxy
                        /             \
               authentication      authorization
                  |                    |
                401/redirect         403/401
                  |                    |
           handled inside Spring Security
                            |
                            v
                    DispatcherHandler
                            |
                    HandlerMapping
                            |
                    HandlerAdapter
                            |
                  @RestController method
                            |
              +-------------+---------------+
              |                             |
              v                             v
           Mono.value                   Mono.error(e)
              |                             |
              v                             v
         ResultHandler            @ExceptionHandler (local)
                                            |
                                            v
                                   @ControllerAdvice
                                            |
                              handled -> HTTP response
                              unhandled -> propagate
                                            |
                                            v
                         WebExceptionHandler chain / Boot fallback
```

The diagram distinguishes **inner/outer layers**. In practice, `DispatcherHandler` and `HandlerAdapter` support multiple asynchronous error-handling mechanisms; some errors arise during handler mapping or result handling, not only inside controller bodies.

**Quick rules to remember:**

- **Errors from a `WebFilter` before a controller is chosen:** do not expect `@ControllerAdvice` to catch them; handle intentionally in the filter or in `WebExceptionHandler`.
- **Business errors from annotated controllers/handler results:** controller `@ExceptionHandler`, then `@ControllerAdvice`, or global fallback if unhandled.
- **Errors handled nowhere yet:** `WebExceptionHandler` ordered by `@Order`; Spring Boot provides a default error handler.
- **Authentication/authorization errors:** prioritize `ServerAuthenticationEntryPoint`, `ServerAccessDeniedHandler`, and Spring Security filters instead of replacing them with generic exception mappings.
- **Response already sent:** status/headers/body cannot be arbitrarily rewritten. You may need to close the connection or only log/emit metrics rather than generating a new error JSON.

## 2. Three Abstractions and Their Differences

### 2.1. WebFilter

`WebFilter` is a hook wrapping the request-processing chain:

```java
public interface WebFilter {
    Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain);
}
```

A filter can:

- Inspect request path/headers before reaching handlers.
- Set correlation IDs, measure timing, verify preconditions, and populate `ServerWebExchange` attributes.
- Short-circuit the request with an appropriate response.
- Emit an error via `Mono.error(...)`.
- Attach `doOnError`/`doFinally` around `chain.filter(exchange)` to observe downstream outcomes.

Minimal example:

```java
return chain.filter(exchange)
        .doOnError(error -> {
            // Only record metrics or log redacted non-sensitive details.
            // doOnError does not "swallow" exceptions.
        });
```

**Misconception:** Any `WebFilter` with `onErrorResume` acts as a "system-wide error handler". A filter can observe **unhandled** downstream errors, yet does not necessarily see errors already handled by `@ControllerAdvice`/Spring Security. Nor can it safely rewrite a response after commit.

### 2.2. @ControllerAdvice / @RestControllerAdvice

`@ControllerAdvice` belongs to the **annotated controller model**. `@ExceptionHandler` methods can handle errors from controllers or result processing within the supported handler scope.

`@RestControllerAdvice` combines `@ControllerAdvice` with `@ResponseBody`, suited for returning JSON:

```java
@RestControllerAdvice
class ApiAdvice {
    @ExceptionHandler(DomainFailureException.class)
    ResponseEntity<ApiError> onDomainFailure(
            DomainFailureException ex) {

        return ResponseEntity.status(HttpStatus.UNPROCESSABLE_ENTITY)
                .body(new ApiError(
                        "BUSINESS_RULE", "Request violates business rules"));
    }
}
```

It **does not automatically become a global WebFilter exception interceptor**. Errors emitted by a filter running before `DispatcherHandler` may have no controller context for applying `@ExceptionHandler`. Spring Framework 6.x adds finer-grained dispatch exception handling in `HandlerAdapter`, yet you should never build policy assuming `@ControllerAdvice` definitely catches every pre-handler exception.

**Do not write `@ExceptionHandler(Exception.class)` turning everything into 200 or 500** without a strategy separating `AccessDeniedException`, `AuthenticationException`, `ResponseStatusException`, binding errors, and protocol errors. A catch-all can accidentally intercept security errors from controller/method security before `ExceptionTranslationWebFilter` handles them.

### 2.3. WebExceptionHandler

`WebExceptionHandler` is an abstraction of the **WebFlux WebHandler API**:

```java
public interface WebExceptionHandler {
    Mono<Void> handle(ServerWebExchange exchange, Throwable ex);
}
```

It handles unhandled exceptions from the WebFilter chain and target WebHandler. Register as a Spring bean and optionally use `@Order` to specify priority.

- Return a normally completing `Mono<Void>` when the handler **has handled** the error and completed the response.
- Return `Mono.error(ex)` when the handler **does not handle this error type** so the next handler gets a chance.
- Check `exchange.getResponse().isCommitted()` before setting status, headers, or writing body.
- Do not swallow every Throwable with `Mono.empty()`; that can turn errors into inconsistent responses or mask security bugs.
- Do not assume a controller has been selected.
- Never log raw Authorization headers, session cookies, access tokens, passwords, or output stack traces to responses.

Spring Boot 3.3 automatically provides `DefaultErrorWebExceptionHandler` for unhandled errors. It can return HTML when clients request HTML and JSON for machine clients; content depends on `server.error.*` settings and content negotiation. Do not assume an identical fixed body across versions.

### 2.4. Responsibility Comparison Table

| Criterion | `WebFilter` | `@RestControllerAdvice` | `WebExceptionHandler` |
| --- | --- | --- | --- |
| Runs before router? | Possibly | Not an independent filter layer | Part of global error processing |
| Receives `ServerWebExchange` | Yes | Available as handler method argument | Yes |
| Handles reactive controller errors | Only unhandled downstream errors | Primary responsibility | If unresolved by advice/handler |
| Handles pre-controller filter errors | Handles itself or emits upstream | Should not be relied on | Can handle |
| Reactive contract | `Mono<Void> filter(...)` | `@ExceptionHandler` returns response body/`Mono`/`ResponseEntity` | `Mono<Void> handle(...)` |
| Ordering | WebFilter `@Order` | Local handler before global advice, own advice order | `@Order` in WebExceptionHandler chain |
| 401/403 security errors | Spring Security filters handle internally | Not the default place to alter security status | Only propagating security errors, not standard path |
| Can write HTTP body | Yes, if uncommitted | Yes via message writers | Yes directly or via fallback mechanism |
| Best suited for | Cross-cutting, preconditions, metrics | Controller business/API errors | Global fallback or WebHandler/filter-layer errors |

**Two independent `@Order` scopes:** `@Order(-200)` on a `WebFilter` does not sit "before" `@Order(-2)` on a `WebExceptionHandler` in the **same list**. They belong to two separate chains created at different layers. Internal Spring Security filter ordering is yet another layer.

## 3. Where Does Spring Security Handle 401/403?

### 3.1. Authentication Errors

A request requiring login with missing or invalid credentials can end in **401**, a form-login redirect, or another response depending on the authentication mechanism.

Relevant components:

- `ServerAuthenticationEntryPoint`: initiates authentication when a request lacks a valid identity; e.g., Basic challenge/redirect.
- `AuthenticationWebFilter` and authentication failure handlers: handle credential failures for a specific mechanism.
- `ExceptionTranslationWebFilter`: in the reactive security chain, routes downstream `AccessDeniedException` to the entry point or access-denied handler depending on authentication state and policy.

With HTTP Basic, clients normally receive **401** with `WWW-Authenticate`. If you write a catch-all `WebExceptionHandler` returning 500 for `AuthenticationException` before Spring Security responds, the response violates the protocol and can leak information.

### 3.2. Authorization Errors

When an authenticated user lacks a role/scope, `AuthorizationWebFilter` or method security may emit `AccessDeniedException`. Spring Security reactive normally uses `ServerAccessDeniedHandler` to return **403**.

**Note:** When the caller is unauthenticated, an authorization denial can be converted into **401/redirect** instead of 403. Therefore, never infer HTTP codes from the exception class name alone; inspect the principal and configured entry point/handler.

### 3.3. CSRF Is Not a Controller Business Error

With cookie/session-based browser POSTs, `CsrfWebFilter` can reject requests missing a token **before the controller** and return 403. Adding a `@RestControllerAdvice` catching `IllegalArgumentException` will not solve this. To fix it, inspect the request CSRF token, cookies, HTTP method, and chain config; never casually call `csrf.disable()`.

### 3.4. Customizing Security Responses

In WebFlux, `ServerHttpSecurity`'s DSL supports:

```java
http.exceptionHandling(spec -> spec
        .authenticationEntryPoint(entryPoint)
        .accessDeniedHandler(deniedHandler));
```

This is a **configuration snippet**; provide real `ServerAuthenticationEntryPoint` and `ServerAccessDeniedHandler` beans writing contract-compliant responses. Never use Servlet's `HttpSecurity.exceptionHandling(...)` in this project.

**Important:** Customizing the HTTP Basic entry point can accidentally drop `WWW-Authenticate` if you set status 401 without preserving the challenge. For a Bearer Resource Server, preserve standard `WWW-Authenticate: Bearer` and OAuth error code semantics; do not return HTML forms or arbitrary bodies for APIs. That is why the runnable example in the next section **keeps the default Basic mechanism**.

## 4. Error Flow Models: "Handled" vs "Unhandled"

### 4.1. Error in an Early Filter

```text
Request /api/filter-fail
  |
  v
PreRoutingFailureFilter (WebFilter, runs before security/router)
  |
  +--> Mono.error(FilterPhaseException)
            |
            +--> no controller selected
            |
            v
  Custom WebExceptionHandler @Order(-2)
            |
            +--> matches FilterPhaseException type
            +--> response not committed
            +--> HTTP 503 + static JSON
            |
            v
  Response complete
```

In this situation, `@RestControllerAdvice` does not run. Even if a controller maps the same URL, it **is never invoked**.

### 4.2. Error from a Controller Mono

```text
Request /api/business-fail
  |
  v
WebFilters -> Security permitAll -> DispatcherHandler
  |
  v
@RestController method -> Mono.error(DomainFailureException)
  |
  v
@RestControllerAdvice @ExceptionHandler(DomainFailureException.class)
  |
  +--> HTTP 422 + JSON code BUSINESS_RULE
  |
  v
Response complete; WebExceptionHandler fallback not needed
```

Returning `Mono.error(...)` from a controller differs from creating `Mono.just(...)` and throwing elsewhere outside the publisher; both can be handled by the framework in many cases, yet the error signal must be subscribed within DispatcherHandler's flow for advice to intercept it.

### 4.3. Unhandled Controller Error Without a Specific Handler

```text
Request /api/unhandled
  |
  v
@RestController -> Mono.error(IllegalStateException)
  |
  v
No @ExceptionHandler for IllegalStateException
  |
  v
Error signal propagates to WebExceptionHandler chain
  |
  v
Spring Boot DefaultErrorWebExceptionHandler
  |
  +--> HTTP 500 + body depending on Accept/config (JSON/HTML)
```

Do not treat Boot's default error JSON as a stable public API schema unless locked down with contract tests. The fallback's job is a safe response; business APIs should define their own expected errors.

### 4.4. 401/403 Errors

```text
GET /api/private (no credentials)
  -> Spring Security requires authentication
  -> HTTP Basic 401 + WWW-Authenticate
  -> controller not invoked

GET /api/admin (Basic user without ROLE_ADMIN)
  -> authentication succeeds
  -> authorization DENY
  -> Spring Security access denied handler
  -> HTTP 403, controller does not run
```

There is no reason to force these two flows through a custom `@ControllerAdvice` returning 500.

## 5. Complete Example: WebFlux, Filter, Advice, and Global Error Handler

The example uses **Java 17+, Spring Boot 3.3.13**, Gradle, and Spring Security WebFlux. Its goal is not to simulate a production app with a DB; it deliberately creates errors at exact stages so **status/body/headers can be compared via tests**.

Endpoints:

| Endpoint | Mechanism | Expected |
| --- | --- | --- |
| `GET /api/public/ok` | No login needed | 200 `OK` |
| `GET /api/business-fail` | Controller `Mono.error(DomainFailureException)` | 422 + code `BUSINESS_RULE` |
| `GET /api/filter-fail` | Early WebFilter `Mono.error(FilterPhaseException)` | 503 + code `FILTER_FAILURE` |
| `GET /api/unhandled` | Controller `Mono.error(IllegalStateException)` | 500 from Boot fallback |
| `GET /api/private` | Requires authenticated | No credentials: 401 |
| `GET /api/admin` | Requires ROLE_ADMIN | User with only ROLE_USER: 403 |

### 5.1. Project Structure

```text
webflux-error-boundaries/
  settings.gradle
  build.gradle
  src/main/java/example/
    ErrorBoundaryApplication.java
    ApiController.java
    ApiError.java
    DomainFailureException.java
    FilterPhaseException.java
    PreRoutingFailureFilter.java
    ApiAdvice.java
    FilterFailureHandler.java
  src/test/java/example/
    ErrorBoundaryApplicationTests.java
```

### 5.2. Gradle

Create `settings.gradle`:

```groovy
rootProject.name = 'webflux-error-boundaries'
```

Create `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

The Boot BOM manages compatible Framework/Security/Reactor versions. Never add `spring-boot-starter-web` (MVC/Servlet) to this WebFlux project.

### 5.3. ErrorBoundaryApplication.java

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.reactive
        .EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails
        .MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
@EnableWebFluxSecurity
public class ErrorBoundaryApplication {

    public static void main(String[] args) {
        SpringApplication.run(ErrorBoundaryApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(
                                "/api/public/**",
                                "/api/business-fail",
                                "/api/filter-fail",
                                "/api/unhandled")
                        .permitAll()
                        .pathMatchers("/api/admin")
                        .hasRole("ADMIN")
                        .anyExchange().authenticated())
                .httpBasic(withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails user = User.withUsername("alice")
                .password("{noop}learn")
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(user);
    }
}
```

**Explanation:**

- `@EnableWebFluxSecurity` activates the reactive security chain.
- `/api/public/**` and the three demo error URLs allow unauthenticated access purely to test the **error origin**.
- `/api/admin` requires ADMIN; `alice` only has ROLE_USER so she gets 403 when logged in.
- `/api/private` is not in permitAll, so it is protected by `anyExchange().authenticated()`.
- `httpBasic(withDefaults())` ensures 401 returns a valid Basic challenge.
- `formLogin(...disable())` avoids form redirects that would obscure 401 test results.
- `{noop}learn` is **for local learning environments only**; production needs a proper password encoder, HTTPS, rate limiting, and secure credential storage.

### 5.4. Two Dedicated Exceptions

Create `src/main/java/example/DomainFailureException.java`:

```java
package example;

public class DomainFailureException extends RuntimeException {
    public DomainFailureException() {
        super("Demo business rule failed");
    }
}
```

Create `src/main/java/example/FilterPhaseException.java`:

```java
package example;

public class FilterPhaseException extends RuntimeException {
    public FilterPhaseException() {
        super("Demo pre-routing filter failure");
    }
}
```

These two classes help verify **the right handling layer** without matching text on a generic `IllegalStateException`. In real products, define clear exception types for domain, validation, access policy, and infrastructure failures, while avoiding dozens of classes without clear contracts.

### 5.5. ApiError.java — Response DTO

Create `src/main/java/example/ApiError.java`:

```java
package example;

public record ApiError(String code, String message) {
}
```

The DTO separates the stable error code (`code`) from display text (`message`). Never put stack traces, SQL details, hashes, or session data in responses. For larger APIs, consider `ProblemDetail`/RFC 9457 and synchronized request trace IDs.

### 5.6. ApiController.java — Errors from Controller

Create `src/main/java/example/ApiController.java`:

```java
package example;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/api/public/ok")
    public Mono<String> ok() {
        return Mono.just("OK");
    }

    @GetMapping("/api/business-fail")
    public Mono<String> businessFailure() {
        return Mono.error(new DomainFailureException());
    }

    @GetMapping("/api/unhandled")
    public Mono<String> unexpectedFailure() {
        return Mono.error(
                new IllegalStateException("demo unhandled exception"));
    }

    @GetMapping("/api/filter-fail")
    public Mono<String> shouldNotReachController() {
        return Mono.just("CONTROLLER_WAS_CALLED");
    }

    @GetMapping("/api/private")
    public Mono<String> privateEndpoint() {
        return Mono.just("PRIVATE_OK");
    }

    @GetMapping("/api/admin")
    public Mono<String> adminEndpoint() {
        return Mono.just("ADMIN_OK");
    }
}
```

A controller mapping for `/api/filter-fail` is deliberately included to prove **the filter blocks before the controller**. If the actual response is 503 with code FILTER_FAILURE, this handler never ran to return `CONTROLLER_WAS_CALLED`.

`Mono.error(...)` pushes the error into the reactive chain. `Mono.empty()` is not an error; returning empty from a controller can complete the response without generating error JSON. Do not "fix" errors by swallowing exceptions into empty when the client needs to know a failure occurred.

### 5.7. ApiAdvice.java — Catching Only Business Errors

Create `src/main/java/example/ApiAdvice.java`:

```java
package example;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiAdvice {

    @ExceptionHandler(DomainFailureException.class)
    public ResponseEntity<ApiError> handleDomainFailure(
            DomainFailureException error) {

        return ResponseEntity
                .status(HttpStatus.UNPROCESSABLE_ENTITY)
                .header("X-Error-Handled-By", "controller-advice")
                .body(new ApiError(
                        "BUSINESS_RULE",
                        "Request violates business rules"));
    }
}
```

**Why intentionally catch only `DomainFailureException`?**

- `@RestControllerAdvice` uses DispatcherHandler's annotated-controller error handling.
- It does not claim `FilterPhaseException` emitted before a controller was chosen.
- It does not swallow `AccessDeniedException`/`AuthenticationException` and alter security statuses.
- It does not intercept the unexpected fallback `IllegalStateException`; Boot handles it as 500.
- The body contains a safe controlled message, never copying exception messages or stack traces directly.

In real applications you may need `@ExceptionHandler(ResponseStatusException.class)`, validation exception handlers, or a `ResponseEntityExceptionHandler` subclass to customize `ProblemDetail`. Each handler should have an explicit scope and order; avoid unguarded blanket catch-alls.

### 5.8. PreRoutingFailureFilter.java — Emitting Errors Before the Controller

Create `src/main/java/example/PreRoutingFailureFilter.java`:

```java
package example;

import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
@Order(-200)
public class PreRoutingFailureFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String path = exchange.getRequest()
                .getPath().pathWithinApplication().value();

        if (exchange.getRequest().getMethod() == HttpMethod.GET
                && "/api/filter-fail".equals(path)) {
            return Mono.error(new FilterPhaseException());
        }

        return chain.filter(exchange);
    }
}
```

**Ordering:** Spring Boot 3.3 normally registers Spring Security's WebFilterChainProxy at order `-100`; the demo filter's `@Order(-200)` runs earlier. This number illustrates an error occurring **before Spring Security and DispatcherHandler**, not a recommendation to always place custom filters before security.

**What NOT to do in production:**

- Read/write a security principal before the authentication filter populates context and treat it as verified.
- Place filters with side effects or custom permission checks ahead of the standard chain without evaluating bypasses.
- Write status/body for every exception solely via `onErrorResume(Exception.class, ...)`.
- Call `block()` or perform blocking I/O on the Netty event loop.
- Write an HTTP response and then still call `chain.filter(exchange)`; that risks writing bodies twice.

This example only emits a dedicated exception type for the test path.

### 5.9. FilterFailureHandler.java — Ordered WebExceptionHandler

Create `src/main/java/example/FilterFailureHandler.java`:

```java
package example;

import java.nio.charset.StandardCharsets;

import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebExceptionHandler;
import reactor.core.publisher.Mono;

@Component
@Order(-2)
public class FilterFailureHandler implements WebExceptionHandler {

    @Override
    public Mono<Void> handle(ServerWebExchange exchange, Throwable error) {

        if (!(error instanceof FilterPhaseException)) {
            // Forward errors outside this handler's responsibility
            // to the next WebExceptionHandler.
            return Mono.error(error);
        }

        if (exchange.getResponse().isCommitted()) {
            // Cannot change status/body once the response is committed.
            return Mono.error(error);
        }

        var response = exchange.getResponse();
        response.setStatusCode(HttpStatus.SERVICE_UNAVAILABLE);
        response.getHeaders().setContentType(MediaType.APPLICATION_JSON);
        response.getHeaders().set("X-Error-Handled-By",
                "web-exception-handler");

        String payload = """
                {"code":"FILTER_FAILURE","message":"Filter rejected request"}
                """.trim();

        byte[] bytes = payload.getBytes(StandardCharsets.UTF_8);

        return response.writeWith(Mono.just(
                response.bufferFactory().wrap(bytes)));
    }
}
```

**Contract explanation:**

1. Only `FilterPhaseException` is handled; other exceptions return `Mono.error(error)` for the next handler.
2. If the response is already `isCommitted()`, do not rewrite it. There is no general "response rollback".
3. Sets `503 Service Unavailable`, JSON content type, and a header showing where it was handled.
4. The static payload avoids manually inserting sensitive input or arbitrary messages into JSON. When dynamic bodies are needed, use a controlled serializer for proper escaping instead of concatenating client input into JSON strings.
5. `writeWith(Mono.just(buffer))` returns a publisher that writes the body and completes per the `Mono<Void>` contract. Do not call `subscribe()` separately.
6. `@Order(-2)` puts this handler **ahead of Boot's default error handler**, which is normally ordered `-1` in Boot 3.3 configs; it does not replace Boot's default handler for other exceptions.
7. Using a dedicated exception type reduces the risk of accidentally catching authentication/authorization errors.

**Warning about `@Order`:** Only compare order against **other WebExceptionHandlers**. Never compare `@Order(-2)` here with a WebFilter's `@Order(-200)` as if they lived in the same chain.

In larger apps, to format JSON errors consistently, you can replace the static JSON snippet with a utility using `ObjectMapper`/`ServerCodecConfigurer`, while managing DataBuffer lifecycles and avoiding post-commit writes. That is a framework-level responsibility rather than calling controller advice from a filter.

## 6. Testing via HTTP and Comparing

Requires **JDK 17+** and Gradle compatible with Spring Boot 3.3.13.

```bash
gradle bootRun
```

If the project has a Gradle Wrapper, use `./gradlew bootRun` (Linux/macOS) or `gradlew.bat bootRun` (Windows).

In another terminal:

```bash
curl -i http://localhost:8080/api/public/ok
curl -i http://localhost:8080/api/business-fail
curl -i http://localhost:8080/api/filter-fail
curl -i http://localhost:8080/api/unhandled
curl -i http://localhost:8080/api/private
curl -i -u alice:learn http://localhost:8080/api/private
curl -i -u alice:learn http://localhost:8080/api/admin
```

Expected demo application results:

| Request | Status | Handler | Indicators |
| --- | --- | --- | --- |
| Public OK | 200 | Controller | Body `OK` |
| Business fail | 422 | `ApiAdvice` | Header `X-Error-Handled-By: controller-advice`, code `BUSINESS_RULE` |
| Filter fail | 503 | `FilterFailureHandler` | Header `X-Error-Handled-By: web-exception-handler`, code `FILTER_FAILURE` |
| Unhandled | 500 | Boot fallback `DefaultErrorWebExceptionHandler` | Body depends on `Accept`/`server.error.*` |
| Private no credentials | 401 | Spring Security | Basic challenge |
| Private with Basic alice | 200 | Controller | Body `PRIVATE_OK` |
| Admin with Basic alice | 403 | Spring Security | Missing `ROLE_ADMIN` |

The goal is **distinguishing paths**. Do not treat the `X-Error-Handled-By` header as a production standard or security requirement; it is a demonstration observation aid. Boot fallback bodies are not fixed strings across Spring Boot versions, so test primarily for status 500.

If sending `Accept: text/html`, Boot fallback may render an HTML error view, whereas the custom `FilterFailureHandler` in the example always returns JSON. That is the handler's choice, with no automatic content negotiation for manually written bodies. Production APIs need an explicit media-type contract.

## 7. Complete Testing with WebTestClient

Create `src/test/java/example/ErrorBoundaryApplicationTests.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive
        .AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.boot.test.context.SpringBootTest
        .WebEnvironment.RANDOM_PORT;

@SpringBootTest(webEnvironment = RANDOM_PORT)
@AutoConfigureWebTestClient
class ErrorBoundaryApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void publicRouteIsOk() {
        client.get().uri("/api/public/ok")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("OK");
    }

    @Test
    void controllerErrorIsHandledByAdvice() {
        client.get().uri("/api/business-fail")
                .exchange()
                .expectStatus().isEqualTo(422)
                .expectHeader()
                .valueEquals("X-Error-Handled-By",
                        "controller-advice")
                .expectBody()
                .jsonPath("$.code").isEqualTo("BUSINESS_RULE");
    }

    @Test
    void filterErrorIsHandledByWebExceptionHandler() {
        client.get().uri("/api/filter-fail")
                .exchange()
                .expectStatus().isEqualTo(503)
                .expectHeader()
                .valueEquals("X-Error-Handled-By",
                        "web-exception-handler")
                .expectBody()
                .jsonPath("$.code").isEqualTo("FILTER_FAILURE");
    }

    @Test
    void unexpectedControllerErrorFallsBackToBoot() {
        client.get().uri("/api/unhandled")
                .header(HttpHeaders.ACCEPT, "application/json")
                .exchange()
                .expectStatus().is5xxServerError();
    }

    @Test
    void unauthenticatedPrivateRequestGetsBasicChallenge() {
        client.get().uri("/api/private")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().exists(
                        HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void authenticatedUserCanAccessPrivateEndpoint() {
        client.get().uri("/api/private")
                .headers(h -> h.setBasicAuth("alice", "learn"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("PRIVATE_OK");
    }

    @Test
    void authenticatedNonAdminGetsForbidden() {
        client.get().uri("/api/admin")
                .headers(h -> h.setBasicAuth("alice", "learn"))
                .exchange()
                .expectStatus().isForbidden();
    }
}
```

Run:

```bash
gradle test
```

### What Do These Tests Verify?

- **200:** request passes through filters to the controller normally.
- **422:** `@RestControllerAdvice` handles the exception type emitted from an annotated controller.
- **503:** WebFilter emits an error before the controller, and a dedicated `WebExceptionHandler` handles it without advice swallowing it.
- **500:** controller error unhandled by advice falls back globally.
- **401:** Spring Security entry point responds with challenge; no business controller response runs.
- **403:** user has Authentication but lacks permissions; no `ADMIN_OK` handler body is returned.

These are integration tests on a real Spring Boot application via WebTestClient. They do not prove all streaming/commit errors, Netty load behavior, or production 404/validation policies; add tests matching real runtime/routes.

## 8. The Committed Response Boundary

This is the case that most often causes confusing failures when working with reactive streams.

### 8.1. When the Response Is Not Committed

If an error occurs before status/headers/body are sent, the handler can:

- Set an appropriate status;
- Set `Content-Type`, cache control, and safe headers;
- Serialize a small JSON body;
- Complete the response or let another handler handle it.

### 8.2. When the Response Is Already Committed

Suppose a handler starts writing a `Flux`:

```text
HTTP/1.1 200 OK
Content-Type: application/json

[{"id":1},
 ... error occurred after part of the body was sent ...
```

The in-flight response cannot be changed into:

```text
HTTP/1.1 500 Internal Server Error
{"error":"failed"}
```

because the status line and part of the body **have already been sent to the client**. `ServerHttpResponse.isCommitted()` reflects this state. Normal handling logs the error and terminates the stream/connection per infrastructure behavior, or uses a streaming format (SSE/gRPC protocol-level errors) with dedicated error semantics. Never append an error JSON object in the middle of an incomplete JSON array and treat it as a valid response.

### 8.3. Illustrative Mid-Stream Error Example

```java
// ILLUSTRATIVE SNIPPET, not part of the complete demo.
@GetMapping(value = "/api/stream",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<String> stream() {
    return Flux.concat(
            Flux.just("first", "second"),
            Flux.error(new IllegalStateException(
                    "downstream stream failure")));
}
```

For SSE, some events may already have been written. `@ControllerAdvice`/`WebExceptionHandler` is not guaranteed to be able to rewrite HTTP 200 into 500. To signal errors **at the application protocol level** once a stream is open, design an SSE `event: error` event with a safe schema (leaking no internals) and handle it inside the stream; that differs from changing HTTP status.

**Important:** `onErrorResume` inside a stream can recover with a valid event **if the protocol allows it**. However, never turn database or authorization failures into fake success data; define an explicit contract so clients distinguish partial success from failure.

## 9. @ControllerAdvice with Functional Endpoints and Handler Mapping

Spring WebFlux has two routing models:

1. **Annotated controllers:** `@RestController`, `@RequestMapping`, `@ExceptionHandler`, and `@ControllerAdvice`.
2. **Functional endpoints:** `RouterFunction<ServerResponse>` and `HandlerFunction<ServerResponse>`.

`@ControllerAdvice` is not a default mechanism applied directly to every functional `HandlerFunction`. With functional routing, handle errors inside the publisher, in a router/handler filter, or let `WebExceptionHandler`/Boot fallback handle them.

Example handling errors directly in a functional handler (illustrative snippet):

```java
Mono<ServerResponse> response =
        businessService.execute()
            .flatMap(value ->
                    ServerResponse.ok().bodyValue(value))
            .onErrorResume(DomainFailureException.class,
                ex -> ServerResponse.status(422)
                        .bodyValue(new ApiError(
                                "BUSINESS_RULE",
                                "Request violates business rules")));
```

This snippet requires `businessService` and RouterFunction API imports; it is not a standalone file. Key point: **functional handlers decide how to turn domain exceptions into ServerResponse** when not delegating to a global error handler.

Handler mapping errors before a controller exists may be mapped by the framework to HTTP 404/405/400 via built-in mechanisms; never conclude all such errors pass through your custom `@ControllerAdvice`. In WebFlux 6.x, `HandlerAdapter`'s `DispatchExceptionHandler` can assist with certain errors before/outside handler invocation, yet it **does not turn advice into a universal filter**.

### 9.1. Controller @ExceptionHandler vs Global Advice

If a controller has:

```java
@RestController
class LocalController {

    @GetMapping("/api/local-error")
    public Mono<String> fail() {
        return Mono.error(new DomainFailureException());
    }

    @ExceptionHandler(DomainFailureException.class)
    public ResponseEntity<ApiError> localHandler(
            DomainFailureException ex) {
        return ResponseEntity.status(409)
                .body(new ApiError(
                        "LOCAL_FAILURE", "Handled locally"));
    }
}
```

and a global `@RestControllerAdvice` also catches `DomainFailureException`, the controller's **local `@ExceptionHandler`** takes precedence over global advice for that controller. Across multiple advice beans, `@Order`/scope selectors follow advice resolution rules. Do not compare advice order against `WebFilter`/`WebExceptionHandler` `@Order`.

## 10. Spring Boot ErrorWebExceptionHandler and ProblemDetail

Spring Boot auto-configures `DefaultErrorWebExceptionHandler` (implementing `ErrorWebExceptionHandler`/`WebExceptionHandler`) to handle remaining errors. It uses `ErrorAttributes` and can render JSON or an HTML error view depending on `Accept`/template paths.

For REST APIs, pick a consistent error contract. Spring Framework supports **RFC 9457 Problem Details** via `ProblemDetail`, `ErrorResponse`, and `ResponseEntityExceptionHandler`.

Example for a business exception in an annotated controller:

```java
// Illustrative snippet replacing the @ExceptionHandler method
// in ApiAdvice when adopting RFC 9457.
@ExceptionHandler(DomainFailureException.class)
public ResponseEntity<ProblemDetail> problem(
        DomainFailureException ex) {

    ProblemDetail body = ProblemDetail.forStatus(422);
    body.setTitle("Business rule denied");
    body.setDetail("Request violates a business rule");
    body.setProperty("code", "BUSINESS_RULE");

    return ResponseEntity.status(422).body(body);
}
```

This is a snippet requiring `ProblemDetail` and corresponding annotations/`ResponseEntity` imports, not a complete standalone class. `ProblemDetail` provides standard `type/title/status/detail/instance` fields; responses can use `application/problem+json` through message converters when content negotiation matches.

**Do not try to force all Spring Security error codes into ProblemDetail via a catch-all in advice.** 401/403 carry authentication/authorization semantics (WWW-Authenticate, redirects, credentials/sessions) and should be controlled in the Spring Security chain. You can share one formatter so `ServerAuthenticationEntryPoint`, `ServerAccessDeniedHandler`, and application handlers emit the same schema, implemented **in each respective interface**.

### A Spring Boot 3.x Option

Property `spring.webflux.problemdetails.enabled` enables Problem Details support for standard Boot-managed WebFlux errors. This does not completely replace custom domain mappings or Spring Security entry points/denied handlers. If enabled, check `@ControllerAdvice` ordering relative to framework advice and retest 400/404/405/415 instead of guessing default precedence.

**Never send arbitrary exception messages** to clients if they could contain SQL, file paths, sensitive user IDs, or implementation details. For 500 errors, responses should use a neutral message and correlation ID; internal logs store full errors under proper access controls.

## 11. Debugging: Why Did My Expected Handler Miss the Error?

### 11.1. Error Occurred Before the Controller

Symptom: `@ExceptionHandler(Exception.class)` was never called even though the request returned 500.

Check:

- Did the exception come from a `WebFilter`, CORS, Spring Security, request body codec, or handler mapping?
- Did the request select an annotated handler at all?
- Is a `WebExceptionHandler`/Boot fallback catching the error?
- Did a filter return `Mono.error` or write a response and complete itself?

Action: identify the **error-originating layer**, rather than blindly adding catch-all advice. For specific filter errors, use a custom `WebExceptionHandler` matching the exception type or handle cleanly inside the filter when the contract is clear.

### 11.2. 401/403 Turned Into 500

If controller/method security emits `AccessDeniedException`, an `@ExceptionHandler(Exception.class)` might catch it before Security filters depending on propagation and return 500. Or a custom `WebExceptionHandler` might catch generic `Throwable` and write a 500 body.

Inspect and narrow handlers; let `AuthenticationException`/`AccessDeniedException` flow through security handlers when they are security errors, or define security handlers via the reactive `exceptionHandling(...)` DSL. Never turn 403 into 200 just so the client sees no error.

### 11.3. WebExceptionHandler Did Not Catch the Exception

Possible causes:

- Exception type does not match the handler's `instanceof` check.
- A higher-priority handler handled it first.
- `@ControllerAdvice`/Spring Security handled and completed the response, so the error stopped propagating.
- Response was already committed and cannot be rewritten.
- The error happened outside the request's Reactor pipeline due to manual `subscribe()`, unmanaged schedulers/background tasks, or improperly subscribed I/O.

Never fix this by having the handler catch every `Throwable` and return 200. Use `doOnError`, correlation IDs, and layer-appropriate tests.

### 11.4. Correct HTTP Status but Different Body

- Basic 401 carries `WWW-Authenticate`, and the body may not match the business schema.
- Boot error handler uses content negotiation; `Accept: text/html` may receive HTML.
- Default 404/405/415 usually come from the framework, not `DomainFailureException`.
- If the app enables ProblemDetail, content type may be `application/problem+json`.
- If the response was committed, clients may receive partial bodies or connection resets.
- Proxies/gateways may substitute error pages. Test the app directly and via ingress separately.

### 11.5. Exception Swallowed by onErrorResume

```java
// WRONG: turns an error into normal completion, potentially making clients
// think the request succeeded or leaving a partial response.
return chain.filter(exchange)
        .onErrorResume(error -> Mono.empty());
```

Replace with **type-specific** handling when the filter truly owns it:

```java
// Illustrative snippet: only log then propagate error to global handlers.
return chain.filter(exchange)
        .doOnError(error -> recordFailureType(error));
```

`recordFailureType` here is an application helper recording only safe details; the snippet does not compile standalone. Never use `doOnError` to write responses or alter status codes, because that operator does not convert error signals into responses.

## 12. Controlling Order and Avoiding Omnipotent Handlers

### 12.1. Three Ordering Scopes

| Scope | Component | Ordering |
| --- | --- | --- |
| Global WebFilter | `@Order` or `Ordered` on filter bean | Controls filter position in request chain |
| Spring Security chain | `@Order` on `SecurityWebFilterChain` + `securityMatcher`; `SecurityWebFiltersOrder` inside | Selects chain and internal security filter sequence |
| Global WebExceptionHandler | `@Order` or `Ordered` on handler bean | Determines which handler is tried before fallback |

`@ControllerAdvice` has its own handler-selection system: local controller `@ExceptionHandler` methods usually take precedence over global ones; across multiple advice beans, `@Order`/scope selectors govern handler resolution. Never merge these orders into a single numeric list.

### 12.2. Why Not Create a "Catch-Everything" WebExceptionHandler?

Dangerous example:

```java
// STRATEGICALLY WRONG: swallows every error and fakes success.
@Override
public Mono<Void> handle(ServerWebExchange exchange, Throwable ex) {
    exchange.getResponse().setStatusCode(HttpStatus.OK);
    return exchange.getResponse().setComplete();
}
```

Database errors, JSON parsing failures, authentication, authorization, and response commit failures get hidden. Clients receive 200 despite failed operations; monitoring goes blind; security failures lose their proper statuses.

A good global handler should:

1. Accept only **exception types assigned to it**.
2. Verify the response is not yet committed.
3. Write protocol-compliant status and body without leaking sensitive data.
4. When outside its responsibility, **propagate the error** to the next handler.
5. Handle `onError` cleanly if the handler itself fails, avoiding loops/recursion.
6. Test 401/403 before and after adding the handler.
7. Record error metrics by code/stage, never by raw messages that may contain PII.
8. Keep Boot's fallback so unexpected exceptions are not dropped.

### 12.3. When a Filter Must Intentionally Reject

If a filter enforces an explicit precondition and wants to return 429/503, **writing the response directly from the filter** is sometimes simpler than throwing to a global handler. For instance, a rate limiter can write status 429 and `Retry-After` per its contract.

However, once status/body is written in a filter, **never continue `chain.filter(exchange)`** and never simultaneously emit an exception for a global handler to rewrite. Pick one response owner per execution path.

For **access permissions**, prefer Spring Security `ReactiveAuthorizationManager` and security exception handling; never build a custom filter checking `X-Role` and returning 403 just because it feels easier. Separate business/security/network responsibilities to prevent bypasses.

## 13. Post-Commit Errors, Logging, and Operations

### 13.1. Where to Log?

- **Observability WebFilter:** `doOnError` to log unhandled downstream outcomes, `doFinally` to measure duration.
- **Controller advice:** log business code, HTTP status, and correlation ID; avoid spamming stack traces for expected 4xx errors.
- **WebExceptionHandler:** log unexpected errors in filter/handler layers it owns; distinguish already-committed errors.
- **Security:** use audit/events/metrics for authentication failures, access denied, and CSRF failures without logging credentials.
- **Boot fallback:** keep observability for unhandled 500 errors.

Avoid **duplicate logging**: one error can pass through a filter, custom handler, and global fallback. Use a consistent correlation ID/request ID and event type so the same exception is not counted three times as three incidents.

### 13.2. Stable API Error Codes

Prefer:

```json
{
  "code": "BUSINESS_RULE",
  "message": "Request violates a business rule"
}
```

or standard `ProblemDetail`/RFC 9457. Never use `Throwable.getMessage()` as the `code` field, because messages change across versions, contain private data, or are hard to translate. If adding a request ID, obtain it from a trusted source and sanitize before echoing.

### 13.3. Preventing Information Leakage Through Errors

Never return to clients:

- Java stack traces or internal package/class names.
- SQL queries, database hostnames/passwords, secrets, session IDs.
- Authorization/Bearer tokens or `SESSION` cookies.
- Overly specific "this account exists" / "account locked" login details that assist enumeration.
- Unredacted raw URLs/queries from requests containing sensitive data.
- Internal ACL/tenant policy details that should stay private.

Spring Boot apps have `server.error.include-message`, `server.error.include-stacktrace`, and other error options. Never enable settings that dump raw stack traces/messages into production responses.

### 13.4. Distinguishing Application Errors from Protocol Errors

Some errors have different owners:

| Error | Appropriate owner |
| --- | --- |
| Malformed JSON body | WebFlux binding/codec handling, built-in error response, or intentional advice |
| No handler 404 | DispatcherHandler/Boot fallback/status handler per version |
| Unsupported HTTP method 405 | WebFlux mapping & error response |
| Invalid business state 422 | Domain `@ExceptionHandler`/`@RestControllerAdvice` |
| Filter dependency outage 503 | Intentional filter handling or custom `WebExceptionHandler` |
| Uncaught IllegalStateException 500 | Global `WebExceptionHandler`/Boot fallback |
| Unauthenticated 401 | Spring Security `ServerAuthenticationEntryPoint` |
| Wrong authentication credentials | Authentication failure handler/entry point depending on mechanism |
| Authenticated, insufficient permission 403 | Spring Security `ServerAccessDeniedHandler` |
| Invalid CSRF token 403 | Spring Security `CsrfWebFilter` |
| Mid-stream error after commit | Streaming protocol/connection termination; cannot change HTTP status |

A functional `RouterFunction` endpoint should rely on functional pipeline error handling or global handlers rather than assuming annotated `@RestControllerAdvice` is always invoked.

## 14. Pre-Production Verification Checklist

1. **Which stage owns the error?** Pre-filter, security, handler mapping, annotated controller, functional handler, DB, or streaming response.
2. **Is there a specific handler?** Domain exceptions mapped in advice; dedicated filter types in WebExceptionHandler; Boot fallback for unexpected ones.
3. **Are auth statuses compliant?** 401 preserves challenges/redirects properly; 403 never turns into 200/500.
4. **One owner per response:** Never double-write bodies; never continue the chain after a filter ends the response.
5. **Check isCommitted:** Never write new status/body after commit.
6. **Clear ordering:** Global WebFilter, SecurityWebFilterChain, and WebExceptionHandler have separate priorities.
7. **Stable error codes:** Use codes/schemas or ProblemDetail; never return raw exception text.
8. **Do not swallow Mono.error:** No broad `onErrorResume(e -> Mono.empty())`, no `onErrorReturn(success)`.
9. **Never block the event loop:** No `block()`, synchronous JDBC/HTTP clients inside error handlers; response writes compose `Mono<Void>`.
10. **Negative tests written:** Business 422, filter 503, unexpected 500, Basic 401, role 403, CSRF 403 where applicable.
11. **Post-commit tests:** Streaming/SSE, partial body, connection close, client timeout, and proxy behavior.
12. **No data leaks:** Safe logs, masked headers/PII, no exposed stack traces.
13. **Do not change defaults blindly:** Enabling ProblemDetail or custom error handlers requires regression checks for 404/405/415/validation/CSRF.
14. **Observability:** Metrics by route/status/error code/correlation ID and tracking which handler processed it.

## 15. Self-Check Questions

**1. Does an error from a WebFilter running before DispatcherHandler automatically fall into @ControllerAdvice?**  
Do not expect it to. `@ControllerAdvice` belongs to annotated controller error handling; pre-routing filter errors normally need handling in the filter or `WebExceptionHandler`.

**2. How does @RestControllerAdvice differ from WebExceptionHandler?**  
Advice uses `@ExceptionHandler` inside the annotated controller model; WebExceptionHandler is the global WebFlux handler component for unresolved errors from WebFilters/WebHandlers.

**3. If @ControllerAdvice already handled DomainFailureException, does WebExceptionHandler still see that error?**  
Normally no, because the error has already been converted into a completed response at the advice layer. WebExceptionHandler is for unhandled error signals.

**4. Why should an unauthenticated Basic request return 401 rather than turning all errors into 500?**  
It is an authentication requirement that must go through `ServerAuthenticationEntryPoint`/security mechanisms. 500 indicates a server error, not missing client credentials.

**5. A user with ROLE_USER sends GET /api/admin in the demo; what responds?**  
Spring Security authorization/access-denied handler returns 403; the controller does not run.

**6. In a WebExceptionHandler, what should you do when an error type is not recognized?**  
Return `Mono.error(error)` so the next handler processes it. Never use `Mono.empty()` to pretend it was handled.

**7. When isCommitted() == true, can you change status from 200 to 500?**  
No. Headers/status were already sent, so the response cannot be rewritten. Handle per streaming/connection semantics and observe the error.

**8. Can @Order(-200) on a WebFilter and @Order(-2) on a WebExceptionHandler be compared directly?**  
No. They belong to two separate chains with different roles.

**9. Why not write @ExceptionHandler(Exception.class) returning 200 "OK"?**  
It hides business/security/framework errors and misleads clients about state; it can lead to bypasses or blind monitoring.

**10. When Boot fallback returns HTML instead of JSON, is @ControllerAdvice broken?**  
Not necessarily. Boot's error handler uses content negotiation; check `Accept`, `server.error.*`, and whether the exception is within advice's scope.

**11. Are errors from functional RouterFunctions automatically caught by annotated controller @RestControllerAdvice?**  
Do not assume so. Use functional pipeline error handling or a global `WebExceptionHandler` when needed.

**12. Why must both 401 and 403 be tested after adding a custom WebExceptionHandler?**  
To verify the new handler does not swallow security errors, break challenges/redirects, or turn denials into 500/200.

**13. Is Mono.empty from a WebFilter an error or success?**  
Normally completing `Mono.empty()`/`Mono<Void>` is just completion, not an error signal. If a filter completes early without setting an appropriate response, the client may get an unexpected response.

**14. Should CSRF 403 be routed into @RestControllerAdvice to return a different status?**  
Not by default. Fix the token/session/method or customize the security handler in the right place rather than using business advice to bypass CSRF.

**15. How do you prove the controller did not run on /api/filter-fail?**  
It has a handler that would return `CONTROLLER_WAS_CALLED`, yet the test receives 503 with code `FILTER_FAILURE` from WebExceptionHandler; the filter intercepted the flow before the controller.

**In summary:** To return accurate error responses in Spring Security WebFlux, you must know **where the error originated, which signal remains unhandled, and whether the response is already committed**. Business exceptions from annotated controllers belong to `@ControllerAdvice`; unhandled pre-routing/filter errors belong to `WebExceptionHandler` or intentional filter handling; 401/403 belong to Spring Security entry point/denied handlers; remaining unexpected errors go to Spring Boot fallback. Designing clear boundaries preserves HTTP semantics, information security, and debuggability.

## References

- [Spring Framework — WebFlux Reactive Core / Exceptions](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html): `WebFilter`, `WebExceptionHandler`, WebHandler chain, and `@Order`.
- [Spring Framework — WebFlux @ControllerAdvice](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-advice.html): annotated controller scope, local/global `@ExceptionHandler`, `@RestControllerAdvice`.
- [Spring Framework — DispatcherHandler Exceptions](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/dispatcher-handler.html): exception handling in handler adapters, result handling, and dispatch pipeline.
- [Spring Framework — WebFlux Error Responses](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/ann-rest-exceptions.html): `ProblemDetail`, `ErrorResponse`, `ResponseEntityExceptionHandler`, RFC 9457.
- [Spring Boot 3.3.13 — DefaultErrorWebExceptionHandler API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/reactive/error/DefaultErrorWebExceptionHandler.html): fallback errors, JSON, and HTML.
- [Spring Boot — Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html): Boot's WebExceptionHandler position, WebFilter order, and error handling.
- [Spring Security 6.3 — ServerHttpSecurity.ExceptionHandlingSpec API](https://docs.spring.io/spring-security/site/docs/6.3.3/api/org/springframework/security/config/web/server/ServerHttpSecurity.ExceptionHandlingSpec.html): `authenticationEntryPoint` and `accessDeniedHandler`.
- [Spring Security — ExceptionTranslationWebFilter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authorization/ExceptionTranslationWebFilter.html): translating authorization denials into HTTP security responses.
- [Spring Security — WebFlux HTTP Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): security chain, access rules, and denial.
- [Spring Security — Reactive CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): pre-controller CSRF errors.
- [Spring Framework — WebExceptionHandler API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/server/WebExceptionHandler.html): `Mono<Void> handle(exchange, ex)` contract.
