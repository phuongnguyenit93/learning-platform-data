# SecurityWebFiltersOrder and the Order of Processing Stages in Spring Security WebFlux

## Lesson Objectives

After this lesson, you will be able to:

1. Explain how `SecurityWebFiltersOrder` controls the positions of `WebFilter` instances **inside** a `SecurityWebFilterChain`.
2. Read the order of the main stages: headers/HTTPS, CORS/CSRF, Reactor Context, authentication, anonymous, exception translation, authorization, and HTTP handling.
3. Distinguish **chain selection order** from **in-chain filter order**, as well as the incoming request direction from the outgoing response completion direction.
4. Use `ServerHttpSecurity.addFilterBefore(...)`, `addFilterAfter(...)`, and `addFilterAt(...)` for their intended purpose when adding a custom WebFilter.
5. Verify HTTP 200, 401, and 403 and observe the stages using Java/Spring WebFlux code without accidentally bypassing security mechanisms.

> Scope: **Spring Security for WebFlux (reactive)**. In Spring MVC/Servlet, the corresponding APIs are `SecurityFilterChain`, `HttpSecurity`, and `jakarta.servlet.Filter`; do not use Servlet APIs to directly infer the ordering of `SecurityWebFilterChain`.

## 1. Three Layers of "Order" That Are Easily Confused

When an HTTP request arrives at a WebFlux application, ordering is determined across different layers:

```text
Client
  |
  v
WebFlux WebFilter chain (application-wide filters)
  |
  v
Spring Security WebFilterChainProxy
  |
  +--> Select ONE matching SecurityWebFilterChain for the request
  |    (priority order among chains: @Order and securityMatcher)
  |
  +--> Run the WebFilters ACTUALLY present in the selected chain
  |    (relative position: SecurityWebFiltersOrder)
  |
  v
WebHandler / RouterFunction / Controller
  |
  v
HTTP response is completed back through the filter layers
```

- **Application-wide filter order:** `WebFilter` instances registered with WebFlux can be ordered by `@Order` or Spring ordering mechanisms. This is the layer outside the Security chain.
- **`SecurityWebFilterChain` selection order:** if multiple chain beans are defined, `@Order` and `securityMatcher(...)` determine which chain is tried first. Spring Security selects **one matching chain** for the request.
- **Internal filter order:** `SecurityWebFiltersOrder` is an enum describing standard position anchors used by `ServerHttpSecurity` when assembling filters inside the selected chain.

Therefore, `@Order(1)` on a `SecurityWebFilterChain` bean **does not mean** the authentication filter is at position 1. Similarly, `SecurityWebFiltersOrder.AUTHORIZATION` **is not** an authorization rule configuration; it is the position reserved for the permission-checking stage.

### What Is SecurityWebFiltersOrder?

`org.springframework.security.config.web.server.SecurityWebFiltersOrder` is an enum providing default positions for WebFlux security filters. Each constant has `getOrder()`; when building `ServerHttpSecurity`, filters are sorted by their corresponding order values.

Keep the right mental model:

- The enum lists **insertion anchors**. It does **not** mean every anchor contains a filter on every request or in every configuration. For instance, if an application only uses HTTP Basic, there is no reason to expect form login or OAuth2 login filters to also be present.
- The order expresses **relative position**, not a guarantee of a fixed integer per filter across every version. When comparing, use `getOrder()`; avoid hardcoding numbers or relying on `ordinal()`.
- A filter can **terminate a request early** (CORS preflight, CSRF rejection, failed authentication, logout, denied access). Subsequent filters may not be called.
- Enum constants/features can change between Spring Security 6.x and 7.x. Check the Javadoc for your project's exact library version before using an uncommon constant.

## 2. Order of SecurityWebFiltersOrder Anchors

The table below lists the constants in **declaration order from the Spring Security 7.1 Javadoc**; constants that only appear in newer versions or apply only to opt-in features are noted. When using Spring Security 6.x, check your project's own 6.x API; do not copy 7.x defaults blindly.

| Position | `SecurityWebFiltersOrder` Constant | Meaning / Typical Filter |
| --- | --- | --- |
| 1 | `FIRST` | Starting anchor for filters that must run very early |
| 2 | `HTTP_HEADERS_WRITER` | Sets configured security response headers |
| 3 | `HTTPS_REDIRECT` | `HttpsRedirectWebFilter` when HTTPS redirection is enabled |
| 4 | `CORS` | `CorsWebFilter` when appropriate CORS configuration is present |
| 5 | `CSRF` | `CsrfWebFilter` handling CSRF protection |
| 6 | `REACTOR_CONTEXT` | `ReactorContextWebFilter` loads `SecurityContext` from repository into Reactor Context |
| 7 | `HTTP_BASIC` | HTTP Basic authentication position when enabled |
| 8 | `FORM_LOGIN` | `AuthenticationWebFilter` position for form login when enabled |
| 9 | `AUTHENTICATION` | General authentication position, e.g., custom/Bearer in appropriate configurations |
| 10 | `ANONYMOUS_AUTHENTICATION` | `AnonymousAuthenticationWebFilter` provides an anonymous identity when needed |
| 11 | `OAUTH2_AUTHORIZATION_CODE` | Position supporting the OAuth2 authorization code flow when enabled |
| 12 | `LOGIN_PAGE_GENERATING` | Generates the default login page if the feature is used |
| 13 | `LOGOUT_PAGE_GENERATING` | Generates the logout confirmation page if configured |
| 14 | `ONE_TIME_TOKEN` | Filter supporting one-time-token login in versions with this feature |
| 15 | `ONE_TIME_TOKEN_SUBMIT_PAGE_GENERATING` | Generates the one-time token submission page when that feature is enabled |
| 16 | `SECURITY_CONTEXT_SERVER_WEB_EXCHANGE` | `SecurityContextServerWebExchangeWebFilter` enables `exchange.getPrincipal()` to use the reactive security context |
| 17 | `SERVER_REQUEST_CACHE` | `ServerRequestCacheWebFilter` supports saving/restoring requests in certain login flows |
| 18 | `LOGOUT` | Handles logout requests if configured |
| 19 | `EXCEPTION_TRANSLATION` | Translates downstream authentication/authorization errors into responses handled by security handlers |
| 20 | `AUTHORIZATION` | Checks exchange access rules before reaching the handler |
| 21 | `LAST` | Final anchor for additional filters |

**Read the table as positions, not a mandatory runtime list:** most projects only instantiate a subset depending on `httpBasic`, `formLogin`, `oauth2Login`, `oauth2ResourceServer`, `csrf`, `cors`, etc. The `FIRST`/`LAST` anchors are mainly useful for filter insertion. Table row numbers also do not represent the integers returned by `getOrder()`.

Notice two important pairs of positions:

- `REACTOR_CONTEXT` is **before authentication positions**: it supports loading pre-existing authentication info from the repository into Reactor Context. When new authentication succeeds, the authentication mechanism can provide the context to downstream processing.
- `EXCEPTION_TRANSLATION` is **before `AUTHORIZATION`**: it wraps downstream processing, so it can catch unauthenticated/unauthorized errors raised during authorization and select the appropriate entry point or access-denied handler.

### REACTOR_CONTEXT vs. SECURITY_CONTEXT_SERVER_WEB_EXCHANGE

The two names look similar but have different responsibilities:

| Anchor | Focus |
| --- | --- |
| `REACTOR_CONTEXT` | Uses `ServerSecurityContextRepository` to place `SecurityContext` into `ReactiveSecurityContextHolder` in the processing flow |
| `SECURITY_CONTEXT_SERVER_WEB_EXCHANGE` | Adapts `ServerWebExchange.getPrincipal()` to look up the principal from `ReactiveSecurityContextHolder` |

Neither of them is a password verifier. Verification belongs to authentication filters/managers. `ReactiveSecurityContextHolder` is bound to the subscription's Reactor Context; do not call thread-local `SecurityContextHolder.getContext()` in a reactive service to guess identity.

## 3. Reading the Stages Along a Request's Execution Flow

An HTTP Basic request to `GET /admin` can be viewed along the following conceptual sequence (only for stages present in the configuration):

```text
Incoming request
   |
   +--> Security headers / HTTPS / CORS / CSRF
   |
   +--> Load SecurityContext into Reactor Context if present
   |
   +--> HTTP Basic -> AuthenticationManager (if Basic credentials are present)
   |
   +--> Other authentication positions / anonymous when applicable
   |
   +--> Wrap exchange principal / request cache / logout when applicable
   |
   +--> Exception translation prepares to handle downstream errors
   |
   +--> Authorization: does /admin require ROLE_ADMIN?
   |      |
   |      +-- No: error/denial -> security handler -> 401 or 403
   |      |
   |      +-- Yes: invoke next WebFilterChain -> Controller
   |
   +--> Mono/Flux response completes or errors
   |
Response exits through the participating filters
```

This is a learning map, **not a guaranteed trace for every request**. For example:

- CORS preflight may be handled early without reaching the controller.
- CSRF only needs to reject requests within its protection rules; GET/HEAD typically do not require a token.
- If invalid Basic credentials are provided, authentication may emit an error handled by an entry point, and the controller is not called.
- An authenticated request lacking the required role is typically denied with 403; an unauthenticated request to a protected resource typically receives 401 in the HTTP Basic example.
- Logout can handle matching requests and stop the rest of the chain.
- `permitAll()` is only a rule at authorization: other filters may still run before it. A "public endpoint" does not automatically make the entire Security chain vanish.

### Why Is EXCEPTION_TRANSLATION Before AUTHORIZATION?

In `WebFilter.filter(exchange, chain)`, calling `chain.filter(exchange)` receives the publisher for the downstream portion. An upstream filter can wrap this publisher to catch errors. Therefore, **request entry order** differs from **completion callback exit order**.

Picture two filters `A`, `B` and an endpoint:

```text
A: before
  B: before
    Handler
  B: after
A: after
```

This resembles nested parentheses. `EXCEPTION_TRANSLATION` sits before `AUTHORIZATION` so it gets the chance to intercept `AccessDeniedException` or security errors originating inside what it wraps. Do not put a blanket `onErrorResume` in a custom filter that turns every `AccessDeniedException` into success: that can mask the 401/403 response mechanism.

### Simulating Enter/Exit Order with Reactor

File **`src/main/java/demo/FilterNestingDemo.java`**, run with Java 17+ and `reactor-core` on the classpath:

```java
package demo;

import reactor.core.publisher.Mono;

public class FilterNestingDemo {
    public static void main(String[] args) {
        Mono<Void> handler =
                Mono.fromRunnable(() -> System.out.println("handler")).then();

        Mono<Void> security = around("security", handler);
        Mono<Void> global = around("global", security);

        global.block(); // Only in this console program
    }

    private static Mono<Void> around(String name, Mono<Void> next) {
        return Mono.defer(() -> {
            System.out.println(name + " before");
            return next.then(Mono.fromRunnable(
                    () -> System.out.println(name + " after")));
        });
    }
}
```

Exact stdout when the publisher completes successfully:

```text
global before
security before
handler
security after
global after
```

Run via an appropriate Gradle task/application or in an IDE with the Reactor library. This is only a model for signal ordering: real code in Spring Security has error branches, cancellation, and filters that short-circuit the chain early. `then(...)` only executes the final action when upstream completes successfully; if you also need to observe errors/cancellation, consider `doFinally(signalType -> ...)`. Inside a WebFlux controller/filter, **never call `block()`**.

## 4. Where Should a Custom WebFilter Be Placed?

Use `ServerHttpSecurity` APIs:

```java
http.addFilterBefore(customWebFilter, SecurityWebFiltersOrder.AUTHORIZATION);
http.addFilterAfter(customWebFilter, SecurityWebFiltersOrder.AUTHENTICATION);
http.addFilterAt(customWebFilter, SecurityWebFiltersOrder.AUTHENTICATION);
```

| API | Meaning | Notes |
| --- | --- | --- |
| `addFilterBefore(filter, order)` | Insert immediately before the chosen **order anchor** | Suitable for processing/observing before authorization |
| `addFilterAfter(filter, order)` | Insert immediately after the chosen **order anchor** | Does not imply every configured authentication method has already finished |
| `addFilterAt(filter, order)` | Register a filter at the same order position | **Does not replace** an existing filter; ties at the same slot may not have guaranteed relative order |

**Choosing a position based on purpose:**

- Need to read the authenticated identity and write general request audit logs: typically insert `addFilterBefore(probe, AUTHORIZATION)`; still must handle anonymous/empty context cases.
- Need to handle a special credential type: integrate into `AuthenticationWebFilter` + `ServerAuthenticationConverter` + `ReactiveAuthenticationManager` and insert at the appropriate authentication anchor; do not just read a header and assume the user is logged in.
- Need to add access-control rules: prefer the `authorizeExchange` DSL, `ReactiveAuthorizationManager`, or reactive method security rather than writing a custom WebFilter returning 200/403.
- Need CORS/CSRF/headers: prefer the standard configurations provided by `ServerHttpSecurity`; avoid reimplementing protective filters in hand-written code.

Do not register a custom security filter with `@Component` or a global `@Bean WebFilter` if the goal is to control **its position solely inside SecurityWebFilterChain**. Doing so can cause it to appear in the outer WebFlux chain (or run an extra time if also inserted into the security chain).

### "At" Does Not Mean "Replace"

In WebFlux, `addFilterAt(filter, AUTHENTICATION)` **adds** a WebFilter at the same order; there is no contract guaranteeing removal of an existing authentication filter. If you truly want to change the authentication mechanism, explicitly configure/disable the old mechanism and register the new one. Do not rely on tie-breaking among multiple filters with the same order.

### Source-Code Configuration Order Is Not Execution Order

Two `addFilterBefore(...)` / `addFilterAfter(...)` calls can appear in any order in Java configuration code, because filters are sorted by order when building the chain. Avoid putting two custom filters in the same slot so you do not assume tie-break stability. Observe with logs/tests instead of guessing from code line order.

## 5. Hands-On WebFlux Example with a Filter Before Authorization

The following example uses **Java 17+**, Spring Boot with Spring Security WebFlux, one Security chain, HTTP Basic, and a custom `WebFilter` that only logs the observed authentication type. It does not replace permission checks and does not authenticate credentials itself.

In a Spring Boot Gradle project with plugins and dependency management already configured:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
```

**`src/main/java/demo/orderdemo/OrderDemoApplication.java`**:

```java
package demo.orderdemo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.WebFilter;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class OrderDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderDemoApplication.class, args);
    }
}

@Configuration
@EnableWebFluxSecurity
class SecurityConfiguration {
    private static final Logger LOG =
            LoggerFactory.getLogger(SecurityConfiguration.class);

    @Bean
    SecurityWebFilterChain securityChain(ServerHttpSecurity http) {
        WebFilter stageProbe = (exchange, chain) ->
                ReactiveSecurityContextHolder.getContext()
                        .map(ctx -> ctx.getAuthentication())
                        .map(auth -> auth.getClass().getSimpleName())
                        .defaultIfEmpty("NoSecurityContext")
                        .doOnNext(type -> LOG.info(
                                "Before AUTHORIZATION path={} authType={}",
                                exchange.getRequest().getPath().value(),
                                type))
                        .then(Mono.defer(() -> chain.filter(exchange)))
                        .doFinally(signal -> LOG.info(
                                "Finished downstream path={} signal={}",
                                exchange.getRequest().getPath().value(),
                                signal));

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public").permitAll()
                        .pathMatchers("/admin").hasRole("ADMIN")
                        .anyExchange().authenticated()
                )
                .httpBasic(Customizer.withDefaults())
                .addFilterBefore(stageProbe, SecurityWebFiltersOrder.AUTHORIZATION)
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("reader-pass"))
                .roles("READER")
                .build();
        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN")
                .build();
        return new MapReactiveUserDetailsService(reader, admin);
    }
}

@RestController
class ExampleApi {
    @GetMapping("/public")
    Mono<String> publicEndpoint() {
        return Mono.just("public");
    }

    @GetMapping("/me")
    Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
                .map(ctx -> "hello " + ctx.getAuthentication().getName());
    }

    @GetMapping("/admin")
    Mono<String> admin() {
        return Mono.just("admin only");
    }
}
```

**Why this placement and code?**

1. `stageProbe` is inserted only via `ServerHttpSecurity` into the chain, with no `@Component` registering a global WebFilter.
2. `addFilterBefore(..., AUTHORIZATION)` places it after standard authentication positions and before the exchange permission check.
3. `ReactiveSecurityContextHolder.getContext()` retrieves the context from the pipeline. `defaultIfEmpty(...)` ensures the probe still invokes `chain.filter(exchange)` when there is no context.
4. `then(Mono.defer(() -> chain.filter(exchange)))` runs downstream after the preceding log operation completes. There is no manual `subscribe()` or `block()` in the filter.
5. `doFinally` logs the downstream termination signal across complete/error/cancel. For denied requests, the signal may be `onError` at the probe's position, even though the final HTTP response is translated by the outer exception-translation filter into 401/403. **A signal is not an HTTP status code.**
6. The probe logs only the authentication class name, avoiding printing passwords, Basic credentials, bearer tokens, or the entire `SecurityContext`.

Run from a project with Gradle Wrapper:

```bash
./gradlew bootRun
```

On Windows PowerShell you can use `.\gradlew.bat bootRun`. The system needs a Java version compatible with the Spring Boot version, typically Java 17+ for Boot 3.x. This Java code requires Spring Boot and dependencies managed by Gradle/Maven; standalone `javac` without the Spring classpath will not compile.

In another terminal:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/admin
curl -i -u reader:reader-pass http://localhost:8080/me
curl -i -u reader:reader-pass http://localhost:8080/admin
curl -i -u admin:admin-pass http://localhost:8080/admin
```

| Request | Expected HTTP Status | Body on Success | Reason |
| --- | --- | --- | --- |
| `GET /public` without credentials | `200` | `public` | `permitAll()` |
| `GET /admin` without credentials | `401` | Depends on entry point | Login required |
| `GET /me` as `reader` | `200` | `hello reader` | Authenticated; controller reads context |
| `GET /admin` as `reader` | `403` | Depends on handler | Authenticated but lacks `ROLE_ADMIN` |
| `GET /admin` as `admin` | `200` | `admin only` | Has `ROLE_ADMIN` |

Note: `roles("ADMIN")` creates authority `ROLE_ADMIN`; `hasRole("ADMIN")` automatically applies the `ROLE_` prefix. Headers, error bodies, and log details depend on version/configuration; do not write tests by matching **verbatim** entire logs or error bodies. The accounts/passwords above are strictly for practice environments; never put example credentials into production source.

### Automated Verification of HTTP Statuses

With Spring Boot 3.x and `spring-boot-starter-test`, add:

**`src/test/java/demo/orderdemo/OrderDemoHttpTest.java`**:

```java
package demo.orderdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class OrderDemoHttpTest {
    @Autowired
    WebTestClient client;

    @Test
    void anonymousCannotReadAdmin() {
        client.get().uri("/admin").exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void readerCannotReadAdmin() {
        client.get().uri("/admin")
                .headers(headers -> headers.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminCanReadAdmin() {
        client.get().uri("/admin")
                .headers(headers -> headers.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin only");
    }
}
```

Run `./gradlew test --tests demo.orderdemo.OrderDemoHttpTest` (PowerShell: `.\gradlew.bat test --tests demo.orderdemo.OrderDemoHttpTest`). When configured properly, all three tests PASS. These tests **verify access behavior**. To prove precisely that a custom filter ran before authorization or measure log order, add controlled instrumentation such as a spy/metric in the test rather than relying solely on status codes.

## 6. Distinguishing Multiple-Chain Order from Filter Order

An advanced configuration might dedicate `/api/**` to a JWT resource server while other URLs use HTTP Basic. The key is the ordering of **chain beans** and matchers, not `SecurityWebFiltersOrder`.

Illustrative structural snippet, not a standalone runnable program (requires a JWT decoder bean and other resource server components):

```java
@Bean
@Order(1)
SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
    return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(ex -> ex.anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
            .build();
}

@Bean
SecurityWebFilterChain defaultChain(ServerHttpSecurity http) {
    return http
            .authorizeExchange(ex -> ex.anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}
```

For `/api/orders`, the chain with `@Order(1)` is evaluated first; if the matcher matches, Spring Security uses the API chain. For `/dashboard`, the API matcher does not match and the default chain handles it. Each chain has its own filters ordered by `SecurityWebFiltersOrder`.

**Critical mistake to avoid:** letting a specialized chain match every URL because you forgot `securityMatcher`, leaving the remaining chain no chance to run; or configuring matchers that leave protected endpoints uncovered. Test request routing across every chain, especially public, protected, API, admin, and unmatched requests.

## 7. Common Misconceptions and Pitfalls

| Misconception / Mistake | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| "The enum has 21 constants, so every request runs 21 filters" | The enum defines slots; many features are disabled | Inspect the actually built chain and enabled authentication mechanisms |
| "Changing Java declaration order changes execution order" | Filters are sorted by order value | Insert with `addFilterBefore/After/At` at an explicit anchor |
| "`addFilterAt` replaces an existing filter" | Adds at the same order, potentially creating a tie | Disable/replace the old mechanism via config and choose an appropriate position |
| "`@Order` on a chain is the same as `SecurityWebFiltersOrder`" | One selects the chain; the other orders filters | Identify which ordering layer is being configured |
| "HTTP Basic always runs for every request" | Only runs when the mechanism and matcher/credentials apply | Read the actual configuration; test different request types |
| "Authorization must run before authentication" | Cannot check identity-based permissions before context exists | Let authentication/context mechanisms run at the appropriate stage |
| "No need for EXCEPTION_TRANSLATION because we have ControllerAdvice" | Security errors can occur before the controller | Use Spring Security's entry point/access-denied handler |
| "`permitAll()` skips all filters" | Only allows access at the authorization step | If different behavior is needed, configure matchers/filters purposefully |
| "Using `@Component` WebFilter and `addFilterBefore` together is safe" | Can register in both global and security chains | Register only through the single path actually needed |
| "Stopping the Mono when SecurityContext is missing will automatically deny" | `Mono.empty()` is only an empty value signal | Always handle empty branches explicitly and continue the chain/authorization properly |
| "`doFinally(ON_ERROR)` proves the response is definitely HTTP 500" | Exception translation can convert errors into 401/403 | Assert status separately and understand the observation scope |
| "Logging tokens and SecurityContext makes debugging easier" | Can expose sensitive login data | Log controlled types/trace IDs; never log credentials |

### Custom Filter Design Checklist

- Determine whether the filter needs to run **before or after** authentication and authorization; if the principal is needed, read it with `ReactiveSecurityContextHolder`, handling anonymous/empty cases.
- Never use `block()` or manual `subscribe()` inside a WebFilter; return `chain.filter(exchange)`'s publisher and preserve error/cancellation paths.
- Do not return a success response upon receiving `AuthenticationException` or `AccessDeniedException` without an explicit policy; keep exception translation working.
- Avoid reading the request body in a filter unless caching/replay guarantees are implemented; a reactive body can be consumed so the controller can no longer read it.
- When placing multiple filters near an anchor, test the actual order; do not assume two filters with the same order sort deterministically.
- When running multiple chains, verify every `securityMatcher` and `@Order` priority; a request is routed to a single matching chain and does not inherit rules from other chains.
- Do not disable CSRF, CORS, or security headers just to test ordering; these protections serve distinct purposes and require separate decisions.

## 8. Practice Exercises

1. Change the demo filter to `addFilterAfter(stageProbe, SecurityWebFiltersOrder.AUTHENTICATION)`. Use logs/a spy to verify its position and explain why "after the AUTHENTICATION slot" does not mean after every optional authentication method.
2. Add one filter before `EXCEPTION_TRANSLATION` and one filter before `AUTHORIZATION`. When accessing `/admin` without the required role, compare the observed error signals and the final HTTP status code.
3. Print the comparison between `SecurityWebFiltersOrder.REATOR_CONTEXT` and `AUTHORIZATION` using `getOrder()`, after fixing the constant name properly. Explain why order integers should not be hardcoded.
4. Add `/api/**` with a separate higher-priority chain; try accessing an API URL, a default URL, and a URL with no rule. Find the failure mode if the API chain accidentally matches everything.
5. Test an OPTIONS preflight request with CORS properly configured, and a POST missing a CSRF token in a session-based app. Distinguish which stage rejects each, and why ordering cannot be inferred solely from status codes.
6. Write a test for a custom filter ensuring `chain.filter(exchange)` is subscribed to **exactly once** both when a security context is present and when it is absent.

**Core takeaway:** `SecurityWebFiltersOrder` specifies the **relative position** of WebFlux security filters. Read incoming request processing in the forward flow and outgoing completion signals as publishers complete; select the right chain before thinking about individual filters. When adding filters, preserve the reactive contract and let Spring Security's authentication/authorization/exception translation do their jobs.

## Official Documentation

- [Spring Security — SecurityWebFiltersOrder Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/SecurityWebFiltersOrder.html)
- [Spring Security — ServerHttpSecurity Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Security — WebFlux Security and Multiple Chains Support](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security — Reactive SecurityContext and Spring Security](https://docs.spring.io/spring-security/reference/reactive/authentication/index.html)
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
