# Setting context with contextWrite and withAuthentication

> **Topic:** Security context in Spring Security reactive (Spring WebFlux, Reactor, Spring Boot 3.x, Spring Security 6.x, Java 17+). This lesson focuses on how to **supply a trusted, verified `Authentication` into Reactor Context for a specific reactive pipeline**, using `contextWrite(ReactiveSecurityContextHolder.withAuthentication(authentication))`, and how to read, test, and scope that context.

## 1. Learning outcomes

After this lesson, you will be able to:

1. Explain the differences between `ThreadLocal`, `reactor.util.context.Context`, `SecurityContext`, and `Authentication`.
2. Understand that `ReactiveSecurityContextHolder.withAuthentication(authentication)` returns a **Reactor `Context`** rather than a `Mono<Authentication>`, and how `contextWrite(...)` attaches context to a subscription.
3. Write a pipeline that reads the principal with `ReactiveSecurityContextHolder.getContext()`, and supply context for test pipelines or already-authenticated internal tasks.
4. Accurately predict the effects of `contextWrite` placement, `flatMap` branches, `publishOn`, and multiple independent subscriptions.
5. Recognize security boundaries: `withAuthentication` **does not verify passwords/JWTs, does not persist sessions, and does not replace WebFlux's authentication process**.

## 2. Why does Spring Security reactive need Reactor Context?

In traditional Servlet applications, a request typically has a processing flow tied to a worker thread; familiar code might call `SecurityContextHolder.getContext().getAuthentication()`. That approach relies mainly on storing context per execution thread, usually via `ThreadLocal`.

In WebFlux, a `Mono`/`Flux` pipeline can:

- Execute only after a subscriber subscribes;
- Switch between multiple threads via `publishOn` / `subscribeOn`;
- Run asynchronous branches with `flatMap`;
- Reuse the same publisher across multiple independent subscriptions;
- Have no fixed "one request = one thread" relationship.

Relying solely on the current thread's `ThreadLocal` can lose or misread identity when threads switch. Spring Security reactive uses `ReactiveSecurityContextHolder` to retrieve `SecurityContext` from the **subscription's Reactor Context**.

Related concepts:

| Concept | Role |
| --- | --- |
| `Authentication` | Represents the principal, credentials (if still present), authorities, and authentication state of a subject |
| `SecurityContext` | Container holding `Authentication` used in making security decisions |
| `reactor.util.context.Context` | API-immutable key–value store bound to a subscription and propagated by Reactor along the operator chain |
| `ReactiveSecurityContextHolder` | Spring Security adapter to read or store `Mono<SecurityContext>` in Reactor Context |
| `contextWrite(...)` | Reactor operator that modifies the context **seen upstream** of the operator's position when subscription occurs |
| `ReactiveSecurityContextHolder.getContext()` | Returns `Mono<SecurityContext>` from the subscriber's context; can be empty when no context is present |

**Distinguish two similarly named classes:** `SecurityContext` is Spring Security's security data. `Context` is Reactor's immutable container. Spring Security stores a `Mono<SecurityContext>` publisher under an internal key in Reactor Context; it does not directly store a username under an arbitrary key like `"user"`.

### 2.1 From SecurityContext to Authentication

Read identity from the reactive context using the official API:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import reactor.core.publisher.Mono;

public class CurrentUserService {

    public Mono<String> currentUsername() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(Authentication::isAuthenticated)
            .map(Authentication::getName)
            .defaultIfEmpty("anonymous");
    }
}
```

This is a **complete Java class ready to place in source** (not yet annotated with `@Service` or registered as a bean), using Spring Security core and Reactor. `"anonymous"` is a fallback **when no matching value exists in the pipeline**, not because Spring Security itself always assigns that name to principals. In HTTP WebFlux, anonymous authentication may exist when security filters are active; thus whether `getContext()` returns a context also depends on the security chain.

`filter(Authentication::isAuthenticated)` only checks the status flag on the object already in context; **it does not prove credentials were properly verified**. A manually constructed object can declare that flag itself; always distinguish demo data from results issued by an authentication manager/trusted provider.

## 3. Core APIs: withAuthentication(...) and contextWrite(...)

`ReactiveSecurityContextHolder` has four important APIs for this lesson:

| API | Return type | Meaning |
| --- | --- | --- |
| `getContext()` | `Mono<SecurityContext>` | Reads the security context from the active Reactor Context |
| `withAuthentication(Authentication)` | `Context` | Creates a Reactor Context carrying a `Mono<SecurityContext>` containing the supplied authentication |
| `withSecurityContext(Mono<? extends SecurityContext>)` | `Context` | Supplies a SecurityContext publisher directly when controlling how the context is obtained |
| `clearContext()` | `Function<Context, Context>` | Creates a transformation removing the SecurityContext key within the applicable Reactor Context scope |

Typical syntax:

```java
Mono<String> result = currentUsername()
    .map(name -> "Hello " + name)
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(authentication)
    );
```

This is a **snippet inside a method with a valid `authentication` variable and `currentUsername()` method**, not a standalone runnable file. `withAuthentication(authentication)` creates a `Context` holding a `Mono<SecurityContext>`; `contextWrite(...)` is the Reactor operator that attaches that context to the subscriber when the pipeline is subscribed. Because `currentUsername()` is **upstream** of `contextWrite`, it reads the attached authentication.

**Do not confuse written order with execution time:**

```text
Publisher declaration (assembly):
  currentUsername() -> map(...) -> contextWrite(withAuthentication(auth))
                                       ^ at the end of the code chain

On subscribe:
  Subscriber
      |
      v
  contextWrite creates/merges Reactor Context
      |
      v (context visible upstream)
  map(...) -> currentUsername() reads ReactiveSecurityContextHolder.getContext()

The onNext data flow then travels from source to subscriber.
```

Reactor Context is bound to the **Subscriber**, not a global variable, not automatically persisted across requests, and not a mutation of a mutable object in a thread. `Context` is API-immutable: `put` or merge operations create a new context for the corresponding operator scope.

### 3.1 Concise and equivalent forms

Once you have a **trusted** `Authentication`, the following two approaches share the same goal:

```java
// Approach 1: use the helper directly
Mono<String> viaAuthentication = currentUsername()
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth));

// Approach 2: construct SecurityContext yourself to provide via Mono
SecurityContext securityContext = new SecurityContextImpl(auth);
Mono<String> viaSecurityContext = currentUsername()
    .contextWrite(
        ReactiveSecurityContextHolder.withSecurityContext(
            Mono.just(securityContext)
        )
    );
```

The lines above are an **illustrative snippet requiring imports** for `Mono`, `SecurityContext`, `SecurityContextImpl`, and existing `auth` / `currentUsername()`. In practice, use `withAuthentication` when you only need to pass an Authentication; use `withSecurityContext` when you already have a context publisher, such as from a controlled authentication component or repository.

**Do not do this:**

```java
// Semantically wrong: "auth" is unverified data self-declared by the client
Authentication auth = /* constructed from username/role taken directly from the HTTP request */;
return protectedBusinessOperation()
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth));
```

This pattern is **intentionally non-compiling pseudocode** as a warning. `withAuthentication` does not check token signatures, passwords, permissions, or data sources. Placing an object with authorities into context is a **security-privileged** action, performed only after trusted verification and when that scope is authorized to use that identity.

## 4. Runnable lab with JUnit 5 and StepVerifier

To observe this clearly without starting a web server or simulating HTTP login, create a Spring Boot 3.x WebFlux/Java 17+ project with the following dependencies in `build.gradle` configured with the Spring Boot plugin:

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

`spring-boot-starter-security` brings in Spring Security, `spring-boot-starter-webflux` includes Reactor core and WebFlux APIs, and `reactor-test` provides `StepVerifier`. The test below **does not require `@SpringBootTest` or running an HTTP server**: it directly tests `contextWrite` semantics in a pure reactive pipeline.

Create `src/test/java/com/example/reactivesecurity/ReactiveContextExamplesTest.java`:

```java
package com.example.reactivesecurity;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextImpl;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

class ReactiveContextExamplesTest {

    // An Authentication already marked authenticated solely for building TEST data.
    // Production must obtain it from a valid authentication manager/IdP.
    private static Authentication auth(String username) {
        return UsernamePasswordAuthenticationToken.authenticated(
            username,
            "unused-test-credential",
            List.of(new SimpleGrantedAuthority("ROLE_READER"))
        );
    }

    private static Mono<String> username() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName)
            .defaultIfEmpty("anonymous");
    }

    @Test
    void readsAuthenticationFromContextWrite() {
        Mono<String> result = username()
            .map(name -> "Hello " + name)
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(auth("alice"))
            );

        StepVerifier.create(result)
            .expectNext("Hello alice")
            .verifyComplete();
    }

    @Test
    void noContextMeansNoSecurityContextValue() {
        StepVerifier.create(username())
            .expectNext("anonymous")
            .verifyComplete();
    }

    @Test
    void withSecurityContextCanBeUsedInstead() {
        SecurityContext securityContext = new SecurityContextImpl(auth("bob"));

        Mono<String> result = username()
            .contextWrite(
                ReactiveSecurityContextHolder.withSecurityContext(
                    Mono.just(securityContext)
                )
            );

        StepVerifier.create(result)
            .expectNext("bob")
            .verifyComplete();
    }

    @Test
    void contextWriteMustBeDownstreamOfReader() {
        // Placing contextWrite BEFORE flatMap only supplies context to the upstream Mono.just.
        // username() in the downstream flatMap does not see it.
        Mono<String> misplaced = Mono.just("start")
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(auth("alice"))
            )
            .flatMap(ignored -> username());

        StepVerifier.create(misplaced)
            .expectNext("anonymous")
            .verifyComplete();

        // Correct: contextWrite at the end, downstream of the reader.
        Mono<String> corrected = Mono.just("start")
            .flatMap(ignored -> username())
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(auth("alice"))
            );

        StepVerifier.create(corrected)
            .expectNext("alice")
            .verifyComplete();
    }

    @Test
    void differentSubscribersCanHaveDifferentAuthentications() {
        Mono<String> asAlice = username()
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(auth("alice"))
            );

        Mono<String> asBob = username()
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(auth("bob"))
            );

        StepVerifier.create(Mono.zip(asAlice, asBob))
            .assertNext(names -> {
                assertThat(names.getT1()).isEqualTo("alice");
                assertThat(names.getT2()).isEqualTo("bob");
            })
            .verifyComplete();
    }

    @Test
    void innerContextDoesNotEscalateToFollowingOuterStage() {
        Mono<String> flow = Mono.just("start")
            .flatMap(ignored ->
                username().contextWrite(
                    ReactiveSecurityContextHolder.withAuthentication(auth("worker"))
                )
            )
            .flatMap(innerName ->
                username().map(outerName -> innerName + "/" + outerName)
            );

        StepVerifier.create(flow)
            .expectNext("worker/anonymous")
            .verifyComplete();
    }

    @Test
    void contextSurvivesReactorSchedulerChange() {
        Mono<String> flow = Mono.just("trigger")
            .publishOn(Schedulers.parallel())
            .flatMap(ignored -> username())
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(auth("alice"))
            );

        StepVerifier.create(flow)
            .expectNext("alice")
            .verifyComplete();
    }

    @Test
    void clearContextCanMaskAuthenticationForOneScope() {
        Mono<String> flow = username()
            .contextWrite(ReactiveSecurityContextHolder.clearContext())
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(auth("alice"))
            );

        StepVerifier.create(flow)
            .expectNext("anonymous")
            .verifyComplete();
    }

    @Test
    void aNewSubscriptionDoesNotInheritAnotherSubscriptionContext() {
        Mono<String> sharedSource = username();

        StepVerifier.create(sharedSource.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(auth("alice"))
            ))
            .expectNext("alice")
            .verifyComplete();

        StepVerifier.create(sharedSource)
            .expectNext("anonymous")
            .verifyComplete();
    }
}
```

Run from the project directory:

```bash
./gradlew test --tests '*ReactiveContextExamplesTest'
```

On Windows PowerShell, use `.\gradlew.bat test --tests '*ReactiveContextExamplesTest'`. This is a **JUnit test**, not a Java SE application that can run with `javac` and `java` without Spring Security, Reactor, and JUnit dependencies.

If the tests succeed, Gradle reports the test task as complete. Strings like `"Hello alice"` and `"worker/anonymous"` are **expected StepVerifier values**, not output printed to stdout. This content states expectations from the code; run the command in the corresponding project to confirm on your actual dependency versions.

### 4.1 Explaining each test group

- `readsAuthenticationFromContextWrite`: upstream of `contextWrite`, `getContext()` sees the `SecurityContext` containing the `Authentication` named `alice`.
- `noContextMeansNoSecurityContextValue`: pure Reactor test without default WebFilters, so `getContext()` has no security key → falls back to `anonymous`.
- `withSecurityContextCanBeUsedInstead`: uses the lower-level helper to supply `Mono<SecurityContext>`; the read result is still `bob`.
- `contextWriteMustBeDownstreamOfReader`: operator placement decides **which upstream readers** receive the context; context does not "flow" freely to every subsequent operator.
- `differentSubscribersCanHaveDifferentAuthentications`: the same principal-reading API, yet two independent subscription branches carry two different contexts.
- `innerContextDoesNotEscalateToFollowingOuterStage`: context added inside `flatMap` affects only the sub-publisher it was applied to; it does not alter the context for subsequent operators of the outer chain.
- `contextSurvivesReactorSchedulerChange`: switching schedulers **within the same Reactor chain** preserves Reactor Context in the proper scope.
- `clearContextCanMaskAuthenticationForOneScope`: removes the key in the upstream segment's context; this is not an HTTP logout or token revocation.
- `aNewSubscriptionDoesNotInheritAnotherSubscriptionContext`: a publisher can be subscribed to again with a different context; the new subscription does not automatically carry the previous one's context.

### 4.2 Dedicated illustration of contextWrite direction

Compare two pipelines:

```java
// Correct: contextWrite is downstream of the getContext() position
Mono<String> yes = ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName())
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth));

// Wrong expectation: getContext() in a flatMap downstream of contextWrite
Mono<String> no = Mono.just("x")
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth))
    .flatMap(x -> ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName()))
    .defaultIfEmpty("no-context");
```

This is a **snippet requiring a valid `auth` variable and imports**. `yes` will emit the username when `auth` is trusted and non-null; `no` usually emits `"no-context"` if no SecurityContext is provided by an outer subscriber. In an HTTP environment with security filters or a subscriber wrapped with another context, results can differ; the right placement is always determined by **actual context and subscriber scope**, not a "global variable" model.

## 5. Why does contextWrite work bottom-up?

Reactor Context **is not a data signal** flowing forward through every `map`/`flatMap`. It is attached to the subscriber and propagated during subscription from downstream to upstream operators. Therefore:

```text
Assembly order (top-down in code):

  Mono.deferContextual(read)
    .map(transform)
    .contextWrite(addContext)

Subscription starts:
  subscriber
    -> contextWrite(addContext) creates new Context
    -> upstream map(transform)
    -> upstream deferContextual(read) sees new Context

Data/onNext:
  read -> transform -> subscriber
```

`contextWrite(ContextView)` merges the entries of `ContextView` with the downstream context, producing the context seen upstream. `contextWrite(Function<Context,Context>)` receives the downstream context and returns a context for upstream, such as `ctx -> ctx.put("requestId", "r-001")`.

A general Reactor Context example:

```java
Mono<String> trace = Mono.deferContextual(view ->
        Mono.just(view.getOrDefault("requestId", "missing")))
    .contextWrite(ctx -> ctx.put("requestId", "r-001"));
```

This snippet should emit `"r-001"`. However, **`ctx.put("requestId", "...")` does not create a Spring SecurityContext**; `ReactiveSecurityContextHolder.getContext()` looks up Spring Security's internal key/type. Use `withAuthentication` or `withSecurityContext` instead of guessing keys or putting a `"user"` field expecting Spring Security to use it.

When multiple `contextWrite` operators modify the same key, an upstream reader sees the entry from the context closest to it in application order. A `contextWrite` inside an inner publisher normally supplies context only to **that inner publisher**, rather than writing backward as "state of the outer pipeline".

## 6. When should you use withAuthentication manually?

### 6.1 Unit, service, and reactive method security testing

This is the clearest case: you need to execute a reactive service or permission-checked method **in a test** with a specific test identity.

```java
Authentication testUser = UsernamePasswordAuthenticationToken.authenticated(
    "alice",
    "not-used",
    List.of(new SimpleGrantedAuthority("ROLE_READER"))
);

Mono<String> result = service.findCurrentUserData()
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(testUser));

StepVerifier.create(result)
    .expectNext("expected-data-for-alice")
    .verifyComplete();
```

This is an **illustrative test snippet**: `service.findCurrentUserData()` and expected data depend on the actual service. With `@EnableReactiveMethodSecurity` / `@PreAuthorize`, SecurityContext must appear in Reactor Context when the publisher is subscribed, and the method must use a reactive signature supported by Spring Security.

For WebFlux HTTP tests (controllers, routers, filter chains), prefer `spring-security-test` helpers such as `SecurityMockServerConfigurers.mockUser(...)`, `mockAuthentication(...)`, `mockJwt(...)`, or `@WithMockUser` depending on the test type and runtime. They set authentication at the proper test layer, helping avoid unintentionally bypassing web filters.

### 6.2 Internal tasks after a trusted authentication step

Sometimes a reactive component needs to run a pipeline with an `Authentication` just verified by **`ReactiveAuthenticationManager`**:

```java
public Mono<String> authenticateThenDoWork(
        ReactiveAuthenticationManager manager,
        Authentication presented,
        Mono<String> protectedWork) {

    return manager.authenticate(presented)
        .switchIfEmpty(Mono.error(
            new BadCredentialsException("Authentication did not succeed")))
        .flatMap(authenticated ->
            protectedWork.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(authenticated)
            )
        );
}
```

This is an **illustrative method placed in a Java class**; import `ReactiveAuthenticationManager` from `org.springframework.security.authentication`, `BadCredentialsException` from the same package, `Authentication`, and `Mono`. Unauthenticated `presented` is passed only to `manager.authenticate`; **only the `authenticated` result accepted by the manager** is placed into Reactor Context. In a real implementation, pick the manager suited to the credential mechanism and handle authentication errors per policy.

To avoid accidentally sharing a hot publisher across principals, you can replace `Mono<String> protectedWork` with `Supplier<Mono<String>> workFactory` and call `workFactory.get()` inside `flatMap`. The shorter version above is sound in `contextWrite` semantics for a cold publisher created for the task.

**Security boundary:** Never accept an `Authentication` with authorities/roles from an arbitrary body or header and pass it to `withAuthentication`, even if `isAuthenticated()` is `true`. That status flag is an object property; verifying the credential source remains the responsibility of the authentication provider/manager. Supply context only for the right task and principal; avoid "run as admin" unless there is a designed delegation/control mechanism.

### 6.3 In normal WebFlux HTTP requests: the framework does this

A WebFlux request with `SecurityWebFilterChain` and suitable authentication usually already has its security context inserted into the reactive chain by Spring Security components (such as `ReactorContextWebFilter` and authentication filters). Business services **only need to read**:

```java
public Mono<String> currentPrincipalName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
}
```

This is a **method in a Spring service**, requiring no manual `withAuthentication` per request. Manually constructing a "trusted" Authentication directly in a controller to satisfy a role is a way of **bypassing authentication**, not proper Spring Security usage.

`contextWrite(withAuthentication(...))` is particularly useful in tests or when supplying context for **an already-authenticated reactive computation**. It does not give an HTTP request valid credentials, does not replace authentication filters, does not automatically forward credentials to downstream HTTP services, and does not persist sessions for subsequent requests.

## 7. WebFlux example reading context created by Spring Security from HTTP Basic

To distinguish **framework-supplied context** from context manually attached in unit tests, here is a small HTTP application using Basic authentication (for learning only). Keep `build.gradle` from section 4 and create files under package `com.example.reactivesecurity`.

### 7.1 Application: ReactiveContextApplication.java

`src/main/java/com/example/reactivesecurity/ReactiveContextApplication.java`:

```java
package com.example.reactivesecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveContextApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveContextApplication.class, args);
    }
}
```

### 7.2 SecurityConfig.java

`src/main/java/com/example/reactivesecurity/SecurityConfig.java`:

```java
package com.example.reactivesecurity;

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
                .anyExchange().authenticated())
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
        var reader = User.withUsername("reader")
            .password(encoder.encode("reader-demo-password"))
            .roles("READER")
            .build();
        return new MapReactiveUserDetailsService(reader);
    }
}
```

The demo code creates user `reader` with an encoded password from a sample value. Do not ship hard-coded test accounts to production, and do not use Basic auth over unencrypted HTTP outside local environments. For POST/PUT/DELETE, Spring Security may require CSRF tokens depending on configuration; GET does not require a CSRF token for this example.

### 7.3 WhoAmIController.java

`src/main/java/com/example/reactivesecurity/WhoAmIController.java`:

```java
package com.example.reactivesecurity;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class WhoAmIController {

    @GetMapping("/whoami")
    public Mono<String> whoami() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(Authentication::isAuthenticated)
            .map(Authentication::getName)
            .switchIfEmpty(Mono.error(
                new IllegalStateException("No authenticated principal")));
    }
}
```

The controller **does not call `withAuthentication`**: `SecurityWebFilterChain` already processed the Basic credentials, verified the user, and provided a valid Authentication to the request pipeline. `whoami()` only reads the principal from Reactor Context.

Run the application:

```bash
./gradlew bootRun
```

In another terminal, in a **localhost test-only** environment, run:

```bash
curl -i http://localhost:8080/whoami
curl -i -u reader http://localhost:8080/whoami
```

The second command prompts interactively for the password: `reader-demo-password`. The first is expected to return **401 Unauthorized** due to missing credentials, and the second **200 OK** with body:

```text
reader
```

The actual response also includes HTTP headers added by the server/security; the block above depicts only the **expected body**. If the application uses another profile/port, adjust the URL accordingly. A 401 on wrong credentials is proper authentication behavior; do not "fix" it by manually creating an Authentication in the controller.

### 7.4 HTTP test using Spring Security instead of manual withAuthentication

When testing the **HTTP filter chain**, add `testImplementation 'org.springframework.security:spring-security-test'` and use `WebTestClient` / test security configurers as appropriate, or send a Basic header as below to exercise the real filter:

`src/test/java/com/example/reactivesecurity/WhoAmIHttpTest.java`:

```java
package com.example.reactivesecurity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class WhoAmIHttpTest {

    @Autowired
    WebTestClient client;

    @Test
    void anonymousRequestIsUnauthorized() {
        client.get()
            .uri("/whoami")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedRequestReadsPrincipalFromReactorContext() {
        client.get()
            .uri("/whoami")
            .headers(h -> h.setBasicAuth(
                "reader", "reader-demo-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("reader");
    }
}
```

This test runs against a real Spring Boot WebFlux server with `SecurityConfig` scanned. It does not require `withAuthentication` in the Controller. Conversely, when testing only a service/publisher, `StepVerifier` with `contextWrite(withAuthentication(testAuth))` isolates reactive logic without starting a server. These are **two complementary testing layers**.

## 8. Scope, propagation, concurrency, and subtle bugs

### 8.1 Reactor Context propagates through Reactor operators, not every async API

This example can still read the user:

```java
Mono<String> onAnotherScheduler = Mono.just("start")
    .publishOn(Schedulers.parallel())
    .flatMap(ignored -> username())
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(auth)
    );
```

This snippet uses `username()` and `auth` from the surrounding environment. `publishOn` switches the scheduler, yet the chain still belongs to the Reactor subscription; Reactor Context remains available. Concluding "switching threads always loses context" **is false for properly chained Reactor operators**.

Conversely, if work is dispatched to `new Thread(...)`, `CompletableFuture.supplyAsync(...)`, external SDK callbacks, or a manual `subscribe()` creating a separate subscription, you cannot assume context propagates there automatically. Some libraries/configs provide a **context propagation bridge**, but you must know exactly which mechanism is active and test it rather than relying on a `ThreadLocal` that happens to hold a value.

Never call `block()` to read authentication on the WebFlux event loop. Besides stalling the thread, it can create a new subscription with a context other than what you expect. Instead of:

```java
// Wrong in a reactive request pipeline:
String name = ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName())
    .block();
```

**Keep the flow reactive**:

```java
return ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName())
    .flatMap(this::loadDataForUser);
```

Both blocks are **method snippets**, not standalone code; `loadDataForUser(String)` must return a suitable `Mono<...>`. The main message is to pass the username into downstream operators rather than breaking the flow with `block()`.

### 8.2 Each subscription has its own context, yet objects inside it must be safe

`Context` is only immutable with respect to `put`/`delete` operations. It **does not automatically make every contained object immutable**. `SecurityContextImpl`/`Authentication` have mutable state; avoid sharing a mutable SecurityContext and calling `setAuthentication(...)` across multiple requests or users.

Creating a separate context per subscription in tests is a safe illustration. Do not store an active `Authentication` in a `static` field, mutable singleton bean, simulated global Reactor context, or unpartitioned cache. A pre-created `Mono` does not automatically carry the latest subscription's Authentication.

### 8.3 Placement in flatMap determines scope

When running:

```java
Mono<String> result = Mono.just("go")
    .flatMap(ignored ->
        username().contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(workerAuth)
        )
    )
    .flatMap(inner ->
        username().map(outer -> inner + "/" + outer)
    );
```

When the outer subscriber has no other authentication, the expected result is `"worker/anonymous"`. The inner `username()` receives `workerAuth`, while `username()` in the subsequent `flatMap` does not inherit the inner publisher's context. For the entire upstream region of the outer chain to use the same identity, place `contextWrite(withAuthentication(...))` **at the end of the outer chain** for the authorized scope.

**Do not "fix" this by assigning Authentication to a static/thread-local variable**. Doing so can cause identity or privilege leakage across requests.

### 8.4 Concurrent subscriptions do not turn context into global data

Two-branch example:

```java
Mono<String> fromAlice = username()
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(aliceAuth)
    );

Mono<String> fromBob = username()
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(bobAuth)
    );

Mono.zip(fromAlice, fromBob);
```

They can execute concurrently, yet each branch is bound to the context of its own publisher/subscription. `aliceAuth` does not overwrite `bobAuth` like a global variable would. Be careful not to share mutable state among objects placed **inside** the Context.

### 8.5 clearContext is not logout

`ReactiveSecurityContextHolder.clearContext()` returns a Reactor Context transformation function, used with:

```java
Mono<String> scoped = username()
    .contextWrite(ReactiveSecurityContextHolder.clearContext());
```

It **removes the security key from this publisher's upstream context**. It does not delete cookies, invalidate `WebSession`, revoke access tokens, remove server-side OAuth2 authorized clients, or ensure the next HTTP request is logged out. Real logout must use the appropriate Spring Security logout/session/token mechanism.

## 9. How does an established context affect authorization?

In reactive method security, interceptors such as `@PreAuthorize` read the authenticated principal/authorities from the reactive context. When a service returns a publisher and is proxied by Spring Security in a supported way, subscribing with the appropriate user's context allows the policy to evaluate permissions.

However, **setting context does not create an authorization policy by itself**. For instance, if you supply an `Authentication` with `ROLE_READER`, yet the method/API does not check roles or object ownership, it can still return data that should not be accessed. You must enable `@EnableReactiveMethodSecurity` and configure method annotations/rule logic properly; for HTTP, configure `SecurityWebFilterChain` and `authorizeExchange`.

Moreover, `isAuthenticated()` / authorities only represent attributes **issued by a trusted authenticator**. Do not infer "logged in" merely because an object in tests or internal code carries an authenticated flag.

When calling a downstream HTTP service with `WebClient`, the caller's Reactor Context does not automatically become an `Authorization` header on the outgoing HTTP request. You need OAuth2 Client/authorized client, permitted token relay, mTLS, or a proper service identity mechanism. Never forward a raw user token to another service if audience/scope do not permit it.

## 10. Common mistakes and fixes table

| Mistake | Symptom | Resolution |
| --- | --- | --- |
| Calling Servlet-style `SecurityContextHolder.getContext()` in reactive code | Username wrong/lost when switching schedulers | Use `ReactiveSecurityContextHolder.getContext()` in Reactor chains |
| Placing `contextWrite` on the source before a downstream reader | Reader sees empty or old context | Place `contextWrite` downstream of the operators that need to read |
| Putting string `"alice"` into `Context` then calling `getContext()` | `getContext()` is empty | Use `withAuthentication` / `withSecurityContext` |
| Creating `Authentication` with roles from an unverified HTTP request | Authentication bypass/privilege escalation | Use SecurityWebFilterChain, ReactiveAuthenticationManager, JWT verification, trusted IdP |
| Calling `block()` / manual `subscribe()` in a handler | Context lost or event loop blocked | Compose with `map` / `flatMap` and return `Mono/Flux` |
| Expecting `contextWrite` inside an inner `flatMap` to alter the outer pipeline's context | Subsequent step sees a different/missing principal | Scope `contextWrite` on the outer publisher when needed |
| Expecting `contextWrite` to survive into a new request | New user or background job lacks context | Re-supply context in a valid subscription; for HTTP, let Spring Security manage it |
| Confusing `clearContext()` with logout | Session/token remains active | Use appropriate logout/session invalidation/token revocation |
| Assuming `withAuthentication` alone is enough authorization | Method lacks role/ownership checks | Enable/configure authorization, enforce permissions on resources/services |
| Sending SecurityContext to `WebClient` expecting downstream to receive the user | Downstream returns 401/403 | Explicitly configure permitted credentials/token relay and verify audience/scope |
| Creating a shared context containing mutable Authentication | Data leakage across tasks/users | Keep subscription scope, use appropriate objects, and never mutate shared context |
| Testing a service with contextWrite and concluding HTTP endpoints are secure | Unit tests pass while HTTP auth is broken | Test SecurityWebFilterChain separately with WebTestClient |

## 11. Self-check exercises and answers

**Question 1.** Why is `contextWrite(withAuthentication(auth))` usually placed at the **end** of a pipeline used to read the principal?

Because subscribers originate from downstream and Reactor Context is visible to **upstream** operators. Placing it at the end lets upstream operators like `ReactiveSecurityContextHolder.getContext()` read the supplied `SecurityContext`.

**Question 2.** Does `withAuthentication(new UsernamePasswordAuthenticationToken(...))` verify the password itself?

No. The helper only **wraps a provided Authentication** into context. You must use a proper authentication manager/provider to authenticate. Only use manually constructed authentication in tests or tightly verified and authorized internal cases.

**Question 3.** If you use `publishOn(Schedulers.parallel())` and then read the username, is the context lost?

Normally **no**, as long as it remains within the same properly subscribed Reactor chain and `contextWrite` covers the reader. `Context` propagates with the subscriber rather than relying on staying on the same thread.

**Question 4.** If an inner `flatMap` uses `withAuthentication(workerAuth)`, will a subsequent `flatMap` in the outer chain automatically see `workerAuth`?

No. The new Context is supplied only to the sub-publisher that called `contextWrite`; it does not write backward into the outer sequence's context.

**Question 5.** Does `ReactiveSecurityContextHolder.getContext()` return `SecurityContext` directly or a `Mono<SecurityContext>`?

It returns **`Mono<SecurityContext>`**. It must be handled reactively with `map` / `flatMap`; the publisher can be empty if no security key exists in Reactor Context.

**Question 6.** Can `clearContext()` be used to log out a WebFlux user?

No. It only clears the context key within the scope of the publisher it was applied to; logout must handle sessions/cookies/tokens according to the authentication model.

**Question 7.** If a `StepVerifier` test of a service using `withAuthentication` passes, does that prove the Spring Security HTTP filter protects the endpoint?

Not yet. Publisher tests verify propagation and logic within test scope. Real HTTP tests are needed to prove request authentication, authorization, and CSRF/route policies.

**Question 8.** Is `ctx.put("username", "alice")` enough for `ReactiveSecurityContextHolder.getContext()` to see Alice?

No. `ReactiveSecurityContextHolder` uses an internal structure/key holding `Mono<SecurityContext>` and does not recognize arbitrary custom keys.

## 12. Implementation checklist

- [ ] Have an `Authentication` **verified by a trusted component** before supplying context with `withAuthentication`.
- [ ] Publishers that need to read Authentication sit **upstream** of the applied `contextWrite` position.
- [ ] `ReactiveSecurityContextHolder.getContext()` is handled via `Mono`, handling missing-context cases when appropriate.
- [ ] Scopes of `flatMap`, inner publishers, re-subscriptions, parallel branches, and schedulers are understood and tested.
- [ ] Do not call `block()` on the WebFlux event loop, do not detach subscriptions unintentionally, and do not use mutable global Authentication.
- [ ] Do not treat `withAuthentication` as credential verification, authorization, session storage, or logout.
- [ ] In normal HTTP requests, let Spring Security WebFlux create/restore context and manage the filter chain.
- [ ] Unit test with `StepVerifier`, and HTTP test with `WebTestClient` when endpoint security needs to be proven.
- [ ] If method security is used, configure and test permissions on the actual publishers.
- [ ] For downstream `WebClient` calls, handle credentials/delegation separately via valid security mechanisms.

**Core takeaway:** `ReactiveSecurityContextHolder.withAuthentication(auth)` creates a **Reactor Context carrying a Spring SecurityContext**; `contextWrite(...)` supplies that context to **upstream operators in the applied subscription**. This is a technique for controlling **the presence of SecurityContext in a reactive pipeline**, not a substitute for application authentication and authorization.

### Official documentation

- [Spring Security — ReactiveSecurityContextHolder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html)
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security — Reactive Testing Authentication](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html)
- [Reactor Core — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
- [Reactor Core — Context Propagation Support](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html)
