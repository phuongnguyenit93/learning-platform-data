# ReactiveSecurityContextHolder and Reactor Context

Imagine a Spring WebFlux application handling thousands of concurrent requests. Mai calls `GET /me` and An calls `GET /me` almost simultaneously. Both requests can be processed on a **small group of event-loop threads**, and a single request may switch to another thread when the pipeline uses `publishOn` or chains an asynchronous call. Even so, the application must know the **exact caller of each execution chain** so Mai's profile is never returned to An.

In synchronous Servlet programming, we commonly use `SecurityContextHolder.getContext()`: Spring Security defaults to binding `SecurityContext` to the current thread. In **reactive** programming, the assumption "one thread corresponds to one request" cannot be relied upon as a security foundation. Spring Security provides **`ReactiveSecurityContextHolder`**, built atop **Reactor Context** so identity travels with the **subscriber/subscription** context instead of staying pinned to a Java thread.

This lesson explains: what Reactor Context is, how `ReactiveSecurityContextHolder` reads and puts `SecurityContext` into `Mono`/`Flux` streams, which direction `contextWrite` operates, how WebFlux Security attaches context automatically, which repository persists sessions, why tasks outside Reactor can lose context, and how to write runnable Java 17+ code and tests.

**Scope:** Spring Security **WebFlux/reactive stack** with Project Reactor. Do not confuse `ReactiveSecurityContextHolder` with Servlet `SecurityContextHolder`, and do not use `jakarta.servlet`'s `SecurityContextRepository` for WebFlux. Examples clearly distinguish runnable code from application fragments.

## 1. Separating four objects before reading Reactor Context

| Object | Primary role | Key points |
| --- | --- | --- |
| `Authentication` | Represents the authenticated or authenticating principal, plus authorities | May be username/password, JWT, OAuth2/OIDC, or custom principal |
| `SecurityContext` | Holds the active `Authentication` | May hold an authenticated `Authentication` or no user yet |
| `SecurityContextHolder` | Accesses context using an **imperative** strategy, defaulting to ThreadLocal in Servlet | Not the default source of truth in a Reactor pipeline |
| `ReactiveSecurityContextHolder` | Reads/writes `Mono<SecurityContext>` in **Reactor Context** | Uses `getContext()`, `withAuthentication(...)`, `withSecurityContext(...)`, and `clearContext()` |

Suppose a WebFlux controller writes:

~~~java
// Code fragment placed inside a reactive service/controller.
Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
}
~~~

The return value is **`Mono<String>`**, not a username fetched synchronously when the method is called. Only when a subscriber subscribes to the pipeline does `ReactiveSecurityContextHolder` retrieve that subscription's context.

If no `SecurityContext` exists in Reactor Context, `getContext()` normally completes **empty** (`Mono.empty()`), without fabricating a trusted account or returning `"anonymous"`. To handle a missing context, use `switchIfEmpty`/`defaultIfEmpty` intentionally.

~~~java
// Code fragment inside a reactive application.
Mono<String> nameOrGuest() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .filter(java.util.Objects::nonNull)
        .map(Authentication::getName)
        .defaultIfEmpty("guest");
}
~~~

The string `guest` is strictly a **fallback display value**, never a valid `Authentication` or data-access permission.

## 2. Why is ThreadLocal insufficient in WebFlux?

A common Servlet idiom:

~~~java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();
~~~

This works in imperative flows where Security filters have already bound context to the thread. With Reactor, however:

~~~text
Mai's HTTP request
    |
    v
event-loop-thread-1
    | map(), flatMap()
    v
publishOn(parallel scheduler)
    |
    v
worker-thread-3
    | calls another service
    v
Mai's HTTP response

An's HTTP request
    |
    v
event-loop-thread-1 (may be the exact thread that just served Mai)
    |
    v
An's HTTP response
~~~

**Threads can be reused across many requests, and a single subscription can switch threads.** If code tries fetching the user via `SecurityContextHolder` at an arbitrary point in the pipeline, data may be `null`, unset, or different from what the developer assumed. Worse, manually setting `ThreadLocal` without proper cleanup risks mixing identities across tasks.

It is not that `publishOn` always drops the security context. **Reactor Context is designed to follow the subscription across Reactor operators**, even when scheduling changes. What breaks is **thread-based assumptions** or context left behind when code escapes a managed publisher.

### Two different axes

~~~text
ThreadLocal:
  "Which Thread number am I running on?"
  -> Data is tied to that Thread.

Reactor Context:
  "Which subscription am I a Subscriber in?"
  -> Data is tied to the reactive chain and flows via ContextView.
~~~

Reactor Context is **not** global application memory and not long-term account storage. It acts like a **metadata compartment attached to a subscription**, carrying cross-cutting info along the processing chain such as security context, trace/correlation IDs, or locale when properly managed.

## 3. What is Reactor Context?

Reactor `Context` is an **immutable** key-value data structure at the API level: adding or removing a key returns a new context instead of mutating the old object in place. `ContextView` provides a **read-only** interface for querying existing keys.

Standalone Reactor example (fragment requiring `reactor-core`):

~~~java
Mono<String> pipeline =
    Mono.deferContextual(view ->
        Mono.just("trace=" + view.getOrDefault("traceId", "none"))
    )
    .contextWrite(ctx -> ctx.put("traceId", "req-101"));
~~~

When subscribed, the pipeline can emit:

~~~text
trace=req-101
~~~

Here:

- `Mono.deferContextual(view -> ...)` reads the subscription's `ContextView` **at subscription time**, not when assembly code runs.
- `contextWrite(...)` produces a context visible to **upstream** operators in the segment where it is applied.
- Key `traceId` is merely an application metadata example, not a substitute for `SecurityContext`.
- Two subscriptions can carry two different `traceId` values while sharing the same `Mono` instance.

### Context flows from subscriber upstream

An easy diagram to remember:

~~~text
          UPSTREAM                        DOWNSTREAM
       +--------------+              +-----------------+
       | deferContextual| -> map() -> | contextWrite(...) | -> subscribe()
       +--------------+              +-----------------+
                  ^                              |
                  +----- Context from subscriber-+
~~~

**Data signals** (`onNext`, `onComplete`, `onError`) normally flow from upstream to downstream. **Reactor Context** propagates at subscribe time **from downstream to upstream**. Therefore:

~~~java
Mono<String> result = Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("color", "none"))
    )
    .contextWrite(ctx -> ctx.put("color", "blue"));
~~~

`deferContextual` can read `blue`. However, if `contextWrite` sits **upstream** of a `flatMap` appearing downstream, publishers created inside that downstream `flatMap` are not automatically affected by a context written only for earlier upstream operators.

**Note on scope:** `contextWrite` does not mutate a global variable. It applies to a specific publisher segment within a subscription. To give a business branch a security context, place `contextWrite` at the **downstream boundary** wrapping the branch that needs it. Never copy a user's `Context` into a shared singleton.

### Context is immutable, yet stored values may be mutable

`Context` prevents modifying keys/values inside the old object directly, yet values like `SecurityContext` or `Authentication` can be Java objects with mutable fields. **Do not create one global `SecurityContext` and share it across users** simply because Reactor Context is immutable. Enforcing per-subscription ownership remains the application's responsibility.

## 4. Core ReactiveSecurityContextHolder API

Class:

~~~java
org.springframework.security.core.context.ReactiveSecurityContextHolder
~~~

Four key methods in modern Spring Security:

~~~java
// API showing actual signatures; imports omitted to focus on meaning.
static Mono<SecurityContext> getContext();

static reactor.util.context.Context withAuthentication(
        Authentication authentication);

static reactor.util.context.Context withSecurityContext(
        Mono<? extends SecurityContext> securityContext);

static java.util.function.Function<
    reactor.util.context.Context,
    reactor.util.context.Context> clearContext();
~~~

### 4.1. getContext(): reads per subscription, not ThreadLocal

~~~java
Mono<String> username = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName);
~~~

`getContext()` returns `Mono<SecurityContext>`, so you can compose it with `flatMap`, `switchIfEmpty`, `filter`, `zipWhen`, or reactive policies. There is no need to call `block()` to get the name in a WebFlux controller: return `Mono<String>` and let the framework subscribe properly.

The `Mono` can complete empty: **never throw a `NullPointerException`** by assuming context always exists. If an endpoint requires login, Spring Security authorization should reject anonymous **before** the controller is invoked. For public endpoints, handle missing context per policy.

### 4.2. withAuthentication(authentication): sets context for a chain

~~~java
Authentication identity = UsernamePasswordAuthenticationToken.authenticated(
    "mai", null,
    java.util.List.of(new SimpleGrantedAuthority("ROLE_USER"))
);

Mono<String> who = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName);

Mono<String> answer = who.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(identity)
);
~~~

Here `identity` is an object marked authenticated for **illustration/testing**, not a valid result built from self-declared user data. In a real app, `Authentication` must come from a mechanism that **verified password/token/SSO**. `withAuthentication` only **places an existing identity into context**; it does not verify credentials.

This method returns a `reactor.util.context.Context` merged via `contextWrite(...)`. **It does not behave like `SecurityContextHolder.setContext` writing a global variable**, nor does it automatically persist a session in the HTTP response.

### 4.3. withSecurityContext(Mono<SecurityContext>): provides context via publisher

Another way to use it:

~~~java
SecurityContext securityContext = new SecurityContextImpl();
securityContext.setAuthentication(identity);

Mono<String> answer = who.contextWrite(
    ReactiveSecurityContextHolder.withSecurityContext(
        Mono.just(securityContext)
    )
);
~~~

Unlike `withAuthentication`, this accepts **a `Mono<SecurityContext>`**. It is useful when context is loaded from a reactive store or produced by an asynchronous verified step. Never use `Mono.just` with a `null` context; Reactor does not support emitting `null` as a valid data signal.

Never build a `Mono<SecurityContext>` from an unverified username header or claim and pass it to `withSecurityContext`: that **marks an unverified identity as trusted**.

### 4.4. clearContext(): removes the security key from a pipeline segment

~~~java
Mono<String> anonymousView =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .defaultIfEmpty("anonymous")
        .contextWrite(ReactiveSecurityContextHolder.clearContext());
~~~

`clearContext()` returns a **Reactor Context transformer function** passed to `contextWrite`. It drops `ReactiveSecurityContextHolder`'s key for the **upstream segment it applies to**; it does not delete server sessions, revoke JWTs, or log out all devices.

**Ordering matters:** in `chain.contextWrite(clearContext()).contextWrite(withAuthentication(mai))`, operators upstream of `clearContext` see no identity even though downstream sets Mai. Because `contextWrite` operators participate during subscription from downstream, placement determines scope.

## 5. Standalone Java 17+ example: two users, two subscriptions, one thread switch

Before integrating WebFlux HTTP, observe Reactor Context in a program **without a web server**. This cleanly isolates the core: Spring Security Core provides `ReactiveSecurityContextHolder`, while Project Reactor provides `Mono`, `contextWrite`, and schedulers.

### 5.1. Create the Gradle project

~~~text
reactive-context-core-demo/
  build.gradle
  src/main/java/ReactiveContextDemo.java
  src/test/java/ReactiveContextDemoTest.java
~~~

Create `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    // BOM only manages compatible versions; this is not a Boot app.
    implementation platform('org.springframework.boot:spring-boot-dependencies:4.1.2')
    testImplementation platform('org.springframework.boot:spring-boot-dependencies:4.1.2')

    implementation 'org.springframework.security:spring-security-core'
    implementation 'io.projectreactor:reactor-core'

    testImplementation 'org.junit.jupiter:junit-jupiter'
    testImplementation 'io.projectreactor:reactor-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

application {
    mainClass = 'ReactiveContextDemo'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

The project uses the **Spring Boot BOM** for aligned dependency versions without the Spring Boot plugin, since it simply runs `public static void main` via Gradle's application plugin. Requires JDK 17+, Gradle supporting Java 17, and Maven Central access on initial dependency download.

### 5.2. Complete, compilable/runnable Java

Create `src/main/java/ReactiveContextDemo.java`:

~~~java
import java.util.List;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextImpl;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public final class ReactiveContextDemo {

    private static Authentication user(String name) {
        // DEMO ONLY: in production verify credentials before
        // constructing an authenticated Authentication.
        return UsernamePasswordAuthenticationToken.authenticated(
            name, null, List.of(new SimpleGrantedAuthority("ROLE_USER")));
    }

    private static Mono<String> currentName() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName)
            .defaultIfEmpty("anonymous");
    }

    public static void main(String[] args) {
        Authentication mai = user("mai");
        Authentication an = user("an");

        // Same publisher; three subscriptions observe
        // three independent contexts per each subscription's contextWrite.
        Mono<String> lookup = currentName();

        System.out.println("without=" + lookup.block());

        System.out.println("with-mai=" + lookup
            .contextWrite(ReactiveSecurityContextHolder
                .withAuthentication(mai))
            .block());

        System.out.println("with-an=" + lookup
            .contextWrite(ReactiveSecurityContextHolder
                .withAuthentication(an))
            .block());

        System.out.println("cleared=" + lookup
            .contextWrite(ReactiveSecurityContextHolder.clearContext())
            .contextWrite(ReactiveSecurityContextHolder.withAuthentication(mai))
            .block());

        // Reading context happens AFTER publishOn inside flatMap.
        Mono<String> switched = Mono.just("start")
            .publishOn(Schedulers.parallel())
            .flatMap(ignored -> ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName))
            .contextWrite(ReactiveSecurityContextHolder.withAuthentication(mai));

        System.out.println("after-thread-switch=" + switched.block());

        SecurityContext saved = new SecurityContextImpl();
        saved.setAuthentication(an);
        System.out.println("with-security-context=" + lookup
            .contextWrite(ReactiveSecurityContextHolder
                .withSecurityContext(Mono.just(saved)))
            .block());
    }
}
~~~

From the project directory:

~~~bash
java -version
gradle --version
gradle run --quiet
~~~

Expected output printed by the `println` statements:

~~~text
without=anonymous
with-mai=mai
with-an=an
cleared=anonymous
after-thread-switch=mai
with-security-context=an
~~~

The output reflects the **deterministic API logic of the example**, independent of thread names, scheduler speed, or system timing. The program uses `block()` strictly because **this is a CLI boundary inside `main`**; inside a WebFlux request handler you must not `block()` like this.

Line-by-line explanation:

1. `without=anonymous`: the subscription has no security key; `getContext()` emits no `SecurityContext`, so `defaultIfEmpty` triggers.
2. `with-mai=mai`: the first subscription carries Mai's `Authentication` supplied by `withAuthentication`.
3. `with-an=an`: reuses the **same `lookup` publisher**, yet a separate subscription carries An. No global ThreadLocal variable is "overwritten with another user".
4. `cleared=anonymous`: in the upstream scope, `clearContext` applies after downstream `withAuthentication(mai)` inserts data.
5. `after-thread-switch=mai`: the `flatMap` running after `publishOn` still reads the right Reactor Context; switching schedulers in Reactor does not mean losing context.
6. `with-security-context=an`: `withSecurityContext(Mono.just(saved))` supplies the context containing An's `Authentication`.

**Security boundary:** `user(name)` in the example intentionally builds an `authenticated` token from a literal to teach Reactor Context. It is **not a login method**; never take a client-sent username and use this logic to mark it authenticated in production.

### 5.3. Testing subscriptions and missing context

Create `src/test/java/ReactiveContextDemoTest.java`:

~~~java
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactiveContextDemoTest {

    private static Authentication identity(String name) {
        return UsernamePasswordAuthenticationToken.authenticated(
            name, null, List.of(new SimpleGrantedAuthority("ROLE_USER")));
    }

    private static Mono<String> currentName() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);
    }

    @Test
    void samePublisherCanSeeSeparateIdentities() {
        Mono<String> lookup = currentName();

        StepVerifier.create(lookup.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(identity("mai"))))
            .expectNext("mai")
            .verifyComplete();

        StepVerifier.create(lookup.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(identity("an"))))
            .expectNext("an")
            .verifyComplete();
    }

    @Test
    void noContextProducesEmptyPublisher() {
        StepVerifier.create(currentName())
            .verifyComplete();
    }

    @Test
    void clearContextRemovesUpstreamSecurityIdentity() {
        StepVerifier.create(currentName()
                .contextWrite(ReactiveSecurityContextHolder.clearContext())
                .contextWrite(ReactiveSecurityContextHolder
                    .withAuthentication(identity("mai"))))
            .verifyComplete();
    }
}
~~~

Run:

~~~bash
gradle test
~~~

Expected result: **3 tests pass** when JDK/Gradle/dependencies are configured properly. `noContextProducesEmptyPublisher` confirms absence is represented by an empty publisher. `samePublisherCanSeeSeparateIdentities` proves **no identity leaks from one subscription to another** when contexts are supplied separately.

All three tests construct `Authentication` to **simulate a trusted identity in unit tests**, not to prove a provider verified passwords. Production systems must also test the authentication manager, WebFlux security filter chain, and authorization.

## 6. How does Spring WebFlux automatically attach Reactive SecurityContext?

In a WebFlux application with Spring Security, you do not write `contextWrite(withAuthentication(...))` in every controller. Security web filters are configured to **load or construct a verified Authentication and place it into Reactor Context** per request.

Diagram:

~~~text
HTTP request / WebFlux ServerWebExchange
                |
                v
           SecurityWebFilterChain
                |
                +--> context repository if present
                |       ReactorContextWebFilter
                |       -> supplies SecurityContext to Reactor Context
                |
                +--> AuthenticationWebFilter or mechanism-specific filter
                |       -> ReactiveAuthenticationManager verifies credentials
                |       -> produces trusted Authentication
                |
                +--> AuthorizationWebFilter
                |       -> accesses Authentication in reactive context
                |
                v
          Router/Controller/Service
                |
                +--> ReactiveSecurityContextHolder.getContext()
                |
                v
          Mono/Flux response and subscriber
~~~

This is a **conceptual** diagram, not the exact class/filter ordering across every JWT, Basic, OAuth2 mechanism and version. What matters is that web security and reactive method security both use the **appropriate Reactor Context**.

Two classes worth remembering:

- `ReactorContextWebFilter` uses `ServerSecurityContextRepository` to source `SecurityContext` for `ReactiveSecurityContextHolder`.
- `AuthenticationWebFilter` is used in many reactive authentication flows; depending on config, it converts the request to `Authentication`, calls `ReactiveAuthenticationManager`, and handles success/failure and context.

Specialized mechanisms like JWT Resource Server may use different components and persistence policies. Never assume every login uses a shared web session or that every `Authentication` is created by a single `AuthenticationWebFilter`.

### Which classes differ from Servlet?

| Servlet / Spring MVC | Reactive / Spring WebFlux |
| --- | --- |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `HttpSecurity` | `ServerHttpSecurity` |
| `SecurityContextHolder` (thread strategy) | `ReactiveSecurityContextHolder` (Reactor Context) |
| `AuthenticationManager` | `ReactiveAuthenticationManager` |
| `UserDetailsService` | `ReactiveUserDetailsService` |
| `SecurityContextRepository` | `ServerSecurityContextRepository` |
| `HttpSessionSecurityContextRepository` | `WebSessionServerSecurityContextRepository` |
| `NullSecurityContextRepository` | `NoOpServerSecurityContextRepository` |
| `jakarta.servlet.http.HttpServletRequest` | `ServerWebExchange` |

Similar names, yet **non-interchangeable interfaces**. Servlet's `SecurityContextRepository` has `saveContext(..., HttpServletRequest, HttpServletResponse)` and `loadDeferredContext(HttpServletRequest)`; WebFlux has `ServerSecurityContextRepository.save(exchange, context): Mono<Void>` and `load(exchange): Mono<SecurityContext>`.

## 7. WebFlux session repository vs active Reactor Context

This is a critical distinction:

- **Reactor Context:** binds identity to the **subscription** while processing a request or operation.
- **`ServerSecurityContextRepository`:** determines whether the authenticated identity can be **saved/loaded across requests**, depending on implementation.
- **`WebSession`:** a server-side store that can link multiple HTTP requests via a session cookie.
- **Bearer token:** can be verified **on every request** without session persistence.

Reactive interface:

~~~java
// Summary signatures from WebFlux API, not a standalone class.
Mono<SecurityContext> load(ServerWebExchange exchange);

Mono<Void> save(ServerWebExchange exchange, SecurityContext context);
~~~

This is `org.springframework.security.web.server.context.ServerSecurityContextRepository`; do not use `jakarta.servlet`.

Key implementations:

| Class | Behavior | When useful |
| --- | --- | --- |
| `WebSessionServerSecurityContextRepository` | Saves/reads SecurityContext in WebFlux `WebSession` | Login flows with sessions and cookies |
| `NoOpServerSecurityContextRepository` | Does not persist context across requests | Stateless APIs verifying bearer tokens per request |
| Custom repository | Loads/saves context via app-controlled store | Specialized cases needing security & lifecycle tests |

With Spring Security-provided filters, successful authentication configuration controls placing context into Reactor Context and which repository is used. When writing a custom flow, inspect **both**: the current request's context and how persistence works if future requests should stay logged in.

**Do not infer:** because `getContext()` returns Authentication in request A, request B is guaranteed to stay authenticated. Reactor Context is not a cross-HTTP-request persistence mechanism.

### Common mistake when calling reactive save manually

A broken fragment:

~~~java
// WRONG: Mono<Void> is a lazy publisher; never subscribed so
// no save operation may occur.
serverSecurityContextRepository.save(exchange, context);
return Mono.just("ok");
~~~

The right way is to **compose** the save work into the returned pipeline:

~~~java
// Fragment inside a reactive authentication flow after verifying identity.
return serverSecurityContextRepository.save(exchange, context)
    .thenReturn("ok");
~~~

This is not a full production login implementation: you still need CSRF, cookie/session strategy, credential handling, logout, failure handling, policies, and account checks. Still, it illustrates a vital reactive rule: **an unsubscribed/uncomposed Mono will not execute its side effect**.

Do not call `.subscribe()` manually inside a controller just to trigger saving; detaching from the pipeline can lose context, swallow errors, and race with the response. Return a `Mono` chained via `then`/`flatMap` and let WebFlux subscribe.

## 8. Runnable WebFlux example: API reading identity from Reactor Context

The complete HTTP application below uses **Spring Boot 4.1.2**, WebFlux, reactive Spring Security, and HTTP Basic so it can be called with `curl`. It demonstrates:

- `GET /public` allows anonymous access.
- `GET /me` requires authentication; the controller reads username via `ReactiveSecurityContextHolder.getContext()`.
- User `mai` has `ROLE_USER` and cannot access `/admin`.
- User `admin` has `ROLE_ADMIN` and is allowed on `/admin`.
- Identity lives in the reactive context populated by the standard filter chain, without touching `ThreadLocal`.

**HTTP Basic here is for local demonstration only**; production needs HTTPS, throttling, credential lifecycles, redacted logs, and proper authentication design.

### 8.1. Structure

~~~text
webflux-security-context-lab/
  pom.xml
  src/main/java/com/example/reactive/
    ReactiveSecurityApplication.java
    SecurityConfiguration.java
    IdentityController.java
~~~

### 8.2. Maven pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>webflux-security-context-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
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
~~~

Use only `spring-boot-starter-webflux` — **do not** add `spring-boot-starter-webmvc`: when both MVC and WebFlux are present, Spring Boot may favor Servlet over WebFlux unless the application type is explicitly overridden. Keeping a single reactive web stack prevents unintended mixing of `SecurityContextHolder` and `ReactiveSecurityContextHolder`.

### 8.3. Main class

Create `src/main/java/com/example/reactive/ReactiveSecurityApplication.java`:

~~~java
package com.example.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveSecurityApplication.class, args);
    }
}
~~~

### 8.4. SecurityWebFilterChain + ReactiveUserDetailsService

Create `src/main/java/com/example/reactive/SecurityConfiguration.java`:

~~~java
package com.example.reactive;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails mai = User.withUsername("mai")
            .password(encoder.encode("demo-password"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("demo-password"))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(mai, admin);
    }

    @Bean
    SecurityWebFilterChain webFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public").permitAll()
                .pathMatchers("/admin").hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

`MapReactiveUserDetailsService` is a **reactive** implementation of `ReactiveUserDetailsService`. It stores users in memory strictly for demos, not as a production user store. `BCryptPasswordEncoder` hashes passwords rather than keeping plaintext in `UserDetails`.

`SecurityWebFilterChain` and `ServerHttpSecurity` are reactive types, distinct from Servlet's `SecurityFilterChain`/`HttpSecurity`. `hasRole("ADMIN")` checks authority `ROLE_ADMIN` by default. There is no need to build `Authentication` manually from client strings, as standard filters/providers verify credentials.

### 8.5. Controller reading the subscription's security context

Create `src/main/java/com/example/reactive/IdentityController.java`:

~~~java
package com.example.reactive;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class IdentityController {

    @GetMapping("/public")
    public Mono<String> publicPage() {
        return Mono.just("public");
    }

    @GetMapping("/me")
    public Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName)
            .map(name -> "hello-" + name);
    }

    @GetMapping("/admin")
    public Mono<String> admin() {
        return Mono.just("admin-area");
    }
}
~~~

`me()` never calls `block()`, `subscribe()`, or `SecurityContextHolder.getContext()`. It returns a `Mono<String>`, letting the **framework subscribe per active request**. With valid Basic credentials, security filters populate the reactive context so `getContext()` yields a verified Authentication.

If a public endpoint wants to display a guest name, provide an explicit fallback such as `defaultIfEmpty("guest")`. In `/me`, however, `anyExchange().authenticated()` already requires an authenticated caller, so the code need not grant access to anonymous callers.

### 8.6. Running with Maven and testing HTTP

~~~bash
java -version
mvn -version
mvn -q -DskipTests package
mvn spring-boot:run
~~~

In another terminal:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u mai:demo-password http://localhost:8080/me
curl -i -u mai:demo-password http://localhost:8080/admin
curl -i -u admin:demo-password http://localhost:8080/admin
~~~

Results under the demo policy:

| Request | Expected status | Body on success |
| --- | --- | --- |
| Anonymous `GET /public` | `200` | `public` |
| Anonymous `GET /me` | `401` per Basic entry point | Message/challenge depending on config |
| Mai `GET /me` | `200` | `hello-mai` |
| Mai `GET /admin` | `403` | Denied admin content |
| Admin `GET /admin` | `200` | `admin-area` |

These are **expected results inferred from SecurityWebFilterChain and the code**; the code was not executed inside this guide. If an app has multiple chains, form login, reverse proxies, or custom entry points, response status/body may vary.

Demo passwords appear in `curl` because this is a local environment. **Never pass real credentials on the command line or in shell history**, and never use unencrypted HTTP over the Internet. Production requires HTTPS and log sanitization so `Authorization` headers are never logged.

## 9. @EnableReactiveMethodSecurity and service-layer permissions

WebFlux authorization is not limited to URLs. With reactive Spring Security, you can enable **method security**:

~~~java
@Configuration
@EnableReactiveMethodSecurity
class ReactiveMethodSecurityConfiguration {
}
~~~

Requires importing `org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity`; this is a **fragment**, not a third complete project. Protected methods normally must return a `Publisher` like `Mono` or `Flux` so enforcement integrates properly with Reactor Context. Depending on version/setup, Kotlin coroutines have dedicated support.

Service example:

~~~java
// Fragment inside a Spring-proxied @Service bean.
@PreAuthorize("hasRole('ADMIN')")
public Mono<String> adminSummary() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(auth -> "admin-summary-for-" + auth.getName());
}
~~~

For `@PreAuthorize` to take effect, method security must be enabled and calls must go **through the Spring proxy** (do not `new` the service or self-invoke a secured method expecting AOP to intercept). Even with `ADMIN`, still check **record/tenant-specific permissions** when handling sensitive data.

Reactive Spring Security method authorization relies on Reactor Context, so setting a `ThreadLocal` `SecurityContextHolder` in a controller does not give the subscriber the right identity.

### When to use an Authentication parameter instead of ReactiveSecurityContextHolder?

In WebFlux, Spring can resolve a `Principal` or `Mono<Principal>` for matching handlers. At the **service layer**, however, avoid coupling directly to WebFlux's `ServerWebExchange` just to find the caller; `ReactiveSecurityContextHolder.getContext()` is the clean reactive integration point.

For larger business logic, create a `CurrentActorResolver` returning `Mono<CurrentActor>` that extracts the verified `accountId` and loads the current account. This decouples the security principal from domain accounts and eases testing.

## 10. With long-lived Flux or streaming, context lives per subscription

A WebFlux endpoint can return a long-running `Flux<Event>` (Server-Sent Events) or a service can subscribe to multiple sources. Reactor Context stays bound to the **subscription** and does not vanish simply because threads switch. Still, watch these design points:

- A `Flux` can be **subscribed multiple times**. Each subscription needs its own proper context.
- If a publisher is **shared/hot** across multiple users, items emitted from the shared source must be filtered/authorized per **individual subscriber/request**, never turning the first subscriber's `SecurityContext` into a global variable.
- During long streams, roles or account status may change mid-stream. Account for **permission revocation latency** and closing streams when an account is locked.
- Never `cache()` results containing user A's data in a singleton and serve them to user B without safe cache keys/policies.
- Reactor's `publishOn` does not drop context by default, yet **escaping the pipeline** into a non-Reactor library callback can lose scope.

Warning example:

~~~java
// WRONG: subscribing manually inside a controller, detached from request management.
public Mono<String> handler() {
    service.findData()
        .subscribe(value -> sendSomewhere(value)); // detached side effect
    return Mono.just("accepted");
}
~~~

`sendSomewhere` is undefined, making this a **warning fragment**. The issue is that errors, cancellation, backpressure, and context in the detached branch are no longer managed by the publisher WebFlux subscribes to.

Instead **compose**:

~~~java
// Fragment: service and sender return appropriate Monos.
public Mono<String> handler() {
    return service.findData()
        .flatMap(value -> sender.send(value).thenReturn("accepted"));
}
~~~

When components stay inside one proper reactive pipeline, context, errors, and cancellation are managed consistently. Never assume any method returning `Mono` is automatically secure: still verify authorization before reading or emitting data.

## 11. Boundaries that commonly lose context

### 11.1. CompletableFuture and raw Executors

A `CompletableFuture.supplyAsync(...)` or `ExecutorService.submit(...)` task **does not automatically inherit Reactor Context** just because it was started inside a `flatMap`. Code on that thread calling `SecurityContextHolder.getContext()` may see empty; nor can it blindly call `ReactiveSecurityContextHolder.getContext()` unless subscribed within a Reactor chain carrying context.

When passing metadata across this boundary, pass a **verified CurrentActor/subject ID** as an explicit parameter or use the Reactor/Micrometer/Spring Security context propagation mechanism for your version. Never pass raw passwords, bearer tokens, or the entire `Authentication` into long-lived jobs without dedicated security architecture.

### 11.2. ThreadLocal MDC and logging

Logging MDC usually relies on ThreadLocal. `contextWrite(ctx -> ctx.put("traceId", ...))` does not guarantee MDC keeps the right value across every scheduler without a configured bridge. Likewise, enabling a tracing-context propagation integration **does not mean security context automatically propagates the way you expect**.

**Never put passwords, access tokens, or full JWT claims into MDC/traces** to "debug context". Log only minimal, permitted data like correlation IDs and policy-approved account IDs.

### 11.3. block() on the event loop

In the CLI demo, `block()` waits for results to print to stdout. In WebFlux, calling `block()` or `blockOptional()` inside a request handler stalls the event loop and can even throw exceptions on non-blocking threads depending on scheduler. Do not blindly offload everything onto `boundedElastic`.

If relying on blocking libraries (JDBC, legacy file I/O), isolate blocking parts onto a dedicated scheduler and test concurrency/latency; reactive services themselves should return `Mono`/`Flux` so the pipeline preserves context.

### 11.4. Treating Reactor Context as permanent session storage

No. Once the HTTP request completes, the subscription ends. The next request requires fresh authentication or a repository/session/token to restore identity. `ReactiveSecurityContextHolder.withAuthentication(mai)` does not emit session cookies or revoke JWTs.

### 11.5. Minting an authenticated Authentication from client input

Dangerous example:

~~~java
// WRONG: username from query param/unverified input marked as trusted.
Authentication auth = UsernamePasswordAuthenticationToken.authenticated(
    usernameFromRequest,
    null,
    java.util.List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
);
return securedAction.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(auth)
);
~~~

This is **direct privilege escalation** if used in a real request. `withAuthentication` only places an object into Reactor Context; it checks no password, JWT signature, or account authority. In production, identity must come from verified filters/providers/managers and authoritative role assignments.

## 12. Comparing context mutations: global set, withAuthentication, and clearContext

| Action | Imperative Servlet | Reactive Reactor |
| --- | --- | --- |
| Read identity | `SecurityContextHolder.getContext()` | `ReactiveSecurityContextHolder.getContext()` |
| Set identity for execution | `SecurityContextHolder.setContext(ctx)` | `publisher.contextWrite(withAuthentication(auth))` |
| Clear local association | `SecurityContextHolder.clearContext()` | `publisher.contextWrite(clearContext())` with right scope |
| Persist across requests | `SecurityContextRepository` with servlet request/response | `ServerSecurityContextRepository` with `ServerWebExchange` |
| Password user store | `UserDetailsService` | `ReactiveUserDetailsService` |
| Filter chain | `SecurityFilterChain` | `SecurityWebFilterChain` |

**Imperfect equivalence:** `ReactiveSecurityContextHolder.clearContext()` only returns a context modifier function for a reactive branch. It is not an immediate mutation of the current ThreadLocal. Only when `contextWrite` sits in the right position does the upstream subscription see the key removed.

### Nested old and new contexts

Suppose an outer request has identity Mai. In a unit test, we want to execute a sub-branch under identity An:

~~~java
Mono<String> check = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName);

Mono<String> asAn = check.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(testAn)
);
~~~

This is a **test snippet**, where `testAn` is an `Authentication` built from a trusted fixture, not user input. `asAn` reads An **in its specific upstream segment**, without switching the whole request's other pipelines to An. Overwriting context in production code can cause **confused deputy** bugs: a module acts under permissions different from the actual caller.

Best practice: never override security context to "fix a missing user error". Fix how the publisher connects to the security chain or pass a controlled actor for genuinely authorized work.

## 13. Authentication and authorization: a valid context is not enough

A context with `Authentication.isAuthenticated()==true` does not mean the user can view any record. Two layers:

~~~text
Authentication:
   Is there a verified token/password?
   Which account does the identity belong to?
   Were MFA/required policies passed?
             |
             v
Reactor Context holds verified Authentication
             |
             v
Authorization:
   Allowed to perform the action?
   Belongs to the tenant?
   Resource owned by/validly shared with principal?
   Account still enabled, token/session not revoked?
             |
             v
Execute permitted operation only
~~~

In multi-tenant apps, a user with `ROLE_ADMIN` in company A is not automatically allowed to read company B's data. `ReactiveSecurityContextHolder.getContext()` identifies the **current principal**; services/authorization managers still must verify membership, owner, tenant, and resource policies.

A service fragment:

~~~java
// Fragment inside a reactive service; repository/policy are app components.
public Mono<DocumentView> findDocument(String documentId) {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .flatMap(auth -> documentRepository.findById(documentId)
            .flatMap(document ->
                authorizationPolicy.canRead(auth, document)
                    .filter(Boolean::booleanValue)
                    .switchIfEmpty(Mono.error(
                        new AccessDeniedException("Forbidden")))
                    .thenReturn(mapper.toView(document))
            )
        );
}
~~~

This is an **architectural fragment**, not a standalone class; it requires `DocumentView`, `authorizationPolicy`, mapper, repository, and null/error handling. Ensure `DocumentView` is never emitted before the policy approves; for sensitive data, filter queries at the database level by tenant/owner as well.

Never grant access if `getContext()` completes empty. In authenticated APIs the security chain must deny it; in services missing context must follow policy (typically deny, never falling back to a "default user").

## 14. Testing reactive context properly

There are three key layers:

### Layer A — Reactor Context unit tests

Use `StepVerifier` and `contextWrite(withAuthentication(...))` to assert publishers read the expected principal, separate subscriptions, and never leak data. Section 5 provides three complete tests.

### Layer B — WebFlux filter chain

Use `WebTestClient` or HTTP integration tests to confirm:

- Anonymous requests to `/me` are rejected.
- Valid users reading `/me` see the right username.
- User Mai accessing `/admin` is denied despite valid Basic credentials.
- Admin accessing `/admin` succeeds.
- Two concurrent requests with different credentials never see each other's identity.

Do not rely solely on `@WithMockUser` tests to prove passwords were verified: the annotation injects a pre-built security context, bypassing `ReactiveAuthenticationManager` or `ReactiveUserDetailsService`.

### Layer C — Non-Reactor boundaries and repositories

Verify behavior across `publishOn`, `subscribeOn`, `flatMap`, WebClient, external library callbacks, executors, session persistence, and token-based requests. Tests must mirror where context is populated and where code reads it.

A test matrix:

| Scenario | Expected outcome |
| --- | --- |
| Publisher without security context | `getContext()` empty; service handles per policy |
| `withAuthentication(mai)` on one subscription | Reads Mai in matching upstream |
| One publisher subscribed with Mai then An | Each subscription sees its own identity |
| `clearContext()` applied at right scope | Upstream has no security context |
| `publishOn` inside same Reactor chain | Right context still reaches downstream branch |
| Manual `CompletableFuture`/executor | Do not assume Reactor Context exists inside |
| `block()` in CLI `main` | Acceptable to await result |
| `block()` on WebFlux event loop | Avoid; can stall or error |
| Valid WebFlux HTTP Basic | `ReactiveSecurityContextHolder` sees verified Authentication |
| Wrong password or invalid token | No trusted privileged context created |
| USER role calls ADMIN endpoint | Denied by authorization |
| Invalidated WebFlux session | Permissions not restored from old session |
| Expired JWT token | Rejected by decoder/validator |
| Role revoked after token/session issued | Policy defines refresh latency and revocation mechanism |
| Shared hot Flux | No A-to-B data leak via shared cache/source |
| Exception mid-pipeline | Must not mark success or emit pre-authz data |

One valuable testing rule: **never assert thread names** to prove correct identity. Thread scheduling is an execution detail; assert Authentication/username/authorities per subscription.

## 15. Common misconceptions

1. **"ReactiveSecurityContextHolder is also a ThreadLocal."** No. It reads context attached to the Reactor subscription.
2. **"WebFlux is still one thread per request like Servlet."** False; pipelines share and switch threads.
3. **"Reading `SecurityContextHolder.getContext()` inside `flatMap` always gives the right user."** Not by default; use the reactive API.
4. **"`ReactiveSecurityContextHolder.getContext()` returns `SecurityContext` directly."** It returns `Mono<SecurityContext>`.
5. **"Missing context automatically defaults to `ROLE_USER` or authenticated=true."** No; absence must be handled safely.
6. **"`contextWrite` mutates a global map."** No; context is per subscription and scoped.
7. **"`contextWrite` pushes data in the `onNext` direction."** No; context propagates from subscriber upstream.
8. **"Placing `contextWrite` anywhere affects every operator."** No; chain position matters.
9. **"`withAuthentication(username)` verifies the password."** It accepts an existing `Authentication`; it does not verify credentials.
10. **"Having Authentication in Reactor Context means an HTTP session exists."** No; these are two distinct lifecycles.
11. **"`ServerSecurityContextRepository` is the same interface as Servlet's `SecurityContextRepository`."** No; different methods and stacks.
12. **"`NoOpServerSecurityContextRepository` validates JWTs automatically."** No; you need filters/decoders.
13. **"Calling `save(exchange, context)` without subscribing is enough."** No; you must compose the publisher.
14. **"Calling `.subscribe()` in a controller makes it faster."** Easily loses errors/cancellation/context and detaches work from the request.
15. **"`publishOn` always wipes Reactor Context."** No; Reactor operators preserve context within the same subscription.
16. **"`CompletableFuture.supplyAsync` inherits all Reactor Context keys by default."** No; requires a bridge or controlled data passing.
17. **"`block()` in WebFlux is the easiest way to get username."** Avoid it; return Mono/Flux.
18. **"Because Reactor Context is immutable, one mutable SecurityContext can be shared across all users."** No; values inside can be mutable and hold per-user identity.
19. **"`clearContext()` logs out all devices."** No; it only clears the key in that publisher's scope.
20. **"Having ROLE_ADMIN grants access to every tenant."** No; object/tenant-level authorization is still required.
21. **"`@EnableReactiveMethodSecurity` protects arbitrary methods without Publishers."** Reactive method security contracts require compatible reactive return types/call paths and Spring proxies.
22. **"Once HTTP Basic request A succeeds, request B needs no credentials."** Not by default; Basic normally checks the header on every request.
23. **"Putting a client-supplied token into withSecurityContext makes it valid."** No; tokens must pass signature/issuer/audience/expiry validation.
24. **"A publisher can cache A's data and serve B as long as security context exists."** No; caches leak data if keys/scopes are wrong.
25. **"`@WithMockUser` tests prove real providers work."** No; mock tests fake identity without verifying passwords or tokens.

## 16. Self-check questions

**Q1.** What return type does `ReactiveSecurityContextHolder.getContext()` produce?

*Answer:* `Mono<SecurityContext>` retrieved from the subscription's Reactor Context.

**Q2.** Why is `SecurityContextHolder.getContext()` not a reliable default in a WebFlux reactive pipeline?

*Answer:* `SecurityContextHolder` binds context to a thread by default, whereas reactive subscriptions can switch or share threads. Reactor Context bound to the subscriber fits better.

**Q3.** Does `withAuthentication(auth)` verify passwords?

*Answer:* No. It creates a context wrapping an existing `Authentication` for `contextWrite` to supply to a chain. The Authentication must come from a verified source.

**Q4.** Does `contextWrite` affect upstream or downstream operators?

*Answer:* It supplies context to **upstream** operators when subscription travels from downstream.

**Q5.** Why can the exact same `Mono<String>` return Mai then An across two subscriptions?

*Answer:* Because each subscription gets its own Reactor Context; `withAuthentication` scopes to the subscription rather than mutating a global user.

**Q6.** Does `publishOn(Schedulers.parallel())` automatically erase Reactor Context?

*Answer:* Not inside a properly connected Reactor chain; context is carried across operators. Stepping out into raw executors/callbacks detached from the pipeline is a different boundary.

**Q7.** Does `clearContext()` revoke an access token on the client?

*Answer:* No. It removes the security key from Reactor Context's scope; JWT/token lifetimes and revocation need dedicated mechanisms.

**Q8.** Which repository does WebFlux use instead of Servlet's `HttpSessionSecurityContextRepository`?

*Answer:* `WebSessionServerSecurityContextRepository`, which stores context in WebFlux's `WebSession`; the interface is `ServerSecurityContextRepository`.

**Q9.** If you call `repository.save(exchange, context)` and discard the `Mono<Void>`, is context saved?

*Answer:* You cannot treat it as saved; Monos are lazy and must be composed/subscribed by the flow.

**Q10.** Why should a WebFlux controller return `Mono<String>` instead of calling `getContext().block()`?

*Answer:* Returning a publisher lets the framework manage subscriber context, non-blocking execution, errors, and cancellation. Blocking on the event loop risks stalls or exceptions.

**Q11.** Does a context with `ROLE_ADMIN` in the current request prove the admin can read every tenant's data?

*Answer:* No; permissions must still be checked per tenant, owner/resource, state, and policy.

**Q12.** When unit testing with `withAuthentication`, do you need a real password?

*Answer:* No. Build an Authentication fixture in tests to verify propagation; to test real authentication, exercise filters/providers/managers.

## 17. Production WebFlux deployment checklist

- [ ] The application genuinely uses Spring WebFlux and `SecurityWebFilterChain`, without accidentally mixing Servlet security config.
- [ ] Code inside `Mono`/`Flux` uses `ReactiveSecurityContextHolder.getContext()` when current principal/authorities are needed.
- [ ] No reliance on ThreadLocal `SecurityContextHolder` or `Thread.currentThread()` to identify users.
- [ ] Team understands Reactor Context flows from subscriber upstream; `contextWrite` is scoped properly with no unintended auth overrides.
- [ ] Authentication comes from verified filters/providers/managers, never trusting request-supplied usernames/roles.
- [ ] Avoid internal `block()` or `.subscribe()` inside WebFlux handlers/services.
- [ ] No shared singleton/global mutable `SecurityContext` across users.
- [ ] Clear identity-passing policies at `CompletableFuture`, executor, callback, WebClient, queue, and long-lived Flux boundaries.
- [ ] If using WebSession, configure appropriate `ServerSecurityContextRepository`, timeouts, cookies, logout, and session fixation protection.
- [ ] If using stateless bearer tokens, validate tokens on every request; do not confuse Reactor Context with durable token storage.
- [ ] All `Mono<Void>` save/side-effect operations are composed into the returned publisher; no fire-and-forget.
- [ ] Reactive method security is enabled properly and secured methods are called through Spring proxies.
- [ ] Authorization verifies roles/permissions alongside owner/tenant/resource-level policies.
- [ ] Revoked permissions/locked accounts have defined SLAs and invalidation/re-evaluation strategies.
- [ ] Logs/metrics/traces exclude raw passwords, OTPs, bearer tokens, and full security contexts.
- [ ] Tests cover one publisher with multiple contexts, absent context, `clearContext`, `publishOn`, and real HTTP flows.
- [ ] Tests verify `/public`, `/me`, `/admin` through the security filter chain, not only `@WithMockUser`.
- [ ] No caching or hot-sharing of one user's private data to other subscribers without access checks.
- [ ] Context-loss monitoring exists without logging sensitive data while debugging.
- [ ] Spring Security, Reactor, Spring Boot, and test dependencies stay updated per BOM/patches.

### Summary

**`SecurityContextHolder` primarily handles thread-bound context in imperative/Servlet code; `ReactiveSecurityContextHolder` handles subscription-bound context in Spring WebFlux/Reactor.** `getContext()` returns `Mono<SecurityContext>`, while `withAuthentication`, `withSecurityContext`, and `clearContext` work with `contextWrite` to scope context.

In WebFlux, security filters supply Reactor Context per request, while `ServerSecurityContextRepository` decides whether context persists across requests. Preserving the right identity after `publishOn` never excuses skipping password/JWT verification, owner/tenant authorization, or session/token lifecycles.

A guiding design principle: **never ask "who does this thread belong to?"; ask "which security context does this verified subscription/request carry, and what permissions does that principal have on the target resource?"**

### Official references

- [Spring Security — ReactiveSecurityContextHolder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html)
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring Security — Authorize ServerHttpRequest](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html)
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security — Reactive Authentication](https://docs.spring.io/spring-security/reference/reactive/authentication/index.html)
- [Spring Security — ReactorContextWebFilter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/ReactorContextWebFilter.html)
- [Spring Security — ServerSecurityContextRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/ServerSecurityContextRepository.html)
- [Spring Security — WebSessionServerSecurityContextRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/WebSessionServerSecurityContextRepository.html)
- [Spring Security — AuthenticationWebFilter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html)
- [Project Reactor — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
- [Project Reactor — Context Propagation Support](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html)
- [Spring Boot — Build Systems](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
