# Applying the Same Security Chain to Controllers and RouterFunctions

> **Topic:** `WebFilter` architecture in Spring Security reactive. Examples target **Spring Boot 3.x, Spring Security 6.x, Spring WebFlux, and Java 17+**. An application can declare endpoints with both `@RestController` and `RouterFunction`, and **the same `SecurityWebFilterChain` protects both** when HTTP requests flow through the application's Spring WebFlux infrastructure.

## Objectives

After this lesson, you will be able to:

1. Describe the path from an HTTP request through Spring Security `WebFilter` instances to `DispatcherHandler`, and then to an annotated controller or functional handler.
2. Distinguish **`SecurityWebFilterChain` applied to HTTP exchanges** from `HandlerFilterFunction` applied only within a group of functional routes.
3. Write **a single `SecurityWebFilterChain` bean** and a shared `authorizeExchange` policy for paths handled by both handler styles.
4. Verify **401 / 403 / 200** behavior on both endpoints using `WebTestClient` and catch missed path-matcher bugs.
5. Know when multiple security chains are needed and why `securityMatcher`, `@Order`, and authorization rule ordering change outcomes.

## 1. Two Endpoint Declaration Styles, One WebFlux Runtime

Spring WebFlux provides two endpoint programming models:

| Aspect | Annotation-Based Controller | Functional RouterFunction |
| --- | --- | --- |
| Route declaration | `@RestController`, `@GetMapping`, `@RequestMapping` | `RouterFunction<ServerResponse>` bean with `RequestPredicates` |
| Request-handling unit | Handler method on controller bean | `HandlerFunction<ServerResponse>` receiving `ServerRequest` |
| Common return type | `Mono<T>`, `Flux<T>`, or framework-supported types | `Mono<ServerResponse>` |
| Handler mapping | `RequestMappingHandlerMapping` | `RouterFunctionMapping` |
| Handler execution | `RequestMappingHandlerAdapter` | `HandlerFunctionAdapter` and `ServerResponseResultHandler` |
| Shared infrastructure | `DispatcherHandler` and WebFlux infrastructure | Same `DispatcherHandler` and WebFlux infrastructure |
| HTTP server security | `SecurityWebFilterChain` | **Same `SecurityWebFilterChain`** |

Choosing Controller or RouterFunction is a choice of **how routes and handlers are defined**. It does not create a separate kind of HTTP security. When both live in the **same WebFlux application context and HTTP server**, requests to both pass through the application-level `WebFilter` chain, including Spring Security's `WebFilterChainProxy`.

Example URLs:

- `GET /api/annotated/hello` handled by `@RestController`.
- `GET /api/functional/hello` handled by `RouterFunction`.
- `GET /public/ping` is a public route to observe rule ordering.

We will apply the same rules: GET under `/api/**` requires role `READER`, whereas `/public/ping` requires no login.

## 2. Request Path and Where Spring Security Makes Decisions

Overall flow of a **typical WebFlux server**:

```text
Client HTTP request
    |
    v
HttpHandler / WebHandler with application's WebFilter chain
    |
    v
Spring Security WebFilterChainProxy
    |-- selects matching SecurityWebFilterChain for ServerWebExchange
    |-- verifies credentials, creates Authentication when valid
    |-- applies authorization rules, CSRF, and related filters
    |-- can terminate with 401/403 before invoking handler
    |
    v
DispatcherHandler (Spring WebFlux)
    |
    +--> RequestMappingHandlerMapping --> @RestController method
    |
    +--> RouterFunctionMapping --> HandlerFunction (WebFlux.fn)
    |
    v
Response is written back to client
```

The diagram highlights **security's position in the request pipeline**, without mandating that every filter runs in the listed order. Actual filter order is managed by Spring Security and depends on login mechanisms, CSRF, exception handling, etc.

**Why does the same chain apply to both handler types?**

- `SecurityWebFilterChain` matches requests by `ServerWebExchange`: URL, HTTP method, and request attributes that matchers can evaluate.
- Authorization in `authorizeExchange` executes inside the WebFilter pipeline, before either controller or functional handler performs work.
- Spring Security **does not inspect** whether an endpoint was written with `@GetMapping` or `RouterFunctions.route(...)` to pick a different chain by default.
- Only after passing security does `DispatcherHandler` delegate to the matching handler mapping. Annotated and functional endpoints can both be served in the same application.

**Prerequisite:** This must be a **true WebFlux server**. If an application has both `spring-boot-starter-web` and `spring-boot-starter-webflux`, Spring Boot usually prefers **Spring MVC/Servlet** by default; in that case `SecurityFilterChain`/`HttpSecurity` is the Servlet security mechanism. For this lesson, use `spring-boot-starter-webflux` as the web server and verify the app selects `REACTIVE`. Having `WebClient` or `Mono` on the classpath is not enough to prove the server runs WebFlux.

## 3. Preparing the Sample Project

Create a Spring Boot 3.x project with Java 17+, Gradle Groovy DSL, and the needed dependencies.

In the `build.gradle` of a project with the Spring Boot plugin and dependency management applied:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Do not add `spring-boot-starter-web` for this exercise.** `starter-webflux` provides the WebFlux HTTP server; `starter-security` provides Spring Security; `starter-test` provides JUnit 5, AssertJ, and `WebTestClient` via the associated test libraries.

Example code layout:

```text
src/
  main/java/com/example/webfluxsecurity/
    DemoApplication.java
    GreetingController.java
    FunctionalRoutes.java
    WebSecurityConfig.java
  test/java/com/example/webfluxsecurity/
    SharedSecurityChainTest.java
```

The code listings below are **separate files in the same package**. Do not merge four `public` classes into one Java file. Once the Spring Boot project is configured with Gradle, run `./gradlew bootRun` and `./gradlew test`. On Windows PowerShell, use `.\gradlew.bat` instead.

### 3.1 Startup File

`src/main/java/com/example/webfluxsecurity/DemoApplication.java`:

```java
package com.example.webfluxsecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

`@SpringBootApplication` scans components in the same package and subpackages. The Controller, RouterFunction bean, and SecurityConfig in the following files are all registered into **the same Spring application context**.

### 3.2 Annotated Controller

`src/main/java/com/example/webfluxsecurity/GreetingController.java`:

```java
package com.example.webfluxsecurity;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class GreetingController {

    @GetMapping(
        value = "/api/annotated/hello",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> hello() {
        return Mono.just("Hello from Controller");
    }

    @GetMapping(
        value = "/public/ping",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> ping() {
        return Mono.just("pong");
    }
}
```

The `hello()` handler returns `Mono<String>`; Spring WebFlux sends the text body when the publisher completes. `ping()` exercises the `permitAll` route. Both paths are seen by Spring Security as HTTP exchanges, not as a special "controller request" type.

### 3.3 Functional RouterFunction

`src/main/java/com/example/webfluxsecurity/FunctionalRoutes.java`:

```java
package com.example.webfluxsecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RequestPredicates;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration(proxyBeanMethods = false)
public class FunctionalRoutes {

    @Bean
    RouterFunction<ServerResponse> greetingRoute() {
        return RouterFunctions.route(
            RequestPredicates.GET("/api/functional/hello"),
            request -> ServerResponse.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("Hello from RouterFunction")
        );
    }
}
```

`RequestPredicates.GET(...)` defines the URL and HTTP method; `HandlerFunction` receives `ServerRequest` and produces `Mono<ServerResponse>`. The handler does not check credentials itself. It is protected **before invocation** by the shared `WebFilter` chain.

**Distinguishing two filter layers:** `RouterFunctions.route().filter(...)` or `RouterFunction.filter(...)` adds a `HandlerFilterFunction` only to the functional routes attached to that router. It does not apply to `@RestController`. To apply authentication, authorization, and HTTP server policies to both, configure a **Spring Security `SecurityWebFilterChain`**.

## 4. One Shared SecurityWebFilterChain for Both

`src/main/java/com/example/webfluxsecurity/WebSecurityConfig.java`:

```java
package com.example.webfluxsecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
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
public class WebSecurityConfig {

    @Bean
    SecurityWebFilterChain sharedSecurityChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/public/ping").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/**").hasRole("READER")
                .anyExchange().denyAll()
            )
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

        var viewer = User.withUsername("viewer")
            .password(encoder.encode("viewer-demo-password"))
            .roles("VIEWER")
            .build();

        return new MapReactiveUserDetailsService(reader, viewer);
    }
}
```

**Why does this configuration use exactly one chain?**

1. There is only **one `SecurityWebFilterChain` bean** declared as `sharedSecurityChain`. Without a `securityMatcher(...)` limiting chain scope, the chain evaluates all incoming HTTP requests by default.
2. `authorizeExchange` inspects URL and method, not handler type. Both `GET /api/annotated/hello` and `GET /api/functional/hello` match `GET /api/**` and require `hasRole("READER")`.
3. `hasRole("READER")` corresponds to requiring authority `ROLE_READER`. `User.roles("READER")` creates that authority automatically. `viewer` logs in validly but only has `ROLE_VIEWER`, so it is blocked from both endpoints.
4. `httpBasic` authenticates via `Authorization: Basic ...` for the demo; `formLogin` is disabled to avoid form redirects that obscure observing 401. HTTP Basic is **only an illustrative choice**, not a blanket recommendation for every real-world WebFlux app.
5. `anyExchange().denyAll()` rejects all remaining requests in the chain. Place specific rules before general rules so a broad rule does not swallow requests.
6. Spring Security WebFlux **enables CSRF protection by default**. The example has only GET endpoints, so no CSRF token is needed when calling sample routes; if adding POST/PUT/DELETE, design CSRF handling for your client type. Never disable CSRF globally just to make a demo easy to run.

**Passwords in code are solely for internal testing.** In real deployments, never hardcode accounts or secrets in source; use a proper user store/identity provider and secret management. HTTP Basic must run over HTTPS outside localhost. In practice you can replace HTTP Basic with form sessions, OAuth2 Login, or JWT Resource Server without changing the core principle: **the security chain operates before both handlers**.

### 4.1 Shared Rules Are Based on URL, Not Annotations

Suppose a client sends:

```http
GET /api/annotated/hello HTTP/1.1
Host: localhost:8080
Authorization: Basic ...
```

and then sends:

```http
GET /api/functional/hello HTTP/1.1
Host: localhost:8080
Authorization: Basic ...
```

The same `SecurityWebFilterChain` receives both `ServerWebExchange` instances, the same `pathMatchers(HttpMethod.GET, "/api/**")`, the same authentication provider, and the `hasRole("READER")` rule. Differences begin only when `DispatcherHandler` resolves the handler to produce the response.

If you want one endpoint to require different permissions, add a dedicated rule **before** the `/api/**` rule, for example:

```java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/public/**").permitAll()
    .pathMatchers(HttpMethod.GET, "/api/functional/admin/**")
        .hasRole("ADMIN")
    .pathMatchers(HttpMethod.GET, "/api/**")
        .hasRole("READER")
    .anyExchange().denyAll()
)
```

The block above is a **configuration snippet replacing the `authorizeExchange` section** in `WebSecurityConfig`, not a standalone Java method. Actual new endpoints must be defined accordingly. Even when an admin route lives in a RouterFunction, Spring Security still applies rules by URL/method as usual.

## 5. Verifying Each Path via HTTP

After running `./gradlew bootRun` with default settings (typically port 8080), expected table:

| HTTP Request | Authentication | Endpoint | Expectation |
| --- | --- | --- | --- |
| `GET /public/ping` | None | Controller | `200 OK`, body `pong` |
| `GET /api/annotated/hello` | None | Controller | `401 Unauthorized` |
| `GET /api/functional/hello` | None | RouterFunction | `401 Unauthorized` |
| `GET /api/annotated/hello` | `reader`, valid password | Controller | `200 OK`, body `Hello from Controller` |
| `GET /api/functional/hello` | `reader`, valid password | RouterFunction | `200 OK`, body `Hello from RouterFunction` |
| `GET /api/annotated/hello` | `viewer`, valid password | Controller | `403 Forbidden` |
| `GET /api/functional/hello` | `viewer`, valid password | RouterFunction | `403 Forbidden` |
| `POST /api/functional/hello` | Any | No POST route | Not executed like the GET route; status depends on auth/CSRF/handler resolution |

**401 and 403 differ:** 401 means not validly authenticated or missing credentials for a protected resource; 403 means authenticated but lacking sufficient authorities (here, missing `ROLE_READER`). When a route does not exist, the final HTTP error also depends on security and processing order: do not use 404 to conclude that filters did not run.

Test the public route and unauthenticated requests with curl:

```bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/annotated/hello
curl -i http://localhost:8080/api/functional/hello
```

To test the `reader` account, you can run `curl -i -u reader http://localhost:8080/api/functional/hello` and enter the demo password when curl prompts. Interactive entry avoids putting passwords directly on the command line. For real applications, HTTP Basic must run over HTTPS; never send passwords over plain HTTP.

Example results **to observe** (not exhaustive simulated logs):

```text
GET /public/ping          -> HTTP 200, pong
GET /api/annotated/hello  -> HTTP 401 without credentials
GET /api/functional/hello -> HTTP 401 without credentials
reader + annotated        -> HTTP 200, Hello from Controller
reader + functional       -> HTTP 200, Hello from RouterFunction
viewer + annotated        -> HTTP 403
viewer + functional       -> HTTP 403
```

## 6. Integration Tests: Proving the Shared Security Chain via Behavior

Tests running directly against the real HTTP server of `@SpringBootTest(webEnvironment = RANDOM_PORT)` are more trustworthy than testing a single router in isolation and assuming application security also ran. File:

`src/test/java/com/example/webfluxsecurity/SharedSecurityChainTest.java`:

```java
package com.example.webfluxsecurity;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class SharedSecurityChainTest {

    private static final List<String> PROTECTED_PATHS = List.of(
        "/api/annotated/hello",
        "/api/functional/hello"
    );

    @Autowired
    WebTestClient client;

    @Autowired
    ApplicationContext context;

    @Test
    void oneSecurityChainIsRegistered() {
        assertThat(context.getBeansOfType(SecurityWebFilterChain.class))
            .hasSize(1);
    }

    @Test
    void anonymousIsRejectedOnBothEndpoints() {
        for (String path : PROTECTED_PATHS) {
            client.get()
                .uri(path)
                .exchange()
                .expectStatus().isUnauthorized();
        }
    }

    @Test
    void readerCanCallBothEndpoints() {
        client.get()
            .uri("/api/annotated/hello")
            .headers(h -> h.setBasicAuth(
                "reader", "reader-demo-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("Hello from Controller");

        client.get()
            .uri("/api/functional/hello")
            .headers(h -> h.setBasicAuth(
                "reader", "reader-demo-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("Hello from RouterFunction");
    }

    @Test
    void viewerIsForbiddenOnBothEndpoints() {
        for (String path : PROTECTED_PATHS) {
            client.get()
                .uri(path)
                .headers(h -> h.setBasicAuth(
                    "viewer", "viewer-demo-password"))
                .exchange()
                .expectStatus().isForbidden();
        }
    }

    @Test
    void publicControllerIsAccessibleWithoutLogin() {
        client.get()
            .uri("/public/ping")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("pong");
    }
}
```

**Checks actually performed by this test:**

- The context started by Spring Boot has one `SecurityWebFilterChain` bean.
- An unauthenticated caller is rejected at **both** endpoints; there is no functional "shortcut" bypassing security.
- A user with `ROLE_READER` can reach both; a valid user lacking the role is blocked at both.
- The public endpoint remains accessible without credentials.

Run:

```bash
./gradlew test --tests '*SharedSecurityChainTest'
```

Expect Gradle to report passing tests when source, packages, dependencies, and context match the example. Tests can fail if the application has an extra `SecurityWebFilterChain`, lacks the WebFlux starter, uses a wrong password, has external configuration altering port/security, or misses component scanning of endpoints. In that case, inspect the actual assertion and exception; never "fix" it by disabling security.

**Note on test slices:** `@WebFluxTest` loads only a slice of the context and may not auto-detect `RouterFunction` beans or custom `SecurityWebFilterChain` beans; you must import the relevant components. Plain `WebTestClient.bindToRouterFunction(...)` may test only the handler while **bypassing the application's security context**. Use `@SpringBootTest` as above to observe both annotated and functional endpoints with the actual declared security configuration.

## 7. How Does SecurityWebFilterChain Differ from HandlerFilterFunction?

Both names contain *Filter*, but their scope and responsibilities differ:

| Criterion | Spring Security `SecurityWebFilterChain` | WebFlux.fn `HandlerFilterFunction` |
| --- | --- | --- |
| Scope | HTTP `ServerWebExchange` passing through Spring Security `WebFilterChainProxy` | `HandlerFunction` instances belonging to the router where the filter is declared |
| Affects `@RestController` | Yes, when request matches the chain | Does not apply automatically |
| Affects `RouterFunction` | Yes, when request matches the chain | Yes, within the functional route group containing the filter |
| Timing | WebFilter layer of the application pipeline before the handler | Around invoking the functional handler once the corresponding router is matched |
| Used for | Authentication, authorization, CSRF, security context, security headers | Logging/modifying request-response or local business checks inside functional routing |
| Configuration | `@Bean SecurityWebFilterChain` with `ServerHttpSecurity` | `RouterFunctions.route().filter(...)` or `RouterFunction.filter(...)` |

Example of a functional filter:

```java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
    .GET("/api/functional/hello",
        req -> ServerResponse.ok().bodyValue("Hello from RouterFunction"))
    .filter((request, next) -> {
        // Applies only within this RouterFunction.
        return next.handle(request);
    })
    .build();
```

This is an **illustrative snippet inside a configuration method**, not a complete class. `next.handle(request)` invokes the next handler. If you omit that call and return a response immediately, the handler will not run. Even if you add a filter here, annotated controllers do not receive that filter. For shared authentication and authorization, you must still use Spring Security `WebFilter` chains.

**Similarly:** `@ControllerAdvice`, MVC `HandlerInterceptor`, and Servlet `Filter` do not replace WebFlux's `SecurityWebFilterChain`.

## 8. Matchers: Common Causes of an Endpoint Not Being Protected as Expected

### 8.1 Security Matchers Select the Chain, Authorization Matchers Select Rules

In the **single-chain** configuration in section 4, there is no restricting `securityMatcher`, so all requests enter the same chain and are then evaluated by `authorizeExchange`.

When splitting into multiple chains, for example:

```java
.securityMatcher(
    new PathPatternParserServerWebExchangeMatcher("/api/**"))
.authorizeExchange(exchanges -> exchanges
    .anyExchange().authenticated())
```

This is a **snippet inside chain construction** requiring `PathPatternParserServerWebExchangeMatcher` imported. It causes the chain to **evaluate only requests with path `/api/**`**. After the chain matches, `anyExchange()` inside that chain evaluates the request. These two matcher layers are distinct.

If you mistakenly write the matcher as `/api/annotated/**`, the functional route `/api/functional/hello` will **not enter that chain**, even though the functional handler still exists. Without another matching chain, requests may bypass the Spring Security policy you intended to enforce. **Do not rely on `anyExchange().denyAll()` inside a chain matching only annotated paths to protect functional paths outside that chain.**

### 8.2 Multiple Chains Are Selected in Order

If you need to secure Bearer-token APIs differently from browser sessions, you can have multiple `SecurityWebFilterChain` beans, usually with `@Order` to establish chain priority:

```text
@Order(1) apiChain:   securityMatcher("/api/**")
@Order(2) webChain:   securityMatcher(any request)
```

This is a **conceptual diagram**, not compilable Java. Spring Security evaluates chains in order and selects **the single first matching chain** for the request. It does not combine authorization policies across all chains. Both Controllers and RouterFunctions under `/api/**` still enter **the same apiChain**; handler style does not alter the chain-selection algorithm.

**Important:** a request matching a chain's path but not matching an inner rule may receive unexpected results depending on `anyExchange`. Best practice is declaring complete rules, placing specific rules before broad ones, and providing a safe catch-all rule.

### 8.3 HTTP Method Also Matters

`pathMatchers(HttpMethod.GET, "/api/**")` applies to GET; POST or DELETE do not automatically inherit role READER from that rule. In the example, `anyExchange().denyAll()` denies remaining methods per authorization policy, and for unsafe methods the CSRF filter may also block earlier. Having a `GET` RouterFunction does not grant `POST` access.

Also check factors that easily break matchers: reverse-proxy prefixes, `spring.webflux.base-path`, gateway path rewrites, trailing slashes, path variables, and HTTP methods. Verify the URL actually arriving at the server rather than looking only at the client-side path.

## 9. SecurityContext, Method Security, and Shared Business Authorization

Once HTTP Basic (or JWT/OIDC/session) is processed in a WebFilter, the authenticated identity travels in the reactive context. Controllers and HandlerFunctions can share service beans that enforce permissions. In WebFlux, read authentication via `ReactiveSecurityContextHolder` rather than assuming Servlet-style ThreadLocal.

Example reactive method in a service bean:

```java
public Mono<String> currentUsername() {
    return org.springframework.security.core.context.ReactiveSecurityContextHolder
        .getContext()
        .map(context -> context.getAuthentication().getName())
        .defaultIfEmpty("anonymous");
}
```

The snippet above is an **illustrative method inside a class/service**, not a standalone application. When executed inside an authenticated request pipeline, it returns the principal name. Do not call `block()` on the event loop or `subscribe()` outside the pipeline, which loses context attachment and lifecycle control.

You can enable `@EnableReactiveMethodSecurity` and use `@PreAuthorize` on **Spring bean methods** to strengthen authorization in shared services. A lambda inside a RouterFunction does not automatically become a `@PreAuthorize`-proxied method merely by living in a router. Global HTTP authorization is still needed to inspect requests before reaching handlers; the business layer still needs ownership/tenant/record-level permission checks per resource. A shared `hasRole("READER")` path rule does not guarantee a user may read **every** record in the system.

For a JWT Resource Server, replace `httpBasic(...)` with `oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))` and configure valid issuer/audience; check scopes with `hasAuthority("SCOPE_read")` (if the JWT scope maps to that authority). That changes **how authentication works**, while the principle of **one HTTP WebFilter chain for both Controller and RouterFunction** remains unchanged. Never assign roles to a token yourself if claims/authority mapping does not back them.

## 10. CSRF, CORS, and Easily Overlooked Security Gaps

**CSRF:** In WebFlux, CSRF protection operates in the security WebFilter chain and can affect both annotated and functional endpoints. The GET-only example does not need to send CSRF tokens. If adding form/cookie sessions and state-changing endpoints, keep CSRF protection enabled and supply valid CSRF tokens. For Bearer-only APIs not using auto-attached cookies, you may consider disabling CSRF for the **appropriate API scope**, rather than disabling it application-wide by habit.

**CORS:** CORS is a browser cross-origin policy and does not replace authentication, authorization, or CSRF. Controllers can use `@CrossOrigin`, but that annotation does not automatically cover RouterFunctions. For a unified CORS policy, use WebFlux/CorsWebFilter configuration or Spring Security-compatible configuration for the relevant paths. Test `OPTIONS` preflight requests when an API has clients on another origin; a rule allowing only GET does not automatically satisfy browser preflights.

**Error handling:** When Spring Security blocks a request before the handler, controller exception handlers or functional error handlers do not necessarily receive that error. Use security exception handling/entry points/access denied handlers at the proper layer when customizing 401/403. Do not assume handler logging will always execute for security-blocked requests.

**Observability:** Logs in Spring Security and the HTTP server must scrub `Authorization` headers and credentials. Use trace IDs and route/status for tracking; testing 401/403/200 on both handler types matters more than seeing a log line saying "route registered".

## 11. Practice Exercise for Catching Misconfigurations

Make **one change at a time**, re-run `SharedSecurityChainTest`, and explain why tests pass or fail:

1. **Change `/api/**` to `/api/annotated/**`** in the authorization rule while keeping `anyExchange().denyAll()`: the controller succeeds for role READER, while functional GET is denied because it does not match the permitted GET rule. Fix with a matcher covering both paths.
2. **Change `hasRole("READER")` to `hasRole("ADMIN")`**: neither endpoint is open to reader anymore; the 200 tests for reader must fail together. This confirms the shared rule.
3. **Move `anyExchange().denyAll()` before `pathMatchers`**: the broad rule wins first, and specific rules no longer take effect as intended; fix the ordering.
4. **Add a `HandlerFilterFunction` to the RouterFunction** without changing `SecurityConfig`: the annotated controller does not run the functional filter, while Spring Security's policy for both remains unchanged.
5. **Switch HTTP Basic to JWT** with valid test client/token: both endpoints remain protected by the same path matcher; only authentication and authority mapping change.
6. **Use `@WebFluxTest(GreetingController.class)` without importing RouterFunction/SecurityConfig**: test slices do not necessarily include functional routes or custom chains. Use full-context tests when verifying shared behavior.

Do not mistake test failures caused by wrong dependencies/context for business permission bugs; if the MVC starter is present, first verify Boot is actually running `REACTIVE`.

## 12. Checklist for Real-World Projects

- [ ] Server actually runs **Spring WebFlux**, not accidentally switched to MVC by dependencies.
- [ ] Annotated Controller and `RouterFunction` live in the same HTTP WebFlux application context.
- [ ] There is a `SecurityWebFilterChain` matching **both** URL sets, or when using multiple chains, `securityMatcher` and `@Order` cover them properly.
- [ ] `authorizeExchange` checks HTTP method, path, and authority accurately; the catch-all rule is fail-safe.
- [ ] Authentication (HTTP Basic, OIDC login, JWT, session) is configured in the WebFilter chain rather than inside just one handler style.
- [ ] Tests verify **401 when unauthenticated**, **403 when lacking permissions**, and **200 when authorized** for each endpoint type.
- [ ] Functional `HandlerFilterFunction` is used only for appropriate local logic, not to replace Controller protection.
- [ ] CSRF, CORS, error handling, security headers, and resource-level authorization are reviewed for actual client/credential types.
- [ ] Tests run against the full application context to avoid missing route beans or security configs in test slices.

**Conclusion:** In Spring Security reactive, the layer that decides HTTP security is **`WebFilter` and `SecurityWebFilterChain`**, not annotations or route-definition style. When a Controller and a RouterFunction run under the same WebFlux HTTP server, a `SecurityWebFilterChain` bean not overly narrowed by matchers applies consistently to both. Prove it with 401/403/200 assertions on **every endpoint**.

### Official References

- [Spring Security — WebFlux Security: Shared WebFilter for WebFlux and WebFlux.fn, Multiple Chains](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security — Reactive HTTP requests / authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html)
- [Spring Framework — WebFlux functional endpoints, RouterFunctionMapping and HandlerFilterFunction](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html)
- [Spring Framework — WebFlux DispatcherHandler and HandlerMapping](https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html)
- [Spring Boot 3.3 — Testing Spring Boot Applications, WebTestClient and WebFluxTest](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html)
- [Spring Security — Reactive test support](https://docs.spring.io/spring-security/reference/reactive/test/index.html)
