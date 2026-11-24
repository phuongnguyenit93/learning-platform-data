# Request Flow Through WebFilter, WebFilterChainProxy, and SecurityWebFilterChain

## Objectives and Context

This lesson is part of the **WebFilter Architecture** section of **Spring Security - reactive**. After completing it, you should be able to explain:

1. How an HTTP request enters the global `WebFilter` chain from Spring WebFlux.
2. Why `WebFilterChainProxy` is a `WebFilter` while `SecurityWebFilterChain` is not that `WebFilter` itself.
3. How Spring Security selects **one** `SecurityWebFilterChain` based on `securityMatcher` and priority order.
4. How authentication and authorization filters run before the handler, and when the pipeline stops early.
5. How to configure, observe, and test the request flow with **multiple security chains** without leaving URLs exposed.

This is the **Spring WebFlux** architecture using Reactor (`Mono`/`Flux`). The classes `jakarta.servlet.Filter`, `FilterChainProxy`, and `SecurityFilterChain` in Servlet share similar concepts, but **must not be used in place of** WebFlux's `WebFilter`, `WebFilterChainProxy`, and `SecurityWebFilterChain`.

## 1. Distinguishing the Four Core Components

| Component | Layer | Primary Contract | Responsibility |
| --- | --- | --- | --- |
| `WebFilter` | Spring WebFlux | `Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain)` | Intercepts before/after HTTP processing; can continue the chain, return a response, or emit an error |
| `WebFilterChain` | Spring WebFlux | `Mono<Void> filter(ServerWebExchange exchange)` | Represents **the rest** of the filter chain and ultimately the `WebHandler` |
| `WebFilterChainProxy` | Spring Security reactive | Itself **implements `WebFilter`** | Receives the exchange, applies the firewall, finds the matching security chain, and lets the security filters join the pipeline |
| `SecurityWebFilterChain` | Spring Security reactive | `Mono<Boolean> matches(ServerWebExchange)` and `Flux<WebFilter> getWebFilters()` | Describes the **condition for selecting the chain** along with its corresponding **list of security WebFilters** |

Meanings that are often conflated:

- `WebFilterChain` is a **continuation path**; it is passed through each `filter(...)` invocation.
- `SecurityWebFilterChain` is a **configuration selected for a request**, consisting of a matcher and a list of filters; it does **not** itself have a `filter(exchange, chain)` method like a `WebFilter`.
- `WebFilterChainProxy` is the **bridge** between the two worlds: a single filter in the global WebFlux chain and multiple sets of security filters selected conditionally.
- `ServerHttpSecurity` is a DSL used to configure and `build()` a `SecurityWebFilterChain`; it does not represent an in-flight request.

For example, one `SecurityWebFilterChain` can protect `/api/**` with HTTP Basic, while another chain protects the remaining paths with a different mechanism. The proxy inspects each request and chooses the appropriate chain; having two beans does not mean both sets of filters run sequentially.

## 2. Request Flow Diagram

```text
Client sends HTTP request
    |
    v
HTTP server/reactive adapter (e.g., Reactor Netty)
    |
    v
HttpWebHandlerAdapter / Spring WebFlux WebHandler pipeline
    |
    v
FilteringWebHandler
    |
    +--> Global WebFilter A (if registered)
    |       |
    |       +--> WebFilterChainProxy  <-- also a WebFilter
    |                  |
    |                  +--> ServerWebExchangeFirewall inspects exchange
    |                  |
    |                  +--> iterates SecurityWebFilterChains by priority
    |                          |
    |                          +--> matches(exchange): Mono<Boolean>
    |                          +--> selects the FIRST matching CHAIN
    |                                  |
    |                                  v
    |                             list of WebFilters in that chain
    |                             (context, authentication, authorization,
    |                              exception handling, headers... depending on configuration)
    |                                  |
    |                                  v
    |                             Original WebFilterChain continues
    |       |                          |
    |       +--------------------------+
    |       |
    +--> Global WebFilter B (if any remain in chain)
    |
    v
WebHandler / DispatcherHandler / RouterFunction handler
    |
    v
Result is written to ServerHttpResponse
    |
    v
Reactive pipeline completes or terminates due to error/cancellation
```

This diagram is **conceptual**; the exact positions of A, B, and the security filters depend on registration order and configuration. The **global WebFilters** include the security proxy itself, whereas the **inner security WebFilters** are only spliced in once the proxy selects a `SecurityWebFilterChain`.

The response path is not a filter chain running "in reverse" automatically like synchronous function calls. Operators such as `doOnSuccess`, `doOnError`, `doFinally`, or `then` attached by a filter to the `Mono<Void>` can execute when the downstream flow completes, errors, or is cancelled. Everything executes according to the reactive contract when the publisher is subscribed to.

## 3. Startup Phase and Request-Handling Phase

### 3.1. Application Startup

When Spring Security reactive is enabled, for instance via `@EnableWebFluxSecurity` or the appropriate auto-configuration, the application can create one or more `SecurityWebFilterChain` beans using `ServerHttpSecurity`:

```java
// Configuration snippet, not a standalone application.
@Bean
SecurityWebFilterChain defaultSecurity(ServerHttpSecurity http) {
    return http
            .authorizeExchange(exchanges -> exchanges
                    .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}
```

During wiring, Spring Security provides `WebFilterChainProxy` to use those security chains. WebFlux sees the proxy as a `WebFilter` in the global filter sequence. In Spring Boot WebFlux, `WebFilter` beans are detected and sorted by `Ordered`/`@Order`; by default, Spring Boot places the security `WebFilterChainProxy` at order **-100**. This number is the order **among global WebFilters** in that Boot configuration, not the order inside each security chain.

For each `SecurityWebFilterChain`, `ServerHttpSecurity.build()` assembles the security filters needed by the configuration (security context, authentication, CSRF, authorization, etc.). The actual list varies with `httpBasic`, `formLogin`, JWT, CSRF, headers, and framework version; **do not assume every application has the same filters or the same number of filters**.

### 3.2. When a Request Arrives

1. The HTTP server passes the request into WebFlux; the framework creates a `ServerWebExchange` containing the request, response, and exchange attributes.
2. The global `WebFilter` chain is invoked in order; each filter receives a `WebFilterChain` so it can proceed.
3. When it is `WebFilterChainProxy`'s turn, the proxy applies `ServerWebExchangeFirewall`. An invalid exchange can be rejected right before authentication/authorization.
4. The proxy iterates through the ordered `SecurityWebFilterChain` instances: calling `matches(exchange)` on each chain until the **first** chain returns `true`.
5. The proxy retrieves `getWebFilters()` of the selected chain and combines them with the original `WebFilterChain` to preserve the ability to continue to the remaining WebFilters and the handler.
6. The security filters in the chain execute logic according to the configuration; a filter may continue, challenge the user, deny access, or return an error.
7. When all steps allow it, the flow continues to `DispatcherHandler`/the functional handler to execute the endpoint and write the response.

Conceptually, chain selection can be pictured as `Flux.fromIterable(chains).filterWhen(chain -> chain.matches(exchange)).next()`: `filterWhen` evaluates the reactive matcher; `next()` takes the **first matching element**. This is a conceptual description of the selection mechanism, **not an API for the application to call directly**.

If **no chain matches**, the proxy continues the original WebFlux chain **without inserting the security filters of any SecurityWebFilterChain**. This is an easy place to expose endpoints if an application only defines a chain with matcher `/api/**` and forgets to protect other URLs. Do not assume "no match" means "denied by default": you must define a chain covering the remaining requests or have another verified protection layer.

## 4. Two Ordering Layers and One Authorization Rule Layer

The following three mechanisms can coexist in one application, but they do not substitute for one another:

| Configuration Point | What does it order? | Example |
| --- | --- | --- |
| `@Order` on a global `WebFilter` bean | Filter position in the WebFlux pipeline (before/after the proxy) | An observability filter at order `-200` runs before Boot's default security proxy (`-100`) |
| `@Order` on a `SecurityWebFilterChain` bean | Order in which **chains are evaluated for a match first** | `@Order(1)` for `/api/**`; `@Order(2)` for the fallback chain |
| `SecurityWebFiltersOrder`, `addFilterBefore/After/At` | Position of a filter **inside** the selected security chain | Insert a custom security `WebFilter` before `AUTHORIZATION` |

Meanwhile, `authorizeExchange(exchanges -> exchanges.pathMatchers(...).permitAll() ...)` is an **in-chain rule**, and does not decide chain selection. Distinguish two questions:

- **Which chain handles the request?** Decided by each chain's `securityMatcher(...)` and `@Order`.
- **Is the request allowed within the selected chain?** Decided by `authorizeExchange(...)`, authentication, and the corresponding security filters.

For example, if both the `/api/**` chain and the default chain match `GET /api/hello`, only the higher-priority `/api/**` chain is used. A `permitAll()` or `denyAll()` rule placed in the default chain **does not stack** onto that request.

**Do not arbitrarily attach `@Order(-200)` to a `WebFilter` to let a request through without calling `chain.filter(exchange)`**. If it completes the response early, the security proxy may not have been invoked yet; any bypass cases must be designed and tested as part of the security architecture.

## 5. Runnable Example with Java 17+ and Two Security Chains

This minimal example uses Spring Boot 3.3.13, Java 17+, WebFlux, and compatible Spring Security managed by the BOM. The app has three GET endpoints:

- `GET /api/hello`: API chain, accessible only to logged-in users.
- `GET /public/ping`: fallback chain, publicly accessible.
- `GET /internal/secret`: fallback chain, denies everyone, including logged-in users.

Create `settings.gradle`:

```groovy
rootProject.name = 'webfilter-flow-demo'
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
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Create `src/main/java/example/WebFilterFlowApplication.java`:

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.WebFilter;
import reactor.core.publisher.Mono;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
@EnableWebFluxSecurity
@RestController
public class WebFilterFlowApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebFilterFlowApplication.class, args);
    }

    @GetMapping("/api/hello")
    public String apiHello() {
        return "api-ok";
    }

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/internal/secret")
    public String secret() {
        return "secret";
    }

    @Bean
    @Order(1)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(exchanges -> exchanges
                .anyExchange().authenticated())
            .httpBasic(withDefaults());
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
        http
            // No securityMatcher: applies to all remaining paths.
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public/**").permitAll()
                .anyExchange().denyAll())
            .httpBasic(withDefaults());
        return http.build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails alice = User.withUsername("alice")
            .password("{noop}demo")
            .roles("USER")
            .build();
        return new MapReactiveUserDetailsService(alice);
    }

    @Bean
    @Order(-200)
    WebFilter traceOutsideSecurity() {
        return (exchange, chain) -> Mono.defer(() -> {
            String path = exchange.getRequest().getPath().value();
            System.out.println("OUTER enter: " + path);
            return chain.filter(exchange)
                .doFinally(signal ->
                    System.out.println("OUTER finish: " + path + " / " + signal));
        });
    }
}
```

**Part-by-part explanation:**

- `apiChain` uses `securityMatcher("/api/**")` and `@Order(1)`; it is evaluated first. `authenticated()` is a rule **inside the API chain**.
- `fallbackChain` uses the default matcher that matches every request and `@Order(2)`; URLs that do not enter the API chain still have an explicit policy. `/public/**` is permitted, and all remaining paths are denied.
- `MapReactiveUserDetailsService` provides the user `alice` to test HTTP Basic. `{noop}` is suitable only for **local demos**; real applications need encoded passwords and proper secret management.
- `traceOutsideSecurity` is a **global WebFilter**: order `-200` makes it run before the default security proxy at order `-100` in Spring Boot WebFlux. `Mono.defer` ensures the print statement runs when the flow is subscribed to; `doFinally` runs when the pipeline completes, errors, or is cancelled. It must not be used as an authorization decision mechanism.
- Two security chains must not manually invoke one another with `chain.filter(...)` inside bean methods. The proxy automatically selects the chain and arranges the corresponding security filters.

Run with Gradle 8.5+ and JDK 17+:

```bash
gradle bootRun
```

If the project has a Gradle Wrapper, use `./gradlew bootRun` on Linux/macOS or `gradlew.bat bootRun` on Windows. Once the application is ready on port 8080, try:

```bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/hello
curl -i -u alice:demo http://localhost:8080/api/hello
curl -i -u alice:demo http://localhost:8080/internal/secret
```

Results to observe (status codes with the configuration above; exact headers/log formatting are not required to be identical across versions):

| Request | Selected Chain | Expected Result |
| --- | --- | --- |
| `GET /public/ping` without credentials | `fallbackChain` | `200`, body `pong` |
| `GET /api/hello` without credentials | `apiChain` | `401`, HTTP Basic challenge |
| `GET /api/hello` with `alice:demo` | `apiChain` | `200`, body `api-ok` |
| `GET /internal/secret` with `alice:demo` | `fallbackChain` | `403`; `secret()` handler is not invoked |

Do not infer that an unauthenticated request hitting `denyAll` will always return 403: when unauthenticated, the entry point may return 401 or redirect depending on configuration. The example above uses **valid credentials** for the 403 test case to clearly separate authorization from authentication.

Logs vary depending on when the request finishes, but look like:

```text
OUTER enter: /api/hello
OUTER finish: /api/hello / onComplete
```

The actual execution path still includes the security filters inside the proxy between those two points. The `onComplete` signal can also occur when a denied request **has been handled by the framework into a response**, because `Mono<Void>` completes after writing the response; the completion log itself **does not prove** the handler ran or that authorization succeeded.

## 6. Deep Dive into WebFilterChainProxy and Chain Selection

The following pseudocode illustrates responsibilities, **not source code to copy into an application**:

```java
// PSEUDOCODE: conceptual illustration; not an API implementation.
Mono<Void> filter(ServerWebExchange exchange, WebFilterChain original) {
    return firewall.check(exchange)
        .flatMap(safeExchange ->
            firstMatchingChain(safeExchange)
                .flatMap(chosen -> {
                    List<WebFilter> filters = chosen.getWebFilters();
                    WebFilterChain secured = decorate(original, filters);
                    return secured.filter(safeExchange);
                })
                .switchIfEmpty(Mono.defer(
                    () -> original.filter(safeExchange))));
}
```

Facts to distinguish:

**(1) Matchers return an asynchronous signal.** `SecurityWebFilterChain.matches(...)` has return type `Mono<Boolean>`, not a synchronous `boolean`. The framework evaluates chains in order until there is a match; do not call `block()` inside a WebFlux request to grab the result.

**(2) Only the first matching chain is used.** With the list `apiChain` then `fallbackChain`, a request to `/api/hello` satisfies both the `/api/**` matcher and the default matcher, but `fallbackChain`'s filters do not run because the proxy already selected `apiChain`. No default "OR" or "AND" combination is applied across different chains.

**(3) Matching does not mean allowing.** The matcher only determines which chain configuration a request belongs to; decisions such as `permitAll`, `authenticated`, `hasRole`, or `denyAll` are evaluated afterward by the corresponding security filters.

**(4) No match is a dangerous case.** The proxy can still forward the request down to the application without protection from security WebFilters. Therefore, it is common practice to define a default chain matching the rest and use `anyExchange().denyAll()` or an approved policy.

**(5) The firewall is not an authorization rule.** The firewall validates exchange conditions, such as suspicious paths, before or alongside other security steps. A rejection by the firewall does not have the same cause as a 401 unauthenticated or 403 insufficient permissions response.

**(6) SecurityWebFilterChain is not the global WebFilterChain.** `getWebFilters()` returns `Flux<WebFilter>`; the proxy combines the selected filters with the original `WebFilterChain`. The security filters inside the selected chain are still `WebFilter` objects, but they are managed according to the corresponding security configuration.

## 7. What Happens Inside Security Filters?

For a chain with authentication and authorization, a typical flow comprises the following responsibilities; the exact order and actual components are built by `ServerHttpSecurity`:

1. **Security context:** restores or propagates `SecurityContext` / `Authentication` through the Reactor Context and Spring Security components. Do not assume you can always read the user from `ThreadLocal` like in Servlet code.
2. **Authentication:** filters suited to HTTP Basic, bearer token, form login, or another mechanism extract credentials, convert them into an `Authentication`, and authenticate them; on failure, the configured handler/entry point can produce a 401 or a redirect.
3. **Security exception handling:** the corresponding filter handles security errors such as authentication or access denied according to the framework mechanism. It may decide on a challenge, a denied response, or propagate the error upstream.
4. **Authorization:** `AuthorizationWebFilter` applies `ReactiveAuthorizationManager` to the request; an insufficient-permission decision can prevent execution from reaching the handler.
5. **Continuation:** if not blocked, the security filters invoke the remaining `WebFilterChain`. WebFlux runs the route handler and writes the body.

Filter names you may encounter when reading source code or TRACE logs: `ReactorContextWebFilter`, `AuthenticationWebFilter`, `ExceptionTranslationWebFilter`, `AuthorizationWebFilter`, `HeaderWriterWebFilter`, `CsrfWebFilter`. They are not guaranteed to all appear in every configuration. There are cases where filters managing the security context or handling errors sit before or after one another according to framework-defined ordering, so **do not infer runtime order from the line order of DSL calls in `ServerHttpSecurity`**.

Separate three concepts:

- **Authentication:** who is making the access? Missing credentials or invalid credentials typically trigger the challenge flow.
- **Authorization:** does that identity have permission to enter the endpoint? A valid user can still receive a 403.
- **Request handling:** the controller/functional handler runs after security allows the pipeline to proceed. If the chain stops or terminates with an exception, the handler does not run.

Reading `ReactiveSecurityContextHolder.getContext()` must be done via the reactive API; the security context usually lives in the subscriber's Reactor Context, and `ThreadLocal`-based `SecurityContextHolder.getContext()` should not be treated as the source of truth for WebFlux flows.

## 8. Stopping the Chain Early, Mono Signals, and Responses

A `WebFilter` must return `Mono<Void>`. The standard way to proceed is:

```java
// Routing-independent snippet, assuming we are inside the WebFilter.filter method.
return chain.filter(exchange);
```

If you want to attach before/after logic:

```java
return Mono.defer(() -> {
    log.debug("before");
    return chain.filter(exchange)
        .doOnError(error -> log.warn("failed", error))
        .doFinally(signal -> log.debug("finished: {}", signal));
});
```

The snippet above illustrates only the method body; `log` is an application-provided logger. `doFinally` also runs on `CANCEL`, and print order across nested filters can be affected by reactive operators. Do not use `block()` or blocking I/O inside a `WebFilter` because it can tie up event-loop threads.

A filter can return `exchange.getResponse().setComplete()` **without** calling `chain.filter(exchange)` to deliberately terminate the response. This is valid behavior for designed cases (such as a special protocol check), but if a global filter runs before the proxy and skips calling the chain, that request **has not gone through Spring Security**. Directly returning `Mono.empty()` also does not automatically produce a security decision or an appropriate HTTP status code; you are responsible for setting the response properly.

**Distinguishing scenarios:**

| What happens | Do security/handler continue? |
| --- | --- |
| Global WebFilter calls `chain.filter(exchange)` | Reaches the next filter, potentially reaching the security proxy |
| Global WebFilter returns a response before calling the chain | Downstream filters (including the proxy if positioned after) and the handler do not run |
| Proxy finds no matching `SecurityWebFilterChain` | No security filters from any chain are applied; the original WebFlux chain continues |
| Authentication succeeds | May reach authorization; **not yet guaranteed to be allowed** |
| Authorization denies | Handler is blocked; framework handles AccessDenied/authentication response |
| Security allows and filters continue | Handler executes; response may complete, error, or be cancelled by the client |

Do not handle errors by unconditionally using `onErrorResume(error -> chain.filter(exchange))` outside the security proxy: it risks re-invoking the flow and bypassing the security denial/error step. Errors must be handled at the proper layer with a clear contract; do not attempt to re-run the rest of the chain simply because an exception was caught.

## 9. Observing Both Filter Layers Properly

To understand the path while debugging, observe both simultaneously:

**WebFlux layer:** global `WebFilter` beans, `@Order`, request path, and whether `chain.filter(exchange)` is called. With Spring Boot, `WebFilterChainProxy` is typically at order -100; a filter at -200 can observe before the proxy, while a filter at order 0 usually sits after the proxy. However, if security blocks the request early, a filter running **after the proxy** may not be invoked.

**Spring Security layer:** `SecurityWebFilterChain` beans, `@Order`, `securityMatcher`, the list of filters produced by `ServerHttpSecurity.build()`, and authentication/authorization results. Enable TRACE in a development environment when needed, for example in `application.yml`:

```yaml
logging:
  level:
    org.springframework.security: TRACE
```

TRACE can expose a lot of detail about requests and security flows; enable it only during controlled debugging and avoid keeping sensitive logs in production environments. With multiple chains, record the path, expected matching chain, and final response with explicit tests; do not conclude which chain was selected solely from a global WebFilter's log line.

**Inserting a filter at the right layer:** If you want to record every request, use a global `WebFilter` bean. If you want to inspect/add a step **inside** the selected security configuration, add a `WebFilter` via `ServerHttpSecurity.addFilterBefore(...)`, `addFilterAfter(...)`, or `addFilterAt(...)` with the appropriate `SecurityWebFiltersOrder` anchor. Configuration snippet example:

```java
// Code snippet inside a ServerHttpSecurity configuration method:
WebFilter traceBeforeAuthorization = (exchange, chain) -> {
    System.out.println("before security authorization");
    return chain.filter(exchange);
};
http.addFilterBefore(
    traceBeforeAuthorization,
    SecurityWebFiltersOrder.AUTHORIZATION
);
```

You need to import `org.springframework.security.config.web.server.SecurityWebFiltersOrder`. The added filter in this example participates only in **the security chain where you configure it**. Do not treat that position as an authorization policy; to enforce permission checks, use the corresponding security DSL/managers.

## 10. Meaningful Test Scenarios

To demonstrate understanding of the architecture, test the following cases rather than only testing successful endpoints:

| Scenario | Expected Chain | Evidence to Verify |
| --- | --- | --- |
| `/api/hello` without credentials | API | Challenge/401; handler does not return `api-ok` |
| `/api/hello` with valid credentials | API | 200; handler returns `api-ok` |
| `/public/ping` without credentials | Fallback | 200; handler returns `pong` |
| `/internal/secret` with valid credentials | Fallback | 403; handler does not return `secret` |
| `/api/**` chain placed after a default matcher matching all paths | Fallback may win | Test will expose the misordered configuration |
| Only `/api/**` chain declared, no fallback | No chain matches `/internal/secret` | Security proxy has no security filters for this path: protection must be added |
| Global WebFilter before proxy terminates early | Never enters proxy | No security check observed; must clearly explain why it stopped early |
| Matcher/filter emits an error | Not an ALLOW decision | Verify error handling, metrics, and response; do not ignore the error |

In integration tests, `WebTestClient` can send requests into the WebFlux application with real security chains. When using mock authentication, remember that mocks do not necessarily verify real HTTP Basic or JWT flows. Therefore, separate tests for **authentication mechanisms** and tests for **authorization rules**; for bypass risks caused by chain matchers, you must include test cases for URLs outside the higher-priority matcher.

## 11. Common Mistakes and How to Fix Them

**Mistake 1 — Confusing Servlet and WebFlux.** Using `FilterChainProxy`/`SecurityFilterChain` (Servlet) when building WebFlux breaks APIs and execution mechanics. Use `WebFilterChainProxy` and `SecurityWebFilterChain` from the `org.springframework.security.web.server` package.

**Mistake 2 — Assuming multiple chains all execute.** The proxy picks the **first match**; subsequent chains do not run once a chain matches. Put specific matchers first and general matchers last.

**Mistake 3 — Confusing `securityMatcher` with `pathMatchers`.** The former selects the chain; the latter selects rules **within that chain**. If you only configure `pathMatchers` on a chain that is never selected, the rule will never apply.

**Mistake 4 — Having no fallback chain.** Paths outside the matchers can reach handlers without passing through Spring Security's security filters. Use a catch-all chain with a deny-by-default policy or an explicitly comprehensive design.

**Mistake 5 — Adding a global WebFilter and thinking it is an inner security filter.** `@Order` on a global bean controls position around the proxy; `SecurityWebFiltersOrder` positions a filter inside the selected chain. Choose the right API.

**Mistake 6 — Global filter stopping before the proxy.** Returning `setComplete()` without calling `chain.filter(exchange)` can be a bypass. When intentional, thoroughly test the endpoint/response and apply appropriate protection.

**Mistake 7 — Calling `block()` inside a filter.** Reactor/WebFlux is designed to be non-blocking; replace it with `flatMap`, `then`, or other reactive operators.

**Mistake 8 — Drawing wrong conclusions from status codes or logs.** `401`, `403`, firewall `400`, `5xx` errors, and a completed `Mono<Void>` are different events. A completed response does not prove the request reached the handler or passed authorization.

**Mistake 9 — Logging full credentials/tokens during debugging.** Only log enough metadata to verify the chain/path, and use security TRACE only when needed under controlled conditions.

## 12. Self-Check Questions

**Question 1.** A request `/api/orders/1` matches both `apiChain` and `fallbackChain`. How many `SecurityWebFilterChain` instances are executed? **One**: the first matching chain according to priority order.

**Question 2.** Does using `.pathMatchers("/public/**").permitAll()` in `fallbackChain` cause `apiChain` to skip security for `/public/**`? **No**. `pathMatchers` defines authorization inside the selected chain; `securityMatcher` decides which chain a request enters.

**Question 3.** When `WebFilterChainProxy` finds no matching chain, does it automatically throw 403 by default? **No**. It can continue the original `WebFilterChain` without installing additional security filters for the request; this is a configuration risk that must be tested.

**Question 4.** Do `@Order(-200)` on a global WebFilter and `@Order(1)` on a security chain have the same meaning? **No**. One controls WebFilter order in WebFlux; the other controls the matcher evaluation order of security chains.

**Question 5.** Why must `Mono.empty()` not be returned from a custom WebFilter as a way to return 403? Because it only emits an empty completion signal and does not itself carry a denial decision or a 403 status. To stop execution, you must implement explicit response/error handling and place the filter at the proper layer.

**Key takeaway:** Requests flow through **WebFlux's WebFilter chain**; `WebFilterChainProxy` is **one WebFilter** in that chain; the proxy picks the **first matching SecurityWebFilterChain** and splices the selected chain's **security WebFilters** into the remaining execution. Matchers decide *which chain*, authorization decides *whether access is allowed*, and the WebFlux handler runs only when the pipeline permits reaching it.

## References

- [Spring Framework — WebFlux Reactive Core, Filters](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html) — `WebFilter` contract and how `WebFilter` is registered.
- [Spring Boot — Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html) — auto-detection of `WebFilter` beans and default proxy ordering in Boot.
- [Spring Security — WebFlux Security, Multiple Chains Support](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html) — `SecurityWebFilterChain`, `securityMatcher`, `@Order`, `ServerHttpSecurity`.
- [Spring Security — SecurityWebFilterChain API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/SecurityWebFilterChain.html) — `matches` and `getWebFilters`.
- [Spring Security — ServerHttpSecurity API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html) — `addFilterBefore`, `addFilterAfter`, `addFilterAt`.
- [Spring Security — WebFilterChainProxy source](https://github.com/spring-projects/spring-security/blob/main/web/src/main/java/org/springframework/security/web/server/WebFilterChainProxy.java) — verify how the proxy selects the first chain and chains filters together.
