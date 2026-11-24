# Mono, Flux, and Publisher in the Spring Security WebFlux Processing Flow

## Objectives

This lesson helps you understand `Publisher<T>`, `Mono<T>`, and `Flux<T>`, trace the authentication/authorization flow in Spring Security WebFlux, access the identity via `Reactor Context`, choose appropriate reactive operators, and avoid pitfalls such as `block()`, manual `subscribe()`, or misunderstanding `Mono.empty()`.

## 1. Why Does the WebFlux Security Flow Use Publisher?

In Spring MVC/Servlet, request processing is typically programmed synchronously, and the application can rely on a single thread to hold `SecurityContext` via `ThreadLocal`. In Spring WebFlux, a request passes through multiple asynchronous I/O operations and may switch threads. Therefore, reactive Spring Security integrates with Reactor to keep authentication data bound to the **request's subscription**, rather than assuming the identity is fixed to a thread.

`SecurityWebFilterChain` protects the HTTP exchange. Filters, authenticators, and controllers compose through publishers so that the framework manages subscribing for signals, execution, errors, and request cancellation. Returning a `Mono` or `Flux` **does not automatically turn a blocking operation into a non-blocking one**; query drivers, HTTP clients, and called libraries must also be suitable.

## 2. Distinguishing Publisher, Mono, and Flux

| Type | Number of `onNext` elements | Security examples |
| --- | --- | --- |
| `Publisher<T>` | Generic interface, does not specify quantity | Reactive Streams contract for a `Subscriber` to subscribe to |
| `Mono<T>` | 0 or 1 | `Mono<Authentication>`, `Mono<SecurityContext>`, a single query result |
| `Flux<T>` | 0 to many | `Flux<Report>` or records returned after authorization checks |
| `Mono<Void>` | No value elements | `WebFilter.filter(...)` chain completes or signals an error |

`org.reactivestreams.Publisher<T>` defines `subscribe(Subscriber)`. Reactor implements this interface with `Mono` and `Flux`, along with operators such as `map`, `flatMap`, `filter`, `switchIfEmpty`, and `onErrorResume`.

A subscription has the following primary signals:

1. `onSubscribe`: receives the `Subscription`; the subscriber can request a number of elements via `request(n)`.
2. `onNext(value)`: receives a value, at most once for `Mono`.
3. `onComplete`: completes normally. `Mono.empty()` emits no `onNext` but still completes.
4. `onError(error)`: terminates with an error; no `onComplete` is emitted after `onError`.
5. `cancel()`: downstream cancels interest; upstream should stop work and release resources.

Most Reactor publishers are created from cold sources: work is triggered on subscription and may run again when subscribed to again. Hot sources or shared/cached publishers are exceptions. **Subscription is a data-processing mechanism, not a form of granting authorization**.

How to choose: return `Mono` when the logic produces at most one result (one identity or one record); return `Flux` when the logic produces multiple results; return `Mono<Void>` when only a completion signal is needed, such as in an HTTP filter. Do not use `Flux` just because you want "asynchronous": `Mono` is also asynchronous.

## 3. Where Do Publishers Sit in the Authentication/Authorization Flow?

This is a **conceptual** diagram; it does not assert that every request passes through all filters or follows an identical order in every configuration:

```text
HTTP request
  |
  v
ServerWebExchange -> SecurityWebFilterChain / WebFilter
  |
  +--> Extract credentials from request (if present)
  |       ServerAuthenticationConverter -> Mono<Authentication>
  |
  +--> ReactiveAuthenticationManager.authenticate(...)
  |       Mono<Authentication>: success / empty / error
  |
  +--> SecurityContext in Reactor Context
  |       may integrate ServerSecurityContextRepository
  |       depending on security context storage/restoration mechanism
  |
  +--> Authorization for HTTP exchange or method
  |       authorized: continue; unauthorized: deny
  |
  v
Controller/Service -> Mono<T> or Flux<T>
  |
  v
Framework subscribes, writes HTTP response
WebFilterChain completes with Mono<Void>
```

Role of each component:

- `SecurityWebFilterChain` is configured by `ServerHttpSecurity`; it is the **WebFlux** filter chain, distinct from `SecurityFilterChain` for Servlet.
- `AuthenticationWebFilter` can use `ServerAuthenticationConverter` to create an `Authentication` and then invoke `ReactiveAuthenticationManager` for matching requests. If there are no credentials or the filter does not match, this branch can be skipped.
- `ReactiveAuthenticationManager` verifies credentials and returns a publisher of the authenticated `Authentication` object.
- `ReactiveSecurityContextHolder` reads/sets `SecurityContext` in the flow's Reactor Context.
- `authorizeExchange` and reactive method security perform **authorization**, meaning evaluating whether access is allowed.
- `WebFilter.filter(ServerWebExchange, WebFilterChain)` returns `Mono<Void>` to indicate request processing completion/error. It does not return a boolean "allowed".

**Authentication** asks "who is the user?"; **authorization** asks "what is the user allowed to do?". Having valid credentials does not guarantee access to every resource.

### Three Cases of `Mono<Authentication>`

Per the `ReactiveAuthenticationManager.authenticate(...)` contract:

- Success: the publisher emits a valid `Authentication` and then completes.
- `Mono.empty()`: the manager **cannot determine** authentication for the input, for example an unsupported token type.
- `Mono.error(...)`: the manager attempted authentication and **failed** (e.g., `BadCredentialsException`).

Do not convert all password errors into `Mono.empty()` using a blanket `onErrorResume`. In a **controller** or repository, `Mono.empty()` can simply mean "no data found". Do not infer 401, 403, or "allow" directly from an empty `Mono`; the HTTP status code is decided by Spring Security and the exception handling/entry point configuration.

## 4. Reactor Operators to Know When Reading Security Code

| Operator | Purpose | Example |
| --- | --- | --- |
| `map` | Synchronously transform a value | `Authentication -> username` |
| `flatMap` | Transform a value into another `Mono` and chain it | Load a profile using a reactive repository |
| `flatMapMany` | Transform a `Mono` result into a `Flux` | Fetch multiple records by authenticated username |
| `filter` | Keep elements matching a condition | Filter data; does not replace endpoint security |
| `switchIfEmpty` | Branch when no value is emitted | Choose an appropriate response for not-found cases |
| `onErrorResume` | Branch to handle specific errors | Intentionally recover from business errors |
| `defer`, `deferContextual` | Create a publisher at subscription time, optionally reading context | Avoid eager computation |
| `contextWrite` | Add Reactor Context entries visible upstream | Supply data for the subscription |
| `doOnNext`, `doOnError` | Observe signals | Controlled logging/auditing, without extra subscriptions |
| `concatMap` | Chain inner publishers sequentially | Preserve processing order when required |

The Java 17+ example below is **a standalone console program in source code**, requiring the `reactor-core` library on the classpath. In a Spring Boot WebFlux project, that dependency is already pulled in transitively:

**`src/main/java/demo/ReactorSignalsDemo.java`**

```java
package demo;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class ReactorSignalsDemo {
    public static void main(String[] args) {
        Mono<String> user = Mono.just("linh")
                .map(String::toUpperCase);

        Flux<Integer> ids = Flux.just(1, 2, 3)
                .filter(id -> id != 2)
                .map(id -> id * 10);

        System.out.println(user.block());
        System.out.println(ids.collectList().block());
    }
}
```

Exact stdout:

```text
LINH
[10, 30]
```

`block()` in this example **is only for a console/test program**. Do not use it on the WebFlux HTTP processing path. For asynchronous I/O, chain publishers with `flatMap`. The following snippet sits **inside a method returning `Mono<Profile>`**, assuming the repository provides `Mono<Profile> findByUsername(String)`:

```java
return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication().getName())
        .flatMap(username -> profileRepository.findByUsername(username));
```

Using `map` at the repository call step would produce `Mono<Mono<Profile>>`; `flatMap` yields `Mono<Profile>` as required by the contract.

## 5. Reactor Context: Where the Identity Travels

In a reactive application, read the principal with:

```java
Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
            .map(ctx -> ctx.getAuthentication().getName());
}
```

This is an **illustrative method snippet** placed inside a component handling a reactive request with a context. `ReactiveSecurityContextHolder.getContext()` returns `Mono<SecurityContext>`; do not use synchronous `SecurityContextHolder.getContext()` assuming a request always runs on one thread.

Understand Reactor Context accurately:

1. Context is attached to the **subscriber/subscription** and can follow the chain when Reactor switches threads, rather than being a global thread-local variable.
2. Context is immutable in the sense that mutation methods return a new context; `contextWrite` creates a context for **upstream** relative to that operator's position.
3. Spring Security attaches the context through its authentication filter mechanism. In a unit test or standalone publisher, you can use `ReactiveSecurityContextHolder.withAuthentication(authentication)`.
4. Reactor Context only represents context while processing a subscription; it is **not** a mechanism to store sessions or tokens for subsequent requests.
5. When integrating callbacks, executors, or APIs outside Reactor, check how context is propagated; do not assume it automatically follows every thread.

Basic Context illustration:

```java
Mono<String> trace = Mono.deferContextual(ctx ->
        Mono.just("user=" + ctx.get("username")))
    .contextWrite(ctx -> ctx.put("username", "linh"));

// In main or a test, trace.block() produces the string: "user=linh".
```

The `username` key here is only for learning `Context`. **Setting this key yourself does not mean the user has been authenticated.** When working with Spring Security, use `ReactiveSecurityContextHolder` together with actual managers and authentication rules.

## 6. WebFlux Example: Public Endpoint, Identity, and Reports

Use Spring Boot with Java 17+, including `spring-boot-starter-webflux` and `spring-boot-starter-security`. In a Gradle Spring Boot project with plugins/dependency management configured:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
```

Do not also add `spring-boot-starter-web` for this example: when both MVC and WebFlux are present, Spring Boot normally selects a Servlet application unless the application type is explicitly configured.

**`src/main/java/demo/securityreactive/DemoApplication.java`** (a Java 17+ file with one public class):

```java
package demo.securityreactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

@Configuration
@EnableWebFluxSecurity
class SecurityConfig {
    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public").permitAll()
                        .pathMatchers("/reports").hasRole("ANALYST")
                        .anyExchange().authenticated()
                )
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails viewer = User.withUsername("viewer")
                .password(encoder.encode("viewer-pass"))
                .roles("VIEWER")
                .build();
        UserDetails analyst = User.withUsername("analyst")
                .password(encoder.encode("analyst-pass"))
                .roles("ANALYST")
                .build();
        return new MapReactiveUserDetailsService(viewer, analyst);
    }
}

@RestController
class DemoController {
    @GetMapping("/public")
    Mono<String> publicMessage() {
        return Mono.just("public");
    }

    @GetMapping("/me")
    Mono<String> currentUser() {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(authentication -> "hello " + authentication.getName());
    }

    @GetMapping("/reports")
    Flux<Report> reports() {
        return Flux.just(
                new Report("R1", "internal"),
                new Report("R2", "internal")
        );
    }
}

record Report(String id, String classification) {}
```

Run in a project with Gradle Wrapper using `./gradlew bootRun` (PowerShell: `.\gradlew.bat bootRun`). The sample cannot compile with standalone `javac` without the Spring/Reactor libraries; Gradle provides that classpath. Package-private classes and a record in the same file are valid in Java 17.

Try the following requests:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u viewer:viewer-pass http://localhost:8080/me
curl -i -u viewer:viewer-pass http://localhost:8080/reports
curl -i -u analyst:analyst-pass http://localhost:8080/reports
```

| Request | Expected result | Explanation |
| --- | --- | --- |
| `GET /public`, anonymous | `200`, body `public` | `permitAll()` |
| `GET /me`, anonymous | `401` per HTTP Basic in the example | Not authenticated |
| `GET /me`, viewer | `200`, body `hello viewer` | Authenticated, principal read from Reactor Context |
| `GET /reports`, viewer | `403` | Authenticated but missing `ROLE_ANALYST` |
| `GET /reports`, analyst | `200`, report data | Has `ROLE_ANALYST` |

`roles("ANALYST")` generates the `ROLE_ANALYST` authority, so `hasRole("ANALYST")` automatically applies the `ROLE_` prefix. Error body/header formatting depends on configuration and content negotiation; what needs to be verified here is the **access boundary**.

Hardcoded accounts/passwords are strictly for local learning. In production, manage credentials securely and do not keep sample passwords in source code. This example only uses `GET`; **do not arbitrarily disable CSRF** for browser applications using cookies/sessions.

### Tracing `GET /reports`

1. The request enters WebFlux and the security filters.
2. HTTP Basic converts matching credentials into an `Authentication`; the manager verifies them.
3. The `hasRole("ANALYST")` rule is evaluated before the controller is invoked.
4. If authorization fails, access is denied. If authorized, the controller returns `Flux<Report>` with two elements.
5. The framework subscribes and encodes the result into an HTTP response. The controller **does not call `subscribe()` itself**.

Returning `Flux<Report>` only means multiple business elements. It **does not guarantee** the system re-checks authorization on each individual record. If records have separate owners or sensitivity levels, you must design query conditions and per-record authorization checks; endpoint filters are only one layer of protection.

## 7. Testing Reactor Context with StepVerifier

To verify that a publisher can read the identity within a subscription without starting an HTTP server, create the following test file. It requires `spring-boot-starter-test` and `reactor-test` as declared:

**`src/test/java/demo/securityreactive/ReactiveContextTest.java`**

```java
package demo.securityreactive;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactiveContextTest {
    @Test
    void readsAuthenticatedPrincipalFromContext() {
        Authentication authentication =
                new UsernamePasswordAuthenticationToken(
                        "linh",
                        "unused",
                        List.of(new SimpleGrantedAuthority("ROLE_USER"))
                );

        Mono<String> username = ReactiveSecurityContextHolder.getContext()
                .map(ctx -> ctx.getAuthentication().getName())
                .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(authentication)
                );

        StepVerifier.create(username)
                .expectNext("linh")
                .verifyComplete();
    }
}
```

Run `./gradlew test --tests demo.securityreactive.ReactiveContextTest` (PowerShell: `.\gradlew.bat test --tests demo.securityreactive.ReactiveContextTest`). The test should PASS: `StepVerifier` subscribes, observes the exact value `linh`, and then `onComplete`. This is a context propagation test, **not** a password verification or HTTP 401/403 test; endpoints must be tested separately.

## 8. Common Pitfalls

| Pitfall | Consequence | Fix |
| --- | --- | --- |
| `block()`, `blockFirst()`, `blockLast()` in controller/WebFilter | Blocks the event loop or throws an error on non-blocking threads | Return the publisher and chain with `flatMap`, `concatMap` |
| Manual `subscribe()` in controller/filter | Loses management of response lifecycle, errors, cancellation, or context | Return `Mono`/`Flux` so the framework subscribes |
| Servlet-style `SecurityContextHolder.getContext()` | May be missing or read the wrong principal due to thread switching | Use `ReactiveSecurityContextHolder.getContext()` |
| `map` with a function returning `Mono` | Produces `Mono<Mono<T>>` | Use `flatMap` |
| Swallowing `AuthenticationException` with `onErrorResume(... -> Mono.empty())` | Hides invalid credentials and violates the manager contract | Distinguish unsupported tokens from failed authentication |
| Assuming `Flux.filter(...)` suffices for record-level authorization | May leak information in other services/queries | Enforce authorization at the endpoint, service, and data-fetch conditions |
| Placing `contextWrite` in the wrong position | Downstream operators do not see the new value | Remember Context propagates from subscriber upstream |
| `Mono.just(blockingCall())` | Blocking function runs eagerly when assembling the publisher | Use non-blocking sources or defer/offload blocking properly |
| Using `flatMap` and assuming order is always preserved | Inner tasks may complete out of order | Use `concatMap` when order matters |

Several advanced scenarios also require attention:

- **Backpressure:** `request(n)` regulates data demand between compatible subscribers and publishers. It is not a request limit/rate limit and does not replace authorization.
- **Cancellation:** when a client disconnects a stream, the reactive source should stop work and release resources; do not spawn detached subscriptions that make this difficult.
- **Long-lived streams:** checking authorization at the start of an HTTP request does not mean automatically re-checking when a role is revoked while the stream remains open. For immediate revocation requirements, design re-checks/stream termination.
- **Blocking sources:** synchronous JDBC or a blocking SDK does not become non-blocking merely by wrapping it in `Mono`. Prefer reactive drivers or controlled blocking isolation, while also verifying context propagation.
- **Method security:** you can use `@EnableReactiveMethodSecurity` and `@PreAuthorize` on methods returning `Mono`/`Flux`. Verify the method actually goes through the Spring proxy and write tests for permissions; internal calls within the same bean may bypass the proxy.

## 9. Self-Check Exercises

1. Add `GET /profile` returning `Mono<String>` containing the username. Prove that anonymous requests are blocked and valid accounts read the correct identity.
2. Add an `AUDITOR` role and an endpoint restricted to that role. Test and distinguish 401 (unauthenticated) from 403 (authenticated but lacking permission).
3. Replace `Flux.just(...)` with a reactive repository query filtered by the authenticated username; test one user trying to access another user's records.
4. Write a `StepVerifier` test for cases with and without Reactor Security Context; explain why `Mono.empty()` does not automatically mean HTTP 403.
5. Create a slow `Flux` and cancel the subscription in a test; observe producer termination and cleanup.

**Remember:** `Publisher` defines the signal emission contract; `Mono`/`Flux` describe the cardinality of values; Spring Security governs authentication/authorization within that pipeline. Read the identity via Reactor Context, let the framework manage subscriptions, and apply authorization checks at the appropriate business layers.

## Official References

- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring Security API — ReactiveAuthenticationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ReactiveAuthenticationManager.html)
- [Spring Security API — ReactiveSecurityContextHolder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html)
- [Project Reactor — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
