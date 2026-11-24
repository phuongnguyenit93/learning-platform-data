# Roles of ReactorContextWebFilter and SecurityContextServerWebExchangeWebFilter

## 1. Why Are Two SecurityContext-Related WebFilters Needed?

In Spring Security Reactive, a Spring WebFlux HTTP request passes through multiple `WebFilter` instances before reaching a handler. The framework cannot assume every processing stage runs on a single thread. Therefore, the request's security information is propagated through the **Reactor Context** in the executing subscription, rather than relying on `ThreadLocal` as in many Spring MVC/Servlet examples.

The two filters have easily confused names, yet they perform **two distinct responsibilities**:

1. **`ReactorContextWebFilter`** retrieves `SecurityContext` from a `ServerSecurityContextRepository` and makes it available to `ReactiveSecurityContextHolder` in the Reactor Context of the request-processing chain.
2. **`SecurityContextServerWebExchangeWebFilter`** decorates `ServerWebExchange` so that calling `exchange.getPrincipal()` looks up the principal from `ReactiveSecurityContextHolder`.

In other words, one filter bridges **repository → Reactor Context**, while the other bridges **Reactor Context → `ServerWebExchange.getPrincipal()` API**.

These are not two standalone login filters. They do not verify passwords themselves, do not validate JWTs themselves, do not decide access permissions themselves, and do not replace `AuthenticationWebFilter` or authorization components.

After this lesson, you will be able to:
- Identify the inputs, outputs, and responsibilities of each filter.
- Distinguish `SecurityContext`, `Authentication`, `Principal`, `ServerSecurityContextRepository`, Reactor Context, and `ServerWebExchange`.
- Describe scenarios where context comes from a saved login session or from fresh authentication in the current request.
- Use both `ReactiveSecurityContextHolder.getContext()` and `ServerWebExchange.getPrincipal()` in a real runnable WebFlux API.
- Diagnose context-loss bugs, stateless/session confusion, manual `subscribe()`, blocking calls, and filter-order mistakes.

## 2. Participating Objects: Do Not Conflate Them

| Component | Nature | Role |
| --- | --- | --- |
| `Authentication` | Spring Security interface that also acts as a `Principal` | Holds the caller's identity, authentication status, and authorities |
| `SecurityContext` | Container holding an `Authentication` | Provides security information for a processing chain |
| `ReactiveSecurityContextHolder` | API for accessing `SecurityContext` from Reactor Context | `getContext()` returns `Mono<SecurityContext>` |
| Reactor `Context` | Context attached to a Reactor subscription | Propagates data along a reactive chain even across thread switches |
| `ServerWebExchange` | WebFlux abstraction for an HTTP request/response | Provides request, response, attributes, `getPrincipal()`, etc. |
| `ServerSecurityContextRepository` | Strategy with `load(exchange)` / `save(exchange, context)` | Saves and/or loads context depending on session/stateless mechanism |
| `ReactorContextWebFilter` | WebFilter in the security chain | Initializes context access from the repository in Reactor |
| `SecurityContextServerWebExchangeWebFilter` | WebFilter in the security chain | Makes `exchange.getPrincipal()` read the principal from the reactive security context |

**`SecurityContext` differs from `Authentication`:** `SecurityContext` is the wrapper; `context.getAuthentication()` retrieves the object carrying identity and authorities. Not every `Authentication` proves a user actually logged in: the system can also use anonymous authentication and unauthenticated authentication tokens depending on the flow. Granting access must rely on the authorization layer, not merely on a non-null object.

**`ServerWebExchange` differs from Reactor Context:** `ServerWebExchange` describes the HTTP interaction of the request. Reactor Context is contextual data of the subscription. Spring Security connects these two worlds with filters and holder APIs; they are not automatically a single object.

## 3. Exact Role of `ReactorContextWebFilter`

Spring Security's API describes `ReactorContextWebFilter` as a `WebFilter` that uses a `ServerSecurityContextRepository` to provide the `SecurityContext` for initializing `ReactiveSecurityContextHolder`.

Conceptual steps:

1. The filter receives `ServerWebExchange` and `WebFilterChain`.
2. It holds a configured `ServerSecurityContextRepository`.
3. The repository can load a `Mono<SecurityContext>` corresponding to the exchange.
4. The filter makes that context publisher accessible in the Reactor Context of the downstream chain through `ReactiveSecurityContextHolder`'s mechanism.
5. Downstream components can call `ReactiveSecurityContextHolder.getContext()` to read the context when the subscription actually runs.

Diagram:

~~~text
HTTP request
    |
    v
ServerWebExchange
    |
    v
ReactorContextWebFilter
    |
    |  ServerSecurityContextRepository.load(exchange)
    |                 |
    |          Mono<SecurityContext>
    |                 |
    +--> Subscription's Reactor Context
                   |
                   v
         ReactiveSecurityContextHolder.getContext()
                   |
                   v
          Authentication / principal
~~~

**This is a context loading/provisioning mechanism, not credential authentication.** If the repository returns `Mono.empty()`, you cannot conclude the filter "rejected" the request; another authentication filter may still inspect the current request's credentials and create a new authentication.

### 3.1. What Does Repository Mean?

`ServerSecurityContextRepository` has two core methods:

~~~java
Mono<Void> save(ServerWebExchange exchange, SecurityContext context);
Mono<SecurityContext> load(ServerWebExchange exchange);
~~~

These are **illustrative API signatures**, not a standalone Java program. `load` returns `Mono.empty()` when no context is found; it does not return `null`.

Two important implementations:
- `WebSessionServerSecurityContextRepository`: stores `SecurityContext` in `WebSession`; suitable for session-based mechanisms when authentication is properly saved.
- `NoOpServerSecurityContextRepository`: neither saves context nor reloads saved context. Suitable when cross-request persistence is unnecessary, such as many stateless Bearer token configurations.

Note: **a repository used for loading context does not automatically guarantee new authentications are saved.** Whether a successful authentication is persisted also depends on the authentication mechanism and the repository used by the authentication filter. Never assume every login is written to the session merely because you see a `WebSessionServerSecurityContextRepository` bean.

### 3.2. Where Does `ReactiveSecurityContextHolder` Read From?

The call:

~~~java
Mono<SecurityContext> contextMono =
        ReactiveSecurityContextHolder.getContext();
~~~

does not query a database directly, does not read a thread-local global variable, and does not make an HTTP call. It reads the security context from the **Reactor Context attached to the subscription**; that context may have been populated from the repository by `ReactorContextWebFilter` or added into the request pipeline by an authentication component.

To process the identity:

~~~java
Mono<String> username = ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication().getName());
~~~

The snippet above is a syntax example and requires the corresponding imports inside a class. The `Mono` can be empty if no `SecurityContext` exists in the context being read. For endpoints requiring authentication, let the security chain reject unauthenticated callers before reaching the handler.

### 3.3. Reactor Context Is Not `ThreadLocal`

A pipeline can switch schedulers while still carrying Reactor Context because the context travels with the subscription:

~~~java
return ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName())
        .publishOn(Schedulers.parallel())
        .map(name -> "Hello " + name);
~~~

Import `reactor.core.scheduler.Schedulers` if using this illustrative snippet. `publishOn` within the same chain **does not by itself lose Reactor Context**. Conversely, calling `subscribe()` elsewhere creates a new subscription; spawning a raw `Thread` or `CompletableFuture.runAsync` likewise does not automatically carry the HTTP request's context.

## 4. Exact Role of `SecurityContextServerWebExchangeWebFilter`

The official API describes the second filter: it overrides how `ServerWebExchange.getPrincipal()` works so the principal is looked up via `ReactiveSecurityContextHolder`.

In WebFlux, downstream code can ask:

~~~java
Mono<? extends Principal> principal = exchange.getPrincipal();
~~~

Thanks to `SecurityContextServerWebExchangeWebFilter`, the exchange passed down to the handler goes through a wrapper capable of resolving `getPrincipal()` from the reactive security context. The related component is **`SecurityContextServerWebExchange`**, a `ServerWebExchangeDecorator`.

Diagram:

~~~text
Reactor Context holding Mono<SecurityContext>
                         |
                         v
             ReactiveSecurityContextHolder
                         |
                         v
SecurityContextServerWebExchangeWebFilter
                         |
                         v
           SecurityContextServerWebExchange
                         |
                         v
             exchange.getPrincipal()
                         |
                         v
                  Mono<Principal>
~~~

Key points:
- This filter does **not** call the repository itself to load context; that is the job of the preceding filter/context.
- This filter does **not** authenticate username/password/JWT.
- This filter does **not** grant or modify roles/authorities.
- It provides a consistent way to read the principal for code using the standard `ServerWebExchange.getPrincipal()` API.
- Exchange decoration is for **downstream** components. A WebFilter running earlier, holding the original exchange instance, should not assume it already received the wrapper created by a later filter.

### 4.1. Why Is `getPrincipal()` Needed When the Holder Exists?

Many WebFlux components are designed to work with the generic HTTP `ServerWebExchange` interface, `Principal`, or handler arguments such as `Principal`/`Mono<Principal>`. They do not necessarily depend directly on Spring Security's internal APIs.

When `getPrincipal()` pulls from the holder, handlers see the identity authenticated by the security chain without querying sessions, parsing tokens, or referencing `ThreadLocal`. Meanwhile, components that need authorities, credential type details, or the full `Authentication` can still access `ReactiveSecurityContextHolder`.

### 4.2. Do Not Confuse the Direction of the Bridge

`ReactorContextWebFilter` makes the security context from the repository accessible inside Reactor Context.

`SecurityContextServerWebExchangeWebFilter` makes `exchange.getPrincipal()` able to access the principal **from** Reactor Context.

Therefore, do not assume overriding `ServerWebExchange.getPrincipal()` yourself is enough to alter `ReactiveSecurityContextHolder`, or that putting an arbitrary attribute on the exchange automatically becomes trusted authentication.

## 5. Where Do the Two Filters Sit in SecurityWebFilterChain?

A Spring Security WebFlux configuration typically builds a `SecurityWebFilterChain` bean using `ServerHttpSecurity`. When a request matches the matcher, security filters are ordered according to the positions described by `SecurityWebFiltersOrder`. The two official named positions are:

- `SecurityWebFiltersOrder.REACTOR_CONTEXT`: for `ReactorContextWebFilter`.
- `SecurityWebFiltersOrder.SECURITY_CONTEXT_SERVER_WEB_EXCHANGE`: for `SecurityContextServerWebExchangeWebFilter`.

In the default chain of the Spring Security 6.x line, the Reactor Context step is positioned before common HTTP authentication positions; the exchange-decorating step is placed after those authentication positions and before many downstream steps such as authorization. Actual configurations may include or omit other filters depending on HTTP Basic, form login, OAuth2/JWT, CSRF, CORS, anonymous authentication, and chain matchers.

Overall picture:

~~~text
Request
  |
  v
WebFilterChainProxy / matching SecurityWebFilterChain
  |
  +--> ReactorContextWebFilter
  |     loads SecurityContext from repository into Reactor Context
  |
  +--> Matching authentication filter(s)
  |     verifies credential/token when request carries authentication info
  |     places created Authentication into request's security context
  |
  +--> SecurityContextServerWebExchangeWebFilter
  |     enables getPrincipal() to read from ReactiveSecurityContextHolder
  |
  +--> Authorization / other protective filters
  |     checks permissions or enforces relevant policies
  |
  v
WebFlux handler / controller / reactive service
~~~

**Conceptual diagram:** it does not attempt to reproduce every filter, detailed order, or branch across all Spring Security versions. Filters like CORS, CSRF, login, logout, exception translation, and anonymous authentication have their own positions and activation rules. When configuring custom filters, use `SecurityWebFiltersOrder` rather than relying on intuition about appearance order in a Java file.

Note the differences from Servlet:
- Reactive: `ServerHttpSecurity`, `SecurityWebFilterChain`, `WebFilter`, `ReactiveSecurityContextHolder`, `ServerSecurityContextRepository`.
- Servlet: `HttpSecurity`, `SecurityFilterChain`, Servlet `Filter`, and the corresponding `SecurityContextHolder`/repository mechanisms.

Do not use Servlet APIs merely because the filter names look similar.

## 6. Two Concrete Flows: Session and Bearer Token

### 6.1. Flow with Saved Session/Context

Suppose an application uses `WebSessionServerSecurityContextRepository` and a previous login mechanism **successfully saved** the `SecurityContext` into the session:

1. The browser sends the session cookie.
2. `ReactorContextWebFilter` can load the context associated with `ServerWebExchange` from the repository.
3. Downstream `ReactiveSecurityContextHolder.getContext()` reads the saved authentication.
4. `SecurityContextServerWebExchangeWebFilter` makes `exchange.getPrincipal()` return the corresponding principal.
5. Authorization checks permissions, then the handler is invoked if permitted.

The "successfully saved" condition matters. Merely having a cookie or a `WebSession` does not imply an authenticated `SecurityContext` exists.

### 6.2. Stateless Flow with JWT

Suppose an API uses OAuth2 Resource Server, the client sends a Bearer token on **every request**, and authentication does not need to be saved in a session:

1. The repository may be no-op, so `ReactorContextWebFilter` loads no context from a prior request.
2. The appropriate authentication filter verifies the Bearer token (signature, expiration, issuer/audience per configuration) and builds an `Authentication` for the current request.
3. Spring Security places the current authentication into the pipeline's reactive security context.
4. The exchange-decorating filter lets `getPrincipal()` reflect the request's authentication.
5. Authorization checks mapped scopes/roles/authorities, while data ownership must still be enforced in business logic.

There is **no contradiction** when a no-op repository is used yet the handler still reads a principal. The repository controls loading/saving **across requests**, whereas the security context for the **current request** can be constructed from the credentials/token just verified.

Crucially, never describe `ReactorContextWebFilter` as "the JWT decoding filter" or `SecurityContextServerWebExchangeWebFilter` as "the login filter". Authentication belongs to a different stage in the chain.

## 7. Runnable WebFlux Example: Reading the Same Identity Two Ways

This example uses Java 17, Spring Boot 3.3.13, and Gradle. It is a learning sample to observe the principal name; accounts/passwords and HTTP Basic are minimally configured for local environments.

Structure:

~~~text
reactive-context-filter-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/
    ├── DemoApplication.java
    ├── SecurityConfig.java
    └── WhoAmIController.java
~~~

**`settings.gradle`**

~~~groovy
rootProject.name = 'reactive-context-filter-demo'
~~~

**`build.gradle`**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
~~~

**`src/main/java/demo/DemoApplication.java`**

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

**`src/main/java/demo/SecurityConfig.java`**

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public").permitAll()
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails learner = User.withUsername("learner")
                .password("{noop}localpass")
                .roles("USER")
                .build();

        return new MapReactiveUserDetailsService(learner);
    }
}
~~~

**`src/main/java/demo/WhoAmIController.java`**

~~~java
package demo;

import java.security.Principal;
import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
public class WhoAmIController {

    @GetMapping("/public")
    public Mono<String> publicEndpoint() {
        return Mono.just("public");
    }

    @GetMapping("/whoami")
    public Mono<Map<String, String>> whoAmI(ServerWebExchange exchange) {
        Mono<String> fromContext = ReactiveSecurityContextHolder
                .getContext()
                .map(context -> context.getAuthentication())
                .map(Authentication::getName);

        Mono<String> fromExchange = exchange
                .<Principal>getPrincipal()
                .map(Principal::getName);

        return Mono.zip(fromContext, fromExchange)
                .map(names -> Map.of(
                        "reactorContext", names.getT1(),
                        "exchangePrincipal", names.getT2()));
    }
}
~~~

Explanation:
- `fromContext` uses the reactive security API, suited when you also need `Authentication`, authorities, etc.
- `fromExchange` only retrieves `Principal` via the WebFlux API. The exchange-decorating filter is the bridge enabling this API to use the same security context.
- `Mono.zip` waits for both publishers to emit a value. Because `/whoami` requires valid authentication, the example expects both to carry the name `learner`. If either `Mono` is empty, `zip` can complete empty; that is Reactor behavior, not a JSON serializer bug.
- The controller does not call `block()` or `subscribe()` itself; WebFlux is what subscribes to the returned publisher.
- This configuration **does not implement** the two filters manually, because Spring Security already attaches them to the security chain when appropriate. Do not create duplicate filters to "turn on" the feature.

### Running the Demo

From the directory containing `build.gradle`, run:

~~~bash
gradle bootRun
~~~

If the project has a Gradle Wrapper, use `./gradlew bootRun`. When the server is running on default port 8080, open another terminal:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/whoami
curl -i -u learner:localpass http://localhost:8080/whoami
curl -i -u learner:wrong http://localhost:8080/whoami
~~~

Expected results:

| Request | HTTP Status | Meaningful Result |
| --- | --- | --- |
| `GET /public`, no credentials | **200 OK** | Body `public` |
| `GET /whoami`, no credentials | **401 Unauthorized** | Route requires login; HTTP Basic may return `WWW-Authenticate` header |
| `GET /whoami`, valid `learner:localpass` | **200 OK** | JSON has `reactorContext = learner` and `exchangePrincipal = learner` |
| `GET /whoami`, wrong password | **401 Unauthorized** | No valid authenticated principal produced |

A successful JSON response represents the values:

~~~json
{
  "reactorContext": "learner",
  "exchangePrincipal": "learner"
}
~~~

**JSON key ordering is not guaranteed**, because the example uses `Map.of`. Error bodies, messages, and headers may also vary by Spring Security version/configuration.

**Safety note:** `{noop}` means unhashed passwords, solely for local demos. Never use hardcoded usernames/passwords or HTTP Basic over unencrypted connections in production; protect credentials with HTTPS and use a strong password encoder/appropriate secrets vault. Spring Boot 3.3.13 here is an illustrative version for running the lesson; real projects must use a supported branch with security updates.

### Experiment to Understand "Repository Is Not Authentication"

In the demo, each `curl -u` command sends HTTP Basic credentials directly on the request. Even if cross-request persistence is changed, a request carrying valid credentials can still be authenticated by `AuthenticationWebFilter` and have its principal placed into the pipeline. Do not use the `/whoami` result with HTTP Basic to conclude for sure that the user was saved into the session.

To prove session persistence, you need a separate example with a login flow that actually **saves** the context to `WebSessionServerSecurityContextRepository` and a subsequent request that reuses the session without sending credentials. That is a different test case from the current HTTP Basic example.

## 8. Self-Check with a Controlled Test

The example below illustrates how to **manually inject** an Authentication into Reactor Context outside an HTTP request to observe `ReactiveSecurityContextHolder`. It does not create a `ServerWebExchange`, so it does not directly test the exchange-decorating filter.

~~~java
// Illustrative snippet in code that already has Spring Security + Reactor dependencies.
Authentication auth = new UsernamePasswordAuthenticationToken(
        "test-user", "N/A",
        AuthorityUtils.createAuthorityList("ROLE_USER"));

Mono<String> name = ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication().getName())
        .contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth));
~~~

If you subscribe to `name` in a test with `StepVerifier` or call `block()` **outside** the event loop at a console boundary, the result is `test-user`. You must import `Authentication`, `UsernamePasswordAuthenticationToken`, `AuthorityUtils`, and `Mono` when placing the code inside a class.

This example proves the holder reads from Reactor Context; **it does not prove** `ReactorContextWebFilter` loaded context from a repository. Both filters operate fully only when a `SecurityWebFilterChain` has a running request/exchange.

## 9. Common Mistakes When Reading Context and Principal

### Mistake 1 — Thinking `ReactorContextWebFilter` Authenticates Tokens Itself

**Wrong:** "Having ReactorContextWebFilter means JWTs are validated automatically."

**Right:** It makes the security context supplied by the repository present in the reactive pipeline. Resource Server authentication must use OAuth2/JWT configuration and dedicated token verification. Once the JWT is valid, the authentication filter places the result into the request context; `SecurityContextServerWebExchangeWebFilter` then reflects that principal through the exchange.

### Mistake 2 — Thinking the Exchange-Decorating Filter Saves Sessions

**Wrong:** "`SecurityContextServerWebExchangeWebFilter` writes the principal into WebSession."

**Right:** Its documented role is overriding `ServerWebExchange.getPrincipal()` with a lookup from `ReactiveSecurityContextHolder`. Persistence belongs to `ServerSecurityContextRepository` and the authentication flow's save mechanism.

### Mistake 3 — Context Missing After Calling `subscribe()` Manually

~~~java
// WRONG: detaches the subscription from the HTTP request's publisher.
auditService.writeEvent(event).subscribe();
return Mono.just("ok");
~~~

A separately subscribed publisher is not guaranteed to have the Reactor Context attached to the request. Audit errors may also occur after sending the response, bypassing the request's error flow.

When auditing is a condition for completing the request, compose it into the same chain:

~~~java
return auditService.writeEvent(event)
        .thenReturn("ok");
~~~

If auditing truly needs to outlive the HTTP response, use a job/queue/outbox with its own lifecycle and pass the authenticated actor ID as explicit data.

### Mistake 4 — Calling `block()` to Fetch SecurityContext

~~~java
// WRONG inside a reactive handler/service.
Authentication auth = ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication())
        .block();
~~~

`block()` creates a new subscription and blocks the thread; on the event loop it can raise blocking errors, and the request's context is not guaranteed to propagate into a new subscription.

Better:

~~~java
return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication())
        .flatMap(auth -> orderService.findOrdersFor(auth.getName()));
~~~

The snippet above is illustrative integration code; it requires the corresponding service and imports to run.

### Mistake 5 — Reading Servlet-Style ThreadLocal `SecurityContextHolder`

A WebFlux request can switch threads as it passes through Reactor operators. Therefore, do not treat `ThreadLocal`-based `SecurityContextHolder.getContext()` as the request's default identity source. Use `ReactiveSecurityContextHolder`, or `exchange.getPrincipal()` in a handler receiving a filter-processed exchange.

### Mistake 6 — Calling `exchange.getPrincipal()` Too Early in a Custom WebFilter

A custom filter running **before** `SecurityContextServerWebExchangeWebFilter` can receive an undecorated exchange. If you need the principal created by Spring Security, choose a compatible position in the chain; do not manually alter internal filter orders or assume the wrapper exists from the very start of the request.

### Mistake 7 — Missing Principal Yet Only Checking Whether a Repository Bean Exists

Verify in order:
1. Did the request go through the right `SecurityWebFilterChain` and security matcher?
2. Is there a matching authentication mechanism for Basic/Bearer/session and valid credentials?
3. Is `ServerSecurityContextRepository.load(exchange)` expected to find a saved context?
4. If stateless, was the fresh authentication placed into the **current request's** Reactor Context?
5. Is downstream code inside the same reactive chain, or did it detach a subscription?
6. For `getPrincipal()`, has the exchange passed through the decorating filter yet?
7. Is the route permitted to anonymous callers, and does authentication exist as expected?

Never log the full `SecurityContext`, passwords, `Authorization` headers, or JWTs for debugging. Log only necessary non-sensitive info and an appropriate correlation ID.

## 10. Testing Each Layer's Responsibilities Properly

Do not test only that the controller returns 200. A minimal matrix:

| Scenario | What to Verify |
| --- | --- |
| Public request, not logged in | Public route works, but do not assume `getPrincipal()` is empty if anonymous authentication is enabled |
| Protected request, no credentials | Denied by the appropriate entry point, e.g., Basic is typically 401 |
| Protected request, valid credentials | `ReactiveSecurityContextHolder` and `exchange.getPrincipal()` reflect the same caller name |
| Wrong credentials | No valid authentication and protected route is denied |
| Valid authentication but lacking authority | Authorization denies (typically 403), even though principal is present |
| Stateful login saving session | Subsequent request using session reloads security context |
| Stateless Bearer token | Each request must supply the token itself; `NoOpServerSecurityContextRepository` does not persist login across requests |
| Custom operator switching schedulers within the same chain | Reactor Context remains accessible when no independent subscription is created |
| Task calling `subscribe()` outside the chain | Detect and avoid relying on request context or request cancellation |

When using `WebTestClient` and Spring Security Test utilities, verify both URL-level and method-level permissions, and also enforce data ownership in services if the application has multi-user resources. `getPrincipal()` returning the right name **does not by itself prove** the caller has rights to every resource.

A practical observation check: on the `/whoami` endpoint, compare the two JSON fields after calling with the same account. If they mismatch or the publisher is empty despite an authenticated request, review pipeline composition, custom filters, principal mapping, and security chain matchers before blaming Reactor thread switching.

## 11. Self-Check Questions

**Question 1.** Which filter uses `ServerSecurityContextRepository` to make `SecurityContext` available in Reactor Context?

> `ReactorContextWebFilter`.

**Question 2.** Which filter enables `ServerWebExchange.getPrincipal()` to read the identity from `ReactiveSecurityContextHolder`?

> `SecurityContextServerWebExchangeWebFilter`, via the decorated exchange.

**Question 3.** When using `NoOpServerSecurityContextRepository`, can a request with a valid Bearer token have a principal?

> Yes. Authentication for the current request can be created by the authentication filter and attached to Reactor Context; the no-op repository merely provides no persistence across requests.

**Question 4.** After logging in with WebSession, why might the next request still lack context even though the repository is configured?

> You need to check whether the authentication flow actually saved the `SecurityContext` to the repository, whether the session cookie was sent back, and whether the request went through the right security chain.

**Question 5.** Do `exchange.getPrincipal()` and `ReactiveSecurityContextHolder.getContext()` have the same return type?

> No. `getPrincipal()` returns a `Mono` of `Principal`; the holder returns `Mono<SecurityContext>`, from which `Authentication` can be read.

**Question 6.** Why should you not read the security context using `block()` in a WebFlux controller?

> Because it blocks the thread and creates a new subscription, which can break the connection to the request's Reactor Context.

**Question 7.** Do these two filters replace `AuthenticationWebFilter` or `AuthorizationWebFilter`?

> No. They bridge context/principal representations and access; credential verification and permission decisions are still executed by other components.

## 12. Summary

In Spring Security Reactive's WebFilter architecture, **`ReactorContextWebFilter` ensures context can be loaded from a repository into the Reactor flow**, while **`SecurityContextServerWebExchangeWebFilter` makes the `ServerWebExchange.getPrincipal()` API reflect that flow's security context**. The two filters support authentication and authorization components, but do not directly replace them.

Key points to remember in practice:
- Clearly distinguish **cross-request persistence** from **the current request's security context**.
- Read identity inside the pipeline using `ReactiveSecurityContextHolder` or `exchange.getPrincipal()` at the proper position in the security chain.
- Keep work requiring authorization inside the same reactive chain; do not manually `subscribe()` or `block()` in WebFlux handlers.
- Separately verify authentication, authorization, context propagation, and session/stateless behavior when diagnosing issues.

### Official Documentation

- Spring Security Javadoc — `ReactorContextWebFilter`: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/context/ReactorContextWebFilter.html
- Spring Security Javadoc — `SecurityContextServerWebExchangeWebFilter`: https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/web/server/context/SecurityContextServerWebExchangeWebFilter.html
- Spring Security Javadoc — `ServerSecurityContextRepository`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/context/ServerSecurityContextRepository.html
- Spring Security Javadoc — `SecurityWebFiltersOrder`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/SecurityWebFiltersOrder.html
- Spring Security Reference — Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Reactor Reference — Context: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html