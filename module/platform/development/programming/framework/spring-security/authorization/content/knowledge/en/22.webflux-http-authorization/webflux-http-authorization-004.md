# SecurityWebExchangeMatcher and Filter Chain Selection in Spring Security WebFlux

## 1. Context: a WebFlux application with multiple security zones

In a **Spring WebFlux** application, the same server can expose multiple kinds of HTTP endpoints:

- `/api/**`: REST APIs accepting Bearer JWTs.
- `/api/admin/**`: administrative APIs requiring a special authority.
- `/ui/**`: an internal UI or API for clients using HTTP Basic authentication.
- `/actuator/**`: health/metrics endpoints with their own access rules.
- Remaining paths: must be denied by default instead of accidentally left open.

The issue is not merely whether an endpoint requires READ or WRITE permission. Each zone may need **a different WebFilter chain**, using different authentication mechanisms, sessions, CSRF, exception handling, and header policies.

Spring Security Reactive lets you register multiple `SecurityWebFilterChain` beans; a dispatcher evaluates them in order and selects the **first chain matching** the incoming `ServerWebExchange`. Inside each selected chain, authorization rules then decide whether a specific request requires `permitAll`, `authenticated`, `hasRole`, `hasAuthority`, or `denyAll`.

**API name distinction:** the title contains the phrase "SecurityWebExchangeMatcher". In Spring Security WebFlux's codebase, the official matcher interface is **`ServerWebExchangeMatcher`**, not a separate interface named `SecurityWebExchangeMatcher`. The chain type is **`SecurityWebFilterChain`**. Always search for and import these exact names when working with the Java API.

Learning objectives:

1. Understand the roles of `ServerWebExchangeMatcher` and `SecurityWebFilterChain`.
2. Distinguish **chain selection** from **authorization rule selection inside a chain**.
3. Master the **first matching chain wins** principle, `@Order`, and fallbacks.
4. Configure multiple chains using JWT/HTTP Basic without leaking routes.
5. Use `PathPatternParserServerWebExchangeMatcher`, `ServerWebExchangeMatchers`, and composite matchers.
6. Know how to test with `WebTestClient` and detect shadowed or missed chains.
7. Avoid confusing WebFlux architecture with Servlet, as well as avoiding blocking matchers in the reactive stack.

## 2. Which APIs differ between WebFlux and Servlet?

| Purpose | Servlet stack | Reactive WebFlux |
| --- | --- | --- |
| Request context | `HttpServletRequest` | `ServerWebExchange` |
| HTTP config API | `HttpSecurity` | `ServerHttpSecurity` |
| Security filter | Servlet `Filter` | WebFlux `WebFilter` |
| Chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Matcher | `RequestMatcher` | **`ServerWebExchangeMatcher`** |
| Chain coordinator | `FilterChainProxy` | `WebFilterChainProxy` |
| Authorization DSL | `authorizeHttpRequests(...)` | `authorizeExchange(...)` |
| Rule-level path matching | `requestMatchers(...)` | `pathMatchers(...)`/`matchers(...)` |
| HTTP test client | `MockMvc` | `WebTestClient` |
| Principal in reactive pipeline | Servlet context/thread strategy | Reactive SecurityContext attached to Reactor Context |

Do not copy `AntPathRequestMatcher`, `RequestAuthorizationContext`, or Servlet `SecurityFilterChain` directly into a WebFlux app expecting it to behave like `ServerWebExchangeMatcher`. In a project that has both MVC and WebFlux dependencies, verify **which web application type is actually running**, because Spring Boot has rules for choosing the web application type; importing the right class names does not guarantee the reactive server is running.

In WebFlux, matching and authentication operations may rely on **`Mono`**, because the pipeline is asynchronous. Avoid blocking the event loop with `block()`, blocking JDBC, synchronous file I/O, or blocking HTTP calls inside a custom matcher.

## 3. How does SecurityWebFilterChain work?

`SecurityWebFilterChain` is a contract with two key concepts:

```java
Mono<Boolean> matches(ServerWebExchange exchange);
Flux<WebFilter> getWebFilters();
```

These are **illustrative interface signatures** (Reactor/Spring imports are needed and details vary by version); Spring Security builds chains via `ServerHttpSecurity`, so most applications do not implement this interface directly.

`WebFilterChainProxy` receives the registered `SecurityWebFilterChain` beans in order and executes the following conceptual logic:

```text
HTTP request: GET /api/documents/42
           |
           v
WebFilterChainProxy
           |
           +--> Chain 1 matcher ?  NO
           |
           +--> Chain 2 matcher ?  YES
           |              |
           |              +--> select CHAIN 2
           |              +--> run CHAIN 2 WebFilters
           |              +--> inside the chain, evaluate authorization rules
           |
           +--> Chain 3? NOT evaluated further
```

**First match wins:** A request does not execute sequentially across *all* `SecurityWebFilterChain`s. Selecting a chain is different from invoking multiple authorization managers inside the same chain.

Once a chain matches, if an inner rule returns DENY or authentication fails, Spring Security **does not fall through to the next chain to find a more lenient rule**. This keeps chain behavior predictable and also means an overly broad chain at high priority will easily "swallow" every chain behind it.

In a multi-chain configuration, **`@Order`** on the bean determines evaluation order: lower numbers are evaluated first. Place specialized chains before general chains.

## 4. What is ServerWebExchangeMatcher?

The interface `org.springframework.security.web.server.util.matcher.ServerWebExchangeMatcher` has the method:

```java
Mono<ServerWebExchangeMatcher.MatchResult> matches(
    ServerWebExchange exchange
);
```

**Key differences to remember:**

- `ServerWebExchangeMatcher.matches(...)` returns `Mono<MatchResult>`.
- `SecurityWebFilterChain.matches(...)` returns `Mono<Boolean>`.
- `MatchResult` exposes `isMatch()` and `getVariables()`, which can contain extracted path variables.
- A matcher determines **whether a request matches a condition**, not whether a user is authorized to access a resource.
- A matcher can inspect HTTP method, path, content type, and other properties depending on the implementation.

Common factories and implementations:

| Type | Purpose |
| --- | --- |
| `PathPatternParserServerWebExchangeMatcher` | Matches path patterns using Spring `PathPattern` |
| `ServerWebExchangeMatchers.pathMatchers(...)` | Factory matching one or more paths, with HTTP method overloads |
| `ServerWebExchangeMatchers.anyExchange()` | Matches every request |
| `ServerWebExchangeMatchers.matchers(...)` | Combines with OR, matching if any child matcher matches |
| `AndServerWebExchangeMatcher` | Combines with AND: every child matcher must match |
| `OrServerWebExchangeMatcher` | Combines with OR: only one child matcher needs to match |
| `NegatedServerWebExchangeMatcher` | Negates a matcher |
| `MediaTypeServerWebExchangeMatcher` | Matches by media type per specific API/configuration |
| `IpAddressServerWebExchangeMatcher` | Matches by IP address/subnet; must account for proxy trust |

Matchers are purely **route selection** tools. If a dedicated chain targets `/api/admin/**`, that chain must still configure appropriate authentication and authorities. Nothing automatically infers an ADMIN role from the path name.

### Path matching factory

```java
import org.springframework.http.HttpMethod;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatcher;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

ServerWebExchangeMatcher allApi =
    ServerWebExchangeMatchers.pathMatchers("/api/**");

ServerWebExchangeMatcher onlyApiPost =
    ServerWebExchangeMatchers.pathMatchers(
        HttpMethod.POST, "/api/**");
```

This is a **fragment** inside a Spring Security Reactive application, not runnable standalone with plain `javac`. The first matcher places no restriction on HTTP method; the second matches only POST within that path scope. When the second matcher is assigned to an **entire chain**, GET and OPTIONS will not enter that chain.

### PathPatternParserServerWebExchangeMatcher

```java
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

var apiMatcher =
    new PathPatternParserServerWebExchangeMatcher("/api/**");
```

Spring WebFlux uses the `PathPattern` system; do not carry over every `AntPathMatcher` assumption from legacy Servlet code. Test real path variations, context paths, trailing slashes, encoding, letter casing, and paths routed through a reverse proxy. Simply reading `"/api/**"` without testing does not prove full endpoint coverage.

## 5. Two matcher tiers: chain-level and authorization rule-level

This is the most important distinction in this guide:

| Tier | API | Question |
| --- | --- | --- |
| **Chain selection** | `http.securityMatcher(matcher)` | Does this security configuration chain apply to the request? |
| **Rules inside the chain** | `http.authorizeExchange(ex -> ex.pathMatchers(...))` | What permissions does a request entering this chain require? |

Example:

```java
http
    .securityMatcher(
        new PathPatternParserServerWebExchangeMatcher("/api/**")
    )
    .authorizeExchange(exchanges -> exchanges
        .pathMatchers("/api/public/**").permitAll()
        .pathMatchers("/api/admin/**").hasAuthority("SCOPE_admin")
        .anyExchange().authenticated()
    );
```

Meaning:

1. This chain is **evaluated successfully only** for requests matching `/api/**`.
2. Within that chain, `/api/public/**` is permitted unless other mechanisms block it.
3. `/api/admin/**` requires authority `SCOPE_admin`.
4. All other API paths require authentication.
5. `/dashboard` is **unaffected** by `anyExchange().authenticated()` in this chain, because the chain-level matcher did not select it.

A critical mistake:

```java
http
    .securityMatcher(
        new PathPatternParserServerWebExchangeMatcher("/api/**")
    )
    .authorizeExchange(ex -> ex
        .anyExchange().authenticated()
    );
```

If this is the only chain and the app exposes `/admin` outside `/api/**`, requests to `/admin` **may pass through without any Spring Security WebFilter chain**. They are not automatically blocked by `authenticated()`. Therefore, you need a **fallback chain** matching every request, or a design covering all protected routes.

### Rule-level `permitAll` is not the same as bypassing security filters

`permitAll()` means the authorization rule allows the request at that step. It **does not skip the chain**, and does not disable CSRF, authentication filters, CORS, security headers, or exception handling.

For example, if `GET /api/public/info` is `permitAll` in a JWT-enabled chain: a request with no `Authorization` header can proceed, yet a request carrying an **invalid Bearer token** can still be rejected by the authentication filter according to resource server behavior. Never assume `permitAll` bypasses all filters.

Conversely, **no chain matching** means that chain's security filters never participate in the request. That is why you must explicitly check for matcher "coverage gaps."

## 6. `@Order`: specialized chains must come before general chains

Consider two chains:

- `admin`: `/api/admin/**`, requiring a dedicated admin policy.
- `api`: `/api/**`, requiring JWT authentication for normal APIs.

If `api` comes first, `GET /api/admin/users` matches `/api/**` and stops at the API chain. The admin chain is **never evaluated**, regardless of how strict its role requirements are.

**Wrong:**

```text
@Order(1) apiChain   -> /api/**       authenticated()
@Order(2) adminChain -> /api/admin/** hasRole("ADMIN")
GET /api/admin/users -> enters apiChain, adminChain is shadowed
```

**Right direction:**

```text
@Order(1) adminChain -> /api/admin/** admin policy
@Order(2) apiChain   -> /api/**       normal API policy
@Order(99) fallback  -> all requests  denyAll()
```

You do not necessarily need a separate admin chain if it uses the **same authentication mechanism** as the rest of the API. In that case, one API chain with `pathMatchers("/api/admin/**").hasRole("ADMIN")` before `anyExchange().authenticated()` is usually simpler. Use multiple chains when you genuinely need separate **WebFilter stacks/authentication mechanisms** or distinct HTTP settings, not just one bean per URL.

### `@Order` is not `SecurityWebFiltersOrder`

`@Order` on a `SecurityWebFilterChain` controls **which chain is evaluated first**.

`SecurityWebFiltersOrder` is used with `http.addFilterAt/addFilterBefore/addFilterAfter` to control the position of a **WebFilter inside the selected chain**.

These are two independent ordering axes. Inserting a custom WebFilter at an "early" position does not cause its enclosing chain to be selected ahead of other chains.

## 7. Practical configuration: JWT API, HTTP Basic UI, and DENY fallback

The following example is written for a **Spring Boot WebFlux + Spring Security** application using Java 17+. It is an **application configuration class** that compiles when compatible dependencies are declared; running a real server also requires endpoints, JWT decoder/issuer configuration, a Basic user store, and related infrastructure.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Configuration
@EnableWebFluxSecurity
public class ReactiveSecurityChainsConfig {

    // Requests to /api/** use Bearer JWT.
    @Bean
    @Order(1)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/**")
            )
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(
                    HttpMethod.GET, "/api/public/info"
                ).permitAll()
                .pathMatchers("/api/admin/**")
                    .hasAuthority("SCOPE_admin")
                .anyExchange().authenticated()
            )
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            // Suitable only for APIs genuinely using Bearer tokens and not using
            // browser cookies/sessions as an authentication source.
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            )
            .build();
    }

    // Internal UI uses HTTP Basic for demonstration purposes.
    @Bean
    @Order(2)
    SecurityWebFilterChain uiChain(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/ui/**")
            )
            .authorizeExchange(exchanges -> exchanges
                .anyExchange().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    // Do not let any URL fall outside Spring Security.
    @Bean
    @Order(99)
    SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .anyExchange().denyAll()
            )
            .build();
    }
}
```

**Essential notes when using this example:**

1. `@EnableWebFluxSecurity` applies to the WebFlux stack. If the app uses Spring MVC, this is not a substitute for `@EnableWebSecurity`.
2. `@Order(1)`, `@Order(2)`, and `@Order(99)` establish an explicit order independent of bean registration order.
3. The API chain's `securityMatcher` matches all HTTP methods under `/api/**`. `authorizeExchange` then enforces specific permissions.
4. `hasAuthority("SCOPE_admin")` assumes the JWT authority converter maps scope `admin` to `SCOPE_admin` per configuration. If the converter differs, update the authority accordingly rather than granting roles arbitrarily.
5. `httpBasic(...)` on the UI chain needs an appropriate `ReactiveUserDetailsService` or `ReactiveAuthenticationManager`. Never hardcode plaintext passwords in production.
6. `oauth2ResourceServer(...jwt(...))` requires a decoder and reliable issuer/audience/token verification settings. Without them, startup may fail or JWTs may not validate as expected.
7. `csrf(disable)` on the API chain is valid only when endpoints **do not rely on browser-auto-sent cookie credentials**; if cookies/sessions or mixed-mode flows exist, evaluate CSRF instead of copying this blindly.
8. The fallback chain with `denyAll()` is how you **block requests outside API/UI**. If a public endpoint like health is needed, add an intentional narrow rule in the fallback or a tested dedicated chain—never delete the fallback.
9. A request to `/api/admin/users` uses **apiChain** and is checked for `SCOPE_admin`. This example has no separate admin chain because JWT authentication is uniform across the API.
10. If Spring Boot Management/Actuator runs on a **separate management port or context**, inspect that context's security configuration; do not infer it solely from the main application context chains.

### Routing table for the configuration above

| Request | Selected chain | Authorization rule |
| --- | --- | --- |
| `GET /api/public/info` | apiChain | permitAll |
| `POST /api/public/info` | apiChain | authenticated (GET-only public rule does not match) |
| `GET /api/documents/42` | apiChain | authenticated |
| `POST /api/admin/users` | apiChain | `SCOPE_admin` |
| `GET /ui/home` | uiChain | authenticated via configured Basic auth |
| `GET /random` | fallbackChain | denyAll |
| `OPTIONS /api/documents` | apiChain | Selected by path; CORS/preflight depends on configuration |
| `GET /actuator/health` | fallbackChain if in same app context | denyAll unless explicitly exempted |

This table describes chain selection and rules, **not a guarantee of a single status code**: authentication entry points, CORS, CSRF, resource existence, exception handling, and request headers also shape the HTTP result. If an endpoint has no controller, it can still return 404 after passing authorization.

## 8. If you need a separate admin chain

Split `/api/admin/**` into its own chain only when it truly needs distinct security mechanisms or header policies. Example illustrating the general ordering rule:

```java
@Bean
@Order(1)
SecurityWebFilterChain adminChain(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher(
                "/api/admin/**"
            )
        )
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().hasAuthority("SCOPE_admin")
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
        )
        .build();
}

@Bean
@Order(2)
SecurityWebFilterChain ordinaryApiChain(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/**")
        )
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
        )
        .build();
}
```

These are **two sample beans replacing `apiChain` from the previous section**, not snippets to drop alongside the existing `apiChain` bean. Copying all three creates overlapping chains with confusing behavior. Add imports, JWT config, and a fallback chain as needed.

**Crucial boundary:** each chain must configure all security features it requires. The admin chain does not automatically "inherit" JWT, CSRF, or exception handling from a lower-priority API chain just because their paths overlap. The first matching chain **owns the entire request**.

## 9. When to use one chain instead of multiple chains

A single chain is usually easier to audit when the entire application shares the **same authentication mechanism** and differs only in permissions:

```java
@Bean
SecurityWebFilterChain oneChain(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/public/**").permitAll()
            .pathMatchers("/api/admin/**").hasRole("ADMIN")
            .pathMatchers(HttpMethod.GET, "/api/**")
                .hasAuthority("SCOPE_read")
            .pathMatchers(HttpMethod.POST, "/api/**")
                .hasAuthority("SCOPE_write")
            .anyExchange().denyAll()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
        )
        .build();
}
```

This is an **alternative** (requiring imports, a JWT decoder, and endpoints), not an add-on to the three-chain example above.

**Scope distinctions:**

- `anyExchange().denyAll()` in a match-all chain protects every request that matched no earlier rule.
- `anyExchange().denyAll()` in a chain matching only `/api/**` protects only the **unmatched portion of the API**. Other URLs need another chain.
- `pathMatchers(...).permitAll()` opens only the matched pattern, not the whole chain.
- Do not split chains per role: authorization rules inside one chain are already evaluated **in declaration order**.

Multiple chains make sense when:

- A Bearer-only API needs a different CSRF strategy from a cookie-based UI.
- One area uses form login while another uses OAuth2 Resource Server.
- One area requires different exception handling or security headers.
- Management endpoints use an independent security mechanism.
- Certain routes need a different security context repository (be careful with stateless vs stateful).
- You need to reduce matcher complexity inside an overly large chain.

If everything differs only by `READ/WRITE/ADMIN`, a single chain with carefully ordered rules is usually less error-prone.

## 10. Rule ordering inside `authorizeExchange`

There are **two kinds of ordering**:

**Tier 1 – across SecurityWebFilterChains:** controlled by `@Order` and `securityMatcher(...)`.

**Tier 2 – inside the selected chain:** `authorizeExchange` evaluates matchers/rules in registration order.

Example:

```java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/**").authenticated()
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .anyExchange().denyAll()
)
```

Because the broad `/api/**` rule comes first, `/api/admin/**` requests match the first rule; the specialized ADMIN rule below is **not applied** as intended.

Correct:

```java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .pathMatchers("/api/**").authenticated()
    .anyExchange().denyAll()
)
```

**Specific before general** applies at both tiers, yet they are **two separate configurations** and must not be conflated.

### A 403 response does not cause the next chain to be tried

Suppose the first chain matches `/api/admin/**` and denies a request because the user lacks the role. Spring Security does not proceed to try a second chain matching `/api/**` to let the user through with `authenticated()`. If it did, policies would be trivial to bypass. First-match chain selection prevents a fallback from relaxing access once a chain has been chosen.

## 11. Path, HTTP method, context path, and reverse proxy

Many bugs appear only when running behind an API gateway or reverse proxy:

```text
Client:   https://example.test/service-a/api/documents/42
Proxy:    strip prefix /service-a
Backend:  /api/documents/42
```

WebFlux's `/api/**` matcher works on the backend if the proxy stripped the prefix. However, if the proxy preserves the prefix and the app sees a different path, the chain may not match as expected.

Always test **the path WebFlux actually observes**, not just the URL shown in the browser. If the app configures a custom context path or base-path, verify path pattern behavior with tests.

### Cases to test

| Scenario | Risk |
| --- | --- |
| `/api` and `/api/` | Pattern `/api/**` may not behave identically in all cases; test it |
| `/api/admin` and `/api/admin/` | Do not rely on intuition regarding trailing slashes |
| Encoded slash / percent encoding | Proxy and backend may normalize differently |
| Case variation | `/API` vs `/api` |
| Double slashes and dot-segments | Path normalization differences across tiers |
| HTTP `HEAD` | Does the GET rule apply? Test independently |
| `OPTIONS` preflight | Which chain is selected, and does auth/CSRF block before CORS? |
| WebSocket upgrade | Is the HTTP handshake protected, and do frames have their own policy? |
| Gateway URL rewrites | Public route inadvertently becomes protected or vice versa |
| Separate management port | App chains do not automatically cover the management context |

Avoid hand-rolled `path.startsWith("/api")` checks for security routing when segment boundaries matter. Without segment-boundary checks, it also matches `/apix` and `/api-admin`. Use Spring `PathPattern` or tested matchers.

### A path variable is not authorization

A matcher like `"/api/users/{userId}"` can extract `userId`, but matching the path **does not prove** the logged-in user is that `userId`. Policies must still verify subject/resource/tenant and business permissions from trusted sources.

## 12. HTTP-method matchers: benefits and traps

`ServerWebExchangeMatchers.pathMatchers(HttpMethod.POST, "/api/**")` works if you truly want a chain exclusively for POST. However, it leaves GET/PUT/PATCH/DELETE/HEAD/OPTIONS outside that chain.

**Dangerous example if a fallback is missing:**

```java
@Bean
SecurityWebFilterChain postOnly(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            ServerWebExchangeMatchers.pathMatchers(
                HttpMethod.POST, "/api/**"
            )
        )
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().authenticated()
        )
        .build();
}
```

If this is the only chain, `GET /api/private` does not match. It is left unprotected by this chain. In most cases, it is safer to match `/api/**` at the **chain level** and differentiate HTTP methods **inside `authorizeExchange`**.

Example:

```java
http
    .securityMatcher(
        ServerWebExchangeMatchers.pathMatchers("/api/**")
    )
    .authorizeExchange(exchanges -> exchanges
        .pathMatchers(HttpMethod.GET, "/api/public/**").permitAll()
        .pathMatchers(HttpMethod.POST, "/api/**")
            .hasAuthority("SCOPE_write")
        .pathMatchers(HttpMethod.GET, "/api/**")
            .hasAuthority("SCOPE_read")
        .anyExchange().denyAll()
    );
```

PUT or DELETE requests are not accidentally treated like GET or POST. `anyExchange().denyAll()` makes the behavior for unconfigured methods explicit.

## 13. CORS, CSRF, and authentication are not the same problem

### 13.1. CORS preflight is usually OPTIONS

A browser sends:

```http
OPTIONS /api/documents/42
Origin: https://app.example.test
Access-Control-Request-Method: PUT
Access-Control-Request-Headers: authorization,content-type
```

Preflight requests often **lack a Bearer token**. If the API chain matches **only POST/GET** at the chain level or defaults to requiring authentication for every OPTIONS request, CORS can break even when a non-browser HTTP client is authorized for PUT.

Proper approach:

- The chain-level path matcher should cover `OPTIONS` for the API area.
- Configure CORS with explicit **allowed origins, methods, and headers** in server/WebFlux/Spring Security.
- Check preflight handling order; do not solve it by calling `permitAll()` on all routes or all origins.
- Test both valid preflights and disallowed origins or headers.
- Never treat browser CORS as authorization protection: non-browser clients are not constrained by CORS like browsers are.

### 13.2. Do not disable CSRF recklessly

For a stateless API accepting only Bearer tokens in `Authorization` without auto-sent cookies, you may consider disabling CSRF on **that specific API chain**. Yet if a WebFlux UI uses cookies/sessions or automatic browser credentials, CSRF remains an essential defense for state changes.

Do not disable CSRF server-wide merely because `/api/**` is an API. Switching chains can alter CSRF filters; if a path enters the wrong chain, you change both authentication and CSRF behavior.

### 13.3. 401, 403, and 404 do not re-select a chain

- **401** usually means unauthenticated or invalid credentials per the entry point.
- **403** usually means authenticated but lacking permission (or certain CSRF failures).
- **404** may simply mean no handler/resource exists; it does not prove a chain protects the endpoint properly.

Not seeing 401 in a test does not prove authentication is disabled: inspect whether the endpoint exists, which chain was selected, and what status the error handler returned.

## 14. Composite matchers: AND, OR, NOT

When one chain applies to multiple equivalent regions:

```java
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatcher;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

ServerWebExchangeMatcher protectedAreas =
    ServerWebExchangeMatchers.matchers(
        ServerWebExchangeMatchers.pathMatchers("/api/**"),
        ServerWebExchangeMatchers.pathMatchers("/internal/**")
    );
```

The `matchers(...)` factory in the docs builds an **OR** matcher: matching any region suffices.

Equivalent using the class directly:

```java
import org.springframework.security.web.server.util.matcher.OrServerWebExchangeMatcher;

ServerWebExchangeMatcher protectedAreas =
    new OrServerWebExchangeMatcher(
        ServerWebExchangeMatchers.pathMatchers("/api/**"),
        ServerWebExchangeMatchers.pathMatchers("/internal/**")
    );
```

This is a **separate replacement fragment** for the one above; do not declare two `protectedAreas` variables in the same scope. Use `OrServerWebExchangeMatcher` for multiple **managed and tested** paths.

Combining with AND:

```java
import org.springframework.http.HttpMethod;
import org.springframework.security.web.server.util.matcher.AndServerWebExchangeMatcher;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatcher;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

ServerWebExchangeMatcher onlyPostApi =
    new AndServerWebExchangeMatcher(
        ServerWebExchangeMatchers.pathMatchers("/api/**"),
        ServerWebExchangeMatchers.pathMatchers(
            HttpMethod.POST, "/api/**"
        )
    );
```

Here AND is slightly redundant (the second matcher already restricts both method and path) and only illustrates that **all** conditions must match. In real code, use a single method+path matcher for simple cases.

Negation:

```java
import org.springframework.security.web.server.util.matcher.NegatedServerWebExchangeMatcher;

ServerWebExchangeMatcher notApi =
    new NegatedServerWebExchangeMatcher(
        ServerWebExchangeMatchers.pathMatchers("/api/**")
    );
```

**Warning:** negating a region can produce a **very broad** scope that includes unknown new endpoints. If `notApi` is used for a public chain, you can accidentally expose sensitive routes. Every broad NOT/OR matcher must be paired with `denyAll`/guardrails and negative tests.

## 15. Custom `ServerWebExchangeMatcher`: when and how to write one

You can implement `ServerWebExchangeMatcher` when you need a chain-selection condition that no built-in factory covers.

Example matcher applying only to **GET on `/reports/**`**:

```java
import org.springframework.http.HttpMethod;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatcher;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;
import reactor.core.publisher.Mono;

ServerWebExchangeMatcher reportsGet =
    ServerWebExchangeMatchers.pathMatchers(
        HttpMethod.GET, "/reports/**");
```

This case **needs no custom matcher**. Built-in factories are usually easier to review.

When custom logic is needed, the interface requires returning `Mono<MatchResult>`:

```java
import org.springframework.http.HttpMethod;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatcher;

ServerWebExchangeMatcher healthGet = exchange -> {
    boolean allowedPath =
        "/health".equals(
            exchange.getRequest().getPath().pathWithinApplication().value());
    boolean isGet =
        HttpMethod.GET.equals(exchange.getRequest().getMethod());

    return allowedPath && isGet
        ? ServerWebExchangeMatcher.MatchResult.match()
        : ServerWebExchangeMatcher.MatchResult.notMatch();
};
```

This is a **WebFlux fragment**, requiring an application/context and corresponding imports. It inspects simple synchronous request metadata and returns a known `Mono` without calling `block()`. For complex paths, prefer `PathPatternParserServerWebExchangeMatcher` over string equality.

### Never trust client-supplied request headers as a trust anchor

For example, a matcher that treats `X-Internal-Request: true` as proof that a request came from an internal system lets an attacker select a less-protected chain simply by sending that header.

To distinguish internal vs public traffic, use a reliable trust boundary: a gateway enforcing mTLS/service identity, network controls, token audience, certificate verification, or combined checks; keep in mind **chain selection happens before some authentication steps**, so do not assume an authenticated principal already exists there.

**Principle:** a matcher selects **how a request is routed through chains**, and can never replace authentication and authorization on real resources.

### Avoid blocking inside matchers

Do not write:

```java
ServerWebExchangeMatcher badMatcher = exchange -> {
    // Anti-pattern: blocking database query directly on the event loop.
    boolean enabled = jdbcRepository.checkSomePolicy();
    return enabled
        ? ServerWebExchangeMatcher.MatchResult.match()
        : ServerWebExchangeMatcher.MatchResult.notMatch();
};
```

This is an illustrative **anti-pattern**, not code to use. Matchers must also be lightweight, side-effect-free, and never arbitrarily read/consume the request body. If you genuinely need I/O data to choose a chain, consider whether you can avoid splitting chains and move the decision into a `ReactiveAuthorizationManager` inside the chain; if unavoidable, use non-blocking reactive data access with explicit timeouts and failure handling rather than `block()`.

## 16. Do not confuse matchers with `ReactiveAuthorizationManager`

In WebFlux, custom rules in `authorizeExchange(...).access(...)` use reactive authorization. Example checking object permission for a principal:

```java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/documents/{documentId}")
        .access((authenticationMono, context) ->
            authenticationMono
                .flatMap(auth -> documentPolicy
                    .canRead(auth,
                        context.getVariables().get("documentId"))
                )
                .map(
                    org.springframework.security.authorization.AuthorizationDecision::new
                )
                .defaultIfEmpty(
                    new org.springframework.security.authorization.AuthorizationDecision(false)
                )
        )
    .anyExchange().denyAll()
)
```

This is **fragment-level configuration pseudocode**, assuming `documentPolicy.canRead(auth, id)` returns `Mono<Boolean>` and reads resource/tenant/owner data from a trusted source. `documentPolicy` is not a built-in standard method. Reactive authorization interfaces/return types may evolve across newer Spring Security versions; verify against Javadoc and compile a real project.

Key distinctions:

- `ServerWebExchangeMatcher`: "Does this path/method match?"
- `ReactiveAuthorizationManager`: "Is this `Authentication` allowed to perform this action in this context?"
- `SecurityWebFilterChain`: "Which WebFilters will protect requests matching this chain?"

**Never** embed ownership of Document 42 into a chain matcher and assume every endpoint in the chain is authorized. Object-level policies must still verify the exact object ID, action, tenant, and business state at the service/data layer.

## 17. Spring Boot Actuator, health, and management endpoints

Systems commonly expose `/actuator/health` for readiness/liveness probes, but its public policy differs from metrics, env, or heapdump.

A broken configuration:

```java
.authorizeExchange(ex -> ex
    .pathMatchers("/actuator/**").permitAll()
    .anyExchange().authenticated()
)
```

This can expose **every** exposed actuator endpoint publicly if no other protection layer exists.

A better design: permit only explicitly allowed health endpoints, protect metrics/prometheus/admin endpoints with dedicated authorities and network policies, and block the rest.

```java
.authorizeExchange(ex -> ex
    .pathMatchers(HttpMethod.GET, "/actuator/health")
        .permitAll()
    .pathMatchers("/actuator/**")
        .hasAuthority("ACTUATOR_ADMIN")
    .anyExchange().denyAll()
)
```

**This is a fragment** illustrating rules only. If management endpoints run on a different port/context, the main application chain's matchers may **not apply**. Spring Boot's dedicated Actuator matchers may be preferable to hardcoded paths when a custom base-path is configured; check auto-configuration, management server settings, and real tests.

Also verify that a custom `/health` path is not routed through a chain permitting all HTTP methods; a public GET health endpoint does not mean POST/DELETE on the same path should be allowed.

## 18. WebSocket, SSE, functional routing, and GraphQL

**Running in the same WebFlux app does not mean every kind of traffic is a plain REST GET.**

- **SSE/streaming:** the request opens a stream; chain selection runs when the HTTP request arrives, yet permissions can be revoked mid-stream. If real-time termination is required, enforce authorization inside the service/streaming layer.
- **WebSocket:** the handshake uses HTTP so matchers/chains participate, but individual messages after protocol upgrade need application-specific policies.
- **Functional routes (`RouterFunction`):** endpoints may lack controller annotations while still passing through the WebFlux HTTP `WebFilter` chain; test the exact URLs/methods.
- **GraphQL:** often multiplexed at `POST /graphql`; chain path matchers cannot see which resource IDs a query asks for. Resolvers, data fetchers, and services must enforce object-level authorization.
- **Gateway:** if the backend receives rewritten paths, matchers must be configured for the paths the backend sees, not only the original gateway routes.

Never treat `anyExchange().authenticated()` as sufficient for operations involving object IDs, tenant selection, or field-level permissions.

## 19. Testing with `WebTestClient`: proving which chain protects what

### 19.1. Why not test only the controller?

Using `WebTestClient.bindToController(new Controller())` without wiring Spring Security WebFilters tests business responses **without testing real chain selection**. To verify matchers, write integration tests with the application context and security support, or test isolated matchers directly with `MockServerWebExchange` for special paths/methods.

Typical setup example:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

public class ReactiveSecurityTests {
    @Autowired ApplicationContext context;
    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }
}
```

This is a **test class fragment**, requiring a test runner/config that loads the application context, real controllers, `spring-security-test`, and security dependencies. You can use `@SpringBootTest` + `@AutoConfigureWebTestClient` to set up the corresponding context if your Spring Boot project provides them.

### 19.2. Testing a Bearer JWT API

With Spring Security Test, `mockJwt()` simulates a JWT `Authentication` so you can focus on authorization:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;

client
    .mutateWith(mockJwt())
    .get()
    .uri("/api/documents/42")
    .exchange()
    .expectStatus().isOk();
```

Expect 200 only if the controller exists and object-level policy allows the fixture to read it; `mockJwt()` **does not automatically grant permission on Document 42**. Nor does it test signature/issuer/audience validation of a real token. To verify those, add Resource Server integration tests with a real JWT/decoder.

Testing a specific scope:

```java
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;

client
    .mutateWith(mockJwt().authorities(
        new SimpleGrantedAuthority("SCOPE_admin")
    ))
    .post()
    .uri("/api/admin/ping")
    .exchange()
    .expectStatus().is2xxSuccessful();
```

This is a **fragment**, requiring a real `POST /api/admin/ping` endpoint and valid fixtures; if the endpoint does not exist, the status will not be 2xx even if authorization passes. Add a control test with a JWT missing `SCOPE_admin` that gets denied and verify no side effects occurred.

### 19.3. Key chain scenarios to test

| Request | Authentication | Security outcome to verify |
| --- | --- | --- |
| `GET /api/documents` | No JWT | Challenged for authentication (typically 401) |
| `GET /api/documents` | Valid JWT | Enters API chain; authorization/object policy proceeds |
| `GET /api/admin/users` | JWT without admin authority | 403/denied per contract |
| `GET /api/admin/users` | JWT with admin authority | Not denied by admin rule |
| `GET /api/public/info` | No token | Public rule requires no authentication |
| `POST /api/public/info` | No token | Not treated as public because rule is GET-only |
| `GET /ui/home` | No Basic credentials | Challenged per UI chain authentication |
| `GET /random` | Valid token | Still DENIED by fallback |
| `OPTIONS /api/documents` | Browser preflight | Proper CORS behavior; no route mismatch |
| `/api/admin/**` | API chain placed before admin chain | Test catches shadowed admin chain |
| `GET /apix/documents` | Unauthenticated | Does not fall into API chain via prefix mistake; fallback DENY |
| `GET /api/admin` | Regular JWT | Tests path variant that may not match `/api/admin/**` as assumed |
| `GET /actuator/env` | Regular user | Does not leak management data |

**Important:** asserting only HTTP status is insufficient when the same status can originate from a controller, CORS, CSRF, or matcher. Add checks on the authentication mechanism behavior, chain-level logging/auditing (never logging secrets), or unit tests for matchers to prove which chain was selected.

### 19.4. Testing `ServerWebExchangeMatcher` directly

Use `MockServerWebExchange` and `MockServerHttpRequest` to test an individual matcher:

```java
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
import reactor.test.StepVerifier;

var matcher =
    new PathPatternParserServerWebExchangeMatcher("/api/**");

var exchange = MockServerWebExchange.from(
    MockServerHttpRequest.get("/api/documents/42")
);

StepVerifier.create(matcher.matches(exchange))
    .expectNextMatches(result -> result.isMatch())
    .verifyComplete();
```

This is a **JUnit/reactor-test fragment**, requiring a test class/method and Spring Test + Reactor Test dependencies. Since matchers return `Mono<MatchResult>`, assert `isMatch()` and any extracted path variables directly. Also test negative paths, methods, and boundary paths; testing `/api/documents/42` alone is not enough.

## 20. Standalone Java 17: simulating first-match chain selection

The following program **does not run Spring Security**; instead, it simulates ordered chain list evaluation in plain Java 17. It demonstrates that the **first selected chain decides**, rules on later chains are unused, and a fallback must match every request.

Create `WebFluxChainSelectionDemo.java`:

```java
import java.util.Comparator;
import java.util.List;
import java.util.function.Function;
import java.util.function.Predicate;

public class WebFluxChainSelectionDemo {

    record Request(String method, String path) {}

    record Chain(
        int order,
        String name,
        Predicate<Request> matches,
        Function<Request, String> rule
    ) {}

    static boolean under(String path, String prefix) {
        return path.equals(prefix) || path.startsWith(prefix + "/");
    }

    static String select(List<Chain> chains, Request request) {
        return chains.stream()
            .sorted(Comparator.comparingInt(Chain::order))
            .filter(chain -> chain.matches().test(request))
            .findFirst()
            .map(chain -> chain.name() + " -> "
                + chain.rule().apply(request))
            .orElse("NO_CHAIN -> UNPROTECTED_BY_THIS_MODEL");
    }

    public static void main(String[] args) {
        Chain admin = new Chain(
            1, "admin",
            r -> under(r.path(), "/api/admin"),
            r -> "ADMIN_JWT_REQUIRED"
        );

        Chain api = new Chain(
            2, "api",
            r -> under(r.path(), "/api"),
            r -> r.method().equals("GET")
                    && r.path().equals("/api/public/info")
                ? "PUBLIC_PERMIT"
                : "JWT_REQUIRED"
        );

        Chain ui = new Chain(
            3, "ui",
            r -> under(r.path(), "/ui"),
            r -> "BASIC_REQUIRED"
        );

        Chain fallback = new Chain(
            99, "fallback",
            r -> true,
            r -> "DENY_ALL"
        );

        List<Chain> safe = List.of(api, fallback, admin, ui);

        System.out.println("Admin: "
            + select(safe, new Request("GET", "/api/admin/users")));
        System.out.println("Public GET: "
            + select(safe, new Request("GET", "/api/public/info")));
        System.out.println("Public POST: "
            + select(safe, new Request("POST", "/api/public/info")));
        System.out.println("UI: "
            + select(safe, new Request("GET", "/ui/home")));
        System.out.println("Unknown: "
            + select(safe, new Request("GET", "/unknown")));
        System.out.println("Near-prefix: "
            + select(safe, new Request("GET", "/api-admin/data")));

        // Wrong order: broad API comes before admin.
        Chain apiFirst = new Chain(
            1, "api",
            api.matches(),
            api.rule()
        );
        Chain adminSecond = new Chain(
            2, "admin",
            admin.matches(),
            admin.rule()
        );
        System.out.println("Wrong order: "
            + select(List.of(apiFirst, adminSecond, fallback),
                new Request("GET", "/api/admin/users")));

        // No fallback: URLs outside scope are not protected by any chain.
        System.out.println("No fallback: "
            + select(List.of(admin, api, ui),
                new Request("GET", "/unknown")));
    }
}
```

Run with Java 17 or newer:

```bash
javac WebFluxChainSelectionDemo.java
java WebFluxChainSelectionDemo
```

Exact stdout:

```text
Admin: admin -> ADMIN_JWT_REQUIRED
Public GET: api -> PUBLIC_PERMIT
Public POST: api -> JWT_REQUIRED
UI: ui -> BASIC_REQUIRED
Unknown: fallback -> DENY_ALL
Near-prefix: fallback -> DENY_ALL
Wrong order: api -> JWT_REQUIRED
No fallback: NO_CHAIN -> UNPROTECTED_BY_THIS_MODEL
```

Explanation:

1. Although `safe` is listed in the order `api, fallback, admin, ui`, `select` **sorts by order**, so admin is evaluated before API.
2. `GET /api/public/info` is public in the API chain, whereas POST to the same URL requires JWT.
3. `/api-admin/data` is not treated as `/api/**` because `under` checks segment boundaries.
4. The fallback matches every request not claimed by an earlier chain and decides DENY.
5. Reversing the order sends `/api/admin/users` into the broad API chain, losing the stricter admin rule.
6. Removing the fallback leaves `/unknown` with no chain in the model—a gap to avoid whenever the app has routes outside matchers.
7. This code only models **chain selection + rule name**; it **does not perform JWT/Basic authentication, CSRF, Reactor Context, or Spring PathPattern parsing**. Real applications must test with `WebTestClient`.

## 21. Debugging and observing chain selection in production

When an endpoint unexpectedly returns 401/403, do not immediately switch to `permitAll()`. Investigate systematically:

1. Confirm whether the app is actually running WebFlux or MVC.
2. List the `SecurityWebFilterChain` beans and their `@Order`.
3. Inspect each bean's chain-level `securityMatcher`.
4. Check the path/method the server sees **after proxy rewrites**.
5. Identify the first matching chain.
6. Inside that chain, trace authorization rules in order.
7. Verify the enabled authentication mechanism, token/Basic credentials, and authority mapping.
8. Check CSRF/CORS, exception handling, and controller/handler status codes.
9. Check object-level authorization in the service/domain layer.
10. Add a regression test for the failing request.

You can enable Spring Security DEBUG logging in development with a redaction policy:

```properties
logging.level.org.springframework.security=DEBUG
```

**Never** enable TRACE or log full Authorization headers, JWTs, cookies, and sensitive details in production without a log-protection plan. Decision logs should record path templates, chain name/revision if available, action, outcome, and correlation ID—never tokens or resource contents.

### Why did a chain "disappear" after adding a bean?

Spring Boot/Spring Security auto-configuration has conditional rules that step back once an application declares its own `SecurityWebFilterChain` bean. Never guess which default chain remains: inspect the **beans actually registered** in the application context and test every endpoint. Adding one custom bean can suppress auto-configured chains you assumed were still there.

If multiple beans share the same `@Order`, ordering can become unpredictable. Assign distinct orders to overlapping matchers and write tests verifying the exact behavior.

## 22. Multi-chain security: things commonly missed

### Chain selection does not replace resource authorization

A `GET /api/documents/42` request hits the right API chain and carries a valid JWT. Yet if Document 42 belongs to Bob or another tenant, successful authentication still does not prove READ permission on that object.

You must also enforce:

```text
Valid JWT
AND matching action role/authority
AND verified tenant
AND object actually belongs to the tenant
AND (owner or valid ACL/share grant)
AND resource status permits
```

Place policies in the service/domain layer and data-scoped repository queries. GraphQL, export, streaming, and messaging paths all need proper resource checks.

### Do not try to select chains by authenticated permissions in matchers

`ServerWebExchangeMatcher` primarily classifies requests **before authentication mechanisms inside the chain run**. If you put "user has ROLE_ADMIN" inside a custom matcher, an authenticated `Authentication` may not even exist yet at that point. Keep role/claim checks inside `ReactiveAuthorizationManager` or the selected chain's service policies.

### Do not use a `permitAll` fallback chain

A fallback:

```java
@Bean
SecurityWebFilterChain fallback(ServerHttpSecurity http) {
    return http.authorizeExchange(ex -> ex
        .anyExchange().permitAll()
    ).build();
}
```

can silently expose any newly added route outside `/api/**` without anyone noticing. Unless there is an explicit public requirement, choose `denyAll` and add narrow allowlist rules as needed.

### Every chain must verify its relevant security features

When separating JWT/Basic or UI/API, review:

- CSRF behavior.
- CORS behavior.
- OAuth2 resource server / login support.
- HTTP Basic / form login.
- Session / security context repository.
- Exception handling / entry point.
- Security headers, HSTS, and HTTPS redirects (per deployment).
- Logout endpoints.
- Filter ordering and custom WebFilters.
- Tests for account lock, token expiry, issuer/audience, and revoked permissions.

Splitting chains does not automatically inherit another chain's configuration. A `denyAll` rule may block access, yet that does not guarantee another chain's headers or security filters ran.

## 23. Mandatory pre-release test matrix

### 23.1. Chain selection

| Scenario | Expected |
| --- | --- |
| Overlapping `/api/admin/**` and `/api/**` | Higher-priority chain is selected properly |
| Broad matcher placed before narrow matcher | Test catches shadowed chain bug |
| `/api/**` vs `/apix/**` | No prefix confusion |
| `/api`, `/api/`, `/api/admin` | Matches real path contract |
| GET vs POST vs PUT | Does not fall outside chain due to narrow method matcher |
| OPTIONS preflight | Correct chain and CORS behavior |
| Matches no specialized chain | Fallback `denyAll` |
| No fallback configured | Test detects unprotected route |
| New endpoint outside `/api/**` | Not automatically public |
| Uppercase / URL-encoded / double-slash routes | Handled consistently with proxy and router |

### 23.2. Authentication and authorization

| Scenario | Expected |
| --- | --- |
| Bearer-only API, missing token | Cannot access protected API |
| API token with invalid signature/issuer/audience | Not authenticated |
| Valid JWT missing scope | 403 / appropriate action denial |
| JWT with admin scope | Not blocked by admin rule; object policy still applies |
| Valid/invalid UI Basic credentials | Handled solely by UI chain |
| Public request without token | Public path works per contract |
| Public path sent with invalid token | Test authentication filter behavior; do not assume permitAll wins |
| Admin URL hitting broad API chain by mistake | Caught by regression test |
| Document belonging to another tenant | Blocked by object-level policy |
| Cookie-based mutation missing CSRF token | Denied per CSRF policy |
| Non-existent request | Do not treat 404 as proof of security |

### 23.3. Infrastructure and non-REST

- CORS origins and preflight.
- Actuator on the same port and on a separate management port.
- Proxy prefix stripping, context paths, trailing slashes.
- `RouterFunction`, GraphQL, SSE, and WebSocket handshakes.
- Reactive method security if `@EnableReactiveMethodSecurity` is present.
- Async/background work not relying on HTTP chains for domain permission checks.
- Access paths for caches, search, and file downloads.
- Multiple Spring Security/Boot versions during upgrades, API/matcher names, and Java 17 requirements.
- Test dependency `spring-security-test`, configuring `WebTestClient.apply(springSecurity())`, and JWT mocking.
- Startup tests confirming chain beans are created in order with no unexpected duplicate orders.

## 24. Common mistakes and fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Searching for `SecurityWebExchangeMatcher` | Interface does not exist under that name | Use `ServerWebExchangeMatcher` |
| Bringing Servlet `RequestMatcher` into WebFlux | Wrong API/stack type | Use reactive matchers / `ServerWebExchange` |
| Thinking `authorizeExchange().anyExchange()` applies app-wide | URLs outside chain go unprotected | Inspect chain-level matchers and add fallback |
| Putting `/api/**` chain before `/api/admin/**` | Narrow chain is shadowed | Use explicit bean `@Order` |
| Thinking DENY tries the next chain | Misunderstanding first-match logic | DENY is final inside the selected chain |
| Matching only POST on chain while forgetting GET/OPTIONS | Other methods bypass the chain | Match paths broadly, check methods at rule layer |
| Using `@Order` to reorder filters inside a chain | Does not change internal filter order | Use `SecurityWebFiltersOrder` when needed |
| Using `addFilterAt` to reorder chains | Does not affect chain selection | Order via `@Order` and `securityMatcher` |
| `permitAll` fallback | New routes accidentally become public | Use `denyAll` fallback |
| Missing fallback | Unmatched URLs may skip security | Register a match-all chain last |
| Hand-rolled `startsWith("/api")` matching | Confuses `/apix`, `/api-admin` | Use `PathPattern` matchers |
| Trusting `X-Internal` as identity | Users forge header to pick lenient chain | Use authentication / service trust boundaries |
| Calling `block()` inside a matcher | Blocks event loop, latency/deadlock issues | Use reactive non-blocking APIs |
| Using chain matchers as object authorization | IDOR/BOLA | Enforce subject-resource-action service policies |
| Disabling CSRF on all chains | Cookie-based UI becomes vulnerable to CSRF | Evaluate per chain's auth mechanism |
| Opening `/actuator/**` with `permitAll` | Exposes management endpoints | Narrow health allowlist and lock down sensitive endpoints |
| Testing controllers with `WebTestClient` without security | Does not test `WebFilterChainProxy` | Apply `springSecurity()` or test server |
| Testing only GET happy paths | Misses method/URL overlaps | Test path × method × authentication matrix |
| Using mock JWTs to claim token signature safety | Mocks do not test real decoders | Add Resource Server integration tests |
| Forgetting WebFlux vs MVC auto-selection | Config ignored at runtime | Verify application type, beans, and imports |
| Multiple chains sharing the same order | Unpredictable behavior | Use consistent orders and real tests |
| Using Servlet `SecurityFilterChain` as fallback | Does not protect WebFlux | Use reactive `SecurityWebFilterChain` |

## 25. Final checklist

1. Is the app running **WebFlux** or **Servlet MVC**?
2. Were `ServerWebExchangeMatcher` and `SecurityWebFilterChain` imported properly?
3. How many chain beans exist, and what is each chain's `@Order`?
4. Which matchers have broad scopes that could shadow narrow matchers?
5. Does each chain configure its own authentication/CSRF/CORS/headers?
6. Do all protected paths/methods match a chain?
7. Is there a **match-all + `denyAll`** fallback for remaining routes?
8. Is `securityMatcher` selecting the chain while `pathMatchers` selects the rule? Does the team distinguish the two tiers?
9. Do narrow rules precede `anyExchange` or broad `/api/**` rules?
10. Have `/api`, `/api/`, HEAD/OPTIONS, and proxy rewrites been tested?
11. Does the Bearer-only API have a clear CSRF policy and valid JWT issuer/audience?
12. Does the cookie/Basic/form-login UI have appropriate CSRF and session policies?
13. Are management/actuator paths protected even when running on a separate port?
14. Do `permitAll` public APIs still pass through authentication/security filters as expected?
15. Are custom matchers non-blocking, side-effect-free, and free of reliance on forged headers?
16. Is object-level authorization enforced after JWT/Basic authentication?
17. Are `WebTestClient` tests wired with the real Spring Security `WebFilter` chain?
18. Are there negative tests for chain overlap, missing scopes, IDOR, and CORS preflight?
19. Are logs/audits safe and able to distinguish matcher misses, auth failures, and authorization denials?
20. Does every route or chain bean change run regression tests covering the full critical matrix?

**Summary:** In Spring Security WebFlux, **`ServerWebExchangeMatcher` determines whether a request belongs to a `SecurityWebFilterChain`**. The proxy evaluates chains by `@Order` and **selects the first matching chain**; `authorizeExchange().pathMatchers(...)` rules are evaluated only **inside that chain**. Place specific matchers before general ones, add a match-all `denyAll` fallback, test both paths and HTTP methods, and enforce real resource permissions in the service/data layer. That is the key to safely separating JWT/UI/management zones without accidentally leaving any request unprotected.

## Official references

- [Spring Security — WebFlux Security, Multiple Chains Support](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): multiple `SecurityWebFilterChain` examples with `@Order` and `securityMatcher`.
- [Spring Security — Authorize ServerHttpRequest](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): `authorizeExchange`, rule ordering, `pathMatchers`, custom reactive authorization.
- [Spring Security Javadoc — ServerWebExchangeMatcher](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/util/matcher/ServerWebExchangeMatcher.html): `matches(ServerWebExchange)` and `Mono<MatchResult>`.
- [Spring Security Javadoc — ServerWebExchangeMatchers](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/util/matcher/ServerWebExchangeMatchers.html): path/method, OR, and match-all matcher factories.
- [Spring Security Javadoc — SecurityWebFilterChain](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/SecurityWebFilterChain.html): `matches` and `getWebFilters`.
- [Spring Security Javadoc — ServerHttpSecurity](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html): `securityMatcher`, `authorizeExchange`, CSRF, filters, and authentication mechanisms.
- [Spring Security — WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html): `apply(springSecurity())`.
- [Spring Security — Reactive Testing OAuth2/JWT](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockJwt` and testing scope for authentication/authorization.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): setting up a test client for WebFlux.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): service-layer permission checks using Reactor Context and method security.
