# `ReactiveSecurityContextHolder` and Reactor Context

> **Topic:** Spring Security – authorization → **HTTP on WebFlux**. This article explains how Spring Security stores and propagates `SecurityContext` in Reactor `Context` per subscription, using `ReactiveSecurityContextHolder`, understanding `contextWrite`/`deferContextual`, preserving identity when running `Mono`/`Flux` across multiple schedulers, preventing cross-user data leaks, testing with `StepVerifier`/`WebTestClient`, and integrating Reactive Method Security. Examples use Java 17+, Spring Boot 3.x, and Spring Security 6.x.

## 1. Why shouldn't WebFlux retrieve the user via `ThreadLocal`?

In a synchronous servlet app, you might see:

~~~java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

String username = authentication.getName();
~~~

`SecurityContextHolder` in the imperative model normally binds `SecurityContext` to the current thread. Yet WebFlux runs via reactive execution: one thread can serve many requests, and a single request can resume on a different thread.

~~~text
HTTP Request A (alice)            HTTP Request B (bob)
      |                                 |
   event-loop-1                      event-loop-1
      |                                 |
   flatMap                            flatMap
      |                                 |
   parallel-2                        parallel-3
      |                                 |
   Response A                        Response B
~~~

If code attempts to stash a username in a `ThreadLocal` and read it back after a `publishOn` or another callback, the value can vanish or belong to the wrong request. The risk goes beyond exceptions: using the wrong identity in authorization can expose another tenant's data.

**Solution:** Reactor `Context` binds to the **Subscriber/subscription**, not to a fixed thread. Spring Security places `SecurityContext` into Reactor Context; reactive code reads it via `ReactiveSecurityContextHolder.getContext()`.

> User identity must never be stored in a singleton field, static variable, shared cached `Mono`, or self-declared header. Rely on the verified `Authentication` inside the proper reactive subscription.

## 2. Distinguishing the security data layers

| Concept | What does it hold / solve? | Common mistake |
| --- | --- | --- |
| `Authentication` | Principal, authorities, authentication state | Confusing coarse roles with permissions on every object |
| `SecurityContext` | Object holding `Authentication` | Confusing it with HTTP session/JWT |
| `SecurityContextHolder` | Imperative context API, usually thread-bound | Using it by default in WebFlux |
| Reactor `Context` | Per-Subscriber key/value map | Treating it as a mutable global map |
| `ReactiveSecurityContextHolder` | API to get/put `SecurityContext` via Reactor Context | Thinking of it as a global "current user" |
| `ReactiveSecurityContextHolder.getContext()` | `Mono<SecurityContext>` | Assuming it returns `SecurityContext` directly |
| `@EnableReactiveMethodSecurity` | Enables reactive method checks | Confusing with servlet `@EnableMethodSecurity` |

Conceptual structure:

~~~text
Reactor Context (bound to Subscriber)
      |
      +-- Spring Security key
             |
             +-- Mono<SecurityContext>
                         |
                         +-- Authentication
                                 |-- principal / name
                                 |-- authorities
                                 +-- isAuthenticated
      |
      +-- traceId / correlationId / other keys
~~~

`Reactor Context` can hold various contextual entries; `ReactiveSecurityContextHolder` manages Spring Security's entry. A custom `"user"` key set by the application does not automatically become a verified `Authentication`.

## 3. Mechanics of Reactor Context

### 3.1. Publishers are assembled first, subscribed later

~~~text
Assembly phase:
  Mono<String> request = service.currentName();
  // Request logic has not run yet.

Subscription phase:
  subscriber
       |
       v
  contextWrite(...) -> upstream operators -> data/error/completion
~~~

A `Mono` describes work; context reads occur during subscription flow. When calling `ReactiveSecurityContextHolder.getContext()`, **compose** the result instead of blocking synchronously with `block()`.

### 3.2. Immutable Context

~~~java
Context first = Context.of("traceId", "t-1");
Context second = first.put("tenant", "acme");
~~~

`second` contains the new key, while `first` is not mutated in place. `ContextView` is the read-only interface; `getOrDefault`/`getOrEmpty` avoid throwing exceptions if a key is absent. Never treat context as a global map mutated across concurrent requests.

### 3.3. Context attaches to the subscriber, not the Java thread

| Operation | Reactor Context | Default `ThreadLocal` |
| --- | --- | --- |
| `map`, `flatMap` in same subscription | Readable when context is set properly | Thread-dependent |
| `publishOn(Schedulers.parallel())` | Preserves reactive context in pipeline | `ThreadLocal` may disappear |
| `subscribeOn(...)` | Context belongs to the subscription | Does not copy thread-locals automatically |
| `new Thread(...)`, `Executor.submit(...)` | Does not inherit parent Reactor Context | Does not inherit `ThreadLocal` |
| `CompletableFuture.supplyAsync(...)` | Does not understand Reactor Context automatically | Does not preserve `ThreadLocal` |
| New `subscribe()` outside request chain | Separate subscription, does not inherit old context | No guarantee |
| `WebClient` calling a remote service | Context does not automatically become an HTTP Authorization header | `ThreadLocal` does not send tokens either |

Reactor Context propagates along **the subscription chain and Reactor operators**; it does not automatically cross non-Reactor callbacks, message queues, manual threads, or network boundaries.

## 4. `ReactiveSecurityContextHolder` API

Import:

~~~java
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
~~~

| Method | Return type | Purpose |
| --- | --- | --- |
| `getContext()` | `Mono<SecurityContext>` | Retrieves `SecurityContext` in the current reactive subscription |
| `withAuthentication(Authentication)` | Reactor `Context` | Places `Authentication` into the context of a branch/subscription |
| `withSecurityContext(Mono<? extends SecurityContext>)` | Reactor `Context` | Places a reactive `SecurityContext` into context |
| `clearContext()` | `Function<Context, Context>` | Removes the `SecurityContext` entry for affected upstream operators |

### 4.1. `getContext()`

~~~java
Mono<String> name = ReactiveSecurityContextHolder.getContext()
        .flatMap(ctx ->
                Mono.justOrEmpty(ctx.getAuthentication()))
        .map(Authentication::getName);
~~~

Imports:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;
~~~

If no context or `Authentication` exists, the publisher completes empty. For sensitive endpoints, **never** treat "no context" as a system user. Fail closed with `switchIfEmpty(Mono.error(...))` or an appropriate reactive authorization mechanism.

### 4.2. `withAuthentication(...)`

~~~java
Authentication trustedAuthentication = /* verified value */;

Mono<String> response = service.currentName()
        .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                        trustedAuthentication));
~~~

**This is an integration illustration**, not a standalone Java file; `service` and `Authentication` must be defined. In tests, you can intentionally construct a mock `Authentication`. In production, never use client-submitted usernames or authorities to forge an authenticated principal.

`withAuthentication` returns a Reactor `Context`; it does **not** replace a global user or mutate a `ThreadLocal` `SecurityContextHolder`.

### 4.3. `withSecurityContext(...)`

~~~java
SecurityContext securityContext =
        new SecurityContextImpl(trustedAuthentication);

Mono<String> response = service.currentName()
        .contextWrite(
                ReactiveSecurityContextHolder.withSecurityContext(
                        Mono.just(securityContext)));
~~~

Related imports:

~~~java
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextImpl;
~~~

This method accepts a `Mono<? extends SecurityContext>`; when you already have an `Authentication`, `withAuthentication(...)` is more concise.

### 4.4. `clearContext()`

~~~java
Mono<String> response = service.currentName()
        .contextWrite(
                ReactiveSecurityContextHolder.clearContext());
~~~

`clearContext()` returns a **Context transformation function**—it is not a server-wide logout, does not clear cookies/sessions, and does not revoke JWTs. It only clears `SecurityContext` data for upstream operators affected by that `contextWrite`.

## 5. Direction of `contextWrite`: downstream → upstream

In Reactor, `contextWrite` flows context data from the subscriber side **up to upstream operators**. Operator placement matters.

### 5.1. Writing on the right side

~~~java
Mono<String> pipeline = Mono.deferContextual(ctx -> {
    String traceId = ctx.getOrDefault("traceId", "missing");
    return Mono.just("trace=" + traceId);
}).contextWrite(ctx -> ctx.put("traceId", "t-42"));
~~~

On subscribe, result:

~~~text
trace=t-42
~~~

### 5.2. Writing on the wrong side

~~~java
Mono<String> pipeline = Mono.just("start")
        .contextWrite(ctx -> ctx.put("traceId", "t-42"))
        .flatMap(ignored -> Mono.deferContextual(ctx -> {
            String traceId = ctx.getOrDefault("traceId", "missing");
            return Mono.just(traceId);
        }));
~~~

Result:

~~~text
missing
~~~

Readers **downstream** of `contextWrite` do not see that key. Do not assume that "an operator writing context earlier in code" makes it visible to everything below.

### 5.3. Two writes to the same key

~~~java
Mono<String> pipeline = Mono.deferContextual(ctx -> {
    String value = ctx.get("role");
    return Mono.just(value);
})
.contextWrite(ctx -> ctx.put("role", "INNER"))
.contextWrite(ctx -> ctx.put("role", "OUTER"));
~~~

Result:

~~~text
INNER
~~~

The `contextWrite` closer to the reader along subscription order overrides keys with the same name. For **security context**, this means a library or callback arbitrarily swapping context could make upstream read a different identity. Write `Authentication` only from trusted sources.

### 5.4. Inner publishers inside `flatMap`

~~~java
Mono<String> pipeline = Mono.just("A")
        .flatMap(value -> Mono.deferContextual(ctx -> {
            String scope = ctx.getOrDefault("scope", "none");
            return Mono.just(value + "-" + scope);
        }).contextWrite(ctx -> ctx.put("scope", "inner")))
        .flatMap(value -> Mono.deferContextual(ctx -> {
            String scope = ctx.getOrDefault("scope", "none");
            return Mono.just(value + "-" + scope);
        }))
        .contextWrite(ctx -> ctx.put("scope", "outer"));
~~~

Result:

~~~text
A-inner-outer
~~~

A local context written inside one inner reactive chain does not leak into subsequent inner chains. Test scoping whenever an application composes multiple helpers.

## 6. Spring Security integration with WebFlux

Overview flow:

~~~text
HTTP Request
    |
    v
Spring WebFlux WebFilter chain
    |
    v
SecurityWebFilterChain
    |
    +-- Authentication (Basic / OAuth2 / session)
    +-- verify credentials
    +-- place SecurityContext into Reactor Context
    +-- HTTP authorization
    |
    v
Controller -> Mono/Flux -> service -> reactive repository
                             |
                             v
           ReactiveSecurityContextHolder.getContext()
~~~

An HTTP request authenticated by Spring Security normally does not require controllers to call `withAuthentication`; the framework binds the context to reactive execution. Scheduled jobs, message consumers, and pure Reactor tests **have no built-in request context** and must never infer a user from the current thread.

### 6.1. When should you inject `Authentication` into a controller?

Spring WebFlux / Spring Security can inject the verified authentication:

~~~java
@GetMapping("/api/me")
public Mono<String> me(Authentication authentication) {
    return Mono.just(authentication.getName());
}
~~~

This is convenient when a controller needs the user right at the HTTP boundary. However, when reading the principal deep inside a reactive service or when subscription executes on another scheduler, `ReactiveSecurityContextHolder.getContext()` fits Publisher composition better.

The `Authentication` argument is resolved by the framework from the verified request, **not** from user-supplied strings.

## 7. Complete Java 17+ and Spring Boot 3.x example

The demo app uses:
- Spring WebFlux + HTTP Basic;
- `ReactiveSecurityContextHolder` in the service;
- `@EnableReactiveMethodSecurity` and `@PreAuthorize`;
- Two demo users, Alice and Bob, with distinct authorities;
- Controllers returning `Mono<String>`;
- JUnit tests with `WebTestClient` and `StepVerifier`.

The example uses a Spring Boot 3.x project with Java 17, Gradle, the Boot plugin, and compatible dependency management. Dependencies rely on Spring Boot's BOM to manage Spring Security and Reactor versions. The demo is not a production authentication architecture.

### 7.1. `build.gradle` dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Do not add `spring-boot-starter-web` to a WebFlux-only demo. The Spring Security starter **does not automatically enable** Reactive Method Security without the corresponding configuration.

### 7.2. `src/main/java/demo/reactivecontext/ReactiveContextApplication.java`

~~~java
package demo.reactivecontext;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveContextApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveContextApplication.class, args);
    }
}
~~~

### 7.3. `src/main/java/demo/reactivecontext/ReactiveSecurityConfig.java`

~~~java
package demo.reactivecontext;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/api/public/ping").permitAll()
                        .pathMatchers("/api/me", "/api/restricted")
                            .authenticated()
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        PasswordEncoder encoder =
                PasswordEncoderFactories.createDelegatingPasswordEncoder();

        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .authorities("DOC_READ")
                .build();

        UserDetails bob = User.withUsername("bob")
                .password(encoder.encode("bob-pass"))
                .authorities("DOC_VIEW")
                .build();

        return new MapReactiveUserDetailsService(alice, bob);
    }
}
~~~

**Explanation:**
1. `@EnableWebFluxSecurity` activates WebFlux Security.
2. `@EnableReactiveMethodSecurity` enables reactive method-level authorization such as `@PreAuthorize`.
3. `/api/public/ping` is public; `/api/me` and `/api/restricted` require valid `Authentication`; all other URLs are denied.
4. `httpBasic` is used in the demo; `formLogin` is disabled so API responses stay clean and emit a 401 challenge.
5. Alice holds `DOC_READ`, whereas Bob only holds `DOC_VIEW`, so logging in successfully does not grant every method.
6. Default CSRF remains enabled for unsafe HTTP methods; this example uses GET only. Never disable CSRF if browsers can send credentials automatically.

`MapReactiveUserDetailsService` is an in-memory user store for tests; never hardcode passwords in production. Real systems need an Identity Provider, HTTPS, password/secret management, brute-force protection, and tenant/resource policies.

### 7.4. `src/main/java/demo/reactivecontext/CurrentActorService.java`

~~~java
package demo.reactivecontext;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class CurrentActorService {

    public Mono<String> currentName() {
        return ReactiveSecurityContextHolder.getContext()
                .flatMap(ctx ->
                        Mono.justOrEmpty(ctx.getAuthentication()))
                .filter(auth -> auth.isAuthenticated()
                        && !(auth instanceof AnonymousAuthenticationToken))
                .map(Authentication::getName)
                .switchIfEmpty(Mono.error(
                        new AccessDeniedException(
                                "Authentication required")));
    }

    @PreAuthorize("hasAuthority('DOC_READ')")
    public Mono<String> restrictedMessage() {
        return currentName().map(name -> "READ:" + name);
    }
}
~~~

**Why is this code safer than an imperative `SecurityContextHolder`?**
- `getContext` returns a `Mono<SecurityContext>` resolved at subscription time.
- `Mono.justOrEmpty` handles a null `Authentication`.
- `filter` rejects anonymous tokens (an anonymous token can report `isAuthenticated` as true).
- `switchIfEmpty` throws `AccessDeniedException` when identity cannot be verified rather than falling back to `system`.
- `restrictedMessage` is guarded by Spring reactive method security. It returns `Mono` without subscribing or blocking.
- From the controller, invoke the service through the Spring-managed bean proxy; self-invocation of annotated methods can bypass interceptors.

### 7.5. `src/main/java/demo/reactivecontext/ReactiveUserController.java`

~~~java
package demo.reactivecontext;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ReactiveUserController {

    private final CurrentActorService actors;

    public ReactiveUserController(CurrentActorService actors) {
        this.actors = actors;
    }

    @GetMapping("/api/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/api/me")
    public Mono<String> me() {
        return actors.currentName();
    }

    @GetMapping("/api/restricted")
    public Mono<String> restricted() {
        return actors.restrictedMessage();
    }
}
~~~

Never read username/authority from a request body. The controller returns `Mono` so WebFlux handles subscription, cancellation, errors, and lifecycle. The service obtains identity from the context established by Spring Security.

### 7.6. Expected HTTP results

~~~bash
curl -i http://localhost:8080/api/public/ping
curl -i -u alice:alice-pass http://localhost:8080/api/me
curl -i -u bob:bob-pass http://localhost:8080/api/restricted
curl -i -u alice:alice-pass http://localhost:8080/api/restricted
~~~

| Request | HTTP | Primary body |
| --- | --- | --- |
| GET public/ping, anonymous | 200 | `pong` |
| GET /api/me, Alice | 200 | `alice` |
| GET /api/restricted, Bob | 403 | Denied |
| GET /api/restricted, Alice | 200 | `READ:alice` |

Examples are for local demos only. Outside learning environments, use HTTPS and keep credentials out of shell history and public scripts.

## 8. Integration tests with `WebTestClient` and `StepVerifier`

`WebTestClient` passes through WebFlux security filters when bound to the `ApplicationContext` with `springSecurity()`. `StepVerifier` is the right tool to verify `Mono`/`Flux` and per-subscription context without calling `block()` in services.

### 8.1. `src/test/java/demo/reactivecontext/ReactiveContextIntegrationTest.java`

~~~java
package demo.reactivecontext;

import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(
        classes = ReactiveContextApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class ReactiveContextIntegrationTest {

    @Autowired ApplicationContext applicationContext;
    @Autowired CurrentActorService actors;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient
                .bindToApplicationContext(applicationContext)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    private Authentication user(String name, String authority) {
        return new UsernamePasswordAuthenticationToken(
                name, "test-only",
                List.of(new SimpleGrantedAuthority(authority)));
    }

    @Test
    void publicPingWithoutLogin() {
        client.get().uri("/api/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void anonymousCannotReadCurrentUser() {
        client.get().uri("/api/me")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void httpBasicPrincipalIsVisibleInsideMono() {
        client.get().uri("/api/me")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("alice");
    }

    @Test
    void bobSeesBobNotAlice() {
        client.get().uri("/api/me")
                .headers(h -> h.setBasicAuth("bob", "bob-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("bob");
    }

    @Test
    void methodSecurityDeniesAuthenticatedUserWithoutAuthority() {
        client.get().uri("/api/restricted")
                .headers(h -> h.setBasicAuth("bob", "bob-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void methodSecurityAllowsDocReadAuthority() {
        client.get().uri("/api/restricted")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("READ:alice");
    }

    @Test
    void oneColdMonoTwoSubscribersTwoIdentities() {
        Mono<String> cold = actors.currentName();

        StepVerifier.create(cold.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                        user("alice", "DOC_READ"))))
                .expectNext("alice")
                .verifyComplete();

        StepVerifier.create(cold.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                        user("bob", "DOC_VIEW"))))
                .expectNext("bob")
                .verifyComplete();
    }

    @Test
    void missingContextIsRejected() {
        StepVerifier.create(actors.currentName())
                .expectError(AccessDeniedException.class)
                .verify();
    }

    @Test
    void contextStillWorksAfterSchedulerSwitch() {
        Mono<String> sequence = actors.currentName()
                .publishOn(Schedulers.parallel())
                .map(String::toUpperCase)
                .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(
                                user("alice", "DOC_READ")));

        StepVerifier.create(sequence)
                .expectNext("ALICE")
                .verifyComplete();
    }

    @Test
    void nestedFluxOperatorsShareSubscriberContext() {
        Mono<List<String>> values = Flux.range(1, 3)
                .concatMap(i -> actors.currentName()
                        .map(name -> i + ":" + name))
                .collectList()
                .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(
                                user("bob", "DOC_VIEW")));

        StepVerifier.create(values)
                .expectNext(List.of("1:bob", "2:bob", "3:bob"))
                .verifyComplete();
    }

    @Test
    void clearContextMasksAuthenticationUpstream() {
        Mono<String> sequence = actors.currentName()
                .contextWrite(
                        ReactiveSecurityContextHolder.clearContext())
                .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(
                                user("alice", "DOC_READ")));

        StepVerifier.create(sequence)
                .expectError(AccessDeniedException.class)
                .verify();
    }

    @Test
    void injectedIdentityDrivesReactiveMethodSecurity() {
        StepVerifier.create(actors.restrictedMessage()
                .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(
                                user("alice", "DOC_READ"))))
                .expectNext("READ:alice")
                .verifyComplete();

        StepVerifier.create(actors.restrictedMessage()
                .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(
                                user("bob", "DOC_VIEW"))))
                .expectError(AccessDeniedException.class)
                .verify();
    }
}
~~~

### 8.2. Test matrix

| Test | Outcome | Proves |
| --- | --- | --- |
| Public ping | 200, pong | Public route remains operational |
| No login /api/me | 401 | HTTP layer rejects anonymous callers |
| Alice HTTP Basic | alice | User in Reactor Context is accurate |
| Bob HTTP Basic | bob | Does not reuse Alice's identity |
| Bob on restricted | 403 | Authenticated without enough authority |
| Alice on restricted | READ:alice | Method Security allows |
| Same cold `Mono`, two subscriptions | Alice then Bob | Context is isolated per subscriber |
| Missing context in `StepVerifier` | `AccessDeniedException` | Fail closed |
| `publishOn` | ALICE | Context does not depend on one thread |
| `concatMap` and inner `Mono` | 1:bob, 2:bob, 3:bob | Context visible inside reactive composition |
| `clearContext()` | `AccessDeniedException` | Upstream branch sees no context |
| Inject test auth into `@PreAuthorize` | Alice allow, Bob deny | Method Security reads Reactive Context |

For tests injecting auth, `withAuthentication` is a testing/trusted-integration utility, not a client authentication mechanism. Only the HTTP Basic tests exercise Spring Security's real authentication filter.

### 8.3. Running the tests

~~~bash
./gradlew test --tests demo.reactivecontext.ReactiveContextIntegrationTest
./gradlew bootRun
~~~

Windows:

~~~text
gradlew.bat test --tests demo.reactivecontext.ReactiveContextIntegrationTest
gradlew.bat bootRun
~~~

The code contains no `System.out.println`, so there is no fixed business stdout. Success means all assertions pass and HTTP status/bodies match. The example was statically verified; run it in an actual Boot 3.x / Security 6.x environment before production use.

## 9. Anti-patterns directly tied to security

### 9.1. Reading imperative `SecurityContextHolder` on the event loop

~~~java
// WRONG FOR WEBFLUX:
public Mono<String> currentNameUnsafe() {
    Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();
    return Mono.just(auth.getName());
}
~~~

This reads context **from the current thread** at method call time, not the Reactor subscription's `Authentication`. Threads can switch and context can be null. Fix by using reactive `getContext()` inside `Mono`.

### 9.2. `block()` creates a new subscription and can lose context

~~~java
// WRONG in a reactive event-loop/controller:
public String currentNameBlocking() {
    return ReactiveSecurityContextHolder.getContext()
            .map(ctx -> ctx.getAuthentication().getName())
            .block();
}
~~~

`block()` waits synchronously, can throw on non-blocking threads, and starts an independent subscription lacking the desired context. Never use it to unwrap `Mono<Authentication>` into `Authentication` during a WebFlux request.

Replace with:

~~~java
public Mono<String> currentNameReactive() {
    return ReactiveSecurityContextHolder.getContext()
            .flatMap(ctx ->
                    Mono.justOrEmpty(ctx.getAuthentication()))
            .map(Authentication::getName);
}
~~~

### 9.3. Calling `subscribe()` manually inside a service

~~~java
// ANTI-PATTERN: the new publisher is detached from the HTTP request lifecycle.
public Mono<String> handle() {
    actorService.currentName().subscribe(name -> audit(name));
    return Mono.just("done");
}
~~~

This code does not propagate audit errors back to the request, can detach context/cancellation, and can return a successful response before auditing completes. `actorService` and `audit` are illustrative dependencies.

Right direction:

~~~java
public Mono<String> handle() {
    return actorService.currentName()
            .flatMap(name -> auditReactive(name)
                    .thenReturn("done"));
}
~~~

`auditReactive` here is a reactive method you implement yourself. The key is **composing `Mono`/`Flux`** so the framework acts as subscriber and manages errors.

### 9.4. Global `Mono.cache()` can leak users

~~~java
// EXTREMELY DANGEROUS if the publisher is held in a singleton/global:
Mono<String> cachedCurrentUser =
        actorService.currentName().cache();
~~~

`Mono.cache()` stores the **result of the first subscription**. Subsequent subscribers, even with a different user's `Authentication`, can receive the first user's name. A new subscriber's `Reactor Context` does not automatically invalidate a previously cached result.

Principles:
- Never cache a publisher whose value depends on `Authentication` **across requests**.
- If caching domain data, keys must include valid principal/tenant/resource/action/policy revision.
- Design proper TTL, revocation, and authorization-invalidation strategies.
- Never place a user-specific `Mono` in a mutable singleton field shared across callers.

### 9.5. Constructing `Authentication` from unverified headers

~~~java
// ANTI-PATTERN: client-supplied X-User/X-Role is not a trusted identity.
Authentication forged =
        new UsernamePasswordAuthenticationToken(
                userHeader,
                "ignored",
                List.of(new SimpleGrantedAuthority("ROLE_ADMIN")));

return service.readSecret().contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(forged));
~~~

`withAuthentication` **does not verify** usernames, roles, JWT signatures, or credentials; it merely attaches the supplied object to Reactor Context. Never build an authenticated principal from untrusted input.

### 9.6. Tenant context is a selector, not a permission

~~~java
Mono<String> response = service.readDocument()
        .contextWrite(Context.of("tenantId", requestedTenant));
~~~

If `requestedTenant` came from a URL or header, it only indicates the target tenant—it is not authorized yet. You must verify the actor holds membership in that tenant and the resource actually belongs to it. Reactor Context **carries data; it does not prove the data is trustworthy**.

## 10. Scheduler switches and boundaries outside Reactor

### 10.1. `publishOn`, `subscribeOn`

~~~java
Mono<String> pipeline = actors.currentName()
        .publishOn(Schedulers.parallel())
        .map(String::toUpperCase)
        .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                        trustedAuthentication));
~~~

`trustedAuthentication` in this example is a verified `Authentication`, not a user self-declared in the request. Reactor Context propagates when a pipeline uses `publishOn` or `subscribeOn` properly; that does not mean another library's `ThreadLocal` automatically holds the same value.

### 10.2. Boundaries where context is easily lost

| Boundary | What not to assume | Approach |
| --- | --- | --- |
| `new Thread`/`Executor.submit` | Child thread inherits security context | Pass trusted actor explicitly or bridge carefully |
| `CompletableFuture.supplyAsync` | Future sees Reactor Context automatically | Use supported context propagation |
| Detached `subscribe()` | New subscription retains HTTP auth | Compose into the main pipeline |
| Remote `WebClient` | Reactor Context sends Bearer tokens automatically | Scoped OAuth2 authorized client / token relay |
| Kafka/Rabbit consumer | Holds producer's HTTP user in memory | Verify command source / service principal |
| Scheduled job | Holds the last logged-in user | Least-privilege service identity |
| Global `Mono.cache()` | Result partitions per principal automatically | Never share cached user results |
| Custom context replacement | Preserves Spring Security keys | Merge/write via `contextWrite`, avoid wiping everything |

### 10.3. Micrometer Context Propagation and MDC

Recent Reactor versions support Context Propagation, integrating Micrometer Context Propagation and registered `ThreadLocalAccessor`s. `contextCapture()` or `Hooks.enableAutomaticContextPropagation()` helps bridge data between Reactor Context and `ThreadLocal`s of logging/tracing libraries.

Yet never conclude that:
- Enabling a hook authenticates users automatically.
- Principals are forwarded across the network automatically.
- It restores context for an unrooted detached subscription.
- It fixes a cached `Mono` leaking results from an earlier user.
- All `ThreadLocal`s, including imperative security context, match automatically without proper accessor/version setup.

In Spring WebFlux, continue preferring `ReactiveSecurityContextHolder` as the `Authentication` source in reactive flows. MDC/`traceId` is a separate concern and should never hold raw tokens or passwords.

## 11. Reactive Method Security still needs resource authorization

A rule:

~~~java
@PreAuthorize("hasAuthority('DOC_READ')")
public Mono<Document> getById(Long id) {
    return repository.findById(id);
}
~~~

is a **conceptual snippet** omitting `Document` and `repository`. It checks only a coarse authority, without verifying which tenant owns the document, who owns it, or whether it is locked. If Alice only has permissions in ACME, `DOC_READ` does not mean Alice may read every BETA document.

A complete policy may require:

~~~text
authenticated(actor)
AND hasAuthority(actor, "DOC_READ")
AND activeMembership(actor, targetTenant)
AND document.tenantId == targetTenant
AND permissionEvaluator.hasPermission(actor, document, "READ")
AND document.status != LOCKED
~~~

Enforce checks in the service/repository in addition to HTTP URL rules, because the same use case can be invoked from GraphQL, background workers, or message consumers. Also remember `@PreAuthorize` on reactive publishers must run through a Spring proxy; self-invocation may bypass interception.

## 12. Authentication/Session/Logout are different from `clearContext`

A security context in Reactor Context exists for a single subscription or operator scope. Do not confuse:

- `ReactiveSecurityContextHolder.clearContext()`: clears the entry inside one branch.
- HTTP logout: clears the `SecurityContext` repository/session/cookie per configuration.
- JWT revocation: invalidates tokens/entitlements per protocol, not just local context.
- Role revocation: updates IAM/policy/cache, which may not appear immediately in old JWTs.
- MFA/step-up: action-specific authentication requirements, not enforced merely by reading context.

If an access token expires or a user is locked mid-request, sensitive actions need explicit revocation/consistency contracts. "Reactive context still sees Alice" does not prove Alice remains authorized at the moment of a domain mutation.

## 13. Background jobs, `WebClient`, and message consumers

### Scheduled jobs

A `@Scheduled` job has no HTTP principal by default. Use a transparent service identity with minimal scope:

~~~text
actorType=SERVICE
actorId=nightly-indexer
tenantScope=acme
permissions=[DOC_INDEX]
jobId=nightly-2026
~~~

If constructing a trusted service `Authentication` with `withAuthentication`, audit it and grant least privilege. Never use a blanket `ROLE_SYSTEM_ADMIN` for every task.

### `WebClient`

~~~java
return webClient.get()
        .uri("/documents/{id}", id)
        .retrieve()
        .bodyToMono(DocumentView.class);
~~~

This code is illustrative because `webClient` and `DocumentView` must be configured separately. Local Reactor Context **does not automatically** create a valid `Authorization` header for downstream services. Token relay or client credentials require proper filters/authorized-client integration with exact audience and scope. Never blindly forward all inbound headers to arbitrary hosts.

### Message consumers

A message containing `principalId`/`tenantId` does not prove the producer was authorized to act for that user. Consumers must verify producer/service identity, signatures/trust, replay protection, tenant scope, and policies at processing time. Never pass an unverified message body into `withAuthentication` and treat it as a valid `Authentication`.

## 14. Reactive transactions and Reactor `SecurityContext` are separate contexts

In Spring Reactive Transaction Management, transactions may also use Reactor Context to hold transaction state. However:

| Concern | Related context | Meaning |
| --- | --- | --- |
| Security | `Mono<SecurityContext>` | Who is calling, authorities |
| Transaction | Reactive transaction metadata | Commit/rollback participating operations |
| Tracing | Trace/span/correlation | Request observability |
| Tenant | Tenant selection/membership | Data scope |

Having `Authentication` in Reactor Context **does not open a transaction**. Having a transaction **does not prove the actor is authorized**. When mutating domain data, combine proper resource authorization with appropriate transactions and locking.

Never replace the entire `Context` with an empty context carelessly; that can wipe out security, transaction, and tracing metadata alike. Use each framework's APIs and `contextWrite(ctx -> ctx.put(...))` when adding keys.

## 15. Common mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| `getContext()` empty in `StepVerifier` | No test auth attached | `contextWrite(withAuthentication(...))` |
| HTTP login succeeds but service lacks principal | Detached subscription / custom async boundary | Compose the chain; test with `WebTestClient` |
| `SecurityContextHolder.getContext()` null after `publishOn` | Imperative `ThreadLocal` used in reactive code | Use `ReactiveSecurityContextHolder` |
| Bob sees Alice's name | Shared `Mono.cache()` / singleton state | Never cache per-user results globally |
| `contextWrite` has no effect | Placed on wrong side of reader | Place writer downstream of reader |
| `clearContext` runs yet user still has session | Clearing local entry does not log out | Design separate logout/revocation |
| `@PreAuthorize` does not run | Missing `@EnableReactiveMethodSecurity` or proxy bypass | Enable annotation / call injected bean |
| Bob allowed on `restricted` | Broken authority mapping / proxy | Test HTTP 403 + reactive service |
| API returns 401 | No valid `Authentication` | Check HTTP Basic / JWT filter |
| API returns 403 | Missing role or CSRF | Separate positive/negative HTTP tests |
| `block()` throws event-loop error | Blocking a reactive thread | Compose `Mono`/`Flux` |
| `CompletableFuture` misses security | Does not read Reactor Context automatically | Explicit actor / capture / bridge |
| MDC missing `traceId` | Logger `ThreadLocal` lacks context propagation | Configure Micrometer for your version |
| Job runs under previous user | Reused global / `ThreadLocal` state | Dedicated service identity |
| Downstream `WebClient` gets 401 | Token not sent per policy | Scoped OAuth2 client/filter |
| Cross-tenant access | Identity present without domain checks | Tenant-scoped queries + permissions |
| Anonymous counted as authenticated | Checked only `isAuthenticated()` flag | Filter anonymous / trust resolver |
| Token revoked yet requests still succeed | Cache / stale JWT | Revocation strategy, versioning, or policy lookup |

## 16. Checklist for reviewing WebFlux security context

1. Using WebFlux `SecurityWebFilterChain` instead of servlet `HttpSecurity`?
2. Is `ReactiveSecurityContextHolder.getContext()` used inside a properly subscribed `Publisher`?
3. Does it fail closed when `Authentication` is null, anonymous, or the context is empty?
4. Zero `block()` calls on the event loop, and zero manual `subscribe()` calls inside controllers/services?
5. No usernames or `Authentication` objects stored in mutable singleton fields or global `Mono.cache()`?
6. Are `contextWrite` operators placed downstream of the readers that need them?
7. Have `publishOn`/`subscribeOn` and inner `flatMap` scopes been tested?
8. Have you tested two users subscribing to the same cold `Publisher` with different contexts?
9. No authenticated principal forged from unverified request data or headers?
10. Is `@EnableReactiveMethodSecurity` enabled and do protected methods return reactive types?
11. Are protected methods invoked through Spring-managed proxies without self-invocation?
12. Are tenant and document permissions checked explicitly rather than relying solely on global authorities?
13. Do background jobs and message consumers use trusted identities with minimal scope?
14. Does `WebClient` OAuth2/token relay send tokens only to intended destinations/audiences?
15. Do `ThreadLocal`/MDC bridges use proper accessors/versions without being treated as security primitives?
16. Are reactive transactions and `SecurityContext` responsibilities cleanly separated?
17. Do HTTP tests wire full Spring Security filters, and do `StepVerifier` tests cover subscriptions?
18. Do logs redact passwords/JWTs so trace/security metadata never leaks sensitive data?

## 17. Practice exercises

**Exercise 1 – Two subscribers.** Create a cold `Mono` from `currentName()` and subscribe twice with Alice and Bob. Use `withAuthentication` for each subscription and verify independent outputs.

**Exercise 2 – `contextWrite` placement.** Try `Mono.deferContextual` reading `traceId` with `contextWrite` before and after the reader. Explain why one case yields `missing`.

**Exercise 3 – Clearing context.** Chain `currentName().contextWrite(clearContext()).contextWrite(withAuthentication(alice))`. Use `StepVerifier` to confirm fail-closed behavior and explain why this is not an HTTP logout.

**Exercise 4 – Schedulers.** Use `publishOn(Schedulers.parallel())` and `subscribeOn(Schedulers.boundedElastic())` on the same pipeline. Compare Reactive `SecurityContext` with `ThreadLocal`; do not call `block()` on the event loop.

**Exercise 5 – Cache leak.** Try creating a shared `Mono.cache()` that reads `currentName`, subscribing as Alice first and then Bob. Observe the identity leak and fix it by never sharing principal-dependent caches.

**Exercise 6 – Method Security.** Add a `@PreAuthorize("hasAuthority('DOC_EXPORT')")` method returning `Mono`. Test accounts with and without the authority using `StepVerifier` and `WebTestClient`.

**Exercise 7 – Tenant scope.** Add a reactive repository query by `documentId + tenantId`, verifying membership and resource policy. Test that an ACME user cannot read a BETA document despite valid `Authentication`.

**Exercise 8 – Detached tasks.** Create a `CompletableFuture`/`subscribe()` detached from the request and observe the missing context; replace it with `flatMap`/reactive composition or an explicit trusted actor boundary.

**Exercise 9 – `WebClient`.** Test a case with valid local context yet missing downstream Bearer token; add an OAuth2 authorized client and verify scope/audience.

**Exercise 10 – Correlation ID.** Use Reactor Context + `deferContextual` to carry `traceId` across operators. Evaluate MDC `ThreadLocal` and context propagation across scheduler switches.

**Completion criteria:** You understand subscriber-scoped Reactor Context, distinguish `SecurityContextHolder` from `ReactiveSecurityContextHolder`, use `getContext`/`withAuthentication`/`withSecurityContext`/`clearContext` properly, place `contextWrite` correctly, avoid `block`/`subscribe`/caching user results, enable Reactive Method Security, and test both HTTP and reactive subscriptions.

## 18. Official references

- Spring Security – **ReactiveSecurityContextHolder API**: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html
- Spring Security – **Reactive Method Security**, `@EnableReactiveMethodSecurity` and Reactor Context: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Security – **WebFlux Security Configuration**: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security – **Testing WebFlux Authentication**: https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html
- Spring Security – **WebTestClient Security Setup**: https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html
- Spring Security – **Method Security Tests** and `ReactorContextTestExecutionListener`: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Project Reactor – **Adding a Context to a Reactive Sequence**: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
- Project Reactor – **Context Propagation Support**: https://projectreactor.io/docs/core/release/reference/advancedFeatures/contextPropagation.html
- Spring Framework – **Transaction Management**: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
