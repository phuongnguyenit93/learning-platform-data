# ReactiveSecurityContextHolder and Reactor Context

## 1. Goal and Problem Statement

In a Spring Security application running on **Spring WebFlux**, a request can pass through many `Mono`/`Flux` operators, be processed on different threads, and still need to know **who is authenticated**. `ReactiveSecurityContextHolder` is the API for accessing the `SecurityContext` of a reactive processing flow via the **Reactor Context**.

After this lesson, you should be able to distinguish `SecurityContext` from Reactor `Context`, read `Authentication` in a pipeline, understand where to place `contextWrite`, recognize the scope of each subscription, and test context propagation without depending on the current thread.

**Scope:** Spring Security 6.x with Java 17+ and Reactor 3.x (aligned with the Spring Boot 3.x ecosystem). Several of these APIs remain available in newer versions.

## 2. Two Types of Context with Different Responsibilities

- `Authentication`: represents the principal, authorities, authentication status, and information related to an authentication.
- `SecurityContext`: a Spring Security object holding `Authentication` (`getAuthentication()` and `setAuthentication()`).
- `reactor.util.context.Context`: a key–value collection serving a reactive processing sequence; it travels with the **Subscriber/subscription**, not bound permanently to a single Java thread.
- `ReactiveSecurityContextHolder`: Spring Security's bridge for storing/retrieving a `Mono<SecurityContext>` in the Reactor Context through a public API. You do not need to know Spring Security's internal key directly.

| Aspect | Standard synchronous Servlet | WebFlux using Reactor |
| --- | --- | --- |
| Where security context is typically read | `SecurityContextHolder.getContext()` | `ReactiveSecurityContextHolder.getContext()` |
| Primary context propagation mechanism | `ThreadLocal` with the default holder strategy | Reactor Context attached to the subscription |
| When switching threads | Requires an appropriate `ThreadLocal` propagation mechanism | Reactor Context can still propagate across Reactor operators within the same subscription |
| How data is received | Call returns the object directly | `Mono<SecurityContext>` must be composed into the pipeline |

**Do not conflate the two Context types:** Reactor Context is the data transport mechanism; `SecurityContext` is the security data being transported. Reactor `Context` is structurally immutable (`put`/`delete` produce a new Context), whereas objects placed inside it such as `SecurityContextImpl` are not immutable by default.

## 3. How Does Context Follow a Subscription?

A reactive sequence is declared first and only executes when there is a subscriber. `contextWrite(...)` modifies the context seen by **upstream operators** as the subscribe signal travels from downstream to upstream.

```text
Subscriber / WebFlux runtime
        |
        | subscribe + Reactor Context
        v
contextWrite(withAuthentication(auth))
        |
        | Context propagated upstream
        v
flatMap(...) -> ReactiveSecurityContextHolder.getContext()
        |
        v
Authentication -> username / authorities
```

When using `publishOn`, `subscribeOn`, or switching threads through Reactor operators, context data is not tied to the old thread, provided the work stays within the connected and properly subscribed reactive sequence. **An independent `subscribe()` call creates a separate subscription** and does not automatically receive all context from the sequence that invoked it.

Example of operator placement:

```java
// CORRECT: the read is upstream of contextWrite.
Mono<String> ok = readUserName()
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth));

// UNINTENDED: readUserName() is created inside flatMap downstream
// of the contextWrite below; it does not see the Context applied only upstream.
Mono<String> missing = Mono.just("go")
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth))
    .flatMap(ignored -> readUserName());
```

`readUserName()` is an illustrative method returning `Mono<String>` that reads `ReactiveSecurityContextHolder`. The snippet above illustrates operator placement, not a standalone Java program. Place the Context-populating operation at the appropriate boundary of the entire sequence that needs to use it.

## 4. Core API of ReactiveSecurityContextHolder

| API | Meaning | Key takeaway |
| --- | --- | --- |
| `getContext()` | Returns a `Mono<SecurityContext>` read from the subscriber's Reactor Context | If no context is present, the `Mono` may complete without emitting a value |
| `withAuthentication(authentication)` | Creates a Reactor `Context` containing a `SecurityContext` from `Authentication` | Used with `.contextWrite(...)`; does not update global state |
| `withSecurityContext(Mono<? extends SecurityContext>)` | Creates a Reactor `Context` from a `SecurityContext` publisher | Useful when the context is supplied asynchronously |
| `clearContext()` | Returns a Context transformation function to remove the security context in the applied scope | Not equivalent to logging out or revoking tokens/sessions |

A safe way to read when `SecurityContext` or `Authentication` may be absent:

```java
Mono<String> userName = ReactiveSecurityContextHolder.getContext()
    .flatMap(sc -> Mono.justOrEmpty(sc.getAuthentication()))
    .map(Authentication::getName)
    .defaultIfEmpty("unknown");
```

`Mono.justOrEmpty(...)` avoids emitting `null` into Reactor (Reactor does not allow `null` elements). `defaultIfEmpty` handles the case with no value; pipeline errors still propagate as errors. Do not assume that `isAuthenticated() == true` always means a real user has logged in: some `Authentication` types such as anonymous have their own semantics. Access-control rules must come from Spring Security authorization.

## 5. Runnable Java 17+ Example: Context Survives Thread Switching

The code below is a standalone Java program **when the project already has** `org.springframework.security:spring-security-core` and `io.projectreactor:reactor-core` on the classpath; with Spring Boot 3, the BOM can manage versions. File located at `src/main/java/example/ReactiveContextDemo.java`.

```java
package example;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public final class ReactiveContextDemo {
    private static Mono<String> currentUserName() {
        return ReactiveSecurityContextHolder.getContext()
            .flatMap(sc -> Mono.justOrEmpty(sc.getAuthentication()))
            .map(Authentication::getName)
            .defaultIfEmpty("(no Authentication)");
    }

    public static void main(String[] args) {
        // Simulated authenticated token for demonstration purposes;
        // a real application must authenticate through Spring Security mechanisms.
        Authentication user = UsernamePasswordAuthenticationToken.authenticated(
            "linh",
            null,
            AuthorityUtils.createAuthorityList("ROLE_READER")
        );

        Mono<String> pipeline = Mono.just("request")
            .publishOn(Schedulers.parallel())
            .flatMap(ignored -> currentUserName());

        String withContext = pipeline
            .contextWrite(ReactiveSecurityContextHolder.withAuthentication(user))
            .block();

        String withoutContext = pipeline.block();

        System.out.println(withContext);
        System.out.println(withoutContext);
    }
}
```

**Exact stdout:**

```text
linh
(no Authentication)
```

Explanation:

1. `pipeline` switches subsequent processing to another scheduler via `publishOn`.
2. The first subscription attaches an `Authentication` to the Reactor Context via `contextWrite`; `currentUserName()` reads `linh`.
3. The second subscription uses **the same pipeline** without attaching a security context, so it receives only the default value. Both `block()` calls here serve the console demo program; **do not use `block()` in WebFlux request processing**.
4. `UsernamePasswordAuthenticationToken.authenticated(...)` only simulates a completed authentication result. Do not construct this token directly from user input to grant privileges in a real application.

If the project configures the Gradle `application` plugin with main class `example.ReactiveContextDemo`, it can be run with `./gradlew run`; you cannot use plain JDK `javac` without putting the Reactor/Spring Security JARs on the classpath.

## 6. Using in Real WebFlux Requests

With properly configured Spring WebFlux and Spring Security, the security web filters place the authenticated request's `SecurityContext` into the Reactor Context. For instance, `ReactorContextWebFilter` uses `ServerSecurityContextRepository` to initialize the appropriate context. Therefore, in a service/controller returning `Mono` or `Flux`, you normally only need to **read** the context rather than calling `withAuthentication` yourself for each request.

The controller example below uses Spring WebFlux and Spring Security in an application with authentication configured. File `WhoAmIController.java`:

```java
package example;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@RestController
public class WhoAmIController {
    @GetMapping("/me")
    public Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
            .flatMap(sc -> Mono.justOrEmpty(sc.getAuthentication()))
            .map(Authentication::getName)
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                    HttpStatus.UNAUTHORIZED, "Missing Authentication"
                )
            ));
    }
}
```

A minimal WebFlux Security configuration for that endpoint (file `WebSecurityConfig.java`):

```java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableWebFluxSecurity
public class WebSecurityConfig {
    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(ex -> ex
                .pathMatchers("/me").authenticated()
                .anyExchange().permitAll())
            .httpBasic(withDefaults())
            .build();
    }
}
```

The project also needs to configure a valid user source or authentication mechanism (for example, a reactive user details service, OAuth2 Resource Server, etc.). The snippet above **does not** create a demo user or configure credentials. On an endpoint requiring authentication, the security filter chain blocks unauthorized requests before the controller according to the declared policy. Do not use controller code as the sole authorization layer.

You can retrieve user information via `Principal`/`@AuthenticationPrincipal` when appropriate; `ReactiveSecurityContextHolder` is especially useful in components deep inside a reactive pipeline that do not have direct HTTP parameters.

## 7. Attaching an Existing SecurityContext and Clearing Within a Sequence Scope

In tests, background tasks with an explicit policy, or special integration flows, you can actively attach a context:

```java
// Illustrative snippet placed where an Authentication auth variable
// and a Mono<String> readUserName() method already exist.
SecurityContext securityContext = new SecurityContextImpl(auth);

Mono<String> scoped = readUserName()
    .contextWrite(ReactiveSecurityContextHolder.withSecurityContext(
        Mono.just(securityContext)
    ));
```

You need to import `org.springframework.security.core.context.SecurityContext`, `SecurityContextImpl`, and `reactor.core.publisher.Mono`. `withSecurityContext` accepts `Mono<? extends SecurityContext>`, while `withAuthentication` is shorthand when you already have an `Authentication`.

If you need to drop the security context within only one reactive region:

```java
Mono<String> cleared = readUserName()
    .contextWrite(ReactiveSecurityContextHolder.clearContext())
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth));
```

In this sequence, the `clearContext` operation closer to the read removes the security context from that upstream portion. **Do not use `clearContext()` instead of logout:** logging out also depends on invalidating the session, deleting cookies, revoking tokens, or the application's security context storage policy.

Do not mutate a `SecurityContextImpl` that is being shared across subscriptions. If you must change the identity or authorities, establish the appropriate context at the processing boundary using an object scoped to the request/subscription lifecycle.

## 8. Relationship with Reactive Method Security

`@EnableReactiveMethodSecurity` enables applying annotations such as `@PreAuthorize` to reactive methods; Spring Security uses the Reactor Context to obtain authentication information at subscription time.

```java
@Configuration
@EnableReactiveMethodSecurity
class ReactiveMethodSecurityConfig {}

@Service
class ReportService {
    @PreAuthorize("hasRole('READER')")
    public Mono<String> getReport() {
        return Mono.just("Protected report");
    }
}
```

The imports belong to `org.springframework.context.annotation`, `org.springframework.stereotype.Service`, `org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity`, `org.springframework.security.access.prepost.PreAuthorize`, and `reactor.core.publisher.Mono`. These are two Spring components within the same application, not a self-contained runnable Java file; invoke through a Spring-managed bean so the method-security proxy/interceptor works. In the common reactive model, the protected method returns `Mono` or `Flux`; do not convert it to a synchronous value and expect the reactive context to remain available.

`hasRole('READER')` checks the `ROLE_READER` authority. HTTP-level authorization (`authorizeExchange`) and method-level authorization (`@PreAuthorize`) can work together, but each layer must be configured properly.

## 9. Testing the Context of Two Subscriptions

In a project with `reactor-test`, JUnit Jupiter, and `spring-security-core`, file `src/test/java/example/ReactiveContextTest.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactiveContextTest {
    @Test
    void authenticationIsScopedToOneSubscription() {
        Authentication alice = UsernamePasswordAuthenticationToken.authenticated(
            "alice", null, AuthorityUtils.createAuthorityList("ROLE_READER")
        );

        Mono<String> source = ReactiveSecurityContextHolder.getContext()
            .flatMap(sc -> Mono.justOrEmpty(sc.getAuthentication()))
            .map(Authentication::getName);

        StepVerifier.create(source.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(alice)))
            .expectNext("alice")
            .verifyComplete();

        // A new subscription does not receive the previous subscription's context.
        StepVerifier.create(source)
            .verifyComplete();
    }
}
```

Run with `./gradlew test` if the project uses Gradle and has the appropriate test dependencies. The test confirms that the same publisher can be subscribed to multiple times with different contexts while avoiding global `SecurityContextHolder` operations.

Besides unit tests, for WebFlux endpoints with real authentication, use `WebTestClient` to test requests with valid credentials, without credentials, and with insufficient authorities; avoid testing only paths where you manually injected `Authentication`.

## 10. Common Errors and Fixes

| Symptom | Common cause | Fix |
| --- | --- | --- |
| `ReactiveSecurityContextHolder.getContext()` is empty | No authentication present, pipeline runs outside the security chain, or context was lost at a subscription boundary | Verify that the request flow is handled by Spring Security and check the subscribe scope |
| User is read early on but lost later | `contextWrite` placed in the wrong position or separate `subscribe()` called | Keep a single continuous pipeline; place `contextWrite` downstream of the reads that need to see the context |
| Using `SecurityContextHolder.getContext()` in `publishOn` sees wrong/empty context | Relying on `ThreadLocal` across thread switches | Use `ReactiveSecurityContextHolder.getContext()` in the reactive pipeline |
| Using `map(sc -> sc.getAuthentication())` leads to errors when null | Reactor does not accept `null` elements | Use `flatMap(sc -> Mono.justOrEmpty(sc.getAuthentication()))` |
| Test has context but real request fails | Test manually injects a token without verifying actual authentication/filter chain | Separate context unit tests from authentication/authorization integration tests |
| Calling `block()` or manual `subscribe()` in a controller/service | Detaches lifecycle from WebFlux, risking event-loop blocking or lost context | Return and compose `Mono`/`Flux` with `map`/`flatMap`, letting the framework subscribe |
| Calling `clearContext()` and assuming logout occurred | Only removes context data within the pipeline scope | Use an appropriate logout/session/token strategy |

**Practical rule:** in a reactive request, let Spring Security establish the authenticated context; read the context at subscription time with `ReactiveSecurityContextHolder`; keep processing steps within the same `Mono`/`Flux` sequence; use `contextWrite` mainly for tests and controlled special cases. Never use a client-declared context as proof of authentication.

## 11. Reference Documentation

- Spring Security API — `ReactiveSecurityContextHolder`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html
- Spring Security — Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Project Reactor — Adding a Context to a Reactive Sequence: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
